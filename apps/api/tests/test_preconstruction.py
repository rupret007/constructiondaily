"""Tests for Preconstruction Plan Annotation API and services."""

from __future__ import annotations

from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from audit.models import AuditEvent
from core.models import Project, ProjectMembership
from preconstruction.models import (
    AIAnalysisRun,
    AISuggestion,
    AnnotationItem,
    AnnotationLayer,
    ExportRecord,
    PlanSet,
    PlanSheet,
    RevisionSnapshot,
    TakeoffItem,
)
from preconstruction.services import (
    accept_suggestion,
    batch_accept_suggestions,
    build_snapshot_payload,
    reject_suggestion,
    run_plan_analysis,
)
from preconstruction.providers.registry import get_provider


# Minimal valid PDF bytes (single page)
MINIMAL_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n%%EOF"


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
                "quantity": "4",
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)
        self.assertEqual(create_resp.json()["quantity"], "4.0000")
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

    def test_provider_registry(self):
        provider = get_provider("mock")
        self.assertIsNotNone(provider)
        from preconstruction.providers.base import BaseAnalysisProvider
        self.assertTrue(isinstance(provider, BaseAnalysisProvider))
        with self.assertRaises(ValueError):
            get_provider("nonexistent")

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
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.decision_state, AISuggestion.DecisionState.EDITED)
        self.assertGreaterEqual(
            AuditEvent.objects.filter(event_type="edit_ai_suggestion").count(),
            1,
        )

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

    def test_export_pdf_metadata_placeholder(self):
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
        self.assertEqual(export_resp.status_code, 201)
        self.assertIn("payload", export_resp.json())
        payload = export_resp.json()["payload"]
        self.assertIn("message", payload)
        self.assertIn("plan_set_id", payload)
        self.assertEqual(payload["plan_set_id"], str(plan_set.id))
        record = ExportRecord.objects.get(plan_set=plan_set, export_type="pdf_metadata")
        self.assertEqual(record.status, ExportRecord.Status.GENERATED)

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
