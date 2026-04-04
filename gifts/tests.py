from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import UserProfile
from .models import CustomGiftOrder, Gift

User = get_user_model()


class GiftAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="ownergift", password="owner-pass-123", email="ownergift@example.com")
        self.owner.profile.role = UserProfile.Role.OWNER
        self.owner.profile.can_access_owner_portal = True
        self.owner.profile.save()
        self.owner_token = Token.objects.create(user=self.owner)

        self.client_user = User.objects.create_user(username="giftclient", password="studio-pass-123", email="giftclient@example.com")
        self.client_user.profile.role = UserProfile.Role.CLIENT
        self.client_user.profile.save()
        self.client_token = Token.objects.create(user=self.client_user)

        Gift.objects.create(name="Gallery Frame", category=Gift.Category.FRAMES, price="1899.00", description="Frame gift")
        Gift.objects.create(name="Story Album", category=Gift.Category.ALBUMS, price="4200.00", description="Album gift")

    def test_public_gift_list_supports_category_filter(self):
        response = self.client.get(reverse("gift-list"), {"category": Gift.Category.ALBUMS})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Story Album")

    def test_owner_can_create_gift_item(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.owner_token.key}")
        response = self.client.post(
            reverse("gift-manage-list-create"),
            {
                "name": "Signature Mug",
                "category": Gift.Category.MUGS,
                "price": "799.00",
                "description": "Mug gift",
                "is_featured": True,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Gift.objects.filter(name="Signature Mug").count(), 1)

    def test_authenticated_client_custom_order_is_attached_to_user(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.client_token.key}")
        image = SimpleUploadedFile("preview.gif", b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;", content_type="image/gif")

        response = self.client.post(
            reverse("custom-gift-order-list-create"),
            {
                "customer_name": "Gift Client",
                "phone": "9876543210",
                "product_type": "frame",
                "notes": "Please use the uploaded photo.",
                "reference_image": image,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CustomGiftOrder.objects.count(), 1)
        self.assertEqual(CustomGiftOrder.objects.first().user, self.client_user)
