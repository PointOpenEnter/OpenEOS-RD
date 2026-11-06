"""
OpenEOS — Профессиональная утилита проверки пробега и ресурса затвора фотокамер.
Community Edition (Версия для сообщества / GitHub).
100% автономная работа без внешних зависимостей (ExifTool/Perl не требуются).
Поддерживает прямое чтение:
  - Sony (.ARW, .JPG) — чистый механический затвор (MakerNotes 0x9050)
  - Nikon (.NEF, .JPG) — кумулятивный пробег (MakerNotes 0x00A7)
  - Canon (.CR3, .CR2) — Track4 DIGIC X / EXIF
  - Canon (.XML) — заводской сервисный отчёт процедуры CamInfo_Debug
  - DNG, Fujifilm, Panasonic, Olympus
  - Подготовка сервисной SD-карты Canon с записью загрузочного сектора SCRIPT
"""
from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cbasic_card
import raw_engine

APP_TITLE = "OpenEOS"
APP_SUBTITLE = "Определение реального пробега и ресурса затвора фотокамер"
APP_VERSION = "0.6.0"
APP_EDITION = "COMMUNITY"

def get_resource_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    if "NUITKA_ONEFILE_TEMP" in os.environ:
        return Path(os.environ["NUITKA_ONEFILE_TEMP"])
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _test = TkinterDnD.Tk()
    _test.destroy()
    DND_AVAILABLE = True
    ROOT_CLASS = TkinterDnD.Tk
except Exception:
    DND_FILES = None
    DND_AVAILABLE = False
    ROOT_CLASS = tk.Tk

def setup_windows_dpi():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

def detect_system_theme() -> str:
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return "dark" if val == 0 else "light"
        except Exception:
            pass
    return "dark"

def apply_titlebar_theme(root: tk.Tk, dark: bool) -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            hwnd = None
            frame = root.wm_frame()
            if frame:
                hwnd = int(frame, 16)
            if not hwnd:
                hwnd = root.winfo_id()
            if not hwnd:
                return
            root_hwnd = ctypes.windll.user32.GetAncestor(ctypes.c_void_p(hwnd), ctypes.c_uint(2))
            if root_hwnd:
                hwnd = root_hwnd

            val = ctypes.c_int(1 if dark else 0)
            res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), ctypes.c_uint(20), ctypes.byref(val), ctypes.sizeof(val)
            )
            if res != 0:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd), ctypes.c_uint(19), ctypes.byref(val), ctypes.sizeof(val)
                )
        except Exception:
            pass

THEMES = {
    "light": {
        "BG": "#F5F6F8", "CARD": "#FFFFFF", "CARD_BORDER": "#E1E4E8",
        "TEXT": "#1A1A1A", "MUTED": "#666666", "SUBTLE": "#8E8E93", "BORDER": "#E1E4E8",
        "ACCENT": "#0066CC", "ACCENT_HOVER": "#0052A3", "ACCENT_BG": "#EBF3FB",
        "GRAY_BTN": "#E8ECEF", "GRAY_BTN_HOVER": "#DCE1E5", "GRAY_BTN_FG": "#1A1A1A",
        "STATUS_BG_IDLE": "#E8ECEF", "STATUS_FG_IDLE": "#666666",
        "STATUS_BG_OK": "#E6F4EA", "STATUS_FG_OK": "#137333",
        "STATUS_BG_WARN": "#FEF7E0", "STATUS_FG_WARN": "#B06000",
        "STATUS_BG_ERR": "#FCE8E6", "STATUS_FG_ERR": "#C5221F",
        "TAB_BG": "#F5F6F8", "TAB_SEL_BG": "#FFFFFF", "TAB_SEL_FG": "#0066CC",
        "BADGE_BG": "#E8ECEF", "BADGE_FG": "#444444",
    },
    "dark": {
        "BG": "#18191A", "CARD": "#242526", "CARD_BORDER": "#38393B",
        "TEXT": "#E4E6EB", "MUTED": "#B0B3B8", "SUBTLE": "#747679", "BORDER": "#38393B",
        "ACCENT": "#2D88FF", "ACCENT_HOVER": "#4599FF", "ACCENT_BG": "#1C2A3A",
        "GRAY_BTN": "#3A3B3C", "GRAY_BTN_HOVER": "#4E4F50", "GRAY_BTN_FG": "#E4E6EB",
        "STATUS_BG_IDLE": "#3A3B3C", "STATUS_FG_IDLE": "#B0B3B8",
        "STATUS_BG_OK": "#1C3829", "STATUS_FG_OK": "#4CD964",
        "STATUS_BG_WARN": "#423214", "STATUS_FG_WARN": "#F9AB00",
        "STATUS_BG_ERR": "#442326", "STATUS_FG_ERR": "#F28B82",
        "TAB_BG": "#18191A", "TAB_SEL_BG": "#242526", "TAB_SEL_FG": "#2D88FF",
        "BADGE_BG": "#3A3B3C", "BADGE_FG": "#B0B3B8",
    },
}

SUPPORTED_FILETYPES = [
    ("Все форматы OpenEOS", "*.CR2 *.CR3 *.ARW *.NEF *.RAF *.DNG *.JPG *.JPEG *.XML"),
    ("Sony RAW (ARW)", "*.ARW"),
    ("Nikon RAW (NEF)", "*.NEF"),
    ("Canon RAW (CR3, CR2)", "*.CR3 *.CR2"),
    ("Canon Сервисный XML", "*.XML"),
    ("DNG / Fujifilm", "*.DNG *.RAF"),
    ("Все файлы", "*.*"),
]


def make_text_selectable_and_copyable(txt_widget: tk.Text, root: tk.Tk, colors: dict):
    def _copy(event=None):
        try:
            sel = txt_widget.get("sel.first", "sel.last")
            if sel:
                root.clipboard_clear()
                root.clipboard_append(sel)
                return "break"
        except Exception:
            pass
        return "break"

    def _select_all(event=None):
        txt_widget.tag_add("sel", "1.0", "end")
        return "break"

    txt_widget.bind("<Control-c>", _copy)
    txt_widget.bind("<Control-C>", _copy)
    txt_widget.bind("<Control-Insert>", _copy)
    txt_widget.bind("<Control-a>", _select_all)
    txt_widget.bind("<Control-A>", _select_all)

    menu = tk.Menu(txt_widget, tearoff=0, bg=colors["CARD"], fg=colors["TEXT"], activebackground=colors["ACCENT"], activeforeground="#FFFFFF")
    menu.add_command(label="Копировать выделенное", command=_copy)
    menu.add_command(label="Выделить всё", command=_select_all)

    def _show_menu(event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    txt_widget.bind("<Button-3>", _show_menu)


class OpenEOSCommunityApp:
    FONT_FAMILY = "Segoe UI" if sys.platform == "win32" else "Helvetica"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.theme_name = detect_system_theme()
        self.colors = THEMES[self.theme_name]

        self.root.title(f"{APP_TITLE} {APP_VERSION} [{APP_EDITION}] — {APP_SUBTITLE}")
        self.root.configure(bg=self.colors["BG"])

        # Фиксированные эргономичные размеры окна 920 × 650
        self.setup_geometry(920, 650)
        apply_titlebar_theme(self.root, self.theme_name == "dark")

        self.current_tab = 0
        self.last_file_report: dict | None = None

        self.create_ui()

    def setup_geometry(self, width: int, height: int):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(920, 650)

    def toggle_theme(self):
        saved_report = self.last_file_report
        saved_tab = getattr(self, "current_tab", 0)

        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.colors = THEMES[self.theme_name]
        apply_titlebar_theme(self.root, self.theme_name == "dark")
        for child in self.root.winfo_children():
            child.destroy()
        self.create_ui()

        # Восстанавливаем вкладку и данные отчёта
        self.switch_tab(saved_tab)
        if saved_report:
            self.display_file_result(saved_report)

    def create_ui(self):
        self.root.configure(bg=self.colors["BG"])

        # ===================================================================
        # Хедер (Заголовок, переключатель темы, памятка)
        # ===================================================================
        header = tk.Frame(self.root, bg=self.colors["BG"])
        header.pack(fill="x", padx=24, pady=(14, 8))

        # Сначала упаковываем правую часть — кнопки всегда на виду и не обрезаются
        right_h = tk.Frame(header, bg=self.colors["BG"])
        right_h.pack(side="right")

        guide_btn = tk.Button(
            right_h, text="📘 Памятка покупателя", font=(self.FONT_FAMILY, 9, "bold"),
            bg=self.colors["GRAY_BTN"], fg=self.colors["GRAY_BTN_FG"],
            activebackground=self.colors["GRAY_BTN_HOVER"], activeforeground=self.colors["TEXT"],
            bd=0, relief="flat", padx=12, pady=5, cursor="hand2",
            command=self.show_buyer_guide
        )
        guide_btn.pack(side="left", padx=(0, 8))

        theme_txt = "☀️ Светлая" if self.theme_name == "dark" else "🌙 Тёмная"
        theme_btn = tk.Button(
            right_h, text=theme_txt, font=(self.FONT_FAMILY, 9),
            bg=self.colors["GRAY_BTN"], fg=self.colors["GRAY_BTN_FG"],
            activebackground=self.colors["GRAY_BTN_HOVER"], activeforeground=self.colors["TEXT"],
            bd=0, relief="flat", padx=10, pady=5, cursor="hand2",
            command=self.toggle_theme
        )
        theme_btn.pack(side="left")

        # Левая часть: название и единый бейдж версии
        left_h = tk.Frame(header, bg=self.colors["BG"])
        left_h.pack(side="left", fill="x", expand=True)

        tk.Label(
            left_h, text=APP_TITLE, font=(self.FONT_FAMILY, 19, "bold"),
            bg=self.colors["BG"], fg=self.colors["TEXT"]
        ).pack(side="left")

        tk.Label(
            left_h, text=f"{APP_EDITION} v{APP_VERSION}", font=(self.FONT_FAMILY, 8, "bold"),
            bg=self.colors["ACCENT"], fg="#FFFFFF", padx=8, pady=2
        ).pack(side="left", padx=(10, 12))

        tk.Label(
            left_h, text=APP_SUBTITLE, font=(self.FONT_FAMILY, 9),
            bg=self.colors["BG"], fg=self.colors["MUTED"]
        ).pack(side="left")

        # ===================================================================
        # Вкладки (2 чистые вкладки для публичного релиза)
        # ===================================================================
        tab_bar = tk.Frame(self.root, bg=self.colors["BG"])
        tab_bar.pack(fill="x", padx=24, pady=(4, 0))

        self.tab_btn_0 = tk.Button(
            tab_bar, text="📁  Анализ файлов (RAW / XML / EXIF)", font=(self.FONT_FAMILY, 10, "bold"),
            bd=0, relief="flat", padx=16, pady=7, cursor="hand2",
            command=lambda: self.switch_tab(0)
        )
        self.tab_btn_0.pack(side="left", padx=(0, 6))

        self.tab_btn_1 = tk.Button(
            tab_bar, text="💳  Подготовка SD-карты (Canon)", font=(self.FONT_FAMILY, 10, "bold"),
            bd=0, relief="flat", padx=16, pady=7, cursor="hand2",
            command=lambda: self.switch_tab(1)
        )
        self.tab_btn_1.pack(side="left")

        divider = tk.Frame(self.root, bg=self.colors["BORDER"], height=1)
        divider.pack(fill="x", padx=24, pady=(4, 8))

        self.container = tk.Frame(self.root, bg=self.colors["BG"])
        self.container.pack(fill="both", expand=True, padx=24, pady=(0, 14))

        self.frame_files = tk.Frame(self.container, bg=self.colors["BG"])
        self.frame_card = tk.Frame(self.container, bg=self.colors["BG"])

        self.build_files_tab()
        self.build_card_tab()

        self.switch_tab(0)

        if DND_AVAILABLE:
            self.register_dnd(self.root)

    def switch_tab(self, idx: int):
        self.current_tab = idx
        if idx == 0:
            self.frame_card.pack_forget()
            self.frame_files.pack(fill="both", expand=True)
            self.tab_btn_0.config(
                bg=self.colors["TAB_SEL_BG"], fg=self.colors["TAB_SEL_FG"],
                highlightthickness=1, highlightbackground=self.colors["BORDER"]
            )
            self.tab_btn_1.config(
                bg=self.colors["BG"], fg=self.colors["MUTED"],
                highlightthickness=0
            )
        else:
            self.frame_files.pack_forget()
            self.frame_card.pack(fill="both", expand=True)
            self.tab_btn_1.config(
                bg=self.colors["TAB_SEL_BG"], fg=self.colors["TAB_SEL_FG"],
                highlightthickness=1, highlightbackground=self.colors["BORDER"]
            )
            self.tab_btn_0.config(
                bg=self.colors["BG"], fg=self.colors["MUTED"],
                highlightthickness=0
            )

    # -----------------------------------------------------------------------
    # Вкладка 1: Анализ файлов
    # -----------------------------------------------------------------------
    def build_files_tab(self):
        # Зона загрузки / выбора файла
        self.drop_card = tk.Frame(
            self.frame_files, bg=self.colors["CARD"],
            highlightbackground=self.colors["CARD_BORDER"], highlightthickness=1
        )
        self.drop_card.pack(fill="x", pady=(0, 10))

        inner_drop = tk.Frame(self.drop_card, bg=self.colors["ACCENT_BG"], padx=16, pady=12)
        inner_drop.pack(fill="x", padx=6, pady=6)

        dnd_text = "Перетащите сюда RAW-файл (ARW, NEF, CR3, CR2) или CAM_INFO.XML" if DND_AVAILABLE else "Выберите фотографию или сервисный XML-файл для анализа"
        tk.Label(
            inner_drop, text=dnd_text, font=(self.FONT_FAMILY, 11, "bold"),
            bg=self.colors["ACCENT_BG"], fg=self.colors["TEXT"]
        ).pack(pady=(0, 2))

        tk.Label(
            inner_drop, text="Sony ARW (0x9050 мех.)  ·  Nikon NEF (0x00A7)  ·  Canon CR3 (Track4)  ·  Canon CAM_INFO.XML",
            font=(self.FONT_FAMILY, 8, "bold"), bg=self.colors["ACCENT_BG"], fg=self.colors["MUTED"]
        ).pack(pady=(0, 8))

        btn_row = tk.Frame(inner_drop, bg=self.colors["ACCENT_BG"])
        btn_row.pack()

        choose_btn = tk.Button(
            btn_row, text="Выбрать файл на диске…", font=(self.FONT_FAMILY, 9, "bold"),
            bg=self.colors["ACCENT"], fg="#FFFFFF", activebackground=self.colors["ACCENT_HOVER"],
            activeforeground="#FFFFFF", bd=0, relief="flat", padx=18, pady=6, cursor="hand2",
            command=self.choose_file_dialog
        )
        choose_btn.pack(side="left", padx=(0, 10))

        self.file_name_lbl = tk.Label(
            btn_row, text="Файл ещё не выбран", font=(self.FONT_FAMILY, 9),
            bg=self.colors["ACCENT_BG"], fg=self.colors["MUTED"]
        )
        self.file_name_lbl.pack(side="left")

        # Карточка результатов
        self.result_card = tk.Frame(
            self.frame_files, bg=self.colors["CARD"],
            highlightbackground=self.colors["CARD_BORDER"], highlightthickness=1, padx=20, pady=12
        )
        self.result_card.pack(fill="x", pady=(0, 10))

        top_val_frame = tk.Frame(self.result_card, bg=self.colors["CARD"])
        top_val_frame.pack(fill="x", pady=(0, 4))

        tk.Label(
            top_val_frame, text="ПОКАЗАНИЕ СЧЁТЧИКА ЗАТВОРА", font=(self.FONT_FAMILY, 8, "bold"),
            bg=self.colors["CARD"], fg=self.colors["MUTED"]
        ).pack(side="left")

        self.counter_type_badge = tk.Label(
            top_val_frame, text="ОЖИДАНИЕ", font=(self.FONT_FAMILY, 8, "bold"),
            bg=self.colors["STATUS_BG_IDLE"], fg=self.colors["STATUS_FG_IDLE"], padx=8, pady=2
        )
        self.counter_type_badge.pack(side="right")

        big_row = tk.Frame(self.result_card, bg=self.colors["CARD"])
        big_row.pack(fill="x", pady=(0, 8))

        self.big_counter_lbl = tk.Label(
            big_row, text="—", font=(self.FONT_FAMILY, 44, "bold"),
            bg=self.colors["CARD"], fg=self.colors["TEXT"]
        )
        self.big_counter_lbl.pack(side="left")

        self.status_pill = tk.Label(
            big_row, text="●  Ожидает файл", font=(self.FONT_FAMILY, 9, "bold"),
            bg=self.colors["STATUS_BG_IDLE"], fg=self.colors["STATUS_FG_IDLE"], padx=10, pady=5
        )
        self.status_pill.pack(side="left", padx=(18, 0), pady=(12, 0))

        stats_frame = tk.Frame(self.result_card, bg=self.colors["CARD"])
        stats_frame.pack(fill="x", pady=(6, 0))
        stats_frame.columnconfigure(0, weight=1)
        stats_frame.columnconfigure(1, weight=1)
        stats_frame.columnconfigure(2, weight=1)

        c1 = tk.Frame(stats_frame, bg=self.colors["CARD"])
        c1.grid(row=0, column=0, sticky="nsew", padx=6)
        tk.Label(c1, text="МОДЕЛЬ КАМЕРЫ", font=(self.FONT_FAMILY, 8, "bold"), bg=self.colors["CARD"], fg=self.colors["MUTED"]).pack(anchor="w")
        self.val_model = tk.Label(c1, text="—", font=(self.FONT_FAMILY, 11, "bold"), bg=self.colors["CARD"], fg=self.colors["TEXT"])
        self.val_model.pack(anchor="w", pady=(2, 0))

        c2 = tk.Frame(stats_frame, bg=self.colors["CARD"])
        c2.grid(row=0, column=1, sticky="nsew", padx=6)
        tk.Label(c2, text="ДАТА СЪЁМКИ", font=(self.FONT_FAMILY, 8, "bold"), bg=self.colors["CARD"], fg=self.colors["MUTED"]).pack(anchor="w")
        self.val_date = tk.Label(c2, text="—", font=(self.FONT_FAMILY, 11, "bold"), bg=self.colors["CARD"], fg=self.colors["TEXT"])
        self.val_date.pack(anchor="w", pady=(2, 0))

        c3 = tk.Frame(stats_frame, bg=self.colors["CARD"])
        c3.grid(row=0, column=2, sticky="nsew", padx=6)
        tk.Label(c3, text="ИЗНОС МЕХАНИКИ", font=(self.FONT_FAMILY, 8, "bold"), bg=self.colors["CARD"], fg=self.colors["MUTED"]).pack(anchor="w")
        self.val_wear = tk.Label(c3, text="—", font=(self.FONT_FAMILY, 11, "bold"), bg=self.colors["CARD"], fg=self.colors["TEXT"])
        self.val_wear.pack(anchor="w", pady=(2, 0))

        # Карточка подробного отчёта (Выделяемый текст + копирование/сохранение)
        details_card = tk.Frame(
            self.frame_files, bg=self.colors["CARD"],
            highlightbackground=self.colors["CARD_BORDER"], highlightthickness=1, padx=14, pady=10
        )
        details_card.pack(fill="both", expand=True)

        bar_actions = tk.Frame(details_card, bg=self.colors["CARD"])
        bar_actions.pack(fill="x", pady=(0, 6))

        tk.Label(
            bar_actions, text="ПОДРОБНЫЙ ОТЧЁТ (текст доступен для выделения и копирования):",
            font=(self.FONT_FAMILY, 8, "bold"), bg=self.colors["CARD"], fg=self.colors["MUTED"]
        ).pack(side="left")

        self.btn_copy_file = tk.Button(
            bar_actions, text="📋 Копировать", font=(self.FONT_FAMILY, 8, "bold"),
            bg=self.colors["GRAY_BTN"], fg=self.colors["GRAY_BTN_FG"],
            activebackground=self.colors["GRAY_BTN_HOVER"], activeforeground=self.colors["TEXT"],
            bd=0, relief="flat", padx=10, pady=3, cursor="hand2", state="disabled",
            command=self.copy_file_report
        )
        self.btn_copy_file.pack(side="right", padx=(6, 0))

        self.btn_save_file = tk.Button(
            bar_actions, text="💾 Сохранить отчёт (.txt)", font=(self.FONT_FAMILY, 8, "bold"),
            bg=self.colors["GRAY_BTN"], fg=self.colors["GRAY_BTN_FG"],
            activebackground=self.colors["GRAY_BTN_HOVER"], activeforeground=self.colors["TEXT"],
            bd=0, relief="flat", padx=10, pady=3, cursor="hand2", state="disabled",
            command=self.save_file_report
        )
        self.btn_save_file.pack(side="right")

        self.txt_file_details = tk.Text(
            details_card, bg=self.colors["BG"], fg=self.colors["TEXT"],
            font=(self.FONT_FAMILY, 9), relief="flat", bd=0, wrap="word",
            padx=10, pady=8, insertbackground=self.colors["TEXT"]
        )
        self.txt_file_details.pack(fill="both", expand=True)
        self.txt_file_details.insert("end", "Перетащите снимок в окно или нажмите «Выбрать файл» для получения исчерпывающей информации о пробеге.")
        self.txt_file_details.config(state="disabled")
        make_text_selectable_and_copyable(self.txt_file_details, self.root, self.colors)

    def choose_file_dialog(self):
        file_path = filedialog.askopenfilename(title="Выберите снимок с камеры", filetypes=SUPPORTED_FILETYPES)
        if file_path:
            self.process_file(file_path)

    def register_dnd(self, widget: tk.Widget):
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.on_drop_event)
        except Exception:
            pass
        for child in widget.winfo_children():
            self.register_dnd(child)

    def on_drop_event(self, event):
        raw = getattr(event, "data", "")
        paths = self.root.tk.splitlist(raw) if hasattr(self.root, "tk") else [raw]
        clean_paths = [os.path.normpath(p.strip("{} \t\r\n")) for p in paths if p.strip("{} \t\r\n")]
        valid_files = [p for p in clean_paths if os.path.isfile(p)]
        if valid_files:
            if self.current_tab != 0:
                self.switch_tab(0)
            self.process_file(valid_files[0])

    def process_file(self, path: str):
        self.file_name_lbl.config(text=f"📄 {os.path.basename(path)}")
        self.big_counter_lbl.config(text="…")
        self.status_pill.config(text="⏳ Чтение…", bg=self.colors["ACCENT_BG"], fg=self.colors["ACCENT"])
        self.root.update_idletasks()

        def _worker():
            try:
                data = raw_engine.analyze_file(path)
                self.root.after(0, self.on_file_success, data)
            except Exception as exc:
                self.root.after(0, self.on_file_error, str(exc))

        threading.Thread(target=_worker, daemon=True).start()

    def on_file_success(self, data: dict):
        self.last_file_report = data
        shutter = data.get("shutter_count")
        if shutter is not None:
            self.big_counter_lbl.config(text=f"{shutter:,}".replace(",", " "))
            self.status_pill.config(text="●  Счётчик прочитан", bg=self.colors["STATUS_BG_OK"], fg=self.colors["STATUS_FG_OK"])
        else:
            self.big_counter_lbl.config(text="Не найден")
            self.status_pill.config(text="●  Счётчик отсутствует в метаданных", bg=self.colors["STATUS_BG_WARN"], fg=self.colors["STATUS_FG_WARN"])

        st_type = data.get("shutter_type", "unknown")
        if st_type == "mechanical":
            self.counter_type_badge.config(text="МЕХАНИЧЕСКИЙ ЗАТВОР", bg=self.colors["STATUS_BG_OK"], fg=self.colors["STATUS_FG_OK"])
        elif st_type == "total":
            self.counter_type_badge.config(text="КУМУЛЯТИВНЫЙ (МЕХ.+ЭЛЕКТР.)", bg=self.colors["STATUS_BG_WARN"], fg=self.colors["STATUS_FG_WARN"])
        else:
            self.counter_type_badge.config(text="ОБЩИЙ", bg=self.colors["STATUS_BG_IDLE"], fg=self.colors["STATUS_FG_IDLE"])

        self.val_model.config(text=data.get("model") or "Не определена")
        self.val_date.config(text=data.get("date") or "—")

        wear = data.get("wear_percent")
        rating = data.get("rating")
        if wear is not None and rating:
            self.val_wear.config(text=f"{wear}% (ресурс ~{rating:,} кадров)".replace(",", " "))
        elif rating:
            self.val_wear.config(text=f"Паспортный ~{rating:,} кадров".replace(",", " "))
        else:
            self.val_wear.config(text="Не заявлен")

        lines = [
            f"Файл:           {data['file_name']} ({data['file_size_mb']} МБ)",
            f"Камера:         {data['model']}",
            f"Дата снимка:    {data['date']}",
            f"Пробег затвора: {f'{shutter:,}'.replace(',', ' ') if shutter is not None else 'Не найден'}",
        ]
        if data.get("release_total"):
            lines.append(f"Всего спусков:  {data['release_total']:,}".replace(",", " "))
        if wear is not None:
            lines.append(f"Износ ресурса:  {wear}% от заявленного ресурса {rating:,} кадров".replace(",", " "))
        lines.append(f"Источник:       {data['source']}")
        lines.append("-" * 65)
        lines.append("ЭКСПЕРТНЫЙ КОММЕНТАРИЙ OPENEOS:")
        lines.append(data.get("vendor_advice") or "—")
        if data.get("notes"):
            lines.append("\nТЕХНИЧЕСКИЕ ДЕТАЛИ:")
            for n in data["notes"]:
                lines.append(f"  • {n}")
        if data.get("errors"):
            lines.append("\nЖУРНАЛ СЕРВИСНЫХ ОШИБОК ИЗ ДАМПА:")
            for e in data["errors"]:
                lines.append(f"  • Код {e.get('code')} (повторений: {e.get('count', 1)}) — {e.get('name', '')}")

        self.txt_file_details.config(state="normal")
        self.txt_file_details.delete("1.0", "end")
        self.txt_file_details.insert("end", "\n".join(lines))
        self.txt_file_details.config(state="disabled")

        self.btn_copy_file.config(state="normal")
        self.btn_save_file.config(state="normal")

    def on_file_error(self, err_msg: str):
        self.big_counter_lbl.config(text="Ошибка")
        self.status_pill.config(text="✕  Сбой чтения", bg=self.colors["STATUS_BG_ERR"], fg=self.colors["STATUS_FG_ERR"])
        self.txt_file_details.config(state="normal")
        self.txt_file_details.delete("1.0", "end")
        self.txt_file_details.insert("end", f"Ошибка анализа файла:\n{err_msg}")
        self.txt_file_details.config(state="disabled")

    def copy_file_report(self):
        text = self.txt_file_details.get("1.0", "end").strip()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            messagebox.showinfo("OpenEOS", "Отчёт скопирован в буфер обмена.")

    def save_file_report(self):
        if not self.last_file_report:
            return
        text = self.txt_file_details.get("1.0", "end").strip()
        dest = filedialog.asksaveasfilename(
            title="Сохранить отчёт", initialfile=f"Report_{Path(self.last_file_report['file_name']).stem}.txt",
            defaultextension=".txt", filetypes=[("Текстовый отчёт", "*.txt")]
        )
        if dest:
            try:
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(text)
                messagebox.showinfo("OpenEOS", f"Отчёт сохранён в файл:\n{dest}")
            except Exception as exc:
                messagebox.showerror("OpenEOS", f"Ошибка сохранения: {exc}")

    # -----------------------------------------------------------------------
    # Вкладка 2: Подготовка SD-карты Canon
    # -----------------------------------------------------------------------
    def build_card_tab(self):
        info_card = tk.Frame(
            self.frame_card, bg=self.colors["CARD"],
            highlightbackground=self.colors["CARD_BORDER"], highlightthickness=1, padx=16, pady=10
        )
        info_card.pack(fill="x", pady=(0, 10))

        tk.Label(
            info_card, text="СЕРВИСНЫЙ МЕТОД CANON BASIC (CamInfo_Debug)", font=(self.FONT_FAMILY, 9, "bold"),
            bg=self.colors["CARD"], fg=self.colors["ACCENT"]
        ).pack(anchor="w", pady=(0, 2))

        desc = (
            "Штатная сервисная процедура Canon для камер серий R, RP, R5, R6 (без Mark) и др.\n"
            "OpenEOS форматирует отдельную карту ≤32 ГБ в FAT32 и прописывает метку загрузочного сектора SCRIPT.\n"
            "После вставки в камеру и нажатия Play + SET камера формирует файл CAM_INFO.XML с реальным пробегом."
        )
        tk.Label(
            info_card, text=desc, font=(self.FONT_FAMILY, 8),
            bg=self.colors["CARD"], fg=self.colors["MUTED"], justify="left"
        ).pack(anchor="w")

        ctrl_card = tk.Frame(
            self.frame_card, bg=self.colors["CARD"],
            highlightbackground=self.colors["CARD_BORDER"], highlightthickness=1, padx=16, pady=10
        )
        ctrl_card.pack(fill="x", pady=(0, 10))

        row1 = tk.Frame(ctrl_card, bg=self.colors["CARD"])
        row1.pack(fill="x", pady=(0, 8))

        tk.Label(
            row1, text="Съёмная карта памяти:", font=(self.FONT_FAMILY, 9, "bold"),
            bg=self.colors["CARD"], fg=self.colors["TEXT"]
        ).pack(side="left")

        self.card_var = tk.StringVar(value="")
        self.combo_card = ttk.Combobox(row1, textvariable=self.card_var, state="readonly", width=42)
        self.combo_card.pack(side="left", padx=(10, 8))

        btn_refresh = tk.Button(
            row1, text="Обновить список", font=(self.FONT_FAMILY, 8, "bold"),
            bg=self.colors["GRAY_BTN"], fg=self.colors["GRAY_BTN_FG"],
            activebackground=self.colors["GRAY_BTN_HOVER"], activeforeground=self.colors["TEXT"],
            bd=0, relief="flat", padx=10, pady=4, cursor="hand2",
            command=self.refresh_drives
        )
        btn_refresh.pack(side="left")

        row2 = tk.Frame(ctrl_card, bg=self.colors["CARD"])
        row2.pack(fill="x")

        self.btn_format_card = tk.Button(
            row2, text="1. Подготовить карту (FAT32 + SCRIPT)", font=(self.FONT_FAMILY, 9, "bold"),
            bg=self.colors["ACCENT"], fg="#FFFFFF", activebackground=self.colors["ACCENT_HOVER"],
            activeforeground="#FFFFFF", bd=0, relief="flat", padx=14, pady=6, cursor="hand2",
            command=self.prepare_card_action
        )
        self.btn_format_card.pack(side="left", padx=(0, 10))

        self.btn_read_card = tk.Button(
            row2, text="2. Прочитать результат (CAM_INFO.XML)", font=(self.FONT_FAMILY, 9, "bold"),
            bg=self.colors["GRAY_BTN"], fg=self.colors["GRAY_BTN_FG"],
            activebackground=self.colors["GRAY_BTN_HOVER"], activeforeground=self.colors["TEXT"],
            bd=0, relief="flat", padx=14, pady=6, cursor="hand2",
            command=self.read_card_action
        )
        self.btn_read_card.pack(side="left", padx=(0, 10))

        card_res_card = tk.Frame(
            self.frame_card, bg=self.colors["CARD"],
            highlightbackground=self.colors["CARD_BORDER"], highlightthickness=1, padx=14, pady=10
        )
        card_res_card.pack(fill="both", expand=True)

        res_bar = tk.Frame(card_res_card, bg=self.colors["CARD"])
        res_bar.pack(fill="x", pady=(0, 6))

        tk.Label(
            res_bar, text="ДАННЫЕ ИЗ ФАЙЛА CAM_INFO.XML (доступны для выделения и копирования):",
            font=(self.FONT_FAMILY, 8, "bold"), bg=self.colors["CARD"], fg=self.colors["MUTED"]
        ).pack(side="left")

        self.txt_card_details = tk.Text(
            card_res_card, bg=self.colors["BG"], fg=self.colors["TEXT"],
            font=(self.FONT_FAMILY, 9), relief="flat", bd=0, wrap="word",
            padx=10, pady=8, insertbackground=self.colors["TEXT"]
        )
        self.txt_card_details.pack(fill="both", expand=True)
        self.txt_card_details.insert(
            "end",
            "Пошаговая инструкция:\n"
            "1. Вставьте карту памяти ≤32 ГБ в кардридер компьютера.\n"
            "2. Выберите её в списке выше и нажмите «Подготовить карту» (внимание: все данные сотрутся!).\n"
            "3. Вставьте карту в выключенную камеру, включите, нажмите кнопку Просмотр (Play) и несколько раз кнопку SET.\n"
            "4. Выключите камеру, верните карту в компьютер и нажмите «Прочитать результат»."
        )
        self.txt_card_details.config(state="disabled")

        self.drives_map = {}
        self.refresh_drives()

    def refresh_drives(self):
        self.drives_map.clear()
        drives = cbasic_card.list_removable_drives()
        vals = []
        for d in drives:
            disp = d.display()
            self.drives_map[disp] = d
            vals.append(disp)
        self.combo_card["values"] = vals
        if vals:
            self.combo_card.current(0)
        else:
            self.card_var.set("")
            self.combo_card.set("")

    def get_selected_drive(self):
        return self.drives_map.get(self.card_var.get())

    def prepare_card_action(self):
        drive = self.get_selected_drive()
        if not drive:
            messagebox.showwarning("OpenEOS", "Выберите карту памяти из списка.")
            return

        conf = messagebox.askyesno(
            "Подтверждение форматирования",
            f"ВНИМАНИЕ! Карта {drive.letter} ({drive.size_gb} ГБ) будет ПОЛНОСТЬЮ СТЁРТА и отформатирована в FAT32.\n\n"
            "Будет записана загрузочная метка SCRIPT и файлы процедуры CamInfo_Debug.\n\n"
            "Вы уверены, что хотите продолжить?",
            icon="warning"
        )
        if not conf:
            return

        self.txt_card_details.config(state="normal")
        self.txt_card_details.delete("1.0", "end")
        self.txt_card_details.insert("end", f"Форматирование карты {drive.letter} в FAT32 и запись метки SCRIPT…\nПожалуйста, подождите.\n")
        self.txt_card_details.config(state="disabled")
        self.root.update_idletasks()

        ok, msg = cbasic_card.format_and_prepare_card(drive)
        self.txt_card_details.config(state="normal")
        if ok:
            self.txt_card_details.insert("end", f"\n[УСПЕХ] {msg}\n\nТеперь вставьте карту в камеру:\n1. Включите камеру\n2. Нажмите Play\n3. Несколько раз нажмите кнопку SET\n4. Выключите камеру и верните карту в ПК для чтения результата.")
            messagebox.showinfo("OpenEOS", "Карта успешно подготовлена!")
        else:
            self.txt_card_details.insert("end", f"\n[ОШИБКА] {msg}")
            messagebox.showerror("OpenEOS", f"Ошибка: {msg}")
        self.txt_card_details.config(state="disabled")
        self.refresh_drives()

    def read_card_action(self):
        drive = self.get_selected_drive()
        if not drive:
            messagebox.showwarning("OpenEOS", "Выберите карту памяти из списка.")
            return

        xml_path = cbasic_card.find_cam_info_xml(drive)
        if not xml_path:
            messagebox.showinfo(
                "OpenEOS",
                f"Файл CAM_INFO.XML на диске {drive.letter} пока не обнаружен.\n\n"
                "Убедитесь, что вы выполнили процедуру в камере (Play → SET несколько раз)."
            )
            return

        self.switch_tab(0)
        self.process_file(str(xml_path))

    # -----------------------------------------------------------------------
    # Памятка покупателя (Модальное окно)
    # -----------------------------------------------------------------------
    def show_buyer_guide(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Памятка покупателя фототехники — OpenEOS")
        dlg.geometry("780x560")
        dlg.minsize(700, 500)
        dlg.configure(bg=self.colors["BG"])
        apply_titlebar_theme(dlg, self.theme_name == "dark")
        dlg.transient(self.root)

        header = tk.Frame(dlg, bg=self.colors["BG"], padx=20, pady=14)
        header.pack(fill="x")
        tk.Label(
            header, text="📘 Памятка по проверке затвора и ресурса фотокамер",
            font=(self.FONT_FAMILY, 14, "bold"), bg=self.colors["BG"], fg=self.colors["TEXT"]
        ).pack(anchor="w")

        content_box = tk.Frame(dlg, bg=self.colors["CARD"], padx=16, pady=12, highlightbackground=self.colors["BORDER"], highlightthickness=1)
        content_box.pack(fill="both", expand=True, padx=20, pady=(0, 14))

        txt = tk.Text(
            content_box, bg=self.colors["CARD"], fg=self.colors["TEXT"],
            font=(self.FONT_FAMILY, 9), relief="flat", bd=0, wrap="word"
        )
        txt.pack(fill="both", expand=True)

        guide = """1. МЕХАНИЧЕСКИЙ ЗАТВОР ПРОТИВ ЭЛЕКТРОННОГО
• Механический затвор — это физические металлические шторки, перемещающиеся перед матрицей. Они подвержены трению и механическому износу. Заявленный ресурс производителя (100–500 тыс. кадров) относится ИСКЛЮЧИТЕЛЬНО к механическому узлу!
• Электронный затвор (Silent Shutter / Бесшумный режим) — построчное считывание сигнала прямо с сенсора. Механические шторки при этом открыты или неподвижны. Износ физического узла равен нулю.
• Электронная передняя шторка (EFCS) — старт электронный, финиш механической шторкой. Износ снижен примерно в 2 раза по сравнению с чистой механикой.

2. КАК СЧИТАЮТ ПРОБЕГ РАЗНЫЕ ВЕНДОРЫ
• SONY (.ARW): в современных камерах тег 0x9050 считает ТОЛЬКО механические срабатывания. Если на камере сняли 50 000 кадров с электронным затвором, счётчик не увеличится ни на единицу! Это идеальный показатель физического износа.
• NIKON (.NEF): счётчик 0x00A7 является сквозным (кумулятивным). Он увеличивается при любом спуске (механика + бесшумный режим). У флагмана Nikon Z9 механики нет вообще, но счётчик честно считает каждый кадр сенсора.
• CANON (CR3): в поколении DIGIC X (R5, R6 Mk II, R6 Mk III, R7, R8, R10 и др.) общий счётчик пишется в служебную дорожку Track4. Для более старых камер (DIGIC 8 и зеркалки) производитель скрыл пробег из EXIF кадра — его можно узнать через встроенную сервисную процедуру CamInfo_Debug на карте памяти или по кабелю USB.

3. РАСШИФРОВКА КРИТИЧЕСКИХ ОШИБОК CANON (ERR LOG)
• Err 20 — Сбой механического узла (заклинивание шторок, привод зеркала или механизма взвода). Серьёзный повод для проверки в сервисе.
• Err 30 — Непосредственный сбой затвора (шторка не смогла завершить цикл экспонирования на нужной выдержке).
• Err 60 — Ошибка привода диафрагмы или вспомогательных шторок.
• Err 70 — Сбой встроенного ПО или оперативной памяти (часто вызывается сбойными картами памяти или несовместимыми объективами).

4. ЧЕК-ЛИСТ ПРОВЕРКИ ПРИ ПОКУПКЕ С РУК
1) Попросите продавца прислать несжатый RAW-файл с камеры (последний кадр) и проверьте его в OpenEOS.
2) Сверьте дату и порядковый номер кадра.
3) Обратите внимание на процент выработки ресурса: до 30% — практически новая камера, 30–70% — рабочее состояние с хорошим запасом, свыше 90% — закладывайте в бюджет стоимость возможной замены затвора.
"""
        txt.insert("end", guide)
        txt.config(state="disabled")

        btn_close = tk.Button(
            dlg, text="Понятно, закрыть", font=(self.FONT_FAMILY, 9, "bold"),
            bg=self.colors["ACCENT"], fg="#FFFFFF", activebackground=self.colors["ACCENT_HOVER"],
            activeforeground="#FFFFFF", bd=0, relief="flat", padx=16, pady=6, cursor="hand2",
            command=dlg.destroy
        )
        btn_close.pack(pady=(0, 14))


def set_app_icon(root: tk.Tk):
    base_dir = get_resource_dir()
    ico = base_dir / "app_icon.ico"
    png = base_dir / "app_icon.png"
    if sys.platform == "win32" and ico.exists():
        try:
            root.iconbitmap(str(ico))
            return
        except Exception:
            pass
    if png.exists():
        try:
            img = tk.PhotoImage(file=str(png))
            root.iconphoto(True, img)
        except Exception:
            pass


def main():
    setup_windows_dpi()
    root = ROOT_CLASS()
    set_app_icon(root)
    app = OpenEOSCommunityApp(root)
    root.mainloop()

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        import traceback
        err = traceback.format_exc()
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f"Критическая ошибка запуска:\n\n{err}", "OpenEOS", 0x10)
        except Exception:
            print(err)
