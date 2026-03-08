from rest_framework.routers import DefaultRouter

from core.views import ProjectMembershipViewSet, ProjectViewSet, UserDirectoryViewSet

router = DefaultRouter()
router.register("", ProjectViewSet, basename="projects")
router.register("memberships", ProjectMembershipViewSet, basename="project-memberships")
router.register("users", UserDirectoryViewSet, basename="project-users")

urlpatterns = router.urls
