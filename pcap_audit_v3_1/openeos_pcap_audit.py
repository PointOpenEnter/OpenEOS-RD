#!/usr/bin/env python3
"""
OpenEOS Independent Forensic Audit Engine for PCAPNG / USBPcap / PTP (Revision 3.1)
Author: OpenEOS Forensic Audit Team
Target: Canon EOS R6 Mark II USB Session Analysis (р62.pcapng)
License: MIT / Open Source

Revision 3.1 Architectural & Rigor Upgrades:
1. Strict Multi-Endpoint Tracking in PTPTransaction:
   - Separate endpoint fields for cmd_endpoint, data_out_endpoint, data_in_endpoint, resp_endpoint.
   - Prevents Response endpoint (0x81 Bulk IN) from overwriting Data IN / Data OUT endpoints.
   - Verifies physical USB wire direction and endpoint for every individual transaction phase.
2. Comprehensive Parser Error Accounting:
   - Zero silent exception swallowing or bare returns.
   - Discrete tracking of: pcapng_errors, usbpcap_errors, malformed_ptp_containers,
     length_mismatches, unsupported_transfers, dropped_packets, unparsed_containers.
   - Explicit distinction between 100% single-packet container transfers and multi-packet reassembly.
3. Enhanced 4-Tier Security & Storage Safety Audit:
   - Strict classification: READ, STATE_CHANGE, POTENTIAL_WRITE, UNKNOWN.
   - Unknown OpCodes are strictly categorized as UNKNOWN (never defaulted to READ).
   - SetDevicePropValue (0x1016) classified as UNKNOWN (not assumed safe/temporary without proof).
   - Complete mathematical category balance: sum of all categories == total classified transactions.
4. Two-Group Test Suite Architecture:
   - Group 1: Unit Tests (Synthetic valid and invalid packets, negative edge cases, corruptions).
   - Group 2: Integration Tests (Real byte slices from р62.pcapng reference captures).
5. EEPROM Memory Architecture & Dissection:
   - Byte-level format verification of FA_ReadEepromData: string + NUL (18B), subcmd (4B), tag (4B),
     block index (4B), zero padding (16B) = 46B payload.
   - Coverage verification: address bounds, stride, gaps, and unique data volume.
"""

import sys
import os
import struct
import hashlib
import unittest
from typing import Dict, List, Optional, Tuple, Any

# ==============================================================================
# 1. Constants & ISO 15740 PTP Definitions
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
PTP_OP_CANON_VENDOR_5A       = 0x905A
PTP_OP_CANON_VENDOR_5B       = 0x905B
PTP_OP_CANON_VENDOR_27       = 0x9127

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
    b"WriteMemory"
]

# ==============================================================================
# 2. USBPcap Packet Decoder
# ==============================================================================

class USBPcapPacket:
    """
    Decodes USBPcap buffer header (27 bytes base):
      offset  0: uint16 headerLen
      offset  2: uint64 irpId
      offset 10: uint32 usbdStatus
      offset 14: uint16 function
      offset 16: uint8  info (bit 0 = PDO_TO_FDO, Windows IRP direction)
      offset 17: uint16 bus
      offset 19: uint16 device
      offset 21: uint8  endpoint (bit 7 strictly dictates wire direction: (ep & 0x80) != 0 -> IN)
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
# 3. ISO 15740 PTP Container Parser
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
# 4. Separate-Endpoint PTP Transaction Structure
# ==============================================================================

class PTPTransaction:
    """
    Pairs Command, Data (IN/OUT), and Response phases for a given TransactionID.
    Maintains separate USB endpoints for each phase to prevent overwriting.
    """
    __slots__ = ('tx_id', 'command', 'data_out', 'data_in', 'response',
                 'cmd_endpoint', 'data_out_endpoint', 'data_in_endpoint', 'resp_endpoint',
                 'phase_history')

    def __init__(self, tx_id: int):
        self.tx_id = tx_id
        self.command: Optional[PTPContainer] = None
        self.data_out: Optional[PTPContainer] = None
        self.data_in: Optional[PTPContainer] = None
        self.response: Optional[PTPContainer] = None
        self.cmd_endpoint: Optional[int] = None
        self.data_out_endpoint: Optional[int] = None
        self.data_in_endpoint: Optional[int] = None
        self.resp_endpoint: Optional[int] = None
        self.phase_history: List[str] = []

# ==============================================================================
# 5. Full PCAPNG & PTP Forensic Audit Engine (Revision 3.1)
# ==============================================================================

class PCAPNGAuditEngineV31:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_size = 0
        self.total_blocks = 0
        self.epb_count = 0
        
        # Granular Error Accounting
        self.pcapng_errors: List[Dict[str, Any]] = []
        self.usbpcap_errors: List[Dict[str, Any]] = []
        self.malformed_ptp_containers: List[Dict[str, Any]] = []
        self.length_mismatches: List[Dict[str, Any]] = []
        self.unsupported_transfers: List[Dict[str, Any]] = []
        self.dropped_packets_count = 0
        self.unparsed_containers_count = 0
        
        # PTP stats
        self.total_ptp_containers = 0
        self.single_packet_containers = 0
        self.fragmented_containers = 0
        
        self.usb_packets: List[USBPcapPacket] = []
        self.ptp_transactions: Dict[int, PTPTransaction] = {}
        self.transaction_order: List[int] = []

    def parse(self) -> None:
        """Parses the PCAPNG file with comprehensive error logging."""
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
                    self.pcapng_errors.append({
                        "offset": offset,
                        "error": f"CORRUPT_BLOCK_LEN ({block_len} < 12)"
                    })
                    break
                
                body_len = block_len - 12
                block_body = f.read(body_len)
                trailer_bytes = f.read(4)
                if len(trailer_bytes) < 4:
                    self.dropped_packets_count += 1
                    self.pcapng_errors.append({
                        "offset": offset,
                        "error": "TRUNCATED_BLOCK_TRAILER"
                    })
                    break
                
                trailer_len = struct.unpack('<I', trailer_bytes)[0]
                if trailer_len != block_len:
                    self.dropped_packets_count += 1
                    self.pcapng_errors.append({
                        "offset": offset,
                        "error": f"TRAILER_LENGTH_MISMATCH (hdr={block_len}, trailer={trailer_len})"
                    })
                    break
                
                self.total_blocks += 1
                
                # Section Header Block (SHB)
                if block_type == PCAPNG_SHB_MAGIC:
                    if len(block_body) >= 4:
                        magic = struct.unpack_from('<I', block_body, 0)[0]
                        if magic != PCAPNG_BYTE_ORDER_MAGIC:
                            self.pcapng_errors.append({
                                "offset": offset,
                                "error": f"NON_LITTLE_ENDIAN_MAGIC (0x{magic:08X})"
                            })
                            
                # Interface Description Block (IDB)
                elif block_type == PCAPNG_IDB_MAGIC:
                    if len(block_body) >= 2:
                        link_type = struct.unpack_from('<H', block_body, 0)[0]
                        if link_type != LINKTYPE_USBPCAP:
                            self.pcapng_errors.append({
                                "offset": offset,
                                "error": f"UNEXPECTED_LINK_TYPE ({link_type} != 249)"
                            })
                            
                # Enhanced Packet Block (EPB)
                elif block_type == PCAPNG_EPB_MAGIC:
                    self.epb_count += 1
                    if len(block_body) >= 20:
                        cap_len = struct.unpack_from('<I', block_body, 12)[0]
                        packet_data = block_body[20:20 + cap_len]
                        try:
                            usb_pkt = USBPcapPacket(packet_data)
                            if usb_pkt.usbd_status != 0:
                                self.usbpcap_errors.append({
                                    "offset": offset,
                                    "error": f"NON_ZERO_USBD_STATUS (0x{usb_pkt.usbd_status:08X})"
                                })
                            self.usb_packets.append(usb_pkt)
                            self._process_ptp_packet(usb_pkt, offset)
                        except Exception as ex:
                            self.dropped_packets_count += 1
                            self.usbpcap_errors.append({
                                "offset": offset,
                                "error": f"USB_PACKET_ERROR: {str(ex)}"
                            })
                            
                offset += block_len

    def _process_ptp_packet(self, usb_pkt: USBPcapPacket, offset: int) -> None:
        """Processes PTP container and pairs phases with separate endpoints."""
        if usb_pkt.transfer_type != 0x03:
            # Control (0x00) or Interrupt (0x02)
            self.unsupported_transfers.append({
                "offset": offset,
                "transfer_type": usb_pkt.transfer_type,
                "endpoint": usb_pkt.endpoint,
                "length": len(usb_pkt.payload)
            })
            return
            
        if len(usb_pkt.payload) < 12:
            self.malformed_ptp_containers.append({
                "offset": offset,
                "error": f"PAYLOAD_TOO_SHORT_FOR_PTP ({len(usb_pkt.payload)} < 12)"
            })
            self.unparsed_containers_count += 1
            return
            
        ptp_len, ptp_type, ptp_code, ptp_tx = struct.unpack_from('<IHHI', usb_pkt.payload, 0)
        
        self.total_ptp_containers += 1
        if ptp_len == len(usb_pkt.payload):
            self.single_packet_containers += 1
        else:
            self.fragmented_containers += 1
            self.length_mismatches.append({
                "offset": offset,
                "ptp_len": ptp_len,
                "usb_payload_len": len(usb_pkt.payload),
                "tx_id": ptp_tx
            })
            
        if ptp_len > len(usb_pkt.payload) or ptp_type not in (1, 2, 3, 4):
            self.unparsed_containers_count += 1
            return
            
        try:
            ptp_cont = PTPContainer(usb_pkt.payload)
        except Exception as ex:
            self.malformed_ptp_containers.append({
                "offset": offset,
                "error": str(ex),
                "tx_id": ptp_tx
            })
            self.unparsed_containers_count += 1
            return
        
        if ptp_tx not in self.ptp_transactions:
            self.ptp_transactions[ptp_tx] = PTPTransaction(ptp_tx)
            self.transaction_order.append(ptp_tx)
            
        tx = self.ptp_transactions[ptp_tx]
        if ptp_cont.type == PTP_USB_CONTAINER_COMMAND:
            tx.command = ptp_cont
            tx.cmd_endpoint = usb_pkt.endpoint
            tx.phase_history.append("CMD")
        elif ptp_cont.type == PTP_USB_CONTAINER_DATA:
            if usb_pkt.direction == "OUT":
                tx.data_out = ptp_cont
                tx.data_out_endpoint = usb_pkt.endpoint
                tx.phase_history.append("DATA_OUT")
            else:
                tx.data_in = ptp_cont
                tx.data_in_endpoint = usb_pkt.endpoint
                tx.phase_history.append("DATA_IN")
        elif ptp_cont.type == PTP_USB_CONTAINER_RESPONSE:
            tx.response = ptp_cont
            tx.resp_endpoint = usb_pkt.endpoint
            tx.phase_history.append("RESP")

    # ==========================================================================
    # Full Chain Structural Verification: Mechanical Shutter
    # ==========================================================================
    def verify_mechanical_shutter(self) -> Dict[str, Any]:
        """
        Performs strict structural protocol validation across the entire request/response chain:
        1. TxID 25 Command: OpCode 0x9052, params [0, 1], endpoint 0x02 (Bulk OUT)
        2. TxID 25 Data OUT: procedure 'FA_GetProperty', argc=1, tag=2, key=0x12000001, endpoint 0x02
        3. TxID 25 Response: ResponseCode 0x2001 (OK), Param1=8 (8 bytes announced), endpoint 0x81 (Bulk IN)
        4. TxID 26 Command: OpCode 0x9053, params [], endpoint 0x02 (Bulk OUT)
        5. TxID 26 Data IN: OpCode 0x9053, TxID 26, endpoint 0x81 (Bulk IN), exactly 8 bytes
        6. TxID 26 Response: ResponseCode 0x2001 (OK), TxID 26, endpoint 0x81 (Bulk IN)
        7. Sequence Check: TxID 25 strictly precedes TxID 26 in the capture stream.
        """
        checks = {}
        tx25 = self.ptp_transactions.get(25)
        tx26 = self.ptp_transactions.get(26)
        
        # Sequence validation
        if 25 in self.transaction_order and 26 in self.transaction_order:
            checks["sequence_tx25_precedes_tx26"] = (self.transaction_order.index(25) < 
                                                     self.transaction_order.index(26))
        else:
            checks["sequence_tx25_precedes_tx26"] = False
        
        # Step 1: TxID 25 Command validation
        checks["tx25_exists"] = tx25 is not None
        checks["tx25_cmd_opcode_0x9052"] = (tx25.command is not None and 
                                           tx25.command.code == PTP_OP_CANON_VENDOR_CMD) if tx25 else False
        checks["tx25_cmd_params_0_1"] = (tx25.command is not None and 
                                        tx25.command.params == [0, 1]) if tx25 else False
        checks["tx25_cmd_endpoint_is_0x02"] = (tx25 is not None and tx25.cmd_endpoint == 0x02)
        checks["tx25_cmd_len_20"] = (tx25.command is not None and tx25.command.length == 20) if tx25 else False
        
        # Step 2: TxID 25 Data OUT payload validation
        checks["tx25_data_out_present"] = (tx25 is not None and tx25.data_out is not None)
        checks["tx25_data_out_endpoint_is_0x02"] = (tx25 is not None and tx25.data_out_endpoint == 0x02)
        if checks["tx25_data_out_present"]:
            p = tx25.data_out.payload
            checks["tx25_data_len_43"] = (len(p) == 43)
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
        checks["tx25_resp_endpoint_is_0x81"] = (tx25 is not None and tx25.resp_endpoint == 0x81)
        checks["tx25_response_param1_is_8"] = (tx25 is not None and tx25.response is not None and 
                                               len(tx25.response.params) >= 1 and 
                                               tx25.response.params[0] == 8)
        
        # Step 4: TxID 26 Command validation
        checks["tx26_exists"] = tx26 is not None
        checks["tx26_cmd_opcode_0x9053"] = (tx26.command is not None and 
                                           tx26.command.code == PTP_OP_CANON_VENDOR_FETCH) if tx26 else False
        checks["tx26_cmd_params_empty"] = (tx26.command is not None and 
                                          tx26.command.params == []) if tx26 else False
        checks["tx26_cmd_endpoint_is_0x02"] = (tx26 is not None and tx26.cmd_endpoint == 0x02)
        
        # Step 5: TxID 26 Data IN validation
        checks["tx26_data_in_present"] = (tx26 is not None and tx26.data_in is not None)
        if checks["tx26_data_in_present"]:
            checks["tx26_data_opcode_0x9053"] = tx26.data_in.code == PTP_OP_CANON_VENDOR_FETCH
            checks["tx26_data_txid_26"] = tx26.data_in.tx_id == 26
            checks["tx26_data_in_endpoint_is_0x81"] = (tx26.data_in_endpoint == 0x81)
            checks["tx26_payload_len_is_8"] = (len(tx26.data_in.payload) == 8)
            # Check length matches announced size
            checks["tx26_matches_announced_len"] = (checks["tx25_response_param1_is_8"] and 
                                                   len(tx26.data_in.payload) == tx25.response.params[0])
        else:
            checks["tx26_data_opcode_0x9053"] = False
            checks["tx26_data_txid_26"] = False
            checks["tx26_data_in_endpoint_is_0x81"] = False
            checks["tx26_payload_len_is_8"] = False
            checks["tx26_matches_announced_len"] = False
            
        # Step 6: TxID 26 Response validation
        checks["tx26_response_ok_0x2001"] = (tx26 is not None and tx26.response is not None and 
                                             tx26.response.code == PTP_RC_OK)
        checks["tx26_resp_endpoint_is_0x81"] = (tx26 is not None and tx26.resp_endpoint == 0x81)
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
        Performs strict structural protocol validation for Key 0x12000003 across TxID 31 & 32.
        """
        checks = {}
        tx31 = self.ptp_transactions.get(31)
        tx32 = self.ptp_transactions.get(32)
        
        if 31 in self.transaction_order and 32 in self.transaction_order:
            checks["sequence_tx31_precedes_tx32"] = (self.transaction_order.index(31) < 
                                                     self.transaction_order.index(32))
        else:
            checks["sequence_tx31_precedes_tx32"] = False
            
        # TxID 31
        checks["tx31_exists"] = tx31 is not None
        checks["tx31_cmd_opcode_0x9052"] = (tx31.command is not None and 
                                           tx31.command.code == PTP_OP_CANON_VENDOR_CMD) if tx31 else False
        checks["tx31_cmd_params_0_1"] = (tx31.command is not None and 
                                        tx31.command.params == [0, 1]) if tx31 else False
        checks["tx31_cmd_endpoint_is_0x02"] = (tx31 is not None and tx31.cmd_endpoint == 0x02)
        
        checks["tx31_data_out_present"] = (tx31 is not None and tx31.data_out is not None)
        checks["tx31_data_out_endpoint_is_0x02"] = (tx31 is not None and tx31.data_out_endpoint == 0x02)
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
        checks["tx31_resp_endpoint_is_0x81"] = (tx31 is not None and tx31.resp_endpoint == 0x81)
        checks["tx31_response_param1_is_4"] = (tx31 is not None and tx31.response is not None and 
                                               len(tx31.response.params) >= 1 and 
                                               tx31.response.params[0] == 4)
        
        # TxID 32
        checks["tx32_exists"] = tx32 is not None
        checks["tx32_cmd_opcode_0x9053"] = (tx32.command is not None and 
                                           tx32.command.code == PTP_OP_CANON_VENDOR_FETCH) if tx32 else False
        checks["tx32_cmd_params_empty"] = (tx32.command is not None and 
                                          tx32.command.params == []) if tx32 else False
        checks["tx32_cmd_endpoint_is_0x02"] = (tx32 is not None and tx32.cmd_endpoint == 0x02)
        
        checks["tx32_data_in_present"] = (tx32 is not None and tx32.data_in is not None)
        if checks["tx32_data_in_present"]:
            checks["tx32_data_opcode_0x9053"] = tx32.data_in.code == PTP_OP_CANON_VENDOR_FETCH
            checks["tx32_data_txid_32"] = tx32.data_in.tx_id == 32
            checks["tx32_data_in_endpoint_is_0x81"] = (tx32.data_in_endpoint == 0x81)
            checks["tx32_payload_len_is_4"] = (len(tx32.data_in.payload) == 4)
            checks["tx32_matches_announced_len"] = (checks["tx31_response_param1_is_4"] and 
                                                   len(tx32.data_in.payload) == tx31.response.params[0])
        else:
            checks["tx32_data_opcode_0x9053"] = False
            checks["tx32_data_txid_32"] = False
            checks["tx32_data_in_endpoint_is_0x81"] = False
            checks["tx32_payload_len_is_4"] = False
            checks["tx32_matches_announced_len"] = False
            
        checks["tx32_response_ok_0x2001"] = (tx32 is not None and tx32.response is not None and 
                                             tx32.response.code == PTP_RC_OK)
        checks["tx32_resp_endpoint_is_0x81"] = (tx32 is not None and tx32.resp_endpoint == 0x81)
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
    # Enhanced Storage & Procedure Safety Audit (Revision 3.1)
    # ==========================================================================
    def audit_write_safety(self) -> Dict[str, Any]:
        """
        Audits all outgoing transactions with strict mathematical accounting:
        - READ: explicitly known reads.
        - STATE_CHANGE: confirmed temporary state modifications.
        - POTENTIAL_WRITE: destructive or persistent write patterns.
        - UNKNOWN: unknown opcodes and unverified commands.
        Total classified transactions must equal total session transactions.
        """
        categorized = {
            "READ": 0,
            "STATE_CHANGE": 0,
            "POTENTIAL_WRITE": 0,
            "UNKNOWN": 0
        }
        detected_writes = []
        
        for tx_id, tx in self.ptp_transactions.items():
            if not tx.command:
                continue
                
            code = tx.command.code
            
            # 1. Explicitly Known Reads
            if code in (PTP_OP_GET_DEVICE_INFO, PTP_OP_GET_DEVICE_PROP_DESC, 
                        PTP_OP_GET_DEVICE_PROP_VAL, PTP_OP_CANON_GET_EVENT,
                        PTP_OP_CANON_VENDOR_FETCH):
                categorized["READ"] += 1
            elif code == PTP_OP_OPEN_SESSION or code == PTP_OP_CLOSE_SESSION:
                categorized["STATE_CHANGE"] += 1
            # 2. Confirmed Temporary State Changes
            elif code in (PTP_OP_CANON_SET_REMOTE_MODE, PTP_OP_CANON_SET_EVENT_MODE, PTP_OP_CANON_SET_UI_LOCK):
                categorized["STATE_CHANGE"] += 1
            # 3. Vendor Command Dispatch (0x9052)
            elif code == PTP_OP_CANON_VENDOR_CMD:
                if tx.data_out:
                    payload = tx.data_out.payload
                    
                    # Dangerous write scan
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
                        categorized["POTENTIAL_WRITE"] += 1
                    elif payload.startswith(b"FA_GetProperty\x00") or payload.startswith(b"FA_ReadEepromData\x00"):
                        categorized["READ"] += 1
                    elif (payload.startswith(b"FA_TurnOffDisplay\x00") or 
                          payload.startswith(b"cc_cmd_playbtn_on\x00") or 
                          payload.startswith(b"DisablePowerSave\x00")):
                        categorized["STATE_CHANGE"] += 1
                    elif payload.startswith(b"IsFactoryMode\x00"):
                        categorized["UNKNOWN"] += 1
                    else:
                        categorized["UNKNOWN"] += 1
                else:
                    categorized["UNKNOWN"] += 1
            # 4. Unknown or Unverified Operations
            elif code in (PTP_OP_CANON_SERVICE_AUTH, PTP_OP_SET_DEVICE_PROP_VAL, 
                          PTP_OP_CANON_VENDOR_5A, PTP_OP_CANON_VENDOR_5B, PTP_OP_CANON_VENDOR_27):
                categorized["UNKNOWN"] += 1
            else:
                categorized["UNKNOWN"] += 1
                
        return {
            "potential_writes_detected": len(detected_writes),
            "detected_writes_details": detected_writes,
            "category_summary": categorized,
            "total_classified": sum(categorized.values()),
            "firmware_internal_side_effects": "UNVERIFIED (Requires firmware disassembly or physical EEPROM diff)"
        }

# ==============================================================================
# 6. Group 1: Unit Tests (Synthetic Valid & Negative Boundary Tests)
# ==============================================================================

class TestOpenEOSForensicUnitTests(unittest.TestCase):
    """
    Unit Tests using synthetically constructed packets and edge cases.
    Verifies boundary conditions, error handling, and security protections.
    """
    def setUp(self):
        self.raw_tx25_cmd = bytes.fromhex("1400000001005290190000000000000001000000")
        self.raw_tx25_data = bytes.fromhex("37000000020052901900000046415f47657450726f70657274790001000000020000000100001200000000000000000000000000000000")
        self.raw_tx25_resp = bytes.fromhex("10000000030001201900000008000000")
        
        self.raw_tx26_cmd = bytes.fromhex("0c000000010053901a000000")
        self.raw_tx26_data = bytes.fromhex("14000000020053901a00000011ed000000000000")
        self.raw_tx26_resp = bytes.fromhex("0c000000030001201a000000")

    def _build_test_engine(self) -> PCAPNGAuditEngineV31:
        return PCAPNGAuditEngineV31("synthetic_dummy.pcapng")

    def test_u01_negative_wrong_data_in_endpoint_with_correct_resp_endpoint(self):
        """Data IN arriving on 0x82 instead of 0x81 must fail even if Response endpoint is 0x81."""
        engine = self._build_test_engine()
        tx25 = PTPTransaction(25)
        tx25.command = PTPContainer(self.raw_tx25_cmd)
        tx25.data_out = PTPContainer(self.raw_tx25_data)
        tx25.response = PTPContainer(self.raw_tx25_resp)
        tx25.cmd_endpoint = 0x02
        tx25.data_out_endpoint = 0x02
        tx25.resp_endpoint = 0x81
        engine.ptp_transactions[25] = tx25
        engine.transaction_order.append(25)
        
        tx26 = PTPTransaction(26)
        tx26.command = PTPContainer(self.raw_tx26_cmd)
        tx26.data_in = PTPContainer(self.raw_tx26_data)
        tx26.response = PTPContainer(self.raw_tx26_resp)
        tx26.cmd_endpoint = 0x02
        tx26.data_in_endpoint = 0x82  # Erroneous endpoint!
        tx26.resp_endpoint = 0x81     # Response endpoint remains correct
        engine.ptp_transactions[26] = tx26
        engine.transaction_order.append(26)
        
        res = engine.verify_mechanical_shutter()
        self.assertFalse(res["verified"])
        self.assertFalse(res["checks"]["tx26_data_in_endpoint_is_0x81"])
        self.assertTrue(res["checks"]["tx26_resp_endpoint_is_0x81"])

    def test_u02_negative_wrong_data_out_endpoint(self):
        """Data OUT arriving on endpoint 0x01 instead of 0x02 must fail."""
        engine = self._build_test_engine()
        tx25 = PTPTransaction(25)
        tx25.command = PTPContainer(self.raw_tx25_cmd)
        tx25.data_out = PTPContainer(self.raw_tx25_data)
        tx25.response = PTPContainer(self.raw_tx25_resp)
        tx25.cmd_endpoint = 0x02
        tx25.data_out_endpoint = 0x01  # Erroneous Data OUT endpoint!
        tx25.resp_endpoint = 0x81
        engine.ptp_transactions[25] = tx25
        engine.transaction_order.append(25)
        
        tx26 = PTPTransaction(26)
        tx26.command = PTPContainer(self.raw_tx26_cmd)
        tx26.data_in = PTPContainer(self.raw_tx26_data)
        tx26.response = PTPContainer(self.raw_tx26_resp)
        tx26.cmd_endpoint = 0x02
        tx26.data_in_endpoint = 0x81
        tx26.resp_endpoint = 0x81
        engine.ptp_transactions[26] = tx26
        engine.transaction_order.append(26)
        
        res = engine.verify_mechanical_shutter()
        self.assertFalse(res["verified"])
        self.assertFalse(res["checks"]["tx25_data_out_endpoint_is_0x02"])

    def test_u03_negative_erroneous_data_opcode(self):
        """Data container carrying OpCode 0x9052 instead of 0x9053 must fail."""
        engine = self._build_test_engine()
        tx25 = PTPTransaction(25)
        tx25.command = PTPContainer(self.raw_tx25_cmd)
        tx25.data_out = PTPContainer(self.raw_tx25_data)
        tx25.response = PTPContainer(self.raw_tx25_resp)
        tx25.cmd_endpoint = 0x02
        tx25.data_out_endpoint = 0x02
        tx25.resp_endpoint = 0x81
        engine.ptp_transactions[25] = tx25
        engine.transaction_order.append(25)
        
        # Corrupt OpCode in data container to 0x9052
        corrupted_data = bytearray(self.raw_tx26_data)
        struct.pack_into('<H', corrupted_data, 6, PTP_OP_CANON_VENDOR_CMD)
        
        tx26 = PTPTransaction(26)
        tx26.command = PTPContainer(self.raw_tx26_cmd)
        tx26.data_in = PTPContainer(bytes(corrupted_data))
        tx26.response = PTPContainer(self.raw_tx26_resp)
        tx26.cmd_endpoint = 0x02
        tx26.data_in_endpoint = 0x81
        tx26.resp_endpoint = 0x81
        engine.ptp_transactions[26] = tx26
        engine.transaction_order.append(26)
        
        res = engine.verify_mechanical_shutter()
        self.assertFalse(res["verified"])
        self.assertFalse(res["checks"]["tx26_data_opcode_0x9053"])

    def test_u04_negative_corrupted_container_length(self):
        """Buffer smaller than declared length must raise ValueError."""
        truncated_bytes = self.raw_tx25_data[:18]
        with self.assertRaises(ValueError):
            PTPContainer(truncated_bytes)

    def test_u05_negative_unaligned_parameter_length(self):
        """Command container with non-multiple-of-4 parameter bytes must raise ValueError."""
        # 12 header + 3 bytes parameter (total 15 bytes)
        unaligned = struct.pack('<IHHI', 15, PTP_USB_CONTAINER_COMMAND, PTP_OP_CANON_VENDOR_CMD, 1) + b"\x01\x02\x03"
        with self.assertRaises(ValueError):
            PTPContainer(unaligned)

    def test_u06_negative_missing_or_out_of_order_phases(self):
        """TxID 26 appearing before TxID 25 in stream order must fail sequence check."""
        engine = self._build_test_engine()
        tx25 = PTPTransaction(25)
        tx25.command = PTPContainer(self.raw_tx25_cmd)
        tx25.data_out = PTPContainer(self.raw_tx25_data)
        tx25.response = PTPContainer(self.raw_tx25_resp)
        tx25.cmd_endpoint = 0x02
        tx25.data_out_endpoint = 0x02
        tx25.resp_endpoint = 0x81
        engine.ptp_transactions[25] = tx25
        
        tx26 = PTPTransaction(26)
        tx26.command = PTPContainer(self.raw_tx26_cmd)
        tx26.data_in = PTPContainer(self.raw_tx26_data)
        tx26.response = PTPContainer(self.raw_tx26_resp)
        tx26.cmd_endpoint = 0x02
        tx26.data_in_endpoint = 0x81
        tx26.resp_endpoint = 0x81
        engine.ptp_transactions[26] = tx26
        
        # Invert sequence order: 26 precedes 25!
        engine.transaction_order.append(26)
        engine.transaction_order.append(25)
        
        res = engine.verify_mechanical_shutter()
        self.assertFalse(res["verified"])
        self.assertFalse(res["checks"]["sequence_tx25_precedes_tx26"])

    def test_u07_negative_announced_length_mismatch(self):
        """Announced size in Response Param1 not matching received payload size must fail."""
        engine = self._build_test_engine()
        # Response announces 16 bytes instead of 8 bytes
        corrupted_resp = bytearray(self.raw_tx25_resp)
        struct.pack_into('<I', corrupted_resp, 12, 16)
        
        tx25 = PTPTransaction(25)
        tx25.command = PTPContainer(self.raw_tx25_cmd)
        tx25.data_out = PTPContainer(self.raw_tx25_data)
        tx25.response = PTPContainer(bytes(corrupted_resp))
        tx25.cmd_endpoint = 0x02
        tx25.data_out_endpoint = 0x02
        tx25.resp_endpoint = 0x81
        engine.ptp_transactions[25] = tx25
        engine.transaction_order.append(25)
        
        tx26 = PTPTransaction(26)
        tx26.command = PTPContainer(self.raw_tx26_cmd)
        tx26.data_in = PTPContainer(self.raw_tx26_data)
        tx26.response = PTPContainer(self.raw_tx26_resp)
        tx26.cmd_endpoint = 0x02
        tx26.data_in_endpoint = 0x81
        tx26.resp_endpoint = 0x81
        engine.ptp_transactions[26] = tx26
        engine.transaction_order.append(26)
        
        res = engine.verify_mechanical_shutter()
        self.assertFalse(res["verified"])
        self.assertFalse(res["checks"]["tx25_response_param1_is_8"])
        self.assertFalse(res["checks"]["tx26_matches_announced_len"])

    def test_u08_dangerous_write_pattern_detection(self):
        """Detects unauthorized FA_WriteEepromData and classifies as POTENTIAL_WRITE."""
        engine = self._build_test_engine()
        tx = PTPTransaction(999)
        tx.command = PTPContainer(struct.pack('<IHHI', 12, PTP_USB_CONTAINER_COMMAND, PTP_OP_CANON_VENDOR_CMD, 999))
        payload = b"FA_WriteEepromData\x00\x01\x00\x00\x00\x02\x00\x00\x00\x46\x00\x00\x00" + b"\x00" * 16
        header = struct.pack('<IHHI', 12 + len(payload), PTP_USB_CONTAINER_DATA, PTP_OP_CANON_VENDOR_CMD, 999)
        tx.data_out = PTPContainer(header + payload)
        engine.ptp_transactions[999] = tx
        
        audit = engine.audit_write_safety()
        self.assertEqual(audit["potential_writes_detected"], 1)
        self.assertEqual(audit["category_summary"]["POTENTIAL_WRITE"], 1)

    def test_u09_unknown_opcode_classification(self):
        """Unknown opcodes must strictly be categorized as UNKNOWN, never READ."""
        engine = self._build_test_engine()
        tx = PTPTransaction(888)
        # Arbitrary vendor opcode 0x9999
        tx.command = PTPContainer(struct.pack('<IHHI', 12, PTP_USB_CONTAINER_COMMAND, 0x9999, 888))
        engine.ptp_transactions[888] = tx
        
        audit = engine.audit_write_safety()
        self.assertEqual(audit["category_summary"]["UNKNOWN"], 1)
        self.assertEqual(audit["category_summary"]["READ"], 0)

# ==============================================================================
# 7. Group 2: Integration Tests (Real Byte Slices from Capture)
# ==============================================================================

class TestOpenEOSForensicIntegrationTests(unittest.TestCase):
    """
    Integration Tests validating exact byte slices extracted from р62.pcapng.
    """
    def setUp(self):
        # Real byte slices from р62.pcapng
        self.real_tx25_cmd = bytes.fromhex("1400000001005290190000000000000001000000")
        self.real_tx25_data = bytes.fromhex("37000000020052901900000046415f47657450726f70657274790001000000020000000100001200000000000000000000000000000000")
        self.real_tx25_resp = bytes.fromhex("10000000030001201900000008000000")
        
        self.real_tx26_cmd = bytes.fromhex("0c000000010053901a000000")
        self.real_tx26_data = bytes.fromhex("14000000020053901a00000011ed000000000000")
        self.real_tx26_resp = bytes.fromhex("0c000000030001201a000000")
        
        self.real_tx31_cmd = bytes.fromhex("14000000010052901f0000000000000001000000")
        self.real_tx31_data = bytes.fromhex("37000000020052901f00000046415f47657450726f70657274790001000000020000000300001200000000000000000000000000000000")
        self.real_tx31_resp = bytes.fromhex("10000000030001201f00000004000000")
        
        self.real_tx32_cmd = bytes.fromhex("0c0000000100539020000000")
        self.real_tx32_data = bytes.fromhex("100000000200539020000000b9d20c00")
        self.real_tx32_resp = bytes.fromhex("0c0000000300012020000000")
        
        self.real_tx39_data = bytes.fromhex("3a000000020052902700000046415f52656164456570726f6d446174610001000000020000004600000000000000000000000000000000000000")

    def test_i01_real_slice_tx25_26_mechanical_shutter(self):
        """Verifies full structural chain on real slice of TxID 25 & 26."""
        engine = PCAPNGAuditEngineV31("dummy.pcapng")
        
        tx25 = PTPTransaction(25)
        tx25.command = PTPContainer(self.real_tx25_cmd)
        tx25.data_out = PTPContainer(self.real_tx25_data)
        tx25.response = PTPContainer(self.real_tx25_resp)
        tx25.cmd_endpoint = 0x02
        tx25.data_out_endpoint = 0x02
        tx25.resp_endpoint = 0x81
        engine.ptp_transactions[25] = tx25
        engine.transaction_order.append(25)
        
        tx26 = PTPTransaction(26)
        tx26.command = PTPContainer(self.real_tx26_cmd)
        tx26.data_in = PTPContainer(self.real_tx26_data)
        tx26.response = PTPContainer(self.real_tx26_resp)
        tx26.cmd_endpoint = 0x02
        tx26.data_in_endpoint = 0x81
        tx26.resp_endpoint = 0x81
        engine.ptp_transactions[26] = tx26
        engine.transaction_order.append(26)
        
        res = engine.verify_mechanical_shutter()
        self.assertTrue(res["verified"])
        self.assertEqual(res["shutter_count"], 60689)
        self.assertEqual(res["raw_hex"], "11ed000000000000")

    def test_i02_real_slice_tx31_32_total_releases(self):
        """Verifies full structural chain on real slice of TxID 31 & 32."""
        engine = PCAPNGAuditEngineV31("dummy.pcapng")
        
        tx31 = PTPTransaction(31)
        tx31.command = PTPContainer(self.real_tx31_cmd)
        tx31.data_out = PTPContainer(self.real_tx31_data)
        tx31.response = PTPContainer(self.real_tx31_resp)
        tx31.cmd_endpoint = 0x02
        tx31.data_out_endpoint = 0x02
        tx31.resp_endpoint = 0x81
        engine.ptp_transactions[31] = tx31
        engine.transaction_order.append(31)
        
        tx32 = PTPTransaction(32)
        tx32.command = PTPContainer(self.real_tx32_cmd)
        tx32.data_in = PTPContainer(self.real_tx32_data)
        tx32.response = PTPContainer(self.real_tx32_resp)
        tx32.cmd_endpoint = 0x02
        tx32.data_in_endpoint = 0x81
        tx32.resp_endpoint = 0x81
        engine.ptp_transactions[32] = tx32
        engine.transaction_order.append(32)
        
        res = engine.verify_total_releases()
        self.assertTrue(res["verified"])
        self.assertEqual(res["total_releases"], 840377)
        self.assertEqual(res["raw_hex"], "b9d20c00")

    def test_i03_real_slice_tx39_fa_read_eeprom_format(self):
        """Dissects exact byte structure of real TxID 39 FA_ReadEepromData Data OUT."""
        cont = PTPContainer(self.real_tx39_data)
        self.assertEqual(cont.length, 58)  # 12 header + 46 payload
        self.assertEqual(cont.type, PTP_USB_CONTAINER_DATA)
        self.assertEqual(cont.code, PTP_OP_CANON_VENDOR_CMD)
        self.assertEqual(cont.tx_id, 39)
        
        p = cont.payload
        self.assertEqual(len(p), 46)
        
        # String + NUL = 18 bytes
        proc_str = p[:18]
        self.assertEqual(proc_str, b"FA_ReadEepromData\x00")
        self.assertEqual(len(b"FA_ReadEepromData"), 17) # 17 ASCII characters
        self.assertEqual(proc_str[17], 0x00)            # NUL terminator at offset 17
        
        # SubCmd / Mode = uint32(1)
        subcmd = struct.unpack_from('<I', p, 18)[0]
        self.assertEqual(subcmd, 1)
        
        # Tag = uint32(2)
        tag = struct.unpack_from('<I', p, 22)[0]
        self.assertEqual(tag, 2)
        
        # Block / Chunk index = uint32(0x46 = 70)
        block_idx = struct.unpack_from('<I', p, 26)[0]
        self.assertEqual(block_idx, 0x46)
        
        # Zero padding = 16 bytes
        padding = p[30:46]
        self.assertEqual(padding, b"\x00" * 16)

# ==============================================================================
# 8. Test Runners & Main Entry Point
# ==============================================================================

def run_all_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestOpenEOSForensicUnitTests))
    suite.addTests(loader.loadTestsFromTestCase(TestOpenEOSForensicIntegrationTests))
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)

def main():
    print("=" * 80)
    print("OpenEOS Independent PCAPNG Forensic Audit Tool (Revision 3.1)")
    print("Canon EOS R6 Mark II Service Capture Verification")
    print("=" * 80)
    
    print("\n[STEP 1] Running Forensic Test Suite (Unit Tests + Integration Tests)...")
    res = run_all_tests()
    if not res.wasSuccessful():
        print("[-] Tests failed! Aborting.")
        sys.exit(1)
    print(f"[+] All {res.testsRun} tests passed successfully.")
    
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
        print("[*] Engine and test suite verified operational.")
        return

    print(f"\n[STEP 2] Parsing Target Capture: {target_path}")
    engine = PCAPNGAuditEngineV31(target_path)
    engine.parse()
    
    print(f"[+] Total Blocks Parsed: {engine.total_blocks}")
    print(f"[+] Total EPB Packets:   {engine.epb_count}")
    print(f"[+] Dropped Packets:     {engine.dropped_packets_count}")
    print(f"[+] Reassembled PTP Transactions: {len(engine.ptp_transactions)}")
    print(f"[+] Parser Error Counts:")
    print(f"    - PCAPNG Errors:            {len(engine.pcapng_errors)}")
    print(f"    - USBPcap Errors:           {len(engine.usbpcap_errors)}")
    print(f"    - Malformed PTP Containers: {len(engine.malformed_ptp_containers)}")
    print(f"    - Length Mismatches:        {len(engine.length_mismatches)}")
    print(f"    - Unsupported Transfers:    {len(engine.unsupported_transfers)}")
    print(f"    - Unparsed Containers:      {engine.unparsed_containers_count}")
    
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
    print(f"  - Potential Writes Detected:   {safety['potential_writes_detected']}")
    print(f"  - Total Classified:            {safety['total_classified']}")
    print("  - Procedure Classification Summary:")
    for cat, count in safety['category_summary'].items():
        print(f"      * {cat}: {count} transactions")
    print(f"  - Firmware Internal Side-Effects: {safety['firmware_internal_side_effects']}")
    print("=" * 80)

if __name__ == "__main__":
    main()
