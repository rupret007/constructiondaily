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
- Draft-only report editing: once submitted, report content stays read-only until a rejection returns it to draft
- Offline job-site data capture with conflict-aware sync
- Defensible records through immutable audit events and PDF snapshots
- Security-by-default: strict authorization, secure sessions, safe uploads

## Preconstruction (Plan Annotation)

**For estimators:** The app delivers **insight on job plans** (counts, areas, rollups, coverage) and **automates estimator tasks** such as counting items (e.g. doors, hardware) and shading or measuring areas via annotations and takeoff. It **learns from your input** by recording every accept, edit, and reject and exposing that in snapshots, exports, and the copilot so you can review and defend estimates; that data is stored for audit and future calibration.

The app includes a **Preconstruction** area for plan annotation and takeoff: upload PDF, DXF, or DWG plan sheets, draw annotations, calibrate sheet dimensions for quantity estimation, and create takeoff lines manually or as annotation-driven takeoff packages (including assembly expansion such as door + hardware). AI-assisted suggestions are supported (default `mock`, optional `openai_vision` for PDF and `cad_dxf` for DXF/DWG), with quantity normalization controls (waste factors and round-up settings) applied across AI-generated rows and manual estimator edits to align with estimator workflows. The sheet viewer now includes a takeoff review workspace with rollups, filters, and editable estimator fields such as review state, cost code, and bid package, and package-generated rows retain source-annotation lineage for linked-item rollups. The dashboard includes a plan-set estimating workspace with cross-sheet rollups for coverage, discipline activity, latest snapshot/export status, and sheet-by-sheet review queues. It also includes a grounded **Estimator Copilot**, while the sheet viewer adds a sheet-scoped copilot that can turn typed or spoken commands into concrete actions such as running analysis, batch-accepting suggestions, creating a takeoff package from the selected annotation, creating snapshots, and exporting the current plan set. Both copilot surfaces can use browser-based voice input when supported and can optionally read grounded answers back aloud. Estimators can upload project documents such as specs, addenda, RFIs, submittals, and vendor docs (`.pdf`, `.txt`, `.md`) and the copilot will search those parsed documents with citations instead of relying only on plan/takeoff metadata. Project documents now land in a staged storage flow: successfully parsed files are promoted to a safe download location, failed parses are quarantined, and only parsed files can be downloaded. Scanned PDFs can also be parsed through an optional OCR fallback using Tesseract, and document retrieval now prefers in-scope and document-type-relevant matches before falling back to older generic hits. If the needed document is not uploaded or did not parse, the copilot will say that clearly instead of guessing. Teams can create **revision snapshots** (with optional lock for defensibility), and **export** takeoff data as JSON or CSV (export records are stored for audit). All actions are project-scoped and auditable. Locked snapshots and AI suggestion outcomes are stored so they can serve as high-quality labeled data for future learning. See **[docs/preconstruction.md](docs/preconstruction.md)** for step-by-step workflows, definitions, learning signals, provider configuration, and architecture reference (endpoints, components, limitations, next steps). Plan files are stored under the API media directory (e.g. `media/plans/`).

## Quick Start

**Easiest (Windows):** From the repo root, run **`start.bat`**. It pulls the latest from GitHub (when you have a git clone), builds the app with Podman, and starts the stack. Then follow [Getting started](docs/getting-started.md) to create a user and sign in at **http://localhost:8000**.

**Linux/macOS:** See [Deployment with Podman](docs/deployment-podman.md) for `podman compose` commands; [Getting started](docs/getting-started.md) has the same user/sign-in steps.

**Pre-built image:** CI builds and pushes images on every push to `main` and the feature branch. You can use `ghcr.io/rupret007/constructiondaily:main-latest` (or `:feature-latest`) instead of building locally; set `APP_IMAGE` in `.env` and run the stack as in [Deployment with Podman](docs/deployment-podman.md).

### Run without containers (API + Web)

1. **API:** In `apps/api`: `pip install -r requirements.txt`, `python manage.py migrate`, optionally `python manage.py seed_demo_data`, then `python manage.py runserver`.
2. **Web:** In `apps/web`: `npm install`, then `npm run dev`.
3. To give your user Preconstruction access: `python manage.py add_user_to_demo <your_username>` (after `createsuperuser`).
4. Open the URL shown by the web dev server and sign in.

## Security Notes

- Session cookies are configured for `Secure`, `HttpOnly`, and `SameSite`.
- Upload endpoints enforce type, extension, and file signature checks.
- Project documents are staged and only downloadable after successful parsing; failed parses are quarantined.
- OCR fallback for scanned project PDFs is supported when `tesseract` is installed/configured in the API environment.
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
- Browser regressions now cover sign-in, navigation into **Preconstruction**, plan-set creation, and the full daily report lifecycle with role handoffs and stale-revision conflict handling using Playwright.
