from rest_framework.routers import DefaultRouter

from core.views import ProjectMembershipViewSet, ProjectViewSet, UserDirectoryViewSet

router = DefaultRouter()
router.register("memberships", ProjectMembershipViewSet, basename="project-memberships")
router.register("users", UserDirectoryViewSet, basename="project-users")
router.register("", ProjectViewSet, basename="projects")

urlpatterns = router.urls
