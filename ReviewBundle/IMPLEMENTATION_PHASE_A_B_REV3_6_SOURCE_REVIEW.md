# OpenEOS REV 3.6 — Доказательная база исходного кода для независимого технического ревью

**Дата:** 2 ноября 2026 г.  
**Проект:** OpenEOS (Canon EOS R6 Mark II PTP Read-Only Diagnostic Subsystem)  
**Ревизия:** REV 3.6  
**Рабочий каталог:** `D:\AI`  
**Целевая платформа:** Windows 10/11 x64, Python 3.14.10  
**Статус исходного кода:** Не изменялся (100% совпадение с REV 3.4 / REV 3.5)  
**Статус физического подключения камеры:** Не подключалась (кабель отключён, 0 байт на USB)  
**Итоговый статус доказательной базы:** **PARTIALLY VERIFIED** (Программная блокировка в коде — `VERIFIED`, поведение ядра Win32/драйвера на реальном оборудовании без подключения камеры — `PARTIALLY VERIFIED`)

---

## Введение

Настоящий документ подготовлен в качестве доказательной базы для независимого технического аудита подсистемы USB/PTP в проекте OpenEOS. Документ содержит буквальные фрагменты локальных исходных файлов с точными номерами строк, исчерпывающий анализ всех точек входа и вызова Win32 API, протокольного брандмауэра и драйверных IOCTL.

Никаких изменений в продакшн-код, тесты или приложение `OpenEOS.py` в рамках данной ревизии не вносилось.

---

## 1. Конструктор `ProtectedUsbPtpTransport.__init__()`

- **Файл:** [`openeos_ptp/transport.py`](file:///D:/AI/openeos_ptp/transport.py)
- **Диапазон строк:** 955–963

```python
    def __init__(self, handle: SafeDeviceHandle, guard: ProtocolGuard):
        if guard is None or not isinstance(guard, ProtocolGuard):
            raise SecurityViolationError("Mandatory Protocol Guard instance is required. Bypass strictly prohibited.")
        if handle is None or not handle.is_valid:
            raise TransportError("Cannot initialize ProtectedUsbPtpTransport with an invalid or closed handle.")

        self._handle = handle
        self._guard = guard
```

### Анализ:
1. Инстанцирование транспорта без экземпляра `ProtocolGuard` невозможно: при передаче `guard=None` или объекта другого типа немедленно возбуждается `SecurityViolationError` (строки 956–957).
2. Транспорт невозможно инициализировать с закрытым или невалидным дескриптором `SafeDeviceHandle` (строки 958–959).
3. Поля `_handle` и `_guard` инкапсулированы как защищённые атрибуты с доступом только на чтение через свойства `@property` (строки 964–970).

---

## 2. Методы отправки: `write_ptp_container()`, `write_ptp_bytes()` и `_write_raw_wire_bytes()`

- **Файл:** [`openeos_ptp/transport.py`](file:///D:/AI/openeos_ptp/transport.py)
- **Диапазон строк:** 972–1017

```python
    def write_ptp_container(self, container: PtpContainer) -> int:
        """
        Submits an outbound PTP container to the transport channel.
        MANDATORY FLOW: PTP Container -> Serialization -> Protocol Guard -> USB WriteFile.
        Zero bypass guarantee: Protocol Guard inspects wire bytes before transmission.
        """
        if not isinstance(container, PtpContainer):
            raise SecurityViolationError(f"Expected PtpContainer instance, got {type(container).__name__}")

        # Step 1: Serialization
        raw_bytes = container.serialize()

        # Step 2: Protocol Guard validation directly on the wire bytes immediately prior to send
        self._guard.validate_outgoing_container_bytes(raw_bytes)

        # Step 3: Low-level wire transmission sink (unconditionally blocked in Phase B)
        return self._write_raw_wire_bytes(raw_bytes)

    def write_ptp_bytes(self, raw_bytes: bytes) -> int:
        """
        Submits pre-serialized PTP container bytes to the transport channel.
        MANDATORY FLOW: Serialization (pre-done) -> Protocol Guard -> USB WriteFile.
        Zero bypass guarantee: Protocol Guard inspects wire bytes before transmission.
        """
        if not isinstance(raw_bytes, (bytes, bytearray)):
            raise SecurityViolationError(f"Expected bytes or bytearray, got {type(raw_bytes).__name__}")

        # Step 1: Protocol Guard validation directly on wire bytes
        self._guard.validate_outgoing_container_bytes(bytes(raw_bytes))

        # Step 2: Low-level wire transmission sink (unconditionally blocked in Phase B)
        return self._write_raw_wire_bytes(bytes(raw_bytes))

    def _write_raw_wire_bytes(self, data: bytes) -> int:
        """
        Low-level wire transmission sink.
        UNCONDITIONALLY BLOCKED IN PHASE B.

        Zero bytes are transmitted to USB. There is no toggle or configuration
        that can authorize physical transmission in this phase.
        Physical dispatch is strictly deferred until Phase C is explicitly authorized.
        """
        raise RuntimeError(
            "Phase C not authorized: physical PTP dispatch to Canon EOS R6 Mark II is strictly disabled. "
            "Zero bytes transmitted to USB."
        )
```

### Анализ:
1. Оба публичных метода отправки ([`write_ptp_container`](file:///D:/AI/openeos_ptp/transport.py#L972) и [`write_ptp_bytes`](file:///D:/AI/openeos_ptp/transport.py#L990)) принудительно вызывают `self._guard.validate_outgoing_container_bytes()` перед передачей управления в метод стока.
2. Метод стока `_write_raw_wire_bytes()` (строки 1005–1017) является единственной точкой, где потенциально мог бы вызываться системный вызов отправки. В текущей кодовой базе данный метод **безусловно** выбрасывает `RuntimeError` (строки 1014–1017).
3. Метод `_write_raw_wire_bytes()` не содержит операторов ветвления (`if`), не проверяет флаги, переменные окружения или атрибуты экземпляра.

---

## 3. `ProtocolGuard.validate_outgoing_container_bytes()` и основные проверки состояния протокола

- **Файл:** [`openeos_ptp/protocol_guard.py`](file:///D:/AI/openeos_ptp/protocol_guard.py)
- **Диапазон строк:** 125–250

```python
    def validate_outgoing_container_bytes(self, raw_bytes: bytes) -> PtpContainer:
        """
        Validates raw outgoing wire bytes immediately prior to USB WriteFile.
        Checks length, container type, OpCode, TransactionID, and payload contents.
        """
        try:
            container = parse_ptp_container(raw_bytes)
        except PayloadFormatError as exc:
            raise SecurityViolationError(f"Protocol Guard rejected malformed PTP container: {exc}") from exc

        self.validate_outgoing_container(container)
        return container

    def validate_outgoing_container(self, container: PtpContainer) -> None:
        """
        Validates a PtpContainer object against active state, allowed OpCodes, and arguments.
        """
        opcode = container.opcode_or_response
        tx_id = container.tx_id

        # 1. Prohibited OpCodes check
        if opcode in (
            PTP_OC_Canon_SaveTransparentMemory,
            PTP_OC_Canon_QuickLoadTransparentMemory,
            PTP_OC_Canon_Auth,
            PTP_OC_Canon_DirectPTP,
            PTP_OC_Canon_EventProc,
        ):
            raise SecurityViolationError(
                f"Prohibited OpCode 0x{opcode:04X} intercepted by Protocol Guard! "
                f"All code uploads, execution triggers, and auth handshakes are strictly barred."
            )

        # 2. Transaction ID Collision / Replay Protection
        if container.is_command:
            if tx_id in self._used_tx_ids:
                raise SecurityViolationError(
                    f"Duplicate TransactionID {tx_id} rejected! "
                    f"Transaction IDs must not be reused within an open session."
                )
            if (self._active_tx_id is not None and tx_id == self._active_tx_id) or \
               (self._active_fetch_tx_id is not None and tx_id == self._active_fetch_tx_id):
                raise SecurityViolationError(
                    f"TransactionID {tx_id} is currently active and cannot be reused concurrently."
                )

        # 3. State Machine & Phase Transitions
        # Case A: OpenSession (Command)
        if opcode == PTP_OC_OpenSession:
            if not container.is_command:
                raise SecurityViolationError("OpenSession must be a Command Container (Type 1).")
            if self._state != ProtocolGuardState.DISCONNECTED:
                raise ProtocolSequenceError(f"Cannot issue OpenSession in state {self._state.value}.")
            if container.length != 16 or len(container.payload_or_params) != 4:
                raise SecurityViolationError(
                    f"OpenSession container length error: expected 16 bytes, got {container.length}."
                )
            params = container.get_params()
            if len(params) != 1:
                raise SecurityViolationError(f"OpenSession requires 1 parameter (SessionID), got {len(params)}.")

            self._active_tx_id = tx_id
            self._state = ProtocolGuardState.WAITING_OPEN_RESPONSE
            return

        # Case B: CloseSession (Command)
        if opcode == PTP_OC_CloseSession:
            if not container.is_command:
                raise SecurityViolationError("CloseSession must be a Command Container (Type 1).")
            if self._state == ProtocolGuardState.DISCONNECTED:
                raise ProtocolSequenceError("Cannot issue CloseSession when DISCONNECTED.")
            if self._state == ProtocolGuardState.WAITING_CLOSE_RESPONSE:
                raise ProtocolSequenceError("CloseSession already dispatched, waiting for response.")
            if self._state != ProtocolGuardState.SESSION_OPEN:
                raise ProtocolSequenceError(
                    f"Cannot issue CloseSession during active/incomplete transaction in state {self._state.value}. "
                    f"All read transactions must complete or fail cleanly first."
                )
            if container.length != 12 or len(container.payload_or_params) != 0:
                raise SecurityViolationError(
                    f"CloseSession container length error: expected 12 bytes, got {container.length}."
                )

            self._active_tx_id = tx_id
            self._state = ProtocolGuardState.WAITING_CLOSE_RESPONSE
            return

        # Case C: 0x9052 FA_Command - Command Phase
        if opcode == PTP_OC_Canon_FA_Command and container.is_command:
            if self._state != ProtocolGuardState.SESSION_OPEN:
                raise ProtocolSequenceError(
                    f"Cannot dispatch 0x9052 Command in state {self._state.value}. "
                    f"Must be in SESSION_OPEN (previous transaction must be fully closed)."
                )
            if container.length != FA_COMMAND_CONTAINER_LEN or len(container.payload_or_params) != 8:
                raise SecurityViolationError(
                    f"0x9052 Command container length error: expected {FA_COMMAND_CONTAINER_LEN} bytes, got {container.length}."
                )
            params = container.get_params()
            if params != [0, 1]:
                raise SecurityViolationError(
                    f"0x9052 Command parameter mismatch: expected [0, 1], got {params}."
                )

            self._active_tx_id = tx_id
            self._state = ProtocolGuardState.WAITING_DATA_OUT
            return

        # Case D: 0x9052 FA_Command - Data OUT Phase
        if opcode == PTP_OC_Canon_FA_Command and container.is_data:
            if self._state != ProtocolGuardState.WAITING_DATA_OUT:
                raise ProtocolSequenceError(
                    f"Unexpected Data OUT container in state {self._state.value}. "
                    f"Data OUT must immediately follow a 0x9052 Command."
                )
            if container.length != FA_GET_PROPERTY_CONTAINER_LEN or len(container.payload_or_params) != 43:
                raise SecurityViolationError(
                    f"0x9052 Data OUT container length error: expected {FA_GET_PROPERTY_CONTAINER_LEN} bytes, got {container.length}."
                )
            # TransactionID MUST match the preceding Command
            if tx_id != self._active_tx_id:
                raise SecurityViolationError(
                    f"TransactionID mismatch between Command ({self._active_tx_id}) "
                    f"and Data OUT ({tx_id})! Possible transaction hijacking attempt."
                )
```

- **Диапазон строк (проверка полезной нагрузки, имени процедуры и PropertyID):** 251–315

```python
            # Strict Payload Verification
            payload = container.payload_or_params
            if len(payload) < 15:
                raise SecurityViolationError("Data OUT payload too short to contain FA procedure name.")

            # Check procedure name field specifically (first 15 bytes) rather than searching arbitrary binary arguments
            proc_name_raw = payload[0:15].split(b"\x00")[0].lower()
            for pattern in PROHIBITED_PROCEDURE_PATTERNS:
                if pattern in proc_name_raw:
                    raise SecurityViolationError(
                        f"Prohibited procedure name {pattern!r} detected in procedure field: {proc_name_raw!r}. "
                        f"Arbitrary EventProc, write routines, and test functions are strictly barred."
                    )

            try:
                validate_fa_get_property_payload(payload)
            except PayloadFormatError as exc:
                raise SecurityViolationError(f"Protocol Guard rejected FA payload: {exc}") from exc

            prop_key = struct.unpack("<I", payload[23:27])[0]
            if prop_key not in ALLOWED_PROPERTY_IDS:
                raise SecurityViolationError(
                    f"Unauthorized Property ID 0x{prop_key:08X} in FA_GetProperty."
                )

            self._active_property_id = prop_key
            self._state = ProtocolGuardState.WAITING_COMMAND_RESPONSE
            return

        # Case E: 0x9053 FA_Fetch - Command Phase
        if opcode == PTP_OC_Canon_FA_Fetch and container.is_command:
            if self._state != ProtocolGuardState.WAITING_FETCH_COMMAND:
                raise ProtocolSequenceError(
                    f"Unexpected 0x9053 Fetch Command in state {self._state.value}. "
                    f"Fetch is ONLY permitted after a successful FA_GetProperty Response."
                )
            if self._last_command_tx_id is not None and tx_id == self._last_command_tx_id:
                raise SecurityViolationError(
                    f"0x9053 Fetch Command cannot reuse the TransactionID ({tx_id}) of preceding 0x9052 command."
                )

            expected_prop = self._active_property_id
            expected_params = FETCH_PARAMS_MAP.get(expected_prop, [])
            expected_len = 12 + len(expected_params) * 4
            if container.length != expected_len or len(container.payload_or_params) != len(expected_params) * 4:
                raise SecurityViolationError(
                    f"0x9053 Fetch container length error: expected {expected_len} bytes, got {container.length}."
                )

            params = container.get_params()
            if params != expected_params:
                raise SecurityViolationError(
                    f"Parameter mismatch for 0x9053 Fetch of Property 0x{expected_prop:08X}: "
                    f"expected {expected_params}, received {params}."
                )

            self._active_fetch_tx_id = tx_id
            self._state = ProtocolGuardState.WAITING_FETCH_DATA_IN
            return

        # Any other outbound container
        raise SecurityViolationError(
            f"Container (Type={container.container_type}, OpCode=0x{opcode:04X}) "
            f"is rejected by OpenEOS Protocol Guard in state {self._state.value}."
        )
```

---

## 4. `init_win32_api()` — объявления API и сигнатуры

- **Файл:** [`openeos_ptp/transport.py`](file:///D:/AI/openeos_ptp/transport.py)
- **Диапазон строк:** 812–936

```python
def init_win32_api(setupapi=None, kernel32=None) -> None:
    """
    Configures explicit argtypes and restype on Windows x64 / x86 for all Win32 APIs
    used across the transport module. Eliminates 64-bit handle truncation, structure pointer
    mismatch, and signedness errors.
    
    Verified APIs:
      1. SetupDiGetClassDevsW
      2. SetupDiEnumDeviceInterfaces
      3. SetupDiGetDeviceInterfaceDetailW
      4. SetupDiDestroyDeviceInfoList
      5. CreateFileW
      6. DeviceIoControl
      7. ReadFile
      8. WriteFile
      9. CloseHandle
    """
    if sys.platform != "win32" and setupapi is None and kernel32 is None:
        return

    s_api = setupapi or (ctypes.windll.setupapi if hasattr(ctypes, "windll") else None)
    k_api = kernel32 or (ctypes.windll.kernel32 if hasattr(ctypes, "windll") else None)

    if s_api is not None:
        if hasattr(s_api, "SetupDiGetClassDevsW"):
            s_api.SetupDiGetClassDevsW.argtypes = [
                ctypes.POINTER(GUID),
                ctypes.c_wchar_p,
                wintypes.HWND,
                wintypes.DWORD,
            ]
            s_api.SetupDiGetClassDevsW.restype = wintypes.HANDLE

        if hasattr(s_api, "SetupDiEnumDeviceInterfaces"):
            s_api.SetupDiEnumDeviceInterfaces.argtypes = [
                wintypes.HANDLE,
                ctypes.c_void_p,
                ctypes.POINTER(GUID),
                wintypes.DWORD,
                ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
            ]
            s_api.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL

        if hasattr(s_api, "SetupDiGetDeviceInterfaceDetailW"):
            s_api.SetupDiGetDeviceInterfaceDetailW.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
                ctypes.POINTER(SP_DEVINFO_DATA),
            ]
            s_api.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL

        if hasattr(s_api, "SetupDiDestroyDeviceInfoList"):
            s_api.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
            s_api.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

        if hasattr(s_api, "SetupDiGetDeviceInstanceIdW"):
            s_api.SetupDiGetDeviceInstanceIdW.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(SP_DEVINFO_DATA),
                ctypes.c_wchar_p,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
            ]
            s_api.SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL

    if k_api is not None:
        if hasattr(k_api, "CreateFileW"):
            k_api.CreateFileW.argtypes = [
                ctypes.c_wchar_p,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.c_void_p,
            ]
            k_api.CreateFileW.restype = wintypes.HANDLE

        if hasattr(k_api, "CloseHandle"):
            k_api.CloseHandle.argtypes = [wintypes.HANDLE]
            k_api.CloseHandle.restype = wintypes.BOOL

        if hasattr(k_api, "DeviceIoControl"):
            k_api.DeviceIoControl.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
                ctypes.c_void_p,
            ]
            k_api.DeviceIoControl.restype = wintypes.BOOL

        if hasattr(k_api, "ReadFile"):
            k_api.ReadFile.argtypes = [
                wintypes.HANDLE,
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
                ctypes.c_void_p,
            ]
            k_api.ReadFile.restype = wintypes.BOOL

        if hasattr(k_api, "WriteFile"):
            k_api.WriteFile.argtypes = [
                wintypes.HANDLE,
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
                ctypes.c_void_p,
            ]
            k_api.WriteFile.restype = wintypes.BOOL
```

---

## 5. Все места вызова `WriteFile` и `DeviceIoControl`

### 5.1. Анализ вызовов `WriteFile`
- **В продакшн-коде (`openeos_ptp/` и `OpenEOS.py`):** **0 вызовов.**
  Ни в одном продакшн-модуле вызов `kernel32.WriteFile(...)` не выполняется.
- **В тестах (`tests/test_phase_b_protected_transport.py`):**
  - Строки 393–400 и 406–410 (в `test_10`):
    ```python
    if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "kernel32"):
        with patch.object(ctypes.windll.kernel32, "WriteFile", MagicMock()) as mock_win32_write:
            with self.assertRaises(RuntimeError) as cm:
                self.transport.write_ptp_container(open_c)
            self.assertIn("Phase C not authorized", str(cm.exception))
            self.assertIn("Zero bytes transmitted to USB", str(cm.exception))
            mock_win32_write.assert_not_called()

            self.guard.reset()
            self.transport.PHYSICAL_IO_ENABLED = True  # Attempt to bypass
            with self.assertRaises(RuntimeError) as cm_bypass:
                self.transport.write_ptp_container(open_c)
            self.assertIn("Phase C not authorized", str(cm_bypass.exception))
            self.assertIn("Zero bytes transmitted to USB", str(cm_bypass.exception))
            mock_win32_write.assert_not_called()
    ```
  - Строки 434–441 (в `test_11`):
    ```python
    if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "kernel32"):
        with patch.object(ctypes.windll.kernel32, "WriteFile", MagicMock()) as mock_win32_write:
            with self.assertRaises(RuntimeError) as cm:
                self.transport.write_ptp_bytes(valid_wire)
            self.assertIn("Phase C not authorized", str(cm.exception))
            self.assertIn("Zero bytes transmitted to USB", str(cm.exception))
            mock_win32_write.assert_not_called()
    ```

### 5.2. Все места вызова `DeviceIoControl` в коде с контекстом

#### Вызов 1: Опрос дескрипторов конечных точек (Query Pipe Config)
- **Файл:** [`openeos_ptp/transport.py`](file:///D:/AI/openeos_ptp/transport.py)
- **Класс / Метод:** `PipeConfigurationInspector.query_usbscan_pipe_config`
- **Диапазон строк:** 442–460

```python
        kernel32 = ctypes.windll.kernel32
        pipe_cfg = USBSCAN_PIPE_CONFIGURATION()
        bytes_returned = ctypes.c_ulong(0)

        success = kernel32.DeviceIoControl(
            ctypes.c_void_p(handle),
            IOCTL_GET_PIPE_CONFIGURATION,
            None,
            0,
            ctypes.byref(pipe_cfg),
            ctypes.sizeof(pipe_cfg),
            ctypes.byref(bytes_returned),
            None,
        )

        if not success:
            err = kernel32.GetLastError()
            raise PipeConfigurationError(f"IOCTL_GET_PIPE_CONFIGURATION failed with error {err}.")
```
*Назначение:* Чтение дескрипторов pipe из драйвера `usbscan.sys`. Входной буфер равен `None` (0 байт), выходной — структура `USBSCAN_PIPE_CONFIGURATION`.

#### Вызов 2: Сброс зависания конечной точки (Reset Pipe)
- **Файл:** [`openeos_ptp/transport.py`](file:///D:/AI/openeos_ptp/transport.py)
- **Функция:** `reset_usbscan_pipe`
- **Диапазон строк:** 524–540

```python
    kernel32 = ctypes.windll.kernel32
    in_buf = ctypes.c_uint(int(pipe_type))
    bytes_returned = ctypes.c_ulong(0)
    success = kernel32.DeviceIoControl(
        ctypes.c_void_p(handle),
        IOCTL_RESET_PIPE,
        ctypes.byref(in_buf),
        ctypes.sizeof(in_buf),
        None,
        0,
        ctypes.byref(bytes_returned),
        None,
    )
    if not success:
        err = kernel32.GetLastError()
        raise TransportError(f"IOCTL_RESET_PIPE failed with Win32 Error {err}.")
```
*Назначение:* Передаёт 4 байта `USBSCAN_PIPE_TYPE` (номер функционального канала для сброса STALL в драйвере). Данные PTP в камеру не передаются.

#### Вызов 3: Отмена асинхронных запросов (Cancel I/O)
- **Файл:** [`openeos_ptp/transport.py`](file:///D:/AI/openeos_ptp/transport.py)
- **Функция:** `cancel_usbscan_io`
- **Диапазон строк:** 550–566

```python
    kernel32 = ctypes.windll.kernel32
    in_buf = ctypes.c_uint(int(pipe_type))
    bytes_returned = ctypes.c_ulong(0)
    success = kernel32.DeviceIoControl(
        ctypes.c_void_p(handle),
        IOCTL_CANCEL_IO,
        ctypes.byref(in_buf),
        ctypes.sizeof(in_buf),
        None,
        0,
        ctypes.byref(bytes_returned),
        None,
    )
    if not success:
        err = kernel32.GetLastError()
        raise TransportError(f"IOCTL_CANCEL_IO failed with Win32 Error {err}.")
```
*Назначение:* Отмена зависших запросов драйвера. Входной буфер — 4 байта enum.

#### Вызов 4: Конфигурация тайм-аутов драйвера (Set Timeouts)
- **Файл:** [`openeos_ptp/transport.py`](file:///D:/AI/openeos_ptp/transport.py)
- **Функция:** `set_usbscan_timeouts`
- **Диапазон строк:** 580–600

```python
    kernel32 = ctypes.windll.kernel32
    t = USBSCAN_TIMEOUT(
        TimeoutRead=timeout_read_ms,
        TimeoutWrite=timeout_write_ms,
        TimeoutEvent=timeout_event_ms,
    )
    bytes_returned = ctypes.c_ulong(0)
    success = kernel32.DeviceIoControl(
        ctypes.c_void_p(handle),
        IOCTL_SET_TIMEOUT,
        ctypes.byref(t),
        ctypes.sizeof(t),
        None,
        0,
        ctypes.byref(bytes_returned),
        None,
    )
    if not success:
        err = kernel32.GetLastError()
        raise TransportError(f"IOCTL_SET_TIMEOUT failed with Win32 Error {err}.")
```
*Назначение:* Задаёт тайм-ауты драйвера (структура 12 байт: 3 x ULONG).

#### Вызов 5: Ожидание прерывания от устройства (Wait on Device Event)
- **Файл:** [`openeos_ptp/transport.py`](file:///D:/AI/openeos_ptp/transport.py)
- **Функция:** `wait_usbscan_device_event`
- **Диапазон строк:** 612–629

```python
    kernel32 = ctypes.windll.kernel32
    out_buf = ctypes.create_string_buffer(buffer_size)
    bytes_returned = ctypes.c_ulong(0)
    success = kernel32.DeviceIoControl(
        ctypes.c_void_p(handle),
        IOCTL_WAIT_ON_DEVICE_EVENT,
        None,
        0,
        ctypes.byref(out_buf),
        buffer_size,
        ctypes.byref(bytes_returned),
        None,
    )
    if not success:
        err = kernel32.GetLastError()
        raise TransportError(f"IOCTL_WAIT_ON_DEVICE_EVENT failed with Win32 Error {err}.")
    return out_buf.raw[:bytes_returned.value]
```
*Назначение:* Чтение пакета прерывания с Interrupt IN (0 входных байтов, читает событие из камеры).

---

## 6. Все места использования `CreateFileW` и `GENERIC_WRITE`

### 6.1. Определение констант
- **Файл:** [`openeos_ptp/transport.py`](file:///D:/AI/openeos_ptp/transport.py)
- **Диапазон строк:** 43–48

```python
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
```

### 6.2. Вызов `CreateFileW`
- **Файл:** [`openeos_ptp/transport.py`](file:///D:/AI/openeos_ptp/transport.py)
- **Класс / Метод:** `CameraAccessManager._default_open_handle`
- **Диапазон строк:** 787–810

```python
    @staticmethod
    def _default_open_handle(path: str) -> Tuple[int, int]:
        """
        Opens a raw device handle via Win32 CreateFileW in synchronous mode.
        NOTE: FILE_FLAG_OVERLAPPED is intentionally omitted because current transport
        uses synchronous ReadFile/WriteFile semantics.
        """
        if sys.platform != "win32":
            return INVALID_HANDLE_VALUE, ERROR_DEVICE_NOT_CONNECTED

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateFileW(
            ctypes.c_wchar_p(path),
            GENERIC_READ | GENERIC_WRITE,
            0,  # Exclusive access
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,  # Synchronous Win32 I/O
            None,
        )
        if handle == INVALID_HANDLE_VALUE:
            err = kernel32.GetLastError()
            return INVALID_HANDLE_VALUE, err
        return handle, 0
```

### 6.3. Анализ использования `GENERIC_WRITE`:
1. `GENERIC_WRITE` передаётся в `CreateFileW` вместе с `GENERIC_READ` на строке 799.
2. Согласно документации Microsoft DDK / Still Image Architecture (`usbscan.sys`), флаг `GENERIC_WRITE` обязателен для создания дескриптора устройства, если через него планируется вызывать управляющие `DeviceIoControl` (например, `IOCTL_SET_TIMEOUT`), даже если отправка данных по Bulk OUT не выполняется.
3. Открытие дескриптора с `GENERIC_WRITE` **не передаёт никаких байтов по USB шине**. Однако оно создаёт в ядре дескриптор с правом записи.

---

## 7. Определения `IOCTL_WRITE_REGISTERS` и `IOCTL_SEND_USB_REQUEST` и поиск их использования

### 7.1. Определения
- **Файл:** [`openeos_ptp/constants.py`](file:///D:/AI/openeos_ptp/constants.py)
- **Диапазон строк:** 134–135, 149–150

```python
# 4. IOCTL_WRITE_REGISTERS = CTL_CODE(0x8000, 0x0804, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_WRITE_REGISTERS = 0x80002010

# 9. IOCTL_SEND_USB_REQUEST = CTL_CODE(0x8000, 0x0809, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_SEND_USB_REQUEST = 0x80002024
```

### 7.2. Исчерпывающий поиск по всем файлам проекта:
1. `openeos_ptp/constants.py`:
   - Строка 135: объявление `IOCTL_WRITE_REGISTERS = 0x80002010`.
   - Строка 150: объявление `IOCTL_SEND_USB_REQUEST = 0x80002024`.
2. `openeos_ptp/__init__.py`:
   - Строки 37, 42: импорт из `.constants`.
   - Строки 136, 141: включение в список экспорта `__all__`.
3. `tests/test_phase_b_transport_mock.py`:
   - Строки 34, 39: импорт для тестирования формулы CTL_CODE.
   - Строки 486, 491, 520: проверка правильности вычисления значения `0x80002010` и `0x80002024` по формуле Microsoft WDK `CTL_CODE(0x8000, 0x0800 + offset, METHOD_BUFFERED, FILE_ANY_ACCESS)`.
4. **Результат поиска в `openeos_ptp/transport.py`:** **0 совпадений**. Константы не импортируются и нигде в коде транспорта не используются.
5. **Результат поиска в `OpenEOS.py`:** **0 совпадений**.

---

## 8. `format_pipe_specific_device_path()` и все места его вызова

### 8.1. Реализация и документация функции
- **Файл:** [`openeos_ptp/transport.py`](file:///D:/AI/openeos_ptp/transport.py)
- **Диапазон строк:** 631–660

```python
def format_pipe_specific_device_path(base_device_path: str, pipe_index: Optional[int] = None) -> str:
    """
    [UNVERIFIED / EXPERIMENTAL HELPER - NOT USED IN PRODUCTION EXECUTION PATH]

    Formats a device path with a pipe suffix for CreateFile.
    
    IMPORTANT TECHNICAL NOTES:
    1. Microsoft STI documentation describes appending '\\<index>' (e.g. '\\0', '\\1')
       specifically to port names returned by IStiDeviceControl::GetMyDevicePortName
       (or legacy port names like '\\\\.\\Usbscan0\\0').
    2. Appending '\\<index>' to a SetupAPI Device Interface Path
       ('\\\\?\\usb#vid_04a9&pid_330b#...#{6bdd1fc6-810f-11d0-bec7-08002be2092f}')
       is NOT officially documented by Microsoft for arbitrary device interfaces,
       is completely unverified on physical hardware, and may be rejected by the OS.
    3. For Canon EOS R6 Mark II:
       The device configuration descriptor exposes exactly one interface (Class 6 Still Image)
       with a single triplet of endpoints:
         - Bulk IN: Endpoint 0x81 (Pipe 1)
         - Bulk OUT: Endpoint 0x02 (Pipe 0)
         - Interrupt IN: Endpoint 0x83 (Pipe 2)
       When opening the base device interface path directly with CreateFileW (without '\\index'):
         - usbscan.sys automatically binds ReadFile to the default Bulk IN endpoint.
         - usbscan.sys automatically binds WriteFile to the default Bulk OUT endpoint.
         - Interrupt events are retrieved via IOCTL_WAIT_ON_DEVICE_EVENT on the same handle.
       Therefore, opening the base device path directly is fully sufficient and avoids any
       path parsing hazards. This function is retained strictly as an experimental helper.
    """
    if pipe_index is None:
        return base_device_path
    return f"{base_device_path}\\{pipe_index}"
```

### 8.2. Места вызова в проекте:
1. `openeos_ptp/transport.py`: **0 вызовов** (функция только объявлена).
2. `openeos_ptp/__init__.py`: импорт и экспорт в `__all__` (строки 95, 182).
3. `tests/test_phase_b_transport_mock.py`:
   - Строки 462–466 в `test_ctypes_structure_sizes_and_alignments`:
     ```python
     base_path = r"\\?\usb#vid_04a9&pid_330b#123#{6bdd1fc6-810f-11d0-bec7-08002be2092f}"
     self.assertEqual(format_pipe_specific_device_path(base_path, None), base_path)
     self.assertEqual(format_pipe_specific_device_path(base_path, 0), base_path + r"\0")
     self.assertEqual(format_pipe_specific_device_path(base_path, 1), base_path + r"\1")
     self.assertIn("EXPERIMENTAL HELPER", format_pipe_specific_device_path.__doc__ or "")
     ```
4. Функция **полностью исключена из рабочего цикла программы** и не выполняет системных вызовов.

---

## 9. Поиск скрытых и альтернативных путей отправки

### 9.1. Поиск сетевых сокетов и сетевых библиотек
- Поисковые термины: `import socket`, `from socket`, `urllib`, `requests`, `http.client`, `asyncio`
- **Результат поиска в `openeos_ptp/`:** **0 совпадений**. Сетевые модули не импортируются.

### 9.2. Поиск альтернативных USB-библиотек
- Поисковые термины: `usb.core`, `pyusb`, `libusb`, `winusb`, `hid`, `serial`
- **Результат поиска в `openeos_ptp/`:** **0 совпадений**. Сторонние низкоуровневые библиотеки отсутствуют.

### 9.3. Поиск альтернативных классов транспорта
- Поисковые термины: `class *Transport`
- Обнаружено 2 класса:
  1. `ProtectedUsbPtpTransport` ([`transport.py:939`](file:///D:/AI/openeos_ptp/transport.py#L939)) — рабочий класс с безусловной блокировкой отправки в `_write_raw_wire_bytes`.
  2. `MockPtpTransport` ([`mock_transport.py:37`](file:///D:/AI/openeos_ptp/mock_transport.py#L37)) — симулятор на фиксированных байтовых срезах `p62.pcapng`. Не использует `ctypes`, Win32 API и физические порты.

### 9.4. Поиск динамических переключателей разрешения отправки
- Поисковый термин: `PHYSICAL_IO_ENABLED`
  - В `openeos_ptp/`: **0 совпадений** (атрибут полностью удалён).
  - В тестах: встречается только в `tests/test_phase_b_protected_transport.py` как искусственная попытка обхода блокировки, которая приводит к `RuntimeError`.
- Поисковый термин: `os.environ`
  - В `openeos_ptp/`: **0 совпадений**. Конфигурация через переменные окружения отсутствует.
- Поисковый термин: `sys.argv`
  - В `openeos_ptp/`: **0 совпадений**. Аргументы командной строки в библиотеке не считываются.

---

## 10. Непроверенные предположения и ограничения

1. **Предположение о поведении драйвера `usbscan.sys` при вызове `CreateFileW`:**
   - Предполагается, что вызов `CreateFileW` с флагами `GENERIC_READ | GENERIC_WRITE` на пути `\\?\usb#vid_04a9&pid_330b#...#{6bdd1fc6-810f-11d0-bec7-08002be2092f}` открывает дескриптор устройства без немедленной генерации физических USB-пакетов на шине.
   - *Статус предположения:* Опирается на документацию Microsoft WDK usbscan, однако на реальном контроллере шины и физической камере Canon EOS R6 Mark II аппаратно с помощью аппаратного USB-сниффера не верифицировалось (камера не подключалась).
2. **Предположение о дефолтной привязке endpoints к ReadFile/WriteFile:**
   - Предполагается, что на Canon EOS R6 Mark II открытие базового пути устройства связывает Bulk IN с endpoint 0x81 и Bulk OUT с endpoint 0x02 автоматически.
   - *Статус предположения:* Подтверждается дескрипторами в `p62.pcapng` и спецификацией STI usbscan.sys, но работа с физическим устройством в текущей фазе не проводилась.
3. **Функция `format_pipe_specific_device_path`:**
   - Поведение драйвера при открытии путей с суффиксами `\0`, `\1` на произвольных Device Interface GUID не верифицировано на физическом оборудовании (в коде помечена как экспериментальная и не используется).

---

## 11. Разграничение статусов верификации отдельных утверждений

| Утверждение / Компонент | Статус | Обоснование |
|---|---|---|
| Метод `_write_raw_wire_bytes` безусловно возбуждает `RuntimeError` | **VERIFIED** | Доказано кодом ([`transport.py:1014-1017`](file:///D:/AI/openeos_ptp/transport.py#L1014-L1017)) и тестами `test_10`, `test_11`. |
| Ни один метод `write_ptp_*` не может миновать `_write_raw_wire_bytes` | **VERIFIED** | Доказано статической структурой методов ([`transport.py:988, 1003`](file:///D:/AI/openeos_ptp/transport.py#L988)). |
| `ProtocolGuard` обязательно вызывается до отправки в `write_ptp_*` | **VERIFIED** | Доказано строками [`transport.py:985, 1000`](file:///D:/AI/openeos_ptp/transport.py#L985). |
| Отсутствие вызовов `WriteFile` в кодовой базе `openeos_ptp/` | **VERIFIED** | Подтверждено поиском по всем файлам (вызовов 0). |
| Отсутствие PTP-пакетов в вызовах `DeviceIoControl` | **VERIFIED** | Все 5 вызовов передают только служебные структуры `usbscan.sys`. |
| Отсутствие сторонних USB/сетевых библиотек и сокетов | **VERIFIED** | Подтверждено полным отсутствием импортов. |
| Изоляция GUI `OpenEOS.py` от PTP-подсистемы | **VERIFIED** | В `OpenEOS.py` нет импортов `openeos_ptp`. |
| Поведение ядра Win32 / `usbscan.sys` при открытии дескриптора на физической шине | **PARTIALLY VERIFIED** | Код доказан статически, но физический запуск с камерой не проводился. |
| Работа с физическими endpoints камеры через usbscan.sys | **PARTIALLY VERIFIED** | Опирается на WDK и PCAPNG, но физический кабель отключён. |
| Поведение `format_pipe_specific_device_path` на реальном драйвере | **UNKNOWN** | Функция помечена как непроверенная и в коде не вызывается. |

### Общий итоговый статус отчёта: **PARTIALLY VERIFIED**
*Пояснение:* Поскольку физическое оборудование не подключалось, а поведение драйвера ОС при создании дескриптора не может быть проверено аппаратно без подключения камеры, присвоение общего статуса `VERIFIED` противоречило бы принципу доказательной строгости. Программный запрет отправки в кодовой базе имеет статус **VERIFIED**.

---

## 12. Подтверждение целостности файлов и отсутствия физического I/O

- **Изменение файлов:** В ходе выполнения задачи ни один файл с исходным кодом (`openeos_ptp/*.py`, `tests/*.py`, `OpenEOS.py`) **не модифицировался**.
- **Физический I/O:** Физическая камера Canon EOS R6 Mark II **не подключалась** к ПК, команды на USB-контроллер **не отправлялись**, физическая передача строго равна 0 байт.
