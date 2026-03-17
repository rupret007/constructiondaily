# Getting started (user guide)

This guide gets you from zero to signed in so you can use **Daily Reports** and **Preconstruction**.

## 1. Start the app

From the repo root, run:

```batch
start.bat
```

On Linux/macOS:

```bash
cp .env.example .env   # only if .env doesn't exist
podman compose -f infra/podman-compose.yml build
podman compose -f infra/podman-compose.yml up -d
```

When it finishes, the app is running at **http://localhost:8000**. If Podman isn’t installed, the script will prompt you; see [Deployment with Podman](deployment-podman.md).

## 2. Create a user (first time only)

You need at least one user to log in. Choose one of these.

### Option A: Quick demo users (easiest)

Creates a project and three users (all use the same password):

```batch
podman compose -f infra/podman-compose.yml exec app python manage.py seed_e2e_data
```

Then sign in at http://localhost:8000 with:

- **Username:** `e2e_pm`  
- **Password:** `e2e-pass-123`

Other demo users: `e2e_super`, `e2e_admin` (same password). They have different roles on the seeded project.

### Option B: Your own admin user

Create a superuser and set the password when prompted:

```batch
podman compose -f infra/podman-compose.yml exec app python manage.py createsuperuser
```

Then sign in with the username and password you chose. To use **Preconstruction**, create a project in the app (or use the Django admin at http://localhost:8000/admin/) and add your user to the project with a role (e.g. Project Manager).

## 3. Sign in

1. Open **http://localhost:8000** in your browser.
2. Enter your **username** and **password**.
3. Click **Login**.

## 4. What you can do next

- **Daily Reports** – Create and submit daily reports for a project; view and approve as superintendent or project manager.
- **Preconstruction** – Create a plan set, upload plan sheets (PDF/DXF/DWG), run analysis, accept or edit suggestions, use the copilot, create snapshots, and export takeoff data. See [Preconstruction](preconstruction.md) for workflows and concepts.

To stop the app: `podman compose -f infra/podman-compose.yml down` (from repo root).
