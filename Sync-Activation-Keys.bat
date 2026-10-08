@echo off
title Aghanya Devanya Enterprises - Sync Keys from Excel
color 0a
echo ===================================================================
echo     AGHANYA DEVANYA ENTERPRISES - KEY SYNC FROM EXCEL / CSV
echo ===================================================================
echo.
echo Reading Activation_Keys\Aghanya_Devanya_Activation_Keys.xlsx / .csv ...
echo.

python sync_keys.py

echo.
echo [INFO] Nayi keys software mein sync ho gayi hain.
echo Agar aap chahein toh nayi .EXE compile karne ke liye Build-New-EXE.bat chala sakte hain.
echo.
echo Press any key to exit...
pause >nul
