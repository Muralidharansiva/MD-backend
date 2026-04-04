from rest_framework.permissions import BasePermission

from .models import UserProfile


OWNER_ROLE = UserProfile.Role.OWNER
CLIENT_ROLE = UserProfile.Role.CLIENT


def resolve_user_role(user):
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser or user.is_staff:
        return OWNER_ROLE
    profile = getattr(user, "profile", None)
    if profile:
        return profile.role
    return None


def can_access_owner_portal(user):
    if not user or not user.is_authenticated:
        return False
    profile = getattr(user, "profile", None)
    if profile is None:
        return False
    return resolve_user_role(user) == OWNER_ROLE and profile.can_access_owner_portal


class IsOwner(BasePermission):
    def has_permission(self, request, view):
        return can_access_owner_portal(request.user)


class IsClient(BasePermission):
    def has_permission(self, request, view):
        return resolve_user_role(request.user) == CLIENT_ROLE
