from rest_framework import serializers


class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError('Mot de passe incorrect.')
        return value
