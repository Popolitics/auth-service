from unittest.mock import patch

from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.tokens import RefreshToken
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

User = get_user_model()


class RegistrationTests(APITestCase):
    url = '/api/register/'
    password = 'Secure!Password739'

    def register(self, **overrides):
        data = {'email': 'marie@example.org', 'password': self.password}
        data.update(overrides)
        return self.client.post(self.url, data, format='json')

    def test_register_without_username(self):
        response = self.register(email='Marie@EXAMPLE.org')
        self.assertEqual(response.status_code, 201)
        self.assertNotIn('password', response.data)
        user = User.objects.get()
        self.assertEqual(user.email, 'marie@example.org')
        self.assertIsNone(user.username)
        self.assertTrue(user.check_password(self.password))

    def test_multiple_users_without_username(self):
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(self.register(email='autre@example.org', username='').status_code, 201)

    def test_optional_username_is_preserved_and_unique(self):
        self.assertEqual(self.register(username='marie').status_code, 201)
        response = self.register(email='autre@example.org', username='marie')
        self.assertEqual(response.status_code, 400)
        self.assertIn('username', response.data)
        self.assertEqual(User.objects.get().username, 'marie')

    def test_password_complexity(self):
        for password in ['Abc1234', 'abcdefgh1', 'ABCDEFGH', 'abcdefgh', '12345678']:
            with self.subTest(password=password):
                response = self.register(password=password)
                self.assertEqual(response.status_code, 400)
                self.assertIn('password', response.data)
        self.assertFalse(User.objects.exists())

    def test_required_and_valid_fields(self):
        for data in [{}, {'email': 'invalid', 'password': self.password}, {'email': 'marie@example.org'}]:
            with self.subTest(data=data):
                self.assertEqual(self.client.post(self.url, data, format='json').status_code, 400)

    def test_duplicate_email_case_insensitive(self):
        self.assertEqual(self.register().status_code, 201)
        for email in ['marie@example.org', 'MARIE@EXAMPLE.ORG']:
            with self.subTest(email=email):
                response = self.register(email=email)
                self.assertEqual(response.status_code, 400)
                self.assertIn('email', response.data)
        self.assertEqual(User.objects.count(), 1)

    def test_database_rejects_case_variant_bypassing_save(self):
        self.register()
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.bulk_create([User(email='MARIE@example.org')])

    def test_concurrent_email_conflict_returns_validation_error(self):
        self.register()
        with patch('accounts.serializers.RegisterSerializer.validate_email', return_value='marie@example.org'):
            response = self.register(email='MARIE@example.org')
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.data)

    def test_login_with_email_case_variant(self):
        self.register()
        user = authenticate(email='MARIE@EXAMPLE.ORG', password=self.password)
        self.assertIsNotNone(user)
        self.assertEqual(user.email, 'marie@example.org')
        self.assertIsNone(authenticate(email='MARIE@example.org', password='incorrect'))

    def test_create_superuser_without_username(self):
        user = User.objects.create_superuser(email='ADMIN@example.org', password=self.password)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertEqual(user.email, 'admin@example.org')


class TokenEndpointTests(APITestCase):
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

    def login(self):
        return self.client.post(reverse('token_obtain_pair'), {
            'email': 'MARIE@example.org', 'password': 'Secure!Password739',
        }, format='json')

    def test_login_returns_custom_claims(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        for name in ['access', 'refresh']:
            claims = self.backend.decode(response.data[name])
            self.assertEqual(claims['email'], self.user.email)
            self.assertIsNone(claims['username'])
            self.assertFalse(claims['is_staff'])
            self.assertEqual(claims['user_id'], str(self.user.pk))

    def test_refresh_and_verify_remain_available(self):
        tokens = self.login().data
        response = self.client.post(reverse('token_refresh'), {'refresh': tokens['refresh']}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.backend.decode(response.data['access'])['email'], self.user.email)
        response = self.client.post(reverse('token_verify'), {'token': response.data['access']}, format='json')
        self.assertEqual(response.status_code, 200)

    def test_invalid_credentials(self):
        response = self.client.post(reverse('token_obtain_pair'), {
            'email': self.user.email, 'password': 'incorrect',
        }, format='json')
        self.assertEqual(response.status_code, 401)
        self.assertIn('detail', response.data)

    def test_logout_revokes_refresh_and_preserves_other_sessions(self):
        tokens = self.login().data
        other_session = self.login().data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = self.client.post(reverse('logout'), {'refresh': tokens['refresh']}, format='json')
        self.assertEqual(response.status_code, 204)
        self.client.credentials()
        response = self.client.post(reverse('token_refresh'), {'refresh': tokens['refresh']}, format='json')
        self.assertEqual(response.status_code, 401)
        response = self.client.post(reverse('token_refresh'), {'refresh': other_session['refresh']}, format='json')
        self.assertEqual(response.status_code, 200)
        # Logout revokes only the refresh token, not the current access token.
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(self.client.post(reverse('logout'), {}, format='json').status_code, 400)

    def test_logout_requires_authentication(self):
        tokens = self.login().data
        response = self.client.post(reverse('logout'), {'refresh': tokens['refresh']}, format='json')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.post(reverse('token_refresh'), {'refresh': tokens['refresh']}, format='json').status_code, 200)

    def test_logout_rejects_another_users_token(self):
        tokens = self.login().data
        other_user = User.objects.create_user(email='other@example.org', password='Secure!Password739')
        refresh = str(RefreshToken.for_user(other_user))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = self.client.post(reverse('logout'), {'refresh': refresh}, format='json')
        self.assertEqual(response.status_code, 400)
        self.client.credentials()
        self.assertEqual(self.client.post(reverse('token_refresh'), {'refresh': refresh}, format='json').status_code, 200)

    def test_logout_rejects_missing_invalid_expired_and_access_tokens(self):
        tokens = self.login().data
        expired = RefreshToken(tokens['refresh'])
        expired['exp'] = 1
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        for payload in [{}, {'refresh': 'invalid'}, {'refresh': str(expired)}, {'refresh': tokens['access']}]:
            with self.subTest(payload=payload):
                response = self.client.post(reverse('logout'), payload, format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('refresh', response.data)

    def test_logout_rejects_already_revoked_token(self):
        tokens = self.login().data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        payload = {'refresh': tokens['refresh']}
        self.assertEqual(self.client.post(reverse('logout'), payload, format='json').status_code, 204)
        self.assertEqual(self.client.post(reverse('logout'), payload, format='json').status_code, 400)
