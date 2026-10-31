"""Original flat illustrations for the Smart Food Visuals library (no third-party artwork).

Every picture is drawn here from basic shapes, so the project owns it and may ship it in the EXE,
the cloud and the QR menu. These are *illustrations* — the app labels them as such, never as photos.

python tools/food-library/art.py <out_dir>      → <out_dir>/<id>.svg for every dish family and category
"""
import math
import os
import random
import sys

W = 512


def tile(bg1, bg2, body, ring='#ffffff'):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {W}" width="{W}" height="{W}">
<defs><radialGradient id="bg" cx="50%" cy="38%" r="75%"><stop offset="0" stop-color="{bg1}"/><stop offset="1" stop-color="{bg2}"/></radialGradient>
<radialGradient id="sh" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#000" stop-opacity=".22"/><stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient></defs>
<rect width="{W}" height="{W}" fill="url(#bg)"/>
{body}
</svg>'''


def shadow(cx=256, cy=300, rx=200, ry=70):
    return f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="url(#sh)"/>'


def plate(cx=256, cy=270, r=190, rim='#f8fafc', inner='#ffffff'):
    return (shadow(cx, cy + 40, r + 10, r * .38) +
            f'<ellipse cx="{cx}" cy="{cy}" rx="{r}" ry="{r * .62}" fill="{rim}" stroke="#e2e8f0" stroke-width="3"/>'
            f'<ellipse cx="{cx}" cy="{cy}" rx="{r * .78}" ry="{r * .48}" fill="{inner}" stroke="#eef2f7" stroke-width="2"/>')


def bowl(cx=256, cy=250, r=150, sauce='#e07a2f', rim='#7c2d12', outer='#9a3412', depth=1.0):
    """A handi / katori seen from the front-top: rim ellipse filled with gravy."""
    h = r * .55 * depth
    return (shadow(cx, cy + h + 30, r + 20, 50) +
            f'<path d="M{cx - r},{cy} Q{cx - r * .9},{cy + h * 1.6} {cx},{cy + h * 1.55} Q{cx + r * .9},{cy + h * 1.6} {cx + r},{cy} Z" fill="{outer}"/>'
            f'<path d="M{cx - r * .55},{cy + h * 1.35} Q{cx},{cy + h * 1.5} {cx + r * .55},{cy + h * 1.35}" stroke="#fff" stroke-opacity=".18" stroke-width="8" fill="none"/>'
            f'<ellipse cx="{cx}" cy="{cy}" rx="{r}" ry="{r * .36}" fill="{rim}"/>'
            f'<ellipse cx="{cx}" cy="{cy + 4}" rx="{r * .9}" ry="{r * .3}" fill="{sauce}"/>'
            f'<ellipse cx="{cx - r * .3}" cy="{cy - 4}" rx="{r * .35}" ry="{r * .08}" fill="#fff" fill-opacity=".22"/>')


def scatter(seed, n, cx, cy, rx, ry, draw):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        a = rnd.random() * math.tau
        d = math.sqrt(rnd.random())
        out.append(draw(cx + math.cos(a) * rx * d, cy + math.sin(a) * ry * d, rnd))
    return ''.join(out)


def cube(x, y, s, top, side, rot=0):
    return (f'<g transform="rotate({rot} {x} {y})"><rect x="{x - s / 2}" y="{y - s / 2}" width="{s}" height="{s * .8}" rx="4" fill="{side}"/>'
            f'<rect x="{x - s / 2}" y="{y - s / 2 - s * .18}" width="{s}" height="{s * .6}" rx="4" fill="{top}"/></g>')


def leaves(seed, n, cx, cy, rx, ry, col='#16a34a'):
    return scatter(seed, n, cx, cy, rx, ry, lambda x, y, r: f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="7" ry="3.5" fill="{col}" transform="rotate({r.randint(0, 180)} {x:.0f} {y:.0f})"/>')


def curry(sauce, rim, outer, pieces, seed=1, cream=True, garnish='#16a34a'):
    b = bowl(sauce=sauce, rim=rim, outer=outer)
    b += pieces
    if cream:
        b += '<path d="M180,246 q30,-14 60,0 t60,0 t40,-4" stroke="#fff7ed" stroke-width="7" fill="none" stroke-linecap="round" opacity=".9"/>'
    b += leaves(seed, 9, 256, 250, 110, 30, garnish)
    return b


def pieces_cubes(seed, top, side, n=9, s=30):
    return scatter(seed, n, 256, 252, 105, 28, lambda x, y, r: cube(x, y, s, top, side, r.randint(-20, 20)))


def pieces_blobs(seed, col, dark, n=8, s=26):
    return scatter(seed, n, 256, 252, 105, 28, lambda x, y, r: f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{s}" ry="{s * .62}" fill="{col}"/><ellipse cx="{x - 6:.0f}" cy="{y - 5:.0f}" rx="{s * .45}" ry="{s * .2}" fill="#fff" fill-opacity=".25"/><ellipse cx="{x + 8:.0f}" cy="{y + 6:.0f}" rx="{s * .3}" ry="{s * .18}" fill="{dark}" fill-opacity=".5"/>')


def dots(seed, n, cx, cy, rx, ry, cols, rr=(4, 8)):
    return scatter(seed, n, cx, cy, rx, ry, lambda x, y, r: f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r.randint(*rr)}" fill="{r.choice(cols)}"/>')


def rice_mound(cx=256, cy=270, r=150, grain='#fffaf0', tint='#fff', seed=3, extra=''):
    mound = f'<path d="M{cx - r},{cy + 40} Q{cx - r * .8},{cy - r * .7} {cx},{cy - r * .75} Q{cx + r * .8},{cy - r * .7} {cx + r},{cy + 40} Z" fill="{tint}"/>'
    grains = scatter(seed, 160, cx, cy - 20, r * .85, r * .5, lambda x, y, rn: f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="7" ry="2.6" fill="{grain}" stroke="#e7dcc4" stroke-width=".8" transform="rotate({rn.randint(0, 180)} {x:.0f} {y:.0f})"/>')
    return plate(cy=cy + 30) + mound + grains + extra


def glass(fill, top, cx=256, h=300, w=120, ice=False, straw=None, foam=None, garnish=''):
    y0 = 120
    out = shadow(cx, y0 + h + 10, w + 20, 26)
    out += f'<path d="M{cx - w / 2},{y0} L{cx - w / 2 + 14},{y0 + h} L{cx + w / 2 - 14},{y0 + h} L{cx + w / 2},{y0} Z" fill="#e0f2fe" fill-opacity=".55" stroke="#cbd5e1" stroke-width="3"/>'
    out += f'<path d="M{cx - w / 2 + 6},{y0 + 40} L{cx - w / 2 + 18},{y0 + h - 6} L{cx + w / 2 - 18},{y0 + h - 6} L{cx + w / 2 - 6},{y0 + 40} Z" fill="{fill}"/>'
    out += f'<ellipse cx="{cx}" cy="{y0 + 40}" rx="{w / 2 - 6}" ry="9" fill="{top}"/>'
    if ice:
        for i, (dx, dy) in enumerate([(-22, 70), (18, 95), (-8, 135)]):
            out += f'<rect x="{cx + dx - 18}" y="{y0 + dy}" width="36" height="32" rx="6" fill="#fff" fill-opacity=".45" transform="rotate({12 * (i - 1)} {cx + dx} {y0 + dy})"/>'
    if foam:
        out += f'<path d="M{cx - w / 2 + 4},{y0 + 40} q{w / 4},-46 {w / 2 - 4},-26 q{w / 4},-30 {w / 2 - 4},26 Z" fill="{foam}"/>'
    if straw:
        out += f'<path d="M{cx + 18},{y0 + h - 40} L{cx + 40},{y0 - 50} L{cx + 70},{y0 - 70}" stroke="{straw}" stroke-width="12" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    out += f'<path d="M{cx - w / 2 + 16},{y0 + 50} L{cx - w / 2 + 26},{y0 + h - 30}" stroke="#fff" stroke-opacity=".5" stroke-width="7" stroke-linecap="round"/>'
    return out + garnish


def cup(fill, saucer='#e2e8f0', body='#ffffff', steam=True, art=''):
    out = shadow(256, 380, 190, 36)
    out += f'<ellipse cx="256" cy="360" rx="170" ry="46" fill="{saucer}"/><ellipse cx="256" cy="352" rx="120" ry="28" fill="#cbd5e1"/>'
    out += f'<path d="M140,230 Q146,350 256,352 Q366,350 372,230 Z" fill="{body}" stroke="#e2e8f0" stroke-width="3"/>'
    out += '<path d="M370,250 q60,0 52,45 q-8,40 -60,40" stroke="#e2e8f0" stroke-width="18" fill="none"/>'
    out += f'<ellipse cx="256" cy="230" rx="116" ry="30" fill="{body}"/><ellipse cx="256" cy="232" rx="104" ry="24" fill="{fill}"/>' + art
    if steam:
        out += ''.join(f'<path d="M{x},190 q-18,-30 0,-55 q18,-25 0,-55" stroke="#fff" stroke-opacity=".75" stroke-width="9" fill="none" stroke-linecap="round"/>' for x in (215, 256, 297))
    return out


def flatbread(cx, cy, rx, ry, col, spot, seed, rot=0, n=26, edge='#c2410c'):
    s = f'<g transform="rotate({rot} {cx} {cy})"><ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{col}" stroke="{edge}" stroke-opacity=".35" stroke-width="4"/>'
    s += scatter(seed, n, cx, cy, rx * .85, ry * .8, lambda x, y, r: f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{r.randint(5, 12)}" ry="{r.randint(3, 7)}" fill="{spot}" fill-opacity="{r.uniform(.35, .8):.2f}"/>')
    return s + '</g>'


def drumstick(x, y, rot, col='#c2410c'):
    return (f'<g transform="rotate({rot} {x} {y})"><ellipse cx="{x}" cy="{y}" rx="58" ry="40" fill="{col}"/>'
            f'<ellipse cx="{x - 14}" cy="{y - 12}" rx="24" ry="10" fill="#fff" fill-opacity=".18"/>'
            f'<rect x="{x + 46}" y="{y - 9}" width="46" height="18" rx="9" fill="#fef3c7"/><circle cx="{x + 94}" cy="{y - 8}" r="11" fill="#fef3c7"/><circle cx="{x + 94}" cy="{y + 8}" r="11" fill="#fef3c7"/>'
            + ''.join(f'<path d="M{x - 30 + i * 18},{y - 20} l10,40" stroke="#7c2d12" stroke-opacity=".55" stroke-width="6" stroke-linecap="round"/>' for i in range(4)) + '</g>')


def onion_lemon(cx=380, cy=330):
    return (f'<ellipse cx="{cx}" cy="{cy}" rx="34" ry="22" fill="#fde68a" stroke="#facc15" stroke-width="5"/>'
            f'<path d="M{cx - 30},{cy} h60 M{cx},{cy - 20} v40" stroke="#facc15" stroke-width="3"/>'
            f'<ellipse cx="{cx - 230}" cy="{cy + 5}" rx="36" ry="24" fill="none" stroke="#f9a8d4" stroke-width="8"/>'
            f'<ellipse cx="{cx - 200}" cy="{cy + 14}" rx="28" ry="18" fill="none" stroke="#f9a8d4" stroke-width="7"/>')


def skewer(y, cols, x0=110, x1=400):
    s = f'<line x1="{x0 - 30}" y1="{y + 30}" x2="{x1 + 40}" y2="{y - 30}" stroke="#a16207" stroke-width="7" stroke-linecap="round"/>'
    n = len(cols)
    for i, (top, side) in enumerate(cols):
        x = x0 + (x1 - x0) * i / (n - 1)
        yy = y + 30 - 60 * (x - x0 + 30) / (x1 - x0 + 70)
        s += cube(x, yy, 46, top, side, -10)
    return s


def char_marks(seed, n, cx, cy, rx, ry):
    return scatter(seed, n, cx, cy, rx, ry, lambda x, y, r: f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{r.randint(4, 9)}" ry="3" fill="#431407" fill-opacity=".45"/>')


# ---------- dish families ----------
def ART():
    A = {}
    A['paneer-curry'] = tile('#fff7ed', '#fed7aa', curry('#ea7a2c', '#7c2d12', '#9a3412', pieces_cubes(11, '#fffbeb', '#fde68a'), 2))
    A['veg-curry'] = tile('#fefce8', '#fde68a', curry('#d97706', '#78350f', '#92400e', pieces_blobs(12, '#facc15', '#a16207', 6, 22) + dots(5, 26, 256, 252, 110, 30, ['#16a34a', '#f97316', '#fef9c3', '#22c55e'], (5, 9)), 3))
    A['bean-curry'] = tile('#fff1f2', '#fecaca', curry('#b45309', '#451a03', '#78350f', scatter(13, 60, 256, 252, 110, 30, lambda x, y, r: f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="11" ry="8" fill="{r.choice(["#d6a35c", "#c48a3f", "#e0b574"])}" stroke="#7c2d12" stroke-opacity=".4"/>'), 4, cream=False) + '<path d="M300,236 l10,-12 l10,12 z" fill="#fde68a"/>')
    A['dal'] = tile('#fefce8', '#fef08a', curry('#eab308', '#713f12', '#854d0e', dots(14, 30, 256, 250, 105, 28, ['#b91c1c', '#7f1d1d', '#facc15'], (3, 6)), 5, cream=True))
    A['chicken-curry'] = tile('#fff7ed', '#fdba74', curry('#dc5a1e', '#7c2d12', '#9a3412', pieces_blobs(15, '#b45309', '#7c2d12', 7, 28), 6))
    A['mutton-curry'] = tile('#fef2f2', '#fca5a5', curry('#9a3412', '#450a0a', '#7f1d1d', pieces_blobs(16, '#6b2a0e', '#3f1205', 7, 28), 7, cream=False))
    A['egg-curry'] = tile('#fff7ed', '#fed7aa', curry('#e2742a', '#7c2d12', '#9a3412', scatter(17, 4, 256, 250, 90, 22, lambda x, y, r: f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="32" ry="22" fill="#fff"/><circle cx="{x:.0f}" cy="{y - 2:.0f}" r="12" fill="#f59e0b"/>'), 8, cream=False))
    A['fish-curry'] = tile('#ecfeff', '#a5f3fc', curry('#f97316', '#7c2d12', '#9a3412', scatter(18, 5, 256, 250, 95, 24, lambda x, y, r: f'<rect x="{x - 30:.0f}" y="{y - 14:.0f}" width="60" height="28" rx="12" fill="#fdba74" stroke="#c2410c" stroke-width="3" transform="rotate({r.randint(-25, 25)} {x:.0f} {y:.0f})"/>'), 9, cream=False) + '<circle cx="360" cy="236" r="6" fill="#facc15"/>')
    A['tandoori-chicken'] = tile('#fff1f2', '#fda4af', plate() + drumstick(205, 250, -12) + drumstick(300, 290, 18, '#b91c1c') + drumstick(240, 312, 4, '#dc2626') + onion_lemon() + leaves(19, 8, 256, 270, 150, 60))
    A['paneer-tikka'] = tile('#fff7ed', '#fdba74', plate() + skewer(250, [('#fb923c', '#c2410c'), ('#22c55e', '#15803d'), ('#fdba74', '#ea580c'), ('#ef4444', '#b91c1c'), ('#fb923c', '#c2410c')]) + char_marks(20, 14, 256, 245, 140, 30) + onion_lemon(390, 320) + leaves(21, 6, 256, 300, 150, 40))
    fillet = lambda x, y, rot: f'<g transform="rotate({rot} {x} {y})"><path d="M{x - 80},{y} Q{x - 60},{y - 40} {x + 20},{y - 34} Q{x + 80},{y - 28} {x + 90},{y} Q{x + 80},{y + 28} {x + 20},{y + 34} Q{x - 60},{y + 40} {x - 80},{y} Z" fill="#d97706" stroke="#92400e" stroke-width="4"/>' + ''.join(f'<circle cx="{x - 50 + i * 22}" cy="{y + (i % 2) * 10 - 5}" r="5" fill="#7c2d12" fill-opacity=".45"/>' for i in range(6)) + '</g>'
    A['fish-fry'] = tile('#ecfeff', '#a5f3fc', plate() + fillet(220, 240, -8) + fillet(290, 300, 6) + onion_lemon(390, 300) + leaves(72, 8, 256, 270, 150, 55))
    seekh = lambda y, col: f'<line x1="90" y1="{y + 20}" x2="420" y2="{y - 20}" stroke="#a16207" stroke-width="6" stroke-linecap="round"/><path d="M130,{y + 16} L380,{y - 14}" stroke="{col}" stroke-width="38" stroke-linecap="round"/>' + ''.join(f'<path d="M{150 + i * 38},{y + 26 - i * 4.5} l8,-34" stroke="#3f1205" stroke-opacity=".45" stroke-width="5" stroke-linecap="round"/>' for i in range(6))
    A['kebab'] = tile('#fff1f2', '#fda4af', plate() + seekh(230, '#9a3412') + seekh(300, '#7c2d12') + onion_lemon(390, 330) + leaves(73, 10, 256, 270, 150, 55))
    patty = lambda x, y, col: f'<ellipse cx="{x}" cy="{y + 8}" rx="54" ry="30" fill="#78350f" fill-opacity=".35"/><ellipse cx="{x}" cy="{y}" rx="54" ry="30" fill="{col}"/><ellipse cx="{x - 14}" cy="{y - 10}" rx="20" ry="8" fill="#fff" fill-opacity=".25"/>' + ''.join(f'<circle cx="{x + dx}" cy="{y + dy}" r="4" fill="#facc15"/>' for dx, dy in ((-20, 6), (10, -8), (24, 10)))
    A['veg-kebab'] = tile('#f0fdf4', '#bbf7d0', plate() + patty(190, 245, '#4d7c0f') + patty(300, 240, '#65a30d') + patty(245, 305, '#3f6212') + '<ellipse cx="370" cy="315" rx="36" ry="18" fill="#16a34a"/>' + leaves(74, 6, 256, 270, 140, 50))
    A['veg-biryani'] = tile('#fefce8', '#fde68a', rice_mound(grain='#fff7d6', tint='#fde68a', seed=22, extra=dots(23, 28, 256, 245, 120, 60, ['#f97316', '#16a34a', '#facc15', '#fb923c'], (5, 8)) + leaves(24, 10, 256, 235, 110, 55) + '<path d="M300,180 q20,-10 30,10" stroke="#a16207" stroke-width="5" fill="none"/>'))
    A['chicken-biryani'] = tile('#fff7ed', '#fdba74', rice_mound(grain='#fff7d6', tint='#fcd34d', seed=25, extra=drumstick(220, 225, -20, '#b45309') + '<ellipse cx="320" cy="245" rx="30" ry="22" fill="#fff"/><circle cx="320" cy="243" r="11" fill="#f59e0b"/>' + leaves(26, 10, 256, 240, 110, 55) + dots(27, 14, 256, 250, 110, 50, ['#ea580c', '#f97316'], (4, 6))))
    A['rice'] = tile('#f8fafc', '#e2e8f0', rice_mound(seed=28, extra=dots(29, 24, 256, 240, 110, 55, ['#78350f', '#451a03'], (2, 3)) + leaves(30, 5, 256, 230, 80, 40)))
    A['fried-rice'] = tile('#fefce8', '#fef08a', rice_mound(grain='#fef3c7', tint='#fde68a', seed=31, extra=dots(32, 50, 256, 245, 125, 60, ['#16a34a', '#f97316', '#fbbf24', '#22c55e', '#dc2626'], (5, 8)) + scatter(33, 14, 256, 240, 110, 50, lambda x, y, r: f'<rect x="{x - 8:.0f}" y="{y - 3:.0f}" width="16" height="6" rx="3" fill="#22c55e" transform="rotate({r.randint(0, 180)} {x:.0f} {y:.0f})"/>')))
    noodle = ''.join(f'<path d="M{150 + i * 10},{240 + (i % 3) * 8} q30,-50 60,0 t60,0 t60,0 t40,-10" stroke="{["#fcd34d", "#fbbf24", "#f59e0b"][i % 3]}" stroke-width="8" fill="none" stroke-linecap="round"/>' for i in range(12))
    A['noodles'] = tile('#fff7ed', '#fed7aa', bowl(sauce='#fde68a', rim='#1f2937', outer='#111827') + noodle + dots(34, 20, 256, 245, 110, 30, ['#16a34a', '#f97316', '#dc2626'], (4, 7)) + '<line x1="320" y1="120" x2="230" y2="250" stroke="#a16207" stroke-width="9" stroke-linecap="round"/><line x1="345" y1="125" x2="250" y2="252" stroke="#a16207" stroke-width="9" stroke-linecap="round"/>')
    A['indo-chinese'] = tile('#fef2f2', '#fecaca', bowl(sauce='#991b1b', rim='#1f2937', outer='#111827') + pieces_blobs(35, '#b45309', '#7c2d12', 9, 24) + scatter(36, 16, 256, 250, 110, 30, lambda x, y, r: f'<rect x="{x - 9:.0f}" y="{y - 4:.0f}" width="18" height="8" rx="4" fill="{r.choice(["#22c55e", "#16a34a", "#ef4444"])}" transform="rotate({r.randint(0, 180)} {x:.0f} {y:.0f})"/>') + '<ellipse cx="220" cy="236" rx="60" ry="8" fill="#fff" fill-opacity=".25"/>')
    momo = lambda x, y: f'<path d="M{x - 44},{y + 18} Q{x - 46},{y - 34} {x},{y - 38} Q{x + 46},{y - 34} {x + 44},{y + 18} Q{x},{y + 34} {x - 44},{y + 18} Z" fill="#fffbeb" stroke="#e7e5e4" stroke-width="3"/>' + ''.join(f'<path d="M{x},{y - 36} q{d},20 {d * 2.2},44" stroke="#e7e5e4" stroke-width="3" fill="none"/>' for d in (-14, -5, 5, 14))
    A['momos'] = tile('#f0fdf4', '#bbf7d0', plate() + momo(190, 250) + momo(290, 235) + momo(240, 300) + momo(335, 300) + '<ellipse cx="380" cy="215" rx="34" ry="20" fill="#dc2626"/><ellipse cx="380" cy="215" rx="28" ry="15" fill="#ef4444"/>')
    roll = lambda x, y, rot: f'<g transform="rotate({rot} {x} {y})"><rect x="{x - 80}" y="{y - 22}" width="160" height="44" rx="22" fill="#f59e0b"/><rect x="{x - 70}" y="{y - 16}" width="140" height="10" rx="5" fill="#fde68a" fill-opacity=".6"/><ellipse cx="{x + 78}" cy="{y}" rx="14" ry="22" fill="#fde68a"/><circle cx="{x + 78}" cy="{y}" r="9" fill="#16a34a"/></g>'
    A['spring-roll'] = tile('#fffbeb', '#fde68a', plate() + roll(230, 230, -12) + roll(270, 280, 6) + roll(225, 325, -4) + '<ellipse cx="385" cy="320" rx="34" ry="20" fill="#b91c1c"/>')
    A['dosa'] = tile('#fefce8', '#fde68a', plate(r=205) + '<path d="M70,300 Q256,190 442,250 L430,280 Q256,240 80,330 Z" fill="#d97706"/><path d="M80,300 Q256,205 430,252" stroke="#fbbf24" stroke-width="16" fill="none"/>' + char_marks(37, 18, 256, 265, 150, 25) + '<ellipse cx="160" cy="350" rx="46" ry="20" fill="#e2e8f0"/><ellipse cx="160" cy="346" rx="38" ry="14" fill="#f8fafc"/><ellipse cx="350" cy="350" rx="46" ry="20" fill="#e2e8f0"/><ellipse cx="350" cy="346" rx="38" ry="14" fill="#ea7a2c"/>')
    idli = lambda x, y: f'<ellipse cx="{x}" cy="{y}" rx="52" ry="30" fill="#fafaf9" stroke="#e7e5e4" stroke-width="3"/><ellipse cx="{x - 10}" cy="{y - 8}" rx="28" ry="9" fill="#fff"/>'
    A['idli'] = tile('#f0fdf4', '#bbf7d0', plate() + idli(195, 255) + idli(300, 245) + idli(245, 300) + '<ellipse cx="370" cy="310" rx="46" ry="22" fill="#e2e8f0"/><ellipse cx="370" cy="306" rx="38" ry="15" fill="#ea7a2c"/><ellipse cx="150" cy="320" rx="38" ry="18" fill="#e2e8f0"/><ellipse cx="150" cy="316" rx="30" ry="12" fill="#f8fafc"/>' + dots(38, 6, 370, 305, 25, 8, ['#facc15', '#16a34a'], (3, 5)))
    A['naan'] = tile('#fff7ed', '#fed7aa', plate() + '<path d="M120,300 Q110,190 250,190 Q400,200 400,260 Q390,330 250,330 Q150,335 120,300 Z" fill="#f5d19a" stroke="#c2410c" stroke-opacity=".3" stroke-width="4"/>' + scatter(39, 30, 255, 260, 120, 55, lambda x, y, r: f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{r.randint(6, 13)}" ry="{r.randint(4, 7)}" fill="#a16207" fill-opacity="{r.uniform(.3, .7):.2f}"/>') + dots(40, 10, 255, 255, 110, 45, ['#fde68a'], (6, 9)))
    A['roti'] = tile('#fefce8', '#fde68a', plate() + flatbread(240, 270, 140, 85, '#e8c07d', '#92400e', 41, 0) + flatbread(270, 248, 130, 78, '#efcb8c', '#92400e', 42, 0))
    A['paratha'] = tile('#fff7ed', '#fdba74', plate() + flatbread(250, 265, 150, 90, '#e9a94f', '#7c2d12', 43, 0, 30) + ''.join(f'<ellipse cx="250" cy="265" rx="{150 - i * 28}" ry="{90 - i * 17}" fill="none" stroke="#b45309" stroke-opacity=".35" stroke-width="3"/>' for i in range(1, 5)) + '<rect x="230" y="235" width="40" height="26" rx="4" fill="#fef9c3"/>')
    puri = lambda x, y, r: f'<ellipse cx="{x}" cy="{y}" rx="{r}" ry="{r * .7}" fill="#f2b45c" stroke="#b45309" stroke-opacity=".4" stroke-width="3"/><ellipse cx="{x - r * .25}" cy="{y - r * .25}" rx="{r * .45}" ry="{r * .2}" fill="#fde68a" fill-opacity=".7"/>'
    A['puri'] = tile('#fff7ed', '#fed7aa', plate() + puri(200, 240, 78) + puri(300, 230, 70) + '<ellipse cx="290" cy="320" rx="70" ry="28" fill="#e2e8f0"/><ellipse cx="290" cy="316" rx="60" ry="20" fill="#b45309"/>' + dots(44, 18, 290, 314, 50, 12, ['#d6a35c', '#e0b574'], (5, 7)) + leaves(45, 4, 290, 312, 40, 10))
    tri = lambda x, y, rot: f'<g transform="rotate({rot} {x} {y})"><path d="M{x},{y - 70} L{x + 70},{y + 45} Q{x},{y + 62} {x - 70},{y + 45} Z" fill="#e9a94f" stroke="#b45309" stroke-width="4" stroke-linejoin="round"/>' + ''.join(f'<circle cx="{x + dx}" cy="{y + dy}" r="4" fill="#b45309" fill-opacity=".5"/>' for dx, dy in ((-10, 0), (14, 18), (-24, 30), (20, -20))) + '</g>'
    A['samosa'] = tile('#fff7ed', '#fdba74', plate() + tri(200, 255, -10) + tri(310, 255, 12) + '<ellipse cx="255" cy="335" rx="40" ry="16" fill="#16a34a"/><ellipse cx="350" cy="340" rx="30" ry="13" fill="#7c2d12"/>')
    A['pakora'] = tile('#fefce8', '#fde68a', plate() + scatter(46, 11, 256, 265, 130, 55, lambda x, y, r: f'<path d="M{x - 34:.0f},{y:.0f} q8,-30 34,-28 q30,-4 34,26 q-6,26 -34,24 q-30,4 -34,-22 z" fill="{r.choice(["#d97706", "#ca8a04", "#b45309"])}"/>' + ''.join(f'<circle cx="{x + r.randint(-20, 20):.0f}" cy="{y + r.randint(-14, 10):.0f}" r="4" fill="#fde68a" fill-opacity=".8"/>' for _ in range(4))) + leaves(47, 6, 256, 270, 130, 50))
    pp = lambda x, y: f'<ellipse cx="{x}" cy="{y}" rx="34" ry="24" fill="#f2b45c" stroke="#b45309" stroke-opacity=".4" stroke-width="3"/><ellipse cx="{x}" cy="{y - 6}" rx="18" ry="9" fill="#78350f"/>'
    A['chaat'] = tile('#fdf4ff', '#f5d0fe', plate() + ''.join(pp(x, y) for x, y in ((190, 230), (256, 220), (322, 230), (220, 285), (292, 285))) + dots(48, 40, 256, 255, 120, 55, ['#facc15', '#16a34a', '#fef3c7', '#dc2626'], (2, 4)) + '<path d="M180,255 q40,20 80,0 t80,0" stroke="#fff" stroke-width="6" fill="none" opacity=".85"/>')
    bun = lambda x, y: f'<ellipse cx="{x}" cy="{y}" rx="52" ry="34" fill="#f2b45c"/><ellipse cx="{x}" cy="{y - 6}" rx="44" ry="22" fill="#f8c879"/><ellipse cx="{x - 14}" cy="{y - 14}" rx="14" ry="6" fill="#fff" fill-opacity=".35"/>'
    A['pav-bhaji'] = tile('#fff7ed', '#fdba74', plate() + '<ellipse cx="300" cy="260" rx="110" ry="58" fill="#e2e8f0"/><ellipse cx="300" cy="256" rx="96" ry="46" fill="#d9480f"/>' + dots(49, 28, 300, 254, 80, 34, ['#16a34a', '#fde68a', '#fff7ed'], (3, 6)) + '<rect x="285" y="228" width="30" height="20" rx="3" fill="#fef9c3"/>' + bun(160, 250) + bun(180, 310))
    A['pizza'] = tile('#fef2f2', '#fecaca', plate(r=200) + '<circle cx="256" cy="262" r="150" fill="#f2b45c"/><circle cx="256" cy="262" r="128" fill="#dc2626"/><circle cx="256" cy="262" r="120" fill="#fde68a"/>' + dots(50, 14, 256, 262, 105, 105, ['#dc2626', '#b91c1c'], (12, 16)) + leaves(51, 14, 256, 262, 105, 105, '#15803d') + ''.join(f'<line x1="256" y1="262" x2="{256 + 150 * math.cos(a):.0f}" y2="{262 + 150 * math.sin(a):.0f}" stroke="#b45309" stroke-opacity=".45" stroke-width="3"/>' for a in [i * math.tau / 6 for i in range(6)]))
    A['burger'] = tile('#fff7ed', '#fdba74', shadow(256, 400, 170, 30) + '<path d="M110,330 h292 q0,40 -40,44 h-212 q-40,-4 -40,-44 z" fill="#d97706"/><rect x="100" y="300" width="312" height="32" rx="14" fill="#7c2d12"/><path d="M96,296 h320 l-18,22 h-284 z" fill="#facc15"/><path d="M100,282 q40,22 80,0 t80,0 t80,0 t70,0 v12 h-310 z" fill="#22c55e"/><rect x="118" y="262" width="276" height="18" rx="9" fill="#ef4444"/><path d="M112,262 Q120,140 256,136 Q392,140 400,262 Z" fill="#f59e0b"/>' + dots(52, 16, 256, 190, 110, 40, ['#fef3c7'], (3, 4)))
    A['sandwich'] = tile('#fefce8', '#fef08a', plate() + '<path d="M120,320 L250,160 L250,320 Z" fill="#fde68a" stroke="#d97706" stroke-width="10" stroke-linejoin="round"/><path d="M262,320 L262,160 L392,320 Z" fill="#fde68a" stroke="#d97706" stroke-width="10" stroke-linejoin="round"/><path d="M140,300 L240,180" stroke="#22c55e" stroke-width="10"/><path d="M372,300 L272,180" stroke="#ef4444" stroke-width="10"/><path d="M150,312 L245,198" stroke="#facc15" stroke-width="6"/>' + char_marks(53, 10, 256, 260, 100, 40))
    fry = ''.join(f'<rect x="{170 + i * 18}" y="{120 + (i * 37) % 50}" width="16" height="150" rx="5" fill="{["#facc15", "#fbbf24", "#fde047"][i % 3]}" transform="rotate({(i - 5) * 3} {178 + i * 18} 260)"/>' for i in range(10))
    A['fries'] = tile('#fef2f2', '#fecaca', shadow(256, 410, 140, 26) + fry + '<path d="M150,230 L362,230 L340,400 L172,400 Z" fill="#dc2626"/><path d="M150,230 q106,40 212,0" fill="#b91c1c"/><circle cx="256" cy="320" r="34" fill="#fef2f2"/><path d="M240,320 l12,12 l20,-24" stroke="#dc2626" stroke-width="8" fill="none"/>')
    A['pasta'] = tile('#fff7ed', '#fed7aa', bowl(sauce='#fde68a', rim='#e2e8f0', outer='#cbd5e1') + scatter(54, 26, 256, 248, 105, 28, lambda x, y, r: f'<rect x="{x - 16:.0f}" y="{y - 6:.0f}" width="32" height="12" rx="5" fill="{r.choice(["#fcd34d", "#fbbf24"])}" stroke="#d97706" stroke-width="2" transform="rotate({r.randint(-60, 60)} {x:.0f} {y:.0f})"/>') + leaves(55, 8, 256, 245, 100, 26, '#15803d') + dots(56, 10, 256, 248, 100, 26, ['#dc2626'], (5, 7)))
    A['soup'] = tile('#fef2f2', '#fecaca', bowl(sauce='#dc2626', rim='#f1f5f9', outer='#e2e8f0') + '<path d="M190,248 q30,-10 60,0 t60,0" stroke="#fff7ed" stroke-width="7" fill="none" stroke-linecap="round"/>' + leaves(57, 6, 256, 248, 90, 22) + '<path d="M370,170 L300,250" stroke="#94a3b8" stroke-width="12" stroke-linecap="round"/><ellipse cx="292" cy="256" rx="22" ry="12" fill="#cbd5e1"/>')
    A['salad'] = tile('#f0fdf4', '#bbf7d0', bowl(sauce='#16a34a', rim='#f8fafc', outer='#e2e8f0') + scatter(58, 18, 256, 240, 110, 32, lambda x, y, r: f'<path d="M{x - 26:.0f},{y:.0f} q26,-30 52,0 q-26,16 -52,0 z" fill="{r.choice(["#22c55e", "#4ade80", "#15803d"])}" transform="rotate({r.randint(-40, 40)} {x:.0f} {y:.0f})"/>') + dots(59, 10, 256, 240, 100, 26, ['#ef4444', '#f97316'], (10, 13)) + scatter(60, 6, 256, 240, 100, 26, lambda x, y, r: f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="14" ry="10" fill="#f0fdf4" stroke="#86efac" stroke-width="3"/>'))
    katori = lambda x, y, c: f'<ellipse cx="{x}" cy="{y}" rx="46" ry="22" fill="#cbd5e1"/><ellipse cx="{x}" cy="{y - 2}" rx="38" ry="16" fill="{c}"/>'
    A['thali'] = tile('#fefce8', '#fde68a', shadow(256, 330, 220, 80) + '<ellipse cx="256" cy="270" rx="220" ry="135" fill="#cbd5e1"/><ellipse cx="256" cy="268" rx="204" ry="122" fill="#e2e8f0"/>' + katori(150, 215, '#eab308') + katori(235, 190, '#ea7a2c') + katori(325, 200, '#f8fafc') + katori(385, 255, '#9a3412') + flatbread(175, 300, 70, 40, '#e8c07d', '#92400e', 61, -10, 12) + '<path d="M250,280 q40,-40 90,-6 q20,40 -30,50 q-60,6 -60,-44 z" fill="#fff7d6"/>' + dots(62, 10, 300, 300, 30, 14, ['#16a34a'], (3, 4)))
    A['raita'] = tile('#f8fafc', '#e2e8f0', bowl(sauce='#f8fafc', rim='#e2e8f0', outer='#94a3b8') + dots(63, 30, 256, 250, 105, 28, ['#fbbf24', '#d97706'], (5, 7)) + leaves(64, 8, 256, 250, 100, 26) + dots(65, 20, 256, 250, 105, 28, ['#b91c1c'], (2, 3)))
    A['papad'] = tile('#fffbeb', '#fde68a', plate() + '<circle cx="256" cy="262" r="140" fill="#f5deb3" stroke="#d6b88a" stroke-width="5"/>' + dots(66, 60, 256, 262, 125, 125, ['#a16207', '#78350f'], (2, 4)) + dots(67, 30, 256, 262, 100, 100, ['#ef4444', '#16a34a', '#fde68a'], (4, 7)))
    A['tea'] = tile('#fff7ed', '#fed7aa', cup('#c08552'))
    A['coffee-hot'] = tile('#fefce8', '#fde68a', cup('#6b3a1e', art='<path d="M256,256 c-30,-26 -44,-6 -30,8 l30,16 l30,-16 c14,-14 0,-34 -30,-8 z" fill="#f5deb3"/>'))
    A['coffee-cold'] = tile('#f5f5f4', '#d6d3d1', glass('#8b5a2b', '#a47148', ice=True, straw='#1f2937', foam='#fef3c7'))
    A['lassi'] = tile('#fefce8', '#fde68a', glass('#fef9c3', '#fffbeb', foam='#ffffff', garnish=dots(68, 8, 256, 108, 40, 10, ['#16a34a', '#f59e0b'], (3, 5))))
    A['shake'] = tile('#fdf2f8', '#fbcfe8', glass('#7c4a2d', '#8b5a3c', straw='#ec4899', foam='#fff7ed', garnish='<circle cx="270" cy="70" r="16" fill="#dc2626"/><path d="M270,56 q8,-16 18,-12" stroke="#15803d" stroke-width="4" fill="none"/>'))
    A['juice'] = tile('#fff7ed', '#fdba74', glass('#fb923c', '#fdba74', ice=True, straw='#16a34a', garnish='<circle cx="196" cy="150" r="40" fill="#facc15" stroke="#eab308" stroke-width="6"/><path d="M196,112 v76 M158,150 h76" stroke="#fde68a" stroke-width="4"/>'))
    A['soft-drink'] = tile('#fef2f2', '#fecaca', glass('#3f1d0b', '#5a2a12', ice=True, straw='#dc2626', garnish=dots(69, 20, 256, 300, 40, 110, ['#ffffff'], (2, 4))))
    A['water'] = tile('#eff6ff', '#bfdbfe', shadow(256, 440, 100, 22) + '<rect x="196" y="140" width="120" height="300" rx="34" fill="#dbeafe" fill-opacity=".8" stroke="#93c5fd" stroke-width="4"/><rect x="226" y="90" width="60" height="56" rx="10" fill="#93c5fd"/><rect x="220" y="80" width="72" height="22" rx="6" fill="#2563eb"/><rect x="196" y="230" width="120" height="80" fill="#2563eb"/><path d="M256,250 q-16,22 0,40 q16,-18 0,-40 z" fill="#fff"/><path d="M212,160 v260" stroke="#fff" stroke-opacity=".6" stroke-width="10" stroke-linecap="round"/>')
    A['ice-cream'] = tile('#fdf2f8', '#fbcfe8', bowl(sauce='#fdf2f8', rim='#f8fafc', outer='#e2e8f0', cy=300) + '<circle cx="210" cy="250" r="56" fill="#fef3c7"/><circle cx="300" cy="250" r="56" fill="#f9a8d4"/><circle cx="256" cy="200" r="56" fill="#7c4a2d"/><path d="M220,190 q20,30 40,0 q20,30 36,4" stroke="#3f1d0b" stroke-width="10" fill="none" stroke-linecap="round"/><circle cx="256" cy="140" r="14" fill="#dc2626"/>' + dots(70, 16, 256, 230, 90, 50, ['#22c55e', '#f59e0b', '#3b82f6', '#ec4899'], (3, 4)))
    A['indian-sweet'] = tile('#fff7ed', '#fdba74', bowl(sauce='#d97706', rim='#e2e8f0', outer='#94a3b8') + ''.join(f'<circle cx="{x}" cy="{y}" r="36" fill="#7c2d12"/><ellipse cx="{x - 10}" cy="{y - 12}" rx="14" ry="7" fill="#fff" fill-opacity=".35"/>' for x, y in ((205, 238), (275, 230), (240, 262), (310, 258))) + dots(71, 8, 256, 240, 80, 20, ['#a3e635', '#fef3c7'], (3, 4)))
    A['cake'] = tile('#fdf2f8', '#fbcfe8', plate() + '<path d="M150,300 L330,330 L380,250 L200,220 Z" fill="#fde68a"/><path d="M150,300 L150,240 L200,160 L200,220 Z" fill="#7c4a2d"/><path d="M150,240 L330,270 L380,190 L200,160 Z" fill="#4a2511"/><path d="M150,300 L330,330 L330,270 L150,240 Z" fill="#7c4a2d"/><path d="M150,272 L330,302" stroke="#fef3c7" stroke-width="10"/><path d="M330,330 L380,250 L380,190 L330,270 Z" fill="#5b2e14"/><circle cx="290" cy="200" r="18" fill="#dc2626"/><path d="M300,186 q10,-20 24,-16" stroke="#15803d" stroke-width="4" fill="none"/>')

    # ---------- category placeholders: soft, line-drawn, clearly "not a photo" ----------
    def ph(bg1, bg2, glyph):
        return tile(bg1, bg2, f'<circle cx="256" cy="246" r="150" fill="#fff" fill-opacity=".55"/><g fill="none" stroke="#475569" stroke-width="12" stroke-linecap="round" stroke-linejoin="round" opacity=".8">{glyph}</g>')
    A['cat-starter'] = ph('#fff7ed', '#fed7aa', '<line x1="150" y1="320" x2="370" y2="170"/><rect x="180" y="250" width="46" height="46" rx="8"/><rect x="246" y="206" width="46" height="46" rx="8"/><rect x="312" y="164" width="40" height="40" rx="8"/>')
    A['cat-main'] = ph('#fefce8', '#fde68a', '<path d="M140,240 h232 q-10,90 -116,96 q-106,-6 -116,-96 z"/><path d="M200,200 q10,-30 0,-50 M256,200 q10,-30 0,-50 M312,200 q10,-30 0,-50"/>')
    A['cat-bread'] = ph('#fff7ed', '#fdba74', '<path d="M150,300 Q140,180 260,180 Q380,190 375,250 Q370,320 260,320 Q170,326 150,300 Z"/><path d="M210,240 h20 M270,220 h20 M300,270 h20 M230,285 h20"/>')
    A['cat-rice'] = ph('#f8fafc', '#e2e8f0', '<path d="M130,300 h252"/><path d="M150,300 Q170,170 256,170 Q342,170 362,300"/><path d="M220,230 l14,-6 M270,210 l14,6 M300,250 l14,-6 M230,270 l14,6"/>')
    A['cat-chinese'] = ph('#fef2f2', '#fecaca', '<path d="M140,250 h232 q-10,90 -116,96 q-106,-6 -116,-96 z"/><line x1="330" y1="130" x2="250" y2="240"/><line x1="370" y1="140" x2="280" y2="242"/>')
    A['cat-south'] = ph('#f0fdf4', '#bbf7d0', '<path d="M120,300 Q256,200 392,250"/><path d="M130,320 Q256,230 380,272"/><ellipse cx="200" cy="340" rx="40" ry="16"/>')
    A['cat-snacks'] = ph('#fff7ed', '#fdba74', '<path d="M256,170 L340,310 Q256,330 172,310 Z"/><path d="M230,260 h10 M270,280 h10"/>')
    A['cat-beverage'] = ph('#eff6ff', '#bfdbfe', '<path d="M196,170 L212,350 h88 L316,170 Z"/><path d="M196,220 h120"/><path d="M280,170 L300,120 L330,110"/>')
    A['cat-dessert'] = ph('#fdf2f8', '#fbcfe8', '<path d="M190,260 h132 l-20,90 h-92 z"/><path d="M180,260 q-10,-60 40,-70 q20,-50 72,-20 q60,0 40,90"/><circle cx="256" cy="150" r="10"/>')
    A['cat-fastfood'] = ph('#fefce8', '#fef08a', '<path d="M150,250 Q160,160 256,160 Q352,160 362,250 Z"/><path d="M146,276 h220"/><path d="M156,302 h200 q0,36 -30,40 h-140 q-30,-4 -30,-40 z"/>')
    A['cat-soup'] = ph('#f0fdf4', '#bbf7d0', '<path d="M140,250 h232 q-10,90 -116,96 q-106,-6 -116,-96 z"/><path d="M350,150 L290,230"/><path d="M200,210 q10,-25 0,-45 M240,210 q10,-25 0,-45"/>')
    A['cat-generic'] = ph('#f1f5f9', '#cbd5e1', '<path d="M150,300 Q150,190 256,190 Q362,190 362,300 Z"/><path d="M130,300 h252"/><circle cx="256" cy="176" r="12"/><path d="M110,200 v60 M96,200 v26 q14,14 28,0 v-26 M410,200 v100 M410,200 q-24,20 0,50"/>')
    return A


if __name__ == '__main__':
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    art = ART()
    for k, v in art.items():
        with open(os.path.join(out, k + '.svg'), 'w', encoding='utf-8') as f:
            f.write(v)
    print(len(art), 'svg files')
