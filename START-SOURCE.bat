@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "ORT_DISABLE_TELEMETRY=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8:backslashreplace"
set "ROOT=%~dp0"
set "PYTHON=%LOCALAPPDATA%\KAINMapleTranslator\BuildVenv0418\Scripts\python.exe"
if not exist "%PYTHON%" goto MISSING_ENV
"%PYTHON%" "%ROOT%launch.py"
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" goto RUN_FAILED
exit /b 0
:RUN_FAILED
echo Program exited with code %CODE%.
pause
exit /b %CODE%
:MISSING_ENV
echo Python environment missing. Run BUILD-WINDOWS.bat first.
pause
exit /b 1
