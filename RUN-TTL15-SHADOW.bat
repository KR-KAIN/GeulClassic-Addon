@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "KAIN_TTL15_MODE=shadow"
set "EXE="
for %%F in ("%~dp0dist\*\*.exe") do if not defined EXE if exist "%%~fF" set "EXE=%%~fF"
if not defined EXE (
 echo [ERROR] No Windows EXE. Run BUILD-WINDOWS.bat first.
 pause
 exit /b 1
)
echo TTL experiment mode: shadow
echo %EXE%
start "" /wait "%EXE%"
endlocal
