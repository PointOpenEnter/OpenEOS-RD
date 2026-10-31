@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "VENV_PYTHON=%~dp0build-env\Scripts\python.exe"

if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" "%~dp0setup_git.py"
) else (
    python "%~dp0setup_git.py"
)

exit /b %ERRORLEVEL%
