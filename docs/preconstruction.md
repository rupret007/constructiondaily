# Preconstruction Plan Annotation

Preconstruction supports plan-set management, plan sheet upload (PDF and DXF), on-sheet annotation, takeoff tracking, AI suggestion review (configurable provider), revision snapshots, and exports.

## Access and roles

- Authentication is required.
- Read access: any user with active membership on the project.
- Write access for most actions: Foreman, Superintendent, Project Manager, Admin.
- Snapshot lock: Project Manager or Admin.

## Supported workflow

1. Open **Preconstruction** and choose a project.
2. Create a plan set.
3. Upload one or more plan files (`.pdf` or `.dxf`) to the selected plan set.
4. Open a sheet in the viewer.
5. Create point/rectangle/polygon/polyline annotations directly on the canvas.
6. (Optional) Set sheet calibration (full-sheet width/height + unit) to enable auto area/length quantity estimates.
7. Create takeoff items manually or from selected annotations.
8. Run AI analysis, then accept/reject/edit suggestions.
9. Choose analysis provider per run (`mock`, `openai_vision` for PDF, or `cad_dxf` for DXF).
10. Batch-accept high-confidence suggestions (default threshold 85%).
11. Create snapshots and lock when final.
12. Export JSON or CSV.

## Current capabilities

- PDF rendering with zoom and drag pan.
- Layer visibility toggles.
- Annotation inspector with delete and "create takeoff" actions.
- On-canvas geometry edit handles for point/rectangle/polygon/polyline annotations.
- AI suggestion review panel with:
  - Accept
  - Reject
  - Edit + accept
  - Batch accept
- Provider selection in the analysis panel (`mock`, `openai_vision`, `cad_dxf`).
- DXF entity extraction provider (`cad_dxf`) for ASCII DXF plans:
  - Parses `LINE`, `LWPOLYLINE`, `CIRCLE`, `ARC`, `INSERT`, `TEXT`, `MTEXT`
  - Converts entities into normalized geometry suggestions for review/accept flow
- Auto quantity estimation during suggestion acceptance:
  - `square_feet` from geometry when calibration exists
  - `linear_feet` from polyline/rectangle geometry when calibration exists
  - fallback to `1` when calibration or geometry is insufficient
- Auto geometry-based quantity estimation when creating takeoff from a selected annotation.
- Snapshot create + lock.
- Export record creation with JSON/CSV payload responses.

## Current limitations

- Default AI provider remains `mock` unless `PRECONSTRUCTION_ANALYSIS_PROVIDER=openai_vision` is configured.
- `openai_vision` requires `PRECONSTRUCTION_OPENAI_API_KEY` and `pymupdf` installed in the API environment.
- `openai_vision` supports PDF sheets only.
- `cad_dxf` supports ASCII DXF only (binary DXF and DWG are not yet supported).
- DXF files are analyzable but not yet rendered in the canvas viewer.
- Provider quality still depends on prompt quality, plan clarity, and calibration quality.
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

## API summary

Base path: `/api/preconstruction/`

- `sets/`: create/list/retrieve/update/delete plan sets
- `sheets/`: upload/list/retrieve/update/delete plan sheets
- `sheets/{id}/file/`: serve uploaded sheet file (PDF/DXF)
- `layers/`: annotation layers
- `annotations/`: annotation CRUD
- `takeoff/`: takeoff CRUD
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
