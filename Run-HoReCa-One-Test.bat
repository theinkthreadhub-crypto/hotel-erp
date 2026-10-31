@echo off
setlocal
title HoReCa One Preview - Safe Isolated Test
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Install Python 3.12 or use the Preview EXE artifact.
  pause
  exit /b 1
)
set "PREVIEW_DATA=%~dp0horeca-preview-data"
if not exist "%PREVIEW_DATA%" mkdir "%PREVIEW_DATA%"
echo HoReCa One test data: "%PREVIEW_DATA%"
echo This preview does not use your installed ERP database folder.
start "HoReCa One Preview Server" cmd /k python app_main.py --server --port 8161 --data "%PREVIEW_DATA%"
timeout /t 4 /nobreak >nul
start "" "http://127.0.0.1:8161/hotel_erp.html"
echo.
echo Opened HoReCa One at http://127.0.0.1:8161/hotel_erp.html
echo Use TEST data only. Stop the preview server window when finished.
pause
