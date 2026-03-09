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

The app includes a **Preconstruction** area for plan annotation and takeoff: upload PDF plan sheets, draw annotations, record quantities, use AI-assisted suggestions (mock in v1), create **revision snapshots** (with optional lock for defensibility), and **export** takeoff data as JSON or CSV (export records are stored for audit). All actions are project-scoped and auditable. Locked snapshots and AI suggestion outcomes are stored so they can serve as high-quality labeled data for future learning. See **[docs/preconstruction.md](docs/preconstruction.md)** for step-by-step workflows, definitions, learning signals, and architecture reference (endpoints, components, limitations, next steps). Plan files are stored under the API media directory (e.g. `media/plans/`).

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

From the repo root, run **`start-dev.bat`** to open two windows: the API (port 8000) and the web dev server (port 5173). Then open http://127.0.0.1:5173 in your browser. Requires Python and Node.js in your PATH; run `migrate` and `npm install` once per machine as in Quick Start above.

## Security Notes

- Session cookies are configured for `Secure`, `HttpOnly`, and `SameSite`.
- Upload endpoints enforce type, extension, and file signature checks.
- Audit logs are append-only for business-critical actions.
- The app never stores credentials or API secrets in source code.

## Validation Commands

- Backend tests: `python manage.py test` (from `apps/api`)
- Frontend tests: `npm run test` (from `apps/web`)
- Frontend build validation: `npm run build` (from `apps/web`)
