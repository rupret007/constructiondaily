@echo off
REM Stop the Construction Daily Report dev servers (API on 8000, Web on 5173).
REM Uses PowerShell to find and kill processes listening on those ports.

echo Stopping Construction Daily Report dev servers...
echo.

powershell -NoProfile -Command ^
  "$ports = 8000, 5173; foreach ($p in $ports) { $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($c) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue; Write-Host ('Stopped process on port ' + $p) } else { Write-Host ('No process found on port ' + $p) } }"

echo.
echo Done. If either server was running, it has been stopped.
