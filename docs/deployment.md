# Deployment Guide

This guide covers production deployment for Construction Daily Report (Django + React/Vite).

## Architecture

- **Single server:** Django serves the API (`/api/*`), the built React SPA (all other routes), and static files via WhiteNoise.
- **Database:** PostgreSQL (use `DATABASE_URL` or `POSTGRES_*` env vars).
- **Process:** Gunicorn (WSGI) runs the Django app.

## Prerequisites

- Python 3.11+ with venv
- Node.js 18+ (for frontend build only)
- PostgreSQL

## Build

1. **From repo root**, run the build script:
   ```bat
   build.bat
   ```
   This builds the frontend (`npm run build`), runs `collectstatic`, and performs a deploy check.

2. **Or manually:**
   ```bash
   cd apps/web && npm install && npm run build
   cd ../../apps/api && pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --noinput
   ```

## Environment Variables

Set before running in production:

| Variable | Required | Description |
|----------|----------|-------------|
| `DJANGO_DEBUG` | Yes | Must be `false` |
| `DJANGO_SECRET_KEY` | Yes | Long random string (e.g. 50+ chars) |
| `DJANGO_ALLOWED_HOSTS` | Yes | Comma-separated hosts (e.g. `yourdomain.com,www.yourdomain.com`) |
| `DATABASE_URL` | For Postgres | `postgres://user:pass@host:5432/dbname` |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, etc. | If using Postgres | See `.env.example` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | If HTTPS | Comma-separated origins (e.g. `https://yourdomain.com`) |

For HTTPS, also set:

- `SECURE_SSL_REDIRECT=True` (or use a reverse proxy to redirect)
- `SECURE_HSTS_SECONDS=31536000` (if entire site is HTTPS)

## Run with Gunicorn

```bash
cd apps/api
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2
```

For production, use a process manager (systemd, supervisord) and a reverse proxy (Nginx, Caddy) in front for HTTPS and static/media optimization.

## Deploy Check

Run `python manage.py check --deploy` before deploying. It reports security and configuration issues. Address warnings before going live.

## Static and Media Files

- **Static:** WhiteNoise serves files from `STATIC_ROOT` (populated by `collectstatic`).
- **Media:** Uploaded files go to `MEDIA_ROOT`. In production, serve media via Nginx or object storage; Django can serve it in development.

## Docker (infra)

See `infra/docker-compose.yml` for a PostgreSQL service. Extend it with a Django/Gunicorn service for full containerized deployment.
