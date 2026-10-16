from django.urls import path

from accounts.views import health, RegisterView, LogoutView

urlpatterns = [
    path("health/", health, name="health"),
    path('register/', RegisterView.as_view(), name='auth_register'),
    path('logout/', LogoutView.as_view(), name='logout'),
]
