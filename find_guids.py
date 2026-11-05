"""
Find all GUIDs, Device Interfaces, and IOCTLs in TornadoEOS.exe.
"""
import re
from pathlib import Path

exe_path = Path(r"c:\Users\and!m\Downloads\Telegram Desktop\TornadoEOS\TornadoEOS.exe")
data = exe_path.read_bytes()

print(f"Loaded TornadoEOS.exe ({len(data):,} bytes)")

# 1. Search for text GUIDs: {XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}
guid_re = re.compile(rb"\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}")
guids = set(guid_re.findall(data))
print(f"\n--- Text GUIDs Found ({len(guids)}) ---")
for g in sorted(guids):
    g_str = g.decode("ascii")
    print(f"  • {g_str}")

# 2. Search for strings mentioning device paths or classes
print("\n--- Device Paths and Interface Strings ---")
dev_re = re.compile(rb"(\\\\?\\?[a-zA-Z0-9_\-\#\{\}\&]+)")
matches = set(dev_re.findall(data))
for m in sorted(matches):
    if len(m) > 6 and any(k in m.lower() for k in [b"usb", b"wpd", b"mtp", b"canon", b"vid", b"pid", b"device"]):
        print(f"  • {m.decode('ascii', errors='replace')}")

# 3. Search for known PTP / Canon method strings
print("\n--- Canon PTP Method Strings ---")
ptp_words = [b"PTP", b"MTP", b"FA_", b"EOS_", b"SendCommand", b"GetProperty", b"SetProperty", b"OpenSession", b"CloseSession"]
for w in ptp_words:
    hits = data.count(w)
    if hits > 0:
        print(f"  • '{w.decode('ascii')}': {hits} occurrences")

print("\n[OK] GUID and Interface search complete.")
