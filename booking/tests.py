from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import UserProfile
from .models import Booking, BookingSlotLock

User = get_user_model()


class BookingAPITests(APITestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(username="clientone", password="studio-pass-123", email="client@example.com")
        self.client_user.profile.role = UserProfile.Role.CLIENT
        self.client_user.profile.phone = "9876543210"
        self.client_user.profile.save()

        self.owner_user = User.objects.create_user(username="ownerone", password="owner-pass-123", email="owner@example.com")
        self.owner_user.profile.role = UserProfile.Role.OWNER
        self.owner_user.profile.can_access_owner_portal = True
        self.owner_user.profile.save()

    def csrf_headers(self):
        self.client.get(reverse("auth-csrf"))
        return {"HTTP_X_CSRFTOKEN": self.client.cookies["csrftoken"].value}

    def login_as_client(self):
        response = self.client.post(
            reverse("auth-login"),
            {"login": "clientone", "password": "studio-pass-123", "role": UserProfile.Role.CLIENT},
            format="json",
            **self.csrf_headers(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def login_as_owner(self):
        response = self.client.post(
            reverse("auth-login"),
            {"login": "ownerone", "password": "owner-pass-123", "role": UserProfile.Role.OWNER},
            format="json",
            **self.csrf_headers(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def acquire_lock(self, date_value="2026-04-18", time_value="17:30:00"):
        return self.client.post(
            reverse("booking-slot-lock"),
            {"date": date_value, "time": time_value, "service_type": "Wedding Stories"},
            format="json",
            **self.csrf_headers(),
        )

    def test_client_can_create_booking(self):
        self.login_as_client()
        lock_response = self.acquire_lock()
        self.assertEqual(lock_response.status_code, status.HTTP_201_CREATED)

        payload = {
            "customer_name": "Dinesh Kumar",
            "phone": "9876543210",
            "service_type": "Wedding Stories",
            "date": "2026-04-18",
            "time": "17:30:00",
            "brief": "Need warm editorial coverage.",
            "lock_token": lock_response.data["lock_token"],
        }

        response = self.client.post(reverse("booking-list-create"), payload, format="json", **self.csrf_headers())

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(Booking.objects.first().user, self.client_user)
        self.assertEqual(BookingSlotLock.objects.count(), 0)

    def test_same_slot_cannot_be_double_booked(self):
        Booking.objects.create(
            user=self.client_user,
            customer_name="First Client",
            phone="9999999999",
            service_type="Wedding Stories",
            date="2026-04-18",
            time="17:30:00",
        )

        another_user = User.objects.create_user(username="clienttwo", password="studio-pass-123", email="client2@example.com")
        another_user.profile.role = UserProfile.Role.CLIENT
        another_user.profile.save()

        self.client.post(
            reverse("auth-login"),
            {"login": "clienttwo", "password": "studio-pass-123", "role": UserProfile.Role.CLIENT},
            format="json",
            **self.csrf_headers(),
        )

        lock_response = self.acquire_lock()
        self.assertEqual(lock_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_owner_can_view_all_bookings(self):
        Booking.objects.create(
            user=self.client_user,
            customer_name="First Client",
            phone="9999999999",
            service_type="Portrait Session",
            date="2026-04-19",
            time="10:00:00",
        )

        self.login_as_owner()
        response = self.client.get(reverse("booking-list-create"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_availability_endpoint_marks_booked_slot(self):
        Booking.objects.create(
            user=self.client_user,
            customer_name="First Client",
            phone="9999999999",
            service_type="Portrait Session",
            date="2026-04-19",
            time="10:00:00",
        )

        response = self.client.get(reverse("booking-availability"), {"date": "2026-04-19"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        booked_slot = next(slot for slot in response.data["slots"] if slot["value"] == "10:00:00")
        self.assertTrue(booked_slot["is_booked"])
        self.assertFalse(booked_slot["is_available"])

    def test_slot_lock_prevents_other_client_from_locking_same_slot(self):
        self.login_as_client()
        first_lock = self.acquire_lock(date_value="2026-04-22", time_value="10:00:00")
        self.assertEqual(first_lock.status_code, status.HTTP_201_CREATED)

        another_user = User.objects.create_user(username="clientthree", password="studio-pass-123", email="client3@example.com")
        another_user.profile.role = UserProfile.Role.CLIENT
        another_user.profile.save()

        self.client.post(
            reverse("auth-login"),
            {"login": "clientthree", "password": "studio-pass-123", "role": UserProfile.Role.CLIENT},
            format="json",
            **self.csrf_headers(),
        )
        second_lock = self.acquire_lock(date_value="2026-04-22", time_value="10:00:00")
        self.assertEqual(second_lock.status_code, status.HTTP_409_CONFLICT)

    def test_booking_requires_valid_lock_token(self):
        self.login_as_client()
        response = self.client.post(
            reverse("booking-list-create"),
            {
                "customer_name": "Client Without Lock",
                "phone": "9876543210",
                "service_type": "Portrait Session",
                "date": "2026-04-22",
                "time": "10:00:00",
                "lock_token": "b05896e7-ef14-4d52-8fa0-86ed5d14f1d1",
            },
            format="json",
            **self.csrf_headers(),
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
