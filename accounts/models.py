from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    class Role(models.TextChoices):
        CLIENT = "client", "Client"
        OWNER = "owner", "Owner"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CLIENT)
    phone = models.CharField(max_length=20, blank=True)
    can_access_owner_portal = models.BooleanField(default=False)
    otp_enabled = models.BooleanField(default=False)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    lockout_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__username"]

    def clean(self):
        if self.can_access_owner_portal:
            approved_owner_count = UserProfile.objects.filter(can_access_owner_portal=True).exclude(pk=self.pk).count()
            if approved_owner_count >= 3:
                raise ValidationError({"can_access_owner_portal": "Only 3 accounts can be approved for owner login."})

    @property
    def is_locked_out(self):
        return bool(self.lockout_until and self.lockout_until > timezone.now())

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


class LoginAttempt(models.Model):
    login_identifier = models.CharField(max_length=255)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="login_attempts")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    successful = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["login_identifier", "-created_at"]),
            models.Index(fields=["ip_address", "-created_at"]),
        ]

    def __str__(self):
        result = "success" if self.successful else "failed"
        return f"{self.login_identifier} ({result})"


class OTPChallenge(models.Model):
    class Purpose(models.TextChoices):
        LOGIN = "login", "Login"
        REGISTER = "register", "Register"

    login_identifier = models.CharField(max_length=255, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="otp_challenges")
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    delivery_target = models.CharField(max_length=255)
    code = models.CharField(max_length=6)
    payload = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["purpose", "delivery_target", "-created_at"]),
        ]

    @property
    def is_active(self):
        return self.consumed_at is None and self.expires_at > timezone.now()

    def __str__(self):
        return f"{self.get_purpose_display()} OTP for {self.delivery_target}"


class ActivityLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_logs")
    actor_role = models.CharField(max_length=20, blank=True)
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=50, blank=True)
    entity_id = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["entity_type", "entity_id"]),
        ]

    def __str__(self):
        return f"{self.action} @ {self.created_at:%Y-%m-%d %H:%M}"


class NotificationLog(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="notification_logs")
    channel = models.CharField(max_length=20, choices=Channel.choices)
    destination = models.CharField(max_length=255)
    subject = models.CharField(max_length=255, blank=True)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    related_booking_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["channel", "status", "-created_at"])]

    def __str__(self):
        return f"{self.get_channel_display()} to {self.destination} ({self.status})"
