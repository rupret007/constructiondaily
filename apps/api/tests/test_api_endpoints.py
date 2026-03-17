from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient


class ApiEndpointSmokeTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_schema_endpoint_available(self):
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, 200)

    def test_session_endpoint_works_unauthenticated(self):
        response = self.client.get("/api/auth/session/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["authenticated"], False)

    def test_login_session_logout_round_trip(self):
        User.objects.create_user(username="api-user", password="test-pass")

        login_response = self.client.post(
            "/api/auth/login/",
            {"username": "api-user", "password": "test-pass"},
            format="json",
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.json()["username"], "api-user")

        session_response = self.client.get("/api/auth/session/")
        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(session_response.json()["authenticated"], True)
        self.assertEqual(session_response.json()["user"]["username"], "api-user")
        self.assertTrue(session_response.json()["csrfToken"])

        logout_response = self.client.post("/api/auth/logout/")
        self.assertEqual(logout_response.status_code, 204)

        final_session_response = self.client.get("/api/auth/session/")
        self.assertEqual(final_session_response.status_code, 200)
        self.assertEqual(final_session_response.json()["authenticated"], False)
