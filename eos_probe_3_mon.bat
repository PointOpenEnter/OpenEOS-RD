@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [OpenEOS] Сборка пробника (канал MPU)...
"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe" /nologo /platform:x86 /out:eos_probe.exe eos_probe.cs > eos_probe_build.txt 2>&1
if errorlevel 1 (
  type eos_probe_build.txt
  echo BUILD FAILED
  timeout /t 20
  exit /b 1
)
echo [OpenEOS] Проба чтения памяти MPU (MonRead, без ключа)...
eos_probe.exe mon > eos_probe_mon_out.txt 2>&1
type eos_probe_mon_out.txt
timeout /t 12
