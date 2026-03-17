from __future__ import annotations

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import serializers

from core.models import Project, ProjectMembership


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(username=attrs["username"], password=attrs["password"])
        if not user:
            raise serializers.ValidationError("Invalid username or password.")
        attrs["user"] = user
        return attrs


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name", "email")


class SessionSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    user = UserSerializer(required=False, allow_null=True)
    csrfToken = serializers.CharField()


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ("id", "name", "code", "location", "latitude", "longitude", "is_active", "created_at", "updated_at")
        read_only_fields = ("created_at", "updated_at")


class ProjectMembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), write_only=True, source="user")

    class Meta:
        model = ProjectMembership
        fields = ("id", "project", "user", "user_id", "role", "is_active", "created_at", "updated_at")
        read_only_fields = ("created_at", "updated_at")

    def validate(self, attrs):
        if self.instance:
            incoming_project = attrs.get("project", self.instance.project)
            incoming_user = attrs.get("user", self.instance.user)
            if incoming_project.id != self.instance.project_id:
                raise serializers.ValidationError("Project cannot be changed after membership creation.")
            if incoming_user.id != self.instance.user_id:
                raise serializers.ValidationError("User cannot be changed after membership creation.")
        return attrs
