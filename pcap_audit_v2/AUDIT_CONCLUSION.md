# SCIENTIFIC AUDIT CONCLUSION & FORENSIC TAXONOMY (REVISION 2)
**Investigation:** Forensic Audit of Canon EOS R6 Mark II Service Capture (`р62.pcapng`)  
**Investigator:** OpenEOS Independent Engineering Review  
**Date:** November 2026 (Revision 2)  
**Methodology:** Byte-Level Packet Dissection & Strict Evidential Standards  

---

## 1. Evidential Standards

* **[VERIFIED]:** Empirically proven by raw bytes, packet headers, completed IRP descriptors, and mathematical decoding.
* **[LIKELY]:** High-probability technical deduction based on known DIGIC architecture, but lacking official Canon engineering documentation.
* **[UNKNOWN]:** Questions that cannot be answered from USB traffic alone without Canon firmware disassembly or hardware debugging.
* **[REFUTED / SPECULATION]:** Hypotheses and community assumptions proven false or unsubstantiated.

---

## 2. Updated Scientific Taxonomy

### A. [VERIFIED] Facts

1. **Hardware & Firmware Identity:**
   * VID: `0x04A9`, PID: `0x330B` (Canon EOS R6 Mark II).
   * Serial Number: `183121000830`.
   * Firmware: `1.7.0` (DryOS / DIGIC X).
2. **Mechanical Shutter Actuation Count = 60,689:**
   * Requested in **TxID 25** via `FA_GetProperty` with Key `0x12000001`.
   * Returned in **TxID 26** on Bulk IN Endpoint `0x81` (`11 ed 00 00 00 00 00 00` $\to$ `0x0000ED11` = $60\,689$).
   * Proof of direction: Completed read IRP `0xFFFF800100A11A00` with device-to-host flag (`0x01`). The value was produced by the camera hardware.
3. **Total Releases Count = 840,377:**
   * Requested in **TxID 31** via `FA_GetProperty` with Key `0x12000003`.
   * Returned in **TxID 32** on Bulk IN Endpoint `0x81` (`b9 d2 0c 00` $\to$ `0x000CD2B9` = $840\,377$).
4. **Diagnostic Error Incident Log:**
   * Retrieved in **TxID 33 & 34** via Key `0x13000000`. Returns 400 bytes of structured fault history (`Err 60`, `Err 70`).
5. **Exact PTP Container Arithmetic:**
   * Total Transactions: 3,219 (TxID 0 through 3,218).
   * Command Containers (Type 1): 3,219.
   * Response Containers (Type 3): 3,219.
   * Data Containers (Type 2): 3,215 (all transactions except TxID 0, 6, 7, 18).
   * **True Total PTP Containers:** $3,219 + 3,219 + 3,215 =$ **`9,653` containers**.
6. **Handshake Token Mapping:**
   * TxID 9 carries **both** `"saitamatch"` (11B) and `"gunmafukaya"` (12B) in a 55-byte Data OUT payload.
   * TxID 10 carries `"saitamatch"` with token `0x00071590` (39-byte payload).
   * TxID 11 carries `"saitamatch"` with token `0x00150AD3` (39-byte payload).
7. **Independence of `IsFactoryMode` (TxID 15) and Factory Flags (TxID 16/17):**
   * TxID 15 executes `"IsFactoryMode\0"` and terminates with Response `0x2001` (0 data bytes returned).
   * TxID 16/17 is an independent `FA_GetProperty(0x0100001D)` query returning 80 bytes of factory configuration flags.
8. **Absence of Direct EEPROM Write Commands:**
   * Across all 24,379 packets, zero direct EEPROM programming commands (`FA_WriteEepromData`, etc.) were transmitted over USB Bulk OUT.

---

### B. [LIKELY] Deductions

1. **Numeric Tag 2 in `FA_GetProperty`:**
   * The integer `0x00000002` at offset 19 functions as a scalar 32-bit property type descriptor in DIGIC X.
2. **Total Releases Semantics:**
   * Property `0x12000003` represents the camera's global release cycle counter across all actuation modes.

---

### C. [UNKNOWN] Questions (Requires Firmware Reverse Engineering)

1. **Firmware-Triggered EEPROM Side-Effects:**
   * While no direct EEPROM write commands were sent over USB, whether opaque routines like `IsFactoryMode` (TxID 15) or `DisablePowerSave` (TxID 38) trigger background writes to internal EEPROM or SPI Flash within DryOS cannot be proven without a pre/post hardware flash dump or firmware disassembly.
2. **Dual-Syntax OpCode `0x9053` Parameters:**
   * Why Tornado passes zero parameters for shutter properties (TxID 26, 32) and diagnostic tables, but passes `(0, 0, 1)` for serial numbers and firmware build info, is empirically observed but internally unproven.
3. **Exact Mathematical Inclusion of Total Releases:**
   * The precise firmware rules determining which non-mechanical operations (video start/stop, autofocus calibration sweeps) increment `0x12000003`.

---

### D. [REFUTED / SPECULATION] Past Claims Disproven

1. **"Tornado executed 7 EEPROM write operations":**
   * **REFUTED.** The 7 outgoing operations were authentication tokens and volatile state modifications.
2. **"Difference 840,377 - 60,689 is strictly Electronic Shutter count":**
   * **SPECULATION.** Unverified without firmware analysis; must be scientifically termed Total Releases minus Mechanical Actuations.
3. **"The entire session is strictly read-only":**
   * **REFUTED.** Tornado modified camera runtime states: remote mode, event notification, UI lock, display shutdown, and power save inhibition.
4. **"100% EEPROM safety is guaranteed":**
   * **UNVERIFIED.** Absence of user write commands is proven; absence of internal firmware logging side-effects is not.
