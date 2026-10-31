import urllib.request
import urllib.error
import re
import ssl
import json

url = "https://shuttercount.org/"
print(f"Connecting to {url} ...")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(
    url,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
)

try:
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")
        headers = dict(resp.getheaders())

    print(f"Status: {resp.status}")
    print(f"HTML length: {len(html)} bytes")

    # Extract scripts, forms, APIs
    scripts = re.findall(r'<script[^>]*src=["\'](.*?)["\']', html, re.I)
    forms = re.findall(r'<form[^>]*action=["\'](.*?)["\']', html, re.I)
    title = re.search(r'<title>(.*?)</title>', html, re.I)
    title_text = title.group(1) if title else "No title"

    # Search for keywords
    keywords = ["exiftool", "shutter", "canon", "cr3", "wasm", "upload", "api", "database", "mechanical"]
    findings = {}
    for kw in keywords:
        matches = len(re.findall(re.escape(kw), html, re.I))
        findings[kw] = matches

    out_file = "shuttercount_analysis.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(f"Title: {title_text}\n")
        f.write(f"Headers: {json.dumps(headers, indent=2)}\n\n")
        f.write(f"Scripts: {scripts}\n\n")
        f.write(f"Forms: {forms}\n\n")
        f.write(f"Keyword counts: {json.dumps(findings, indent=2)}\n\n")
        f.write("=== HTML PREVIEW (first 4000 chars) ===\n")
        f.write(html[:4000])

    print(f"Analysis saved to {out_file}")

except Exception as e:
    print(f"Error connecting: {e}")
    with open("shuttercount_analysis.txt", "w", encoding="utf-8") as f:
        f.write(f"Error: {e}\n")
