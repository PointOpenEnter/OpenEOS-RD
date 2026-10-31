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

# Extract text without HTML tags for clean reading
clean_text = re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
clean_text = re.sub(r'<style\b[^>]*>.*?</style>', '', clean_text, flags=re.DOTALL | re.IGNORECASE)
clean_text = re.sub(r'<[^>]+>', '\n', clean_text)
lines = [l.strip() for l in clean_text.split('\n') if l.strip()]

# Find all lines mentioning canon, mechanical, cr3, shutter
relevant = []
for i, line in enumerate(lines):
    l_lower = line.lower()
    if any(k in l_lower for k in ["canon", "mechanical", "cr3", "rating", "database", "accuracy", "electronic"]):
        start = max(0, i - 2)
        end = min(len(lines), i + 3)
        relevant.append("\n".join(lines[start:end]))

with open("shuttercount_canon_report.txt", "w", encoding="utf-8") as f:
    f.write("=== RELEVANT EXCERPTS FROM SHUTTERCOUNT.ORG ===\n\n")
    seen = set()
    for block in relevant:
        if block not in seen:
            seen.add(block)
            f.write(block + "\n" + "-"*50 + "\n")

print("Canon report generated.")
