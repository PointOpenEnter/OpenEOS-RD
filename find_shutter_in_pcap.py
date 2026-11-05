from pathlib import Path
import struct

pcap = Path(r"c:\Users\and!m\Documents\р62.pcapng")
lines = []

if pcap.exists():
    raw = pcap.read_bytes()
    lines.append(f"PCAP loaded: {len(raw):,} bytes")

    targets = {
        "Shutter 60688": struct.pack("<I", 60688),
        "Shutter 60689": struct.pack("<I", 60689),
        "Release 840377": struct.pack("<I", 840377),
    }

    for name, b in targets.items():
        idx = 0
        while True:
            idx = raw.find(b, idx)
            if idx == -1: break
            # Context around the match
            ctx = raw[max(0, idx - 32):min(len(raw), idx + 32)]
            lines.append(f"[MATCH] {name} at offset 0x{idx:08X} ({idx:,})")
            lines.append(f"  Hex context: {ctx.hex(' ')}")
            idx += 1

Path(r"C:\Users\and!m\OpenEOS\pcap_shutter_hits.txt").write_text("\n".join(lines), encoding="utf-8")
