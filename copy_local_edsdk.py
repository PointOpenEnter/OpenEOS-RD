import shutil
from pathlib import Path

src_dir = Path(r"C:\Program Files (x86)\Canon\EOS Utility\EU3")
dest_dir = Path(r"C:\Users\and!m\OpenEOS")

copied = []
for fn in ["EDSDK.dll", "EdsImage.dll"]:
    src = src_dir / fn
    dest = dest_dir / fn
    if src.exists():
        shutil.copy2(src, dest)
        copied.append(f"{fn} ({dest.stat().st_size:,} bytes)")

Path(dest_dir / "copied_edsdk.log").write_text("\n".join(copied), encoding="utf-8")
