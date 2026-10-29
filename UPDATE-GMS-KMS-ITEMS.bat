@echo off
setlocal EnableExtensions DisableDelayedExpansion
title KAIN Maple Translator - GMS to KMS item name sync
set "ROOT=%~dp0"
set "CODE=1"
set "PY=%LOCALAPPDATA%\KAINMapleTranslator\BuildVenv0418\Scripts\python.exe"
if exist "%PY%" goto RUN
set "PY=%LOCALAPPDATA%\KAINMapleTranslator\BuildPython312\python.exe"
if exist "%PY%" goto RUN
set "PY="
where python.exe >nul 2>&1
if not errorlevel 1 set "PY=python.exe"
if defined PY goto RUN
echo Python not found. Run BUILD-WINDOWS.bat first or install Python 3.12.
goto ERROR
:RUN
cd /d "%ROOT%"
echo.
echo KAIN Maple Translator - One-time GMS 62 / KMS 65 then KMS 284 ID sync
echo This contacts maplestory.io. No Planet Helper scraping.
echo Previous item DB will be kept intact if network or matching fails.
echo.
"%PY%" "%ROOT%scripts\sync_gms_kms_items.py" > "%ROOT%ITEM-SYNC-REPORT.txt" 2>&1
set "CODE=%ERRORLEVEL%"
type "%ROOT%ITEM-SYNC-REPORT.txt"
if not "%CODE%"=="0" goto ERROR
echo.
echo ITEM-SYNC PASS. New verified ID pairs load on next app launch / next chat scan.
goto END
:ERROR
echo.
echo ITEM-SYNC FAILED. Check ITEM-SYNC-REPORT.txt. Current DB preserved.
:END
echo.
echo Press any key to close.
pause >nul
exit /b %CODE%
