from __future__ import annotations

import uuid

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Project, ProjectMembership
from files.models import Attachment
from reports.models import DailyReport, LaborEntry
from safety.models import SafetyEntry


class IntegrityGuardTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.superintendent = User.objects.create_user(username="integrity_super", password="test-pass")
        self.safety_user = User.objects.create_user(username="integrity_safety", password="test-pass")
        self.project = Project.objects.create(code="INT-1", name="Integrity One", location="Site 1")
        self.other_project = Project.objects.create(code="INT-2", name="Integrity Two", location="Site 2")
        ProjectMembership.objects.create(
            user=self.superintendent,
            project=self.project,
            role=ProjectMembership.Role.SUPERINTENDENT,
        )
        ProjectMembership.objects.create(
            user=self.safety_user,
            project=self.project,
            role=ProjectMembership.Role.SAFETY,
        )
        self.report_a = DailyReport.objects.create(
            project=self.project,
            report_date="2026-03-08",
            location="Site 1",
            prepared_by=self.superintendent,
            summary="A",
        )
        self.report_b = DailyReport.objects.create(
            project=self.project,
            report_date="2026-03-09",
            location="Site 1",
            prepared_by=self.superintendent,
            summary="B",
        )

    def _create_attachment(self) -> Attachment:
        suffix = uuid.uuid4().hex[:8]
        return Attachment.objects.create(
            report=self.report_a,
            original_filename=f"photo-{suffix}.png",
            stored_filename=f"stored-{suffix}.png",
            storage_key=f"stage/raw/{suffix}.png",
            mime_type="image/png",
            file_extension="png",
            size_bytes=128,
            sha256="a" * 64,
            uploaded_by=self.superintendent,
            scan_status=Attachment.ScanStatus.PENDING,
        )

    def test_report_update_rejects_project_reassignment(self):
        self.client.login(username="integrity_super", password="test-pass")
        response = self.client.patch(
            f"/api/reports/daily/{self.report_a.id}/",
            {"project": str(self.other_project.id), "revision": self.report_a.revision},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.report_a.refresh_from_db()
        self.assertEqual(self.report_a.project_id, self.project.id)

    def test_labor_entry_update_rejects_report_reassignment(self):
        labor = LaborEntry.objects.create(
            report=self.report_a,
            trade="Electrical",
            company="ACME",
            workers=2,
            regular_hours=8,
            overtime_hours=0,
        )
        self.client.login(username="integrity_super", password="test-pass")
        response = self.client.patch(
            f"/api/reports/labor/{labor.id}/",
            {"report": str(self.report_b.id), "workers": 3},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        labor.refresh_from_db()
        self.assertEqual(labor.report_id, self.report_a.id)

    def test_safety_entry_update_rejects_report_reassignment(self):
        entry = SafetyEntry.objects.create(
            report=self.report_a,
            entry_type=SafetyEntry.EntryType.OBSERVATION,
            severity=SafetyEntry.Severity.LOW,
            description="Initial observation",
        )
        self.client.login(username="integrity_safety", password="test-pass")
        response = self.client.patch(
            f"/api/safety/{entry.id}/",
            {"report": str(self.report_b.id), "description": "Updated"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        entry.refresh_from_db()
        self.assertEqual(entry.report_id, self.report_a.id)

    def test_attachment_delete_requires_write_role(self):
        attachment = self._create_attachment()
        self.client.login(username="integrity_safety", password="test-pass")
        response = self.client.delete(f"/api/files/attachments/{attachment.id}/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Attachment.objects.filter(id=attachment.id).exists())

    def test_attachment_update_endpoint_disabled(self):
        attachment = self._create_attachment()
        self.client.login(username="integrity_super", password="test-pass")
        response = self.client.patch(
            f"/api/files/attachments/{attachment.id}/",
            {"report": str(self.report_b.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 405)
        attachment.refresh_from_db()
        self.assertEqual(attachment.report_id, self.report_a.id)

    def test_upload_intent_rejects_invalid_max_size(self):
        self.client.login(username="integrity_super", password="test-pass")
        bad_type = self.client.post(
            "/api/files/intents/",
            {"report": str(self.report_a.id), "max_size_bytes": "abc"},
            format="json",
        )
        self.assertEqual(bad_type.status_code, 400)

        non_positive = self.client.post(
            "/api/files/intents/",
            {"report": str(self.report_a.id), "max_size_bytes": 0},
            format="json",
        )
        self.assertEqual(non_positive.status_code, 400)
