#!/bin/sh
set -e
if [ -n "$DATABASE_URL" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput --clear
fi
exec "$@"
