from rest_framework.routers import DefaultRouter

from .views import (
    AIAnalysisRunViewSet,
    AISuggestionViewSet,
    AnnotationItemViewSet,
    AnnotationLayerViewSet,
    ExportRecordViewSet,
    PreconstructionCopilotViewSet,
    PlanSetViewSet,
    PlanSheetViewSet,
    RevisionSnapshotViewSet,
    TakeoffItemViewSet,
)

router = DefaultRouter()
router.register("copilot", PreconstructionCopilotViewSet, basename="preconstruction-copilot")
router.register("sets", PlanSetViewSet, basename="plan-set")
router.register("sheets", PlanSheetViewSet, basename="plan-sheet")
router.register("layers", AnnotationLayerViewSet, basename="annotation-layer")
router.register("annotations", AnnotationItemViewSet, basename="annotation-item")
router.register("takeoff", TakeoffItemViewSet, basename="takeoff-item")
router.register("analysis", AIAnalysisRunViewSet, basename="ai-analysis-run")
router.register("suggestions", AISuggestionViewSet, basename="ai-suggestion")
router.register("snapshots", RevisionSnapshotViewSet, basename="revision-snapshot")
router.register("exports", ExportRecordViewSet, basename="export-record")

urlpatterns = router.urls
