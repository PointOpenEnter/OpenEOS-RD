@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "PROJECT=%USERPROFILE%\OpenEOS"
set "PYTHON=%PROJECT%\build-env\Scripts\python.exe"
set "EXIFTOOL_DIR=C:\Tools\ExifTool"
set "SOURCE=%PROJECT%\openeos.py"
set "PORTABLE_SOURCE=%PROJECT%\openeos_portable.py"
set "OUTPUT=%PROJECT%\dist\OpenEOS.exe"

 echo.
echo ============================================================
echo                 OpenEOS - Windows x64 build
echo ============================================================
echo.

if not exist "%PYTHON%" (
    echo ERROR: Build Python environment was not found:
    echo %PYTHON%
    echo.
    echo Please create build-env and install PyInstaller and tkinterdnd2 first.
    goto :failed
)

if not exist "%SOURCE%" (
    echo ERROR: OpenEOS source file was not found:
    echo %SOURCE%
    goto :failed
)

if not exist "%EXIFTOOL_DIR%\exiftool.exe" (
    echo ERROR: exiftool.exe was not found in %EXIFTOOL_DIR%
    goto :failed
)

if not exist "%EXIFTOOL_DIR%\exiftool_files" (
    echo ERROR: exiftool_files folder was not found in %EXIFTOOL_DIR%
    goto :failed
)

echo [1/4] Checking build tools...
"%PYTHON%" -c "import PyInstaller, tkinterdnd2; print('PyInstaller', PyInstaller.__version__); print('TkinterDnD2 import OK')"
if errorlevel 1 goto :failed

echo.
echo [2/4] Preparing portable copy and camera icon...
"%PYTHON%" "%PROJECT%\create_icons.py"
if errorlevel 1 goto :failed
"%PYTHON%" "%PROJECT%\prepare_for_build.py" "%SOURCE%" "%PORTABLE_SOURCE%"
if errorlevel 1 goto :failed

echo.
echo [3/4] Building one-file Windows application...
"%PYTHON%" -m PyInstaller ^
 --noconfirm ^
 --clean ^
 --onefile ^
 --windowed ^
 --noupx ^
 --name OpenEOS ^
 --icon "%PROJECT%\app_icon.ico" ^
 --distpath "%PROJECT%\dist" ^
 --workpath "%PROJECT%\build" ^
 --specpath "%PROJECT%\build_spec" ^
 --add-binary "%EXIFTOOL_DIR%\exiftool.exe;." ^
 --add-data "%EXIFTOOL_DIR%\exiftool_files;exiftool_files" ^
 --add-data "%PROJECT%\app_icon.png;." ^
 --add-data "%PROJECT%\app_icon.ico;." ^
 --collect-all tkinterdnd2 ^
 --hidden-import tkinterdnd2 ^
 "%PORTABLE_SOURCE%"
if errorlevel 1 goto :failed

echo.
echo [4/4] Checking output...
if not exist "%OUTPUT%" (
    echo ERROR: PyInstaller finished but OpenEOS.exe was not found.
    goto :failed
)

for %%F in ("%OUTPUT%") do set "EXE_SIZE=%%~zF"
echo.
echo ============================================================
echo BUILD SUCCESSFUL
echo ============================================================
echo File: %OUTPUT%
echo Size: %EXE_SIZE% bytes
echo.
echo The original openeos.py was not modified.
echo The distributable is this one file: dist\OpenEOS.exe
echo.
echo IMPORTANT: Test this EXE on this PC before sharing it.
echo Then test on a Windows 10/11 x64 PC without Python/ExifTool.
echo.
start "" "%PROJECT%\dist"
pause
exit /b 0

:failed
echo.
echo BUILD FAILED. No successful EXE is being claimed.
echo Check the error above and send the complete output for diagnosis.
echo.
pause
exit /b 1
