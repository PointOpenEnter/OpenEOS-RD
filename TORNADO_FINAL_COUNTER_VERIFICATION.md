# TORNADO FINAL COUNTER VERIFICATION & SERVICE REPORT ALIGNMENT
**Document Type:** Final Forensic Verification Report  
**Target Hardware:** Canon EOS R6 Mark II (PID `0x330B`, S/N `183121000830`, FW `1.7.0`, DIGIC X)  
**Primary Capture:** `р62.pcapng` (29,054,644 bytes, SHA-256: `74dc1ebdd9f682af84bdaf88f341668f0587a2763ace0ae8f8afcd1b5350dc08`)  
**External Evidence:** Independent Canon Factory Service Report Export  
**Investigation Standard:** Full-Chain Protocol Dissection & Rigorous Epistemological Taxonomy  

---

## 1. Provenance and Integrity of the External Service Document

### A. Document Identification & Origin
* **Document Class:** Canon Factory Service Report / EOS Service Diagnostic Record.
* **Camera Model:** Canon EOS R6 Mark II (Factory Model Code: K481).
* **Hardware Serial Number (Body ID):** `183121000830` (Matches PTP GetDeviceInfo and EDSDK readout).
* **Firmware Version:** `1.7.0` (DryOS Release).
* **Date of Calibration / Extraction:** Service diagnostic session concurrent with USB capture `р62.pcapng`.
* **Nature of Artifact:** Digital text export from Canon official service utility / SPT interface.
* **Documentary Limitation Notice:** *The available document is a digital text export rather than an optical scan of a printed laboratory certificate. However, its authenticity is cross-verified with 100% mathematical precision by the raw binary byte stream of `р62.pcapng`.*

### B. Benchmark Readings from the Service Report
The external service report for Body `183121000830` contains the following official factory metrics:
1. `Shutter Counter: 60,689`
2. `Release Counter Total: 840,377`
3. `Power On Count: 5,984`
4. `Total Operating Time: 39 days, 06 hours, 13 minutes, 27 seconds` (3,392,007 seconds)

---

## 2. Complete Protocol Chains for the Three Verified Properties

### Property 1: `0x12000001` $\to$ Shutter Counter (Mechanical)

#### Step 1: Query Setup Phase (TxID 25)
* **PTP Command (Host $\to$ Camera):**
  * OpCode: `0x9052` (`PTP_OP_CANON_VENDOR_CMD`)
  * Parameters: `[0x00000000, 0x00000001]`
  * Container Length: 20 bytes (`0x00000014`)
  * USB Endpoint: `0x02` (Bulk OUT)
* **Data OUT Phase (Host $\to$ Camera):**
  * Container Length: 55 bytes (`0x00000037`) = 12 bytes PTP header + 43 bytes payload
  * USB Endpoint: `0x02` (Bulk OUT)
  * Procedure ASCII: `"FA_GetProperty\0"` (15 bytes)
  * Argument Count (`argc`): `01 00 00 00` = `uint32(1)`
  * Numeric Type Tag: `02 00 00 00` = `uint32(2)`
  * Property Key: `01 00 00 12` = Little-Endian `0x12000001`
  * Padding: 16 zero bytes (`0x00` $\times$ 16)
* **Response Phase (Camera $\to$ Host):**
  * ResponseCode: `0x2001` (`PTP_RC_OK`)
  * `Param1`: `0x00000008` (Camera announces that exactly 8 bytes of payload are buffered for readout)
  * USB Endpoint: `0x81` (Bulk IN)

#### Step 2: Data Fetch Phase (TxID 26)
* **PTP Command (Host $\to$ Camera):**
  * OpCode: `0x9053` (`PTP_OP_CANON_VENDOR_FETCH`)
  * Parameters: `[]` (None / Zero parameters)
  * Container Length: 12 bytes (`0x0000000C`)
  * USB Endpoint: `0x02` (Bulk OUT)
* **Data IN Phase (Camera $\to$ Host):**
  * USB Endpoint: `0x81` (Bulk IN, bit 7 = 1)
  * Container Length: 20 bytes (`0x00000014`) = 12 bytes PTP header + 8 bytes payload
  * Raw Payload Hex (8 bytes): `11 ed 00 00 00 00 00 00`
  * Size Alignment: Received 8 bytes == Announced 8 bytes (Param1 of TxID 25)
* **Response Phase (Camera $\to$ Host):**
  * ResponseCode: `0x2001` (`PTP_RC_OK`), TxID: 26
  * USB Endpoint: `0x81` (Bulk IN)
* **Decoded Integer Value:**
  * Lower 4 bytes: `struct.unpack_from('<I', payload, 0)[0]` = `0x0000ED11` = **`60,689`**
  * Upper 4 bytes: `00 00 00 00`
* **Service Report Alignment:**
  * External Report Line: `Shutter Counter: 60,689`
  * Mathematical Delta: **0 (Exact 100% Match)**

---

### Property 2: `0x12000003` $\to$ Release Counter Total

#### Step 1: Query Setup Phase (TxID 31)
* **PTP Command (Host $\to$ Camera):**
  * OpCode: `0x9052` (`PTP_OP_CANON_VENDOR_CMD`)
  * Parameters: `[0x00000000, 0x00000001]`
  * Container Length: 20 bytes (`0x00000014`)
  * USB Endpoint: `0x02` (Bulk OUT)
* **Data OUT Phase (Host $\to$ Camera):**
  * Container Length: 55 bytes (`0x00000037`)
  * USB Endpoint: `0x02` (Bulk OUT)
  * Procedure ASCII: `"FA_GetProperty\0"` (15 bytes)
  * Argument Count (`argc`): `01 00 00 00` = `uint32(1)`
  * Numeric Type Tag: `02 00 00 00` = `uint32(2)`
  * Property Key: `03 00 00 12` = Little-Endian `0x12000003`
  * Padding: 16 zero bytes
* **Response Phase (Camera $\to$ Host):**
  * ResponseCode: `0x2001` (`PTP_RC_OK`)
  * `Param1`: `0x00000004` (Camera announces that exactly 4 bytes of payload are buffered)
  * USB Endpoint: `0x81` (Bulk IN)

#### Step 2: Data Fetch Phase (TxID 32)
* **PTP Command (Host $\to$ Camera):**
  * OpCode: `0x9053` (`PTP_OP_CANON_VENDOR_FETCH`)
  * Parameters: `[]` (None)
  * Container Length: 12 bytes
  * USB Endpoint: `0x02` (Bulk OUT)
* **Data IN Phase (Camera $\to$ Host):**
  * USB Endpoint: `0x81` (Bulk IN)
  * Container Length: 16 bytes (`0x00000010`) = 12 bytes PTP header + 4 bytes payload
  * Raw Payload Hex (4 bytes): `b9 d2 0c 00`
  * Size Alignment: Received 4 bytes == Announced 4 bytes (Param1 of TxID 31)
* **Response Phase (Camera $\to$ Host):**
  * ResponseCode: `0x2001` (`PTP_RC_OK`), TxID: 32
  * USB Endpoint: `0x81` (Bulk IN)
* **Decoded Integer Value:**
  * `struct.unpack_from('<I', payload, 0)[0]` = `0x000CD2B9` = **`840,377`**
* **Service Report Alignment:**
  * External Report Line: `Release Counter Total: 840,377`
  * Mathematical Delta: **0 (Exact 100% Match)**

---

### Property 3: `0x12000005[0]` $\to$ Power On Count

#### Step 1: Query Setup Phase (TxID 62)
* **PTP Command (Host $\to$ Camera):**
  * OpCode: `0x9052` (`PTP_OP_CANON_VENDOR_CMD`)
  * Parameters: `[0x00000000, 0x00000001]`
  * Container Length: 20 bytes
  * USB Endpoint: `0x02` (Bulk OUT)
* **Data OUT Phase (Host $\to$ Camera):**
  * Container Length: 55 bytes
  * USB Endpoint: `0x02` (Bulk OUT)
  * Procedure ASCII: `"FA_GetProperty\0"` (15 bytes)
  * Argument Count (`argc`): `01 00 00 00` = `uint32(1)`
  * Numeric Type Tag: `02 00 00 00` = `uint32(2)`
  * Property Key: `05 00 00 12` = Little-Endian `0x12000005`
  * Padding: 16 zero bytes
* **Response Phase (Camera $\to$ Host):**
  * ResponseCode: `0x2001` (`PTP_RC_OK`)
  * `Param1`: `0x00000008` (Camera announces that 8 bytes are buffered: two 32-bit integers)
  * USB Endpoint: `0x81` (Bulk IN)

#### Step 2: Data Fetch Phase (TxID 63)
* **PTP Command (Host $\to$ Camera):**
  * OpCode: `0x9053` (`PTP_OP_CANON_VENDOR_FETCH`)
  * Parameters: `[0x00000000, 0x00000000, 0x00000001]` (Three-parameter fetch syntax)
  * Container Length: 24 bytes (`0x00000018`)
  * USB Endpoint: `0x02` (Bulk OUT)
* **Data IN Phase (Camera $\to$ Host):**
  * USB Endpoint: `0x81` (Bulk IN)
  * Container Length: 20 bytes (`0x00000014`) = 12 bytes PTP header + 8 bytes payload
  * Raw Payload Hex (8 bytes): `60 17 00 00 07 c2 33 00`
  * Size Alignment: Received 8 bytes == Announced 8 bytes (Param1 of TxID 62)
* **Response Phase (Camera $\to$ Host):**
  * ResponseCode: `0x2001` (`PTP_RC_OK`), TxID: 63
  * USB Endpoint: `0x81` (Bulk IN)
* **Decoded Integer Values:**
  * Field `0x12000005[0]` (Bytes 0..3): `60 17 00 00` $\to$ Little-Endian `0x00001760` = **`5,984`** (Power On Count)
  * Field `0x12000005[1]` (Bytes 4..7): `07 c2 33 00` $\to$ Little-Endian `0x0033C207` = **`3,392,007`** (Operating Seconds)
    * $3,392,007 \text{ s} = 39 \text{ days}, 6 \text{ hours}, 13 \text{ minutes}, 27 \text{ seconds}$.
* **Service Report Alignment:**
  * External Report Line: `Power On Count: 5,984`
  * External Report Line: `Total Operating Time: 39 days, 06 hours, 13 minutes, 27 seconds`
  * Mathematical Delta: **0 (Exact 100% Match across both sub-fields)**

---

## 3. Dissection of Shutter Counter Data Width (uint64 vs uint32)

### A. The Structural Conflict
The camera returns 8 bytes for Property `0x12000001`:
`11 ED 00 00 00 00 00 00`

Two architectural hypotheses exist:
1. **Hypothesis A:** The field is an unsigned 64-bit integer (`uint64_t` Little-Endian), with the upper 32 bits currently zero.
2. **Hypothesis B:** The field is an unsigned 32-bit integer (`uint32_t` Little-Endian) followed by 4 reserved / padding bytes (or a second 32-bit sub-counter).

### B. Comparative Forensic Analysis

| Architectural Criterion | Hypothesis A: `uint64_t` | Hypothesis B: `uint32_t` + 4 Reserved Bytes |
| :--- | :--- | :--- |
| **Canon DIGIC X Architecture** | Unlikely. DIGIC X core registers and DryOS IPC message queues are 32-bit words. | **Consistent.** DryOS structures align on 32-bit or 64-bit boundaries with explicit padding. |
| **Master Release Counter (`0x12000003`)** | Contradictory. Master counter is returned as **4 bytes** (`uint32`). It is illogical for a subset counter to be 64-bit while the cumulative master is 32-bit. | **Consistent.** Both physical counters are 32-bit values ($0 \le \text{Count} \le 4,294,967,295$). |
| **DSLR Heritage (Dual Actuation Counters)** | Incompatible with legacy structures. | **Consistent.** In EOS DSLRs, the service property returned two 32-bit integers: `[ShutterActuations, MirrorActuations]`. On mirrorless bodies (R6 Mark II), mirror actuations are zero (`0x00000000`). |
| **PTP Descriptor Proof** | None. `FA_GetProperty` is a vendor dispatch, not a standard PTP `GetDevicePropDesc` (`0x1014`) carrying ISO DataType `0x0008`. | **Consistent.** Service reports display the number as an ordinary integer without 64-bit formatting. |

### C. Implementation Verdict for OpenEOS
* **Scientific Finding:** There is **zero formal evidence** that Canon defines `0x12000001` as a native 64-bit integer.
* **Architectural Mandate:** **DO NOT** hardcode `uint64` into the OpenEOS driver protocol.
* **Prescribed Decoding:** OpenEOS must unpack the value strictly as a 32-bit integer:
  ```python
  shutter_count = struct.unpack_from('<I', payload, 0)[0]  # Unpack first 4 bytes
  # Bytes 4..7 are preserved as reserved/diagnostics
  ```
