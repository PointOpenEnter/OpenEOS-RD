@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if exist "%~dp0build-env\Scripts\python.exe" (
    "%~dp0build-env\Scripts\python.exe" "%~dp0setup_git.py"
) else (
    python "%~dp0setup_git.py"
)

exit /b %ERRORLEVEL%
