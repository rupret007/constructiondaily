from django.contrib import admin
from .models import (
    PlanSet,
    PlanSheet,
    AnnotationLayer,
    AnnotationItem,
    TakeoffItem,
    AIAnalysisRun,
    AISuggestion,
    RevisionSnapshot,
    ExportRecord,
)


@admin.register(PlanSet)
class PlanSetAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "status", "created_at")
    list_filter = ("status", "project")
    search_fields = ("name", "project__code")


@admin.register(PlanSheet)
class PlanSheetAdmin(admin.ModelAdmin):
    list_display = ("title", "sheet_number", "plan_set", "parse_status", "created_at")
    list_filter = ("parse_status", "plan_set__project")


@admin.register(AnnotationLayer)
class AnnotationLayerAdmin(admin.ModelAdmin):
    list_display = ("name", "plan_sheet", "is_visible", "is_locked")
    list_filter = ("plan_sheet__plan_set",)


@admin.register(AnnotationItem)
class AnnotationItemAdmin(admin.ModelAdmin):
    list_display = ("annotation_type", "label", "layer", "source", "review_state")
    list_filter = ("source", "review_state", "annotation_type")


@admin.register(TakeoffItem)
class TakeoffItemAdmin(admin.ModelAdmin):
    list_display = ("category", "quantity", "unit", "plan_set", "source")
    list_filter = ("category", "source", "plan_set")


@admin.register(AIAnalysisRun)
class AIAnalysisRunAdmin(admin.ModelAdmin):
    list_display = ("plan_sheet", "provider_name", "status", "created_at")
    list_filter = ("status", "provider_name")


@admin.register(AISuggestion)
class AISuggestionAdmin(admin.ModelAdmin):
    list_display = ("label", "analysis_run", "decision_state", "confidence")
    list_filter = ("decision_state",)


@admin.register(RevisionSnapshot)
class RevisionSnapshotAdmin(admin.ModelAdmin):
    list_display = ("name", "plan_set", "status", "created_at")
    list_filter = ("status",)


@admin.register(ExportRecord)
class ExportRecordAdmin(admin.ModelAdmin):
    list_display = ("plan_set", "export_type", "status", "created_at")
    list_filter = ("export_type", "status")
