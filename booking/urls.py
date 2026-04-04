from django.urls import path

from .views import (
    BookingAvailabilityAPIView,
    BookingListCreateAPIView,
    BookingSlotLockAPIView,
    BookingSlotLockDetailAPIView,
    OwnerBookingStatusUpdateAPIView,
)

urlpatterns = [
    path("", BookingListCreateAPIView.as_view(), name="booking-list-create"),
    path("availability/", BookingAvailabilityAPIView.as_view(), name="booking-availability"),
    path("locks/", BookingSlotLockAPIView.as_view(), name="booking-slot-lock"),
    path("locks/<uuid:token>/", BookingSlotLockDetailAPIView.as_view(), name="booking-slot-lock-detail"),
    path("<int:pk>/status/", OwnerBookingStatusUpdateAPIView.as_view(), name="booking-status-update"),
]
