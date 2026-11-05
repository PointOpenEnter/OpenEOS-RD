"""
Offline Mock Transport for OpenEOS PTP Service.
Simulates Canon EOS R6 Mark II PTP endpoint responses strictly based on р62.pcapng,
enforcing ISO 15740 container phase separation (Command, Data OUT, Data IN, Response)
and Protocol Guard inspection on all transactions.
"""

from __future__ import annotations

import struct
from typing import List, Optional, Tuple

from .constants import (
    PTP_CONTAINER_COMMAND,
    PTP_CONTAINER_DATA,
    PTP_CONTAINER_RESPONSE,
    PTP_OC_OpenSession,
    PTP_OC_CloseSession,
    PTP_OC_Canon_FA_Command,
    PTP_OC_Canon_FA_Fetch,
    PTP_RC_OK,
    PTP_RC_OperationNotSupported,
    PTP_RC_AccessDenied,
    PTP_RC_DeviceBusy,
    PROP_SHUTTER_COUNTER,
    PROP_RELEASE_TOTAL,
    PROP_POWER_AND_UPTIME,
)
from .protocol_guard import ProtocolGuard, SecurityViolationError, ProtocolSequenceError
from .payloads import (
    PtpContainer,
    build_ptp_response_container,
    parse_ptp_container,
)


class MockPtpTransport:
    """
    Simulates the Canon EOS R6 Mark II USB PTP stack in memory.
    Ensures all containers pass Protocol Guard validation before execution.
    """

    # Exact wire responses from р62.pcapng
    PCAPNG_SHUTTER_DATA = bytes.fromhex("11 ed 00 00 00 00 00 00")  # TxID 26: 60,689 + 00000000
    PCAPNG_RELEASE_DATA = bytes.fromhex("b9 d2 0c 00")              # TxID 32: 840,377
    PCAPNG_UPTIME_DATA = bytes.fromhex("60 17 00 00 07 c2 33 00")   # TxID 63: 5,984 + 3,392,007 s

    def __init__(self, guard: Optional[ProtocolGuard] = None):
        self.guard = guard or ProtocolGuard()
        self.is_connected = False
        self.active_session_id: Optional[int] = None
        self.last_property_queried: Optional[int] = None
        self.simulated_fault: Optional[int] = None
        self.simulate_timeout: bool = False
        self.container_log: List[PtpContainer] = []
        self._inbound_queue: List[PtpContainer] = []

    def reset(self) -> None:
        self.guard.reset()
        self.is_connected = False
        self.active_session_id = None
        self.last_property_queried = None
        self.simulated_fault = None
        self.simulate_timeout = False
        self.container_log.clear()
        self._inbound_queue.clear()

    def write_ptp_container(self, container: PtpContainer) -> int:
        """
        Accepts outbound PtpContainer, enforces PtpContainer type, validates via ProtocolGuard,
        and enqueues the simulated camera responses.
        """
        if not isinstance(container, PtpContainer):
            raise SecurityViolationError(f"Expected PtpContainer instance, got {type(container).__name__}")
        resp = self.send_container(container)
        if resp is not None:
            self._inbound_queue.append(resp)
            # If this was Fetch command (0x9053), also enqueue the trailing OK Response (Type 3)
            if container.opcode_or_response == PTP_OC_Canon_FA_Fetch and container.is_command:
                ok_resp = PtpContainer(
                    length=12,
                    container_type=PTP_CONTAINER_RESPONSE,
                    opcode_or_response=PTP_RC_OK,
                    tx_id=container.tx_id,
                    payload_or_params=b"",
                )
                self.guard.validate_inbound_container(ok_resp)
                self._inbound_queue.append(ok_resp)
        return container.length

    def read_ptp_container(self, max_buffer_size: int = 4096) -> PtpContainer:
        """Pops the next simulated inbound PtpContainer from the queue."""
        if not self._inbound_queue:
            raise TransportError("Mock transport inbound queue is empty (no response from camera).")
        return self._inbound_queue.pop(0)

    def authorize_live_session(self) -> None:
        pass

    def revoke_live_session(self) -> None:
        pass

    def send_container(self, container: PtpContainer) -> Optional[PtpContainer]:
        """
        Sends an outbound PtpContainer through the Protocol Guard.
        Returns the simulated camera's immediate response container (if applicable).
        """
        # 1. Inspect outbound container via Protocol Guard
        self.guard.validate_outgoing_container(container)

        if self.simulate_timeout:
            raise TimeoutError("Simulated USB transport pipe timeout (device not responding).")

        self.container_log.append(container)

        # 2. Check injected fault code
        if self.simulated_fault is not None:
            fault_code = self.simulated_fault
            self.simulated_fault = None
            resp = PtpContainer(
                length=12,
                container_type=PTP_CONTAINER_RESPONSE,
                opcode_or_response=fault_code,
                tx_id=container.tx_id,
                payload_or_params=b"",
            )
            self.guard.validate_inbound_container(resp)
            return resp

        # 3. Simulate camera responses per phase
        opcode = container.opcode_or_response
        tx_id = container.tx_id

        # Phase A: OpenSession Command
        if opcode == PTP_OC_OpenSession and container.is_command:
            self.is_connected = True
            params = container.get_params()
            self.active_session_id = params[0] if params else 1
            resp = PtpContainer(
                length=12,
                container_type=PTP_CONTAINER_RESPONSE,
                opcode_or_response=PTP_RC_OK,
                tx_id=tx_id,
                payload_or_params=b"",
            )
            self.guard.validate_inbound_container(resp)
            return resp

        # Phase B: CloseSession Command
        elif opcode == PTP_OC_CloseSession and container.is_command:
            self.is_connected = False
            self.active_session_id = None
            self.last_property_queried = None
            resp = PtpContainer(
                length=12,
                container_type=PTP_CONTAINER_RESPONSE,
                opcode_or_response=PTP_RC_OK,
                tx_id=tx_id,
                payload_or_params=b"",
            )
            self.guard.reset()
            return resp

        # Phase C: 0x9052 Command Container
        elif opcode == PTP_OC_Canon_FA_Command and container.is_command:
            # Device acknowledges command and waits for Data OUT phase. No wire response yet.
            return None

        # Phase D: 0x9052 Data OUT Container
        elif opcode == PTP_OC_Canon_FA_Command and container.is_data:
            prop_key = struct.unpack("<I", container.payload_or_params[23:27])[0]
            self.last_property_queried = prop_key

            # In р62.pcapng, camera replies with 0x2001 and param = [declared length]
            declared_len = 4 if prop_key == PROP_RELEASE_TOTAL else 8
            resp_bytes = struct.pack("<I", declared_len)
            resp = PtpContainer(
                length=16,
                container_type=PTP_CONTAINER_RESPONSE,
                opcode_or_response=PTP_RC_OK,
                tx_id=tx_id,
                payload_or_params=resp_bytes,
            )
            self.guard.validate_inbound_container(resp)
            return resp

        # Phase E: 0x9053 Command Container (Trigger Fetch)
        elif opcode == PTP_OC_Canon_FA_Fetch and container.is_command:
            # Camera responds with:
            # 1. Data IN container
            # 2. Followed by Response container (Type 3, 0x2001)
            prop_key = self.last_property_queried
            self.last_property_queried = None

            if prop_key == PROP_SHUTTER_COUNTER:
                payload = self.PCAPNG_SHUTTER_DATA
            elif prop_key == PROP_RELEASE_TOTAL:
                payload = self.PCAPNG_RELEASE_DATA
            elif prop_key == PROP_POWER_AND_UPTIME:
                payload = self.PCAPNG_UPTIME_DATA
            else:
                payload = b""

            # Data IN container
            data_in = PtpContainer(
                length=12 + len(payload),
                container_type=PTP_CONTAINER_DATA,
                opcode_or_response=PTP_OC_Canon_FA_Fetch,
                tx_id=tx_id,
                payload_or_params=payload,
            )
            self.guard.validate_inbound_container(data_in)

            # Response container
            resp = PtpContainer(
                length=12,
                container_type=PTP_CONTAINER_RESPONSE,
                opcode_or_response=PTP_RC_OK,
                tx_id=tx_id,
                payload_or_params=b"",
            )
            self.guard.validate_inbound_container(resp)

            # Return the Data IN container to the caller
            return data_in

        raise SecurityViolationError(f"Unhandled container in mock transport: {container}")

    def send_command(
        self,
        opcode: int,
        tx_id: int,
        params: Optional[List[int]] = None,
        payload: Optional[bytes] = None,
    ) -> Tuple[int, Optional[bytes], List[int]]:
        """
        High-level compatibility helper executing a complete transaction step.
        """
        params = params or []
        if opcode == PTP_OC_Canon_FA_Command:
            # Send Command Container
            param_bytes = b"".join(struct.pack("<I", p) for p in params)
            cmd_c = PtpContainer(
                length=12 + len(param_bytes),
                container_type=PTP_CONTAINER_COMMAND,
                opcode_or_response=opcode,
                tx_id=tx_id,
                payload_or_params=param_bytes,
            )
            self.send_container(cmd_c)

            # Send Data OUT Container
            assert payload is not None
            data_c = PtpContainer(
                length=12 + len(payload),
                container_type=PTP_CONTAINER_DATA,
                opcode_or_response=opcode,
                tx_id=tx_id,
                payload_or_params=payload,
            )
            resp = self.send_container(data_c)
            assert resp is not None
            return resp.opcode_or_response, None, resp.get_params()

        elif opcode == PTP_OC_Canon_FA_Fetch:
            param_bytes = b"".join(struct.pack("<I", p) for p in params)
            cmd_c = PtpContainer(
                length=12 + len(param_bytes),
                container_type=PTP_CONTAINER_COMMAND,
                opcode_or_response=opcode,
                tx_id=tx_id,
                payload_or_params=param_bytes,
            )
            data_in = self.send_container(cmd_c)
            assert data_in is not None
            return PTP_RC_OK, data_in.payload_or_params, []

        else:
            # Standard single command (OpenSession, CloseSession)
            param_bytes = b"".join(struct.pack("<I", p) for p in params)
            cmd_c = PtpContainer(
                length=12 + len(param_bytes),
                container_type=PTP_CONTAINER_COMMAND,
                opcode_or_response=opcode,
                tx_id=tx_id,
                payload_or_params=param_bytes,
            )
            resp = self.send_container(cmd_c)
            assert resp is not None
            return resp.opcode_or_response, None, resp.get_params()
