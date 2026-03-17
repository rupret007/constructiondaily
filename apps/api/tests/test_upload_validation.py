from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import Project, ProjectMembership
from files.models import Attachment
from reports.models import DailyReport


class UploadValidationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="super2", password="test-pass")
        self.project = Project.objects.create(code="PRJ-3", name="Hospital", location="Site D")
        ProjectMembership.objects.create(user=self.user, project=self.project, role=ProjectMembership.Role.SUPERINTENDENT)
        self.report = DailyReport.objects.create(
            project=self.project,
            report_date="2026-03-08",
            location="Site D",
            prepared_by=self.user,
        )

    def test_reject_bad_extension(self):
        self.client.login(username="super2", password="test-pass")
        bad_file = SimpleUploadedFile("payload.exe", b"MZ-content", content_type="application/octet-stream")
        response = self.client.post(
            "/api/files/attachments/",
            {"report": str(self.report.id), "file": bad_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_accept_valid_png(self):
        self.client.login(username="super2", password="test-pass")
        png_header = b"\x89PNG\r\n\x1a\n" + b"0" * 20
        good_file = SimpleUploadedFile("photo.png", png_header, content_type="image/png")
        response = self.client.post(
            "/api/files/attachments/",
            {"report": str(self.report.id), "file": good_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Attachment.objects.count(), 1)
        self.report.refresh_from_db()
        self.assertEqual(self.report.revision, 2)

    def test_upload_intent_flow(self):
        self.client.login(username="super2", password="test-pass")
        intent_response = self.client.post(
            "/api/files/intents/",
            {"report": str(self.report.id), "max_size_bytes": 1024 * 1024},
            format="json",
        )
        self.assertEqual(intent_response.status_code, 201)
        intent_id = intent_response.json()["id"]

        png_header = b"\x89PNG\r\n\x1a\n" + b"0" * 20
        good_file = SimpleUploadedFile("photo.png", png_header, content_type="image/png")
        upload_response = self.client.post(
            f"/api/files/intents/{intent_id}/upload/",
            {"file": good_file},
            format="multipart",
        )
        self.assertEqual(upload_response.status_code, 201)

    def test_upload_intent_rejected_for_locked_report(self):
        self.report.status = DailyReport.Status.LOCKED
        self.report.save(update_fields=["status", "updated_at"])
        self.client.login(username="super2", password="test-pass")
        intent_response = self.client.post(
            "/api/files/intents/",
            {"report": str(self.report.id), "max_size_bytes": 1024 * 1024},
            format="json",
        )
        self.assertEqual(intent_response.status_code, 400)

    def test_direct_upload_rejected_for_submitted_report(self):
        self.report.status = DailyReport.Status.SUBMITTED
        self.report.save(update_fields=["status", "updated_at"])
        self.client.login(username="super2", password="test-pass")
        png_header = b"\x89PNG\r\n\x1a\n" + b"0" * 20
        good_file = SimpleUploadedFile("photo.png", png_header, content_type="image/png")
        response = self.client.post(
            "/api/files/attachments/",
            {"report": str(self.report.id), "file": good_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_attachment_delete_removes_file_from_storage(self):
        self.client.login(username="super2", password="test-pass")
        png_header = b"\x89PNG\r\n\x1a\n" + b"0" * 20

        with TemporaryDirectory() as temp_media_root:
            with override_settings(MEDIA_ROOT=temp_media_root):
                good_file = SimpleUploadedFile("photo.png", png_header, content_type="image/png")
                response = self.client.post(
                    "/api/files/attachments/",
                    {"report": str(self.report.id), "file": good_file},
                    format="multipart",
                )
                self.assertEqual(response.status_code, 201)
                attachment = Attachment.objects.get()
                stored_path = Path(temp_media_root) / attachment.storage_key
                self.assertTrue(stored_path.exists())

                delete_response = self.client.delete(f"/api/files/attachments/{attachment.id}/")
                self.assertEqual(delete_response.status_code, 204)
                self.assertFalse(stored_path.exists())
                self.report.refresh_from_db()
                self.assertEqual(self.report.revision, 3)
