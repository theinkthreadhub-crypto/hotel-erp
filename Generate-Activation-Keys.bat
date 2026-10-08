@echo off
title Aghanya Devanya Enterprises - Key Generator Vault
color 0b
echo ===================================================================
echo     AGHANYA DEVANYA ENTERPRISES - MULTI-TIER ACTIVATION SYSTEM
echo ===================================================================
echo.
echo Choose an option:
echo   [1] Generate 1-Month Keys (30 Days)
echo   [2] Generate 2-Months Keys (60 Days)
echo   [3] Generate 3-Months Keys (Quarterly - 90 Days)
echo   [4] Generate 6-Months Keys (Half-Yearly - 180 Days)
echo   [5] Generate 1-Year Keys (Annual - 365 Days)
echo   [6] Generate Individual Lifetime Keys
echo   [7] View Universal Common Lifetime Key (for All Hotels)
echo   [8] Open Activation_Keys Folder (Excel / CSV Spreadsheet)
echo   [9] Sync Keys from Excel into ERP Software
echo.
set /p opt=Enter option (1-9, Default 1): 
if "%opt%"=="" set opt=1

if "%opt%"=="8" (
    start "" "Activation_Keys"
    start "" "Activation_Keys\Aghanya_Devanya_Activation_Keys.xlsx"
    goto end
)

if "%opt%"=="9" (
    python sync_keys.py
    goto end
)

python keygen.py %opt%

:end
echo.
echo Press any key to exit...
pause >nul
