from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from core.models import Project, ProjectMembership


class Command(BaseCommand):
    help = "Add an existing user to the demo project with Project Manager role (Preconstruction write access)."

    def add_arguments(self, parser):
        parser.add_argument(
            "username",
            nargs="?",
            type=str,
            help="Username to add (e.g. from createsuperuser). If omitted, lists demo project and members.",
        )
        parser.add_argument(
            "--role",
            type=str,
            default=ProjectMembership.Role.PROJECT_MANAGER,
            choices=[r for r, _ in ProjectMembership.Role.choices],
            help="Role to assign (default: project_manager).",
        )

    def handle(self, *args, **options):
        project = Project.objects.filter(code="DEMO-001").first()
        if not project:
            raise CommandError("Demo project not found. Run 'python manage.py seed_demo_data' first.")

        username = options.get("username")
        role = options["role"]

        if not username:
            self.stdout.write(
                self.style.WARNING(
                    f"Usage: python manage.py add_user_to_demo <username> [--role project_manager]"
                )
            )
            members = ProjectMembership.objects.filter(project=project, is_active=True).select_related(
                "user"
            )
            for m in members:
                self.stdout.write(f"  {m.user.username} ({m.role})")
            return

        try:
            user = User.objects.get_by_natural_key(username)
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' does not exist. Create with createsuperuser first.")

        _, created = ProjectMembership.objects.get_or_create(
            user=user, project=project, role=role, defaults={"is_active": True}
        )
        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Added {username} to {project.code} ({project.name}) as {role}.")
            )
        else:
            self.stdout.write(
                self.style.NOTICE(f"{username} already has a membership on {project.code}; no change.")
            )
