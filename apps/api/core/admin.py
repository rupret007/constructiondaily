from django.contrib import admin

from core.models import Project, ProjectMembership


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "location", "is_active")
    search_fields = ("code", "name", "location")


@admin.register(ProjectMembership)
class ProjectMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "project", "role", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("user__username", "project__code")
