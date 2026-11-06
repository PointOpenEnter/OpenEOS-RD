@echo off
chcp 65001 >nul
title OpenEOS Community Edition
cd /d "%~dp0"
python openeos.py
if errorlevel 1 (
    echo.
    echo Ошибка запуска. Убедитесь, что установлен Python 3.
    pause
)
