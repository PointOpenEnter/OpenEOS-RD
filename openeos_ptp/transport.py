"""
Windows Still Image (STI / usbscan.sys) and USB Transport Harness for OpenEOS.
Implements device enumeration, pipe configuration querying (IOCTL_GET_PIPE_CONFIGURATION),
safe handle lifecycle management, and CameraAccessManager for coordinated EDSDK / Direct PTP arbitration.

STRICT INVARIANT: No PTP containers or sessions are dispatched in Phase B.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import re
import struct
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple, TypeVar

from .constants import (
    CANON_VID,
    CANON_EOS_R6_MARK_II_PID,
    CANON_EOS_R10_PID,
    SUPPORTED_DEVICES,
    GUID_DEVINTERFACE_IMAGE,
    GUID_DEVINTERFACE_WPD,
    IOCTL_GET_PIPE_CONFIGURATION,
    IOCTL_SET_TIMEOUT,
    IOCTL_RESET_PIPE,
    IOCTL_WAIT_ON_DEVICE_EVENT,
    IOCTL_CANCEL_IO,
    USBSCAN_PIPE_TYPE,
    USBSCAN_RAW_PIPE_TYPE,
    DIGCF_PRESENT,
    DIGCF_DEVICEINTERFACE,
)
from .payloads import PtpContainer
from .protocol_guard import ProtocolGuard, SecurityViolationError

# Win32 Constants
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
ERROR_ACCESS_DENIED = 5
ERROR_SHARING_VIOLATION = 32
ERROR_DEVICE_NOT_CONNECTED = 1167
ERROR_SEM_TIMEOUT = 121

# Microsoft usbscan.sys definitions (usbscan.h)
USBSCAN_MAX_NUM_PIPES = 8

# RAW_PIPE_TYPE name mapping (from USBSCAN_RAW_PIPE_TYPE)
PIPE_TYPE_NAMES = {
    int(USBSCAN_RAW_PIPE_TYPE.PIPE_TYPE_CONTROL): "CONTROL",
    int(USBSCAN_RAW_PIPE_TYPE.PIPE_TYPE_ISOCHRONOUS): "ISOCHRONOUS",
    int(USBSCAN_RAW_PIPE_TYPE.PIPE_TYPE_BULK_IN): "BULK_IN",
    int(USBSCAN_RAW_PIPE_TYPE.PIPE_TYPE_BULK_OUT): "BULK_OUT",
    int(USBSCAN_RAW_PIPE_TYPE.PIPE_TYPE_INTERRUPT): "INTERRUPT_IN",
}


# Windows SetupAPI and Win32 GUID structures
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def guid_from_string(guid_str: str) -> GUID:
    """Parses a standard Windows GUID string into a ctypes GUID structure."""
    clean = guid_str.strip("{}")
    parts = clean.split("-")
    data1 = int(parts[0], 16)
    data2 = int(parts[1], 16)
    data3 = int(parts[2], 16)
    data4_bytes = bytes.fromhex(parts[3] + parts[4])
    return GUID(data1, data2, data3, (ctypes.c_ubyte * 8)(*data4_bytes))


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("InterfaceClassGuid", GUID),
        ("Flags", ctypes.c_ulong),
        ("Reserved", ctypes.c_void_p),
    ]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("ClassGuid", GUID),
        ("DevInst", ctypes.c_ulong),
        ("Reserved", ctypes.c_void_p),
    ]


class USBSCAN_PIPE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("MaximumPacketSize", ctypes.c_ushort),
        ("EndpointAddress", ctypes.c_ubyte),
        ("Interval", ctypes.c_ubyte),
        ("PipeType", ctypes.c_uint),  # USBSCAN_RAW_PIPE_TYPE
    ]


class USBSCAN_PIPE_CONFIGURATION(ctypes.Structure):
    _fields_ = [
        ("NumberOfPipes", ctypes.c_ulong),
        ("PipeInfo", USBSCAN_PIPE_INFORMATION * USBSCAN_MAX_NUM_PIPES),
    ]


class USBSCAN_TIMEOUT(ctypes.Structure):
    """
    Microsoft usbscan.h USBSCAN_TIMEOUT structure.
    Used with IOCTL_SET_TIMEOUT (0x80000014).
    All timeout values are expressed in milliseconds.
    """
    _fields_ = [
        ("TimeoutRead", ctypes.c_ulong),
        ("TimeoutWrite", ctypes.c_ulong),
        ("TimeoutEvent", ctypes.c_ulong),
    ]


class TransportError(Exception):
    """Base exception for all transport errors."""
    pass


class TransportAuthorizationError(TransportError, RuntimeError):
    """
    Raised when physical USB wire transmission/reception is attempted without explicit authorization.
    Inherits from both TransportError and RuntimeError to preserve backwards compatibility with Phase B tests.
    """
    pass


class DeviceNotFoundError(TransportError):
    """Raised when no matching Still Image device is detected."""
    pass


class DeviceAccessDeniedError(TransportError):
    """Raised when the device handle cannot be opened due to exclusivity locks."""
    pass


class DeviceBusyError(TransportError):
    """Raised when an operation times out waiting for the device."""
    pass


class PipeConfigurationError(TransportError):
    """Raised when the USB interface does not match required Bulk IN/OUT pipe specifications."""
    pass


@dataclass(frozen=True)
class PipeInfo:
    """
    Information about an enumerated USB pipe reported by IOCTL_GET_PIPE_CONFIGURATION.
    
    IMPORTANT MICROSOFT USBSCAN SPECIFICATION:
      - endpoint_address: Hardware USB endpoint address (e.g. 0x02, 0x81, 0x83).
      - pipe_index: 0-based index in the USBSCAN_PIPE_CONFIGURATION.PipeInfo array.
        Per Microsoft WDK documentation, IOCTL_RESET_PIPE and IOCTL_CANCEL_IO take
        a functional PIPE_TYPE enum (EVENT_PIPE, READ_DATA_PIPE, WRITE_DATA_PIPE, ALL_PIPE),
        NOT an integer pipe array index.
      - For multi-channel devices requiring a specific pipe handle, usbscan supports
        appending a "\\<pipe_index>" suffix to the port name upon CreateFile. For Canon EOS
        cameras with single Bulk IN / Bulk OUT / Interrupt IN endpoints, opening the base
        device path binds ReadFile/WriteFile to default Bulk data pipes without a suffix.
    """
    pipe_index: int
    endpoint_address: int
    pipe_type: str  # "BULK_IN", "BULK_OUT", "INTERRUPT_IN", "CONTROL", "OTHER"
    max_packet_size: int

    @property
    def is_in(self) -> bool:
        return bool(self.endpoint_address & 0x80)

    @property
    def is_bulk(self) -> bool:
        return "BULK" in self.pipe_type

    @property
    def is_interrupt(self) -> bool:
        return "INTERRUPT" in self.pipe_type


@dataclass(frozen=True)
class DiscoveredCamera:
    """Representation of a discovered Canon camera on the host system."""
    vid: int
    pid: int
    model_name: str
    device_path: str
    is_supported: bool
    instance_id: str = ""
    interface_guid: str = GUID_DEVINTERFACE_IMAGE


def is_invalid_handle(handle: Optional[int]) -> bool:
    """
    Checks whether a Win32 HANDLE represents an invalid or NULL descriptor.
    Handles signed -1, 32-bit unsigned 0xFFFFFFFF, 64-bit unsigned 0xFFFFFFFFFFFFFFFF,
    and 0 / None.
    """
    if handle is None or handle == 0:
        return True
    return handle in (-1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF, INVALID_HANDLE_VALUE)


class SafeDeviceHandle:
    """
    RAII context manager for a Win32 device handle.
    Guarantees handle closure in __exit__ even if exceptions or timeouts occur.
    """

    def __init__(self, handle: int):
        self._handle = handle

    @property
    def handle(self) -> int:
        return self._handle

    @property
    def is_valid(self) -> bool:
        return not is_invalid_handle(self._handle)

    def close(self) -> None:
        if self.is_valid:
            try:
                kernel32 = ctypes.windll.kernel32
                kernel32.CloseHandle(ctypes.c_void_p(self._handle))
            except Exception:
                pass
            finally:
                self._handle = INVALID_HANDLE_VALUE

    def __enter__(self) -> SafeDeviceHandle:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


class StillImageDeviceFinder:
    """
    Discovers connected Still Image (usbscan.sys) devices via Windows SetupAPI,
    verifying VID and PID against supported Canon models without opening exclusive locks.
    
    IMPORTANT:
    - Uses official Win32 SetupAPI enumeration (SetupDiGetClassDevsW, SetupDiEnumDeviceInterfaces,
      SetupDiGetDeviceInterfaceDetailW).
    - Returns the exact kernel DevicePath without manual path string fabrication.
    - Separately retrieves device instance ID / serial number via SetupDiGetDeviceInstanceIdW.
    - Guarantees HDEVINFO destruction in try...finally.
    - WPD GUID ({6AC27878-A6FA-4125-BA57-F98F7A78810E}) is strictly diagnostic and never
      used to open low-level Still Image Bulk pipes.
    """

    @staticmethod
    def extract_vid_pid_from_path(device_path: str) -> Tuple[Optional[int], Optional[int]]:
        """Extracts VID and PID hex integers from a Windows device path or Hardware ID."""
        vid_match = re.search(r"vid_([0-9a-fA-F]{4})", device_path, re.IGNORECASE)
        pid_match = re.search(r"pid_([0-9a-fA-F]{4})", device_path, re.IGNORECASE)

        vid = int(vid_match.group(1), 16) if vid_match else None
        pid = int(pid_match.group(1), 16) if pid_match else None
        return vid, pid

    @classmethod
    def enumerate_cameras(cls, setupapi_module=None) -> List[DiscoveredCamera]:
        """
        Enumerates connected Still Image devices using Windows SetupAPI.
        Accepts optional setupapi_module for unit testing mock injection.
        """
        discovered: List[DiscoveredCamera] = []

        if sys.platform != "win32" and setupapi_module is None:
            return discovered

        setupapi = setupapi_module or ctypes.windll.setupapi
        guid = guid_from_string(GUID_DEVINTERFACE_IMAGE)

        flags = DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
        hdevinfo = setupapi.SetupDiGetClassDevsW(
            ctypes.byref(guid),
            None,
            None,
            flags,
        )

        if hdevinfo == INVALID_HANDLE_VALUE or hdevinfo == 0:
            return discovered

        try:
            member_index = 0
            cb_size = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6

            while True:
                if_data = SP_DEVICE_INTERFACE_DATA()
                if_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)

                res = setupapi.SetupDiEnumDeviceInterfaces(
                    hdevinfo,
                    None,
                    ctypes.byref(guid),
                    member_index,
                    ctypes.byref(if_data),
                )
                if not res:
                    break

                member_index += 1

                # Query required size for detail structure
                required_size = ctypes.c_ulong(0)
                devinfo_data = SP_DEVINFO_DATA()
                devinfo_data.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)

                setupapi.SetupDiGetDeviceInterfaceDetailW(
                    hdevinfo,
                    ctypes.byref(if_data),
                    None,
                    0,
                    ctypes.byref(required_size),
                    ctypes.byref(devinfo_data),
                )

                if required_size.value == 0:
                    continue

                detail_buf = ctypes.create_string_buffer(required_size.value)
                struct.pack_into("I", detail_buf, 0, cb_size)

                ok = setupapi.SetupDiGetDeviceInterfaceDetailW(
                    hdevinfo,
                    ctypes.byref(if_data),
                    ctypes.cast(detail_buf, ctypes.c_void_p),
                    required_size.value,
                    ctypes.byref(required_size),
                    ctypes.byref(devinfo_data),
                )
                if not ok:
                    continue

                # DevicePath is at offset 4
                device_path = ctypes.wstring_at(ctypes.addressof(detail_buf) + 4)

                # Query Instance ID separately
                instance_id = ""
                id_buf = ctypes.create_unicode_buffer(512)
                if hasattr(setupapi, "SetupDiGetDeviceInstanceIdW"):
                    if setupapi.SetupDiGetDeviceInstanceIdW(
                        hdevinfo,
                        ctypes.byref(devinfo_data),
                        id_buf,
                        512,
                        None,
                    ):
                        instance_id = id_buf.value

                # Filter VID and PID
                vid, pid = cls.extract_vid_pid_from_path(device_path)
                if vid is None and instance_id:
                    vid, pid = cls.extract_vid_pid_from_path(instance_id)

                if vid == CANON_VID:
                    model_name = SUPPORTED_DEVICES.get(
                        (vid, pid or 0),
                        f"Canon USB Device (PID 0x{pid:04X})" if pid else "Canon USB Device"
                    )
                    is_supported = (vid, pid) in SUPPORTED_DEVICES
                    discovered.append(DiscoveredCamera(
                        vid=vid,
                        pid=pid or 0,
                        model_name=model_name,
                        device_path=device_path,  # Exact kernel path from Windows SetupAPI
                        is_supported=is_supported,
                        instance_id=instance_id,
                        interface_guid=GUID_DEVINTERFACE_IMAGE,
                    ))
        finally:
            setupapi.SetupDiDestroyDeviceInfoList(hdevinfo)

        return discovered

    @classmethod
    def find_r6_mark_ii(cls) -> Optional[DiscoveredCamera]:
        """Convenience method to locate a connected Canon EOS R6 Mark II."""
        cameras = cls.enumerate_cameras()
        for cam in cameras:
            if cam.vid == CANON_VID and cam.pid == CANON_EOS_R6_MARK_II_PID:
                return cam
        return None

    @classmethod
    def find_r10(cls) -> Optional[DiscoveredCamera]:
        """Convenience method to locate a connected Canon EOS R10."""
        cameras = cls.enumerate_cameras()
        for cam in cameras:
            if cam.vid == CANON_VID and cam.pid == CANON_EOS_R10_PID:
                return cam
        return None

    @classmethod
    def find_first_canon(cls) -> Optional[DiscoveredCamera]:
        """Locates the first connected supported Canon camera."""
        cameras = cls.enumerate_cameras()
        for cam in cameras:
            if cam.vid == CANON_VID and cam.is_supported:
                return cam
        for cam in cameras:
            if cam.vid == CANON_VID:
                return cam
        return None


class PipeConfigurationInspector:
    """
    Inspects and validates pipe configurations on a Still Image device interface.
    DOES NOT assume endpoint addresses 0x02, 0x81, 0x83 are universal:
    it inspects actual descriptors via IOCTL_GET_PIPE_CONFIGURATION and routes
    Bulk and Interrupt endpoints separately.
    """

    @staticmethod
    def classify_endpoint(pipe_index: int, address: int, attributes: int, max_packet_size: int) -> PipeInfo:
        """Classifies a USB endpoint into a PipeInfo record."""
        is_in = bool(address & 0x80)
        transfer_type = attributes & 0x03

        if transfer_type == 2:  # Bulk
            p_type = "BULK_IN" if is_in else "BULK_OUT"
        elif transfer_type == 3:  # Interrupt
            p_type = "INTERRUPT_IN" if is_in else "INTERRUPT_OUT"
        elif transfer_type == 0:
            p_type = "CONTROL"
        else:
            p_type = "OTHER"

        return PipeInfo(
            pipe_index=pipe_index,
            endpoint_address=address,
            pipe_type=p_type,
            max_packet_size=max_packet_size,
        )

    @classmethod
    def query_usbscan_pipe_config(cls, handle: int) -> List[PipeInfo]:
        """
        Queries actual pipe configuration from usbscan.sys using IOCTL_GET_PIPE_CONFIGURATION.
        Returns a list of PipeInfo structures.
        """
        if sys.platform != "win32":
            return []

        kernel32 = ctypes.windll.kernel32
        pipe_cfg = USBSCAN_PIPE_CONFIGURATION()
        bytes_returned = ctypes.c_ulong(0)

        success = kernel32.DeviceIoControl(
            ctypes.c_void_p(handle),
            IOCTL_GET_PIPE_CONFIGURATION,
            None,
            0,
            ctypes.byref(pipe_cfg),
            ctypes.sizeof(pipe_cfg),
            ctypes.byref(bytes_returned),
            None,
        )

        if not success:
            err = kernel32.GetLastError()
            raise PipeConfigurationError(f"IOCTL_GET_PIPE_CONFIGURATION failed with error {err}.")

        pipes: List[PipeInfo] = []
        for i in range(pipe_cfg.NumberOfPipes):
            p = pipe_cfg.PipeInfo[i]
            pipe_type_str = PIPE_TYPE_NAMES.get(p.PipeType, "OTHER")
            pipes.append(PipeInfo(
                pipe_index=i,
                endpoint_address=p.EndpointAddress,
                pipe_type=pipe_type_str,
                max_packet_size=p.MaximumPacketSize,
            ))
        return pipes

    @classmethod
    def validate_pipes(cls, pipes: List[PipeInfo]) -> Dict[str, PipeInfo]:
        """
        Verifies that the enumerated pipes contain the required Still Image Bulk endpoints.
        In Windows Still Image architecture (usbscan.sys):
          - WriteFile transfers data to the default Bulk OUT pipe.
          - ReadFile transfers data from the default Bulk IN pipe.
          - Interrupt IN is handled separately via IOCTL_WAIT_ON_DEVICE_EVENT.
        """
        bulk_in: Optional[PipeInfo] = None
        bulk_out: Optional[PipeInfo] = None
        interrupt_in: Optional[PipeInfo] = None

        for p in pipes:
            if p.pipe_type == "BULK_IN" and bulk_in is None:
                bulk_in = p
            elif p.pipe_type == "BULK_OUT" and bulk_out is None:
                bulk_out = p
            elif p.pipe_type == "INTERRUPT_IN" and interrupt_in is None:
                interrupt_in = p

        if bulk_in is None:
            raise PipeConfigurationError("No valid Bulk IN endpoint found in pipe configuration.")
        if bulk_out is None:
            raise PipeConfigurationError("No valid Bulk OUT endpoint found in pipe configuration.")

        config = {
            "bulk_in": bulk_in,
            "bulk_out": bulk_out,
        }
        if interrupt_in:
            config["interrupt_in"] = interrupt_in
        return config


T = TypeVar("T")


# ==============================================================================
# Microsoft usbscan.sys IOCTL Helper Functions (WDK Specification Reference)
# ==============================================================================

def reset_usbscan_pipe(handle: int, pipe_type: USBSCAN_PIPE_TYPE = USBSCAN_PIPE_TYPE.ALL_PIPE) -> None:
    """
    Resets a Still Image pipe using IOCTL_RESET_PIPE (0x8000201C).
    Per Microsoft usbscan.h, input buffer is a 4-byte PIPE_TYPE enum:
      EVENT_PIPE (0), READ_DATA_PIPE (1), WRITE_DATA_PIPE (2), ALL_PIPE (3).
    It does NOT take an integer array index into USBSCAN_PIPE_CONFIGURATION.
    """
    if sys.platform != "win32":
        return
    kernel32 = ctypes.windll.kernel32
    in_buf = ctypes.c_uint(int(pipe_type))
    bytes_returned = ctypes.c_ulong(0)
    success = kernel32.DeviceIoControl(
        ctypes.c_void_p(handle),
        IOCTL_RESET_PIPE,
        ctypes.byref(in_buf),
        ctypes.sizeof(in_buf),
        None,
        0,
        ctypes.byref(bytes_returned),
        None,
    )
    if not success:
        err = kernel32.GetLastError()
        raise TransportError(f"IOCTL_RESET_PIPE failed with Win32 Error {err}.")


def cancel_usbscan_io(handle: int, pipe_type: USBSCAN_PIPE_TYPE = USBSCAN_PIPE_TYPE.ALL_PIPE) -> None:
    """
    Cancels pending I/O on a Still Image pipe using IOCTL_CANCEL_IO (0x80002004).
    Per Microsoft usbscan.h, input buffer is a 4-byte PIPE_TYPE enum:
      EVENT_PIPE (0), READ_DATA_PIPE (1), WRITE_DATA_PIPE (2), ALL_PIPE (3).
    """
    if sys.platform != "win32":
        return
    kernel32 = ctypes.windll.kernel32
    in_buf = ctypes.c_uint(int(pipe_type))
    bytes_returned = ctypes.c_ulong(0)
    success = kernel32.DeviceIoControl(
        ctypes.c_void_p(handle),
        IOCTL_CANCEL_IO,
        ctypes.byref(in_buf),
        ctypes.sizeof(in_buf),
        None,
        0,
        ctypes.byref(bytes_returned),
        None,
    )
    if not success:
        err = kernel32.GetLastError()
        raise TransportError(f"IOCTL_CANCEL_IO failed with Win32 Error {err}.")


def set_usbscan_timeouts(
    handle: int,
    timeout_read_ms: int = 5000,
    timeout_write_ms: int = 5000,
    timeout_event_ms: int = 5000,
) -> None:
    """
    Configures I/O timeouts using IOCTL_SET_TIMEOUT (0x8000202C).
    Per Microsoft usbscan.h, input buffer is a USBSCAN_TIMEOUT struct (12 bytes: 3 x ULONG ms).
    """
    if sys.platform != "win32":
        return
    kernel32 = ctypes.windll.kernel32
    t = USBSCAN_TIMEOUT(
        TimeoutRead=timeout_read_ms,
        TimeoutWrite=timeout_write_ms,
        TimeoutEvent=timeout_event_ms,
    )
    bytes_returned = ctypes.c_ulong(0)
    success = kernel32.DeviceIoControl(
        ctypes.c_void_p(handle),
        IOCTL_SET_TIMEOUT,
        ctypes.byref(t),
        ctypes.sizeof(t),
        None,
        0,
        ctypes.byref(bytes_returned),
        None,
    )
    if not success:
        err = kernel32.GetLastError()
        raise TransportError(f"IOCTL_SET_TIMEOUT failed with Win32 Error {err}.")


def wait_usbscan_device_event(handle: int, buffer_size: int = 64) -> bytes:
    """
    Waits for an asynchronous interrupt event packet using IOCTL_WAIT_ON_DEVICE_EVENT (0x80002008).
    Per Microsoft usbscan.h:
      - lpInBuffer = NULL, nInBufferSize = 0.
      - lpOutBuffer points to a caller-allocated buffer of at least the interrupt pipe's MaximumPacketSize.
      - nOutBufferSize = buffer_size.
    """
    if sys.platform != "win32":
        return b""
    kernel32 = ctypes.windll.kernel32
    out_buf = ctypes.create_string_buffer(buffer_size)
    bytes_returned = ctypes.c_ulong(0)
    success = kernel32.DeviceIoControl(
        ctypes.c_void_p(handle),
        IOCTL_WAIT_ON_DEVICE_EVENT,
        None,
        0,
        ctypes.byref(out_buf),
        buffer_size,
        ctypes.byref(bytes_returned),
        None,
    )
    if not success:
        err = kernel32.GetLastError()
        raise TransportError(f"IOCTL_WAIT_ON_DEVICE_EVENT failed with Win32 Error {err}.")
    return out_buf.raw[:bytes_returned.value]


def format_pipe_specific_device_path(base_device_path: str, pipe_index: Optional[int] = None) -> str:
    """
    [UNVERIFIED / EXPERIMENTAL HELPER - NOT USED IN PRODUCTION EXECUTION PATH]

    Formats a device path with a pipe suffix for CreateFile.
    
    IMPORTANT TECHNICAL NOTES:
    1. Microsoft STI documentation describes appending '\\<index>' (e.g. '\\0', '\\1')
       specifically to port names returned by IStiDeviceControl::GetMyDevicePortName
       (or legacy port names like '\\\\.\\Usbscan0\\0').
    2. Appending '\\<index>' to a SetupAPI Device Interface Path
       ('\\\\?\\usb#vid_04a9&pid_330b#...#{6bdd1fc6-810f-11d0-bec7-08002be2092f}')
       is NOT officially documented by Microsoft for arbitrary device interfaces,
       is completely unverified on physical hardware, and may be rejected by the OS.
    3. For Canon EOS R6 Mark II:
       The device configuration descriptor exposes exactly one interface (Class 6 Still Image)
       with a single triplet of endpoints:
         - Bulk IN: Endpoint 0x81 (Pipe 1)
         - Bulk OUT: Endpoint 0x02 (Pipe 0)
         - Interrupt IN: Endpoint 0x83 (Pipe 2)
       When opening the base device interface path directly with CreateFileW (without '\\index'):
         - usbscan.sys automatically binds ReadFile to the default Bulk IN endpoint.
         - usbscan.sys automatically binds WriteFile to the default Bulk OUT endpoint.
         - Interrupt events are retrieved via IOCTL_WAIT_ON_DEVICE_EVENT on the same handle.
       Therefore, opening the base device path directly is fully sufficient and avoids any
       path parsing hazards. This function is retained strictly as an experimental helper.
    """
    if pipe_index is None:
        return base_device_path
    return f"{base_device_path}\\{pipe_index}"


class CameraAccessManager:
    """
    Coordinates exclusive interface ownership between Canon EDSDK and Direct PTP.
    
    MANDATORY CONTRACT:
    - Callers MUST provide an 'edsdk_status_callback' to reliably verify EDSDK status.
      If this callback is missing or fails, device acquisition is safely denied.
    - If EDSDK is reported active, 'edsdk_close_callback' is MANDATORY to release
      exclusive control before direct USB acquisition. If missing or fails, acquisition is denied.
    - Never assumes a fixed 100 ms release guarantee; implements non-blocking handle polling
      with backoff and timeout.
    - Guarantees fail-safe EDSDK restoration in try...finally.
    - In Phase B, strictly inspects device readiness without sending any PTP commands.
    """

    def __init__(
        self,
        timeout_sec: float = 4.0,
        poll_interval_sec: float = 0.05,
        edsdk_close_callback: Optional[Callable[[], None]] = None,
        edsdk_restore_callback: Optional[Callable[[], None]] = None,
        edsdk_status_callback: Optional[Callable[[], bool]] = None,
    ):
        self.timeout_sec = timeout_sec
        self.poll_interval_sec = poll_interval_sec
        self._edsdk_close = edsdk_close_callback
        self._edsdk_restore = edsdk_restore_callback
        self._edsdk_status = edsdk_status_callback
        self._lock = threading.Lock()

    def is_edsdk_active(self) -> bool:
        """
        Queries EDSDK active status via the registered callback.
        Raises DeviceAccessDeniedError if callback is missing or fails.
        """
        if self._edsdk_status is None:
            raise DeviceAccessDeniedError(
                "Mandatory safety contract violated: 'edsdk_status_callback' is not provided. "
                "Cannot determine whether Canon EDSDK holds exclusive USB locks. "
                "Device opening safely denied to prevent interface contention."
            )
        try:
            return bool(self._edsdk_status())
        except Exception as exc:
            raise DeviceAccessDeniedError(
                f"EDSDK status check callback failed: {exc}. "
                f"Device opening safely denied because EDSDK state is indeterminate."
            ) from exc

    def acquire_device_handle(
        self,
        device_path: str,
        open_fn: Optional[Callable[[str], Tuple[int, int]]] = None,
    ) -> SafeDeviceHandle:
        """
        Attempts to acquire an exclusive handle to the camera, polling until the
        interface is freed by EDSDK or the OS Still Image driver.
        """
        open_handle = open_fn or self._default_open_handle
        start_time = time.monotonic()
        last_error = 0

        while (time.monotonic() - start_time) < self.timeout_sec:
            raw_handle, err = open_handle(device_path)
            if raw_handle != INVALID_HANDLE_VALUE:
                return SafeDeviceHandle(raw_handle)

            last_error = err
            if err in (ERROR_ACCESS_DENIED, ERROR_SHARING_VIOLATION):
                time.sleep(self.poll_interval_sec)
            else:
                break

        if last_error in (ERROR_ACCESS_DENIED, ERROR_SHARING_VIOLATION):
            raise DeviceAccessDeniedError(
                f"Timed out after {self.timeout_sec:.1f} s waiting for device interface. "
                f"Camera is held exclusively by another process (Win32 Error {last_error})."
            )
        raise DeviceNotFoundError(
            f"Failed to open device at '{device_path}' (Win32 Error {last_error})."
        )

    def execute_with_exclusive_access(
        self,
        device_path: str,
        callback: Callable[[SafeDeviceHandle], T],
        open_fn: Optional[Callable[[str], Tuple[int, int]]] = None,
    ) -> T:
        """
        Executes a diagnostic routine with coordinated exclusive device ownership.
        Ensures EDSDK is gracefully shut down beforehand and restored afterward.
        """
        with self._lock:
            # Step 1: Verify EDSDK state according to mandatory contract
            edsdk_was_active = self.is_edsdk_active()

            # Step 2: If EDSDK is active, close callback is strictly required
            if edsdk_was_active:
                if self._edsdk_close is None:
                    raise DeviceAccessDeniedError(
                        "Canon EDSDK is active and holding camera resources, "
                        "but no 'edsdk_close_callback' was provided to shut down EDSDK. "
                        "Device acquisition cannot proceed safely."
                    )
                try:
                    self._edsdk_close()
                except Exception as exc:
                    raise DeviceAccessDeniedError(
                        f"Failed to shut down active EDSDK session: {exc}. Device acquisition aborted."
                    ) from exc

            safe_handle = None
            try:
                safe_handle = self.acquire_device_handle(device_path, open_fn=open_fn)
                with safe_handle:
                    return callback(safe_handle)
            finally:
                if edsdk_was_active and self._edsdk_restore:
                    try:
                        self._edsdk_restore()
                    except Exception:
                        pass

    @staticmethod
    def _default_open_handle(path: str) -> Tuple[int, int]:
        """
        Opens a raw device handle via Win32 CreateFileW in synchronous mode.
        NOTE: FILE_FLAG_OVERLAPPED is intentionally omitted because current transport
        uses synchronous ReadFile/WriteFile semantics.
        """
        if sys.platform != "win32":
            return INVALID_HANDLE_VALUE, ERROR_DEVICE_NOT_CONNECTED

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateFileW(
            ctypes.c_wchar_p(path),
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,  # Shared access preventing contention with EDSDK/WPD
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,  # Synchronous Win32 I/O
            None,
        )
        if handle == INVALID_HANDLE_VALUE:
            err = kernel32.GetLastError()
            return INVALID_HANDLE_VALUE, err
        return handle, 0


def init_win32_api(setupapi=None, kernel32=None) -> None:
    """
    Configures explicit argtypes and restype on Windows x64 / x86 for all Win32 APIs
    used across the transport module. Eliminates 64-bit handle truncation, structure pointer
    mismatch, and signedness errors.
    
    Verified APIs:
      1. SetupDiGetClassDevsW
      2. SetupDiEnumDeviceInterfaces
      3. SetupDiGetDeviceInterfaceDetailW
      4. SetupDiDestroyDeviceInfoList
      5. CreateFileW
      6. DeviceIoControl
      7. ReadFile
      8. WriteFile
      9. CloseHandle
    """
    if sys.platform != "win32" and setupapi is None and kernel32 is None:
        return

    s_api = setupapi or (ctypes.windll.setupapi if hasattr(ctypes, "windll") else None)
    k_api = kernel32 or (ctypes.windll.kernel32 if hasattr(ctypes, "windll") else None)

    if s_api is not None:
        if hasattr(s_api, "SetupDiGetClassDevsW"):
            s_api.SetupDiGetClassDevsW.argtypes = [
                ctypes.POINTER(GUID),
                ctypes.c_wchar_p,
                wintypes.HWND,
                wintypes.DWORD,
            ]
            s_api.SetupDiGetClassDevsW.restype = wintypes.HANDLE

        if hasattr(s_api, "SetupDiEnumDeviceInterfaces"):
            s_api.SetupDiEnumDeviceInterfaces.argtypes = [
                wintypes.HANDLE,
                ctypes.c_void_p,
                ctypes.POINTER(GUID),
                wintypes.DWORD,
                ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
            ]
            s_api.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL

        if hasattr(s_api, "SetupDiGetDeviceInterfaceDetailW"):
            s_api.SetupDiGetDeviceInterfaceDetailW.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
                ctypes.POINTER(SP_DEVINFO_DATA),
            ]
            s_api.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL

        if hasattr(s_api, "SetupDiDestroyDeviceInfoList"):
            s_api.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
            s_api.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

        if hasattr(s_api, "SetupDiGetDeviceInstanceIdW"):
            s_api.SetupDiGetDeviceInstanceIdW.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(SP_DEVINFO_DATA),
                ctypes.c_wchar_p,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
            ]
            s_api.SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL

    if k_api is not None:
        if hasattr(k_api, "CreateFileW"):
            k_api.CreateFileW.argtypes = [
                ctypes.c_wchar_p,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.c_void_p,
            ]
            k_api.CreateFileW.restype = wintypes.HANDLE

        if hasattr(k_api, "CloseHandle"):
            k_api.CloseHandle.argtypes = [wintypes.HANDLE]
            k_api.CloseHandle.restype = wintypes.BOOL

        if hasattr(k_api, "DeviceIoControl"):
            k_api.DeviceIoControl.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
                ctypes.c_void_p,
            ]
            k_api.DeviceIoControl.restype = wintypes.BOOL

        if hasattr(k_api, "ReadFile"):
            k_api.ReadFile.argtypes = [
                wintypes.HANDLE,
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
                ctypes.c_void_p,
            ]
            k_api.ReadFile.restype = wintypes.BOOL

        if hasattr(k_api, "WriteFile"):
            k_api.WriteFile.argtypes = [
                wintypes.HANDLE,
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
                ctypes.c_void_p,
            ]
            k_api.WriteFile.restype = wintypes.BOOL


# Initialize Win32 API signatures immediately on Windows platforms
if sys.platform == "win32":
    try:
        init_win32_api()
    except Exception:
        pass


class ProtectedUsbPtpTransport:
    """
    Unified Secure USB PTP Transport Channel.
    Enforces the single non-bypassable transmission pipeline:
      PTP Container -> Serialization -> Protocol Guard -> USB WriteFile

    ARCHITECTURE & SAFETY CONTRACT:
    - Zero bypass guarantee: No raw bytes or PTP containers can reach USB WriteFile
      without passing Protocol Guard's state machine, OpCode filtering, and payload checks.
    - Physical I/O gating: In Phase B, physical wire transmission is UNCONDITIONALLY BLOCKED.
      Zero bytes are transmitted to USB hardware. No toggle, config, or setting can authorize
      physical transmission in Phase B.
    - If Protocol Guard is not supplied or None is attempted, initialization is rejected.
    - If handle is invalid or closed, initialization is rejected.
    """

    def __init__(self, handle: SafeDeviceHandle, guard: ProtocolGuard):
        if guard is None or not isinstance(guard, ProtocolGuard):
            raise SecurityViolationError("Mandatory Protocol Guard instance is required. Bypass strictly prohibited.")
        if handle is None or not handle.is_valid:
            raise TransportError("Cannot initialize ProtectedUsbPtpTransport with an invalid or closed handle.")

        self._handle = handle
        self._guard = guard
        self._live_session_authorized = False

    @property
    def guard(self) -> ProtocolGuard:
        return self._guard

    @property
    def handle(self) -> SafeDeviceHandle:
        return self._handle

    @property
    def is_live_session_authorized(self) -> bool:
        return self._live_session_authorized

    def authorize_live_session(self) -> None:
        """
        Explicitly authorizes live hardware USB I/O for the active session.
        Mandatory gate preventing accidental physical dispatch during Phase B tests or passive inspection.
        """
        self._live_session_authorized = True

    def revoke_live_session(self) -> None:
        """
        Revokes hardware USB I/O authorization immediately.
        Guarantees that no physical transactions can proceed once session is closed or faulted.
        """
        self._live_session_authorized = False

    def write_ptp_container(self, container: PtpContainer) -> int:
        """
        Submits an outbound PTP container to the transport channel.
        MANDATORY FLOW: PTP Container -> Serialization -> Protocol Guard -> USB WriteFile.
        Zero bypass guarantee: Protocol Guard inspects wire bytes before transmission.
        """
        if not isinstance(container, PtpContainer):
            raise SecurityViolationError(f"Expected PtpContainer instance, got {type(container).__name__}")

        # Step 1: Serialization
        raw_bytes = container.serialize()

        # Step 2: Protocol Guard validation directly on the wire bytes immediately prior to send
        self._guard.validate_outgoing_container_bytes(raw_bytes)

        # Step 3: Low-level wire transmission sink
        return self._write_raw_wire_bytes(raw_bytes)

    def write_ptp_bytes(self, raw_bytes: bytes) -> int:
        """
        Submits pre-serialized PTP container bytes to the transport channel.
        MANDATORY FLOW: Serialization (pre-done) -> Protocol Guard -> USB WriteFile.
        Zero bypass guarantee: Protocol Guard inspects wire bytes before transmission.
        """
        if not isinstance(raw_bytes, (bytes, bytearray)):
            raise SecurityViolationError(f"Expected bytes or bytearray, got {type(raw_bytes).__name__}")

        # Step 1: Protocol Guard validation directly on wire bytes
        self._guard.validate_outgoing_container_bytes(bytes(raw_bytes))

        # Step 2: Low-level wire transmission sink
        return self._write_raw_wire_bytes(bytes(raw_bytes))

    def read_ptp_container(self, max_buffer_size: int = 4096) -> PtpContainer:
        """
        Reads an inbound PTP container from USB Bulk IN endpoint.
        MANDATORY FLOW: USB ReadFile -> Protocol Guard Validation -> Return PtpContainer.
        Zero bypass guarantee: Wire bytes are inspected and validated immediately upon receipt.
        """
        raw_bytes = self._read_raw_wire_bytes(max_buffer_size=max_buffer_size)
        return self._guard.validate_inbound_container_bytes(raw_bytes)

    def read_ptp_bytes(self, max_buffer_size: int = 4096) -> bytes:
        """
        Reads raw wire bytes from USB Bulk IN endpoint without container parsing.
        """
        return self._read_raw_wire_bytes(max_buffer_size=max_buffer_size)

    def _write_raw_wire_bytes(self, data: bytes) -> int:
        """
        Low-level wire transmission sink.
        UNCONDITIONALLY BLOCKED until authorize_live_session() is called.
        """
        if not self._live_session_authorized:
            raise TransportAuthorizationError(
                "Физический USB-канал заблокирован: требуется явная авторизация живой сессии чтения. "
                "Phase C not authorized: physical PTP dispatch to Canon EOS R6 Mark II is strictly disabled. "
                "Zero bytes transmitted to USB."
            )
        if sys.platform != "win32":
            raise TransportError("Physical USB I/O requires a Windows Win32 environment.")

        kernel32 = ctypes.windll.kernel32
        bytes_written = wintypes.DWORD(0)
        buf = ctypes.create_string_buffer(data, len(data))
        ok = kernel32.WriteFile(
            wintypes.HANDLE(self._handle.handle),
            buf,
            wintypes.DWORD(len(data)),
            ctypes.byref(bytes_written),
            None,
        )
        if not ok:
            err = kernel32.GetLastError()
            if err == 50:
                raise TransportError("Win32 WriteFile failed (Error 50: ERROR_NOT_SUPPORTED). Корневой дескриптор Still Image не поддерживает прямую потоковую запись Bulk OUT под драйвером WPD. Требуется WPD MTP Extension Pass-Through.")
            raise TransportError(f"Win32 WriteFile failed (Error {err}).")
        if bytes_written.value != len(data):
            raise TransportError(
                f"Incomplete USB write: requested {len(data)} bytes, wrote {bytes_written.value} bytes."
            )
        return bytes_written.value

    def _read_raw_wire_bytes(self, max_buffer_size: int = 4096) -> bytes:
        """
        Low-level wire reception sink.
        UNCONDITIONALLY BLOCKED until authorize_live_session() is called.
        """
        if not self._live_session_authorized:
            raise TransportAuthorizationError(
                "Физический USB-канал заблокирован: требуется явная авторизация живой сессии чтения. "
                "Phase C not authorized: physical PTP reception from Canon EOS R6 Mark II is strictly disabled. "
                "Zero bytes received from USB."
            )
        if sys.platform != "win32":
            raise TransportError("Physical USB I/O requires a Windows Win32 environment.")

        kernel32 = ctypes.windll.kernel32
        buf = ctypes.create_string_buffer(max_buffer_size)
        bytes_read = wintypes.DWORD(0)
        ok = kernel32.ReadFile(
            wintypes.HANDLE(self._handle.handle),
            buf,
            wintypes.DWORD(max_buffer_size),
            ctypes.byref(bytes_read),
            None,
        )
        if not ok:
            err = kernel32.GetLastError()
            raise TransportError(f"Win32 ReadFile failed (Error {err}).")
        if bytes_read.value == 0:
            raise TransportError("USB ReadFile returned 0 bytes (device timeout or closed pipe).")

        return buf.raw[:bytes_read.value]
