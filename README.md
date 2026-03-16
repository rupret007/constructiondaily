# Construction Daily Report

Internal web application for construction daily job reporting with:

- React PWA frontend for mobile-first field entry
- Django REST API backend for workflow and security controls
- PostgreSQL data model for auditable project records
- Object storage compatible media pipeline for photos and attachments

## Repository Layout

- `apps/web` - React + TypeScript + Vite PWA
- `apps/api` - Django + DRF API services
- `infra` - local deployment samples and environment templates
- `docs` - architecture and operational guides

## Design Goals

- Daily-report-first workflow: draft, submit, review, approve, lock
- Offline job-site data capture with conflict-aware sync
- Defensible records through immutable audit events and PDF snapshots
- Security-by-default: strict authorization, secure sessions, safe uploads

## Preconstruction (Plan Annotation)

 The app includes a **Preconstruction** area for plan annotation and takeoff: upload PDF, DXF, or DWG plan sheets, draw annotations, calibrate sheet dimensions for quantity estimation, and create takeoff lines manually or as annotation-driven takeoff packages (including assembly expansion such as door + hardware). AI-assisted suggestions are supported (default `mock`, optional `openai_vision` for PDF and `cad_dxf` for DXF/DWG), with quantity normalization controls (waste factors and round-up settings) applied across AI-generated rows and manual estimator edits to align with estimator workflows. The sheet viewer now includes a takeoff review workspace with rollups, filters, and editable estimator fields such as review state, cost code, and bid package, and package-generated rows retain source-annotation lineage for linked-item rollups. The dashboard also now includes a typed **Estimator Copilot** that answers grounded questions from live preconstruction data already in the app: plan sets, sheets, takeoff summaries, AI runs, snapshots, exports, and parsed project documents. Estimators can upload project documents such as specs, addenda, RFIs, submittals, and vendor docs (`.pdf`, `.txt`, `.md`) and the copilot will search those parsed documents with citations instead of relying only on plan/takeoff metadata. Project documents now land in a staged storage flow: successfully parsed files are promoted to a safe download location, failed parses are quarantined, and only parsed files can be downloaded. If the needed document is not uploaded or did not parse, the copilot will say that clearly instead of guessing. Teams can create **revision snapshots** (with optional lock for defensibility), and **export** takeoff data as JSON or CSV (export records are stored for audit). All actions are project-scoped and auditable. Locked snapshots and AI suggestion outcomes are stored so they can serve as high-quality labeled data for future learning. See **[docs/preconstruction.md](docs/preconstruction.md)** for step-by-step workflows, definitions, learning signals, provider configuration, and architecture reference (endpoints, components, limitations, next steps). Plan files are stored under the API media directory (e.g. `media/plans/`).

## Quick Start

### API

1. Create virtual environment in `apps/api`.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Initialize database:
   - `python manage.py migrate`
4. Seed pilot users/project (optional):
   - `python manage.py seed_demo_data`
5. Give your own user Preconstruction access (optional): if you use `createsuperuser` and want to use the Preconstruction area, add that user to the demo project with a write role:
   - `python manage.py add_user_to_demo <your_username>`
6. Run API:
   - `python manage.py runserver`

### Web

1. Install dependencies in `apps/web`:
   - `npm install`
2. Start development server:
   - `npm run dev`

### One-command startup (Windows)

From the repo root, run **`start-dev.bat`** to start everything: it runs `migrate` then the API (port 8000), and `npm install` then the web dev server (port 5173) in two windows. Open http://127.0.0.1:5173 in your browser when ready. Requires Python and Node.js in your PATH. To stop the servers, run **`stop-dev.bat`** or close the two server windows.

## Security Notes

- Session cookies are configured for `Secure`, `HttpOnly`, and `SameSite`.
- Upload endpoints enforce type, extension, and file signature checks.
- Project documents are staged and only downloadable after successful parsing; failed parses are quarantined.
- Audit logs are append-only for business-critical actions.
- The app never stores credentials or API secrets in source code.

## Production Build

From the repo root, run **`build.bat`** to build the frontend, collect static files, and run the deploy check. See [docs/deployment.md](docs/deployment.md) for full production deployment.

## Validation Commands

- Backend tests: `python manage.py test` (from `apps/api`)
- Frontend tests: `npm run test` (from `apps/web`)
- Frontend build validation: `npm run build` (from `apps/web`)
- Browser smoke/regression tests: `npx playwright install chromium` then `npm run test:e2e` (from `apps/web`)

## Regression Guardrails

- Repository CI now lives in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) and runs backend tests, frontend tests/build, and browser smoke tests on pushes and pull requests.
- Deterministic browser smoke-test data can be seeded from `apps/api` with `python manage.py seed_e2e_data`.
- The first browser regression covers sign-in, navigation into **Preconstruction**, and plan-set creation using Playwright.
