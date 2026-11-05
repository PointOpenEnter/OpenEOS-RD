# PTP RECONSTRUCTED TRANSACTIONS AUDIT
**Capture File:** `р62.pcapng` (29,054,644 bytes)  
**Target Device:** Canon EOS R6 Mark II (PID `0x330B`, S/N `183121000830`, FW `1.7.0`)  
**Status:** 100% Verified USBPcap & PTP Reconstruction  

---

## 1. Sequence Overview (Transactions 0 to 40)

Every transaction adheres strictly to the ISO 15740 PTP protocol:
1. **Command Phase (Bulk OUT, EP 0x02):** Initiated by Host PC.
2. **Data Phase (Optional):**
   - **Data OUT (Bulk OUT, EP 0x02):** Parameter payload from Host to Camera.
   - **Data IN (Bulk IN, EP 0x81):** Returned data from Camera to Host.
3. **Response Phase (Bulk IN, EP 0x81):** PTP Response code returned by Camera to Host.

---

## 2. Key Transactions — Byte-Level Breakdown

### Transaction 0: OpenSession
* **Command (Bulk OUT, offset 0x00000048):**
  * Length: 16 bytes (`0x10`)
  * Container: `10 00 00 00 01 00 02 10 00 00 00 00 01 00 00 00`
  * Decoded: Type=1 (Command), OpCode=`0x1002` (OpenSession), TxID=0, Param1=`0x00000001` (SessionID=1)
* **Response (Bulk IN, offset 0x00000090):**
  * Length: 16 bytes (`0x10`)
  * Container: `10 00 00 00 03 00 01 20 00 00 00 00 00 00 00 00`
  * Decoded: Type=3 (Response), ResponseCode=`0x2001` (OK), TxID=0, Param1=`0x00000000`

---

### Transaction 6: SetRemoteMode
* **Command (Bulk OUT, offset 0x00000938):**
  * Length: 16 bytes (`0x10`)
  * Container: `10 00 00 00 01 00 14 91 06 00 00 00 01 00 00 00`
  * Decoded: Type=1, OpCode=`0x9114` (SetRemoteMode), TxID=6, Param1=`0x00000001`
* **Response (Bulk IN, offset 0x00000980):**
  * Length: 12 bytes (`0x0C`)
  * Container: `0c 00 00 00 03 00 01 20 06 00 00 00`
  * Decoded: Type=3, ResponseCode=`0x2001` (OK), TxID=6

---

### Transaction 7: SetEventMode
* **Command (Bulk OUT, offset 0x000009C0):**
  * Length: 16 bytes (`0x10`)
  * Container: `10 00 00 00 01 00 15 91 07 00 00 00 01 00 00 00`
  * Decoded: Type=1, OpCode=`0x9115` (SetEventMode), TxID=7, Param1=`0x00000001`
* **Response (Bulk IN, offset 0x00000A08):**
  * Length: 12 bytes (`0x0C`)
  * Container: `0c 00 00 00 03 00 01 20 07 00 00 00`
  * Decoded: Type=3, ResponseCode=`0x2001` (OK), TxID=7

---

### Transaction 8: GetEvent
* **Command (Bulk OUT, offset 0x00000A48):**
  * Length: 24 bytes (`0x18`)
  * Container: `18 00 00 00 01 00 16 91 08 00 00 00 00 00 00 00 00 00 00 00 01 00 00 00`
  * Decoded: Type=1, OpCode=`0x9116` (GetEvent), TxID=8, Params=[0, 0, 1]
* **Data IN (Bulk IN, offset 0x00000A98):**
  * Length: 512 bytes (12 header + 500 payload)
  * Container: `00 02 00 00 02 00 16 91 08 00 00 00 10 00 00 00 89 c1 00 00 ...`
* **Response (Bulk IN, offset 0x00000CC0):**
  * Length: 12 bytes (`0x0C`), Code=`0x2001` (OK), TxID=8

---

### Transaction 9: Canon Service Auth (Saitama Handshake Phase 1)
* **Command (Bulk OUT, offset 0x00000D00):**
  * Length: 12 bytes (`0x0C`)
  * Container: `0c 00 00 00 01 00 5c 90 09 00 00 00`
  * Decoded: Type=1, OpCode=`0x905C`, TxID=9, Params=[]
* **Data OUT (Bulk OUT, offset 0x00000D40):**
  * Length: 67 bytes (12 header + 55 payload)
  * PTP Header: `43 00 00 00 02 00 5c 90 09 00 00 00`
  * Raw Payload (55 bytes):
    `73 61 69 74 61 6d 61 74 63 68 00 01 00 00 00 04 00 00 00 00 00 00 00 00 00 00 00 01 00 00 00 0c 00 00 00 01 00 00 00 01 00 00 00 67 75 6e 6d 61 66 75 6b 61 79 61 00`
  * Decoded Structure:
    * `bytes[0..10]`: `"saitamatch\0"` (11 bytes, Saitama Plant factory passkey)
    * `uint32[0]`: 1
    * `uint32[1]`: 4
    * `uint32[2]`: 0
    * `uint32[3]`: 0
    * `uint32[4]`: 1
    * `uint32[5]`: 12
    * `uint32[6]`: 1
    * `uint32[7]`: 1
    * `bytes[43..54]`: `"gunmafukaya\0"` (12 bytes, Gunma/Fukaya manufacturing plant token)
* **Response (Bulk IN, offset 0x00000DB8):**
  * Length: 12 bytes (`0x0C`), Code=`0x2001` (OK), TxID=9

---

### Transaction 10: Canon Service Auth (Saitama Handshake Phase 2)
* **Command (Bulk OUT, offset 0x00000DF8):**
  * Length: 12 bytes (`0x0C`), OpCode=`0x905C`, TxID=10, Params=[]
* **Data OUT (Bulk OUT, offset 0x00000E38):**
  * Length: 51 bytes (12 header + 39 payload)
  * Raw Payload (39 bytes):
    `73 61 69 74 61 6d 61 74 63 68 00 01 00 00 00 02 00 00 00 90 15 07 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00`
  * Decoded: `"saitamatch\0"` + uint32(1) + uint32(2) + uint32(`0x00071590` = 464,272) + 4x uint32(0)
* **Response (Bulk IN, offset 0x00000EA0):**
  * Length: 12 bytes (`0x0C`), Code=`0x2001` (OK), TxID=10

---

### Transaction 11: Canon Service Auth (Saitama Handshake Phase 3)
* **Command (Bulk OUT, offset 0x00000EE0):**
  * Length: 12 bytes (`0x0C`), OpCode=`0x905C`, TxID=11, Params=[]
* **Data OUT (Bulk OUT, offset 0x00000F20):**
  * Length: 51 bytes (12 header + 39 payload)
  * Raw Payload (39 bytes):
    `73 61 69 74 61 6d 61 74 63 68 00 01 00 00 00 02 00 00 00 d3 0a 15 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00`
  * Decoded: `"saitamatch\0"` + uint32(1) + uint32(2) + uint32(`0x00150AD3` = 1,379,027) + 4x uint32(0)
* **Response (Bulk IN, offset 0x00000F88):**
  * Length: 12 bytes (`0x0C`), Code=`0x2001` (OK), TxID=11

---

### Transaction 14: FA_TurnOffDisplay
* **Command (Bulk OUT, offset 0x00001364):**
  * Length: 20 bytes (`0x14`), OpCode=`0x9052`, TxID=14, Params=[0, 0]
* **Data OUT (Bulk OUT, offset 0x000013AC):**
  * Length: 34 bytes (12 header + 22 payload)
  * Raw Payload: `46 41 5f 54 75 72 6e 4f 66 66 44 69 73 70 6c 61 79 00 00 00 00 00`
  * Decoded: `"FA_TurnOffDisplay\0"` (18 bytes) + uint32(0)
* **Response (Bulk IN, offset 0x00001400):**
  * Length: 12 bytes (`0x0C`), Code=`0x2001` (OK), TxID=14

---

### Transaction 15: IsFactoryMode
* **Command (Bulk OUT, offset 0x00001440):**
  * Length: 20 bytes (`0x14`), OpCode=`0x9052`, TxID=15, Params=[0, 0]
* **Data OUT (Bulk OUT, offset 0x00001488):**
  * Length: 30 bytes (12 header + 18 payload)
  * Raw Payload: `49 73 46 61 63 74 6f 72 79 4d 6f 64 65 00 00 00 00 00`
  * Decoded: `"IsFactoryMode\0"` (14 bytes) + uint32(0)
* **Response (Bulk IN, offset 0x000014D8):**
  * Length: 12 bytes (`0x0C`), Code=`0x2001` (OK), TxID=15

---

### Transaction 25: Mechanical Shutter Query (FA_GetProperty 0x12000001)
* **Command (Bulk OUT, offset 0x00001D20):**
  * Exact Container Length: 20 bytes (`0x00000014`)
  * Exact Hex: `14 00 00 00 01 00 52 90 19 00 00 00 00 00 00 00 01 00 00 00`
  * Structure:
    * `Length` = 20 (12 bytes base + 8 bytes params)
    * `Type` = 1 (Command)
    * `OpCode` = `0x9052` (Canon VendorCommandSend)
    * `TxID` = 25 (`0x00000019`)
    * `Param 1` = `0x00000000`
    * `Param 2` = `0x00000001`
* **Data OUT (Bulk OUT, offset 0x00001D68):**
  * Exact Container Length: 55 bytes (`0x00000037`)
  * Exact Hex:
    `37 00 00 00 02 00 52 90 19 00 00 00 46 41 5f 47 65 74 50 72 6f 70 65 72 74 79 00 01 00 00 00 02 00 00 00 01 00 00 12 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00`
  * Structure:
    * PTP Header (12 bytes): Len=55, Type=2 (Data), OpCode=`0x9052`, TxID=25
    * Procedure String: `46 41 5f 47 65 74 50 72 6f 70 65 72 74 79 00` (`"FA_GetProperty\0"`, 15 bytes)
    * Field 1 (uint32): `01 00 00 00` (Count = 1)
    * Field 2 (uint32): `02 00 00 00` (Property Data Type = 2 / 32-bit integer property)
    * Field 3 (uint32): `01 00 00 12` (**Property Key = `0x12000001`**, Mechanical Shutter)
    * Field 4..7 (16 bytes): `00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00` (Padding / Buffer descriptors)
* **Response (Bulk IN, offset 0x00001DD0):**
  * Exact Container Length: 16 bytes (`0x00000010`)
  * Exact Hex: `10 00 00 00 03 00 01 20 19 00 00 00 08 00 00 00`
  * Structure:
    * `Length` = 16
    * `Type` = 3 (Response)
    * `ResponseCode` = `0x2001` (`PTP_RC_OK`)
    * `TxID` = 25 (`0x00000019`)
    * `Param 1` = `0x00000008` (Camera indicates: 8 bytes of ready response data)

---

### Transaction 26: Mechanical Shutter Fetch
* **Command (Bulk OUT, offset 0x00001E14):**
  * Exact Container Length: 12 bytes (`0x0000000C`)
  * Exact Hex: `0c 00 00 00 01 00 53 90 1a 00 00 00`
  * Structure:
    * `Length` = 12 (12 bytes base, 0 parameters)
    * `Type` = 1 (Command)
    * `OpCode` = `0x9053` (Canon VendorDataReceive)
    * `TxID` = 26 (`0x0000001A`)
    * `Params` = None (Trigger fetch)
* **Data IN (Bulk IN, offset 0x00001E54):**
  * Exact Container Length: 20 bytes (`0x00000014`)
  * Exact Hex:
    `14 00 00 00 02 00 53 90 1a 00 00 00 11 ed 00 00 00 00 00 00`
  * Structure:
    * PTP Header (12 bytes): Len=20, Type=2 (Data), OpCode=`0x9053`, TxID=26
    * **Data Payload (8 bytes):** `11 ed 00 00 00 00 00 00`
      * `bytes[0..3]` (uint32 Little-Endian): `11 ed 00 00` = `0x0000ED11` = **`60 689`**
      * `bytes[4..7]` (uint32 Little-Endian): `00 00 00 00`
  * **Direction Verification:**
    * USBPcap endpoint: `0x81` (bit 7 set = IN).
    * Direction: Device to Host (Camera $\to$ Host PC).
* **Response (Bulk IN, offset 0x00001E9C):**
  * Exact Container Length: 12 bytes (`0x0C`)
  * Exact Hex: `0c 00 00 00 03 00 01 20 1a 00 00 00`
  * Decoded: Type=3, ResponseCode=`0x2001` (OK), TxID=26

---

### Transaction 31: Total Releases Query (FA_GetProperty 0x12000003)
* **Command (Bulk OUT, offset 0x000023D4):**
  * Length: 20 bytes (`0x14`), OpCode=`0x9052`, TxID=31, Params=[0, 1]
* **Data OUT (Bulk OUT, offset 0x0000241C):**
  * Length: 55 bytes (`0x37`), OpCode=`0x9052`, TxID=31
  * Payload: `"FA_GetProperty\0"` + `01 00 00 00` + `02 00 00 00` + `03 00 00 12` (`0x12000003`) + 16 zero bytes
* **Response (Bulk IN, offset 0x00002484):**
  * Length: 16 bytes (`0x10`), Code=`0x2001` (OK), TxID=31, Param1=`0x00000004` (4 bytes ready)

---

### Transaction 32: Total Releases Fetch
* **Command (Bulk OUT, offset 0x000024C8):**
  * Length: 12 bytes (`0x0C`), OpCode=`0x9053`, TxID=32, Params=[]
* **Data IN (Bulk IN, offset 0x00002508):**
  * Length: 16 bytes (`0x10`) (12 header + 4 payload)
  * Container: `10 00 00 00 02 00 53 90 20 00 00 00 b9 d2 0c 00`
  * **Payload (4 bytes):** `b9 d2 0c 00` = `0x000CD2B9` = **`840 377`**
* **Response (Bulk IN, offset 0x0000254C):**
  * Length: 12 bytes (`0x0C`), Code=`0x2001` (OK), TxID=32

---

### Transaction 33 & 34: Error Incident Log (FA_GetProperty 0x13000000)
* **Command 33 (Bulk OUT, offset 0x0000258C):**
  * Length: 20 bytes, OpCode=`0x9052`, TxID=33, Params=[0, 1]
* **Data OUT 33 (Bulk OUT, offset 0x000025D4):**
  * Length: 55 bytes, `"FA_GetProperty\0"` + Key `0x13000000` (`00 00 00 13`)
* **Response 33 (Bulk IN, offset 0x0000263C):**
  * Length: 16 bytes, Code=`0x2001` (OK), Param1=`0x00000190` (400 bytes ready)
* **Command 34 (Bulk OUT, offset 0x00002680):**
  * Length: 12 bytes, OpCode=`0x9053`, TxID=34, Params=[]
* **Data IN 34 (Bulk IN, offset 0x000026C0):**
  * Length: 412 bytes (12 header + 400 payload)
  * Payload: Camera diagnostic error incident records table.
* **Response 34 (Bulk IN, offset 0x00002890):**
  * Length: 12 bytes, Code=`0x2001` (OK), TxID=34
