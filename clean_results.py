from pathlib import Path

raw = Path(r"c:\Users\and!m\OpenEOS\pe_imports_results.txt").read_bytes()
# Clean to safe printable ASCII lines
clean_lines = []
for line in raw.splitlines():
    clean = "".join(chr(b) if 32 <= b <= 126 else " " for b in line).strip()
    if clean:
        clean_lines.append(clean)

Path(r"c:\Users\and!m\OpenEOS\pe_clean.txt").write_text("\n".join(clean_lines), encoding="ascii")
print(f"Cleaned {len(clean_lines)} lines to pe_clean.txt")
