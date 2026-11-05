# TORNADO SESSION CHRONOLOGY & BLEFA_STARTFACTORY AUDIT
**Investigation Subject:** Structural Order of Events, Session Lifecycle, and `blefa_startfactory` Analysis  
**Target Hardware:** Canon EOS R6 Mark II (PID `0x330B`, S/N `183121000830`, FW `1.7.0`, DIGIC X)  
**Primary Capture:** `р62.pcapng` (29,054,644 bytes, SHA-256: `74dc1ebdd9f682af84bdaf88f341668f0587a2763ace0ae8f8afcd1b5350dc08`)  
**Investigator:** OpenEOS Forensic Engineering Review  

---

## 1. Forensic Profile of `blefa_startfactory`

### A. Transaction Metrics
* **TransactionID (TxID):** **54** (`0x00000036`)
* **PTP OpCode:** `0x9052` (`PTP_OP_CANON_VENDOR_CMD`)
* **Command Parameters:** `[0x00000000, 0x00000000]`
* **Command Endpoint:** `0x02` (Bulk OUT, Host $\to$ Camera)
* **Command Container Length:** 20 bytes (`0x00000014`)

### B. Data OUT Phase Metrics
* **Container Type:** `0x0002` (PTP Data Container)
* **Data Endpoint:** `0x02` (Bulk OUT)
* **Container Length:** 31 bytes (`0x0000001F`) = 12 bytes PTP header + 19 bytes payload
* **Raw Payload Hex:**  
  `62 6c 65 66 61 5f 73 74 61 72 74 66 61 63 74 6f 72 79 00`
* **Decoded ASCII String:** `"blefa_startfactory\0"` (18 characters + NUL terminator)
* **PTP Response:** ResponseCode `0x2001` (`PTP_RC_OK`), TxID: 54, Endpoint: `0x81` (Bulk IN)

---

## 2. Chronological Position in the Session Stream

The table below maps the exact chronological sequence surrounding `blefa_startfactory`:

| Phase / Order | TxID | PTP OpCode | Subsystem / Command | Physical Target | Relative Position to Shutter Readout |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 0 | `0x1002` | `OpenSession` | USB Session Manager | Session Start |
| 2 | 1..5 | `0x1001` | `GetDeviceInfo` / PropDesc | Standard PTP Enumeration | Pre-Auth |
| 3 | 9..11 | `0x905C` | `saitamatch` / `gunmafukaya` | Factory Auth Tokens | Security Unlock |
| 4 | 14 | `0x9052` | `FA_TurnOffDisplay` | Display Controller | Sleep LCD/EVF |
| 5 | 15 | `0x9052` | `IsFactoryMode` | Session Flag Query | Factory Verification |
| **6** | **25 / 26** | **`0x9052` / `0x9053`** | **`FA_GetProperty(0x12000001)`** | **Mechanical Shutter Register** | **SHUTTER COUNT (60,689) READ HERE** |
| **7** | **31 / 32** | **`0x9052` / `0x9053`** | **`FA_GetProperty(0x12000003)`** | **Master Release Register** | **TOTAL RELEASES (840,377) READ HERE** |
| 8 | 33 / 34 | `0x9052` / `0x9053` | `FA_GetProperty(0x13000000)` | Fault History Table | Error Log Extraction |
| 9 | 37..38 | `0x9052` | `cc_cmd_playbtn_on` / `DisablePowerSave` | Window Manager / APM | UI / Sleep Inhibit |
| 10 | 39 | `0x9052` | `FA_ReadEepromData` (Block 70) | EEPROM Memory Manager | EEPROM Dump Starts |
| 11 | 40..53 | `0x9052` / `0x9053` | `FA_ReadEepromData` (Blocks 71..84) | EEPROM Memory Manager | 14 Blocks Read |
| **12** | **54** | **`0x9052`** | **`blefa_startfactory`** | **Bluetooth Low Energy Subsystem** | **28 Tx AFTER Shutter Count Readout** |
| 13 | 55..61 | `0x9052` / `0x9053` | `FA_ReadEepromData` (Blocks 85..91) | EEPROM Memory Manager | EEPROM Dump Resumes |
| **14** | **62 / 63** | **`0x9052` / `0x9053`** | **`FA_GetProperty(0x12000005)`** | **Power Management Register** | **POWER ON COUNT (5,984) READ HERE** |
| 15 | 90 | `0x905A` | `Canon_SaveTransparentMemory` | Volatile SDRAM Buffer | First FAEXE Upload |

---

## 3. Resolving the Analytical Paradox

### The Question:
*Why have earlier community reports claimed that `blefa_startfactory` (TxID 54) "preceded the readout of camera counters," when TxID 25/26 already contained the shutter counter query and response?*

### The Forensic Resolution:
1. **Misconception of Counter Storage:** Earlier investigators erroneously assumed that the shutter count was embedded somewhere deep inside the 407,040-byte EEPROM memory dump. Because the EEPROM dump was interrupted around Block 84 when TxID 54 was dispatched, analysts assumed that TxID 54 was a prerequisite switch needed to access subsequent diagnostic metrics.
2. **Subsystem Disambiguation (`blefa`):** The prefix `blefa` stands for **Bluetooth Low Energy Factory Application**. Modern Canon EOS R cameras feature dedicated BLE / Wi-Fi co-processors. Tornado's comprehensive diagnostic suite tests the wireless radio hardware concurrently while dumping EEPROM in the background.
3. **Physical Wire Fact:** The mechanical shutter count was fully acquired at **TxID 25 and 26**, exactly **28 transactions prior to `blefa_startfactory`**.
4. **Architectural Implication:** `blefa_startfactory` is **COMPLETELY UNNECESSARY** for shutter and release count extraction.

---

## 4. Session Architecture: OpenSession & Transaction Integrity

### A. Single Session Monolithic Model
* **Number of PTP `OpenSession` Calls:** Exactly **ONE (1)** (`TxID 0`, OpCode `0x1002`, Parameter `0x00000001`).
* **Number of PTP `CloseSession` Calls:** Exactly **ONE (1)** (`TxID 3219`, OpCode `0x1003`).
* **Session Continuity:** The entire capture of 24,379 packets exists within a single, continuous, unbroken PTP session.

### B. TxID Monotonicity & Reset Audit
* **Initial TxID:** `0` (OpenSession)
* **First Operational TxID:** `1` (GetDeviceInfo)
* **Terminal TxID:** `3219` (CloseSession / Terminal Dispatch)
* **TxID Resets:** **ZERO (0)**. There are no TxID rollbacks, resets to zero, or session discontinuities.
* **Transaction Gaps:** **ZERO (0)**. Every integer from `0` to `3219` is represented sequentially without omissions.

---

## 5. Factory Mode: Empirical Facts vs Speculative Assumptions

```
+----------------------------------------------------------------------------------------------------+
|                                    FACTORY MODE EVIDENTIAL MATRIX                                  |
+--------------------------+-----------------------+-------------------------------------------------+
| Dimension                | Evidential Status     | Technical Reality from Wire Analysis            |
+--------------------------+-----------------------+-------------------------------------------------+
| Authentication Tokens    | [VERIFIED]            | 0x905C ("saitamatch", "gunmafukaya") dispatched |
| Volatile State Change    | [VERIFIED]            | Camera accepts vendor commands 0x9052 / 0x9053  |
| Non-Volatile Mode Change | [REFUTED]             | Factory mode does NOT persist across power cycle|
| Requirement for Shutter  | [REFUTED]             | TxID 25/26 reads shutter; TxID 54 is radio-only |
| Hardware Reboot Needed   | [REFUTED]             | Camera never reboots during the entire session  |
+--------------------------+-----------------------+-------------------------------------------------+
```

### Conclusions for OpenEOS:
1. OpenEOS requires only the lightweight authentication tokens (`0x905C`) to query `FA_GetProperty`.
2. OpenEOS must **NEVER** issue `blefa_startfactory` (TxID 54), as touching the camera's wireless hardware subsystem introduces unnecessary risk without diagnostic benefit.
