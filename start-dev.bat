@echo off
REM Start API and Web dev servers for Construction Daily Report.
REM Runs: migrate, then API (port 8000); npm install, then Web (port 5173).
REM To stop: run stop-dev.bat or close the two server windows.

set ROOT=%~dp0
set API=%ROOT%apps\api
set WEB=%ROOT%apps\web

REM Ensure Node is on PATH for the spawned Web window (common install location)
set "NODE_DIR=C:\Program Files\nodejs"
if exist "%NODE_DIR%\node.exe" set "PATH=%NODE_DIR%;%PATH%"

echo Starting Construction Daily Report...
echo.
echo Window 1: Django API - migrate then runserver (http://127.0.0.1:8000)
echo Window 2: Vite Web - npm install then dev (http://127.0.0.1:5173)
echo.
echo Open http://127.0.0.1:5173 in your browser when both are ready.
echo To stop: run stop-dev.bat or close the two server windows.
echo.

start "Construction Daily - API" cmd /k "cd /d "%API%" && python manage.py migrate && python manage.py runserver"
timeout /t 2 /nobreak >nul
start "Construction Daily - Web" cmd /k "cd /d "%WEB%" && npm install && npm run dev"

echo.
echo Both servers started. Check the two new windows for any errors.
