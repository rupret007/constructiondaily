#!/usr/bin/env bash
# Deploy or update the app container. Use from server deploy path or set DEPLOY_PATH.
# Usage: ./deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_PATH="${DEPLOY_PATH:-$REPO_ROOT}"
COMPOSE_FILE="${COMPOSE_FILE:-$DEPLOY_PATH/infra/podman-compose.yml}"

cd "$DEPLOY_PATH"
if [ -f .env ]; then set -a; . ./.env; set +a; fi

COMPOSE_CMD="podman-compose"
if ! command -v podman-compose &>/dev/null; then
  COMPOSE_CMD="podman compose"
fi

"$COMPOSE_CMD" -f "$COMPOSE_FILE" pull app
"$COMPOSE_CMD" -f "$COMPOSE_FILE" up -d app
# Run migrations if app is already up (e.g. from CI)
"$COMPOSE_CMD" -f "$COMPOSE_FILE" exec -T app python manage.py migrate --noinput 2>/dev/null || true

echo "App container updated. Check health with: $COMPOSE_CMD -f $COMPOSE_FILE ps"
