from __future__ import annotations

from rest_framework import serializers

from safety.models import SafetyEntry


class SafetyEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = SafetyEntry
        fields = "__all__"
