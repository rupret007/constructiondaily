from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from audit.models import AuditEvent
from core.models import Project, ProjectMembership
from reports.models import DailyReport, ReportSnapshot


class ReportWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.superintendent = User.objects.create_user(username="super1", password="test-pass")
        self.pm = User.objects.create_user(username="pm1", password="test-pass")
        self.admin = User.objects.create_user(username="admin1", password="test-pass")
        self.project = Project.objects.create(code="PRJ-1", name="Tower", location="Site A")
        ProjectMembership.objects.create(
            user=self.superintendent, project=self.project, role=ProjectMembership.Role.SUPERINTENDENT
        )
        ProjectMembership.objects.create(user=self.pm, project=self.project, role=ProjectMembership.Role.PROJECT_MANAGER)
        ProjectMembership.objects.create(user=self.admin, project=self.project, role=ProjectMembership.Role.ADMIN)

    def _create_report(self) -> str:
        self.client.login(username="super1", password="test-pass")
        response = self.client.post(
            "/api/reports/daily/",
            {
                "project": str(self.project.id),
                "report_date": "2026-03-08",
                "location": "Area B",
                "summary": "Initial work complete",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        report_id = response.json()["id"]
        self.client.logout()
        return report_id

    def test_workflow_end_to_end(self):
        report_id = self._create_report()

        self.client.login(username="super1", password="test-pass")
        submit_response = self.client.post(f"/api/reports/daily/{report_id}/submit/", {}, format="json")
        self.assertEqual(submit_response.status_code, 200)
        self.assertEqual(submit_response.json()["status"], "submitted")
        self.client.logout()

        self.client.login(username="pm1", password="test-pass")
        review_response = self.client.post(f"/api/reports/daily/{report_id}/review/", {}, format="json")
        self.assertEqual(review_response.status_code, 200)
        self.assertEqual(review_response.json()["status"], "reviewed")

        approve_response = self.client.post(f"/api/reports/daily/{report_id}/approve/", {}, format="json")
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.json()["status"], "approved")
        self.client.logout()

        self.client.login(username="admin1", password="test-pass")
        lock_response = self.client.post(f"/api/reports/daily/{report_id}/lock/", {}, format="json")
        self.assertEqual(lock_response.status_code, 200)
        self.assertEqual(lock_response.json()["status"], "locked")
        self.assertGreaterEqual(ReportSnapshot.objects.filter(report_id=report_id).count(), 1)
        self.assertGreaterEqual(AuditEvent.objects.filter(object_id=report_id).count(), 4)

        blocked_update = self.client.patch(f"/api/reports/daily/{report_id}/", {"summary": "change"}, format="json")
        self.assertEqual(blocked_update.status_code, 403)
