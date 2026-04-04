from django.urls import path

from .views import (
    CsrfCookieAPIView,
    CurrentUserAPIView,
    LoginAPIView,
    LogoutAPIView,
    OTPRequestAPIView,
    OTPVerifyAPIView,
    OwnerAccessGateAPIView,
    OwnerDashboardAPIView,
    RegisterAPIView,
)

urlpatterns = [
    path("csrf/", CsrfCookieAPIView.as_view(), name="auth-csrf"),
    path("register/", RegisterAPIView.as_view(), name="auth-register"),
    path("login/", LoginAPIView.as_view(), name="auth-login"),
    path("otp/request/", OTPRequestAPIView.as_view(), name="auth-otp-request"),
    path("otp/verify/", OTPVerifyAPIView.as_view(), name="auth-otp-verify"),
    path("owner-gate/", OwnerAccessGateAPIView.as_view(), name="auth-owner-gate"),
    path("logout/", LogoutAPIView.as_view(), name="auth-logout"),
    path("me/", CurrentUserAPIView.as_view(), name="auth-me"),
    path("owner-dashboard/", OwnerDashboardAPIView.as_view(), name="auth-owner-dashboard"),
]
