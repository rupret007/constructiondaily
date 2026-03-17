"""Tests for seed_simple management command."""

from __future__ import annotations

from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from core.models import Project, ProjectMembership


class SeedSimpleCommandTests(TestCase):
    def test_seed_simple_creates_admin_and_demo_project(self):
        out = StringIO()
        call_command("seed_simple", stdout=out)

        user = User.objects.get(username="admin")
        self.assertTrue(user.check_password("admin"))
        project = Project.objects.get(code="DEMO")
        self.assertEqual(project.name, "Demo Project")
        membership = ProjectMembership.objects.get(user=user, project=project)
        self.assertEqual(membership.role, ProjectMembership.Role.PROJECT_MANAGER)
        self.assertTrue(membership.is_active)
        self.assertIn("admin", out.getvalue())

    def test_seed_simple_custom_username_password(self):
        call_command("seed_simple", "--username", "demo", "--password", "demo")

        user = User.objects.get(username="demo")
        self.assertTrue(user.check_password("demo"))
        self.assertTrue(
            ProjectMembership.objects.filter(user=user, project__code="DEMO", is_active=True).exists()
        )

    def test_seed_simple_idempotent(self):
        call_command("seed_simple")
        call_command("seed_simple")

        self.assertEqual(User.objects.filter(username="admin").count(), 1)
        self.assertEqual(Project.objects.filter(code="DEMO").count(), 1)
