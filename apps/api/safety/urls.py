from rest_framework.routers import DefaultRouter

from safety.views import SafetyEntryViewSet

router = DefaultRouter()
router.register("", SafetyEntryViewSet, basename="safety-entries")

urlpatterns = router.urls
