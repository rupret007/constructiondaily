@echo off
REM Start API and Web dev servers for Construction Daily Report.
REM Opens two windows: API on port 8000, Web on port 5173.
REM Close both windows to stop.

set ROOT=%~dp0
set API=%ROOT%apps\api
set WEB=%ROOT%apps\web

REM Ensure Node is on PATH for the spawned Web window (common install location)
set "NODE_DIR=C:\Program Files\nodejs"
if exist "%NODE_DIR%\node.exe" set "PATH=%NODE_DIR%;%PATH%"

echo Starting Construction Daily Report...
echo.
echo Window 1: Django API (http://127.0.0.1:8000)
echo Window 2: Vite Web (http://127.0.0.1:5173)
echo.
echo Open http://127.0.0.1:5173 in your browser when both are ready.
echo Close the API and Web windows when done.
echo.

start "Construction Daily - API" cmd /k "cd /d "%API%" && python manage.py runserver"
timeout /t 2 /nobreak >nul
start "Construction Daily - Web" cmd /k "cd /d "%WEB%" && npm run dev"

echo.
echo Both servers started. Check the two new windows for any errors.
