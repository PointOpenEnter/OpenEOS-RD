"""
OpenEOS: альтернативный метод чтения счётчика через штатную заводскую
процедуру камеры CamInfo_Debug (встроенный интерпретатор Canon Basic),
без служебного USB PTP канала (0x9052/0x9053) и без авторизации 0x905C.

Источники, независимо подтверждающие метод:
  - https://github.com/fedoroff-aa/shutter-check-canon
    (список проверенных моделей включает EOS R6 Mark II и EOS R10)
  - форум Magic Lantern, ветка "Canon Basic scripting (DIGIC 8, DIGIC X models)"
    (участник kitor называет те же свойства PROP_MECHA_COUNTER / PROP_RELEASE_COUNTER)

ВАЖНО:
  - EOS R6 Mark III в списке подтверждённых моделей НЕТ.
  - CamInfo_Debug — штатная, предусмотренная Canon диагностическая функция
    (используется сервисными центрами), а не взлом или изменение прошивки.
  - OpenEOS форматирует карту сам (format.com, FAT32) и сам пишет метку
    загрузочного сектора "SCRIPT" — сторонняя утилита EOScard больше не
    используется (несколько антивирусов помечали её бинарник как вредоносный).
    Спецификация метки подтверждена независимо двумя фрагментами документации
    сообщества CHDK (вики-страница "Canon_Basic/Card_Setup" + приведённая там
    же shell-команда `dd bs=1 count=6 seek=496 of=$1`, где 496 = 0x1F0 — оба
    источника совпадают): ASCII-строка "SCRIPT" (6 байт, без завершающего
    нуля) по смещению 0x1F0 первого (загрузочного) сектора раздела.
  - Запись метки действует ТОЛЬКО на карту, которую пользователь явно выбрал
    из списка СЪЁМНЫХ дисков (list_removable_drives исключает жёсткие и
    системные диски). Перед записью проверяется стандартная сигнатура
    загрузочного сектора (0x55 0xAA на смещениях 0x1FE/0x1FF) — если её нет,
    запись отменяется, чтобы не портить непонятно что.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import re
import string
import subprocess
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

# ASCII "SCRIPT" (6 байт) по смещению 0x1F0 первого сектора раздела.
# Подтверждено: вики CHDK (страница Canon_Basic/Card_Setup) + независимая
# shell-команда `dd bs=1 count=6 seek=496 of=$1` (496 = 0x1F0).
SCRIPT_MARKER_OFFSET = 0x1F0
SCRIPT_MARKER_BYTES = b"SCRIPT"
BOOT_SIG_OFFSET = 0x1FE
BOOT_SIG_BYTES = b"\x55\xAA"

# ВНИМАНИЕ: этот список взят из внешнего проекта shutter-check-canon ("подходящие"
# модели по мнению его автора) и НЕ является результатом наших собственных тестов —
# он нигде в коде не используется как блокирующая проверка (в отличие от Guard() в
# eos_probe.cs для USB-метода). Реальные результаты наших тестов на живых камерах
# 2026-11-04/05, расходящиеся с этим списком:
#   ✓ EOS R6 (первая версия, без Mark) — метод РАБОТАЕТ, файл CAM_INFO.XML получен.
#   ✕ EOS R6 Mark II, EOS R10 — метод НЕ РАБОТАЕТ на практике: карта читается камерой
#     (мигает индикатор), но файл результата не появляется ни при каком числе SET.
# Остальные модели ниже нами не проверялись вообще.
CONFIRMED_MODELS = (
    "EOS R", "EOS Ra", "EOS RP", "EOS R3", "EOS R5", "EOS R5 C", "EOS R5 Mark II",
    "EOS R6", "EOS R6 Mark II", "EOS R7", "EOS R8", "EOS R10",
)

KNOWN_ERROR_CODES = {
    "E01": "ошибка связи с объективом / контактами",
    "E02": "ошибка связи с объективом",
    "E04": "расшифровка этого кода пока неизвестна",
    "E20": "системная ошибка (разное)",
    "E60": "расшифровка этого кода пока неизвестна",
    "E70": "системная ошибка: сбой чтения/записи памяти",
}


class RemovableDrive:
    def __init__(self, letter: str, label: str, fstype: str, total_bytes: int, free_bytes: int):
        self.letter = letter  # например "E:\\"
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
        label = self.label or "без метки"
        return f"{self.letter}   {label}  ·  {self.fstype}  ·  {self.size_gb} ГБ"


def list_removable_drives() -> list[RemovableDrive]:
    """
    Только СЪЁМНЫЕ диски (карты памяти через кардридер, флешки).
    Жёсткие и системные диски намеренно исключены, чтобы пользователь
    не мог случайно выбрать не ту букву диска.
    """
    DRIVE_REMOVABLE = 2
    kernel32 = ctypes.windll.kernel32
    drives: list[RemovableDrive] = []

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
                continue  # дисковод есть, но карты нет

            free_b = ctypes.c_ulonglong(0)
            total_b = ctypes.c_ulonglong(0)
            kernel32.GetDiskFreeSpaceExW(root, ctypes.byref(free_b), ctypes.byref(total_b), None)

            drives.append(RemovableDrive(root, vol_buf.value, fs_buf.value or "?", total_b.value, free_b.value))
        except Exception:
            continue
    return drives


def write_script_marker(drive: RemovableDrive) -> tuple[bool, str]:
    """
    Пишет ASCII-метку "SCRIPT" по смещению 0x1F0 загрузочного сектора карты
    (см. обоснование в заголовке модуля). Перед записью проверяет сигнатуру
    0x55AA на стандартном месте (0x1FE/0x1FF) — без неё запись не производится.
    Работает только с диском, который пользователь выбрал из списка СЪЁМНЫХ
    устройств (RemovableDrive берётся только из list_removable_drives()).
    """
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    OPEN_EXISTING = 3
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    ERROR_ACCESS_DENIED = 5

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.ReadFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    kernel32.WriteFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    kernel32.SetFilePointer.argtypes = [
        wintypes.HANDLE, wintypes.LONG, ctypes.POINTER(wintypes.LONG), wintypes.DWORD,
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    letter = drive.letter.rstrip("\\")  # "E:\\" -> "E:"
    volume_path = f"\\\\.\\{letter}"

    # Сразу после format.com том иногда на доли секунды остаётся занят
    # системой (переразметка/перемонтирование) — CreateFileW может на этот
    # короткий момент вернуть ошибку доступа, хотя карта исправна. Несколько
    # коротких повторов устраняют этот ложный сбой.
    handle = None
    err = 0
    for attempt in range(5):
        handle = kernel32.CreateFileW(
            volume_path, GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None
        )
        if handle and handle != INVALID_HANDLE_VALUE:
            break
        err = ctypes.GetLastError()
        handle = None
        if attempt < 4:
            time.sleep(0.4)

    if not handle:
        if err == ERROR_ACCESS_DENIED:
            return False, (
                "Нет доступа к карте на уровне сектора (ERROR_ACCESS_DENIED).\n"
                "Запустите OpenEOS от имени администратора и повторите."
            )
        return False, f"Не удалось открыть карту для записи метки (код ошибки Windows: {err})."

    try:
        buf = ctypes.create_string_buffer(512)
        bytes_read = wintypes.DWORD(0)
        ok = kernel32.ReadFile(handle, buf, 512, ctypes.byref(bytes_read), None)
        if not ok or bytes_read.value < 512:
            return False, "Не удалось прочитать загрузочный сектор карты."

        data = bytearray(buf.raw)
        if bytes(data[BOOT_SIG_OFFSET:BOOT_SIG_OFFSET + 2]) != BOOT_SIG_BYTES:
            return False, (
                "В загрузочном секторе карты не найдена стандартная сигнатура 0x55AA.\n"
                "Запись метки отменена — похоже, карта не отформатирована как FAT/FAT32, "
                "либо это неподдерживаемая разметка."
            )

        data[SCRIPT_MARKER_OFFSET:SCRIPT_MARKER_OFFSET + len(SCRIPT_MARKER_BYTES)] = SCRIPT_MARKER_BYTES

        pos = kernel32.SetFilePointer(handle, 0, None, 0)  # FILE_BEGIN
        if pos == 0xFFFFFFFF:
            return False, "Не удалось перейти к началу сектора для записи."

        bytes_written = wintypes.DWORD(0)
        out_buf = bytes(data)
        ok = kernel32.WriteFile(handle, out_buf, len(out_buf), ctypes.byref(bytes_written), None)
        if not ok or bytes_written.value != 512:
            return False, "Запись метки не удалась (ошибка WriteFile)."

        return True, "Метка SCRIPT записана в загрузочный сектор карты."
    finally:
        kernel32.CloseHandle(handle)


def format_card(drive: RemovableDrive, volume_label: str = "OPENEOS") -> tuple[bool, str]:
    """
    Быстрое форматирование карты в FAT32 штатной утилитой Windows (format.com).
    УНИЧТОЖАЕТ все данные на карте — вызывающий код обязан явно спросить
    подтверждение пользователя ДО вызова этой функции.
    Работает только с диском, который пользователь выбрал из списка СЪЁМНЫХ
    устройств (RemovableDrive берётся только из list_removable_drives()).
    FAT32 — обязательное требование метода CamInfo_Debug; для карт >32 ГБ
    штатный format.com на некоторых версиях Windows может отказаться
    форматировать в FAT32 (ограничение самой Windows, не этой программы) —
    в этом случае возьмите карту ≤32 ГБ (SDHC).
    """
    letter = drive.letter.rstrip("\\")  # "E:\\" -> "E:"
    label = re.sub(r"[^A-Za-z0-9 _-]", "", volume_label)[:11] or "OPENEOS"

    cmd = ["format", letter, "/FS:FAT32", "/Q", f"/V:{label}", "/X", "/Y"]
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=180,
            input="\n\n\n",  # закрывает возможные приглашения "Insert new disk..."/"Press ENTER"
        )
    except subprocess.TimeoutExpired:
        return False, "Форматирование не завершилось за отведённое время (180 с) — возможно, карта неисправна."
    except Exception as ex:
        return False, f"Не удалось запустить форматирование: {ex}"

    output = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    if proc.returncode != 0:
        return False, (
            f"Форматирование не удалось (код {proc.returncode}).\n"
            f"Ответ системы: {output.strip()[:400]}"
        )
    return True, f"Карта {letter} отформатирована в FAT32 (метка «{label}»)."


def prepare_card(drive: RemovableDrive) -> tuple[bool, str]:
    """
    Подготовка уже отформатированной (FAT/FAT32) карты: метка SCRIPT
    в загрузочном секторе + файлы extend.m/script.req в корне.
    """
    if not drive.is_fat:
        return False, (
            f"Карта отформатирована как {drive.fstype}, а не FAT/FAT32.\n"
            "Для этого метода нужна отдельная карта ≤32 ГБ (SDHC), "
            "отформатированная как FAT32."
        )

    ok, msg = write_script_marker(drive)
    if not ok:
        return False, msg

    ok2, msg2 = copy_script_files(drive)
    if not ok2:
        return False, f"Метка записана, но файлы скопировать не удалось: {msg2}"

    return True, f"{msg} {msg2}"


def format_and_prepare_card(drive: RemovableDrive, volume_label: str = "OPENEOS") -> tuple[bool, str]:
    """
    Единая операция «одна кнопка»: форматирует карту в FAT32, затем сразу
    пишет метку SCRIPT в загрузочный сектор и копирует extend.m/script.req.
    УНИЧТОЖАЕТ все данные на карте — вызывающий код обязан явно спросить
    подтверждение пользователя ДО вызова этой функции.
    """
    ok, msg = format_card(drive, volume_label)
    if not ok:
        return False, msg

    # После форматирования переоткрываем диск заново — метка/ФС в ОС
    # обновляются не мгновенно, а RemovableDrive с устаревшими полями
    # использовать для is_fat/проверок нельзя. GetVolumeInformationW может
    # на короткое время после format.com не отвечать — несколько повторов.
    fresh = None
    for attempt in range(5):
        for d in list_removable_drives():
            if d.letter == drive.letter:
                fresh = d
                break
        if fresh is not None:
            break
        time.sleep(0.4)
    if fresh is None:
        return False, (
            f"{msg}\nНо диск не удалось найти повторно после форматирования — "
            "выньте и вставьте карту заново, затем запишите файлы ещё раз."
        )

    ok2, msg2 = prepare_card(fresh)
    if not ok2:
        return False, f"{msg} Однако подготовка скрипта не удалась: {msg2}"

    return True, f"{msg} {msg2}"


def copy_script_files(drive: RemovableDrive) -> tuple[bool, str]:
    """Копирует extend.m и script.req в корень карты."""
    try:
        root = Path(drive.letter)
        (root / "extend.m").write_text(EXTEND_M_CONTENT, encoding="ascii")
        (root / "script.req").write_text(SCRIPT_REQ_CONTENT, encoding="ascii")
        return True, "Файлы extend.m и script.req записаны на карту."
    except Exception as ex:
        return False, f"Не удалось записать файлы на карту: {ex}"


def find_cam_info_xml(drive: RemovableDrive) -> Path | None:
    root = Path(drive.letter)
    direct = root / "CAM_INFO.XML"
    if direct.exists():
        return direct
    try:
        for p in root.rglob("CAM_INFO.XML"):
            return p
    except Exception:
        pass
    return None


def parse_cam_info_xml(path: Path) -> dict:
    """
    Формат подтверждён сообществом (shutter-check-canon) и реальным файлом,
    полученным 2026-11-05 с живой камеры (Canon EOS R6, первая версия).
    Отсутствующие или нераспознанные поля остаются None/пустыми — без
    подстановки придуманных значений.

    Реальная структура ErrorList (важно для парсинга — так ошибку
    не найти по .text самого элемента, код и счётчик лежат в дочерних
    тегах):
        <ErrorList>
          <Kind><ID>E70</ID><Count>2</Count><ErrorLog>...</ErrorLog></Kind>
          ...
        </ErrorList>
    """
    result = {
        "serial": None,
        "firmware": None,
        "total_shutter": None,   # TotalShutter — счётчик МЕХАНИЧЕСКОГО затвора
        "total_shoot": None,     # TotalShoot — все кадры (мех. + электр.)
        "power_on_count": None,
        "total_running_time": None,  # секунды (как в файле, строкой)
        "errors": [],             # [{"code": "E70", "count": 2, "name": "..."}]
        "raw_path": str(path),
        "parse_error": None,
    }
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        root = ET.fromstring(text)
    except Exception as ex:
        result["parse_error"] = str(ex)
        return result

    def text_of(el):
        return el.text.strip() if (el is not None and el.text) else None

    def int_of(tag: str):
        el = root.find(f".//{tag}")
        t = text_of(el)
        return int(t) if (t and t.isdigit()) else None

    result["serial"] = text_of(root.find(".//Serial"))

    fw_el = root.find(".//FirmwareVer")
    if fw_el is not None:
        fw_major = text_of(fw_el.find("Major"))
        fw_internal = text_of(fw_el.find("Internal"))
        if fw_major:
            result["firmware"] = fw_major + (f" (internal {fw_internal})" if fw_internal else "")

    result["total_shutter"] = int_of("TotalShutter")
    result["total_shoot"] = int_of("TotalShoot")
    result["power_on_count"] = int_of("PowerOnCount")
    result["total_running_time"] = text_of(root.find(".//TotalRunningTime"))

    err_list_el = root.find(".//ErrorList")
    if err_list_el is not None:
        for kind_el in err_list_el.findall("Kind"):
            code = text_of(kind_el.find("ID"))
            count_text = text_of(kind_el.find("Count"))
            count = int(count_text) if (count_text and count_text.isdigit()) else 0
            if code:
                result["errors"].append({
                    "code": code,
                    "count": count,
                    "name": KNOWN_ERROR_CODES.get(code, ""),
                })

    return result
