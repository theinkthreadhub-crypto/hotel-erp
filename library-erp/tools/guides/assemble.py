# python3 assemble.py cover.pdf body.pdf out.pdf  [chapter-title-prefix-regex ...]
import sys, re
from pypdf import PdfReader, PdfWriter
cover, body, out = sys.argv[1:4]
w = PdfWriter()
for f in (cover, body):
    for pg in PdfReader(f).pages: w.add_page(pg)
rd = PdfReader(body); n0 = len(PdfReader(cover).pages)
seen = set()
for i, pg in enumerate(rd.pages):
    t = (pg.extract_text() or '')
    first = t.strip().split('\n')[0] if t.strip() else ''
    m = re.match(r'^(\d{1,2}\.\s.+|Is guide me kya hai|Setu Pro Team Guide.*|Ye guide.*)$', first)
    if m and first not in seen:
        seen.add(first); w.add_outline_item(first[:70], n0 + i)
w.add_metadata({'/Title': sys.argv[4] if len(sys.argv) > 4 else 'Guide', '/Author': 'Setu Pro'})
w.write(out); print('assembled', out, len(w.pages), 'pages')
