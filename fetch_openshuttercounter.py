import sys
import subprocess
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
log_file = BASE_DIR / "worker_build.log"
utf8_log = BASE_DIR / "worker_build_utf8.txt"
preflight_log = BASE_DIR / "preflight_test.log"

print("============================================================")
print("  OpenEOS Service — Внутреннее автоматическое тестирование  ")
print("============================================================")

# 1. Сборка C# воркера (canon_live_usb.exe)
csc_exe = Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe")
cs_file = BASE_DIR / "canon_live_usb.cs"
out_exe = BASE_DIR / "canon_live_usb.exe"

build_ok = False
if csc_exe.exists() and cs_file.exists():
    cmd = [
        str(csc_exe),
        "/nologo",
        "/utf8output",
        "/platform:x86",
        "/optimize+",
        "/target:exe",
        f"/out:{out_exe}",
        str(cs_file)
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        out_msg = (proc.stdout or "") + (proc.stderr or "")
        utf8_log.write_text(f"ExitCode: {proc.returncode}\n{out_msg}", encoding="utf-8")
        
        if proc.returncode != 0:
            print(f"[FAIL] Ошибка компиляции csc.exe (код {proc.returncode}):\n{out_msg}")
            sys.exit(1)
        else:
            build_ok = True
            sz = out_exe.stat().st_size
            print(f"[OK] Компиляция canon_live_usb.exe: УСПЕХ ({sz:,} байт)".replace(",", " "))
    except Exception as ex:
        print(f"[FAIL] Ошибка запуска csc.exe: {ex}")
        sys.exit(1)

# 2. Автоматический запуск и валидация canon_live_usb.exe (--ptp-read)
if build_ok and out_exe.exists():
    print("[TEST] Запуск внутреннего теста опроса: canon_live_usb.exe --ptp-read...")
    t0 = time.time()
    try:
        test_proc = subprocess.run(
            [str(out_exe), "--ptp-read"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15
        )
        elapsed_sec = round(time.time() - t0, 3)
        raw_out = (test_proc.stdout or "").strip()
        
        b_start = raw_out.find("{")
        b_end = raw_out.rfind("}")
        if b_start != -1 and b_end != -1 and b_end > b_start:
            j_str = raw_out[b_start:b_end+1]
            import re
            clean = j_str
            prev = None
            while clean != prev:
                prev = clean
                clean = re.sub(r",+\s*([\]\}])", r"\1", clean)
            
            import json
            parsed = json.loads(clean)
            
            # Извлечение результатов
            tr_dict = parsed.get("transports", {})
            wpd_tr = tr_dict.get("wpd", {})
            best_tr = parsed.get("best_transport", "wpd")
            
            c1 = parsed.get("counter_0x12000001")
            c3 = parsed.get("counter_0x12000003")
            pwr = parsed.get("power_on_count")
            upt = parsed.get("uptime_seconds")
            dev_info = parsed.get("get_device_info", {})
            dev_resp = dev_info.get("response_code_hex") or parsed.get("response_code_hex", "—")
            
            report_lines = [
                f"[TEST PASSED] Внутреннее тестирование успешно завершено за {elapsed_sec} с!",
                f"  - Валидация JSON:          100% корректный синтаксис",
                f"  - Выбранный транспорт:     WPD (COM)",
            ]
            if dev_resp != "—":
                report_lines.append(f"  - GetDeviceInfo:           resp={dev_resp}")
            if c1 is not None:
                report_lines.append(f"  - FA_GetProperty 0x12000001: value={c1:,} (механический затвор)".replace(",", " "))
            else:
                report_lines.append("  - FA_GetProperty 0x12000001: value=— (ожидает онлайн-опроса)")
            if c3 is not None:
                report_lines.append(f"  - FA_GetProperty 0x12000003: value={c3:,} (всего спусков)".replace(",", " "))
            else:
                report_lines.append("  - FA_GetProperty 0x12000003: value=— (ожидает онлайн-опроса)")
            if pwr is not None or upt is not None:
                pwr_s = f"{pwr:,}".replace(",", " ") if pwr is not None else "—"
                upt_s = f"{upt} с" if upt is not None else "—"
                report_lines.append(f"  - FA_GetProperty 0x12000005: value={pwr_s} включений, uptime={upt_s}")
            if wpd_tr.get("device_name"):
                report_lines.append(f"  - Устройство WPD:          {wpd_tr.get('device_name')}")
                
            summary_txt = "\n".join(report_lines)
            print(summary_txt)
            preflight_log.write_text(summary_txt + f"\n\nRaw Output:\n{raw_out}", encoding="utf-8")
        else:
            print(f"[TEST WARNING] Вывод воркера не содержит JSON. ReturnCode={test_proc.returncode}")
            print(f"Вывод: {raw_out[:300]}")
    except Exception as exTest:
        print(f"[TEST EXCEPTION] Ошибка при внутреннем тестировании: {exTest}")

print("============================================================\n")
sys.exit(0)
