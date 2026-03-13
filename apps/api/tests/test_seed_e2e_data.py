from __future__ import annotations

from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from core.models import Project, ProjectMembership


class SeedE2EDataCommandTests(TestCase):
    def test_seed_e2e_data_creates_user_project_and_membership(self):
        out = StringIO()

        call_command("seed_e2e_data", stdout=out)

        user = User.objects.get(username="e2e_pm")
        project = Project.objects.get(code="E2E-001")
        self.assertTrue(user.check_password("e2e-pass-123"))
        self.assertEqual(project.name, "E2E Smoke Project")
        self.assertTrue(
            ProjectMembership.objects.filter(
                user=user,
                project=project,
                role=ProjectMembership.Role.PROJECT_MANAGER,
                is_active=True,
            ).exists()
        )
        self.assertIn("Prepared E2E user e2e_pm", out.getvalue())

    def test_seed_e2e_data_is_idempotent_and_reactivates_membership(self):
        user = User.objects.create_user(username="e2e_pm", password="old-pass")
        project = Project.objects.create(code="E2E-001", name="Old", location="Old")
        membership = ProjectMembership.objects.create(
            user=user,
            project=project,
            role=ProjectMembership.Role.PROJECT_MANAGER,
            is_active=False,
        )

        call_command("seed_e2e_data", stdout=StringIO())

        user.refresh_from_db()
        project.refresh_from_db()
        membership.refresh_from_db()
        self.assertTrue(user.check_password("e2e-pass-123"))
        self.assertEqual(project.name, "E2E Smoke Project")
        self.assertEqual(project.location, "Automation Yard")
        self.assertTrue(membership.is_active)
