@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo  ЭКСПЕРИМЕНТ: применить токены R6 Mark II к ДРУГОМУ серийнику
echo  той же модели (--force-model-match). Запускать ТОЛЬКО если
echo  вы осознанно согласны на риск Err 70 / зависания на ~30 сек
echo  на подключённой сейчас камере.
echo ============================================================
echo.
set /p CONFIRM="Подключена именно R6 Mark II (другой экземпляр)? Продолжить? (y/n): "
if /i not "%CONFIRM%"=="y" (
  echo Отменено.
  timeout /t 5
  exit /b 1
)
echo [OpenEOS] Сборка пробника...
"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe" /nologo /platform:x86 /out:eos_probe.exe eos_probe.cs > eos_probe_build.txt 2>&1
if errorlevel 1 (
  echo BUILD FAILED>> eos_probe_build.txt
  type eos_probe_build.txt
  timeout /t 15
  exit /b 1
)
echo [OpenEOS] Шаг 2: чтение счётчиков (ЭКСПЕРИМЕНТ, --force-model-match)...
eos_probe.exe counters "" --force-model-match > eos_probe_experiment_out.txt 2>&1
type eos_probe_experiment_out.txt
echo.
echo Лог со строкой "ЭКСПЕРИМЕНТ:" см. в eos_probe_log.txt
timeout /t 10
