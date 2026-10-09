@echo off
cd /d "%~dp0"
node -v
if errorlevel 1 (
  echo Pehle Node.js install karein: https://nodejs.org
  pause
  exit /b 1
)
if not exist public_key.pem node keygen.js init
call npm install --no-audit --no-fund
call npm run build
echo.
echo dist folder mein LibraryERP.exe aur LibraryKeygen.exe ban gaye.
pause
