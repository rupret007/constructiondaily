from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from core.models import Project, ProjectMembership


class Command(BaseCommand):
    help = "Seed deterministic project and user data for browser smoke tests."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="e2e_pm")
        parser.add_argument("--password", default="e2e-pass-123")
        parser.add_argument("--project-code", default="E2E-001")
        parser.add_argument("--project-name", default="E2E Smoke Project")
        parser.add_argument("--location", default="Automation Yard")

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        project_code = options["project_code"]

        user, _ = User.objects.get_or_create(
            username=username,
            defaults={"email": f"{username}@example.local"},
        )
        user.set_password(password)
        user.save(update_fields=["password"])

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

        membership, _ = ProjectMembership.objects.get_or_create(
            user=user,
            project=project,
            role=ProjectMembership.Role.PROJECT_MANAGER,
            defaults={"is_active": True},
        )
        if not membership.is_active:
            membership.is_active = True
            membership.save(update_fields=["is_active", "updated_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Prepared E2E user {username} on project {project.code} with role {membership.role}."
            )
        )
