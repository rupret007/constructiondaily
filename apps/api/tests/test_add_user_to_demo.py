"""Tests for add_user_to_demo management command."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.models import Project, ProjectMembership
from django.contrib.auth.models import User


class AddUserToDemoCommandTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            code="DEMO-001",
            name="Demo Construction Project",
            location="Test Site",
        )
        self.user = User.objects.create_user(username="devuser", password="test")

    def test_add_user_to_demo_creates_membership(self):
        out = StringIO()
        call_command("add_user_to_demo", "devuser", stdout=out)
        self.assertIn("Added devuser to DEMO-001", out.getvalue())
        self.assertTrue(
            ProjectMembership.objects.filter(
                user=self.user, project=self.project, role=ProjectMembership.Role.PROJECT_MANAGER
            ).exists()
        )

    def test_add_user_to_demo_idempotent(self):
        ProjectMembership.objects.create(
            user=self.user, project=self.project, role=ProjectMembership.Role.PROJECT_MANAGER
        )
        out = StringIO()
        call_command("add_user_to_demo", "devuser", stdout=out)
        self.assertIn("already has a membership", out.getvalue())
        self.assertEqual(
            ProjectMembership.objects.filter(user=self.user, project=self.project).count(), 1
        )

    def test_add_user_to_demo_nonexistent_user_raises(self):
        with self.assertRaises(Exception) as ctx:
            call_command("add_user_to_demo", "nonexistent", stdout=StringIO())
        self.assertIn("nonexistent", str(ctx.exception))

    def test_add_user_to_demo_no_project_raises(self):
        Project.objects.filter(code="DEMO-001").delete()
        with self.assertRaises(Exception) as ctx:
            call_command("add_user_to_demo", "devuser", stdout=StringIO())
        self.assertIn("Demo project not found", str(ctx.exception))

    def test_add_user_to_demo_no_username_lists_members(self):
        ProjectMembership.objects.create(
            user=self.user, project=self.project, role=ProjectMembership.Role.FOREMAN
        )
        out = StringIO()
        call_command("add_user_to_demo", stdout=out)
        self.assertIn("Usage:", out.getvalue())
        self.assertIn("devuser", out.getvalue())
        self.assertIn("foreman", out.getvalue())
