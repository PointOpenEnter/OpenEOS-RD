from pathlib import Path
import re

p = Path(r"c:\Users\and!m\Downloads\Telegram Desktop\TornadoEOS\TornadoEOS.exe")
if p.exists():
    raw = p.read_bytes()
    # Search for Unicode and ASCII strings
    ascii_strs = re.findall(rb'[\x20-\x7E]{4,120}', raw)
    unicode_strs = re.findall(rb'(?:[\x20-\x7E]\x00){4,120}', raw)
    
    matches = []
    for s in ascii_strs:
        text = s.decode('ascii', errors='ignore')
        if any(w in text.lower() for w in ["\\\\", "vid_", "pid_", "usb#", "wpd", "ptp", "setupdi", "deviceio", "createfile", "ioctl"]):
            matches.append("ASCII: " + text)

    for s in unicode_strs:
        text = s.decode('utf-16le', errors='ignore')
        if any(w in text.lower() for w in ["\\\\", "vid_", "pid_", "usb#", "wpd", "ptp", "setupdi", "deviceio", "createfile", "ioctl"]):
            matches.append("UNICODE: " + text)

    Path(r"C:\Users\and!m\OpenEOS\tornado_target_strings.txt").write_text("\n".join(matches[:200]), encoding="utf-8")
