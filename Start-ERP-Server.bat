@echo off
title Aghanya Devanya Hotel ERP Server
echo Starting Aghanya Devanya Hotel ERP Server on port 8000...
cd /d "%~dp0"
python -m http.server 8000
pause
