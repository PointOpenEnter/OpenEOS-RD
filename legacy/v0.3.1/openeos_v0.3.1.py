import csv
import json
import os
import subprocess
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "OpenEOS"
APP_VERSION = "0.3.1"
EXIFTOOL = r"C:\Tools\ExifTool\exiftool.exe"
BATCH_CHUNK_SIZE = 50
TABLE_CHUNK_SIZE = 150
# Supported containers/readable image formats, ordered for the Canon-first UI.
# ExifTool can read metadata from these formats; ShutterCount may be absent.
SUPPORTED_EXTENSIONS = (
    ".cr2", ".cr3", ".dng", ".jpg", ".jpeg",
    ".heic", ".hif", ".nef", ".arw", ".raf", ".pef",
)
SUPPORTED_FILETYPES = [
    ("Все форматы OpenEOS", "*.CR2 *.CR3 *.DNG *.JPG *.JPEG *.HEIC *.HIF *.NEF *.ARW *.RAF *.PEF"),
    ("Canon RAW — CR2 и CR3", "*.CR2 *.CR3"),
    ("Все файлы", "*.*"),
]
SUPPORTED_FORMATS_LABEL = (
    "CR2  ·  CR3  ·  DNG  ·  JPG/JPEG  ·  HEIC  ·  HIF  ·  NEF  ·  ARW  ·  RAF  ·  PEF"
)

# Drag-and-drop is optional. File selection works without this package.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
    ROOT_CLASS = TkinterDnD.Tk
except ImportError:
    DND_FILES = None
    DND_AVAILABLE = False
    ROOT_CLASS = tk.Tk


class OpenEOSApp:
    BG = "#F3F6FA"
    CARD = "#FFFFFF"
    NAVY = "#172B4D"
    TEXT = "#27364B"
    MUTED = "#68788D"
    ACCENT = "#2764D7"
    ACCENT_DARK = "#1F50AD"
    PALE_BLUE = "#EAF1FF"
    BORDER = "#DCE4EF"
    GREEN = "#16845B"
    PALE_GREEN = "#E8F6EF"
    RED = "#B42318"
    PALE_RED = "#FDEDEA"
    AMBER = "#9A6700"
    PALE_AMBER = "#FFF4D6"

    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_TITLE} — проверка показания счётчика")
        self.root.configure(bg=self.BG)
        self.root.resizable(True, True)

        self.busy = False
        self.current_mode = None
        self.single_file = None
        self.batch_results = []
        self.batch_metadata = {}
        self.batch_cancel_event = threading.Event()
        self.batch_process = None
        self.batch_process_lock = threading.Lock()
        self.batch_folder_path = None
        self.batch_total = 0
        self.batch_processed = 0
        self.batch_started_at = None
        self.render_index = 0
        self.render_readable = 0
        self.render_missing = 0
        self.batch_cancelled = False

        self.folder_text = tk.StringVar(value="Папка не выбрана")

        self.configure_styles()
        self.create_interface()
        self.tabs.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self.root.after(80, lambda: self.fit_window(880, 650))

    # ---------------------------------------------------------
    # Window and styles
    # ---------------------------------------------------------
    def configure_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TNotebook", background=self.BG, borderwidth=0)
        style.configure(
            "TNotebook.Tab", background="#E7ECF3", foreground=self.MUTED,
            padding=(18, 9), font=("Segoe UI", 10, "bold")
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", self.CARD)],
            foreground=[("selected", self.NAVY)],
        )
        style.configure(
            "Treeview", background=self.CARD, fieldbackground=self.CARD,
            foreground=self.TEXT, rowheight=27, borderwidth=0,
            font=("Segoe UI", 9)
        )
        style.configure(
            "Treeview.Heading", background="#EAF0F7", foreground=self.NAVY,
            font=("Segoe UI", 9, "bold"), padding=(7, 7)
        )
        style.map("Treeview", background=[("selected", "#DCE8FF")])

    def fit_window(self, requested_width, requested_height):
        """Size the window to the active screen; long filenames never resize it."""
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        available_w = max(700, screen_w - 48)
        available_h = max(520, screen_h - 88)
        width = min(requested_width, available_w)
        height = min(requested_height, available_h)
        min_w = min(720, width)
        min_h = min(520, height)
        self.root.minsize(min_w, min_h)
        self.root.maxsize(available_w, available_h)
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def on_tab_changed(self, _event=None):
        if self.busy and self.current_mode == "batch":
            # Keep the cancellation control in view while a batch is running.
            self.tabs.select(self.batch_tab)
            return
        try:
            index = self.tabs.index(self.tabs.select())
        except tk.TclError:
            return
        if index == 0:
            self.fit_window(880, 650)
        else:
            self.fit_window(1180, 710)

    @staticmethod
    def compact_text(value, limit=70):
        text = str(value or "")
        if len(text) <= limit:
            return text
        keep = max(8, (limit - 1) // 2)
        return text[:keep] + "…" + text[-keep:]

    # ---------------------------------------------------------
    # Main interface
    # ---------------------------------------------------------
    def create_interface(self):
        header = tk.Frame(self.root, bg=self.BG)
        header.pack(fill="x", padx=22, pady=(13, 8))

        tk.Label(
            header, text="OpenEOS", bg=self.BG, fg=self.NAVY,
            font=("Segoe UI", 20, "bold")
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Проверка фото локально на компьютере — файл не отправляется в интернет.",
            bg=self.BG, fg=self.MUTED, font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(0, 1))

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        self.single_tab = tk.Frame(self.tabs, bg=self.BG)
        self.batch_tab = tk.Frame(self.tabs, bg=self.BG)
        self.tabs.add(self.single_tab, text="  Проверить фото  ")
        self.tabs.add(self.batch_tab, text="  Анализ папки  ")

        self.create_single_tab()
        self.create_batch_tab()
        # Enable file drops throughout the whole single-photo tab, not just
        # the small highlighted card. The normal file-picker remains available.
        if DND_AVAILABLE:
            self.register_drop_targets(self.single_tab)

    # ---------------------------------------------------------
    # Single file screen: compact, stable layout
    # ---------------------------------------------------------
    def create_single_tab(self):
        page = tk.Frame(self.single_tab, bg=self.BG)
        page.pack(fill="both", expand=True, padx=18, pady=8)

        tk.Label(
            page, text="Узнайте показание счётчика камеры по фото",
            bg=self.BG, fg=self.NAVY, font=("Segoe UI", 14, "bold")
        ).pack(anchor="w")
        tk.Label(
            page,
            text="Выберите оригинальный JPEG или RAW. Для наиболее актуального значения используйте самый свежий файл.",
            bg=self.BG, fg=self.MUTED, font=("Segoe UI", 9),
            wraplength=800, justify="left"
        ).pack(anchor="w", pady=(3, 10))

        self.drop_card = tk.Frame(
            page, bg=self.CARD, highlightbackground=self.BORDER,
            highlightthickness=1, bd=0
        )
        self.drop_card.pack(fill="x", pady=(0, 10))

        drop_inner = tk.Frame(self.drop_card, bg=self.PALE_BLUE)
        drop_inner.pack(fill="x", padx=9, pady=7)

        if DND_AVAILABLE:
            prompt = "Перетащите фото в эту область или выберите файл"
        else:
            prompt = "Выберите файл кнопкой · для перетаскивания установите tkinterdnd2"

        tk.Label(
            drop_inner, text=prompt, bg=self.PALE_BLUE, fg=self.NAVY,
            font=("Segoe UI", 12, "bold")
        ).pack(pady=(4, 2))
        tk.Label(
            drop_inner,
            text=SUPPORTED_FORMATS_LABEL,
            bg=self.PALE_BLUE, fg=self.MUTED, font=("Segoe UI", 8, "bold")
        ).pack(pady=(0, 5))

        self.single_select_button = tk.Button(
            drop_inner, text="Выбрать файл", command=self.select_single_file,
            bg=self.ACCENT, fg="#FFFFFF", activebackground=self.ACCENT_DARK,
            activeforeground="#FFFFFF", relief="flat", bd=0,
            padx=22, pady=8, font=("Segoe UI", 9, "bold"), cursor="hand2"
        )
        self.single_select_button.pack(pady=(0, 4))

        self.selected_file_label = tk.Label(
            self.drop_card, text="Файл не выбран", bg=self.CARD,
            fg=self.MUTED, font=("Segoe UI", 8), anchor="center",
            padx=12, pady=5
        )
        self.selected_file_label.pack(fill="x")

        self.result_card = tk.Frame(
            page, bg=self.CARD, highlightbackground=self.BORDER,
            highlightthickness=1, bd=0
        )
        self.result_card.pack(fill="both", expand=True)

        tk.Label(
            self.result_card, text="ПОКАЗАНИЕ СЧЁТЧИКА",
            bg=self.CARD, fg=self.MUTED, font=("Segoe UI", 8, "bold")
        ).pack(pady=(7, 0))

        value_row = tk.Frame(self.result_card, bg=self.CARD)
        value_row.pack(anchor="center", pady=(0, 3))

        self.counter_label = tk.Label(
            value_row, text="—", bg=self.CARD, fg=self.NAVY,
            font=("Segoe UI", 32, "bold")
        )
        self.counter_label.pack(side="left", padx=(0, 12))

        self.single_status_label = tk.Label(
            value_row, text="Ожидает фото", bg="#EDF1F6", fg=self.MUTED,
            font=("Segoe UI", 8, "bold"), padx=9, pady=5
        )
        self.single_status_label.pack(side="left", pady=(8, 0))

        tk.Frame(self.result_card, bg=self.BORDER, height=1).pack(
            fill="x", padx=22, pady=(5, 8)
        )

        meta_frame = tk.Frame(self.result_card, bg=self.CARD)
        meta_frame.pack(fill="x", padx=18, pady=(0, 7))
        meta_frame.columnconfigure(0, weight=2)
        meta_frame.columnconfigure(1, weight=1)
        meta_frame.columnconfigure(2, weight=1)

        self.single_meta = {}
        for col, (label, key) in enumerate((
            ("ФАЙЛ", "filename"),
            ("КАМЕРА", "model"),
            ("ДАТА СЪЁМКИ", "date"),
        )):
            cell = tk.Frame(meta_frame, bg=self.CARD)
            cell.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 10, 4))
            tk.Label(
                cell, text=label, bg=self.CARD, fg=self.MUTED,
                font=("Segoe UI", 7, "bold")
            ).pack(anchor="w")
            value = tk.Label(
                cell, text="—", bg=self.CARD, fg=self.TEXT,
                font=("Segoe UI", 9, "bold"), anchor="w"
            )
            value.pack(fill="x", anchor="w", pady=(3, 0))
            self.single_meta[key] = value

    def register_drop_targets(self, widget):
        """Register a widget and its descendants as Windows file-drop targets."""
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.on_file_drop)
        except (AttributeError, tk.TclError):
            # Some Tk widgets/platforms may not expose a drop-target API.
            pass

        for child in widget.winfo_children():
            self.register_drop_targets(child)

    def on_file_drop(self, event):
        if self.busy:
            messagebox.showinfo(
                "OpenEOS",
                "Сначала дождитесь завершения текущей операции или остановите пакетный анализ."
            )
            return "break"

        try:
            # event.data is a Tcl list; splitlist correctly preserves spaces
            # and Cyrillic characters in Windows paths.
            dropped_paths = list(self.root.tk.splitlist(event.data))
        except (tk.TclError, TypeError):
            dropped_paths = [str(getattr(event, "data", ""))]

        dropped_paths = [os.path.normpath(path.strip()) for path in dropped_paths if path.strip()]
        existing_files = [path for path in dropped_paths if os.path.isfile(path)]
        supported_files = [
            path for path in existing_files
            if os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS
        ]

        if not supported_files:
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
            else:
                messagebox.showwarning(
                    "OpenEOS",
                    "Перетащите в окно файл фотографии, а не папку."
                )
            return "break"

        if len(supported_files) > 1:
            messagebox.showinfo(
                "OpenEOS",
                "В режиме проверки фото используется один файл.\n"
                "Будет проверен первый поддерживаемый файл из перетащенных."
            )

        self.start_single_file(supported_files[0])
        return "break"

    def select_single_file(self):
        path = filedialog.askopenfilename(
            title="Выберите фотографию", filetypes=SUPPORTED_FILETYPES
        )
        if path:
            self.start_single_file(path)

    def start_single_file(self, path):
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
        self.set_single_status("Читаем…", self.PALE_BLUE, self.ACCENT)
        self.selected_file_label.config(
            text=self.compact_text(os.path.basename(path), 92), fg=self.TEXT
        )
        self.single_meta["filename"].config(
            text=self.compact_text(os.path.basename(path), 34)
        )
        self.single_meta["model"].config(text="—")
        self.single_meta["date"].config(text="—")
        self.set_busy(True, "single")
        threading.Thread(
            target=self.single_worker, args=(path,), daemon=True
        ).start()

    def analyze_single_again(self):
        if self.single_file:
            self.start_single_file(self.single_file)

    def set_single_status(self, text, background, foreground):
        self.single_status_label.config(
            text=text, bg=background, fg=foreground
        )

    def single_worker(self, path):
        try:
            data = self.read_single_file(path)
        except Exception as exc:
            self.root.after(0, self.finish_single_error, str(exc))
        else:
            self.root.after(0, self.finish_single_success, data, path)

    def finish_single_success(self, data, path):
        try:
            if not data:
                raise RuntimeError("ExifTool не вернул данные по выбранному файлу.")
            shutter = data.get("ShutterCount")
            if shutter is None:
                self.counter_label.config(text="Не найден")
                self.set_single_status(
                    "Счётчик не найден", self.PALE_AMBER, self.AMBER
                )
            else:
                self.counter_label.config(text=str(shutter))
                self.set_single_status("Проверено", self.PALE_GREEN, self.GREEN)
            self.single_meta["filename"].config(
                text=self.compact_text(data.get("FileName") or os.path.basename(path), 34)
            )
            self.single_meta["model"].config(
                text=self.compact_text(data.get("Model") or "Не определена", 28)
            )
            self.single_meta["date"].config(
                text=data.get("DateTimeOriginal") or "Не указана"
            )
        except Exception as exc:
            self.finish_single_error(str(exc))
            return
        self.set_busy(False)

    def finish_single_error(self, message):
        self.set_busy(False)
        self.counter_label.config(text="—")
        self.set_single_status("Ошибка чтения", self.PALE_RED, self.RED)
        self.show_error(message)

    # ---------------------------------------------------------
    # Batch screen
    # ---------------------------------------------------------
    def create_batch_tab(self):
        page = tk.Frame(self.batch_tab, bg=self.BG)
        page.pack(fill="both", expand=True, padx=14, pady=6)

        tk.Label(
            page, text="Пакетная проверка CR3",
            bg=self.BG, fg=self.NAVY, font=("Segoe UI", 15, "bold")
        ).pack(anchor="w")
        tk.Label(
            page,
            text="Сравнение показаний ShutterCount в CR3-файлах одной папки. Исходные фотографии не изменяются.",
            bg=self.BG, fg=self.MUTED, font=("Segoe UI", 8)
        ).pack(anchor="w", pady=(1, 6))

        folder_card = tk.Frame(
            page, bg=self.CARD, highlightbackground=self.BORDER,
            highlightthickness=1
        )
        folder_card.pack(fill="x", pady=(0, 8))
        folder_row = tk.Frame(folder_card, bg=self.CARD)
        folder_row.pack(fill="x", padx=10, pady=7)
        tk.Label(
            folder_row, text="ПАПКА С CR3", bg=self.CARD, fg=self.MUTED,
            font=("Segoe UI", 7, "bold")
        ).pack(side="left", padx=(0, 12))
        self.folder_value = tk.Label(
            folder_row, textvariable=self.folder_text, bg="#F4F7FB",
            fg=self.TEXT, anchor="w", padx=9, pady=7,
            font=("Segoe UI", 9)
        )
        self.folder_value.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.batch_select_button = tk.Button(
            folder_row, text="Выбрать папку", command=self.select_batch_folder,
            bg="#EAF1FF", fg=self.ACCENT_DARK, activebackground="#DCE8FF",
            relief="flat", bd=0, padx=13, pady=7,
            font=("Segoe UI", 9, "bold"), cursor="hand2"
        )
        self.batch_select_button.pack(side="right")

        actions = tk.Frame(page, bg=self.BG)
        actions.pack(fill="x", pady=(0, 6))
        self.batch_analyze_button = tk.Button(
            actions, text="Анализировать папку", command=self.analyze_batch,
            bg=self.ACCENT, fg="#FFFFFF", activebackground=self.ACCENT_DARK,
            activeforeground="#FFFFFF", relief="flat", bd=0,
            padx=16, pady=8, font=("Segoe UI", 9, "bold"), cursor="hand2"
        )
        self.batch_analyze_button.pack(side="left")
        self.csv_button = tk.Button(
            actions, text="Экспорт CSV", command=self.export_csv,
            bg="#E8EDF4", fg=self.TEXT, activebackground="#DCE4EF",
            relief="flat", bd=0, padx=14, pady=8,
            font=("Segoe UI", 9, "bold"), cursor="hand2", state="disabled"
        )
        self.csv_button.pack(side="left", padx=(8, 0))
        self.cancel_button = tk.Button(
            actions, text="Прервать анализ", command=self.cancel_batch,
            bg=self.PALE_RED, fg=self.RED, activebackground="#F8D8D3",
            activeforeground=self.RED, relief="flat", bd=0,
            padx=14, pady=8, font=("Segoe UI", 9, "bold"),
            cursor="hand2", state="disabled"
        )
        self.cancel_button.pack(side="right")

        progress_card = tk.Frame(
            page, bg=self.CARD, highlightbackground=self.BORDER,
            highlightthickness=1
        )
        progress_card.pack(fill="x", pady=(0, 8))
        progress_inner = tk.Frame(progress_card, bg=self.CARD)
        progress_inner.pack(fill="x", padx=12, pady=7)
        progress_top = tk.Frame(progress_inner, bg=self.CARD)
        progress_top.pack(fill="x", pady=(0, 3))
        tk.Label(
            progress_top, text="Ход анализа", bg=self.CARD,
            fg=self.NAVY, font=("Segoe UI", 9, "bold")
        ).pack(side="left")
        self.progress_percent = tk.Label(
            progress_top, text="0%", bg=self.CARD, fg=self.ACCENT,
            font=("Segoe UI", 9, "bold")
        )
        self.progress_percent.pack(side="right")

        # A canvas-based bar guarantees a visibly filled 0–100% indicator
        # across Windows themes; it does not use the indeterminate animation.
        self.progress_canvas = tk.Canvas(
            progress_inner, height=10, bg="#E6ECF4",
            highlightthickness=0, bd=0
        )
        self.progress_canvas.pack(fill="x")
        self.progress_fill = self.progress_canvas.create_rectangle(
            0, 0, 0, 10, fill=self.ACCENT, outline=""
        )
        self.progress_canvas.bind("<Configure>", self.redraw_progress)

        self.batch_progress_label = tk.Label(
            progress_inner, text="Ожидает запуска.", bg=self.CARD,
            fg=self.MUTED, anchor="w", font=("Segoe UI", 8)
        )
        self.batch_progress_label.pack(fill="x", pady=(4, 1))
        self.batch_summary = tk.Label(
            progress_inner, text="Результатов пока нет.", bg=self.CARD,
            fg=self.MUTED, anchor="w", font=("Segoe UI", 8, "bold")
        )
        self.batch_summary.pack(fill="x")

        table_card = tk.Frame(
            page, bg=self.CARD, highlightbackground=self.BORDER,
            highlightthickness=1
        )
        table_card.pack(fill="both", expand=True)
        table_inner = tk.Frame(table_card, bg=self.CARD)
        table_inner.pack(fill="both", expand=True, padx=7, pady=7)
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
            "filename": 155, "shutter": 105, "date": 155,
            "model": 125, "observations": 170, "path": 330
        }
        for col in columns:
            self.batch_table.heading(
                col, text=headings[col],
                command=lambda column=col: self.sort_batch_table(column, False)
            )
            self.batch_table.column(col, width=widths[col], minwidth=65)
        yscroll = ttk.Scrollbar(
            table_inner, orient="vertical", command=self.batch_table.yview
        )
        xscroll = ttk.Scrollbar(
            table_inner, orient="horizontal", command=self.batch_table.xview
        )
        self.batch_table.configure(
            yscrollcommand=yscroll.set, xscrollcommand=xscroll.set
        )
        self.batch_table.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_inner.rowconfigure(0, weight=1)
        table_inner.columnconfigure(0, weight=1)

    def redraw_progress(self, _event=None):
        width = max(0, self.progress_canvas.winfo_width())
        if width <= 1:
            return
        total = max(getattr(self, "batch_total", 0), 1)
        current = min(getattr(self, "batch_processed", 0), total)
        fraction = current / total
        self.progress_canvas.coords(
            self.progress_fill, 0, 0, int(width * fraction), 10
        )

    def set_progress(self, current, total):
        self.batch_processed = current
        self.batch_total = total
        fraction = current / total if total else 0
        self.progress_percent.config(text=f"{fraction * 100:.1f}%")
        width = max(0, self.progress_canvas.winfo_width())
        if width > 1:
            self.progress_canvas.coords(
                self.progress_fill, 0, 0, int(width * fraction), 10
            )

    def select_batch_folder(self):
        if self.busy:
            return
        folder = filedialog.askdirectory(title="Выберите папку с CR3")
        if not folder:
            return
        self.batch_folder_path = folder
        self.folder_text.set(self.compact_text(folder, 96))
        self.batch_results = []
        self.batch_metadata = {}
        existing_rows = self.batch_table.get_children()
        if existing_rows:
            self.batch_table.delete(*existing_rows)
        self.batch_summary.config(text="Папка выбрана. Анализ ещё не запускался.")
        self.set_progress(0, 0)
        self.batch_progress_label.config(text="Готово к запуску.")
        self.csv_button.config(state="disabled")

    def analyze_batch(self):
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
        self.batch_progress_label.config(text="Ищем CR3-файлы в папке…")
        self.batch_summary.config(text="Подготовка списка файлов.")
        threading.Thread(
            target=self.batch_worker, args=(folder,), daemon=True
        ).start()

    # ---------------------------------------------------------
    # Batch worker: collect CR3 list, then process cancellable chunks
    # ---------------------------------------------------------
    def batch_worker(self, folder):
        started = time.monotonic()
        results = []
        warnings = []
        warnings_lock = threading.Lock()
        files = []
        attempted = 0
        cancelled = False
        error_message = None
        process = None
        stderr_thread = None

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
            # A one-level folder scan provides an exact denominator for 0–100%.
            with os.scandir(folder) as entries:
                for index, entry in enumerate(entries, start=1):
                    if self.batch_cancel_event.is_set():
                        cancelled = True
                        break
                    try:
                        if entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(".cr3"):
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
                    [EXIFTOOL, "-charset", "filename=UTF8", "-stay_open", "True", "-@", "-"],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=creationflags,
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

                    output_lines = []
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

                    # Discard the incomplete chunk if the user stopped mid-read.
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
    def path_key(path):
        if not path:
            return ""
        return os.path.normcase(os.path.abspath(path))

    def update_scan_status(self, entries_scanned, cr3_found):
        if not self.busy or self.current_mode != "batch":
            return
        self.batch_progress_label.config(
            text=(
                f"Поиск CR3: просмотрено {entries_scanned:,} элементов, "
                f"найдено {cr3_found:,} файлов"
            ).replace(",", " ")
        )

    def begin_determinate_progress(self, total):
        if not self.busy:
            return
        self.batch_total = total
        self.batch_processed = 0
        self.set_progress(0, total)
        if total:
            self.batch_progress_label.config(text=f"Найдено CR3: {total:,}. Начинаем чтение…".replace(",", " "))
            self.batch_summary.config(text="Чтение метаданных. Можно прервать анализ в любой момент.")
        else:
            self.batch_progress_label.config(text="CR3-файлы не найдены.")
            self.batch_summary.config(text="В выбранной папке нет файлов с расширением .CR3.")

    @staticmethod
    def format_duration(seconds):
        if seconds is None or seconds < 0:
            return "—"
        seconds = int(seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def update_batch_progress(self, current, total, speed, remaining, last_file):
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

    def cancel_batch(self):
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

    def build_batch_metadata(self, started, processed, total, warnings, elapsed_override=None):
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

    def finish_batch_success(self, results, metadata):
        self.batch_results = results
        self.batch_metadata = metadata
        self.batch_cancelled = False
        self.start_table_render()

    def finish_batch_cancelled(self, results, metadata, processed, total):
        self.batch_results = results
        self.batch_metadata = metadata
        self.batch_cancelled = True
        self.batch_metadata["cancelled"] = True
        if total:
            self.set_progress(processed, total)
        self.start_table_render()

    def finish_batch_error(self, message):
        self.set_busy(False)
        self.batch_progress_label.config(text="Анализ не завершён.")
        self.batch_summary.config(text="Возникла ошибка. Исходные файлы не изменены.")
        self.show_error(message)

    # ---------------------------------------------------------
    # Progressive table rendering
    # ---------------------------------------------------------
    def start_table_render(self):
        # ExifTool has finished; disabling Stop avoids implying that table display can be cancelled.
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
                self.batch_summary.config(text="В выбранной папке CR3-файлы не найдены.")
            self.set_busy(False)
            return
        stage = "Пакет остановлен. Формируем таблицу…" if self.batch_cancelled else "Чтение завершено. Формируем таблицу…"
        self.batch_progress_label.config(text=stage)
        self.root.after(10, self.insert_table_chunk)

    def insert_table_chunk(self):
        total = len(self.batch_results)
        end = min(self.render_index + TABLE_CHUNK_SIZE, total)
        for index in range(self.render_index, end):
            data = self.batch_results[index]
            shutter = data.get("ShutterCount")
            observations = []
            if shutter is None:
                self.render_missing += 1
                shutter_text = "Не найден"
                observations.append(data.get("ProcessingError") or "ShutterCount отсутствует")
            else:
                self.render_readable += 1
                shutter_text = str(shutter)
            if not data.get("DateTimeOriginal"):
                observations.append("Нет даты")
            if not data.get("Model"):
                observations.append("Нет модели")
            if not observations:
                observations.append("—")
            self.batch_table.insert(
                "", "end",
                values=(
                    data.get("FileName") or "—", shutter_text,
                    data.get("DateTimeOriginal") or "—",
                    data.get("Model") or "—", "; ".join(observations),
                    data.get("SourceFile", "")
                )
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

    def sort_batch_table(self, column, reverse):
        rows = [(self.batch_table.set(item, column), item) for item in self.batch_table.get_children("")]
        if column == "shutter":
            def key_fn(row):
                try:
                    return (0, int(row[0]))
                except (TypeError, ValueError):
                    return (1, str(row[0]).lower())
        else:
            key_fn = lambda row: str(row[0]).lower()
        rows.sort(key=key_fn, reverse=reverse)
        for index, (_, item) in enumerate(rows):
            self.batch_table.move(item, "", index)
        self.batch_table.heading(
            column, command=lambda: self.sort_batch_table(column, not reverse)
        )

    # ---------------------------------------------------------
    # ExifTool helpers
    # ---------------------------------------------------------
    def check_exiftool(self, show_message=False):
        if os.path.isfile(EXIFTOOL):
            return True
        message = (
            "Не найден ExifTool по указанному пути:\n\n"
            f"{EXIFTOOL}\n\n"
            "Проверьте, что ExifTool установлен в C:\\Tools\\ExifTool."
        )
        if show_message:
            messagebox.showerror("OpenEOS", message)
        return False

    @staticmethod
    def get_tag(record, tag, preferred_groups=()):
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

    def normalise_record(self, record, fallback_path=""):
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

    def read_single_file(self, path):
        command = [
            EXIFTOOL, "-json", "-G1", "-a", "-s", "-ShutterCount",
            "-DateTimeOriginal", "-Model", "-FileName", "-Directory", path
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            command, capture_output=True, text=True,
            encoding="utf-8", errors="replace", creationflags=creationflags
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
    def get_exiftool_version():
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                [EXIFTOOL, "-ver"], capture_output=True, text=True,
                encoding="utf-8", errors="replace", creationflags=creationflags
            )
            return result.stdout.strip() if result.returncode == 0 else "Не удалось определить"
        except OSError:
            return "Не удалось определить"

    # ---------------------------------------------------------
    # CSV export
    # ---------------------------------------------------------
    def export_csv(self):
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

    # ---------------------------------------------------------
    # Busy state and errors
    # ---------------------------------------------------------
    def set_busy(self, busy, mode=None):
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

    def show_error(self, error):
        messagebox.showerror("OpenEOS — ошибка", error)


if __name__ == "__main__":
    root = ROOT_CLASS()
    app = OpenEOSApp(root)
    root.mainloop()
