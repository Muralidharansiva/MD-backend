from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bookings",
        null=True,
        blank=True,
    )
    customer_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    service_type = models.CharField(max_length=120)
    date = models.DateField()
    time = models.TimeField()
    brief = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    owner_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "time", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["date", "time"],
                condition=Q(status__in=["pending", "confirmed", "completed"]),
                name="unique_active_booking_slot",
            )
        ]

    def __str__(self):
        return f"{self.customer_name} - {self.service_type} on {self.date}"

    @property
    def time_label(self):
        return self.time.strftime("%I:%M %p").lstrip("0")

    def clean(self):
        exists = Booking.objects.exclude(id=self.id).filter(
            date=self.date,
            time=self.time,
            status__in=[
                Booking.Status.PENDING,
                Booking.Status.CONFIRMED,
                Booking.Status.COMPLETED,
            ],
        ).exists()
        if exists:
            raise ValidationError("This time slot is already booked.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class BookingSlotLock(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="booking_slot_locks")
    date = models.DateField()
    time = models.TimeField()
    service_type = models.CharField(max_length=120, blank=True)
    lock_token = models.UUIDField(default=uuid4, unique=True, editable=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["date", "time", "expires_at"]),
            models.Index(fields=["user", "expires_at"]),
        ]

    @property
    def is_active(self):
        return self.expires_at > timezone.now()

    def __str__(self):
        return f"Lock {self.date} {self.time} for {self.user}"

    @property
    def time_label(self):
        return self.time.strftime("%I:%M %p").lstrip("0")


