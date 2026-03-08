from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Project, ProjectMembership


class PermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.foreman = User.objects.create_user(username="foreman", password="test-pass")
        self.other = User.objects.create_user(username="outsider", password="test-pass")
        self.project = Project.objects.create(code="PRJ-2", name="Bridge", location="Zone C")
        ProjectMembership.objects.create(user=self.foreman, project=self.project, role=ProjectMembership.Role.FOREMAN)

    def test_non_member_cannot_create_report(self):
        self.client.login(username="outsider", password="test-pass")
        response = self.client.post(
            "/api/reports/daily/",
            {
                "project": str(self.project.id),
                "report_date": "2026-03-08",
                "location": "Zone C",
                "summary": "Attempt by non-member",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_member_can_create_report(self):
        self.client.login(username="foreman", password="test-pass")
        response = self.client.post(
            "/api/reports/daily/",
            {
                "project": str(self.project.id),
                "report_date": "2026-03-08",
                "location": "Zone C",
                "summary": "Valid report",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
