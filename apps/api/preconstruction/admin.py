from django.contrib import admin
from .models import (
    PlanSet,
    PlanSheet,
    ProjectDocument,
    ProjectDocumentChunk,
    ProjectTakeoffRule,
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


@admin.register(ProjectDocument)
class ProjectDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "document_type", "project", "plan_set", "parse_status", "created_at")
    list_filter = ("document_type", "parse_status", "project")
    search_fields = ("title", "original_filename", "project__code")


@admin.register(ProjectDocumentChunk)
class ProjectDocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "chunk_index", "page_number", "created_at")
    list_filter = ("document__document_type", "document__project")
    search_fields = ("document__title", "content")


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


@admin.register(ProjectTakeoffRule)
class ProjectTakeoffRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "trigger_category", "trigger_label_pattern")
    list_filter = ("project", "trigger_category")
    search_fields = ("name", "trigger_category")
