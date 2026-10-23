from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .helpers import RS256BackendMixin

User = get_user_model()


class TokenEndpointTests(RS256BackendMixin, APITestCase):

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
