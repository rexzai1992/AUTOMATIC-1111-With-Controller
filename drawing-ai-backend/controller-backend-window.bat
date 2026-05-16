@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ==================================================
REM Dedicated controller window
REM - waits for Stable Diffusion API
REM - starts backend after SD is ready
REM ==================================================

if not defined BACKEND_DIR (
    set "BACKEND_DIR=%~dp0"
    if "%BACKEND_DIR:~-1%"=="\" set "BACKEND_DIR=%BACKEND_DIR:~0,-1%"
)

set "SD_API_URL=http://127.0.0.1:7860/sdapi/v1/sd-models"
set "POLL_SECONDS=3"
set "TIMEOUT_SECONDS=180"

echo ==================================================
echo Controller Backend Window
echo ==================================================
echo [INFO] Controller route: "%BACKEND_DIR%"
echo [INFO] Waiting for Stable Diffusion API before starting backend...
echo [INFO] SD API URL: %SD_API_URL%

set /a ELAPSED=0
set /a ATTEMPT=0

:wait_sd
set /a ATTEMPT+=1
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"try { ^
  $resp = Invoke-WebRequest -Uri '%SD_API_URL%' -UseBasicParsing -TimeoutSec 4; ^
  if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400) { exit 0 } else { exit 1 } ^
} catch { ^
  exit 1 ^
}"

if not errorlevel 1 goto start_backend

echo [WAIT] Stable Diffusion not ready... !ELAPSED!s/%TIMEOUT_SECONDS%s (try !ATTEMPT!)
if !ELAPSED! GEQ %TIMEOUT_SECONDS% (
    echo Stable Diffusion startup failed
    echo Backend startup failed
    goto :eof
)

timeout /t %POLL_SECONDS% /nobreak >nul
set /a ELAPSED+=%POLL_SECONDS%
goto :wait_sd

:start_backend
echo [OK] Stable Diffusion API is ready.
echo [INFO] Starting backend server...
cd /d "%BACKEND_DIR%"

REM Use explicit Python interpreter so dependency checks and uvicorn share the same environment.
set "PY_CMD=python"
%PY_CMD% -c "import sys" >nul 2>&1
if errorlevel 1 (
    set "PY_CMD=py -3"
)

%PY_CMD% -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing backend requirements...
    %PY_CMD% -m pip install -r "%BACKEND_DIR%\requirements.txt"
)

%PY_CMD% -c "import websockets" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing WebSocket support (websockets)...
    %PY_CMD% -m pip install websockets wsproto
)

%PY_CMD% -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --ws websockets

echo.
echo [INFO] Backend process exited.
