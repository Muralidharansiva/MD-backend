from django.contrib import admin

from .models import ActivityLog, LoginAttempt, NotificationLog, OTPChallenge, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "role",
        "can_access_owner_portal",
        "otp_enabled",
        "failed_login_attempts",
        "lockout_until",
        "phone",
        "created_at",
    )
    list_filter = ("role", "can_access_owner_portal", "otp_enabled")
    search_fields = ("user__username", "user__email", "phone")


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("login_identifier", "user", "successful", "ip_address", "created_at")
    list_filter = ("successful",)
    search_fields = ("login_identifier", "user__username", "user__email", "ip_address")
    readonly_fields = ("created_at",)


@admin.register(OTPChallenge)
class OTPChallengeAdmin(admin.ModelAdmin):
    list_display = ("delivery_target", "purpose", "user", "expires_at", "consumed_at", "created_at")
    list_filter = ("purpose", "consumed_at")
    search_fields = ("delivery_target", "login_identifier", "user__username", "user__email")
    readonly_fields = ("created_at",)


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("action", "actor", "actor_role", "entity_type", "entity_id", "created_at")
    list_filter = ("action", "actor_role", "entity_type")
    search_fields = ("description", "actor__username", "entity_type")
    readonly_fields = ("created_at",)


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("channel", "destination", "status", "related_booking_id", "created_at")
    list_filter = ("channel", "status")
    search_fields = ("destination", "subject", "message")
    readonly_fields = ("created_at",)
