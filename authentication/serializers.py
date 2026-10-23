from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer, TokenVerifySerializer
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings

User = get_user_model()


def require_active_token_user(token):
    if not User.objects.filter(pk=token.get(api_settings.USER_ID_CLAIM), is_active=True).exists():
        raise AuthenticationFailed('Compte indisponible.')


class ActiveUserTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        require_active_token_user(RefreshToken(attrs['refresh']))
        try:
            return super().validate(attrs)
        except User.DoesNotExist as exc:
            raise AuthenticationFailed('Compte indisponible.') from exc


class ActiveUserTokenVerifySerializer(TokenVerifySerializer):
    def validate(self, attrs):
        require_active_token_user(UntypedToken(attrs['token']))
        return super().validate(attrs)


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
