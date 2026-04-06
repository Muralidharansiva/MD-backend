from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from booking.models import Booking
from gifts.models import CustomGiftOrder, Gift

from .models import ActivityLog, NotificationLog, OTPChallenge, UserProfile
from .permissions import IsOwner, can_access_owner_portal
from .serializers import (
    ClientRegisterSerializer,
    CurrentUserSerializer,
    LoginSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
    ProfileUpdateSerializer,
)
from .services import (
    create_otp_challenge,
    log_activity,
    mark_otp_used,
    record_login_attempt,
    send_business_notification,
)
from .throttles import LoginRateThrottle, OTPRequestRateThrottle, OTPVerifyRateThrottle

User = get_user_model()


def apply_auth_cookie(response, token_key):
    cookie_kwargs = {
        "httponly": settings.AUTH_COOKIE_HTTPONLY,
        "secure": settings.AUTH_COOKIE_SECURE,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
        "path": settings.AUTH_COOKIE_PATH,
    }
    if getattr(settings, "AUTH_COOKIE_PARTITIONED", False):
        try:
            response.set_cookie(settings.AUTH_COOKIE_NAME, token_key, partitioned=True, **cookie_kwargs)
            return response
        except TypeError:
            pass
    response.set_cookie(settings.AUTH_COOKIE_NAME, token_key, **cookie_kwargs)
    return response


def delete_auth_cookie(response):
    delete_kwargs = {
        "path": settings.AUTH_COOKIE_PATH,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
    }
    if getattr(settings, "AUTH_COOKIE_PARTITIONED", False):
        try:
            response.delete_cookie(settings.AUTH_COOKIE_NAME, partitioned=True, **delete_kwargs)
            return response
        except TypeError:
            pass
    response.delete_cookie(settings.AUTH_COOKIE_NAME, **delete_kwargs)
    return response


def build_auth_response(user, message, status_code=status.HTTP_200_OK):
    token, _ = Token.objects.get_or_create(user=user)
    response = Response(
        {
            "message": message,
            "user": CurrentUserSerializer(user).data,
        },
        status=status_code,
    )
    return apply_auth_cookie(response, token.key)


def clear_auth_cookie(response):
    return delete_auth_cookie(response)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfCookieAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class RegisterAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        serializer = ClientRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        log_activity("client_registered", f"Client account created for {user.username}", actor=user, entity_type="user", entity_id=user.id)
        return build_auth_response(user, "Client account created successfully.", status.HTTP_201_CREATED)


class LoginAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        login_identifier = str(request.data.get("login", "")).strip()
        known_user = User.objects.filter(Q(username__iexact=login_identifier) | Q(email__iexact=login_identifier)).first() if login_identifier else None

        serializer = LoginSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            record_login_attempt(login_identifier=login_identifier, request=request, successful=False, user=known_user)
            raise

        user = serializer.validated_data["user"]
        record_login_attempt(login_identifier=login_identifier, request=request, successful=True, user=user)
        log_activity("user_login", f"{user.username} signed in", actor=user, entity_type="user", entity_id=user.id)
        return build_auth_response(user, "Login successful.")


class OwnerAccessGateAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        login = str(request.data.get("login", "")).strip()
        if not login:
            return Response({"login": "Username or email is required."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(Q(username__iexact=login) | Q(email__iexact=login)).first()
        if user is None or not can_access_owner_portal(user):
            return Response({"detail": "Owner access is not available for this account."}, status=status.HTTP_403_FORBIDDEN)

        approved_login = user.email if user.email and user.email.lower() == login.lower() else user.username
        return Response({"approved": True, "login": approved_login})


class OTPRequestAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestRateThrottle]
    throttle_scope = "otp_request"

    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        challenge = create_otp_challenge(
            purpose=serializer.validated_data["purpose"],
            delivery_target=serializer.validated_data["delivery_target"],
            login_identifier=serializer.validated_data.get("login_identifier", ""),
            user=serializer.validated_data.get("user"),
            payload=serializer.validated_data.get("payload", {}),
        )
        send_business_notification(
            user=challenge.user,
            destination=challenge.delivery_target,
            subject="MD Studio OTP",
            message=f"Your MD Studio OTP is {challenge.code}. It expires in 10 minutes.",
        )
        log_activity(
            "otp_requested",
            f"OTP requested for {challenge.delivery_target}",
            actor=challenge.user,
            entity_type="otp_challenge",
            entity_id=challenge.id,
            metadata={"purpose": challenge.purpose},
        )
        payload = {"message": "OTP sent successfully.", "challenge_id": challenge.id, "expires_at": challenge.expires_at}
        if settings.DEBUG or getattr(settings, "TESTING", False):
            payload["debug_code"] = challenge.code
        return Response(payload, status=status.HTTP_201_CREATED)


class OTPVerifyAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPVerifyRateThrottle]
    throttle_scope = "otp_verify"

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        challenge = serializer.validated_data["challenge"]

        if challenge.purpose == OTPChallenge.Purpose.REGISTER:
            payload = challenge.payload or {}
            user = User.objects.create(
                username=payload["username"],
                email=payload["email"],
                first_name=payload.get("first_name", ""),
                last_name=payload.get("last_name", ""),
                password=payload["password_hash"],
            )
            user.profile.role = UserProfile.Role.CLIENT
            user.profile.phone = payload.get("phone", "")
            user.profile.otp_enabled = True
            user.profile.save()
            action = "otp_register_verified"
            message = "OTP verified and account created successfully."
        else:
            user = challenge.user
            if user is None:
                return Response({"detail": "OTP user not found."}, status=status.HTTP_400_BAD_REQUEST)
            record_login_attempt(login_identifier=challenge.login_identifier, request=request, successful=True, user=user)
            action = "otp_login_verified"
            message = "OTP verified successfully."

        mark_otp_used(challenge)
        log_activity(action, f"OTP verified for {user.username}", actor=user, entity_type="otp_challenge", entity_id=challenge.id)
        return build_auth_response(user, message)


class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        log_activity("user_logout", f"{request.user.username} signed out", actor=request.user, entity_type="user", entity_id=request.user.id)
        Token.objects.filter(user=request.user).delete()
        response = Response({"message": "Logged out successfully."})
        return clear_auth_cookie(response)


class CurrentUserAPIView(APIView):
    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request):
        if not request.user or not request.user.is_authenticated:
            return Response({"authenticated": False, "user": None})
        return Response({"authenticated": True, "user": CurrentUserSerializer(request.user).data})

    def patch(self, request):
        serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        log_activity("profile_updated", f"{user.username} updated profile", actor=user, entity_type="user", entity_id=user.id)
        return Response({"message": "Profile updated successfully.", "user": CurrentUserSerializer(user).data})


class OwnerDashboardAPIView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        recent_bookings = [
            {
                "id": booking.id,
                "customer_name": booking.customer_name,
                "service_type": booking.service_type,
                "date": booking.date,
                "time": booking.time,
                "status": booking.status,
                "status_label": booking.get_status_display(),
            }
            for booking in Booking.objects.select_related("user").order_by("-created_at")[:5]
        ]
        recent_orders = [
            {
                "id": order.id,
                "customer_name": order.customer_name,
                "product_type": order.product_type,
                "product_type_label": order.get_product_type_display(),
                "status": order.status,
                "status_label": order.get_status_display(),
                "created_at": order.created_at,
            }
            for order in CustomGiftOrder.objects.select_related("user").order_by("-created_at")[:5]
        ]
        recent_clients = [
            {
                "id": client.id,
                "username": client.username,
                "full_name": f"{client.first_name} {client.last_name}".strip() or client.username,
                "email": client.email,
            }
            for client in User.objects.filter(profile__role=UserProfile.Role.CLIENT).order_by("-date_joined")[:5]
        ]
        recent_activity = [
            {
                "id": log.id,
                "action": log.action,
                "description": log.description,
                "created_at": log.created_at,
            }
            for log in ActivityLog.objects.select_related("actor").order_by("-created_at")[:8]
        ]
        recent_notifications = [
            {
                "id": notice.id,
                "channel": notice.channel,
                "destination": notice.destination,
                "status": notice.status,
                "created_at": notice.created_at,
            }
            for notice in NotificationLog.objects.order_by("-created_at")[:8]
        ]

        return Response(
            {
                "counts": {
                    "total_bookings": Booking.objects.count(),
                    "pending_bookings": Booking.objects.filter(status=Booking.Status.PENDING).count(),
                    "confirmed_bookings": Booking.objects.filter(status=Booking.Status.CONFIRMED).count(),
                    "total_gifts": Gift.objects.count(),
                    "custom_orders": CustomGiftOrder.objects.count(),
                    "active_clients": User.objects.filter(profile__role=UserProfile.Role.CLIENT).count(),
                },
                "recent_bookings": recent_bookings,
                "recent_orders": recent_orders,
                "recent_clients": recent_clients,
                "recent_activity": recent_activity,
                "recent_notifications": recent_notifications,
            }
        )

