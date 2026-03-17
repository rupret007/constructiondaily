# Development Guide

## Local startup

Run the API and Web in two terminals, or use the Podman stack.

- **API:** From `apps/api`: `python manage.py migrate && python manage.py runserver` (port 8000).
- **Web:** From `apps/web`: `npm install && npm run dev` (port 5173). Open http://127.0.0.1:5173 when ready.
- **Containers:** For a full stack (app + Postgres), see [Deployment with Podman](deployment-podman.md).

## Preconstruction access

Preconstruction write actions require one of these project roles:

- Foreman
- Superintendent
- Project Manager
- Admin

Safety role has read access but cannot perform estimator write actions such as suggestion accept/reject.

## Offline sync behavior

- Report rejection now requires a non-empty reason.
- During offline sync, non-retryable validation/client errors (for example `400`) are dropped so one invalid payload does not block the entire queue. Authentication/authorization failures remain queued for retry after re-authentication.

## Demo setup

1. Seed demo data:
   - `python manage.py seed_demo_data`
2. Add your own user to the demo project (if needed):
   - `python manage.py add_user_to_demo <username>`
3. View demo project memberships:
   - `python manage.py add_user_to_demo`

Run commands from `apps/api`.
