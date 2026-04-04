from django.conf import settings
from django.db import models


class Gift(models.Model):
    class Category(models.TextChoices):
        FRAMES = "frames", "Frames"
        ALBUMS = "albums", "Albums"
        MUGS = "mugs", "Mugs"
        DESK = "desk", "Desk Gifts"
        PRINTS = "prints", "Prints"

    name = models.CharField(max_length=150)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.FRAMES)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="gifts/", blank=True, null=True)
    is_featured = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CustomGiftOrder(models.Model):
    class ProductType(models.TextChoices):
        FRAME = "frame", "Photo Frame"
        MUG = "mug", "Photo Mug"
        ALBUM = "album", "Photo Album"

    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In Progress"
        READY = "ready", "Ready"
        DELIVERED = "delivered", "Delivered"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="custom_gift_orders")
    customer_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    product_type = models.CharField(max_length=20, choices=ProductType.choices)
    notes = models.TextField(blank=True)
    reference_image = models.ImageField(upload_to="custom-orders/")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer_name} - {self.get_product_type_display()}"
