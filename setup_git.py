"""Automated Git initialization and push for OpenEOS-RD."""
from __future__ import annotations

import os
import subprocess
import sys

REPO_URL = "https://github.com/berr3374-lgtm/OpenEOS-RD.git"
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
            res = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                text=True,
            )
            if res.returncode == 0:
                return candidate
        except Exception:
            continue
    return None


def run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    cmd = [GIT_CMD, *args]
    print(f">> {' '.join(cmd)}")
    res = subprocess.run(
        cmd,
        cwd=PROJECT_DIR,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if res.stdout and res.stdout.strip():
        print(res.stdout.strip())
    if res.stderr and res.returncode != 0:
        print(res.stderr.strip())
    if check and res.returncode != 0:
        raise RuntimeError(f"Git command failed: {' '.join(cmd)}\n{res.stderr}")
    return res


def main() -> int:
    global GIT_CMD

    print("=" * 60)
    print("      OpenEOS-RD — Инициализация и публикация в GitHub")
    print("=" * 60)
    print(f"Репозиторий:   {REPO_URL}")
    print(f"Папка проекта: {PROJECT_DIR}\n")

    # 1. Поиск утилиты git (в PATH и стандартных папках установки)
    found_git = find_git()
    if not found_git:
        print("\n[ОШИБКА] Утилита git не найдена в системе.")
        print("Если вы только что установили Git, возможно, требуется перезапустить окно консоли.")
        print("Официальный установщик: https://git-scm.com/download/win")
        input("\nНажмите Enter для выхода...")
        return 1

    GIT_CMD = found_git
    ver = subprocess.run([GIT_CMD, "--version"], capture_output=True, text=True).stdout.strip()
    print(f"[OK] Используется Git: {GIT_CMD} ({ver})")

    # 2. Проверка и настройка имени автора коммита (для свежей установки Git)
    user_name = subprocess.run([GIT_CMD, "config", "user.name"], capture_output=True, text=True).stdout.strip()
    if not user_name:
        print("[INFO] Первичная настройка профиля автора Git (berr3374-lgtm)...")
        subprocess.run([GIT_CMD, "config", "user.name", "berr3374-lgtm"], cwd=PROJECT_DIR)
        subprocess.run([GIT_CMD, "config", "user.email", "berr3374-lgtm@users.noreply.github.com"], cwd=PROJECT_DIR)

    # 3. Инициализация репозитория
    git_dir = os.path.join(PROJECT_DIR, ".git")
    if not os.path.isdir(git_dir):
        print("\n[1/5] Инициализация нового Git-репозитория...")
        run_git(["init", "-b", "main"])
    else:
        print("\n[1/5] Репозиторий уже инициализирован.")
        run_git(["branch", "-M", "main"], check=False)

    # 4. Настройка remote origin
    print("\n[2/5] Настройка удаленного репозитория...")
    res = run_git(["remote", "get-url", "origin"], check=False)
    if res.returncode == 0:
        run_git(["remote", "set-url", "origin", REPO_URL])
    else:
        run_git(["remote", "add", "origin", REPO_URL])

    # 5. Добавление файлов по .gitignore
    print("\n[3/5] Добавление файлов по структуре...")
    run_git(["add", "."])

    # 6. Фиксация коммита и релизного тега v0.4.1
    print("\n[4/5] Создание коммита и релизного тега v0.4.1...")
    commit_res = run_git(
        ["commit", "-m", "feat: Initial OpenEOS-RD repository structure (v0.4.1)"],
        check=False,
    )
    if commit_res.returncode == 0:
        print("[OK] Коммит успешно создан.")
    else:
        print("[INFO] Рабочая директория чиста или изменения уже закоммичены.")

    run_git(
        ["tag", "-a", "v0.4.1", "-m", "OpenEOS Release v0.4.1 (Stable Fluent UI, Camera Icon, Fixed Geometry)"],
        check=False,
    )

    # 7. Отправка в GitHub (ветка main и теги)
    print("\n[5/5] Отправка в GitHub (ветка main и теги)...")
    push_res = run_git(["push", "-u", "origin", "main", "--tags"], check=False)

    if push_res.returncode == 0:
        print("\n" + "=" * 60)
        print("[УСПЕХ] Все файлы и теги успешно отправлены в GitHub!")
        print(f"Страница репозитория: https://github.com/berr3374-lgtm/OpenEOS-RD")
        print("=" * 60)
    else:
        print("\n" + "-" * 60)
        print("[ВНИМАНИЕ] Не удалось выполнить push с первого раза:")
        err_text = (push_res.stderr or push_res.stdout or "").strip()
        print(err_text)

        # Если в удаленном репозитории уже были файлы (например, дефолтный README с GitHub)
        if "fetch first" in err_text or "non-fast-forward" in err_text:
            print("\nВ удаленном репозитории на GitHub уже были файлы (например, авто-README).")
            print("Выполняем синхронизацию: git pull --rebase...")
            pull_res = run_git(["pull", "origin", "main", "--rebase"], check=False)
            if pull_res.returncode == 0:
                print("Синхронизация успешна. Повторяем отправку...")
                push_res2 = run_git(["push", "-u", "origin", "main", "--tags"], check=False)
                if push_res2.returncode == 0:
                    print("\n" + "=" * 60)
                    print("[УСПЕХ] Все файлы успешно отправлены в GitHub!")
                    print(f"Страница репозитория: https://github.com/berr3374-lgtm/OpenEOS-RD")
                    print("=" * 60)
                    input("\nНажмите Enter для завершения...")
                    return 0

        print("\nЧто сделать сейчас:")
        print("1. В открывшемся окне браузера подтвердите вход в GitHub (Sign in with browser).")
        print("2. Либо выполните в консоли команду принудительной отправки:")
        print("     git push -u origin main --force --tags")
        print("-" * 60)

    input("\nНажмите Enter для завершения...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
