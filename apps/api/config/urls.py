from django.conf import settings
from django.contrib import admin
from django.http import FileResponse
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def serve_spa(request):
    """Serve the React SPA index.html for client-side routing."""
    index_path = settings.BASE_DIR.parent / "web" / "dist" / "index.html"
    if not index_path.exists():
        from django.http import HttpResponse
        return HttpResponse(
            "Frontend not built. Run: cd apps/web && npm run build",
            status=503,
            content_type="text/plain",
        )
    return FileResponse(open(index_path, "rb"), content_type="text/html")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/auth/", include("core.urls")),
    path("api/projects/", include("core.project_urls")),
    path("api/reports/", include("reports.urls")),
    path("api/files/", include("files.urls")),
    path("api/safety/", include("safety.urls")),
    path("api/audit/", include("audit.urls")),
    path("api/preconstruction/", include("preconstruction.urls")),
    # SPA catch-all: serve index.html for all non-API routes (client-side routing)
    re_path(r"^.*$", serve_spa),
]
