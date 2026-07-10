@echo off
setlocal
title Drawing AI Backend Launcher

cd /d "%~dp0"

set "TUNNEL_LOCAL_URL=http://127.0.0.1:8000"
set "TUNNEL_PUBLIC_HOST=Image-generator-wonderpark.izzul.xyz"
set "TUNNEL_NAME=image-generator-wonderpark"
set "LAN_IP="
if defined CLOUDFLARE_TUNNEL_NAME set "TUNNEL_NAME=%CLOUDFLARE_TUNNEL_NAME%"
if defined CLOUDFLARE_PUBLIC_HOST set "TUNNEL_PUBLIC_HOST=%CLOUDFLARE_PUBLIC_HOST%"
for /f "delims=" %%I in ('powershell -NoProfile -Command "$ips=[System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) ^| Where-Object { $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and $_.ToString() -notlike '127.*' -and $_.ToString() -notlike '169.254.*' }; if ($ips) { $ips[0].ToString() }"') do (
  if not defined LAN_IP set "LAN_IP=%%I"
)

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

echo [Run] Starting backend on http://0.0.0.0:8000
echo [Info] Local links:
echo        http://127.0.0.1:8000/splash
echo        http://127.0.0.1:8000/staff
echo        http://127.0.0.1:8000/gallery
echo        http://127.0.0.1:8000/comfy/staff
echo        http://127.0.0.1:8000/showcase
echo        http://127.0.0.1:8000/public/wonderpark
echo        http://127.0.0.1:8000/publicgallery
if defined LAN_IP (
  echo [Info] LAN links:
  echo        http://%LAN_IP%:8000/splash
  echo        http://%LAN_IP%:8000/staff
  echo        http://%LAN_IP%:8000/gallery
  echo        http://%LAN_IP%:8000/comfy/staff
  echo        http://%LAN_IP%:8000/showcase
  echo        http://%LAN_IP%:8000/public/wonderpark
  echo        http://%LAN_IP%:8000/publicgallery
)
call :start_cloudflare_tunnel
if not errorlevel 1 (
  echo [Info] Public links:
  echo        https://%TUNNEL_PUBLIC_HOST%/splash
  echo        https://%TUNNEL_PUBLIC_HOST%/staff
  echo        https://%TUNNEL_PUBLIC_HOST%/gallery
  echo        https://%TUNNEL_PUBLIC_HOST%/comfy/staff
  echo        https://%TUNNEL_PUBLIC_HOST%/showcase
  echo        https://%TUNNEL_PUBLIC_HOST%/public/wonderpark
  echo        https://%TUNNEL_PUBLIC_HOST%/publicgallery
)
start "" "http://127.0.0.1:8000/staff"
start "" "http://127.0.0.1:8000/gallery"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --ws websockets

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
  echo [WARN] cloudflared is not installed. Tunnel is skipped.
  echo [WARN] Install Cloudflare Tunnel, then rerun this launcher.
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
