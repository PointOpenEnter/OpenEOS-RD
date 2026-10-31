@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if exist "%~dp0build-env\Scripts\pythonw.exe" (
    start "" "%~dp0build-env\Scripts\pythonw.exe" "%~dp0openeos.py"
) else (
    start "" pythonw "%~dp0openeos.py"
)
exit /b 0
