@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo           OpenEOS - USB Camera Diagnostic Probe
echo ============================================================
echo.

set "PYTHON_EXE="

if exist "%~dp0build-env\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0build-env\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYTHON_EXE=python"
    ) else (
        where py >nul 2>nul
        if %errorlevel% equ 0 (
            set "PYTHON_EXE=py -3"
        )
    )
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python not found on your system.
    echo Please make sure Python is installed.
    echo.
    pause
    exit /b 1
)

"%PYTHON_EXE%" probe_camera.py

echo.
echo ============================================================
echo Diagnostic finished. Press any key to exit...
pause >nul
