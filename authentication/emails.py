from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def send_password_reset_email(user):
    query = urlencode({'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                       'token': default_token_generator.make_token(user)})
    context = {
        'link': f'{settings.PASSWORD_RESET_URL}?{query}',
        'validity_minutes': settings.PASSWORD_RESET_TIMEOUT // 60,
    }
    send_mail(
        'Réinitialisation de votre mot de passe',
        render_to_string('authentication/emails/password_reset.txt', context),
        None,
        [user.email],
    )
