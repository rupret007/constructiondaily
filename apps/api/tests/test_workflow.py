from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from audit.models import AuditEvent
from core.models import Project, ProjectMembership
from reports.models import (
    ApprovalAction,
    DailyReport,
    LaborEntry,
    ReportSnapshot,
)


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

    def test_report_retrieve_query_count(self):
        """Retrieve report detail should use prefetch_related and not N+1."""
        report_id = self._create_report()
        report = DailyReport.objects.get(pk=report_id)
        LaborEntry.objects.create(
            report=report, trade="Carpenter", company="ABC", workers=2, notes=""
        )
        self.client.login(username="super1", password="test-pass")
        self.client.post(f"/api/reports/daily/{report_id}/submit/", {}, format="json")
        self.client.logout()
        self.client.login(username="pm1", password="test-pass")
        with self.assertNumQueries(12):
            response = self.client.get(f"/api/reports/daily/{report_id}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("labor_entries", data)
        self.assertIn("approval_actions", data)

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

    def test_reject_requires_reason(self):
        report_id = self._create_report()

        self.client.login(username="super1", password="test-pass")
        submit_response = self.client.post(f"/api/reports/daily/{report_id}/submit/", {}, format="json")
        self.assertEqual(submit_response.status_code, 200)
        self.client.logout()

        self.client.login(username="pm1", password="test-pass")
        reject_response = self.client.post(
            f"/api/reports/daily/{report_id}/reject/",
            {"reason": "   "},
            format="json",
        )
        self.assertEqual(reject_response.status_code, 400)

    def test_submitted_report_blocks_further_content_edits_until_rejected(self):
        report_id = self._create_report()

        self.client.login(username="super1", password="test-pass")
        submit_response = self.client.post(
            f"/api/reports/daily/{report_id}/submit/",
            {"revision": 1},
            format="json",
        )
        self.assertEqual(submit_response.status_code, 200)

        blocked_update = self.client.patch(
            f"/api/reports/daily/{report_id}/",
            {"summary": "Changed after submit", "revision": 2},
            format="json",
        )
        self.assertEqual(blocked_update.status_code, 403)

        blocked_labor = self.client.post(
            "/api/reports/labor/",
            {
                "report": report_id,
                "trade": "Electrical",
                "company": "ACME",
                "workers": 2,
                "regular_hours": "8.00",
                "overtime_hours": "0.00",
            },
            format="json",
        )
        self.assertEqual(blocked_labor.status_code, 403)

    def test_submit_rejects_stale_revision(self):
        report_id = self._create_report()

        self.client.login(username="super1", password="test-pass")
        update_response = self.client.patch(
            f"/api/reports/daily/{report_id}/",
            {"summary": "Updated before submit", "revision": 1},
            format="json",
        )
        self.assertEqual(update_response.status_code, 200)

        stale_submit = self.client.post(
            f"/api/reports/daily/{report_id}/submit/",
            {"revision": 1},
            format="json",
        )
        self.assertEqual(stale_submit.status_code, 400)
        self.assertIn("refresh and manually resolve conflicts", str(stale_submit.json()).lower())

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
        submit_response = self.client.post(f"/api/reports/daily/{report_id}/submit/", {"revision": 1}, format="json")
        self.assertEqual(submit_response.status_code, 200)
        self.client.logout()

        self.client.login(username="pm1", password="test-pass")
        review_response = self.client.post(f"/api/reports/daily/{report_id}/review/", {"revision": 2}, format="json")
        self.assertEqual(review_response.status_code, 200)
        approve_response = self.client.post(
            f"/api/reports/daily/{report_id}/approve/",
            {"signature_intent": "Approved by PM with field verification.", "revision": 3},
            format="json",
        )
        self.assertEqual(approve_response.status_code, 200)

        latest_approval = ApprovalAction.objects.filter(report_id=report_id, action=ApprovalAction.Action.APPROVE).latest("created_at")
        self.assertEqual(latest_approval.signature_intent, "Approved by PM with field verification.")
