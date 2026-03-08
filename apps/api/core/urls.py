from django.urls import path

from core.views import login_view, logout_view, session_view

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("session/", session_view, name="session"),
]
