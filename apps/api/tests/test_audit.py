"""Tests for AuditEventViewSet: listing, filtering, and project scoping."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from audit.models import AuditEvent
from core.models import Project, ProjectMembership


class AuditEventViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.superuser = User.objects.create_superuser(username="admin", password="test-pass")
        self.pm_user = User.objects.create_user(username="pm1", password="test-pass")
        self.foreman_user = User.objects.create_user(username="foreman1", password="test-pass")
        self.project_a = Project.objects.create(code="A", name="Project A", location="Site A")
        self.project_b = Project.objects.create(code="B", name="Project B", location="Site B")
        ProjectMembership.objects.create(
            user=self.pm_user,
            project=self.project_a,
            role=ProjectMembership.Role.PROJECT_MANAGER,
            is_active=True,
        )
        ProjectMembership.objects.create(
            user=self.foreman_user,
            project=self.project_a,
            role=ProjectMembership.Role.FOREMAN,
            is_active=True,
        )
        self.event_a = AuditEvent.objects.create(
            event_type="report.created",
            object_type="DailyReport",
            object_id="r1",
            project_id=str(self.project_a.id),
        )
        self.event_b = AuditEvent.objects.create(
            event_type="report.created",
            object_type="DailyReport",
            object_id="r2",
            project_id=str(self.project_b.id),
        )

    def test_superuser_sees_all_events(self):
        self.client.login(username="admin", password="test-pass")
        response = self.client.get("/api/audit/")
        self.assertEqual(response.status_code, 200)
        ids = [e["id"] for e in response.json()]
        self.assertIn(str(self.event_a.id), ids)
        self.assertIn(str(self.event_b.id), ids)

    def test_pm_sees_only_their_projects_events(self):
        self.client.login(username="pm1", password="test-pass")
        response = self.client.get("/api/audit/")
        self.assertEqual(response.status_code, 200)
        ids = [e["id"] for e in response.json()]
        self.assertIn(str(self.event_a.id), ids)
        self.assertNotIn(str(self.event_b.id), ids)

    def test_foreman_cannot_list_audit_events(self):
        """Only ADMIN and PROJECT_MANAGER can list audit; Foreman cannot."""
        self.client.login(username="foreman1", password="test-pass")
        response = self.client.get("/api/audit/")
        self.assertEqual(response.status_code, 200)
        ids = [e["id"] for e in response.json()]
        self.assertEqual(len(ids), 0)

    def test_filter_by_project_id(self):
        self.client.login(username="admin", password="test-pass")
        response = self.client.get("/api/audit/", {"project_id": str(self.project_a.id)})
        self.assertEqual(response.status_code, 200)
        ids = [e["id"] for e in response.json()]
        self.assertIn(str(self.event_a.id), ids)
        self.assertNotIn(str(self.event_b.id), ids)
