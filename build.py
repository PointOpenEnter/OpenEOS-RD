"""
build.py — Автономный скрипт сборки OpenEOS (Community и PRO).
Работает на чистом Python, исключая любые ошибки кодировки Windows командной строки.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def run_cmd(cmd: list[str]) -> bool:
    print(f"\n[ВЫПОЛНЕНИЕ] {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(BASE_DIR))
    return res.returncode == 0

def check_and_install_package(pkg: str):
    print(f"[*] Проверка {pkg}...")
    try:
        __import__(pkg)
        print(f"[+] {pkg} уже установлен.")
    except ImportError:
        print(f"[-] {pkg} не найден. Устанавливаю: pip install {pkg}...")
        subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=True)

def build_pyinstaller():
    check_and_install_package("PyInstaller")

    dist_dir = BASE_DIR / "dist"
    build_dir = BASE_DIR / "build"
    dist_dir.mkdir(exist_ok=True)

    # 1. Сборка Community Edition
    print("\n" + "=" * 65)
    print(" 1. Сборка OpenEOS.exe (Community Edition: 2 вкладки, для сообщества)")
    print("=" * 65)
    cmd_comm = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "OpenEOS",
        "--icon", str(BASE_DIR / "app_icon.ico"),
        "--add-data", f"{BASE_DIR / 'app_icon.png'};.",
        "--add-data", f"{BASE_DIR / 'app_icon.ico'};.",
        str(BASE_DIR / "openeos.py")
    ]
    if not run_cmd(cmd_comm):
        print("\n[ОШИБКА] Сборка OpenEOS.exe не удалась!")
        return False

    # 2. Сборка Pro Edition
    print("\n" + "=" * 65)
    print(" 2. Сборка OpenEOS_PRO.exe (Pro Edition: USB, EEPROM, журнал ошибок)")
    print("=" * 65)
    cmd_pro = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "OpenEOS_PRO",
        "--icon", str(BASE_DIR / "app_icon_pro.ico"),
        "--add-data", f"{BASE_DIR / 'app_icon_pro.png'};.",
        "--add-data", f"{BASE_DIR / 'app_icon_pro.ico'};.",
        "--add-data", f"{BASE_DIR / 'eos_probe.exe'};.",
        str(BASE_DIR / "openeos_pro.py")
    ]
    if not run_cmd(cmd_pro):
        print("\n[ОШИБКА] Сборка OpenEOS_PRO.exe не удалась!")
        return False

    # Копирование вспомогательного файла probe в dist
    probe_src = BASE_DIR / "eos_probe.exe"
    if probe_src.exists():
        shutil.copy2(probe_src, dist_dir / "eos_probe.exe")

    print("\n" + "=" * 65)
    print(" [УСПЕХ] Сборка успешно завершена!")
    print(f" Готовые файлы находятся в папке: {dist_dir}")
    print("   • dist/OpenEOS.exe       (Базовая версия для публикации)")
    print("   • dist/OpenEOS_PRO.exe   (Pro версия для личной работы)")
    print("=" * 65 + "\n")
    return True

if __name__ == "__main__":
    success = build_pyinstaller()
    if not success:
        sys.exit(1)
