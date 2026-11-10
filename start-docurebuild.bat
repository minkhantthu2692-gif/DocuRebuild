@echo off
setlocal EnableExtensions
title DocuRebuild
cd /d "%~dp0"

echo.
echo   DocuRebuild
echo   -----------
echo   Starting the local workspace...
echo.

where node >nul 2>nul
if errorlevel 1 goto :missing_node

node -e "process.exit(process.versions.node.split('.')[0] >= 20 ? 0 : 1)" >nul 2>nul
if errorlevel 1 goto :old_node

where python >nul 2>nul
if errorlevel 1 goto :missing_python

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto :old_python

if not exist "node_modules\vite\bin\vite.js" (
  echo Installing web dependencies. This is only needed once...
  call npm install
  if errorlevel 1 goto :install_failed
)

if not exist "backend\.venv\Scripts\python.exe" (
  echo Creating the local Python environment. This is only needed once...
  python -m venv "backend\.venv"
  if errorlevel 1 goto :install_failed
)

"backend\.venv\Scripts\python.exe" -c "import fastapi, uvicorn, sqlalchemy, alembic, pymupdf, PIL" >nul 2>nul
if errorlevel 1 (
  echo Installing backend dependencies. This is only needed once...
  "backend\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
  if errorlevel 1 goto :install_failed
)

call :ensure_api
call :ensure_web

echo.
echo Waiting for DocuRebuild to start...
call :wait_for "http://127.0.0.1:8000/api/health"
if errorlevel 1 goto :startup_failed
call :wait_for "http://localhost:5173/"
if errorlevel 1 goto :startup_failed

start "" "http://localhost:5173/"
echo.
echo DocuRebuild is running at http://localhost:5173/
echo Close the minimized "DocuRebuild API" and "DocuRebuild Web" windows to stop it.
ping 127.0.0.1 -n 4 >nul
exit /b 0


:ensure_api
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if not errorlevel 1 (
  echo The local API is already running on port 8000.
  exit /b 0
)
echo Starting the local API...
start "DocuRebuild API" /min "%~dp0backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir "%~dp0backend"
exit /b 0


:ensure_web
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if not errorlevel 1 (
  echo The web client is already running on port 5173.
  exit /b 0
)
echo Starting the web client...
start "DocuRebuild Web" /min cmd /c "npm run dev:web"
exit /b 0


:wait_for
powershell -NoProfile -Command "$end = (Get-Date).AddSeconds(90); while ((Get-Date) -lt $end) { try { $response = Invoke-WebRequest -UseBasicParsing -Uri '%~1' -TimeoutSec 2; if ($response.StatusCode -lt 400) { exit 0 } } catch {}; Start-Sleep -Milliseconds 500 }; exit 1"
if errorlevel 1 exit /b 1
exit /b 0


:missing_node
echo.
echo [ERROR] Node.js was not found.
echo Install Node.js 20 or newer, then run this file again.
echo https://nodejs.org/
goto :failed

:old_node
echo.
echo [ERROR] Node.js 20 or newer is required.
echo Update Node.js, then run this file again.
echo https://nodejs.org/
goto :failed

:missing_python
echo.
echo [ERROR] Python was not found.
echo Install Python 3.11 or newer, then run this file again.
echo https://www.python.org/downloads/
goto :failed

:old_python
echo.
echo [ERROR] Python 3.11 or newer is required.
echo Update Python, then run this file again.
echo https://www.python.org/downloads/
goto :failed

:install_failed
echo.
echo [ERROR] Dependency installation failed.
echo Check your internet connection and the messages above, then try again.
goto :failed

:startup_failed
echo.
echo [ERROR] DocuRebuild did not finish starting.
echo Check the minimized "DocuRebuild API" and "DocuRebuild Web" windows for details.
goto :failed

:failed
echo.
pause
exit /b 1
