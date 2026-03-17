from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Project, ProjectMembership


class ProjectMembershipGuardTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_user(username="pm_admin", password="test-pass")
        self.pm_user = User.objects.create_user(username="pm_manager", password="test-pass")
        self.worker_user = User.objects.create_user(username="pm_worker", password="test-pass")
        self.other_user = User.objects.create_user(username="pm_other", password="test-pass")
        self.superuser = User.objects.create_superuser(
            username="pm_root",
            password="test-pass",
            email="root@example.com",
        )
        self.project_a = Project.objects.create(code="PM-A", name="Project A", location="A")
        self.project_b = Project.objects.create(code="PM-B", name="Project B", location="B")
        ProjectMembership.objects.create(
            user=self.admin_user,
            project=self.project_a,
            role=ProjectMembership.Role.ADMIN,
        )
        ProjectMembership.objects.create(
            user=self.pm_user,
            project=self.project_a,
            role=ProjectMembership.Role.PROJECT_MANAGER,
        )
        self.worker_membership = ProjectMembership.objects.create(
            user=self.worker_user,
            project=self.project_a,
            role=ProjectMembership.Role.FOREMAN,
        )

    def test_membership_update_cannot_change_project(self):
        self.client.login(username="pm_admin", password="test-pass")
        response = self.client.patch(
            f"/api/projects/memberships/{self.worker_membership.id}/",
            {"project": str(self.project_b.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.worker_membership.refresh_from_db()
        self.assertEqual(self.worker_membership.project_id, self.project_a.id)

    def test_membership_update_cannot_change_user(self):
        self.client.login(username="pm_admin", password="test-pass")
        response = self.client.patch(
            f"/api/projects/memberships/{self.worker_membership.id}/",
            {"user_id": self.other_user.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.worker_membership.refresh_from_db()
        self.assertEqual(self.worker_membership.user_id, self.worker_user.id)

    def test_membership_create_invalid_user_rejected(self):
        self.client.login(username="pm_admin", password="test-pass")
        response = self.client.post(
            "/api/projects/memberships/",
            {
                "project": str(self.project_a.id),
                "user_id": 999999,
                "role": ProjectMembership.Role.FOREMAN,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_superuser_can_create_membership(self):
        self.client.login(username="pm_root", password="test-pass")
        response = self.client.post(
            "/api/projects/memberships/",
            {
                "project": str(self.project_b.id),
                "user_id": self.other_user.id,
                "role": ProjectMembership.Role.SUPERINTENDENT,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=self.project_b,
                user=self.other_user,
                role=ProjectMembership.Role.SUPERINTENDENT,
            ).exists()
        )

    def test_project_manager_cannot_create_admin_membership(self):
        self.client.login(username="pm_manager", password="test-pass")
        response = self.client.post(
            "/api/projects/memberships/",
            {
                "project": str(self.project_a.id),
                "user_id": self.other_user.id,
                "role": ProjectMembership.Role.ADMIN,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_project_manager_cannot_promote_membership_to_project_manager(self):
        self.client.login(username="pm_manager", password="test-pass")
        response = self.client.patch(
            f"/api/projects/memberships/{self.worker_membership.id}/",
            {"role": ProjectMembership.Role.PROJECT_MANAGER},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.worker_membership.refresh_from_db()
        self.assertEqual(self.worker_membership.role, ProjectMembership.Role.FOREMAN)

    def test_project_manager_cannot_delete_admin_membership(self):
        admin_membership = ProjectMembership.objects.get(
            user=self.admin_user,
            project=self.project_a,
            role=ProjectMembership.Role.ADMIN,
        )
        self.client.login(username="pm_manager", password="test-pass")
        response = self.client.delete(f"/api/projects/memberships/{admin_membership.id}/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ProjectMembership.objects.filter(id=admin_membership.id).exists())
