from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from core.models import Project, ProjectMembership


class Command(BaseCommand):
    help = "Seed deterministic project and user data for browser smoke tests."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="e2e-pass-123")
        parser.add_argument("--project-code", default="E2E-001")
        parser.add_argument("--project-name", default="E2E Smoke Project")
        parser.add_argument("--location", default="Automation Yard")

    def handle(self, *args, **options):
        password = options["password"]
        project_code = options["project_code"]

        users_by_role = {
            "e2e_super": ProjectMembership.Role.SUPERINTENDENT,
            "e2e_pm": ProjectMembership.Role.PROJECT_MANAGER,
            "e2e_admin": ProjectMembership.Role.ADMIN,
        }

        created_users = []
        for username in users_by_role:
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={"email": f"{username}@example.local"},
            )
            user.set_password(password)
            user.save(update_fields=["password"])
            created_users.append(user)

        project, created = Project.objects.get_or_create(
            code=project_code,
            defaults={
                "name": options["project_name"],
                "location": options["location"],
            },
        )
        if not created:
            project.name = options["project_name"]
            project.location = options["location"]
            project.is_active = True
            project.save(update_fields=["name", "location", "is_active", "updated_at"])

        # Reset project-scoped workflow data so browser tests run against a clean, repeatable fixture.
        project.plan_sets.all().delete()
        project.project_documents.all().delete()
        project.daily_reports.all().delete()

        prepared_memberships = []
        for user in created_users:
            role = users_by_role[user.username]
            membership, _ = ProjectMembership.objects.get_or_create(
                user=user,
                project=project,
                role=role,
                defaults={"is_active": True},
            )
            if not membership.is_active:
                membership.is_active = True
                membership.save(update_fields=["is_active", "updated_at"])
            prepared_memberships.append((user.username, membership.role))

        self.stdout.write(
            self.style.SUCCESS(
                "Prepared E2E project "
                f"{project.code} with users: "
                + ", ".join(f"{username} ({role})" for username, role in prepared_memberships)
            )
        )
