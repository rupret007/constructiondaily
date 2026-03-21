"""Regression tests for DailyReport API endpoints."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Project, ProjectMembership
from reports.models import (
    ApprovalAction,
    DailyReport,
    DelayEntry,
    EquipmentEntry,
    LaborEntry,
    MaterialEntry,
    WorkLogEntry,
)


class DailyReportN1QueryRegressionTest(TestCase):
    """Regression tests to ensure N+1 query issues are prevented in DailyReport detail endpoint.

    The DailyReport detail endpoint (/api/reports/daily/{id}/) should use prefetch_related
    to avoid N+1 queries when loading related entries (labor, equipment, materials, etc.).
    Target: ~3-6 queries for a report with multiple related entries.
    """

    def setUp(self):
        self.client = APIClient()
        self.superintendent = User.objects.create_user(
            username="reports_super", password="test-pass"
        )
        self.project = Project.objects.create(
            code="N1QR-1", name="N+1 Query Regression Test", location="Site 1"
        )
        ProjectMembership.objects.create(
            user=self.superintendent,
            project=self.project,
            role=ProjectMembership.Role.SUPERINTENDENT,
        )
        self.report = DailyReport.objects.create(
            project=self.project,
            report_date="2026-03-15",
            location="Test Site",
            prepared_by=self.superintendent,
            summary="Regression test report",
        )

    def _create_labor_entries(self, count: int):
        """Create multiple labor entries for the report."""
        for i in range(count):
            LaborEntry.objects.create(
                report=self.report,
                trade=f"Trade {i}",
                company="Test Company",
                workers=2,
                regular_hours=8,
                overtime_hours=0,
            )

    def _create_equipment_entries(self, count: int):
        """Create multiple equipment entries for the report."""
        for i in range(count):
            EquipmentEntry.objects.create(
                report=self.report,
                equipment_name=f"Equipment {i}",
                quantity=1,
                hours_used=4,
            )

    def _create_material_entries(self, count: int):
        """Create multiple material entries for the report."""
        for i in range(count):
            MaterialEntry.objects.create(
                report=self.report,
                material_name=f"Material {i}",
                unit="tons",
                quantity_delivered=1.5,
            )

    def _create_work_log_entries(self, count: int):
        """Create multiple work log entries for the report."""
        for i in range(count):
            WorkLogEntry.objects.create(
                report=self.report,
                area="Main Bldg",
                activity=f"Work log entry {i}",
            )

    def _create_delay_entries(self, count: int):
        """Create multiple delay entries for the report."""
        for i in range(count):
            DelayEntry.objects.create(
                report=self.report,
                cause=f"Delay reason {i}",
                impact="Big impact",
                hours_lost=0.5,
            )

    def _create_approval_actions(self, count: int):
        """Create multiple approval actions for the report."""
        for i in range(count):
            ApprovalAction.objects.create(
                report=self.report,
                actor=self.superintendent,
                action=ApprovalAction.Action.APPROVE,
                reason=f"Approved {i}",
            )

    def test_daily_report_detail_query_count_with_related_entries(self):
        """DailyReport detail should not cause N+1 queries with prefetch_related."""
        # Create multiple related entries
        self._create_labor_entries(10)
        self._create_equipment_entries(8)
        self._create_material_entries(5)
        self._create_work_log_entries(6)
        self._create_delay_entries(3)
        self._create_approval_actions(2)

        self.client.login(username="reports_super", password="test-pass")

        # Target: ~6 queries
        # 1. User/Session (auth)
        # 2. DailyReport (the object)
        # 3. ProjectMembership (get_queryset filter)
        # 4. Prefetch: laborentry_set
        # 5. Prefetch: equipmententry_set
        # 6. Prefetch: materialentry_set
        # 7. Prefetch: worklogentry_set
        # 8. Prefetch: delayentry_set
        # 9. Prefetch: approval_actions (plus actor select_related)
        # 10. Prefetch: safety_entries (empty)
        # 11. Prefetch: attachments (empty)
        # 12. Prefetch: snapshots (empty)
        # The goal is that it stays CONSTANT regardless of entry count.
        
        with self.assertNumQueries(12):
            response = self.client.get(f"/api/reports/daily/{self.report.id}/")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify all related entries are included (names from serializer)
        self.assertIn("labor_entries", data)
        self.assertIn("equipment_entries", data)
        self.assertIn("material_entries", data)
        self.assertIn("work_entries", data)
        self.assertIn("delay_entries", data)
        self.assertIn("approval_actions", data)

        # Verify counts match what we created
        self.assertEqual(len(data["labor_entries"]), 10)
        self.assertEqual(len(data["equipment_entries"]), 8)
        self.assertEqual(len(data["material_entries"]), 5)
        self.assertEqual(len(data["work_entries"]), 6)
        self.assertEqual(len(data["delay_entries"]), 3)
        self.assertEqual(len(data["approval_actions"]), 2)

    def test_daily_report_detail_query_count_is_constant(self):
        """Verify query count doesn't increase with more data (N+1 check)."""
        self.client.login(username="reports_super", password="test-pass")
        
        # 1. Baseline with 1 entry each
        self._create_labor_entries(1)
        self._create_equipment_entries(1)
        with self.assertNumQueries(12):
            self.client.get(f"/api/reports/daily/{self.report.id}/")
            
        # 2. Add 20 more entries
        self._create_labor_entries(20)
        self._create_equipment_entries(20)
        
        # Query count should remain EXACTLY the same
        with self.assertNumQueries(12):
            self.client.get(f"/api/reports/daily/{self.report.id}/")

    def test_daily_report_list_query_performance(self):
        """DailyReport list should also perform efficiently."""
        # Create multiple reports
        for i in range(5):
            DailyReport.objects.create(
                project=self.project,
                report_date=f"2026-03-{10 + i}",
                location="Test Site",
                prepared_by=self.superintendent,
                summary=f"Report {i}",
            )

        self.client.login(username="reports_super", password="test-pass")

        # 1. Auth/User
        # 2. ProjectMembership
        # 3. DailyReports (select_related project, prepared_by, locked_by)
        with self.assertNumQueries(3):
            response = self.client.get("/api/reports/daily/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(len(data), 5)
