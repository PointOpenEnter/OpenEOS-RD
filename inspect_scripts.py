import urllib.request
import re
import ssl

url = "https://shuttercount.org/"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(
    url,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
)

with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
    html = resp.read().decode("utf-8", errors="replace")

# Save full HTML
with open("shuttercount_full.html", "w", encoding="utf-8") as f:
    f.write(html)

# Find all script tags (inline and src)
script_blocks = re.findall(r'<script\b[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
script_srcs = re.findall(r'<script\b[^>]*\bsrc=["\'](.*?)["\']', html, re.IGNORECASE)

# Find module scripts or Vite / Webpack bundles
links = re.findall(r'<link\b[^>]*\bhref=["\'](.*?)["\']', html, re.IGNORECASE)

with open("shuttercount_details.txt", "w", encoding="utf-8") as f:
    f.write("=== SCRIPT SRCS ===\n")
    for s in script_srcs:
        f.write(s + "\n")
    f.write("\n=== LINK ASSETS ===\n")
    for l in links:
        if ".js" in l or ".css" in l:
            f.write(l + "\n")
    f.write(f"\n=== INLINE SCRIPTS ({len(script_blocks)} blocks) ===\n")
    for i, sb in enumerate(script_blocks):
        if len(sb.strip()) > 0:
            f.write(f"\n--- BLOCK {i} ({len(sb)} chars) ---\n")
            f.write(sb[:1500] + ("\n...[truncated]..." if len(sb) > 1500 else ""))

print("Done details.")
