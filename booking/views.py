from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsOwner, resolve_user_role
from accounts.services import log_activity, notify_booking_created, notify_booking_status_change
from accounts.throttles import BookingWriteRateThrottle, SlotLockRateThrottle

from .models import Booking, BookingSlotLock
from .serializers import (
    BookingSerializer,
    BookingSlotLockSerializer,
    BookingStatusUpdateSerializer,
    SLOT_END,
    SLOT_INTERVAL_MINUTES,
    SLOT_START,
    format_time_12h,
)


def cleanup_expired_locks():
    BookingSlotLock.objects.filter(expires_at__lte=timezone.now()).delete()


class BookingAvailabilityAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        cleanup_expired_locks()
        date_value = request.query_params.get("date", "").strip()
        if not date_value:
            return Response({"detail": "date query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            requested_date = datetime.strptime(date_value, "%Y-%m-%d").date()
        except ValueError:
            return Response({"detail": "Use YYYY-MM-DD for the date query parameter."}, status=status.HTTP_400_BAD_REQUEST)

        if requested_date < timezone.localdate():
            return Response({"date": requested_date, "slots": []})

        booked_times = {
            booked.strftime("%H:%M")
            for booked in Booking.objects.exclude(status=Booking.Status.CANCELLED).filter(date=requested_date).values_list("time", flat=True)
        }
        active_locks = BookingSlotLock.objects.filter(date=requested_date, expires_at__gt=timezone.now())
        locked_times = {locked.time.strftime("%H:%M") for locked in active_locks}
        my_locked_times = set()
        if request.user.is_authenticated:
            my_locked_times = {locked.time.strftime("%H:%M") for locked in active_locks.filter(user=request.user)}

        slots = []
        current = datetime.combine(requested_date, SLOT_START)
        end = datetime.combine(requested_date, SLOT_END)
        now_time = timezone.localtime().time().replace(second=0, microsecond=0)

        while current < end:
            slot_time = current.time().replace(second=0, microsecond=0)
            slot_key = current.strftime("%H:%M")

            if requested_date == timezone.localdate() and slot_time <= now_time:
                current += timedelta(minutes=SLOT_INTERVAL_MINUTES)
                continue

            is_booked = slot_key in booked_times
            is_locked = slot_key in locked_times and slot_key not in my_locked_times
            slots.append(
                {
                    "value": current.strftime("%H:%M:%S"),
                    "label": format_time_12h(slot_time),
                    "is_booked": is_booked,
                    "is_locked": is_locked,
                    "is_available": not is_booked and not is_locked,
                }
            )
            current += timedelta(minutes=SLOT_INTERVAL_MINUTES)

        return Response({"date": requested_date, "slots": slots})


class BookingSlotLockAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SlotLockRateThrottle]

    def post(self, request):
        cleanup_expired_locks()
        if resolve_user_role(request.user) != "client":
            return Response({"detail": "Only client accounts can lock slots."}, status=status.HTTP_403_FORBIDDEN)

        serializer = BookingSlotLockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lock_date = serializer.validated_data["date"]
        lock_time = serializer.validated_data["time"]

        if Booking.objects.exclude(status=Booking.Status.CANCELLED).filter(date=lock_date, time=lock_time).exists():
            return Response({"detail": "This slot is already booked."}, status=status.HTTP_400_BAD_REQUEST)

        existing_other_lock = BookingSlotLock.objects.filter(date=lock_date, time=lock_time, expires_at__gt=timezone.now()).exclude(user=request.user).first()
        if existing_other_lock:
            return Response({"detail": "This slot is temporarily locked by another client."}, status=status.HTTP_409_CONFLICT)

        BookingSlotLock.objects.filter(user=request.user, expires_at__gt=timezone.now()).exclude(date=lock_date, time=lock_time).delete()
        lock = BookingSlotLock.objects.filter(user=request.user, date=lock_date, time=lock_time, expires_at__gt=timezone.now()).first()
        if lock is None:
            lock = BookingSlotLock.objects.create(
                user=request.user,
                date=lock_date,
                time=lock_time,
                service_type=serializer.validated_data.get("service_type", ""),
                expires_at=timezone.now() + timedelta(minutes=3),
            )
        else:
            lock.service_type = serializer.validated_data.get("service_type", lock.service_type)
            lock.expires_at = timezone.now() + timedelta(minutes=3)
            lock.save(update_fields=["service_type", "expires_at"])

        log_activity(
            "slot_locked",
            f"{request.user.username} locked {lock.date} {lock.time}",
            actor=request.user,
            entity_type="booking_slot_lock",
            entity_id=lock.id,
        )
        return Response(BookingSlotLockSerializer(lock).data, status=status.HTTP_201_CREATED)


class BookingSlotLockDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, token):
        lock = BookingSlotLock.objects.filter(lock_token=token, user=request.user).first()
        if lock:
            log_activity(
                "slot_released",
                f"{request.user.username} released {lock.date} {lock.time}",
                actor=request.user,
                entity_type="booking_slot_lock",
                entity_id=lock.id,
            )
            lock.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BookingListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Booking.objects.select_related("user")
        if resolve_user_role(self.request.user) == "owner":
            return queryset.order_by("date", "time")
        return queryset.filter(user=self.request.user).order_by("date", "time")

    def get_throttles(self):
        if self.request.method == "POST":
            return [BookingWriteRateThrottle()]
        return super().get_throttles()

    def create(self, request, *args, **kwargs):
        cleanup_expired_locks()
        if resolve_user_role(request.user) != "client":
            return Response({"detail": "Only client accounts can create bookings."}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking_date = serializer.validated_data["date"]
        booking_time = serializer.validated_data["time"]
        lock_token = serializer.validated_data.get("lock_token")

        if not lock_token:
            return Response({"lock_token": ["A valid slot lock is required before booking."]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                slot_lock = BookingSlotLock.objects.select_for_update().filter(
                    lock_token=lock_token,
                    user=request.user,
                    date=booking_date,
                    time=booking_time,
                    expires_at__gt=timezone.now(),
                ).first()
                if slot_lock is None:
                    return Response({"lock_token": ["Your slot lock expired. Please select the slot again."]}, status=status.HTTP_409_CONFLICT)

                if Booking.objects.exclude(status=Booking.Status.CANCELLED).filter(date=booking_date, time=booking_time).exists():
                    slot_lock.delete()
                    return Response({"time": ["This time slot is already booked."]}, status=status.HTTP_400_BAD_REQUEST)

                booking = serializer.save(user=request.user)
                slot_lock.delete()
        except IntegrityError:
            return Response({"time": ["This time slot is already booked."]}, status=status.HTTP_400_BAD_REQUEST)

        log_activity(
            "booking_created",
            f"Booking created for {booking.customer_name} on {booking.date} at {booking.time}",
            actor=request.user,
            entity_type="booking",
            entity_id=booking.id,
            metadata={"status": booking.status},
        )
        notify_booking_created(booking)

        output = BookingSerializer(booking, context=self.get_serializer_context())
        headers = self.get_success_headers(output.data)
        return Response({"message": "Booking created successfully.", "booking": output.data}, status=status.HTTP_201_CREATED, headers=headers)


class OwnerBookingStatusUpdateAPIView(generics.UpdateAPIView):
    queryset = Booking.objects.select_related("user")
    serializer_class = BookingStatusUpdateSerializer
    permission_classes = [IsOwner]

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        response = super().update(request, *args, **kwargs)
        booking = self.get_object()
        log_activity(
            "booking_status_updated",
            f"Booking {booking.id} updated to {booking.status}",
            actor=request.user,
            entity_type="booking",
            entity_id=booking.id,
            metadata={"status": booking.status},
        )
        notify_booking_status_change(booking)
        return response


