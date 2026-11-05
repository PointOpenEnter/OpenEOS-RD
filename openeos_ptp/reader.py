"""
OpenEOS Live Camera Counter Reader (Canon EOS R6 Mark II).
Dedicated operational module for reading live camera actuation counters:
  - Property 0x12000001: Shutter Counter (нейтральное обозначение)
  - Property 0x12000003: Release Counter Total

STRICT ARCHITECTURAL INVARIANTS:
1. Zero-Mock / Zero-Cache: Every value is retrieved dynamically from the active physical PTP session.
   No values from PCAPNG, reports, CSV, or prior runs are permitted in runtime logic.
2. Scope restriction: Property 0x12000005 is strictly excluded at this stage.
3. Every packet is constructed as an ISO 15740 PtpContainer and strictly validated:
   - Container type
   - Response code (0x2001 OK)
   - Transaction ID exact match
   - Data IN payload length (8 bytes for 0x12000001, 4 bytes for 0x12000003)
   - Absence of unexpected or malformed containers
4. Controlled authorization lifecycle: physical USB I/O is enabled only during explicit read calls
   and revoked immediately in finally blocks.
5. Returns comprehensive diagnostic telemetry for each transaction.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

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
    PROP_SHUTTER_COUNTER,
    PROP_RELEASE_TOTAL,
    CANON_EOS_R6_MARK_II_PID,
    CANON_EOS_R10_PID,
    CANON_VID,
)
from .payloads import (
    PtpContainer,
    build_ptp_command_container,
    build_fa_command_container,
    build_fa_get_property_container,
    build_fa_fetch_command,
)
from .decoders import (
    decode_shutter_counter,
    decode_release_counter,
    DecoderError,
)
from .protocol_guard import ProtocolGuard, SecurityViolationError, ProtocolSequenceError
from .transport import (
    ProtectedUsbPtpTransport,
    CameraAccessManager,
    StillImageDeviceFinder,
    SafeDeviceHandle,
    set_usbscan_timeouts,
    TransportError,
    TransportAuthorizationError,
    DeviceNotFoundError,
    DeviceAccessDeniedError,
)

PTP_RESPONSE_NAMES = {
    0x2001: "OK",
    0x2002: "GeneralError",
    0x2003: "SessionNotOpen",
    0x2004: "InvalidTransactionID",
    0x2005: "OperationNotSupported",
    0x2006: "ParameterNotSupported",
    0x2007: "IncompleteTransfer",
    0x2008: "InvalidStorageID",
    0x2009: "InvalidObjectHandle",
    0x200A: "DevicePropNotSupported",
    0x200B: "InvalidObjectFormatCode",
    0x200C: "StoreFull",
    0x200D: "ObjectWriteProtected",
    0x200E: "StoreReadOnly",
    0x200F: "AccessDenied",
    0x2014: "SpecificationByFormatUnsupported",
    0x2017: "UnknownVendorCode",
    0x2019: "DeviceBusy",
    0x201D: "InvalidParameter",
    0x201E: "SessionAlreadyOpen",
    0x201F: "TransactionCanceled",
}


@dataclass
class PropertyDiagnosticRecord:
    """Diagnostic telemetry record for an individual PTP property query."""
    source: str
    request_time: str
    property_id: str
    property_name: str
    raw_bytes_hex: str
    decoded_value: Optional[int]
    status: str
    error_message: Optional[str] = None
    request_sent: str = ""
    response_code_hex: str = ""
    tx_id: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "request_time": self.request_time,
            "property_id": self.property_id,
            "property_name": self.property_name,
            "request_sent": self.request_sent,
            "response_code_hex": self.response_code_hex,
            "tx_id": self.tx_id,
            "raw_bytes_hex": self.raw_bytes_hex,
            "decoded_value": self.decoded_value,
            "status": self.status,
            "error_message": self.error_message,
        }


@dataclass
class LiveCameraReadResult:
    """Consolidated readout result from an active camera interrogation session."""
    source: str
    timestamp: str
    counter_0x12000001: Optional[int] = None
    raw_0x12000001_hex: Optional[str] = None
    counter_0x12000003: Optional[int] = None
    raw_0x12000003_hex: Optional[str] = None
    status: str = "ERROR"
    error_message: Optional[str] = None
    diagnostics: List[PropertyDiagnosticRecord] = field(default_factory=list)

    # Aliases for backwards compatibility with existing UI
    @property
    def shutter_counter(self) -> Optional[int]:
        return self.counter_0x12000001

    @property
    def shutter_raw_hex(self) -> Optional[str]:
        return self.raw_0x12000001_hex

    @property
    def release_total(self) -> Optional[int]:
        return self.counter_0x12000003

    @property
    def release_raw_hex(self) -> Optional[str]:
        return self.raw_0x12000003_hex

    @property
    def is_success(self) -> bool:
        return self.status == "SUCCESS" and self.counter_0x12000001 is not None and self.counter_0x12000003 is not None


class LiveCameraReader:
    """
    Executes the exact 2-property Canon Service PTP readout sequence
    over an authenticated, protected transport channel.
    """

    def __init__(self, transport: Any, authorize_live_io: bool = False):
        """
        Accepts any transport providing write_ptp_container() and read_ptp_container().
        If authorize_live_io is False and transport requires authorization,
        read_counters() will safely reject physical dispatch.
        """
        self._transport = transport
        self._default_authorize_live_io = authorize_live_io

    @staticmethod
    def _assert_response(
        container: PtpContainer,
        expected_tx_id: int,
        expected_code: int = PTP_RC_OK,
        expected_param_count: Optional[int] = None,
    ) -> List[int]:
        """Validates that a received container is a valid PTP Response with exact matching parameters."""
        if not isinstance(container, PtpContainer):
            raise TransportError(f"Получен некорректный объект ответа: {type(container).__name__}")
        if not container.is_response:
            raise TransportError(
                f"Нарушение протокола PTP: ожидался Response-контейнер (тип 3), "
                f"фактически получен контейнер типа {container.container_type}."
            )
        if container.tx_id != expected_tx_id:
            raise TransportError(
                f"Несовпадение Transaction ID: ожидался {expected_tx_id}, "
                f"камера вернула {container.tx_id}."
            )
        if container.opcode_or_response != expected_code:
            raise TransportError(
                f"Камера отклонила операцию: ResponseCode 0x{container.opcode_or_response:04X} "
                f"(ожидался 0x{expected_code:04X} OK)."
            )
        params = container.get_params()
        if expected_param_count is not None and len(params) != expected_param_count:
            raise TransportError(
                f"Неверное число параметров ответа: ожидалось {expected_param_count}, получено {len(params)}."
            )
        return params

    @staticmethod
    def _assert_data_in(
        container: PtpContainer,
        expected_tx_id: int,
        expected_opcode: int,
        expected_payload_length: int,
    ) -> bytes:
        """Validates that a received container is a valid PTP Data IN container with exact matching payload."""
        if not isinstance(container, PtpContainer):
            raise TransportError(f"Получен некорректный объект данных: {type(container).__name__}")
        if not container.is_data:
            raise TransportError(
                f"Нарушение протокола PTP: ожидался Data IN-контейнер (тип 2), "
                f"фактически получен контейнер типа {container.container_type}."
            )
        if container.tx_id != expected_tx_id:
            raise TransportError(
                f"Несовпадение Transaction ID в Data IN: ожидался {expected_tx_id}, "
                f"камера вернула {container.tx_id}."
            )
        if container.opcode_or_response != expected_opcode:
            raise TransportError(
                f"Неверный OpCode в Data IN: ожидался 0x{expected_opcode:04X}, "
                f"камера вернула 0x{container.opcode_or_response:04X}."
            )
        actual_len = len(container.payload_or_params)
        if actual_len != expected_payload_length:
            raise TransportError(
                f"Неверная длина полезной нагрузки Data IN: ожидалось {expected_payload_length} байт, "
                f"получено {actual_len} байт."
            )
        expected_container_len = 12 + expected_payload_length
        if container.length != expected_container_len:
            raise TransportError(
                f"Нарушение структуры контейнера Data IN: объявленная длина {container.length} байт "
                f"не равна ожидаемой {expected_container_len} байт."
            )
        return bytes(container.payload_or_params)

    def read_counters(self, authorize_live_io: Optional[bool] = None) -> LiveCameraReadResult:
        """
        Executes the live counter retrieval pipeline:
          1. Check authorization gate (refuse without authorization)
          2. OpenSession (TxID 1)
          3. Query Property 0x12000001: Command (TxID 2) + Fetch (TxID 3)
          4. Query Property 0x12000003: Command (TxID 4) + Fetch (TxID 5)
          5. CloseSession (TxID 6)
        """
        session_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        diagnostics: List[PropertyDiagnosticRecord] = []
        val_01: Optional[int] = None
        hex_01: Optional[str] = None
        val_03: Optional[int] = None
        hex_03: Optional[str] = None
        session_opened = False

        should_authorize = self._default_authorize_live_io if authorize_live_io is None else authorize_live_io
        is_live_transport = hasattr(self._transport, "authorize_live_session") and hasattr(self._transport, "revoke_live_session")
        already_authorized = getattr(self._transport, "is_live_session_authorized", False)

        # -----------------------------------------------------------------
        # Authorization Gate Check
        # -----------------------------------------------------------------
        if is_live_transport and not should_authorize and not already_authorized:
            return LiveCameraReadResult(
                source="Физическая камера",
                timestamp=session_time,
                status="ERROR",
                error_message="Отказ в доступе: физический ввод-вывод к камере не авторизован. Требуется явный вызов чтения.",
                diagnostics=[],
            )

        if is_live_transport and should_authorize:
            self._transport.authorize_live_session()

        try:
            # -------------------------------------------------------------
            # Step 1: OpenSession (TxID = 1, SessionID = 1)
            # -------------------------------------------------------------
            open_cmd = build_ptp_command_container(PTP_OC_OpenSession, tx_id=1, params=[1])
            self._transport.write_ptp_container(open_cmd)
            open_resp = self._transport.read_ptp_container()

            self._assert_response(
                open_resp,
                expected_tx_id=1,
                expected_code=PTP_RC_OK,
                expected_param_count=0,
            )
            session_opened = True

            # -------------------------------------------------------------
            # Step 2: Query Property 0x12000001 (Shutter Counter)
            # -------------------------------------------------------------
            t_shutter = datetime.datetime.now(datetime.timezone.utc).isoformat()
            req_01_desc = "0x9052 (FA_GetProperty [0x12000001]) + 0x9053 (FA_Fetch)"
            try:
                # 2a. Command Phase (TxID = 2)
                cmd_25 = build_fa_command_container(tx_id=2, params=[0, 1])
                self._transport.write_ptp_container(cmd_25)

                # 2b. Data OUT Phase (TxID = 2)
                data_25 = build_fa_get_property_container(tx_id=2, property_id=PROP_SHUTTER_COUNTER)
                self._transport.write_ptp_container(data_25)

                # 2c. Command Response Phase
                resp_25 = self._transport.read_ptp_container()
                resp_code_01 = resp_25.opcode_or_response
                tx_01 = resp_25.tx_id

                if resp_code_01 != PTP_RC_OK:
                    rc_name = PTP_RESPONSE_NAMES.get(resp_code_01, f"0x{resp_code_01:04X}")
                    diagnostics.append(PropertyDiagnosticRecord(
                        source="Физическая камера",
                        request_time=t_shutter,
                        property_id="0x12000001",
                        property_name="Свойство 0x12000001 (Shutter Counter)",
                        request_sent=req_01_desc,
                        response_code_hex=f"0x{resp_code_01:04X} ({rc_name})",
                        tx_id=tx_01,
                        raw_bytes_hex="[отклонено камерой]",
                        decoded_value=None,
                        status="UNSUPPORTED" if resp_code_01 == 0x2005 else "REJECTED",
                        error_message=f"Камера отклонила операцию 0x9052: ResponseCode 0x{resp_code_01:04X} ({rc_name})",
                    ))
                else:
                    params_25 = resp_25.get_params()
                    if params_25 != [8]:
                        diagnostics.append(PropertyDiagnosticRecord(
                            source="Физическая камера",
                            request_time=t_shutter,
                            property_id="0x12000001",
                            property_name="Свойство 0x12000001 (Shutter Counter)",
                            request_sent=req_01_desc,
                            response_code_hex="0x2001 (OK)",
                            tx_id=tx_01,
                            raw_bytes_hex=f"[неожиданная длина буфера: {params_25}]",
                            decoded_value=None,
                            status="ERROR",
                            error_message=f"Камера объявила неожиданную длину буфера для 0x12000001: {params_25}, ожидалось [8].",
                        ))
                    else:
                        # 2d. Fetch Command Phase (TxID = 3)
                        fetch_26 = build_fa_fetch_command(tx_id=3, property_id=PROP_SHUTTER_COUNTER)
                        self._transport.write_ptp_container(fetch_26)

                        # 2e. Fetch Data IN Phase: exactly 8 bytes
                        data_in_26 = self._transport.read_ptp_container()
                        raw_bytes_shutter = self._assert_data_in(
                            data_in_26,
                            expected_tx_id=3,
                            expected_opcode=PTP_OC_Canon_FA_Fetch,
                            expected_payload_length=8,
                        )
                        hex_01 = raw_bytes_shutter.hex(" ")

                        # 2f. Fetch Response Phase (TxID = 3)
                        resp_26 = self._transport.read_ptp_container()
                        self._assert_response(
                            resp_26,
                            expected_tx_id=3,
                            expected_code=PTP_RC_OK,
                            expected_param_count=0,
                        )

                        # 2g. Pure byte decoding
                        decoded_shutter = decode_shutter_counter(raw_bytes_shutter)
                        val_01 = decoded_shutter.shutter_counter

                        diagnostics.append(PropertyDiagnosticRecord(
                            source="Физическая камера",
                            request_time=t_shutter,
                            property_id="0x12000001",
                            property_name="Свойство 0x12000001 (Shutter Counter)",
                            request_sent=req_01_desc,
                            response_code_hex="0x2001 (OK)",
                            tx_id=3,
                            raw_bytes_hex=hex_01,
                            decoded_value=val_01,
                            status="SUCCESS",
                        ))
            except Exception as ex_01:
                diagnostics.append(PropertyDiagnosticRecord(
                    source="Физическая камера",
                    request_time=t_shutter,
                    property_id="0x12000001",
                    property_name="Свойство 0x12000001 (Shutter Counter)",
                    request_sent=req_01_desc,
                    response_code_hex="ERROR",
                    tx_id=2,
                    raw_bytes_hex="[сбой опроса]",
                    decoded_value=None,
                    status="ERROR",
                    error_message=str(ex_01),
                ))

            # -------------------------------------------------------------
            # Step 3: Query Property 0x12000003 (Release Counter Total)
            # -------------------------------------------------------------
            t_release = datetime.datetime.now(datetime.timezone.utc).isoformat()
            req_03_desc = "0x9052 (FA_GetProperty [0x12000003]) + 0x9053 (FA_Fetch)"
            try:
                # 3a. Command Phase (TxID = 4)
                cmd_31 = build_fa_command_container(tx_id=4, params=[0, 1])
                self._transport.write_ptp_container(cmd_31)

                # 3b. Data OUT Phase (TxID = 4)
                data_31 = build_fa_get_property_container(tx_id=4, property_id=PROP_RELEASE_TOTAL)
                self._transport.write_ptp_container(data_31)

                # 3c. Command Response Phase
                resp_31 = self._transport.read_ptp_container()
                resp_code_03 = resp_31.opcode_or_response
                tx_03 = resp_31.tx_id

                if resp_code_03 != PTP_RC_OK:
                    rc_name = PTP_RESPONSE_NAMES.get(resp_code_03, f"0x{resp_code_03:04X}")
                    diagnostics.append(PropertyDiagnosticRecord(
                        source="Физическая камера",
                        request_time=t_release,
                        property_id="0x12000003",
                        property_name="Свойство 0x12000003 (Release Counter Total)",
                        request_sent=req_03_desc,
                        response_code_hex=f"0x{resp_code_03:04X} ({rc_name})",
                        tx_id=tx_03,
                        raw_bytes_hex="[отклонено камерой]",
                        decoded_value=None,
                        status="UNSUPPORTED" if resp_code_03 == 0x2005 else "REJECTED",
                        error_message=f"Камера отклонила операцию 0x9052: ResponseCode 0x{resp_code_03:04X} ({rc_name})",
                    ))
                else:
                    params_31 = resp_31.get_params()
                    if params_31 != [4]:
                        diagnostics.append(PropertyDiagnosticRecord(
                            source="Физическая камера",
                            request_time=t_release,
                            property_id="0x12000003",
                            property_name="Свойство 0x12000003 (Release Counter Total)",
                            request_sent=req_03_desc,
                            response_code_hex="0x2001 (OK)",
                            tx_id=tx_03,
                            raw_bytes_hex=f"[неожиданная длина буфера: {params_31}]",
                            decoded_value=None,
                            status="ERROR",
                            error_message=f"Камера объявила неожиданную длину буфера для 0x12000003: {params_31}, ожидалось [4].",
                        ))
                    else:
                        # 3d. Fetch Command Phase (TxID = 5)
                        fetch_32 = build_fa_fetch_command(tx_id=5, property_id=PROP_RELEASE_TOTAL)
                        self._transport.write_ptp_container(fetch_32)

                        # 3e. Fetch Data IN Phase: exactly 4 bytes
                        data_in_32 = self._transport.read_ptp_container()
                        raw_bytes_release = self._assert_data_in(
                            data_in_32,
                            expected_tx_id=5,
                            expected_opcode=PTP_OC_Canon_FA_Fetch,
                            expected_payload_length=4,
                        )
                        hex_03 = raw_bytes_release.hex(" ")

                        # 3f. Fetch Response Phase (TxID = 5)
                        resp_32 = self._transport.read_ptp_container()
                        self._assert_response(
                            resp_32,
                            expected_tx_id=5,
                            expected_code=PTP_RC_OK,
                            expected_param_count=0,
                        )

                        # 3g. Pure byte decoding
                        decoded_release = decode_release_counter(raw_bytes_release)
                        val_03 = decoded_release.release_counter_total

                        diagnostics.append(PropertyDiagnosticRecord(
                            source="Физическая камера",
                            request_time=t_release,
                            property_id="0x12000003",
                            property_name="Свойство 0x12000003 (Release Counter Total)",
                            request_sent=req_03_desc,
                            response_code_hex="0x2001 (OK)",
                            tx_id=5,
                            raw_bytes_hex=hex_03,
                            decoded_value=val_03,
                            status="SUCCESS",
                        ))
            except Exception as ex_03:
                diagnostics.append(PropertyDiagnosticRecord(
                    source="Физическая камера",
                    request_time=t_release,
                    property_id="0x12000003",
                    property_name="Свойство 0x12000003 (Release Counter Total)",
                    request_sent=req_03_desc,
                    response_code_hex="ERROR",
                    tx_id=4,
                    raw_bytes_hex="[сбой опроса]",
                    decoded_value=None,
                    status="ERROR",
                    error_message=str(ex_03),
                ))

            # Determine overall session status
            success_count = sum(1 for d in diagnostics if d.status == "SUCCESS")
            unsupported_count = sum(1 for d in diagnostics if d.status == "UNSUPPORTED")
            if success_count == len(diagnostics) and len(diagnostics) == 2:
                overall_status = "SUCCESS"
                err_text = None
            elif success_count > 0:
                overall_status = "PARTIAL_SUCCESS"
                err_text = "Частичное чтение: одно или несколько свойств не поддерживаются камерой."
            elif unsupported_count == len(diagnostics) and len(diagnostics) > 0:
                overall_status = "UNSUPPORTED"
                err_text = "Камера отклонила операцию 0x9052: свойства не поддерживаются в текущем режиме."
            else:
                overall_status = "ERROR"
                err_text = "Сбой при чтении PTP-свойств камеры."

            return LiveCameraReadResult(
                source="Физическая камера",
                timestamp=session_time,
                counter_0x12000001=val_01,
                raw_0x12000001_hex=hex_01,
                counter_0x12000003=val_03,
                raw_0x12000003_hex=hex_03,
                status=overall_status,
                error_message=err_text,
                diagnostics=diagnostics,
            )

        except Exception as exc:
            return LiveCameraReadResult(
                source="Физическая камера",
                timestamp=session_time,
                counter_0x12000001=val_01,
                raw_0x12000001_hex=hex_01,
                counter_0x12000003=val_03,
                raw_0x12000003_hex=hex_03,
                status="ERROR",
                error_message=str(exc),
                diagnostics=diagnostics,
            )

        finally:
            # -------------------------------------------------------------
            # Step 5: CloseSession (TxID = 6) - Guaranteed in finally
            # -------------------------------------------------------------
            if session_opened:
                try:
                    close_cmd = build_ptp_command_container(PTP_OC_CloseSession, tx_id=6, params=[])
                    self._transport.write_ptp_container(close_cmd)
                    close_resp = self._transport.read_ptp_container()
                    self._assert_response(
                        close_resp,
                        expected_tx_id=6,
                        expected_code=PTP_RC_OK,
                        expected_param_count=0,
                    )
                except Exception:
                    pass

            # Always revoke authorization on completion
            if is_live_transport and should_authorize:
                self._transport.revoke_live_session()


def read_live_counters(
    device_path: Optional[str] = None,
    target_pid: Optional[int] = None,
    access_manager: Optional[CameraAccessManager] = None,
    edsdk_status_callback: Optional[Callable[[], bool]] = None,
    edsdk_close_callback: Optional[Callable[[], None]] = None,
    edsdk_restore_callback: Optional[Callable[[], None]] = None,
    timeout_read_ms: int = 5000,
    timeout_write_ms: int = 5000,
    authorize_live_io: bool = False,
) -> LiveCameraReadResult:
    """
    High-level entry point to discover connected Canon camera (R10, R6 Mark II, etc.),
    acquire exclusive Win32 device handle, initialize ProtectedUsbPtpTransport,
    and read live counters. Physical I/O is guarded by authorize_live_io parameter.
    """
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if not authorize_live_io:
        return LiveCameraReadResult(
            source="Физическая камера",
            timestamp=timestamp,
            status="ERROR",
            error_message="Отказ в доступе: физический ввод-вывод к камере не авторизован (authorize_live_io=False).",
            diagnostics=[],
        )

    # 1. Device discovery if path not provided
    if device_path is None:
        target_camera = None
        if target_pid == CANON_EOS_R10_PID:
            target_camera = StillImageDeviceFinder.find_r10()
        elif target_pid == CANON_EOS_R6_MARK_II_PID:
            target_camera = StillImageDeviceFinder.find_r6_mark_ii()

        if target_camera is None:
            target_camera = StillImageDeviceFinder.find_first_canon()

        if target_camera is None:
            return LiveCameraReadResult(
                source="Физическая камера",
                timestamp=timestamp,
                status="ERROR",
                error_message="Камера Canon не обнаружена в системе (USB кабель отключён или драйвер не готов).",
            )
        device_path = target_camera.device_path

    # 2. Access Manager configuration
    mgr = access_manager or CameraAccessManager(
        edsdk_status_callback=edsdk_status_callback or (lambda: False),
        edsdk_close_callback=edsdk_close_callback,
        edsdk_restore_callback=edsdk_restore_callback,
    )

    def _interrogate_callback(safe_handle: SafeDeviceHandle) -> LiveCameraReadResult:
        # Step A: Configure driver timeouts
        try:
            set_usbscan_timeouts(
                safe_handle.handle,
                timeout_read_ms=timeout_read_ms,
                timeout_write_ms=timeout_write_ms,
            )
        except Exception:
            pass

        # Step B: Instantiate Protocol Guard and Protected Transport
        guard = ProtocolGuard()
        transport = ProtectedUsbPtpTransport(safe_handle, guard=guard)

        # Step C: Execute Live Readout under explicit authorization
        reader = LiveCameraReader(transport, authorize_live_io=True)
        return reader.read_counters(authorize_live_io=True)

    try:
        return mgr.execute_with_exclusive_access(
            device_path=device_path,
            callback=_interrogate_callback,
        )
    except DeviceNotFoundError as exc:
        return LiveCameraReadResult(
            source="Физическая камера",
            timestamp=timestamp,
            status="ERROR",
            error_message=f"Ошибка обнаружения устройства: {exc}",
        )
    except DeviceAccessDeniedError as exc:
        return LiveCameraReadResult(
            source="Физическая камера",
            timestamp=timestamp,
            status="ERROR",
            error_message=f"Доступ к камере заблокирован другим процессом (EDSDK/EOS Utility): {exc}",
        )
    except Exception as exc:
        return LiveCameraReadResult(
            source="Физическая камера",
            timestamp=timestamp,
            status="ERROR",
            error_message=f"Сбой при чтении камеры: {exc}",
        )


# Backward compatibility alias
read_r6m2_live_counters = read_live_counters
