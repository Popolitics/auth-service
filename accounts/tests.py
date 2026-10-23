from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import DatabaseError
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from authentication.tests import TokenTestCase

User = get_user_model()


class AccountDeletionTests(TokenTestCase):
    url = '/api/accounts/delete/'

    def setUp(self):
        super().setUp()
        self.tokens = [self.login().data, self.login().data]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.tokens[0]['access']}")

    def delete_account(self, **overrides):
        payload = {'password': 'Secure!Password739'}
        payload.update(overrides)
        return self.client.post(self.url, payload, format='json')

    def test_valid_password_is_required(self):
        for data in [{}, {'password': ''}, {'password': None},
                     {'password': 'incorrect'}]:
            with self.subTest(data=data):
                self.assertEqual(self.client.post(self.url, data, format='json').status_code, 400)
                self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_only_post_is_supported_and_old_route_is_removed(self):
        for method in ['get', 'delete', 'put', 'patch']:
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(self.url).status_code, 405)
        self.assertEqual(self.client.post('/api/accounts/me/', {}, format='json').status_code, 404)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_expired_access_token_is_rejected(self):
        claims = self.backend.decode(self.tokens[0]['access'])
        claims['exp'] = 1
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.backend.encode(claims)}')
        self.assertEqual(self.delete_account().status_code, 401)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_anonymous_and_invalid_tokens_are_rejected(self):
        for authorization in ['', 'Bearer invalid']:
            self.client.credentials(HTTP_AUTHORIZATION=authorization)
            self.assertEqual(self.delete_account().status_code, 401)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_deletes_only_authenticated_account_and_its_sessions_and_tokens(self):
        other = User.objects.create_user(email='other@example.org', password='Another!Password739')
        other_refresh = str(RefreshToken.for_user(other))
        own_browser, other_browser = APIClient(), APIClient()
        own_browser.force_login(self.user)
        own_session = own_browser.session.session_key
        other_browser.force_login(other)
        other_session = other_browser.session.session_key
        self.assertTrue(Session.objects.filter(pk=own_session).exists())
        response = self.delete_account(user_id=str(other.pk))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b'')
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(User.objects.filter(pk=other.pk).exists())
        self.assertFalse(Session.objects.filter(pk=own_session).exists())
        self.assertTrue(Session.objects.filter(pk=other_session).exists())
        self.assertFalse(OutstandingToken.objects.filter(user_id=self.user.pk).exists())
        self.assertTrue(OutstandingToken.objects.filter(user=other).exists())
        self.client.credentials()
        self.assertEqual(self.client.post('/api/token/refresh/',
                         {'refresh': other_refresh}, format='json').status_code, 200)

    def test_all_access_refresh_and_verify_tokens_are_rejected_after_deletion(self):
        rotated = self.client.post('/api/token/refresh/',
                                   {'refresh': self.tokens[1]['refresh']}, format='json')
        self.assertEqual(rotated.status_code, 200)
        self.tokens.append(rotated.data)
        self.assertEqual(self.delete_account().status_code, 204)
        for tokens in self.tokens:
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
            self.assertEqual(self.delete_account().status_code, 401)
            self.client.credentials()
            self.assertEqual(self.client.post('/api/token/refresh/',
                             {'refresh': tokens['refresh']}, format='json').status_code, 401)
            for token in tokens.values():
                self.assertEqual(self.client.post('/api/token/verify/',
                                 {'token': token}, format='json').status_code, 401)
        self.assertEqual(self.login().status_code, 401)

    def test_database_failure_rolls_back_everything_and_returns_generic_error(self):
        with patch('accounts.models.User.delete', side_effect=DatabaseError('sensitive details')):
            response = self.delete_account()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('sensitive', str(response.data))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(OutstandingToken.objects.filter(user=self.user).count(), 2)
        self.assertEqual(self.delete_account().status_code, 204)
