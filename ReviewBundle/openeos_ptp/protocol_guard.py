"""
OpenEOS Protocol Guard.
Mandatory security firewall enforcing strict command filtering, sequence tracking,
and zero-compromise protection against arbitrary code execution or non-volatile writes.
Strictly separates Command, Data OUT, Data IN, and Response phases according to ISO 15740.
"""

from __future__ import annotations

import enum
import struct
from typing import List, Optional

from .constants import (
    PTP_CONTAINER_COMMAND,
    PTP_CONTAINER_DATA,
    PTP_CONTAINER_RESPONSE,
    PTP_OC_OpenSession,
    PTP_OC_CloseSession,
    PTP_OC_Canon_FA_Command,
    PTP_OC_Canon_FA_Fetch,
    PTP_OC_Canon_SaveTransparentMemory,
    PTP_OC_Canon_QuickLoadTransparentMemory,
    PTP_OC_Canon_Auth,
    PTP_OC_Canon_DirectPTP,
    PTP_OC_Canon_EventProc,
    PTP_RC_OK,
    PTP_RC_OperationNotSupported,
    PTP_RC_AccessDenied,
    PTP_RC_DeviceBusy,
    PROP_SHUTTER_COUNTER,
    PROP_RELEASE_TOTAL,
    PROP_POWER_AND_UPTIME,
    ALLOWED_PROPERTY_IDS,
    FETCH_PARAMS_MAP,
    EXPECTED_DATA_LENGTHS,
    FA_COMMAND_CONTAINER_LEN,
    FA_GET_PROPERTY_CONTAINER_LEN,
)
from .payloads import (
    PtpContainer,
    parse_ptp_container,
    validate_fa_get_property_payload,
    PayloadFormatError,
)


class SecurityViolationError(Exception):
    """Raised when a prohibited command, tampered transaction, or unauthorized operation is attempted."""
    pass


class ProtocolSequenceError(SecurityViolationError):
    """Raised when containers are issued out of the valid protocol state sequence."""
    pass


class ProtocolGuardState(enum.Enum):
    """Internal transaction phase states for the protocol firewall."""
    DISCONNECTED = "DISCONNECTED"
    WAITING_OPEN_RESPONSE = "WAITING_OPEN_RESPONSE"
    SESSION_OPEN = "SESSION_OPEN"
    WAITING_DATA_OUT = "WAITING_DATA_OUT"
    WAITING_COMMAND_RESPONSE = "WAITING_COMMAND_RESPONSE"
    WAITING_FETCH_COMMAND = "WAITING_FETCH_COMMAND"
    WAITING_FETCH_DATA_IN = "WAITING_FETCH_DATA_IN"
    WAITING_FETCH_RESPONSE = "WAITING_FETCH_RESPONSE"
    WAITING_CLOSE_RESPONSE = "WAITING_CLOSE_RESPONSE"


# Prohibited strings that must NEVER appear in any payload or procedure name
PROHIBITED_PROCEDURE_PATTERNS = [
    b"eventproc",
    b"fa_setproperty",
    b"fa_setcalendar",
    b"monwrite",
    b"eeprom",
    b"flash",
    b"format",
    b"delete",
    b"execute",
    b"system",
    b"factory_test",
    b"ptp_write",
    b"save_transparent_memory",
    b"quick_load",
]


class ProtocolGuard:
    """
    Protocol Guard acts as a strict gateway between OpenEOS and the USB transport.
    No physical or mock container can reach the wire without passing this inspection.
    """

    def __init__(self):
        self._state = ProtocolGuardState.DISCONNECTED
        self._active_tx_id: Optional[int] = None
        self._active_property_id: Optional[int] = None
        self._active_fetch_tx_id: Optional[int] = None
        self._last_command_tx_id: Optional[int] = None
        self._used_tx_ids: set[int] = set()

    @property
    def state(self) -> ProtocolGuardState:
        return self._state

    @property
    def active_property_id(self) -> Optional[int]:
        return self._active_property_id

    @property
    def active_tx_id(self) -> Optional[int]:
        return self._active_tx_id

    def reset(self) -> None:
        """Resets the firewall state to DISCONNECTED and clears active transaction trackers."""
        self._state = ProtocolGuardState.DISCONNECTED
        self._active_tx_id = None
        self._active_property_id = None
        self._active_fetch_tx_id = None
        self._last_command_tx_id = None
        self._used_tx_ids.clear()

    def validate_outgoing_container_bytes(self, raw_bytes: bytes) -> PtpContainer:
        """
        Validates raw outgoing wire bytes immediately prior to USB WriteFile.
        Checks length, container type, OpCode, TransactionID, and payload contents.
        """
        try:
            container = parse_ptp_container(raw_bytes)
        except PayloadFormatError as exc:
            raise SecurityViolationError(f"Protocol Guard rejected malformed PTP container: {exc}") from exc

        self.validate_outgoing_container(container)
        return container

    def validate_outgoing_container(self, container: PtpContainer) -> None:
        """
        Validates a PtpContainer object against active state, allowed OpCodes, and arguments.
        """
        opcode = container.opcode_or_response
        tx_id = container.tx_id

        # 1. Prohibited OpCodes check
        if opcode in (
            PTP_OC_Canon_SaveTransparentMemory,
            PTP_OC_Canon_QuickLoadTransparentMemory,
            PTP_OC_Canon_Auth,
            PTP_OC_Canon_DirectPTP,
            PTP_OC_Canon_EventProc,
        ):
            raise SecurityViolationError(
                f"Prohibited OpCode 0x{opcode:04X} intercepted by Protocol Guard! "
                f"All code uploads, execution triggers, and auth handshakes are strictly barred."
            )

        # 2. Transaction ID Collision / Replay Protection
        if container.is_command:
            if tx_id in self._used_tx_ids:
                raise SecurityViolationError(
                    f"Duplicate TransactionID {tx_id} rejected! "
                    f"Transaction IDs must not be reused within an open session."
                )
            if (self._active_tx_id is not None and tx_id == self._active_tx_id) or \
               (self._active_fetch_tx_id is not None and tx_id == self._active_fetch_tx_id):
                raise SecurityViolationError(
                    f"TransactionID {tx_id} is currently active and cannot be reused concurrently."
                )

        # 3. State Machine & Phase Transitions
        # Case A: OpenSession (Command)
        if opcode == PTP_OC_OpenSession:
            if not container.is_command:
                raise SecurityViolationError("OpenSession must be a Command Container (Type 1).")
            if self._state != ProtocolGuardState.DISCONNECTED:
                raise ProtocolSequenceError(f"Cannot issue OpenSession in state {self._state.value}.")
            if container.length != 16 or len(container.payload_or_params) != 4:
                raise SecurityViolationError(
                    f"OpenSession container length error: expected 16 bytes, got {container.length}."
                )
            params = container.get_params()
            if len(params) != 1:
                raise SecurityViolationError(f"OpenSession requires 1 parameter (SessionID), got {len(params)}.")

            self._active_tx_id = tx_id
            self._state = ProtocolGuardState.WAITING_OPEN_RESPONSE
            return

        # Case B: CloseSession (Command)
        if opcode == PTP_OC_CloseSession:
            if not container.is_command:
                raise SecurityViolationError("CloseSession must be a Command Container (Type 1).")
            if self._state == ProtocolGuardState.DISCONNECTED:
                raise ProtocolSequenceError("Cannot issue CloseSession when DISCONNECTED.")
            if self._state == ProtocolGuardState.WAITING_CLOSE_RESPONSE:
                raise ProtocolSequenceError("CloseSession already dispatched, waiting for response.")
            if self._state != ProtocolGuardState.SESSION_OPEN:
                raise ProtocolSequenceError(
                    f"Cannot issue CloseSession during active/incomplete transaction in state {self._state.value}. "
                    f"All read transactions must complete or fail cleanly first."
                )
            if container.length != 12 or len(container.payload_or_params) != 0:
                raise SecurityViolationError(
                    f"CloseSession container length error: expected 12 bytes, got {container.length}."
                )

            self._active_tx_id = tx_id
            self._state = ProtocolGuardState.WAITING_CLOSE_RESPONSE
            return

        # Case C: 0x9052 FA_Command - Command Phase
        if opcode == PTP_OC_Canon_FA_Command and container.is_command:
            if self._state != ProtocolGuardState.SESSION_OPEN:
                raise ProtocolSequenceError(
                    f"Cannot dispatch 0x9052 Command in state {self._state.value}. "
                    f"Must be in SESSION_OPEN (previous transaction must be fully closed)."
                )
            if container.length != FA_COMMAND_CONTAINER_LEN or len(container.payload_or_params) != 8:
                raise SecurityViolationError(
                    f"0x9052 Command container length error: expected {FA_COMMAND_CONTAINER_LEN} bytes, got {container.length}."
                )
            params = container.get_params()
            if params != [0, 1]:
                raise SecurityViolationError(
                    f"0x9052 Command parameter mismatch: expected [0, 1], got {params}."
                )

            self._active_tx_id = tx_id
            self._state = ProtocolGuardState.WAITING_DATA_OUT
            return

        # Case D: 0x9052 FA_Command - Data OUT Phase
        if opcode == PTP_OC_Canon_FA_Command and container.is_data:
            if self._state != ProtocolGuardState.WAITING_DATA_OUT:
                raise ProtocolSequenceError(
                    f"Unexpected Data OUT container in state {self._state.value}. "
                    f"Data OUT must immediately follow a 0x9052 Command."
                )
            if container.length != FA_GET_PROPERTY_CONTAINER_LEN or len(container.payload_or_params) != 43:
                raise SecurityViolationError(
                    f"0x9052 Data OUT container length error: expected {FA_GET_PROPERTY_CONTAINER_LEN} bytes, got {container.length}."
                )
            # TransactionID MUST match the preceding Command
            if tx_id != self._active_tx_id:
                raise SecurityViolationError(
                    f"TransactionID mismatch between Command ({self._active_tx_id}) "
                    f"and Data OUT ({tx_id})! Possible transaction hijacking attempt."
                )

            # Strict Payload Verification
            payload = container.payload_or_params
            if len(payload) < 15:
                raise SecurityViolationError("Data OUT payload too short to contain FA procedure name.")

            # Check procedure name field specifically (first 15 bytes) rather than searching arbitrary binary arguments
            proc_name_raw = payload[0:15].split(b"\x00")[0].lower()
            for pattern in PROHIBITED_PROCEDURE_PATTERNS:
                if pattern in proc_name_raw:
                    raise SecurityViolationError(
                        f"Prohibited procedure name {pattern!r} detected in procedure field: {proc_name_raw!r}. "
                        f"Arbitrary EventProc, write routines, and test functions are strictly barred."
                    )

            try:
                validate_fa_get_property_payload(payload)
            except PayloadFormatError as exc:
                raise SecurityViolationError(f"Protocol Guard rejected FA payload: {exc}") from exc

            prop_key = struct.unpack("<I", payload[23:27])[0]
            if prop_key not in ALLOWED_PROPERTY_IDS:
                raise SecurityViolationError(
                    f"Unauthorized Property ID 0x{prop_key:08X} in FA_GetProperty."
                )

            self._active_property_id = prop_key
            self._state = ProtocolGuardState.WAITING_COMMAND_RESPONSE
            return

        # Case E: 0x9053 FA_Fetch - Command Phase
        if opcode == PTP_OC_Canon_FA_Fetch and container.is_command:
            if self._state != ProtocolGuardState.WAITING_FETCH_COMMAND:
                raise ProtocolSequenceError(
                    f"Unexpected 0x9053 Fetch Command in state {self._state.value}. "
                    f"Fetch is ONLY permitted after a successful FA_GetProperty Response."
                )
            if self._last_command_tx_id is not None and tx_id == self._last_command_tx_id:
                raise SecurityViolationError(
                    f"0x9053 Fetch Command cannot reuse the TransactionID ({tx_id}) of preceding 0x9052 command."
                )

            expected_prop = self._active_property_id
            expected_params = FETCH_PARAMS_MAP.get(expected_prop, [])
            expected_len = 12 + len(expected_params) * 4
            if container.length != expected_len or len(container.payload_or_params) != len(expected_params) * 4:
                raise SecurityViolationError(
                    f"0x9053 Fetch container length error: expected {expected_len} bytes, got {container.length}."
                )

            params = container.get_params()
            if params != expected_params:
                raise SecurityViolationError(
                    f"Parameter mismatch for 0x9053 Fetch of Property 0x{expected_prop:08X}: "
                    f"expected {expected_params}, received {params}."
                )

            self._active_fetch_tx_id = tx_id
            self._state = ProtocolGuardState.WAITING_FETCH_DATA_IN
            return

        # Any other outbound container
        raise SecurityViolationError(
            f"Container (Type={container.container_type}, OpCode=0x{opcode:04X}) "
            f"is rejected by OpenEOS Protocol Guard in state {self._state.value}."
        )

    def validate_inbound_container_bytes(self, raw_bytes: bytes) -> PtpContainer:
        """
        Validates raw inbound wire bytes immediately after USB ReadFile.
        Checks container type, ResponseCode / OpCode, TransactionID, and data length.
        """
        try:
            container = parse_ptp_container(raw_bytes)
        except PayloadFormatError as exc:
            raise SecurityViolationError(f"Protocol Guard rejected malformed inbound container: {exc}") from exc

        self.validate_inbound_container(container)
        return container

    def validate_inbound_container(self, container: PtpContainer) -> None:
        """
        Validates an inbound PtpContainer against active expectation states.
        Enforces Transaction ID verification, parameter lengths, and automatic error state cleanup.
        """
        # Case A: OpenSession Response
        if self._state == ProtocolGuardState.WAITING_OPEN_RESPONSE:
            if not container.is_response:
                self.reset()
                raise ProtocolSequenceError("Expected Response container for OpenSession.")
            if container.tx_id != self._active_tx_id:
                self.reset()
                raise SecurityViolationError(
                    f"TransactionID mismatch on OpenSession response: expected {self._active_tx_id}, got {container.tx_id}."
                )
            if container.opcode_or_response != PTP_RC_OK:
                resp = container.opcode_or_response
                self.reset()
                raise SecurityViolationError(f"OpenSession failed with ResponseCode 0x{resp:04X}.")

            if self._active_tx_id is not None:
                self._used_tx_ids.add(self._active_tx_id)
            self._state = ProtocolGuardState.SESSION_OPEN
            self._active_tx_id = None
            return

        # Case B: 0x9052 FA_Command Response
        if self._state == ProtocolGuardState.WAITING_COMMAND_RESPONSE:
            if not container.is_response:
                self._state = ProtocolGuardState.SESSION_OPEN
                self._active_tx_id = None
                self._active_property_id = None
                raise ProtocolSequenceError("Expected Response container for 0x9052.")
            if container.tx_id != self._active_tx_id:
                self._state = ProtocolGuardState.SESSION_OPEN
                self._active_tx_id = None
                self._active_property_id = None
                raise SecurityViolationError(
                    f"TransactionID mismatch on 0x9052 response: expected {self._active_tx_id}, got {container.tx_id}."
                )
            if container.opcode_or_response != PTP_RC_OK:
                resp = container.opcode_or_response
                self._state = ProtocolGuardState.SESSION_OPEN
                self._active_tx_id = None
                self._active_property_id = None
                raise SecurityViolationError(f"0x9052 command rejected by camera: 0x{resp:04X}.")

            # Strict verification of response parameter declaring buffer length
            prop_key = self._active_property_id
            expected_len = EXPECTED_DATA_LENGTHS.get(prop_key, 0)
            params = container.get_params()
            if params != [expected_len]:
                self._state = ProtocolGuardState.SESSION_OPEN
                self._active_tx_id = None
                self._active_property_id = None
                raise SecurityViolationError(
                    f"0x9052 response parameter mismatch for Property 0x{prop_key:08X}: "
                    f"expected [{expected_len}], got {params}."
                )

            # Record used TxID and transition to expecting Fetch Command
            if self._active_tx_id is not None:
                self._used_tx_ids.add(self._active_tx_id)
            self._last_command_tx_id = self._active_tx_id
            self._active_tx_id = None
            self._state = ProtocolGuardState.WAITING_FETCH_COMMAND
            return

        # Case C: 0x9053 FA_Fetch Data IN Phase
        if self._state == ProtocolGuardState.WAITING_FETCH_DATA_IN:
            if not container.is_data:
                self._state = ProtocolGuardState.SESSION_OPEN
                self._active_fetch_tx_id = None
                self._active_property_id = None
                self._last_command_tx_id = None
                raise ProtocolSequenceError("Expected Data IN container for 0x9053 Fetch.")
            if container.tx_id != self._active_fetch_tx_id:
                self._state = ProtocolGuardState.SESSION_OPEN
                self._active_fetch_tx_id = None
                self._active_property_id = None
                self._last_command_tx_id = None
                raise SecurityViolationError(
                    f"TransactionID mismatch on Fetch Data IN: expected {self._active_fetch_tx_id}, got {container.tx_id}."
                )
            if container.opcode_or_response != PTP_OC_Canon_FA_Fetch:
                self._state = ProtocolGuardState.SESSION_OPEN
                self._active_fetch_tx_id = None
                self._active_property_id = None
                self._last_command_tx_id = None
                raise SecurityViolationError(
                    f"OpCode mismatch on Fetch Data IN: expected 0x9053, got 0x{container.opcode_or_response:04X}."
                )

            # Strict Payload Length Check
            prop_key = self._active_property_id
            expected_len = EXPECTED_DATA_LENGTHS.get(prop_key, 0)
            actual_len = len(container.payload_or_params)
            if actual_len != expected_len:
                self._state = ProtocolGuardState.SESSION_OPEN
                self._active_fetch_tx_id = None
                self._active_property_id = None
                self._last_command_tx_id = None
                raise SecurityViolationError(
                    f"Inbound Data length error for Property 0x{prop_key:08X}: "
                    f"expected {expected_len} bytes, received {actual_len} bytes."
                )

            self._state = ProtocolGuardState.WAITING_FETCH_RESPONSE
            return

        # Case D: 0x9053 FA_Fetch Final Response Phase
        if self._state == ProtocolGuardState.WAITING_FETCH_RESPONSE:
            if not container.is_response:
                self._state = ProtocolGuardState.SESSION_OPEN
                self._active_fetch_tx_id = None
                self._active_property_id = None
                self._last_command_tx_id = None
                raise ProtocolSequenceError("Expected final Response container for 0x9053 Fetch.")
            if container.tx_id != self._active_fetch_tx_id:
                self._state = ProtocolGuardState.SESSION_OPEN
                self._active_fetch_tx_id = None
                self._active_property_id = None
                self._last_command_tx_id = None
                raise SecurityViolationError(
                    f"TransactionID mismatch on Fetch response: expected {self._active_fetch_tx_id}, got {container.tx_id}."
                )
            if container.opcode_or_response != PTP_RC_OK:
                resp = container.opcode_or_response
                self._state = ProtocolGuardState.SESSION_OPEN
                self._active_fetch_tx_id = None
                self._active_property_id = None
                self._last_command_tx_id = None
                raise SecurityViolationError(f"Fetch response rejected: 0x{resp:04X}.")

            # Transaction complete: return to SESSION_OPEN
            if self._active_fetch_tx_id is not None:
                self._used_tx_ids.add(self._active_fetch_tx_id)
            self._state = ProtocolGuardState.SESSION_OPEN
            self._active_fetch_tx_id = None
            self._active_property_id = None
            self._last_command_tx_id = None
            return

        # Case E: CloseSession Response Phase
        if self._state == ProtocolGuardState.WAITING_CLOSE_RESPONSE:
            if not container.is_response:
                self.reset()
                raise ProtocolSequenceError("Expected Response container for CloseSession.")
            if container.tx_id != self._active_tx_id:
                self.reset()
                raise SecurityViolationError(
                    f"TransactionID mismatch on CloseSession response: expected {self._active_tx_id}, got {container.tx_id}."
                )
            if container.opcode_or_response != PTP_RC_OK:
                resp = container.opcode_or_response
                self.reset()
                raise SecurityViolationError(f"CloseSession rejected with ResponseCode 0x{resp:04X}.")

            # Teardown completed successfully
            self.reset()
            return

        raise ProtocolSequenceError(f"Unexpected inbound container in state {self._state.value}.")

    def validate_outgoing_command(
        self,
        opcode: int,
        tx_id: int,
        params: Optional[List[int]] = None,
        payload: Optional[bytes] = None,
    ) -> None:
        """
        Legacy / high-level validation adapter converting arguments to PtpContainer.
        """
        params = params or []
        if payload is not None:
            # Data container
            container = PtpContainer(
                length=12 + len(payload),
                container_type=PTP_CONTAINER_DATA,
                opcode_or_response=opcode,
                tx_id=tx_id,
                payload_or_params=payload,
            )
        else:
            # Command container
            param_bytes = b"".join(struct.pack("<I", p) for p in params)
            container = PtpContainer(
                length=12 + len(param_bytes),
                container_type=PTP_CONTAINER_COMMAND,
                opcode_or_response=opcode,
                tx_id=tx_id,
                payload_or_params=param_bytes,
            )

        self.validate_outgoing_container(container)

    def notify_command_sent(
        self,
        opcode: int,
        tx_id: int,
        params: Optional[List[int]] = None,
        payload: Optional[bytes] = None,
    ) -> None:
        """
        Legacy adapter for state notification. (Internal state is already updated in validate_outgoing_container).
        """
        pass
