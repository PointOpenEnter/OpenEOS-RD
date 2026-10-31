"""Automated Git synchronization for OpenEOS-RD (PointOpenEnter)."""
from __future__ import annotations

import os
import subprocess
import sys

REPO_URL = "https://github.com/PointOpenEnter/OpenEOS-RD.git"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

GIT_CANDIDATES = [
    "git",
    r"C:\Program Files\Git\cmd\git.exe",
    r"C:\Program Files\Git\bin\git.exe",
    r"C:\Program Files (x86)\Git\cmd\git.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\cmd\git.exe"),
]

GIT_CMD = "git"


def find_git() -> str | None:
    for candidate in GIT_CANDIDATES:
        try:
            res = subprocess.run([candidate, "--version"], capture_output=True, text=True)
            if res.returncode == 0:
                return candidate
        except Exception:
            continue
    return None


def run_git(args: list[str]) -> int:
    cmd = [GIT_CMD, *args]
    print(f">> {' '.join(cmd)}")
    sys.stdout.flush()
    res = subprocess.run(cmd, cwd=PROJECT_DIR)
    return res.returncode


def main() -> int:
    global GIT_CMD

    print("=" * 60)
    print("      OpenEOS-RD — Синхронизация репозитория GitHub")
    print("=" * 60)
    print(f"Репозиторий:   {REPO_URL}")
    print(f"Папка проекта: {PROJECT_DIR}\n")

    # 1. Поиск утилиты git
    found_git = find_git()
    if not found_git:
        print("\n[ОШИБКА] Утилита git не найдена в системе.")
        print("Пожалуйста, убедитесь, что Git для Windows установлен.")
        input("\nНажмите Enter для выхода...")
        return 1

    GIT_CMD = found_git
    ver = subprocess.run([GIT_CMD, "--version"], capture_output=True, text=True).stdout.strip()
    print(f"[OK] Используется Git: {GIT_CMD} ({ver})")

    # 2. Настройка автора коммитов
    subprocess.run([GIT_CMD, "config", "user.name", "PointOpenEnter"], cwd=PROJECT_DIR)
    subprocess.run([GIT_CMD, "config", "user.email", "PointOpenEnter@users.noreply.github.com"], cwd=PROJECT_DIR)

    # 3. Добавление всех файлов по структуре
    print("\n[1/3] Индексация файлов (включая архив legacy/v0.3.1)...")
    run_git(["add", "."])

    # 4. Фиксация коммита и релизных тегов v0.4.1 и v0.3.1
    print("\n[2/3] Создание коммита и релизных тегов...")
    run_git(["commit", "-m", "feat: Add v0.3.1 legacy archive and eliminate theme startup blink"])
    run_git(["tag", "-f", "-a", "v0.4.1", "-m", "OpenEOS Release v0.4.1 (Stable Fluent UI, Camera Icon, Fixed Geometry)"])
    run_git(["tag", "-a", "v0.3.1", "-m", "OpenEOS Release v0.3.1 (Legacy light-theme baseline)"])

    # 5. Отправка в GitHub (ветка main и все теги)
    print("\n[3/3] Отправка в GitHub (ветка main и теги v0.4.1, v0.3.1)...")
    push_code = run_git(["push", "-u", "origin", "main", "--tags"])

    if push_code == 0:
        print("\n" + "=" * 60)
        print("[УСПЕХ] Все изменения, архив v0.3.1 и теги успешно отправлены в GitHub!")
        print(f"Страница репозитория: {REPO_URL[:-4]}")
        print("=" * 60)
    else:
        print("\n[ИНФО] Повторная отправка с авто-синхронизацией...")
        run_git(["pull", "origin", "main", "--rebase"])
        push_code = run_git(["push", "-u", "origin", "main", "--tags"])

    input("\nНажмите Enter для завершения...")
    return push_code


if __name__ == "__main__":
    sys.exit(main())
