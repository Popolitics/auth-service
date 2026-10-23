import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .emails import send_password_reset_email

User = get_user_model()
logger = logging.getLogger(__name__)

INVALID_RESET_LINK = 'Lien de réinitialisation invalide ou expiré.'


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def save(self, **kwargs):
        # Always succeeds silently so the endpoint does not reveal which emails have an account.
        user = User.objects.filter(email__iexact=self.validated_data['email'].strip(), is_active=True).first()
        if user is None or not user.has_usable_password():
            return
        try:
            send_password_reset_email(user)
        except OSError:  # smtplib errors and connection failures
            logger.exception('Password reset email could not be sent (user %s)', user.pk)


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(write_only=True)
    token = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(attrs['uid'])), is_active=True)
        except (TypeError, ValueError, OverflowError, ValidationError, User.DoesNotExist):
            user = None
        if user is None or not default_token_generator.check_token(user, attrs['token']):
            raise serializers.ValidationError({'token': INVALID_RESET_LINK})
        try:
            validate_password(attrs['new_password'], user)
        except ValidationError as exc:
            raise serializers.ValidationError({'new_password': exc.messages}) from exc
        attrs['user'] = user
        return attrs

    def save(self, **kwargs):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=self.validated_data['user'].pk)
            if not default_token_generator.check_token(user, self.validated_data['token']):
                raise serializers.ValidationError({'token': INVALID_RESET_LINK})
            user.set_password(self.validated_data['new_password'])
            user.save(update_fields=['password'])
            # Revoke every open session: whoever knew the old password must not stay logged in.
            for token in OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True):
                BlacklistedToken.objects.get_or_create(token=token)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)

    def validate_refresh(self, value):
        try:
            token = RefreshToken(value)
        except TokenError as exc:
            raise serializers.ValidationError('Refresh token invalide ou expiré.') from exc
        user_id = getattr(self.context['request'].user, api_settings.USER_ID_FIELD)
        if str(token.get(api_settings.USER_ID_CLAIM)) != str(user_id):
            raise serializers.ValidationError('Ce token ne correspond pas au compte connecté.')
        return token

    def save(self, **kwargs):
        self.validated_data['refresh'].blacklist()

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        token['email'] = user.email
        token['username'] = user.username
        token['is_staff'] = user.is_staff

        return token


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Un compte utilise déjà cet email.')
        return value

    def validate(self, attrs):
        try:
            validate_password(attrs['password'], User(email=attrs['email'], username=attrs.get('username')))
        except ValidationError as exc:
            raise serializers.ValidationError({'password': exc.messages}) from exc
        return attrs

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password')

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return User.objects.create_user(**validated_data)
        except IntegrityError as exc:
            if User.objects.filter(email__iexact=validated_data['email']).exists():
                raise serializers.ValidationError({'email': 'Un compte utilise déjà cet email.'}) from exc
            raise
