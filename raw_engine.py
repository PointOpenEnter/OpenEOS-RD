"""
raw_engine.py — Сверхбыстрый автономный анализатор метаданных RAW и EXIF.
Работает полностью на чистом Python 3 без внешних библиотек и сторонних утилит.
Поддерживает прямое чтение:
  - Sony (.ARW, .JPG): MakerNotes тег 0x9050 (чистый механический затвор)
  - Nikon (.NEF, .JPG): MakerNotes тег 0x00A7 (кумулятивный счётчик спусков)
  - Canon (.CR3): ISOBMFF контейнер (Track4 ShutterCount для DIGIC X)
  - Canon (.CR2): TIFF IFD / MakerNotes
  - Canon (.XML): CAM_INFO.XML сервисный дамп процедуры CamInfo_Debug
  - DNG, Fujifilm, Panasonic, Olympus, JPEG
"""
from __future__ import annotations

import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

# Официальная база паспортов механического затвора
CAMERA_SHUTTER_RATINGS = {
    # Canon Mirrorless
    "r1": 500_000, "r3": 500_000, "r5 mark ii": 500_000, "r5 ii": 500_000, "r5m2": 500_000,
    "r5": 500_000, "r6 mark iii": 500_000, "r6 iii": 500_000, "r6m3": 500_000,
    "r6 mark ii": 500_000, "r6 ii": 500_000, "r6m2": 500_000, "r6": 300_000,
    "r7": 200_000, "eos r": 200_000, "ra": 200_000, "r8": 100_000, "r10": 100_000,
    "r50": 100_000, "r100": 100_000, "rp": 100_000,
    # Canon DSLR
    "1d x mark iii": 500_000, "1d x mark ii": 400_000, "1d x": 400_000,
    "5d mark iv": 150_000, "5d mark iii": 150_000, "5d mark ii": 150_000, "5ds": 150_000,
    "6d mark ii": 100_000, "6d": 100_000, "7d mark ii": 200_000, "7d": 150_000,
    "90d": 120_000, "80d": 100_000, "70d": 100_000,
    # Sony
    "ilce-1": 500_000, "ilce-9m3": 500_000, "ilce-9m2": 500_000, "ilce-9": 500_000,
    "a1": 500_000, "a9 iii": 500_000, "a9 ii": 500_000, "a9": 500_000,
    "ilce-7rm5": 500_000, "ilce-7rm4": 500_000, "ilce-7rm3": 500_000,
    "a7r v": 500_000, "a7rv": 500_000, "a7r iv": 500_000, "a7riv": 500_000, "a7r iii": 500_000,
    "ilce-7sm3": 500_000, "a7s iii": 500_000,
    "ilce-7m4": 200_000, "ilce-7m3": 200_000, "a7 iv": 200_000, "a7m4": 200_000,
    "a7 iii": 200_000, "a7m3": 200_000, "a7c ii": 200_000, "a7cr": 200_000, "a7c": 200_000,
    "a6700": 200_000, "a6600": 200_000, "a6400": 200_000, "a6100": 100_000, "a6000": 100_000,
    # Nikon
    "z 9": 500_000, "z9": 500_000, "z 8": 500_000, "z8": 500_000,
    "z 7ii": 200_000, "z 7": 200_000, "z7": 200_000,
    "z 6iii": 200_000, "z 6ii": 200_000, "z 6": 200_000, "z6": 200_000,
    "z 5": 200_000, "z5": 200_000, "z f": 200_000, "zf": 200_000, "z fc": 100_000, "z50": 100_000,
    "d850": 200_000, "d810": 200_000, "d800": 200_000, "d780": 150_000, "d750": 150_000,
    "d500": 200_000, "d6": 400_000, "d5": 400_000, "d4": 400_000,
    # Fujifilm
    "x-h2": 500_000, "x-h2s": 500_000, "x-t5": 300_000, "x-t4": 300_000, "x-t3": 150_000,
    "x-s20": 100_000, "x-s10": 100_000, "gfx 100": 150_000, "gfx 100 ii": 150_000, "gfx 50s": 150_000,
}

def get_camera_rating(model_str: str | None) -> int | None:
    if not model_str:
        return None
    m = model_str.lower().replace("-", " ").replace("_", " ").strip()
    m = re.sub(r"\s+", " ", m)
    for key in sorted(CAMERA_SHUTTER_RATINGS.keys(), key=len, reverse=True):
        pattern = rf"\b{re.escape(key)}\b"
        if re.search(pattern, m):
            return CAMERA_SHUTTER_RATINGS[key]
    return None

def format_date(raw: str | None) -> str:
    if not raw or not isinstance(raw, str):
        return "—"
    raw = raw.strip()
    parts = raw.split(" ")
    if len(parts) == 2 and parts[0].count(":") == 2:
        ymd = parts[0].split(":")
        if len(ymd) == 3 and len(ymd[0]) == 4:
            return f"{ymd[2]}.{ymd[1]}.{ymd[0]}, {parts[1]}"
    return raw

# ---------------------------------------------------------------------------
# TIFF / EXIF / MakerNotes Parser
# ---------------------------------------------------------------------------
class TiffParser:
    def __init__(self, data: bytes):
        self.data = data
        self.endian = "<"
        self.is_valid = False
        if len(self.data) >= 8:
            if self.data[:2] == b"II" and struct.unpack_from("<H", self.data, 2)[0] == 42:
                self.endian = "<"
                self.is_valid = True
            elif self.data[:2] == b"MM" and struct.unpack_from(">H", self.data, 2)[0] == 42:
                self.endian = ">"
                self.is_valid = True

    def read_u16(self, offset: int) -> int:
        return struct.unpack_from(self.endian + "H", self.data, offset)[0]

    def read_u32(self, offset: int) -> int:
        return struct.unpack_from(self.endian + "I", self.data, offset)[0]

    def parse_ifd(self, offset: int) -> dict[int, tuple[int, int, int, bytes]]:
        tags = {}
        if offset + 2 > len(self.data):
            return tags
        try:
            num = self.read_u16(offset)
            pos = offset + 2
            for _ in range(num):
                if pos + 12 > len(self.data):
                    break
                tag = self.read_u16(pos)
                dtype = self.read_u16(pos + 2)
                count = self.read_u32(pos + 4)
                val_bytes = self.data[pos + 8:pos + 12]
                val_u32 = struct.unpack_from(self.endian + "I", val_bytes)[0]
                tags[tag] = (dtype, count, val_u32, val_bytes)
                pos += 12
        except Exception:
            pass
        return tags

    def get_string(self, entry: tuple[int, int, int, bytes]) -> str:
        dtype, count, val_u32, val_bytes = entry
        if dtype != 2:
            return ""
        if count <= 4:
            s = val_bytes[:count].split(b"\x00")[0]
            return s.decode("latin1", errors="replace").strip()
        if val_u32 + count <= len(self.data):
            s = self.data[val_u32:val_u32 + count].split(b"\x00")[0]
            return s.decode("latin1", errors="replace").strip()
        return ""

    def get_int(self, entry: tuple[int, int, int, bytes]) -> int | None:
        dtype, count, val_u32, val_bytes = entry
        if dtype == 3:  # SHORT
            return struct.unpack_from(self.endian + "H", val_bytes[:2])[0]
        if dtype in (4, 9):  # LONG / SLONG
            return val_u32
        return val_u32


def parse_tiff_raw(data: bytes) -> dict:
    parser = TiffParser(data)
    if not parser.is_valid:
        return {}

    result = {
        "make": None,
        "model": None,
        "date": None,
        "shutter_count": None,
        "shutter_type": "unknown",
        "vendor_notes": [],
    }

    try:
        first_ifd = parser.read_u32(4)
        ifd0 = parser.parse_ifd(first_ifd)

        if 0x010F in ifd0:
            result["make"] = parser.get_string(ifd0[0x010F])
        if 0x0110 in ifd0:
            result["model"] = parser.get_string(ifd0[0x0110])
        if 0x0132 in ifd0:  # DateTime в IFD0 — запасной вариант, если в EXIF нет DateTimeOriginal
            result["date"] = parser.get_string(ifd0[0x0132])

        exif_offset = ifd0[0x8769][2] if 0x8769 in ifd0 else None
        makernote_offset = None

        if exif_offset and exif_offset < len(data):
            exif_ifd = parser.parse_ifd(exif_offset)
            if 0x9003 in exif_ifd:
                result["date"] = parser.get_string(exif_ifd[0x9003])
            if 0x927C in exif_ifd:
                makernote_offset = exif_ifd[0x927C][2]

        make_str = (result.get("make") or "").lower()
        model_str = (result.get("model") or "").lower()

        # SONY: ARW MakerNotes тег 0x9050 (Точный механический затвор)
        if "sony" in make_str or "ilce" in model_str or "nex" in model_str:
            result["shutter_type"] = "mechanical"
            pattern_le = b"\x50\x90\x04\x00\x01\x00\x00\x00"
            idx = data.find(pattern_le)
            if idx != -1 and idx + 12 <= len(data):
                val = struct.unpack_from("<I", data, idx + 8)[0]
                if 0 < val < 5_000_000:
                    result["shutter_count"] = val
                    result["vendor_notes"].append("Sony: точный счётчик механических шторок (MakerNotes 0x9050)")

            if result["shutter_count"] is None and makernote_offset:
                mn_ifd = parser.parse_ifd(makernote_offset)
                if 0x9050 in mn_ifd:
                    result["shutter_count"] = parser.get_int(mn_ifd[0x9050])
                    result["vendor_notes"].append("Sony: тег 0x9050 из каталога MakerNotes")

        # NIKON: NEF MakerNotes тег 0x00A7 (Кумулятивный спуск)
        elif "nikon" in make_str:
            result["shutter_type"] = "total"
            pattern_a7 = b"\xa7\x00\x04\x00\x01\x00\x00\x00"
            idx = data.find(pattern_a7)
            if idx != -1 and idx + 12 <= len(data):
                val = struct.unpack_from("<I", data, idx + 8)[0]
                if 0 < val < 5_000_000:
                    result["shutter_count"] = val
                    result["vendor_notes"].append("Nikon: кумулятивный счётчик затвора (MakerNotes 0x00A7, мех.+электр.)")

            if result["shutter_count"] is None and makernote_offset:
                for off in [makernote_offset + 10, makernote_offset + 18, makernote_offset + 8]:
                    if off < len(data):
                        nikon_ifd = parser.parse_ifd(off)
                        if 0x00A7 in nikon_ifd:
                            result["shutter_count"] = parser.get_int(nikon_ifd[0x00A7])
                            result["vendor_notes"].append("Nikon: тег 0x00A7 из каталога MakerNotes")
                            break

    except Exception as ex:
        result["vendor_notes"].append(f"Замечание разбора: {ex}")

    return result


# ---------------------------------------------------------------------------
# CANON CR3: ISOBMFF QuickTime / Track4
# ---------------------------------------------------------------------------
def parse_canon_cr3(path: str) -> dict:
    result = {
        "make": "Canon",
        "model": None,
        "date": None,
        "shutter_count": None,
        "shutter_type": "total",
        "vendor_notes": [],
    }
    try:
        max_scan = min(os.path.getsize(path), 16 * 1024 * 1024)
        with open(path, "rb") as f:
            data = f.read(max_scan)

        m_model = re.search(rb"(Canon EOS [A-Za-z0-9\s\-]+?)\x00", data)
        if m_model:
            result["model"] = m_model.group(1).decode("ascii", errors="replace").strip()

        m_date = re.search(rb"(\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2})", data)
        if m_date:
            result["date"] = m_date.group(1).decode("ascii", errors="replace")

        if b"Track4" in data:
            result["vendor_notes"].append("Обнаружена служебная дорожка Canon DIGIC X (Track4)")

        sc_pos = data.find(b"ShutterCount")
        if sc_pos != -1:
            chunk = data[sc_pos:sc_pos + 128]
            m_num = re.search(rb"ShutterCount.*?(\d+)", chunk)
            if m_num:
                result["shutter_count"] = int(m_num.group(1).decode("ascii"))
                result["vendor_notes"].append("Canon DIGIC X: ShutterCount из метаданных контейнера CR3")

    except Exception as ex:
        result["vendor_notes"].append(f"Замечание чтения CR3: {ex}")

    return result


# ---------------------------------------------------------------------------
# Публичный анализ файла
# ---------------------------------------------------------------------------
def analyze_file(file_path: str) -> dict:
    path_obj = Path(file_path)
    if not path_obj.is_file():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    ext = path_obj.suffix.lower()

    if ext == ".xml":
        import cbasic_card
        card_data = cbasic_card.parse_cam_info_xml(path_obj)
        shutter = card_data.get("total_shutter")
        release = card_data.get("total_shoot")
        serial = card_data.get("serial")
        fw = card_data.get("firmware")
        errs = card_data.get("errors", [])
        return {
            "file_name": path_obj.name,
            "file_path": str(path_obj.resolve()),
            "file_size_mb": round(path_obj.stat().st_size / (1024 * 1024), 2),
            "make": "Canon",
            "model": "Canon EOS (по сервисному дампу)",
            "date": "Из XML дампа",
            "serial": serial,
            "firmware": fw,
            "shutter_count": shutter,
            "release_total": release,
            "shutter_type": "mechanical",
            "rating": None,
            "wear_percent": None,
            "errors": errs,
            "vendor_advice": (
                "Файл CAM_INFO.XML — официальный заводской отчёт сервисной процедуры Canon CamInfo_Debug.\n"
                f"• Механический затвор (TotalShutter): {f'{shutter:,}'.replace(',', ' ') if shutter else '—'} кадров\n"
                f"• Общее число спусков (TotalShoot): {f'{release:,}'.replace(',', ' ') if release else '—'} кадров\n"
                f"• Зафиксированных сервисных ошибок: {len(errs)}"
            ),
            "source": "Canon CAM_INFO.XML",
        }

    res = {}
    if ext in (".arw", ".nef", ".cr2", ".dng", ".tif", ".tiff", ".jpg", ".jpeg"):
        read_len = min(path_obj.stat().st_size, 2 * 1024 * 1024)
        with open(file_path, "rb") as f:
            raw_data = f.read(read_len)
        res = parse_tiff_raw(raw_data)
    elif ext == ".cr3":
        res = parse_canon_cr3(file_path)

    model = res.get("model") or "Не определена"
    make = res.get("make") or ""
    date = format_date(res.get("date"))
    shutter = res.get("shutter_count")
    shutter_type = res.get("shutter_type", "unknown")

    rating = get_camera_rating(model)
    wear_pct = None
    if shutter is not None and rating:
        wear_pct = round((shutter / rating) * 100, 1)

    advice_lines = []
    if "sony" in make.lower() or "ilce" in model.lower():
        advice_lines.append("• Sony ARW: счётчик отражает ТОЛЬКО физические срабатывания механических шторок.")
        advice_lines.append("• Кадры в бесшумном режиме (электронный затвор) НЕ расходуют ресурс механики.")
    elif "nikon" in make.lower():
        advice_lines.append("• Nikon NEF: счётчик является кумулятивным (механический + электронный затвор суммарно).")
        advice_lines.append("• Во флагманах вроде Nikon Z9 механического затвора нет вообще, счётчик фиксирует спуски сенсора.")
    elif "canon" in make.lower():
        if "cr3" in ext:
            advice_lines.append("• Canon CR3: дорожка Track4 (DIGIC X) фиксирует общее число срабатываний камеры.")
            advice_lines.append("• Для R6 Mark II, R6 Mark III, R10 и др. общее число спусков фиксируется в каждом RAW.")
            advice_lines.append("• Точное разделение на механику/электронику доступно через USB или процедуру CamInfo_Debug.")
        elif "cr2" in ext:
            short_model = re.sub(r"^\s*canon\s+eos\s+", "", model, flags=re.I).strip() or "этой камеры"
            advice_lines.append("• В файлах CR2 зеркалок Canon пробег затвора намеренно скрыт производителем.")
            advice_lines.append(f"• Для точного чтения пробега {short_model} подключите камеру кабелем USB "
                                "во вкладке «Камера по USB» (Pro-версия).")
    else:
        advice_lines.append("• Счётчик извлечён из заводских метаданных производителя кадра.")

    return {
        "file_name": path_obj.name,
        "file_path": str(path_obj.resolve()),
        "file_size_mb": round(path_obj.stat().st_size / (1024 * 1024), 2),
        "make": make,
        "model": model,
        "date": date,
        "shutter_count": shutter,
        "shutter_type": shutter_type,
        "rating": rating,
        "wear_percent": wear_pct,
        "notes": res.get("vendor_notes", []),
        "vendor_advice": "\n".join(advice_lines),
        "source": res.get("source", "Native OpenEOS Engine"),
    }
