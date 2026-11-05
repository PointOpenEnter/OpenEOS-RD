# FORENSIC WRITE & OUTGOING OPERATIONS AUDIT (REVISION 2)
**Target Capture:** `р62.pcapng` (29,054,644 bytes)  
**Target Device:** Canon EOS R6 Mark II (VID 0x04A9, PID 0x330B, FW 1.7.0)  
**Investigation Standard:** Empirical Byte-Level Trace Analysis  

---

## 1. Executive Summary & Categorization Framework

The session performed by the Tornado utility cannot be classified as "purely read-only". While no direct flash-programming commands were transmitted over USB Bulk OUT, Tornado actively altered the camera's operational state by:
- Engaging remote-control mode;
- Activating asynchronous event messaging;
- Locking the hardware physical user interface (dials and buttons);
- Extinguishing the rear LCD and OLED viewfinder;
- Disabling the auto-sleep power management timer;
- Injecting a virtual playback keypress.

To maintain strict scientific objectivity, every outgoing operation in `р62.pcapng` is divided into three distinct functional categories:
1. **[READ QUERIES] (Чтение данных):** Operations whose sole purpose is querying properties, polling event queues, or dumping memory tables without modifying operational state.
2. **[VOLATILE STATE MODIFICATIONS] (Изменение временного состояния камеры):** Operations that alter registers, display drivers, power timers, or UI locks in microcontroller RAM.
3. **[UNKNOWN / OPAQUE OPERATIONS] (Неизвестные / неверифицированные процедуры):** Vendor-proprietary authentication routines or factory mode dispatchers whose internal firmware side-effects cannot be proven without firmware reverse engineering.

---

## 2. Complete Inventory of Outgoing Operations & Re-calculated Lengths

Every PTP transaction with a Data OUT phase carries a 12-byte PTP container header:
$$\text{PTP Container Length} = \text{Data Payload Length} + 12 \text{ bytes}$$

The table below presents the verified lengths and classification for all outgoing procedures:

| Step | TxID | OpCode | Procedure / Command | Container Length (bytes) | Payload Length (bytes) | Payload Hex Overview / ASCII String | Operational Category |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 2 | `0x1016` | `SetDevicePropValue(0xD406)` | 107 | 95 | `2f 57 00 69 00 6e ...` (`/Windows/10...`) | **Volatile State Modification** (Host OS ID) |
| 2 | 6 | `0x9114` | `SetRemoteMode(1)` | 16 (Cmd) | 0 (No Data) | Parameter 1 = `0x00000001` | **Volatile State Modification** (PC Remote Mode) |
| 3 | 7 | `0x9115` | `SetEventMode(1)` | 16 (Cmd) | 0 (No Data) | Parameter 1 = `0x00000001` | **Volatile State Modification** (Event Notification) |
| 4 | 8 | `0x9116` | `GetEvent(0,0,1)` | 24 (Cmd) | 0 (Data IN) | Parameters = `[0, 0, 1]` | **Read Query / Event Queue Drain** |
| 5 | 9 | `0x905C` | Canon Service Auth Phase 1 | 67 | 55 | `"saitamatch\0"` + 32B + `"gunmafukaya\0"` | **Unknown / Opaque Operation** (Handshake Step 1) |
| 6 | 10 | `0x905C` | Canon Service Auth Phase 2 | 51 | 39 | `"saitamatch\0"` + token `0x00071590` | **Unknown / Opaque Operation** (Handshake Step 2) |
| 7 | 11 | `0x905C` | Canon Service Auth Phase 3 | 51 | 39 | `"saitamatch\0"` + token `0x00150AD3` | **Unknown / Opaque Operation** (Handshake Step 3) |
| 8 | 12 | `0x9052` | `FA_GetProperty(0x00000002)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x00000002` | **Read Query** (Prime model info) |
| 9 | 14 | `0x9052` | `FA_TurnOffDisplay(0)` | 34 | 22 | `"FA_TurnOffDisplay\0"` + uint32(0) | **Volatile State Modification** (Display cut) |
| 10 | 15 | `0x9052` | `IsFactoryMode(0)` | 30 | 18 | `"IsFactoryMode\0"` + uint32(0) | **Unknown / Opaque Operation** (Factory dispatch) |
| 11 | 16 | `0x9052` | `FA_GetProperty(0x0100001D)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x0100001D` | **Read Query** (Factory mode flags query) |
| 12 | 18 | `0x911B` | `SetUILock(1)` | 16 (Cmd) | 0 (No Data) | Parameter 1 = `0x00000001` | **Volatile State Modification** (Lock UI dials) |
| 13 | 19 | `0x9052` | `FA_GetProperty(0x01000006)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x01000006` | **Read Query** (Power state) |
| 14 | 21 | `0x9052` | `FA_GetProperty(0x02000005)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x02000005` | **Read Query** (Firmware build info) |
| 15 | 23 | `0x9052` | `FA_GetProperty(0x80030000)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x80030000` | **Read Query** (Sensor matrix descriptor) |
| 16 | 25 | `0x9052` | `FA_GetProperty(0x12000001)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x12000001` | **Read Query** (Mechanical shutter query) |
| 17 | 27 | `0x9052` | `FA_GetProperty(0x01000021)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x01000021` | **Read Query** (Diagnostic table 1) |
| 18 | 29 | `0x9052` | `FA_GetProperty(0x01000021)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x01000021` | **Read Query** (Diagnostic table 2) |
| 19 | 31 | `0x9052` | `FA_GetProperty(0x12000003)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x12000003` | **Read Query** (Total releases query) |
| 20 | 33 | `0x9052` | `FA_GetProperty(0x13000000)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x13000000` | **Read Query** (Error incident log query) |
| 21 | 35 | `0x9052` | `FA_GetProperty(0x01000002)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x01000002` | **Read Query** (Mainboard serial query) |
| 22 | 37 | `0x9052` | `cc_cmd_playbtn_on(0)` | 34 | 22 | `"cc_cmd_playbtn_on\0"` + uint32(0) | **Volatile State Modification** (Virtual keypress) |
| 23 | 38 | `0x9052` | `DisablePowerSave(1,2,0...)` | 57 | 45 | `"DisablePowerSave\0"` + 28B args | **Volatile State Modification** (Mask sleep timer) |
| 24 | 39+ | `0x9052` | `FA_ReadEepromData(...)` | 58 | 46 | `"FA_ReadEepromData\0"` + offset/len | **Read Query** (Diagnostic EEPROM dump) |

---

## 3. Dissection of the Factory Security Handshake (TxID 9, 10, 11)

A critical correction to previous reports concerns the exact token placement in OpCode `0x905C`:

### Transaction 9: Handshake Phase 1
* **Command:** Container Length = 12 bytes (`0x0C`), OpCode = `0x905C`, TxID = 9, Params = [].
* **Data OUT:**
  * PTP Container Length: **67 bytes** (`0x00000043`).
  * Payload Length: **55 bytes** (`0x37`).
  * Payload Hex:
    `73 61 69 74 61 6d 61 74 63 68 00 01 00 00 00 04 00 00 00 00 00 00 00 00 00 00 00 01 00 00 00 0c 00 00 00 01 00 00 00 01 00 00 00 67 75 6e 6d 61 66 75 6b 61 79 61 00`
  * Byte Breakdown:
    * `bytes[0..10]`: `"saitamatch\0"` (11 ASCII bytes, Saitama factory passkey).
    * `uint32[0..7]`: `[1, 4, 0, 0, 1, 12, 1, 1]` (32 binary bytes).
    * `bytes[43..54]`: `"gunmafukaya\0"` (12 ASCII bytes, Gunma/Fukaya manufacturing plant token).
  * **Finding:** TxID 9 contains **BOTH** `"saitamatch"` and `"gunmafukaya"` within a single payload.

### Transaction 10: Handshake Phase 2
* **Command:** Container Length = 12 bytes, OpCode = `0x905C`, TxID = 10, Params = [].
* **Data OUT:**
  * PTP Container Length: **51 bytes** (`0x00000033`).
  * Payload Length: **39 bytes** (`0x27`).
  * Payload Hex:
    `73 61 69 74 61 6d 61 74 63 68 00 01 00 00 00 02 00 00 00 90 15 07 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00`
  * Byte Breakdown:
    * `bytes[0..10]`: `"saitamatch\0"` (11 ASCII bytes).
    * `uint32[0]`: 1.
    * `uint32[1]`: 2.
    * `uint32[2]`: `0x00071590` (464,272).
    * `uint32[3..6]`: 16 zero padding bytes.
  * **Finding:** TxID 10 contains `"saitamatch"`, NOT `"gunmafukaya"`.

### Transaction 11: Handshake Phase 3
* **Command:** Container Length = 12 bytes, OpCode = `0x905C`, TxID = 11, Params = [].
* **Data OUT:**
  * PTP Container Length: **51 bytes** (`0x00000033`).
  * Payload Length: **39 bytes** (`0x27`).
  * Payload Hex:
    `73 61 69 74 61 6d 61 74 63 68 00 01 00 00 00 02 00 00 00 d3 0a 15 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00`
  * Byte Breakdown:
    * `bytes[0..10]`: `"saitamatch\0"` (11 ASCII bytes).
    * `uint32[0]`: 1.
    * `uint32[1]`: 2.
    * `uint32[2]`: `0x00150AD3` (1,379,027).
    * `uint32[3..6]`: 16 zero padding bytes.
  * **Finding:** TxID 11 also contains `"saitamatch"`, NOT `"gunmafukaya"`. The earlier draft erroneously labeled TxID 11 as `"gunmafukaya"`.

---

## 4. Strict Decoupling of `IsFactoryMode` (TxID 15) and `FA_GetProperty` (TxID 16/17)

In previous drafts, the 80-byte result retrieved in TxID 17 was conflated with procedure `IsFactoryMode` (TxID 15). The byte-level sequence demonstrates that they are two distinct, independent operations:

1. **Transaction 15 (`IsFactoryMode` Dispatch):**
   * Command: `0x9052` (Params: `[0, 0]`).
   * Data OUT: Container = 30 bytes, Payload = 18 bytes (`"IsFactoryMode\0"` + uint32(0)).
   * Response: Container = 12 bytes (`ResponseCode = 0x2001` OK).
   * **Crucial Fact:** TxID 15 concludes immediately after the camera sends Response `0x2001`. It carries **no Data IN phase** and returns no payload bytes to the host.
2. **Transaction 16 (`FA_GetProperty` Query):**
   * Command: `0x9052` (Params: `[0, 1]`).
   * Data OUT: Container = 55 bytes, Payload = 43 bytes (`"FA_GetProperty\0"` with Property Key `0x0100001D`).
   * Response: Container = 16 bytes (`ResponseCode = 0x2001` OK, `Param1 = 0x00000050` = 80 bytes).
3. **Transaction 17 (`0x9053` Fetch):**
   * Command: `0x9053` (Params: `[0, 0, 1]`).
   * Data IN: Container = 92 bytes (12 bytes header + 80 bytes payload: `00 00 00 00 ... ff ff ff ff`).
   * Response: Container = 12 bytes (`ResponseCode = 0x2001` OK).
   * **Finding:** The 80 bytes returned in TxID 17 are the payload of Property `0x0100001D` (Factory Configuration Descriptor), NOT the return value of `IsFactoryMode`.

---

## 5. Storage Non-Volatility & Forensic Boundaries of Safety

### A. What is Empirically Proven from the Capture:
* Throughout all 24,379 USB packets in `р62.pcapng`, there is **zero (0) execution** of explicit non-volatile programming commands (`FA_WriteEepromData`, `FA_WriteEepromBlock`, `WriteMemory`, `WriteDevicePropValue`).
* All EEPROM operations present in the capture (`FA_ReadEepromData`, TxID 39 through 3,218) are **read queries** accompanied by Bulk IN transfers from camera to host.

### B. What CANNOT Be Proven Without Firmware Disassembly:
* It is scientifically impossible to claim "100% EEPROM safety" solely from sniffing USB traffic.
* Certain opaque procedures (such as `IsFactoryMode` in TxID 15 or `DisablePowerSave` in TxID 38) could, in principle, cause the camera's internal DryOS firmware to write diagnostic reboot flags, power-fail counters, or error timestamps into internal EEPROM or SPI Flash.
* Without performing a bitwise diff of the camera's EEPROM before and after the session, or disassembling the camera's internal `FA_Task` firmware, the presence or absence of background firmware-triggered EEPROM writes remains **UNVERIFIED**.
* **Forensic Statement:** Direct user-level EEPROM write commands were NOT issued; however, absolute zero non-volatile side-effects cannot be mathematically proven from USB capture alone.
