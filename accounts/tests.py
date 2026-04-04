from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import OTPChallenge, UserProfile

User = get_user_model()


class AuthAPITests(APITestCase):
    def test_client_can_register_and_receive_auth_cookie(self):
        payload = {
            "username": "clientone",
            "email": "client@example.com",
            "password": "studio-pass-123",
            "first_name": "Client",
            "last_name": "One",
            "phone": "9876543210",
        }

        response = self.client.post(reverse("auth-register"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("token", response.data)
        self.assertEqual(response.data["user"]["role"], UserProfile.Role.CLIENT)
        self.assertIn("mdstudio_auth", response.cookies)

    def test_public_auth_routes_ignore_stale_invalid_cookie(self):
        self.client.cookies["mdstudio_auth"] = "stale-invalid-token"

        response = self.client.get(reverse("auth-me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["authenticated"], False)

    def test_client_can_login_with_client_role(self):
        client = User.objects.create_user(username="clientlogin", email="clientlogin@example.com", password="studio-pass-123")
        client.profile.role = UserProfile.Role.CLIENT
        client.profile.phone = "9876543210"
        client.profile.save()

        response = self.client.post(
            reverse("auth-login"),
            {"login": "clientlogin", "password": "studio-pass-123", "role": UserProfile.Role.CLIENT},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["role"], UserProfile.Role.CLIENT)
        self.assertIn("mdstudio_auth", response.cookies)

    def test_duplicate_username_is_rejected_for_client_registration(self):
        User.objects.create_user(username="duplicateuser", email="first@example.com", password="studio-pass-123")

        response = self.client.post(
            reverse("auth-register"),
            {
                "username": "duplicateuser",
                "email": "second@example.com",
                "password": "studio-pass-123",
                "first_name": "Client",
                "last_name": "Two",
                "phone": "9876543211",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)

    def test_owner_access_gate_allows_only_approved_owner(self):
        owner = User.objects.create_user(username="ownerone", email="owner@example.com", password="owner-pass-123")
        owner.profile.role = UserProfile.Role.OWNER
        owner.profile.can_access_owner_portal = True
        owner.profile.save()

        response = self.client.post(reverse("auth-owner-gate"), {"login": "ownerone"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["approved"])

    def test_owner_access_gate_denies_unapproved_owner(self):
        owner = User.objects.create_user(username="ownerblocked", email="blocked@example.com", password="owner-pass-123")
        owner.profile.role = UserProfile.Role.OWNER
        owner.profile.can_access_owner_portal = False
        owner.profile.save()

        response = self.client.post(reverse("auth-owner-gate"), {"login": "ownerblocked"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("detail", response.data)

    def test_owner_can_login_from_owner_role_when_approved(self):
        owner = User.objects.create_user(username="ownerone-login", email="ownerlogin@example.com", password="owner-pass-123")
        owner.profile.role = UserProfile.Role.OWNER
        owner.profile.can_access_owner_portal = True
        owner.profile.save()

        response = self.client.post(
            reverse("auth-login"),
            {"login": "ownerone-login", "password": "owner-pass-123", "role": UserProfile.Role.OWNER},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["role"], UserProfile.Role.OWNER)
        self.assertTrue(response.data["user"]["can_access_owner_portal"])
        self.assertIn("mdstudio_auth", response.cookies)

    def test_unapproved_owner_cannot_login_to_owner_portal(self):
        owner = User.objects.create_user(username="ownerblocked-login", email="blockedlogin@example.com", password="owner-pass-123")
        owner.profile.role = UserProfile.Role.OWNER
        owner.profile.can_access_owner_portal = False
        owner.profile.save()

        response = self.client.post(
            reverse("auth-login"),
            {"login": "ownerblocked-login", "password": "owner-pass-123", "role": UserProfile.Role.OWNER},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data)

    def test_authenticated_client_can_update_profile(self):
        user = User.objects.create_user(username="clientupdate", email="clientupdate@example.com", password="studio-pass-123")
        user.profile.role = UserProfile.Role.CLIENT
        user.profile.phone = "9999999999"
        user.profile.save()
        token = Token.objects.create(user=user)
        self.client.cookies["mdstudio_auth"] = token.key
        self.client.get(reverse("auth-csrf"))

        response = self.client.patch(
            reverse("auth-me"),
            {"first_name": "Updated", "last_name": "Client", "phone": "9876543210"},
            format="json",
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Updated")
        self.assertEqual(user.profile.phone, "9876543210")

    def test_logout_clears_auth_cookie(self):
        user = User.objects.create_user(username="clientlogout", email="logout@example.com", password="studio-pass-123")
        user.profile.role = UserProfile.Role.CLIENT
        user.profile.save()
        token = Token.objects.create(user=user)
        self.client.cookies["mdstudio_auth"] = token.key
        self.client.get(reverse("auth-csrf"))

        response = self.client.post(reverse("auth-logout"), {}, format="json", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.cookies["mdstudio_auth"].value, "")
        self.assertFalse(Token.objects.filter(user=user).exists())

    def test_failed_login_attempts_trigger_lockout(self):
        user = User.objects.create_user(username="lockme", email="lockme@example.com", password="studio-pass-123")
        user.profile.role = UserProfile.Role.CLIENT
        user.profile.save()

        for _ in range(5):
            response = self.client.post(
                reverse("auth-login"),
                {"login": "lockme", "password": "wrong-pass", "role": UserProfile.Role.CLIENT},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        user.profile.refresh_from_db()
        self.assertIsNotNone(user.profile.lockout_until)

    def test_can_request_and_verify_login_otp(self):
        user = User.objects.create_user(username="otpclient", email="otp@example.com", password="studio-pass-123")
        user.profile.role = UserProfile.Role.CLIENT
        user.profile.save()

        request_response = self.client.post(
            reverse("auth-otp-request"),
            {"purpose": OTPChallenge.Purpose.LOGIN, "login": "otpclient", "role": UserProfile.Role.CLIENT},
            format="json",
        )
        self.assertEqual(request_response.status_code, status.HTTP_201_CREATED)

        verify_response = self.client.post(
            reverse("auth-otp-verify"),
            {"challenge_id": request_response.data["challenge_id"], "code": request_response.data["debug_code"]},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertIn("mdstudio_auth", verify_response.cookies)

    def test_can_request_and_verify_register_otp(self):
        request_response = self.client.post(
            reverse("auth-otp-request"),
            {
                "purpose": OTPChallenge.Purpose.REGISTER,
                "username": "otpnewclient",
                "email": "otpnew@example.com",
                "password": "studio-pass-123",
                "first_name": "OTP",
                "last_name": "Client",
                "phone": "9876543210",
            },
            format="json",
        )
        self.assertEqual(request_response.status_code, status.HTTP_201_CREATED)

        verify_response = self.client.post(
            reverse("auth-otp-verify"),
            {"challenge_id": request_response.data["challenge_id"], "code": request_response.data["debug_code"]},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertTrue(User.objects.filter(username="otpnewclient").exists())
