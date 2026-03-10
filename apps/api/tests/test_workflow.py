from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from audit.models import AuditEvent
from core.models import Project, ProjectMembership
from reports.models import DailyReport, ReportSnapshot
from reports.models import ApprovalAction


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

    def test_reject_from_reviewed_returns_to_draft(self):
        report_id = self._create_report()

        self.client.login(username="super1", password="test-pass")
        submit_response = self.client.post(f"/api/reports/daily/{report_id}/submit/", {}, format="json")
        self.assertEqual(submit_response.status_code, 200)
        self.client.logout()

        self.client.login(username="pm1", password="test-pass")
        review_response = self.client.post(f"/api/reports/daily/{report_id}/review/", {}, format="json")
        self.assertEqual(review_response.status_code, 200)
        reject_response = self.client.post(
            f"/api/reports/daily/{report_id}/reject/",
            {"reason": "Needs corrections"},
            format="json",
        )
        self.assertEqual(reject_response.status_code, 200)
        self.assertEqual(reject_response.json()["status"], "draft")

    def test_sync_weather_requires_write_role(self):
        report_id = self._create_report()
        safety_user = User.objects.create_user(username="safety1", password="test-pass")
        ProjectMembership.objects.create(
            user=safety_user,
            project=self.project,
            role=ProjectMembership.Role.SAFETY,
        )
        self.client.login(username="safety1", password="test-pass")
        response = self.client.post(f"/api/reports/daily/{report_id}/sync-weather/", {}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_sync_weather_blocked_when_locked(self):
        report_id = self._create_report()
        report = DailyReport.objects.get(id=report_id)
        report.status = DailyReport.Status.LOCKED
        report.save(update_fields=["status", "updated_at"])
        self.client.login(username="admin1", password="test-pass")
        response = self.client.post(f"/api/reports/daily/{report_id}/sync-weather/", {}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_approve_uses_custom_signature_intent(self):
        report_id = self._create_report()

        self.client.login(username="super1", password="test-pass")
        submit_response = self.client.post(f"/api/reports/daily/{report_id}/submit/", {}, format="json")
        self.assertEqual(submit_response.status_code, 200)
        self.client.logout()

        self.client.login(username="pm1", password="test-pass")
        review_response = self.client.post(f"/api/reports/daily/{report_id}/review/", {}, format="json")
        self.assertEqual(review_response.status_code, 200)
        approve_response = self.client.post(
            f"/api/reports/daily/{report_id}/approve/",
            {"signature_intent": "Approved by PM with field verification."},
            format="json",
        )
        self.assertEqual(approve_response.status_code, 200)

        latest_approval = ApprovalAction.objects.filter(report_id=report_id, action=ApprovalAction.Action.APPROVE).latest("created_at")
        self.assertEqual(latest_approval.signature_intent, "Approved by PM with field verification.")
