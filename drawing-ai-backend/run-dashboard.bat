@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ==================================================
REM Dashboard launcher (backend + Cloudflare Tunnel)
REM - Starts backend if not already running
REM - Starts Cloudflare Tunnel (named tunnel if available, else quick tunnel)
REM - Opens public dashboard pages
REM ==================================================

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%.") do set "BACKEND_DIR=%%~fI"

set "BACKEND_HEALTH_URL=http://127.0.0.1:8000/health"
set "TUNNEL_LOCAL_URL=http://127.0.0.1:8000"
set "TUNNEL_PUBLIC_HOST=Image-generator-wonderpark.izzul.xyz"
set "TUNNEL_NAME=image-generator-wonderpark"

REM Optional overrides from environment variables.
if defined CLOUDFLARE_TUNNEL_NAME set "TUNNEL_NAME=%CLOUDFLARE_TUNNEL_NAME%"
if defined CLOUDFLARE_PUBLIC_HOST set "TUNNEL_PUBLIC_HOST=%CLOUDFLARE_PUBLIC_HOST%"

if not exist "%BACKEND_DIR%\app\main.py" (
  echo [ERROR] Backend path is invalid:
  echo         %BACKEND_DIR%
  exit /b 1
)

call :resolve_python_cmd
if errorlevel 1 exit /b 1

echo ==================================================
echo Checking backend...
echo ==================================================
call :is_url_ready "%BACKEND_HEALTH_URL%"
if errorlevel 1 (
  echo [INFO] Backend is not running. Starting backend...
  start "Drawing AI Backend" cmd /k "cd /d ""%BACKEND_DIR%"" && %PY_LAUNCH% -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --ws websockets"
  echo [WAIT] Waiting for backend health...
  call :wait_for_url "%BACKEND_HEALTH_URL%" 2 120 "Backend /health"
  if errorlevel 1 exit /b 1
) else (
  echo [INFO] Backend is already running.
)

call :start_cloudflare_tunnel

start "" "https://%TUNNEL_PUBLIC_HOST%/staff"
start "" "https://%TUNNEL_PUBLIC_HOST%/gallery"

echo.
echo [OK] Dashboard ready.
echo Staff:   https://%TUNNEL_PUBLIC_HOST%/staff
echo Gallery: https://%TUNNEL_PUBLIC_HOST%/gallery
echo.
echo [SECURITY] Stable Diffusion remains local-only at http://127.0.0.1:7860
echo            Only backend port 8000 is tunnelled.
exit /b 0

:wait_for_url
set "CHECK_URL=%~1"
set "POLL_SECONDS=%~2"
set "TIMEOUT_SECONDS=%~3"
set "SERVICE_NAME=%~4"

set /a ELAPSED=0
set /a ATTEMPT=0

:wait_loop
set /a ATTEMPT+=1
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"try { ^
  $resp = Invoke-WebRequest -Uri '%CHECK_URL%' -UseBasicParsing -TimeoutSec 5; ^
  if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400) { exit 0 } else { exit 1 } ^
} catch { ^
  exit 1 ^
}"
if not errorlevel 1 (
  echo [OK] %SERVICE_NAME% is ready.
  exit /b 0
)

if !ELAPSED! GEQ %TIMEOUT_SECONDS% (
  echo [ERROR] %SERVICE_NAME% did not become ready in %TIMEOUT_SECONDS%s.
  exit /b 1
)

echo [WAIT] %SERVICE_NAME% not ready yet... !ELAPSED!s (attempt !ATTEMPT!)
timeout /t %POLL_SECONDS% /nobreak >nul
set /a ELAPSED+=%POLL_SECONDS%
goto :wait_loop

:is_url_ready
set "CHECK_URL=%~1"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"try { ^
  $resp = Invoke-WebRequest -Uri '%CHECK_URL%' -UseBasicParsing -TimeoutSec 5; ^
  if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400) { exit 0 } else { exit 1 } ^
} catch { ^
  exit 1 ^
}"
if errorlevel 1 exit /b 1
exit /b 0

:resolve_python_cmd
if exist "%BACKEND_DIR%\.venv\Scripts\python.exe" (
  set "PY_LAUNCH=""%BACKEND_DIR%\.venv\Scripts\python.exe"""
  exit /b 0
)

python -c "import sys" >nul 2>&1
if errorlevel 1 (
  py -3 -c "import sys" >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Python 3 was not found in PATH.
    exit /b 1
  )
  set "PY_LAUNCH=py -3"
  exit /b 0
)
set "PY_LAUNCH=python"
exit /b 0

:cloudflared_installed
call :resolve_cloudflared_cmd
if errorlevel 1 exit /b 1
"%CF_EXE%" --version >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0

:cloudflared_running
tasklist /FI "IMAGENAME eq cloudflared.exe" 2>nul | find /I "cloudflared.exe" >nul
if errorlevel 1 exit /b 1
exit /b 0

:can_use_named_tunnel
if "%TUNNEL_NAME%"=="" exit /b 1
"%CF_EXE%" tunnel info "%TUNNEL_NAME%" >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0

:resolve_cloudflared_cmd
if defined CF_EXE (
  if exist "%CF_EXE%" exit /b 0
)
set "CF_EXE="
if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" set "CF_EXE=%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
if not defined CF_EXE if exist "%ProgramFiles%\cloudflared\cloudflared.exe" set "CF_EXE=%ProgramFiles%\cloudflared\cloudflared.exe"
if not defined CF_EXE if exist "%LocalAppData%\Programs\cloudflared\cloudflared.exe" set "CF_EXE=%LocalAppData%\Programs\cloudflared\cloudflared.exe"
if not defined CF_EXE (
  for /f "delims=" %%I in ('where cloudflared 2^>nul') do (
    if not defined CF_EXE set "CF_EXE=%%I"
  )
)
if not defined CF_EXE exit /b 1
exit /b 0

:start_cloudflare_tunnel
call :cloudflared_installed
if errorlevel 1 (
  echo cloudflared is not installed. Install Cloudflare Tunnel first.
  exit /b 1
)

call :cloudflared_running
if not errorlevel 1 (
  echo [INFO] cloudflared is already running. Skipping tunnel launch.
  exit /b 0
)

echo ==================================================
echo Starting Cloudflare Tunnel...
echo ==================================================
call :can_use_named_tunnel
if not errorlevel 1 (
  echo [INFO] Using named tunnel: %TUNNEL_NAME%
  start "Cloudflare Tunnel" cmd /k ""%CF_EXE%" tunnel --url %TUNNEL_LOCAL_URL% run "%TUNNEL_NAME%""
) else (
  echo [INFO] Named tunnel not available. Using quick tunnel to %TUNNEL_LOCAL_URL%
  start "Cloudflare Tunnel" cmd /k ""%CF_EXE%" tunnel --url %TUNNEL_LOCAL_URL%"
)
exit /b 0
