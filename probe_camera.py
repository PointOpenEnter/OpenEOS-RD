# -*- coding: utf-8 -*-
"""
OpenEOS - USB Camera Diagnostic Probe (Safe Read-Only Detection)
Проверяет подключение камеры Canon по USB через системный инвентарь Windows PnP/WMI.
Не отправляет никаких сервисных или модифицирующих команд на камеру.
"""

import sys
import os
import subprocess
import json

def get_canon_pnp_devices():
    """
    Опрашивает PnP устройства Windows через PowerShell на предмет устройств Canon (VID 04A9).
    """
    ps_cmd = (
        'Get-PnpDevice | '
        'Where-Object { $_.InstanceId -like "*VID_04A9*" -or $_.FriendlyName -like "*Canon*" } | '
        'Select-Object FriendlyName, InstanceId, Class, Status, Problem | '
        'ConvertTo-Json'
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        output = res.stdout.strip()
        if not output:
            return []
        data = json.loads(output)
        if isinstance(data, dict):
            return [data]
        elif isinstance(data, list):
            return data
        return []
    except Exception as e:
        return [{"error": str(e)}]

def get_wpd_devices():
    """
    Проверяет устройства в классе WPD (Windows Portable Devices).
    """
    ps_cmd = (
        'Get-PnpDevice -Class "WPD" | '
        'Select-Object FriendlyName, InstanceId, Status | '
        'ConvertTo-Json'
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        output = res.stdout.strip()
        if not output:
            return []
        data = json.loads(output)
        if isinstance(data, dict):
            return [data]
        elif isinstance(data, list):
            return data
        return []
    except Exception as e:
        return [{"error": str(e)}]

def check_conflicting_processes():
    """
    Проверяет, запущены ли программы, которые могут захватывать USB-соединение (EOS Utility и т.п.).
    """
    conflicts = ["EOS Utility", "EOS Web Service", "EOSUPNPSV", "Lightroom"]
    running = []
    ps_cmd = 'Get-Process | Select-Object -ExpandProperty ProcessName'
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        procs = res.stdout.splitlines()
        for p in procs:
            p_clean = p.strip()
            for c in conflicts:
                if c.lower() in p_clean.lower():
                    running.append(p_clean)
    except Exception:
        pass
    return list(set(running))

def main():
    report_lines = []
    def log(msg=""):
        print(msg)
        report_lines.append(msg)

    log("=" * 65)
    log("       OpenEOS: Диагностика USB-подключения Canon (Шаг 1)")
    log("=" * 65)
    log("Режим: БЕЗОПАСНЫЙ (только чтение системных устройств Windows)")
    log()

    # 1. Поиск устройств Canon
    log("[1/3] Поиск подключенных устройств Canon по USB (VID 04A9)...")
    canon_devs = get_canon_pnp_devices()

    if not canon_devs:
        log("[-] Устройства Canon не обнаружены в системе.")
        log("    Возможные причины:")
        log("    - Камера не подключена кабелем USB к компьютеру;")
        log("    - Камера выключена (переключатель питания в положении OFF);")
        log("    - USB-кабель работает только на зарядку (нужен кабель с поддержкой передачи данных);")
        log("    - В меню камеры включен режим только зарядки или Wi-Fi блокирует USB.")
    else:
        for idx, dev in enumerate(canon_devs, 1):
            if "error" in dev:
                log(f"    Ошибка опроса PnP: {dev['error']}")
                continue
            name = dev.get("FriendlyName", "Неизвестное устройство")
            inst = dev.get("InstanceId", "")
            cls = dev.get("Class", "")
            status = dev.get("Status", "")
            log(f"    [{idx}] Устройство: {name}")
            log(f"        Класс: {cls}")
            log(f"        Статус: {status}")
            log(f"        ID: {inst}")

    log()

    # 2. Проверка WPD (Windows Portable Devices)
    log("[2/3] Проверка переносных устройств Windows (WPD)...")
    wpd_devs = get_wpd_devices()
    canon_wpd = [d for d in wpd_devs if "Canon" in str(d.get("FriendlyName", ""))]
    if canon_wpd:
        for d in canon_wpd:
            log(f"    [+] Найдено WPD устройство: {d.get('FriendlyName')} (Статус: {d.get('Status')})")
    else:
        log("    [*] В категории WPD устройства Canon не зарегистрированы.")

    log()

    # 3. Проверка конфликтующих процессов
    log("[3/3] Проверка фоновых программ Canon...")
    conflicts = check_conflicting_processes()
    if conflicts:
        log("    [!] ВНИМАНИЕ: Обнаружены запущенные программы, которые могут занимать USB-порт:")
        for c in conflicts:
            log(f"        - {c}")
        log("        (Рекомендуется закрыть EOS Utility для прямого доступа к камере).")
    else:
        log("    [+] Конфликтующие процессы (EOS Utility и т.п.) не обнаружены.")

    log()
    log("=" * 65)
    log("Диагностика завершена.")
    
    # Сохранение отчета
    report_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camera_probe_report.txt")
    try:
        with open(report_file, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines) + "\n")
        log(f"Результат сохранен в файл: {report_file}")
    except Exception as e:
        log(f"Не удалось сохранить файл отчета: {e}")

    log("=" * 65)

if __name__ == "__main__":
    main()
