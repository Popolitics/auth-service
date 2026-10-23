from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import DatabaseError, transaction
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from .serializers import DeleteAccountSerializer


class DeleteAccountView(generics.GenericAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = DeleteAccountSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
                # Remove stored JWT payloads as they contain personal claims.
                OutstandingToken.objects.filter(user=user).delete()
                for session in Session.objects.iterator():
                    if session.get_decoded().get('_auth_user_id') == str(user.pk):
                        session.delete()
                user.delete()
        except get_user_model().DoesNotExist:
            return Response({'detail': 'Compte indisponible.'}, status=401)
        except DatabaseError:
            return Response({'detail': 'Suppression indisponible. Veuillez réessayer.'}, status=503)
        return Response(status=204)
