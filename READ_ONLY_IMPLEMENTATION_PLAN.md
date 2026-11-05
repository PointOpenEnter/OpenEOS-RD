# OPENEOS READ-ONLY IMPLEMENTATION PLAN
**Document Class:** Engineering Implementation Roadmap & Safety Protocol  
**Target Platform:** Canon EOS R6 Mark II (DIGIC X, VID `0x04A9`, PID `0x330B`, Subsystem `K481`, FW `1.7.0`)  
**Specification Reference:** `OPENEOS_ONLINE_READ_SPEC_V1.2.md`  
**Capture Reference:** `р62.pcapng` (SHA-256: `74dc1ebdd9f682af84bdaf88f341668f0587a2763ace0ae8f8afcd1b5350dc08`)  
**Strict Directives:** Read-Only Operation, Zero Non-Volatile Memory Modifications, No Hardware Connection in Current Turn  

---

## 1. Overview and Architecture Principles

The goal of this implementation plan is to transition the forensically verified readout mechanics discovered in `р62.pcapng` into a production-grade, fail-safe read-only diagnostic module for OpenEOS.

### Core Engineering Invariants:
1. **Safety First:** Absolute prohibition of `0x905A` (code upload), `0x905B`, `EventProc`, `FA_SetProperty`, and any EEPROM/Flash write commands.
2. **Dynamic Session Identifiers:** Dynamic generation of `TransactionID` ($0, 1, 2, \dots$) and `SessionID`; static hardcoded capture IDs are strictly barred.
3. **Epistemic Discipline:** Every module, test, and routine is classified by evidential certainty:
   - **`[VERIFIED]`**: Fully proven from bit-level wire capture (`р62.pcapng`) and corroborated by Canon Service Report.
   - **`[LIKELY]`**: Functionally consistent with camera behavior and architecture, pending isolated actuation verification.
   - **`[UNKNOWN]`**: Black-box behavior or unmeasured parameters requiring controlled hardware discovery.

---

## 2. Four-Phase Implementation Roadmap

```
+-----------------------------------------------------------------------------------+
| PHASE A: Offline Parser & Byte-Exact Unit Tests [VERIFIED]                        |
| - Wire-exact PTP container synthesizers (TxID 25, 31, 62)                         |
| - Binary response decoders (TxID 26, 32, 63) against PCAP templates              |
| - ISO 15740 response code handling and mock transport state machine               |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| PHASE B: USB/PTP Transport Harness without Camera Commands [VERIFIED]             |
| - Win32 SetupAPI / WinUSB device enumeration (VID 0x04A9, PID 0x330B)             |
| - Endpoint binding (Bulk OUT 0x02, Bulk IN 0x81, Interrupt 0x83)                  |
| - CameraAccessManager EDSDK coexistence and graceful mutex handover               |
| - Whitelist-enforced transport firewall (blocks all non-whitelisted OpCodes)     |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| PHASE C: Controlled Readout of Confirmed Properties [LIKELY]                      |
| - Sequence execution: OpenSession -> Read 0x12000001 -> Read 0x12000003 ->       |
|   Read 0x12000005 -> CloseSession                                                 |
| - Parameterization harness: 0 params (TxID 26/32) vs [0,0,1] (TxID 63)            |
| - Atomic fail-safe abort on 0x2005 (Unsupported) or 0x200F (AccessDenied)         |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| PHASE D: Subsequent Diagnostic Expansion [UNKNOWN]                                |
| - Experimental isolation of blefa_startfactory and prerequisite checks            |
| - Exploration of error log tables, temperature sensors, battery telemetry         |
| - Mechanical vs Electronic actuation increment validation                         |
+-----------------------------------------------------------------------------------+
```

---

## 3. Phase A: Offline Parser & Byte-Exact Unit Tests

**Evidential Status:** `[VERIFIED]`  
**Hardware Requirement:** None (100% offline, purely programmatic).

### 3.1 Task A.1: Outbound PTP Payload Builder
* **Requirement:** Construct outgoing `FA_GetProperty` 55-byte PTP containers ($12\text{B Header} + 43\text{B Payload}$).
* **Byte Layout Verification:**
  - `0x00..0x03`: Container Length = `0x00000037` (55 bytes).
  - `0x04..0x05`: Container Type = `0x0002` (Data Container).
  - `0x06..0x07`: OpCode = `0x9052`.
  - `0x08..0x0B`: Transaction ID (dynamically assigned).
  - `0x0C..0x1A`: ASCII Command Name = `FA_GetProperty\0` (15 bytes).
  - `0x1B..0x1E`: `argc = 1` (`0x00000001`).
  - `0x1F..0x22`: `tag = 2` (`0x00000002`).
  - `0x23..0x26`: `PropertyKey` (e.g. `0x12000001`, `0x12000003`, `0x12000005`).
  - `0x27..0x32`: 12 zero padding bytes (`0x00` * 12).
  - `0x33..0x36`: 4 zero alignment bytes (`0x00` * 4).
* **Unit Test:** `test_fa_get_property_builder()`  
  Must match wire bytes from `р62.pcapng` TxID 25 (EPB #70), TxID 31 (EPB #88), and TxID 62 (EPB #174) with 100% byte-for-byte fidelity (excluding dynamic TxID).

### 3.2 Task A.2: Inbound Data Decoders
* **Task A.2.1: Shutter Counter Decoder (`0x12000001`)**
  - Input: 8 bytes (`11 ed 00 00 00 00 00 00`).
  - Extraction: `shutter_counter = unpack('<I', payload[0:4])[0]` $\implies 60,689$.
  - Verification: `opaque_tail = payload[4:8]` preserved as raw binary.
* **Task A.2.2: Release Counter Total Decoder (`0x12000003`)**
  - Input: 4 bytes (`b9 d2 0c 00`).
  - Extraction: `release_total = unpack('<I', payload[0:4])[0]` $\implies 840,377$.
* **Task A.2.3: Power On & Operating Time Decoder (`0x12000005`)**
  - Input: 8 bytes (`60 17 00 00 07 c2 33 00`).
  - Extraction:
    - `power_on_count = unpack('<I', payload[0:4])[0]` $\implies 5,984$.
    - `uptime_seconds = unpack('<I', payload[4:8])[0]` $\implies 3,392,007$ s ($39\text{d } 06\text{h } 13\text{m } 27\text{s}$).
* **Unit Test:** `test_counter_decoders()` validates extracted numbers against official Canon Service Report benchmarks.

### 3.3 Task A.3: Response Code State Machine & Mock Transport
* Implement ISO 15740 response evaluator:
  - `0x2001 (PTP_RC_OK)`: Transition to next state.
  - `0x2005 (PTP_RC_OperationNotSupported)`: Abort with `UnsupportedOperationException`.
  - `0x200F (PTP_RC_AccessDenied)`: Abort with `AuthenticationRequiredException`.
  - `0x2019 (PTP_RC_DeviceBusy)`: Trigger retry handler with exponential backoff.
* Mock test validates that illegal OpCodes or unexpected camera responses safely terminate the pipeline without exceptions leaking or hanging.

---

## 4. Phase B: USB/PTP Transport Harness without Camera Commands

**Evidential Status:** `[VERIFIED]`  
**Hardware Requirement:** Camera connected via USB, but **ZERO camera-specific commands dispatched** (device handle & endpoint inspection only).

### 4.1 Task B.1: Device Enumeration & Descriptor Parsing
* Locate Canon Still Image devices via Win32 SetupAPI using GUID `{6AC27878-A6FA-4125-BA57-F98F7A78810E}`.
* Filter for Canon VID `0x04A9` and R6 Mark II PID `0x330B`.
* Verify endpoint configuration:
  - Pipe 0: Endpoint `0x02` (Bulk OUT, wMaxPacketSize = 512 / 1024 bytes).
  - Pipe 1: Endpoint `0x81` (Bulk IN, wMaxPacketSize = 512 / 1024 bytes).
  - Pipe 2: Endpoint `0x83` (Interrupt IN, wMaxPacketSize = 64 bytes).

### 4.2 Task B.2: EDSDK Mutex & Coexistence Manager (`CameraAccessManager`)
* **Problem:** Canon EDSDK holds exclusive handle ownership; concurrent Win32 file access fails with `ERROR_ACCESS_DENIED (5)`.
* **Implementation:**
  1. Detect if EDSDK is initialized in process memory.
  2. If active, issue `EdsCloseSession()` followed by `EdsTerminateSDK()`.
  3. Enter polling loop attempting non-blocking `CreateFileW` with `FILE_FLAG_OVERLAPPED` and `OPEN_EXISTING`.
  4. Timeout after 3.0 seconds if interface remains locked.
  5. Enforce Python `try...finally` block ensuring handle `CloseHandle()` is called even upon unhandled exceptions before restoring EDSDK.

### 4.3 Task B.3: Protocol Transport Firewall
* Hardcode outgoing OpCode whitelist at the physical transport layer:
  ```python
  ALLOWED_OPCODES = {
      0x1002: "OpenSession",
      0x1003: "CloseSession",
      0x9052: "FA_Command",
      0x9053: "FA_Fetch"
  }
  ```
* Any call attempting to send OpCode `0x905A`, `0x905B`, `0x9028`, or any unlisted OpCode throws a fatal `SecurityViolationError` before touching the USB driver.

---

## 5. Phase C: Controlled Readout of Confirmed Properties

**Evidential Status:** `[LIKELY]`  
**Hardware Requirement:** Live Canon EOS R6 Mark II (strictly after Phase A and Phase B achieve 100% test pass).

### 5.1 Task C.1: Session Initialization
1. Dynamically generate `SessionID = 1`.
2. Dispatch `OpenSession (0x1002)` with TxID 1.
3. Validate Response is `0x2001 (PTP_RC_OK)`.

### 5.2 Task C.2: Step-by-Step Property Readout
* **Step 1: Read Shutter Counter (`0x12000001`)**
  - Dispatch `FA_GetProperty` (OpCode `0x9052`, TxID $N$, Params `[0, 1]`, Payload 43B).
  - Await Response `0x2001` (Params `[0x00000008]`).
  - Dispatch Fetch (OpCode `0x9053`, TxID $N+1$, **Params `[]`**).
  - Read Bulk IN (8 bytes) + Response `0x2001`.
  - Extract and verify Shutter Counter.
* **Step 2: Read Release Counter Total (`0x12000003`)**
  - Dispatch `FA_GetProperty` (OpCode `0x9052`, TxID $N+2$, Params `[0, 1]`, Payload 43B).
  - Await Response `0x2001` (Params `[0x00000004]`).
  - Dispatch Fetch (OpCode `0x9053`, TxID $N+3$, **Params `[]`**).
  - Read Bulk IN (4 bytes) + Response `0x2001`.
  - Extract and verify Release Counter Total.
* **Step 3: Read Power On Count & Operating Time (`0x12000005`)**
  - Dispatch `FA_GetProperty` (OpCode `0x9052`, TxID $N+4$, Params `[0, 1]`, Payload 43B).
  - Await Response `0x2001` (Params `[0x00000008]`).
  - Dispatch Fetch (OpCode `0x9053`, TxID $N+5$, **Params `[0, 0, 1]`**).
  - Read Bulk IN (8 bytes) + Response `0x2001`.
  - Extract and verify Power On Count and Operating Time.

### 5.3 Task C.3: Clean Session Teardown
1. Dispatch `CloseSession (0x1003)` with TxID $N+6$.
2. Close USB pipe handles.
3. Notify `CameraAccessManager` that transport is released.

---

## 6. Phase D: Subsequent Diagnostic Expansion

**Evidential Status:** `[UNKNOWN]`  
**Prerequisite:** Full operational success of Phase C.

### 6.1 Task D.1: Authorization & Factory Mode Dependency Investigation
* Test whether `FA_GetProperty` succeeds without preceding `0x905C` handshake.
* If camera responds `0x200F (AccessDenied)`, evaluate safe read-only authorization sequence.

### 6.2 Task D.2: Investigation of `blefa_startfactory`
* Determine if Property `0x12000005` can be retrieved without issuing `blefa_startfactory` (TxID 54).
* If required, analyze minimal read-only preconditions.

### 6.3 Task D.3: Mechanical vs Electronic Actuation Verification
* Perform controlled experimental test: take 5 single mechanical exposures vs 50 electronic silent burst exposures.
* Confirm whether `0x12000001` increments solely on mechanical cycles, while `0x12000003` increments on all exposures.

---

## 7. Safety Validation & Pass/Fail Criteria Matrix

| Checkpoint | Pass Criteria | Fail Action | Evidential Tier |
| :--- | :--- | :--- | :---: |
| **A. Unit Test Payload Match** | Outgoing bytes 100% identical to PCAPNG templates (TxID 25/31/62). | Halt build; refuse transport execution. | `[VERIFIED]` |
| **B. Whitelist Enforcement** | Non-whitelisted OpCodes trigger immediate internal exception. | Abort execution; lock interface. | `[VERIFIED]` |
| **C. EDSDK Mutex Check** | Device handle acquired without `ERROR_ACCESS_DENIED`. | Abort with timeout message; release mutex. | `[VERIFIED]` |
| **D. Inbound Response Code** | Camera returns `0x2001 (PTP_RC_OK)`. | If `0x2005` or `0x200F`, log and gracefully disconnect. | `[VERIFIED]` |
| **E. Data Length Check** | Inbound payload length matches expected (8B / 4B / 8B). | Reject payload; issue warning; close session. | `[VERIFIED]` |
| **F. Actuation Logic Check** | `Shutter Counter <= Release Counter Total`. | Flag anomaly in diagnostic report. | `[LIKELY]` |
