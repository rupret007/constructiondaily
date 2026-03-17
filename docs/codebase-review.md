# Codebase Review: Construction Daily

This document summarizes a deeper review of backend, frontend, config, and tests beyond the Podman/deploy work. It identifies issues and recommendations.

---

## 1. Scope of review

| Area | What was reviewed |
|------|-------------------|
| **Backend** | Reports, Files, Audit, Core, Preconstruction views/serializers/services; permissions; transactions; N+1 risk |
| **Frontend** | API client, auth flow, error handling, 401/session expiry |
| **Config** | settings.py (DEBUG, SECRET_KEY, ALLOWED_HOSTS, security) |
| **Tests** | Backend and frontend test coverage and gaps |

---

## 2. Confirmed correct behavior

- **Audit:** `AuditEventViewSet` restricts listing to superuser or users with ADMIN/PROJECT_MANAGER on the project; no unbounded exposure.
- **Files scan-result:** `AttachmentViewSet.scan_result` uses `get_object()` (project-scoped) plus explicit ADMIN/SAFETY role check; authorization is correct.
- **User directory:** `UserDirectoryViewSet.get_queryset()` limits users to those sharing a project with the current user; search is scoped the same way.
- **File upload validation:** Extension, MIME, size, and magic-byte checks in `files/validators.py`; limits from `settings.REPORT_ATTACHMENT_MAX_BYTES` and allowed extension/MIME sets.
- **Preconstruction services:** Critical paths use `transaction.atomic()` and `select_for_update()` (e.g. accept suggestion, revision snapshot, run_plan_analysis).
- **No dangerous frontend patterns:** No `innerHTML`, `dangerouslySetInnerHTML`, `eval`, or `document.write` found.

---

## 3. Issues and recommendations

### 3.1 Reports: N+1 on report detail (backend)

**Location:** [apps/api/reports/views.py](apps/api/reports/views.py), [apps/api/reports/serializers.py](apps/api/reports/serializers.py)

**Issue:** `DailyReportViewSet` uses a single queryset with only `select_related("project", "prepared_by", "locked_by")`. For `action == "retrieve"`, `DailyReportDetailSerializer` is used; it accesses `laborentry_set`, `equipmententry_set`, `materialentry_set`, `worklogentry_set`, `delayentry_set`, `safety_entries`, `attachments`, `approval_actions`, and `snapshots` (and `ApprovalAction.actor`). Each causes extra queries per report retrieve.

**Recommendation:** In `DailyReportViewSet.get_queryset()`, when `self.action == "retrieve"`, add:

```python
prefetch_related(
    "laborentry_set", "equipmententry_set", "materialentry_set",
    "worklogentry_set", "delayentry_set", "safety_entries",
    "attachments", "approval_actions", "snapshots",
)
```

and prefetch `approval_actions__actor` (or use `Prefer('approval_actions', queryset=ApprovalAction.objects.select_related('actor'))`). Alternatively, override `retrieve()` and use an optimized queryset only for that action. Add a test that asserts query count on report detail (e.g. with `assertNumQueries`) to prevent regression.

---

### 3.2 Frontend: 401 / session expiry not clearing app state

**Location:** [apps/web/src/App.tsx](apps/web/src/App.tsx), [apps/web/src/services/api.ts](apps/web/src/services/api.ts)

**Issue:** When the session expires, any API call (e.g. `fetchReports`, `fetchReport`, `createReport`) returns 401 and throws `ApiRequestError`. The error is shown via `setError(getErrorMessage(...))`, but `user` and app state are not cleared. The user remains on the main app UI with an error banner instead of being shown the login form.

**Recommendation:** Either:

- **Option A:** In `apiRequest`, on `response.status === 401`, after throwing, the caller could be expected to handle 401. Add a small helper that catches 401 and calls a callback (e.g. `onUnauthorized` from a React context), and use it in `App.tsx` for key flows so that on 401 the app calls `resetAppState()` and shows the login form.
- **Option B:** In `App.tsx`, in the initial `loadSessionAndProjects` and in the catch blocks for `loadReports`, `refreshSelectedReport`, and other critical API calls, if the error is `ApiRequestError` with `status === 401`, call `resetAppState()` before or instead of `setError(...)`.

Option B is minimal and keeps 401 handling in one place (App) without changing the API layer.

---

### 3.3 SECRET_KEY when unset (production)

**Location:** [apps/api/config/settings.py](apps/api/config/settings.py)

**Issue:** `SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or secrets.token_urlsafe(64)` means that if `DJANGO_SECRET_KEY` is not set, each process gets a new random key. Sessions and signed data would be invalidated on restart; password reset tokens and similar would break.

**Recommendation:** Document clearly in [docs/deployment.md](docs/deployment.md) and [docs/deployment-podman.md](docs/deployment-podman.md) that `DJANGO_SECRET_KEY` must be set in production and that omitting it causes session/signing breakage. Optionally, in production (e.g. when `DEBUG` is False), raise an error at startup if `DJANGO_SECRET_KEY` is missing so misconfiguration fails fast.

---

### 3.4 DEBUG defaults to True

**Location:** [apps/api/config/settings.py](apps/api/config/settings.py)

**Issue:** `DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"` defaults to `True`. If an operator deploys without setting `DJANGO_DEBUG=false`, the app runs in debug mode (tracebacks, etc.).

**Recommendation:** Already covered in deployment docs; ensure `.env.example` and both deployment guides state that production must set `DJANGO_DEBUG=false`. No code change required if docs are clear.

---

## 4. Test coverage gaps

- **Report detail N+1:** No test that asserts query count when retrieving a report with entries/attachments/approvals/snapshots; add one after fixing 3.1.
- **Audit:** No dedicated tests for `AuditEventViewSet` (listing, filtering, project scoping for non-superuser).
- **Files:** No explicit tests for `scan_result` authorization (only ADMIN/SAFETY can post) or for upload-intent consume under concurrency.
- **Safety:** Safety entry lifecycle is implied via report tests; consider a short test that creates/updates safety entries and checks permissions.
- **Frontend:** No test that, on 401 from an API call, the app clears user state and shows login (or that 401 is handled in a defined way).
- **Preconstruction:** Export and copilot failure paths (e.g. provider timeout, invalid sheet) are not explicitly tested.

Adding tests for the N+1 fix, audit listing, and 401 handling would have the highest impact.

---

## 5. Optional follow-ups

- **DB indexes:** If report list is filtered often by `(project_id, report_date)` or `status`, consider adding `Index` on `DailyReport`; same for other high-traffic filters. Profile first.
- **Preconstruction:** Review long `services.py` for consistent error handling (e.g. AI provider timeouts) and ensure all external calls are wrapped with timeouts and clear error messages.
- **CORS:** If the frontend is ever served from a different origin than the API, add `django-cors-headers` and configure `CORS_ALLOWED_ORIGINS`; currently no CORS middleware is present (same-origin or proxy assumed).
- **Platform (containers):** Image is built for `linux/amd64`; document or add multi-platform if ARM (e.g. Raspberry Pi) is needed.

---

## 6. Summary

| Priority | Item | Action |
|----------|------|--------|
| High | Report detail N+1 | Add prefetch_related for retrieve; add query-count test |
| High | 401 not clearing app state | On 401 in key flows, call resetAppState() so login form shows |
| Medium | SECRET_KEY unset in prod | Document; optionally fail startup when DEBUG is False and SECRET_KEY unset |
| Medium | Test gaps | Add tests for audit, scan_result auth, 401 handling |
| Low | DEBUG default | Keep; ensure docs state production must set DJANGO_DEBUG=false |
| Low | Indexes / CORS / platform | Optional; profile and document as needed |

This review did not change any code; it only documents findings and recommendations.
