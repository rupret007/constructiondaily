# Preconstruction Plan Annotation

Preconstruction supports plan-set management, PDF sheet upload, on-sheet annotation, takeoff tracking, AI suggestion review (mock provider), revision snapshots, and exports.

## Access and roles

- Authentication is required.
- Read access: any user with active membership on the project.
- Write access for most actions: Foreman, Superintendent, Project Manager, Admin.
- Snapshot lock: Project Manager or Admin.

## Supported workflow

1. Open **Preconstruction** and choose a project.
2. Create a plan set.
3. Upload one or more PDF sheets to the selected plan set.
4. Open a sheet in the viewer.
5. Create point/rectangle annotations directly on the canvas.
6. Create takeoff items manually or from selected annotations.
7. Run AI analysis, then accept/reject/edit suggestions.
8. Batch-accept high-confidence suggestions (default threshold 85%).
9. Create snapshots and lock when final.
10. Export JSON or CSV.

## Current capabilities

- PDF rendering with zoom and drag pan.
- Layer visibility toggles.
- Annotation inspector with delete and "create takeoff" actions.
- AI suggestion review panel with:
  - Accept
  - Reject
  - Edit + accept
  - Batch accept
- Snapshot create + lock.
- Export record creation with JSON/CSV payload responses.

## Current limitations

- AI provider is mock/keyword-based, not production OCR/CV.
- UI only creates point and rectangle annotations (polygon/polyline models exist but no create tool yet).
- No geometric edit handles (move/resize) after annotation creation.
- No snapshot diff/compare screen.
- "PDF metadata" export remains a placeholder, not a generated PDF file.

## API summary

Base path: `/api/preconstruction/`

- `sets/`: create/list/retrieve/update/delete plan sets
- `sheets/`: upload/list/retrieve/update plan sheets
- `sheets/{id}/file/`: serve sheet PDF
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
