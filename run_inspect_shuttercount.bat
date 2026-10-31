@echo off
set "PROJECT=%USERPROFILE%\OpenEOS"
set "PYTHON=%PROJECT%\build-env\Scripts\python.exe"

echo ============================================================
echo Inspecting https://shuttercount.org/
echo ============================================================
"%PYTHON%" "%PROJECT%\inspect_shuttercount.py"
"%PYTHON%" "%PROJECT%\inspect_scripts.py"
"%PYTHON%" "%PROJECT%\extract_canon_info.py"
echo.
echo Inspection complete! Check shuttercount_analysis.txt and shuttercount_canon_report.txt!
pause
