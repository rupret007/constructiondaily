# Preconstruction Plan Annotation

The Preconstruction (Plan Annotation and Takeoff) feature lets estimators upload plan sheets, draw annotations, record takeoff quantities, use AI-assisted suggestions, and export data for bids. All actions are auditable and human review is required for AI suggestions.

## Prerequisites

- You must be **logged in** and have access to at least one **project** (same as Daily Reports).
- Use a modern browser (Chrome, Firefox, Edge, Safari) with JavaScript enabled.
- **Plan files**: PDF only. Maximum size follows the API setting (default same as report attachments, e.g. 10 MB). The file must be a valid PDF (correct magic bytes).

## Definitions

- **Plan set** — A named collection of plan sheets for a project (e.g. a bid package or estimate version).
- **Plan sheet** — One uploaded drawing/plan file (one PDF). Shown in the viewer with zoom and pan.
- **Annotation layer** — A logical layer on a sheet that groups annotations (e.g. “Doors”, “Fixtures”). You can show/hide layers.
- **Annotation** — A single markup on the sheet: point, rectangle, polygon, polyline, or text. Stored in normalized coordinates so they stay correct at any zoom.
- **Takeoff item** — A quantity record for estimating: category (doors, windows, concrete, etc.), unit (count, square feet, linear feet, etc.), and quantity. Can be linked to an annotation or entered manually.
- **Revision snapshot** — A saved state of the plan set and takeoff summary at a point in time. Can be locked for defensibility.
- **Export** — A generated file (JSON or CSV) of the takeoff summary (and optionally snapshot) for use in bids or other tools.

## Step-by-step workflows

### 1. Open Preconstruction and select project

- In the app header, click **Preconstruction**.
- Use the project dropdown to select the project you are estimating for. Only projects you have access to appear.

### 2. Create a plan set

- Click **Create plan set**.
- Enter a name (e.g. “Floor 1 – Bid Package A”) and click **Create**.
- The new set appears in the list. Select it to work with its sheets.

### 3. Upload plan sheets (PDFs)

- With a plan set selected, use the **file input** to choose a PDF plan file.
- Optionally enter a **Sheet title** (e.g. “A-101”) before uploading.
- Click **Refresh** after upload to see the new sheet in the list.
- Only PDF files are accepted; size and type are validated by the server.

### 4. Open a sheet in the viewer

- In the sheet list, click **Open** next to a sheet.
- The PDF loads in the viewer with zoom (+ / −) controls. Annotations and layers are shown as overlays.

### 5. Create annotation layers and annotations

- In the viewer, the **Layers** panel lists layers for the sheet. If there are none, adding an annotation will create a default layer.
- Click **Add point** to enter placement mode, then click on the plan to place a point. Click **Add rectangle** to enter placement mode, then click and drag on the plan to draw a rectangle. Use the **Annotations** list to select one; the **Annotation inspector** shows details and actions (Create takeoff from this, Delete).
- Annotations are stored in normalized coordinates (0–1) so they remain correct at any zoom level.

### 6. Create takeoff items

- In the **Takeoff summary** panel, choose **Category** (e.g. Doors, Windows, Plumbing fixtures), **Quantity**, and **Unit** (Count, SF, LF, Each).
- Click **Add takeoff** to create a takeoff item for the current sheet.
- Takeoff items can also be created when you **Accept** an AI suggestion (see below).

### 7. Use AI suggestions (mock in v1)

- In the **AI suggestions** section, enter a prompt (e.g. “highlight all doors”, “find plumbing fixtures”, “mark concrete slab areas”).
- Click **Run analysis**. The system returns placeholder suggestions based on keywords and sheet metadata (no real AI in v1).
- For each suggestion you see **Accept** and **Reject**. **Accept** creates an annotation and a takeoff item from that suggestion; you can adjust category/unit/quantity. **Reject** marks the suggestion as rejected. All decisions are recorded for audit and future learning.

### 8. Create a revision snapshot and lock (optional)

- In **Revision snapshots**, click **Create snapshot**. This saves the current state of the plan set (metadata, sheets, annotation layers and items, takeoff items, and AI suggestion outcomes per sheet) as a reproducible JSON payload stored on the snapshot.
- For a snapshot in **draft** status, click **Lock** to make it immutable. Locked snapshots are suitable for formal records and serve as high-quality labeled data for future learning (see [Learning signals](#learning-signals-traceable-feedback)).

### 9. Export takeoff data

- Click **Export JSON** or **Export CSV** to generate an export of the takeoff summary and plan set state. An **export record** is created for each export (JSON, CSV, or PDF metadata) for audit. The last export payload is shown in the viewer; use the JSON/CSV in your bid tools.
- **PDF metadata** export is a placeholder (no true PDF file yet); it creates an export record and returns a small metadata payload.

## Where to find things

- **Audit history**: All important actions (create plan set, upload sheet, create/update/delete annotation, takeoff, run AI, accept/reject suggestion, create/lock snapshot, export) are recorded as audit events. Use the existing audit API or admin to filter by `event_type` and `object_type` for preconstruction (e.g. `create_plan_set`, `upload_plan_sheet`, `accept_ai_suggestion`).

## Troubleshooting

| Issue | What to check |
|-------|----------------|
| I don’t see **Preconstruction** | You must be logged in and have at least one project. If the tab is missing, ensure the app is up to date. |
| **Upload failed** | Ensure the file is a PDF, under the size limit, and not corrupt. Check the error message shown in the UI. |
| **PDF doesn’t load** in the viewer | Confirm the file is a valid PDF. Very large or password-protected PDFs may not load in the browser viewer. |
| I can’t **edit** or **create** | You need a role that can edit the project (e.g. Foreman, Superintendent, Project Manager, Admin). Locked snapshots cannot be changed. |
| **Run analysis** returns no suggestions | The mock provider uses prompt keywords (e.g. doors, windows, plumbing, concrete). Try phrases that include those words. |

## Frontend implementation summary

- **Routes / entry**: Preconstruction is an app area (state in `App.tsx`: `area === 'preconstruction'`). No URL path change; "Preconstruction" tab in the navbar switches area. Sheet viewer is shown when `preconstructionSheetId` and `preconstructionPlanSetId` are set (after clicking **Open** on a sheet).
- **Components**: `PreconstructionDashboard`, `PlanSetList`, `PlanSheetList`, `SheetViewer`. All under `apps/web/src/preconstruction/`.
- **Fully working**: Project-scoped plan set list; create plan set; upload PDF sheets; open sheet in viewer; PDF render (pdfjs-dist) with zoom and drag-to-pan; layer list with visibility toggle (wired to API); point and rectangle annotation creation; annotation list and inspector (select, view label/notes/source/review_state, delete, "Create takeoff from this"); takeoff summary panel and add takeoff; AI suggestion review panel (prompt, Run analysis, list with label/suggestion_type/rationale/confidence; Accept, Reject, Edit with form for label/category/unit/quantity and "Accept with edits"); decision outcome (accepted/rejected/edited) + decided_at; revision snapshots with Create/Lock and Draft vs Locked labels; Export JSON/CSV and recent exports.
- **Stubbed or minimal**: Polygon/polyline creation (backend and types support; UI only has point + rectangle). Click-on-canvas to place point/rectangle not implemented (fixed positions). Annotation geometry editing (e.g. resize) not in UI. Linking takeoff to annotation is implicit (notes text) until backend supports `linked_takeoff_item`.
- **Known limitations before deeper AI workflow**: Mock AI only (keyword-based). No batch accept/reject. No annotation conflict resolution UI. Revision comparison (diff) not implemented. Export is current state only (snapshot export can be added via API).

## Learning signals (traceable feedback)

The system stores structured feedback for future calibration and training only. There is **no opaque autonomous learning** or active self-training; all signals are human-reviewed and auditable.

- **AISuggestion**: `decision_state` (pending / accepted / rejected / edited), `decided_by`, `decided_at`, `accepted_annotation` (when accepted or edited). Original suggestion: `geometry_json`, `label`, `rationale`, `confidence`, `suggestion_type`.
- **AnnotationItem** (created from a suggestion): Final `geometry_json`, `label`, `source`, `review_state` (accepted / edited).
- **TakeoffItem** (created from a suggestion): Final `category`, `unit`, `quantity`, `source`, `review_state`.
- **AIAnalysisRun**: `request_payload_json` (user_prompt, plan_sheet_id), `response_payload_json` (raw suggestions or error).
- **Audit events**: `trigger_ai_analysis`, `accept_ai_suggestion`, `reject_ai_suggestion`, `edit_ai_suggestion` (with overrides metadata).

Project and sheet context (plan_set, plan_sheet, project_id) are stored on all entities for organization-specific recommendation quality later.

### Where learning signals live in the data model

| Signal | Model | Fields | Snapshot payload |
|--------|--------|--------|-------------------|
| AI suggestion outcome (accepted/rejected/edited) | `AISuggestion` | `decision_state`, `decided_by`, `decided_at`, `accepted_annotation_id` | `sheets[].ai_suggestion_outcomes[]` (id, decision_state, label, geometry_json, accepted_annotation_id, decided_at) |
| Original suggestion (for comparison) | `AISuggestion` | `geometry_json`, `label`, `rationale`, `confidence`, `suggestion_type` | same |
| Final annotation after user decision | `AnnotationItem` | `geometry_json`, `label`, `source`, `review_state` | `sheets[].layers[].items[]` (includes source, review_state) |
| Final takeoff after review | `TakeoffItem` | `category`, `unit`, `quantity`, `source`, `review_state` | `sheets[].takeoff_items[]`, `plan_set_level_takeoff[]` |
| Locked/finalized revision | `RevisionSnapshot` | `status=locked`, `snapshot_payload_json` | full payload frozen at lock time |

Locked revision snapshots capture the above in `snapshot_payload_json`, so they are the single place to query for high-quality labeled data (human decisions + final geometry and takeoff).

## Revision snapshots and export records

- **Snapshot payload** (stored in `RevisionSnapshot.snapshot_payload_json` and built by `build_snapshot_payload`) includes: plan set id/name/status, `captured_at`, per-sheet id/title/sheet_number, layers (id, name, items with id/type/label/geometry_json/review_state/source), takeoff items (id, category, unit, quantity, source, review_state), and **ai_suggestion_outcomes** per sheet (id, decision_state, label, suggestion_type, geometry_json, rationale, confidence, accepted_annotation_id, decided_at). Plan-set-level takeoff is also included.
- **Export records** (`ExportRecord`): every export (JSON, CSV, or PDF metadata) creates a record with project, plan_set, optional revision_snapshot, export_type, status, created_by. JSON and CSV responses include the payload; PDF metadata returns a placeholder payload and no file.

## Plugging in a real provider (OCR, CV, CAD, multimodal)

- **Interface**: Implement `BaseAnalysisProvider` in `apps/api/preconstruction/providers/base.py`. The only method is `run_analysis(plan_sheet, user_prompt, **kwargs)` returning a list of dicts with keys: `suggestion_type`, `geometry_json`, `label`, `rationale`, `confidence` (geometry in normalized 0–1 coordinates).
- **Integration**: Add a new class (e.g. `OCRPlanProvider`, `VisionPlanProvider`) in `providers/`. It receives the same `plan_sheet` and `user_prompt`; use the plan sheet’s file URL or stored bytes to call your OCR, computer vision, CAD parser, or multimodal API. Map the provider’s output to the same dict shape. Register the class in `providers/registry.py` under a name (e.g. `"ocr"`, `"vision"`). Trigger analysis via the existing `POST /api/preconstruction/analysis/` endpoint (optionally pass `provider_name` in the body or derive from settings). No change to `run_plan_analysis` logic beyond calling `get_provider(provider_name).run_analysis(...)`.
- **Data flow**: Request and raw response are already stored on `AIAnalysisRun`. Human decisions (accept / reject / edit) are stored on `AISuggestion` and the created `AnnotationItem` / `TakeoffItem`. A real provider plugs in without schema changes.

## API base path

Preconstruction endpoints are under: `/api/preconstruction/`  
- Sets: `GET/POST /api/preconstruction/sets/`  
- Sheets: `GET/POST /api/preconstruction/sheets/`, `GET /api/preconstruction/sheets/:id/file/`  
- Layers, annotations, takeoff, analysis, suggestions, snapshots, exports: see API docs at `/api/docs/`.

---

## Architecture summary and reference

### 1. Concise architecture summary

- **Backend**: Django app `preconstruction` with project-scoped models (PlanSet, PlanSheet, AnnotationLayer, AnnotationItem, TakeoffItem, AIAnalysisRun, AISuggestion, RevisionSnapshot, ExportRecord). Plan PDFs stored under media; analysis provided by a pluggable provider (mock in v1). All mutations are audited; request/response and human decisions are stored for traceable feedback. Revision snapshots capture full state (including AI outcomes) and can be locked; exports produce JSON/CSV (and a PDF metadata placeholder) and create ExportRecords.
- **Frontend**: React area (no dedicated URL path) with Preconstruction tab; dashboard (project, plan set list, create set, sheet list, upload); sheet viewer (PDF via pdfjs-dist, zoom/pan, layers, annotations, takeoff, AI suggestion review with Accept/Reject/Edit, snapshots, export). API client and typed models in `services/preconstruction` and `types/api`.

### 2. Backend endpoints added (all under `/api/preconstruction/`)

| Method | Path | Description |
|--------|------|-------------|
| GET, POST | `/sets/` | List/create plan sets (filter by project) |
| GET, PATCH | `/sets/:id/` | Retrieve/update plan set |
| GET, POST | `/sheets/` | List/create plan sheets |
| GET, PATCH | `/sheets/:id/` | Retrieve/update sheet |
| GET | `/sheets/:id/file/` | Serve plan PDF file |
| GET, POST | `/layers/` | List/create annotation layers |
| GET, PATCH | `/layers/:id/` | Retrieve/update layer |
| GET, POST | `/annotations/` | List/create annotations |
| GET, PATCH, DELETE | `/annotations/:id/` | Retrieve/update/delete annotation |
| GET, POST | `/takeoff/` | List/create takeoff items |
| GET, PATCH, DELETE | `/takeoff/:id/` | Retrieve/update/delete takeoff |
| POST | `/analysis/` | Trigger AI analysis (body: plan_sheet, user_prompt) |
| GET | `/suggestions/` | List suggestions (filter by plan_sheet, analysis_run, decision_state) |
| POST | `/suggestions/:id/accept/` | Accept suggestion (optional: layer_id, geometry_json, label, category, unit, quantity) |
| POST | `/suggestions/:id/reject/` | Reject suggestion |
| GET, POST | `/snapshots/` | List/create revision snapshots |
| POST | `/snapshots/:id/lock/` | Lock snapshot |
| GET, POST | `/exports/` | List/create export records (body: plan_set, export_type, optional revision_snapshot) |

### 3. Frontend routes and components

- **Routes**: No separate URL routes; app state in `App.tsx`: `area === 'preconstruction'` and, when a sheet is open, `preconstructionSheetId` and `preconstructionPlanSetId`. Navbar tab **Preconstruction** switches area.
- **Components** (under `apps/web/src/preconstruction/`): `PreconstructionDashboard` (project dropdown, create set, plan set list, sheet list, upload, Open); `PlanSetList`; `PlanSheetList`; `SheetViewer` (PDF viewer, layers, annotations + inspector, takeoff, AI suggestion review, snapshots, export).

### 4. Known limitations

- Mock AI only (keyword-based); no real OCR/CV/CAD.
- No batch accept/reject for suggestions; no conflict resolution UI.
- Point/rectangle annotations at fixed positions (no click-on-canvas place).
- No annotation geometry editing (resize/move) in UI.
- Revision comparison (diff between snapshots) not implemented.
- Export is current plan set state (or optional snapshot); PDF export is metadata placeholder only.
- Plan set/sheet list is not paginated.

### 5. Recommended next steps for production hardening

- Add pagination and filtering for sets, sheets, and suggestions.
- Implement real PDF export (e.g. reportlab or weasyprint) and optional storage of export files (e.g. S3) with `storage_key` on ExportRecord.
- Rate limiting and cost controls for analysis endpoint when a paid provider is used.
- Stronger validation and size limits for `geometry_json` and snapshot payload size.
- E2E tests (e.g. Playwright) for create set → upload → open → annotate → snapshot → export.

### 6. Recommended next steps for future learning-based AI improvements

- Use **locked revision snapshots** and **AISuggestion** + **AnnotationItem** + **TakeoffItem** as labeled datasets: export payloads or query by `decision_state` and `review_state` for training or calibration.
- Add an offline pipeline (no autonomous training in-app) that reads audit events and snapshot payloads to produce training batches (input: plan sheet + prompt; label: accepted/rejected/edited + final geometry/takeoff).
- Consider storing anonymized or aggregated statistics (e.g. accept rate by suggestion_type, category) for model monitoring.
- When integrating a real provider, log provider-specific metadata in `AIAnalysisRun.response_payload_json` for debugging and future A/B evaluation.

---

## Developer notes (conventions and consistency)

- **Auth and scoping**: All preconstruction ViewSets use `IsAuthenticated` and restrict querysets with `_project_ids_for_user(request.user)`. Create/update/delete enforce `user_has_project_role(..., PROJECT_WRITE_ROLES)` (Foreman, Superintendent, Project Manager, Admin). Snapshot lock requires Project Manager or Admin.
- **Audit events**: Preconstruction uses underscore naming (e.g. `create_plan_set`, `upload_plan_sheet`, `accept_ai_suggestion`). Other apps in this repo use dot naming (e.g. `report.created`). When querying audit logs, filter by `object_type` and `event_type`; see list in [§ Architecture summary and reference](#2-backend-endpoints-added-all-under-apipreconstruction).
- **API and frontend types**: API returns snake_case (DRF default). Frontend types in `apps/web/src/types/api.ts` use snake_case to match (e.g. `plan_sheet`, `geometry_json`, `decision_state`). Keep types in sync when adding serializer fields.
- **Learning signal capture**: Stored explicitly on `AISuggestion` (decision_state, decided_by, decided_at, accepted_annotation), `AnnotationItem` (source, review_state, geometry_json), `TakeoffItem` (source, review_state, category, unit, quantity), and in `RevisionSnapshot.snapshot_payload_json` (including `ai_suggestion_outcomes` per sheet). No automatic training runs; data is for offline pipelines only.
- **Validations**: Plan uploads are validated (PDF extension, MIME, size, magic bytes) in `validators.validate_plan_upload`. The accept-suggestion endpoint returns 400 for invalid `layer_id` (layer not found or not on this sheet) or invalid `quantity` (non-numeric or negative). `geometry_json` and snapshot payloads are not schema-validated beyond JSONField; consider adding serializer or model validators for geometry shape and payload size in production.

---

## Final reference

### File-by-file summary

| File | Purpose |
|------|--------|
| `apps/api/preconstruction/models.py` | PlanSet, PlanSheet, AnnotationLayer, AnnotationItem, TakeoffItem, AIAnalysisRun, AISuggestion, RevisionSnapshot, ExportRecord |
| `apps/api/preconstruction/serializers.py` | DRF serializers for all models; PreconstructionUserSlimSerializer |
| `apps/api/preconstruction/views.py` | ViewSets for sets, sheets, layers, annotations, takeoff, analysis, suggestions, snapshots, exports; project scoping and audit in perform_* |
| `apps/api/preconstruction/urls.py` | Router registering all ViewSets under `api/preconstruction/` |
| `apps/api/preconstruction/services.py` | accept_suggestion, reject_suggestion, run_plan_analysis, build_snapshot_payload, create_export, create_export_record; _record() for audit |
| `apps/api/preconstruction/storage.py` | store_plan_file, get_plan_file_path (media/plans/...) |
| `apps/api/preconstruction/validators.py` | validate_plan_upload (PDF extension, MIME, size, magic bytes) |
| `apps/api/preconstruction/providers/base.py` | BaseAnalysisProvider abstract interface |
| `apps/api/preconstruction/providers/mock.py` | MockAnalysisProvider (deterministic, keyword-based) |
| `apps/api/preconstruction/providers/registry.py` | get_provider(name) for pluggable backends |
| `apps/api/preconstruction/admin.py` | Django admin for all models |
| `apps/web/src/preconstruction/PreconstructionDashboard.tsx` | Project dropdown, create set, PlanSetList, PlanSheetList |
| `apps/web/src/preconstruction/PlanSetList.tsx` | List plan sets, select one |
| `apps/web/src/preconstruction/PlanSheetList.tsx` | List sheets, upload PDF, Open → viewer |
| `apps/web/src/preconstruction/SheetViewer.tsx` | PDF (pdfjs), zoom/pan, layers, annotations, inspector, takeoff, AI review, snapshots, export |
| `apps/web/src/services/preconstruction.ts` | API client for all preconstruction endpoints |
| `apps/web/src/types/api.ts` | PlanSet, PlanSheet, AnnotationItem, TakeoffItem, AISuggestion, etc. (snake_case to match API) |
| `docs/preconstruction.md` | User workflows, learning signals, architecture, developer notes, punch list |

### Final list of backend routes and endpoints

Base path: `/api/preconstruction/`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/sets/` | List plan sets (filter: project, status) |
| POST | `/sets/` | Create plan set |
| GET | `/sets/:id/` | Retrieve plan set |
| PATCH | `/sets/:id/` | Update plan set |
| DELETE | `/sets/:id/` | Delete plan set |
| GET | `/sheets/` | List plan sheets (filter: project, plan_set, parse_status) |
| POST | `/sheets/` | Upload plan sheet (multipart: plan_set, file, optional title, sheet_number, discipline, sheet_index) |
| GET | `/sheets/:id/` | Retrieve plan sheet |
| PATCH | `/sheets/:id/` | Update plan sheet |
| GET | `/sheets/:id/file/` | Serve plan PDF file |
| GET | `/layers/` | List annotation layers (filter: project, plan_set, plan_sheet) |
| POST | `/layers/` | Create annotation layer |
| GET | `/layers/:id/` | Retrieve annotation layer |
| PATCH | `/layers/:id/` | Update annotation layer |
| DELETE | `/layers/:id/` | Delete annotation layer |
| GET | `/annotations/` | List annotations (filter: project, plan_sheet, layer, source, review_state) |
| POST | `/annotations/` | Create annotation |
| GET | `/annotations/:id/` | Retrieve annotation |
| PATCH | `/annotations/:id/` | Update annotation |
| DELETE | `/annotations/:id/` | Delete annotation |
| GET | `/takeoff/` | List takeoff items (filter: project, plan_set, plan_sheet, category, source) |
| POST | `/takeoff/` | Create takeoff item |
| GET | `/takeoff/:id/` | Retrieve takeoff item |
| PATCH | `/takeoff/:id/` | Update takeoff item |
| DELETE | `/takeoff/:id/` | Delete takeoff item |
| GET | `/analysis/` | List AI analysis runs (filter: project, plan_set, plan_sheet, status) |
| POST | `/analysis/` | Trigger analysis (body: plan_sheet, user_prompt) |
| GET | `/suggestions/` | List suggestions (filter: project, plan_sheet, analysis_run, decision_state) |
| POST | `/suggestions/:id/accept/` | Accept suggestion (optional: layer_id, geometry_json, label, category, unit, quantity) |
| POST | `/suggestions/:id/reject/` | Reject suggestion |
| GET | `/snapshots/` | List revision snapshots (filter: project, plan_set, status) |
| POST | `/snapshots/` | Create revision snapshot (body: project, plan_set, name) |
| GET | `/snapshots/:id/` | Retrieve revision snapshot |
| POST | `/snapshots/:id/lock/` | Lock snapshot |
| GET | `/exports/` | List export records (filter: project, plan_set, export_type, status) |
| POST | `/exports/` | Create export (body: plan_set, export_type, optional revision_snapshot); returns record + payload |

### Final list of data models

| Model | Key fields | Purpose |
|-------|------------|--------|
| PlanSet | project, name, description, status, version_label | Named collection of sheets |
| PlanSheet | project, plan_set, title, sheet_number, discipline, storage_key, page_count, sheet_index, width, height, parse_status | One PDF plan file |
| AnnotationLayer | project, plan_set, plan_sheet, name, color, category, is_visible, is_locked | Logical layer for annotations |
| AnnotationItem | project, plan_sheet, layer, annotation_type, geometry_json, label, notes, source, confidence, review_state, linked_takeoff_item | Single annotation (point/rect/polygon/etc.) |
| TakeoffItem | project, plan_set, plan_sheet, category, subcategory, unit, quantity, source, review_state | Quantity takeoff line |
| AIAnalysisRun | project, plan_set, plan_sheet, provider_name, user_prompt, status, request_payload_json, response_payload_json | One AI run |
| AISuggestion | analysis_run, plan_sheet, suggestion_type, geometry_json, label, rationale, confidence, accepted_annotation, decision_state, decided_by, decided_at | One suggestion; learning signals |
| RevisionSnapshot | project, plan_set, name, status, snapshot_payload_json | Saved state; locked = immutable |
| ExportRecord | project, plan_set, revision_snapshot, export_type, status, storage_key, metadata_json | Audit record for each export |

### Punch list before production use

- [ ] **Audit event naming**: Consider aligning preconstruction event types to dot convention (e.g. `preconstruction.plan_set.created`) for consistency with reports/files; update tests and any consumers.
- [ ] **Geometry validation**: Add serializer or model validator for `geometry_json` (e.g. require `type` in {point, rectangle, polygon, polyline}, normalized 0–1 bounds) to avoid invalid data.
- [ ] **Snapshot payload size**: Consider limiting or chunking `snapshot_payload_json` size; document max practical size for DB/store.
- [ ] **Pagination**: Add pagination for list endpoints (sets, sheets, suggestions, snapshots, exports) for large projects.
- [ ] **Rate limiting**: Apply rate limiting to `POST /analysis/` (and future paid provider) to avoid abuse.
- [ ] **Export file storage**: Implement optional storage of export files (e.g. S3) and set `storage_key` on ExportRecord; add download URL or redirect.
- [ ] **PDF export**: Replace PDF metadata placeholder with real PDF generation (e.g. reportlab) when required.
- [ ] **E2E tests**: Add end-to-end tests (e.g. Playwright) for critical path: create set → upload sheet → open viewer → add annotation → run AI → accept suggestion → create snapshot → lock → export.
- [ ] **Delete plan set/sheet**: Confirm cascade behavior and whether soft-delete or audit-only delete is desired for plan sets and sheets.
- [ ] **Frontend error handling**: Standardize API error display and retry/refresh for sheet viewer and suggestion actions.
