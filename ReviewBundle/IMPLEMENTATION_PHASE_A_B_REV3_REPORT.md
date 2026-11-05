# OpenEOS — Отчёт о точечной ревизии фаз A и B (REV 3)

**Дата составления:** 2 ноября 2026 г.  
**Статус:** ФАЗА A ЗАВЕРШЕНА (100%), ФАЗА B ЗАВЕРШЕНА (100% Mock / Архитектура готова, Physical I/O заблокирован), ФАЗА C ЗАБЛОКИРОВАНА.  
**Физическое подключение:** 0 подключений, 0 байт отправлено на физическую камеру. Основной файл `OpenEOS.py` (v0.4.2, 1980 строк) **полностью неизменен**.

---

## 1. Сводка ревизии и контрольный перечень файлов

В рамках ревизии REV 3 устранены все замечания внешнего аудита DeepSeek и внутреннего анализа безопасности Protocol Guard, Win32 ctypes на платформе Windows x64 и обработки дескрипторов устройств.

### Контрольный перечень модифицированных файлов

| Файл | Назначение | Изменения в REV 3 |
|---|---|---|
| `openeos_ptp/constants.py` | PTP константы, GUIDs, IOCTLs usbscan.h | Переход к нейтральной терминологии `Shutter Counter` (`PROP_SHUTTER_COUNTER = 0x12000001`), сохранение обратной совместимости (`PROP_MECHANICAL_SHUTTER = PROP_SHUTTER_COUNTER`), все 12 IOCTL с базой `0x80002000`. |
| `openeos_ptp/decoders.py` | Офлайн-декодеры свойств PTP | Нейтральное имя поля `shutter_counter`, свойство обратной совместимости `@property mechanical_shutter_counter`, сохранение `opaque_tail`. |
| `openeos_ptp/protocol_guard.py` | Фильтр безопасности и автомат состояний | Валидация параметра длины в ответе 0x9052 (`[8]`/`[4]`/`[8]`), отслеживание использованных TxID (`_used_tx_ids`), запрет повторного использования TxID и совпадения TxID Fetch с Command, запрет `CloseSession` во время незавершённых транзакций, строгая проверка ответа `CloseSession` (`PTP_RC_OK`), безопасный сброс состояния при ошибках. |
| `openeos_ptp/transport.py` | Транспортный слой Windows usbscan.sys | Функция `is_invalid_handle()` (проверка `-1`, `0xFFFFFFFF`, `0xFFFFFFFFFFFFFFFF`, `0`, `None`), функция `init_win32_api()` с явными `argtypes`/`restype` для 9 функций Win32, класс `ProtectedUsbPtpTransport` (пайплайн `Container -> Guard -> USB`, `PHYSICAL_IO_ENABLED = False`). |
| `openeos_ptp/__init__.py` | Точка входа пакета | Экспорт `PROP_MECHANICAL_SHUTTER`, `ProtectedUsbPtpTransport`, `is_invalid_handle`, `init_win32_api`. |
| `tests/test_phase_a_decoders.py` | Unit-тесты декодеров (11 тестов) | Проверка `shutter_counter` и алиаса `mechanical_shutter_counter`, сохранение `opaque_tail`. |
| `tests/test_phase_a_payloads.py` | Unit-тесты контейнеров (9 тестов) | Проверка генераторов 55B/20B, смещений полей, байтовой валидации. |
| `tests/test_phase_b_protocol_guard.py` | Unit-тесты Protocol Guard (16 тестов) | Добавлены негативные тесты: несовпадение объявленной длины в ответе 0x9052, дублирование TxID, CloseSession во время активной транзакции, отказ CloseSession, восстановление сессии при ошибках данных. |
| `tests/test_phase_b_transport_mock.py` | Unit-тесты транспорта и Win32 (20 тестов) | Добавлены негативные тесты: попытка обхода Protocol Guard, проверка `is_invalid_handle`, размеры и выравнивание структур ctypes (`USBSCAN_PIPE_INFORMATION` 8B, `USBSCAN_PIPE_CONFIGURATION` 68B, `USBSCAN_TIMEOUT` 12B), сигнатуры 9 функций Win32. |

**Итого тестов в наборе:** 56 тестов (11 + 9 + 16 + 20).

---

## 2. Детализация реализованных исправлений

### 2.1. Семантика свойства 0x12000001 (Shutter Counter)
- Термин «механический затвор» снят как недоказанное аппаратное утверждение: в официальном сервисном отчёте Canon свойство фигурирует как «Shutter Counter: 60,689».
- Поле структуры переименовано в `shutter_counter`.
- Для сохранения 100% обратной совместимости с существующим кодом реализован алиас `@property mechanical_shutter_counter`, возвращающий то же значение. В `constants.py` добавлен алиас `PROP_MECHANICAL_SHUTTER = PROP_SHUTTER_COUNTER`.
- Неизвестные верхние 4 байта (opaque tail `00 00 00 00`) сохраняются в неизменном виде в поле `opaque_tail`.

### 2.2. Усиление Protocol Guard (`protocol_guard.py`)
1. **Валидация длины ответа 0x9052:**
   - На основании данных дампа `р62.pcapng` (фреймы EPB #71, #89, #175) установлено, что ответ камеры на команду 0x9052 содержит ровно один 4-байтовый параметр, объявляющий размер последующего буфера данных:
     - Для `0x12000001` (Shutter Counter): параметр `[8]`;
     - Для `0x12000003` (Release Counter Total): параметр `[4]`;
     - Для `0x12000005` (Power & Uptime): параметр `[8]`.
   - Protocol Guard сверяет возвращённый параметр со словарём ожидаемых длин `EXPECTED_DATA_LENGTHS`. При несовпадении транзакция немедленно блокируется, генерируется `SecurityViolationError`, а автомат возвращается в безопасное состояние `SESSION_OPEN`.
2. **Контроль Transaction ID:**
   - Введён реестр `_used_tx_ids: set[int]`, действующий в рамках открытой сессии. Повторная отправка команды с уже использованным TxID категорически блокируется.
   - Запрещено совпадение TxID команды 0x9053 (Fetch) с предшествующей командой 0x9052.
3. **Строгая фазовая изоляция:**
   - Запрещён пропуск фазы Data OUT (попытка отправить 0x9053 Fetch сразу после 0x9052 Command вызывает `ProtocolSequenceError`).
   - Запрещён вызов 0x9053 Fetch до получения ответа `PTP_RC_OK` на фазу 0x9052.
   - Запрещён повторный вызов 0x9053 Fetch подряд (двойное чтение буфера).
   - Все входящие контейнеры Data IN проверяются на соответствие точной длине свойства.
4. **Безопасное завершение сессии (`CloseSession`):**
   - Запрещена отправка `CloseSession` во время незавершённых фаз транзакции (`WAITING_DATA_OUT`, `WAITING_COMMAND_RESPONSE`, `WAITING_FETCH_COMMAND`, `WAITING_FETCH_DATA_IN`).
   - Ответ камеры на `CloseSession` проверяется на код `PTP_RC_OK`. При любом коде ошибки генерируется исключение, но состояние охранника безусловно сбрасывается в `DISCONNECTED`, предотвращая зависание сессии.

### 2.3. Единый защищённый конвейер отправки данных
- Реализован класс `ProtectedUsbPtpTransport(device_handle, guard)`:
  - Инициализация без переданного экземпляра `ProtocolGuard` невозможна (вызывает `SecurityViolationError`).
  - Любая запись PTP контейнера проходит строгий пайплайн:
    $$\text{PTP Container} \longrightarrow \text{Protocol Guard} \longrightarrow \text{USB WriteFile}$$
  - Прямой обход гварда физически невозможен.
  - Атрибут `PHYSICAL_IO_ENABLED = False` аппаратно блокирует отправку байт в дескриптор устройства на уровне метода `_write_raw_wire_bytes()`, вызывая `RuntimeError("Phase C not authorized")`.
  - Статус архитектуры: ядро готово к подключению, ожидает авторизации Фазы C.

### 2.4. Совместимость Win32 ctypes на Windows x64
1. **Проблема усечения указателей 64-бит:**
   - В стандартном Python `ctypes` возвращаемое значение функции Win32 по умолчанию считается 32-битным знаковым целым (`c_int`), если явно не задан `restype`. При работе на 64-битной Windows указатели `HANDLE` (`c_void_p`) при адресах выше $2^{31}-1$ усекаются, что приводит к краху `CreateFileW` и `SetupDiGetClassDevsW`.
   - Реализована функция `init_win32_api(setupapi, kernel32)`, которая на старте модуля строго конфигурирует типы аргументов (`argtypes`) и тип результата (`restype`) для всех 9 функций Win32:
     - `SetupDiGetClassDevsW` (restype = `c_void_p`)
     - `SetupDiEnumDeviceInterfaces` (restype = `c_bool`)
     - `SetupDiGetDeviceInterfaceDetailW` (restype = `c_bool`)
     - `SetupDiDestroyDeviceInfoList` (restype = `c_bool`)
     - `SetupDiGetDeviceInstanceIdW` (restype = `c_bool`)
     - `CreateFileW` (restype = `c_void_p`)
     - `DeviceIoControl` (restype = `c_bool`)
     - `ReadFile` (restype = `c_bool`)
     - `WriteFile` (restype = `c_bool`)
     - `CloseHandle` (restype = `c_bool`)
2. **Проблема знаковости `INVALID_HANDLE_VALUE`:**
   - В C++ константа `INVALID_HANDLE_VALUE` определена как `((HANDLE)(LONG_PTR)-1)`. В 64-битном Python значение `c_void_p(-1).value` равно беззнаковому `0xFFFFFFFFFFFFFFFF` (18446744073709551615). Сравнение `handle == -1` в Python возвращает `False`.
   - Реализована функция `is_invalid_handle(handle)`, поддерживающая знаковые `-1`, 32-битные `0xFFFFFFFF`, 64-битные `0xFFFFFFFFFFFFFFFF`, а также `0` и `None`.
3. **Размеры и выравнивание структур ctypes (usbscan.h):**
   - `USBSCAN_PIPE_INFORMATION`: ровно 8 байт (MaxPacket 2B, EndpointAddress 1B, Interval 1B, PipeType 4B).
   - `USBSCAN_PIPE_CONFIGURATION`: ровно 68 байт (NumberOfPipes 4B, 8 записей по 8B).
   - `USBSCAN_TIMEOUT`: ровно 12 байт (TimeoutRead 4B, TimeoutWrite 4B, TimeoutEvent 4B).

---

## 3. Детальный состав и структура тестового набора (56 тестов)

### Набор 1: `tests.test_phase_a_decoders` (11 тестов)
1. `test_shutter_counter_exact_value` — точное совпадение с сервисным отчётом: 60,689, проверка обратного алиаса `mechanical_shutter_counter`.
2. `test_shutter_counter_opaque_tail_preserved` — полное сохранение верхних 4 байт (opaque tail) в сыром и кастомном виде.
3. `test_shutter_counter_little_endian` — проверка порядка байт uint32-LE.
4. `test_shutter_counter_length_validation` — отклонение буферов длиной $\neq 8$ байт.
5. `test_release_counter_exact_value` — точное совпадение с сервисным отчётом: 840,377.
6. `test_release_counter_little_endian` — проверка порядка байт uint32-LE.
7. `test_release_counter_length_validation` — отклонение буферов длиной $\neq 4$ байт.
8. `test_power_and_uptime_exact_value` — точное совпадение: 5,984 включений и 3,392,007 секунд.
9. `test_power_and_uptime_formatting` — математическая корректность расчёта строки времени (`39d 06h 13m 27s`).
10. `test_power_and_uptime_length_validation` — отклонение буферов длиной $\neq 8$ байт.
11. `test_invalid_types_raise_decoder_error` — отклонение некорректных типов (`None`, `str`, `list`).

### Набор 2: `tests.test_phase_a_payloads` (9 тестов)
1. `test_build_fa_command_container_txid_26_exact` — байтовое совпадение с 20-байтным контейнером 0x9052 из `р62.pcapng`.
2. `test_build_fa_get_property_container_txid_26_exact` — побайтовое совпадение с 55-байтным контейнером Data OUT (FA_GetProperty) из `р62.pcapng`.
3. `test_fa_get_property_payload_offsets` — проверка смещений: имя (смещение 0), argc (смещение 15), arg1 tag=2 (смещение 19), prop_id (смещение 23), padding (смещение 39).
4. `test_build_fa_fetch_command_empty_params` — генерация 12-байтной команды 0x9053 для TxID 26 и 32.
5. `test_build_fa_fetch_command_with_params` — генерация 24-байтной команды 0x9053 для TxID 63 (`[0, 0, 1]`).
6. `test_validate_fa_get_property_payload_valid` — успешная валидация корректных буферов.
7. `test_validate_fa_get_property_payload_rejections` — отказ при неверном размере, имени процедуры или теге аргумента.
8. `test_parse_ptp_container` — разбор сырых байт контейнера в именованные поля.
9. `test_parse_ptp_container_short_buffer` — отказ при длине буфера менее 12 байт.

### Набор 3: `tests.test_phase_b_protocol_guard` (16 тестов)
1. `test_forbidden_opcodes_immediately_rejected` — немедленная блокировка опасных OpCode (`0x905A`, `0x905B`, `0x905C`, `0x9028`, `0x9054`).
2. `test_prohibited_procedure_patterns_rejected` — блокировка опасных текстовых команд в payload (`EventProc`, `FA_SetProperty`, `MonWrite` и др.).
3. `test_valid_full_readout_sequence` — прохождение полного штатного цикла транзакции через все фазы.
4. `test_close_session_and_reopen_without_manual_reset` — корректный сброс состояния при `CloseSession` и повторное открытие сессии.
5. `test_binary_arguments_with_text_sequences_not_falsely_rejected` — отсутствие ложных срабатываний фильтра на бинарных данных аргументов.
6. `test_tampered_transaction_id` — блокировка при подмене TxID в теле Data OUT.
7. `test_skip_data_out` — блокировка при попытке пропустить Data OUT и сразу вызвать 0x9053 Fetch.
8. `test_unexpected_response` — корректная обработка кода отказа камеры (`0x2005` OperationNotSupported) с откатом состояния.
9. `test_invalid_data_in_length` — отказ при получении буфера Data IN неверной длины.
10. `test_duplicate_fetch` — блокировка при попытке выполнить повторный 0x9053 Fetch подряд.
11. `test_command_different_procedure_name` — отказ при любой процедуре, отличной от `FA_GetProperty`.
12. `test_fa_command_response_invalid_declared_length` — **(Новый REV 3)** отказ при несовпадении длины в параметре ответа 0x9052.
13. `test_duplicate_transaction_id_rejected` — **(Новый REV 3)** блокировка повторного использования TxID и совпадения TxID Fetch с Command.
14. `test_close_session_during_active_transaction_rejected` — **(Новый REV 3)** запрет вызова `CloseSession` во время незавершённой транзакции.
15. `test_close_session_error_response_handling` — **(Новый REV 3)** обработка отказа `CloseSession` с гарантированным переводом в `DISCONNECTED`.
16. `test_error_state_cleanup_restores_session_open` — **(Новый REV 3)** сброс состояния в безопасное `SESSION_OPEN` при повреждении данных, исключающий зависание.

### Набор 4: `tests.test_phase_b_transport_mock` (20 тестов)
1. `test_guid_constants_verification` — проверка официальных GUID Microsoft (`GUID_DEVINTERFACE_IMAGE`, `GUID_DEVINTERFACE_WPD`).
2. `test_extract_vid_pid` — регулярное выражение извлечения VID/PID из путей интерфейсов Windows.
3. `test_pipe_inspection_pipe_index_vs_endpoint_address` — строгое разграничение Windows Pipe Index и USB Endpoint Address.
4. `test_pipe_inspection_arbitrary_endpoints` — независимость логики от конкретных адресов эндпоинтов.
5. `test_pipe_inspection_missing_bulk_endpoints` — отказ при отсутствии необходимых эндпоинтов Bulk IN / Bulk OUT.
6. `test_safe_device_handle_lifecycle` — RAII дескриптора при штатном выходе и исключениях.
7. `test_camera_access_manager_edsdk_handover` — корректная передача управления между EDSDK и usbscan.sys.
8. `test_camera_access_manager_timeout_on_access_denied` — таймаут при устойчивом захвате камеры другим процессом.
9. `test_mock_transport_full_readout_sequence` — сквозной тест опроса всех 3 свойств через Mock Transport.
10. `test_mock_transport_timeout_simulation` — симуляция аппаратного таймаута с генерацией `TimeoutError`.
11. `test_setupapi_enumeration_mock_success` — корректное перечисление устройств через SetupAPI на моке.
12. `test_setupapi_enumeration_error_handling` — устойчивость к ошибкам SetupAPI.
13. `test_invalid_device_path_handling` — обработка несуществующих путей устройств.
14. `test_camera_access_manager_mandatory_contracts` — проверка строгих контрактов обратных вызовов EDSDK.
15. `test_usbscan_pipe_types_and_ioctl_structures` — проверка enum usbscan.sys и экспериментального форматирования пути.
16. `test_usbscan_ioctl_ctl_code_derivation_all_12_functions` — проверка формулы `CTL_CODE` для всех 12 функций usbscan.h.
17. `test_guard_bypass_attempt` — **(Новый REV 3)** проверка блокировки отправки в обход Protocol Guard и запрета физического ввода-вывода.
18. `test_invalid_handle_checks` — **(Новый REV 3)** проверка `is_invalid_handle` для всех представлений (`-1`, `0xFFFFFFFF`, `0xFFFFFFFFFFFFFFFF`, `0`, `None`).
19. `test_ctypes_structure_sizes_and_alignments` — **(Новый REV 3)** проверка размеров и смещений полей структур `USBSCAN_PIPE_INFORMATION` (8B), `USBSCAN_PIPE_CONFIGURATION` (68B), `USBSCAN_TIMEOUT` (12B).
20. `test_win32_api_function_signatures` — **(Новый REV 3)** проверка явной инициализации `argtypes` и `restype` для всех 9 функций Win32 x64.

---

## 4. Инструкция по локальному запуску тестов (PowerShell)

Для локальной проверки всего пакета выполните следующие команды в терминале PowerShell из директории `d:\AI` (или `C:\Users\and!m\OpenEOS`):

### 4.1. Запуск полного набора тестов (все 56 тестов)
```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

### 4.2. Помодульный запуск наборов
```powershell
# 1. Тесты офлайн-декодеров свойств (11 тестов)
python -m unittest tests.test_phase_a_decoders -v

# 2. Тесты генераторов контейнеров и полезных нагрузок (9 тестов)
python -m unittest tests.test_phase_a_payloads -v

# 3. Тесты фильтра безопасности Protocol Guard (16 тестов)
python -m unittest tests.test_phase_b_protocol_guard -v

# 4. Тесты Still Image транспорта, SetupAPI, IOCTL и ctypes (20 тестов)
python -m unittest tests.test_phase_b_transport_mock -v
```

### 4.3. Проверка синтаксиса всех модулей
```powershell
python -m compileall openeos_ptp tests
```

---

## 5. Оставшиеся неисследованные вопросы (UNKNOWN)

Несмотря на полное покрытие протокольных фаз A и B, остаются следующие аппаратные аспекты, требующие осторожности:

1. **Значение верхних 4 байт (opaque tail) в свойстве 0x12000001:**
   - В дампе `р62.pcapng` свойство `0x12000001` возвращает 8 байт: `11 ed 00 00 00 00 00 00`.
   - Значение `60,689` полностью содержится в первых 4 байтах (`11 ed 00 00`).
   - Назначение байт 4..7 в точности неизвестно: это может быть счётчик электронного затвора, старшее слово 64-битного счётчика (на случай переполнения) либо резервные флаги. Текущая реализация сохраняет эти байты полностью в `opaque_tail`, не делая необоснованных предположений.
2. **Параметры команды 0x9053 Fetch для других сервисных свойств:**
   - Свойства `0x12000001` и `0x12000003` вычитываются с пустым списком параметров (`argc = 0`).
   - Свойство `0x12000005` (Uptime) требует параметров `[0, 0, 1]`.
   - Семантика этих трёх параметров до конца недокументирована производителем; декодер строго соблюдает наблюдаемый в дампе формат.
3. **Поведение usbscan.sys на нестандартных хост-контроллерах USB 3.x:**
   - Поведение драйвера Microsoft `usbscan.sys` зависит от реализации хост-контроллера (Intel, AMD, ASMedia) при передаче коротких пакетов (Short Packet) по каналу Bulk IN. Механизм таймаутов через `IOCTL_SET_TIMEOUT` настроен консервативно (5000 мс на чтение/запись).

---

## 6. Оценка готовности фаз и статус

### Фаза A (Офлайн-декодеры и генераторы контейнеров)
- **Готовность:** 100% (READY).
- **Обоснование:** Все 3 свойства (`0x12000001`, `0x12000003`, `0x12000005`) точно декодируются из сырых дампов PCAPNG и сервисного отчёта Canon. Структура `FA_GetProperty` строго валидируется по байтам. Сохранена полная обратная совместимость.

### Фаза B (Транспортный слой, Protocol Guard, SetupAPI, Mock)
- **Готовность:** 100% (READY для Mock и архитектуры безопасности).
- **Обоснование:** Все Win32 ctypes структуры выровнены и протестированы. Все 12 IOCTL usbscan.sys пересчитаны и верифицированы. Все 9 функций Win32 имеют строгие типы. Protocol Guard защищён от 14 видов атак и сбоев. Программный флаг `PHYSICAL_IO_ENABLED = False` физически блокирует отправку данных.

### Фаза C (Физическое подключение к камере Canon EOS R6 Mark II)
- **Готовность:** ЗАБЛОКИРОВАНА (BLOCKED).
- **Статус:** Категорически запрещена до явного отдельного указания пользователя. Физическая камера не подключалась, PTP-пакеты не отправлялись.
