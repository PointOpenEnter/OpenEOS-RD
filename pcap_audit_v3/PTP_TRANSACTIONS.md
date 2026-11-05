# PTP RECONSTRUCTED TRANSACTIONS AUDIT (REVISION 3)
**Capture File:** `р62.pcapng` (29,054,644 bytes)  
**Target Device:** Canon EOS R6 Mark II (PID `0x330B`, S/N `183121000830`, FW `1.7.0`)  
**Standard:** ISO 15740 PTP Protocol Specification  

---

## 1. Sequence Architecture

Every transaction conforms to standard PTP transaction state phases:
1. **Command Phase (Bulk OUT, EP 0x02):** Initiated by Host PC.
2. **Data Phase (Optional):**
   - **Data OUT (Bulk OUT, EP 0x02):** Parameter block passed from Host to Camera.
   - **Data IN (Bulk IN, EP 0x81):** Data payload returned from Camera to Host.
3. **Response Phase (Bulk IN, EP 0x81):** Completion response code returned by Camera to Host.

---

## 2. Key Transactions Dissection

### Transaction 0: OpenSession
* **Command (Bulk OUT, offset 0x00000048):**
  * Container Length: 16 bytes (`0x10`).
  * Hex: `10 00 00 00 01 00 02 10 00 00 00 00 01 00 00 00`.
  * Decoded: Type=1 (Command), OpCode=`0x1002` (OpenSession), TxID=0, Param1=`0x00000001` (SessionID=1).
* **Response (Bulk IN, offset 0x00000090):**
  * Container Length: 16 bytes (`0x10`).
  * Hex: `10 00 00 00 03 00 01 20 00 00 00 00 00 00 00 00`.
  * Decoded: Type=3 (Response), ResponseCode=`0x2001` (OK), TxID=0, Param1=`0x00000000`.

---

### Transaction 2: SetDevicePropValue (Host OS Identification)
* **Command (Bulk OUT, offset 0x00000380):**
  * Container Length: 16 bytes, OpCode=`0x1016`, TxID=2, Param1=`0x0000D406` (MTP Device Property).
* **Data OUT (Bulk OUT, offset 0x000003C8):**
  * Container Length: 107 bytes.
  * Header (12 bytes) + Payload (95 bytes): UTF-16 MTP client version string (`/Windows/10...`).
* **Response (Bulk IN, offset 0x00000468):**
  * Container Length: 12 bytes, ResponseCode=`0x2001` (OK), TxID=2.

---

### Transaction 6: SetRemoteMode (PC Tethered Control)
* **Command (Bulk OUT, offset 0x00000938):**
  * Container Length: 16 bytes, OpCode=`0x9114`, TxID=6, Param1=`0x00000001` (Enable Remote Mode).
* **Response (Bulk IN, offset 0x00000980):**
  * Container Length: 12 bytes, ResponseCode=`0x2001` (OK), TxID=6.

---

### Transaction 7: SetEventMode (Asynchronous Event System)
* **Command (Bulk OUT, offset 0x000009C0):**
  * Container Length: 16 bytes, OpCode=`0x9115`, TxID=7, Param1=`0x00000001` (Enable Event Mode).
* **Response (Bulk IN, offset 0x00000A08):**
  * Container Length: 12 bytes, ResponseCode=`0x2001` (OK), TxID=7.

---

### Transaction 8: GetEvent (Drain Event Queue)
* **Command (Bulk OUT, offset 0x00000A48):**
  * Container Length: 24 bytes, OpCode=`0x9116`, TxID=8, Params=[0, 0, 1].
* **Data IN (Bulk IN, offset 0x00000A98):**
  * Container Length: 512 bytes (12 header + 500 payload): Initial event queue records.
* **Response (Bulk IN, offset 0x00000CC0):**
  * Container Length: 12 bytes, ResponseCode=`0x2001` (OK), TxID=8.

---

### Transaction 9: Canon Service Auth Phase 1
* **Command (Bulk OUT, offset 0x00000D00):**
  * Container Length: 12 bytes, OpCode=`0x905C`, TxID=9, Params=[].
* **Data OUT (Bulk OUT, offset 0x00000D40):**
  * Container Length: **67 bytes** (12 header + 55 payload).
  * Payload Hex (55 bytes):
    `73 61 69 74 61 6d 61 74 63 68 00 01 00 00 00 04 00 00 00 00 00 00 00 00 00 00 00 01 00 00 00 0c 00 00 00 01 00 00 00 01 00 00 00 67 75 6e 6d 61 66 75 6b 61 79 61 00`
  * Decoded: `"saitamatch\0"` (11B) + `[1, 4, 0, 0, 1, 12, 1, 1]` (32B) + `"gunmafukaya\0"` (12B).
* **Response (Bulk IN, offset 0x00000DB8):**
  * Container Length: 12 bytes, ResponseCode=`0x2001` (OK), TxID=9.

---

### Transaction 10: Canon Service Auth Phase 2
* **Command (Bulk OUT, offset 0x00000DF8):**
  * Container Length: 12 bytes, OpCode=`0x905C`, TxID=10, Params=[].
* **Data OUT (Bulk OUT, offset 0x00000E38):**
  * Container Length: **51 bytes** (12 header + 39 payload).
  * Payload Hex (39 bytes):
    `73 61 69 74 61 6d 61 74 63 68 00 01 00 00 00 02 00 00 00 90 15 07 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00`
  * Decoded: `"saitamatch\0"` (11B) + uint32(1) + uint32(2) + uint32(`0x00071590` = 464,272) + 16 zero bytes.
* **Response (Bulk IN, offset 0x00000EA0):**
  * Container Length: 12 bytes, ResponseCode=`0x2001` (OK), TxID=10.

---

### Transaction 11: Canon Service Auth Phase 3
* **Command (Bulk OUT, offset 0x00000EE0):**
  * Container Length: 12 bytes, OpCode=`0x905C`, TxID=11, Params=[].
* **Data OUT (Bulk OUT, offset 0x00000F20):**
  * Container Length: **51 bytes** (12 header + 39 payload).
  * Payload Hex (39 bytes):
    `73 61 69 74 61 6d 61 74 63 68 00 01 00 00 00 02 00 00 00 d3 0a 15 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00`
  * Decoded: `"saitamatch\0"` (11B) + uint32(1) + uint32(2) + uint32(`0x00150AD3` = 1,379,027) + 16 zero bytes.
* **Response (Bulk IN, offset 0x00000F88):**
  * Container Length: 12 bytes, ResponseCode=`0x2001` (OK), TxID=11.

---

### Transaction 14: FA_TurnOffDisplay
* **Command (Bulk OUT, offset 0x00001364):**
  * Container Length: 20 bytes (`0x14`), OpCode=`0x9052`, TxID=14, Params=[0, 0].
* **Data OUT (Bulk OUT, offset 0x000013AC):**
  * Container Length: **34 bytes** (12 header + 22 payload).
  * Payload Hex: `46 41 5f 54 75 72 6e 4f 66 66 44 69 73 70 6c 61 79 00 00 00 00 00` (`"FA_TurnOffDisplay\0"` + uint32(0)).
* **Response (Bulk IN, offset 0x00001400):**
  * Container Length: 12 bytes, ResponseCode=`0x2001` (OK), TxID=14.

---

### Transaction 15: IsFactoryMode Dispatch
* **Command (Bulk OUT, offset 0x00001440):**
  * Container Length: 20 bytes (`0x14`), OpCode=`0x9052`, TxID=15, Params=[0, 0].
* **Data OUT (Bulk OUT, offset 0x00001488):**
  * Container Length: **30 bytes** (12 header + 18 payload).
  * Payload Hex: `49 73 46 61 63 74 6f 72 79 4d 6f 64 65 00 00 00 00 00` (`"IsFactoryMode\0"` + uint32(0)).
* **Response (Bulk IN, offset 0x000014D8):**
  * Container Length: 12 bytes, ResponseCode=`0x2001` (OK), TxID=15.
  * Note: Concludes with 0 data return bytes.

---

### Transaction 16 & 17: Factory Configuration Descriptor
* **TxID 16 Command (Bulk OUT, offset 0x00001518):**
  * Container Length: 20 bytes, OpCode=`0x9052`, TxID=16, Params=[0, 1].
* **TxID 16 Data OUT (Bulk OUT, offset 0x00001560):**
  * Container Length: **55 bytes** (12 header + 43 payload): `"FA_GetProperty\0"` with Property Key `0x0100001D`.
* **TxID 16 Response (Bulk IN, offset 0x000015C8):**
  * Container Length: 16 bytes, ResponseCode=`0x2001` (OK), Param1=`0x00000050` (80 bytes ready).
* **TxID 17 Command (Bulk OUT, offset 0x0000160C):**
  * Container Length: 24 bytes, OpCode=`0x9053`, TxID=17, Params=[0, 0, 1].
* **TxID 17 Data IN (Bulk IN, offset 0x00001658):**
  * Container Length: 92 bytes (12 header + 80 payload: `00 00 00 00 ... ff ff ff ff`).
* **TxID 17 Response (Bulk IN, offset 0x000016E8):**
  * Container Length: 12 bytes, ResponseCode=`0x2001` (OK), TxID=17.

---

### Transaction 18: SetUILock (Lock User Interface)
* **Command (Bulk OUT, offset 0x00001728):**
  * Container Length: 16 bytes, OpCode=`0x911B`, TxID=18, Param1=`0x00000001`.
* **Response (Bulk IN, offset 0x00001770):**
  * Container Length: 12 bytes, ResponseCode=`0x2001` (OK), TxID=18.

---

### Transaction 25: Mechanical Shutter Query (FA_GetProperty 0x12000001)
* **Command (Bulk OUT, offset 0x00001D20):**
  * Container Length: **20 bytes (`0x00000014`)**.
  * Raw Bytes: `14 00 00 00 01 00 52 90 19 00 00 00 00 00 00 00 01 00 00 00`.
  * Decoded: Type=1, OpCode=`0x9052`, TxID=25, Params=[0, 1].
* **Data OUT (Bulk OUT, offset 0x00001D68):**
  * Container Length: **55 bytes (`0x00000037`)** (12 header + 43 payload).
  * Payload Breakdown:
    * `"FA_GetProperty\0"` (15 bytes)
    * `01 00 00 00` (uint32: 1)
    * `02 00 00 00` (uint32: 2, Numeric Tag)
    * `01 00 00 12` (uint32: `0x12000001`, Mechanical Shutter)
    * 16 zero bytes.
* **Response (Bulk IN, offset 0x00001DD0):**
  * Container Length: 16 bytes, ResponseCode=`0x2001` (OK), Param1=`0x00000008` (8 bytes ready).

---

### Transaction 26: Mechanical Shutter Fetch
* **Command (Bulk OUT, offset 0x00001E14):**
  * Container Length: **12 bytes (`0x0000000C`)**.
  * Raw Bytes: `0c 00 00 00 01 00 53 90 1a 00 00 00`.
  * Decoded: Type=1, OpCode=`0x9053`, TxID=26, Params=[].
* **Data IN (Bulk IN, offset 0x00001E54):**
  * Container Length: **20 bytes (`0x00000014`)** (12 header + 8 payload).
  * Raw Payload: `11 ed 00 00 00 00 00 00`.
  * Decoded: Little-Endian `0x0000ED11` = **`60,689`**.
* **Response (Bulk IN, offset 0x00001E9C):**
  * Container Length: 12 bytes, ResponseCode=`0x2001` (OK), TxID=26.

---

### Transaction 31 & 32: Total Releases (FA_GetProperty 0x12000003)
* **TxID 31 Command & Data OUT (Bulk OUT):**
  * Container Length: 55 bytes, Payload: `"FA_GetProperty\0"` with Key `0x12000003`.
* **TxID 31 Response:** ResponseCode=`0x2001`, Param1=`0x00000004` (4 bytes ready).
* **TxID 32 Command (Bulk OUT):** Container Length: 12 bytes, OpCode=`0x9053`, Params=[].
* **TxID 32 Data IN (Bulk IN, offset 0x00002508):**
  * Container Length: 16 bytes (12 header + 4 payload).
  * Raw Payload: `b9 d2 0c 00` $\to$ Little-Endian `0x000CD2B9` = **`840,377`**.
* **TxID 32 Response:** Container Length: 12 bytes, ResponseCode=`0x2001`, TxID=32.

---

### Transaction 33 & 34: Error Incident Log (FA_GetProperty 0x13000000)
* **TxID 33:** Requests Key `0x13000000`. Response announces 400 bytes ready (`Param1 = 0x00000190`).
* **TxID 34:** Returns 400 bytes structured error logs (`Err 60`, `Err 70`).

---

### Transaction 37: Virtual Playback Keypress (cc_cmd_playbtn_on)
* **Command (Bulk OUT, offset 0x000029E8):**
  * Container Length: 20 bytes (`0x14`), OpCode=`0x9052`, TxID=37, Params=[0, 0].
* **Data OUT (Bulk OUT, offset 0x00002A30):**
  * Container Length: **34 bytes** (12 header + 22 payload).
  * Payload Hex: `63 63 5f 63 6d 64 5f 70 6c 61 79 62 74 6e 5f 6f 6e 00 00 00 00 00` (`"cc_cmd_playbtn_on\0"` + uint32(0)).
* **Response (Bulk IN, offset 0x00002A88):**
  * Container Length: 12 bytes, ResponseCode=`0x2001` (OK), TxID=37.
  * Purpose: Injects a virtual keypress event to force the camera subsystem out of standby/capture into playback state.

---

### Transaction 38: Inhibit Auto Power-Saving (DisablePowerSave)
* **Command (Bulk OUT, offset 0x00002AC8):**
  * Container Length: 20 bytes (`0x14`), OpCode=`0x9052`, TxID=38, Params=[0, 0].
* **Data OUT (Bulk OUT, offset 0x00002B10):**
  * Container Length: **57 bytes** (12 header + 45 payload).
  * Payload Hex: `"DisablePowerSave\0"` (17 bytes) + 28 bytes binary parameters (`01 00 00 00 02 00 00 00 00 00 00 00 ...`).
* **Response (Bulk IN, offset 0x00002B7C):**
  * Container Length: 12 bytes, ResponseCode=`0x2001` (OK), TxID=38.
  * Purpose: Masks hardware auto-power-off timers during the prolonged EEPROM extraction sequence.

---

### Transaction 39 & 40: Initiation of EEPROM Diagnostic Memory Dump
* **TxID 39 Command (Bulk OUT, offset 0x00002BBC):**
  * Container Length: 20 bytes (`0x14`), OpCode=`0x9052`, TxID=39, Params=[0, 1].
* **TxID 39 Data OUT (Bulk OUT, offset 0x00002C04):**
  * Container Length: **58 bytes** (12 header + 46 payload).
  * Payload Hex: `"FA_ReadEepromData\0"` (18 bytes) + `uint32(2)` (argc) + `uint32(0)` (Offset 0) + `uint32(256)` (Chunk Size) + 16 zero padding bytes.
* **TxID 39 Response (Bulk IN, offset 0x00002C70):**
  * Container Length: 16 bytes, ResponseCode=`0x2001` (OK), Param1=`0x00000100` (256 bytes ready). TxID=39.
* **TxID 40 Command (Bulk OUT, offset 0x00002CB4):**
  * Container Length: 12 bytes (`0x0C`), OpCode=`0x9053`, TxID=40, Params=[].
* **TxID 40 Data IN (Bulk IN, offset 0x00002CF4):**
  * Container Length: **268 bytes** (12 header + 256 payload).
  * Transmitted across USB Endpoint `0x81` (Bulk IN). First 256-byte chunk of camera diagnostic EEPROM.
* **TxID 40 Response (Bulk IN, offset 0x00002E34):**
  * Container Length: 12 bytes, ResponseCode=`0x2001` (OK), TxID=40.
