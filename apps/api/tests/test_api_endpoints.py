from __future__ import annotations

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
