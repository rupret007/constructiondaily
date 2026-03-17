#!/usr/bin/env bash
# Poll registry for new app image; if digest changed, pull and recreate app.
# Run via systemd timer (hourly) or cron. Set APP_IMAGE in .env (e.g. ghcr.io/.../constructiondaily:feature-latest).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_PATH="${DEPLOY_PATH:-$REPO_ROOT}"
COMPOSE_FILE="${COMPOSE_FILE:-$DEPLOY_PATH/infra/podman-compose.yml}"
DIGEST_FILE="${DEPLOY_PATH}/.constructiondaily-image-digest"

cd "$DEPLOY_PATH"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
APP_IMAGE="${APP_IMAGE:-ghcr.io/rupret007/constructiondaily:feature-latest}"

COMPOSE_CMD="podman-compose"
command -v podman-compose &>/dev/null || COMPOSE_CMD="podman compose"

OLD_DIGEST=""
[ -f "$DIGEST_FILE" ] && OLD_DIGEST=$(cat "$DIGEST_FILE")

if ! $COMPOSE_CMD -f "$COMPOSE_FILE" pull app; then
  echo "Pull failed for app image" >&2
  exit 1
fi

NEW_DIGEST=$(podman image inspect --format '{{.Digest}}' "$APP_IMAGE" 2>/dev/null || echo "")
if [ -z "$NEW_DIGEST" ]; then
  echo "Could not get image digest for $APP_IMAGE after pull" >&2
  exit 1
fi

if [ "$OLD_DIGEST" = "$NEW_DIGEST" ]; then
  echo "No update: digest $NEW_DIGEST"
  exit 0
fi

echo "New image digest $NEW_DIGEST (was ${OLD_DIGEST:-none}), recreating app..."
$COMPOSE_CMD -f "$COMPOSE_FILE" up -d app
echo "$NEW_DIGEST" > "$DIGEST_FILE"
echo "Deploy completed."
