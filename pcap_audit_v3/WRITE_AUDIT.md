# FORENSIC WRITE & OUTGOING OPERATIONS AUDIT (REVISION 3)
**Target Capture:** `р62.pcapng` (29,054,644 bytes)  
**Target Device:** Canon EOS R6 Mark II (VID 0x04A9, PID 0x330B, FW 1.7.0, S/N 183121000830)  
**Investigation Standard:** Empirical Byte-Level Trace Analysis & Strict Evidential Boundary  

---

## 1. Executive Summary & Four-Tier Categorization Framework

The service session performed by the Tornado utility cannot be classified as "purely read-only". While no direct flash-programming commands were transmitted over USB Bulk OUT, Tornado actively altered the camera's operational state by:
- Engaging PC tethered remote-control mode;
- Activating asynchronous event messaging;
- Locking the hardware physical user interface (dials and buttons);
- Extinguishing the rear LCD and OLED viewfinder;
- Disabling the auto-sleep power management timer;
- Injecting a virtual playback keypress.

To maintain strict scientific objectivity and eliminate unverified assumptions, every outgoing operation in `р62.pcapng` is divided into four distinct functional categories:

1. **[READ]:** Non-modifying queries whose sole purpose is querying device descriptors, polling event queues, reading properties, or dumping memory tables (e.g., `GetDeviceInfo`, `GetEvent`, `FA_GetProperty`, `FA_ReadEepromData`, `0x9053` fetch).
2. **[VOLATILE_STATE_CHANGE]:** Operations that alter registers, display drivers, power timers, or UI locks in microcontroller RAM for the duration of the USB session.
3. **[POTENTIAL_FACTORY_WRITE]:** Destructive or persistent flash-programming routines (`FA_Write*`, `FA_SetProperty`, `FA_SetCalendar`, `MonWrite`, `MonCall`, `FA_TestMonReadAndWrite`). Exactly **zero (0)** instances of these patterns exist in `р62.pcapng`.
4. **[UNKNOWN_OPERATION]:** Vendor-proprietary authentication handshakes (`0x905C`) or factory dispatchers (`IsFactoryMode`) whose internal firmware side-effects cannot be proven without firmware reverse engineering.

---

## 2. Complete Inventory of Outgoing Operations & Re-calculated Lengths

In standard ISO 15740 PTP encapsulation over USB:
$$\text{PTP Container Length} = \text{Data Payload Length} + 12 \text{ bytes}$$

The table below presents the verified lengths, offsets, and classifications for all outgoing procedures:

| Step | TxID | OpCode | Procedure / Command | Container Length (bytes) | Payload Length (bytes) | Payload Hex Overview / ASCII String | Operational Category |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 2 | `0x1016` | `SetDevicePropValue(0xD406)` | 107 | 95 | `2f 57 00 69 00 6e ...` (`/Windows/10...`) | **VOLATILE_STATE_CHANGE** (Host OS ID) |
| 2 | 6 | `0x9114` | `SetRemoteMode(1)` | 16 (Cmd) | 0 (No Data) | Parameter 1 = `0x00000001` | **VOLATILE_STATE_CHANGE** (PC Remote Mode) |
| 3 | 7 | `0x9115` | `SetEventMode(1)` | 16 (Cmd) | 0 (No Data) | Parameter 1 = `0x00000001` | **VOLATILE_STATE_CHANGE** (Event Notification) |
| 4 | 8 | `0x9116` | `GetEvent(0,0,1)` | 24 (Cmd) | 0 (Data IN) | Parameters = `[0, 0, 1]` | **READ** (Event Queue Drain) |
| 5 | 9 | `0x905C` | Canon Service Auth Phase 1 | 67 | 55 | `"saitamatch\0"` + 32B + `"gunmafukaya\0"` | **UNKNOWN_OPERATION** (Handshake Step 1) |
| 6 | 10 | `0x905C` | Canon Service Auth Phase 2 | 51 | 39 | `"saitamatch\0"` + token `0x00071590` | **UNKNOWN_OPERATION** (Handshake Step 2) |
| 7 | 11 | `0x905C` | Canon Service Auth Phase 3 | 51 | 39 | `"saitamatch\0"` + token `0x00150AD3` | **UNKNOWN_OPERATION** (Handshake Step 3) |
| 8 | 12 | `0x9052` | `FA_GetProperty(0x00000002)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x00000002` | **READ** (Primary model info) |
| 9 | 14 | `0x9052` | `FA_TurnOffDisplay(0)` | 34 | 22 | `"FA_TurnOffDisplay\0"` + uint32(0) | **VOLATILE_STATE_CHANGE** (Display cut) |
| 10 | 15 | `0x9052` | `IsFactoryMode(0)` | 30 | 18 | `"IsFactoryMode\0"` + uint32(0) | **UNKNOWN_OPERATION** (Factory dispatch) |
| 11 | 16 | `0x9052` | `FA_GetProperty(0x0100001D)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x0100001D` | **READ** (Factory mode flags query) |
| 12 | 18 | `0x911B` | `SetUILock(1)` | 16 (Cmd) | 0 (No Data) | Parameter 1 = `0x00000001` | **VOLATILE_STATE_CHANGE** (Lock UI dials) |
| 13 | 19 | `0x9052` | `FA_GetProperty(0x01000006)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x01000006` | **READ** (Power state) |
| 14 | 21 | `0x9052` | `FA_GetProperty(0x02000005)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x02000005` | **READ** (Firmware build info) |
| 15 | 23 | `0x9052` | `FA_GetProperty(0x80030000)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x80030000` | **READ** (Sensor matrix descriptor) |
| 16 | 25 | `0x9052` | `FA_GetProperty(0x12000001)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x12000001` | **READ** (Mechanical shutter query) |
| 17 | 27 | `0x9052` | `FA_GetProperty(0x01000021)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x01000021` | **READ** (Diagnostic table 1) |
| 18 | 29 | `0x9052` | `FA_GetProperty(0x01000021)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x01000021` | **READ** (Diagnostic table 2) |
| 19 | 31 | `0x9052` | `FA_GetProperty(0x12000003)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x12000003` | **READ** (Total releases query) |
| 20 | 33 | `0x9052` | `FA_GetProperty(0x13000000)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x13000000` | **READ** (Error incident log query) |
| 21 | 35 | `0x9052` | `FA_GetProperty(0x01000002)` | 55 | 43 | `"FA_GetProperty\0"` + Key `0x01000002` | **READ** (Mainboard serial query) |
| 22 | 37 | `0x9052` | `cc_cmd_playbtn_on(0)` | 34 | 22 | `"cc_cmd_playbtn_on\0"` + uint32(0) | **VOLATILE_STATE_CHANGE** (Virtual keypress) |
| 23 | 38 | `0x9052` | `DisablePowerSave(...)` | 57 | 45 | `"DisablePowerSave\0"` + 28B args | **VOLATILE_STATE_CHANGE** (Mask sleep timer) |
| 24 | 39+ | `0x9052` | `FA_ReadEepromData(...)` | 58 | 46 | `"FA_ReadEepromData\0"` + offset/len | **READ** (Diagnostic EEPROM dump) |

---

## 3. Storage Safety & Dangerous Procedure Audit

To ensure no unauthorized persistent changes occurred, the entire byte payload of all outgoing Bulk OUT transfers was audited against dangerous Canon factory commands:

| Target Search Pattern | Intended / Dangerous Operation | Matches in `р62.pcapng` | Audit Status |
|---|---|:---:|:---:|
| `b"FA_Write"` | EEPROM / Flash write procedures (`FA_WriteEepromData`, etc.) | **0** | PASSED (Clean) |
| `b"FA_SetProperty"` | Persistent factory property modification | **0** | PASSED (Clean) |
| `b"FA_SetCalendar"` | Hardware RTC clock / calendar reprogramming | **0** | PASSED (Clean) |
| `b"MonWrite"` | Low-level memory monitor / register write | **0** | PASSED (Clean) |
| `b"MonCall"` | Direct routine execution / code injection in RAM/ROM | **0** | PASSED (Clean) |
| `b"FA_TestMonReadAndWrite"`| Factory bidirectional bus test write cycle | **0** | PASSED (Clean) |
| `0x100D` (PTP OpCode) | Standard PTP SetObjectPropValue | **0** | PASSED (Clean) |
| `0x1016` (PTP OpCode) | Standard PTP SetDevicePropValue (used only for Host OS ID) | **1** | PASSED (Volatile OS ID) |

**Conclusion on User-Level Write Commands:**  
Direct user-level non-volatile memory write commands: **EXACTLY ZERO (0)**.

---

## 4. Dissection of the Factory Security Handshake (TxID 9, 10, 11)

A critical forensic finding in `р62.pcapng` concerns the exact token placement in OpCode `0x905C` (Service Authentication):

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
  * **Finding:** TxID 11 also contains `"saitamatch"`, NOT `"gunmafukaya"`.

---

## 5. Strict Decoupling of `IsFactoryMode` (TxID 15) and `FA_GetProperty` (TxID 16/17)

In earlier community discussions, the 80-byte result retrieved in TxID 17 was conflated with procedure `IsFactoryMode` (TxID 15). The byte-level sequence demonstrates that they are two distinct, independent operations:

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

## 6. Storage Non-Volatility & Forensic Boundaries of Safety

### A. What is Empirically Proven from the Capture:
* Throughout all 24,379 USB packets in `р62.pcapng`, there is **zero (0) execution** of explicit non-volatile programming commands (`FA_WriteEepromData`, `FA_WriteEepromBlock`, `WriteMemory`, `WriteDevicePropValue`).
* All EEPROM operations present in the capture (`FA_ReadEepromData`, TxID 39 through 3,218) are **read queries** accompanied by Bulk IN transfers from camera to host.

### B. What CANNOT Be Proven Without Firmware Disassembly (The Scientific Boundary):
* It is scientifically unsound to claim "100% EEPROM safety" or "safe_read_only" solely from sniffing USB traffic.
* Certain opaque procedures (such as `IsFactoryMode` in TxID 15 or `DisablePowerSave` in TxID 38) could, in principle, cause the camera's internal DryOS firmware to write diagnostic reboot flags, power-fail counters, or error timestamps into internal EEPROM or SPI Flash.
* Without performing a bitwise diff of the camera's EEPROM before and after the session, or disassembling the camera's internal `FA_Task` firmware, the presence or absence of background firmware-triggered EEPROM writes remains strictly **UNVERIFIED**.
* **Forensic Statement:** Direct user-level EEPROM write commands were NOT issued; however, absolute zero non-volatile side-effects cannot be mathematically proven from USB capture alone.
