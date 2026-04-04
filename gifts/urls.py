from django.urls import path

from .views import CustomGiftOrderListCreateAPIView, CustomGiftOrderStatusUpdateAPIView, GiftListAPIView, OwnerGiftDetailAPIView, OwnerGiftListCreateAPIView

urlpatterns = [
    path("", GiftListAPIView.as_view(), name="gift-list"),
    path("manage/", OwnerGiftListCreateAPIView.as_view(), name="gift-manage-list-create"),
    path("manage/<int:pk>/", OwnerGiftDetailAPIView.as_view(), name="gift-manage-detail"),
    path("custom-orders/", CustomGiftOrderListCreateAPIView.as_view(), name="custom-gift-order-list-create"),
    path("custom-orders/<int:pk>/status/", CustomGiftOrderStatusUpdateAPIView.as_view(), name="custom-gift-order-status-update"),
]
