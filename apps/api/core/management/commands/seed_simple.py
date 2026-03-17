"""Seed a single demo user and project for quick local login. Use only for local/dev."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from core.models import Project, ProjectMembership


class Command(BaseCommand):
    help = "Seed one user (admin/admin) and one project for quick local sign-in. Local/dev only."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin", help="Login username")
        parser.add_argument("--password", default="admin", help="Login password")

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]

        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": f"{username}@local.dev"},
        )
        user.set_password(password)
        user.save(update_fields=["password"])

        project, _ = Project.objects.get_or_create(
            code="DEMO",
            defaults={
                "name": "Demo Project",
                "location": "Local",
            },
        )
        ProjectMembership.objects.get_or_create(
            user=user,
            project=project,
            defaults={"role": ProjectMembership.Role.PROJECT_MANAGER, "is_active": True},
        )

        self.stdout.write(
            self.style.SUCCESS(f"Done. Sign in at http://localhost:8000 as {username} / {password}")
        )
