@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [OpenEOS] Сборка пробника...
"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe" /nologo /platform:x86 /out:eos_probe.exe eos_probe.cs > eos_probe_build.txt 2>&1
if errorlevel 1 (
  echo BUILD FAILED>> eos_probe_build.txt
  type eos_probe_build.txt
  timeout /t 15
  exit /b 1
)
echo [OpenEOS] Шаг 1: только чтение DeviceInfo...
eos_probe.exe info > eos_probe_out.txt 2>&1
type eos_probe_out.txt
timeout /t 8
