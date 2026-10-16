from django.core.exceptions import ValidationError


class PasswordComplexityValidator:
    def validate(self, password, user=None):
        if not any(char.isupper() for char in password) or not any(char.isdigit() for char in password):
            raise ValidationError(self.get_help_text(), code='password_complexity')

    def get_help_text(self):
        return 'Le mot de passe doit contenir au moins une majuscule et un chiffre.'
