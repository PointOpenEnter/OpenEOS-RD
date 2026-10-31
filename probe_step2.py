# -*- coding: utf-8 -*-
"""
OpenEOS - PTP Probe Step 2 Launcher
Диагностирует COM-сервер WPD, компилирует 64-битный модуль и запускает безопасный PTP-опрос.
"""

import os
import sys
import subprocess
import winreg

def check_wpd_com():
    clsid = r"CLSID\{0AF10CEC-2ECD-4B92-9581-34F6754D1210}"
    res = {}
    for name, flag in [("64-bit", winreg.KEY_WOW64_64KEY), ("32-bit", winreg.KEY_WOW64_32KEY)]:
        try:
            k = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, clsid, 0, winreg.KEY_READ | flag)
            winreg.CloseKey(k)
            res[name] = True
        except OSError:
            res[name] = False
    return res

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cs_file = os.path.join(base_dir, "ptp_client.cs")
    exe_file = os.path.join(base_dir, "ptp_client.exe")

    print("=" * 65)
    print("      OpenEOS: PTP DeviceInfo & Properties Probe (Шаг 2)")
    print("=" * 65)
    print()

    # 1. Проверка регистрации COM класса в реестре Windows
    print("[1/3] Проверка системного WPD COM-сервера Windows...")
    com_status = check_wpd_com()
    print(f"      64-bit системный реестр: {'OK (Зарегистрирован)' if com_status['64-bit'] else 'Отсутствует'}")
    print(f"      32-bit подсистема WOW64: {'OK (Зарегистрирован)' if com_status['32-bit'] else 'Отсутствует'}")

    dll_64 = r"C:\Windows\System32\PortableDeviceApi.dll"
    if not com_status["64-bit"]:
        if os.path.isfile(dll_64):
            print(f"[*] Регистрация {dll_64} в системе...")
            subprocess.run(["regsvr32", "/s", dll_64])
            com_status = check_wpd_com()
            print(f"      Повторный статус 64-bit: {'OK' if com_status['64-bit'] else 'Не удалось зарегистрировать'}")
        else:
            print(f"[-] Файл {dll_64} не найден в системе (Media Feature Pack не установлен).")

    print()

    # 2. Поиск системного 64-битного компилятора C#
    print("[2/3] Компиляция нативного 64-битного PTP-модуля (x64)...")
    csc_exe = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    if not os.path.isfile(csc_exe):
        csc_exe = r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"

    if not os.path.isfile(csc_exe):
        print("[-] Системный .NET компилятор csc.exe не найден.")
        return

    # Удаляем старый exe, если был собран как AnyCPU / 32-bit
    if os.path.isfile(exe_file):
        try:
            os.remove(exe_file)
        except Exception:
            pass

    compile_cmd = [
        csc_exe,
        "/nologo",
        "/optimize+",
        "/platform:x64",  # Строго 64-битная сборка для совпадения с 64-битным Windows WPD!
        "/target:exe",
        f"/out:{exe_file}",
        cs_file
    ]

    res = subprocess.run(compile_cmd, capture_output=True, text=True, errors='replace')
    if res.returncode != 0:
        print("[-] Ошибка компиляции модуля:")
        print(res.stdout)
        print(res.stderr)
        return
    print("[+] Модуль x64 успешно собран.")
    print()

    # 3. Запуск x64 ptp_client.exe
    print("[3/3] Запуск безопасного PTP-опроса камеры...")
    print("-" * 65)
    try:
        subprocess.run([exe_file], text=True, errors='replace')
    except Exception as e:
        print(f"[-] Ошибка запуска {exe_file}: {e}")

if __name__ == "__main__":
    main()
