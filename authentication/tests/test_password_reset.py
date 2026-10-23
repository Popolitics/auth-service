from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from authentication.serializers import PasswordResetConfirmSerializer

from .helpers import RS256BackendMixin

User = get_user_model()


@override_settings(PASSWORD_RESET_URL='https://app.example.org/reset-password')
class PasswordResetTests(RS256BackendMixin, APITestCase):
    new_password = 'Another!Password482'

    def request_reset(self, email='marie@example.org'):
        return self.client.post(reverse('password_reset'), {'email': email}, format='json')

    def reset_params(self):
        self.assertEqual(self.request_reset().status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        link = next(word for word in mail.outbox[0].body.split() if word.startswith('https://'))
        self.assertTrue(link.startswith('https://app.example.org/reset-password?'))
        return {key: values[0] for key, values in parse_qs(urlparse(link).query).items()}

    def confirm(self, params, password=None):
        return self.client.post(reverse('password_reset_confirm'),
                                {**params, 'new_password': password or self.new_password}, format='json')

    def test_request_sends_link_to_account_email(self):
        response = self.request_reset('MARIE@Example.org')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['marie@example.org'])
        self.assertIn('https://app.example.org/reset-password?uid=', mail.outbox[0].body)

    def test_request_does_not_reveal_unknown_or_inactive_accounts(self):
        known = self.request_reset()
        mail.outbox.clear()
        User.objects.create_user(email='inactive@example.org', password='Secure!Password739', is_active=False)
        for email in ['unknown@example.org', 'inactive@example.org']:
            with self.subTest(email=email):
                response = self.request_reset(email)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, known.data)
        self.assertEqual(mail.outbox, [])

    def test_request_hides_email_sending_failure(self):
        known = self.request_reset()
        with patch('authentication.serializers.send_password_reset_email', side_effect=ConnectionRefusedError), \
                self.assertLogs('authentication.serializers', 'ERROR'):
            response = self.request_reset()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, known.data)

    def test_request_requires_valid_email(self):
        for data in [{}, {'email': 'invalid'}]:
            with self.subTest(data=data):
                self.assertEqual(self.client.post(reverse('password_reset'), data, format='json').status_code, 400)

    def test_confirm_sets_new_password(self):
        response = self.confirm(self.reset_params())
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertIsNone(authenticate(email=self.user.email, password='Secure!Password739'))

    def test_link_is_single_use(self):
        params = self.reset_params()
        self.assertEqual(self.confirm(params).status_code, 204)
        response = self.confirm(params, 'Third!Password915')
        self.assertEqual(response.status_code, 400)
        self.assertIn('token', response.data)

    def test_concurrent_confirmations_with_same_link(self):
        params = self.reset_params()
        first = PasswordResetConfirmSerializer(data={**params, 'new_password': self.new_password})
        second = PasswordResetConfirmSerializer(data={**params, 'new_password': 'Third!Password915'})
        # Both validated before either saves, as with two simultaneous requests.
        self.assertTrue(first.is_valid())
        self.assertTrue(second.is_valid())
        first.save()
        with self.assertRaises(ValidationError):
            second.save()
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))

    def test_link_expires_after_one_hour(self):
        params = self.reset_params()
        now = datetime.now()  # PasswordResetTokenGenerator._now() is naive local time
        with patch.object(PasswordResetTokenGenerator, '_now', return_value=now + timedelta(minutes=59)):
            response = self.confirm(params, 'Weak')
        # Still valid at 59 minutes: only the weak password is rejected.
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('token', response.data)
        self.assertIn('new_password', response.data)
        with patch.object(PasswordResetTokenGenerator, '_now', return_value=now + timedelta(hours=1, minutes=1)):
            response = self.confirm(params)
        self.assertEqual(response.status_code, 400)
        self.assertIn('token', response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Secure!Password739'))

    def test_confirm_rejects_invalid_uid_or_token(self):
        params = self.reset_params()
        for override in [{'token': 'invalid'}, {'uid': 'invalid'}, {'uid': 'bm90LWEtdXVpZA'}, {'uid': ''}]:
            with self.subTest(override=override):
                response = self.confirm({**params, **override})
                self.assertEqual(response.status_code, 400)

    def test_confirm_enforces_password_policy(self):
        params = self.reset_params()
        response = self.confirm(params, 'abcdefgh1')
        self.assertEqual(response.status_code, 400)
        self.assertIn('new_password', response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Secure!Password739'))
        self.assertEqual(self.confirm(params).status_code, 204)

    def test_confirm_revokes_existing_sessions(self):
        refresh = str(RefreshToken.for_user(self.user))
        self.assertEqual(self.confirm(self.reset_params()).status_code, 204)
        response = self.client.post(reverse('token_refresh'), {'refresh': refresh}, format='json')
        self.assertEqual(response.status_code, 401)
