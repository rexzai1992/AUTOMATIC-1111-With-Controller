@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ==================================================
REM One-click launcher for Stable Diffusion + Drawing AI Backend
REM Opens separate windows for Stable Diffusion and Controller.
REM ==================================================

REM ----- Resolve script location (backend folder) -----
set "BACKEND_DIR=%~dp0"
if "%BACKEND_DIR:~-1%"=="\" set "BACKEND_DIR=%BACKEND_DIR:~0,-1%"

REM ----- Configuration -----
set "SD_DIR=C:\AI ofline\stable-diffusion-webui"
set "SD_LAUNCHER=%SD_DIR%\webui-user.bat"
set "SD_API_URL=http://127.0.0.1:7860/sdapi/v1/sd-models"

set "CONTROLLER_WINDOW_SCRIPT=%BACKEND_DIR%\controller-backend-window.bat"
set "BACKEND_HEALTH_URL=http://127.0.0.1:8000/health"
set "BACKEND_STAFF_URL=http://localhost:8000/staff"
set "BACKEND_GALLERY_URL=http://localhost:8000/gallery"

echo ==================================================
echo Starting Drawing AI System...
echo ==================================================
echo [INFO] Stable Diffusion route: "%SD_DIR%"
echo [INFO] Controller route: "%BACKEND_DIR%"

REM Step 1: Start Stable Diffusion in a dedicated CMD window
if not exist "%SD_LAUNCHER%" (
    echo [ERROR] Stable Diffusion launcher not found:
    echo         "%SD_LAUNCHER%"
    exit /b 1
)

echo [1/6] Starting Stable Diffusion WebUI...
start "Stable Diffusion WebUI" conhost.exe cmd /k "cd /d ""%SD_DIR%"" && set ""COMMANDLINE_ARGS=--api --opt-sdp-attention"" && call ""%SD_LAUNCHER%"""
if errorlevel 1 (
    echo [ERROR] Could not open Stable Diffusion window.
    exit /b 1
)

REM Step 2: Open controller window immediately (it waits for SD then starts backend)
if not exist "%BACKEND_DIR%\app\main.py" (
    echo [ERROR] Backend app entry not found:
    echo         "%BACKEND_DIR%\app\main.py"
    exit /b 1
)
if not exist "%CONTROLLER_WINDOW_SCRIPT%" (
    echo [ERROR] Controller window script not found:
    echo         "%CONTROLLER_WINDOW_SCRIPT%"
    exit /b 1
)

echo [2/6] Opening Controller Backend window...
start "Controller Backend" conhost.exe cmd /k "set ""BACKEND_DIR=%BACKEND_DIR%"" && call ""%CONTROLLER_WINDOW_SCRIPT%"""
if errorlevel 1 (
    echo [ERROR] Could not open Controller Backend window.
    exit /b 1
)

REM Step 3: Wait until Stable Diffusion API responds
REM Poll interval: 3 seconds, timeout: 180 seconds
echo [3/6] Waiting for Stable Diffusion API...
call :wait_for_url "%SD_API_URL%" 3 180 "Stable Diffusion API"
if errorlevel 1 (
    echo Stable Diffusion startup failed
    exit /b 1
)

REM Step 4: Wait until backend health responds
REM Poll interval: 2 seconds, timeout: 60 seconds
echo [4/6] Waiting for Backend health endpoint...
call :wait_for_url "%BACKEND_HEALTH_URL%" 2 60 "Backend API"
if errorlevel 1 (
    echo Backend startup failed
    exit /b 1
)

REM Step 5: Open staff and gallery pages
echo [5/6] Opening browser tabs...
start "" "%BACKEND_STAFF_URL%"
start "" "%BACKEND_GALLERY_URL%"

REM Step 6: Final success status
echo [6/6] Final status:
echo.
echo System Ready
echo Stable Diffusion API: OK
echo Backend API: OK
echo Staff UI: OK
echo Gallery UI: OK

goto :eof

:wait_for_url
REM Args:
REM   %1 = URL
REM   %2 = poll interval seconds
REM   %3 = timeout seconds
REM   %4 = service name
set "CHECK_URL=%~1"
set "POLL_SECONDS=%~2"
set "TIMEOUT_SECONDS=%~3"
set "SERVICE_NAME=%~4"

echo [INFO] Checking %SERVICE_NAME% at %CHECK_URL%

set /a ELAPSED=0
set /a ATTEMPT=0

:wait_loop
set /a ATTEMPT+=1
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"try { ^
  $resp = Invoke-WebRequest -Uri '%CHECK_URL%' -UseBasicParsing -TimeoutSec 4; ^
  if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400) { exit 0 } else { exit 1 } ^
} catch { ^
  exit 1 ^
}"

if not errorlevel 1 (
    echo [OK] %SERVICE_NAME% is responding.
    exit /b 0
)

echo [WAIT] %SERVICE_NAME% not ready yet... !ELAPSED!s/%TIMEOUT_SECONDS%s (try !ATTEMPT!)
if !ELAPSED! GEQ %TIMEOUT_SECONDS% (
    echo [ERROR] %SERVICE_NAME% did not respond in %TIMEOUT_SECONDS% seconds.
    exit /b 1
)

timeout /t %POLL_SECONDS% /nobreak >nul
set /a ELAPSED+=%POLL_SECONDS%
goto :wait_loop
