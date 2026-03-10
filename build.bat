@echo off
REM Production build: frontend + collectstatic. Run from repo root.
REM Requires: Node.js and Python in PATH. Run in apps/api venv for Python deps.

set ROOT=%~dp0
set API=%ROOT%apps\api
set WEB=%ROOT%apps\web

set "NODE_DIR=C:\Program Files\nodejs"
if exist "%NODE_DIR%\node.exe" set "PATH=%NODE_DIR%;%PATH%"

echo Building Construction Daily Report for production...
echo.

echo [1/3] Building frontend (npm run build in apps/web)...
cd /d "%WEB%"
call npm run build
if errorlevel 1 (
  echo ERROR: Frontend build failed.
  exit /b 1
)

echo.
echo [2/3] Collecting static files (manage.py collectstatic)...
cd /d "%API%"
call python manage.py collectstatic --noinput
if errorlevel 1 (
  echo ERROR: collectstatic failed.
  exit /b 1
)

echo.
echo [3/3] Run deploy check (manage.py check --deploy)...
call python manage.py check --deploy
if errorlevel 1 (
  echo WARNING: check --deploy reported issues. Review before deploying.
)

echo.
echo Build complete. To run in production:
echo   cd apps\api
echo   gunicorn config.wsgi:application --bind 0.0.0.0:8000
echo.
echo Set env: DJANGO_DEBUG=false, DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, etc.
echo See docs/deployment.md for details.
