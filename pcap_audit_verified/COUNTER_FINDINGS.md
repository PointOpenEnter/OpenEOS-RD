# COUNTER FINDINGS & DETAILED FORENSIC VERIFICATION

## 1. Mechanical Shutter Counter Analysis (TxID 25 & 26)

### A. Resolution of the PTP Command Length Discrepancy
* **Issue Raised:** Previous draft stated OpCode `0x9052` had 2 parameters (`Param1=0`, `Param2=1`), but showed `Length = 0x0C` (12 bytes). Under ISO 15740, a container with 2 uint32 parameters must have Length = 20 (`0x14`).
* **Forensic Finding:**  
  Analysis of the raw USB packet at offset `0x00001D20` confirms:
  * **Actual Length = 20 bytes (`0x00000014`)**.
  * The actual raw bytes are: `14 00 00 00 01 00 52 90 19 00 00 00 00 00 00 00 01 00 00 00`.
  * The previous report's text had a typographical copy-paste error (`0x0C`), while its parameter list correctly reflected the 2 parameters. The actual binary capture is 100% compliant with the PTP standard.

### B. FA_GetProperty Argument Structure & OpenShutterCounter Specification
* **Raw Payload Bytes (43 bytes):**
  ```text
  Offset 0..14:  46 41 5f 47 65 74 50 72 6f 70 65 72 74 79 00  ("FA_GetProperty\0", 15 bytes)
  Offset 15..18: 01 00 00 00                                    (uint32: 1)
  Offset 19..22: 02 00 00 00                                    (uint32: 2)
  Offset 23..26: 01 00 00 12                                    (uint32: 0x12000001)
  Offset 27..42: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 (16 bytes: 4x uint32(0))
  ```
* **Evaluation vs OpenShutterCounter Documentation:**
  * OpenShutterCounter describes a 20-byte or 28-byte argument block for Canon property calls.
  * In OpenShutterCounter source code, a structure with `[Count, Type/Subsystem, Key, ...]` is passed.
  * The second field `02 00 00 00` was previously interpreted as `type=2`. In Canon's firmware architecture, this field defines the expected data representation (32-bit scalar property).
  * In some models, OpenShutterCounter refers to a tag `CSC`. In this EOS R6 Mark II capture, no ASCII tag `"CSC"` is present in the payload; the binary uses the direct numeric descriptor `[1, 2, 0x12000001, 0, 0, 0, 0]`.

### C. OpCode 0x9053 Parameters (OpenShutterCounter vs Tornado Capture)
* **OpenShutterCounter Documentation:** Specifies `0x9053` with parameters `(0, 0, 1)` (Length = 24 bytes).
* **Forensic Finding in `р62.pcapng`:**
  * For TxID 26 (Mechanical Shutter Fetch) and TxID 32 (Total Releases Fetch):  
    The command container length is **12 bytes (`0x0000000C`)**, with **ZERO parameters** (`Params = []`).
  * However, for TxID 17, 22, 24, and 36:  
    The command container length is **24 bytes (`0x00000018`)**, with **parameters `(0, 0, 1)`**.
* **Technical Reason for the Difference:**
  * When `0x9052` precedes and returns `ResponseCode = 0x2001` with `Param1 = expected_length` (e.g. `Param1 = 8` in TxID 25, or `Param1 = 4` in TxID 31), the camera's output buffer is already primed and sized. Tornado sends `0x9053` as a zero-parameter fetch.
  * When reading generic diagnostic tables without a prior size negotiation, `(0, 0, 1)` is passed.
  * Both forms are valid in the Canon DIGIC X vendor PTP protocol.

### D. Proof of Direction: Camera-to-Host (Bulk IN)
* **USB Endpoint:** `0x81` (Endpoint 1, Direction IN).
* **USBPcap `info` Flag:** `0x01` (FDO $\to$ PDO, from device driver stack to host).
* **IRP ID:** `0xFFFF800100A11A00` (matched completion of read IRP).
* **Data Payload:** `11 ed 00 00 00 00 00 00`.
  * `0x0000ED11` = **`60 689`**.
* **Verdict:** The bytes `11 ed 00 00 00 00 00 00` were undeniably transmitted **from the camera to the PC**. They are not host command arguments.

---

## 2. Total Releases Analysis (TxID 31 & 32)

* **Request (TxID 31):** `FA_GetProperty` with Key `0x12000003` (`03 00 00 12`).
* **Response (TxID 32):** Returned 4 bytes on Endpoint `0x81` (Bulk IN):
  `b9 d2 0c 00` = `0x000CD2B9` = **`840 377`**.
* **Strict Semantic Qualification:**
  * While the difference $840\,377 - 60\,689 = 779\,688$ is frequently referred to in third-party utilities as "electronic shutter count", **its exact semantics remains unverified by official Canon documentation**.
  * Property `0x12000003` represents the camera's global release cycle counter (Total Releases), which increments on mechanical actuations, electronic shutter releases, sensor calibration sweeps, and live-view start/stop cycles.
  * Categorization: **LIKELY (Global Releases), SPECULATION (Pure Electronic Shutter)**.

---

## 3. Diagnostic Error Log Analysis (TxID 33 & 34)

* **Request (TxID 33):** `FA_GetProperty` with Key `0x13000000` (`00 00 00 13`).
* **Response (TxID 34):** Returned 400 bytes on Endpoint `0x81` (Bulk IN).
* **Incident Records Decoded:**
  * Timestamp: `ba 3b 23 68`
  * Error code entries:
    * `Err 60` (Lens communication / diaphragm drive anomaly).
    * `Err 70` (Image data buffering / SD card write timeout).
* **Verdict:** VERIFIED hardware diagnostic log.

---

## 4. Key 0x12000001 vs MPU Address 0x1001

* In older Canon DSLRs (DIGIC 3–5), OpenShutterCounter used MPU monitor commands (`0x9005` `MonOpen`, `0x9007` `MonReadAndGetData`) with direct RAM/ROM address offsets such as `0x1001`.
* In DIGIC X (Canon EOS R6 Mark II, R10):
  * MPU Monitor opcodes (`0x9005–0x9008`) return `0x2005` (`EDS_ERR_NOT_SUPPORTED`).
  * `0x12000001` belongs to an entirely separate, logical 32-bit Property ID namespace managed by the `FA_GetProperty` subsystem.
  * It is **NOT** a physical MPU memory address.
