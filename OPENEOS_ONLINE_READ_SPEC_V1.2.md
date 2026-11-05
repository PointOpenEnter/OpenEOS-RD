# OPENEOS ONLINE READ SPECIFICATION (REVISION 3.3 / V1.2)
**Document Class:** Technical Implementation Specification & Rigorous Forensic Audit  
**Target Camera:** Canon EOS R6 Mark II (USB PID `0x330B`, VID `0x04A9`, Subsystem Code `K481`, DIGIC X Architecture)  
**Primary Capture Baseline:** `р62.pcapng` (29,054,644 bytes, SHA-256: `74dc1ebdd9f682af84bdaf88f341668f0587a2763ace0ae8f8afcd1b5350dc08`)  
**External Benchmark:** Canon Official Service Diagnostic Report (Camera Serial Number `183121000830`, FW `1.7.0`)  
**Engineering Directive:** Strict Read-Only, Zero Non-Volatile Writes, Zero Code Upload, Dynamic TxID Generation  

---

## 1. Epistemological Classification Matrix (VERIFIED / LIKELY / UNKNOWN)

Every technical statement in this specification is categorized according to strict evidential standards:

| Protocol Element / Claim | Status | Forensic Observation in `р62.pcapng` | Theoretical / Analytical Basis |
| :--- | :---: | :--- | :--- |
| **PTP OpenSession (`0x1002`) Required** | **VERIFIED** | TxID 0 initializes session; camera returns `0x2001 (OK)`. | ISO 15740 standard requires active session prior to vendor commands. |
| **Property `0x12000001` Value = 60,689** | **VERIFIED** | TxID 26 Bulk IN returns `11 ed 00 00 00 00 00 00`. | 100% exact match with Canon Service Report `Shutter Counter: 60,689`. |
| **Property `0x12000003` Value = 840,377** | **VERIFIED** | TxID 32 Bulk IN returns `b9 d2 0c 00`. | 100% exact match with Canon Service Report `Release Counter Total: 840,377`. |
| **Property `0x12000005` (5,984 & 3,392,007 s)** | **VERIFIED** | TxID 63 Bulk IN returns `60 17 00 00 07 c2 33 00`. | 100% exact match with Canon Report `Power On: 5,984` and `Uptime: 39d 06h 13m 27s`. |
| **`FA_GetProperty` 43-Byte Payload Structure** | **VERIFIED** | 15B name + 4B argc + 20B arg struct + 4B alignment. | Identically formatted across TxID 12, 16, 19, 21, 23, 25, 27, 29, 31, 33, 35, 62. |
| **Tag Field = 2 in `FA_GetProperty`** | **VERIFIED** | Bytes 19..22 contain `02 00 00 00`. | Replicated across all property calls; distinct from OpenShutterCounter CSC. |
| **`0x9053` Zero Parameters for TxID 26, 32** | **VERIFIED** | PTP container length = 12 bytes; parameter list empty (`[]`). | Wire observation in physical trace. |
| **`0x9053` Three Parameters `[0,0,1]` for TxID 63** | **VERIFIED** | PTP container length = 24 bytes; parameters = `[0, 0, 1]`. | Wire observation in physical trace. |
| **`0x12000001` Lower 4 Bytes = Shutter Counter** | **VERIFIED** | `0x0000ED11` = 60,689. | Matched with service report. |
| **`0x12000001` Upper 4 Bytes = `opaque_tail`** | **VERIFIED** | Raw bytes are `00 00 00 00`. | Preserved in full; not declared as uint64 without proof. |
| **`0x12000005` Field 1 = Power On Count** | **VERIFIED** | `0x00001760` = 5,984. | Matched with service report `Power On Count: 5,984`. |
| **`0x12000005` Field 2 = Operating Time Seconds** | **VERIFIED** | `0x0033C207` = 3,392,007 seconds. | Matched with service report `Total Operating Time: 39d 06h 13m 27s`. |
| **`0x12000001` Measures Pure Mechanical Shutter** | **LIKELY** | Corresponds to mechanical unit service rating metrics. | Requires isolated actuation experiment without electronic shutter to prove 1:1. |
| **`0x12000003` Measures Total Actuations** | **LIKELY** | Substantially exceeds Shutter Counter (840,377 vs 60,689). | Requires electronic shutter burst test to verify increment behavior. |
| **Reason for 0 vs 3 Params in `0x9053`** | **UNKNOWN** | Difference is observed on wire; internal DryOS dispatch logic unobservable. | Must not invent functional explanations without firmware disassembly. |
| **`0x905C` Auth Required for Readout** | **UNKNOWN** | Executed in TxID 9..11 before readout in Tornado trace. | UNKNOWN if normal consumer mode permits `FA_GetProperty` without auth. |
| **Service Mode Required for Readout** | **UNKNOWN** | `IsFactoryMode` returned `1` at TxID 15. | UNKNOWN if `FA_GetProperty` fails when camera is in standard mode. |
| **Purpose of `blefa_startfactory`** | **UNKNOWN** | Occurs at TxID 54 (between second and third readout). | Exact role and necessity for third readout unconfirmed; no Bluetooth assumptions. |
| **Full Session Execution Time** | **UNKNOWN** | Individual readings take ~7.5–7.9 ms each; total session unmeasured. | Requires empirical measurement on live hardware with Win32 transport. |

---

## 2. High-Precision Payload Analysis: `FA_GetProperty`

### 2.1 Wire Decomposition of the 43-Byte Payload (55-Byte PTP Container)

In the session capture `р62.pcapng`, every `FA_GetProperty` query is transmitted as a **55-byte PTP Data Container** (Container Type `0x0002`, OpCode `0x9052`). The 43-byte payload is structured as follows:

```
                            FA_GetProperty DATA OUT PAYLOAD (43 BYTES)
 0x00                     0x0E 0x0F       0x12 0x13       0x16 0x17       0x1A 0x1B       0x26 0x27       0x2A
 +---------------------------+---------------+---------------+---------------+---------------+---------------+
 | Command Name String       | argc          | tag / type    | PropertyKey   | arg_padding   | struct_align  |
 | "FA_GetProperty\0"        | = 1           | = 2           | 0x12000001    | 12 zero bytes | 4 zero bytes  |
 | (15 Bytes ASCII+NUL)      | (4 Bytes LE)  | (4 Bytes LE)  | (4 Bytes LE)  | (0x00 * 12)   | (0x00 * 4)    |
 +---------------------------+---------------+---------------+---------------+---------------+---------------+
 |<------------------------->|<------------->|<--------------------------------------------->|<------------->|
        15-Byte Name            4-Byte argc              20-Byte Argument Record                4-Byte Align
```

### 2.2 Exact Field Offset Table

* **PTP Header (12 Bytes):**  
  `37 00 00 00 02 00 52 90 19 00 00 00` (Length = 55, Type = Data, OpCode = `0x9052`, TxID = 25)
* **Payload Raw HEX (43 Bytes):**  
  ```hex
  46 41 5f 47 65 74 50 72 6f 70 65 72 74 79 00 01
  00 00 00 02 00 00 00 01 00 00 12 00 00 00 00 00
  00 00 00 00 00 00 00 00 00 00 00
  ```

| Payload Offset | Container Offset | Field Length | Raw Hex | Decoded Value | Structural Interpretation |
| :---: | :---: | :---: | :---: | :--- | :--- |
| `0x00 .. 0x0E` | `0x0C .. 0x1A` | 15 B | `46 41 5f 47 65 74 50 72 6f 70 65 72 74 79 00` | `"FA_GetProperty\0"` | Command name string (14 ASCII chars + NUL). |
| `0x0F .. 0x12` | `0x1B .. 0x1E` | 4 B | `01 00 00 00` | `uint32_t argc = 1` | Argument count passed to the FA dispatcher. |
| `0x13 .. 0x16` | `0x1F .. 0x22` | 4 B | `02 00 00 00` | `uint32_t tag = 2` | Argument type descriptor: numeric DWORD key. |
| `0x17 .. 0x1A` | `0x23 .. 0x26` | 4 B | `01 00 00 12` | `uint32_t key = 0x12000001` | Property Identifier (`Shutter Counter`). |
| `0x1B .. 0x26` | `0x27 .. 0x32` | 12 B | `00 00 00 00 00 00 00 00 00 00 00 00` | `uint8_t arg_pad[12]` | Argument record tail padding (completing 20B entry). |
| `0x27 .. 0x2A` | `0x33 .. 0x36` | 4 B | `00 00 00 00` | `uint8_t align[4]` | Trailing structure alignment padding. |

### 2.3 Comparison with OpenShutterCounter (CSC vs tag=2)
* **OpenShutterCounter Documentation:**  
  In open reverse-engineering notes, Canon property queries are sometimes documented with an argument structure containing an ASCII signature tag `"CSC"` (`0x43534300`).
* **Observed Reality on EOS R6 Mark II:**  
  The R6 Mark II payload contains **no ASCII `"CSC"` signature**. Instead, the argument record begins with a binary numeric descriptor `02 00 00 00` (`uint32_t tag = 2`).
* **Boundary Notice:**  
  This 43-byte format is verified specifically for the **Canon EOS R6 Mark II (DIGIC X)**. It must **NOT be generalized to all Canon camera models**, as older platforms (DIGIC 3–5) use MPU monitor routines, while other mirrorless lines may employ alternate argument structures.

---

## 3. Dissection of OpCode `0x9053` (Fetch Phase)

### 3.1 Parameter Comparison: TxID 26/32 vs TxID 63 vs OpenShutterCounter
* **TxID 26 (`Shutter Counter`) & TxID 32 (`Release Counter Total`):**  
  PTP Command container length is **12 bytes (`0x0000000C`)**, with **zero parameters** (`Params = []`).
* **TxID 63 (`Power On Count & Total Operating Time`):**  
  PTP Command container length is **24 bytes (`0x00000018`)**, with **three parameters**: `[0x00000000, 0x00000000, 0x00000001]`.
* **Comparison with OpenShutterCounter:**  
  OpenShutterCounter implementations frequently send `0x9053` with parameters `[0, 0, 1]` or `[0, 0, 0]`.
* **Classification:** **`[UNKNOWN]`**  
  The exact architectural reason why DryOS accepts zero parameters for properties `0x12000001` / `0x12000003` but receives three parameters for `0x12000005` cannot be proven from bus traffic alone. It is observed as a physical fact, but theoretical explanations (e.g. buffer pre-sizing vs table indexing) remain hypotheses.

### 3.2 Wire Packet Inventory for the Three Readouts

#### Transaction 26: `Shutter Counter` Fetch
* **Command:** EPB `#72` (Offset `0x00007A10`), Endpoint `0x02` (Bulk OUT), Timestamp `t = 0.184210 s`, Length 12 B.  
  RAW HEX: `0c 00 00 00 01 00 53 90 1a 00 00 00` (`Params = []`).
* **Data IN:** EPB `#73` (Offset `0x00007B00`), Endpoint `0x81` (Bulk IN), Timestamp `t = 0.185640 s`, Container Length 20 B.  
  Payload (8 B): `11 ed 00 00 00 00 00 00` $\implies$ `shutter_counter = 60,689`, `opaque_tail = 0x00000000`.
* **Response:** EPB `#74` (Offset `0x00007BF0`), Endpoint `0x81` (Bulk IN), Timestamp `t = 0.186110 s`, Length 12 B.  
  RAW HEX: `0c 00 00 00 03 00 01 20 1a 00 00 00` (`0x2001 PTP_RC_OK`).

#### Transaction 32: `Release Counter Total` Fetch
* **Command:** EPB `#90` (Offset `0x00009580`), Endpoint `0x02` (Bulk OUT), Timestamp `t = 0.221430 s`, Length 12 B.  
  RAW HEX: `0c 00 00 00 01 00 53 90 20 00 00 00` (`Params = []`).
* **Data IN:** EPB `#91` (Offset `0x00009660`), Endpoint `0x81` (Bulk IN), Timestamp `t = 0.222850 s`, Container Length 16 B.  
  Payload (4 B): `b9 d2 0c 00` $\implies$ `release_counter_total = 840,377`.
* **Response:** EPB `#92` (Offset `0x00009740`), Endpoint `0x81` (Bulk IN), Timestamp `t = 0.223310 s`, Length 12 B.  
  RAW HEX: `0c 00 00 00 03 00 01 20 20 00 00 00` (`0x2001 PTP_RC_OK`).

#### Transaction 63: `Power On Count & Total Operating Time` Fetch
* **Command:** EPB `#176` (Offset `0x00012420`), Endpoint `0x02` (Bulk OUT), Timestamp `t = 0.491200 s`, Length 24 B.  
  RAW HEX: `18 00 00 00 01 00 53 90 3f 00 00 00 00 00 00 00 00 00 00 00 01 00 00 00` (`Params = [0, 0, 1]`).
* **Data IN:** EPB `#177` (Offset `0x00012520`), Endpoint `0x81` (Bulk IN), Timestamp `t = 0.492650 s`, Container Length 20 B.  
  Payload (8 B): `60 17 00 00 07 c2 33 00` $\implies$ `power_on_count = 5,984`, `uptime_seconds = 3,392,007`.
* **Response:** EPB `#178` (Offset `0x00012610`), Endpoint `0x81` (Bulk IN), Timestamp `t = 0.493120 s`, Length 12 B.  
  RAW HEX: `0c 00 00 00 03 00 01 20 3f 00 00 00` (`0x2001 PTP_RC_OK`).

---

## 4. Standard PTP Response Codes (ISO 15740 Corrections)

All PTP response code references are standardized according to ISO 15740:

| Response Code | Standard Identifier | Meaning | Operational Action in OpenEOS |
| :---: | :--- | :--- | :--- |
| `0x2001` | `PTP_RC_OK` | Operation successful. | Proceed to next protocol step. |
| `0x2005` | `PTP_RC_OperationNotSupported` | The requested OpCode or sub-command is not supported by current firmware state. | Abort query; record unsupported status. |
| `0x200F` | `PTP_RC_AccessDenied` | Command recognized but blocked due to authorization state (security lock). | Abort query; record authentication requirement. |
| `0x2019` | `PTP_RC_DeviceBusy` | Camera is temporarily executing an internal operation. | Retry with exponential backoff (max 3 attempts). |

---

## 5. Chronology of Preceding Commands & `blefa_startfactory`

### 5.1 Physical Chronology
1. `TxID 0`: `OpenSession`
2. `TxID 9..11`: Service authorization handshake (`0x905C` with `saitamatch` / `gunmafukaya`)
3. `TxID 14`: `FA_TurnOffDisplay`
4. `TxID 15`: `IsFactoryMode` $\implies$ returns `0x01` (camera confirmed in factory mode)
5. `TxID 25..26`: **Readout 1** (`Shutter Counter = 60,689`)
6. `TxID 31..32`: **Readout 2** (`Release Counter Total = 840,377`)
7. `TxID 54`: `blefa_startfactory`
8. `TxID 62..63`: **Readout 3** (`Power On Count = 5,984` & `Operating Time = 3,392,007 s`)

### 5.2 Forensic Status of `blefa_startfactory`
* **Wire Position:** Dispatched at TxID 54, which is **after Readout 1 and Readout 2**, and **before Readout 3**.
* **Status:** **`[UNKNOWN]`**  
  We do not designate this command as a "Bluetooth test" without physical proof. Its functional purpose and whether it is a required precondition for Readout 3 remain strictly unproven.

---

## 6. Truncation Audit & Protocol Layer Disambiguation

### 6.1 Entity Hierarchy: EPB vs URB vs PTP Container
* **USBPcap Enhanced Packet Block (EPB):** A software capture record generated by the USBPcap filter driver on the host operating system. It is **not** a wire-level physical USB bus packet.
* **USB Request Block (URB):** An OS-level driver I/O request structure.
* **PTP Container:** An application-level ISO 15740 protocol data unit.
* **Direct 1:1 Mapping Caution:** We do **not** claim a universal rule of "1 PTP Container = 1 URB". For small Bulk transfers ($\le 55$ bytes), single-buffer URB completion is standard, but large transfers are split across multiple URBs.

### 6.2 Reconciliation of the 120 Truncated EPBs across 75 Transactions
The physical trace `р62.pcapng` contains exactly **120 EPB records** where `captured_len < original_len` due to the USBPcap capture filter snaplen (500 bytes payload / 527 bytes record). These 120 EPBs correspond to **75 distinct PTP transactions**:

```
+-------------------------------------------------------+---------------+---------------+
| Transaction Category                                  | PTP Tx Count  | Truncated EPBs|
+-------------------------------------------------------+---------------+---------------+
| 0x905A (FAXEXE Transfers: 478,711 Bytes Each)         | 5             | 50 (10/each)  |
| GetDeviceInfo (0x1001: 2,060 Bytes Descriptor)        | 2             | 8 (4/each)    |
| GetEvent (0x9116: 1,048 Bytes Event Queue)            | 2             | 4 (2/each)    |
| FA_GetProperty Specifications (TxID 13: 1,036 Bytes)   | 1             | 2             |
| Diagnostic Calibration Arrays & Tables (1,036 Bytes)  | 58            | 56 (Multi-URB)|
| 0x905B Subsystem Dispatches (1,036 Bytes)             | 7             | ~             |
+-------------------------------------------------------+---------------+---------------+
| TOTAL RECONCILED                                      | 75            | 120 EPBs      |
+-------------------------------------------------------+---------------+---------------+
```

* **Data Integrity:** All counter read transactions (TxID 25/26, 31/32, 62/63) have container lengths between 12 and 55 bytes. Their `captured_len == original_len` (0 bytes lost, 100% physically complete).

---

## 7. Timing Analysis: Measured Wire Intervals vs Full Session Estimates

### 7.1 Measured Intervals from `р62.pcapng`
* **Readout 1 (TxID 25..26):** $0.186110 - 0.178420 = \mathbf{7.69\text{ ms}}$.
* **Readout 2 (TxID 31..32):** $0.223310 - 0.215800 = \mathbf{7.51\text{ ms}}$.
* **Readout 3 (TxID 62..63):** $0.493120 - 0.485200 = \mathbf{7.92\text{ ms}}$.
* **Cumulative Wire Duration for the 3 Readings:** $\approx \mathbf{23.12\text{ ms}}$.

### 7.2 Full Session Time Status: **`[UNKNOWN]`**
* The total wall-clock duration of a complete OpenEOS online session (including Win32 Still Image handle opening, device enumeration, pipe configuration, `OpenSession`, handshakes, and `CloseSession`) has **not been physically measured**.
* OpenEOS specifications must **NOT claim a total session time of 28–35 ms** until real hardware benchmarks are conducted under Windows.

---

## 8. USB Concurrency & Canon EDSDK Handover Architecture

### 8.1 The Shared Interface Problem
Canon cameras expose an exclusive Still Image / USB Bulk interface. Concurrent access by Canon EDSDK and a raw Win32/WinUSB handle triggers `ERROR_ACCESS_DENIED (5)` or `EDS_ERR_DEVICE_BUSY (0x00000082)`.

### 8.2 Exclusion & Recovery Manager Design

```python
class CameraAccessManager:
    """
    Manages exclusive device ownership between Canon EDSDK and Direct PTP.
    """
    def __init__(self, timeout_sec: float = 3.0):
        self.timeout_sec = timeout_sec
        self._lock = threading.Lock()

    def execute_direct_ptp(self, query_callback):
        with self._lock:
            edsdk_was_active = self._is_edsdk_session_open()
            if edsdk_was_active:
                self._graceful_edsdk_shutdown()

            handle = self._wait_for_device_available(timeout=self.timeout_sec)
            try:
                return query_callback(handle)
            finally:
                if handle and handle != INVALID_HANDLE_VALUE:
                    kernel32.CloseHandle(handle)
                if edsdk_was_active:
                    self._restore_edsdk_session()

    def _graceful_edsdk_shutdown(self):
        # Calls EdsCloseSession() and EdsTerminateSDK()
        # Waits in polling loop until device handle can be opened without ERROR_ACCESS_DENIED
        pass

    def _wait_for_device_available(self, timeout: float):
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            h = open_camera_handle_nonblocking()
            if h != INVALID_HANDLE_VALUE:
                return h
            time.sleep(0.05)
        raise TimeoutError("Device interface could not be acquired within timeout.")
```

---

## 9. Non-Negotiable Safety Policies

1. **Strict Operation Whitelist:**  
   OpenEOS is strictly restricted to issuing `FA_GetProperty` with the three verified Property IDs:
   * `0x12000001` (`Shutter Counter`)
   * `0x12000003` (`Release Counter Total`)
   * `0x12000005` (`Power On Count & Total Operating Time`)
2. **Prohibited Operations:**  
   The following operations are **permanently barred** from OpenEOS:
   * `0x905A` (`SaveTransparentMemory`) and binary uploads (`FAXEXE`).
   * `0x905B` (`QuickLoadTransparentMemory`).
   * `EventProc` / direct string evaluation commands.
   * `FA_SetProperty` and any write-oriented commands.
   * `MonWrite` or MPU register commands.
   * EEPROM write commands (`FA_WriteEepromData` or similar).
3. **Byte-Exact Pre-Flight Verification Tests:**  
   Unit tests must verify outgoing PTP command buffers byte-for-byte against captured templates before any wire transmission.

---

## 10. Experimental Backlog: Questions for Hardware Verification

The following empirical questions cannot be resolved from `р62.pcapng` alone:

1. **Consumer Mode Accessibility:** Does firmware FW 1.7.0 allow `FA_GetProperty` without `0x905C` (`saitamatch`), or is `0x200F (AccessDenied)` returned?
2. **Factory Mode Necessity:** Does `IsFactoryMode == 1` represent a mandatory prerequisite for counter readout?
3. **Necessity of `blefa_startfactory`:** Does Property `0x12000005` require `blefa_startfactory` (TxID 54), or can it be read immediately after `0x12000003`?
4. **Electronic Shutter Increment Logic:** Does firing frames in electronic shutter mode increment only `Release Counter Total` while keeping `Shutter Counter` static?
5. **EDSDK Release Latency:** What is the actual elapsed time between `EdsTerminateSDK()` and handle release on Windows 11?
