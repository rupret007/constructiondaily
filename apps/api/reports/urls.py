from rest_framework.routers import DefaultRouter

from reports.views import (
    DailyReportViewSet,
    DelayEntryViewSet,
    EquipmentEntryViewSet,
    LaborEntryViewSet,
    MaterialEntryViewSet,
    WorkLogEntryViewSet,
)

router = DefaultRouter()
router.register("daily", DailyReportViewSet, basename="daily-reports")
router.register("labor", LaborEntryViewSet, basename="labor-entries")
router.register("equipment", EquipmentEntryViewSet, basename="equipment-entries")
router.register("materials", MaterialEntryViewSet, basename="material-entries")
router.register("work", WorkLogEntryViewSet, basename="worklog-entries")
router.register("delays", DelayEntryViewSet, basename="delay-entries")

urlpatterns = router.urls
