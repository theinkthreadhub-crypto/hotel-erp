@echo off
title Aghanya Devanya - Setu Hotel ERP Launcher
color 0a

echo ======================================================================
echo       AGHANYA DEVANYA ENTERPRISES - HOTEL ERP INSTANT LAUNCHER
echo ======================================================================
echo.

cd /d "%~dp0"

if exist "Aghanya-Devanya-Hotel-ERP.exe" (
    echo [1/2] Aghanya-Devanya-Hotel-ERP.exe mil gayi! Starting application...
    start "" "Aghanya-Devanya-Hotel-ERP.exe"
    goto finish
)

if exist "dist\Aghanya-Devanya-Hotel-ERP.exe" (
    echo [1/2] dist\Aghanya-Devanya-Hotel-ERP.exe mil gayi! Starting application...
    start "" "dist\Aghanya-Devanya-Hotel-ERP.exe"
    goto finish
)

echo [1/2] Starting Setu Hotel ERP using Python runtime...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Na toh Aghanya-Devanya-Hotel-ERP.exe mili aur na hi Python install hai.
    echo Kripya Install-Aghanya-Devanya-ERP-Setup.bat chalayein ya Python install karein.
    pause
    exit /b 1
)

start "" python app_main.py
goto finish

:finish
echo [2/2] Software chalu ho gaya hai!
echo Browser URL: http://127.0.0.1:8000/hotel_erp.html
echo.
echo ======================================================================
echo  Setu Hotel ERP chal raha hai. Is window ko band kar sakte hain.
echo ======================================================================
timeout /t 5 >nul
exit /b 0

