# Shared helpers for the two PDF guides (HTML -> PDF via Playwright/Chromium)
import base64, io, os
from PIL import Image
SHOTS = os.environ.get('SHOTS', '/tmp/claude-0/guide/shots')
CSS = r'''
@page { size: A4; margin: 16mm 15mm 18mm 15mm; }
*{box-sizing:border-box}
body{font-family:"Inter","Noto Sans","DejaVu Sans",Arial,sans-serif;font-size:10.6pt;line-height:1.5;color:#1d2433;margin:0}
h1{font-size:22pt;color:#1f3a63;margin:0 0 4mm;border-bottom:3px solid #e8590c;padding-bottom:3mm;margin-top:11mm;page-break-after:avoid}
h1.first{margin-top:0}
h2{font-size:13.5pt;color:#1f3a63;margin:7mm 0 2mm;page-break-after:avoid}
h3{font-size:11.5pt;color:#2b4c7e;margin:5mm 0 1.5mm;page-break-after:avoid}
p{margin:0 0 2.4mm}
.lead{font-size:11.5pt;color:#3a4358}
ol,ul{margin:1mm 0 3mm 0;padding-left:6mm}li{margin:0 0 1.4mm}
ol.steps{counter-reset:s;list-style:none;padding-left:0}
ol.steps>li{counter-increment:s;position:relative;padding-left:9mm;margin-bottom:2.2mm;page-break-inside:avoid}
ol.steps>li:before{content:counter(s);position:absolute;left:0;top:0.3mm;width:6.2mm;height:6.2mm;border-radius:50%;background:#1f3a63;color:#fff;font-weight:700;font-size:9pt;text-align:center;line-height:6.2mm}
.box{border-radius:2.5mm;padding:3mm 4mm;margin:3mm 0;page-break-inside:avoid;font-size:10pt}
.tip{background:#e8f5ea;border-left:1.6mm solid #1e8e3e}
.warn{background:#fff4de;border-left:1.6mm solid #e08a00}
.danger{background:#fde8e8;border-left:1.6mm solid #c62828}
.info{background:#e9f0fb;border-left:1.6mm solid #2b4c7e}
.box b.t{display:block;margin-bottom:0.8mm}
table{border-collapse:collapse;width:100%;margin:2.5mm 0 4mm;font-size:9.6pt;page-break-inside:auto}
th{background:#1f3a63;color:#fff;text-align:left;padding:1.8mm 2.4mm;font-weight:600}
td{padding:1.7mm 2.4mm;border-bottom:0.3mm solid #dfe4ee;vertical-align:top}
tr:nth-child(even) td{background:#f6f8fc}tr{page-break-inside:avoid}
code,.k{font-family:"DejaVu Sans Mono",Consolas,monospace;background:#eef2f8;border:0.3mm solid #d5dcea;border-radius:1mm;padding:0 1.2mm;font-size:9.4pt}
.k{font-weight:700;color:#1f3a63;background:#fff;border-bottom-width:0.7mm}
figure{margin:3mm 0 4mm;text-align:center;page-break-inside:avoid}
figure img{max-width:100%;border:0.3mm solid #c9d2e3;border-radius:1.5mm;box-shadow:0 0.6mm 2mm #1d2b4a22}
figcaption{font-size:8.8pt;color:#5a6478;margin-top:1.2mm}
.row2{display:flex;gap:4mm;justify-content:center;align-items:flex-start}
.row2 figure{flex:1;margin:3mm 0}.row2 img{max-height:112mm;width:auto;max-width:100%}
.row3 img{max-height:92mm}
.small{font-size:9pt;color:#5a6478}
.pill{display:inline-block;background:#1f3a63;color:#fff;border-radius:20px;padding:0 2.5mm;font-size:9pt;font-weight:600}
.toc td{padding:1.1mm 2mm;border:0;background:none!important}.toc td.n{width:8mm;color:#e8590c;font-weight:700}
.cols{display:flex;gap:5mm}.cols>div{flex:1}
.card3{display:flex;gap:3mm;margin:3mm 0}.card3>div{flex:1;border:0.3mm solid #d5dcea;border-radius:2.5mm;padding:3mm;background:#f9fbff;font-size:9.6pt}
.card3 b{color:#1f3a63;display:block;margin-bottom:1mm;font-size:10.5pt}
'''
def img(name, w=1000, q=80):
    p = os.path.join(SHOTS, name + '.jpg')
    im = Image.open(p).convert('RGB')
    if im.width > w: im = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
    b = io.BytesIO(); im.save(b, 'JPEG', quality=q, optimize=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()
def fig(name, cap='', w=1000):
    return f'<figure><img src="{img(name, w)}"><figcaption>{cap}</figcaption></figure>'
def row(names, caps, w=460, cls=''):
    return '<div class="row2 %s">' % cls + ''.join(f'<figure><img src="{img(n, w)}"><figcaption>{c}</figcaption></figure>' for n, c in zip(names, caps)) + '</div>'
def box(kind, title, body):
    return f'<div class="box {kind}"><b class="t">{title}</b>{body}</div>'
def steps(*items): return '<ol class="steps">' + ''.join(f'<li>{i}</li>' for i in items) + '</ol>'
def ul(*items): return '<ul>' + ''.join(f'<li>{i}</li>' for i in items) + '</ul>'
def table(head, rows): return '<table><tr>' + ''.join(f'<th>{h}</th>' for h in head) + '</tr>' + ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows) + '</table>'
def cover(title, sub, who, ver='v1.26'):
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
@page{{size:A4;margin:0}}*{{box-sizing:border-box}}body{{margin:0;font-family:"Inter","Noto Sans",Arial,sans-serif;color:#fff}}
.c{{width:210mm;height:297mm;background:linear-gradient(160deg,#16294a 0%,#1f3a63 55%,#2b4c7e 100%);padding:26mm 20mm;position:relative;overflow:hidden}}
.c:before{{content:"";position:absolute;right:-40mm;top:-30mm;width:130mm;height:130mm;border-radius:50%;background:#e8590c;opacity:.9}}
.c:after{{content:"";position:absolute;left:-30mm;bottom:-40mm;width:110mm;height:110mm;border-radius:50%;background:#ffffff14}}
.brand{{position:relative;font-size:15pt;letter-spacing:3px;font-weight:700}}.brand span{{color:#ffb585}}
h1{{position:relative;font-size:38pt;line-height:1.1;margin:55mm 0 8mm;border:0;padding:0;color:#fff;max-width:150mm}}
.sub{{position:relative;font-size:15pt;max-width:140mm;opacity:.95;line-height:1.45}}
.who{{position:relative;margin-top:14mm;display:inline-block;background:#ffffff22;border:0.4mm solid #ffffff66;border-radius:30px;padding:2.4mm 6mm;font-size:12pt;font-weight:600}}
.foot{{position:absolute;left:20mm;right:20mm;bottom:20mm;font-size:11pt;line-height:1.6}}
.foot b{{font-size:13pt}}
</style></head><body><div class="c"><div class="brand">SETU <span>PRO</span></div>
<h1>{title}</h1><div class="sub">{sub}</div><div class="who">{who}</div>
<div class="foot"><b>Setu Pro — Customer Support: 6392995127</b><br>setuproindia@gmail.com · www.setupro.in<br>Software version {ver} · October 2026</div></div></body></html>'''
def page(body, title):
    return f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><style>{CSS}</style></head><body>{body}</body></html>'
