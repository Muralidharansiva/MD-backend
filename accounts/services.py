import random
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import ActivityLog, LoginAttempt, NotificationLog, OTPChallenge, UserProfile
from .permissions import resolve_user_role


def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_activity(action, description, actor=None, entity_type="", entity_id=None, metadata=None):
    actor_role = resolve_user_role(actor) or ""
    return ActivityLog.objects.create(
        actor=actor,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        metadata=metadata or {},
    )


def send_business_notification(*, user=None, channel=NotificationLog.Channel.EMAIL, destination="", subject="", message="", related_booking_id=None):
    status_value = NotificationLog.Status.QUEUED

    if channel == NotificationLog.Channel.EMAIL and destination:
        try:
            send_mail(subject or "MD Studio Update", message, settings.DEFAULT_FROM_EMAIL, [destination], fail_silently=False)
            status_value = NotificationLog.Status.SENT
        except Exception:
            status_value = NotificationLog.Status.FAILED
    else:
        status_value = NotificationLog.Status.SENT

    return NotificationLog.objects.create(
        recipient=user,
        channel=channel,
        destination=destination,
        subject=subject,
        message=message,
        status=status_value,
        related_booking_id=related_booking_id,
    )


def record_login_attempt(*, login_identifier, request, successful, user=None):
    LoginAttempt.objects.create(
        login_identifier=login_identifier or "",
        user=user,
        ip_address=get_client_ip(request),
        successful=successful,
    )

    if user is None or not hasattr(user, "profile"):
        return None

    profile = user.profile
    if successful:
        profile.failed_login_attempts = 0
        profile.lockout_until = None
        profile.save(update_fields=["failed_login_attempts", "lockout_until"])
        return profile

    now = timezone.now()
    profile.failed_login_attempts += 1
    if profile.failed_login_attempts >= 5:
        profile.lockout_until = now + timedelta(minutes=15)
        profile.failed_login_attempts = 0
    profile.save(update_fields=["failed_login_attempts", "lockout_until"])
    return profile


def build_otp_code():
    return f"{random.randint(0, 999999):06d}"


def create_otp_challenge(*, purpose, delivery_target, login_identifier="", user=None, payload=None):
    OTPChallenge.objects.filter(delivery_target=delivery_target, purpose=purpose, consumed_at__isnull=True).update(consumed_at=timezone.now())
    challenge = OTPChallenge.objects.create(
        purpose=purpose,
        delivery_target=delivery_target,
        login_identifier=login_identifier,
        user=user,
        code=build_otp_code(),
        payload=payload or {},
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    return challenge


def mark_otp_used(challenge):
    challenge.consumed_at = timezone.now()
    challenge.save(update_fields=["consumed_at"])
    return challenge


def notify_booking_created(booking):
    destination = booking.user.email if booking.user and booking.user.email else f"Phone: {booking.phone}"
    message = (
        f"Your MD Studio booking for {booking.service_type} on {booking.date} at {booking.time} was created successfully. "
        f"Current status: {booking.get_status_display()}."
    )
    return send_business_notification(
        user=booking.user,
        destination=destination,
        subject="MD Studio booking created",
        message=message,
        related_booking_id=booking.id,
    )


def notify_booking_status_change(booking):
    destination = booking.user.email if booking.user and booking.user.email else f"Phone: {booking.phone}"
    message = (
        f"Your MD Studio booking for {booking.service_type} on {booking.date} at {booking.time} was updated. "
        f"New status: {booking.get_status_display()}."
    )
    return send_business_notification(
        user=booking.user,
        destination=destination,
        subject="MD Studio booking status update",
        message=message,
        related_booking_id=booking.id,
    )
