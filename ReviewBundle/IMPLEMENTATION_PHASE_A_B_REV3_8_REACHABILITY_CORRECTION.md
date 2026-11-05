# OpenEOS REV 3.8 — Проверка реальной достижимости Win32 API

**Дата:** 2 ноября 2026 г.  
**Проект:** OpenEOS (Canon EOS R6 Mark II PTP Read-Only Diagnostic Subsystem)  
**Ревизия:** REV 3.8  
**Рабочий каталог:** `D:\AI`  
**Целевая платформа:** Windows 10/11 x64, Python 3.14.10  
**Статус кодовой базы:** Без изменений (100% совпадение с REV 3.4–REV 3.7)  
**Статус физического подключения камеры:** Не подключалась (кабель отключён, 0 байт на USB)  
**Итоговый статус отчёта:** **PARTIALLY VERIFIED** (Статическая изоляция и отсутствие скрытых путей доказаны как `VERIFIED`; аппаратное поведение при реальном исполнении Win32 API без подключения оборудования остаётся непроверенным)

---

## 1. Методологическое разграничение понятий

Для исключения терминологической двусмысленности в настоящем аудите строго разделены три независимых уровня анализа:

1. **Синтаксическое существование вызова API (Syntactic Presence):**
   В тексте исходного кода физически присутствует строка вызова функции `kernel32.<Function>(...)` или `setupapi.<Function>(...)` через библиотеку `ctypes`.
2. **Достижимость по графу функций (Call Graph Reachability):**
   Существует непрерывная цепочка вызовов (call path) от публичных интерфейсов модуля (экспортированных функций или методов классов), способная передать управление строке с синтаксическим вызовом API при вызове из внешнего Python-кода.
3. **Реальное исполнение с настоящим Win32 API (Actual Execution):**
   Вызов функции реально выполнялся во время прогона тестов с обращением к системным библиотекам Windows (а не через mock-объект), либо исполнялся на реальном аппаратном оборудовании.

### Исправление терминологии в выводах аудита:
- **«Не интегрировано в GUI» $\neq$ «Недостижимо»:** Модуль `openeos_ptp` является самостоятельной Python-библиотекой. Тот факт, что графическое приложение `OpenEOS.py` в настоящее время не импортирует `openeos_ptp`, доказывает отсутствие вызовов из интерфейса пользователя, но **не делает код недостижимым** для любого скрипта или консольной команды Python, импортирующей этот модуль.
- **Экспорт функции $\neq$ Фактический вызов:** Включение функции в список `__all__` файла `__init__.py` делает её доступной для импорта, но если внутри кодовой базы проекта отсутствуют обращения к ней, функция представляет собой неактивный (dormant / dead) код.
- **Успешный mock-тест $\neq$ Доказательство физической безопасности или работоспособности:** Прохождение теста с передачей `MockSetupAPI` или поддельного дескриптора доказывает исключительно корректность внутренней логики Python-кода, но не доказывает совместимость с поведением реального драйвера ядра Windows или контроллера USB.

---

## 2. Поэлементный аудит 10 ключевых методов

Ниже приведён исчерпывающий статический анализ каждого из 10 методов подсистемы транспорта с указанием файлов, номеров строк и параметров вызовов.

---

### 2.1. `StillImageDeviceFinder.enumerate_cameras(setupapi_module=None)`
- **Где объявлен:** [`openeos_ptp/transport.py:276–391`](file:///D:/AI/openeos_ptp/transport.py#L276-L391).
- **Синтаксические вызовы Win32 API внутри:**
  - `SetupDiGetClassDevsW` (строка 291)
  - `SetupDiEnumDeviceInterfaces` (строка 309)
  - `SetupDiGetDeviceInterfaceDetailW` (строки 326, 341)
  - `SetupDiGetDeviceInstanceIdW` (строка 359)
  - `SetupDiDestroyDeviceInfoList` (строка 389)
- **Где экспортируется:** Класс `StillImageDeviceFinder` импортируется в [`openeos_ptp/__init__.py:81`](file:///D:/AI/openeos_ptp/__init__.py#L81) и экспортируется в `__all__` (строка 168).
- **Где вызывается в проекте:**
  1. Внутри `transport.py`: на строке 396 внутри метода `find_r6_mark_ii()`:
     ```python
     cameras = cls.enumerate_cameras()
     ```
     *(вызывается с параметром по умолчанию `setupapi_module=None`)*.
  2. В тестах [`tests/test_phase_b_transport_mock.py`](file:///D:/AI/tests/test_phase_b_transport_mock.py):
     - Строка 364: `StillImageDeviceFinder.enumerate_cameras(setupapi_module=MockSetupAPI)` — **вызов с MOCK**.
     - Строка 389: `StillImageDeviceFinder.enumerate_cameras(setupapi_module=MockFailingSetupAPI)` — **вызов с MOCK**.
  3. В `OpenEOS.py`: **0 вызовов**.
- **Реальный Win32 API vs Mock в тестах:** В тестах исполнялся **исключительно с Mock**. Настоящие вызовы SetupAPI в тестовом наборе не выполнялись.
- **Достижимость:** Публичный метод. Достижим для любого внешнего вызова. При вызове без параметров (`setupapi_module=None`) на платформе Windows обращается к реальной системной библиотеке `setupapi.dll`. Физический I/O на шину USB отсутствует (чтение реестра PnP).

---

### 2.2. `CameraAccessManager.execute_with_exclusive_access(device_path, callback, open_fn=None)`
- **Где объявлен:** [`openeos_ptp/transport.py:745–785`](file:///D:/AI/openeos_ptp/transport.py#L745-L785).
- **Синтаксические вызовы Win32 API внутри:** Прямых вызовов нет; делегирует открытие дескриптора методу `acquire_device_handle()`, а закрытие — `SafeDeviceHandle.close()` (через context manager `with safe_handle:`).
- **Где экспортируется:** Класс `CameraAccessManager` импортируется в [`openeos_ptp/__init__.py:80`](file:///D:/AI/openeos_ptp/__init__.py#L80) и экспортируется в `__all__` (строка 167).
- **Где вызывается в проекте:**
  - Внутри библиотеки `openeos_ptp/`: **0 вызовов** (другие методы его не вызывают).
  - В тестах [`tests/test_phase_b_transport_mock.py`](file:///D:/AI/tests/test_phase_b_transport_mock.py):
    - Строка 224: `manager.execute_with_exclusive_access("\\\\?\\USB#TEST", client_callback, open_fn=mock_open)` — **вызов с MOCK** (`mock_open` возвращает дескриптор `9999`).
    - Строки 412, 421, 430, 442: тесты контрактов безопасности EDSDK (вызовы прерываются исключением `DeviceAccessDeniedError` до этапа открытия дескриптора).
  - В `OpenEOS.py`: **0 вызовов**.
- **Реальный Win32 API vs Mock в тестах:** В тестах исполнялся **только с явным mock `open_fn`** или прерывался проверкой контракта.
- **Достижимость и пути по умолчанию:** Публичный метод. Если вызывается внешним кодом с параметром по умолчанию `open_fn=None`, управление передаётся в `acquire_device_handle(open_fn=None)` $\rightarrow$ `_default_open_handle()` $\rightarrow$ **реальный `kernel32.CreateFileW`**.

---

### 2.3. `CameraAccessManager.acquire_device_handle(device_path, open_fn=None)`
- **Где объявлен:** [`openeos_ptp/transport.py:712–744`](file:///D:/AI/openeos_ptp/transport.py#L712-L744).
- **Синтаксические вызовы Win32 API внутри:** Прямых вызовов нет; вызывает `open_handle(device_path)`, где `open_handle = open_fn or self._default_open_handle`.
- **Где экспортируется:** Публичный метод класса `CameraAccessManager`.
- **Где вызывается в проекте:**
  - Внутри `transport.py`: строка 776 (внутри `execute_with_exclusive_access`).
  - В тестах [`tests/test_phase_b_transport_mock.py`](file:///D:/AI/tests/test_phase_b_transport_mock.py):
    - Строка 405: `manager.acquire_device_handle("\\\\?\\USB#NON_EXISTENT", open_fn=mock_open_not_found)` — **вызов с MOCK**.
  - В `OpenEOS.py`: **0 вызовов**.
- **Реальный Win32 API vs Mock в тестах:** В тестах исполнялся **только с Mock**.
- **Достижимость:** Публичный метод. При вызове без передачи `open_fn` переходит на `_default_open_handle`.

---

### 2.4. `CameraAccessManager._default_open_handle(path)`
- **Где объявлен:** [`openeos_ptp/transport.py:787–810`](file:///D:/AI/openeos_ptp/transport.py#L787-L810).
- **Синтаксические вызовы Win32 API внутри:**
  - `kernel32.CreateFileW` (строка 797):
    ```python
    handle = kernel32.CreateFileW(
        ctypes.c_wchar_p(path),
        GENERIC_READ | GENERIC_WRITE,
        0,  # Exclusive access
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )
    ```
- **Где экспортируется:** Приватный статический метод (префикс `_`), непосредственно в `__all__` не экспортируется, но доступен через атрибут класса `CameraAccessManager._default_open_handle`.
- **Где вызывается в проекте:**
  - Внутри `transport.py`: строка 721 как значение по умолчанию при `open_fn is None`:
    ```python
    open_handle = open_fn or self._default_open_handle
    ```
  - В тестах: **0 прямых вызовов**. Во всех юнит-тестах `open_fn` переопределялся фиктивными функциями `mock_open` и `mock_open_not_found`.
  - В `OpenEOS.py`: **0 вызовов**.
- **Реальный Win32 API vs Mock в тестах:** **В тестах не исполнялся ни разу**.
- **Достижимость:** Синтаксически это **единственное место** в проекте, где написан реальный вызов `CreateFileW`. Достижим по цепочке вызовов: `CameraAccessManager.execute_with_exclusive_access(path, cb)` $\rightarrow$ `acquire_device_handle(path)` $\rightarrow$ `_default_open_handle(path)`.

---

### 2.5. `PipeConfigurationInspector.query_usbscan_pipe_config(handle)`
- **Где объявлен:** [`openeos_ptp/transport.py:434–472`](file:///D:/AI/openeos_ptp/transport.py#L434-L472).
- **Синтаксические вызовы Win32 API внутри:**
  - `kernel32.DeviceIoControl` (строки 446–455) с кодом `IOCTL_GET_PIPE_CONFIGURATION` (`0x80002028`).
- **Где экспортируется:** Класс `PipeConfigurationInspector` импортируется в [`openeos_ptp/__init__.py:82`](file:///D:/AI/openeos_ptp/__init__.py#L82) и экспортируется в `__all__` (строка 169).
- **Где вызывается в проекте:**
  - Внутри `transport.py`: **0 вызовов** (другие методы `transport.py` его не вызывают).
  - В тестах (`tests/*.py`): **0 вызовов**.
    *(Область поиска: поиск по строке `query_usbscan_pipe_config` по всей папке `tests/` дал 0 совпадений. Тесты класса проверяют только метод `validate_pipes`, передавая ему сгенерированные вручную объекты `PipeInfo`)*.
  - В `OpenEOS.py`: **0 вызовов**.
- **Реальный Win32 API vs Mock в тестах:** **Не исполнялся вообще** (ни с реальным Win32, ни с mock).
- **Достижимость:** Публичный классовый метод. Достижим для любого внешнего кода при наличии открытого дескриптора. Внутри текущего репозитория является автономным невызываемым кодом.

---

### 2.6. `reset_usbscan_pipe(handle, pipe_type=USBSCAN_PIPE_TYPE.ALL_PIPE)`
- **Где объявлен:** [`openeos_ptp/transport.py:515–540`](file:///D:/AI/openeos_ptp/transport.py#L515-L540).
- **Синтаксические вызовы Win32 API внутри:**
  - `kernel32.DeviceIoControl` (строки 527–536) с кодом `IOCTL_RESET_PIPE` (`0x8000201C`).
- **Где экспортируется:** Импортируется в [`openeos_ptp/__init__.py:91`](file:///D:/AI/openeos_ptp/__init__.py#L91) и экспортируется в `__all__` (строка 178).
- **Где вызывается в проекте:**
  - Внутри `transport.py`: **0 вызовов**.
  - В тестах (`tests/*.py`): **0 вызовов**.
    *(Область поиска: поиск по строке `reset_usbscan_pipe` по всей папке `tests/` дал 0 совпадений)*.
  - В `OpenEOS.py`: **0 вызовов**.
- **Реальный Win32 API vs Mock в тестах:** **Не исполнялся вообще**.
- **Достижимость:** Экспортированная функция верхнего уровня. Достижима для внешнего импорта. В кодовой базе вызовы отсутствуют (dead code).

---

### 2.7. `cancel_usbscan_io(handle, pipe_type=USBSCAN_PIPE_TYPE.ALL_PIPE)`
- **Где объявлен:** [`openeos_ptp/transport.py:542–566`](file:///D:/AI/openeos_ptp/transport.py#L542-L566).
- **Синтаксические вызовы Win32 API внутри:**
  - `kernel32.DeviceIoControl` (строки 553–562) с кодом `IOCTL_CANCEL_IO` (`0x80002004`).
- **Где экспортируется:** Импортируется в [`openeos_ptp/__init__.py:92`](file:///D:/AI/openeos_ptp/__init__.py#L92) и экспортируется в `__all__` (строка 179).
- **Где вызывается в проекте:**
  - Внутри `transport.py`: **0 вызовов**.
  - В тестах (`tests/*.py`): **0 вызовов**.
    *(Область поиска: поиск `cancel_usbscan_io` по `tests/` дал 0 совпадений)*.
  - В `OpenEOS.py`: **0 вызовов**.
- **Реальный Win32 API vs Mock в тестах:** **Не исполнялся вообще**.
- **Достижимость:** Экспортированная функция верхнего уровня. Достижима для внешнего импорта. Внутри проекта не вызывается (dead code).

---

### 2.8. `set_usbscan_timeouts(handle, timeout_read_ms=5000, ...)`
- **Где объявлен:** [`openeos_ptp/transport.py:568–600`](file:///D:/AI/openeos_ptp/transport.py#L568-L600).
- **Синтаксические вызовы Win32 API внутри:**
  - `kernel32.DeviceIoControl` (строки 587–596) с кодом `IOCTL_SET_TIMEOUT` (`0x8000202C`).
- **Где экспортируется:** Импортируется в [`openeos_ptp/__init__.py:93`](file:///D:/AI/openeos_ptp/__init__.py#L93) и экспортируется в `__all__` (строка 180).
- **Где вызывается в проекте:**
  - Внутри `transport.py`: **0 вызовов**.
  - В тестах (`tests/*.py`): **0 вызовов**.
    *(Область поиска: поиск `set_usbscan_timeouts` по `tests/` дал 0 совпадений)*.
  - В `OpenEOS.py`: **0 вызовов**.
- **Реальный Win32 API vs Mock в тестах:** **Не исполнялся вообще**.
- **Достижимость:** Экспортированная функция. Достижима для внешнего кода. В коде проекта не вызывается (dead code).

---

### 2.9. `wait_usbscan_device_event(handle, buffer_size=64)`
- **Где объявлен:** [`openeos_ptp/transport.py:602–629`](file:///D:/AI/openeos_ptp/transport.py#L602-L629).
- **Синтаксические вызовы Win32 API внутри:**
  - `kernel32.DeviceIoControl` (строки 615–624) с кодом `IOCTL_WAIT_ON_DEVICE_EVENT` (`0x80002008`).
- **Где экспортируется:** Импортируется в [`openeos_ptp/__init__.py:94`](file:///D:/AI/openeos_ptp/__init__.py#L94) и экспортируется в `__all__` (строка 181).
- **Где вызывается в проекте:**
  - Внутри `transport.py`: **0 вызовов**.
  - В тестах (`tests/*.py`): **0 вызовов**.
    *(Область поиска: поиск `wait_usbscan_device_event` по `tests/` дал 0 совпадений)*.
  - В `OpenEOS.py`: **0 вызовов**.
- **Реальный Win32 API vs Mock в тестах:** **Не исполнялся вообще**.
- **Достижимость:** Экспортированная функция. Достижима для внешнего вызова при наличии дескриптора. В текущем коде не вызывается (dead code).

---

### 2.10. `SafeDeviceHandle.close()`
- **Где объявлен:** [`openeos_ptp/transport.py:234–243`](file:///D:/AI/openeos_ptp/transport.py#L234-L243).
- **Синтаксические вызовы Win32 API внутри:**
  - `kernel32.CloseHandle` (строка 238):
    ```python
    kernel32 = ctypes.windll.kernel32
    kernel32.CloseHandle(ctypes.c_void_p(self._handle))
    ```
- **Где экспортируется:** Класс `SafeDeviceHandle` импортируется в [`openeos_ptp/__init__.py:85`](file:///D:/AI/openeos_ptp/__init__.py#L85) и экспортируется в `__all__` (строка 172).
- **Где вызывается в проекте:**
  - Внутри `transport.py`:
    1. Строка 248: внутри `__exit__` класса `SafeDeviceHandle` (`self.close()`).
    2. Строка 777: внутри `execute_with_exclusive_access` через блок `with safe_handle:`.
  - В тестах [`tests/test_phase_b_transport_mock.py`](file:///D:/AI/tests/test_phase_b_transport_mock.py):
    1. Строки 172–187 (`test_safe_device_handle_lifecycle`): метод `close()` переопределён в подклассе `MockSafeHandle` для перехвата вызовов без вызова Win32 API (**MOCK**).
    2. Строка 224 (`test_camera_access_manager_edsdk_handover`): `execute_with_exclusive_access` использует реальный класс `SafeDeviceHandle(9999)` внутри блока `with safe_handle:`.
       При выходе из блока вызывается `safe_handle.close()`, который на строке 238 исполняет **реальный системный вызов `kernel32.CloseHandle(9999)`**!
       *(Системный вызов Windows завершается с кодом ошибки `ERROR_INVALID_HANDLE`, перехватывается блоком `except Exception: pass`, дескриптор сбрасывается в `INVALID_HANDLE_VALUE`)*.
  - В `OpenEOS.py`: **0 вызовов**.
- **Реальный Win32 API vs Mock в тестах:** В тесте строки 224 выполнялся **реальный вызов Win32 `CloseHandle`**, но к фиктивному дескриптору `9999` (не к аппаратному устройству).
- **Достижимость:** Автоматически вызывается при любом нормальном или аварийном завершении работы с `SafeDeviceHandle`.

---

## 3. Особые механизмы: `open_fn`, `callback` и пути к `_default_open_handle`

### 3.1. Параметр `open_fn` и значение по умолчанию
В методе `acquire_device_handle` (строка 721):
```python
open_handle = open_fn or self._default_open_handle
```
- Если вызывающий код передаёт собственный `open_fn` (как это делают юнит-тесты), системный вызов `CreateFileW` подменяется функцией пользователя.
- Если вызывающий код опускает параметр `open_fn` (значение по умолчанию `None`), **безусловно вызывается метод `_default_open_handle`**, исполняющий Win32 `CreateFileW`.

### 3.2. Роль `callback` в `execute_with_exclusive_access`
Метод `execute_with_exclusive_access(device_path, callback, open_fn=None)` принимает пользовательский `callback`, получающий валидный экземпляр `SafeDeviceHandle`.
- Внутри блока `with safe_handle:` управление полностью передаётся этому колбэку.
- Если колбэк попытается вызвать любой из методов `query_usbscan_pipe_config`, `set_usbscan_timeouts`, `wait_usbscan_device_event` или `reset_usbscan_pipe`, передав `safe_handle.handle`, соответствующий `DeviceIoControl` будет реально выполнен.
- Однако сам по себе `execute_with_exclusive_access` внутри себя **не вызывает ни один `DeviceIoControl`**.

---

## 4. Влияние импорта модулей и создания экземпляров классов

Проведена проверка сценария импорта библиотеки и инициализации объектов без явного вызова рабочих методов:

1. **При вызове `import openeos_ptp` или `import openeos_ptp.transport`:**
   - Единственный выполняемый код верхнего уровня — строки 932–936 в `transport.py`:
     ```python
     if sys.platform == "win32":
         try:
             init_win32_api()
         except Exception:
             pass
     ```
   - Метод `init_win32_api()` **только инициализирует атрибуты `argtypes` и `restype`** у объектов `ctypes.windll.kernel32` и `ctypes.windll.setupapi`.
   - **Физический I/O не выполняется, дескрипторы не открываются, системные вызовы ввода-вывода не производятся.**
2. **При инстанцировании объектов классов:**
   - `CameraAccessManager(...)`: инициализирует числа таймаутов, ссылки на колбэки и `threading.Lock()`. Дескрипторы не создаются, фоновые потоки не запускаются.
   - `SafeDeviceHandle(handle)`: сохраняет целочисленный дескриптор в поле `_handle`.
   - `ProtectedUsbPtpTransport(handle, guard)`: валидирует типы аргументов и сохраняет ссылки в защищённые поля.
   - `ProtocolGuard()`: инициализирует внутренний автомат состояний в значение `DISCONNECTED`.
   - `PipeConfigurationInspector` и `StillImageDeviceFinder`: содержат только статические и классовые методы, состояния экземпляра не имеют.

**Вывод:** Импорт модулей `openeos_ptp` и создание объектов его классов являются на 100% пассивными операциями, не производящими аппаратного взаимодействия с шиной USB.  
**Статус утверждения:** **VERIFIED**.

---

## 5. Итоговая сводная таблица достижимости Win32 API

| Метод / API | Объявлен (файл, строки) | Экспортирован в `__init__` | Есть вызов в коде проекта | Реальный Win32 или Mock в тестах | Достижим из GUI (`OpenEOS.py`) | Физический I/O доказан |
|---|---|---|---|---|---|---|
| **`StillImageDeviceFinder.enumerate_cameras`** | [`transport.py:276–391`](file:///D:/AI/openeos_ptp/transport.py#L276-L391) | **Да** (`__all__:168`) | Да (`find_r6_mark_ii:396`, тесты) | **Mock** в тестах (`MockSetupAPI`) | **Нет** (GUI не импортирует) | **Нет** (в тестах только mock; на шине не тестировался) |
| **`CameraAccessManager.execute_with_exclusive_access`** | [`transport.py:745–785`](file:///D:/AI/openeos_ptp/transport.py#L745-L785) | **Да** (`__all__:167`) | Да (только в тестах) | **Mock** в тестах (`mock_open`) | **Нет** (GUI не импортирует) | **Нет** |
| **`CameraAccessManager.acquire_device_handle`** | [`transport.py:712–744`](file:///D:/AI/openeos_ptp/transport.py#L712-L744) | **Да** (метод класса) | Да (`execute...:776`, тесты) | **Mock** в тестах (`mock_open_not_found`) | **Нет** (GUI не импортирует) | **Нет** |
| **`CameraAccessManager._default_open_handle`** | [`transport.py:787–810`](file:///D:/AI/openeos_ptp/transport.py#L787-L810) | **Нет** (приватный статический) | Да (`acquire...:721` default) | **Не вызывался в тестах** (подменялся mock) | **Нет** (GUI не импортирует) | **Нет** (вызов `CreateFileW` реален в коде, но на оборудовании не запускался) |
| **`PipeConfigurationInspector.query_usbscan_pipe_config`** | [`transport.py:434–472`](file:///D:/AI/openeos_ptp/transport.py#L434-L472) | **Да** (`__all__:169`) | **Нет (0 вызовов)** | **Не вызывался вообще** | **Нет** (GUI не импортирует) | **Нет** |
| **`reset_usbscan_pipe`** | [`transport.py:515–540`](file:///D:/AI/openeos_ptp/transport.py#L515-L540) | **Да** (`__all__:178`) | **Нет (0 вызовов)** | **Не вызывался вообще** | **Нет** (GUI не импортирует) | **Нет** |
| **`cancel_usbscan_io`** | [`transport.py:542–566`](file:///D:/AI/openeos_ptp/transport.py#L542-L566) | **Да** (`__all__:179`) | **Нет (0 вызовов)** | **Не вызывался вообще** | **Нет** (GUI не импортирует) | **Нет** |
| **`set_usbscan_timeouts`** | [`transport.py:568–600`](file:///D:/AI/openeos_ptp/transport.py#L568-L600) | **Да** (`__all__:180`) | **Нет (0 вызовов)** | **Не вызывался вообще** | **Нет** (GUI не импортирует) | **Нет** |
| **`wait_usbscan_device_event`** | [`transport.py:602–629`](file:///D:/AI/openeos_ptp/transport.py#L602-L629) | **Да** (`__all__:181`) | **Нет (0 вызовов)** | **Не вызывался вообще** | **Нет** (GUI не импортирует) | **Нет** |
| **`SafeDeviceHandle.close`** | [`transport.py:234–243`](file:///D:/AI/openeos_ptp/transport.py#L234-L243) | **Да** (`__all__:172`) | Да (`__exit__:248`, тесты) | **Реальный Win32 API** в тесте (на mock-дескрипторе `9999`) | **Нет** (GUI не импортирует) | **Нет** (дескриптор реального устройства не закрывался) |
| **`ProtectedUsbPtpTransport._write_raw_wire_bytes`** | [`transport.py:1005–1017`](file:///D:/AI/openeos_ptp/transport.py#L1005-L1017) | **Нет** (приватный метод) | Да (`write_ptp_*:988, 1003`) | **RuntimeError** (блокировка, нет вызова WriteFile) | **Нет** | **Исключён / Заблокирован** |
| **`kernel32.ReadFile`** | [`transport.py:910–919`](file:///D:/AI/openeos_ptp/transport.py#L910-L919) (сигнатура) | **Нет** | **Нет (0 вызовов)** | **Не вызывался вообще** (только проверка сигнатуры) | **Нет** | **Не существует в коде** |
| **`kernel32.WriteFile`** | [`transport.py:920–929`](file:///D:/AI/openeos_ptp/transport.py#L920-L929) (сигнатура) | **Нет** | **Нет (0 вызовов)** | **Не вызывался вообще** (mock-assertion `assert_not_called`) | **Нет** | **Не существует в коде** |

---

## 6. Подтверждение целостности и условий проверки

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
2. **Поисковые запросы для верификации отсутствия вызовов:**
   - Поиск `query_usbscan_pipe_config` по всей папке `tests/` $\rightarrow$ 0 совпадений.
   - Поиск `reset_usbscan_pipe` по всей папке `tests/` $\rightarrow$ 0 совпадений.
   - Поиск `cancel_usbscan_io` по всей папке `tests/` $\rightarrow$ 0 совпадений.
   - Поиск `set_usbscan_timeouts` по всей папке `tests/` $\rightarrow$ 0 совпадений.
   - Поиск `wait_usbscan_device_event` по всей папке `tests/` $\rightarrow$ 0 совпадений.
   - Поиск `_default_open_handle` по всей папке `tests/` $\rightarrow$ 0 совпадений.
   - Поиск `openeos_ptp` в файле [`OpenEOS.py`](file:///C:/Users/and!m/OpenEOS/OpenEOS.py) $\rightarrow$ 0 совпадений.
3. **Неизменность кода:** Ни один файл исходного кода и тестов не изменялся.
4. **Аппаратная безопасность:** Физическая камера Canon EOS R6 Mark II не подключалась, кабель отключён, системные вызовы ввода-вывода к оборудованию не производились, объём физического трафика строго равен **0 байт**.
