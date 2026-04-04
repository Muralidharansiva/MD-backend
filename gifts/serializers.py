from rest_framework import serializers

from .models import CustomGiftOrder, Gift


class GiftSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Gift
        fields = [
            "id",
            "name",
            "category",
            "category_label",
            "price",
            "description",
            "image",
            "is_featured",
            "created_at",
        ]

    def get_image(self, obj):
        if not obj.image:
            return None
        request = self.context.get("request")
        if request is None:
            return obj.image.url
        return request.build_absolute_uri(obj.image.url)


class GiftWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gift
        fields = ["id", "name", "category", "price", "description", "image", "is_featured"]


class CustomGiftOrderSerializer(serializers.ModelSerializer):
    reference_image = serializers.ImageField(write_only=True)
    reference_image_url = serializers.SerializerMethodField(read_only=True)
    product_type_label = serializers.CharField(source="get_product_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    user_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CustomGiftOrder
        fields = [
            "id",
            "customer_name",
            "phone",
            "product_type",
            "product_type_label",
            "notes",
            "reference_image",
            "reference_image_url",
            "status",
            "status_label",
            "user_name",
            "created_at",
        ]
        read_only_fields = ["status", "status_label", "user_name", "created_at"]

    def get_reference_image_url(self, obj):
        if not obj.reference_image:
            return None
        request = self.context.get("request")
        if request is None:
            return obj.reference_image.url
        return request.build_absolute_uri(obj.reference_image.url)

    def get_user_name(self, obj):
        if obj.user:
            full_name = f"{obj.user.first_name} {obj.user.last_name}".strip()
            return full_name or obj.user.username
        return obj.customer_name


class CustomGiftOrderStatusSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = CustomGiftOrder
        fields = ["id", "status", "status_label"]
