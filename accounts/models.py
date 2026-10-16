import uuid
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.db.models.functions import Lower


class UserManager(DjangoUserManager):
    def create_user(self, username=None, email=None, password=None, **extra_fields):
        if not email:
            raise ValueError("L'email est obligatoire.")
        return super().create_user(username, email.strip().lower(), password, **extra_fields)

    def create_superuser(self, username=None, email=None, password=None, **extra_fields):
        if not email:
            raise ValueError("L'email est obligatoire.")
        return super().create_superuser(username, email.strip().lower(), password, **extra_fields)

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email.strip())

    def _create_user(self, username, email, password, **extra_fields):
        # Django's default manager rejects an empty username.
        user = self.model(username=self.model.normalize_username(username) or None,
                          email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

class User(AbstractUser):
    username = models.CharField(max_length=150, unique=True, blank=True, null=True,
                                default=None, validators=[UnicodeUsernameValidator()])
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta(AbstractUser.Meta):
        constraints = [models.UniqueConstraint(Lower('email'), name='accounts_user_email_ci_unique')]

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        self.username = self.username or None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email
