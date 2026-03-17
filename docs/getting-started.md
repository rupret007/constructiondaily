# Getting started (user guide)

This guide gets you from zero to signed in so you can use **Daily Reports** and **Preconstruction**.

## 1. Start the app

From the repo root, run:

```batch
start.bat
```

When run from a git clone, the script pulls the latest from GitHub and then builds and starts the app, so you always get the latest version. Set `SKIP_PULL=1` to skip the pull step.

On Linux/macOS:

```bash
cp .env.example .env   # only if .env doesn't exist
podman compose -f infra/podman-compose.yml build
podman compose -f infra/podman-compose.yml up -d
```

When it finishes, the app is running at **http://localhost:8000**. If Podman isn’t installed, the script will prompt you; see [Deployment with Podman](deployment-podman.md).

## 2. Create a user (first time only)

You need one user to log in. The app uses username + password (no passwordless option yet).

### Option A: One-step demo (easiest)

Creates one user and one project. Then sign in with:

- **Username:** `admin`  
- **Password:** `admin`

```batch
podman compose -f infra/podman-compose.yml exec app python manage.py seed_simple
```

For a different username/password: `seed_simple --username demo --password demo`

### Option B: Your own user

Create a superuser and choose any password (for local use you can keep it short, e.g. `admin`):

```batch
podman compose -f infra/podman-compose.yml exec app python manage.py createsuperuser
```

Then sign in with what you chose. To use **Preconstruction**, add your user to a project (Django admin at http://localhost:8000/admin/ or create a project in the app).

## 3. Sign in

1. Open **http://localhost:8000** in your browser.
2. Enter your **username** and **password**.
3. Click **Login**.

## 4. What you can do next

- **Daily Reports** – Create and submit daily reports for a project; view and approve as superintendent or project manager.
- **Preconstruction** – Create a plan set, upload plan sheets (PDF/DXF/DWG), run analysis, accept or edit suggestions, use the copilot, create snapshots, and export takeoff data. See [Preconstruction](preconstruction.md) for workflows and concepts.

To stop the app: `podman compose -f infra/podman-compose.yml down` (from repo root).
