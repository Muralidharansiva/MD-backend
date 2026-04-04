from rest_framework.throttling import ScopedRateThrottle


class LoginRateThrottle(ScopedRateThrottle):
    scope = "login"


class OTPRequestRateThrottle(ScopedRateThrottle):
    scope = "otp_request"


class OTPVerifyRateThrottle(ScopedRateThrottle):
    scope = "otp_verify"


class BookingWriteRateThrottle(ScopedRateThrottle):
    scope = "booking_write"


class SlotLockRateThrottle(ScopedRateThrottle):
    scope = "slot_lock"
