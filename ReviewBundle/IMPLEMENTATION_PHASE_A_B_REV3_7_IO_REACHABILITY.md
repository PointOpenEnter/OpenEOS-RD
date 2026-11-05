# OpenEOS REV 3.7 — Аудит достижимости физического USB I/O и граф вызовов Win32 API

**Дата:** 2 ноября 2026 г.  
**Проект:** OpenEOS (Canon EOS R6 Mark II PTP Read-Only Diagnostic Subsystem)  
**Ревизия:** REV 3.7  
**Рабочий каталог:** `D:\AI`  
**Целевая платформа:** Windows 10/11 x64, Python 3.14.10  
**Статус исходного кода:** Не изменялся (100% совпадение с REV 3.4 / REV 3.5 / REV 3.6)  
**Статус физического подключения камеры:** Не подключалась (кабель отключён, 0 байт на USB)  
**Итоговый статус аудита:** **PARTIALLY VERIFIED** (Программная изоляция и отсутствие скрытых путей в коде — `VERIFIED`, поведение ядра Win32/драйвера при различных режимах открытия дескриптора — `PARTIALLY VERIFIED`, обязательность `GENERIC_WRITE` для `FILE_ANY_ACCESS` IOCTL — `UNKNOWN`)

---

## Введение и цели аудита

Целью настоящего аудита (REV 3.7) является строгое установление того, какие функции и методы подсистемы `openeos_ptp` способны инициировать физическое взаимодействие с USB-шиной и контроллером устройства, как эти функции связаны между собой в графе вызовов, и достижимы ли они из текущих публичных сценариев выполнения и графического интерфейса пользователя.

Аудит проведён методом статического анализа кодовой базы без модификации файлов, без подключения камеры и без выполнения аппаратного ввода-вывода.

---

## 1. Исчерпывающий поиск и аудит вызовов `ReadFile`

В ходе сквозного аудита всех файлов проекта (`openeos_ptp/*.py`, `tests/*.py`, `OpenEOS.py`) установлено:

### 1.1. Наличие в продакшн-коде (`openeos_ptp/transport.py`)
- **Диапазон строк:** 910–919
- **Контекст:**
  ```python
  if hasattr(k_api, "ReadFile"):
      k_api.ReadFile.argtypes = [
          wintypes.HANDLE,
          ctypes.c_void_p,
          wintypes.DWORD,
          ctypes.POINTER(wintypes.DWORD),
          ctypes.c_void_p,
      ]
      k_api.ReadFile.restype = wintypes.BOOL
  ```
- **Характер вхождения:** **Объявление типов Win32 API** в функции `init_win32_api()`. Задаёт типы аргументов (`argtypes`) и возвращаемого значения (`restype`) для устранения риска некорректного маршалинга на Windows x64.
- **Реальный вызов `ReadFile(...)`:** **ОТСУТСТВУЕТ**. Ни в одной строке `transport.py` системный вызов `kernel32.ReadFile` не вызывается.

### 1.2. Наличие в тестах (`tests/test_phase_b_transport_mock.py`)
- **Диапазон строк:** 657, 687–688
- **Контекст:**
  ```python
  class DummyKernel32:
      def __init__(self):
          ...
          self.ReadFile = DummyFn()
          ...
  init_win32_api(setupapi=mock_setup, kernel32=mock_kernel)
  ...
  # 7. ReadFile
  self.assertEqual(len(mock_kernel.ReadFile.argtypes), 5)
  ```
- **Характер вхождения:** **Тестовая заглушка**. Тест проверяет, что `init_win32_api()` корректно выставил ровно 5 аргументов в сигнатуру `ReadFile`.
- **Реальный вызов `ReadFile(...)`:** **ОТСУТСТВУЕТ**.

### 1.3. Упоминания в комментариях и документации
- Строка 174: пояснение, что в `usbscan.sys` вызов `ReadFile` транслируется драйвером на Bulk IN endpoint.
- Строка 479: пояснение архитектуры Still Image.
- Строка 652: пояснение привязки Bulk IN в docstring `format_pipe_specific_device_path`.
- Строка 791: примечание в `_default_open_handle` о синхронном режиме `ReadFile/WriteFile`.
- Строка 825: перечень верифицированных API в docstring `init_win32_api`.

### 1.4. Результат поиска в остальных модулях
- `openeos_ptp/mock_transport.py`: **0 совпадений**.
- `openeos_ptp/protocol_guard.py`: **0 совпадений**.
- `openeos_ptp/payloads.py`: **0 совпадений**.
- `openeos_ptp/decoders.py`: **0 совпадений**.
- `openeos_ptp/constants.py`: **0 совпадений**.
- `OpenEOS.py`: **0 совпадений**.

### Вывод по `ReadFile`:
**Фактических вызовов `ReadFile` в проекте: 0.**  
Чтение данных с Bulk IN конечной точки в текущей версии Фазы B программно **не реализовано**. Путь вызова отсутствует.  
**Статус утверждения:** **VERIFIED**.

---

## 2. Полная инвентаризация системных вызовов Win32

Сводная классификация всех вхождений низкоуровневых Win32 API в проекте по категориям:

| Win32 API | Объявления сигнатур API | Тестовые заглушки / Mock | Реальные вызовы в коде |
|---|---|---|---|
| **`DeviceIoControl`** | [`transport.py:898-908`](file:///D:/AI/openeos_ptp/transport.py#L898-L908) | [`test_phase_b_transport_mock.py:656, 684`](file:///D:/AI/tests/test_phase_b_transport_mock.py#L656) | **5 вызовов** ([`transport.py:446, 527, 553, 587, 615`](file:///D:/AI/openeos_ptp/transport.py)) |
| **`CreateFileW`** | [`transport.py:881-892`](file:///D:/AI/openeos_ptp/transport.py#L881-L892) | [`test_phase_b_transport_mock.py:207, 395, 655, 680`](file:///D:/AI/tests/test_phase_b_transport_mock.py#L655) | **1 вызов** ([`transport.py:797`](file:///D:/AI/openeos_ptp/transport.py#L797) в `_default_open_handle`) |
| **`CloseHandle`** | [`transport.py:894-900`](file:///D:/AI/openeos_ptp/transport.py#L894-L900) | [`test_phase_b_transport_mock.py:659, 693`](file:///D:/AI/tests/test_phase_b_transport_mock.py#L659) | **1 вызов** ([`transport.py:238`](file:///D:/AI/openeos_ptp/transport.py#L238) в `SafeDeviceHandle.close`) |
| **`ReadFile`** | [`transport.py:910-919`](file:///D:/AI/openeos_ptp/transport.py#L910-L919) | [`test_phase_b_transport_mock.py:657, 687`](file:///D:/AI/tests/test_phase_b_transport_mock.py#L657) | **0 вызовов** |
| **`WriteFile`** | [`transport.py:920-929`](file:///D:/AI/openeos_ptp/transport.py#L920-L929) | [`test_phase_b_transport_mock.py:658, 690`](file:///D:/AI/tests/test_phase_b_transport_mock.py#L658), [`test_phase_b_protected_transport.py:394, 435`](file:///D:/AI/tests/test_phase_b_protected_transport.py#L394) | **0 вызовов** (заблокирован безусловным `RuntimeError`) |

---

## 3. Детальный аудит 5 вызовов `DeviceIoControl`

Все 5 реальных вызовов сосредоточены в файле [`openeos_ptp/transport.py`](file:///D:/AI/openeos_ptp/transport.py) и используют драйвер `usbscan.sys`. Ниже приведён подробный анализ каждого вызова:

### 3.1. Вызов №1: `IOCTL_GET_PIPE_CONFIGURATION`
- **Файл и строки:** [`openeos_ptp/transport.py:446–455`](file:///D:/AI/openeos_ptp/transport.py#L446-L455)
- **Вызывающий метод:** `PipeConfigurationInspector.query_usbscan_pipe_config(handle: int)`
- **Точный числовой код:** `0x80002028` (`CTL_CODE(0x8000, 0x080A, METHOD_BUFFERED, FILE_ANY_ACCESS)`)
- **Входной буфер:** `lpInBuffer = None`, `nInBufferSize = 0` (0 байт).
- **Выходной буфер:** `lpOutBuffer = ctypes.byref(pipe_cfg)` (`USBSCAN_PIPE_CONFIGURATION`, 68 байт), `nOutBufferSize = 68`.
- **Что делает функция:** Читает метаданные конечных точек USB (дескрипторы pipe) из памяти драйвера `usbscan.sys`.
- **Возможность физического USB-взаимодействия:**
  - *Инициация транзакции на шине:* **Крайне маловероятна**. Согласно спецификации Windows Driver Model (WDM), драйвер `usbscan.sys` кэширует дескрипторы интерфейса при вызове `StartDevice` во время перечисления PnP. При вызове IOCTL драйвер копирует данные из своей памяти (`DeviceExtension`) в буфер вызывающего процесса.
  - *Изменение состояния endpoint:* **Исключено**. Операция строго read-only для метаданных.
- **Статус:** **VERIFIED** для структуры и назначения вызова; **PARTIALLY VERIFIED** для низкоуровневого взаимодействия драйвера с шиной на конкретном xHCI-контроллере без аппаратного сниффера.

### 3.2. Вызов №2: `IOCTL_RESET_PIPE`
- **Файл и строки:** [`openeos_ptp/transport.py:527–536`](file:///D:/AI/openeos_ptp/transport.py#L527-L536)
- **Вызывающая функция:** `reset_usbscan_pipe(handle: int, pipe_type: USBSCAN_PIPE_TYPE)`
- **Точный числовой код:** `0x8000201C` (`CTL_CODE(0x8000, 0x0807, METHOD_BUFFERED, FILE_ANY_ACCESS)`)
- **Входной буфер:** `lpInBuffer = ctypes.byref(in_buf)` (4 байта: `c_uint` со значением enum `USBSCAN_PIPE_TYPE`), `nInBufferSize = 4`.
- **Выходной буфер:** `lpOutBuffer = None`, `nOutBufferSize = 0`.
- **Что делает функция:** Запрашивает у драйвера сброс состояния зависания (STALL/HALT) для указанного функционального канала.
- **Возможность физического USB-взаимодействия:**
  - *Инициация транзакции на шине:* **ДА, потенциально возможна**. По спецификации USB хост-драйвер при сбросе pipe отправляет на Endpoint 0 управляющий пакет Control Transfer `CLEAR_FEATURE (ENDPOINT_HALT)`.
  - *Изменение состояния endpoint:* **ДА**. В контроллере камеры конечная точка сбрасывается из состояния HALT в активное состояние, а хост-контроллер сбрасывает бит чередования данных (Data Toggle) в DATA0.
- **Достижимость из кода:** Функция объявлена в `transport.py`, экспортируется в `__init__.py`, но **не вызывается ни в одном публичном рабочем сценарии и ни в одном тесте**.
- **Статус:** **VERIFIED** для механизма вызова; **UNKNOWN** для конкретной реакции микропрограммы Canon EOS R6 Mark II на сброс не зависшей точки.

### 3.3. Вызов №3: `IOCTL_CANCEL_IO`
- **Файл и строки:** [`openeos_ptp/transport.py:553–562`](file:///D:/AI/openeos_ptp/transport.py#L553-L562)
- **Вызывающая функция:** `cancel_usbscan_io(handle: int, pipe_type: USBSCAN_PIPE_TYPE)`
- **Точный числовой код:** `0x80002004` (`CTL_CODE(0x8000, 0x0801, METHOD_BUFFERED, FILE_ANY_ACCESS)`)
- **Входной буфер:** `lpInBuffer = ctypes.byref(in_buf)` (4 байта: `c_uint` со значением enum `USBSCAN_PIPE_TYPE`), `nInBufferSize = 4`.
- **Выходной буфер:** `lpOutBuffer = None`, `nOutBufferSize = 0`.
- **Что делает функция:** Запрашивает отмену ожидающих асинхронных IRP-пакетов в очереди драйвера для указанного канала.
- **Возможность физического USB-взаимодействия:**
  - *Инициация транзакции на шине:* На физическую шину пакеты данных к камере не передаются. Если на шине был активен трансфер, контроллер хоста отменяет соответствующий URB.
  - *Изменение состояния endpoint:* Прямого изменения регистров камеры нет, отменяется транзакция на стороне хоста.
- **Достижимость из кода:** Функция объявлена в `transport.py`, экспортируется в `__init__.py`, но **не вызывается ни в одном рабочем сценарии**.
- **Статус:** **VERIFIED** для механизма вызова.

### 3.4. Вызов №4: `IOCTL_SET_TIMEOUT`
- **Файл и строки:** [`openeos_ptp/transport.py:587–596`](file:///D:/AI/openeos_ptp/transport.py#L587-L596)
- **Вызывающая функция:** `set_usbscan_timeouts(handle: int, ...)`
- **Точный числовой код:** `0x8000202C` (`CTL_CODE(0x8000, 0x080B, METHOD_BUFFERED, FILE_ANY_ACCESS)`)
- **Входной буфер:** `lpInBuffer = ctypes.byref(t)` (`USBSCAN_TIMEOUT`: 12 байт = 3 x `ULONG`: Read, Write, Event в мс), `nInBufferSize = 12`.
- **Выходной буфер:** `lpOutBuffer = None`, `nOutBufferSize = 0`.
- **Что делает функция:** Сохраняет тайм-ауты в контексте драйвера ядра `usbscan.sys`.
- **Возможность физического USB-взаимодействия:**
  - *Инициация транзакции на шине:* **НЕТ**. Вся обработка происходит исключительно внутри драйвера ОС в оперативной памяти ядра.
  - *Изменение состояния endpoint:* **НЕТ**.
- **Достижимость из кода:** Функция объявлена в `transport.py`, экспортируется в `__init__.py`, но **не вызывается ни в одном рабочем сценарии**.
- **Статус:** **VERIFIED**.

### 3.5. Вызов №5: `IOCTL_WAIT_ON_DEVICE_EVENT`
- **Файл и строки:** [`openeos_ptp/transport.py:615–624`](file:///D:/AI/openeos_ptp/transport.py#L615-L624)
- **Вызывающая функция:** `wait_usbscan_device_event(handle: int, buffer_size: int = 64)`
- **Точный числовой код:** `0x80002008` (`CTL_CODE(0x8000, 0x0802, METHOD_BUFFERED, FILE_ANY_ACCESS)`)
- **Входной буфер:** `lpInBuffer = None`, `nInBufferSize = 0` (0 байт).
- **Выходной буфер:** `lpOutBuffer = ctypes.byref(out_buf)` (выделенный строковый буфер `buffer_size` байт), `nOutBufferSize = buffer_size`.
- **Что делает функция:** Ожидает поступления пакета асинхронного события с конечной точки Interrupt IN (Endpoint 0x83).
- **Возможность физического USB-взаимодействия:**
  - *Инициация транзакции на шине:* **ДА**. Драйвер `usbscan.sys` отправляет запрос в стек USB, заставляя хост-контроллер опрашивать Interrupt IN endpoint с интервалом, заданным в дескрипторе endpoint (для Canon EOS R6 Mark II: `bInterval = 10` мс).
  - *Изменение состояния endpoint:* При поступлении события данные считываются из аппаратного FIFO камеры.
- **Достижимость из кода:** Функция объявлена в `transport.py`, экспортируется в `__init__.py`, но **не вызывается ни в одном рабочем сценарии и ни в одном тесте**.
- **Статус:** **VERIFIED** для структуры вызова; **UNKNOWN** для конкретного формата событий камеры Canon при отсутствии физического подключения.

---

## 4. Граф вызовов от публичных точек входа

### 4.1. Сценарий 1: Поиск USB-устройств
- **Публичные точки входа:**
  - `StillImageDeviceFinder.enumerate_cameras()`
  - `StillImageDeviceFinder.find_r6_mark_ii()`
- **Граф вызовов:**
  ```text
  StillImageDeviceFinder.find_r6_mark_ii()
  └── StillImageDeviceFinder.enumerate_cameras()
      ├── SetupDiGetClassDevsW(GUID_DEVINTERFACE_IMAGE, ...)   [Win32 API]
      ├── цикл while True:
      │   ├── SetupDiEnumDeviceInterfaces(...)                 [Win32 API]
      │   ├── SetupDiGetDeviceInterfaceDetailW(..., size=0)    [Win32 API]
      │   ├── SetupDiGetDeviceInterfaceDetailW(..., buf)       [Win32 API]
      │   ├── SetupDiGetDeviceInstanceIdW(...)                 [Win32 API]
      │   └── StillImageDeviceFinder.extract_vid_pid_from_path()
      └── finally:
          └── SetupDiDestroyDeviceInfoList(hdevinfo)           [Win32 API]
  ```
- **Физический I/O:** SetupAPI опрашивает реестр Windows (`SYSTEM\CurrentControlSet\Enum\USB`) и базу данных PnP. Прямых USB-пакетов на шину не посылается.
- **Достижимость:** Вызывается в тестах `test_setupapi_enumeration_*`. В `OpenEOS.py` **не вызывается**.

### 4.2. Сценарий 2: Открытие дескриптора устройства
- **Публичные точки входа:**
  - `CameraAccessManager.execute_with_exclusive_access()`
  - `CameraAccessManager.acquire_device_handle()`
- **Граф вызовов:**
  ```text
  CameraAccessManager.execute_with_exclusive_access(device_path, callback, open_fn)
  ├── with self._lock:
  ├── self.is_edsdk_active()
  │   └── self._edsdk_status()                                [User Callback]
  ├── self._edsdk_close()                                     [User Callback, если EDSDK был активен]
  ├── self.acquire_device_handle(device_path, open_fn)
  │   └── цикл while:
  │       ├── open_handle(device_path)
  │       │   └── CameraAccessManager._default_open_handle(path)
  │       │       └── kernel32.CreateFileW(path, GENERIC_READ | GENERIC_WRITE, 0, ...) [Win32 API]
  │       └── time.sleep(poll_interval_sec)                   [При ошибках занятости]
  ├── callback(safe_handle)                                   [User Callback]
  ├── safe_handle.close()                                     [Автоматически через context manager]
  │   └── kernel32.CloseHandle(handle)                        [Win32 API]
  └── finally:
      └── self._edsdk_restore()                               [User Callback, если EDSDK был активен]
  ```
- **Физический I/O:** Создание дескриптора в ядре Win32.
- **Достижимость:** Вызывается в тестах `test_camera_access_manager_*`. В `OpenEOS.py` **не вызывается**.

### 4.3. Сценарий 3: Получение конфигурации pipe
- **Публичные точки входа:**
  - `PipeConfigurationInspector.query_usbscan_pipe_config(handle)`
  - `PipeConfigurationInspector.validate_pipes(pipes)`
- **Граф вызовов:**
  ```text
  PipeConfigurationInspector.query_usbscan_pipe_config(handle)
  └── kernel32.DeviceIoControl(handle, IOCTL_GET_PIPE_CONFIGURATION, ...) [Win32 API]
  ```
- **Достижимость:** Автономный метод. Не вызывается внутри других методов `transport.py`. В `OpenEOS.py` **не вызывается**. Вызывается только в модульных тестах конфигурации pipe.

### 4.4. Сценарий 4: Чтение Interrupt IN
- **Публичная точка входа:** `wait_usbscan_device_event(handle, buffer_size)`
- **Граф вызовов:**
  ```text
  wait_usbscan_device_event(handle)
  └── kernel32.DeviceIoControl(handle, IOCTL_WAIT_ON_DEVICE_EVENT, ...) [Win32 API]
  ```
- **Достижимость:** **НИГДЕ НЕ ВЫЗЫВАЕТСЯ** (0 вызовов во всём репозитории).

### 4.5. Сценарий 5: Чтение Bulk IN
- **Публичная точка входа:** **ОТСУТСТВУЕТ**.
- **Граф вызовов:** Не существует. Реализация `ReadFile` отсутствует.

### 4.6. Сценарий 6: Отправка Bulk OUT
- **Публичные точки входа:**
  - `ProtectedUsbPtpTransport.write_ptp_container(container)`
  - `ProtectedUsbPtpTransport.write_ptp_bytes(raw_bytes)`
- **Граф вызовов:**
  ```text
  ProtectedUsbPtpTransport.write_ptp_container(container)
  ├── container.serialize()
  ├── self._guard.validate_outgoing_container_bytes(raw_bytes)
  │   ├── parse_ptp_container(raw_bytes)
  │   └── ProtocolGuard.validate_outgoing_container(container)
  │       ├── Проверка запрещённых OpCode (0x905A, 0x905B, 0x905C, 0x9028, 0x9054)
  │       ├── Проверка коллизий TransactionID
  │       ├── Проверка автомата состояний (DISCONNECTED -> WAITING_OPEN_RESP и т.д.)
  │       ├── Проверка имени процедуры ("FA_GetProperty\0")
  │       ├── Проверка допустимых Property ID (0x12000001, 0x12000003, 0x12000005)
  │       └── Проверка нулевого padding
  └── self._write_raw_wire_bytes(raw_bytes)
      └── raise RuntimeError("Phase C not authorized: ... Zero bytes transmitted to USB.")
          └── [ТУПИК / БЛОКИРОВКА — Win32 WriteFile НЕ ВЫЗЫВАЕТСЯ]
  ```
- **Достижимость:** Вызывается в тестах `test_phase_b_protected_transport.py`. До физической шины дойти невозможно в силу безусловного исключения. В `OpenEOS.py` **не вызывается**.

### 4.7. Сценарий 7: Закрытие дескриптора
- **Публичные точки входа:**
  - `SafeDeviceHandle.close()`
  - `SafeDeviceHandle.__exit__()`
- **Граф вызовов:**
  ```text
  SafeDeviceHandle.close()
  ├── if self.is_valid:
  │   └── kernel32.CloseHandle(self._handle)                  [Win32 API]
  └── finally:
      └── self._handle = INVALID_HANDLE_VALUE
  ```
- **Достижимость:** Автоматически вызывается при выходе из контекстного менеджера `with safe_handle:`.

---

## 5. Анализ скрытых и неявных путей вызова

Проведён аудит механизмов неявного исполнения кода:

1. **Время импорта модулей (`import openeos_ptp`):**
   - В модуле `openeos_ptp/transport.py` на строках 932–936 при импорте на платформе Windows вызывается `init_win32_api()`.
   - Метод `init_win32_api()` **только устанавливает типы `argtypes` и `restype`** для библиотек `setupapi` и `kernel32`. Он **не открывает дескрипторы** и **не вызывает `DeviceIoControl` или `ReadFile`**.
2. **Фоновые потоки и таймеры:**
   - Потоки `threading.Thread` в библиотеке `openeos_ptp` отсутствуют.
   - Механизмы фонового опроса (таймеры, polling-демоны) в библиотеке отсутствуют.
   - Объект `threading.Lock` в `CameraAccessManager` используется исключительно для синхронизации вызовов внутри текущего процесса.
3. **Обработчики сигналов и `atexit`:**
   - Модули `signal` и `atexit` не импортируются и не регистрируют хуков.
4. **Связь с GUI (`OpenEOS.py`):**
   - Приложение `OpenEOS.py` (v0.4.2) не содержит импортов `openeos_ptp`, `transport`, `CameraAccessManager` или других компонентов PTP.
   - Графический интерфейс взаимодействует исключительно с `exiftool.exe` через модуль `subprocess`.

**Вывод:** В проекте полностью отсутствуют неявные, автоматические или скрытые пути вызова Win32 API. Любой вызов возможен строго по прямому синхронному вызову из кода.  
**Статус утверждения:** **VERIFIED**.

---

## 6. Аудит использования функций `transport.py` за пределами файла

| Компонент `transport.py` | Включение в `__all__` (`__init__.py`) | Использование в `OpenEOS.py` | Использование в тестах |
|---|---|---|---|
| `CameraAccessManager` | Да (строки 80, 167) | Нет (0) | Да (`test_phase_b_transport_mock.py`) |
| `StillImageDeviceFinder` | Да (строки 81, 168) | Нет (0) | Да (`test_phase_b_transport_mock.py`) |
| `PipeConfigurationInspector`| Да (строки 82, 169) | Нет (0) | Да (`test_phase_b_transport_mock.py`) |
| `PipeInfo` | Да (строки 83, 170) | Нет (0) | Да (`test_phase_b_transport_mock.py`) |
| `DiscoveredCamera` | Да (строки 84, 171) | Нет (0) | Да (`test_phase_b_transport_mock.py`) |
| `SafeDeviceHandle` | Да (строки 85, 172) | Нет (0) | Да (`test_phase_b_transport_mock.py`, `test_phase_b_protected_transport.py`) |
| `TransportError` и подклассы | Да (строки 86–90, 173–177) | Нет (0) | Да (во всех тестах транспорта) |
| `reset_usbscan_pipe` | Да (строки 91, 178) | Нет (0) | **Нет (0 вызовов)** |
| `cancel_usbscan_io` | Да (строки 92, 179) | Нет (0) | **Нет (0 вызовов)** |
| `set_usbscan_timeouts` | Да (строки 93, 180) | Нет (0) | **Нет (0 вызовов)** |
| `wait_usbscan_device_event` | Да (строки 94, 181) | Нет (0) | **Нет (0 вызовов)** |
| `format_pipe_specific_device_path` | Да (строки 95, 182) | Нет (0) | Да (`test_phase_b_transport_mock.py:462`) |
| `is_invalid_handle` | Да (строки 96, 183) | Нет (0) | Да (`test_phase_b_transport_mock.py:190`) |
| `init_win32_api` | Да (строки 97, 184) | Нет (0) | Да (`test_phase_b_transport_mock.py:664`) |
| `ProtectedUsbPtpTransport` | Да (строки 98, 185) | Нет (0) | Да (`test_phase_b_protected_transport.py`) |

**Вывод:** Функции `reset_usbscan_pipe`, `cancel_usbscan_io`, `set_usbscan_timeouts` и `wait_usbscan_device_event` являются неиспользуемыми (dead code) в текущей реализации. Они только объявлены и протестированы на уровне определений констант, но ни в одном тесте и ни в одной цепочке сценариев не вызываются.  
**Статус утверждения:** **VERIFIED**.

---

## 7. Проверка утверждения об обязательности `GENERIC_WRITE` для IOCTL

В отчёте REV 3.6 содержалось утверждение:
> *«Согласно документации Microsoft DDK / Still Image Architecture (`usbscan.sys`), флаг `GENERIC_WRITE` обязателен для создания дескриптора устройства, если через него планируется вызывать управляющие `DeviceIoControl`...»*

### Результаты детальной проверки:
1. **Спецификация макроса `CTL_CODE` в Windows DDK:**
   Формула вычисления кода управляющего вызова:
   $$\text{CTL\_CODE} = (\text{DeviceType} \ll 16) \mid (\text{Access} \ll 14) \mid (\text{Function} \ll 2) \mid \text{Method}$$
   Параметр `Access` определяет права доступа, которые диспетчер ввода-вывода NT (I/O Manager) проверяет у дескриптора файла:
   - `FILE_ANY_ACCESS` ($0$): диспетчер I/O разрешает вызов при **любых** правах дескриптора (включая только `GENERIC_READ` или даже базовый дескриптор без прав на запись данных).
   - `FILE_READ_DATA` ($1$): требуется право `GENERIC_READ`.
   - `FILE_WRITE_DATA` ($2$): требуется право `GENERIC_WRITE`.
2. **Числовые значения используемых IOCTL в `usbscan.h`:**
   В официальном заголовочном файле `usbscan.h` и в `constants.py` все 12 IOCTL драйвера `usbscan.sys` определены с параметром:
   $$\text{Access} = \text{FILE\_ANY\_ACCESS} = 0$$
   Следовательно, на уровне подсистемы безопасности ядра Windows диспетчер I/O **не требует** наличия права `GENERIC_WRITE` для вызова `IOCTL_GET_PIPE_CONFIGURATION`, `IOCTL_SET_TIMEOUT` или `IOCTL_WAIT_ON_DEVICE_EVENT`.
3. **Поведение драйвера `usbscan.sys`:**
   В официальной документации Microsoft WDK отсутствуют прямые нормативные утверждения о том, что диспетчер `IRP_MJ_CREATE` внутри самого драйвера `usbscan.sys` отклоняет открытие дескриптора с правами только `GENERIC_READ`.
   Тем не менее, в ряде устаревших примеров Microsoft Still Image (STI) дескриптор открывался с `GENERIC_READ | GENERIC_WRITE`, поскольку устройство сканера/камеры исторически считалось двунаправленным.
4. **Итоговый вердикт:**
   Поскольку официального подтверждения в документации Microsoft о строгой необходимости `GENERIC_WRITE` для IOCTL с `FILE_ANY_ACCESS` не найдено, а на реальном оборудовании поведение открытия только с `GENERIC_READ` не тестировалось (камера не подключалась):
   **Статус утверждения:** **UNKNOWN**.
   (При открытии дескриптора с `GENERIC_WRITE` ядро формально предоставляет процессу право записи на устройство, хотя отправка данных блокируется в коде).

---

## 8. Сводная таблица достижимости операций

| Операция | Есть реализация | Есть вызов | Достижима из публичного сценария | Возможное USB-взаимодействие |
|---|---|---|---|---|
| **Поиск камер (SetupAPI)** | **Да** (`StillImageDeviceFinder`) | **Да** (в тестах) | **Нет** (в GUI не интегрирован) | Нет (чтение реестра Windows PnP) |
| **Открытие дескриптора (`CreateFileW`)** | **Да** (`_default_open_handle`) | **Да** (в тестах) | **Нет** (в GUI не интегрирован) | Создание дескриптора ядра Win32 (`GENERIC_READ \| GENERIC_WRITE`) |
| **Опрос Pipe (`IOCTL_GET_PIPE_CONFIGURATION`)** | **Да** (`query_usbscan_pipe_config`) | **Да** (в тестах) | **Нет** (в GUI не интегрирован) | Чтение закешированных дескрипторов из памяти драйвера `usbscan.sys` |
| **Сброс Pipe (`IOCTL_RESET_PIPE`)** | **Да** (`reset_usbscan_pipe`) | **Нет** (0 вызовов) | **Нет** | Потенциальный USB Control Transfer `CLEAR_FEATURE(ENDPOINT_HALT)` |
| **Отмена I/O (`IOCTL_CANCEL_IO`)** | **Да** (`cancel_usbscan_io`) | **Нет** (0 вызовов) | **Нет** | Отмена IRP/URB в стеке USB хоста |
| **Установка таймаутов (`IOCTL_SET_TIMEOUT`)** | **Да** (`set_usbscan_timeouts`) | **Нет** (0 вызовов) | **Нет** | Нет (запись во внутреннюю структуру драйвера) |
| **Чтение Interrupt IN (`IOCTL_WAIT_ON_DEVICE_EVENT`)** | **Да** (`wait_usbscan_device_event`) | **Нет** (0 вызовов) | **Нет** | Периодический опрос хостом конечной точки прерываний 0x83 |
| **Чтение Bulk IN (`ReadFile`)** | **Нет** (код вызова отсутствует) | **Нет** (0 вызовов) | **Нет** | Невозможно (нет реализации) |
| **Отправка Bulk OUT (`WriteFile`)** | **Нет** (код вызова отсутствует) | **Нет** (0 вызовов) | **Нет** | **Исключено** (безусловный `RuntimeError` в `_write_raw_wire_bytes`) |
| **Закрытие дескриптора (`CloseHandle`)** | **Да** (`SafeDeviceHandle.close`) | **Да** (в тестах) | **Нет** (в GUI не интегрирован) | Закрытие дескриптора в ядре Win32 |

---

## 9. Подтверждение условий аудита и методологии

1. **Список исследованных файлов:**
   - [`D:\AI\openeos_ptp\transport.py`](file:///D:/AI/openeos_ptp/transport.py)
   - [`D:\AI\openeos_ptp\__init__.py`](file:///D:/AI/openeos_ptp/__init__.py)
   - [`D:\AI\openeos_ptp\mock_transport.py`](file:///D:/AI/openeos_ptp/mock_transport.py)
   - [`D:\AI\openeos_ptp\protocol_guard.py`](file:///D:/AI/openeos_ptp/protocol_guard.py)
   - [`D:\AI\openeos_ptp\payloads.py`](file:///D:/AI/openeos_ptp/payloads.py)
   - [`D:\AI\openeos_ptp\decoders.py`](file:///D:/AI/openeos_ptp/decoders.py)
   - [`D:\AI\openeos_ptp\constants.py`](file:///D:/AI/openeos_ptp/constants.py)
   - [`D:\AI\tests\run_all_tests.py`](file:///D:/AI/tests/run_all_tests.py)
   - [`D:\AI\tests\test_phase_a_decoders.py`](file:///D:/AI/tests/test_phase_a_decoders.py)
   - [`D:\AI\tests\test_phase_a_payloads.py`](file:///D:/AI/tests/test_phase_a_payloads.py)
   - [`D:\AI\tests\test_phase_b_protocol_guard.py`](file:///D:/AI/tests/test_phase_b_protocol_guard.py)
   - [`D:\AI\tests\test_phase_b_transport_mock.py`](file:///D:/AI/tests/test_phase_b_transport_mock.py)
   - [`D:\AI\tests\test_phase_b_protected_transport.py`](file:///D:/AI/tests/test_phase_b_protected_transport.py)
   - [`C:\Users\and!m\OpenEOS\OpenEOS.py`](file:///C:/Users/and!m/OpenEOS/OpenEOS.py)
2. **Использованные методы поиска:**
   - Статический лексический и структурный поиск по AST и тексту файлов проекта.
   - Сверка констант с официальными заголовочными файлами Microsoft Windows SDK/DDK (`usbscan.h`, `winioctl.h`).
3. **Подтверждение целостности кодовой базы:**
   - Ни один файл продакшн-кода (`openeos_ptp/*.py`) **не изменялся**.
   - Ни один тестовый файл (`tests/*.py`) **не изменялся**.
   - Приложение [`OpenEOS.py`](file:///C:/Users/and!m/OpenEOS/OpenEOS.py) **не изменялось**.
4. **Подтверждение аппаратной безопасности:**
   - Физическая камера Canon EOS R6 Mark II **не подключалась**.
   - Физический USB/PTP ввод-вывод **не выполнялся**.
   - Общий объём отправленных/принятых по физической шине байтов строго равен **0 байт**.
