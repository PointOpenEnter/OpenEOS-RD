#!/usr/bin/env bash
# OpenEOS — Сборка нативного приложения .app и образа .dmg для macOS
# Поддерживает Apple Silicon (M1 / M2 / M3) и Intel

set -e
cd "$(dirname "$0")"

echo "======================================================================"
echo " OpenEOS — Сборка для macOS (.app и .dmg)"
echo "======================================================================"

if ! command -v python3 &> /dev/null; then
    echo "[ОШИБКА] Python 3 не найден в системе."
    echo "Установите Python 3 (brew install python python-tk) и повторите сборку."
    exit 1
fi

# Проверка PyInstaller
if ! python3 -m pip show pyinstaller &> /dev/null; then
    echo "Установка PyInstaller..."
    python3 -m pip install pyinstaller
fi

# Очистка предыдущих сборок
rm -rf build dist
mkdir -p dist

# Сборка OpenEOS Community Edition (.app)
echo "[1/2] Сборка OpenEOS.app (Community Edition)..."
python3 -m PyInstaller \
    --noconfirm \
    --windowed \
    --name "OpenEOS" \
    --add-data "app_icon.png:." \
    openeos.py

# Сборка OpenEOS PRO Edition (.app)
echo "[2/2] Сборка OpenEOS_PRO.app (Pro Edition)..."
python3 -m PyInstaller \
    --noconfirm \
    --windowed \
    --name "OpenEOS_PRO" \
    --add-data "app_icon_pro.png:." \
    openeos_pro.py

# Создание образов .dmg встроенной утилитой macOS hdiutil
echo "Упаковка в DMG..."
if command -v hdiutil &> /dev/null; then
    hdiutil create -volname "OpenEOS" -srcfolder "dist/OpenEOS.app" -ov -format UDZO "dist/OpenEOS.dmg"
    hdiutil create -volname "OpenEOS_PRO" -srcfolder "dist/OpenEOS_PRO.app" -ov -format UDZO "dist/OpenEOS_PRO.dmg"
    echo "======================================================================"
    echo " [УСПЕХ] Сборка на macOS завершена!"
    echo " Готовые образы дисков находятся в папке dist/:"
    echo "   • dist/OpenEOS.dmg"
    echo "   • dist/OpenEOS_PRO.dmg"
    echo "======================================================================"
else
    echo "Приложения .app созданы в папке dist/:"
    echo "   • dist/OpenEOS.app"
    echo "   • dist/OpenEOS_PRO.app"
fi
