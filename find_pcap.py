from pathlib import Path

docs = Path(r"c:\Users\and!m\Documents")
lines = []
if docs.exists():
    for f in docs.glob("*.pcap*"):
        lines.append(f"{f.name} ({f.stat().st_size:,} bytes)")
Path(r"C:\Users\and!m\OpenEOS\pcap_list.txt").write_text("\n".join(lines), encoding="utf-8")
