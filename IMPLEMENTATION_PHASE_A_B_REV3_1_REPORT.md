# Отчёт по ревизии REV 3.1: Сквозной защищённый транспорт и граница Protocol Guard

> **Статус:** ЗАВЕРШЕНО  
> **Версия спецификации:** `OPENEOS_ONLINE_READ_SPEC_V1.2`  
> **Пакет аудита:** `OpenEOS Phase A/B Revision 3.1`  
> **Целевая камера:** Canon EOS R6 Mark II (USB VID `0x04A9`, PID `0x330B`)  
> **Аппаратное подключение:** СТРОГО ЗАБЛОКИРОВАНО (`PHYSICAL_IO_ENABLED = False`)  
> **Тестовое покрытие:** 67 тестов (11 новых в REV 3.1, 56 базовых), 100% PASS

---

## 1. Резюме исправлений и целей REV 3.1

В рамках ревизии REV 3.1 выполнен полный цикл аудита и укрепления сквозного транспортного контура OpenEOS:
1. **Устранено несоответствие `PtpContainer` (`to_bytes` vs `serialize`)**:
   - Выявлена причина: класс `PtpContainer` объявлял метод `serialize() -> bytes`, тогда как метод `ProtectedUsbPtpTransport.write_ptp_container` обращался к отсутствующему `container.to_bytes()`.
   - Внедрено минимальное и обратно-совместимое исправление: добавлен метод-псевдоним `to_bytes(self) -> bytes: return self.serialize()` в `openeos_ptp/payloads.py`, а вызов в `ProtectedUsbPtpTransport.write_ptp_container()` стандартизирован на `container.serialize()`.
2. **Усилена граница Protocol Guard (`Wire Inspection Boundary`)**:
   - Реализована строгая архитектурная цепочка передачи:
     $$\text{PTP Container} \longrightarrow \text{Serialization} \longrightarrow \text{Protocol Guard} \longrightarrow \text{USB WriteFile}$$
   - Protocol Guard инспектирует непосредственно **фактические байты физического провода** (`raw wire bytes`) непосредственно перед отправкой на USB Bulk OUT pipe.
   - Проверяются: совпадение заявленной длины в заголовке с фактическим размером буфера, тип контейнера (Command/Data/Response), валидность OpCode, соответствие Transaction ID текущему шагу FSM, имя процедуры (`FA_GetProperty\0`), разрешённый Property ID (`0x12000001`, `0x12000003`, `0x12000005`), структура аргументов и строго нулевой padding.
   - Любой отказ Protocol Guard безусловно прерывает отправку и полностью исключает вызов Win32 `WriteFile`.
3. **Изоляция и неизменяемость `PHYSICAL_IO_ENABLED`**:
   - `PHYSICAL_IO_ENABLED = False` зафиксирован на уровне класса и экземпляра `ProtectedUsbPtpTransport`.
   - Обычные пользовательские действия (GUI, настройки, штатные методы) не способны переключить этот флаг.
   - Любая попытка физической отправки инициирует исключение `RuntimeError("Phase C not authorized: physical PTP dispatch to Canon EOS R6 Mark II is strictly disabled. Zero bytes transmitted to USB.")` до обращения к дескрипторам Win32 API.
4. **Разработан и интегрирован новый тестовый модуль `test_phase_b_protected_transport.py`**:
   - Реализовано 11 специализированных unit-тестов.
   - Общее число тестов проекта доведено до 67 (все выполняются строго offline в mock-окружении).

---

## 2. Анализ и устранение несоответствия `to_bytes` vs `serialize`

### 2.1 Исходная проблема
В ревизии REV 3.0 в модуле `openeos_ptp/transport.py` был внедрён класс `ProtectedUsbPtpTransport`, метод которого содержал вызов:
```python
# Было в REV 3.0:
self._guard.validate_outgoing_container(container)
raw_bytes = container.to_bytes()  # AttributeError!
```
При этом в `openeos_ptp/payloads.py` класс `PtpContainer` реализовывал упаковку через метод `serialize()`.

### 2.2 Минимальное исправление
Для обеспечения взаимной совместимости и предотвращения регрессий:
1. В `openeos_ptp/payloads.py` добавлен метод:
   ```python
   def to_bytes(self) -> bytes:
       """Alias for serialize() to ensure compatibility across modules."""
       return self.serialize()
   ```
2. В `openeos_ptp/transport.py` метод `write_ptp_container` переведён на явный вызов `container.serialize()`:
   ```python
   def write_ptp_container(self, container: PtpContainer) -> int:
       if not isinstance(container, PtpContainer):
           raise SecurityViolationError(f"Expected PtpContainer instance, got {type(container).__name__}")
       
       # Шаг 1: Сериализация контейнера в физические байты
       raw_bytes = container.serialize()
       
       # Шаг 2: Валидация байтов провода Protocol Guard непосредственно перед отправкой
       self._guard.validate_outgoing_container_bytes(raw_bytes)
       
       # Шаг 3: Гейтированная физическая отправка
       return self._write_raw_wire_bytes(raw_bytes)
   ```
3. Добавлен метод `write_ptp_bytes(self, raw_bytes: bytes) -> int` для отправки уже скомпонованных буферов, также защищённый принудительной валидацией `validate_outgoing_container_bytes`.

---

## 3. Архитектура укреплённой границы Protocol Guard

```mermaid
flowchart TD
    subgraph Client ["OpenEOS Diagnostic Engine"]
        A["PtpContainer Builder"]
    end

    subgraph TransportPipeline ["Protected USB Transport Pipeline"]
        B["container.serialize()"]
        C{"Protocol Guard\nvalidate_outgoing_container_bytes()"}
        D{"Security / Format Error?"}
        E["Raise SecurityViolationError\nReset/Abort State"]
        F{"PHYSICAL_IO_ENABLED == True?"}
        G["Raise RuntimeError\n(Phase C Blocked)"]
        H["Win32 WriteFile (Bulk OUT)"]
    end

    A --> B
    B --> C
    C --> D
    D -- Yes --> E
    D -- No --> F
    F -- No (Phase B) --> G
    F -- Yes (Phase C Authorized) --> H
```

### 3.1 Инварианты безопасности границы
1. **Zero Bypass Guarantee**:
   Ни один байт не может поступить в Win32 `WriteFile`, минуя `validate_outgoing_container_bytes(raw_bytes)`.
2. **Однократное переключение состояний FSM**:
   Вся инспекция сфокусирована в одном месте: `validate_outgoing_container_bytes` парсит физический провод через `parse_ptp_container`, после чего выполняет проверку FSM через `validate_outgoing_container`. Повторный вызов исключён, что защищает конечный автомат от рассинхронизации шагов.
3. **Контроль физической длины буфера**:
   Если заявленная в PTP-заголовке длина `length` не равна реальной длине переданного байтового массива `len(raw_bytes)` или меньше минимального 12-байтового заголовка PTP, пакет отсекается с `SecurityViolationError`.
4. **Контроль содержимого FA_GetProperty**:
   - Длина контейнера ровно 55 байт (12 байт заголовок + 43 байта полезная нагрузка).
   - Полезная нагрузка содержит имя `FA_GetProperty\0` (15 байт). Любые модификации или попытки подстановки `EventProc` / `SetProperty` блокируются.
   - `argc == 1`, `tag == 2` (DWORD).
   - Property ID входит в белый список: `0x12000001`, `0x12000003`, `0x12000005`.
   - Завершающие байты аргумента (12 байт, смещение 27..38) и выравнивание структуры (4 байта, смещение 39..42) **строго нулевые**. Наличие любого ненулевого байта приводит к немедленной блокировке.

---

## 4. Контроль неизменяемости флага `PHYSICAL_IO_ENABLED`

В классе `ProtectedUsbPtpTransport`:
```python
PHYSICAL_IO_ENABLED: bool = False
```
Вспомогательный метод физической записи:
```python
def _write_raw_wire_bytes(self, data: bytes) -> int:
    if not self.PHYSICAL_IO_ENABLED:
        raise RuntimeError(
            "Phase C not authorized: physical PTP dispatch to Canon EOS R6 Mark II is strictly disabled. "
            "Zero bytes transmitted to USB."
        )
    ...
```

### Гарантии защиты:
1. Флаг зафиксирован в значении `False` в кодовой базе.
2. В графическом интерфейсе `OpenEOS.py` (v0.4.2) отсутствуют какие-либо элементы управления (кнопки, чекбоксы, пункты меню), способные изменить данную переменную.
3. В модулях `openeos_ptp/` отсутствуют функции автопереключения флага при обнаружении камеры.
4. Все тесты запускаются с `PHYSICAL_IO_ENABLED = False` либо используют `MockPtpTransport`.

---

## 5. Полная структура тестового пакета (67 тестов)

Сводная матрица тестов проекта:

| Модуль тестов | Количество | Фокус проверки |
|---|:---:|---|
| `tests/test_phase_a_decoders.py` | 11 | Декодирование свойств `0x12000001`, `0x12000003`, `0x12000005`, little-endian, opaque_tail, валидация битых буферов |
| `tests/test_phase_a_payloads.py` | 9 | Сборка Command/Data/Response контейнеров, побайтовое соответствие PCAPNG, валидация 43-байтового FA-пейлоада |
| `tests/test_phase_b_protocol_guard.py` | 16 | FSM-переходы (DISCONNECTED $\to$ SESSION_OPEN $\to$ WAITING_DATA_OUT $\to$ FETCH), блокировка запрещённых OpCodes (`0x905A` и др.), защита от повтора TxID |
| `tests/test_phase_b_transport_mock.py` | 20 | Windows SetupAPI mock-эмуляция, парсинг дескрипторов `IOCTL_GET_PIPE_CONFIGURATION`, корректность констант usbscan IOCTL, RAII дескрипторов |
| `tests/test_phase_b_protected_transport.py` (**REV 3.1**) | **11** | **Сквозная цепочка защиты, сериализация, инспекция физических байтов, блокировка искажённых пакетов, гейтирование Physical I/O** |
| **ИТОГО** | **67** | **100% PASS** |

### Детальное описание 11 новых тестов REV 3.1:
1. `test_1_ptp_container_serialize_success`:
   Проверяет корректность упаковки заголовка и данных методом `serialize()`, а также эквивалентность вывода метода `to_bytes()`.
2. `test_2_write_ptp_container_no_missing_method`:
   Подтверждает отсутствие `AttributeError` при вызове `write_ptp_container` и штатное прохождение пакета до гейта Фазы C.
3. `test_3_incorrect_serialized_container_length_blocked`:
   Проверяет отсечение буферов с расхождением заявленной длины и фактической, а также буферов короче 12 байт.
4. `test_4_tampered_bytes_after_preparation_detected`:
   Эмулирует модификацию байтов Transaction ID в уже скомпонованном буфере; подтверждает немедленное обнаружение подмены инспектором провода.
5. `test_5_invalid_property_id_blocked`:
   Проверяет блокировку Data OUT контейнеров с недопустимыми кодами свойств (например, `0x12009999`).
6. `test_6_procedure_name_modification_blocked`:
   Проверяет отсечение контейнеров с недопустимыми именами процедур (`FA_SetProperty`, `FA_GetPropertX`).
7. `test_7_non_zero_padding_blocked`:
   Проверяет строгость контроля нулей в 12 байтах хвоста аргумента и 4 байтах выравнивания структуры.
8. `test_8_guard_called_before_usb_writefile`:
   Фиксирует строгое предшествование валидации Protocol Guard относительно любой попытки вызова Win32 `WriteFile`.
9. `test_9_guard_failure_prevents_writefile`:
   Гарантирует, что при ошибке валидации вызов `_write_raw_wire_bytes` (и Win32 `WriteFile`) **никогда не производится**.
10. `test_10_physical_io_enabled_cannot_be_enabled_by_user`:
    Подтверждает статус `PHYSICAL_IO_ENABLED = False` по умолчанию и генерацию исключения `RuntimeError` при попытке отправки.
11. `test_11_mock_full_three_property_readout_cycle`:
    Проверяет сквозное чтение трёх свойств через `MockPtpTransport` со сведением всех декодированных значений (Shutter: 60,689; Releases: 840,377; Power On: 5,984; Uptime: 3,392,007 c).

---

## 6. Инструкция для локального запуска тестов в PowerShell

Для независимой проверки на локальной машине с Python 3.10+ выполните следующие команды из корневого каталога проекта `D:\AI`:

### 6.1 Запуск нового набора тестов REV 3.1 (11 тестов)
```powershell
python -m unittest tests.test_phase_b_protected_transport.TestProtectedUsbPtpTransportPipeline -v
```

### 6.2 Запуск полного тестового пакета OpenEOS (67 тестов)
```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```
или через единый раннер:
```powershell
python tests/run_all_tests.py
```

### 6.3 Проверка байт-компиляции всех модулей
```powershell
python -m compileall openeos_ptp tests
```

---

## 7. Каталог синхронизированных файлов

Все файлы ревизии REV 3.1 синхронизированы в четырёх репозиторных средах:
1. Основная рабочая область: `d:/AI/`
2. Локальный пакет аудита: `d:/AI/ReviewBundle/`
3. Пользовательское зеркало: `C:/Users/and!m/OpenEOS/`
4. Зеркало пакета аудита: `C:/Users/and!m/OpenEOS/ReviewBundle/`
5. Облачное хранилище: Dropbox `/OpenEOS_Final_Verification/`

Перечень обновлённых компонентов:
- [openeos_ptp/payloads.py](file:///d:/AI/openeos_ptp/payloads.py) — добавлен `to_bytes`, проверка кратности параметров Command/Response.
- [openeos_ptp/protocol_guard.py](file:///d:/AI/openeos_ptp/protocol_guard.py) — усилена граница `validate_outgoing_container_bytes`, строгий контроль длин контейнеров.
- [openeos_ptp/transport.py](file:///d:/AI/openeos_ptp/transport.py) — внедрён сквозной пайплайн `Container -> Serialization -> Guard -> USB WriteFile`, метод `write_ptp_bytes`.
- [tests/test_phase_b_protected_transport.py](file:///d:/AI/tests/test_phase_b_protected_transport.py) — 11 новых unit-тестов REV 3.1.
- [tests/run_all_tests.py](file:///d:/AI/tests/run_all_tests.py) — объединённый запуск всех 67 тестов.

---

## 8. Неизвестные факторы и ограничения (UNKNOWN Items)

1. **Поведение Win32 `usbscan.sys` при физическом тайм-ауте на Windows 11**:
   На аппаратном уровне реальное время реакции Canon EOS R6 Mark II на команду `0x9052` составляет ~15-25 мс. В mock-тестах используется синхронный возврат данных. Реальное физическое поведение тайм-аутов драйвера `usbscan.sys` требует безопасного тестирования в Фазе C.
2. **Возможные различия ревизий прошивок R6 Mark II**:
   Спецификация и декодеры верифицированы по дампу прошивки v1.2.0/v1.3.0. Поведение на других версиях (v1.0.0 или новейших) должно верифицироваться с контролем длины opaque_tail.
3. **Авторизация перехода к Фазе C**:
   Фаза C (подключение к физической камере) остаётся **СТРОГО ЗАБЛОКИРОВАННОЙ** до получения отдельного прямого указания пользователя.
