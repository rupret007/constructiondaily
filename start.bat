@echo off
REM One-command start: ensure .env, build and run the Podman stack (API + Postgres).
REM Run from repo root. Requires Podman (podman compose or podman-compose).

set ROOT=%~dp0
cd /d "%ROOT%"

where podman >nul 2>&1
if errorlevel 1 (
  echo Podman not found. Install it first, then open a new terminal and run start.bat again.
  echo.
  echo Install with Winget:
  echo   winget install RedHat.Podman
  echo.
  echo First time after install you may need: podman machine init
  echo Then: podman machine start
  echo.
  set /p TRY="Try to install Podman now via Winget? [y/N]: "
  if /i "%TRY%"=="y" (
    winget install RedHat.Podman
    echo.
    echo After install, close this window, open a new terminal, and run start.bat again.
  )
  exit /b 1
)

if not "%SKIP_PULL%"=="1" if exist .git (
  echo Pulling latest...
  git pull
  if errorlevel 1 (
    echo Pull failed or skipped; using current files.
  )
  echo.
)
if "%SKIP_PULL%"=="1" if exist .git (
  echo Skipping pull (SKIP_PULL=1).
  echo.
)
if not exist .git (
  echo Not a git repo, skipping pull.
  echo.
)

if not exist .env (
  echo Creating .env from .env.example...
  copy .env.example .env >nul
  echo Edit .env for production; defaults are for local dev only.
  echo.
)

echo Building and starting containers...
podman compose -f infra/podman-compose.yml build
if errorlevel 1 (
  echo Build failed. If "podman compose" is not found, try: podman-compose -f infra/podman-compose.yml build
  exit /b 1
)

podman compose -f infra/podman-compose.yml up -d
if errorlevel 1 (
  echo Up failed. Try: podman-compose -f infra/podman-compose.yml up -d
  exit /b 1
)

echo.
echo App is running at http://localhost:8000
echo Smoke check: curl -sf http://localhost:8000/api/schema/
echo Logs: podman compose -f infra/podman-compose.yml logs -f app
echo Stop: podman compose -f infra/podman-compose.yml down
echo.
