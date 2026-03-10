# Development Guide

## Local startup

- Preferred on Windows: run `start-dev.bat` from repo root.
- Stop servers with `stop-dev.bat`.

## Preconstruction access

Preconstruction write actions require one of these project roles:

- Foreman
- Superintendent
- Project Manager
- Admin

Safety role has read access but cannot perform estimator write actions such as suggestion accept/reject.

## Demo setup

1. Seed demo data:
   - `python manage.py seed_demo_data`
2. Add your own user to the demo project (if needed):
   - `python manage.py add_user_to_demo <username>`
3. View demo project memberships:
   - `python manage.py add_user_to_demo`

Run commands from `apps/api`.
