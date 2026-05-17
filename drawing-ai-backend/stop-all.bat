@echo off
setlocal EnableExtensions

REM ==================================================
REM Stop launcher services by port
REM - Stable Diffusion API (7860)
REM - Drawing AI Backend (8000)
REM - Cloudflare Tunnel process (cloudflared.exe)
REM ==================================================

echo ==================================================
echo Stopping Drawing AI System...
echo ==================================================

echo.
echo [INFO] Checking port 7860 for Stable Diffusion...
set "FOUND_7860=0"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":7860 .*LISTENING"') do (
    set "FOUND_7860=1"
    echo [INFO] Stopping Stable Diffusion process PID %%P on port 7860...
    taskkill /PID %%P /T >nul 2>&1
    if errorlevel 1 taskkill /PID %%P /T /F >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Could not stop PID %%P for Stable Diffusion.
    ) else (
        echo [OK] Stopped Stable Diffusion ^(PID %%P^).
    )
)
if "%FOUND_7860%"=="0" echo [INFO] Stable Diffusion not running on port 7860.

echo.
echo [INFO] Checking port 8000 for Controller Backend...
set "FOUND_8000=0"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
    set "FOUND_8000=1"
    echo [INFO] Stopping Controller Backend process PID %%P on port 8000...
    taskkill /PID %%P /T >nul 2>&1
    if errorlevel 1 taskkill /PID %%P /T /F >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Could not stop PID %%P for Controller Backend.
    ) else (
        echo [OK] Stopped Controller Backend ^(PID %%P^).
    )
)
if "%FOUND_8000%"=="0" echo [INFO] Controller Backend not running on port 8000.

echo.
echo [INFO] Checking Cloudflare Tunnel process...
tasklist /FI "IMAGENAME eq cloudflared.exe" 2>nul | find /I "cloudflared.exe" >nul
if errorlevel 1 (
    echo [INFO] Cloudflare Tunnel is not running.
) else (
    echo [INFO] Stopping cloudflared.exe...
    taskkill /IM cloudflared.exe /T >nul 2>&1
    if errorlevel 1 taskkill /IM cloudflared.exe /T /F >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Could not stop cloudflared.exe.
    ) else (
        echo [OK] Stopped Cloudflare Tunnel.
    )
)

echo.
echo Stop sequence completed.
exit /b 0
