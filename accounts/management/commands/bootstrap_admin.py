import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import UserProfile


class Command(BaseCommand):
    help = "Create or update a deploy-time Django admin account from environment variables."

    def handle(self, *args, **options):
        username = os.getenv("DEPLOY_ADMIN_USERNAME", "").strip()
        password = os.getenv("DEPLOY_ADMIN_PASSWORD", "").strip()
        email = os.getenv("DEPLOY_ADMIN_EMAIL", "").strip()
        promote_owner = os.getenv("DEPLOY_ADMIN_ENABLE_OWNER", "true").strip().lower() in {"1", "true", "yes", "on"}

        if not username or not password:
            self.stdout.write(self.style.WARNING("Skipping deploy admin bootstrap: DEPLOY_ADMIN_USERNAME or DEPLOY_ADMIN_PASSWORD not set."))
            return

        User = get_user_model()

        with transaction.atomic():
            defaults = {}
            if email:
                defaults["email"] = email

            user, created = User.objects.get_or_create(username=username, defaults=defaults)
            if email and user.email != email:
                user.email = email

            user.is_active = True
            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save()

            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = UserProfile.Role.OWNER

            if promote_owner:
                approved_owners = UserProfile.objects.filter(can_access_owner_portal=True).exclude(pk=profile.pk).count()
                if approved_owners < 3 or profile.can_access_owner_portal:
                    profile.can_access_owner_portal = True
                else:
                    self.stdout.write(self.style.WARNING("Owner portal approval skipped because 3 owner accounts are already approved."))

            profile.save()

        action = "Created" if created else "Updated"
        access = "with owner portal access" if profile.can_access_owner_portal else "without owner portal access"
        self.stdout.write(self.style.SUCCESS(f"{action} deploy admin '{username}' {access}."))
