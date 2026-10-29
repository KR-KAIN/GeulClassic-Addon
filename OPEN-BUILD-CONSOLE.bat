@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "ROOT=%~dp0"
if not exist "%ROOT%BUILD-WINDOWS.bat" goto ERROR
cmd.exe /D /K ""%ROOT%BUILD-WINDOWS.bat""
exit /b %ERRORLEVEL%
:ERROR
echo The real EXE builder is missing. Extract the whole ZIP.
pause
exit /b 2
