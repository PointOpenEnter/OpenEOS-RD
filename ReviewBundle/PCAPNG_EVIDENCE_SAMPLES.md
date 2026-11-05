# PCAPNG FORENSIC EVIDENCE & WIRE TRANSACTIONS

**Document Class:** Raw Forensic Capture Verification & Hex Trace Catalog  
**Target Platform:** Canon EOS R6 Mark II (DIGIC X, Subsystem `K481`, Serial `183121000830`, FW `1.7.0`)  
**Baseline Capture File:** `р62.pcapng`  
**File Size:** `29,054,644 bytes` (27.71 MiB)  
**SHA-256 Checksum:** `74dc1ebdd9f682af84bdaf88f341668f0587a2763ace0ae8f8afcd1b5350dc08`  
**External Benchmark:** Official Canon Service Diagnostic Report (Factory Service Center)

---

## 1. Summary of Verified Properties vs Canon Service Report

| Property ID | Canonical Name | Wire Payload Length | Raw Decoded Hex (LE) | Decoded Engineering Value | Canon Service Report Benchmark | Verification Status |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **`0x12000001`** | Mechanical Shutter Counter | 8 bytes | `11 ed 00 00 00 00 00 00` | Counter: **60,689**<br>Tail: `00 00 00 00` | **`Shutter Counter: 60689`** | **`[VERIFIED]`** |
| **`0x12000003`** | Release Counter Total | 4 bytes | `b9 d2 0c 00` | Counter: **840,377** | **`Release Counter Total: 840377`** | **`[VERIFIED]`** |
| **`0x12000005`** | Power On & Operating Time | 8 bytes | `60 17 00 00 07 c2 33 00` | Power On: **5,984**<br>Uptime: **3,392,007 s** (39d 06h 13m 27s) | **`Power On Count: 5984`**<br>**`Total Operating Time: 3392007`** | **`[VERIFIED]`** |

---

## 2. Complete Transaction Wire Traces from `р62.pcapng`

### 2.1 Property `0x12000001` (Mechanical Shutter Counter: 60,689)

#### Step 1: PTP Command Container (0x9052)
- **Wireshark Frame / EPB Index:** Frame 69, EPB #69
- **Capture Wire Offset:** `0x00007720`
- **PTP Container Type:** `0x0001` (Command Container)
- **OpCode:** `0x9052` (Canon FA Subsystem Command)
- **TransactionID:** `25` (`0x00000019`)
- **Parameters:** `[0, 1]` (2 parameters, 8 bytes)
- **Total Length:** 20 bytes (`0x00000014`)
- **Full Wire HEX:**
  ```hex
  14 00 00 00 01 00 52 90 19 00 00 00 00 00 00 00 01 00 00 00
  ```

#### Step 2: PTP Data OUT Container (0x9052)
- **Wireshark Frame / EPB Index:** Frame 70, EPB #70
- **Capture Wire Offset:** `0x00007800`
- **PTP Container Type:** `0x0002` (Data Container)
- **OpCode:** `0x9052`
- **TransactionID:** `25` (`0x00000019`) — **strictly matches Step 1**
- **Total Length:** 55 bytes (`0x00000037`)
- **Payload Length:** 43 bytes (`0x0000002B`)
- **Field Breakdown:**
  * `0x00..0x0E` (15B): Command Name = `FA_GetProperty\0` (`46 41 5f 47 65 74 50 72 6f 70 65 72 74 79 00`)
  * `0x0F..0x12` (4B): argc = 1 (`01 00 00 00`)
  * `0x13..0x16` (4B): tag = 2 (Numeric DWORD) (`02 00 00 00`)
  * `0x17..0x1A` (4B): Property Key = `0x12000001` (`01 00 00 12`)
  * `0x1B..0x26` (12B): Argument Tail Padding (`00 00 00 00 00 00 00 00 00 00 00 00`)
  * `0x27..0x2A` (4B): Struct Alignment Padding (`00 00 00 00`)
- **Full Wire HEX:**
  ```hex
  37 00 00 00 02 00 52 90 19 00 00 00 46 41 5f 47 65 74 50 72
  6f 70 65 72 74 79 00 01 00 00 00 02 00 00 00 01 00 00 12 00
  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
  ```

#### Step 3: PTP Response Container (0x9052)
- **Wireshark Frame / EPB Index:** Frame 71, EPB #71
- **PTP Container Type:** `0x0003` (Response Container)
- **Response Code:** `0x2001` (`PTP_RC_OK`)
- **TransactionID:** `25` (`0x00000019`)
- **Parameters:** `[8]` (Declares subsequent buffer length = 8 bytes)
- **Total Length:** 16 bytes (`0x00000010`)
- **Full Wire HEX:**
  ```hex
  10 00 00 00 03 00 01 20 19 00 00 00 08 00 00 00
  ```

#### Step 4: PTP Command Container (0x9053 Fetch)
- **Wireshark Frame / EPB Index:** Frame 72, EPB #72
- **PTP Container Type:** `0x0001` (Command Container)
- **OpCode:** `0x9053` (Canon FA Fetch)
- **TransactionID:** `26` (`0x0000001A`)
- **Parameters:** `[]` (0 parameters)
- **Total Length:** 12 bytes (`0x0000000C`)
- **Full Wire HEX:**
  ```hex
  0c 00 00 00 01 00 53 90 1a 00 00 00
  ```

#### Step 5: PTP Data IN Container (0x9053 Fetch Result)
- **Wireshark Frame / EPB Index:** Frame 73, EPB #73
- **USB Bulk Endpoint:** Endpoint `0x81` (Bulk IN)
- **PTP Container Type:** `0x0002` (Data Container)
- **OpCode:** `0x9053`
- **TransactionID:** `26` (`0x0000001A`)
- **Total Length:** 20 bytes (`0x00000014`)
- **Payload Length:** 8 bytes
- **Raw Payload Bytes:** `11 ed 00 00 00 00 00 00`
  * Bytes `0..3` (`11 ed 00 00`): uint32 Little-Endian = `0x0000ED11` = **`60,689`** (Mechanical Shutter Count)
  * Bytes `4..7` (`00 00 00 00`): Opaque Tail / Reserved Bytes (retained intact)
- **Full Wire HEX:**
  ```hex
  14 00 00 00 02 00 53 90 1a 00 00 00 11 ed 00 00 00 00 00 00
  ```

#### Step 6: PTP Response Container (0x9053)
- **Wireshark Frame / EPB Index:** Frame 74, EPB #74
- **PTP Container Type:** `0x0003` (Response Container)
- **Response Code:** `0x2001` (`PTP_RC_OK`)
- **TransactionID:** `26` (`0x0000001A`)
- **Total Length:** 12 bytes (`0x0000000C`)
- **Full Wire HEX:**
  ```hex
  0c 00 00 00 03 00 01 20 1a 00 00 00
  ```

---

### 2.2 Property `0x12000003` (Release Counter Total: 840,377)

#### Step 1: PTP Command Container (0x9052)
- **Wireshark Frame / EPB Index:** Frame 87, EPB #87
- **PTP Container Type:** `0x0001` (Command Container)
- **OpCode:** `0x9052`
- **TransactionID:** `31` (`0x0000001F`)
- **Parameters:** `[0, 1]` (20 bytes)
- **Full Wire HEX:**
  ```hex
  14 00 00 00 01 00 52 90 1f 00 00 00 00 00 00 00 01 00 00 00
  ```

#### Step 2: PTP Data OUT Container (0x9052)
- **Wireshark Frame / EPB Index:** Frame 88, EPB #88
- **Capture Wire Offset:** `0x00009370`
- **PTP Container Type:** `0x0002` (Data Container)
- **OpCode:** `0x9052`
- **TransactionID:** `31` (`0x0000001F`)
- **Property Key:** `0x12000003` (`03 00 00 12`)
- **Total Length:** 55 bytes
- **Full Wire HEX:**
  ```hex
  37 00 00 00 02 00 52 90 1f 00 00 00 46 41 5f 47 65 74 50 72
  6f 70 65 72 74 79 00 01 00 00 00 02 00 00 00 03 00 00 12 00
  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
  ```

#### Step 3: PTP Response Container (0x9052)
- **Wireshark Frame / EPB Index:** Frame 89, EPB #89
- **Response Code:** `0x2001`
- **TransactionID:** `31` (`0x0000001F`)
- **Parameters:** `[4]` (Declares subsequent buffer length = 4 bytes)
- **Total Length:** 16 bytes
- **Full Wire HEX:**
  ```hex
  10 00 00 00 03 00 01 20 1f 00 00 00 04 00 00 00
  ```

#### Step 4: PTP Command Container (0x9053 Fetch)
- **Wireshark Frame / EPB Index:** Frame 90, EPB #90
- **OpCode:** `0x9053`
- **TransactionID:** `32` (`0x00000020`)
- **Parameters:** `[]` (0 parameters, 12 bytes)
- **Full Wire HEX:**
  ```hex
  0c 00 00 00 01 00 53 90 20 00 00 00
  ```

#### Step 5: PTP Data IN Container (0x9053 Fetch Result)
- **Wireshark Frame / EPB Index:** Frame 91, EPB #91
- **USB Bulk Endpoint:** Endpoint `0x81` (Bulk IN)
- **PTP Container Type:** `0x0002` (Data Container)
- **OpCode:** `0x9053`
- **TransactionID:** `32` (`0x00000020`)
- **Total Length:** 16 bytes (`0x00000010`)
- **Payload Length:** 4 bytes
- **Raw Payload Bytes:** `b9 d2 0c 00`
  * Bytes `0..3` (`b9 d2 0c 00`): uint32 Little-Endian = `0x000CD2B9` = **`840,377`** (Release Counter Total)
- **Full Wire HEX:**
  ```hex
  10 00 00 00 02 00 53 90 20 00 00 00 b9 d2 0c 00
  ```

#### Step 6: PTP Response Container (0x9053)
- **Wireshark Frame / EPB Index:** Frame 92, EPB #92
- **Response Code:** `0x2001`
- **TransactionID:** `32` (`0x00000020`)
- **Total Length:** 12 bytes
- **Full Wire HEX:**
  ```hex
  0c 00 00 00 03 00 01 20 20 00 00 00
  ```

---

### 2.3 Property `0x12000005` (Power On Count: 5,984; Operating Time: 3,392,007 s)

#### Step 1: PTP Command Container (0x9052)
- **Wireshark Frame / EPB Index:** Frame 173, EPB #173
- **OpCode:** `0x9052`
- **TransactionID:** `62` (`0x0000003E`)
- **Parameters:** `[0, 1]` (20 bytes)
- **Full Wire HEX:**
  ```hex
  14 00 00 00 01 00 52 90 3e 00 00 00 00 00 00 00 01 00 00 00
  ```

#### Step 2: PTP Data OUT Container (0x9052)
- **Wireshark Frame / EPB Index:** Frame 174, EPB #174
- **Capture Wire Offset:** `0x00012210`
- **OpCode:** `0x9052`
- **TransactionID:** `62` (`0x0000003E`)
- **Property Key:** `0x12000005` (`05 00 00 12`)
- **Total Length:** 55 bytes
- **Full Wire HEX:**
  ```hex
  37 00 00 00 02 00 52 90 3e 00 00 00 46 41 5f 47 65 74 50 72
  6f 70 65 72 74 79 00 01 00 00 00 02 00 00 00 05 00 00 12 00
  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
  ```

#### Step 3: PTP Response Container (0x9052)
- **Wireshark Frame / EPB Index:** Frame 175, EPB #175
- **Response Code:** `0x2001`
- **TransactionID:** `62` (`0x0000003E`)
- **Parameters:** `[8]` (Declares subsequent buffer length = 8 bytes)
- **Total Length:** 16 bytes
- **Full Wire HEX:**
  ```hex
  10 00 00 00 03 00 01 20 3e 00 00 00 08 00 00 00
  ```

#### Step 4: PTP Command Container (0x9053 Fetch) — Distinct Parameters [0, 0, 1]!
- **Wireshark Frame / EPB Index:** Frame 176, EPB #176
- **OpCode:** `0x9053`
- **TransactionID:** `63` (`0x0000003F`)
- **Parameters:** `[0, 0, 1]` (3 parameters, 12 bytes params + 12B header = 24 bytes)
- **Total Length:** 24 bytes (`0x00000018`)
- **Full Wire HEX:**
  ```hex
  18 00 00 00 01 00 53 90 3f 00 00 00 00 00 00 00 00 00 00 00 01 00 00 00
  ```

#### Step 5: PTP Data IN Container (0x9053 Fetch Result)
- **Wireshark Frame / EPB Index:** Frame 177, EPB #177
- **USB Bulk Endpoint:** Endpoint `0x81` (Bulk IN)
- **PTP Container Type:** `0x0002` (Data Container)
- **OpCode:** `0x9053`
- **TransactionID:** `63` (`0x0000003F`)
- **Total Length:** 20 bytes (`0x00000014`)
- **Payload Length:** 8 bytes
- **Raw Payload Bytes:** `60 17 00 00 07 c2 33 00`
  * Bytes `0..3` (`60 17 00 00`): uint32 Little-Endian = `0x00001760` = **`5,984`** (Power On Count)
  * Bytes `4..7` (`07 c2 33 00`): uint32 Little-Endian = `0x0033C207` = **`3,392,007 s`** (Operating Time)
  * Mathematical conversion: $3392007 \div 86400 = 39\text{d}$, rem $22407$; $22407 \div 3600 = 6\text{h}$, rem $807$; $807 \div 60 = 13\text{m}$, rem $27\text{s}$ $\implies$ **`39d 06h 13m 27s`**
- **Full Wire HEX:**
  ```hex
  14 00 00 00 02 00 53 90 3f 00 00 00 60 17 00 00 07 c2 33 00
  ```

#### Step 6: PTP Response Container (0x9053)
- **Wireshark Frame / EPB Index:** Frame 178, EPB #178
- **Response Code:** `0x2001`
- **TransactionID:** `63` (`0x0000003F`)
- **Total Length:** 12 bytes
- **Full Wire HEX:**
  ```hex
  0c 00 00 00 03 00 01 20 3f 00 00 00
  ```
