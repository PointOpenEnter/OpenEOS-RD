#!/usr/bin/env bash
# OpenEOS — Запуск на macOS (Apple Silicon M1 Pro / Intel)
# Не требует сборки или бинарных файлов — запускается нативно через Python 3

cd "$(dirname "$0")"

echo "=== OpenEOS: Запуск на macOS ==="

# Проверка наличия Python 3
if ! command -v python3 &> /dev/null; then
    echo "Ошибка: python3 не найден в системе."
    echo "Установите Python 3 с официального сайта python.org или через 'brew install python-tk'."
    exit 1
fi

# Проверка модуля tkinter
python3 -c "import tkinter" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Предупреждение: Tkinter не найден в системном Python."
    echo "Если окно не откроется, выполните в терминале:"
    echo "  brew install python-tk"
fi

# Запуск приложения
echo "Запуск OpenEOS Community Edition..."
python3 openeos.py
