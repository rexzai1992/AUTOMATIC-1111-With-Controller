@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ==================================================
REM Drawing AI full launcher
REM - Starts Stable Diffusion locally on 127.0.0.1:7860
REM - Starts FastAPI backend on 0.0.0.0:8000
REM - Starts Cloudflare Tunnel that points ONLY to 127.0.0.1:8000
REM ==================================================

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%.") do set "BACKEND_DIR=%%~fI"
for %%I in ("%BACKEND_DIR%\..\stable-diffusion-webui") do set "SD_DIR=%%~fI"

set "SD_LAUNCHER=%SD_DIR%\webui-user.bat"
set "SD_API_URL=http://127.0.0.1:7860/sdapi/v1/sd-models"
set "BACKEND_HEALTH_URL=http://127.0.0.1:8000/health"
set "TUNNEL_LOCAL_URL=http://127.0.0.1:8000"
set "TUNNEL_PUBLIC_HOST=Image-generator-wonderpark.izzul.xyz"
set "TUNNEL_NAME=image-generator-wonderpark"
set "LAN_IP="

REM Optional overrides from environment variables.
if defined CLOUDFLARE_TUNNEL_NAME set "TUNNEL_NAME=%CLOUDFLARE_TUNNEL_NAME%"
if defined CLOUDFLARE_PUBLIC_HOST set "TUNNEL_PUBLIC_HOST=%CLOUDFLARE_PUBLIC_HOST%"
for /f "delims=" %%I in ('powershell -NoProfile -Command "$ips=[System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) ^| Where-Object { $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and $_.ToString() -notlike '127.*' -and $_.ToString() -notlike '169.254.*' }; if ($ips) { $ips[0].ToString() }"') do (
  if not defined LAN_IP set "LAN_IP=%%I"
)

if not exist "%SD_LAUNCHER%" (
  echo [ERROR] Stable Diffusion launcher not found:
  echo         %SD_LAUNCHER%
  exit /b 1
)

if not exist "%BACKEND_DIR%\app\main.py" (
  echo [ERROR] Backend path is invalid:
  echo         %BACKEND_DIR%
  exit /b 1
)

call :resolve_python_cmd
if errorlevel 1 exit /b 1

echo ==================================================
echo Starting Stable Diffusion...
echo ==================================================
call :is_url_ready "%SD_API_URL%"
if errorlevel 1 (
  start "Stable Diffusion WebUI" cmd /k "cd /d ""%SD_DIR%"" && set ""COMMANDLINE_ARGS=--api --opt-sdp-attention"" && call ""%SD_LAUNCHER%"""
  echo [WAIT] Waiting for Stable Diffusion API...
  call :wait_for_url "%SD_API_URL%" 3 240 "Stable Diffusion API"
  if errorlevel 1 exit /b 1
) else (
  echo [INFO] Stable Diffusion API is already running.
)

echo ==================================================
echo Starting Backend...
echo ==================================================
call :is_url_ready "%BACKEND_HEALTH_URL%"
if errorlevel 1 (
  start "Drawing AI Backend" cmd /k "cd /d ""%BACKEND_DIR%"" && %PY_CMD% -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --ws websockets"
  echo [WAIT] Waiting for backend health...
  call :wait_for_url "%BACKEND_HEALTH_URL%" 2 120 "Backend /health"
  if errorlevel 1 exit /b 1
) else (
  echo [INFO] Backend is already running.
)

call :start_cloudflare_tunnel

start "" "http://localhost:8000/staff"
start "" "https://%TUNNEL_PUBLIC_HOST%/staff"

echo.
echo [OK] System ready.
echo Local staff:        http://localhost:8000/staff
echo Local gallery:      http://localhost:8000/gallery
echo Local comfy staff:  http://localhost:8000/comfy/staff
echo Local showcase:     http://localhost:8000/showcase
echo Local wonderpark:   http://localhost:8000/public/wonderpark
if defined LAN_IP (
echo LAN staff:          http://%LAN_IP%:8000/staff
echo LAN gallery:        http://%LAN_IP%:8000/gallery
echo LAN comfy staff:    http://%LAN_IP%:8000/comfy/staff
echo LAN showcase:       http://%LAN_IP%:8000/showcase
echo LAN wonderpark:     http://%LAN_IP%:8000/public/wonderpark
)
echo Public staff:       https://%TUNNEL_PUBLIC_HOST%/staff
echo Public gallery:     https://%TUNNEL_PUBLIC_HOST%/gallery
echo Public comfy staff: https://%TUNNEL_PUBLIC_HOST%/comfy/staff
echo Public showcase:    https://%TUNNEL_PUBLIC_HOST%/showcase
echo Public wonderpark:  https://%TUNNEL_PUBLIC_HOST%/public/wonderpark
echo Public gallery api: https://%TUNNEL_PUBLIC_HOST%/api/gallery
echo.
echo [SECURITY] Stable Diffusion stays private/local at http://127.0.0.1:7860
echo            Only backend port 8000 is exposed via Cloudflare Tunnel.
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
set "PY_CMD=python"
%PY_CMD% -c "import sys" >nul 2>&1
if errorlevel 1 (
  set "PY_CMD=py -3"
  %PY_CMD% -c "import sys" >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Python 3 was not found in PATH.
    exit /b 1
  )
)
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
  echo cloudflared is not installed. Install Cloudflare Tunnel first.
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

echo ==================================================
echo Starting Cloudflare Tunnel...
echo ==================================================

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
