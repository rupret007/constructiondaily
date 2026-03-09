# Development Guide

## Preconstruction access

Preconstruction (plan sets, sheet uploads, annotations) requires the user to have a **project role** with write access: Foreman, Superintendent, Project Manager, or Admin on the selected project.

- **Option A – Seeded demo users:** Run `python manage.py seed_demo_data` to create the demo project and users (`foreman_demo`, `pm_demo`, `admin_demo`, etc.). Log in as one of them to use Preconstruction (passwords are printed once when the command creates the user).
- **Option B – Your own user:** If you use `createsuperuser` and want to use Preconstruction as that user, add them to the demo project:
  - `python manage.py add_user_to_demo <your_username>`
  - This adds a Project Manager membership on the DEMO-001 project. Run `seed_demo_data` first so the demo project exists.

Run `python manage.py add_user_to_demo` with no arguments to see current demo project members.
