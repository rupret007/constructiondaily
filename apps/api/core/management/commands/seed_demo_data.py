from __future__ import annotations

import secrets

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from core.models import Project, ProjectMembership


class Command(BaseCommand):
    help = "Seed demo users, project, and memberships for pilot validation."

    def handle(self, *args, **options):
        project, _ = Project.objects.get_or_create(
            code="DEMO-001",
            defaults={
                "name": "Demo Construction Project",
                "location": "Test Site",
                "latitude": 37.7749,
                "longitude": -122.4194,
            },
        )

        users = {
            "foreman_demo": ProjectMembership.Role.FOREMAN,
            "super_demo": ProjectMembership.Role.SUPERINTENDENT,
            "pm_demo": ProjectMembership.Role.PROJECT_MANAGER,
            "safety_demo": ProjectMembership.Role.SAFETY,
            "admin_demo": ProjectMembership.Role.ADMIN,
        }

        for username, role in users.items():
            user, created = User.objects.get_or_create(username=username, defaults={"email": f"{username}@example.local"})
            if created:
                generated_password = secrets.token_urlsafe(12)
                user.set_password(generated_password)
                user.save(update_fields=["password"])
                self.stdout.write(self.style.WARNING(f"Temporary password for {username}: {generated_password}"))
            ProjectMembership.objects.get_or_create(user=user, project=project, role=role)
            self.stdout.write(self.style.SUCCESS(f"Prepared user {username} with role {role}."))

        self.stdout.write(self.style.SUCCESS("Demo data seeding complete."))
