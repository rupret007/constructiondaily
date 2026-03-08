from rest_framework.routers import DefaultRouter

from files.views import AttachmentViewSet, UploadIntentViewSet

router = DefaultRouter()
router.register("intents", UploadIntentViewSet, basename="upload-intents")
router.register("attachments", AttachmentViewSet, basename="attachments")

urlpatterns = router.urls
