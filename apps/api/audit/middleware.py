from __future__ import annotations

from audit.services import set_request_audit_context


class AuditContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_request_audit_context(
            ip_address=_extract_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        return self.get_response(request)


def _extract_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
