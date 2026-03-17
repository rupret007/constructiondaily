from __future__ import annotations

from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from core.models import Project, ProjectMembership
from reports.models import DailyReport


class SeedE2EDataCommandTests(TestCase):
    def test_seed_e2e_data_creates_project_and_role_specific_users(self):
        out = StringIO()

        call_command("seed_e2e_data", stdout=out)

        project = Project.objects.get(code="E2E-001")
        self.assertEqual(project.name, "E2E Smoke Project")
        for username, role in {
            "e2e_super": ProjectMembership.Role.SUPERINTENDENT,
            "e2e_pm": ProjectMembership.Role.PROJECT_MANAGER,
            "e2e_admin": ProjectMembership.Role.ADMIN,
        }.items():
            user = User.objects.get(username=username)
            self.assertTrue(user.check_password("e2e-pass-123"))
            self.assertTrue(
                ProjectMembership.objects.filter(
                    user=user,
                    project=project,
                    role=role,
                    is_active=True,
                ).exists()
            )
        self.assertIn("Prepared E2E project E2E-001", out.getvalue())

    def test_seed_e2e_data_is_idempotent_reactivates_memberships_and_resets_project_data(self):
        users = {
            "e2e_super": ProjectMembership.Role.SUPERINTENDENT,
            "e2e_pm": ProjectMembership.Role.PROJECT_MANAGER,
            "e2e_admin": ProjectMembership.Role.ADMIN,
        }
        project = Project.objects.create(code="E2E-001", name="Old", location="Old")
        memberships = []
        for username, role in users.items():
            user = User.objects.create_user(username=username, password="old-pass")
            memberships.append(
                ProjectMembership.objects.create(
                    user=user,
                    project=project,
                    role=role,
                    is_active=False,
                )
            )
        DailyReport.objects.create(
            project=project,
            report_date="2026-03-17",
            location="Old",
            prepared_by=User.objects.get(username="e2e_super"),
        )

        call_command("seed_e2e_data", stdout=StringIO())

        project.refresh_from_db()
        self.assertEqual(project.name, "E2E Smoke Project")
        self.assertEqual(project.location, "Automation Yard")
        self.assertEqual(project.daily_reports.count(), 0)
        for membership in memberships:
            membership.refresh_from_db()
            membership.user.refresh_from_db()
            self.assertTrue(membership.user.check_password("e2e-pass-123"))
            self.assertTrue(membership.is_active)
