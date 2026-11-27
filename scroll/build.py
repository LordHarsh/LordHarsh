#!/usr/bin/env python3
"""Draws the pictures this profile is made of.

    python scroll/build.py          everything (needs Pillow and fonttools, and the paintings in scroll/src)
    python scroll/build.py year     only the year of contributions (needs fonttools; this is what the daily Action runs)

Every word in the pictures is drawn as an outline from Baskervville (scroll/fonts, OFL), so nothing depends on the
fonts a visitor has. The paintings are placed inside the SVGs as data, because an SVG shown as an image may not load
anything from outside itself. Each picture is made twice, for light and for dark pages.
"""
import base64, datetime, io, json, os, random, subprocess, sys, urllib.request

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, 'assets')
SRC = os.path.join(HERE, 'src')
USER = 'LordHarsh'

# ---------------------------------------------------------------- the two papers
THEMES = {
    'light': dict(paper=(236, 226, 205), ink='#2b2622', soft='#544b41', faint='#6e6456', red='#b5342a', seal_ink='#f3ead6',
                  slip='#f1e8d5', slip_edge='#cdbf9f', line='#3a332c'),
    'dark': dict(paper=(22, 25, 41), ink='#e9e3d3', soft='#d8d1c1', faint='#b4ae9f', red='#cf4a3c', seal_ink='#f6eedc',
                 slip='#1f2337', slip_edge='#3a4060', line='#c9c2b0'),
}

# ---------------------------------------------------------------- words, as outlines
class Face:
    def __init__(self, name):
        self.f = TTFont(os.path.join(HERE, 'fonts', name))
        self.gs = self.f.getGlyphSet()
        self.cmap = self.f.getBestCmap()
        self.upm = self.f['head'].unitsPerEm
        self.adv = self.f['hmtx']

    def _glyphs(self, text):
        return [self.cmap.get(ord(ch), '.notdef') for ch in text]

    def width(self, text, size, track=0):
        s = size / self.upm
        return sum(self.adv[g][0] * s + track for g in self._glyphs(text)) - (track if text else 0)

    def d(self, text, size, x, y, anchor='start', track=0):
        """The outline of `text`, its baseline starting (or centred, or ending) at x, y."""
        s = size / self.upm
        w = self.width(text, size, track)
        if anchor == 'middle': x -= w / 2
        elif anchor == 'end': x -= w
        pen = SVGPathPen(self.gs, ntos=lambda v: ('%.1f' % v).rstrip('0').rstrip('.'))
        for g in self._glyphs(text):
            self.gs[g].draw(TransformPen(pen, (s, 0, 0, -s, x, y)))
            x += self.adv[g][0] * s + track
        return pen.getCommands()

    def wrap(self, text, size, maxw, track=0):
        lines, cur = [], ''
        for word in text.split():
            trial = (cur + ' ' + word).strip()
            if cur and self.width(trial, size, track) > maxw:
                lines.append(cur); cur = word
            else:
                cur = trial
        if cur: lines.append(cur)
        return lines


_faces = {}
def face(italic=False):
    k = 'Baskervville-Italic.ttf' if italic else 'Baskervville-Regular.ttf'
    if k not in _faces: _faces[k] = Face(k)
    return _faces[k]

_glyphs = {}     # the letters one picture uses: each is drawn once and then placed wherever it is needed

def words(text, size, x, y, fill, anchor='start', track=0, italic=False, extra=''):
    f = face(italic)
    s = size / f.upm
    w = f.width(text, size, track)
    if anchor == 'middle': x -= w / 2
    elif anchor == 'end': x -= w
    out = []
    for g in f._glyphs(text):
        if g != 'space':
            key = ('i' if italic else 'r', g)
            if key not in _glyphs:
                pen = SVGPathPen(f.gs, ntos=lambda v: str(int(round(v))))
                f.gs[g].draw(pen)
                _glyphs[key] = ('%s%d' % (key[0], len(_glyphs)), pen.getCommands())
            out.append(f'<use href="#{_glyphs[key][0]}" transform="matrix({s:.4f} 0 0 {-s:.4f} {x:.2f} {y:.2f})"/>')
        x += f.adv[g][0] * s + track
    return f'<g fill="{fill}"{extra}>{"".join(out)}</g>'

def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('"', '&quot;')

def save(name, svg):
    os.makedirs(OUT, exist_ok=True)
    if _glyphs:
        letters = '<defs>' + ''.join(f'<path id="{i}" d="{d}"/>' for i, d in _glyphs.values()) + '</defs>'
        cut = svg.index('</title>') + 8
        svg = svg[:cut] + letters + svg[cut:]
        _glyphs.clear()
    with open(os.path.join(OUT, name), 'w', encoding='utf-8', newline='\n') as f:
        f.write(svg)
    print(f'{name:28s} {len(svg) / 1024:7.0f} KB')

def svg_open(w, h, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-label="{esc(title)}"><title>{esc(title)}</title>')

# ---------------------------------------------------------------- pictures, as data
def uri(img, quality=82, lossless=False):
    buf = io.BytesIO()
    img.save(buf, 'WEBP', quality=quality, lossless=lossless, method=6)
    return 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode()

def grain(size, seed, strength, slow=True):
    """Paper tooth: fine grain over slow mottling, as a grey image centred on 128."""
    from PIL import Image, ImageFilter
    import numpy as np
    rng = np.random.default_rng(seed)
    w, h = size
    fine = rng.normal(0, 1, (h, w))
    coarse = Image.fromarray((rng.normal(0, 1, (h // 160 + 3, w // 160 + 3)) * 40 + 128).clip(0, 255).astype('uint8')).resize((w, h), Image.BICUBIC)
    fibre = Image.fromarray((rng.normal(0, 1, (h // 2, w // 14 + 2)) * 40 + 128).clip(0, 255).astype('uint8')).resize((w, h), Image.BICUBIC)
    if not slow: return fine * strength
    a = fine * strength + (np.asarray(coarse, dtype=float) - 128) * strength * .035 + (np.asarray(fibre, dtype=float) - 128) * strength * .03
    return a

def paper_image(size, theme, seed=7, strength=3.2):
    from PIL import Image
    import numpy as np
    w, h = size
    base = np.array(THEMES[theme]['paper'], dtype=float)
    a = grain(size, seed, strength if theme == 'light' else strength * .7)
    arr = base[None, None, :] + a[:, :, None]
    return Image.fromarray(arr.clip(0, 255).astype('uint8'), 'RGB')

# ---------------------------------------------------------------- the hero
W, H = 1200, 600
BS = .56                       # the bough's scale on the sheet
BX, BY = 749, -30              # where its top left corner sits
BOUGH = dict(w=787, h=1170, seat=(385, 474), joint=(545, 482), part=(0, 215, 522, 400))
REL = .74                      # the bird beside the bough (as on the site)
# x, y, w, h on the sheet, then the eye and the feet inside the frame (from engine/messenger.js of the site)
FR = {
    'f1': [0, 0, 279, 238, 233.1, 151.8, 141.5, 234], 'f2': [281, 0, 281, 188, 232.6, 23.2, 159, 184], 'f3': [564, 0, 283, 193, 234.2, 23.1, 152.5, 189],
    'f4': [849, 0, 277, 167, 226.6, 80, 141, 163], 'f5': [1128, 0, 281, 205, 233.3, 107, 88, 201],
    'p1': [856, 240, 267, 211, 212.8, 26.2, 139, 207], 'p2': [1125, 240, 251, 223, 201.6, 23.5, 137.5, 217], 'p3': [0, 485, 223, 214, 148.5, 26.3, 139, 212],
    'p4': [225, 485, 226, 216, 182, 34, 133, 212], 'p5': [453, 485, 225, 228, 162, 36, 132, 226], 'p6': [680, 485, 259, 224, 203.6, 25.4, 140.5, 216],
    'p8': [0, 722, 258, 198, 206.1, 44.7, 163.5, 194],
    'l1': [260, 722, 289, 267, 239.2, 93.6, 153.5, 263], 'l2': [551, 722, 268, 285, 221.7, 144.1, 167.5, 281], 'l3': [821, 722, 271, 218, 217.1, 52.7, 140.5, 216],
    'l4': [1094, 722, 281, 172, 232, 25.3, 169, 168], 'l6': [264, 1009, 286, 144, 240.3, 30.3, 160, 140], 'l7': [552, 1009, 284, 304, 231.2, 140.8, 93.5, 300],
    'l8': [838, 1009, 282, 222, 235.5, 123.9, 141, 218],
}
FLAP = ['f1', 'f4', 'f2', 'f3', 'f5']
T = 38.0                       # one visit, in seconds
# what she does while she is there: the drawing, and for how long
IDLE = [('l4', .7), ('p1', 2.3), ('p3', 1.5), ('p1', 1.7), ('p2', 1.3), ('p1', .9), ('p4', 1.9), ('p5', 1.1), ('p4', .8), ('p1', 1.6),
        ('p6', .45), ('p1', .22), ('p6', .6), ('p1', .3), ('p6', .5), ('p1', 1.5), ('p8', 2.6), ('p1', 2.1), ('p3', 1.2), ('p1', 1.4)]
T_IN, T_NEAR, T_DOWN = 1.6, 4.3, 4.85      # she appears, she is over the bough, she has landed
T_UP = T_DOWN + sum(d for _, d in IDLE)    # she crouches to leave
T_GONE = T_UP + 3.6

def pct(t):
    return ('%.3f' % (t / T * 100)).rstrip('0').rstrip('.') + '%'

def shown(name, spans, period=None):
    """Keyframes that show something only inside the given spans of time (it steps, it does not fade)."""
    period = period or T
    pts = {0.0: 0}
    for a, b in spans:
        pts[round(a, 4)] = 1
        if b < period: pts[round(b, 4)] = 0
    body = ''.join(f"{('%.3f' % (t / period * 100)).rstrip('0').rstrip('.')}%{{opacity:{v}}}" for t, v in sorted(pts.items()))
    return f'@keyframes {name}{{{body}}}'

def hero_background(theme):
    """Paper, and the landscape washed over it in ink (its darkness becomes the ink's opacity)."""
    from PIL import Image, ImageFilter, ImageDraw
    import numpy as np
    S = 1.5
    w, h = int(W * S), int(H * S)
    img = paper_image((w, h), theme, seed=11).convert('RGBA')
    if theme == 'dark':
        # a night sky: a little lighter toward the moon
        yy, xx = np.mgrid[0:h, 0:w]
        mx, my = 560 * S, 118 * S
        glow = np.exp(-(((xx - mx) / (420 * S)) ** 2 + ((yy - my) / (300 * S)) ** 2))
        arr = np.asarray(img, dtype=float)
        arr[:, :, :3] += glow[:, :, None] * np.array([16, 19, 30])[None, None, :]
        arr[:, :, :3] *= (1 - .22 * (yy / h))[:, :, None]
        img = Image.fromarray(arr.clip(0, 255).astype('uint8'), 'RGBA')
    p = Image.open(os.path.join(SRC, 'dp-37464-002-l.webp')).convert('L')
    pw, ph = p.size
    p = p.crop((int(pw * .06), int(ph * .17), int(pw * .94), int(ph * .84)))
    tw = int(1010 * S); th = int(tw * p.size[1] / p.size[0])
    p = p.resize((tw, th), Image.LANCZOS)
    a = np.asarray(p, dtype=float)
    ground, deep = np.percentile(a, 80), np.percentile(a, 1.5)
    dark = ((ground - a) / (ground - deep)).clip(0, 1) ** .95
    # it fades out toward the foot and toward the bough
    yy, xx = np.mgrid[0:th, 0:tw]
    fy = (1 - ((yy / S - 196) / 176).clip(0, 1)) ** 1.3
    fx = (1 - ((xx / S - 640) / 330).clip(0, 1)) ** 1.2
    fl = ((xx / S) / 70).clip(0, 1)
    ft = ((yy / S) / 40).clip(0, 1)
    alpha = dark * fy * fx * fl * ft * (.78 if theme == 'light' else .86)
    ink = (58, 52, 46) if theme == 'light' else (6, 8, 16)
    wash = Image.new('RGBA', (tw, th), ink + (0,))
    wash.putalpha(Image.fromarray((alpha * 255).astype('uint8')))
    img.alpha_composite(wash, (int(-20 * S), int(6 * S)))
    if theme == 'dark':
        moon = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(moon)
        r = 30 * S
        d.ellipse((mx - r * 3.2, my - r * 3.2, mx + r * 3.2, my + r * 3.2), fill=(214, 220, 240, 34))
        moon = moon.filter(ImageFilter.GaussianBlur(40 * S))
        d = ImageDraw.Draw(moon)
        d.ellipse((mx - r, my - r, mx + r, my + r), fill=(230, 226, 208, 228))
        moon = moon.filter(ImageFilter.GaussianBlur(1.1 * S))
        img.alpha_composite(moon)
    return img.convert('RGB')

def mist_image(theme):
    from PIL import Image, ImageDraw, ImageFilter
    im = Image.new('RGBA', (640, 150), (0, 0, 0, 0))
    col = (247, 240, 225) if theme == 'light' else (70, 80, 118)
    d = ImageDraw.Draw(im)
    d.ellipse((90, 52, 550, 98), fill=col + (150 if theme == 'light' else 95,))
    d.ellipse((230, 42, 470, 86), fill=col + (120 if theme == 'light' else 70,))
    return im.filter(ImageFilter.GaussianBlur(26))

def hero(theme):
    from PIL import Image
    c = THEMES[theme]
    NS = 90                                  # the size of the name; the seal follows it
    SX = round(76 + face().width('Harsh Kumar Banka', NS, -.6) + 26); SY = 346
    bg = uri(hero_background(theme), quality=80)
    mist = uri(mist_image(theme), quality=70)
    bough = Image.open(os.path.join(SRC, 'bough-night-1.webp' if theme == 'dark' else 'bough-1.webp')).convert('RGBA')
    px, py, pw, ph = BOUGH['part']
    part = bough.crop((px, py, px + pw, py + ph))
    rest = bough.copy(); rest.paste((0, 0, 0, 0), (px, py, px + pw, py + ph))
    sheet = Image.open(os.path.join(SRC, 'kotori-1.webp')).convert('RGBA')

    def frame(k, eye_at=None):
        x, y, w, h, ex, ey, fx, fy = FR[k]
        im = sheet.crop((x, y, x + w, y + h))
        im = im.resize((round(w * .8), round(h * .8)), Image.LANCZOS)
        ox, oy = (-fx, -fy) if eye_at is None else (eye_at[0] - ex, eye_at[1] - ey)
        return f'<image class="k {k}" href="{uri(im, 84)}" x="{ox:.1f}" y="{oy:.1f}" width="{w}" height="{h}"/>'

    # in the air her eye is what keeps still; it is put where it is in the first drawing of the landing
    l1 = FR['l1']; eye = (l1[4] - l1[6], l1[5] - l1[7])
    seat = (BX + BOUGH['seat'][0] * BS, BY + BOUGH['seat'][1] * BS)
    joint = (BX + BOUGH['joint'][0] * BS, BY + BOUGH['joint'][1] * BS)
    bs = REL * BS

    # ---- the times of the visit
    spans = {}
    t = T_DOWN
    for k, dur in IDLE:
        spans.setdefault(k, []).append((t, t + dur)); t += dur
    spans.setdefault('l1', []).append((T_NEAR, T_NEAR + .16))
    spans.setdefault('l2', []).append((T_NEAR + .16, T_NEAR + .34))
    spans.setdefault('l3', []).append((T_NEAR + .34, T_DOWN))
    spans.setdefault('l6', []).append((T_UP, T_UP + .22))
    spans.setdefault('l7', []).append((T_UP + .22, T_UP + .4))
    spans.setdefault('l8', []).append((T_UP + .4, T_UP + .58))
    fly = [(T_IN, T_NEAR), (T_UP + .58, T_GONE)]
    css = [shown('v_' + k, v) for k, v in spans.items()]
    css.append(shown('v_fly', fly))
    beat = .44
    for i, k in enumerate(FLAP):
        css.append(shown('w_' + k, [(i * beat / 5, (i + 1) * beat / 5)], beat))
    css.append(
        f"@keyframes bx{{0%,{pct(T_IN)}{{transform:translateX(-1090px);animation-timing-function:cubic-bezier(.22,.55,.3,1)}}"
        f"{pct(T_NEAR + .3)},{pct(T_UP + .2)}{{transform:translateX(0);animation-timing-function:cubic-bezier(.5,0,.85,.6)}}"
        f"{pct(T_GONE)},100%{{transform:translateX(330px)}}}}")
    css.append(
        f"@keyframes by{{0%,{pct(T_IN)}{{transform:translateY(-120px);animation-timing-function:ease-in-out}}"
        f"{pct(T_IN + 1.75)}{{transform:translateY(44px);animation-timing-function:ease-out}}"
        f"{pct(T_NEAR)}{{transform:translateY(-22px);animation-timing-function:ease-in}}"
        f"{pct(T_DOWN - .08)},{pct(T_UP + .2)}{{transform:translateY(0);animation-timing-function:ease-out}}"
        f"{pct(T_UP + .6)}{{transform:translateY(-46px);animation-timing-function:linear}}"
        f"{pct(T_GONE)},100%{{transform:translateY(-360px)}}}}")
    # the bough gives under her and springs back; the same when she pushes off
    a, b = T_DOWN - .1, T_UP + .2
    css.append(
        f"@keyframes sway{{0%,{pct(a)}{{transform:rotate(0deg);animation-timing-function:ease-out}}"
        f"{pct(a + .2)}{{transform:rotate(-2deg);animation-timing-function:ease-in-out}}"
        f"{pct(a + .62)}{{transform:rotate(.75deg);animation-timing-function:ease-in-out}}"
        f"{pct(a + 1.1)}{{transform:rotate(-.4deg);animation-timing-function:ease-in-out}}"
        f"{pct(a + 1.7)}{{transform:rotate(.15deg);animation-timing-function:ease-in-out}}"
        f"{pct(a + 2.4)},{pct(b)}{{transform:rotate(0deg);animation-timing-function:ease-out}}"
        f"{pct(b + .12)}{{transform:rotate(-1.5deg);animation-timing-function:ease-in-out}}"
        f"{pct(b + .5)}{{transform:rotate(1.1deg);animation-timing-function:ease-in-out}}"
        f"{pct(b + 1.0)}{{transform:rotate(-.5deg);animation-timing-function:ease-in-out}}"
        f"{pct(b + 1.6)}{{transform:rotate(.2deg);animation-timing-function:ease-in-out}}"
        f"{pct(b + 2.3)},100%{{transform:rotate(0deg)}}}}")
    css.append('@keyframes grow{from{transform:translateY(700px)}to{transform:translateY(0)}}')
    css.append('@keyframes write{from{transform:translateX(-900px)}to{transform:translateX(0)}}')
    css.append('@keyframes stamp{0%{opacity:0;transform:scale(1.35) rotate(-4deg)}60%{opacity:1;transform:scale(.97) rotate(-4deg)}100%{opacity:1;transform:scale(1) rotate(-4deg)}}')
    css.append('@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}')
    css.append('@keyframes drift1{from{transform:translateX(-70px)}to{transform:translateX(90px)}}')
    css.append('@keyframes drift2{from{transform:translateX(60px)}to{transform:translateX(-110px)}}')
    css.append(
        f".k{{opacity:0;animation-duration:{T}s;animation-timing-function:step-end;animation-iteration-count:infinite}}"
        f".p1{{opacity:1}}"
        + ''.join(f".{k}{{animation-name:v_{k}}}" for k in spans)
        + f".fly{{opacity:0;animation:v_fly {T}s step-end infinite}}"
        + ''.join(f".w{i}{{opacity:{1 if i == 0 else 0};animation:w_{k} {beat}s step-end infinite}}" for i, k in enumerate(FLAP))
        + f".bx{{animation:bx {T}s infinite}}.by{{animation:by {T}s infinite}}"
        f".sway{{transform-origin:{joint[0]:.1f}px {joint[1]:.1f}px;animation:sway {T}s infinite}}"
        ".grow{animation:grow 2.9s cubic-bezier(.3,.1,.25,1) both}"
        ".write{animation:write 1.9s .35s cubic-bezier(.4,0,.2,1) both}"
        f".seal{{transform-origin:{SX + 28}px {SY + 28}px;transform:rotate(-4deg);animation:stamp .42s 2.3s ease-out both}}"
        ".r1{animation:rise .9s .1s ease-out both}.r2{animation:rise .9s 1.7s ease-out both}.r3{animation:rise .9s 2.6s ease-out both}"
        ".m1{animation:drift1 53s ease-in-out infinite alternate}.m2{animation:drift2 71s ease-in-out infinite alternate}"
        "@media (prefers-reduced-motion:reduce){*{animation:none!important}}")

    flap = ''.join(f'<image class="w{i}" href="{uri(sheet.crop((FR[k][0], FR[k][1], FR[k][0] + FR[k][2], FR[k][1] + FR[k][3])).resize((round(FR[k][2] * .8), round(FR[k][3] * .8)), Image.LANCZOS), 84)}" '
                   f'x="{eye[0] - FR[k][4]:.1f}" y="{eye[1] - FR[k][5]:.1f}" width="{FR[k][2]}" height="{FR[k][3]}"/>' for i, k in enumerate(FLAP))
    frames = ''.join(frame(k) for k in spans)

    title = ('Harsh Kumar Banka. Software Engineer at Quinence. I build AI agents and the production systems behind them. '
             'An ink painting: mountains in mist, a plum branch, and a small bird that flies in and sits on it. harshbanka.tech')
    o = [svg_open(W, H, title), f'<style>{"".join(css)}</style>',
         '<defs>'
         f'<clipPath id="page"><rect width="{W}" height="{H}" rx="18"/></clipPath>'
         '<linearGradient id="gv" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".12" stop-color="#fff"/></linearGradient>'
         '<linearGradient id="gh" x1="0" y1="0" x2="1" y2="0"><stop offset=".9" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
         f'<mask id="mgrow" maskUnits="userSpaceOnUse" x="{BX - 20}" y="-60" width="520" height="720"><rect class="grow" x="{BX - 20}" y="-60" width="520" height="760" fill="url(#gv)"/></mask>'
         '<mask id="mwrite" maskUnits="userSpaceOnUse" x="40" y="310" width="900" height="150"><rect class="write" x="40" y="310" width="900" height="150" fill="url(#gh)"/></mask>'
         '</defs>',
         '<g clip-path="url(#page)">',
         f'<image href="{bg}" width="{W}" height="{H}" preserveAspectRatio="none"/>',
         f'<image class="m1" href="{mist}" x="60" y="150" width="760" height="178" opacity=".9"/>',
         f'<image class="m2" href="{mist}" x="420" y="60" width="620" height="140" opacity=".6"/>',
         # the bough: the stem, and the part that turns about the joint
         f'<g mask="url(#mgrow)"><image href="{uri(rest, 82)}" x="{BX}" y="{BY}" width="{BOUGH["w"] * BS:.1f}" height="{BOUGH["h"] * BS:.1f}"/>'
         f'<g class="sway"><image href="{uri(part, 84)}" x="{BX + px * BS:.1f}" y="{BY + py * BS:.1f}" width="{pw * BS:.1f}" height="{ph * BS:.1f}"/></g></g>',
         # the bird, riding the same bough
         f'<g class="sway"><g transform="translate({seat[0]:.1f} {seat[1]:.1f})"><g class="bx"><g class="by"><g transform="scale({bs:.4f})">'
         f'{frames}<g class="fly">{flap}</g></g></g></g></g></g>',
         # the words
         f'<g class="seal"><rect x="{SX}" y="{SY}" width="56" height="56" rx="6" fill="{c["red"]}"/>'
         f'<rect x="{SX + 5}" y="{SY + 5}" width="46" height="46" rx="3" fill="none" stroke="{c["seal_ink"]}" stroke-opacity=".55" stroke-width="1.2"/>'
         f'{words("HB", 26, SX + 28, SY + 37, c["seal_ink"], "middle", .5)}</g>',
         f'<g class="r1">{words("SOFTWARE ENGINEER   ·   QUINENCE", 19, 80, 322, c["soft"], track=4.2)}</g>',
         f'<g mask="url(#mwrite)">{words("Harsh Kumar Banka", NS, 76, 410, c["ink"], track=-.6)}</g>',
         f'<g class="r2">{words("I build AI agents and the production systems behind them.", 28.5, 80, 466, c["soft"], italic=True)}</g>',
         f'<g class="r3">{words("The full scroll:", 19, 80, 546, c["faint"], italic=True)}'
         f'{words("harshbanka.tech", 21, 80 + face(True).width("The full scroll: ", 19), 546, c["ink"])}'
         f'<path d="M{80 + face(True).width("The full scroll: ", 19):.1f} 554h{face().width("harshbanka.tech", 21):.1f}" stroke="{c["red"]}" stroke-width="1.4" stroke-linecap="round" opacity=".85"/></g>',
         '</g></svg>']
    save(f'hero-{theme}.svg', ''.join(o))


# ---------------------------------------------------------------- paper for the slips and the cards
_tiles = {}
def tile(theme):
    """A small piece of paper, repeated as a pattern."""
    if theme not in _tiles:
        from PIL import Image
        import numpy as np
        c = THEMES[theme]
        rgb = tuple(int(c['slip'][i:i + 2], 16) for i in (1, 3, 5))
        a = grain((320, 320), 23, 2.6 if theme == 'light' else 1.7, slow=False)
        # make it tile: blend the edges into their opposite sides
        arr = np.array(rgb, dtype=float)[None, None, :] + a[:, :, None]
        _tiles[theme] = uri(Image.fromarray(arr.clip(0, 255).astype('uint8'), 'RGB'), 78)
    return f'<pattern id="paper" patternUnits="userSpaceOnUse" width="320" height="320"><image href="{_tiles[theme]}" width="320" height="320"/></pattern>'

# ---------------------------------------------------------------- the work, on hanging slips
SLIPS = [
    ('NOW', 'Quinence', 'Software Engineer, Jun 2026 to present', [
        'Built Halocard: spend crypto with a Visa card. KYC, card issuing and deposits, live in production.',
        'A multi-tenant MCP server, so each customer of a B2B platform can query their own data from Claude or ChatGPT.',
        'An AI support agent on Claude Code that traces tickets to their root cause.']),
    ('BEFORE', 'EmendoAI', 'Software Engineer (AI/ML), Oct 2024 to May 2026', [
        'AI agents and a Gemini document pipeline for a construction platform.',
        'An LLM test framework: regression tests across 10+ features, with no manual work.',
        '200+ Lambda functions across 35 AWS CDK stacks, in production.']),
    ('ALSO', 'Research and wins', 'NIT Trichy, and two hackathons', [
        'Pose estimation research at NIT Trichy: HRNet and FiDIP, to monitor infant motor skills.',
        'First place, CodeFest Hackathon 2024, with an AI interview system.',
        'First place, DigiZest Hackathon 2023, with home automation you run by talking to an LLM.']),
]

def slips(theme):
    c = THEMES[theme]
    w, sw, top = 1200, 344, 86
    xs = [44, 428, 812]
    bodies, heights = [], []
    for (label, name, sub, points) in SLIPS:
        y = top + 58
        o = [words(label, 15, 30, y, c['red'], track=4)]
        y += 46; o.append(words(name, 35, 29, y, c['ink']))
        y += 30
        for ln in face(True).wrap(sub, 17.5, sw - 60):
            o.append(words(ln, 17.5, 30, y, c['soft'], italic=True)); y += 23
        y += 4; o.append(f'<path d="M30 {y}h{sw - 60}" stroke="{c["slip_edge"]}" stroke-width="1"/>'); y += 34
        for p in points:
            o.append(f'<circle cx="34" cy="{y - 6}" r="2.6" fill="{c["red"]}" opacity=".85"/>')
            for ln in face().wrap(p, 18.5, sw - 78):
                o.append(words(ln, 18.5, 48, y, c['ink'])); y += 26
            y += 12
        heights.append(y + 16 - top); bodies.append(''.join(o))
    sh = max(heights)
    h = top + sh + 34
    title = 'Work. ' + ' '.join(f'{l.capitalize()}: {n}, {s}. ' + ' '.join(p) for l, n, s, p in SLIPS)
    # the slips hang still: text that turns, even by half a degree, shimmers as it is redrawn and is tiring to read
    css = ''
    o = [svg_open(w, h, title), f'<style>{css}</style><defs>{tile(theme)}</defs>',
         f'<path d="M14 26C300 34 900 34 1186 26" fill="none" stroke="{c["line"]}" stroke-width="2.2" stroke-linecap="round" opacity=".8"/>']
    for i, body in enumerate(bodies):
        x = xs[i]; cx = x + sw / 2
        o.append(f'<g class="s{i}"><path d="M{cx} 31V{top + 16}" stroke="{c["line"]}" stroke-width="1.5" opacity=".8"/>'
                 f'<rect x="{x + 5}" y="{top + 6}" width="{sw}" height="{sh}" rx="3" fill="#000" opacity="{.10 if theme == "light" else .32}"/>'
                 f'<rect x="{x}" y="{top}" width="{sw}" height="{sh}" rx="3" fill="url(#paper)" stroke="{c["slip_edge"]}" stroke-width="1"/>'
                 f'<circle cx="{cx}" cy="{top + 16}" r="4.2" fill="none" stroke="{c["line"]}" stroke-width="1.3" opacity=".7"/>'
                 f'<g transform="translate({x} 0)">{body}</g></g>')
    o.append('</svg>')
    save(f'work-{theme}.svg', ''.join(o))


# ---------------------------------------------------------------- four things built, one card each
CARDS = [
    ('medclaim', 'AI · PERSONAL', 'MedClaim AI',
     'Insurance claims, decided by five LangGraph agents: verify, extract, check the policy, flag fraud, decide. Runs on SQS-triggered Lambda with live progress.',
     'LangGraph · Gemini · Lambda · SQS'),
    ('layerwise', 'AI · PERSONAL', 'Layerwise',
     'AI takeoff for construction blueprints. Gemini Vision counts and measures what is drawn, and finds the scale of the drawing by itself.',
     'Next.js · FastAPI · Gemini Vision · Pydantic AI'),
    ('newsbug', 'AI · PERSONAL', 'News Insights',
     'Tracks disease outbreaks from the news. It crawls sources, pulls out diseases, places and case counts with AI, and maps them on a 3D globe.',
     'Next.js · Gemini · spaCy · Mapbox'),
    ('crm', 'FULL STACK · PERSONAL', 'Mini CRM',
     'Customer segments built with a rule builder or in plain English, campaigns sent to them, and AI summaries of how each one did.',
     'Next.js · Redis Streams · Google OAuth'),
]

def cards(theme):
    c = THEMES[theme]
    w, h = 600, 318
    for key, tag, name, text, chips in CARDS:
        o = [svg_open(w, h, f'{name}. {text} Built with {chips.replace(" · ", ", ")}.'), f'<defs>{tile(theme)}</defs>',
             f'<rect x="13" y="15" width="{w - 20}" height="{h - 22}" rx="4" fill="#000" opacity="{.09 if theme == "light" else .3}"/>',
             f'<rect x="8" y="8" width="{w - 20}" height="{h - 22}" rx="4" fill="url(#paper)" stroke="{c["slip_edge"]}"/>',
             words(tag, 15, 40, 60, c['red'], track=3.6),
             words(name, 40, 39, 112, c['ink'])]
        y = 154
        for ln in face().wrap(text, 20.5, w - 96):
            o.append(words(ln, 20.5, 40, y, c['soft'])); y += 29
        o.append(f'<path d="M40 {h - 68}h{w - 96}" stroke="{c["slip_edge"]}"/>')
        o.append(words(chips, 17.5, 40, h - 40, c['faint'], italic=True))
        o.append('</svg>')
        save(f'card-{key}-{theme}.svg', ''.join(o))


# ---------------------------------------------------------------- what I work with, set as type
STACK = [
    ('LANGUAGES', 'Python · TypeScript · JavaScript · SQL · Java · C/C++'),
    ('GENAI', 'Gemini · OpenAI · LangGraph · LangChain · Vercel AI SDK · Claude Agent SDK · Google ADK · Pinecone'),
    ('AI/ML', 'PyTorch · TensorFlow · scikit-learn · OpenCV · Transformers · MLflow · ZenML'),
    ('DEVELOPMENT', 'Next.js · React · Node.js · Express · FastAPI · Django · Spring Boot · Tailwind CSS · GraphQL'),
    ('DATA & CLOUD', 'AWS · Azure · Vercel · Cloudflare · Supabase · Docker · PostgreSQL · MongoDB · Redis'),
]

def item_lines(items, size, maxw):
    """Lines of whole items; a line never ends on the dot that separates them."""
    lines, cur = [], ''
    for it in items.split(' · '):
        trial = cur + ' · ' + it if cur else it
        if cur and face().width(trial, size) > maxw:
            lines.append(cur); cur = it
        else:
            cur = trial
    return lines + [cur]

def stack(theme):
    c = THEMES[theme]
    w = 1200
    o, y = [], 46
    for label, items in STACK:
        o.append(words(label, 15.5, 250, y, c['red'], 'end', track=3.6))
        for ln in item_lines(items, 22, w - 300 - 40):
            o.append(words(ln, 22, 290, y + 1, c['ink'])); y += 31
        y += 17
    h = y - 4
    o.insert(0, f'<path d="M270 22V{h - 18}" stroke="{c["faint"]}" stroke-width="1" opacity=".5"/>')
    title = 'What I work with. ' + ' '.join(f'{l.capitalize()}: {i.replace(" · ", ", ")}.' for l, i in STACK)
    save(f'stack-{theme}.svg', svg_open(w, h, title) + ''.join(o) + '</svg>')


# ---------------------------------------------------------------- a year of contributions, as dabs of ink
QUERY = 'query($u:String!){user(login:$u){contributionsCollection{contributionCalendar{totalContributions weeks{contributionDays{date contributionCount contributionLevel weekday}}}}}}'
LEVEL = {'NONE': 0, 'FIRST_QUARTILE': 1, 'SECOND_QUARTILE': 2, 'THIRD_QUARTILE': 3, 'FOURTH_QUARTILE': 4}

def calendar():
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if not token:
        token = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, check=True).stdout.strip()
    req = urllib.request.Request('https://api.github.com/graphql', data=json.dumps({'query': QUERY, 'variables': {'u': USER}}).encode(),
                                 headers={'Authorization': 'bearer ' + token, 'User-Agent': 'profile-scroll'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return data['data']['user']['contributionsCollection']['contributionCalendar']

def year(cal=None):
    cal = cal or calendar()
    weeks = cal['weeks']
    total = cal['totalContributions']
    days = [d for wk in weeks for d in wk['contributionDays']]
    busiest = max(days, key=lambda d: d['contributionCount'])
    active = sum(1 for d in days if d['contributionCount'])
    step, x0, y0 = 20.2, 62, 92
    w, h = 1200, 326
    months = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()
    for theme in THEMES:
        c = THEMES[theme]
        o, labels, last = [], [], None
        for i, wk in enumerate(weeks):
            first = wk['contributionDays'][0]['date']
            m = int(first[5:7])
            if m != last and int(first[8:10]) <= 7:
                labels.append(words(months[m - 1], 16, x0 + i * step - 4, 64, c['faint'], italic=True))
            if int(first[8:10]) <= 7: last = m
            for d in wk['contributionDays']:
                lv = LEVEL[d['contributionLevel']]
                rnd = random.Random(d['date'])           # the same day is always the same dab
                cx = x0 + i * step + rnd.uniform(-1.1, 1.1); cy = y0 + d['weekday'] * step + rnd.uniform(-1.1, 1.1)
                if lv == 0:
                    o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="1.5" fill="{c["ink"]}" opacity=".16"/>')
                    continue
                r = 2.9 + lv * 1.55
                rx, ry = r * rnd.uniform(.9, 1.12), r * rnd.uniform(.84, 1.04)
                op = (.3, .48, .68, .9)[lv - 1] * rnd.uniform(.9, 1.05)
                today = d is days[-1]
                o.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" transform="rotate({rnd.uniform(-40, 40):.0f} {cx:.1f} {cy:.1f})" '
                         f'fill="{c["red"] if today else c["ink"]}" opacity="{min(op, 1):.2f}"/>')
        num = f'{total:,}'
        o2 = [words('A YEAR, IN INK', 15.5, x0 - 6, 30, c['red'], track=3.8),
              words(num, 46, w - 60, 286, c['ink'], 'end'),
              words('contributions in the last year', 18, w - 60 - face().width(num, 46) - 14, 286, c['soft'], 'end', italic=True),
              words(f'{active} days with work on them. The busiest had {busiest["contributionCount"]}.', 18, x0 - 6, 286, c['faint'], italic=True)]
        title = (f'A year of contributions on GitHub, drawn as dabs of ink, one per day: the darker the dab, the more was done. '
                 f'{num} contributions in the last year, on {active} days.')
        svg = (svg_open(w, h, title) +
               '<defs><filter id="brush" x="-5%" y="-5%" width="110%" height="110%"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" seed="4" result="n"/>'
               '<feDisplacementMap in="SourceGraphic" in2="n" scale="2.6" xChannelSelector="R" yChannelSelector="G"/></filter></defs>'
               + ''.join(labels) + f'<g filter="url(#brush)">{"".join(o)}</g>' + ''.join(o2) + '</svg>')
        save(f'year-{theme}.svg', svg)


# ---------------------------------------------------------------- the page that shows them
REPOS = {'medclaim': 'medclaim-ai', 'layerwise': 'layerwise.ai', 'newsbug': 'news-bug', 'crm': 'crm-xeno'}

def pic(name, alt, width='100%'):
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">'
            f'<img src="assets/{name}-light.svg" width="{width}" alt="{esc(alt)}"></picture>')

def readme():
    work = ' '.join(f'{l.capitalize()}: {n} ({s}). ' + ' '.join(p) for l, n, s, p in SLIPS)
    rows = []
    for i in (0, 2):
        rows.append('<p align="center">\n' + '\n'.join(
            f'  <a href="https://github.com/{USER}/{REPOS[k]}">{pic("card-" + k, f"{name}. {text} Built with {chips.replace(chr(32) + chr(183) + chr(32), chr(44) + chr(32))}.", "49%")}</a>'
            for k, tag, name, text, chips in CARDS[i:i + 2]) + '\n</p>')
    plain = ['<details>', '<summary>The same, in plain text</summary>', '',
             '**Harsh Kumar Banka.** Software Engineer at Quinence. I build AI agents and the production systems behind them.', '']
    for l, n, s_, pts in SLIPS:
        plain += [f'**{n}**, {s_}', ''] + [f'- {p_}' for p_ in pts] + ['']
    plain += ['**Things I built**', ''] + [f'- [{name}](https://github.com/{USER}/{REPOS[k]}): {text}' for k, tag, name, text, chips in CARDS] + ['']
    plain += ['**What I work with**', ''] + [f'- {l.capitalize()}: {i.replace(" · ", ", ")}' for l, i in STACK] + ['', '</details>']
    md = [
        f'<a href="https://www.harshbanka.tech">{pic("hero", "Harsh Kumar Banka. Software Engineer at Quinence. I build AI agents and the production systems behind them. An ink painting of mountains in mist and a plum branch; a small bird flies in and sits on it. The full scroll is at harshbanka.tech.")}</a>',
        '', '<br>', '',
        f'<p align="center">{pic("work", "Work, on three hanging slips of paper. " + work)}</p>',
        '', *rows, '',
        f'<p align="center">{pic("year", "A year of contributions on GitHub, drawn as dabs of ink, one per day. The darker the dab, the more was done that day.")}</p>',
        '',
        f'<p align="center">{pic("stack", "What I work with. " + " ".join(f"{l.capitalize()}: {i.replace(chr(32) + chr(183) + chr(32), chr(44) + chr(32))}." for l, i in STACK))}</p>',
        '',
        '<p align="center">',
        '  <a href="https://www.harshbanka.tech">Portfolio</a> &nbsp;·&nbsp;',
        '  <a href="https://www.linkedin.com/in/harsh-banka">LinkedIn</a> &nbsp;·&nbsp;',
        '  <a href="https://www.harshbanka.tech/Harsh_Kumar_Banka_Resume.pdf">Resume</a>',
        '</p>', '',
        *plain, '',
        '<p align="center"><sub>',
        '  The landscape is a painting from The Metropolitan Museum of Art, public domain. The bird and her plum branch were painted with a Gemini image model.<br>',
        '  The type is Baskervville (OFL). Everything here is drawn by <a href="scroll/build.py">a script in this repository</a>, and the year of ink is redrawn every day.',
        '</sub></p>', '']
    with open(os.path.join(ROOT, 'README.md'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(md))
    print('README.md')


if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if what == 'year':
        year()
    else:
        for th in THEMES:
            hero(th); slips(th); cards(th); stack(th)
        if what != 'offline': year()
        readme()
