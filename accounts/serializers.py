from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import make_password
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from .models import OTPChallenge, UserProfile
from .permissions import can_access_owner_portal, resolve_user_role

User = get_user_model()


class CurrentUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    can_access_owner_portal = serializers.SerializerMethodField()
    otp_enabled = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "phone",
            "can_access_owner_portal",
            "otp_enabled",
        ]

    def get_full_name(self, obj):
        full_name = f"{obj.first_name} {obj.last_name}".strip()
        return full_name or obj.username

    def get_role(self, obj):
        return resolve_user_role(obj)

    def get_phone(self, obj):
        profile = getattr(obj, "profile", None)
        return profile.phone if profile else ""

    def get_can_access_owner_portal(self, obj):
        return can_access_owner_portal(obj)

    def get_otp_enabled(self, obj):
        profile = getattr(obj, "profile", None)
        return profile.otp_enabled if profile else False


class ProfileUpdateSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "phone"]

    def validate_email(self, value):
        user = self.instance
        if User.objects.filter(email__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_phone(self, value):
        if value and (not value.isdigit() or len(value) < 10 or len(value) > 15):
            raise serializers.ValidationError("Enter a valid phone number.")
        return value

    def update(self, instance, validated_data):
        phone = validated_data.pop("phone", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        if phone is not None:
            instance.profile.phone = phone
            instance.profile.save()

        return instance


class ClientRegisterSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(max_length=20, write_only=True)
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["username", "email", "password", "first_name", "last_name", "phone"]

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("An account with this username already exists.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_phone(self, value):
        if not value.isdigit() or len(value) < 10 or len(value) > 15:
            raise serializers.ValidationError("Enter a valid phone number.")
        return value

    def create(self, validated_data):
        phone = validated_data.pop("phone", "")
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        user.profile.role = UserProfile.Role.CLIENT
        user.profile.phone = phone
        user.profile.save()
        return user


class LoginSerializer(serializers.Serializer):
    login = serializers.CharField()
    password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=UserProfile.Role.choices)

    def validate(self, attrs):
        login = attrs["login"].strip()
        password = attrs["password"]
        expected_role = attrs["role"]

        if not login:
            raise serializers.ValidationError({"login": "Username or email is required."})

        user = User.objects.filter(Q(username__iexact=login) | Q(email__iexact=login)).first()
        if user is None:
            raise serializers.ValidationError({"login": "Account not found."})

        profile = getattr(user, "profile", None)
        if profile and profile.lockout_until and profile.lockout_until > timezone.now():
            raise serializers.ValidationError({"detail": "Too many failed login attempts. Please try again later."})

        authenticated_user = authenticate(username=user.username, password=password)
        if authenticated_user is None:
            raise serializers.ValidationError({"password": "Invalid password."})

        actual_role = resolve_user_role(authenticated_user)
        if actual_role != expected_role:
            raise serializers.ValidationError({"role": "This account does not have access to the selected login role."})

        if expected_role == UserProfile.Role.OWNER and not can_access_owner_portal(authenticated_user):
            raise serializers.ValidationError({"role": "This owner account is not approved for owner login."})

        attrs["user"] = authenticated_user
        return attrs


class OTPRequestSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=OTPChallenge.Purpose.choices)
    role = serializers.ChoiceField(choices=UserProfile.Role.choices, required=False)
    login = serializers.CharField(required=False, allow_blank=True)
    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(required=False, allow_blank=True, write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        purpose = attrs["purpose"]

        if purpose == OTPChallenge.Purpose.LOGIN:
            login = attrs.get("login", "").strip()
            role = attrs.get("role")
            if not login or not role:
                raise serializers.ValidationError({"detail": "Login and role are required for OTP login."})
            user = User.objects.filter(Q(username__iexact=login) | Q(email__iexact=login)).first()
            if user is None:
                raise serializers.ValidationError({"login": "Account not found."})
            if resolve_user_role(user) != role:
                raise serializers.ValidationError({"role": "This account does not match the selected role."})
            if role == UserProfile.Role.OWNER and not can_access_owner_portal(user):
                raise serializers.ValidationError({"role": "This owner account is not approved for owner login."})
            if getattr(user, "profile", None) and user.profile.lockout_until and user.profile.lockout_until > timezone.now():
                raise serializers.ValidationError({"detail": "Too many failed login attempts. Please try again later."})
            attrs["user"] = user
            attrs["delivery_target"] = user.email or login
            attrs["login_identifier"] = login
            return attrs

        required_fields = ["username", "email", "password", "first_name", "phone"]
        missing = [field for field in required_fields if not str(attrs.get(field, "")).strip()]
        if missing:
            raise serializers.ValidationError({"detail": f"Missing required fields for OTP registration: {', '.join(missing)}."})
        if User.objects.filter(username__iexact=attrs["username"]).exists():
            raise serializers.ValidationError({"username": "An account with this username already exists."})
        if User.objects.filter(email__iexact=attrs["email"]).exists():
            raise serializers.ValidationError({"email": "An account with this email already exists."})
        if not attrs["phone"].isdigit() or len(attrs["phone"]) < 10 or len(attrs["phone"]) > 15:
            raise serializers.ValidationError({"phone": "Enter a valid phone number."})
        attrs["delivery_target"] = attrs["email"]
        attrs["payload"] = {
            "username": attrs["username"],
            "email": attrs["email"],
            "password_hash": make_password(attrs["password"]),
            "first_name": attrs.get("first_name", ""),
            "last_name": attrs.get("last_name", ""),
            "phone": attrs.get("phone", ""),
        }
        return attrs


class OTPVerifySerializer(serializers.Serializer):
    challenge_id = serializers.IntegerField()
    code = serializers.CharField(max_length=6)

    def validate(self, attrs):
        challenge = OTPChallenge.objects.filter(id=attrs["challenge_id"]).first()
        if challenge is None:
            raise serializers.ValidationError({"detail": "OTP challenge not found."})
        if challenge.consumed_at is not None:
            raise serializers.ValidationError({"detail": "OTP has already been used."})
        if challenge.expires_at <= timezone.now():
            raise serializers.ValidationError({"detail": "OTP has expired."})
        if challenge.code != attrs["code"]:
            raise serializers.ValidationError({"code": "Invalid OTP code."})
        attrs["challenge"] = challenge
        return attrs
