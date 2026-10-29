@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
set "OUT=%~dp0OCR-STAGE-TRACE-EXPORT.jsonl"
set "NEW_TRACE=%LOCALAPPDATA%\KAINMapleTranslator\diagnostics\OCR-STAGE-TRACE-EXPORT.jsonl"
set "OLD_TRACE=%LOCALAPPDATA%\KAINMapleTranslator\diagnostics\OCR-STAGE-TRACE.jsonl"
set "TRACE="
if exist "%NEW_TRACE%" set "TRACE=%NEW_TRACE%"
if not defined TRACE if exist "%OLD_TRACE%" set "TRACE=%OLD_TRACE%"
if not defined TRACE goto NO_TRACE
for %%A in ("%TRACE%") do if %%~zA EQU 0 goto EMPTY_TRACE
copy /B /Y "%TRACE%" "%OUT%" >nul
if errorlevel 1 goto COPY_FAILED

echo.
echo [OK] OCR trace copied to:
echo "%OUT%"
echo.
set "PY=%LOCALAPPDATA%\KAINMapleTranslator\BuildPython312\python.exe"
if exist "%PY%" goto SUMMARIZE
where py.exe >nul 2>&1
if not errorlevel 1 (
  py -3 "%~dp0scripts\summarize_ocr_trace.py" "%OUT%" "%~dp0OCR-STAGE-SUMMARY.txt"
  goto END
)
where python.exe >nul 2>&1
if not errorlevel 1 (
  python.exe "%~dp0scripts\summarize_ocr_trace.py" "%OUT%" "%~dp0OCR-STAGE-SUMMARY.txt"
  goto END
)
echo Python not found. JSONL export is ready; optional summary skipped.
goto END

:SUMMARIZE
"%PY%" "%~dp0scripts\summarize_ocr_trace.py" "%OUT%" "%~dp0OCR-STAGE-SUMMARY.txt"
if errorlevel 1 echo Summary failed, but JSONL export is available.
goto END

:NO_TRACE
echo [NOT FOUND] No OCR trace has been created on this Windows account.
echo Start the newly built PROFILE EXPORT FIX app and enable chat OCR.
echo New expected trace path: "%NEW_TRACE%"
echo Older version trace path: "%OLD_TRACE%"
goto ERROR

:EMPTY_TRACE
echo [EMPTY] The trace exists, but contains no data yet.
echo Enable chat OCR and allow it to run, then export again.
goto ERROR

:COPY_FAILED
echo [FAILED] Could not copy trace. Try closing the app and retry.
goto ERROR

:END
echo.
echo JSONL contains measurements only, not text or screenshots.
echo If summary says 0 frames, the engine did not process any chat frames yet.
pause
exit /b 0

:ERROR
echo.
pause
exit /b 1
