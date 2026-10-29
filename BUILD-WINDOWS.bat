@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "ORT_DISABLE_TELEMETRY=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8:backslashreplace"
title KAIN GEULCLASSIC v0.4.54-R14-FIX1 - REAL WINDOWS EXE BUILD
set "ROOT=%~dp0"
set "STARTUP_LOG=%ROOT%BUILD-STARTUP-LOG.txt"
set "BUILD_EXIT=0"
> "%STARTUP_LOG%" echo KAIN GEULCLASSIC v0.4.54-R14-FIX1 REAL EXE BUILDER
>> "%STARTUP_LOG%" echo Started: %DATE% %TIME%
>> "%STARTUP_LOG%" echo File: %~f0
>> "%STARTUP_LOG%" echo Root: %ROOT%
echo.
echo ==============================================================
echo   KAIN GEULCLASSIC v0.4.54-R14-FIX1 - FULL WINDOWS EXE BUILDER
echo   NOT THE ITEM INDEX TOOL - Creates the executable.
echo ==============================================================
echo   Do NOT close this window before BUILD PASS or BUILD FAILED.
echo   STARTUP LOG: "%STARTUP_LOG%"
echo.
if not exist "%ROOT%launch.py" goto MISSING_SOURCE
if not exist "%ROOT%scripts\BUILD-WINDOWS.ps1" goto MISSING_SOURCE
where powershell.exe >nul 2>&1
if errorlevel 1 goto POWERSHELL_MISSING
pushd "%ROOT%"
if errorlevel 1 goto INVALID_PATH
>> "%STARTUP_LOG%" echo STEP: Starting FULL PowerShell build, not ITEM-ID-only.
echo [FULL BUILD] Installing dependencies, building item index,
echo [FULL BUILD] preparing translations, then packaging Windows EXE.
echo [FULL BUILD] Korean names = 0 in legacy ID index is NOT an install error.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\BUILD-WINDOWS.ps1"
set "BUILD_EXIT=%ERRORLEVEL%"
>> "%STARTUP_LOG%" echo PowerShell exit code: %BUILD_EXIT%
popd
if not "%BUILD_EXIT%"=="0" goto BUILD_FAILED
if not exist "%ROOT%BUILD-REPORT.txt" goto FALSE_SUCCESS
findstr /C:"BUILD PASS - EXE and EN/KO models packaged" "%ROOT%BUILD-REPORT.txt" >nul 2>&1
if errorlevel 1 goto FALSE_SUCCESS
>> "%STARTUP_LOG%" echo RESULT: Build PASS verified in BUILD-REPORT.txt.
echo.
echo ==============================================================
echo  BUILD PASS - EXE and offline models verified in build report.
echo  EXE location: dist folder inside this extracted directory.
echo ==============================================================
goto END

:FALSE_SUCCESS
set "BUILD_EXIT=7"
>> "%STARTUP_LOG%" echo ERROR: Success not verified against BUILD-REPORT.txt.
echo ERROR: PowerShell returned 0 but complete EXE build not verified.
goto BUILD_FAILED

:MISSING_SOURCE
set "BUILD_EXIT=2"
>> "%STARTUP_LOG%" echo ERROR: Incomplete ZIP extraction; required source missing.
echo ERROR: Required files missing. Extract WHOLE ZIP to a NEW folder.
goto END

:POWERSHELL_MISSING
set "BUILD_EXIT=3"
>> "%STARTUP_LOG%" echo ERROR: Windows PowerShell not found.
echo ERROR: Windows PowerShell missing.
goto END

:INVALID_PATH
set "BUILD_EXIT=4"
>> "%STARTUP_LOG%" echo ERROR: Cannot open extracted folder.
echo ERROR: Cannot enter folder. Try a local short path.
goto END

:BUILD_FAILED
>> "%STARTUP_LOG%" echo RESULT: BUILD FAILED code %BUILD_EXIT%.
echo.
echo ==============================================================
echo  BUILD FAILED code %BUILD_EXIT%.
echo  Send BUILD-STARTUP-LOG.txt and BUILD-REPORT.txt.
echo  If present, also send MODEL-TRANSLATION-REPORT.txt.
echo ==============================================================

:END
echo.
echo End of build. Press any key to close this window.
pause >nul
exit /b %BUILD_EXIT%
