from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.backends import TokenBackend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

User = get_user_model()


class RS256BackendMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.backend = TokenBackend(
            algorithm='RS256',
            signing_key=key.private_bytes(serialization.Encoding.PEM,
                                         serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()).decode(),
            verifying_key=key.public_key().public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode(),
        )

    def setUp(self):
        patcher = patch('rest_framework_simplejwt.tokens.Token.get_token_backend', return_value=self.backend)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = User.objects.create_user(email='marie@example.org', password='Secure!Password739')
