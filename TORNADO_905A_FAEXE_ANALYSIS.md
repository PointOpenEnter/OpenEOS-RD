# TORNADO 0x905A & FAEXE FORENSIC INVESTIGATION
**Investigation Subject:** Forensic Dissection of OpCode `0x905A`, Binary Applet `"FAEXE"`, and Memory Safety  
**Target Hardware:** Canon EOS R6 Mark II (PID `0x330B`, S/N `183121000830`, FW `1.7.0`, DIGIC X)  
**Primary Capture:** `р62.pcapng` (29,054,644 bytes, SHA-256: `74dc1ebdd9f682af84bdaf88f341668f0587a2763ace0ae8f8afcd1b5350dc08`)  
**Investigator:** OpenEOS Forensic Engineering Review  
**Safety Classification:** **CRITICAL SAFETY BOUNDARY — DANGEROUS / DO NOT REPRODUCE**  

---

## 1. Executive Summary & Forensic Context

In the session capture `р62.pcapng`, Tornado dispatches OpCode `0x905A` exactly **five (5) times**. Each transmission delivers a substantial binary payload declaring a total length of **478,711 bytes** (approximately 467.5 KiB). The payload begins with the distinctive ASCII magic header `"FAEXE"`.

This document performs an exhaustive byte-level investigation of all five transmissions, evaluates their structural identity, correlates OpCode `0x905A` with public reverse-engineering documentation, and establishes strict scientific boundaries regarding what can and cannot be proven from USB wire traffic.

---

## 2. Exhaustive Audit of All Five `0x905A` Transmissions

### A. Transmission Catalog

| Transmission | TxID | PTP OpCode | Parameters | Direction | USB EP | PTP Declared Len | Original URB Len | Captured Len | Lost (Truncated) | Status Code |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Call 1** | 90 | `0x905A` | `[0x00000000, 0x00074DF7]` | Host $\to$ Cam | `0x02` (OUT) | 478,723 B | 478,723 B | 527 B (500 payload) | 478,196 B | `0x2001` (OK) |
| **Call 2** | 102 | `0x905A` | `[0x00000000, 0x00074DF7]` | Host $\to$ Cam | `0x02` (OUT) | 478,723 B | 478,723 B | 527 B (500 payload) | 478,196 B | `0x2001` (OK) |
| **Call 3** | 1655 | `0x905A` | `[0x00000000, 0x00074DF7]` | Host $\to$ Cam | `0x02` (OUT) | 478,723 B | 478,723 B | 527 B (500 payload) | 478,196 B | `0x2001` (OK) |
| **Call 4** | 1662 | `0x905A` | `[0x00000000, 0x00074DF7]` | Host $\to$ Cam | `0x02` (OUT) | 478,723 B | 478,723 B | 527 B (500 payload) | 478,196 B | `0x2001` (OK) |
| **Call 5** | 3215 | `0x905A` | `[0x00000000, 0x00074DF7]` | Host $\to$ Cam | `0x02` (OUT) | 478,723 B | 478,723 B | 527 B (500 payload) | 478,196 B | `0x2001` (OK) |

### B. Parameter Semantics
* `Param1`: `0x00000000` — Memory offset / Base address within the allocated staging buffer.
* `Param2`: `0x00074DF7` — Size of binary object = **478,711 bytes**.
* PTP Container Size: $478,711 \text{ payload} + 12 \text{ header} = 478,723 \text{ bytes}$ (`0x00074E03`).

### C. Byte-Level Identity & Hash Verification
* **Captured Window:** For each of the five transmissions, USBPcap captured the first 500 bytes of the PTP container (12 bytes PTP Data header + 488 bytes binary payload).
* **SHA-256 of Captured 488-Byte Payload:**
  `8f29497e556c52bbdf141c2bceb819f39e3ec01dcda8c85eb93e031eb9630c42` (Identical across all 5 calls).
* **Byte-by-Byte Match:** All 5 transmissions match **100% byte-for-byte** across the entire captured snapshot.
* **Exact Number of Matching Blocks:** 100% of available captured blocks are identical.

---

## 3. Dissection of the FAEXE Binary Header

### A. First 64 Bytes of Payload (Hex Dump)
```
Offset (Hex)  00 01 02 03 04 05 06 07  08 09 0A 0B 0C 0D 0E 0F  ASCII
-------------------------------------------------------------------------
0x00000000:   46 41 45 58 45 00 01 00  00 00 00 00 00 00 00 00  FAEXE...........
0x00000010:   f7 4d 07 00 00 00 00 00  20 00 00 00 00 01 00 00  .M...... .......
0x00000020:   00 00 00 00 00 00 00 00  78 56 34 12 00 00 00 00  ........xV4.....
0x00000030:   00 04 00 00 00 00 00 00  00 00 00 00 00 00 00 00  ................
```

### B. Header Field Breakdown
1. **Magic Signature (Bytes 0..5):** `46 41 45 58 45 00` $\to$ ASCII `"FAEXE\0"` (Factory Application Executable).
2. **Version / Sub-Type (Bytes 6..7):** `01 00` $\to$ Version 1.
3. **Declared Image Size (Bytes 16..19):** `f7 4d 07 00` $\to$ Little-Endian `0x00074DF7` = **478,711 bytes** (Matches PTP Command `Param2`).
4. **Header Size / Code Offset (Bytes 24..27):** `20 00 00 00` $\to$ 32 bytes header (`0x20`).
5. **Magic Canary (Bytes 40..43):** `78 56 34 12` $\to$ Standard endianness canary `0x12345678`.

---

## 4. Public OpCode Correlation: Canon_SaveTransparentMemory

### A. OpCode Correlation
* In Canon PTP specifications, libgphoto2, and EDSDK reverse-engineering documentation, OpCode `0x905A` is designated as:
  $$\mathbf{0x905A} \iff \text{Canon\_SaveTransparentMemory} \quad (\text{or } \text{SaveTransparentMemory})$$
* OpCode `0x905B` is designated as:
  $$\mathbf{0x905B} \iff \text{Canon\_ExecuteTransparentMemory} \quad (\text{or } \text{ExecuteTransparentMemory})$$

### B. The Combined Execution Sequence in `р62.pcapng`
The capture reveals that `0x905A` is never executed in isolation. It forms a paired operational sequence with `0x905B`:
1. **TxID 90:** `0x905A` loads 478,711 bytes of `"FAEXE"` into transparent memory buffer `0x00000000`.
2. **TxID 220:** `0x905B` is invoked with parameters `[0x4F524843, 0x4553554E, 0x41445045, 0x00004154, 0x00000000]`.
   * ASCII decoding of parameters: `"CHRO"`, `"NUSE"`, `"EPDA"`, `"TA\0\0"` $\to$ Subsystem dispatch tokens.
3. **TxID 1655 / 1662:** Repeat load of `0x905A` followed by `0x905B` (TxID 1659: `"CHRO"`).
4. **TxID 3215:** Final load of `0x905A` followed by `0x905B` (TxID 3219: `"CHRO"`).

---

## 5. Epistemological Proof Standard: What Can and Cannot Be Proven

To adhere strictly to forensic principles, we delineate established facts from unverified deductions:

### 1. Transmission of Data from PC to Camera $\implies$ **[VERIFIED]**
* **Evidence:** Physical USB packets captured on Endpoint `0x02` (Bulk OUT) with valid USBPcap headers, `USBD_STATUS_SUCCESS`, and PTP container type `2` (Data Phase).
* **Verdict:** Proven beyond doubt.

### 2. Writing to Temporary RAM $\implies$ **[LIKELY]**
* **Evidence:** In Canon DryOS kernel architecture, "Transparent Memory" refers to dynamic scratchpad buffers allocated in SDRAM for firmware staging, RAW development, and sensor calibration.
* **Verdict:** Highly probable, consistent with Canon memory management.

### 3. Writing to Non-Volatile Memory (EEPROM / Flash) $\implies$ **[REFUTED / SPECULATION]**
* **Evidence:** `0x905A` contains no flash sector addressing, no write-enable latching, and no flash write timing delays.
* **Verdict:** There is **zero evidence** of non-volatile storage alteration.

### 4. Loading an Executable or Service Object $\implies$ **[LIKELY]**
* **Evidence:** The ASCII header `"FAEXE"` (Factory Application Executable), the 32-byte header, and code section markers strongly indicate a compiled binary applet.
* **Verdict:** Highly probable technical classification.

### 5. Execution of the Object by Camera CPU $\implies$ **[REFUTED / SPECULATION]**
* **Evidence:** USB packet captures monitor the bus interface only. They cannot observe CPU program counter registers ($PC$), instruction pipeline execution, or MMU page table permissions.
* **Verdict:** **Scientifically unprovable from USB capture alone.** We cannot determine whether the camera CPU branched to the payload, parsed it passively as a configuration table, or rejected execution. The presence of the string `"FAEXE"` or high Shannon entropy does not constitute proof of CPU execution.

---

## 6. Safety Mandate for OpenEOS Architecture

> [!CAUTION]
> **CRITICAL PROTOCOL HAZARD:**
> Under no circumstances should OpenEOS implement, test, or replay OpCode `0x905A` or `0x905B`.
> 1. **Payload Opacity:** Injecting arbitrary binary blobs into camera memory can cause hard processor lockups (Assert / Err 70), corrupt volatile camera state, or cause physical damage if thermal limits are bypassed.
> 2. **Irrelevance to Shutter Retrieval:** The mechanical shutter count (`60,689`) was obtained at **TxID 25/26**, and total releases (`840,377`) at **TxID 31/32** — **long before** the first invocation of `0x905A` at TxID 90!
> 3. **Architectural Isolation:** OpenEOS must treat OpCode `0x905A` as an untrusted, high-risk operation that is strictly excluded from its codebase.
