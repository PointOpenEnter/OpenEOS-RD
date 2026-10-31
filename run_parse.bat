@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo           OpenEOS - PCAPNG PTP Traffic Analyzer
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
    pause
    exit /b 1
)

"%PYTHON_EXE%" parse_pcap.py

echo.
echo ============================================================
echo Analysis finished. Press any key to exit...
pause >nul
