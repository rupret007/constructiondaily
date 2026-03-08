from __future__ import annotations

from rest_framework import serializers

from files.models import Attachment, UploadIntent


class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = (
            "id",
            "report",
            "original_filename",
            "stored_filename",
            "storage_key",
            "mime_type",
            "file_extension",
            "size_bytes",
            "sha256",
            "scan_status",
            "scan_detail",
            "created_at",
        )
        read_only_fields = (
            "stored_filename",
            "storage_key",
            "sha256",
            "scan_status",
            "scan_detail",
            "created_at",
        )


class UploadIntentSerializer(serializers.ModelSerializer):
    upload_url = serializers.SerializerMethodField()

    class Meta:
        model = UploadIntent
        fields = (
            "id",
            "report",
            "max_size_bytes",
            "expires_at",
            "consumed",
            "upload_url",
        )
        read_only_fields = ("expires_at", "consumed", "upload_url")

    def get_upload_url(self, obj: UploadIntent) -> str:
        return f"/api/files/intents/{obj.id}/upload/"
