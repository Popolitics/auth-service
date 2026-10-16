from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

User = get_user_model()

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
