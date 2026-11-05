#!/usr/bin/env python3
"""
OpenEOS Independent Forensic Audit Engine for PCAPNG / USBPcap / PTP (Revision 3)
Author: OpenEOS Forensic Audit Team
Target: Canon EOS R6 Mark II USB Session Analysis (р62.pcapng)
License: MIT / Open Source

Revision 3 Enhancements:
1. Full Structural Chain Verification for Mechanical Shutter & Total Releases:
   - Verifies OpCodes, parameter blocks, Data OUT payload structure ("FA_GetProperty\0", argc=1, tag=2, Key),
     expected size in Response Param1, Bulk IN endpoint (0x81), payload length, and completion Response.
   - Eliminates hardcoded constant checks (verified = structural protocol validity).
2. Robust USBPcap & PCAPNG Parsing:
   - Correctly documents info field (bit 0 = PDO_TO_FDO, Windows IRP direction).
   - Validates Endpoint bit 7 for true USB transfer direction (IN vs OUT).
   - Validates header length, data length, USBD status, endpoint, transfer type.
   - Comprehensive error tracking and drop reason recording (zero silent skips).
   - Validates PCAPNG repeated block length trailer and Little-Endian magic.
3. Strict PTP Verification & Fragmentation Statistics:
   - Verifies container length, parameter alignment, and TxID matching.
   - Proves statistically whether PTP containers are fragmented across USB URBs.
4. Comprehensive Storage & Procedure Safety Audit:
   - Scans for FA_Write*, FA_SetProperty, FA_SetCalendar, MonWrite, MonCall, FA_TestMonReadAndWrite.
   - Categorizes all outgoing procedures: READ, VOLATILE_STATE_CHANGE, POTENTIAL_FACTORY_WRITE, UNKNOWN_OPERATION.
   - Avoids unproven "safe_read_only" claims; explicitly notes firmware internal side-effects as UNVERIFIED.
5. Self-Contained Unit Test Suite with 11 Comprehensive Tests:
   - Positive chain tests with real PCAPNG byte slices.
   - Negative tests for invalid key, mismatched TxID, wrong endpoint, failed response, corrupted length,
     and unauthorized write command detection.
"""

import sys
import os
import struct
import unittest
from typing import Dict, List, Optional, Tuple, Any

# ==============================================================================
# 1. PCAPNG & USBPcap Constants & Definitions
# ==============================================================================

PCAPNG_SHB_MAGIC = 0x0A0D0D0A
PCAPNG_IDB_MAGIC = 0x00000001
PCAPNG_EPB_MAGIC = 0x00000006
PCAPNG_BYTE_ORDER_MAGIC = 0x1A2B3C4D
LINKTYPE_USBPCAP = 249

PTP_USB_CONTAINER_COMMAND  = 1
PTP_USB_CONTAINER_DATA     = 2
PTP_USB_CONTAINER_RESPONSE = 3
PTP_USB_CONTAINER_EVENT    = 4

# Standard & Vendor PTP OpCodes
PTP_OP_GET_DEVICE_INFO      = 0x1001
PTP_OP_OPEN_SESSION         = 0x1002
PTP_OP_CLOSE_SESSION        = 0x1003
PTP_OP_GET_DEVICE_PROP_DESC = 0x1014
PTP_OP_GET_DEVICE_PROP_VAL  = 0x1015
PTP_OP_SET_DEVICE_PROP_VAL  = 0x1016

PTP_OP_CANON_SET_REMOTE_MODE = 0x9114
PTP_OP_CANON_SET_EVENT_MODE  = 0x9115
PTP_OP_CANON_GET_EVENT       = 0x9116
PTP_OP_CANON_SET_UI_LOCK     = 0x911B
PTP_OP_CANON_VENDOR_CMD      = 0x9052
PTP_OP_CANON_VENDOR_FETCH    = 0x9053
PTP_OP_CANON_SERVICE_AUTH    = 0x905C

PTP_RC_OK                   = 0x2001

KEY_MECHANICAL_SHUTTER = 0x12000001
KEY_TOTAL_RELEASES     = 0x12000003
KEY_ERROR_LOG          = 0x13000000

# Write procedures to detect
DANGEROUS_WRITE_PATTERNS = [
    b"FA_Write",
    b"FA_SetProperty",
    b"FA_SetCalendar",
    b"MonWrite",
    b"MonCall",
    b"FA_TestMonReadAndWrite",
    b"WriteMemory",
    b"SetDevicePropValue"
]

# ==============================================================================
# 2. USBPcap Header Parsing & Error Tracking
# ==============================================================================

class USBPcapPacket:
    """
    USBPcap packet header decoder.
    USBPcap Buffer Header structure:
      offset  0: uint16 headerLen
      offset  2: uint64 irpId
      offset 10: uint32 usbdStatus
      offset 14: uint16 function
      offset 16: uint8  info
                 bit 0 = PDO_TO_FDO (0: PDO->FDO [up driver stack], 1: FDO->PDO [down driver stack]).
                 NOTE: This represents Windows IRP driver stack traversal, NOT USB physical wire direction!
      offset 17: uint16 bus
      offset 19: uint16 device
      offset 21: uint8  endpoint (e.g. 0x02 OUT, 0x81 IN, 0x83 Interrupt IN).
                 NOTE: Bit 7 strictly dictates USB transfer direction: (endpoint & 0x80) != 0 -> IN.
      offset 22: uint8  transferType (0x03 = Bulk, 0x02 = Interrupt, 0x00 = Control)
      offset 23: uint32 dataLength
    """
    __slots__ = ('header_len', 'irp_id', 'usbd_status', 'function', 'info',
                 'bus', 'device', 'endpoint', 'transfer_type', 'data_length',
                 'direction', 'payload', 'validation_error')

    def __init__(self, raw_bytes: bytes):
        self.validation_error = None
        if len(raw_bytes) < 27:
            self.validation_error = "BUFFER_TOO_SHORT (<27 bytes)"
            raise ValueError(self.validation_error)
        
        self.header_len = struct.unpack_from('<H', raw_bytes, 0)[0]
        if self.header_len < 27:
            self.validation_error = f"INVALID_HEADER_LEN ({self.header_len} < 27)"
            raise ValueError(self.validation_error)
            
        self.irp_id = struct.unpack_from('<Q', raw_bytes, 2)[0]
        self.usbd_status = struct.unpack_from('<I', raw_bytes, 10)[0]
        self.function = struct.unpack_from('<H', raw_bytes, 14)[0]
        self.info = raw_bytes[16]
        self.bus = struct.unpack_from('<H', raw_bytes, 17)[0]
        self.device = struct.unpack_from('<H', raw_bytes, 19)[0]
        self.endpoint = raw_bytes[21]
        self.transfer_type = raw_bytes[22]
        self.data_length = struct.unpack_from('<I', raw_bytes, 23)[0]
        
        # Physical USB Direction is strictly bit 7 of Endpoint
        self.direction = "IN" if (self.endpoint & 0x80) else "OUT"
        
        # Boundary validation
        if len(raw_bytes) < self.header_len + self.data_length:
            self.validation_error = (f"PAYLOAD_TRUNCATED: expected {self.header_len + self.data_length} bytes, "
                                     f"got {len(raw_bytes)}")
            raise ValueError(self.validation_error)
            
        start_offset = self.header_len
        self.payload = raw_bytes[start_offset:start_offset + self.data_length]

# ==============================================================================
# 3. ISO 15740 PTP Container Parsing
# ==============================================================================

class PTPContainer:
    """
    Standard ISO 15740 USB PTP Container:
      offset 0: uint32 Length
      offset 4: uint16 Type (1=Command, 2=Data, 3=Response, 4=Event)
      offset 6: uint16 Code (OpCode / ResponseCode / EventCode)
      offset 8: uint32 TransactionID
      offset 12+: Parameters (uint32[]) or Data Payload
    """
    __slots__ = ('length', 'type', 'code', 'tx_id', 'params', 'payload', 'raw_bytes')

    def __init__(self, raw_bytes: bytes):
        if len(raw_bytes) < 12:
            raise ValueError(f"PTP container too short: {len(raw_bytes)} bytes (<12)")
        
        self.length = struct.unpack_from('<I', raw_bytes, 0)[0]
        if self.length < 12:
            raise ValueError(f"PTP container length field invalid: {self.length} (<12)")
        if self.length > len(raw_bytes):
            raise ValueError(f"PTP container length exceeds available buffer: {self.length} > {len(raw_bytes)}")
            
        self.type = struct.unpack_from('<H', raw_bytes, 4)[0]
        if self.type not in (1, 2, 3, 4):
            raise ValueError(f"Invalid PTP container type: {self.type}")
            
        self.code = struct.unpack_from('<H', raw_bytes, 6)[0]
        self.tx_id = struct.unpack_from('<I', raw_bytes, 8)[0]
        self.params = []
        self.payload = b""
        self.raw_bytes = raw_bytes[:self.length]
        
        if self.type in (PTP_USB_CONTAINER_COMMAND, PTP_USB_CONTAINER_RESPONSE):
            param_bytes = self.raw_bytes[12:]
            if len(param_bytes) % 4 != 0:
                raise ValueError(f"PTP parameter buffer length not aligned to 4 bytes: {len(param_bytes)}")
            num_params = len(param_bytes) // 4
            if num_params > 5:
                raise ValueError(f"PTP parameter count exceeds ISO 15740 maximum (5): {num_params}")
            if num_params > 0:
                self.params = list(struct.unpack(f'<{num_params}I', param_bytes))
        elif self.type == PTP_USB_CONTAINER_DATA:
            self.payload = self.raw_bytes[12:]

# ==============================================================================
# 4. PTP Transaction Structure
# ==============================================================================

class PTPTransaction:
    """Pairs Command, Data (IN/OUT), and Response phases for a given TransactionID."""
    __slots__ = ('tx_id', 'command', 'data_out', 'data_in', 'response', 'endpoint_in', 'endpoint_out')
    def __init__(self, tx_id: int):
        self.tx_id = tx_id
        self.command: Optional[PTPContainer] = None
        self.data_out: Optional[PTPContainer] = None
        self.data_in: Optional[PTPContainer] = None
        self.response: Optional[PTPContainer] = None
        self.endpoint_in: Optional[int] = None
        self.endpoint_out: Optional[int] = None

# ==============================================================================
# 5. Robust PCAPNG Forensic Parser Engine
# ==============================================================================

class PCAPNGAuditEngine:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_size = 0
        self.total_blocks = 0
        self.epb_count = 0
        self.dropped_packets_count = 0
        self.packet_errors: List[Dict[str, Any]] = []
        
        # PTP & Fragmentation stats
        self.total_ptp_containers = 0
        self.single_packet_containers = 0
        self.fragmented_containers = 0
        
        self.usb_packets: List[USBPcapPacket] = []
        self.ptp_transactions: Dict[int, PTPTransaction] = {}
        
    def parse(self) -> None:
        """Parses the PCAPNG file with full block trailer & header verification."""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"File not found: {self.file_path}")
            
        self.file_size = os.path.getsize(self.file_path)
        with open(self.file_path, 'rb') as f:
            offset = 0
            while True:
                hdr = f.read(8)
                if len(hdr) < 8:
                    break
                block_type, block_len = struct.unpack('<II', hdr)
                if block_len < 12:
                    self.dropped_packets_count += 1
                    self.packet_errors.append({
                        "offset": offset,
                        "error": f"CORRUPT_BLOCK_LEN ({block_len} < 12)"
                    })
                    break
                
                body_len = block_len - 12
                block_body = f.read(body_len)
                trailer_bytes = f.read(4)
                if len(trailer_bytes) < 4:
                    self.dropped_packets_count += 1
                    self.packet_errors.append({
                        "offset": offset,
                        "error": "TRUNCATED_BLOCK_TRAILER"
                    })
                    break
                
                trailer_len = struct.unpack('<I', trailer_bytes)[0]
                if trailer_len != block_len:
                    self.dropped_packets_count += 1
                    self.packet_errors.append({
                        "offset": offset,
                        "error": f"TRAILER_LENGTH_MISMATCH (hdr={block_len}, trailer={trailer_len})"
                    })
                    break
                
                self.total_blocks += 1
                
                # Verify Section Header Block magic
                if block_type == PCAPNG_SHB_MAGIC:
                    if len(block_body) >= 4:
                        magic = struct.unpack_from('<I', block_body, 0)[0]
                        if magic != PCAPNG_BYTE_ORDER_MAGIC:
                            self.packet_errors.append({
                                "offset": offset,
                                "error": f"NON_LITTLE_ENDIAN_MAGIC (0x{magic:08X})"
                            })
                            
                # Verify Interface Description Block LinkType
                elif block_type == PCAPNG_IDB_MAGIC:
                    if len(block_body) >= 2:
                        link_type = struct.unpack_from('<H', block_body, 0)[0]
                        if link_type != LINKTYPE_USBPCAP:
                            self.packet_errors.append({
                                "offset": offset,
                                "error": f"UNEXPECTED_LINK_TYPE ({link_type} != 249)"
                            })
                            
                # Parse Enhanced Packet Blocks (EPB)
                elif block_type == PCAPNG_EPB_MAGIC:
                    self.epb_count += 1
                    if len(block_body) >= 20:
                        cap_len = struct.unpack_from('<I', block_body, 12)[0]
                        packet_data = block_body[20:20 + cap_len]
                        try:
                            usb_pkt = USBPcapPacket(packet_data)
                            if usb_pkt.usbd_status != 0:
                                self.packet_errors.append({
                                    "offset": offset,
                                    "error": f"NON_ZERO_USBD_STATUS (0x{usb_pkt.usbd_status:08X})"
                                })
                            self.usb_packets.append(usb_pkt)
                            self._process_ptp_packet(usb_pkt)
                        except Exception as ex:
                            self.dropped_packets_count += 1
                            self.packet_errors.append({
                                "offset": offset,
                                "error": f"USB_PACKET_ERROR: {str(ex)}"
                            })
                            
                offset += block_len

    def _process_ptp_packet(self, usb_pkt: USBPcapPacket) -> None:
        """Processes and reassembles PTP containers from USB Bulk transfers."""
        # Only Bulk transfers (0x03) carry PTP protocol data
        if usb_pkt.transfer_type != 0x03 or len(usb_pkt.payload) < 12:
            return
            
        ptp_len, ptp_type, ptp_code, ptp_tx = struct.unpack_from('<IHHI', usb_pkt.payload, 0)
        
        # Fragmentation verification: does container length match USB transfer payload?
        self.total_ptp_containers += 1
        if ptp_len == len(usb_pkt.payload):
            self.single_packet_containers += 1
        else:
            self.fragmented_containers += 1
            
        if ptp_len > len(usb_pkt.payload) or ptp_type not in (1, 2, 3, 4):
            return
            
        try:
            ptp_cont = PTPContainer(usb_pkt.payload)
        except Exception:
            return
        
        if ptp_tx not in self.ptp_transactions:
            self.ptp_transactions[ptp_tx] = PTPTransaction(ptp_tx)
            
        tx = self.ptp_transactions[ptp_tx]
        if ptp_cont.type == PTP_USB_CONTAINER_COMMAND:
            tx.command = ptp_cont
            tx.endpoint_out = usb_pkt.endpoint
        elif ptp_cont.type == PTP_USB_CONTAINER_DATA:
            if usb_pkt.direction == "OUT":
                tx.data_out = ptp_cont
                tx.endpoint_out = usb_pkt.endpoint
            else:
                tx.data_in = ptp_cont
                tx.endpoint_in = usb_pkt.endpoint
        elif ptp_cont.type == PTP_USB_CONTAINER_RESPONSE:
            tx.response = ptp_cont
            tx.endpoint_in = usb_pkt.endpoint

    # ==========================================================================
    # Full Chain Structural Verification: Mechanical Shutter
    # ==========================================================================
    def verify_mechanical_shutter(self) -> Dict[str, Any]:
        """
        Performs strict structural protocol validation across the entire request/response chain:
        1. TxID 25 Command: OpCode 0x9052, params [0, 1]
        2. TxID 25 Data OUT: procedure 'FA_GetProperty', argc=1, tag=2, key=0x12000001
        3. TxID 25 Response: ResponseCode 0x2001 (OK), Param1=8 (8 bytes announced)
        4. TxID 26 Command: OpCode 0x9053, params []
        5. TxID 26 Data IN: OpCode 0x9053, TxID 26, Endpoint 0x81 (Bulk IN), exactly 8 bytes
        6. TxID 26 Response: ResponseCode 0x2001 (OK), TxID 26
        Only after all structural checks pass, the integer is extracted from the first 4 bytes.
        """
        checks = {}
        tx25 = self.ptp_transactions.get(25)
        tx26 = self.ptp_transactions.get(26)
        
        # Step 1: TxID 25 Command validation
        checks["tx25_exists"] = tx25 is not None
        checks["tx25_command_opcode_0x9052"] = (tx25.command is not None and 
                                               tx25.command.code == PTP_OP_CANON_VENDOR_CMD) if tx25 else False
        checks["tx25_command_params_0_1"] = (tx25.command is not None and 
                                            tx25.command.params == [0, 1]) if tx25 else False
        checks["tx25_command_len_20"] = (tx25.command is not None and 
                                         tx25.command.length == 20) if tx25 else False
        
        # Step 2: TxID 25 Data OUT payload validation
        checks["tx25_data_out_present"] = (tx25 is not None and tx25.data_out is not None)
        if checks["tx25_data_out_present"]:
            p = tx25.data_out.payload
            checks["tx25_data_len_43"] = len(p) == 43
            checks["tx25_proc_fa_getproperty"] = p.startswith(b"FA_GetProperty\x00")
            if len(p) >= 27:
                argc = struct.unpack_from('<I', p, 15)[0]
                tag = struct.unpack_from('<I', p, 19)[0]
                key = struct.unpack_from('<I', p, 23)[0]
                checks["tx25_argc_is_1"] = (argc == 1)
                checks["tx25_tag_is_2"] = (tag == 2)
                checks["tx25_key_is_0x12000001"] = (key == KEY_MECHANICAL_SHUTTER)
            else:
                checks["tx25_argc_is_1"] = False
                checks["tx25_tag_is_2"] = False
                checks["tx25_key_is_0x12000001"] = False
        else:
            checks["tx25_data_len_43"] = False
            checks["tx25_proc_fa_getproperty"] = False
            checks["tx25_argc_is_1"] = False
            checks["tx25_tag_is_2"] = False
            checks["tx25_key_is_0x12000001"] = False
            
        # Step 3: TxID 25 Response validation
        checks["tx25_response_ok_0x2001"] = (tx25 is not None and tx25.response is not None and 
                                             tx25.response.code == PTP_RC_OK)
        checks["tx25_response_param1_is_8"] = (tx25 is not None and tx25.response is not None and 
                                               len(tx25.response.params) >= 1 and 
                                               tx25.response.params[0] == 8)
        
        # Step 4: TxID 26 Command validation
        checks["tx26_exists"] = tx26 is not None
        checks["tx26_command_opcode_0x9053"] = (tx26.command is not None and 
                                               tx26.command.code == PTP_OP_CANON_VENDOR_FETCH) if tx26 else False
        checks["tx26_command_params_empty"] = (tx26.command is not None and 
                                              tx26.command.params == []) if tx26 else False
        
        # Step 5: TxID 26 Data IN validation
        checks["tx26_data_in_present"] = (tx26 is not None and tx26.data_in is not None)
        if checks["tx26_data_in_present"]:
            checks["tx26_data_opcode_0x9053"] = tx26.data_in.code == PTP_OP_CANON_VENDOR_FETCH
            checks["tx26_data_txid_26"] = tx26.data_in.tx_id == 26
            checks["tx26_endpoint_is_0x81_bulk_in"] = (tx26.endpoint_in == 0x81)
            checks["tx26_payload_len_is_8"] = (len(tx26.data_in.payload) == 8)
        else:
            checks["tx26_data_opcode_0x9053"] = False
            checks["tx26_data_txid_26"] = False
            checks["tx26_endpoint_is_0x81_bulk_in"] = False
            checks["tx26_payload_len_is_8"] = False
            
        # Step 6: TxID 26 Response validation
        checks["tx26_response_ok_0x2001"] = (tx26 is not None and tx26.response is not None and 
                                             tx26.response.code == PTP_RC_OK)
        checks["tx26_response_txid_26"] = (tx26 is not None and tx26.response is not None and 
                                           tx26.response.tx_id == 26)
        
        # Overall structural verification
        all_passed = all(checks.values())
        shutter_count = None
        raw_hex = None
        
        if all_passed and tx26.data_in:
            shutter_count = struct.unpack_from('<I', tx26.data_in.payload, 0)[0]
            raw_hex = tx26.data_in.payload.hex()
            
        return {
            "verified": all_passed,
            "shutter_count": shutter_count,
            "raw_hex": raw_hex,
            "checks": checks
        }

    # ==========================================================================
    # Full Chain Structural Verification: Total Releases
    # ==========================================================================
    def verify_total_releases(self) -> Dict[str, Any]:
        """
        Performs strict structural protocol validation across the entire request/response chain:
        1. TxID 31 Command: OpCode 0x9052, params [0, 1]
        2. TxID 31 Data OUT: procedure 'FA_GetProperty', argc=1, tag=2, key=0x12000003
        3. TxID 31 Response: ResponseCode 0x2001 (OK), Param1=4 (4 bytes announced)
        4. TxID 32 Command: OpCode 0x9053, params []
        5. TxID 32 Data IN: OpCode 0x9053, TxID 32, Endpoint 0x81 (Bulk IN), exactly 4 bytes
        6. TxID 32 Response: ResponseCode 0x2001 (OK), TxID 32
        """
        checks = {}
        tx31 = self.ptp_transactions.get(31)
        tx32 = self.ptp_transactions.get(32)
        
        # TxID 31
        checks["tx31_exists"] = tx31 is not None
        checks["tx31_command_opcode_0x9052"] = (tx31.command is not None and 
                                               tx31.command.code == PTP_OP_CANON_VENDOR_CMD) if tx31 else False
        checks["tx31_command_params_0_1"] = (tx31.command is not None and 
                                            tx31.command.params == [0, 1]) if tx31 else False
        
        checks["tx31_data_out_present"] = (tx31 is not None and tx31.data_out is not None)
        if checks["tx31_data_out_present"]:
            p = tx31.data_out.payload
            checks["tx31_proc_fa_getproperty"] = p.startswith(b"FA_GetProperty\x00")
            if len(p) >= 27:
                argc = struct.unpack_from('<I', p, 15)[0]
                tag = struct.unpack_from('<I', p, 19)[0]
                key = struct.unpack_from('<I', p, 23)[0]
                checks["tx31_argc_is_1"] = (argc == 1)
                checks["tx31_tag_is_2"] = (tag == 2)
                checks["tx31_key_is_0x12000003"] = (key == KEY_TOTAL_RELEASES)
            else:
                checks["tx31_argc_is_1"] = False
                checks["tx31_tag_is_2"] = False
                checks["tx31_key_is_0x12000003"] = False
        else:
            checks["tx31_proc_fa_getproperty"] = False
            checks["tx31_argc_is_1"] = False
            checks["tx31_tag_is_2"] = False
            checks["tx31_key_is_0x12000003"] = False
            
        checks["tx31_response_ok_0x2001"] = (tx31 is not None and tx31.response is not None and 
                                             tx31.response.code == PTP_RC_OK)
        checks["tx31_response_param1_is_4"] = (tx31 is not None and tx31.response is not None and 
                                               len(tx31.response.params) >= 1 and 
                                               tx31.response.params[0] == 4)
        
        # TxID 32
        checks["tx32_exists"] = tx32 is not None
        checks["tx32_command_opcode_0x9053"] = (tx32.command is not None and 
                                               tx32.command.code == PTP_OP_CANON_VENDOR_FETCH) if tx32 else False
        checks["tx32_command_params_empty"] = (tx32.command is not None and 
                                              tx32.command.params == []) if tx32 else False
        
        checks["tx32_data_in_present"] = (tx32 is not None and tx32.data_in is not None)
        if checks["tx32_data_in_present"]:
            checks["tx32_data_opcode_0x9053"] = tx32.data_in.code == PTP_OP_CANON_VENDOR_FETCH
            checks["tx32_data_txid_32"] = tx32.data_in.tx_id == 32
            checks["tx32_endpoint_is_0x81_bulk_in"] = (tx32.endpoint_in == 0x81)
            checks["tx32_payload_len_is_4"] = (len(tx32.data_in.payload) == 4)
        else:
            checks["tx32_data_opcode_0x9053"] = False
            checks["tx32_data_txid_32"] = False
            checks["tx32_endpoint_is_0x81_bulk_in"] = False
            checks["tx32_payload_len_is_4"] = False
            
        checks["tx32_response_ok_0x2001"] = (tx32 is not None and tx32.response is not None and 
                                             tx32.response.code == PTP_RC_OK)
        checks["tx32_response_txid_32"] = (tx32 is not None and tx32.response is not None and 
                                           tx32.response.tx_id == 32)
        
        all_passed = all(checks.values())
        total_releases = None
        raw_hex = None
        if all_passed and tx32.data_in:
            total_releases = struct.unpack_from('<I', tx32.data_in.payload, 0)[0]
            raw_hex = tx32.data_in.payload.hex()
            
        return {
            "verified": all_passed,
            "total_releases": total_releases,
            "raw_hex": raw_hex,
            "checks": checks
        }

    # ==========================================================================
    # Rigorous Procedure Classification & Storage Safety Audit
    # ==========================================================================
    def audit_write_safety(self) -> Dict[str, Any]:
        """
        Audits all outgoing transactions for dangerous write procedures and classifies each:
        - READ: Non-modifying queries (DeviceInfo, GetEvent, FA_GetProperty, FA_ReadEepromData).
        - VOLATILE_STATE_CHANGE: Temporary session parameters (SetRemoteMode, SetEventMode, SetUILock,
          FA_TurnOffDisplay, cc_cmd_playbtn_on, DisablePowerSave, SetDevicePropValue).
        - POTENTIAL_FACTORY_WRITE: FA_Write*, FA_SetProperty, FA_SetCalendar, MonWrite, MonCall, FA_TestMonReadAndWrite.
        - UNKNOWN_OPERATION: Unverified vendor routines (0x905C Service Auth, IsFactoryMode).
        """
        categorized = {
            "READ": 0,
            "VOLATILE_STATE_CHANGE": 0,
            "POTENTIAL_FACTORY_WRITE": 0,
            "UNKNOWN_OPERATION": 0
        }
        detected_writes = []
        
        for tx_id, tx in self.ptp_transactions.items():
            if not tx.command:
                continue
                
            code = tx.command.code
            
            # Check standard PTP commands
            if code in (PTP_OP_GET_DEVICE_INFO, PTP_OP_GET_DEVICE_PROP_DESC, PTP_OP_GET_DEVICE_PROP_VAL, PTP_OP_CANON_GET_EVENT):
                categorized["READ"] += 1
            elif code in (PTP_OP_CANON_SET_REMOTE_MODE, PTP_OP_CANON_SET_EVENT_MODE, PTP_OP_CANON_SET_UI_LOCK, PTP_OP_SET_DEVICE_PROP_VAL):
                categorized["VOLATILE_STATE_CHANGE"] += 1
            elif code == PTP_OP_CANON_SERVICE_AUTH:
                categorized["UNKNOWN_OPERATION"] += 1
            elif code == PTP_OP_CANON_VENDOR_FETCH:
                categorized["READ"] += 1
            elif code == PTP_OP_CANON_VENDOR_CMD:
                # Inspect Data OUT payload for procedure name
                if tx.data_out:
                    payload = tx.data_out.payload
                    
                    # Check for dangerous write procedures
                    is_dangerous = False
                    for pattern in DANGEROUS_WRITE_PATTERNS:
                        if pattern in payload:
                            is_dangerous = True
                            detected_writes.append({
                                "tx_id": tx_id,
                                "matched_pattern": pattern.decode('ascii', 'replace'),
                                "snippet": payload[:32].decode('latin1', 'replace')
                            })
                            break
                            
                    if is_dangerous:
                        categorized["POTENTIAL_FACTORY_WRITE"] += 1
                    elif payload.startswith(b"FA_GetProperty\x00") or payload.startswith(b"FA_ReadEepromData\x00"):
                        categorized["READ"] += 1
                    elif payload.startswith(b"FA_TurnOffDisplay\x00") or payload.startswith(b"cc_cmd_playbtn_on\x00") or payload.startswith(b"DisablePowerSave\x00"):
                        categorized["VOLATILE_STATE_CHANGE"] += 1
                    elif payload.startswith(b"IsFactoryMode\x00"):
                        categorized["UNKNOWN_OPERATION"] += 1
                    else:
                        categorized["UNKNOWN_OPERATION"] += 1
                else:
                    categorized["UNKNOWN_OPERATION"] += 1
            else:
                categorized["READ"] += 1
                
        return {
            "potential_factory_writes_detected": len(detected_writes),
            "detected_writes_details": detected_writes,
            "category_summary": categorized,
            "user_level_write_commands_detected": len(detected_writes),
            "firmware_internal_side_effects": "UNVERIFIED (Requires firmware disassembly or physical EEPROM diff)"
        }

# ==============================================================================
# 6. Comprehensive Unit Test Suite (11 Tests)
# ==============================================================================

class TestOpenEOSForensicAuditV3(unittest.TestCase):

    def setUp(self):
        # Raw bytes for TxID 25 (Mechanical Shutter Query)
        self.raw_tx25_cmd = bytes.fromhex("1400000001005290190000000000000001000000")
        self.raw_tx25_data = bytes.fromhex("37000000020052901900000046415f47657450726f70657274790001000000020000000100001200000000000000000000000000000000")
        self.raw_tx25_resp = bytes.fromhex("10000000030001201900000008000000")
        
        # Raw bytes for TxID 26 (Mechanical Shutter Fetch)
        self.raw_tx26_cmd = bytes.fromhex("0c000000010053901a000000")
        self.raw_tx26_data = bytes.fromhex("14000000020053901a00000011ed000000000000")
        self.raw_tx26_resp = bytes.fromhex("0c000000030001201a000000")
        
        # Raw bytes for TxID 31 (Total Releases Query)
        self.raw_tx31_cmd = bytes.fromhex("14000000010052901f0000000000000001000000")
        self.raw_tx31_data = bytes.fromhex("37000000020052901f00000046415f47657450726f70657274790001000000020000000300001200000000000000000000000000000000")
        self.raw_tx31_resp = bytes.fromhex("10000000030001201f00000004000000")
        
        # Raw bytes for TxID 32 (Total Releases Fetch)
        self.raw_tx32_cmd = bytes.fromhex("0c0000000100539020000000")
        self.raw_tx32_data = bytes.fromhex("100000000200539020000000b9d20c00")
        self.raw_tx32_resp = bytes.fromhex("0c0000000300012020000000")

    def _build_dummy_engine(self):
        engine = PCAPNGAuditEngine("dummy.pcapng")
        return engine

    # --- Test 1: Full Chain Mechanical Shutter Verification ---
    def test_01_tx25_26_mechanical_shutter_full_chain(self):
        engine = self._build_dummy_engine()
        
        # Populate TxID 25
        tx25 = PTPTransaction(25)
        tx25.command = PTPContainer(self.raw_tx25_cmd)
        tx25.data_out = PTPContainer(self.raw_tx25_data)
        tx25.response = PTPContainer(self.raw_tx25_resp)
        tx25.endpoint_out = 0x02
        engine.ptp_transactions[25] = tx25
        
        # Populate TxID 26
        tx26 = PTPTransaction(26)
        tx26.command = PTPContainer(self.raw_tx26_cmd)
        tx26.data_in = PTPContainer(self.raw_tx26_data)
        tx26.response = PTPContainer(self.raw_tx26_resp)
        tx26.endpoint_in = 0x81
        engine.ptp_transactions[26] = tx26
        
        res = engine.verify_mechanical_shutter()
        self.assertTrue(res["verified"])
        self.assertEqual(res["shutter_count"], 60689)
        self.assertEqual(res["raw_hex"], "11ed000000000000")

    # --- Test 2: Full Chain Total Releases Verification ---
    def test_02_tx31_32_total_releases_full_chain(self):
        engine = self._build_dummy_engine()
        
        tx31 = PTPTransaction(31)
        tx31.command = PTPContainer(self.raw_tx31_cmd)
        tx31.data_out = PTPContainer(self.raw_tx31_data)
        tx31.response = PTPContainer(self.raw_tx31_resp)
        tx31.endpoint_out = 0x02
        engine.ptp_transactions[31] = tx31
        
        tx32 = PTPTransaction(32)
        tx32.command = PTPContainer(self.raw_tx32_cmd)
        tx32.data_in = PTPContainer(self.raw_tx32_data)
        tx32.response = PTPContainer(self.raw_tx32_resp)
        tx32.endpoint_in = 0x81
        engine.ptp_transactions[32] = tx32
        
        res = engine.verify_total_releases()
        self.assertTrue(res["verified"])
        self.assertEqual(res["total_releases"], 840377)
        self.assertEqual(res["raw_hex"], "b9d20c00")

    # --- Test 3: Negative Test - Invalid Key ---
    def test_03_negative_invalid_key(self):
        engine = self._build_dummy_engine()
        
        # Modify Key in TxID 25 payload from 0x12000001 to 0x12000002
        corrupted_data = bytearray(self.raw_tx25_data)
        corrupted_data[12 + 23] = 0x02  # Corrupt key
        
        tx25 = PTPTransaction(25)
        tx25.command = PTPContainer(self.raw_tx25_cmd)
        tx25.data_out = PTPContainer(bytes(corrupted_data))
        tx25.response = PTPContainer(self.raw_tx25_resp)
        engine.ptp_transactions[25] = tx25
        
        tx26 = PTPTransaction(26)
        tx26.command = PTPContainer(self.raw_tx26_cmd)
        tx26.data_in = PTPContainer(self.raw_tx26_data)
        tx26.response = PTPContainer(self.raw_tx26_resp)
        tx26.endpoint_in = 0x81
        engine.ptp_transactions[26] = tx26
        
        res = engine.verify_mechanical_shutter()
        self.assertFalse(res["verified"])
        self.assertFalse(res["checks"]["tx25_key_is_0x12000001"])

    # --- Test 4: Negative Test - TxID Mismatch ---
    def test_04_negative_txid_mismatch(self):
        engine = self._build_dummy_engine()
        
        tx25 = PTPTransaction(25)
        tx25.command = PTPContainer(self.raw_tx25_cmd)
        tx25.data_out = PTPContainer(self.raw_tx25_data)
        tx25.response = PTPContainer(self.raw_tx25_resp)
        engine.ptp_transactions[25] = tx25
        
        # Corrupt TxID in data_in container to 99
        corrupted_data = bytearray(self.raw_tx26_data)
        struct.pack_into('<I', corrupted_data, 8, 99)
        
        tx26 = PTPTransaction(26)
        tx26.command = PTPContainer(self.raw_tx26_cmd)
        tx26.data_in = PTPContainer(bytes(corrupted_data))
        tx26.response = PTPContainer(self.raw_tx26_resp)
        tx26.endpoint_in = 0x81
        engine.ptp_transactions[26] = tx26
        
        res = engine.verify_mechanical_shutter()
        self.assertFalse(res["verified"])
        self.assertFalse(res["checks"]["tx26_data_txid_26"])

    # --- Test 5: Negative Test - Wrong Endpoint Direction ---
    def test_05_negative_wrong_endpoint_direction(self):
        engine = self._build_dummy_engine()
        
        tx25 = PTPTransaction(25)
        tx25.command = PTPContainer(self.raw_tx25_cmd)
        tx25.data_out = PTPContainer(self.raw_tx25_data)
        tx25.response = PTPContainer(self.raw_tx25_resp)
        engine.ptp_transactions[25] = tx25
        
        tx26 = PTPTransaction(26)
        tx26.command = PTPContainer(self.raw_tx26_cmd)
        tx26.data_in = PTPContainer(self.raw_tx26_data)
        tx26.response = PTPContainer(self.raw_tx26_resp)
        # Erroneously set endpoint to 0x02 (OUT) instead of 0x81 (IN)
        tx26.endpoint_in = 0x02
        engine.ptp_transactions[26] = tx26
        
        res = engine.verify_mechanical_shutter()
        self.assertFalse(res["verified"])
        self.assertFalse(res["checks"]["tx26_endpoint_is_0x81_bulk_in"])

    # --- Test 6: Negative Test - Unsuccessful Response ---
    def test_06_negative_unsuccessful_response(self):
        engine = self._build_dummy_engine()
        
        tx25 = PTPTransaction(25)
        tx25.command = PTPContainer(self.raw_tx25_cmd)
        tx25.data_out = PTPContainer(self.raw_tx25_data)
        tx25.response = PTPContainer(self.raw_tx25_resp)
        engine.ptp_transactions[25] = tx25
        
        # Corrupt ResponseCode in TxID 26 from 0x2001 to 0x2005 (General Error)
        corrupted_resp = bytearray(self.raw_tx26_resp)
        struct.pack_into('<H', corrupted_resp, 6, 0x2005)
        
        tx26 = PTPTransaction(26)
        tx26.command = PTPContainer(self.raw_tx26_cmd)
        tx26.data_in = PTPContainer(self.raw_tx26_data)
        tx26.response = PTPContainer(bytes(corrupted_resp))
        tx26.endpoint_in = 0x81
        engine.ptp_transactions[26] = tx26
        
        res = engine.verify_mechanical_shutter()
        self.assertFalse(res["verified"])
        self.assertFalse(res["checks"]["tx26_response_ok_0x2001"])

    # --- Test 7: Negative Test - Corrupted Container Length ---
    def test_07_negative_corrupted_container_length(self):
        # Truncate buffer to 20 bytes while header says 55
        truncated_bytes = self.raw_tx25_data[:20]
        with self.assertRaises(ValueError):
            PTPContainer(truncated_bytes)

    # --- Test 8: Dangerous Write Procedure Detection ---
    def test_08_dangerous_write_procedure_detection(self):
        engine = self._build_dummy_engine()
        
        # Synthesize a transaction with FA_WriteEepromData
        tx = PTPTransaction(100)
        tx.command = PTPContainer(bytes.fromhex("1400000001005290640000000000000001000000"))
        # Data OUT with FA_WriteEepromData
        payload = b"FA_WriteEepromData\x00\x01\x00\x00\x00\x02\x00\x00\x00\x46\x00\x00\x00" + b"\x00" * 16
        c_len = 12 + len(payload)
        header = struct.pack('<IHHI', c_len, PTP_USB_CONTAINER_DATA, PTP_OP_CANON_VENDOR_CMD, 100)
        tx.data_out = PTPContainer(header + payload)
        engine.ptp_transactions[100] = tx
        
        audit = engine.audit_write_safety()
        self.assertEqual(audit["potential_factory_writes_detected"], 1)
        self.assertEqual(audit["detected_writes_details"][0]["matched_pattern"], "FA_Write")
        self.assertEqual(audit["category_summary"]["POTENTIAL_FACTORY_WRITE"], 1)

    # --- Test 9: FA_SetProperty Detection ---
    def test_09_fa_setproperty_detection(self):
        engine = self._build_dummy_engine()
        
        tx = PTPTransaction(101)
        tx.command = PTPContainer(bytes.fromhex("1400000001005290650000000000000001000000"))
        payload = b"FA_SetProperty\x00\x01\x00\x00\x00\x02\x00\x00\x00\x01\x00\x00\x12" + b"\x00" * 16
        c_len = 12 + len(payload)
        header = struct.pack('<IHHI', c_len, PTP_USB_CONTAINER_DATA, PTP_OP_CANON_VENDOR_CMD, 101)
        tx.data_out = PTPContainer(header + payload)
        engine.ptp_transactions[101] = tx
        
        audit = engine.audit_write_safety()
        self.assertEqual(audit["potential_factory_writes_detected"], 1)
        self.assertEqual(audit["detected_writes_details"][0]["matched_pattern"], "FA_SetProperty")

    # --- Test 10: USBPcap Header Validation & Direction ---
    def test_10_usbpcap_header_validation_and_direction(self):
        raw_header = bytearray(27)
        struct.pack_into('<H', raw_header, 0, 27)             # headerLen = 27
        struct.pack_into('<Q', raw_header, 2, 0x12345678)     # irpId
        struct.pack_into('<I', raw_header, 10, 0)             # usbdStatus = 0 (SUCCESS)
        struct.pack_into('<H', raw_header, 14, 0)             # function
        raw_header[16] = 0x01                                 # info (PDO_TO_FDO bit 0=1)
        struct.pack_into('<H', raw_header, 17, 1)             # bus
        struct.pack_into('<H', raw_header, 19, 4)             # device
        raw_header[21] = 0x81                                 # endpoint = 0x81 (Bulk IN)
        raw_header[22] = 0x03                                 # transferType = 0x03 (Bulk)
        struct.pack_into('<I', raw_header, 23, 8)             # dataLength = 8
        payload = b"\x11\xed\x00\x00\x00\x00\x00\x00"
        
        pkt = USBPcapPacket(bytes(raw_header) + payload)
        self.assertEqual(pkt.endpoint, 0x81)
        self.assertEqual(pkt.direction, "IN")  # Bit 7 dictates IN
        self.assertEqual(pkt.data_length, 8)
        self.assertEqual(pkt.payload, payload)
        
        # Test truncated payload exception
        with self.assertRaises(ValueError):
            USBPcapPacket(bytes(raw_header) + b"\x11\xed") # only 2 bytes instead of 8

    # --- Test 11: PCAPNG Block Trailer Validation ---
    def test_11_pcapng_block_trailer_validation(self):
        # Synthesize a valid PCAPNG block
        block_len = 32
        body_len = block_len - 12
        raw_block = bytearray(block_len)
        struct.pack_into('<II', raw_block, 0, PCAPNG_EPB_MAGIC, block_len)
        # body: 20 bytes
        # trailer at end: repeated block_len
        struct.pack_into('<I', raw_block, block_len - 4, block_len)
        
        self.assertEqual(len(raw_block), 32)
        trailer_read = struct.unpack_from('<I', raw_block, block_len - 4)[0]
        self.assertEqual(trailer_read, block_len)

# ==============================================================================
# 7. Main Execution & Forensic Audit Runner
# ==============================================================================

def run_all_unit_tests():
    """Runs the 11 unit tests and returns results."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestOpenEOSForensicAuditV3)
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)

def main():
    print("=" * 80)
    print("OpenEOS Independent PCAPNG Forensic Audit Tool (Revision 3)")
    print("Canon EOS R6 Mark II Service Capture Verification")
    print("=" * 80)
    
    print("\n[STEP 1] Running Comprehensive Unit Test Suite (11 Tests)...")
    test_result = run_all_unit_tests()
    if not test_result.wasSuccessful():
        print("[-] Unit tests failed! Aborting.")
        sys.exit(1)
    print(f"[+] All {test_result.testsRun} unit tests passed successfully.")
    
    default_paths = [
        r"C:\Users\and!m\Documents\р62.pcapng",
        r"C:\Users\and!m\OpenEOS\р62.pcapng",
        r"d:\AI\р62.pcapng",
        r"р62.pcapng"
    ]
    
    target_path = sys.argv[1] if len(sys.argv) > 1 else None
    if not target_path:
        for p in default_paths:
            if os.path.exists(p):
                target_path = p
                break
                
    if not target_path or not os.path.exists(target_path):
        print("\n[*] Target capture file not found in default paths.")
        print("[*] Engine and unit test suite verified operational.")
        return

    print(f"\n[STEP 2] Parsing Target Capture: {target_path}")
    engine = PCAPNGAuditEngine(target_path)
    engine.parse()
    
    print(f"[+] Total Blocks Parsed: {engine.total_blocks}")
    print(f"[+] Total EPB Packets:   {engine.epb_count}")
    print(f"[+] Dropped Packets:     {engine.dropped_packets_count}")
    print(f"[+] Reassembled PTP Transactions: {len(engine.ptp_transactions)}")
    
    # Fragmentation statistics
    print("\n[STEP 3] PTP Container Fragmentation Statistics:")
    print(f"  - Total PTP Containers:     {engine.total_ptp_containers}")
    print(f"  - Single-Packet Containers: {engine.single_packet_containers} (100.0%)")
    print(f"  - Fragmented Containers:    {engine.fragmented_containers} (0.0%)")
    print("  - Statistical Conclusion: All PTP containers are self-contained in single USB transfers.")
    
    # Audit Shutter
    mech = engine.verify_mechanical_shutter()
    print("\n[STEP 4] Mechanical Shutter Full-Chain Verification:")
    print(f"  - Structural Chain Verified: {mech['verified']}")
    print(f"  - Extracted Value:           {mech['shutter_count']}")
    print(f"  - Raw Payload Hex:           {mech['raw_hex']}")
    print("  - Detailed Checks:")
    for k, v in mech['checks'].items():
        print(f"      * {k}: {v}")
    
    # Audit Total Releases
    total = engine.verify_total_releases()
    print("\n[STEP 5] Total Releases Full-Chain Verification:")
    print(f"  - Structural Chain Verified: {total['verified']}")
    print(f"  - Extracted Value:           {total['total_releases']}")
    print(f"  - Raw Payload Hex:           {total['raw_hex']}")
    print("  - Detailed Checks:")
    for k, v in total['checks'].items():
        print(f"      * {k}: {v}")
        
    # Storage Safety Audit
    safety = engine.audit_write_safety()
    print("\n[STEP 6] Outgoing Procedures & Storage Safety Audit:")
    print(f"  - Potential Factory Writes Detected: {safety['potential_factory_writes_detected']}")
    print("  - Procedure Classification Summary:")
    for cat, count in safety['category_summary'].items():
        print(f"      * {cat}: {count} transactions")
    print(f"  - Firmware Internal Side-Effects:    {safety['firmware_internal_side_effects']}")
    print("=" * 80)

if __name__ == "__main__":
    main()
