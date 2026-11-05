import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import struct
import sys
import winreg

log_lines = []
def log(msg):
    log_lines.append(msg)

log("=== DIAGNOSTIC REPORT ===")
log(f"Python executable: {sys.executable}")
log(f"Python bitness: {struct.calcsize('P') * 8}-bit")

# 1. Parse PE imports of TornadoEOS.exe
tornado_exe = Path(r"c:\Users\and!m\Downloads\Telegram Desktop\TornadoEOS\TornadoEOS.exe")
if tornado_exe.exists():
    log(f"\nTornadoEOS.exe found ({tornado_exe.stat().st_size:,} bytes)")
    try:
        raw = tornado_exe.read_bytes()
        # Search for ASCII DLL names
        import re
        dlls = sorted(set(m.group(0).decode('ascii', errors='ignore') for m in re.finditer(rb'[a-zA-Z0-9_\-\.]+\.(?:dll|DLL)', raw)))
        log(f"DLL references in TornadoEOS.exe: {', '.join(dlls[:40])}")
        
        # Search for interesting APIs
        apis = []
        for term in [b"PortableDevice", b"WPD", b"Wpd", b"SetupDi", b"CreateFile", b"DeviceIoControl", b"Sti", b"Wia", b"OpenSession", b"0x9052", b"0x9053"]:
            matches = [m.start() for m in re.finditer(re.escape(term), raw)]
            if matches:
                apis.append(f"{term.decode('ascii', errors='ignore')}: {len(matches)} occurrences")
        log(f"Keywords in TornadoEOS.exe: {', '.join(apis)}")
    except Exception as ex:
        log(f"Error parsing Tornado: {ex}")
else:
    log("TornadoEOS.exe not found")

# 2. Check Registry for PortableDevice CLSIDs
log("\n--- Registry CLSIDs ---")
clsids_to_check = {
    "PortableDeviceManager": "{0af10c2a-ff05-4329-af0e-95d0e3cfa21f}",
    "PortableDevice": "{728a2104-3a47-460c-9856-384d9d10cee4}",
    "PortableDeviceFTM": "{f7c00a74-3637-45dd-a167-96457c9bad42}",
    "PortableDeviceValues": "{0c15d803-d329-476b-9e58-555202630ea5}",
    "PortableDeviceKeyCollection": "{de21072c-4205-41ec-b943-21d733ebaa51}",
}

for name, clsid in clsids_to_check.items():
    found = []
    for is_64 in (True, False):
        access = (winreg.KEY_WOW64_64KEY if is_64 else winreg.KEY_WOW64_32KEY) | winreg.KEY_READ
        for sub in (f"CLSID\\{clsid}\\InprocServer32", f"Software\\Classes\\CLSID\\{clsid}\\InprocServer32"):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub, 0, access) as k:
                    val, _ = winreg.QueryValueEx(k, "")
                    found.append(f"{'64-bit' if is_64 else '32-bit'}: {val}")
            except Exception:
                pass
    if found:
        log(f"  [FOUND] {name} ({clsid}): {'; '.join(found)}")
    else:
        log(f"  [MISSING] {name} ({clsid}) not found in 64-bit or 32-bit registry!")

# 3. Check WIA DeviceManager
try:
    log("\n--- WIA Check ---")
    ole32 = ctypes.oledll.ole32
    ole32.CoInitialize(None)
    # WIA DeviceManager CLSID: {E1C5D730-7E97-4D8A-9E42-BBAE87C2059F}
    CLSID_WiaDevMgr = ctypes.create_string_buffer(16)
    IID_IWiaDevMgr = ctypes.create_string_buffer(16)
    ole32.CLSIDFromString(ctypes.c_wchar_p("{E1C5D730-7E97-4D8A-9E42-BBAE87C2059F}"), CLSID_WiaDevMgr)
    ole32.CLSIDFromString(ctypes.c_wchar_p("{5EB2502A-8CF1-11D1-BF92-0060081ED811}"), IID_IWiaDevMgr)
    p_dev_mgr = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(CLSID_WiaDevMgr, None, 1, IID_IWiaDevMgr, ctypes.byref(p_dev_mgr))
    log(f"WIA CoCreateInstance hr=0x{hr & 0xFFFFFFFF:08X}, ptr={p_dev_mgr.value}")
except Exception as ex:
    log(f"WIA Exception: {ex}")

Path(r"C:\Users\and!m\OpenEOS\diagnostic_output.txt").write_text("\n".join(log_lines), encoding="utf-8")
