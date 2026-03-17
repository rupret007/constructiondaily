# Generated migration for ProjectTakeoffRule

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
        ("preconstruction", "0004_projectdocument_projectdocumentchunk"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectTakeoffRule",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(help_text="Short label for this rule (e.g. Door set).", max_length=128)),
                (
                    "trigger_category",
                    models.CharField(
                        help_text="TakeoffItem category that triggers this rule (e.g. doors).",
                        max_length=64,
                    ),
                ),
                (
                    "trigger_label_pattern",
                    models.CharField(
                        blank=True,
                        help_text="Optional regex on annotation/suggestion label; blank means any label.",
                        max_length=255,
                    ),
                ),
                (
                    "expansion_components",
                    models.JSONField(
                        default=list,
                        help_text='List of {"category", "unit", "quantity_mode": "same"|"one"} to add per primary item.',
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="takeoff_rules",
                        to="core.project",
                    ),
                ),
            ],
            options={
                "ordering": ("trigger_category", "name"),
                "unique_together": {("project", "trigger_category", "name")},
            },
        ),
    ]
