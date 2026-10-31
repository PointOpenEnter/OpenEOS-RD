"""
OpenEOS — проверка показания счётчика затвора по RAW-файлам и метаданным.
Поддерживает Canon (CR2, CR3), Nikon (NEF), Sony (ARW), Fujifilm (RAF),
DNG, JPEG, HEIC, HIF и PEF.
Работает полностью локально без отправки файлов в сеть.
"""
from __future__ import annotations

import csv
import ctypes
import json
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "OpenEOS"
APP_VERSION = "0.4.1"

BATCH_CHUNK_SIZE = 50
TABLE_CHUNK_SIZE = 150

SUPPORTED_EXTENSIONS = (
    ".cr2", ".cr3", ".dng", ".jpg", ".jpeg",
    ".heic", ".hif", ".nef", ".arw", ".raf", ".pef",
)

SUPPORTED_FILETYPES = [
    ("Все форматы OpenEOS", "*.CR2 *.CR3 *.DNG *.JPG *.JPEG *.HEIC *.HIF *.NEF *.ARW *.RAF *.PEF"),
    ("Canon RAW (CR2, CR3)", "*.CR2 *.CR3"),
    ("Nikon RAW (NEF)", "*.NEF"),
    ("Sony RAW (ARW)", "*.ARW"),
    ("Fujifilm RAW (RAF)", "*.RAF"),
    ("DNG Digital Negative", "*.DNG"),
    ("JPEG / HEIF", "*.JPG *.JPEG *.HEIC *.HIF"),
    ("Все файлы", "*.*"),
]

SUPPORTED_FORMATS_LABEL = (
    "CR2  ·  CR3  ·  DNG  ·  JPG/JPEG  ·  HEIC  ·  HIF  ·  NEF  ·  ARW  ·  RAF  ·  PEF"
)


# ---------------------------------------------------------------------------
# База официальных паспортных ресурсов механического затвора производителей
# ---------------------------------------------------------------------------
CAMERA_SHUTTER_RATINGS = {
    # Canon Mirrorless
    "r1": 500_000,
    "r3": 500_000,
    "r5 mark ii": 500_000,
    "r5 ii": 500_000,
    "r5m2": 500_000,
    "r5": 500_000,
    "r6 mark ii": 400_000,
    "r6 ii": 400_000,
    "r6m2": 400_000,
    "r6": 300_000,
    "r7": 200_000,
    "eos r": 200_000,
    "ra": 200_000,
    "r8": 100_000,
    "r10": 100_000,
    "r50": 100_000,
    "r100": 100_000,
    "rp": 100_000,

    # Canon DSLR
    "1d x mark iii": 500_000,
    "1d x mark ii": 400_000,
    "1d x": 400_000,
    "5d mark iv": 150_000,
    "5d mark iii": 150_000,
    "5d mark ii": 150_000,
    "5ds": 150_000,
    "6d mark ii": 100_000,
    "6d": 100_000,
    "7d mark ii": 200_000,
    "7d": 150_000,
    "90d": 120_000,
    "80d": 100_000,
    "70d": 100_000,

    # Sony
    "ilce-1": 500_000,
    "ilce-9": 500_000,
    "a1": 500_000,
    "a9": 500_000,
    "ilce-7rm5": 500_000,
    "ilce-7rm4": 500_000,
    "ilce-7rm3": 500_000,
    "a7r v": 500_000,
    "a7rv": 500_000,
    "a7r iv": 500_000,
    "a7riv": 500_000,
    "a7r iii": 500_000,
    "a7s iii": 500_000,
    "ilce-7m4": 200_000,
    "ilce-7m3": 200_000,
    "a7 iv": 200_000,
    "a7m4": 200_000,
    "a7 iii": 200_000,
    "a7m3": 200_000,
    "a7c ii": 200_000,
    "a7c": 200_000,
    "a6700": 200_000,
    "a6600": 200_000,
    "a6400": 200_000,
    "a6000": 100_000,

    # Nikon
    "z 9": 500_000,
    "z9": 500_000,
    "z 8": 500_000,
    "z8": 500_000,
    "z 7": 200_000,
    "z7": 200_000,
    "z 6": 200_000,
    "z6": 200_000,
    "z 5": 200_000,
    "z5": 200_000,
    "z f": 200_000,
    "zf": 200_000,
    "z50": 100_000,
    "d850": 200_000,
    "d810": 200_000,
    "d780": 150_000,
    "d750": 150_000,
    "d500": 200_000,
    "d6": 400_000,
    "d5": 400_000,
    "d4": 400_000,

    # Fujifilm
    "x-h2": 500_000,
    "x-h2s": 500_000,
    "x-t5": 300_000,
    "x-t4": 300_000,
    "x-t3": 150_000,
    "x-s20": 100_000,
    "x-s10": 100_000,
    "gfx 100": 150_000,
    "gfx 50": 150_000,
}


def get_camera_rating(model_str: str | None) -> int | None:
    """Возвращает официальный паспортный ресурс механики для модели камеры."""
    if not model_str:
        return None
    m = model_str.lower().replace("-", " ").replace("_", " ").strip()
    m = re.sub(r"\s+", " ", m)

    # Поиск по границам слов: исключает ложные срабатывания вроде 'eos r' внутри 'eos r6m2'
    for key in sorted(CAMERA_SHUTTER_RATINGS.keys(), key=len, reverse=True):
        pattern = rf"\b{re.escape(key)}\b"
        if re.search(pattern, m):
            return CAMERA_SHUTTER_RATINGS[key]
    return None


# ---------------------------------------------------------------------------
# Инициализация ExifTool (портативный EXE, локальная папка или среда dev)
# ---------------------------------------------------------------------------
def init_exiftool() -> tuple[list[str], dict[str, str], str | None]:
    """
    Конфигурирует запуск ExifTool. Напрямую использует perl.exe с явным
    -I lib_dir при его наличии, исключая ошибку 'strict.pm in @INC' в PyInstaller.
    """
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    local_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    dev_dir = r"C:\Tools\ExifTool"

    search_dirs = [base_dir, local_dir, dev_dir]
    env = os.environ.copy()
    cmd_prefix: list[str] = []
    exif_cwd: str | None = None

    for candidate_dir in search_dirs:
        if not candidate_dir or not os.path.isdir(candidate_dir):
            continue

        exiftool_files = os.path.join(candidate_dir, "exiftool_files")
        lib_dir = os.path.join(exiftool_files, "lib")
        perl_exe = os.path.join(exiftool_files, "perl.exe")
        exiftool_pl = os.path.join(exiftool_files, "exiftool.pl")
        exiftool_exe = os.path.join(candidate_dir, "exiftool.exe")

        if os.path.isfile(perl_exe) and os.path.isfile(exiftool_pl) and os.path.isdir(lib_dir):
            cmd_prefix = [perl_exe, "-I", lib_dir, exiftool_pl]
            exif_cwd = candidate_dir
            env["PERL5LIB"] = lib_dir
            env["PERLLIB"] = lib_dir
            break

        if os.path.isfile(exiftool_exe):
            cmd_prefix = [exiftool_exe]
            exif_cwd = candidate_dir
            if os.path.isdir(lib_dir):
                env["PERL5LIB"] = lib_dir
                env["PERLLIB"] = lib_dir
            break

    if not cmd_prefix:
        cmd_prefix = [r"C:\Tools\ExifTool\exiftool.exe"]
        exif_cwd = dev_dir

    return cmd_prefix, env, exif_cwd


EXIFTOOL_CMD, EXIFTOOL_ENV, EXIFTOOL_CWD = init_exiftool()


# ---------------------------------------------------------------------------
# Поддержка Drag-and-Drop (tkinterdnd2)
# ---------------------------------------------------------------------------
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
    ROOT_CLASS = TkinterDnD.Tk
except ImportError:
    DND_FILES = None
    DND_AVAILABLE = False
    ROOT_CLASS = tk.Tk


# ---------------------------------------------------------------------------
# Системная интеграция Windows 10/11
# ---------------------------------------------------------------------------
def detect_system_theme() -> str:
    """Определяет системную тему Windows (светлая или тёмная)."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        )
        for param in ("AppsUseLightTheme", "SystemUsesLightTheme"):
            try:
                val, _ = winreg.QueryValueEx(key, param)
                winreg.CloseKey(key)
                return "dark" if val == 0 else "light"
            except FileNotFoundError:
                continue
        winreg.CloseKey(key)
    except Exception:
        pass
    return "dark"


def apply_titlebar_theme(root: tk.Tk, dark: bool) -> None:
    """Устанавливает нативный тёмный или светлый стиль заголовка окна Windows 10/11."""
    try:
        hwnd = None
        try:
            frame = root.wm_frame()
            if frame:
                hwnd = int(frame, 16)
        except Exception:
            pass
        if not hwnd:
            hwnd = root.winfo_id()
        if not hwnd:
            return

        try:
            root_hwnd = ctypes.windll.user32.GetAncestor(ctypes.c_void_p(hwnd), ctypes.c_uint(2))
            if root_hwnd:
                hwnd = root_hwnd
        except Exception:
            pass

        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        val = ctypes.c_int(1 if dark else 0)
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            ctypes.c_uint(DWMWA_USE_IMMERSIVE_DARK_MODE),
            ctypes.byref(val),
            ctypes.sizeof(val)
        )
        if res != 0:
            # Fallback для старых сборок Windows 10
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_uint(19),
                ctypes.byref(val),
                ctypes.sizeof(val)
            )
    except Exception:
        pass





def format_display_date(raw: str | None) -> str:
    """Преобразует машинный формат EXIF 'YYYY:MM:DD HH:MM:SS' в человеческий 'DD.MM.YYYY, HH:MM:SS'."""
    if not raw or not isinstance(raw, str):
        return "—"
    val = raw.strip()
    parts = val.split(" ")
    if len(parts) == 2 and parts[0].count(":") == 2:
        ymd = parts[0].split(":")
        if len(ymd) == 3 and len(ymd[0]) == 4:
            return f"{ymd[2]}.{ymd[1]}.{ymd[0]}, {parts[1]}"
    return val


# ---------------------------------------------------------------------------
# Палитра оформления Fluent (Светлая и Тёмная)
# ---------------------------------------------------------------------------
THEMES = {
    "light": {
        "BG": "#F9F9F9",
        "CARD": "#FFFFFF",
        "TEXT": "#1B1B1B",
        "MUTED": "#6E6E6E",
        "SUBTLE": "#AEAEB2",
        "BORDER": "#E0E0E0",
        "ACCENT": "#0067C0",
        "ACCENT_HOVER": "#005A9E",
        "ACCENT_BG": "#F4F9FD",
        "ACCENT_BORDER": "#C5D9E8",
        "GRAY_BTN": "#EAEAEA",
        "GRAY_BTN_HOVER": "#DFDFDF",
        "GRAY_BTN_FG": "#1B1B1B",
        "STATUS_BG_IDLE": "#EFEFF4",
        "STATUS_FG_IDLE": "#6E6E6E",
        "STATUS_BG_OK": "#EAF7EE",
        "STATUS_FG_OK": "#1E7B34",
        "STATUS_BG_WARN": "#FFF4CE",
        "STATUS_FG_WARN": "#9D5D00",
        "STATUS_BG_ERR": "#FDE7E9",
        "STATUS_FG_ERR": "#C42B1C",
        "RED_BTN_HOVER": "#F8C9CB",
        "TAB_BG": "#F9F9F9",
        "TAB_SEL_BG": "#EFEFEF",
        "TAB_SEL_FG": "#000000",
        "PROG_BG": "#E5E5EA",
        "BADGE_BG": "#EAEAEA",
        "BADGE_FG": "#6E6E6E",
        "ROW_ODD": "#FFFFFF",
        "ROW_EVEN": "#F8F9FA",
        "SCROLL_TROUGH": "#F0F0F0",
        "SCROLL_THUMB": "#CDCDCD",
    },
    "dark": {
        "BG": "#1F1F1F",
        "CARD": "#282828",
        "TEXT": "#FFFFFF",
        "MUTED": "#9E9E9E",
        "SUBTLE": "#6E6E6E",
        "BORDER": "#383838",
        "ACCENT": "#0067C0",
        "ACCENT_HOVER": "#1177D7",
        "ACCENT_BG": "#1E2A35",
        "ACCENT_BORDER": "#2E4456",
        "GRAY_BTN": "#333333",
        "GRAY_BTN_HOVER": "#404040",
        "GRAY_BTN_FG": "#FFFFFF",
        "STATUS_BG_IDLE": "#2F2F2F",
        "STATUS_FG_IDLE": "#A0A0A0",
        "STATUS_BG_OK": "#1C3622",
        "STATUS_FG_OK": "#4CD964",
        "STATUS_BG_WARN": "#3B2E15",
        "STATUS_FG_WARN": "#FFB340",
        "STATUS_BG_ERR": "#3B1D20",
        "STATUS_FG_ERR": "#FF6B6B",
        "RED_BTN_HOVER": "#4E272B",
        "TAB_BG": "#1F1F1F",
        "TAB_SEL_BG": "#2C2C2C",
        "TAB_SEL_FG": "#FFFFFF",
        "PROG_BG": "#333333",
        "BADGE_BG": "#2D2D2D",
        "BADGE_FG": "#A0A0A0",
        "ROW_ODD": "#282828",
        "ROW_EVEN": "#222222",
        "SCROLL_TROUGH": "#202020",
        "SCROLL_THUMB": "#3D3D3D",
    },
}


# ---------------------------------------------------------------------------
# Всплывающая информационная подсказка (Tooltip)
# ---------------------------------------------------------------------------
class InfoToolTip:
    """Всплывающая подсказка с автозакрытием при уходе курсора."""

    def __init__(self, widget: tk.Widget, get_text_func, get_theme_func) -> None:
        self.widget = widget
        self.get_text_func = get_text_func
        self.get_theme_func = get_theme_func
        self.tip_window: tk.Toplevel | None = None
        self._show_job: str | None = None
        self._hide_job: str | None = None

        self.widget.bind("<Enter>", self.schedule_show)
        self.widget.bind("<Leave>", self.schedule_hide)
        self.widget.bind("<Button-1>", self.toggle_tip)
        self.widget.bind("<Destroy>", self.hide_tip)

    def cancel_jobs(self) -> None:
        if self._show_job:
            try:
                self.widget.after_cancel(self._show_job)
            except Exception:
                pass
            self._show_job = None
        if self._hide_job:
            try:
                self.widget.after_cancel(self._hide_job)
            except Exception:
                pass
            self._hide_job = None

    def schedule_show(self, _event=None) -> None:
        self.cancel_jobs()
        if not self.tip_window:
            # Задержка 300 мс исключает ложные срабатывания при переключении темы или случайном движении
            self._show_job = self.widget.after(300, self.show_tip)

    def schedule_hide(self, _event=None) -> None:
        self.cancel_jobs()
        if self.tip_window:
            self._hide_job = self.widget.after(160, self.hide_tip)

    def show_tip(self, _event=None) -> None:
        self.cancel_jobs()
        if self.tip_window:
            return
        text = self.get_text_func()
        if not text:
            return

        theme = self.get_theme_func()
        bg = "#1A1D22" if theme == "dark" else "#FFFFFF"
        fg = "#E6EDF3" if theme == "dark" else "#1F2328"
        border = "#38424D" if theme == "dark" else "#D0D7DE"
        accent = "#60CDFF" if theme == "dark" else "#0067C0"
        muted = "#8B949E" if theme == "dark" else "#656D76"

        screen_w = self.widget.winfo_screenwidth()
        tip_w = 420
        x = self.widget.winfo_rootx() - 320
        if x + tip_w > screen_w - 20:
            x = screen_w - tip_w - 20
        if x < 20:
            x = 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6

        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)

        box = tk.Frame(tw, bg=bg, highlightbackground=border, highlightthickness=1, padx=14, pady=10)
        box.pack(fill="both")

        box.bind("<Enter>", lambda _e: self.cancel_jobs())
        box.bind("<Leave>", lambda _e: self.schedule_hide())

        header = tk.Label(
            box, text="ℹ️  Справка: счётчик в файле и ресурс камеры",
            bg=bg, fg=accent, font=("Segoe UI", 9, "bold"), anchor="w"
        )
        header.pack(fill="x", pady=(0, 6))

        body = tk.Label(
            box, text=text, bg=bg, fg=fg,
            font=("Segoe UI", 8), justify="left", anchor="w"
        )
        body.pack(fill="x")

        footer = tk.Label(
            box, text="Паспортные данные основаны на официальных спецификациях производителей",
            bg=bg, fg=muted, font=("Segoe UI", 7), anchor="w"
        )
        footer.pack(fill="x", pady=(6, 0))

    def hide_tip(self, _event=None) -> None:
        self.cancel_jobs()
        if self.tip_window:
            try:
                self.tip_window.destroy()
            except Exception:
                pass
            self.tip_window = None

    def toggle_tip(self, _event=None) -> None:
        self.cancel_jobs()
        if self.tip_window:
            self.hide_tip()
        else:
            self.show_tip()


# ---------------------------------------------------------------------------
# Основной класс приложения OpenEOS
# ---------------------------------------------------------------------------
class OpenEOSApp:
    FONT_FAMILY = "Segoe UI"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        try:
            self.root.withdraw()
        except Exception:
            pass

        self.theme_name = detect_system_theme()
        self.update_theme_attrs()

        self.root.configure(bg=self.BG)
        self.root.title(f"{APP_TITLE} — проверка показания счётчика")
        self.root.resizable(False, False)

        # Нативный шрифт Windows Fluent (Segoe UI всегда доступен без сканирования реестра)
        self.FONT_FAMILY = "Segoe UI"

        # Строго фиксированный размер окна под интерфейс
        self.setup_window_geometry(860, 520)

        # СРАЗУ применяем стиль заголовка Windows 10/11
        apply_titlebar_theme(self.root, self.theme_name == "dark")

        # Устанавливаем фирменную иконку камеры
        self.setup_app_icon()

        # Состояние приложения
        self.busy = False
        self.current_mode: str | None = None
        self.single_file: str | None = None
        self.last_single_data: dict | None = None
        self.batch_results: list[dict] = []
        self.batch_metadata: dict = {}
        self.batch_cancel_event = threading.Event()
        self.batch_process: subprocess.Popen | None = None
        self.batch_process_lock = threading.Lock()
        self.batch_folder_path: str | None = None
        self.batch_total = 0
        self.batch_processed = 0
        self.batch_started_at: float | None = None
        self.render_index = 0
        self.render_readable = 0
        self.render_missing = 0
        self.batch_cancelled = False
        self.current_tab_index = 0

        self.folder_text = tk.StringVar(value="Папка не выбрана")

        self.configure_styles()
        self.create_interface()

        # Полная компоновка и отрисовка в памяти до показа окна
        apply_titlebar_theme(self.root, self.theme_name == "dark")
        self.root.update_idletasks()

        # Чистое проявление окна без белых вспышек и морганий
        self.root.deiconify()
        apply_titlebar_theme(self.root, self.theme_name == "dark")

    def style_tooltip_button(self, widget: tk.Label) -> None:
        """Стилизует иконку справки (?) и привязывает интерактивный тултип."""
        def on_enter(_e):
            widget.config(fg=self.ACCENT if self.theme_name == "light" else "#60CDFF")
        def on_leave(_e):
            widget.config(fg=self.MUTED)
        widget.bind("<Enter>", on_enter, add="+")
        widget.bind("<Leave>", on_leave, add="+")
        self.rating_info_tip = InfoToolTip(widget, self.get_tooltip_text, lambda: self.theme_name)

    def get_tooltip_text(self) -> str:
        """Формирует понятный текст подсказки с учётом обнаруженной модели камеры."""
        model = self.single_meta.get("model")
        model_name = model.cget("text") if model else ""
        has_model = bool(model_name and model_name not in ("—", "Не определена"))
        rating = get_camera_rating(model_name) if has_model else None

        if rating:
            rating_str = f"~{rating:,} кадров".replace(",", " ")
            res_bullet = f"• Расчётный ресурс механики для {model_name}: {rating_str}."
        else:
            res_bullet = "• Паспортный ресурс производителя нормирует только механический узел шторок."

        return (
            "Счётчик в метаданных кадра (RAW / JPEG):\n"
            "• Фиксирует общее количество спусков во всех режимах съёмки, включая электронный затвор.\n\n"
            "Паспортный ресурс камеры:\n"
            f"{res_bullet}\n"
            "• Заявленный ресурс производителя относится исключительно к механическим шторкам.\n\n"
            "Практический вывод:\n"
            "• Съёмка с электронным затвором не расходует ресурс механического узла камеры."
        )

    def setup_app_icon(self) -> None:
        """Устанавливает фирменную иконку камеры для заголовка окна и панели задач Windows."""
        try:
            # Отвязывает процесс от дефолтного python/tkinter на панели задач Windows
            myappid = f"openeos.shuttercount.desktop.{APP_VERSION}"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        local_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))

        for folder in (base_dir, local_dir):
            if not folder or not os.path.isdir(folder):
                continue
            ico_path = os.path.join(folder, "app_icon.ico")
            png_path = os.path.join(folder, "app_icon.png")

            # 1. Нативная установка Windows ICO (не форсирует отображение скрытого окна)
            if os.path.isfile(ico_path):
                try:
                    self.root.iconbitmap(ico_path)
                    return
                except Exception:
                    pass

            # 2. Fallback: установка PNG через iconphoto только если ICO не найден
            if os.path.isfile(png_path):
                try:
                    self._icon_photo = tk.PhotoImage(file=png_path)
                    self.root.iconphoto(True, self._icon_photo)
                    return
                except Exception:
                    pass

    def update_theme_attrs(self) -> None:
        palette = THEMES[self.theme_name]
        for k, v in palette.items():
            setattr(self, k, v)

    def setup_window_geometry(self, width: int, height: int) -> None:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        w = min(width, screen_w - 40)
        h = min(height, screen_h - 80)
        x = max(0, (screen_w - w) // 2)
        y = max(0, (screen_h - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.resizable(False, False)

    def toggle_theme(self) -> None:
        if self.busy and self.current_mode == "batch":
            messagebox.showinfo("OpenEOS", "Смена темы недоступна во время пакетного анализа.")
            return

        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.update_theme_attrs()
        self.configure_styles()

        # Сохранение текущего состояния Single Tab
        last_shutter_text = self.counter_label.cget("text")
        last_status_text = self.single_status_label.cget("text")
        last_file_label = self.selected_file_label.cget("text")
        last_meta = {k: v.cget("text") for k, v in self.single_meta.items()}
        active_tab = self.current_tab_index

        # Перед перестроением закрываем открытый тултип
        if hasattr(self, "rating_info_tip") and self.rating_info_tip:
            self.rating_info_tip.hide_tip()

        # Перестроение интерфейса под новую тему
        for child in self.root.winfo_children():
            child.destroy()

        self.create_interface()
        self.switch_tab(active_tab, initial=True)

        # Обновление заголовка Windows
        apply_titlebar_theme(self.root, self.theme_name == "dark")
        # Восстановление данных Single Tab
        self.counter_label.config(text=last_shutter_text)
        if "Готово" in last_status_text or "Проверено" in last_status_text:
            self.set_single_status("●  Готово", self.STATUS_BG_OK, self.STATUS_FG_OK)
        elif "Ожидает" in last_status_text:
            self.set_single_status("●  Ожидает фото", self.STATUS_BG_IDLE, self.STATUS_FG_IDLE)
        elif "Не найден" in last_status_text:
            self.set_single_status("●  Счётчик не найден", self.STATUS_BG_WARN, self.STATUS_FG_WARN)
        elif "Ошибка" in last_status_text:
            self.set_single_status("✕  Ошибка", self.STATUS_BG_ERR, self.STATUS_FG_ERR)
        else:
            self.set_single_status(last_status_text, self.STATUS_BG_IDLE, self.STATUS_FG_IDLE)

        self.selected_file_label.config(text=last_file_label)
        for k, val in last_meta.items():
            if k in self.single_meta:
                self.single_meta[k].config(text=val)

        # Восстановление таблицы пакетного анализа при наличии данных
        if self.batch_results:
            self.start_table_render()

    def style_button(self, btn: tk.Button, bg: str, hover_bg: str, fg: str, font: tuple | None = None) -> tk.Button:
        if font is None:
            font = (self.FONT_FAMILY, 9, "bold")
        btn.config(
            bg=bg, fg=fg,
            activebackground=hover_bg,
            activeforeground=fg,
            disabledforeground=self.SUBTLE,
            relief="flat", bd=0,
            font=font,
            cursor="hand2"
        )
        def on_enter(_event):
            if str(btn["state"]) != "disabled":
                btn.config(bg=hover_bg)
        def on_leave(_event):
            if str(btn["state"]) != "disabled":
                btn.config(bg=bg)
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        return btn

    def configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # Таблица Treeview
        style.configure(
            "Treeview",
            background=self.CARD,
            fieldbackground=self.CARD,
            foreground=self.TEXT,
            rowheight=28,
            borderwidth=0,
            relief="flat",
            font=(self.FONT_FAMILY, 9),
        )
        style.configure(
            "Treeview.Heading",
            background=self.GRAY_BTN,
            foreground=self.MUTED,
            font=(self.FONT_FAMILY, 8, "bold"),
            relief="flat",
            borderwidth=0,
            padding=(8, 6),
        )
        style.map(
            "Treeview.Heading",
            background=[("active", self.BORDER)],
            foreground=[("active", self.TEXT)],
        )
        style.map(
            "Treeview",
            background=[("selected", self.ACCENT_BG)],
            foreground=[("selected", self.TEXT)],
        )

        # Скроллбары
        for sbar_name in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            style.configure(
                sbar_name,
                gripcount=0,
                background=self.SCROLL_THUMB,
                darkcolor=self.CARD,
                lightcolor=self.CARD,
                troughcolor=self.SCROLL_TROUGH,
                bordercolor=self.CARD,
                arrowcolor=self.MUTED,
                arrowsize=12,
            )
            style.map(
                sbar_name,
                background=[("active", self.MUTED), ("pressed", self.ACCENT)],
                arrowcolor=[("active", self.TEXT)],
            )

    @staticmethod
    def compact_text(value: str | None, limit: int = 70) -> str:
        text = str(value or "")
        if len(text) <= limit:
            return text
        keep = max(8, (limit - 1) // 2)
        return text[:keep] + "…" + text[-keep:]

    def create_interface(self) -> None:
        self.root.configure(bg=self.BG)

        # Верхняя панель: Название, подзаголовок, кнопка темы и версия
        header = tk.Frame(self.root, bg=self.BG)
        header.pack(fill="x", padx=24, pady=(12, 8))

        left_col = tk.Frame(header, bg=self.BG)
        left_col.pack(side="left", fill="y")

        title_label = tk.Label(
            left_col, text=APP_TITLE, bg=self.BG, fg=self.TEXT,
            font=(self.FONT_FAMILY, 20, "bold")
        )
        title_label.pack(side="left", anchor="center")

        subtitle = tk.Label(
            left_col,
            text="Определение пробега затвора по RAW-файлам",
            bg=self.BG, fg=self.MUTED, font=(self.FONT_FAMILY, 9)
        )
        subtitle.pack(side="left", padx=(12, 0), anchor="center")

        right_col = tk.Frame(header, bg=self.BG)
        right_col.pack(side="right", fill="y")

        theme_text = "🌙  Тёмная" if self.theme_name == "light" else "☀️  Светлая"
        self.theme_btn = tk.Button(
            right_col, text=theme_text, command=self.toggle_theme,
            font=(self.FONT_FAMILY, 8, "bold"), padx=10, pady=3
        )
        self.style_button(
            self.theme_btn,
            bg=self.BADGE_BG, hover_bg=self.GRAY_BTN_HOVER, fg=self.BADGE_FG
        )
        self.theme_btn.pack(side="left", padx=(0, 8))

        v_pill = tk.Label(
            right_col, text=f"v{APP_VERSION}", bg=self.BADGE_BG, fg=self.BADGE_FG,
            font=(self.FONT_FAMILY, 8, "bold"), padx=8, pady=3
        )
        v_pill.pack(side="left")

        # Сегментированные вкладки
        self.tab_bar_frame = tk.Frame(self.root, bg=self.BG)
        self.tab_bar_frame.pack(fill="x", padx=24, pady=(0, 0))

        tabs_inner = tk.Frame(self.tab_bar_frame, bg=self.BG)
        tabs_inner.pack(side="left")

        self.tab_btn_1 = tk.Button(
            tabs_inner, text="Проверить фото", command=lambda: self.switch_tab(0),
            padx=18, pady=7, font=(self.FONT_FAMILY, 9, "bold"),
            bd=0, relief="flat", cursor="hand2"
        )
        self.tab_btn_1.pack(side="left", padx=(0, 6))

        self.tab_btn_2 = tk.Button(
            tabs_inner, text="Анализ папки", command=lambda: self.switch_tab(1),
            padx=18, pady=7, font=(self.FONT_FAMILY, 9, "bold"),
            bd=0, relief="flat", cursor="hand2"
        )
        self.tab_btn_2.pack(side="left")

        # Тонкая разделительная линия под вкладками
        self.tab_baseline = tk.Frame(self.root, bg=self.BORDER, height=1)
        self.tab_baseline.pack(fill="x", padx=24, pady=(3, 6))

        # Контейнер содержимого вкладок
        self.tab_content = tk.Frame(self.root, bg=self.BG)
        self.tab_content.pack(fill="both", expand=True)

        self.single_tab = tk.Frame(self.tab_content, bg=self.BG)
        self.batch_tab = tk.Frame(self.tab_content, bg=self.BG)

        self.create_single_tab()
        self.create_batch_tab()

        self.switch_tab(0, initial=True)

        if DND_AVAILABLE:
            self.register_drop_targets(self.single_tab)
            self.register_drop_targets(self.batch_tab)

    def switch_tab(self, index: int, initial: bool = False) -> None:
        if self.busy and self.current_mode == "batch" and index != 1:
            messagebox.showinfo("OpenEOS", "Сначала дождитесь завершения операции или остановите анализ.")
            return

        self.current_tab_index = index

        if index == 0:
            self.batch_tab.pack_forget()
            self.single_tab.pack(fill="both", expand=True)

            self.tab_btn_1.config(
                bg=self.TAB_SEL_BG, fg=self.TAB_SEL_FG,
                activebackground=self.TAB_SEL_BG, activeforeground=self.TAB_SEL_FG,
                highlightthickness=1, highlightbackground=self.BORDER
            )
            self.tab_btn_2.config(
                bg=self.BG, fg=self.MUTED,
                activebackground=self.BG, activeforeground=self.TEXT,
                highlightthickness=0
            )
        else:
            self.single_tab.pack_forget()
            self.batch_tab.pack(fill="both", expand=True)

            self.tab_btn_2.config(
                bg=self.TAB_SEL_BG, fg=self.TAB_SEL_FG,
                activebackground=self.TAB_SEL_BG, activeforeground=self.TAB_SEL_FG,
                highlightthickness=1, highlightbackground=self.BORDER
            )
            self.tab_btn_1.config(
                bg=self.BG, fg=self.MUTED,
                activebackground=self.BG, activeforeground=self.TEXT,
                highlightthickness=0
            )

    def create_single_tab(self) -> None:
        page = tk.Frame(self.single_tab, bg=self.BG)
        page.pack(fill="x", padx=24, pady=(2, 6))

        # Карточка области загрузки файла (Drop Zone)
        self.drop_card = tk.Frame(
            page, bg=self.CARD, highlightbackground=self.BORDER,
            highlightthickness=1, bd=0
        )
        self.drop_card.pack(fill="x", pady=(0, 8))

        drop_inner = tk.Frame(
            self.drop_card, bg=self.ACCENT_BG,
            highlightbackground=self.ACCENT_BORDER, highlightthickness=1
        )
        drop_inner.pack(fill="x", padx=12, pady=10)

        tk.Label(
            drop_inner, text="📷", bg=self.ACCENT_BG, fg=self.TEXT,
            font=(self.FONT_FAMILY, 22)
        ).pack(pady=(2, 1))

        prompt = "Перетащите фото в эту область или выберите файл" if DND_AVAILABLE else "Выберите файл кнопкой ниже"
        tk.Label(
            drop_inner, text=prompt, bg=self.ACCENT_BG, fg=self.TEXT,
            font=(self.FONT_FAMILY, 11, "bold")
        ).pack(pady=(0, 2))

        tk.Label(
            drop_inner, text=SUPPORTED_FORMATS_LABEL,
            bg=self.ACCENT_BG, fg=self.MUTED, font=(self.FONT_FAMILY, 8, "bold")
        ).pack(pady=(0, 6))

        self.single_select_button = tk.Button(
            drop_inner, text="Выбрать файл…", command=self.select_single_file,
            padx=24, pady=6
        )
        self.style_button(
            self.single_select_button,
            bg=self.ACCENT, hover_bg=self.ACCENT_HOVER, fg="#FFFFFF",
            font=(self.FONT_FAMILY, 9, "bold")
        )
        self.single_select_button.pack(pady=(0, 3))

        # Выбранное имя файла находится прямо под кнопкой
        self.selected_file_label = tk.Label(
            drop_inner, text="Файл не выбран", bg=self.ACCENT_BG,
            fg=self.MUTED, font=(self.FONT_FAMILY, 9), anchor="center"
        )
        self.selected_file_label.pack(pady=(1, 2))

        # Карточка результатов (все элементы видны сразу без разворачивания окна)
        self.result_card = tk.Frame(
            page, bg=self.CARD, highlightbackground=self.BORDER,
            highlightthickness=1, bd=0
        )
        self.result_card.pack(fill="x")

        # Заголовок карточки без знака вопроса
        tk.Label(
            self.result_card, text="ПОКАЗАНИЕ СЧЁТЧИКА ЗАТВОРА",
            bg=self.CARD, fg=self.MUTED, font=(self.FONT_FAMILY, 9, "bold")
        ).pack(pady=(12, 2))

        value_row = tk.Frame(self.result_card, bg=self.CARD)
        value_row.pack(anchor="center", pady=(1, 4))

        self.counter_label = tk.Label(
            value_row, text="—", bg=self.CARD, fg=self.TEXT,
            font=(self.FONT_FAMILY, 44, "bold")
        )
        self.counter_label.pack(side="left", padx=(0, 14))

        self.single_status_label = tk.Label(
            value_row, text="●  Ожидает фото", bg=self.STATUS_BG_IDLE, fg=self.STATUS_FG_IDLE,
            font=(self.FONT_FAMILY, 9, "bold"), padx=10, pady=4
        )
        self.single_status_label.pack(side="left", pady=(10, 0))

        # Разделитель
        tk.Frame(self.result_card, bg=self.BORDER, height=1).pack(
            fill="x", padx=24, pady=(4, 8)
        )

        # 3 сбалансированные колонки: Камера, Дата съёмки, Ресурс затвора (?)
        meta_frame = tk.Frame(self.result_card, bg=self.CARD)
        meta_frame.pack(fill="x", padx=24, pady=(0, 14))
        meta_frame.columnconfigure(0, weight=1)
        meta_frame.columnconfigure(1, weight=1)
        meta_frame.columnconfigure(2, weight=1)

        self.single_meta = {}
        for col, (label, key) in enumerate((
            ("КАМЕРА", "model"),
            ("ДАТА СЪЁМКИ", "date"),
            ("РЕСУРС ЗАТВОРА", "rating"),
        )):
            cell = tk.Frame(meta_frame, bg=self.CARD)
            cell.grid(row=0, column=col, sticky="nsew", padx=8)

            header_box = tk.Frame(cell, bg=self.CARD)
            header_box.pack(anchor="center")

            tk.Label(
                header_box, text=label, bg=self.CARD, fg=self.MUTED,
                font=(self.FONT_FAMILY, 9, "bold")
            ).pack(side="left")

            if key == "rating":
                rating_info = tk.Label(
                    header_box, text=" (?)", bg=self.CARD, fg=self.MUTED,
                    font=(self.FONT_FAMILY, 8, "bold"), cursor="hand2"
                )
                rating_info.pack(side="left")
                self.style_tooltip_button(rating_info)

            value = tk.Label(
                cell, text="—", bg=self.CARD, fg=self.TEXT,
                font=(self.FONT_FAMILY, 11, "bold"), anchor="center"
            )
            value.pack(fill="x", pady=(4, 0))
            self.single_meta[key] = value

    def register_drop_targets(self, widget: tk.Widget) -> None:
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.on_file_drop)
        except (AttributeError, tk.TclError):
            pass

        for child in widget.winfo_children():
            self.register_drop_targets(child)

    def on_file_drop(self, event: tk.Event) -> str:
        if self.busy:
            return "break"

        try:
            dropped_paths = list(self.root.tk.splitlist(event.data))
        except (tk.TclError, TypeError):
            dropped_paths = [str(getattr(event, "data", ""))]

        # Дедупликация путей с сохранением порядка (Windows OLE может дублировать события)
        dropped_paths = list(dict.fromkeys(os.path.normpath(p.strip()) for p in dropped_paths if p.strip()))
        existing_files = [path for path in dropped_paths if os.path.isfile(path)]
        existing_dirs = [path for path in dropped_paths if os.path.isdir(path)]

        supported_files = [
            path for path in existing_files
            if os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS
        ]

        if supported_files:
            # Молча и сразу открываем первый файл без лишних модальных окон
            if self.current_tab_index != 0:
                self.switch_tab(0)
            self.start_single_file(supported_files[0])
            return "break"

        # Если перетащили папку — автоматически переключаем на пакетный анализ
        if existing_dirs:
            self.switch_tab(1)
            self.set_folder_path(existing_dirs[0])
            return "break"

        if existing_files:
            extensions = ", ".join(
                sorted({os.path.splitext(path)[1] or "без расширения" for path in existing_files})
            )
            messagebox.showwarning(
                "OpenEOS — формат не поддерживается",
                "Этот формат не входит в список поддерживаемых OpenEOS.\n\n"
                f"Получено: {extensions}\n\n"
                f"Поддерживаются: {SUPPORTED_FORMATS_LABEL.replace('·', ', ')}"
            )
        return "break"

    def select_single_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите фотографию", filetypes=SUPPORTED_FILETYPES
        )
        if path:
            self.start_single_file(path)

    def start_single_file(self, path: str) -> None:
        if self.busy:
            return
        extension = os.path.splitext(path)[1].lower()
        if extension not in SUPPORTED_EXTENSIONS:
            messagebox.showwarning(
                "OpenEOS — формат не поддерживается",
                "Выберите файл в одном из поддерживаемых форматов:\n\n"
                f"{SUPPORTED_FORMATS_LABEL.replace('·', ', ')}"
            )
            return
        if not self.check_exiftool(show_message=True):
            return

        self.single_file = path
        self.counter_label.config(text="…")
        self.set_single_status("⏳  Читаем…", self.ACCENT_BG, self.ACCENT)
        self.selected_file_label.config(
            text="📄  " + self.compact_text(os.path.basename(path), 92), fg=self.TEXT
        )
        self.single_meta["model"].config(text="—")
        self.single_meta["date"].config(text="—")
        self.single_meta["rating"].config(text="—")
        self.set_busy(True, "single")
        threading.Thread(
            target=self.single_worker, args=(path,), daemon=True
        ).start()

    def set_single_status(self, text: str, background: str, foreground: str) -> None:
        self.single_status_label.config(text=text, bg=background, fg=foreground)

    def single_worker(self, path: str) -> None:
        try:
            data = self.read_single_file(path)
        except Exception as exc:
            self.root.after(0, self.finish_single_error, str(exc))
        else:
            self.root.after(0, self.finish_single_success, data, path)

    def finish_single_success(self, data: dict, path: str) -> None:
        try:
            if not data:
                raise RuntimeError("ExifTool не вернул данные по выбранному файлу.")
            self.last_single_data = data
            shutter = data.get("ShutterCount")
            if shutter is None:
                self.counter_label.config(text="Не найден")
                self.set_single_status(
                    "●  Счётчик не найден", self.STATUS_BG_WARN, self.STATUS_FG_WARN
                )
            else:
                formatted = f"{int(shutter):,}".replace(",", " ") if str(shutter).isdigit() else str(shutter)
                self.counter_label.config(text=formatted)
                self.set_single_status("●  Готово", self.STATUS_BG_OK, self.STATUS_FG_OK)

            model_name = data.get("Model") or ""
            self.single_meta["model"].config(
                text=self.compact_text(model_name or "Не определена", 28)
            )
            self.single_meta["date"].config(
                text=format_display_date(data.get("DateTimeOriginal"))
            )

            # Подстановка паспортного ресурса затвора
            rating = get_camera_rating(model_name)
            if rating:
                rating_str = f"~{rating:,} кадров".replace(",", " ")
                self.single_meta["rating"].config(text=rating_str)
            else:
                self.single_meta["rating"].config(text="Не заявлен")

        except Exception as exc:
            self.finish_single_error(str(exc))
            return
        self.set_busy(False)

    def finish_single_error(self, message: str) -> None:
        self.set_busy(False)
        self.counter_label.config(text="—")
        self.set_single_status("✕  Ошибка чтения", self.STATUS_BG_ERR, self.STATUS_FG_ERR)
        self.single_meta["rating"].config(text="—")
        self.show_error(message)

    def create_batch_tab(self) -> None:
        page = tk.Frame(self.batch_tab, bg=self.BG)
        page.pack(fill="both", expand=True, padx=24, pady=(2, 16))

        folder_card = tk.Frame(
            page, bg=self.CARD, highlightbackground=self.BORDER,
            highlightthickness=1, bd=0
        )
        folder_card.pack(fill="x", pady=(0, 10))

        folder_row = tk.Frame(folder_card, bg=self.CARD)
        folder_row.pack(fill="x", padx=14, pady=10)

        tk.Label(
            folder_row, text="ПАПКА", bg=self.CARD, fg=self.MUTED,
            font=(self.FONT_FAMILY, 7, "bold")
        ).pack(side="left", padx=(0, 12))

        self.folder_value = tk.Label(
            folder_row, textvariable=self.folder_text, bg=self.BG,
            fg=self.TEXT, anchor="w", padx=10, pady=7,
            font=(self.FONT_FAMILY, 9)
        )
        self.folder_value.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.batch_select_button = tk.Button(
            folder_row, text="Выбрать папку…", command=self.select_batch_folder,
            padx=14, pady=7
        )
        self.style_button(
            self.batch_select_button,
            bg=self.GRAY_BTN, hover_bg=self.GRAY_BTN_HOVER, fg=self.GRAY_BTN_FG,
            font=(self.FONT_FAMILY, 9, "bold")
        )
        self.batch_select_button.pack(side="right")

        actions = tk.Frame(page, bg=self.BG)
        actions.pack(fill="x", pady=(0, 10))

        self.batch_analyze_button = tk.Button(
            actions, text="Анализировать папку", command=self.analyze_batch,
            padx=18, pady=8
        )
        self.style_button(
            self.batch_analyze_button,
            bg=self.ACCENT, hover_bg=self.ACCENT_HOVER, fg="#FFFFFF",
            font=(self.FONT_FAMILY, 9, "bold")
        )
        self.batch_analyze_button.pack(side="left")

        self.csv_button = tk.Button(
            actions, text="Экспорт CSV…", command=self.export_csv,
            padx=14, pady=8, state="disabled"
        )
        self.style_button(
            self.csv_button,
            bg=self.GRAY_BTN, hover_bg=self.GRAY_BTN_HOVER, fg=self.GRAY_BTN_FG,
            font=(self.FONT_FAMILY, 9, "bold")
        )
        self.csv_button.pack(side="left", padx=(8, 0))

        self.cancel_button = tk.Button(
            actions, text="Прервать анализ", command=self.cancel_batch,
            padx=14, pady=8, state="disabled"
        )
        self.style_button(
            self.cancel_button,
            bg=self.STATUS_BG_ERR, hover_bg=self.RED_BTN_HOVER, fg=self.STATUS_FG_ERR,
            font=(self.FONT_FAMILY, 9, "bold")
        )
        self.cancel_button.pack(side="right")

        progress_card = tk.Frame(
            page, bg=self.CARD, highlightbackground=self.BORDER,
            highlightthickness=1, bd=0
        )
        progress_card.pack(fill="x", pady=(0, 10))

        progress_inner = tk.Frame(progress_card, bg=self.CARD)
        progress_inner.pack(fill="x", padx=14, pady=8)

        progress_top = tk.Frame(progress_inner, bg=self.CARD)
        progress_top.pack(fill="x", pady=(0, 4))

        tk.Label(
            progress_top, text="Ход анализа", bg=self.CARD,
            fg=self.TEXT, font=(self.FONT_FAMILY, 9, "bold")
        ).pack(side="left")

        self.progress_percent = tk.Label(
            progress_top, text="0%", bg=self.CARD, fg=self.ACCENT,
            font=(self.FONT_FAMILY, 9, "bold")
        )
        self.progress_percent.pack(side="right")

        self.progress_canvas = tk.Canvas(
            progress_inner, height=8, bg=self.PROG_BG,
            highlightthickness=0, bd=0
        )
        self.progress_canvas.pack(fill="x", pady=(2, 4))
        self.progress_fill = self.progress_canvas.create_rectangle(
            0, 0, 0, 8, fill=self.ACCENT, outline=""
        )
        self.progress_canvas.bind("<Configure>", self.redraw_progress)

        self.batch_progress_label = tk.Label(
            progress_inner, text="Ожидает запуска.", bg=self.CARD,
            fg=self.MUTED, anchor="w", font=(self.FONT_FAMILY, 8)
        )
        self.batch_progress_label.pack(fill="x", pady=(2, 1))

        self.batch_summary = tk.Label(
            progress_inner, text="Результатов пока нет.", bg=self.CARD,
            fg=self.MUTED, anchor="w", font=(self.FONT_FAMILY, 8, "bold")
        )
        self.batch_summary.pack(fill="x")

        table_card = tk.Frame(
            page, bg=self.CARD, highlightbackground=self.BORDER,
            highlightthickness=1, bd=0
        )
        table_card.pack(fill="both", expand=True)

        table_inner = tk.Frame(table_card, bg=self.CARD)
        table_inner.pack(fill="both", expand=True, padx=4, pady=4)

        columns = ("filename", "shutter", "date", "model", "observations", "path")
        self.batch_table = ttk.Treeview(
            table_inner, columns=columns, show="headings"
        )
        headings = {
            "filename": "Файл", "shutter": "ShutterCount",
            "date": "Дата съёмки", "model": "Камера",
            "observations": "Примечания", "path": "Полный путь"
        }
        widths = {
            "filename": 160, "shutter": 110, "date": 160,
            "model": 130, "observations": 180, "path": 340
        }
        for col in columns:
            self.batch_table.heading(
                col, text=headings[col],
                command=lambda column=col: self.sort_batch_table(column, False)
            )
            self.batch_table.column(col, width=widths[col], minwidth=70)

        # Зебра-оформление строк
        self.batch_table.tag_configure("odd_row", background=self.ROW_ODD)
        self.batch_table.tag_configure("even_row", background=self.ROW_EVEN)

        yscroll = ttk.Scrollbar(
            table_inner, orient="vertical", command=self.batch_table.yview,
            style="Vertical.TScrollbar"
        )
        xscroll = ttk.Scrollbar(
            table_inner, orient="horizontal", command=self.batch_table.xview,
            style="Horizontal.TScrollbar"
        )
        self.batch_table.configure(
            yscrollcommand=yscroll.set, xscrollcommand=xscroll.set
        )
        self.batch_table.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_inner.rowconfigure(0, weight=1)
        table_inner.columnconfigure(0, weight=1)

    def redraw_progress(self, _event: tk.Event | None = None) -> None:
        width = max(0, self.progress_canvas.winfo_width())
        if width <= 1:
            return
        total = max(getattr(self, "batch_total", 0), 1)
        current = min(getattr(self, "batch_processed", 0), total)
        fraction = current / total
        self.progress_canvas.coords(
            self.progress_fill, 0, 0, int(width * fraction), 8
        )

    def set_progress(self, current: int, total: int) -> None:
        self.batch_processed = current
        self.batch_total = total
        fraction = current / total if total else 0
        self.progress_percent.config(text=f"{fraction * 100:.1f}%")
        width = max(0, self.progress_canvas.winfo_width())
        if width > 1:
            self.progress_canvas.coords(
                self.progress_fill, 0, 0, int(width * fraction), 10
            )

    def set_folder_path(self, folder: str) -> None:
        self.batch_folder_path = folder
        self.folder_text.set(self.compact_text(folder, 96))
        self.batch_results = []
        self.batch_metadata = {}
        existing_rows = self.batch_table.get_children()
        if existing_rows:
            self.batch_table.delete(*existing_rows)
        self.batch_summary.config(text="Папка выбрана. Нажмите «Анализировать папку».")
        self.set_progress(0, 0)
        self.batch_progress_label.config(text="Готово к запуску.")
        self.csv_button.config(state="disabled")

    def select_batch_folder(self) -> None:
        if self.busy:
            return
        folder = filedialog.askdirectory(title="Выберите папку с RAW-файлами")
        if folder:
            self.set_folder_path(folder)

    def analyze_batch(self) -> None:
        folder = self.batch_folder_path
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("OpenEOS", "Сначала выберите папку.")
            return
        if self.busy:
            return
        if not self.check_exiftool(show_message=True):
            return
        self.batch_cancel_event = threading.Event()
        self.batch_results = []
        self.batch_metadata = {}
        self.batch_total = 0
        self.batch_processed = 0
        self.batch_started_at = time.monotonic()
        self.batch_cancelled = False
        self.set_busy(True, "batch")
        self.set_progress(0, 0)
        self.batch_progress_label.config(text="Поиск файлов в папке…")
        self.batch_summary.config(text="Подготовка списка файлов.")
        threading.Thread(
            target=self.batch_worker, args=(folder,), daemon=True
        ).start()

    def batch_worker(self, folder: str) -> None:
        started = time.monotonic()
        results: list[dict] = []
        warnings: list[str] = []
        warnings_lock = threading.Lock()
        files: list[str] = []
        attempted = 0
        cancelled = False
        error_message: str | None = None
        process: subprocess.Popen | None = None
        stderr_thread: threading.Thread | None = None

        def drain_stderr(stderr_pipe):
            try:
                for line in stderr_pipe:
                    line = line.strip()
                    if line:
                        with warnings_lock:
                            warnings.append(line)
                            if len(warnings) > 100:
                                del warnings[:-100]
            except (OSError, ValueError):
                pass

        try:
            with os.scandir(folder) as entries:
                for index, entry in enumerate(entries, start=1):
                    if self.batch_cancel_event.is_set():
                        cancelled = True
                        break
                    try:
                        if entry.is_file(follow_symlinks=False):
                            ext = os.path.splitext(entry.name)[1].lower()
                            if ext in SUPPORTED_EXTENSIONS:
                                files.append(entry.path)
                    except OSError as exc:
                        with warnings_lock:
                            warnings.append(f"Не удалось проверить {entry.name}: {exc}")
                    if index % 500 == 0:
                        self.root.after(0, self.update_scan_status, index, len(files))

            if cancelled or self.batch_cancel_event.is_set():
                cancelled = True
            else:
                total = len(files)
                self.root.after(0, self.begin_determinate_progress, total)

                if total == 0:
                    metadata = self.build_batch_metadata(
                        started, 0, 0, warnings,
                        elapsed_override=max(time.monotonic() - started, 0.001)
                    )
                    self.root.after(0, self.finish_batch_success, [], metadata)
                    return

                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                process = subprocess.Popen(
                    [*EXIFTOOL_CMD, "-charset", "filename=UTF8", "-stay_open", "True", "-@", "-"],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=creationflags,
                    env=EXIFTOOL_ENV, cwd=EXIFTOOL_CWD,
                )
                with self.batch_process_lock:
                    self.batch_process = process
                    cancel_already_requested = self.batch_cancel_event.is_set()
                if cancel_already_requested:
                    process.terminate()
                    cancelled = True

                assert process.stdin is not None
                assert process.stdout is not None
                assert process.stderr is not None
                stderr_thread = threading.Thread(
                    target=drain_stderr, args=(process.stderr,), daemon=True
                )
                stderr_thread.start()

                execute_id = 0
                for offset in range(0, total, BATCH_CHUNK_SIZE):
                    if self.batch_cancel_event.is_set():
                        cancelled = True
                        break
                    chunk = files[offset:offset + BATCH_CHUNK_SIZE]
                    execute_id += 1
                    command_args = [
                        "-json", "-G1", "-a", "-s",
                        "-ShutterCount", "-DateTimeOriginal", "-Model",
                        "-FileName", "-Directory", *chunk,
                        f"-execute{execute_id}",
                    ]
                    for argument in command_args:
                        process.stdin.write(argument + "\n")
                    process.stdin.flush()

                    output_lines: list[str] = []
                    ready_marker = f"{{ready{execute_id}}}"
                    while True:
                        line = process.stdout.readline()
                        if line == "":
                            if self.batch_cancel_event.is_set():
                                cancelled = True
                                break
                            raise RuntimeError(
                                "ExifTool завершился до окончания блока. Проверьте установку ExifTool."
                            )
                        if line.strip() == ready_marker:
                            break
                        output_lines.append(line)

                    if cancelled or self.batch_cancel_event.is_set():
                        cancelled = True
                        break

                    output_text = "".join(output_lines).strip()
                    records = json.loads(output_text) if output_text else []
                    normalised_chunk = [
                        self.normalise_record(record, record.get("SourceFile", ""))
                        for record in records
                    ]
                    results.extend(normalised_chunk)
                    attempted += len(chunk)

                    returned = {
                        self.path_key(item.get("SourceFile", ""))
                        for item in normalised_chunk if item.get("SourceFile")
                    }
                    for item_path in chunk:
                        if self.path_key(item_path) not in returned:
                            results.append({
                                "ShutterCount": None, "CounterTag": None,
                                "DateTimeOriginal": None, "Model": None,
                                "FileName": os.path.basename(item_path),
                                "Directory": os.path.dirname(item_path),
                                "SourceFile": item_path,
                                "ShutterCount_Source": "ExifTool",
                                "ProcessingError": "ExifTool не вернул запись для файла",
                            })

                    elapsed = max(time.monotonic() - started, 0.001)
                    speed = attempted / elapsed
                    remaining = (total - attempted) / speed if speed > 0 else None
                    self.root.after(
                        0, self.update_batch_progress,
                        attempted, total, speed, remaining,
                        os.path.basename(chunk[-1])
                    )

            cancelled = cancelled or self.batch_cancel_event.is_set()

        except Exception as exc:
            error_message = str(exc)

        finally:
            if process is not None:
                try:
                    if process.poll() is None and not cancelled and not error_message:
                        if process.stdin and not process.stdin.closed:
                            process.stdin.write("-stay_open\nFalse\n")
                            process.stdin.flush()
                            process.stdin.close()
                        process.wait(timeout=15)
                    elif process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=3)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        process.kill()
                    except OSError:
                        pass
                finally:
                    for pipe in (process.stdin, process.stdout, process.stderr):
                        if pipe and not pipe.closed:
                            try:
                                pipe.close()
                            except OSError:
                                pass
                    with self.batch_process_lock:
                        if self.batch_process is process:
                            self.batch_process = None
            if stderr_thread is not None:
                stderr_thread.join(timeout=2)

        if error_message:
            self.root.after(0, self.finish_batch_error, error_message)
            return

        elapsed = max(time.monotonic() - started, 0.001)
        metadata = self.build_batch_metadata(
            started, attempted, len(files), warnings, elapsed_override=elapsed
        )
        if cancelled or self.batch_cancel_event.is_set():
            self.root.after(
                0, self.finish_batch_cancelled, results, metadata,
                attempted, len(files)
            )
        else:
            self.root.after(0, self.finish_batch_success, results, metadata)

    @staticmethod
    def path_key(path: str) -> str:
        if not path:
            return ""
        return os.path.normcase(os.path.abspath(path))

    def update_scan_status(self, entries_scanned: int, files_found: int) -> None:
        if not self.busy or self.current_mode != "batch":
            return
        self.batch_progress_label.config(
            text=(
                f"Поиск файлов: просмотрено {entries_scanned:,} элементов, "
                f"найдено {files_found:,} фото"
            ).replace(",", " ")
        )

    def begin_determinate_progress(self, total: int) -> None:
        if not self.busy:
            return
        self.batch_total = total
        self.batch_processed = 0
        self.set_progress(0, total)
        if total:
            self.batch_progress_label.config(text=f"Найдено фото: {total:,}. Начинаем чтение…".replace(",", " "))
            self.batch_summary.config(text="Чтение метаданных. Можно прервать анализ в любой момент.")
        else:
            self.batch_progress_label.config(text="Поддерживаемые фото не найдены.")
            self.batch_summary.config(text="В выбранной папке нет поддерживаемых фотографий (CR2, CR3, DNG, NEF, ARW и др.).")

    @staticmethod
    def format_duration(seconds: float | None) -> str:
        if seconds is None or seconds < 0:
            return "—"
        s = int(seconds)
        hours, remainder = divmod(s, 3600)
        minutes, seconds_part = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds_part:02d}"
        return f"{minutes:02d}:{seconds_part:02d}"

    def update_batch_progress(self, current: int, total: int, speed: float, remaining: float | None, last_file: str) -> None:
        if not self.busy:
            return
        self.set_progress(current, total)
        speed_text = f"{speed:.1f} файл/с" if speed > 0 else "расчёт скорости…"
        eta_text = self.format_duration(remaining)
        short_name = self.compact_text(last_file, 34)
        self.batch_progress_label.config(
            text=(
                f"Обработано {current:,} из {total:,}  ·  {speed_text}  ·  "
                f"осталось ~{eta_text}  ·  {short_name}"
            ).replace(",", " ")
        )
        self.batch_summary.config(text="Чтение метаданных выполняется. Исходные файлы не изменяются.")

    def cancel_batch(self) -> None:
        if not self.busy or self.current_mode != "batch":
            return
        if self.batch_cancel_event.is_set():
            return
        self.batch_cancel_event.set()
        self.cancel_button.config(state="disabled", text="Останавливаем…")
        self.batch_progress_label.config(text="Останавливаем ExifTool…")
        self.batch_summary.config(text="Будут сохранены результаты только полностью обработанных блоков.")
        with self.batch_process_lock:
            process = self.batch_process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def build_batch_metadata(self, started: float, processed: int, total: int, warnings: list[str], elapsed_override: float | None = None) -> dict:
        elapsed = elapsed_override if elapsed_override is not None else max(time.monotonic() - started, 0.001)
        return {
            "analysis_time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "app_version": APP_VERSION,
            "exiftool_version": self.get_exiftool_version(),
            "files_found": total,
            "files_attempted": processed,
            "read_seconds": elapsed,
            "average_files_per_second": processed / elapsed if elapsed > 0 else 0,
            "warnings": warnings[-100:],
        }

    def finish_batch_success(self, results: list[dict], metadata: dict) -> None:
        self.batch_results = results
        self.batch_metadata = metadata
        self.batch_cancelled = False
        self.start_table_render()

    def finish_batch_cancelled(self, results: list[dict], metadata: dict, processed: int, total: int) -> None:
        self.batch_results = results
        self.batch_metadata = metadata
        self.batch_cancelled = True
        self.batch_metadata["cancelled"] = True
        if total:
            self.set_progress(processed, total)
        self.start_table_render()

    def finish_batch_error(self, message: str) -> None:
        self.set_busy(False)
        self.batch_progress_label.config(text="Анализ не завершён.")
        self.batch_summary.config(text="Возникла ошибка. Исходные файлы не изменены.")
        self.show_error(message)

    def start_table_render(self) -> None:
        self.cancel_button.config(state="disabled", text="Формируем таблицу…")
        existing_rows = self.batch_table.get_children()
        if existing_rows:
            self.batch_table.delete(*existing_rows)
        self.render_index = 0
        self.render_readable = 0
        self.render_missing = 0
        self.csv_button.config(state="normal" if self.batch_results else "disabled")
        total = len(self.batch_results)
        if total == 0:
            if self.batch_cancelled:
                self.batch_progress_label.config(text="Анализ остановлен.")
                self.batch_summary.config(text="До остановки не было завершено ни одного блока файлов.")
            else:
                self.batch_progress_label.config(text="Готово.")
                self.batch_summary.config(text="В выбранной папке поддерживаемые фото не найдены.")
            self.set_busy(False)
            return

        stage = "Пакет остановлен. Формируем таблицу…" if self.batch_cancelled else "Чтение завершено. Формируем таблицу…"
        self.batch_progress_label.config(text=stage)
        self.root.after(10, self.insert_table_chunk)

    def insert_table_chunk(self) -> None:
        total = len(self.batch_results)
        end = min(self.render_index + TABLE_CHUNK_SIZE, total)
        for index in range(self.render_index, end):
            data = self.batch_results[index]
            shutter = data.get("ShutterCount")
            observations: list[str] = []
            if shutter is None:
                self.render_missing += 1
                shutter_text = "Не найден"
                observations.append(data.get("ProcessingError") or "ShutterCount отсутствует")
            else:
                self.render_readable += 1
                shutter_text = f"{int(shutter):,}".replace(",", " ") if str(shutter).isdigit() else str(shutter)

            if not data.get("DateTimeOriginal"):
                observations.append("Нет даты")
            if not data.get("Model"):
                observations.append("Нет модели")
            if not observations:
                observations.append("—")

            tag = "even_row" if index % 2 == 0 else "odd_row"
            self.batch_table.insert(
                "", "end",
                values=(
                    data.get("FileName") or "—",
                    shutter_text,
                    format_display_date(data.get("DateTimeOriginal")),
                    data.get("Model") or "—",
                    "; ".join(observations),
                    data.get("SourceFile", "")
                ),
                tags=(tag,)
            )
        self.render_index = end
        if end < total:
            self.batch_progress_label.config(
                text=f"Формируем таблицу результатов: {end:,} из {total:,}".replace(",", " ")
            )
            self.root.after(10, self.insert_table_chunk)
            return

        attempted = self.batch_metadata.get("files_attempted", total)
        elapsed = self.batch_metadata.get("read_seconds", 0)
        speed = self.batch_metadata.get("average_files_per_second", 0)
        duration = self.format_duration(elapsed)
        speed_text = f"{speed:.1f} файлов/с" if speed else "—"

        if self.batch_cancelled:
            expected = self.batch_metadata.get("files_found", attempted)
            self.batch_progress_label.config(
                text=f"Остановлено: обработано {attempted:,} из {expected:,}".replace(",", " ")
            )
            self.batch_summary.config(
                text=(
                    f"Показаны результаты до остановки: в таблице {total:,} записей, "
                    f"ShutterCount найден в {self.render_readable:,}."
                ).replace(",", " ")
            )
        else:
            self.set_progress(total, total)
            self.batch_progress_label.config(
                text=f"Готово: {attempted:,} файлов за {duration}  ·  средняя скорость {speed_text}".replace(",", " ")
            )
            self.batch_summary.config(
                text=(
                    f"Результатов: {total:,}  ·  ShutterCount найден в {self.render_readable:,}  ·  "
                    f"без счётчика: {self.render_missing:,}."
                ).replace(",", " ")
            )
        self.set_busy(False)

    def sort_batch_table(self, column: str, reverse: bool) -> None:
        rows = [(self.batch_table.set(item, column), item) for item in self.batch_table.get_children("")]
        if column == "shutter":
            def key_fn(row):
                try:
                    return (0, int(str(row[0]).replace(" ", "")))
                except (TypeError, ValueError):
                    return (1, str(row[0]).lower())
        else:
            key_fn = lambda row: str(row[0]).lower()
        rows.sort(key=key_fn, reverse=reverse)
        for index, (_, item) in enumerate(rows):
            self.batch_table.move(item, "", index)
            tag = "even_row" if index % 2 == 0 else "odd_row"
            self.batch_table.item(item, tags=(tag,))
        self.batch_table.heading(
            column, command=lambda: self.sort_batch_table(column, not reverse)
        )

    def check_exiftool(self, show_message: bool = False) -> bool:
        ver = self.get_exiftool_version()
        if ver and ver != "Не удалось определить":
            return True
        message = (
            "Не удалось инициализировать или запустить ExifTool.\n\n"
            f"Команда: {' '.join(EXIFTOOL_CMD)}\n\n"
            "Убедитесь, что ExifTool установлен в C:\\Tools\\ExifTool или корректно собран в exe."
        )
        if show_message:
            messagebox.showerror("OpenEOS", message)
        return False

    @staticmethod
    def get_tag(record: dict, tag: str, preferred_groups: tuple = ()) -> tuple[any, str | None]:
        if tag in record:
            return record[tag], tag
        candidates = [key for key in record if key.split(":")[-1].lower() == tag.lower()]
        for group in preferred_groups:
            for key in candidates:
                if key.split(":")[0].lower() == group.lower():
                    return record[key], key
        if candidates:
            key = candidates[0]
            return record[key], key
        return None, None

    def normalise_record(self, record: dict, fallback_path: str = "") -> dict:
        shutter, counter_tag = self.get_tag(record, "ShutterCount", ("Track4",))
        date, _ = self.get_tag(record, "DateTimeOriginal", ("ExifIFD", "EXIF"))
        model, _ = self.get_tag(record, "Model", ("IFD0", "EXIF"))
        filename, _ = self.get_tag(record, "FileName", ("File", "System"))
        directory, _ = self.get_tag(record, "Directory", ("File", "System"))
        source_path = record.get("SourceFile") or fallback_path
        if not filename and source_path:
            filename = os.path.basename(source_path)
        if not directory and source_path:
            directory = os.path.dirname(source_path)
        return {
            "ShutterCount": shutter, "CounterTag": counter_tag,
            "DateTimeOriginal": date, "Model": model,
            "FileName": filename, "Directory": directory,
            "SourceFile": source_path, "ShutterCount_Source": "ExifTool",
        }

    def read_single_file(self, path: str) -> dict:
        command = [
            *EXIFTOOL_CMD, "-json", "-G1", "-a", "-s", "-ShutterCount",
            "-DateTimeOriginal", "-Model", "-FileName", "-Directory", path
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            command, capture_output=True, text=True,
            encoding="utf-8", errors="replace", creationflags=creationflags,
            env=EXIFTOOL_ENV, cwd=EXIFTOOL_CWD,
        )
        if result.returncode != 0 and not result.stdout.strip():
            raise RuntimeError(result.stderr.strip() or "ExifTool не смог прочитать файл.")
        if not result.stdout.strip():
            raise RuntimeError("ExifTool не вернул данные.")
        records = json.loads(result.stdout)
        if not records:
            return {}
        return self.normalise_record(records[0], path)

    @staticmethod
    def get_exiftool_version() -> str:
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                [*EXIFTOOL_CMD, "-ver"], capture_output=True, text=True,
                encoding="utf-8", errors="replace", creationflags=creationflags,
                env=EXIFTOOL_ENV, cwd=EXIFTOOL_CWD,
            )
            return result.stdout.strip() if result.returncode == 0 else "Не удалось определить"
        except OSError:
            return "Не удалось определить"

    def export_csv(self) -> None:
        if self.busy:
            return
        if not self.batch_results:
            messagebox.showwarning("OpenEOS", "Сначала выполните пакетный анализ.")
            return
        path = filedialog.asksaveasfilename(
            title="Сохранить результаты", defaultextension=".csv",
            filetypes=[("CSV", "*.csv")]
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(["OpenEOS_version", APP_VERSION])
                writer.writerow(["ExifTool_version", self.batch_metadata.get("exiftool_version", "")])
                writer.writerow(["Analysis_time", self.batch_metadata.get("analysis_time", "")])
                writer.writerow(["Files_found", self.batch_metadata.get("files_found", "")])
                writer.writerow(["Files_attempted", self.batch_metadata.get("files_attempted", "")])
                writer.writerow(["Read_time_seconds", round(self.batch_metadata.get("read_seconds", 0), 2)])
                writer.writerow(["Average_files_per_second", round(self.batch_metadata.get("average_files_per_second", 0), 2)])
                writer.writerow(["Cancelled_by_user", bool(self.batch_metadata.get("cancelled", False))])
                writer.writerow([])
                writer.writerow([
                    "filename", "shutter_count", "counter_tag", "date_time_original",
                    "model", "directory", "full_path", "processing_error", "source"
                ])
                for data in self.batch_results:
                    writer.writerow([
                        data.get("FileName", ""), data.get("ShutterCount", ""),
                        data.get("CounterTag", ""), data.get("DateTimeOriginal", ""),
                        data.get("Model", ""), data.get("Directory", ""),
                        data.get("SourceFile", ""), data.get("ProcessingError", ""),
                        "ExifTool"
                    ])
            messagebox.showinfo("OpenEOS", "CSV сохранён.")
        except Exception as exc:
            self.show_error(str(exc))

    def set_busy(self, busy: bool, mode: str | None = None) -> None:
        self.busy = busy
        self.current_mode = mode if busy else None
        state = "disabled" if busy else "normal"
        self.single_select_button.config(state=state)
        self.batch_select_button.config(state=state)
        self.batch_analyze_button.config(state=state)
        self.csv_button.config(state="disabled" if busy or not self.batch_results else "normal")
        if busy and mode == "batch":
            self.cancel_button.config(state="normal", text="Прервать анализ")
        else:
            self.cancel_button.config(state="disabled", text="Прервать анализ")

    def show_error(self, error: str) -> None:
        messagebox.showerror("OpenEOS — ошибка", error)


if __name__ == "__main__":
    root = ROOT_CLASS()
    try:
        root.withdraw()
    except Exception:
        pass
    theme = detect_system_theme()
    bg = THEMES[theme]["BG"]
    root.configure(bg=bg)
    apply_titlebar_theme(root, theme == "dark")
    app = OpenEOSApp(root)
    root.mainloop()
