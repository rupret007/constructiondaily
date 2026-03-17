"""Tests for Preconstruction Plan Annotation API and services."""

from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from reportlab.pdfgen import canvas
from rest_framework.test import APIClient

from audit.models import AuditEvent
from core.models import Project, ProjectMembership
from preconstruction import document_services
from preconstruction.models import (
    AIAnalysisRun,
    AISuggestion,
    AnnotationItem,
    AnnotationLayer,
    ExportRecord,
    PlanSet,
    PlanSheet,
    ProjectDocument,
    ProjectDocumentChunk,
    ProjectTakeoffRule,
    RevisionSnapshot,
    TakeoffItem,
)
from preconstruction.services import (
    accept_suggestion,
    batch_accept_suggestions,
    build_snapshot_payload,
    compute_snapshot_diff,
    reject_suggestion,
    run_plan_analysis,
)
from preconstruction.providers.registry import get_provider
from preconstruction.storage import get_project_document_file_path


# Minimal valid PDF bytes (single page)
MINIMAL_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n%%EOF"

# Minimal ASCII DXF with line + block insert + closed polyline
MINIMAL_DXF = (
    b"0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n"
    b"0\nLINE\n8\nA-DOOR\n10\n0.0\n20\n0.0\n11\n100.0\n21\n0.0\n"
    b"0\nINSERT\n8\nA-DOOR-BLOCK\n2\nDOORKNOB\n10\n25.0\n20\n10.0\n"
    b"0\nLWPOLYLINE\n8\nA-WALL\n70\n1\n"
    b"10\n0.0\n20\n0.0\n10\n0.0\n20\n40.0\n10\n60.0\n20\n40.0\n10\n60.0\n20\n0.0\n"
    b"0\nENDSEC\n0\nEOF\n"
)

# Minimal DWG-like header bytes for upload/signature validation.
MINIMAL_DWG = b"AC1027\x00\x01MockDWGContent"


def build_pdf_with_text(*lines: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    y = 760
    for line in lines:
        pdf.drawString(72, y, line)
        y -= 18
    pdf.save()
    return buffer.getvalue()


def build_blank_pdf() -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


class PreconstructionAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="estimator1", password="test-pass")
        self.project = Project.objects.create(code="BID-1", name="Building A", location="Site X")
        ProjectMembership.objects.create(
            user=self.user,
            project=self.project,
            role=ProjectMembership.Role.PROJECT_MANAGER,
        )

    def test_plan_set_crud(self):
        self.client.login(username="estimator1", password="test-pass")
        # Create
        create_resp = self.client.post(
            "/api/preconstruction/sets/",
            {
                "project": str(self.project.id),
                "name": "Floor 1 Plans",
                "description": "First floor only",
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)
        data = create_resp.json()
        set_id = data["id"]
        self.assertEqual(data["name"], "Floor 1 Plans")
        self.assertEqual(data["status"], "draft")

        # List
        list_resp = self.client.get("/api/preconstruction/sets/", {"project": str(self.project.id)})
        self.assertEqual(list_resp.status_code, 200)
        self.assertGreaterEqual(len(list_resp.json()), 1)

        # Retrieve
        get_resp = self.client.get(f"/api/preconstruction/sets/{set_id}/")
        self.assertEqual(get_resp.status_code, 200)

        # Update
        patch_resp = self.client.patch(
            f"/api/preconstruction/sets/{set_id}/",
            {"name": "Floor 1 Plans (revised)"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.json()["name"], "Floor 1 Plans (revised)")

        # Audit
        self.assertGreaterEqual(
            AuditEvent.objects.filter(event_type="create_plan_set", object_id=set_id).count(),
            1,
        )

    def test_plan_sheet_upload_and_file_serve(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Sheets",
            created_by=self.user,
            updated_by=self.user,
        )
        pdf = BytesIO(MINIMAL_PDF)
        pdf.name = "plan.pdf"
        create_resp = self.client.post(
            "/api/preconstruction/sheets/",
            {"plan_set": str(plan_set.id), "title": "A-101", "file": pdf},
            format="multipart",
        )
        self.assertEqual(create_resp.status_code, 201)
        self.assertEqual(create_resp.json()["file_type"], "pdf")
        self.assertEqual(create_resp.json()["file_extension"], "pdf")
        sheet_id = create_resp.json()["id"]
        self.assertTrue(PlanSheet.objects.filter(id=sheet_id).exists())
        sheet = PlanSheet.objects.get(id=sheet_id)
        self.assertTrue(sheet.storage_key)

        # Serve file
        file_resp = self.client.get(f"/api/preconstruction/sheets/{sheet_id}/file/")
        self.assertEqual(file_resp.status_code, 200)
        self.assertIn(file_resp.get("Content-Type", ""), ("application/pdf", "application/octet-stream", ""))

        self.assertGreaterEqual(
            AuditEvent.objects.filter(event_type="upload_plan_sheet", object_id=sheet_id).count(),
            1,
        )

    def test_plan_sheet_upload_invalid_sheet_index_rejected(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Sheets",
            created_by=self.user,
            updated_by=self.user,
        )
        pdf = BytesIO(MINIMAL_PDF)
        pdf.name = "plan.pdf"
        create_resp = self.client.post(
            "/api/preconstruction/sheets/",
            {"plan_set": str(plan_set.id), "title": "A-101", "sheet_index": "abc", "file": pdf},
            format="multipart",
        )
        self.assertEqual(create_resp.status_code, 400)

    def test_plan_sheet_upload_dxf_and_file_serve(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Sheets",
            created_by=self.user,
            updated_by=self.user,
        )
        dxf = BytesIO(MINIMAL_DXF)
        dxf.name = "plan.dxf"
        create_resp = self.client.post(
            "/api/preconstruction/sheets/",
            {"plan_set": str(plan_set.id), "title": "CAD-1", "file": dxf},
            format="multipart",
        )
        self.assertEqual(create_resp.status_code, 201)
        self.assertEqual(create_resp.json()["file_type"], "dxf")
        self.assertEqual(create_resp.json()["file_extension"], "dxf")
        sheet_id = create_resp.json()["id"]

        file_resp = self.client.get(f"/api/preconstruction/sheets/{sheet_id}/file/")
        self.assertEqual(file_resp.status_code, 200)
        self.assertIn(
            file_resp.get("Content-Type", ""),
            ("application/dxf", "application/octet-stream", ""),
        )

    def test_plan_sheet_upload_dwg_and_file_serve(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Sheets",
            created_by=self.user,
            updated_by=self.user,
        )
        dwg = BytesIO(MINIMAL_DWG)
        dwg.name = "plan.dwg"
        create_resp = self.client.post(
            "/api/preconstruction/sheets/",
            {"plan_set": str(plan_set.id), "title": "DWG-1", "file": dwg},
            format="multipart",
        )
        self.assertEqual(create_resp.status_code, 201)
        self.assertEqual(create_resp.json()["file_type"], "dwg")
        self.assertEqual(create_resp.json()["file_extension"], "dwg")
        sheet_id = create_resp.json()["id"]

        file_resp = self.client.get(f"/api/preconstruction/sheets/{sheet_id}/file/")
        self.assertEqual(file_resp.status_code, 200)
        self.assertIn(
            file_resp.get("Content-Type", ""),
            ("application/acad", "application/octet-stream", ""),
        )

    def test_plan_sheet_cad_preview_returns_items_for_dxf(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Sheets",
            created_by=self.user,
            updated_by=self.user,
        )
        dxf = BytesIO(MINIMAL_DXF)
        dxf.name = "preview.dxf"
        create_resp = self.client.post(
            "/api/preconstruction/sheets/",
            {"plan_set": str(plan_set.id), "title": "CAD-Preview", "file": dxf},
            format="multipart",
        )
        self.assertEqual(create_resp.status_code, 201)
        sheet_id = create_resp.json()["id"]

        preview_resp = self.client.get(f"/api/preconstruction/sheets/{sheet_id}/cad_preview/")
        self.assertEqual(preview_resp.status_code, 200)
        payload = preview_resp.json()
        self.assertEqual(payload["source_type"], "dxf")
        self.assertGreater(payload["item_count"], 0)
        self.assertGreaterEqual(len(payload["items"]), 1)
        self.assertIn("geometry_json", payload["items"][0])

    def test_plan_sheet_cad_preview_rejects_pdf(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Sheets",
            created_by=self.user,
            updated_by=self.user,
        )
        pdf = BytesIO(MINIMAL_PDF)
        pdf.name = "plan.pdf"
        create_resp = self.client.post(
            "/api/preconstruction/sheets/",
            {"plan_set": str(plan_set.id), "title": "A-101", "file": pdf},
            format="multipart",
        )
        self.assertEqual(create_resp.status_code, 201)
        sheet_id = create_resp.json()["id"]

        preview_resp = self.client.get(f"/api/preconstruction/sheets/{sheet_id}/cad_preview/")
        self.assertEqual(preview_resp.status_code, 400)
        self.assertIn("DXF/DWG", preview_resp.json()["detail"])

    def test_plan_sheet_update_and_delete_are_audited(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Sheets",
            created_by=self.user,
            updated_by=self.user,
        )
        sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            title="A-100",
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )

        patch_resp = self.client.patch(
            f"/api/preconstruction/sheets/{sheet.id}/",
            {"title": "A-100 Revised"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 200)
        sheet.refresh_from_db()
        self.assertEqual(sheet.title, "A-100 Revised")
        self.assertGreaterEqual(
            AuditEvent.objects.filter(event_type="update_plan_sheet", object_id=str(sheet.id)).count(),
            1,
        )

        delete_resp = self.client.delete(f"/api/preconstruction/sheets/{sheet.id}/")
        self.assertEqual(delete_resp.status_code, 204)
        self.assertFalse(PlanSheet.objects.filter(id=sheet.id).exists())
        self.assertGreaterEqual(
            AuditEvent.objects.filter(event_type="delete_plan_sheet", object_id=str(sheet.id)).count(),
            1,
        )

    def test_plan_sheet_calibration_requires_valid_pair(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Sheets",
            created_by=self.user,
            updated_by=self.user,
        )
        sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            title="A-300",
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )

        missing_height = self.client.patch(
            f"/api/preconstruction/sheets/{sheet.id}/",
            {"calibrated_width": "100"},
            format="json",
        )
        self.assertEqual(missing_height.status_code, 400)

        missing_width = self.client.patch(
            f"/api/preconstruction/sheets/{sheet.id}/",
            {"calibrated_height": "80"},
            format="json",
        )
        self.assertEqual(missing_width.status_code, 400)

        negative_width = self.client.patch(
            f"/api/preconstruction/sheets/{sheet.id}/",
            {"calibrated_width": "-1", "calibrated_height": "80"},
            format="json",
        )
        self.assertEqual(negative_width.status_code, 400)

        valid = self.client.patch(
            f"/api/preconstruction/sheets/{sheet.id}/",
            {"calibrated_width": "100", "calibrated_height": "80", "calibrated_unit": "feet"},
            format="json",
        )
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json()["calibrated_width"], "100.0000")
        self.assertEqual(valid.json()["calibrated_height"], "80.0000")

    def test_plan_sheet_update_and_delete_require_write_role(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Sheets",
            created_by=self.user,
            updated_by=self.user,
        )
        sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            title="A-200",
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        safety_user = User.objects.create_user(username="safety_view_only", password="test-pass")
        ProjectMembership.objects.create(
            user=safety_user,
            project=self.project,
            role=ProjectMembership.Role.SAFETY,
        )
        self.client.logout()
        self.client.login(username="safety_view_only", password="test-pass")

        patch_resp = self.client.patch(
            f"/api/preconstruction/sheets/{sheet.id}/",
            {"title": "Unauthorized edit"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 403)

        delete_resp = self.client.delete(f"/api/preconstruction/sheets/{sheet.id}/")
        self.assertEqual(delete_resp.status_code, 403)
        self.assertTrue(PlanSheet.objects.filter(id=sheet.id).exists())
        sheet.refresh_from_db()
        self.assertEqual(sheet.title, "A-200")

    def test_annotation_layer_and_item(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        layer_resp = self.client.post(
            "/api/preconstruction/layers/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "plan_sheet": str(plan_sheet.id),
                "name": "Doors",
                "color": "#ff0000",
            },
            format="json",
        )
        self.assertEqual(layer_resp.status_code, 201)
        layer_id = layer_resp.json()["id"]
        self.assertGreaterEqual(
            AuditEvent.objects.filter(event_type="create_annotation_layer").count(),
            1,
        )

        ann_resp = self.client.post(
            "/api/preconstruction/annotations/",
            {
                "project": str(self.project.id),
                "plan_sheet": str(plan_sheet.id),
                "layer": layer_id,
                "annotation_type": "rectangle",
                "geometry_json": {"type": "rectangle", "x": 0.1, "y": 0.2, "width": 0.2, "height": 0.15},
                "label": "Door D1",
            },
            format="json",
        )
        self.assertEqual(ann_resp.status_code, 201)
        self.assertGreaterEqual(
            AuditEvent.objects.filter(event_type="create_annotation").count(),
            1,
        )

    def test_annotation_create_rejects_cross_project_references(self):
        self.client.login(username="estimator1", password="test-pass")
        other_project = Project.objects.create(code="BID-2", name="Building B", location="Site Y")
        ProjectMembership.objects.create(
            user=self.user,
            project=other_project,
            role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        other_set = PlanSet.objects.create(
            project=other_project,
            name="Other set",
            created_by=self.user,
            updated_by=self.user,
        )
        other_sheet = PlanSheet.objects.create(
            project=other_project,
            plan_set=other_set,
            storage_key="plans/test/sheet-b.pdf",
            created_by=self.user,
        )
        other_layer = AnnotationLayer.objects.create(
            project=other_project,
            plan_set=other_set,
            plan_sheet=other_sheet,
            name="Other layer",
            created_by=self.user,
        )
        ann_resp = self.client.post(
            "/api/preconstruction/annotations/",
            {
                "project": str(self.project.id),
                "plan_sheet": str(other_sheet.id),
                "layer": str(other_layer.id),
                "annotation_type": "rectangle",
                "geometry_json": {"type": "rectangle", "x": 0.1, "y": 0.2, "width": 0.2, "height": 0.15},
                "label": "Cross-project",
            },
            format="json",
        )
        self.assertEqual(ann_resp.status_code, 400)

    def test_annotation_create_takeoff_auto_profile_generates_package(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        layer = AnnotationLayer.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            name="Doors",
            created_by=self.user,
        )
        annotation = AnnotationItem.objects.create(
            project=self.project,
            plan_sheet=plan_sheet,
            layer=layer,
            annotation_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.2, "width": 0.2, "height": 0.15},
            label="Door D1",
            source=AnnotationItem.Source.MANUAL,
            created_by=self.user,
            updated_by=self.user,
        )
        resp = self.client.post(
            f"/api/preconstruction/annotations/{annotation.id}/create_takeoff/",
            {"assembly_profile": "auto"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["assembly_profile"], "door_set")
        self.assertEqual(data["primary_takeoff"]["category"], "doors")
        self.assertEqual(len(data["extra_takeoffs"]), 1)
        self.assertEqual(data["extra_takeoffs"][0]["category"], "door_hardware")
        annotation.refresh_from_db()
        self.assertIsNotNone(annotation.linked_takeoff_item_id)
        linked_rows = list(
            TakeoffItem.objects.filter(plan_sheet=plan_sheet, source_annotation=annotation).order_by("category")
        )
        self.assertEqual(len(linked_rows), 2)

        summary_resp = self.client.get(
            "/api/preconstruction/takeoff/summary/",
            {"plan_set": str(plan_set.id), "plan_sheet": str(plan_sheet.id)},
        )
        self.assertEqual(summary_resp.status_code, 200)
        self.assertEqual(summary_resp.json()["linked_annotation_items"], 2)

    def test_annotation_create_takeoff_none_profile_generates_single_line(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        layer = AnnotationLayer.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            name="Windows",
            created_by=self.user,
        )
        annotation = AnnotationItem.objects.create(
            project=self.project,
            plan_sheet=plan_sheet,
            layer=layer,
            annotation_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.2, "y": 0.2, "width": 0.2, "height": 0.15},
            label="Door D2",
            source=AnnotationItem.Source.MANUAL,
            created_by=self.user,
            updated_by=self.user,
        )
        resp = self.client.post(
            f"/api/preconstruction/annotations/{annotation.id}/create_takeoff/",
            {"assembly_profile": "none"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["assembly_profile"], "none")
        self.assertEqual(len(data["extra_takeoffs"]), 0)

    def test_annotation_create_takeoff_rejects_when_already_linked(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        layer = AnnotationLayer.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            name="Doors",
            created_by=self.user,
        )
        takeoff = TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            category=TakeoffItem.Category.DOORS,
            unit=TakeoffItem.Unit.COUNT,
            quantity=1,
            created_by=self.user,
            updated_by=self.user,
        )
        annotation = AnnotationItem.objects.create(
            project=self.project,
            plan_sheet=plan_sheet,
            layer=layer,
            annotation_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.2, "y": 0.2, "width": 0.2, "height": 0.15},
            label="Door D3",
            source=AnnotationItem.Source.MANUAL,
            linked_takeoff_item=takeoff,
            created_by=self.user,
            updated_by=self.user,
        )
        resp = self.client.post(
            f"/api/preconstruction/annotations/{annotation.id}/create_takeoff/",
            {"assembly_profile": "auto"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("already has a linked takeoff", resp.json()["detail"])

    def test_annotation_create_takeoff_rejects_invalid_assembly_profile(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        layer = AnnotationLayer.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            name="Doors",
            created_by=self.user,
        )
        annotation = AnnotationItem.objects.create(
            project=self.project,
            plan_sheet=plan_sheet,
            layer=layer,
            annotation_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.2, "y": 0.2, "width": 0.2, "height": 0.15},
            label="Door D4",
            source=AnnotationItem.Source.MANUAL,
            created_by=self.user,
            updated_by=self.user,
        )
        resp = self.client.post(
            f"/api/preconstruction/annotations/{annotation.id}/create_takeoff/",
            {"assembly_profile": []},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid assembly_profile", resp.json()["detail"])

    def test_takeoff_item(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        create_resp = self.client.post(
            "/api/preconstruction/takeoff/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "category": "doors",
                "unit": "count",
                "quantity": "1.2",
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)
        self.assertEqual(create_resp.json()["quantity"], "2.0000")
        self.assertGreaterEqual(
            AuditEvent.objects.filter(event_type="create_takeoff_item").count(),
            1,
        )

        # Delete takeoff and assert audit
        delete_resp = self.client.delete(f"/api/preconstruction/takeoff/{create_resp.json()['id']}/")
        self.assertEqual(delete_resp.status_code, 204)
        self.assertGreaterEqual(
            AuditEvent.objects.filter(event_type="delete_takeoff_item").count(),
            1,
        )

    def test_takeoff_create_rejects_negative_quantity(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        create_resp = self.client.post(
            "/api/preconstruction/takeoff/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "category": "doors",
                "unit": "count",
                "quantity": "-5",
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 400)
        self.assertIn("non-negative", str(create_resp.json()["quantity"][0]))
        self.assertEqual(TakeoffItem.objects.filter(plan_set=plan_set).count(), 0)

    def test_takeoff_update_supports_estimator_review_fields(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        takeoff = TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            category=TakeoffItem.Category.DOORS,
            unit=TakeoffItem.Unit.COUNT,
            quantity="2",
            created_by=self.user,
            updated_by=self.user,
        )
        patch_resp = self.client.patch(
            f"/api/preconstruction/takeoff/{takeoff.id}/",
            {
                "subcategory": "Hollow metal",
                "cost_code": "08710",
                "bid_package": "Doors and frames",
                "review_state": "accepted",
                "notes": "Estimator-reviewed package",
            },
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 200)
        data = patch_resp.json()
        self.assertEqual(data["subcategory"], "Hollow metal")
        self.assertEqual(data["cost_code"], "08710")
        self.assertEqual(data["bid_package"], "Doors and frames")
        self.assertEqual(data["review_state"], "accepted")
        self.assertEqual(data["notes"], "Estimator-reviewed package")
        self.assertGreaterEqual(
            AuditEvent.objects.filter(event_type="update_takeoff_item", object_id=str(takeoff.id)).count(),
            1,
        )

    def test_takeoff_update_normalizes_count_quantity(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        takeoff = TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            category=TakeoffItem.Category.DOORS,
            unit=TakeoffItem.Unit.COUNT,
            quantity="2",
            created_by=self.user,
            updated_by=self.user,
        )
        patch_resp = self.client.patch(
            f"/api/preconstruction/takeoff/{takeoff.id}/",
            {"quantity": "2.2"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.json()["quantity"], "3.0000")

    def test_takeoff_summary_returns_rollups_and_honors_filters(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        layer = AnnotationLayer.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            name="Default",
            created_by=self.user,
        )
        doors_takeoff = TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            category=TakeoffItem.Category.DOORS,
            unit=TakeoffItem.Unit.COUNT,
            quantity="2",
            source=TakeoffItem.Source.MANUAL,
            review_state=TakeoffItem.ReviewState.PENDING,
            created_by=self.user,
            updated_by=self.user,
        )
        AnnotationItem.objects.create(
            project=self.project,
            plan_sheet=plan_sheet,
            layer=layer,
            annotation_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.2, "width": 0.1, "height": 0.1},
            label="Door D1",
            source=AnnotationItem.Source.MANUAL,
            linked_takeoff_item=doors_takeoff,
            created_by=self.user,
            updated_by=self.user,
        )
        TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            category=TakeoffItem.Category.DOOR_HARDWARE,
            unit=TakeoffItem.Unit.EACH,
            quantity="2",
            source=TakeoffItem.Source.AI_ASSISTED,
            review_state=TakeoffItem.ReviewState.ACCEPTED,
            bid_package="Doors and frames",
            cost_code="08710",
            created_by=self.user,
            updated_by=self.user,
        )
        TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            category=TakeoffItem.Category.LINEAR_MEASUREMENTS,
            unit=TakeoffItem.Unit.LINEAR_FEET,
            quantity="12.5",
            source=TakeoffItem.Source.MANUAL,
            review_state=TakeoffItem.ReviewState.REJECTED,
            created_by=self.user,
            updated_by=self.user,
        )

        summary_resp = self.client.get(
            "/api/preconstruction/takeoff/summary/",
            {"plan_set": str(plan_set.id), "plan_sheet": str(plan_sheet.id)},
        )
        self.assertEqual(summary_resp.status_code, 200)
        data = summary_resp.json()
        self.assertEqual(data["total_items"], 3)
        self.assertEqual(data["pending_items"], 1)
        self.assertEqual(data["accepted_items"], 1)
        self.assertEqual(data["rejected_items"], 1)
        self.assertEqual(data["manual_items"], 2)
        self.assertEqual(data["ai_assisted_items"], 1)
        self.assertEqual(data["linked_annotation_items"], 1)
        self.assertTrue(
            any(
                row["category"] == "doors" and row["unit"] == "count" and row["quantity_total"] == "2.0000"
                for row in data["category_totals"]
            )
        )
        self.assertTrue(
            any(
                row["unit"] == "linear_feet" and row["quantity_total"] == "12.5000"
                for row in data["unit_totals"]
            )
        )

        filtered_resp = self.client.get(
            "/api/preconstruction/takeoff/summary/",
            {
                "plan_set": str(plan_set.id),
                "plan_sheet": str(plan_sheet.id),
                "review_state": "pending",
            },
        )
        self.assertEqual(filtered_resp.status_code, 200)
        self.assertEqual(filtered_resp.json()["total_items"], 1)
        self.assertEqual(filtered_resp.json()["pending_items"], 1)

    def test_takeoff_dashboard_returns_cross_sheet_rollups(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Estimating Set",
            status=PlanSet.Status.READY,
            version_label="Bid Set 3",
            created_by=self.user,
            updated_by=self.user,
        )
        sheet_a = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            title="Level 1 Plan",
            sheet_number="A101",
            discipline="Architectural",
            storage_key="plans/test/a101.pdf",
            parse_status=PlanSheet.ParseStatus.PARSED,
            calibrated_width="120",
            calibrated_height="80",
            created_by=self.user,
        )
        sheet_b = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            title="Level 2 Plan",
            sheet_number="A201",
            discipline="Architectural",
            storage_key="plans/test/a201.pdf",
            parse_status=PlanSheet.ParseStatus.PARSED,
            created_by=self.user,
        )
        annotation = AnnotationItem.objects.create(
            project=self.project,
            plan_sheet=sheet_a,
            layer=AnnotationLayer.objects.create(
                project=self.project,
                plan_set=plan_set,
                plan_sheet=sheet_a,
                name="Doors",
                created_by=self.user,
            ),
            annotation_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            label="Door A1",
            source=AnnotationItem.Source.MANUAL,
            created_by=self.user,
            updated_by=self.user,
        )
        TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=sheet_a,
            source_annotation=annotation,
            category=TakeoffItem.Category.DOORS,
            unit=TakeoffItem.Unit.COUNT,
            quantity="4",
            source=TakeoffItem.Source.AI_ASSISTED,
            review_state=TakeoffItem.ReviewState.PENDING,
            created_by=self.user,
            updated_by=self.user,
        )
        TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=sheet_a,
            category=TakeoffItem.Category.WINDOWS,
            unit=TakeoffItem.Unit.COUNT,
            quantity="2",
            source=TakeoffItem.Source.MANUAL,
            review_state=TakeoffItem.ReviewState.ACCEPTED,
            created_by=self.user,
            updated_by=self.user,
        )
        TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=sheet_b,
            category=TakeoffItem.Category.LINEAR_MEASUREMENTS,
            unit=TakeoffItem.Unit.LINEAR_FEET,
            quantity="18.5",
            source=TakeoffItem.Source.MANUAL,
            review_state=TakeoffItem.ReviewState.EDITED,
            created_by=self.user,
            updated_by=self.user,
        )
        TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=None,
            category=TakeoffItem.Category.CUSTOM,
            unit=TakeoffItem.Unit.COUNT,
            quantity="1",
            source=TakeoffItem.Source.MANUAL,
            review_state=TakeoffItem.ReviewState.PENDING,
            created_by=self.user,
            updated_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=sheet_a,
            provider_name="mock",
            user_prompt="Find all doors",
            status=AIAnalysisRun.Status.COMPLETED,
            started_at=timezone.now() - timedelta(minutes=3),
            completed_at=timezone.now() - timedelta(minutes=2),
            created_by=self.user,
        )
        AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=sheet_a,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            label="Door A1",
            rationale="Detected door block",
            confidence="0.97",
        )
        AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=sheet_a,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.2, "y": 0.1, "width": 0.1, "height": 0.1},
            label="Door A2",
            rationale="Detected door block",
            confidence="0.95",
        )
        snapshot = RevisionSnapshot.objects.create(
            project=self.project,
            plan_set=plan_set,
            name="Pricing Snapshot",
            status=RevisionSnapshot.Status.LOCKED,
            created_by=self.user,
        )
        ExportRecord.objects.create(
            project=self.project,
            plan_set=plan_set,
            revision_snapshot=snapshot,
            export_type=ExportRecord.ExportType.CSV,
            status=ExportRecord.Status.GENERATED,
            created_by=self.user,
        )

        resp = self.client.get(
            "/api/preconstruction/takeoff/dashboard/",
            {"plan_set": str(plan_set.id)},
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["plan_set_name"], "Estimating Set")
        self.assertEqual(payload["summary"]["total_items"], 4)
        self.assertEqual(payload["coverage"]["total_sheet_count"], 2)
        self.assertEqual(payload["coverage"]["calibrated_sheet_count"], 1)
        self.assertEqual(payload["coverage"]["analyzed_sheet_count"], 1)
        self.assertEqual(payload["coverage"]["pending_suggestion_count"], 2)
        self.assertEqual(payload["coverage"]["unassigned_takeoff_items"], 1)
        self.assertEqual(payload["unassigned_summary"]["total_items"], 1)
        self.assertEqual(payload["latest_snapshot"]["name"], "Pricing Snapshot")
        self.assertEqual(payload["latest_export"]["export_type"], "csv")
        self.assertEqual(len(payload["sheet_rollups"]), 2)
        self.assertEqual(payload["sheet_rollups"][0]["sheet_number"], "A101")
        self.assertEqual(payload["sheet_rollups"][0]["pending_suggestions"], 2)
        self.assertEqual(payload["sheet_rollups"][0]["latest_analysis_status"], "completed")
        self.assertTrue(
            any(row["category"] == "doors" and row["quantity_total"] == "4.0000" for row in payload["sheet_rollups"][0]["top_categories"])
        )
        self.assertEqual(payload["discipline_rollups"][0]["discipline"], "Architectural")
        self.assertEqual(payload["discipline_rollups"][0]["takeoff_total_items"], 3)

    def test_takeoff_dashboard_uses_latest_completed_ai_run_for_coverage(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="AI Coverage Set",
            created_by=self.user,
            updated_by=self.user,
        )
        sheet_a = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            title="Door Plan",
            sheet_number="A101",
            discipline="Architectural",
            storage_key="plans/test/a101.pdf",
            parse_status=PlanSheet.ParseStatus.PARSED,
            created_by=self.user,
        )
        sheet_b = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            title="Window Plan",
            sheet_number="A201",
            discipline="Architectural",
            storage_key="plans/test/a201.pdf",
            parse_status=PlanSheet.ParseStatus.PARSED,
            created_by=self.user,
        )

        older_completed = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=sheet_a,
            provider_name="mock",
            user_prompt="Older run",
            status=AIAnalysisRun.Status.COMPLETED,
            started_at=timezone.now() - timedelta(minutes=12),
            completed_at=timezone.now() - timedelta(minutes=11),
            created_by=self.user,
        )
        AISuggestion.objects.create(
            analysis_run=older_completed,
            project=self.project,
            plan_sheet=sheet_a,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            label="Older door",
            rationale="Older run suggestion",
            confidence="0.91",
        )

        latest_completed = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=sheet_a,
            provider_name="mock",
            user_prompt="Latest completed run",
            status=AIAnalysisRun.Status.COMPLETED,
            started_at=timezone.now() - timedelta(minutes=7),
            completed_at=timezone.now() - timedelta(minutes=6),
            created_by=self.user,
        )
        AISuggestion.objects.create(
            analysis_run=latest_completed,
            project=self.project,
            plan_sheet=sheet_a,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.2, "y": 0.2, "width": 0.1, "height": 0.1},
            label="Door A1",
            rationale="Latest completed suggestion 1",
            confidence="0.96",
        )
        AISuggestion.objects.create(
            analysis_run=latest_completed,
            project=self.project,
            plan_sheet=sheet_a,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.3, "y": 0.2, "width": 0.1, "height": 0.1},
            label="Door A2",
            rationale="Latest completed suggestion 2",
            confidence="0.95",
        )

        AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=sheet_a,
            provider_name="mock",
            user_prompt="Failed rerun",
            status=AIAnalysisRun.Status.FAILED,
            started_at=timezone.now() - timedelta(minutes=2),
            completed_at=timezone.now() - timedelta(minutes=1),
            created_by=self.user,
        )
        AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=sheet_b,
            provider_name="mock",
            user_prompt="Failed only",
            status=AIAnalysisRun.Status.FAILED,
            started_at=timezone.now() - timedelta(minutes=4),
            completed_at=timezone.now() - timedelta(minutes=3),
            created_by=self.user,
        )

        resp = self.client.get(
            "/api/preconstruction/takeoff/dashboard/",
            {"plan_set": str(plan_set.id)},
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["coverage"]["analyzed_sheet_count"], 1)
        self.assertEqual(payload["coverage"]["pending_suggestion_count"], 2)
        self.assertEqual(payload["discipline_rollups"][0]["analyzed_sheet_count"], 1)
        sheet_rows = {row["sheet_number"]: row for row in payload["sheet_rollups"]}
        self.assertEqual(sheet_rows["A101"]["latest_analysis_status"], "failed")
        self.assertEqual(sheet_rows["A101"]["pending_suggestions"], 2)
        self.assertEqual(sheet_rows["A201"]["latest_analysis_status"], "failed")
        self.assertEqual(sheet_rows["A201"]["pending_suggestions"], 0)

    def test_takeoff_create_rejects_cross_project_references(self):
        self.client.login(username="estimator1", password="test-pass")
        other_project = Project.objects.create(code="BID-3", name="Building C", location="Site Z")
        ProjectMembership.objects.create(
            user=self.user,
            project=other_project,
            role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        other_set = PlanSet.objects.create(
            project=other_project,
            name="Other set",
            created_by=self.user,
            updated_by=self.user,
        )
        create_resp = self.client.post(
            "/api/preconstruction/takeoff/",
            {
                "project": str(self.project.id),
                "plan_set": str(other_set.id),
                "category": "doors",
                "unit": "count",
                "quantity": "4",
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 400)

    def test_ai_analysis_run_and_suggestions(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        run_resp = self.client.post(
            "/api/preconstruction/analysis/",
            {"plan_sheet": str(plan_sheet.id), "user_prompt": "highlight all doors"},
            format="json",
        )
        self.assertEqual(run_resp.status_code, 201)
        run_id = run_resp.json()["id"]
        self.assertEqual(run_resp.json()["status"], "completed")
        run = AIAnalysisRun.objects.get(id=run_id)
        suggestions = list(AISuggestion.objects.filter(analysis_run=run))
        self.assertGreater(len(suggestions), 0)
        for s in suggestions:
            self.assertIsNotNone(s.label)
            self.assertIn("type", s.geometry_json)
            self.assertIsNotNone(s.rationale)
            self.assertIsNotNone(s.suggestion_type)
        self.assertGreaterEqual(
            AuditEvent.objects.filter(event_type="trigger_ai_analysis", object_id=run_id).count(),
            1,
        )

    def test_ai_analysis_runtime_failure_returns_400_and_records_failed_run(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        with patch(
            "preconstruction.services.get_provider",
            side_effect=RuntimeError("Provider initialization failed."),
        ):
            run_resp = self.client.post(
                "/api/preconstruction/analysis/",
                {"plan_sheet": str(plan_sheet.id), "user_prompt": "highlight all doors"},
                format="json",
            )
        self.assertEqual(run_resp.status_code, 400)
        self.assertEqual(run_resp.json()["status"], "failed")
        self.assertIn("Provider initialization failed.", run_resp.json()["detail"])
        run_id = run_resp.json()["run_id"]
        run = AIAnalysisRun.objects.get(id=run_id)
        self.assertEqual(run.status, AIAnalysisRun.Status.FAILED)

    def test_ai_analysis_cad_dxf_provider_on_dxf_sheet(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        dxf = BytesIO(MINIMAL_DXF)
        dxf.name = "doors.dxf"
        upload_resp = self.client.post(
            "/api/preconstruction/sheets/",
            {"plan_set": str(plan_set.id), "title": "CAD Plan", "file": dxf},
            format="multipart",
        )
        self.assertEqual(upload_resp.status_code, 201)
        sheet_id = upload_resp.json()["id"]
        run_resp = self.client.post(
            "/api/preconstruction/analysis/",
            {
                "plan_sheet": sheet_id,
                "provider_name": "cad_dxf",
                "user_prompt": "doorknob and door",
            },
            format="json",
        )
        self.assertEqual(run_resp.status_code, 201)
        self.assertEqual(run_resp.json()["status"], "completed")
        run = AIAnalysisRun.objects.get(id=run_resp.json()["id"])
        suggestions = list(AISuggestion.objects.filter(analysis_run=run))
        self.assertGreater(len(suggestions), 0)
        self.assertTrue(any("door" in s.label.lower() for s in suggestions))

    def test_ai_analysis_openai_provider_rejects_dxf_sheet(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        dxf = BytesIO(MINIMAL_DXF)
        dxf.name = "doors.dxf"
        upload_resp = self.client.post(
            "/api/preconstruction/sheets/",
            {"plan_set": str(plan_set.id), "title": "CAD Plan", "file": dxf},
            format="multipart",
        )
        self.assertEqual(upload_resp.status_code, 201)
        sheet_id = upload_resp.json()["id"]
        run_resp = self.client.post(
            "/api/preconstruction/analysis/",
            {
                "plan_sheet": sheet_id,
                "provider_name": "openai_vision",
                "user_prompt": "find doors",
            },
            format="json",
        )
        self.assertEqual(run_resp.status_code, 400)
        self.assertEqual(run_resp.json()["status"], "failed")
        self.assertIn("PDF", run_resp.json()["detail"])

    def test_ai_analysis_cad_dxf_provider_on_dwg_requires_converter(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        dwg = BytesIO(MINIMAL_DWG)
        dwg.name = "plan.dwg"
        upload_resp = self.client.post(
            "/api/preconstruction/sheets/",
            {"plan_set": str(plan_set.id), "title": "DWG Plan", "file": dwg},
            format="multipart",
        )
        self.assertEqual(upload_resp.status_code, 201)
        sheet_id = upload_resp.json()["id"]
        with patch("preconstruction.cad.settings.PRECONSTRUCTION_DWG_CONVERTER_COMMAND", ""):
            run_resp = self.client.post(
                "/api/preconstruction/analysis/",
                {
                    "plan_sheet": sheet_id,
                    "provider_name": "cad_dxf",
                    "user_prompt": "find doors",
                },
                format="json",
            )
        self.assertEqual(run_resp.status_code, 400)
        self.assertEqual(run_resp.json()["status"], "failed")
        self.assertIn("DWG conversion", run_resp.json()["detail"])

    def test_plan_sheet_cad_preview_for_dwg_uses_converter(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        dwg = BytesIO(MINIMAL_DWG)
        dwg.name = "converted.dwg"
        upload_resp = self.client.post(
            "/api/preconstruction/sheets/",
            {"plan_set": str(plan_set.id), "title": "DWG Plan", "file": dwg},
            format="multipart",
        )
        self.assertEqual(upload_resp.status_code, 201)
        sheet_id = upload_resp.json()["id"]
        with patch("preconstruction.cad._convert_dwg_to_dxf_text", return_value=MINIMAL_DXF.decode("utf-8")):
            preview_resp = self.client.get(f"/api/preconstruction/sheets/{sheet_id}/cad_preview/")
        self.assertEqual(preview_resp.status_code, 200)
        payload = preview_resp.json()
        self.assertEqual(payload["source_type"], "dwg")
        self.assertGreater(payload["item_count"], 0)

    def test_direct_suggestion_create_not_allowed(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            provider_name="mock",
            user_prompt="doors",
            status=AIAnalysisRun.Status.COMPLETED,
            created_by=self.user,
        )
        create_resp = self.client.post(
            "/api/preconstruction/suggestions/",
            {
                "analysis_run": str(run.id),
                "project": str(self.project.id),
                "plan_sheet": str(plan_sheet.id),
                "suggestion_type": "rectangle",
                "geometry_json": {"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
                "label": "Manual injection",
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 405)
        self.assertEqual(AISuggestion.objects.filter(analysis_run=run).count(), 0)

    def test_ai_analysis_deterministic(self):
        """Same sheet + prompt produces same suggestions (mock provider)."""
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        run1 = run_plan_analysis(plan_sheet, "find plumbing fixtures", self.user)
        run2 = run_plan_analysis(plan_sheet, "find plumbing fixtures", self.user)
        sugg1 = list(AISuggestion.objects.filter(analysis_run=run1).order_by("created_at"))
        sugg2 = list(AISuggestion.objects.filter(analysis_run=run2).order_by("created_at"))
        self.assertEqual(len(sugg1), len(sugg2))
        if sugg1 and sugg2:
            self.assertEqual(sugg1[0].geometry_json, sugg2[0].geometry_json)
            self.assertEqual(sugg1[0].label, sugg2[0].label)

    @patch("preconstruction.services.get_provider")
    def test_ai_analysis_rolls_back_partial_suggestions_on_failure(self, mock_get_provider):
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )

        class BrokenProvider:
            def run_analysis(self, _plan_sheet, _prompt):
                return [
                    {
                        "suggestion_type": "rectangle",
                        "geometry_json": {"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
                        "label": "Door A1",
                        "confidence": "0.95",
                    },
                    {
                        "suggestion_type": "rectangle",
                        "geometry_json": {"type": "rectangle", "x": 0.2, "y": 0.2, "width": 0.1, "height": 0.1},
                        "label": "Broken suggestion",
                        "confidence": "not-a-number",
                    },
                ]

        mock_get_provider.return_value = BrokenProvider()

        run = run_plan_analysis(plan_sheet, "find doors", self.user)

        self.assertEqual(run.status, AIAnalysisRun.Status.FAILED)
        self.assertEqual(AISuggestion.objects.filter(analysis_run=run).count(), 0)
        self.assertIn("not-a-number", str(run.response_payload_json.get("error", "")))

    def test_provider_registry(self):
        provider = get_provider("mock")
        self.assertIsNotNone(provider)
        from preconstruction.providers.base import BaseAnalysisProvider
        self.assertTrue(isinstance(provider, BaseAnalysisProvider))
        openai_provider = get_provider("openai_vision")
        self.assertIsNotNone(openai_provider)
        self.assertTrue(isinstance(openai_provider, BaseAnalysisProvider))
        cad_provider = get_provider("cad_dxf")
        self.assertIsNotNone(cad_provider)
        self.assertTrue(isinstance(cad_provider, BaseAnalysisProvider))
        with self.assertRaises(ValueError):
            get_provider("nonexistent")

    def test_analysis_create_rejects_unknown_provider(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        run_resp = self.client.post(
            "/api/preconstruction/analysis/",
            {"plan_sheet": str(plan_sheet.id), "user_prompt": "highlight doors", "provider_name": "bad_provider"},
            format="json",
        )
        self.assertEqual(run_resp.status_code, 400)
        self.assertIn("Unknown provider", run_resp.json().get("detail", ""))

    @override_settings(PRECONSTRUCTION_ANALYSIS_PROVIDER="")
    def test_analysis_create_falls_back_to_mock_provider_when_default_is_blank(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )

        run_resp = self.client.post(
            "/api/preconstruction/analysis/",
            {"plan_sheet": str(plan_sheet.id), "user_prompt": "highlight doors"},
            format="json",
        )

        self.assertEqual(run_resp.status_code, 201)
        self.assertEqual(run_resp.json()["provider_name"], "mock")

    def test_accept_and_reject_suggestion(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            provider_name="mock",
            user_prompt="doors",
            status=AIAnalysisRun.Status.COMPLETED,
            created_by=self.user,
        )
        suggestion = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            label="Door",
            rationale="Mock",
            confidence=0.9,
        )
        accept_resp = self.client.post(
            f"/api/preconstruction/suggestions/{suggestion.id}/accept/",
            {},
            format="json",
        )
        self.assertEqual(accept_resp.status_code, 200)
        self.assertIn("annotation", accept_resp.json())
        self.assertIn("takeoff", accept_resp.json())
        self.assertTrue(
            TakeoffItem.objects.filter(
                plan_sheet=plan_sheet,
                category=TakeoffItem.Category.DOOR_HARDWARE,
            ).exists()
        )
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.decision_state, AISuggestion.DecisionState.ACCEPTED)
        self.assertGreaterEqual(
            AuditEvent.objects.filter(event_type="accept_ai_suggestion").count(),
            1,
        )

        # Reject another suggestion
        suggestion2 = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.2, "y": 0.2, "width": 0.1, "height": 0.1},
            label="Window",
            rationale="Mock",
        )
        reject_resp = self.client.post(
            f"/api/preconstruction/suggestions/{suggestion2.id}/reject/",
            {},
            format="json",
        )
        self.assertEqual(reject_resp.status_code, 200)
        suggestion2.refresh_from_db()
        self.assertEqual(suggestion2.decision_state, AISuggestion.DecisionState.REJECTED)

    def test_accept_and_reject_require_write_role(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            provider_name="mock",
            user_prompt="doors",
            status=AIAnalysisRun.Status.COMPLETED,
            created_by=self.user,
        )
        suggestion = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            label="Door",
            rationale="Mock",
            confidence=0.9,
        )
        safety_user = User.objects.create_user(username="safety_limited", password="test-pass")
        ProjectMembership.objects.create(
            user=safety_user,
            project=self.project,
            role=ProjectMembership.Role.SAFETY,
        )
        self.client.logout()
        self.client.login(username="safety_limited", password="test-pass")

        accept_resp = self.client.post(
            f"/api/preconstruction/suggestions/{suggestion.id}/accept/",
            {},
            format="json",
        )
        self.assertEqual(accept_resp.status_code, 403)

        reject_resp = self.client.post(
            f"/api/preconstruction/suggestions/{suggestion.id}/reject/",
            {},
            format="json",
        )
        self.assertEqual(reject_resp.status_code, 403)

    def test_accept_suggestion_with_overrides_edited(self):
        """Accept with category/unit/quantity overrides sets EDITED and records edit_ai_suggestion."""
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            provider_name="mock",
            user_prompt="doors",
            status=AIAnalysisRun.Status.COMPLETED,
            created_by=self.user,
        )
        suggestion = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            label="Door",
            rationale="Mock",
            confidence=0.9,
        )
        accept_resp = self.client.post(
            f"/api/preconstruction/suggestions/{suggestion.id}/accept/",
            {"category": "doors", "unit": "count", "quantity": "2", "label": "Double door"},
            format="json",
        )
        self.assertEqual(accept_resp.status_code, 200)
        data = accept_resp.json()
        self.assertEqual(data["takeoff"]["category"], "doors")
        self.assertEqual(data["takeoff"]["unit"], "count")
        self.assertEqual(float(data["takeoff"]["quantity"]), 2)
        self.assertEqual(data["annotation"]["label"], "Double door")
        self.assertTrue(
            TakeoffItem.objects.filter(
                plan_sheet=plan_sheet,
                category=TakeoffItem.Category.DOOR_HARDWARE,
                source_annotation_id=data["annotation"]["id"],
            ).exists()
        )
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.decision_state, AISuggestion.DecisionState.EDITED)
        self.assertGreaterEqual(
            AuditEvent.objects.filter(event_type="edit_ai_suggestion").count(),
            1,
        )

    def test_accept_suggestion_invalid_category_rejected(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            provider_name="mock",
            user_prompt="doors",
            status=AIAnalysisRun.Status.COMPLETED,
            created_by=self.user,
        )
        suggestion = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            label="Door",
            rationale="Mock",
            confidence=0.9,
        )
        accept_resp = self.client.post(
            f"/api/preconstruction/suggestions/{suggestion.id}/accept/",
            {"category": "not_a_real_category"},
            format="json",
        )
        self.assertEqual(accept_resp.status_code, 400)
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.decision_state, AISuggestion.DecisionState.PENDING)
        self.assertEqual(TakeoffItem.objects.filter(plan_sheet=plan_sheet).count(), 0)
        self.assertEqual(AnnotationItem.objects.filter(plan_sheet=plan_sheet).count(), 0)

    def test_accept_suggestion_invalid_unit_rejected(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            provider_name="mock",
            user_prompt="doors",
            status=AIAnalysisRun.Status.COMPLETED,
            created_by=self.user,
        )
        suggestion = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            label="Door",
            rationale="Mock",
            confidence=0.9,
        )
        accept_resp = self.client.post(
            f"/api/preconstruction/suggestions/{suggestion.id}/accept/",
            {"unit": "not_a_real_unit"},
            format="json",
        )
        self.assertEqual(accept_resp.status_code, 400)
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.decision_state, AISuggestion.DecisionState.PENDING)
        self.assertEqual(TakeoffItem.objects.filter(plan_sheet=plan_sheet).count(), 0)
        self.assertEqual(AnnotationItem.objects.filter(plan_sheet=plan_sheet).count(), 0)

    def test_accept_suggestion_rejects_non_finite_quantity(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            provider_name="mock",
            user_prompt="doors",
            status=AIAnalysisRun.Status.COMPLETED,
            created_by=self.user,
        )
        suggestion = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            label="Door",
            rationale="Mock",
            confidence=0.9,
        )
        accept_resp = self.client.post(
            f"/api/preconstruction/suggestions/{suggestion.id}/accept/",
            {"quantity": "NaN"},
            format="json",
        )
        self.assertEqual(accept_resp.status_code, 400)
        self.assertIn("finite number", accept_resp.json()["detail"])
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.decision_state, AISuggestion.DecisionState.PENDING)
        self.assertEqual(TakeoffItem.objects.filter(plan_sheet=plan_sheet).count(), 0)
        self.assertEqual(AnnotationItem.objects.filter(plan_sheet=plan_sheet).count(), 0)

    def test_accept_suggestion_auto_area_quantity_uses_sheet_calibration_feet(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            calibrated_width="100",
            calibrated_height="80",
            calibrated_unit=PlanSheet.CalibrationUnit.FEET,
            created_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            provider_name="mock",
            user_prompt="concrete",
            status=AIAnalysisRun.Status.COMPLETED,
            created_by=self.user,
        )
        suggestion = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="polygon",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.5, "height": 0.25},
            label="Concrete area",
            rationale="Mock",
            confidence=0.9,
        )
        accept_resp = self.client.post(
            f"/api/preconstruction/suggestions/{suggestion.id}/accept/",
            {},
            format="json",
        )
        self.assertEqual(accept_resp.status_code, 200)
        takeoff = accept_resp.json()["takeoff"]
        self.assertEqual(takeoff["unit"], "square_feet")
        self.assertEqual(takeoff["quantity"], "1000.0000")

    def test_accept_suggestion_auto_area_quantity_converts_meters_to_feet(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            calibrated_width="30",
            calibrated_height="15",
            calibrated_unit=PlanSheet.CalibrationUnit.METERS,
            created_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            provider_name="mock",
            user_prompt="concrete",
            status=AIAnalysisRun.Status.COMPLETED,
            created_by=self.user,
        )
        suggestion = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="polygon",
            geometry_json={"type": "rectangle", "x": 0.2, "y": 0.2, "width": 0.2, "height": 0.2},
            label="Concrete area",
            rationale="Mock",
            confidence=0.9,
        )
        accept_resp = self.client.post(
            f"/api/preconstruction/suggestions/{suggestion.id}/accept/",
            {},
            format="json",
        )
        self.assertEqual(accept_resp.status_code, 200)
        takeoff = accept_resp.json()["takeoff"]
        self.assertEqual(takeoff["unit"], "square_feet")
        self.assertEqual(takeoff["quantity"], "193.7504")

    def test_accept_suggestion_polyline_defaults_linear_and_estimates_quantity(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            calibrated_width="100",
            calibrated_height="80",
            calibrated_unit=PlanSheet.CalibrationUnit.FEET,
            created_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            provider_name="mock",
            user_prompt="measure lines",
            status=AIAnalysisRun.Status.COMPLETED,
            created_by=self.user,
        )
        suggestion = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="polyline",
            geometry_json={
                "type": "polyline",
                "points": [{"x": 0.1, "y": 0.1}, {"x": 0.4, "y": 0.1}],
            },
            label="",
            rationale="Mock",
            confidence=0.9,
        )
        accept_resp = self.client.post(
            f"/api/preconstruction/suggestions/{suggestion.id}/accept/",
            {},
            format="json",
        )
        self.assertEqual(accept_resp.status_code, 200)
        takeoff = accept_resp.json()["takeoff"]
        self.assertEqual(takeoff["category"], "linear_measurements")
        self.assertEqual(takeoff["unit"], "linear_feet")
        self.assertEqual(takeoff["quantity"], "30.0000")

    def test_batch_accept_suggestions(self):
        """Batch accept accepts only pending suggestions with confidence >= min_confidence."""
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            provider_name="mock",
            user_prompt="doors",
            status=AIAnalysisRun.Status.COMPLETED,
            created_by=self.user,
        )
        high = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            label="Door",
            rationale="Mock",
            confidence=0.92,
        )
        mid = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.2, "y": 0.2, "width": 0.1, "height": 0.1},
            label="Door",
            rationale="Mock",
            confidence=0.85,
        )
        low = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.3, "y": 0.3, "width": 0.1, "height": 0.1},
            label="Door",
            rationale="Mock",
            confidence=0.5,
        )
        resp = self.client.post(
            "/api/preconstruction/suggestions/batch_accept/",
            {"plan_sheet": str(plan_sheet.id), "min_confidence": 0.85},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["accepted_count"], 2)
        self.assertEqual(len(data["annotations"]), 2)
        self.assertEqual(len(data["takeoff_items"]), 2)
        high.refresh_from_db()
        mid.refresh_from_db()
        low.refresh_from_db()
        self.assertEqual(high.decision_state, AISuggestion.DecisionState.ACCEPTED)
        self.assertEqual(mid.decision_state, AISuggestion.DecisionState.ACCEPTED)
        self.assertEqual(low.decision_state, AISuggestion.DecisionState.PENDING)

    def test_batch_accept_requires_plan_sheet(self):
        self.client.login(username="estimator1", password="test-pass")
        resp = self.client.post(
            "/api/preconstruction/suggestions/batch_accept/",
            {},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("plan_sheet", resp.json().get("detail", ""))

    def test_batch_accept_permission(self):
        """User from another project cannot batch accept on this sheet."""
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        other_user = User.objects.create_user(username="other", password="test-pass")
        other_project = Project.objects.create(code="OTHER", name="Other", location="Y")
        ProjectMembership.objects.create(user=other_user, project=other_project, role=ProjectMembership.Role.ADMIN)
        self.client.login(username="other", password="test-pass")
        resp = self.client.post(
            "/api/preconstruction/suggestions/batch_accept/",
            {"plan_sheet": str(plan_sheet.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_revision_snapshot_and_export(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        snap_resp = self.client.post(
            "/api/preconstruction/snapshots/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "name": "v1",
            },
            format="json",
        )
        self.assertEqual(snap_resp.status_code, 201)
        snap_id = snap_resp.json()["id"]
        payload = snap_resp.json()["snapshot_payload_json"]
        self.assertIn("plan_set_id", payload)
        self.assertIn("plan_set_name", payload)
        self.assertIn("sheets", payload)
        self.assertIn("captured_at", payload)

        export_resp = self.client.post(
            "/api/preconstruction/exports/",
            {"plan_set": str(plan_set.id), "export_type": "json"},
            format="json",
        )
        self.assertEqual(export_resp.status_code, 201)
        self.assertIn("payload", export_resp.json())
        self.assertEqual(ExportRecord.objects.filter(plan_set=plan_set, export_type="json").count(), 1)
        self.assertGreaterEqual(
            AuditEvent.objects.filter(event_type="generate_export").count(),
            1,
        )

    def test_revision_snapshot_rejects_cross_project_references(self):
        self.client.login(username="estimator1", password="test-pass")
        other_project = Project.objects.create(code="BID-4", name="Building D", location="Site W")
        ProjectMembership.objects.create(
            user=self.user,
            project=other_project,
            role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        other_set = PlanSet.objects.create(
            project=other_project,
            name="Other set",
            created_by=self.user,
            updated_by=self.user,
        )
        snap_resp = self.client.post(
            "/api/preconstruction/snapshots/",
            {
                "project": str(self.project.id),
                "plan_set": str(other_set.id),
                "name": "invalid",
            },
            format="json",
        )
        self.assertEqual(snap_resp.status_code, 400)

    def test_revision_snapshot_create_forces_draft_status(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        snap_resp = self.client.post(
            "/api/preconstruction/snapshots/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "name": "v1",
                "status": "locked",
            },
            format="json",
        )
        self.assertEqual(snap_resp.status_code, 201)
        self.assertEqual(snap_resp.json()["status"], RevisionSnapshot.Status.DRAFT)

    def test_plan_set_update_cannot_change_project(self):
        self.client.login(username="estimator1", password="test-pass")
        other_project = Project.objects.create(code="BID-5", name="Building E", location="Site Q")
        ProjectMembership.objects.create(
            user=self.user,
            project=other_project,
            role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        patch_resp = self.client.patch(
            f"/api/preconstruction/sets/{plan_set.id}/",
            {"project": str(other_project.id)},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, 400)

    def test_snapshot_payload_includes_learning_data(self):
        """Snapshot payload includes annotation/takeoff source and review_state, and AI suggestion outcomes."""
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        layer = AnnotationLayer.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            name="Default",
            created_by=self.user,
        )
        ann = AnnotationItem.objects.create(
            project=self.project,
            plan_sheet=plan_sheet,
            layer=layer,
            annotation_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1},
            label="Door",
            source=AnnotationItem.Source.AI,
            review_state=AnnotationItem.ReviewState.ACCEPTED,
            created_by=self.user,
            updated_by=self.user,
        )
        takeoff = TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            category=TakeoffItem.Category.DOORS,
            unit=TakeoffItem.Unit.COUNT,
            quantity=1,
            source=TakeoffItem.Source.AI_ASSISTED,
            review_state=TakeoffItem.ReviewState.ACCEPTED,
            created_by=self.user,
            updated_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            provider_name="mock",
            user_prompt="doors",
            status=AIAnalysisRun.Status.COMPLETED,
            created_by=self.user,
        )
        suggestion = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            label="Door",
            rationale="Mock",
            confidence=0.9,
            decision_state=AISuggestion.DecisionState.ACCEPTED,
            accepted_annotation=ann,
            decided_by=self.user,
        )
        payload = build_snapshot_payload(plan_set)
        self.assertEqual(len(payload["sheets"]), 1)
        sheet_data = payload["sheets"][0]
        self.assertEqual(len(sheet_data["layers"]), 1)
        self.assertEqual(len(sheet_data["layers"][0]["items"]), 1)
        self.assertEqual(sheet_data["layers"][0]["items"][0]["source"], "ai")
        self.assertEqual(sheet_data["layers"][0]["items"][0]["review_state"], "accepted")
        self.assertEqual(len(sheet_data["takeoff_items"]), 1)
        self.assertEqual(sheet_data["takeoff_items"][0]["source"], "ai_assisted")
        self.assertEqual(sheet_data["takeoff_items"][0]["review_state"], "accepted")
        self.assertIn("ai_suggestion_outcomes", sheet_data)
        self.assertEqual(len(sheet_data["ai_suggestion_outcomes"]), 1)
        self.assertEqual(sheet_data["ai_suggestion_outcomes"][0]["decision_state"], "accepted")
        self.assertEqual(sheet_data["ai_suggestion_outcomes"][0]["label"], "Door")

    def test_count_scenario_batch_accept_snapshot_export_includes_counts(self):
        """Create sheet with mock door suggestions, batch accept by confidence; snapshot and export include takeoff counts and decision states."""
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            provider_name="mock",
            user_prompt="doors",
            status=AIAnalysisRun.Status.COMPLETED,
            created_by=self.user,
        )
        for i in range(3):
            AISuggestion.objects.create(
                analysis_run=run,
                project=self.project,
                plan_sheet=plan_sheet,
                suggestion_type="rectangle",
                geometry_json={"type": "rectangle", "x": 0.1 * i, "y": 0.1, "width": 0.1, "height": 0.1},
                label="Door",
                rationale="Mock",
                confidence=0.9,
            )
        batch_resp = self.client.post(
            "/api/preconstruction/suggestions/batch_accept/",
            {"plan_sheet": str(plan_sheet.id), "min_confidence": 0.85},
            format="json",
        )
        self.assertEqual(batch_resp.status_code, 200)
        self.assertEqual(batch_resp.json()["accepted_count"], 3)
        snap_resp = self.client.post(
            "/api/preconstruction/snapshots/",
            {"project": str(self.project.id), "plan_set": str(plan_set.id), "name": "v1"},
            format="json",
        )
        self.assertEqual(snap_resp.status_code, 201)
        payload = snap_resp.json()["snapshot_payload_json"]
        sheet_data = payload["sheets"][0]
        # Each accepted Door suggestion creates door + door_hardware takeoff rows (assembly)
        self.assertEqual(len(sheet_data["takeoff_items"]), 6)
        self.assertEqual(len(sheet_data["ai_suggestion_outcomes"]), 3)
        for out in sheet_data["ai_suggestion_outcomes"]:
            self.assertEqual(out["decision_state"], "accepted")
        export_resp = self.client.post(
            "/api/preconstruction/exports/",
            {"plan_set": str(plan_set.id), "export_type": "json"},
            format="json",
        )
        self.assertEqual(export_resp.status_code, 201)
        export_payload = export_resp.json()["payload"]
        self.assertEqual(len(export_payload["sheets"][0]["takeoff_items"]), 6)
        self.assertEqual(len(export_payload["sheets"][0]["ai_suggestion_outcomes"]), 3)

    def test_shade_area_scenario_annotation_takeoff_snapshot_export(self):
        """Create polygon/rectangle annotations, takeoff with area unit and calibration; snapshot/export include quantities and geometry."""
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            calibrated_width="100",
            calibrated_height="80",
            calibrated_unit=PlanSheet.CalibrationUnit.FEET,
            created_by=self.user,
        )
        layer = AnnotationLayer.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            name="Default",
            created_by=self.user,
        )
        # Polygon (normalized 0.5*0.25) * 100*80 = 1000 sq ft
        polygon_geom = {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 0.5, "y": 0},
                {"x": 0.5, "y": 0.25},
                {"x": 0, "y": 0.25},
            ],
        }
        ann = AnnotationItem.objects.create(
            project=self.project,
            plan_sheet=plan_sheet,
            layer=layer,
            annotation_type="polygon",
            geometry_json=polygon_geom,
            label="Shade area",
            created_by=self.user,
            updated_by=self.user,
        )
        create_resp = self.client.post(
            f"/api/preconstruction/annotations/{ann.id}/create_takeoff/",
            {},
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)
        primary = create_resp.json()["primary_takeoff"]
        self.assertEqual(primary["unit"], "square_feet")
        self.assertEqual(primary["quantity"], "1000.0000")
        payload = build_snapshot_payload(plan_set)
        sheet_data = payload["sheets"][0]
        self.assertEqual(len(sheet_data["takeoff_items"]), 1)
        self.assertEqual(sheet_data["takeoff_items"][0]["unit"], "square_feet")
        self.assertEqual(sheet_data["takeoff_items"][0]["quantity"], "1000.0000")
        self.assertEqual(len(sheet_data["layers"][0]["items"]), 1)
        self.assertEqual(sheet_data["layers"][0]["items"][0]["type"], "polygon")
        self.assertEqual(sheet_data["layers"][0]["items"][0]["geometry_json"], polygon_geom)

    def test_learning_audit_accept_with_edits_reflected_in_snapshot_export(self):
        """Accept a suggestion with edits (category/unit/quantity); snapshot and export reflect edited values and decision_state/review_state."""
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            provider_name="mock",
            user_prompt="doors",
            status=AIAnalysisRun.Status.COMPLETED,
            created_by=self.user,
        )
        suggestion = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            label="Door",
            rationale="Mock",
            confidence=0.9,
        )
        accept_resp = self.client.post(
            f"/api/preconstruction/suggestions/{suggestion.id}/accept/",
            {"category": "doors", "unit": "count", "quantity": "2", "label": "Double door"},
            format="json",
        )
        self.assertEqual(accept_resp.status_code, 200)
        snap_resp = self.client.post(
            "/api/preconstruction/snapshots/",
            {"project": str(self.project.id), "plan_set": str(plan_set.id), "name": "v1"},
            format="json",
        )
        self.assertEqual(snap_resp.status_code, 201)
        payload = snap_resp.json()["snapshot_payload_json"]
        sheet_data = payload["sheets"][0]
        self.assertEqual(len(sheet_data["takeoff_items"]), 2)  # door + door_hardware from assembly
        takeoff_categories = {t["category"] for t in sheet_data["takeoff_items"]}
        self.assertIn("doors", takeoff_categories)
        takeoff_doors = next(t for t in sheet_data["takeoff_items"] if t["category"] == "doors")
        self.assertEqual(takeoff_doors["unit"], "count")
        self.assertEqual(takeoff_doors["quantity"], "2.0000")
        self.assertEqual(takeoff_doors["review_state"], "edited")
        self.assertEqual(len(sheet_data["ai_suggestion_outcomes"]), 1)
        self.assertEqual(sheet_data["ai_suggestion_outcomes"][0]["decision_state"], "edited")
        export_resp = self.client.post(
            "/api/preconstruction/exports/",
            {"plan_set": str(plan_set.id), "export_type": "json"},
            format="json",
        )
        self.assertEqual(export_resp.status_code, 201)
        export_payload = export_resp.json()["payload"]
        exp_sheet = export_payload["sheets"][0]
        exp_doors = next(t for t in exp_sheet["takeoff_items"] if t["category"] == "doors")
        self.assertEqual(exp_doors["quantity"], "2.0000")
        self.assertEqual(exp_doors["review_state"], "edited")
        self.assertEqual(exp_sheet["ai_suggestion_outcomes"][0]["decision_state"], "edited")

    def test_snapshot_diff_snapshot_vs_current(self):
        """Diff between a snapshot and current live state returns takeoff and suggestion deltas."""
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        payload_v1 = build_snapshot_payload(plan_set)
        snap = RevisionSnapshot.objects.create(
            project=self.project,
            plan_set=plan_set,
            name="v1",
            status=RevisionSnapshot.Status.DRAFT,
            snapshot_payload_json=payload_v1,
            created_by=self.user,
        )
        TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            category=TakeoffItem.Category.DOORS,
            unit=TakeoffItem.Unit.COUNT,
            quantity=2,
            created_by=self.user,
            updated_by=self.user,
        )
        payload_current = build_snapshot_payload(plan_set)
        diff = compute_snapshot_diff(snap.snapshot_payload_json, payload_current)
        self.assertIn("takeoff_added", diff)
        self.assertIn("takeoff_removed", diff)
        self.assertIn("takeoff_changed", diff)
        self.assertIn("suggestion_summary", diff)
        added = [r for r in diff["takeoff_added"] if r["category"] == "doors" and r["unit"] == "count"]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["quantity"], "2.0000")

    def test_snapshot_diff_api(self):
        """GET snapshots/diff/?left=<id>&right=current returns 200 and structured diff."""
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        snap = RevisionSnapshot.objects.create(
            project=self.project,
            plan_set=plan_set,
            name="v1",
            status=RevisionSnapshot.Status.DRAFT,
            snapshot_payload_json=build_snapshot_payload(plan_set),
            created_by=self.user,
        )
        resp = self.client.get(
            "/api/preconstruction/snapshots/diff/",
            {"left": str(snap.id), "right": "current"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("takeoff_added", data)
        self.assertIn("takeoff_removed", data)
        self.assertIn("takeoff_changed", data)
        self.assertIn("suggestion_summary", data)

    def test_project_takeoff_rule_expansion(self):
        """When a project has a takeoff rule for doors, accept suggestion uses rule expansion instead of built-in."""
        self.client.login(username="estimator1", password="test-pass")
        ProjectTakeoffRule.objects.create(
            project=self.project,
            name="Door set",
            trigger_category="doors",
            trigger_label_pattern="",
            expansion_components=[
                {"category": "door_hardware", "unit": "each", "quantity_mode": "one"},
            ],
        )
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            provider_name="mock",
            user_prompt="doors",
            status=AIAnalysisRun.Status.COMPLETED,
            created_by=self.user,
        )
        suggestion = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            label="Door",
            rationale="Mock",
            confidence=0.9,
        )
        accept_resp = self.client.post(
            f"/api/preconstruction/suggestions/{suggestion.id}/accept/",
            {},
            format="json",
        )
        self.assertEqual(accept_resp.status_code, 200)
        takeoff_items = TakeoffItem.objects.filter(plan_sheet=plan_sheet).order_by("category")
        self.assertEqual(takeoff_items.count(), 2)
        categories = list(takeoff_items.values_list("category", flat=True))
        self.assertIn("doors", categories)
        self.assertIn("door_hardware", categories)
        door_hardware = takeoff_items.get(category="door_hardware")
        self.assertEqual(door_hardware.unit, "each")
        self.assertEqual(door_hardware.quantity, 1)

    def test_feedback_export_returns_suggestion_outcomes(self):
        """GET suggestions/feedback_export/?project= returns list of suggestion outcomes for calibration."""
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            storage_key="plans/test/sheet.pdf",
            created_by=self.user,
        )
        run = AIAnalysisRun.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            provider_name="mock",
            user_prompt="doors",
            status=AIAnalysisRun.Status.COMPLETED,
            created_by=self.user,
        )
        suggestion = AISuggestion.objects.create(
            analysis_run=run,
            project=self.project,
            plan_sheet=plan_sheet,
            suggestion_type="rectangle",
            label="Door",
            rationale="Mock",
            confidence=0.85,
            decision_state=AISuggestion.DecisionState.ACCEPTED,
        )
        ann = AnnotationItem.objects.create(
            project=self.project,
            plan_sheet=plan_sheet,
            layer=AnnotationLayer.objects.create(
                project=self.project,
                plan_set=plan_set,
                plan_sheet=plan_sheet,
                name="Default",
                created_by=self.user,
            ),
            annotation_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0, "y": 0, "width": 0.1, "height": 0.1},
            label="Door",
            created_by=self.user,
            updated_by=self.user,
        )
        takeoff = TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            category=TakeoffItem.Category.DOORS,
            unit=TakeoffItem.Unit.COUNT,
            quantity=1,
            source_annotation=ann,
            created_by=self.user,
            updated_by=self.user,
        )
        suggestion.accepted_annotation = ann
        suggestion.save(update_fields=["accepted_annotation"])
        resp = self.client.get(
            "/api/preconstruction/suggestions/feedback_export/",
            {"project": str(self.project.id)},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)
        row = next(r for r in data if r["id"] == str(suggestion.id))
        self.assertEqual(row["decision_state"], "accepted")
        self.assertEqual(row["accepted_category"], "doors")
        self.assertEqual(row["accepted_unit"], "count")
        self.assertEqual(row["accepted_quantity"], "1.0000")

    def test_snapshot_lock(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        snap = RevisionSnapshot.objects.create(
            project=self.project,
            plan_set=plan_set,
            name="v1",
            status=RevisionSnapshot.Status.DRAFT,
            snapshot_payload_json=build_snapshot_payload(plan_set),
            created_by=self.user,
        )
        lock_resp = self.client.post(
            f"/api/preconstruction/snapshots/{snap.id}/lock/",
            {},
            format="json",
        )
        self.assertEqual(lock_resp.status_code, 200)
        snap.refresh_from_db()
        self.assertEqual(snap.status, RevisionSnapshot.Status.LOCKED)
        self.assertGreaterEqual(
            AuditEvent.objects.filter(event_type="lock_revision_snapshot", object_id=str(snap.id)).count(),
            1,
        )

    def test_export_csv_creates_record(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        export_resp = self.client.post(
            "/api/preconstruction/exports/",
            {"plan_set": str(plan_set.id), "export_type": "csv"},
            format="json",
        )
        self.assertEqual(export_resp.status_code, 201)
        self.assertIn("payload", export_resp.json())
        record = ExportRecord.objects.get(plan_set=plan_set, export_type="csv")
        self.assertEqual(record.status, ExportRecord.Status.GENERATED)

    def test_export_invalid_type_rejected(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        export_resp = self.client.post(
            "/api/preconstruction/exports/",
            {"plan_set": str(plan_set.id), "export_type": "invalid_type"},
            format="json",
        )
        self.assertEqual(export_resp.status_code, 400)
        self.assertEqual(ExportRecord.objects.filter(plan_set=plan_set).count(), 0)

    def test_export_pdf_returns_generated_pdf(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        export_resp = self.client.post(
            "/api/preconstruction/exports/",
            {"plan_set": str(plan_set.id), "export_type": "pdf_metadata"},
            format="json",
        )
        self.assertEqual(export_resp.status_code, 200)
        self.assertEqual(export_resp.get("Content-Type", ""), "application/pdf")
        self.assertTrue(
            export_resp.content.startswith(b"%PDF"),
            "Response body should be PDF bytes",
        )
        record = ExportRecord.objects.get(plan_set=plan_set, export_type="pdf_metadata")
        self.assertEqual(record.status, ExportRecord.Status.GENERATED)

    def test_copilot_query_missing_project_returns_400(self):
        self.client.login(username="estimator1", password="test-pass")
        resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {"question": "how many doors?"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_copilot_query_blank_question_returns_400(self):
        self.client.login(username="estimator1", password="test-pass")
        resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {"project": str(self.project.id), "question": "   "},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_preconstruction_copilot_returns_grounded_takeoff_answer(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Bid Set A",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            title="First Floor",
            sheet_number="A101",
            storage_key="plans/test/a101.pdf",
            created_by=self.user,
        )
        TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            category=TakeoffItem.Category.DOORS,
            unit=TakeoffItem.Unit.COUNT,
            quantity="3",
            review_state=TakeoffItem.ReviewState.PENDING,
            created_by=self.user,
            updated_by=self.user,
        )
        TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            category=TakeoffItem.Category.DOORS,
            unit=TakeoffItem.Unit.COUNT,
            quantity="2",
            review_state=TakeoffItem.ReviewState.ACCEPTED,
            created_by=self.user,
            updated_by=self.user,
        )

        resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "question": "How many pending door takeoff items are on this plan set?",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "grounded")
        self.assertEqual(payload["scope"]["plan_set_name"], "Bid Set A")
        self.assertIn("pending", payload["answer"].lower())
        self.assertTrue(any(citation["kind"] == "takeoff_summary" for citation in payload["citations"]))

    def test_preconstruction_copilot_returns_analysis_action_plan_for_sheet_command(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Bid Set Actions",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            title="Action Sheet",
            sheet_number="A201",
            storage_key="plans/test/a201.pdf",
            created_by=self.user,
        )

        resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "plan_sheet": str(plan_sheet.id),
                "provider_name": "mock",
                "question": "Find all doors on this sheet",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "grounded")
        self.assertEqual(payload["action_plan"]["kind"], "run_analysis")
        self.assertEqual(payload["action_plan"]["provider_name"], "mock")
        self.assertIn("find all doors", payload["action_plan"]["prompt"].lower())

    def test_preconstruction_copilot_returns_takeoff_action_plan_for_selected_annotation(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Bid Set Actions",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            title="Action Sheet",
            sheet_number="A202",
            storage_key="plans/test/a202.pdf",
            created_by=self.user,
        )
        layer = AnnotationLayer.objects.create(
            project=self.project,
            plan_set=plan_set,
            plan_sheet=plan_sheet,
            name="Estimator",
            category="general",
            created_by=self.user,
        )
        annotation = AnnotationItem.objects.create(
            project=self.project,
            plan_sheet=plan_sheet,
            layer=layer,
            annotation_type="rectangle",
            geometry_json={"type": "rectangle", "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
            label="Door group",
            source="manual",
            review_state="pending",
            created_by=self.user,
        )

        resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "plan_sheet": str(plan_sheet.id),
                "annotation": str(annotation.id),
                "question": "Create takeoff package from this annotation",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "grounded")
        self.assertEqual(payload["action_plan"]["kind"], "create_takeoff_from_annotation")
        self.assertEqual(payload["action_plan"]["annotation_id"], str(annotation.id))

    def test_preconstruction_copilot_requires_annotation_for_takeoff_action_plan(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Bid Set Actions",
            created_by=self.user,
            updated_by=self.user,
        )
        plan_sheet = PlanSheet.objects.create(
            project=self.project,
            plan_set=plan_set,
            title="Action Sheet",
            sheet_number="A203",
            storage_key="plans/test/a203.pdf",
            created_by=self.user,
        )

        resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "plan_sheet": str(plan_sheet.id),
                "question": "Create takeoff package from this annotation",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "limited")
        self.assertNotIn("action_plan", payload)
        self.assertIn("select an annotation", payload["answer"].lower())

    def test_preconstruction_copilot_flags_document_questions(self):
        self.client.login(username="estimator1", password="test-pass")
        resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {
                "project": str(self.project.id),
                "question": "What spec section covers the door hardware package?",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "needs_documents")
        self.assertIn("do not have parsed project documents", payload["answer"].lower())
        self.assertTrue(any(citation["kind"] == "project" for citation in payload["citations"]))

    def test_preconstruction_copilot_reports_latest_snapshot_and_export(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Bid Set B",
            created_by=self.user,
            updated_by=self.user,
        )
        snapshot = RevisionSnapshot.objects.create(
            project=self.project,
            plan_set=plan_set,
            name="Pricing 1",
            status=RevisionSnapshot.Status.LOCKED,
            snapshot_payload_json=build_snapshot_payload(plan_set),
            created_by=self.user,
        )
        ExportRecord.objects.create(
            project=self.project,
            plan_set=plan_set,
            revision_snapshot=snapshot,
            export_type=ExportRecord.ExportType.CSV,
            status=ExportRecord.Status.GENERATED,
            created_by=self.user,
        )

        snap_resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "question": "What is the latest snapshot status?",
            },
            format="json",
        )
        export_resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "question": "What was the last export created?",
            },
            format="json",
        )

        self.assertEqual(snap_resp.status_code, 200)
        self.assertEqual(snap_resp.json()["status"], "grounded")
        self.assertIn("pricing 1", snap_resp.json()["answer"].lower())
        self.assertTrue(any(citation["kind"] == "snapshot" for citation in snap_resp.json()["citations"]))

        self.assertEqual(export_resp.status_code, 200)
        self.assertEqual(export_resp.json()["status"], "grounded")
        self.assertIn("csv", export_resp.json()["answer"].lower())
        self.assertTrue(any(citation["kind"] == "export" for citation in export_resp.json()["citations"]))

    def test_preconstruction_copilot_rejects_cross_project_scope(self):
        self.client.login(username="estimator1", password="test-pass")
        other_project = Project.objects.create(code="BID-6", name="Building F", location="Site V")
        ProjectMembership.objects.create(
            user=self.user,
            project=other_project,
            role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        other_set = PlanSet.objects.create(
            project=other_project,
            name="Other Set",
            created_by=self.user,
            updated_by=self.user,
        )

        resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {
                "project": str(self.project.id),
                "plan_set": str(other_set.id),
                "question": "List the plan sets for this project.",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 400)
        self.assertIn("plan set", str(resp.json()).lower())

    def test_project_document_upload_extracts_pdf_text(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Docs Set",
            created_by=self.user,
            updated_by=self.user,
        )
        pdf = BytesIO(
            build_pdf_with_text(
                "Section 087100 door hardware.",
                "Provide hardware set BH-1 at all rated openings.",
            )
        )
        pdf.name = "door-spec.pdf"

        resp = self.client.post(
            "/api/preconstruction/documents/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "title": "Door Hardware Spec",
                "document_type": "spec",
                "file": pdf,
            },
            format="multipart",
        )

        self.assertEqual(resp.status_code, 201)
        payload = resp.json()
        self.assertEqual(payload["parse_status"], ProjectDocument.ParseStatus.PARSED)
        self.assertEqual(payload["document_type"], ProjectDocument.DocumentType.SPEC)
        document = ProjectDocument.objects.get(id=payload["id"])
        self.assertGreater(document.page_count, 0)
        self.assertIn("BH-1", document.extracted_text)
        self.assertGreater(document.chunks.count(), 0)
        self.assertGreaterEqual(
            AuditEvent.objects.filter(event_type="upload_project_document", object_id=str(document.id)).count(),
            1,
        )

    @override_settings(
        PRECONSTRUCTION_DOCUMENT_OCR_ENABLED=True,
        PRECONSTRUCTION_DOCUMENT_OCR_MIN_TEXT_CHARS=24,
    )
    @patch("preconstruction.document_services._resolve_ocr_command", return_value=["tesseract"])
    @patch("preconstruction.document_services._run_pdf_page_ocr", return_value="Rated openings require hardware set BH-OCR.")
    def test_project_document_upload_uses_ocr_for_scanned_pdf(self, _run_pdf_page_ocr, _resolve_ocr_command):
        self.client.login(username="estimator1", password="test-pass")
        pdf = BytesIO(build_blank_pdf())
        pdf.name = "scanned-spec.pdf"

        resp = self.client.post(
            "/api/preconstruction/documents/",
            {
                "project": str(self.project.id),
                "title": "Scanned Spec",
                "document_type": "spec",
                "file": pdf,
            },
            format="multipart",
        )

        self.assertEqual(resp.status_code, 201)
        payload = resp.json()
        self.assertEqual(payload["parse_status"], ProjectDocument.ParseStatus.PARSED)
        document = ProjectDocument.objects.get(id=payload["id"])
        self.assertIn("BH-OCR", document.extracted_text)
        self.assertTrue(_run_pdf_page_ocr.called)

    @override_settings(
        PRECONSTRUCTION_DOCUMENT_OCR_ENABLED=True,
        PRECONSTRUCTION_DOCUMENT_OCR_COMMAND="tesseract --oem 1",
        PRECONSTRUCTION_DOCUMENT_OCR_SCALE=2,
        PRECONSTRUCTION_DOCUMENT_OCR_TIMEOUT_SECONDS=5,
    )
    @patch("preconstruction.document_services.subprocess.run")
    @patch("preconstruction.document_services.shutil.which")
    def test_project_document_ocr_command_supports_extra_flags(self, mock_which, mock_run):
        mock_which.side_effect = lambda value: "C:/Tools/tesseract.exe" if value == "tesseract" else None
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="OCR text")

        resolved = document_services._resolve_ocr_command()

        self.assertEqual(resolved, ["C:/Tools/tesseract.exe", "--oem", "1"])

        page = SimpleNamespace(
            get_pixmap=lambda matrix, alpha=False: SimpleNamespace(save=lambda path: None)
        )
        fitz_module = SimpleNamespace(Matrix=lambda x, y: (x, y))

        text = document_services._run_pdf_page_ocr(page, fitz_module, resolved)

        self.assertEqual(text, "OCR text")
        command = mock_run.call_args.args[0]
        self.assertEqual(command[:3], ["C:/Tools/tesseract.exe", "--oem", "1"])
        self.assertTrue(command[3].endswith(".png"))
        self.assertEqual(command[-3:], ["stdout", "--psm", "6"])

    def test_project_document_upload_promotes_safe_file_and_serves_download(self):
        self.client.login(username="estimator1", password="test-pass")
        pdf = BytesIO(build_pdf_with_text("Door hardware spec.", "Use BH-3 at rated openings."))
        pdf.name = "hardware-spec.pdf"

        resp = self.client.post(
            "/api/preconstruction/documents/",
            {
                "project": str(self.project.id),
                "title": "Hardware Spec",
                "document_type": "spec",
                "file": pdf,
            },
            format="multipart",
        )

        self.assertEqual(resp.status_code, 201)
        document = ProjectDocument.objects.get(id=resp.json()["id"])
        self.assertEqual(document.parse_status, ProjectDocument.ParseStatus.PARSED)
        self.assertIn("/safe/", document.storage_key.replace("\\", "/"))
        self.assertTrue(get_project_document_file_path(document.storage_key).exists())

        file_resp = self.client.get(f"/api/preconstruction/documents/{document.id}/file/")
        self.assertEqual(file_resp.status_code, 200)
        self.assertIn("attachment;", file_resp.get("Content-Disposition", ""))

    @patch("preconstruction.document_services._extract_pdf_pages", side_effect=ValueError("synthetic parser failure"))
    def test_project_document_upload_parser_failure_is_quarantined(self, _extract_pdf_pages):
        self.client.login(username="estimator1", password="test-pass")
        pdf = BytesIO(MINIMAL_PDF)
        pdf.name = "broken-spec.pdf"

        resp = self.client.post(
            "/api/preconstruction/documents/",
            {
                "project": str(self.project.id),
                "title": "Broken Spec",
                "document_type": "spec",
                "file": pdf,
            },
            format="multipart",
        )

        self.assertEqual(resp.status_code, 201)
        payload = resp.json()
        self.assertEqual(payload["parse_status"], ProjectDocument.ParseStatus.FAILED)
        self.assertIn("synthetic parser failure", payload["parse_error"])
        document = ProjectDocument.objects.get(id=payload["id"])
        self.assertIn("/quarantine/", document.storage_key.replace("\\", "/"))
        self.assertTrue(get_project_document_file_path(document.storage_key).exists())

        file_resp = self.client.get(f"/api/preconstruction/documents/{document.id}/file/")
        self.assertEqual(file_resp.status_code, 409)

    def test_project_document_delete_removes_stored_file(self):
        self.client.login(username="estimator1", password="test-pass")
        pdf = BytesIO(build_pdf_with_text("Delete me."))
        pdf.name = "delete-me.pdf"

        create_resp = self.client.post(
            "/api/preconstruction/documents/",
            {
                "project": str(self.project.id),
                "title": "Delete Me",
                "document_type": "other",
                "file": pdf,
            },
            format="multipart",
        )

        self.assertEqual(create_resp.status_code, 201)
        document = ProjectDocument.objects.get(id=create_resp.json()["id"])
        path = get_project_document_file_path(document.storage_key)
        self.assertTrue(path.exists())

        delete_resp = self.client.delete(f"/api/preconstruction/documents/{document.id}/")
        self.assertEqual(delete_resp.status_code, 204)
        self.assertFalse(ProjectDocument.objects.filter(id=document.id).exists())
        self.assertFalse(path.exists())

    def test_project_document_copilot_answers_from_uploaded_documents(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Docs Set",
            created_by=self.user,
            updated_by=self.user,
        )
        pdf = BytesIO(
            build_pdf_with_text(
                "Section 087100 door hardware.",
                "Provide hardware set BH-1 at all rated openings.",
                "Use brushed stainless lever hardware.",
            )
        )
        pdf.name = "hardware-spec.pdf"
        upload_resp = self.client.post(
            "/api/preconstruction/documents/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "title": "Hardware Spec",
                "document_type": "spec",
                "file": pdf,
            },
            format="multipart",
        )
        self.assertEqual(upload_resp.status_code, 201)

        resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "question": "What hardware set is called for at rated openings?",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "grounded")
        self.assertIn("bh-1", payload["answer"].lower())
        self.assertTrue(any(citation["kind"] == "document" for citation in payload["citations"]))

    def test_project_document_copilot_prefers_newer_matching_documents(self):
        self.client.login(username="estimator1", password="test-pass")
        older_doc = ProjectDocument.objects.create(
            project=self.project,
            title="Door Notes 1",
            document_type=ProjectDocument.DocumentType.SPEC,
            original_filename="older.txt",
            storage_key="project_documents/mock/project/safe/older.txt",
            mime_type="text/plain",
            file_extension="txt",
            size_bytes=32,
            page_count=1,
            extracted_text="Rated openings use hardware set BH-OLD.",
            parse_status=ProjectDocument.ParseStatus.PARSED,
            created_by=self.user,
            updated_by=self.user,
        )
        ProjectDocumentChunk.objects.create(
            document=older_doc,
            chunk_index=0,
            page_number=1,
            content="Rated openings use hardware set BH-OLD.",
        )
        ProjectDocument.objects.filter(id=older_doc.id).update(created_at=timezone.now() - timedelta(days=2))

        newer_doc = ProjectDocument.objects.create(
            project=self.project,
            title="Door Notes 2",
            document_type=ProjectDocument.DocumentType.ADDENDUM,
            original_filename="newer.txt",
            storage_key="project_documents/mock/project/safe/newer.txt",
            mime_type="text/plain",
            file_extension="txt",
            size_bytes=32,
            page_count=1,
            extracted_text="Rated openings use hardware set BH-NEW.",
            parse_status=ProjectDocument.ParseStatus.PARSED,
            created_by=self.user,
            updated_by=self.user,
        )
        ProjectDocumentChunk.objects.create(
            document=newer_doc,
            chunk_index=0,
            page_number=1,
            content="Rated openings use hardware set BH-NEW.",
        )
        ProjectDocument.objects.filter(id=newer_doc.id).update(created_at=timezone.now() - timedelta(days=1))

        resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {
                "project": str(self.project.id),
                "question": "What hardware set is called for at rated openings?",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "grounded")
        self.assertGreaterEqual(len(payload["citations"]), 2)
        self.assertEqual(payload["citations"][0]["label"], "Door Notes 2")
        self.assertIn("bh-new", payload["answer"].lower())

    def test_project_document_copilot_prefers_plan_set_scoped_docs_when_in_scope(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Scope Set",
            created_by=self.user,
            updated_by=self.user,
        )
        project_doc = ProjectDocument.objects.create(
            project=self.project,
            title="Project Hardware Spec",
            document_type=ProjectDocument.DocumentType.SPEC,
            original_filename="project.txt",
            storage_key="project_documents/mock/project/safe/project.txt",
            mime_type="text/plain",
            file_extension="txt",
            size_bytes=32,
            page_count=1,
            extracted_text="Rated openings use hardware set BH-PROJECT.",
            parse_status=ProjectDocument.ParseStatus.PARSED,
            created_by=self.user,
            updated_by=self.user,
        )
        ProjectDocumentChunk.objects.create(
            document=project_doc,
            chunk_index=0,
            page_number=1,
            content="Rated openings use hardware set BH-PROJECT.",
        )
        ProjectDocument.objects.filter(id=project_doc.id).update(created_at=timezone.now())

        plan_set_doc = ProjectDocument.objects.create(
            project=self.project,
            plan_set=plan_set,
            title="Scoped Hardware Spec",
            document_type=ProjectDocument.DocumentType.SPEC,
            original_filename="scoped.txt",
            storage_key="project_documents/mock/scope-set/safe/scoped.txt",
            mime_type="text/plain",
            file_extension="txt",
            size_bytes=32,
            page_count=1,
            extracted_text="Rated openings use hardware set BH-SCOPED.",
            parse_status=ProjectDocument.ParseStatus.PARSED,
            created_by=self.user,
            updated_by=self.user,
        )
        ProjectDocumentChunk.objects.create(
            document=plan_set_doc,
            chunk_index=0,
            page_number=1,
            content="Rated openings use hardware set BH-SCOPED.",
        )
        ProjectDocument.objects.filter(id=plan_set_doc.id).update(created_at=timezone.now() - timedelta(days=1))

        resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "question": "What hardware set is called for at rated openings?",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "grounded")
        self.assertEqual(payload["citations"][0]["label"], "Scoped Hardware Spec")
        self.assertIn("bh-scoped", payload["answer"].lower())

    def test_project_document_copilot_prefers_matching_document_type_keywords(self):
        self.client.login(username="estimator1", password="test-pass")
        spec_doc = ProjectDocument.objects.create(
            project=self.project,
            title="Door Spec",
            document_type=ProjectDocument.DocumentType.SPEC,
            original_filename="spec.txt",
            storage_key="project_documents/mock/project/safe/spec.txt",
            mime_type="text/plain",
            file_extension="txt",
            size_bytes=32,
            page_count=1,
            extracted_text="Rated openings use hardware set BH-SPEC.",
            parse_status=ProjectDocument.ParseStatus.PARSED,
            created_by=self.user,
            updated_by=self.user,
        )
        ProjectDocumentChunk.objects.create(
            document=spec_doc,
            chunk_index=0,
            page_number=1,
            content="Rated openings use hardware set BH-SPEC.",
        )
        addendum_doc = ProjectDocument.objects.create(
            project=self.project,
            title="Addendum 4",
            document_type=ProjectDocument.DocumentType.ADDENDUM,
            original_filename="addendum.txt",
            storage_key="project_documents/mock/project/safe/addendum.txt",
            mime_type="text/plain",
            file_extension="txt",
            size_bytes=32,
            page_count=1,
            extracted_text="Addendum 4 revises rated openings to hardware set BH-ADD.",
            parse_status=ProjectDocument.ParseStatus.PARSED,
            created_by=self.user,
            updated_by=self.user,
        )
        ProjectDocumentChunk.objects.create(
            document=addendum_doc,
            chunk_index=0,
            page_number=1,
            content="Addendum 4 revises rated openings to hardware set BH-ADD.",
        )

        resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {
                "project": str(self.project.id),
                "question": "What does addendum 4 say about rated openings?",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "grounded")
        self.assertEqual(payload["citations"][0]["label"], "Addendum 4")
        self.assertIn("bh-add", payload["answer"].lower())

    def test_project_document_scope_includes_project_wide_docs_for_plan_set_queries(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Bid Set C",
            created_by=self.user,
            updated_by=self.user,
        )
        pdf = BytesIO(
            build_pdf_with_text(
                "Addendum 2.",
                "All storefront framing shall use thermally broken members.",
            )
        )
        pdf.name = "addendum.pdf"
        upload_resp = self.client.post(
            "/api/preconstruction/documents/",
            {
                "project": str(self.project.id),
                "title": "Addendum 2",
                "document_type": "addendum",
                "file": pdf,
            },
            format="multipart",
        )
        self.assertEqual(upload_resp.status_code, 201)

        resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "question": "What does addendum 2 say about storefront framing?",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "grounded")
        self.assertIn("thermally broken", payload["answer"].lower())

    def test_preconstruction_copilot_routes_category_review_questions_to_takeoff_summary(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Bid Set Doors",
            created_by=self.user,
            updated_by=self.user,
        )
        TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            category=TakeoffItem.Category.DOORS,
            unit=TakeoffItem.Unit.COUNT,
            quantity="4",
            review_state=TakeoffItem.ReviewState.PENDING,
            created_by=self.user,
            updated_by=self.user,
        )
        TakeoffItem.objects.create(
            project=self.project,
            plan_set=plan_set,
            category=TakeoffItem.Category.DOORS,
            unit=TakeoffItem.Unit.COUNT,
            quantity="2",
            review_state=TakeoffItem.ReviewState.ACCEPTED,
            created_by=self.user,
            updated_by=self.user,
        )

        resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "question": "Are there pending doors on this plan set?",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "grounded")
        self.assertIn("pending", payload["answer"].lower())
        self.assertTrue(any(citation["kind"] == "takeoff_summary" for citation in payload["citations"]))

    def test_preconstruction_copilot_does_not_false_match_outdoor_as_doors(self):
        self.client.login(username="estimator1", password="test-pass")
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Exterior Scope",
            created_by=self.user,
            updated_by=self.user,
        )

        resp = self.client.post(
            "/api/preconstruction/copilot/query/",
            {
                "project": str(self.project.id),
                "plan_set": str(plan_set.id),
                "question": "Do we have outdoor staging concerns on this plan set?",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "grounded")
        self.assertIn("is currently draft", payload["answer"].lower())
        self.assertNotIn("door", payload["answer"].lower())

    def test_preconstruction_requires_auth(self):
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Set",
            created_by=self.user,
            updated_by=self.user,
        )
        resp = self.client.get("/api/preconstruction/sets/")
        self.assertEqual(resp.status_code, 403)

    def test_preconstruction_scoped_to_project(self):
        other_user = User.objects.create_user(username="other", password="test-pass")
        other_project = Project.objects.create(code="OTHER", name="Other", location="Elsewhere")
        ProjectMembership.objects.create(
            user=other_user,
            project=other_project,
            role=ProjectMembership.Role.FOREMAN,
        )
        plan_set = PlanSet.objects.create(
            project=self.project,
            name="Our Set",
            created_by=self.user,
            updated_by=self.user,
        )
        self.client.login(username="other", password="test-pass")
        resp = self.client.get("/api/preconstruction/sets/")
        self.assertEqual(resp.status_code, 200)
        ids = [s["id"] for s in resp.json()]
        self.assertNotIn(str(plan_set.id), ids)
