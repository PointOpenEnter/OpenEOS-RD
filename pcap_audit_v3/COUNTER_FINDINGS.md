# COUNTER FINDINGS & DETAILED FORENSIC VERIFICATION (REVISION 3)
**Investigation:** Forensic Analysis of Shutter Counters, Argument Formats, and OpCode Semantics  
**Target Hardware:** Canon EOS R6 Mark II (PID `0x330B`, S/N `183121000830`, FW `1.7.0`, DIGIC X)  
**Capture File:** `р62.pcapng` (29,054,644 bytes)  
**Forensic Standard:** Full Protocol Chain Verification & Rigorous Scientific Classification  

---

## 1. Mechanical Shutter Counter Analysis (TxID 25 & 26)

### A. Full Structural Chain Verification
In Revision 3, validation of the mechanical shutter count does not rely on a static constant check (`if count == 60689`). Instead, the audit engine verifies the complete structural protocol chain according to ISO 15740 and Canon DIGIC X vendor PTP specifications:

```
[Host PC]                                                [Canon EOS R6 Mark II]
   |                                                                |
   |--- (TxID 25) PTP Command 0x9052 (params: [0, 1]) ------------->|
   |--- (TxID 25) Data OUT: "FA_GetProperty\0", argc=1, tag=2, ---->|
   |              key=0x12000001 (55 bytes total)                   |
   |<-- (TxID 25) PTP Response 0x2001 (OK, param1: 8 bytes ready) --|
   |                                                                |
   |--- (TxID 26) PTP Command 0x9053 (params: []) ----------------->|
   |<-- (TxID 26) Data IN (Bulk IN, EP 0x81, 20 bytes total): ------|
   |              Payload: [11 ed 00 00 00 00 00 00]                |
   |<-- (TxID 26) PTP Response 0x2001 (OK) -------------------------|
```

Every link in this chain was independently evaluated:
1. `tx25_exists`: Transaction 25 present in capture. (**PASSED**)
2. `tx25_command_opcode_0x9052`: Command OpCode is `0x9052` (VendorCmd). (**PASSED**)
3. `tx25_command_params_0_1`: Command parameters are exactly `[0, 1]`. (**PASSED**)
4. `tx25_command_len_is_20`: Container length is exactly 20 bytes (`0x14`). (**PASSED**)
5. `tx25_data_out_present`: Bulk OUT Data container present. (**PASSED**)
6. `tx25_proc_name_fa_getproperty`: Procedure string is `"FA_GetProperty\0"`. (**PASSED**)
7. `tx25_argc_is_1`: Argument count integer is `1`. (**PASSED**)
8. `tx25_tag_is_2`: Type descriptor tag is `2` (`0x00000002`). (**PASSED**)
9. `tx25_key_is_0x12000001`: Property Key is `0x12000001`. (**PASSED**)
10. `tx25_response_ok_0x2001`: ResponseCode is `0x2001` (PTP_RC_OK). (**PASSED**)
11. `tx25_response_param1_is_8`: Announced payload size in Response `Param1` is `8`. (**PASSED**)
12. `tx26_exists`: Transaction 26 present in capture. (**PASSED**)
13. `tx26_command_opcode_0x9053`: Command OpCode is `0x9053` (VendorDataReceive). (**PASSED**)
14. `tx26_command_params_empty`: Command parameters are `[]` (None). (**PASSED**)
15. `tx26_data_in_present`: Bulk IN Data container present. (**PASSED**)
16. `tx26_data_opcode_0x9053`: Data container OpCode is `0x9053`. (**PASSED**)
17. `tx26_data_txid_26`: Data container TransactionID is `26`. (**PASSED**)
18. `tx26_endpoint_is_0x81_bulk_in`: USB Endpoint is `0x81` (Bulk IN). (**PASSED**)
19. `tx26_payload_len_is_8`: Received payload is exactly 8 bytes. (**PASSED**)
20. `tx26_response_ok_0x2001`: Final ResponseCode is `0x2001` (OK). (**PASSED**)
21. `tx26_response_txid_26`: Final Response TransactionID matches `26`. (**PASSED**)

**Extracted Value:**  
Only after all 21 structural constraints passed, the value was unpacked:
`struct.unpack_from('<I', payload, 0)[0]` $\to$ Little-Endian `0x0000ED11` = **`60,689`**.  
Trailing 4 bytes: `00 00 00 00` (reserved / zero padding).  
Raw payload hex: `11ed000000000000`.

---

## 2. Total Releases Counter Analysis (TxID 31 & 32)

### A. Full Structural Chain Verification
Total releases were audited through the exact same structural protocol chain:
1. `tx31_exists` & `tx31_command_opcode_0x9052` (params `[0, 1]`). (**PASSED**)
2. `tx31_data_out_present` with `"FA_GetProperty\0"`, `argc = 1`, `tag = 2`. (**PASSED**)
3. `tx31_key_is_0x12000003`: Property Key is `0x12000003`. (**PASSED**)
4. `tx31_response_ok_0x2001` with `Param1 = 4` (announced size = 4 bytes). (**PASSED**)
5. `tx32_command_opcode_0x9053` with empty params `[]`. (**PASSED**)
6. `tx32_endpoint_is_0x81_bulk_in` on Bulk IN endpoint `0x81`. (**PASSED**)
7. `tx32_payload_len_is_4`: Received payload is exactly 4 bytes. (**PASSED**)
8. `tx32_response_ok_0x2001` with `TxID = 32`. (**PASSED**)

**Extracted Value:**  
`struct.unpack_from('<I', payload, 0)[0]` $\to$ Little-Endian `0x000CD2B9` = **`840,377`**.  
Raw payload hex: `b9d20c00`.

### B. Scientific Qualification of Total Releases
- Subtracting mechanical shutter count from total releases:
  $$840,377 - 60,689 = 779,688$$
- Labeling this difference as "pure electronic shutter" is an **unverified speculation**.
- In Canon DIGIC firmware, the release counter increments on electronic shutter exposures, sensor cleaning/calibration actuations, intervalometer triggers, and live-view stop/start cycles.
- Classification:
  * **[VERIFIED]:** Total Releases = `840,377`.
  * **[SPECULATION / UNVERIFIED]:** Electronic Shutter Exposures = `779,688`.

---

## 3. Numeric Tag 2 vs OpenShutterCounter ASCII "CSC"

### A. Empirical Payload Analysis (TxID 25 & 31)
The Data OUT payload (43 bytes) for `FA_GetProperty` is structured as follows:
```text
Offset  0..14 (15 bytes): 46 41 5f 47 65 74 50 72 6f 70 65 72 74 79 00   -> "FA_GetProperty\0"
Offset 15..18 ( 4 bytes): 01 00 00 00                                     -> uint32: 1 (argc)
Offset 19..22 ( 4 bytes): 02 00 00 00                                     -> uint32: 2 (Numeric Tag)
Offset 23..26 ( 4 bytes): 01 00 00 12                                     -> uint32: 0x12000001 (Property Key)
Offset 27..42 (16 bytes): 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 -> 16 zero padding bytes
```

### B. Comparison with OpenShutterCounter Structure
- In the open-source `OpenShutterCounter` codebase and legacy Canon tools, property query builders often support either an ASCII fourcc tag like `"CSC\0"` (`43 53 43 00`) or a numeric tag.
- In `р62.pcapng`, the ASCII string `"CSC"` **does not appear anywhere in the capture**.
- Offset 19 contains strictly the Little-Endian 32-bit integer `2` (`02 00 00 00`).
- **Cross-Model Variation Status: [UNKNOWN]:**
  * We refrain from claiming as universal fact that DIGIC X abandoned `"CSC"`.
  * We empirically state that the Canon EOS R6 Mark II in this session strictly utilizes integer tag `2`.
  * Why certain Canon models accept `"CSC"` while others require numeric tag `2` is designated as **UNKNOWN** pending empirical captures from other camera bodies.

---

## 4. Empirical Analysis of Dual-Syntax OpCode 0x9053 Parameters

In `р62.pcapng`, Tornado utilizes OpCode `0x9053` (VendorDataReceive) in two distinct parameter syntaxes:

| Syntax Type | TxID | Preceding Property Query (0x9052) | Preceding Response Param1 | 0x9053 Container Length | 0x9053 Parameters | Data IN Payload Length |
|---|---|---|---|---|---|---|
| **Zero Params** | 13 | `FA_GetProperty(0x00000002)` | 500 (`0x01F4`) | 12 bytes (`0x0C`) | `[]` (None) | 500 bytes |
| **Zero Params** | 20 | `FA_GetProperty(0x01000006)` | 8 (`0x0008`) | 12 bytes (`0x0C`) | `[]` (None) | 8 bytes |
| **Zero Params** | 26 | `FA_GetProperty(0x12000001)` | 8 (`0x0008`) | 12 bytes (`0x0C`) | `[]` (None) | **8 bytes (Shutter: 60,689)** |
| **Zero Params** | 28 | `FA_GetProperty(0x01000021)` | 200 (`0x00C8`) | 12 bytes (`0x0C`) | `[]` (None) | 200 bytes |
| **Zero Params** | 30 | `FA_GetProperty(0x01000021)` | 200 (`0x00C8`) | 12 bytes (`0x0C`) | `[]` (None) | 200 bytes |
| **Zero Params** | 32 | `FA_GetProperty(0x12000003)` | 4 (`0x0004`) | 12 bytes (`0x0C`) | `[]` (None) | **4 bytes (Total: 840,377)** |
| **Zero Params** | 34 | `FA_GetProperty(0x13000000)` | 400 (`0x0190`) | 12 bytes (`0x0C`) | `[]` (None) | 400 bytes |
| **Three Params**| 17 | `FA_GetProperty(0x0100001D)` | 80 (`0x0050`) | 24 bytes (`0x18`) | `[0, 0, 1]` | 80 bytes |
| **Three Params**| 22 | `FA_GetProperty(0x02000005)` | 36 (`0x0024`) | 24 bytes (`0x18`) | `[0, 0, 1]` | 36 bytes |
| **Three Params**| 24 | `FA_GetProperty(0x80030000)` | 14 (`0x000E`) | 24 bytes (`0x18`) | `[0, 0, 1]` | 14 bytes |
| **Three Params**| 36 | `FA_GetProperty(0x01000002)` | 16 (`0x0010`) | 24 bytes (`0x18`) | `[0, 0, 1]` | 16 bytes |

### Refutation of Earlier Negotiation Hypothesis:
- The hypothesis that Tornado supplies parameters `[0, 0, 1]` only when length was not negotiated is **REFUTED**: in all eleven cases above, the preceding `0x9052` response explicitly communicated the expected size in `Param1`.
- The exact firmware requirement mandating zero parameters for shutter properties (`0x12000001`, `0x12000003`) but three parameters for device serial numbers is classified as **UNKNOWN** without firmware disassembly.

---

## 5. Physical USB Wire Direction vs USBPcap Headers

- **Physical USB Direction:**  
  * Determined strictly by Endpoint Address bit 7: `endpoint & 0x80`.
  * For TxID 26 and TxID 32, Endpoint is `0x81` (`10000001b`). Bit 7 is `1`, proving a physical **Bulk IN** transfer across the USB bus (Camera $\to$ Host).
- **USBPcap Header 'info' Byte:**
  * In USBPcap, bit 0 of `info` indicates Windows driver stack IRP traversal (`0` = PDO to FDO, `1` = FDO to PDO).
  * Completed read IRP: `0xFFFF800100A11A00` with `USBD_STATUS_SUCCESS`.
- **Forensic Verdict:**  
  The mechanical shutter count (60,689) and total releases (840,377) were unquestionably **originated by the camera hardware** and transmitted into host RAM.
