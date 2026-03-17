# Preconstruction Plan Annotation

Preconstruction supports plan-set management, plan sheet upload (PDF, DXF, and DWG), project document ingestion (PDF, TXT, MD), on-sheet annotation, takeoff tracking, plan-set estimating dashboards, AI suggestion review (configurable provider), grounded copilot workflows with browser voice support, revision snapshots, and exports.

## Access and roles

- Authentication is required.
- Read access: any user with active membership on the project.
- Write access for most actions: Foreman, Superintendent, Project Manager, Admin.
- Snapshot lock: Project Manager or Admin.

## Supported workflow

1. Open **Preconstruction** and choose a project.
2. Create a plan set.
3. Upload one or more plan files (`.pdf`, `.dxf`, or `.dwg`) to the selected plan set.
4. Upload supporting project documents (`.pdf`, `.txt`, `.md`) as project-wide documents or scoped to the selected plan set. Parsed files become downloadable; failed parses are quarantined and remain unavailable for download. Scanned PDFs can use OCR fallback when the API environment has Tesseract configured.
5. Use the **Estimator Copilot** on the dashboard to ask grounded questions about the selected project or plan set by typing or, where the browser supports it, by voice.
6. Open a sheet in the viewer.
7. Create point/rectangle/polygon/polyline annotations directly on the canvas.
8. (Optional) Set sheet calibration (full-sheet width/height + unit) to enable auto area/length quantity estimates.
9. Create takeoff items manually or from selected annotations (single-line or assembly package mode).
10. Review takeoff rollups, filter the workspace, and edit quantity/cost code/bid package/review state as needed.
11. Run AI analysis, then accept/reject/edit suggestions.
12. Use the sheet-level copilot to type or speak commands such as:
    - run analysis on the current sheet
    - batch-accept high-confidence suggestions
    - create a takeoff package from the selected annotation
    - create a snapshot
    - export CSV or JSON
13. Choose analysis provider per run (`mock`, `openai_vision` for PDF, or `cad_dxf` for DXF/DWG).
14. Batch-accept high-confidence suggestions (default threshold 85%).
15. Create snapshots and lock when final.
16. Export JSON or CSV.
17. Use the plan-set estimating dashboard to review cross-sheet coverage, discipline activity, unresolved suggestions, and sheet-specific work queues before publishing the estimate.

## Current capabilities

- PDF rendering with zoom and drag pan.
- CAD canvas preview for DXF/DWG sheets via normalized CAD entity geometry.
- Project document upload and parsing for:
  - `pdf`
  - `txt`
  - `md`
  - optional plan-set scoping on top of project-wide docs
  - raw upload staging with safe promotion on successful parse and quarantine on parse failure
  - optional OCR fallback for scanned/image-only PDFs via Tesseract
- Layer visibility toggles.
- Annotation inspector with delete and "create takeoff package" actions.
- Takeoff review workspace with:
  - rollup cards for visible item count, pending review, AI-assisted rows, and linked annotations
  - unit/category summary totals for the current filter set
  - filters by review state, source, and category
  - editable quantity, category, subcategory, review state, cost code, bid package, and notes
- Plan-set estimating dashboard:
  - summarizes takeoff, calibration, parsing, and analysis coverage for the selected plan set
  - rolls up activity by discipline
  - exposes a sheet-by-sheet worklist sorted by pending review and pending suggestions
  - highlights unassigned takeoff rows plus latest snapshot/export status without opening the sheet viewer
- Annotation-to-takeoff package creation profiles:
  - `auto` (detects door/window/fixture patterns)
  - `none` (single-line takeoff only)
  - `door_set`, `window_set`, `fixture_set` (explicit profile)
- On-canvas geometry edit handles for point/rectangle/polygon/polyline annotations.
- AI suggestion review panel with:
  - Accept
  - Reject
  - Edit + accept
  - Batch accept
- Provider selection in the analysis panel (`mock`, `openai_vision`, `cad_dxf`).
- CAD entity extraction provider (`cad_dxf`) for DXF/DWG plans:
  - Parses `LINE`, `LWPOLYLINE`, `CIRCLE`, `ARC`, `INSERT`, `TEXT`, `MTEXT`
  - Converts entities into normalized geometry suggestions for review/accept flow
- Auto quantity estimation during suggestion acceptance:
  - `square_feet` from geometry when calibration exists
  - `linear_feet` from polyline/rectangle geometry when calibration exists
  - fallback to `1` when calibration or geometry is insufficient
- Typed estimator copilot on the dashboard:
  - answers from live plan-set, sheet, takeoff, AI run, snapshot, and export data
  - searches parsed project documents and returns document citations when relevant
  - returns grounded citations for the records it used
  - scopes answers to the selected project and optional selected plan set
  - includes project-wide docs plus plan-set-scoped docs when a plan set is selected
  - routes category/review shorthand questions such as pending doors into takeoff summaries instead of document search
  - retrieval now favors selected-plan-set docs, matching document types, and newer relevant sources before generic fallback matches
  - explicitly reports when a needed spec, RFI, addendum, submittal, or vendor doc is not uploaded or did not parse yet
  - optional browser voice input captures spoken questions into the same grounded workflow
  - optional spoken replies read grounded answers aloud without changing source/citation behavior
- Sheet copilot inside the viewer:
  - understands typed or spoken action commands in sheet context
  - returns a structured action plan before execution
  - can run analysis, batch-accept suggestions, create takeoff packages from the selected annotation, create snapshots, and export CSV/JSON
  - reuses the same audited actions as the manual sheet workflow
  - reuses the existing audited API flows instead of mutating client state directly
- Estimator-grade quantity normalization:
  - applies to AI-generated rows and manual takeoff create/edit flows
  - configurable waste factors for linear/area units
  - configurable round-up steps for linear/area/cubic units
  - count/each quantities round up to whole units
- Auto assembly expansion:
  - accepted AI door suggestions create `doors` + `door_hardware` rows by default, including edited accepts that remain categorized as doors
  - annotation package creation can output primary + extra rows, and generated rows keep source-annotation lineage for review rollups
- Auto geometry-based quantity estimation when creating a takeoff package from a selected annotation.
- Snapshot create + lock.
- Export record creation with JSON/CSV payload responses.

## Current limitations

- Default AI provider remains `mock` unless `PRECONSTRUCTION_ANALYSIS_PROVIDER=openai_vision` is configured.
- `openai_vision` requires `PRECONSTRUCTION_OPENAI_API_KEY` and `pymupdf` installed in the API environment.
- OCR fallback for scanned project PDFs requires Tesseract installed in the API environment or configured via `PRECONSTRUCTION_DOCUMENT_OCR_COMMAND`.
- `openai_vision` supports PDF sheets only.
- `cad_dxf` supports ASCII DXF directly.
- DWG support requires `PRECONSTRUCTION_DWG_CONVERTER_COMMAND` to convert DWG -> DXF server-side.
- Binary DXF is still unsupported.
- Provider quality still depends on prompt quality, plan clarity, and calibration quality.
- PDF project document parsing requires `PyMuPDF` in the API environment.
- OCR fallback is heuristic and only runs on sparse-text PDF pages; poor scans can still fail or produce noisy text.
- Retrieval is still deterministic and citation-first, but now includes scope/type/recency weighting rather than plain token count alone.
- Voice input/output depends on browser speech APIs and gracefully falls back to typed interaction where unsupported.
- The copilot still does not support structured revision diffs.
- No snapshot diff/compare screen.
- "PDF metadata" export remains a placeholder, not a generated PDF file.

**Future (roadmap):** Possible next steps include project- or org-level rules (e.g. "door = doors + door_hardware") and exporting accepted/edited suggestions as labeled data for provider calibration or fine-tuning. No implementation commitment yet.

## AI provider configuration

Set in `apps/api/.env`:

- `PRECONSTRUCTION_ANALYSIS_PROVIDER=mock` (default), `openai_vision`, or `cad_dxf`
- `PRECONSTRUCTION_ANALYSIS_TIMEOUT_SECONDS=120`
- `PRECONSTRUCTION_OPENAI_API_KEY=...`
- `PRECONSTRUCTION_OPENAI_BASE_URL=https://api.openai.com/v1`
- `PRECONSTRUCTION_OPENAI_MODEL=gpt-4.1-mini`
- `PRECONSTRUCTION_OPENAI_MAX_SUGGESTIONS=25`
- `PRECONSTRUCTION_CAD_MAX_SUGGESTIONS=250`
- `PRECONSTRUCTION_CAD_PREVIEW_MAX_ITEMS=800`
- `PRECONSTRUCTION_DWG_CONVERTER_COMMAND=...` (must include `{input}` and either `{output}` or `{output_dir}`)
- `PRECONSTRUCTION_DWG_CONVERTER_TIMEOUT_SECONDS=180`
- `PRECONSTRUCTION_DOCUMENT_OCR_ENABLED=true`
- `PRECONSTRUCTION_DOCUMENT_OCR_COMMAND=tesseract`
- `PRECONSTRUCTION_DOCUMENT_OCR_TIMEOUT_SECONDS=30`
- `PRECONSTRUCTION_DOCUMENT_OCR_SCALE=2`
- `PRECONSTRUCTION_DOCUMENT_OCR_MIN_TEXT_CHARS=24`
- `PRECONSTRUCTION_LINEAR_ROUND_STEP_FEET=0.0001`
- `PRECONSTRUCTION_AREA_ROUND_STEP_SQFT=0.0001`
- `PRECONSTRUCTION_CUBIC_ROUND_STEP_CY=0.0001`
- `PRECONSTRUCTION_LINEAR_WASTE_FACTOR=0`
- `PRECONSTRUCTION_AREA_WASTE_FACTOR=0`

## API summary

Base path: `/api/preconstruction/`

- `sets/`: create/list/retrieve/update/delete plan sets
- `sheets/`: upload/list/retrieve/update/delete plan sheets
- `sheets/{id}/file/`: serve uploaded sheet file (PDF/DXF/DWG)
- `sheets/{id}/cad_preview/`: normalized CAD entity geometry for DXF/DWG canvas preview
- `documents/`: upload/list/retrieve/delete project documents
- `documents/{id}/file/`: download a parsed project document file (failed/unparsed docs return conflict instead of raw file access)
- `layers/`: annotation layers
- `annotations/`: annotation CRUD
- `annotations/{id}/create_takeoff/`: create takeoff package from one annotation (`assembly_profile` supported)
- `takeoff/`: takeoff CRUD
- `takeoff/summary/`: filtered takeoff rollups for estimator review workspace
- `takeoff/dashboard/`: plan-set estimating dashboard with cross-sheet, discipline, and latest-activity rollups
- `copilot/query/`: typed grounded Q&A over current preconstruction records
  - optional sheet-viewer action plans are also returned here when the request includes sheet context and an actionable command
- `analysis/`: trigger/list AI analysis runs
- `suggestions/`: list suggestions + accept/reject + batch_accept
- `snapshots/`: create/list snapshots + lock
- `exports/`: create/list export records

## Learning from estimator input

Every accept, edit, and reject is stored. Accept/edit/reject and review states are persisted on `AISuggestion` (`decision_state`, `decided_by`, `decided_at`) and on takeoff items (`review_state`). Snapshot payloads and exports include these outcomes so estimators can review and defend estimates. There is no active model retraining today; the system **adapts** by letting estimators correct suggestions and by using those corrections for reporting, the copilot, and audit. This data is available for future use (e.g. provider calibration or training data).

## Estimator workflows

- **Counting items (e.g. door knobs):** Use AI suggestions plus batch accept by confidence, or draw point/rectangle annotations and create takeoff (single-line or assembly such as door + hardware). Counts and categories appear in takeoff rollups and in CSV/JSON exports.
- **Shading areas:** Draw polygon or rectangle annotations on the sheet, set sheet calibration (width/height + unit), then create takeoff from the annotation with an area unit. Quantities are computed from geometry and calibration and appear in rollups and exports.
- **Learning from my input:** Every accept/edit/reject is stored; snapshots and exports capture outcomes for audit and for future calibration or learning pipelines.

## Data and audit notes

- AI decisions are stored on `AISuggestion` (`decision_state`, `decided_by`, `decided_at`).
- Accepted/edited outcomes create `AnnotationItem` and `TakeoffItem` entries.
- Snapshot payloads capture sheets, annotations, takeoff, and suggestion outcomes.
- All major mutating actions emit audit events.

## Developer note

Use serializer-level cross-reference validation and role checks for all writes to prevent cross-project payload mismatches.
