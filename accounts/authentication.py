from django.conf import settings
from rest_framework.authentication import SessionAuthentication, TokenAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed


class CookieTokenAuthentication(TokenAuthentication):
    def enforce_csrf(self, request):
        check = SessionAuthentication()
        check.enforce_csrf(request)

    def authenticate(self, request):
        header = get_authorization_header(request)
        if header:
            return None

        token_key = request.COOKIES.get(settings.AUTH_COOKIE_NAME)
        if not token_key:
            return None

        self.enforce_csrf(request)
        try:
            return self.authenticate_credentials(token_key)
        except AuthenticationFailed:
            # Treat stale or revoked cookies as an anonymous session so
            # public pages like login/register do not fail with "Invalid token."
            return None
