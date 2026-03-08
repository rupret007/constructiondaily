from __future__ import annotations

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
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
