"""
Protocol, USB Still Image (usbscan.sys), and hardware constants for OpenEOS PTP Service.
Based on OPENEOS_ONLINE_READ_SPEC_V1.2, Microsoft usbscan.h, sti.h, and ISO 15740.
"""

# PTP Container Types (ISO 15740)
PTP_CONTAINER_UNDEFINED = 0x0000
PTP_CONTAINER_COMMAND = 0x0001
PTP_CONTAINER_DATA = 0x0002
PTP_CONTAINER_RESPONSE = 0x0003
PTP_CONTAINER_EVENT = 0x0004

# PTP Standard OpCodes (ISO 15740)
PTP_OC_GetDeviceInfo = 0x1001
PTP_OC_OpenSession = 0x1002
PTP_OC_CloseSession = 0x1003

# Canon Vendor-Specific OpCodes (Forensically Verified in р62.pcapng)
PTP_OC_Canon_FA_Command = 0x9052  # Data OUT: FA Subsystem Command (e.g. FA_GetProperty)
PTP_OC_Canon_FA_Fetch = 0x9053    # Data IN: Fetch Result Buffer

# Prohibited / Dangerous Vendor OpCodes (Strictly Blocked by Protocol Guard)
PTP_OC_Canon_SaveTransparentMemory = 0x905A       # Code upload / binary execution (FAXEXE)
PTP_OC_Canon_QuickLoadTransparentMemory = 0x905B  # Execution trigger
PTP_OC_Canon_Auth = 0x905C                       # Service authentication handshake
PTP_OC_Canon_DirectPTP = 0x9028                  # Generic direct vendor call
PTP_OC_Canon_EventProc = 0x9054                  # Potential string exec vector

# Standard PTP Response Codes (ISO 15740)
PTP_RC_OK = 0x2001
PTP_RC_GeneralError = 0x2002
PTP_RC_SessionNotOpen = 0x2003
PTP_RC_InvalidTransactionID = 0x2004
PTP_RC_OperationNotSupported = 0x2005
PTP_RC_ParameterNotSupported = 0x2006
PTP_RC_IncompleteTransfer = 0x2007
PTP_RC_InvalidStorageID = 0x2008
PTP_RC_InvalidObjectHandle = 0x2009
PTP_RC_DevicePropNotSupported = 0x200A
PTP_RC_InvalidObjectFormatCode = 0x200B
PTP_RC_StoreFull = 0x200C
PTP_RC_ObjectWriteProtected = 0x200D
PTP_RC_StoreReadOnly = 0x200E
PTP_RC_AccessDenied = 0x200F
PTP_RC_NoThumbnailObject = 0x2010
PTP_RC_SelfTestFailed = 0x2011
PTP_RC_PartialDeletion = 0x2012
PTP_RC_StoreNotAvailable = 0x2013
PTP_RC_SpecificationByFormatUnsupported = 0x2014
PTP_RC_NoValidObjectInfo = 0x2015
PTP_RC_InvalidCodeFormat = 0x2016
PTP_RC_UnknownVendorCode = 0x2017
PTP_RC_CaptureAlreadyTerminated = 0x2018
PTP_RC_DeviceBusy = 0x2019
PTP_RC_InvalidParentObject = 0x201A
PTP_RC_InvalidDevicePropFormat = 0x201B
PTP_RC_InvalidDevicePropValue = 0x201C
PTP_RC_InvalidParameter = 0x201D
PTP_RC_SessionAlreadyOpen = 0x201E
PTP_RC_TransactionCanceled = 0x201F
PTP_RC_DestinationUnsupported = 0x2020

# Canon Verified Diagnostic Property Identifiers
PROP_SHUTTER_COUNTER = 0x12000001    # Shutter Counter (8B: uint32 counter + 4B opaque tail) - Neutral semantics
PROP_MECHANICAL_SHUTTER = PROP_SHUTTER_COUNTER  # DEPRECATED: Historical alias for backward compatibility (not proven mechanical-only)
PROP_RELEASE_TOTAL = 0x12000003      # Release Counter Total (4B: uint32 counter)
PROP_POWER_AND_UPTIME = 0x12000005   # Power On Count (uint32) & Total Operating Time in seconds (uint32)

# Mon Protocol Constants (Canon Monitor Subsystem via 0x9052 / 0x9053)
MON_OPEN_NAME = b"MonOpen\x00"                  # 8 bytes ASCII + NUL
MON_READ_NAME = b"MonReadAndGetData\x00"        # 18 bytes ASCII + NUL
MON_CLOSE_NAME = b"MonClose\x00"                # 9 bytes ASCII + NUL

# Canon EOS R10 Candidate Memory Addresses to Probe
R10_CANDIDATE_ADDR_1001 = 0x1001
R10_CANDIDATE_ADDR_100B = 0x100B
R10_CANDIDATE_ADDR_1015 = 0x1015

R10_CANDIDATE_ADDRESSES = [
    R10_CANDIDATE_ADDR_1001,
    R10_CANDIDATE_ADDR_100B,
    R10_CANDIDATE_ADDR_1015,
]

# Mon Protocol Safety Whitelist (Strictly Allowed Operations)
ALLOWED_MON_COMMANDS = {
    b"MonOpen",
    b"MonReadAndGetData",
    b"MonClose",
}

# Mon Protocol Prohibited Commands (Strictly Blocked by Protocol Guard)
FORBIDDEN_MON_COMMANDS = {
    b"MonWrite",
    b"MonCall",
    b"FA_SetProperty",
    b"FA_SetCalendar",
    b"EEPROM_Write",
    b"FactoryReset",
}

ALLOWED_PROPERTY_IDS = {
    PROP_SHUTTER_COUNTER,
    PROP_RELEASE_TOTAL,
    PROP_POWER_AND_UPTIME,
}

# FA Subsystem Protocol Constants (DIGIC X Architecture)
FA_COMMAND_NAME = b"FA_GetProperty\x00"  # 15 bytes ASCII + NUL
CANON_FA_ARGC_DEFAULT = 1                # uint32 argc = 1
CANON_FA_ARG_TAG_DWORD = 2               # uint32 tag = 2 (Numeric DWORD Key)
FA_GET_PROPERTY_PAYLOAD_LEN = 43         # 15B name + 4B argc + 20B arg entry + 4B struct align
FA_GET_PROPERTY_CONTAINER_LEN = 55       # 12B PTP Header + 43B Payload
FA_COMMAND_CONTAINER_LEN = 20            # 12B PTP Header + 2 params (8B) [0, 1]

# USB Identifiers
CANON_VID = 0x04A9
CANON_EOS_R6_MARK_II_PID = 0x330B
CANON_EOS_R10_PID = 0x32F8

SUPPORTED_DEVICES = {
    (CANON_VID, CANON_EOS_R6_MARK_II_PID): "Canon EOS R6 Mark II",
    (CANON_VID, CANON_EOS_R10_PID): "Canon EOS R10",
    (CANON_VID, 0x32D7): "Canon EOS R5",
    (CANON_VID, 0x3327): "Canon EOS R5 Mark II",
    (CANON_VID, 0x32D8): "Canon EOS R6",
    (CANON_VID, 0x32E4): "Canon EOS R3",
    (CANON_VID, 0x32F7): "Canon EOS R7",
    (CANON_VID, 0x3312): "Canon EOS R8",
    (CANON_VID, 0x3313): "Canon EOS R50",
    (CANON_VID, 0x3314): "Canon EOS R100",
}

# Windows Device Interface GUIDs (Microsoft SDK Reference)
# 1. Official Microsoft Still Image / usbscan.sys Device Interface Class GUID (sti.h, devguid.h)
GUID_DEVINTERFACE_IMAGE = "{6BDD1FC6-810F-11D0-BEC7-08002BE2092F}"

# 2. Microsoft Windows Portable Devices (WPD / MTP) Interface Class GUID (wpd_guid.h)
GUID_DEVINTERFACE_WPD = "{6AC27878-A6FA-4125-BA57-F98F7A78810E}"

# ==============================================================================
# Microsoft Windows DDK usbscan.h IOCTL Definitions & CTL_CODE Macro
# ==============================================================================
# CTL_CODE formula (winioctl.h / devioctl.h):
#   ((DeviceType) << 16) | ((Access) << 14) | ((Function) << 2) | (Method)
#
# usbscan.h base definitions:
#   FILE_DEVICE_USB_SCAN = 0x8000
#   IOCTL_INDEX          = 0x0800
#   METHOD_BUFFERED      = 0
#   FILE_ANY_ACCESS      = 0

FILE_DEVICE_USB_SCAN = 0x8000
IOCTL_INDEX = 0x0800
METHOD_BUFFERED = 0
FILE_ANY_ACCESS = 0


def ctl_code(device_type: int, function: int, method: int = METHOD_BUFFERED, access: int = FILE_ANY_ACCESS) -> int:
    """Computes Win32 / Windows Driver CTL_CODE integer according to winioctl.h specification."""
    return ((device_type & 0xFFFF) << 16) | ((access & 0x03) << 14) | ((function & 0x0FFF) << 2) | (method & 0x03)


# All 12 official Microsoft usbscan.h IOCTLs (IOCTL_INDEX + 0 .. IOCTL_INDEX + 11)
# 0. IOCTL_GET_VERSION = CTL_CODE(0x8000, 0x0800, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_GET_VERSION = 0x80002000

# 1. IOCTL_CANCEL_IO = CTL_CODE(0x8000, 0x0801, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_CANCEL_IO = 0x80002004

# 2. IOCTL_WAIT_ON_DEVICE_EVENT = CTL_CODE(0x8000, 0x0802, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_WAIT_ON_DEVICE_EVENT = 0x80002008

# 3. IOCTL_READ_REGISTERS = CTL_CODE(0x8000, 0x0803, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_READ_REGISTERS = 0x8000200C

# 4. IOCTL_WRITE_REGISTERS = CTL_CODE(0x8000, 0x0804, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_WRITE_REGISTERS = 0x80002010

# 5. IOCTL_GET_CHANNEL_ALIGN_RQST = CTL_CODE(0x8000, 0x0805, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_GET_CHANNEL_ALIGN_RQST = 0x80002014

# 6. IOCTL_GET_DEVICE_DESCRIPTOR = CTL_CODE(0x8000, 0x0806, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_GET_DEVICE_DESCRIPTOR = 0x80002018

# 7. IOCTL_RESET_PIPE = CTL_CODE(0x8000, 0x0807, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_RESET_PIPE = 0x8000201C

# 8. IOCTL_GET_USB_DESCRIPTOR = CTL_CODE(0x8000, 0x0808, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_GET_USB_DESCRIPTOR = 0x80002020

# 9. IOCTL_SEND_USB_REQUEST = CTL_CODE(0x8000, 0x0809, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_SEND_USB_REQUEST = 0x80002024

# 10. IOCTL_GET_PIPE_CONFIGURATION = CTL_CODE(0x8000, 0x080A, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_GET_PIPE_CONFIGURATION = 0x80002028

# 11. IOCTL_SET_TIMEOUT = CTL_CODE(0x8000, 0x080B, METHOD_BUFFERED, FILE_ANY_ACCESS)
IOCTL_SET_TIMEOUT = 0x8000202C

import enum

class USBSCAN_PIPE_TYPE(enum.IntEnum):
    """
    Microsoft usbscan.h PIPE_TYPE enum used by IOCTL_RESET_PIPE and IOCTL_CANCEL_IO.
    Specifies the functional pipe category to reset or cancel, NOT an array index.
    """
    EVENT_PIPE = 0       # Interrupt IN pipe
    READ_DATA_PIPE = 1   # Bulk IN pipe
    WRITE_DATA_PIPE = 2  # Bulk OUT pipe
    ALL_PIPE = 3         # All pipes simultaneously


class USBSCAN_RAW_PIPE_TYPE(enum.IntEnum):
    """
    Microsoft usbscan.h RAW_PIPE_TYPE enum used in USBSCAN_PIPE_INFORMATION.PipeType.
    Describes the underlying USB endpoint transfer type and direction.
    """
    PIPE_TYPE_CONTROL = 0
    PIPE_TYPE_ISOCHRONOUS = 1
    PIPE_TYPE_BULK_IN = 2
    PIPE_TYPE_BULK_OUT = 3
    PIPE_TYPE_INTERRUPT = 4


# Windows SetupAPI Constants
DIGCF_DEFAULT = 0x00000001
DIGCF_PRESENT = 0x00000002
DIGCF_ALLCLASSES = 0x00000004
DIGCF_PROFILE = 0x00000008
DIGCF_DEVICEINTERFACE = 0x00000010

SPDRP_DEVICEDESC = 0x00000000
SPDRP_HARDWAREID = 0x00000001
SPDRP_FRIENDLYNAME = 0x0000000C

# Expected Fetch 0x9053 Parameters
FETCH_PARAMS_MAP = {
    PROP_SHUTTER_COUNTER: [],           # TxID 26: 0 parameters
    PROP_RELEASE_TOTAL: [],             # TxID 32: 0 parameters
    PROP_POWER_AND_UPTIME: [0, 0, 1],   # TxID 63: 3 parameters [0, 0, 1]
}

# Expected Inbound Data Lengths
EXPECTED_DATA_LENGTHS = {
    PROP_SHUTTER_COUNTER: 8,            # 8 bytes payload (4B shutter + 4B opaque_tail)
    PROP_RELEASE_TOTAL: 4,              # 4 bytes payload (4B release total)
    PROP_POWER_AND_UPTIME: 8,           # 8 bytes payload (4B power_on + 4B uptime_sec)
}
