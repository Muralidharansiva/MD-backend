from django.db.models import Q
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsOwner, resolve_user_role

from .models import CustomGiftOrder, Gift
from .serializers import CustomGiftOrderSerializer, CustomGiftOrderStatusSerializer, GiftSerializer, GiftWriteSerializer


class GiftListAPIView(generics.ListAPIView):
    serializer_class = GiftSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = Gift.objects.all().order_by("name")
        search = self.request.query_params.get("search", "").strip()
        category = self.request.query_params.get("category", "").strip()

        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))

        if category:
            queryset = queryset.filter(category=category)

        return queryset


class OwnerGiftListCreateAPIView(generics.ListCreateAPIView):
    queryset = Gift.objects.all().order_by("name")
    permission_classes = [IsOwner]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return GiftWriteSerializer
        return GiftSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        gift = serializer.save()
        response_serializer = GiftSerializer(gift, context={"request": request})
        return Response(
            {"message": "Gift item created successfully.", "gift": response_serializer.data},
            status=status.HTTP_201_CREATED,
        )


class OwnerGiftDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Gift.objects.all().order_by("name")
    permission_classes = [IsOwner]

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return GiftWriteSerializer
        return GiftSerializer


class CustomGiftOrderListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = CustomGiftOrderSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = CustomGiftOrder.objects.select_related("user")
        if resolve_user_role(self.request.user) == "owner":
            return queryset
        return queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(user=user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        return Response(
            {
                "message": "Custom gift request received successfully.",
                "order": serializer.data,
            },
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(serializer.data),
        )


class CustomGiftOrderStatusUpdateAPIView(generics.UpdateAPIView):
    queryset = CustomGiftOrder.objects.select_related("user")
    serializer_class = CustomGiftOrderStatusSerializer
    permission_classes = [IsOwner]

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)
