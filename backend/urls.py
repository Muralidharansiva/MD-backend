from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def api_root(_request):
    return JsonResponse(
        {
            "status": "ok",
            "service": "MD Studio API",
            "admin": "/admin/",
            "auth": "/api/auth/",
            "gifts": "/api/gifts/",
            "bookings": "/api/bookings/",
        }
    )


urlpatterns = [
    path("", api_root),
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/gifts/", include("gifts.urls")),
    path("api/bookings/", include("booking.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
