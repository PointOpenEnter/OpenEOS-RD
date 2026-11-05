# COUNTER FINDINGS & DETAILED FORENSIC VERIFICATION (REVISION 2)
**Investigation:** Forensic Analysis of Shutter Counters, Argument Formats, and OpCode Semantics  
**Target Hardware:** Canon EOS R6 Mark II (FW 1.7.0, DIGIC X)  
**Capture File:** `р62.pcapng`  

---

## 1. Mechanical Shutter Counter Analysis (TxID 25 & 26)

### A. Resolution of the PTP Command Container Length
* In ISO 15740 PTP standard:
  $$\text{Container Length} = 12 \text{ bytes (Base Header)} + 4 \times (\text{Parameter Count})$$
* For TxID 25 (`0x9052` with 2 parameters: `Param1 = 0`, `Param2 = 1`):
  $$\text{Container Length} = 12 + 4 \times 2 = 20 \text{ bytes } (0x14)$$
* Forensic packet analysis at PCAPNG offset `0x00001D20`:
  * Raw Bytes: `14 00 00 00 01 00 52 90 19 00 00 00 00 00 00 00 01 00 00 00`.
  * The actual container length is **exactly 20 bytes (`0x14`)**.
  * The previous draft's mention of `0x0C` was a typographical error in prose; the binary capture is 100% compliant with PTP.

### B. FA_GetProperty Argument Structure: Numeric Tag 2 vs OpenShutterCounter "CSC"
* **Exact Raw Payload Bytes for TxID 25 (Data OUT, 43 bytes payload):**
  ```text
  Offset  0..14 (15 bytes): 46 41 5f 47 65 74 50 72 6f 70 65 72 74 79 00   -> "FA_GetProperty\0"
  Offset 15..18 ( 4 bytes): 01 00 00 00                                     -> uint32: 1 (Count / Sub-command)
  Offset 19..22 ( 4 bytes): 02 00 00 00                                     -> uint32: 2 (Numeric Tag / Type Descriptor)
  Offset 23..26 ( 4 bytes): 01 00 00 12                                     -> uint32: 0x12000001 (Property Key)
  Offset 27..42 (16 bytes): 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 -> 16 zero padding bytes
  ```
* **Comparison with OpenShutterCounter Documentation ("CSC"):**
  * Public OpenShutterCounter documentation and early Canon reverse-engineering notes describe a property query structure incorporating the ASCII fourcc tag `"CSC"` (`43 53 43 00`, representing "Canon Service Command" or "Canon Shutter Counter") or passing an ASCII string in the descriptor field.
  * In the EOS R6 Mark II binary capture, the string `"CSC"` **does not exist anywhere in the payload**.
  * Instead, offset 19 strictly contains the 32-bit integer `0x00000002` (`02 00 00 00`).
* **Why Formats Differ & Possible Interpretations:**
  1. *Architecture Evolution (DIGIC X vs older DIGIC):* On older DSLR platforms (DIGIC 5/6/7), Canon service tools utilized ASCII tokens like `"CSC"` or `"FA_"` to identify service subsystems. On DIGIC X mirrorless cameras, Canon migrated to a strictly binary property model where field `0x00000002` designates a scalar 32-bit property type.
  2. *Divergent Reverse-Engineering Interpretations:* In community codebases, the second 32-bit field has been variously labeled as `type`, `subsystem_id`, or `tag`. A client passing `"CSC"` to an EOS R6 Mark II would likely trigger `EDS_ERR_INVALID_PARAMETER` (`0x201D`), as the DIGIC X handler parses this field as a numeric integer.

### C. Empirical Comparison of OpCode 0x9053 Parameters
In `р62.pcapng`, Tornado utilizes OpCode `0x9053` (VendorDataReceive) in two distinct syntactical variants:

| Variant | TxID | Preceding Query (0x9052) | Preceding Response Param1 (Length) | 0x9053 Container Length | 0x9053 Parameters | Data IN Length (Payload) |
|---|---|---|---|---|---|---|
| **Zero Params** | 13 | `FA_GetProperty(0x00000002)` | 500 (`0x01F4`) | 12 bytes (`0x0C`) | `[]` (None) | 500 bytes |
| **Zero Params** | 20 | `FA_GetProperty(0x01000006)` | 8 (`0x0008`) | 12 bytes (`0x0C`) | `[]` (None) | 8 bytes |
| **Zero Params** | 26 | `FA_GetProperty(0x12000001)` | 8 (`0x0008`) | 12 bytes (`0x0C`) | `[]` (None) | **8 bytes (Shutter: 60,689)** |
| **Zero Params** | 28 | `FA_GetProperty(0x01000021)` | 200 (`0x00C8`) | 12 bytes (`0x0C`) | `[]` (None) | 200 bytes |
| **Zero Params** | 30 | `FA_GetProperty(0x01000021)` | 200 (`0x00C8`) | 12 bytes (`0x0C`) | `[]` (None) | 200 bytes |
| **Zero Params** | 32 | `FA_GetProperty(0x12000003)` | 4 (`0x0004`) | 12 bytes (`0x0C`) | `[]` (None) | **4 bytes (Total: 840,377)** |
| **Zero Params** | 34 | `FA_GetProperty(0x13000000)` | 400 (`0x0190`) | 12 bytes (`0x0C`) | `[]` (None) | 400 bytes |
| **Three Params** | 17 | `FA_GetProperty(0x0100001D)` | 80 (`0x0050`) | 24 bytes (`0x18`) | `[0, 0, 1]` | 80 bytes |
| **Three Params** | 22 | `FA_GetProperty(0x02000005)` | 36 (`0x0024`) | 24 bytes (`0x18`) | `[0, 0, 1]` | 36 bytes |
| **Three Params** | 24 | `FA_GetProperty(0x80030000)` | 14 (`0x000E`) | 24 bytes (`0x18`) | `[0, 0, 1]` | 14 bytes |
| **Three Params** | 36 | `FA_GetProperty(0x01000002)` | 16 (`0x0010`) | 24 bytes (`0x18`) | `[0, 0, 1]` | 16 bytes |

* **Rigorous Scientific Assessment:**
  * Earlier hypotheses proposed that parameters `(0, 0, 1)` are passed only when size was not negotiated. As proven by the table above, this hypothesis is **refuted**: in ALL cases (both Zero Params and Three Params), the preceding `0x9052` response explicitly communicated the expected size in `Param1`.
  * The exact underlying reason why Tornado sends zero parameters for shutter properties (`0x12000001`, `0x12000003`) and diagnostic tables, but sends `(0, 0, 1)` for serial numbers and firmware descriptors, is **internally unproven without access to Canon firmware or Tornado source code**.
  * We record the empirical reality without fabricating unverified technical justifications.

### D. Proof of Direction: Camera-to-Host (Bulk IN)
* USB Endpoint: `0x81` (Endpoint 1, Direction IN).
* USBPcap Header Flag: `info = 0x01` (device driver to host controller).
* Completed IRP: `0xFFFF800100A11A00`.
* Payload: `11 ed 00 00 00 00 00 00` $\to$ Little-Endian `0x0000ED11` = **`60 689`**.
* **Verdict:** The mechanical shutter count was undeniably transmitted **from camera hardware to the PC host**.

---

## 2. Total Releases Analysis (TxID 31 & 32)

* **Query (TxID 31):** `FA_GetProperty` with Key `0x12000003` (`03 00 00 12`).
* **Response (TxID 32):** Returned 4 bytes on Bulk IN Endpoint `0x81`:
  `b9 d2 0c 00` $\to$ Little-Endian `0x000CD2B9` = **`840 377`**.
* **Strict Semantic Qualification:**
  * Subtracting mechanical shutter from total releases ($840\,377 - 60\,689 = 779\,688$) yields non-mechanical release events.
  * Calling this number "pure electronic shutter" is an **unverified speculation**. Total releases increment on electronic shutter captures, sensor calibration cycles, intervalometer frames, and live-view start/stop sequences.
  * Categorization: **VERIFIED (Total Releases = 840,377); SPECULATION (Pure Electronic Shutter = 779,688)**.

---

## 3. Diagnostic Error Log (TxID 33 & 34)

* **Query (TxID 33):** `FA_GetProperty` with Key `0x13000000` (`00 00 00 13`).
* **Response (TxID 34):** Returned 400 bytes on Bulk IN Endpoint `0x81`.
* **Incident Records:** Decodes historical hardware fault logs, including lens communication interruption (`Err 60`) and buffer timeout (`Err 70`).
* **Verdict:** VERIFIED hardware diagnostic log.
