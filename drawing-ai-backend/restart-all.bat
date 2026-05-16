@echo off
setlocal EnableExtensions

REM ==================================================
REM Restart launcher services
REM ==================================================

echo ==================================================
echo Restarting Drawing AI System...
echo ==================================================

REM Step 1: Stop everything
call "%~dp0stop-all.bat"

REM Step 2: Wait 3 seconds
echo Waiting 3 seconds before restart...
timeout /t 3 /nobreak >nul

REM Step 3: Start everything
call "%~dp0start-all.bat"
