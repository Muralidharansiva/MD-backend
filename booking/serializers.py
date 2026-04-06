from datetime import datetime, time, timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import Booking, BookingSlotLock

SLOT_INTERVAL_MINUTES = 30
SLOT_START = time(hour=10, minute=0)
SLOT_END = time(hour=19, minute=0)
LOCK_DURATION_MINUTES = 3


def generate_slot_values():
    slots = []
    current = datetime.combine(timezone.localdate(), SLOT_START)
    end = datetime.combine(timezone.localdate(), SLOT_END)
    while current < end:
        slots.append(current.time().replace(second=0, microsecond=0))
        current += timedelta(minutes=SLOT_INTERVAL_MINUTES)
    return slots


VALID_SLOT_VALUES = {slot.strftime("%H:%M:%S") for slot in generate_slot_values()}


def format_time_12h(value):
    return value.strftime("%I:%M %p").lstrip("0")


class BookingSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    user_name = serializers.SerializerMethodField(read_only=True)
    time_label = serializers.CharField(read_only=True)
    lock_token = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = Booking
        validators = []
        fields = [
            "id",
            "user_name",
            "customer_name",
            "phone",
            "service_type",
            "date",
            "time",
            "time_label",
            "brief",
            "status",
            "status_label",
            "owner_notes",
            "created_at",
            "lock_token",
        ]
        read_only_fields = ["status", "status_label", "owner_notes", "created_at", "user_name", "time_label"]

    def get_user_name(self, obj):
        if obj.user:
            full_name = f"{obj.user.first_name} {obj.user.last_name}".strip()
            return full_name or obj.user.username
        return obj.customer_name

    def validate_phone(self, value):
        value = value.strip()
        if not value or not value.isdigit() or len(value) < 10 or len(value) > 15:
            raise serializers.ValidationError("Enter a valid phone number.")
        return value

    def validate_service_type(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("Service name must be at least 3 characters.")
        return value

    def validate_time(self, value):
        if value.strftime("%H:%M:%S") not in VALID_SLOT_VALUES:
            raise serializers.ValidationError("Choose a valid 30-minute studio slot.")
        return value

    def validate(self, attrs):
        booking_date = attrs.get("date") or getattr(self.instance, "date", None)
        booking_time = attrs.get("time") or getattr(self.instance, "time", None)
        today = timezone.localdate()
        now_time = timezone.localtime().time().replace(second=0, microsecond=0)

        if booking_date and booking_date < today:
            raise serializers.ValidationError({"date": "Please select today or a future date."})

        if booking_date == today and booking_time and booking_time <= now_time:
            raise serializers.ValidationError({"time": "You cannot book a past time slot."})

        if booking_date and booking_time:
            queryset = Booking.objects.exclude(status=Booking.Status.CANCELLED).filter(date=booking_date, time=booking_time)
            if self.instance is not None:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError({"time": "This time slot is already booked."})

        return attrs

    def create(self, validated_data):
        validated_data.pop("lock_token", None)
        return super().create(validated_data)


class BookingSlotLockSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingSlotLock
        fields = ["id", "date", "time", "service_type", "lock_token", "expires_at"]
        read_only_fields = ["id", "lock_token", "expires_at"]

    def validate_time(self, value):
        if value.strftime("%H:%M:%S") not in VALID_SLOT_VALUES:
            raise serializers.ValidationError("Choose a valid 30-minute studio slot.")
        return value

    def validate(self, attrs):
        lock_date = attrs.get("date")
        lock_time = attrs.get("time")
        today = timezone.localdate()
        now_time = timezone.localtime().time().replace(second=0, microsecond=0)

        if lock_date < today:
            raise serializers.ValidationError({"date": "Please select today or a future date."})
        if lock_date == today and lock_time <= now_time:
            raise serializers.ValidationError({"time": "You cannot lock a past time slot."})
        return attrs


class BookingStatusUpdateSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Booking
        fields = ["id", "status", "status_label", "owner_notes"]

