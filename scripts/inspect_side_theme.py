from pathlib import Path
import re

content = Path("hotel_erp.html").read_text(encoding="utf-8")
lines = content.splitlines()

print("Searching for horeca sidebar styling...")
for i, line in enumerate(lines):
    if "horeca" in line.lower() and "#side" in line:
        print(f"L{i+1}: {line[:140]}")

