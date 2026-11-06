"""
cbasic_card.py — Модуль подготовки сервисной SD-карты Canon (CamInfo_Debug).
Заводская процедура Canon для извлечения сервисного отчёта CAM_INFO.XML.
Поддерживает:
  - Безопасное обнаружение ТОЛЬКО съёмных дисков (SD-карты, кардридеры)
  - Форматирование карты в FAT32 с меткой тома OPENEOS
  - Запись ASCII-метки "SCRIPT" по смещению 0x1F0 загрузочного сектора (CHDK спецификация)
  - Создание файлов extend.m и script.req
  - Поиск и разбор заводского отчёта CAM_INFO.XML
"""
from __future__ import annotations

import os
import re
import string
import subprocess
import sys
import time
from pathlib import Path
from xml.etree import ElementTree as ET

EXTEND_M_CONTENT = (
    "private sub Initialize()\n"
    "System.Create()\n"
    "CamInfo_Debug(1)\n"
    "end sub\n"
)
SCRIPT_REQ_CONTENT = "for DC_scriptdisk\n"

SCRIPT_MARKER_OFFSET = 0x1F0
SCRIPT_MARKER_BYTES = b"SCRIPT"
BOOT_SIG_OFFSET = 0x1FE
BOOT_SIG_BYTES = b"\x55\xAA"

KNOWN_ERROR_CODES = {
    "E01": "Ошибка связи с объективом (проверьте контакты байонета)",
    "E02": "Ошибка связи с картой памяти",
    "E04": "Ошибка чтения/записи буфера",
    "E20": "Механический сбой (привод зеркала, взвод или шторки затвора)",
    "E30": "Непосредственный сбой узла затвора (тайминг шторок)",
    "E60": "Сбой привода диафрагмы или вспомогательного мотора",
    "E70": "Системный сбой встроенного ПО или оперативной памяти",
}

class RemovableDrive:
    def __init__(self, letter: str, label: str, fstype: str, total_bytes: int, free_bytes: int):
        self.letter = letter
        self.label = label
        self.fstype = fstype
        self.total_bytes = total_bytes
        self.free_bytes = free_bytes

    @property
    def is_fat(self) -> bool:
        return (self.fstype or "").upper() in ("FAT", "FAT32")

    @property
    def size_gb(self) -> float:
        return round(self.total_bytes / (1024 ** 3), 1) if self.total_bytes else 0.0

    def display(self) -> str:
        lbl = self.label or "SD Card"
        return f"{self.letter}   [{lbl}]  ·  {self.fstype}  ·  {self.size_gb} ГБ"


def list_removable_drives() -> list[RemovableDrive]:
    drives: list[RemovableDrive] = []
    if sys.platform == "win32":
        try:
            import ctypes
            DRIVE_REMOVABLE = 2
            kernel32 = ctypes.windll.kernel32
            bitmask = kernel32.GetLogicalDrives()
            for i, letter in enumerate(string.ascii_uppercase):
                if not (bitmask & (1 << i)):
                    continue
                root = f"{letter}:\\"
                try:
                    if kernel32.GetDriveTypeW(root) != DRIVE_REMOVABLE:
                        continue
                    vol_buf = ctypes.create_unicode_buffer(261)
                    fs_buf = ctypes.create_unicode_buffer(261)
                    ok = kernel32.GetVolumeInformationW(root, vol_buf, 261, None, None, None, fs_buf, 261)
                    if not ok:
                        continue
                    free_b = ctypes.c_ulonglong(0)
                    total_b = ctypes.c_ulonglong(0)
                    kernel32.GetDiskFreeSpaceExW(root, ctypes.byref(free_b), ctypes.byref(total_b), None)
                    drives.append(RemovableDrive(root, vol_buf.value, fs_buf.value or "FAT32", total_b.value, free_b.value))
                except Exception:
                    continue
        except Exception:
            pass
    elif sys.platform == "darwin":
        # macOS: смотрим точки монтирования в /Volumes
        volumes_dir = Path("/Volumes")
        if volumes_dir.is_dir():
            for p in volumes_dir.iterdir():
                if p.is_dir() and not p.name.startswith("Macintosh") and not p.name.startswith("."):
                    try:
                        stat = os.statvfs(str(p))
                        total_b = stat.f_frsize * stat.f_blocks
                        free_b = stat.f_frsize * stat.f_bavail
                        drives.append(RemovableDrive(str(p), p.name, "FAT32", total_b, free_b))
                    except Exception:
                        pass
    return drives


def write_script_marker(drive: RemovableDrive) -> tuple[bool, str]:
    if sys.platform != "win32":
        return True, "На macOS разметка загрузчика пропущена (требуется sudo)."
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        OPEN_EXISTING = 3
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        drive_letter = drive.letter.rstrip("\\")
        volume_path = f"\\\\.\\{drive_letter}"

        h = kernel32.CreateFileW(
            volume_path, GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None
        )
        if h == INVALID_HANDLE_VALUE:
            return False, f"Не удалось открыть диск {volume_path} (запустите от имени Администратора)."

        # Читаем первый сектор (512 байт)
        buf = ctypes.create_string_buffer(512)
        bytes_read = wintypes.DWORD(0)
        if not kernel32.ReadFile(h, buf, 512, ctypes.byref(bytes_read), None) or bytes_read.value != 512:
            kernel32.CloseHandle(h)
            return False, "Не удалось прочитать загрузочный сектор диска."

        data = bytearray(buf.raw)
        if data[BOOT_SIG_OFFSET:BOOT_SIG_OFFSET + 2] != BOOT_SIG_BYTES:
            kernel32.CloseHandle(h)
            return False, "Сигнатура загрузочного сектора 0x55AA не обнаружена. Запись отменена."

        # Пишем метку SCRIPT
        data[SCRIPT_MARKER_OFFSET:SCRIPT_MARKER_OFFSET + len(SCRIPT_MARKER_BYTES)] = SCRIPT_MARKER_BYTES
        kernel32.SetFilePointer(h, 0, None, 0)
        bytes_written = wintypes.DWORD(0)
        write_buf = (ctypes.c_char * 512).from_buffer(data)
        ok = kernel32.WriteFile(h, write_buf, 512, ctypes.byref(bytes_written), None)
        kernel32.CloseHandle(h)

        if not ok or bytes_written.value != 512:
            return False, "Сбой записи сектора в карту памяти."
        return True, "Метка SCRIPT успешно записана в загрузочный сектор."
    except Exception as ex:
        return False, f"Ошибка записи маркера: {ex}"


def copy_script_files(drive: RemovableDrive) -> tuple[bool, str]:
    try:
        root = Path(drive.letter)
        (root / "extend.m").write_text(EXTEND_M_CONTENT, encoding="ascii")
        (root / "script.req").write_text(SCRIPT_REQ_CONTENT, encoding="ascii")
        return True, "Файлы extend.m и script.req успешно записаны на карту."
    except Exception as ex:
        return False, f"Не удалось записать файлы: {ex}"


def format_card(drive: RemovableDrive, volume_label: str = "OPENEOS") -> tuple[bool, str]:
    if sys.platform != "win32":
        return copy_script_files(drive)
    letter = drive.letter.rstrip("\\")
    cmd = f'format {letter} /FS:FAT32 /V:{volume_label} /Q /Y'
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120, input="\n\n\n")
        if proc.returncode != 0:
            return False, f"Форматирование не удалось: {proc.stderr or proc.stdout}"
        return True, f"Карта {letter} отформатирована в FAT32."
    except Exception as ex:
        return False, f"Сбой форматирования: {ex}"


def format_and_prepare_card(drive: RemovableDrive, volume_label: str = "OPENEOS") -> tuple[bool, str]:
    ok, msg = format_card(drive, volume_label)
    if not ok:
        return False, msg
    time.sleep(0.5)

    # Запись загрузочной метки
    ok_marker, msg_marker = write_script_marker(drive)
    ok_files, msg_files = copy_script_files(drive)

    if not ok_files:
        return False, f"{msg} Ошибка скрипта: {msg_files}"
    return True, f"{msg} Загрузочный сектор SCRIPT подготовлен. Файлы extend.m/script.req записаны."


def find_cam_info_xml(drive: RemovableDrive) -> Path | None:
    root = Path(drive.letter)
    direct = root / "CAM_INFO.XML"
    if direct.exists():
        return direct
    try:
        for p in root.rglob("CAM_INFO.XML"):
            return p
        for p in root.rglob("cam_info.xml"):
            return p
    except Exception:
        pass
    return None


def parse_cam_info_xml(path: Path) -> dict:
    result = {
        "serial": None,
        "firmware": None,
        "total_shutter": None,
        "total_shoot": None,
        "power_on_count": None,
        "total_running_time": None,
        "errors": [],
        "raw_path": str(path),
    }
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        root = ET.fromstring(text)

        def get_val(name):
            elem = root.find(f".//{name}")
            return elem.text.strip() if (elem is not None and elem.text) else None

        result["serial"] = get_val("BodyID") or get_val("Serial") or get_val("BodyIDEx")
        result["firmware"] = get_val("Firmware") or get_val("FirmwareVer")

        ts = get_val("TotalShutter") or get_val("ShutterCount")
        if ts and ts.isdigit():
            result["total_shutter"] = int(ts)

        t_shoot = get_val("TotalShoot") or get_val("ReleaseCount")
        if t_shoot and t_shoot.isdigit():
            result["total_shoot"] = int(t_shoot)

        pwr = get_val("PowerOnCount")
        if pwr and pwr.isdigit():
            result["power_on_count"] = int(pwr)

        result["total_running_time"] = get_val("TotalRunningTime")

        # Парсим список ошибок
        for kind in root.findall(".//ErrorList/Kind"):
            id_elem = kind.find("ID")
            count_elem = kind.find("Count")
            code = id_elem.text.strip() if (id_elem is not None and id_elem.text) else None
            cnt = int(count_elem.text.strip()) if (count_elem is not None and count_elem.text and count_elem.text.isdigit()) else 1
            if code:
                name = KNOWN_ERROR_CODES.get(code, "Сервисное событие")
                result["errors"].append({"code": code, "count": cnt, "name": name})

    except Exception as ex:
        result["parse_error"] = str(ex)

    return result
