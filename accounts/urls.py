from django.urls import path

from .views import DeleteAccountView

urlpatterns = [
    path('delete/', DeleteAccountView.as_view(), name='account_delete'),
]
