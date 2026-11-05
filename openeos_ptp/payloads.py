"""
PTP Container and FA_GetProperty payload serialization, parsing, and validation.
Strictly separates Command, Data OUT, Data IN, and Response containers according to ISO 15740.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List, Optional

from .constants import (
    PTP_CONTAINER_COMMAND,
    PTP_CONTAINER_DATA,
    PTP_CONTAINER_RESPONSE,
    PTP_OC_OpenSession,
    PTP_OC_CloseSession,
    PTP_OC_Canon_FA_Command,
    PTP_OC_Canon_FA_Fetch,
    PTP_RC_OK,
    FA_COMMAND_NAME,
    CANON_FA_ARGC_DEFAULT,
    CANON_FA_ARG_TAG_DWORD,
    FA_GET_PROPERTY_PAYLOAD_LEN,
    FA_GET_PROPERTY_CONTAINER_LEN,
    FA_COMMAND_CONTAINER_LEN,
    ALLOWED_PROPERTY_IDS,
    FETCH_PARAMS_MAP,
    MON_OPEN_NAME,
    MON_READ_NAME,
    MON_CLOSE_NAME,
    ALLOWED_MON_COMMANDS,
    FORBIDDEN_MON_COMMANDS,
    R10_CANDIDATE_ADDRESSES,
)


class PayloadFormatError(Exception):
    """Raised when a PTP container or payload fails format validation."""
    pass


@dataclass(frozen=True)
class PtpContainer:
    """
    Representation of an ISO 15740 PTP Container.
    """
    length: int
    container_type: int
    opcode_or_response: int
    tx_id: int
    payload_or_params: bytes

    @property
    def is_command(self) -> bool:
        return self.container_type == PTP_CONTAINER_COMMAND

    @property
    def is_data(self) -> bool:
        return self.container_type == PTP_CONTAINER_DATA

    @property
    def is_response(self) -> bool:
        return self.container_type == PTP_CONTAINER_RESPONSE

    def get_params(self) -> List[int]:
        """Extracts uint32 parameters if this is a Command or Response container."""
        if self.is_data:
            return []
        num_params = len(self.payload_or_params) // 4
        return list(struct.unpack(f"<{num_params}I", self.payload_or_params[:num_params * 4]))

    def serialize(self) -> bytes:
        header = struct.pack(
            "<IHHI",
            self.length,
            self.container_type,
            self.opcode_or_response,
            self.tx_id,
        )
        return header + self.payload_or_params

    def to_bytes(self) -> bytes:
        """Alias for serialize() to ensure compatibility across modules."""
        return self.serialize()

    def __bytes__(self) -> bytes:
        return self.serialize()


def build_ptp_command_container(opcode: int, tx_id: int, params: Optional[List[int]] = None) -> PtpContainer:
    """
    Synthesizes a PTP Command Container (Type 0x0001) as a PtpContainer object.
    Header: Length (uint32), Type = 1 (uint16), OpCode (uint16), TxID (uint32).
    Followed by uint32 parameters.
    """
    params = params or []
    param_bytes = b"".join(struct.pack("<I", p) for p in params)
    total_len = 12 + len(param_bytes)

    return PtpContainer(
        length=total_len,
        container_type=PTP_CONTAINER_COMMAND,
        opcode_or_response=opcode,
        tx_id=tx_id,
        payload_or_params=param_bytes,
    )


def build_ptp_response_container(response_code: int, tx_id: int, params: Optional[List[int]] = None) -> PtpContainer:
    """
    Synthesizes a PTP Response Container (Type 0x0003) as a PtpContainer object.
    Header: Length (uint32), Type = 3 (uint16), ResponseCode (uint16), TxID (uint32).
    Followed by uint32 parameters.
    """
    params = params or []
    param_bytes = b"".join(struct.pack("<I", p) for p in params)
    total_len = 12 + len(param_bytes)

    return PtpContainer(
        length=total_len,
        container_type=PTP_CONTAINER_RESPONSE,
        opcode_or_response=response_code,
        tx_id=tx_id,
        payload_or_params=param_bytes,
    )


def build_fa_command_container(
    tx_id: int,
    params: Optional[List[int]] = None,
    payload_len: Optional[int] = None,
) -> PtpContainer:
    """
    Synthesizes the 20-byte PTP Command container for 0x9052 with params [0, 1] as a PtpContainer object.
    (Observed at TxID 25 in р62.pcapng EPB #69: 14 00 00 00 01 00 52 90 19 00 00 00 00 00 00 00 01 00 00 00).
    """
    if params is None:
        params = [0, 1]
    return build_ptp_command_container(PTP_OC_Canon_FA_Command, tx_id, params)


def build_fa_get_property_container(tx_id: int, property_id: int) -> PtpContainer:
    """
    Synthesizes the 55-byte PTP Data OUT Container (Type 0x0002, OpCode 0x9052)
    containing the 43-byte FA_GetProperty payload as a PtpContainer object.
    """
    if property_id not in ALLOWED_PROPERTY_IDS:
        raise PayloadFormatError(
            f"Property ID 0x{property_id:08X} is not in the allowed diagnostic whitelist "
            f"{[f'0x{k:08X}' for k in ALLOWED_PROPERTY_IDS]}."
        )

    # Build 43-byte payload
    payload = bytearray()
    payload.extend(FA_COMMAND_NAME)                                   # 15 bytes
    payload.extend(struct.pack("<I", CANON_FA_ARGC_DEFAULT))          # 4 bytes (argc = 1)
    payload.extend(struct.pack("<I", CANON_FA_ARG_TAG_DWORD))         # 4 bytes (tag = 2)
    payload.extend(struct.pack("<I", property_id))                    # 4 bytes (key)
    payload.extend(b"\x00" * 12)                                      # 12 bytes (arg tail padding)
    payload.extend(b"\x00" * 4)                                       # 4 bytes (struct alignment)

    if len(payload) != FA_GET_PROPERTY_PAYLOAD_LEN:
        raise PayloadFormatError(
            f"Internal builder error: expected {FA_GET_PROPERTY_PAYLOAD_LEN} bytes payload, "
            f"got {len(payload)}"
        )

    return PtpContainer(
        length=FA_GET_PROPERTY_CONTAINER_LEN,
        container_type=PTP_CONTAINER_DATA,
        opcode_or_response=PTP_OC_Canon_FA_Command,
        tx_id=tx_id,
        payload_or_params=bytes(payload),
    )


def build_fa_fetch_command(
    tx_id: int,
    property_id: Optional[int] = None,
    params: Optional[List[int]] = None,
) -> PtpContainer:
    """
    Synthesizes the PTP Command Container for 0x9053 (FA_Fetch) as a PtpContainer object.
    Params are [] for 0x12000001/0x12000003, and [0, 0, 1] for 0x12000005.
    Unknown Property IDs MUST raise PayloadFormatError without falling back to empty parameters.
    """
    if params is None:
        if property_id is not None:
            if property_id not in FETCH_PARAMS_MAP:
                raise PayloadFormatError(
                    f"Unsupported Property ID 0x{property_id:08X} for 0x9053 Fetch. "
                    f"Allowed properties: {[f'0x{k:08X}' for k in FETCH_PARAMS_MAP]}."
                )
            params = FETCH_PARAMS_MAP[property_id]
        else:
            params = []
    return build_ptp_command_container(PTP_OC_Canon_FA_Fetch, tx_id, params)


def build_mon_open_payload() -> bytes:
    """
    Builds the payload for MonOpen:
    - ASCII string 'MonOpen\0' (8 bytes)
    - argc = 0 (4 bytes uint32)
    Total: 12 bytes.
    """
    payload = bytearray(b"MonOpen\x00")
    payload.extend(struct.pack("<I", 0))  # argc = 0
    return bytes(payload)


def build_mon_open_container(tx_id: int) -> PtpContainer:
    """
    Synthesizes the PTP Data OUT container (0x9052) for MonOpen as a PtpContainer object.
    Length: 12 (PTP header) + 12 (payload) = 24 bytes.
    """
    payload = build_mon_open_payload()
    return PtpContainer(
        length=12 + len(payload),
        container_type=PTP_CONTAINER_DATA,
        opcode_or_response=PTP_OC_Canon_FA_Command,
        tx_id=tx_id,
        payload_or_params=payload,
    )


def build_mon_read_and_get_data_payload(address: int, length: int) -> bytes:
    """
    Builds the payload for MonReadAndGetData(2, address, length):
    - ASCII string 'MonReadAndGetData\0' (18 bytes)
    - argc = 3 (4 bytes uint32)
    - Arg 0: tag = 2 (DWORD), value = 2, 12 bytes zero padding (20 bytes)
    - Arg 1: tag = 2 (DWORD), value = address, 12 bytes zero padding (20 bytes)
    - Arg 2: tag = 2 (DWORD), value = length, 12 bytes zero padding (20 bytes)
    - 2 bytes zero alignment padding (aligns payload to 84 bytes, multiple of 4)
    Total: 18 + 4 + 60 + 2 = 84 bytes.
    """
    if length <= 0 or length > 65536:
        raise PayloadFormatError(f"Invalid requested read length: {length}")
    if address < 0 or address > 0xFFFFFFFF:
        raise PayloadFormatError(f"Invalid memory address: 0x{address:X}")

    payload = bytearray(b"MonReadAndGetData\x00")
    payload.extend(struct.pack("<I", 3))  # argc = 3

    # Arg 0: Tag 2, Value 2 (CANON_FA_ARG_TAG_DWORD = 2)
    payload.extend(struct.pack("<II", CANON_FA_ARG_TAG_DWORD, 2))
    payload.extend(b"\x00" * 12)

    # Arg 1: Tag 2, Value = address
    payload.extend(struct.pack("<II", CANON_FA_ARG_TAG_DWORD, address))
    payload.extend(b"\x00" * 12)

    # Arg 2: Tag 2, Value = length
    payload.extend(struct.pack("<II", CANON_FA_ARG_TAG_DWORD, length))
    payload.extend(b"\x00" * 12)

    # 2 bytes alignment padding
    payload.extend(b"\x00" * 2)

    return bytes(payload)


def build_mon_read_and_get_data_container(tx_id: int, address: int, length: int) -> PtpContainer:
    """
    Synthesizes the PTP Data OUT container (0x9052) for MonReadAndGetData as a PtpContainer object.
    Length: 12 (PTP header) + 84 (payload) = 96 bytes.
    """
    payload = build_mon_read_and_get_data_payload(address, length)
    return PtpContainer(
        length=12 + len(payload),
        container_type=PTP_CONTAINER_DATA,
        opcode_or_response=PTP_OC_Canon_FA_Command,
        tx_id=tx_id,
        payload_or_params=payload,
    )


def build_mon_close_payload() -> bytes:
    """
    Builds the payload for MonClose:
    - ASCII string 'MonClose\0' (9 bytes)
    - argc = 0 (4 bytes uint32)
    - 3 bytes zero alignment padding
    Total: 16 bytes.
    """
    payload = bytearray(b"MonClose\x00")
    payload.extend(struct.pack("<I", 0))  # argc = 0
    payload.extend(b"\x00" * 3)           # 3 bytes alignment padding
    return bytes(payload)


def build_mon_close_container(tx_id: int) -> PtpContainer:
    """
    Synthesizes the PTP Data OUT container (0x9052) for MonClose as a PtpContainer object.
    Length: 12 (PTP header) + 16 (payload) = 28 bytes.
    """
    payload = build_mon_close_payload()
    return PtpContainer(
        length=12 + len(payload),
        container_type=PTP_CONTAINER_DATA,
        opcode_or_response=PTP_OC_Canon_FA_Command,
        tx_id=tx_id,
        payload_or_params=payload,
    )


def validate_mon_command(cmd_name: bytes) -> bool:
    clean_name = cmd_name.split(b"\x00")[0]
    if clean_name in FORBIDDEN_MON_COMMANDS:
        raise PayloadFormatError(f"Forbidden Mon command rejected by safety protocol: {clean_name!r}")
    if clean_name not in ALLOWED_MON_COMMANDS:
        raise PayloadFormatError(f"Unauthorized Mon command: {clean_name!r}")
    return True


def parse_ptp_container(data: bytes) -> PtpContainer:
    """
    Parses a raw byte buffer into a PtpContainer object.
    Validates container header and declared length against buffer length.
    """
    if len(data) < 12:
        raise PayloadFormatError(
            f"PTP container too short for header: expected >= 12 bytes, got {len(data)}"
        )

    length, c_type, opcode, tx_id = struct.unpack("<IHHI", data[0:12])

    if len(data) != length:
        raise PayloadFormatError(
            f"PTP container length mismatch: header declares {length} bytes, "
            f"actual buffer is {len(data)} bytes"
        )

    payload_or_params = data[12:]
    if c_type in (PTP_CONTAINER_COMMAND, PTP_CONTAINER_RESPONSE) and len(payload_or_params) % 4 != 0:
        raise PayloadFormatError(
            f"PTP Command/Response parameters length not multiple of 4: {len(payload_or_params)} bytes"
        )
    return PtpContainer(
        length=length,
        container_type=c_type,
        opcode_or_response=opcode,
        tx_id=tx_id,
        payload_or_params=payload_or_params,
    )


def validate_fa_get_property_payload(
    payload: bytes,
    expected_property_id: Optional[int] = None,
) -> bool:
    """
    Strict validation of a 43-byte FA_GetProperty payload against known wire specifications.
    Raises PayloadFormatError on any discrepancy.
    """
    if len(payload) != FA_GET_PROPERTY_PAYLOAD_LEN:
        raise PayloadFormatError(
            f"FA_GetProperty payload length error: expected {FA_GET_PROPERTY_PAYLOAD_LEN} bytes, "
            f"got {len(payload)}"
        )

    # 1. Check command name string (15 bytes)
    cmd_name = payload[0:15]
    if cmd_name != FA_COMMAND_NAME:
        raise PayloadFormatError(
            f"FA_GetProperty invalid command name: expected {FA_COMMAND_NAME!r}, got {cmd_name!r}"
        )

    # 2. Check argc (must be 1)
    argc = struct.unpack("<I", payload[15:19])[0]
    if argc != CANON_FA_ARGC_DEFAULT:
        raise PayloadFormatError(
            f"FA_GetProperty invalid argc: expected {CANON_FA_ARGC_DEFAULT}, got {argc}"
        )

    # 3. Check argument tag (must be 2, NOT CSC or any other value)
    tag = struct.unpack("<I", payload[19:23])[0]
    if tag != CANON_FA_ARG_TAG_DWORD:
        raise PayloadFormatError(
            f"FA_GetProperty invalid tag: expected {CANON_FA_ARG_TAG_DWORD} (DWORD), got {tag}"
        )

    # 4. Check Property Key
    key = struct.unpack("<I", payload[23:27])[0]
    if key not in ALLOWED_PROPERTY_IDS:
        raise PayloadFormatError(
            f"FA_GetProperty unauthorized property key: 0x{key:08X} not in whitelist"
        )
    if expected_property_id is not None and key != expected_property_id:
        raise PayloadFormatError(
            f"FA_GetProperty property mismatch: expected 0x{expected_property_id:08X}, got 0x{key:08X}"
        )

    # 5. Check argument tail padding (12 bytes must be all zero)
    arg_pad = payload[27:39]
    if arg_pad != b"\x00" * 12:
        raise PayloadFormatError(
            f"FA_GetProperty arg tail padding contains non-zero bytes: {arg_pad.hex()}"
        )

    # 6. Check struct alignment padding (4 bytes must be all zero)
    align = payload[39:43]
    if align != b"\x00" * 4:
        raise PayloadFormatError(
            f"FA_GetProperty alignment padding contains non-zero bytes: {align.hex()}"
        )

    return True
