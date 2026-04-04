from django.contrib import admin

from .models import Booking, BookingSlotLock


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("customer_name", "service_type", "date", "time", "status", "user")
    list_filter = ("status", "date")
    search_fields = ("customer_name", "phone", "service_type", "user__username")


@admin.register(BookingSlotLock)
class BookingSlotLockAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "time", "expires_at", "created_at")
    list_filter = ("date",)
    search_fields = ("user__username", "service_type")
