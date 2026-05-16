@echo off
setlocal
title Drawing AI Backend Launcher

cd /d "%~dp0"

echo.
echo ===================================
echo   Drawing AI Backend Launcher
echo ===================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [Setup] Virtual environment not found. Creating .venv...
  where py >nul 2>nul
  if %errorlevel%==0 (
    py -3 -m venv .venv
  ) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
      python -m venv .venv
    ) else (
      echo [Error] Python was not found. Install Python 3.10+ and try again.
      pause
      exit /b 1
    )
  )

  if errorlevel 1 (
    echo [Error] Failed to create .venv.
    pause
    exit /b 1
  )

  echo [Setup] Installing dependencies...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 goto :pip_error
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :pip_error
  echo [Setup] Done.
  echo.
)

REM Ensure websocket dependency exists even for older already-created .venv.
".venv\Scripts\python.exe" -c "import websockets" >nul 2>nul
if errorlevel 1 (
  echo [Setup] Missing websockets in .venv. Updating dependencies...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :pip_error
)

echo [Info] Checking Stable Diffusion WebUI at http://127.0.0.1:7860 ...
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:7860' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  echo [Warning] Stable Diffusion WebUI is not reachable.
  echo           Start it first if you need image generation.
  echo.
)

echo [Run] Starting backend on http://127.0.0.1:8000
start "" "http://127.0.0.1:8000/staff"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --ws websockets

set "EXIT_CODE=%errorlevel%"
echo.
if "%EXIT_CODE%"=="0" (
  echo [Info] Backend stopped.
) else (
  echo [Error] Backend exited with code %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%

:pip_error
echo [Error] Failed to install dependencies.
pause
exit /b 1
