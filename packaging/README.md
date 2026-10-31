# Руководство по сборке дистрибутива (Packaging)

В этом каталоге описан процесс сборки автономного исполняемого файла `OpenEOS.exe` для 64-битных операционных систем Windows 10 и Windows 11.

---

## ⚙️ Требования к окружению сборщика

Для сборки автономного дистрибутива на компьютере разработчика необходимы:
1. **Python 64-bit (версии 3.10, 3.11 или 3.12)**:
   * Окружение `build-env` с установленными пакетами:
     ```bash
     pip install pyinstaller tkinterdnd2
     ```
2. **Движок ExifTool (Strawberry Perl Engine)**:
   * Располагается в системном каталоге `C:\Tools\ExifTool\`:
     * `exiftool.exe`
     * Папка `exiftool_files/` (содержит `perl.exe`, `exiftool.pl` и каталог модулей `lib/`).

---

## 🚀 Запуск сборки

Сборка осуществляется запуском командного файла в корне проекта:
```cmd
build.bat
```
Файл `build.bat` вызывает полный сценарий `build_OpenEOS.bat`.

---

## 🔄 Шаги конвейера сборки (Build Pipeline)

Скрипт `build_OpenEOS.bat` автоматически выполняет 4 последовательных этапа:

### Этап 1: Проверка инструментов
Проверяется наличие Python, PyInstaller, TkinterDnD2 и файлов Strawberry Perl в `C:\Tools\ExifTool`.

### Этап 2: Генерация иконок и подготовка исходника
1. Запускается автономный скрипт `create_icons.py`, формирующий:
   * `app_icon.ico` (Windows Icon с пятью разрешениями: 256, 64, 48, 32, 16);
   * `app_icon.png` (высококачественный векторный растр со сглаживанием SSAA).
2. Скрипт `prepare_for_build.py` копирует `openeos.py` в промежуточный `openeos_portable.py`.

### Этап 3: Компиляция через PyInstaller
Вызывается PyInstaller со строгими флагами:
```cmd
python -m PyInstaller ^
 --noconfirm ^
 --clean ^
 --onefile ^
 --windowed ^
 --noupx ^
 --name OpenEOS ^
 --icon app_icon.ico ^
 --distpath dist ^
 --workpath build ^
 --specpath build_spec ^
 --add-binary "C:\Tools\ExifTool\exiftool.exe;." ^
 --add-data "C:\Tools\ExifTool\exiftool_files;exiftool_files" ^
 --add-data "app_icon.png;." ^
 --add-data "app_icon.ico;." ^
 --collect-all tkinterdnd2 ^
 --hidden-import tkinterdnd2 ^
 openeos_portable.py
```

* **`--windowed`**: предотвращает появление чёрного консольного окна при запуске.
* **`--noupx`**: отключает упаковщики UPX, исключая ложные срабатывания антивирусов Windows Defender.
* **`--add-data`**: встраивает Strawberry Perl и иконки прямо в тело `.exe`.

### Этап 4: Верификация артефакта
Скрипт проверяет наличие готового файла `dist\OpenEOS.exe`, выводит его точный размер в байтах и открывает папку с результатом.

---

## 📦 Публикация релизов
* Готовые `.exe` файлы **не коммитятся в Git-репозиторий**.
* Они прикрепляются вручную к соответствующему [GitHub Release](https://github.com/PointOpenEnter/OpenEOS-RD/releases), снабженному Git-тегом версии (`v0.4.1`).
