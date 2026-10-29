@echo off
rem Make installer\Output\GeulClassic-Addon-Setup-v<version>.exe from the built
rem app in dist\ (run BUILD-WINDOWS.bat first).
rem Needs Inno Setup 6 (free): winget install JRSoftware.InnoSetup
setlocal
cd /d "%~dp0"
set "ISCC="
for %%P in ("%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe") do (
  if exist %%P set "ISCC=%%~P"
)
if not defined ISCC (
  echo Inno Setup 6 was not found. Install it with: winget install JRSoftware.InnoSetup
  exit /b 1
)
if not exist "..\dist" (
  echo dist is missing. Run BUILD-WINDOWS.bat first.
  exit /b 1
)
"%ISCC%" "GeulClassic-Addon.iss" %*
exit /b %ERRORLEVEL%
