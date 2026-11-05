# REVIEW BUNDLE: INDEPENDENT TECHNICAL AUDIT (DEEPSEEK AUDIT PACKAGE)

**Project:** OpenEOS DIGIC X Diagnostic Readout Module (Phase A & Phase B)  
**Target Platform:** Canon EOS R6 Mark II (USB PID `0x330B`, VID `0x04A9`, Subsystem `K481`, FW `1.7.0`)  
**Document Class:** Technical Review Bundle & Independent Audit Manifest (Revision 3.2)  
**Security Directives:** Strict Read-Only, Zero Code Changes, No Live Camera Connection, Intact Core OpenEOS  

---

## 1. Назначение пакета (Executive Summary)

Данный пакет `ReviewBundle` сформирован для независимого технического и форензического аудита (включая аудит моделью DeepSeek) модулей Фазы A и Фазы B проекта OpenEOS.

Кодовая база включает результаты всех исправлений, зафиксированных в документах [`IMPLEMENTATION_PHASE_A_B_AUDIT.md`](file:///d:/AI/ReviewBundle/IMPLEMENTATION_PHASE_A_B_AUDIT.md), [`IMPLEMENTATION_PHASE_A_B_REV2_REPORT.md`](file:///d:/AI/ReviewBundle/IMPLEMENTATION_PHASE_A_B_REV2_REPORT.md), [`IMPLEMENTATION_PHASE_A_B_REV2_1_REPORT.md`](file:///d:/AI/ReviewBundle/IMPLEMENTATION_PHASE_A_B_REV2_1_REPORT.md), [`IMPLEMENTATION_PHASE_A_B_REV3_1_REPORT.md`](file:///d:/AI/ReviewBundle/IMPLEMENTATION_PHASE_A_B_REV3_1_REPORT.md) и [`IMPLEMENTATION_PHASE_A_B_REV3_2_REPORT.md`](file:///d:/AI/ReviewBundle/IMPLEMENTATION_PHASE_A_B_REV3_2_REPORT.md):
1. **Фаза A:** Побайтово верифицированные офлайн-декодеры свойств `0x12000001`, `0x12000003` и `0x12000005`, точные генераторы командных контейнеров (20B `0x9052` `[0, 1]`, 55B Data OUT `FA_GetProperty` и 12B/24B Fetch `0x9053`).
2. **Фаза B:** Модель состояний PTP (State Machine) с полным разграничением фаз Command / Data / Response, фильтр безопасности `ProtocolGuard` с предварительной валидацией сырых байтов перед отправкой в USB-пайп, транспортный каркас Windows Still Image (`usbscan.sys`) с арбитражем EDSDK и RAII-дескрипторами `SafeDeviceHandle`.
3. **Ревизия 2.1:** Точечный пересчёт и приведение всех 12 кодов `IOCTL` драйвера `usbscan.sys` в 100% соответствие с Microsoft DDK `usbscan.h` (устранено смещение `IOCTL_INDEX = 0x0800`), а также доказательство достаточности базового дескриптора устройства без суффиксов.
4. **Ревизия 3.1:** Устранение расхождения `to_bytes`/`serialize`, укрепление границы Protocol Guard (`PTP Container -> Serialization -> Protocol Guard -> USB WriteFile`), строгое гейтирование физического вывода.
5. **Ревизия 3.2:** Безусловная блокировка физической отправки (удаление переключателя `PHYSICAL_IO_ENABLED`, безусловный `RuntimeError` в `_write_raw_wire_bytes()`, нулевой путь к Win32 `WriteFile`), разделение тестов последовательности и безопасности вызовов (с проверкой через mock Win32 API), переход к нейтральной семантике `shutter_counter` с сохранением `mechanical_shutter_counter` как устаревшего свойства-алиаса (с предупреждением `DeprecationWarning`). Всего **69 unit-тестов**.

---

## 2. Структура пакета ReviewBundle

```
ReviewBundle/
│
├── REVIEW_README.md                         # Данный документ: инструкции, окружение, статус тестов, вопросы аудита
├── PCAPNG_EVIDENCE_SAMPLES.md               # Сводный каталог сырых HEX-дампов, EPB-фреймов и смещений из р62.pcapng
│
├── OPENEOS_ONLINE_READ_SPEC_V1.2.md         # Окончательная спецификация протокола чтения (Revision 3.3 / V1.2)
├── READ_ONLY_IMPLEMENTATION_PLAN.md         # Инженерный план реализации и матрица рисков
├── IMPLEMENTATION_PHASE_A_B_REPORT.md       # Инженерный отчёт о реализации фаз A и B
├── IMPLEMENTATION_PHASE_A_B_AUDIT.md        # Углублённый форензический и системный аудит реализации
├── IMPLEMENTATION_PHASE_A_B_REV2_REPORT.md  # Отчёт по замечаниям независимого аудита DeepSeek (Rev 2)
├── IMPLEMENTATION_PHASE_A_B_REV2_1_REPORT.md# Отчёт о точечной верификации кодов IOCTL и адресации пайпов (Rev 2.1)
├── IMPLEMENTATION_PHASE_A_B_REV3_1_REPORT.md# Отчёт по сквозному защищённому транспорту и границе Guard (Rev 3.1)
├── IMPLEMENTATION_PHASE_A_B_REV3_2_REPORT.md# Финальный отчёт безопасности Фазы B и нейтрализации семантики (Rev 3.2)
│
├── openeos_ptp/                             # Исходный код сервисного PTP-модуля
│   ├── __init__.py                          # Публичный API пакета и экспортируемые сущности (включая 12 IOCTL)
│   ├── constants.py                         # PTP OpCodes, GUID Still Image/WPD, 12 IOCTL usbscan.sys, Property IDs
│   ├── decoders.py                          # Офлайн-декодеры 0x12000001, 0x12000003, 0x12000005 (shutter_counter)
│   ├── payloads.py                          # Сериализаторы контейнеров PTP (Command, Data OUT, Fetch, Response)
│   ├── protocol_guard.py                    # Межсетевой экран протокола, конечный автомат и фильтр безопасности
│   ├── transport.py                         # Windows Still Image (usbscan.sys), PipeInfo, SafeDeviceHandle
│   └── mock_transport.py                    # Тестовый эмулятор камеры в памяти на основе р62.pcapng
│
└── tests/                                   # Набор unit-тестов
    ├── __init__.py                          # Инициализатор пакета тестов
    ├── test_phase_a_decoders.py             # 12 тестов: нейтральный shutter_counter, DeprecationWarning, opaque_tail
    ├── test_phase_a_payloads.py             # 9 тестов: генераторы 20B/55B/12B/24B контейнеров, смещения, отказ неизвестных свойств
    ├── test_phase_b_protocol_guard.py       # 16 тестов: FSM-переходы, запрет 0x905A/B/C/28/54, отсечение повторов TxID
    ├── test_phase_b_transport_mock.py       # 20 тестов: Still Image SetupAPI, PipeIndex, SafeHandle, арбитраж EDSDK, 12 IOCTL
    ├── test_phase_b_protected_transport.py  # 12 тестов: Guard sequence, Guard security, Win32 WriteFile block mock, cycle
    └── run_all_tests.py                     # Автономный раннер всего тестового комплекта (69 тестов)
```

---

## 3. Системные требования и окружение

- **Версия Python:** Python 3.8, 3.9, 3.10, 3.11, 3.12 или выше.
- **Внешние зависимости:** **0 (отсутствуют)**. Используется исключительно стандартная библиотека Python:
  - `ctypes` (Win32 API: `kernel32`, `setupapi`, структуры драйвера `usbscan.sys`);
  - `struct` (бинарная распаковка и упаковка Little-Endian пакетов);
  - `unittest` (тестовый фреймворк);
  - `dataclasses`, `enum`, `typing`, `time`, `re`, `sys`, `os`, `threading`.
- **Целевая ОС:** Windows 10 / Windows 11 (для модулей прямого доступа `transport.py`). Тесты `test_phase_a_*.py`, `test_phase_b_protocol_guard.py` и `mock_transport.py` полностью платформонезависимы и выполняются на Windows, Linux и macOS.

---

## 4. Статус выполнения тестов (Test Execution Status)

### Фактические результаты локальной верификации (Windows, Python 3.14.10):
Тестовый комплект расширен до **69 тестов** (56 базовых + 12 в protected_transport + 1 в decoders):
- `test_phase_a_decoders.py`: 12 тестов — OK (нейтральный `shutter_counter`, `DeprecationWarning` для устаревшего алиаса)
- `test_phase_a_payloads.py`: 9 тестов — OK
- `test_phase_b_protocol_guard.py`: 16 тестов — OK
- `test_phase_b_transport_mock.py`: 20 тестов — OK
- `test_phase_b_protected_transport.py`: 12 тестов (REV 3.2: разделение sequence/security, блокировка Win32 WriteFile с mock) — OK
- **Итоговый статус:** **69 из 69 тестов успешно пройдены (Failures = 0, Errors = 0, 100% PASS)**.
- Байткод: `python -m compileall openeos_ptp tests` — OK (0 errors).

### Ограничение среды ассистента:
При попытке вызова команд через инструмент ассистента возвращается платформенная ошибка:
```
run_command: failed to build agentapi shell injection: failed to format agentapi script: Shell Injection Detected
```
**Причина:** Имя системного каталога пользователя Windows `C:\Users\and!m\` содержит восклицательный знак `!`. Встроенный санитайзер хост-окружения ассистента блокирует форматирование скриптов оболочки.  
Фактический статус тестов зафиксирован по локальному выполнению пользователем.

### Инструкция для независимого аудитора по локальному запуску:
Для подтверждения работоспособности всех модулей выполните в корне пакета:

```powershell
# 1. Запуск набора REV 3.2 (сквозной защищённый транспорт и блокировка WriteFile):
python -m unittest tests.test_phase_b_protected_transport.TestProtectedUsbPtpTransportPipeline -v

# 2. Запуск автономного раннера всех 69 тестов:
python tests/run_all_tests.py

# 3. Запуск через встроенный тестовый раннер Python с подробным выводом:
python -m unittest discover -s tests -p "test_*.py" -v

# 4. Проверка синтаксической чистоты и компиляция байткода:
python -m compileall openeos_ptp tests
```

Ожидаемый результат: **69 тестов, Failures = 0, Errors = 0, 100% PASS**.

---

## 5. Вопросы для глубокой проверки аудитором (DeepSeek Audit Checkpoints)

Просим независимого технического эксперта / аудитора DeepSeek провести предметный аудит пяти ключевых аспектов системной интеграции:

### Чекпоинт 1: Фактическая регистрация Canon R6 Mark II через `GUID_DEVINTERFACE_IMAGE` и драйвер `usbscan.sys`
- **Контекст:** В Windows цифровые камеры Still Image могут регистрироваться под двумя различными системными классами:
  * Класс Still Image (STI / WIA / `usbscan.sys`): `GUID_DEVINTERFACE_IMAGE = "{6BDD1FC6-810F-11D0-BEC7-08002BE2092F}"` (из `sti.h` / `devguid.h`).
  * Класс Windows Portable Devices (WPD / MTP): `GUID_DEVINTERFACE_WPD = "{6AC27878-A6FA-4125-BA57-F98F7A78810E}"` (из `wpd_guid.h`).
- **Вопрос аудитору:** Проверьте корректность использования `GUID_DEVINTERFACE_IMAGE` как основного интерфейса для прямого взаимодействия с `usbscan.sys`. Подтвердите, что попытка открытия WPD-пути через Win32 `CreateFileW` не даёт прямого доступа к Bulk-пайпам без посредничества MTP-драйвера `WpdMtp.sys`.

### Чекпоинт 2: Корректность кодов Win32 IOCTL по спецификации Microsoft `usbscan.h` (Ревизия 2.1)
- **Контекст:** В Ревизии 2.1 устранены ранние расхождения кодов IOCTL. С учётом базового смещения вендорных функций `IOCTL_INDEX = 0x0800` формулой `CTL_CODE(0x8000, 0x0800 + i, METHOD_BUFFERED, FILE_ANY_ACCESS)` получены официальные значения:
  * `IOCTL_GET_VERSION = 0x80002000` (Function `0x0800`)
  * `IOCTL_CANCEL_IO = 0x80002004` (Function `0x0801`)
  * `IOCTL_WAIT_ON_DEVICE_EVENT = 0x80002008` (Function `0x0802`)
  * `IOCTL_READ_REGISTERS = 0x8000200C` (Function `0x0803`)
  * `IOCTL_WRITE_REGISTERS = 0x80002010` (Function `0x0804`)
  * `IOCTL_GET_CHANNEL_ALIGN_RQST = 0x80002014` (Function `0x0805`)
  * `IOCTL_GET_DEVICE_DESCRIPTOR = 0x80002018` (Function `0x0806`)
  * `IOCTL_RESET_PIPE = 0x8000201C` (Function `0x0807`)
  * `IOCTL_GET_USB_DESCRIPTOR = 0x80002020` (Function `0x0808`)
  * `IOCTL_SEND_USB_REQUEST = 0x80002024` (Function `0x0809`)
  * `IOCTL_GET_PIPE_CONFIGURATION = 0x80002028` (Function `0x080A`)
  * `IOCTL_SET_TIMEOUT = 0x8000202C` (Function `0x080B`)
- **Вопрос аудитору:** Подтвердите математическую точность расчёта макроса `CTL_CODE` для всех 12 IOCTL при базовом `FILE_DEVICE_USB_SCAN = 0x8000` и смещении `IOCTL_INDEX = 0x0800`.

### Чекпоинт 3: Соответствие структур `ctypes` официальным `USBSCAN_PIPE_CONFIGURATION` и `USBSCAN_PIPE_INFORMATION`
- **Контекст:** В модуле [`transport.py`](file:///d:/AI/ReviewBundle/openeos_ptp/transport.py) объявлены:
  ```python
  class USBSCAN_PIPE_INFORMATION(ctypes.Structure):
      _fields_ = [
          ("MaximumPacketSize", ctypes.c_ushort),
          ("EndpointAddress", ctypes.c_ubyte),
          ("Interval", ctypes.c_ubyte),
          ("PipeType", ctypes.c_uint),  # RAW_PIPE_TYPE (0=Control, 1=Isoch, 2=BulkIn, 3=BulkOut, 4=Interrupt)
      ]

  class USBSCAN_PIPE_CONFIGURATION(ctypes.Structure):
      _fields_ = [
          ("NumberOfPipes", ctypes.c_ulong),
          ("PipeInfo", USBSCAN_PIPE_INFORMATION * USBSCAN_MAX_NUM_PIPES), # USBSCAN_MAX_NUM_PIPES = 8
      ]
  ```
- **Вопрос аудитору:** Оцените выравнивание полей (packing), размеры типов данных и смещения в структурах на платформе Win32/x64 по стандарту компилятора MSVC.

### Чекпоинт 4: Различие между USB Endpoint Address, Pipe Index и USBSCAN_PIPE_TYPE; достаточность базового handle
- **Контекст:** В USB-стеке аппаратный адрес конечной точки кодируется в дескрипторе эндпоинта (например, `0x02` для Bulk OUT, `0x81` для Bulk IN, `0x83` для Interrupt IN). В драйвере `usbscan.sys` при вызовах `IOCTL_RESET_PIPE` и `IOCTL_CANCEL_IO` Microsoft специфицирует передачу перечисления `PIPE_TYPE` (`EVENT_PIPE=0`, `READ_DATA_PIPE=1`, `WRITE_DATA_PIPE=2`, `ALL_PIPE=3`). Функция `format_pipe_specific_device_path` помечена как экспериментальный helper и исключена из production-кода, так как Canon EOS R6 Mark II имеет строго одну тройку эндпоинтов (Bulk IN `0x81`, Bulk OUT `0x02`, Interrupt IN `0x83`), для которой открытие базового дескриптора устройства автоматически связывает `ReadFile` с Bulk IN, а `WriteFile` с Bulk OUT.
- **Вопрос аудитору:** Подтвердите корректность отказа от суффиксов в `DevicePath` в пользу базового дескриптора и соответствие реализации `reset_usbscan_pipe`/`cancel_usbscan_io` спецификации `usbscan.h`.

### Чекпоинт 5: Отсутствие ложных предположений о совместимости WPD и низкоуровневого USB
- **Контекст:** Некоторые открытые реализации ошибочно предполагают, что устройство Still Image может одновременно опрашиваться через WPD MTP API и через Win32 `CreateFileW`.
- **Вопрос аудитору:** Проверьте реализацию [`CameraAccessManager`](file:///d:/AI/ReviewBundle/openeos_ptp/transport.py#L355-L451). Подтвердите, что механизм эксклюзивного захвата с бэкоффом и колбэками освобождения интерфейса EDSDK корректно изолирует низкоуровневый доступ к устройству.

---

## 6. Базовый захват PCAPNG и доказательная база

- **Файл захвата:** `р62.pcapng`
- **Размер файла:** `29,054,644 байта`
- **SHA-256:** `74dc1ebdd9f682af84bdaf88f341668f0587a2763ace0ae8f8afcd1b5350dc08`
- **Соответствие контрольным точкам:** Все 3 сервисных свойства (`0x12000001`, `0x12000003`, `0x12000005`) детально расписаны в файле [`PCAPNG_EVIDENCE_SAMPLES.md`](file:///d:/AI/ReviewBundle/PCAPNG_EVIDENCE_SAMPLES.md) с указанием номеров Wireshark фреймов (EPB #69, #70, #71, #72, #73, #74, #87, #88, #89, #90, #91, #92, #173, #174, #175, #176, #177, #178) и точных байтовых смещений.
