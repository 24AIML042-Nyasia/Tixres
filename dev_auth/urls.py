from django.urls import path
from dev_auth import views

urlpatterns = [
    path("register/",    views.register,    name="dev-auth-register"),
    path("login/",       views.login,       name="dev-auth-login"),
    # Passwordless token mint for scripting / tests
    path("token/",       views.issue_token, name="dev-auth-token"),
]
