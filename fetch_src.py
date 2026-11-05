import urllib.request
from pathlib import Path

base_url = "https://raw.githubusercontent.com/mvisonneau/openshuttercounter/main/"
files = [
    "pkg/usb/usb.go",
    "pkg/usb/usb_windows.go",
    "pkg/ptp/ptp.go",
    "pkg/canon/canon.go",
    "main.go"
]

dest_dir = Path(r"C:\Users\and!m\OpenEOS\openshuttercounter_src")
dest_dir.mkdir(exist_ok=True)

log = []
for f in files:
    url = base_url + f
    out_file = dest_dir / Path(f).name
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read()
            out_file.write_bytes(content)
            log.append(f"[OK] Downloaded {f} -> {out_file.name} ({len(content):,} bytes)")
    except Exception as ex:
        log.append(f"[FAIL] {f}: {ex}")

Path(r"C:\Users\and!m\OpenEOS\download_sources.log").write_text("\n".join(log), encoding="utf-8")
