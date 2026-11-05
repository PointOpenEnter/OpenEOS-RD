"""
Генератор профессиональной иконки камеры для OpenEOS (PNG и мульти-размерный ICO).
Работает на чистом стандартном Python без внешних зависимостей (zlib + struct).
Создает:
1. app_icon.png / app_icon.ico (классический синий акцент для OpenEOS)
2. app_icon_service.png / app_icon_service.ico (изумрудный зеленый сервисный акцент для OpenEOS Service)
"""
from __future__ import annotations

import math
import os
import struct
import zlib


def write_png(width: int, height: int, rgba_data: bytes) -> bytes:
    """Генерирует стандартный валидный 32-битный RGBA PNG."""
    png = bytearray(b"\x89PNG\r\n\x1a\n")

    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
    png.extend(struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc))

    # IDAT
    raw = bytearray()
    row_stride = width * 4
    for y in range(height):
        raw.append(0)  # Filter None
        start = y * row_stride
        raw.extend(rgba_data[start:start + row_stride])

    compressed = zlib.compress(bytes(raw), 9)
    idat_crc = zlib.crc32(b"IDAT" + compressed)
    png.extend(struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc))

    # IEND
    iend_crc = zlib.crc32(b"IEND")
    png.extend(struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc))
    return bytes(png)


def write_ico(png_dict: dict[int, bytes]) -> bytes:
    """Собирает мульти-размерный Windows ICO файл из набора PNG файлов."""
    count = len(png_dict)
    header = struct.pack("<HHH", 0, 1, count)

    entries = bytearray()
    image_data = bytearray()
    offset = 6 + (16 * count)

    for size in sorted(png_dict.keys(), reverse=True):
        png_bytes = png_dict[size]
        length = len(png_bytes)
        w = size if size < 256 else 0
        h = size if size < 256 else 0

        # Width, Height, ColorCount, Reserved, Planes, BitCount, BytesInRes, ImageOffset
        entry = struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, length, offset)
        entries.extend(entry)
        image_data.extend(png_bytes)
        offset += length

    return bytes(header + entries + image_data)


def render_camera_icon(size: int = 256, color_scheme: str = "blue") -> bytes:
    """Рендерит высококачественную иконку камеры с субпиксельным сглаживанием (SSAA)."""
    pixels = bytearray(size * size * 4)

    scale = size / 256.0
    cx, cy = size / 2.0, size / 2.0 + 4 * scale

    # Параметры корпуса камеры
    body_l, body_r = 28 * scale, 228 * scale
    body_t, body_b = 76 * scale, 218 * scale
    body_radius = 26 * scale

    # Пентапризма / видоискатель
    prism_l, prism_r = 92 * scale, 164 * scale
    prism_t, prism_b = 46 * scale, 80 * scale
    prism_radius = 10 * scale

    # Кнопка спуска
    btn_l, btn_r = 44 * scale, 76 * scale
    btn_t, btn_b = 64 * scale, 76 * scale

    # Объектив
    lens_cx, lens_cy = cx, cy + 10 * scale
    r_outer = 56 * scale
    r_mid = 48 * scale
    r_inner = 38 * scale
    r_glass = 26 * scale

    # Маркер Pro / бейдж
    red_cx, red_cy = 196 * scale, 104 * scale
    red_r = 6.5 * scale

    samples = [(-0.25, -0.25), (0.25, -0.25), (-0.25, 0.25), (0.25, 0.25)]

    is_green = (color_scheme == "green")

    def point_in_rrect(px, py, l, t, r, b, rad):
        if px < l or px > r or py < t or py > b:
            return False
        if px < l + rad and py < t + rad:
            return (px - (l + rad)) ** 2 + (py - (t + rad)) ** 2 <= rad ** 2
        if px > r - rad and py < t + rad:
            return (px - (r - rad)) ** 2 + (py - (t + rad)) ** 2 <= rad ** 2
        if px < l + rad and py > b - rad:
            return (px - (l + rad)) ** 2 + (py - (b - rad)) ** 2 <= rad ** 2
        if px > r - rad and py > b - rad:
            return (px - (r - rad)) ** 2 + (py - (b - rad)) ** 2 <= rad ** 2
        return True

    for y in range(size):
        for x in range(size):
            r_acc, g_acc, b_acc, a_acc = 0, 0, 0, 0

            for dx, dy in samples:
                px = x + 0.5 + dx
                py = y + 0.5 + dy

                # 1. Проверка кнопки спуска
                if btn_l <= px <= btn_r and btn_t <= py <= btn_b:
                    r_acc += 140
                    g_acc += 150
                    b_acc += 165
                    a_acc += 255
                    continue

                # 2. Проверка видоискателя и корпуса
                in_prism = point_in_rrect(px, py, prism_l, prism_t, prism_r, prism_b, prism_radius)
                in_body = point_in_rrect(px, py, body_l, body_t, body_r, body_b, body_radius)

                if in_prism or in_body:
                    grad = (py - body_t) / max(1.0, body_b - body_t)
                    c_val = int(38 - grad * 12)

                    # Объектив
                    dist_lens = math.hypot(px - lens_cx, py - lens_cy)
                    if dist_lens <= r_outer:
                        if dist_lens > r_mid:
                            # Внешний металлический безель (Синий vs Изумрудный Зеленый)
                            if is_green:
                                r_acc += 16
                                g_acc += 185
                                b_acc += 90
                            else:
                                r_acc += 0
                                g_acc += 103
                                b_acc += 192
                            a_acc += 255
                        elif dist_lens > r_inner:
                            # Металлическое кольцо оправы
                            r_acc += 55
                            g_acc += 62
                            b_acc += 72
                            a_acc += 255
                        elif dist_lens > r_glass:
                            # Обод шахты затвора
                            r_acc += 22
                            g_acc += 26
                            b_acc += 32
                            a_acc += 255
                        else:
                            # Стекло с бликом
                            refl_dist = math.hypot(px - (lens_cx - 8 * scale), py - (lens_cy - 8 * scale))
                            if refl_dist < 10 * scale:
                                if is_green:
                                    r_acc += 160
                                    g_acc += 240
                                    b_acc += 200
                                else:
                                    r_acc += 140
                                    g_acc += 215
                                    b_acc += 255
                                a_acc += 255
                            elif refl_dist < 18 * scale and (px < lens_cx and py < lens_cy):
                                if is_green:
                                    r_acc += 20
                                    g_acc += 150
                                    b_acc += 100
                                else:
                                    r_acc += 30
                                    g_acc += 120
                                    b_acc += 190
                                a_acc += 255
                            else:
                                r_acc += 12
                                g_acc += 15
                                b_acc += 20
                                a_acc += 255
                        continue

                    # Маркер Pro / сервисная индикация
                    dist_red = math.hypot(px - red_cx, py - red_cy)
                    if dist_red <= red_r:
                        if is_green:
                            r_acc += 34
                            g_acc += 197
                            b_acc += 94
                        else:
                            r_acc += 225
                            g_acc += 25
                            b_acc += 35
                        a_acc += 255
                        continue

                    # Корпус камеры
                    r_acc += c_val
                    g_acc += c_val + 2
                    b_acc += c_val + 6
                    a_acc += 255

            idx = (y * size + x) * 4
            pixels[idx] = r_acc // 4
            pixels[idx + 1] = g_acc // 4
            pixels[idx + 2] = b_acc // 4
            pixels[idx + 3] = a_acc // 4

    return bytes(pixels)


def generate_all_icons(base_dir: str | None = None) -> None:
    if not base_dir:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    resolutions = [256, 64, 48, 32, 16]

    # 1. Синяя классическая иконка (OpenEOS)
    png_dict_blue = {}
    for res in resolutions:
        raw_rgba = render_camera_icon(res, color_scheme="blue")
        png_data = write_png(res, res, raw_rgba)
        png_dict_blue[res] = png_data
        if res == 256:
            with open(os.path.join(base_dir, "app_icon.png"), "wb") as f:
                f.write(png_data)

    ico_blue = write_ico(png_dict_blue)
    with open(os.path.join(base_dir, "app_icon.ico"), "wb") as f:
        f.write(ico_blue)

    # 2. Изумрудно-зеленая сервисная иконка (OpenEOS Service)
    png_dict_green = {}
    for res in resolutions:
        raw_rgba = render_camera_icon(res, color_scheme="green")
        png_data = write_png(res, res, raw_rgba)
        png_dict_green[res] = png_data
        if res == 256:
            with open(os.path.join(base_dir, "app_icon_service.png"), "wb") as f:
                f.write(png_data)

    ico_green = write_ico(png_dict_green)
    with open(os.path.join(base_dir, "app_icon_service.ico"), "wb") as f:
        f.write(ico_green)


if __name__ == "__main__":
    generate_all_icons()
    print("Иконки успешно сгенерированы: синяя (app_icon.ico) и сервисная зеленая (app_icon_service.ico).")
