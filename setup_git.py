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
    print("\n[1/4] Индексация файлов...")
    run_git(["add", "."])

    # 4. Фиксация коммита (если есть изменения)
    print("\n[2/4] Проверка изменений и создание коммита...")
    status = subprocess.run([GIT_CMD, "status", "--porcelain"], cwd=PROJECT_DIR, capture_output=True, text=True).stdout.strip()
    if status:
        run_git(["commit", "-m", "release: Bump version to v0.4.2 (Zero startup flash, optimized latency, 500k R6m2 rating, legacy archive)"])
    else:
        print("[OK] Все изменения уже зафиксированы в Git.")

    # 5. Обновление релизных тегов
    print("\n[3/4] Установка релизных тегов...")
    run_git(["tag", "-f", "-a", "v0.4.2", "-m", "OpenEOS Release v0.4.2 (Zero Startup Flash, Optimized Latency, Legacy v0.3.1 Archive)"])
    check_v031 = subprocess.run([GIT_CMD, "tag", "-l", "v0.3.1"], cwd=PROJECT_DIR, capture_output=True, text=True).stdout.strip()
    if not check_v031:
        run_git(["tag", "-a", "v0.3.1", "-m", "OpenEOS Release v0.3.1 (Legacy light-theme baseline)"])

    # 6. Отправка ветки main и тегов с флагом --force
    print("\n[4/4] Отправка в GitHub (ветка main и теги)...")
    push_main = run_git(["push", "-u", "origin", "main"])
    push_tags = run_git(["push", "origin", "--tags", "--force"])

    if push_main == 0 and push_tags == 0:
        print("\n" + "=" * 60)
        print("[УСПЕХ] Синхронизация завершена без единой ошибки!")
        print("=" * 60)
        print(f"• Главная страница:      {REPO_URL[:-4]}")
        print(f"• Архив v0.3.1 (папка):  {REPO_URL[:-4]}/tree/main/legacy/v0.3.1")
        print(f"• Список тегов и версий: {REPO_URL[:-4]}/tags")
        print("=" * 60)
    else:
        print("\n[ИНФО] Повторная отправка с авто-синхронизацией...")
        run_git(["pull", "origin", "main", "--rebase"])
        run_git(["push", "-u", "origin", "main"])
        run_git(["push", "origin", "--tags", "--force"])

    input("\nНажмите Enter для завершения...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
