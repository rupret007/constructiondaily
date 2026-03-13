# Preconstruction Plan Annotation

Preconstruction supports plan-set management, plan sheet upload (PDF, DXF, and DWG), project document ingestion (PDF, TXT, MD), on-sheet annotation, takeoff tracking, AI suggestion review (configurable provider), revision snapshots, and exports.

## Access and roles

- Authentication is required.
- Read access: any user with active membership on the project.
- Write access for most actions: Foreman, Superintendent, Project Manager, Admin.
- Snapshot lock: Project Manager or Admin.

## Supported workflow

1. Open **Preconstruction** and choose a project.
2. Create a plan set.
3. Upload one or more plan files (`.pdf`, `.dxf`, or `.dwg`) to the selected plan set.
4. Upload supporting project documents (`.pdf`, `.txt`, `.md`) as project-wide documents or scoped to the selected plan set.
5. Use the typed **Estimator Copilot** on the dashboard to ask grounded questions about the selected project or plan set.
6. Open a sheet in the viewer.
7. Create point/rectangle/polygon/polyline annotations directly on the canvas.
8. (Optional) Set sheet calibration (full-sheet width/height + unit) to enable auto area/length quantity estimates.
9. Create takeoff items manually or from selected annotations (single-line or assembly package mode).
10. Review takeoff rollups, filter the workspace, and edit quantity/cost code/bid package/review state as needed.
11. Run AI analysis, then accept/reject/edit suggestions.
12. Choose analysis provider per run (`mock`, `openai_vision` for PDF, or `cad_dxf` for DXF/DWG).
13. Batch-accept high-confidence suggestions (default threshold 85%).
14. Create snapshots and lock when final.
15. Export JSON or CSV.

## Current capabilities

- PDF rendering with zoom and drag pan.
- CAD canvas preview for DXF/DWG sheets via normalized CAD entity geometry.
- Project document upload and parsing for:
  - `pdf`
  - `txt`
  - `md`
  - optional plan-set scoping on top of project-wide docs
- Layer visibility toggles.
- Annotation inspector with delete and "create takeoff package" actions.
- Takeoff review workspace with:
  - rollup cards for visible item count, pending review, AI-assisted rows, and linked annotations
  - unit/category summary totals for the current filter set
  - filters by review state, source, and category
  - editable quantity, category, subcategory, review state, cost code, bid package, and notes
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
  - explicitly reports when a needed spec, RFI, addendum, submittal, or vendor doc is not uploaded or did not parse yet
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
- `openai_vision` supports PDF sheets only.
- `cad_dxf` supports ASCII DXF directly.
- DWG support requires `PRECONSTRUCTION_DWG_CONVERTER_COMMAND` to convert DWG -> DXF server-side.
- Binary DXF is still unsupported.
- Provider quality still depends on prompt quality, plan clarity, and calibration quality.
- PDF project document parsing requires `PyMuPDF` in the API environment.
- No OCR pipeline yet for scanned image-only PDFs.
- Retrieval is deterministic text search for now; embeddings/reranking/model-grounded synthesis are later phases.
- The typed copilot does not yet support voice interaction or structured revision diffs.
- No snapshot diff/compare screen.
- "PDF metadata" export remains a placeholder, not a generated PDF file.

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
- `documents/{id}/file/`: serve uploaded project document file
- `layers/`: annotation layers
- `annotations/`: annotation CRUD
- `annotations/{id}/create_takeoff/`: create takeoff package from one annotation (`assembly_profile` supported)
- `takeoff/`: takeoff CRUD
- `takeoff/summary/`: filtered takeoff rollups for estimator review workspace
- `copilot/query/`: typed grounded Q&A over current preconstruction records
- `analysis/`: trigger/list AI analysis runs
- `suggestions/`: list suggestions + accept/reject + batch_accept
- `snapshots/`: create/list snapshots + lock
- `exports/`: create/list export records

## Data and audit notes

- AI decisions are stored on `AISuggestion` (`decision_state`, `decided_by`, `decided_at`).
- Accepted/edited outcomes create `AnnotationItem` and `TakeoffItem` entries.
- Snapshot payloads capture sheets, annotations, takeoff, and suggestion outcomes.
- All major mutating actions emit audit events.

## Developer note

Use serializer-level cross-reference validation and role checks for all writes to prevent cross-project payload mismatches.
