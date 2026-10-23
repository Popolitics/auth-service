from unittest.mock import patch

from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase

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
        for data in [{}, {'email': 'invalid', 'password': self.password},
                     {'email': 'marie@example.org'},
                     {'email': 'marie@example.org', 'password': None},
                     {'email': 'marie@example.org', 'password': ''}]:
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
        with patch('authentication.serializers.RegisterSerializer.validate_email', return_value='marie@example.org'):
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
