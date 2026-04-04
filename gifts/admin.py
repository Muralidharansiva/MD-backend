from django.contrib import admin

from .models import CustomGiftOrder, Gift


@admin.register(Gift)
class GiftAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "is_featured", "updated_at")
    list_filter = ("category", "is_featured")
    search_fields = ("name", "description")


@admin.register(CustomGiftOrder)
class CustomGiftOrderAdmin(admin.ModelAdmin):
    list_display = ("customer_name", "product_type", "status", "phone", "created_at")
    list_filter = ("status", "product_type")
    search_fields = ("customer_name", "phone", "notes")
