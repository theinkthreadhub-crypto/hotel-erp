@echo off
title Setu - License Key Generator (Aghanya Devanya Enterprises)
color 0b
cd /d "%~dp0"
echo ===================================================================
echo     SETU LICENSE KEY GENERATOR - Aghanya Devanya Enterprises
echo ===================================================================
echo.
echo Client se uska Install ID lein (Setu ki Sign Up / License screen par likha hota hai).
echo Plans: 1m 2m 3m 6m 1y life demo1h demo24h
echo.
if not exist "setu-license-private.pem" (
  echo [ERROR] setu-license-private.pem is folder mein nahi hai.
  echo Ye file sirf vendor ke paas rehti hai. Uske bina key nahi ban sakti.
  goto end
)
python keygen.py
:end
echo.
echo Press any key to exit...
pause >nul
