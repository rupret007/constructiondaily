# Deployment with Podman (container stack)

This guide covers running Construction Daily as a Podman Compose stack (app + Postgres), with optional **immediate deploy** from GitHub Actions and **hourly poll-update** on the server.

## Quick start (local PC)

From the repo root, run:

```batch
start.bat
```

That creates `.env` from `.env.example` if needed, builds the app image, and starts the stack. The API is at **http://localhost:8000**. No need to edit `.env` for local dev (defaults are dev-only).

To stop: `podman compose -f infra/podman-compose.yml down`

**First-time login:** After the stack is up, create a user so you can sign in. See **[Getting started](getting-started.md)** for step-by-step: simple demo (`seed_simple` → sign in as **admin** / **admin**) or your own user (`createsuperuser`), then open http://localhost:8000 and log in.

On Linux/macOS, same steps without the script:

```bash
cp .env.example .env   # only if .env doesn't exist
podman compose -f infra/podman-compose.yml build
podman compose -f infra/podman-compose.yml up -d
```

## Stack

- **app:** Django + Gunicorn, built frontend assets, port 8000.
- **db:** PostgreSQL 16 (Alpine), persistent volume.

Images are published to **GHCR** and **Docker Hub** on pushes to `feature/preconstruction-plan-annotation` (tags: commit SHA and `feature-latest`).

## Admin deploy from GitHub

Admins can deploy in two ways. **From GitHub:** Push to the feature branch to trigger the container workflow; if deploy secrets are set, the workflow will build the image, push to registries, and optionally SSH to the server to run `deploy.sh` (pull + up + migrations). **On the server:** Ensure `DEPLOY_PATH` and any required secrets are set, then run `./infra/podman/deploy.sh` from the deploy directory, or rely on the hourly timer to pull and restart when a new image is available. After deploy, smoke test with: `curl -sf http://localhost:8000/api/schema/` (or your host); expect HTTP 200.

## Prerequisites

- Podman (and `podman-compose` or `podman compose`; the deploy script detects either).
- Server: either a **full repo clone** (so `podman-compose build` works if you ever build locally) or only **`infra/` and `.env`** if you always update via the deploy script or CI (pull + up only; no build on server).

## Private registry

If `APP_IMAGE` is from a private registry (e.g. private GHCR), log in on the server before the first deploy or before enabling the hourly timer:

```bash
echo "<token>" | podman login ghcr.io -u <username> --password-stdin
```

Use a GitHub PAT or other token with `read:packages` (for pull).

## Environment

Copy `.env.example` to `.env` in the **deploy directory** (repo root or `DEPLOY_PATH`) and set:

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_PASSWORD` | Yes | DB password (match `DATABASE_URL`). Avoid `#`, `@`, `:` or `%`; or URL-encode if you set `DATABASE_URL` by hand. |
| `DJANGO_SECRET_KEY` | Yes | Long random string |
| `APP_IMAGE` | No | Full image:tag (default: `ghcr.io/rupret007/constructiondaily:feature-latest`) |
| `APP_PORT` | No | Host port for app (default: 8000) |
| `DJANGO_DEBUG` | No | `false` in production |
| `DJANGO_ALLOWED_HOSTS` | No | Comma-separated hosts |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | If HTTPS | Comma-separated origins |
| `DEPLOY_PATH` | For scripts | Server path containing `.env` and `infra/` (e.g. `/opt/constructiondaily`) |

`DATABASE_URL` and other Postgres vars are derived from `POSTGRES_*` in the compose file.

## Run the stack

From the **deploy directory** (repo root or `DEPLOY_PATH`):

```bash
podman-compose -f infra/podman-compose.yml up -d
# or: podman compose -f infra/podman-compose.yml up -d
```

- App: http://localhost:8000 (or `APP_PORT`).
- DB: localhost:5432 (for admin tools); use `db:5432` from inside the app container.

## Deploy script (pull and restart app)

To update the app container from the registry without touching the DB:

```bash
./infra/podman/deploy.sh
```

Uses `DEPLOY_PATH` and `COMPOSE_FILE` from the environment (or defaults from script location). Loads `.env` from `DEPLOY_PATH`.

## Hourly poll-update (systemd)

The server can periodically check for a new image and update the app:

1. Copy systemd units and fix paths:
   ```bash
   sudo cp infra/podman/systemd/constructiondaily-update.service /etc/systemd/system/
   sudo cp infra/podman/systemd/constructiondaily-update.timer /etc/systemd/system/
   ```
   Edit the service so both point at your deploy directory (e.g. `/opt/constructiondaily`):
   - `Environment=DEPLOY_PATH=/opt/constructiondaily`
   - `ExecStart=/opt/constructiondaily/infra/podman/poll-update.sh`

2. Ensure the poll script is executable:
   ```bash
   chmod +x /opt/constructiondaily/infra/podman/poll-update.sh
   ```

3. Enable and start the timer:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now constructiondaily-update.timer
   sudo systemctl list-timers constructiondaily-update.timer
   ```

The timer runs **hourly**; the service runs `poll-update.sh`, which compares the current image digest with the last one, and if changed runs pull + `up -d app`. On first run (if the stack was never started), the poll can bring up both `db` and `app` via `up -d app` (because of `depends_on`).

## Rollback

To revert to a previous image:

1. Set the image tag (e.g. previous commit SHA or a known-good tag):
   ```bash
   export APP_IMAGE=ghcr.io/rupret007/constructiondaily:<previous-sha>
   ```
   Or put `APP_IMAGE=...` in `.env`.

2. Redeploy app only (DB volume is unchanged):
   ```bash
   ./infra/podman/deploy.sh
   ```

## Health and smoke check

- Compose healthchecks: app uses `curl -sf http://127.0.0.1:8000/api/schema/`; db uses `pg_isready`.
- After deploy, hit `http://<host>:8000/api/schema/` or the app root to confirm the app is up.

## Data safety

- The **Postgres volume** (`postgres_data`) is separate from the app. Replacing or recreating the app container does **not** recreate the DB volume.
- Media files are in the `app_media` volume; back them up separately if needed.

## CI/CD and secrets

- **Build and push:** On push to `feature/preconstruction-plan-annotation`, `.github/workflows/container-deploy.yml` builds the app image and pushes to GHCR (and optionally Docker Hub). No deploy secrets required for that.
- **Immediate deploy:** If GitHub secrets are set (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_PATH`, and optionally `DEPLOY_PORT`), the workflow SSHs to the server and runs `infra/podman/deploy.sh` (pull, up, migrations). The script works with either `podman-compose` or `podman compose`.
- **Docker Hub:** To push to Docker Hub, set **both** `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`; omit both if you only use GHCR.
- See the workflow file for the full list of deploy and registry secrets.
