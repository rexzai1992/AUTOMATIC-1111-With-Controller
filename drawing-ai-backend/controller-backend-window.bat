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
set "TUNNEL_LOCAL_URL=http://127.0.0.1:8000"
set "TUNNEL_PUBLIC_HOST=Image-generator-wonderpark.izzul.xyz"
set "TUNNEL_NAME=image-generator-wonderpark"

REM Optional overrides from environment variables.
if defined CLOUDFLARE_TUNNEL_NAME set "TUNNEL_NAME=%CLOUDFLARE_TUNNEL_NAME%"
if defined CLOUDFLARE_PUBLIC_HOST set "TUNNEL_PUBLIC_HOST=%CLOUDFLARE_PUBLIC_HOST%"

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

call :start_cloudflare_tunnel
if not errorlevel 1 (
    echo [INFO] Public URL: https://%TUNNEL_PUBLIC_HOST%/staff
)

%PY_CMD% -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --ws websockets

echo.
echo [INFO] Backend process exited.
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

:named_tunnel_active
if "%TUNNEL_NAME%"=="" exit /b 1
for /f "delims=" %%I in ('"%CF_EXE%" tunnel info "%TUNNEL_NAME%" 2^>nul ^| find /I "does not have any active connection."') do (
  exit /b 1
)
"%CF_EXE%" tunnel info "%TUNNEL_NAME%" 2>nul | find /I "CONNECTOR ID" >nul
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
  echo [WARN] cloudflared is not installed. Skipping tunnel start.
  exit /b 1
)

call :can_use_named_tunnel
if not errorlevel 1 (
  call :named_tunnel_active
  if not errorlevel 1 (
    echo [INFO] Named tunnel "%TUNNEL_NAME%" already has active connection.
    exit /b 0
  )
)

call :cloudflared_running
if not errorlevel 1 (
  echo [INFO] cloudflared process is running but tunnel is not active. Restarting cloudflared...
  taskkill /IM cloudflared.exe /T /F >nul 2>&1
  timeout /t 1 /nobreak >nul
)

echo [INFO] Starting Cloudflare Tunnel...
call :can_use_named_tunnel
if not errorlevel 1 (
  echo [INFO] Using named tunnel: %TUNNEL_NAME%
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%CF_EXE%' -ArgumentList @('tunnel','--url','%TUNNEL_LOCAL_URL%','run','%TUNNEL_NAME%') -WindowStyle Hidden"
) else (
  echo [INFO] Named tunnel not available. Using quick tunnel to %TUNNEL_LOCAL_URL%
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%CF_EXE%' -ArgumentList @('tunnel','--url','%TUNNEL_LOCAL_URL%') -WindowStyle Hidden"
)
timeout /t 4 /nobreak >nul
call :can_use_named_tunnel
if not errorlevel 1 (
  call :named_tunnel_active
  if not errorlevel 1 (
    echo [OK] Named tunnel is connected.
    exit /b 0
  )
  echo [WARN] Tunnel process started, but named tunnel has no active connector yet.
)
exit /b 0
