@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "GLYPH_DIR=%LOCALAPPDATA%\KAINMapleTranslator\glyph-dictionaries"
echo This removes only learned glyph dictionaries; OCR models are kept.
echo Close GeulClassic Addon before reset.
if not exist "%GLYPH_DIR%" goto NO_FILES
choice /C YN /N /M "Reset learned glyph dictionaries? (Y/N) "
if errorlevel 2 goto END
del /F /Q "%GLYPH_DIR%\glyph-*.json"
echo Glyph dictionary reset done. Restart GeulClassic Addon.
goto END
:NO_FILES
echo No learned glyph dictionary files found.
:END
pause
