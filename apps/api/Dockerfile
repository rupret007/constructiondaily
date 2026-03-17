# Build context: repo root (so we can copy apps/web and apps/api)
# Multi-stage: frontend build, then Django app with static assets

# ---- Frontend ----
FROM node:22-alpine AS frontend
WORKDIR /build

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web/ .
ENV VITE_API_BASE=/api
RUN npm run build

# ---- App ----
FROM python:3.11-slim AS app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install API dependencies
COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy API code
COPY apps/api/ .

# Frontend static: Django expects BASE_DIR.parent / "web" / "dist" (see settings.py WEB_DIST)
COPY --from=frontend /build/dist /web/dist

# Create dirs for static collect and media
RUN mkdir -p staticfiles media

# Entrypoint: migrate, collectstatic, then gunicorn
COPY apps/api/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
