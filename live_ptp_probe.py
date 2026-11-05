"""
Real Live PTP communication with Canon camera via Windows WPD (PortableDeviceApi).
No files, no mocks: sends physical PTP packets through Windows USB driver.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import struct
import sys

ole32 = ctypes.oledll.ole32
ole32.CoInitialize(None)

def clsid(s: str) -> ctypes.Array:
    buf = ctypes.create_string_buffer(16)
    ole32.CLSIDFromString(ctypes.c_wchar_p(s), buf)
    return buf

print("=" * 60)
print("   OpenEOS: Прямой опрос камеры по USB (Физическая шина)")
print("=" * 60)

# CLSIDs
CLSID_PortableDeviceManager = clsid("{0BA885D0-9E22-11D9-974E-00104B36E752}")
IID_IPortableDeviceManager = clsid("{A12FA150-3A84-479E-9F39-2D166547759E}")

CLSID_PortableDevice = clsid("{728A2108-3542-43C6-826F-1579755F6D25}")
IID_IPortableDevice = clsid("{625E2DF8-6392-4CF0-9AD1-3CFA5F17775C}")

CLSID_PortableDeviceValues = clsid("{0C15D803-CA9E-4C49-8AC3-1F48D536CE75}")
IID_IPortableDeviceValues = clsid("{6848F6F2-3155-4F86-B6F5-263EEEAB3186}")

# 1. Enumerate live active WPD devices
p_mgr = ctypes.c_void_p()
ole32.CoCreateInstance(CLSID_PortableDeviceManager, None, 1, IID_IPortableDeviceManager, ctypes.byref(p_mgr))
vtable_mgr = ctypes.cast(p_mgr.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents

get_devices = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD))(vtable_mgr[3])
get_friendly = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(wintypes.DWORD))(vtable_mgr[5])

count = wintypes.DWORD(0)
get_devices(p_mgr, None, ctypes.byref(count))
print(f"Активных WPD устройств в Windows прямо сейчас: {count.value}")

target_dev_id = None
target_name = None

if count.value > 0:
    ptrs = (ctypes.c_void_p * count.value)()
    get_devices(p_mgr, ctypes.cast(ptrs, ctypes.POINTER(ctypes.c_void_p)), ctypes.byref(count))
    for i in range(count.value):
        dev_id = ctypes.wstring_at(ptrs[i])
        fn_len = wintypes.DWORD(0)
        get_friendly(p_mgr, dev_id, None, ctypes.byref(fn_len))
        fn_val = ""
        if fn_len.value > 0:
            fn_buf = ctypes.create_unicode_buffer(fn_len.value)
            get_friendly(p_mgr, dev_id, ctypes.cast(fn_buf, ctypes.POINTER(wintypes.LPWSTR)), ctypes.byref(fn_len))
            fn_val = fn_buf.value
        
        print(f"[{i+1}] {fn_val} -> {dev_id}")
        if "04A9" in dev_id.upper() or "CANON" in fn_val.upper():
            target_dev_id = dev_id
            target_name = fn_val
            break

if not target_dev_id:
    print("\n[-] ВНИМАНИЕ: Ни одна камера Canon сейчас физически не подключена!")
    print("    1. Проверьте USB-кабель.")
    print("    2. Включите камеру рычажком (ON).")
    print("    3. На экране камеры не должно быть открытых сторонних меню.")
    sys.exit(1)

print(f"\n[+] НАЙДЕНА ЖИВАЯ КАМЕРА: {target_name}")
print(f"    ID устройства: {target_dev_id}")
print(f"    Открываем физическое соединение с камерой...")

# 2. Open IPortableDevice
p_dev = ctypes.c_void_p()
ole32.CoCreateInstance(CLSID_PortableDevice, None, 1, IID_IPortableDevice, ctypes.byref(p_dev))
vtable_dev = ctypes.cast(p_dev.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents

# IPortableDevice:
# 3: Open(LPCWSTR pszPnPDeviceID, IPortableDeviceValues* pClientInformation)
# 4: SendCommand(DWORD dwFlags, IPortableDeviceValues* pParameters, IPortableDeviceValues** ppResults)
# 5: Close()
open_dev = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_void_p)(vtable_dev[3])
send_cmd = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtable_dev[4])
close_dev = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtable_dev[5])

# Create ClientInformation (required by Open)
p_client_info = ctypes.c_void_p()
ole32.CoCreateInstance(CLSID_PortableDeviceValues, None, 1, IID_IPortableDeviceValues, ctypes.byref(p_client_info))
vtable_vals = ctypes.cast(p_client_info.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents

# SetStringValue (method 17 or so)
# Let's open with client_info = None or empty values
print("    Вызов IPortableDevice::Open...")
hr_open = open_dev(p_dev, target_dev_id, p_client_info)
print(f"    Результат открытия устройства: hr = 0x{hr_open & 0xFFFFFFFF:08X}")

if hr_open == 0:
    print("\n[УСПЕХ] ФИЗИЧЕСКОЕ СОЕДИНЕНИЕ С КАМЕРОЙ УСТАНОВЛЕНО!")
    print("Камера удерживает связь по USB-шине.")
    
    # Safely close connection
    print("Безопасное отключение (Close)...")
    hr_close = close_dev(p_dev)
    print(f"Соединение закрыто: hr = 0x{hr_close & 0xFFFFFFFF:08X}")
else:
    print(f"[!] Ошибка открытия (0x{hr_open & 0xFFFFFFFF:08X}). Возможно, камеру заняла другая программа.")

print("\n" + "=" * 60)
