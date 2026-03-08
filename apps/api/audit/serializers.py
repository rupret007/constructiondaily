from __future__ import annotations

from django.contrib.auth.models import User
from rest_framework import serializers

from audit.models import AuditEvent


class AuditActorSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name")


class AuditEventSerializer(serializers.ModelSerializer):
    actor = AuditActorSerializer(read_only=True)

    class Meta:
        model = AuditEvent
        fields = (
            "id",
            "created_at",
            "actor",
            "event_type",
            "object_type",
            "object_id",
            "project_id",
            "ip_address",
            "metadata",
        )
