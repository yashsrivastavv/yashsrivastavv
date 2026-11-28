#!/usr/bin/env python3
"""Render the profile README as a stack of animated SVG cards.

    python3 scripts/render_cards.py            # cards/*.svg + README.md
    STATIC=1 python3 scripts/render_cards.py   # final frame only -> preview/ (+ index.html)

Cards are shown through <img>, so everything is self-contained: an inline <style>
with CSS keyframes, SMIL <animate> for purely decorative pulses, and fonts
subset with pyftsubset and embedded as base64 WOFF2 data URIs.

Every animation is written "from" a hidden state with fill-mode `both`, so the
resting state of every element is the final frame. Turning animation off
(prefers-reduced-motion, or STATIC=1) therefore just shows the finished card.
Gutters between cards are baked into each SVG (PAD), so the README needs no spacing.

Look: deep space. Near-black navy panels under a sparse, seeded starfield, starlight
text, a nebula-violet and a star-gold accent, sharp rules, a huge light sans in caps,
mono and pixel-font "mission" labels, a star-map contribution graph, thrust-column
bars, orbit rings around the name and a dithered halftone portrait in starlight.
Stars are drawn with random.Random seeded by the card name, so output is stable.
"""
import base64, datetime as dt, hashlib, html, json, math, os, random, subprocess, sys, tempfile
from collections import OrderedDict

from fontTools.ttLib import TTFont

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
STATIC = os.environ.get("STATIC") == "1"
OUT = os.path.join(ROOT, "preview" if STATIC else "cards")

# ---- identity ---------------------------------------------------------------------
NAME = ("YASH", "SRIVASTAVA")
CAPTION = ["SENIOR SOFTWARE ENGINEER", "AT NAUKRI.COM, EXPLORING", "ML + BLOCKCHAIN + AR/VR"]
ALT_ABOUT = "Senior software engineer at Naukri.com, exploring machine learning, blockchain and AR/VR."
SITE = ("yashsrivastav.vercel.app", "https://yashsrivastav.vercel.app/")
LINKEDIN = ("in/yash-stv", "https://www.linkedin.com/in/yash-stv/")
EMAIL = "iyashsrivastav@gmail.com"
# Deep-space palette. Contrast against SPACE: STAR 16.9:1, MUTED 6.8:1, GOLD 13.2:1,
# NEBULA 7.9:1; against PANEL: STAR 15.1:1, MUTED 6.1:1; SPACE on NEBULA 7.9:1.
SPACE = "#0b0f1e"   # card background, near-black navy
PANEL = "#151b33"   # a slightly lighter panel
STAR = "#eef1ff"    # starlight: primary text and marks
MUTED = "#8f99c2"   # blue-grey secondary text
FAINT = "#3a4470"   # zero-days, backdrop dots, orbit rings (decoration only, never text)
HAIR = "#1f2640"    # hairlines and borders
NEBULA = "#b794ff"  # nebula violet accent
GOLD = "#ffd166"    # star-gold signal colour (peaks, the brightest star)
INK_L, NEBULA_L = "#0b0f1e", "#6b3fe0"  # heading on GitHub's white page (19.1:1, 6.2:1)
TILES = [  # (file, index, label, roman, sub, href, background, text colour, border)
    ("tile-portfolio", "01", "PORTFOLIO", "See my work", SITE[0].upper(), SITE[1], SPACE, STAR, HAIR),
    ("tile-linkedin", "02", "LINKEDIN", "Say hello", LINKEDIN[0].upper(), LINKEDIN[1], PANEL, STAR, "#2a3358"),
    ("tile-email", "03", "EMAIL", "Write to me", EMAIL.upper(), "mailto:" + EMAIL, NEBULA, SPACE, NEBULA),
]
W = 830          # full-width canvas
PAD = 8          # transparent gutter baked around every card
THIRD = 277      # canvas width of a card shown at 33.333%

FONT_DIR = os.path.join(ROOT, "assets", "fonts")
FONTS = {  # face -> (file, family, css weight)
    "g": ("geist-latin-300-normal.woff2", "Geist", 300),            # huge light display
    "gr": ("geist-latin-400-normal.woff2", "Geist", 400),           # body
    "m": ("geist-mono-latin-400-normal.woff2", "Geist Mono", 400),  # captions
    "mm": ("geist-mono-latin-500-normal.woff2", "Geist Mono", 500),
    "px": ("departure-mono-regular.woff2", "Departure Mono", 400),  # pixel micro labels
}
_ttf = {k: TTFont(os.path.join(FONT_DIR, v[0])) for k, v in FONTS.items()}


def measure(s, size, face="gr", spacing=0):
    f = _ttf[face]
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    return sum(hmtx[cmap.get(ord(c), ".notdef")][0] for c in s) * size / upm + spacing * len(s)


def wrap(s, size, face, width, max_lines):
    lines, cur = [], ""
    for word in s.split():
        t = (cur + " " + word).strip()
        if measure(t, size, face) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and measure(last + "…", size, face) > width:
            last = last[:-1].rstrip()
        lines[-1] = last + "…"
    return lines


def subset_font(face, chars):
    """pyftsubset the source font down to `chars`; return a base64 WOFF2 data URI."""
    src = os.path.join(FONT_DIR, FONTS[face][0])
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "s.woff2")
        subprocess.run([sys.executable, "-m", "fontTools.subset", src, f"--text={''.join(sorted(chars))}",
                        "--flavor=woff2", "--layout-features=kern", "--no-hinting",
                        f"--output-file={out}"], check=True)
        return "data:font/woff2;base64," + base64.b64encode(open(out, "rb").read()).decode()


CSS_BASE = f"""
text{{fill:{STAR};white-space:pre}}
.f-g{{font-family:Geist,system-ui,sans-serif;font-weight:300}}
.f-gr{{font-family:Geist,system-ui,sans-serif;font-weight:400}}
.f-m{{font-family:'Geist Mono',ui-monospace,Menlo,monospace}}
.f-mm{{font-family:'Geist Mono',ui-monospace,Menlo,monospace;font-weight:500}}
.f-px{{font-family:'Departure Mono','Geist Mono',ui-monospace,monospace}}
.mu{{fill:{MUTED}}} .ne{{fill:{NEBULA}}} .go{{fill:{GOLD}}}
.st{{fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:square;stroke-linejoin:miter}}
"""
CSS_ANIM = """
@keyframes rise{from{opacity:0;transform:translateY(10px)}}
@keyframes grow{from{transform:scaleY(0)}}
@keyframes pop{from{opacity:0;transform:scale(.2)}}
@keyframes fade{from{opacity:0}}
@keyframes draw{from{transform:scaleX(0)}}
.rise{animation:rise .7s cubic-bezier(.16,1,.3,1) both}
.fade{animation:fade .5s ease-out both}
.grow{animation:grow .8s cubic-bezier(.16,1,.3,1) both;transform-box:fill-box;transform-origin:50% 100%}
.pop{animation:pop .4s cubic-bezier(.3,1.4,.5,1) both;transform-box:fill-box;transform-origin:center}
.draw{animation:draw .9s cubic-bezier(.16,1,.3,1) both;transform-box:fill-box;transform-origin:0 50%}
@media (prefers-reduced-motion:reduce){*{animation:none!important}.smil{display:none}}
"""


class Card:
    """A canvas of w x h with a sharp-cornered card inset by PAD (bg=None for a bare heading)."""

    def __init__(self, name, w, h, title, desc, bg=SPACE, border=HAIR, ink=STAR):
        self.name, self.w, self.h, self.title, self.desc = name, w, h, title, desc
        self.bg, self.border, self.ink = bg, border, ink
        self.parts, self.chars = [], {k: set() for k in FONTS}

    def add(self, s):
        self.parts.append(s)

    def anim(self, inner, cls, delay):
        return inner if STATIC else f'<g class="{cls}" style="animation-delay:{delay:.2f}s">{inner}</g>'

    def text(self, x, y, s, size, face="gr", cls="", anchor="start", delay=None, spacing=0):
        if not s:
            return
        self.chars[face].update(s)
        c = " ".join(filter(None, [f"f-{face}", cls]))
        ls = f' letter-spacing="{spacing:.2f}"' if spacing else ""
        t = f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size:.1f}"{ls} text-anchor="{anchor}" class="{c}">{html.escape(s)}</text>'
        self.add(self.anim(t, "rise", delay) if delay is not None else t)

    def svg(self):
        faces = "".join(
            f'@font-face{{font-family:"{FONTS[k][1]}";font-weight:{FONTS[k][2]};'
            f'src:url({subset_font(k, chars | {" "})}) format("woff2")}}'
            for k, chars in self.chars.items() if chars)
        css = faces + CSS_BASE.replace(f"fill:{STAR};white", f"fill:{self.ink};white") + ("" if STATIC else CSS_ANIM)
        rect = (f'<rect x="{PAD + .5}" y="{PAD + .5}" width="{self.w - 2*PAD - 1}" height="{self.h - 2*PAD - 1}" '
                f'fill="{self.bg}" stroke="{self.border}"/>') if self.bg else ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" xml:space="preserve" role="img" aria-labelledby="t d">'
                f'<title id="t">{html.escape(self.title)}</title><desc id="d">{html.escape(self.desc)}</desc>'
                f'<style>{css}</style>{rect}' + "".join(self.parts) + "</svg>")

    def save(self):
        os.makedirs(OUT, exist_ok=True)
        data = self.svg()
        with open(os.path.join(OUT, self.name + ".svg"), "w") as f:
            f.write(data)
        return len(data)


def pulse(cx, cy, r0, r1, begin, color=GOLD):
    """Decorative SMIL ring. Hidden under prefers-reduced-motion; omitted in STATIC."""
    if STATIC:
        return ""
    return (f'<circle class="smil" cx="{cx:.1f}" cy="{cy:.1f}" r="{r0}" fill="none" stroke="{color}" stroke-width="1.5" opacity="0">'
            f'<animate attributeName="r" values="{r0};{r1}" dur="2.8s" repeatCount="indefinite" begin="{begin}s"/>'
            f'<animate attributeName="opacity" values="0.7;0" dur="2.8s" repeatCount="indefinite" begin="{begin}s"/></circle>')


def starfield(c, n, avoid=(), color=STAR, twinkle=3, box=None):
    """Sparse background stars for card `c`, seeded by its name so every run draws the same sky.

    `avoid` is a list of (x0, y0, x1, y1) rects kept clear (text, charts). The stars are
    static; a few get a SMIL twinkle overlay that starts from opacity 0, so with motion
    off (STATIC, or prefers-reduced-motion hiding .smil) the plain star remains.
    """
    rng = random.Random("stars:" + c.name)
    x0, y0, x1, y1 = box or (PAD + 6, PAD + 6, c.w - PAD - 6, c.h - PAD - 6)
    stars, tries = [], 0
    while len(stars) < n and tries < n * 40:
        tries += 1
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        if any(a <= x <= b and p <= y <= q for a, p, b, q in avoid):
            continue
        r = rng.choice((0.5, 0.6, 0.7, 0.8, 0.9, 1.1, 1.4))
        stars.append((x, y, r, round(rng.uniform(0.25, 0.85), 2)))
    out = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" opacity="{o}"/>' for x, y, r, o in stars)
    tw = ""
    if not STATIC:
        bright = sorted(stars, key=lambda s: -s[2])[:twinkle]
        for k, (x, y, r, _) in enumerate(bright):
            dur, begin = rng.choice((3.2, 4.1, 5.3)), round(rng.uniform(0, 3), 1)
            tw += (f'<circle class="smil" cx="{x:.1f}" cy="{y:.1f}" r="{r + 0.9:.1f}" opacity="0">'
                   f'<animate attributeName="opacity" values="0;0.9;0" dur="{dur}s" begin="{begin}s" repeatCount="indefinite"/></circle>')
    c.add(f'<g fill="{color}" aria-hidden="true">{out}{tw}</g>')


def sparkle(cx, cy, s, color):
    """A four-point star glyph drawn as a path (no font glyph needed)."""
    k = s * 0.22
    return (f'<path d="M{cx:.1f} {cy - s:.1f}L{cx + k:.1f} {cy - k:.1f}L{cx + s:.1f} {cy:.1f}L{cx + k:.1f} {cy + k:.1f}'
            f'L{cx:.1f} {cy + s:.1f}L{cx - k:.1f} {cy + k:.1f}L{cx - s:.1f} {cy:.1f}L{cx - k:.1f} {cy - k:.1f}Z" fill="{color}"/>')


def arrow(x, y, color, s=1.0):
    return f'<g transform="translate({x:.1f} {y:.1f}) scale({s})" style="color:{color}"><path class="st" d="M3 15L15 3M5 3h10v10"/></g>'


# ---- data -------------------------------------------------------------------------
def load():
    with open(os.path.join(ROOT, "data", "github.json")) as f:
        d = json.load(f)
    for x in d["calendar"]:
        x["d"] = dt.date.fromisoformat(x["date"])
    d["calendar"].sort(key=lambda x: x["d"])
    return d


def month_window(last):
    y, m, out = last.year, last.month, []
    for _ in range(12):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def stats(cal):
    best = cur = 0
    for x in cal:
        cur = cur + 1 if x["count"] else 0
        best = max(best, cur)
    i = len(cal) - 1
    if i >= 0 and cal[i]["count"] == 0:
        i -= 1  # today may simply not have happened yet
    streak = 0
    while i >= 0 and cal[i]["count"]:
        streak += 1
        i -= 1
    months = month_window(cal[-1]["d"])
    win = [x for x in cal if x["d"] >= dt.date(*months[0], 1)]
    tot = OrderedDict((k, 0) for k in months)
    for x in win:
        tot[(x["d"].year, x["d"].month)] += x["count"]
    return dict(streak=streak, longest=best, months=tot, total=sum(tot.values()), days=len(win),
                active=sum(1 for x in win if x["count"]), busiest=max(x["count"] for x in win))


def plural(n, w):
    return f"{n:,} {w}" + ("" if n == 1 else "s")


def halftone():
    p = os.path.join(ROOT, "assets", "portrait-halftone.json")  # made once by scripts/make_halftone.py
    return json.load(open(p)) if os.path.exists(p) else None


# ---- cards ----------------------------------------------------------------------------
def hero(d):
    c = Card("hero", W, 440, d["name"], f"{d['name']}. {ALT_ABOUT}")
    bx, by, bw, bh = 40, 50, 290, 340
    tx, tw = 372, W - 40 - 372
    size = min(104, tw / (measure(NAME[1], 1, "g") - 0.02 * len(NAME[1])))
    ls = -size * 0.02
    cap = size * 0.71
    name_bot = by + cap + size * 0.86 + size * 0.05
    cap_top = by + bh - (len(CAPTION) - 1) * 20 - 3 - 14
    label_y = cap_top - 22
    starfield(c, 70, avoid=[(bx - 6, by - 6, bx + bw + 6, by + bh + 6),
                            (tx - 12, by - 8, W - 30, name_bot + 4),
                            (tx - 6, label_y - 14, W - 30, by + bh + 6)])
    ht = halftone()
    if ht:
        # a faint printed-dot backdrop, then the dithered subject revealed band by band in starlight
        c.add(f'<defs><pattern id="dots" width="3" height="3" patternUnits="userSpaceOnUse">'
              f'<circle cx="1.5" cy="1.5" r=".75" fill="{FAINT}"/></pattern></defs>')
        c.add(c.anim(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="url(#dots)"/>', "fade", 0.0))
        for i, band in enumerate(ht["bands"]):
            if band:
                c.add(c.anim(f'<path d="{band}" transform="translate({bx} {by})" fill="{STAR}"/>', "fade", 0.15 + i * 0.022))
    # orbit motif in the gap between the name and the caption
    ocx, ocy = tx + tw / 2, (name_bot + label_y - 12) / 2
    orx, ory = tw / 2 + 4, max(10.0, (label_y - 12 - name_bot) / 2 - 6)
    ring = f'M{ocx - orx:.1f} {ocy:.1f}A{orx:.1f} {ory:.1f} 0 1 1 {ocx + orx:.1f} {ocy:.1f}A{orx:.1f} {ory:.1f} 0 1 1 {ocx - orx:.1f} {ocy:.1f}'
    a = math.radians(205)
    px_, py_ = ocx + orx * math.cos(a), ocy - ory * math.sin(a)
    orbit = (f'<g transform="rotate(-3 {ocx:.1f} {ocy:.1f})">'
             f'<ellipse cx="{ocx:.1f}" cy="{ocy:.1f}" rx="{orx:.1f}" ry="{ory:.1f}" fill="none" stroke="{FAINT}" stroke-width="1"/>'
             f'<ellipse cx="{ocx:.1f}" cy="{ocy:.1f}" rx="{orx * 0.62:.1f}" ry="{ory * 0.62:.1f}" fill="none" stroke="{HAIR}" '
             f'stroke-width="1" stroke-dasharray="2 5"/>'
             f'<circle cx="{px_:.1f}" cy="{py_:.1f}" r="6" fill="{GOLD}"/>'
             f'<ellipse cx="{px_:.1f}" cy="{py_:.1f}" rx="11" ry="3" fill="none" stroke="{GOLD}" stroke-width="1" '
             f'transform="rotate(-18 {px_:.1f} {py_:.1f})"/>'
             f'<circle cx="{ocx:.1f}" cy="{ocy:.1f}" r="2" fill="{NEBULA}"/></g>')
    c.add(c.anim(orbit, "fade", 0.6))
    if not STATIC:  # a satellite on the outer ring; decorative SMIL, gone under reduced motion
        c.add(f'<g class="smil" transform="rotate(-3 {ocx:.1f} {ocy:.1f})"><circle r="2.6" fill="{STAR}" opacity="0">'
              f'<set attributeName="opacity" to="1" begin="1.2s"/>'
              f'<animateMotion dur="16s" begin="1.2s" repeatCount="indefinite" path="{ring}"/></circle></g>')
    # huge light caps, top-aligned with the portrait
    c.text(tx - size * 0.04, by + cap, NAME[0], size, "g", delay=0.1, spacing=ls)
    c.text(tx - size * 0.04, by + cap + size * 0.86, NAME[1], size, "g", delay=0.25, spacing=ls)
    c.add(c.anim(sparkle(tx + 4, label_y - 4, 5, GOLD), "rise", 0.8))
    c.text(tx + 16, label_y, "MISSION CONTROL  /  EARTH", 10, "px", "mu", delay=0.8, spacing=1)
    c.text(W - 40, label_y, "SIGNAL: ONLINE", 10, "px", "ne", "end", delay=0.85, spacing=1)
    for n, line in enumerate(CAPTION):  # mono caption, bottom-aligned with the portrait
        c.text(tx, by + bh - (len(CAPTION) - 1 - n) * 20 - 3, line, 14, "m", delay=0.9 + n * 0.08)
    return c


def activity(s):
    months = s["months"]
    c = Card("activity", W, 440, "Flight log: contributions in the last 12 months",
             f"{plural(s['total'], 'contribution')} in the last 12 months. Current streak {plural(s['streak'], 'day')}, "
             f"{s['active']} of {s['days']} days active, busiest day {s['busiest']}.")
    sx = 612
    starfield(c, 40, avoid=[(32, 40, 590, 182), (32, 214, 572, 400), (sx - 6, 40, W - 30, 410)])
    b = 1.6
    c.text(40, 58, "FLIGHT LOG  /  LAST 12 MONTHS", 11, "px", "mu", delay=b, spacing=1)
    n = f"{s['total']:,}"
    size = 132
    c.text(36, 70 + size * 0.75, n, size, "g", delay=b + 0.1, spacing=-size * 0.03)
    nw = measure(n, size, "g", -size * 0.03)
    c.text(36 + nw + 14, 70 + size * 0.75, "CONTRIBUTIONS" if s["total"] != 1 else "CONTRIBUTION", 12, "mm", delay=b + 0.2, spacing=1)
    # bars: thrust columns, a nose cone on a fading trail; the busiest month in star-gold
    c.add(f'<defs><linearGradient id="thr" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{STAR}"/>'
          f'<stop offset="1" stop-color="{STAR}" stop-opacity=".18"/></linearGradient>'
          f'<linearGradient id="thrh" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{GOLD}"/>'
          f'<stop offset="1" stop-color="{GOLD}" stop-opacity=".25"/></linearGradient></defs>')
    x0, x1, base_y, top = 40, 560, 372, 232
    mx = max(max(months.values()), 1)
    slot = (x1 - x0) / 12
    c.add(f'<path d="M{x0} {base_y + .5}H{x1}" stroke="{MUTED}" stroke-width="1"/>')
    for i, ((yy, mm), v) in enumerate(months.items()):
        bw, bx = slot - 14, x0 + i * slot + 7
        hgt = max(v / mx * (base_y - top), 3)
        dl = b + 0.4 + i * 0.05
        hot = v == mx and v
        if v:
            nose = min(bw * 0.5, hgt * 0.5)
            col = GOLD if hot else STAR
            bar = (f'<path d="M{bx:.1f} {base_y:.1f}V{base_y - hgt + nose:.1f}L{bx + bw / 2:.1f} {base_y - hgt:.1f}'
                   f'L{bx + bw:.1f} {base_y - hgt + nose:.1f}V{base_y:.1f}Z" fill="url(#{"thrh" if hot else "thr"})"/>'
                   f'<path d="M{bx:.1f} {base_y - hgt + nose:.1f}L{bx + bw / 2:.1f} {base_y - hgt:.1f}L{bx + bw:.1f} '
                   f'{base_y - hgt + nose:.1f}Z" fill="{col}"/>')
        else:
            bar = f'<rect x="{bx:.1f}" y="{base_y - hgt:.1f}" width="{bw:.1f}" height="{hgt:.1f}" fill="{FAINT}"/>'
        c.add(bar if STATIC else f'<g class="grow" style="animation-delay:{dl:.2f}s">{bar}</g>')
        if hot:
            c.text(bx + bw / 2, base_y - hgt - 8, f"{v:,}", 12, "mm", "go", "middle", delay=dl + 0.3)
        c.text(bx + bw / 2, base_y + 20, dt.date(yy, mm, 1).strftime("%b").upper(), 10, "px", "mu", "middle", delay=dl)
    # right column: three figures separated by rules
    day_word = "DAY" if s["streak"] == 1 else "DAYS"
    items = [("CURRENT ORBIT", f"{s['streak']}", day_word, f"LONGEST {s['longest']}  /  DAY STREAK"),
             ("DAYS IN FLIGHT", f"{s['active']}", f"/ {s['days']}", "DAYS WITH A CONTRIBUTION"),
             ("PEAK THRUST", f"{s['busiest']}", "", "CONTRIBUTIONS IN ONE DAY")]
    for i, (lab, big, unit, sub) in enumerate(items):
        y = 58 + i * 118
        dl = b + 0.3 + i * 0.15
        c.add(f'<path d="M{sx - 22} {y - 22 + .5}H{W - 32}" stroke="{HAIR}" stroke-width="1"/>') if i else None
        c.text(sx, y, lab, 11, "px", "mu", delay=dl, spacing=1)
        c.text(sx, y + 52, big, 56, "g", delay=dl + 0.05, spacing=-1.6)
        bwid = measure(big, 56, "g", -1.6)
        if unit:
            c.text(sx + bwid + 8, y + 52, unit, 12, "mm", "mu", delay=dl + 0.1, spacing=1)
        c.text(sx, y + 74, sub, 10, "px", "mu", delay=dl + 0.1, spacing=0.5)
    if s["streak"]:
        c.add(f'<circle cx="{sx + measure("1", 56, "g") + 70:.0f}" cy="86" r="5" fill="{GOLD}"/>'
              + pulse(sx + measure("1", 56, "g") + 70, 86, 5, 15, b + 1.4))
    return c


STAR_R = [1.0, 1.7, 2.5, 3.4, 4.4]      # zero day speck .. busiest
STAR_O = [0.9, 0.55, 0.75, 0.9, 1.0]    # brightness per level (level 0 is drawn in FAINT)


def star_dot(cx, cy, lv):
    col = FAINT if lv == 0 else STAR
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{STAR_R[lv]}" fill="{col}" opacity="{STAR_O[lv]}"/>'


def graph(d, s):
    cal = d["calendar"]
    last = cal[-1]["d"]
    start = last - dt.timedelta(days=364)
    start -= dt.timedelta(days=(start.weekday() + 1) % 7)  # back to Sunday
    by = {x["d"]: x["count"] for x in cal}
    ncols = (last - start).days // 7 + 1
    gx, gy = 40, 146
    pitch = (W - 80) / ncols
    c = Card("graph", W, 330, "Every day, a star",
             f"Contribution star map for the last year: one star per day, bigger and brighter means more. "
             f"{plural(s['total'], 'contribution')} in the last 12 months.")
    label_y = gy + 7 * pitch + 16
    ly = label_y + 34
    starfield(c, 34, avoid=[(gx - 4, gy - 6, W - 36, label_y + 6), (32, 44, 420, 124),
                            (W - 200, 44, W - 32, 64), (W - 240, ly - 16, W - 32, ly + 6)])
    b = 2.9
    c.text(40, 58, "STAR MAP  /  ONE STAR PER DAY", 11, "px", "mu", delay=b, spacing=1)
    c.text(W - 40, 58, "REFRESHED DAILY", 11, "px", "mu", "end", delay=b + 0.05, spacing=1)
    c.text(36, 114, "Every day, a star.", 48, "g", delay=b + 0.05, spacing=-1)
    nz = sorted(v for v in by.values() if v)

    def level(v):
        if not v:
            return 0
        if len(nz) < 4:
            return min(4, 1 + v // 3)
        q = [nz[int(len(nz) * p)] for p in (0.25, 0.5, 0.75)]
        return 1 + sum(v > t for t in q)

    top_day = max(by, key=lambda k: by[k]) if any(by.values()) else None
    top_xy = None
    lastm = None
    for col in range(ncols):
        wk = start + dt.timedelta(days=7 * col)
        dots = []
        for row in range(7):
            day = wk + dt.timedelta(days=row)
            if day > last:
                continue
            lv = level(by.get(day, 0))
            cx, cy = gx + col * pitch + pitch / 2, gy + row * pitch + pitch / 2
            if day == top_day:
                top_xy = (cx, cy)
                dots.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{STAR_R[4] + .4}" fill="{GOLD}"/>'
                            + sparkle(cx, cy, 9, GOLD))
            else:
                dots.append(star_dot(cx, cy, lv))
        c.add(c.anim("".join(dots), "pop", b + 0.25 + col * 0.02))
        first = next((wk + dt.timedelta(days=i) for i in range(7) if (wk + dt.timedelta(days=i)).day == 1), None)
        if first and 0 < col < ncols - 3 and first.month != lastm:
            c.text(gx + col * pitch, label_y, first.strftime("%b").upper(), 10, "px", "mu", delay=b + 0.3 + col * 0.015)
            lastm = first.month
    if top_xy:
        c.add(pulse(top_xy[0], top_xy[1], 6, 18, begin=b + 1.6))
        c.text(40, ly, f"BRIGHTEST STAR  /  {top_day.strftime('%d %b %Y').upper()}  /  {by[top_day]}",
               10, "px", "go", delay=b + 1.4, spacing=0.5)
    # legend: LESS . o O @ MORE, drawn with the same marks as the map
    xe = W - 40
    c.text(xe, ly, "MORE", 10, "px", "mu", "end", delay=b + 1.4, spacing=0.5)
    x = xe - measure("MORE", 10, "px", 0.5) - 14
    for k in range(4, -1, -1):
        c.add(c.anim(star_dot(x, ly - 4, k), "pop", b + 1.4 + (4 - k) * 0.04))
        x -= 18
    c.text(x + 2, ly, "LESS", 10, "px", "mu", "end", delay=b + 1.4, spacing=0.5)
    return c


def tile(i, spec):
    name, idx, label, roman, sub, href, bg, fg, border = spec
    c = Card(name, THIRD, 200, f"{label.title()}: {roman}", sub, bg=bg, border=border, ink=fg)
    accent = bg == NEBULA
    mu = "" if accent else "mu"  # blue-grey is too weak on violet; use the dark ink there
    starfield(c, 6 if accent else 14, avoid=[(26, 38, THIRD - 26, 62), (24, 94, THIRD - 24, 138), (26, 150, THIRD - 24, 170)],
              color=SPACE if accent else STAR, twinkle=0 if accent else 2)
    b = 4.1 + i * 0.12
    c.text(32, 54, f"PROBE {idx}  /  {label}", 11, "px", mu, delay=b, spacing=1)
    c.add(c.anim(arrow(THIRD - 32 - 18, 38, fg), "rise", b))
    text = roman.upper()
    size = 38
    while size > 20 and measure(text, size, "g", -size * 0.02) > THIRD - 64:
        size -= 1
    c.text(30, 130, text, size, "g", delay=b + 0.1, spacing=-size * 0.02)
    c.text(32, 164, sub, 10, "px", mu, delay=b + 0.2, spacing=0.5)
    return c


HEADING = "WHAT I'M LAUNCHING"


def heading(theme):
    # transparent: drawn on GitHub's page, white (#ffffff) or dark (#0d1117)
    ink, acc = (STAR, NEBULA) if theme == "dark" else (INK_L, NEBULA_L)
    c = Card(f"title-building-{theme}", W, 76, HEADING.capitalize().replace("i'm", "I'm"), "Section heading", bg=None, ink=ink)
    b = 4.7
    c.add(c.anim(sparkle(PAD + 14, 39.5, 6, acc), "rise", b))
    c.text(PAD + 28, 44, HEADING, 13, "mm", delay=b, spacing=2)
    c.text(W - PAD - 8, 44, "(03)", 13, "px", "", "end", delay=b + 0.05)
    c.add(c.anim(f'<path d="M{PAD + 8} 58.5H{W - PAD - 24}" stroke="{ink}" stroke-width="1"/>'
                 f'<circle cx="{W - PAD - 14}" cy="58.5" r="3.5" fill="{acc}"/>', "fade", b + 0.1))
    return c


def repo_card(i, r, total):
    c = Card("repo-" + r["name"], W, 156, r["name"], f"{r['name']}: {r['description'] or 'repository'}")
    starfield(c, 24, avoid=[(34, 44, 84, 66), (84, 28, 570, 72), (84, 80, 572, 150),
                            (W - 66, 32, W - 34, 64), (W - 230, 86, W - 34, 128)])
    b = 5.0 + i * 0.2
    c.text(40, 60, f"L-{i + 1:02d}", 11, "px", "go", delay=b, spacing=1)
    c.text(88, 64, r["name"], 32, "g", delay=b, spacing=-0.6)
    c.add(c.anim(arrow(W - 40 - 18, 40, STAR), "rise", b))
    desc = r["description"] or "No description yet."
    for n, line in enumerate(wrap(desc, 14, "gr", 470, 3)):
        c.text(88, 96 + n * 21, line, 14, "gr", "" if r["description"] else "mu", delay=b + 0.1 + n * 0.06)
    pushed = dt.date.fromisoformat(r["pushed"]).strftime("%b %Y").upper()
    meta = [r["language"].upper() or "—", (f"{r['stars']} STAR" + ("" if r["stars"] == 1 else "S")) if r["stars"] else f"UPDATED {pushed}"]
    for n, m in enumerate(meta):
        c.text(W - 40, 102 + n * 20, m, 11, "px", "" if n == 0 else "mu", "end", delay=b + 0.25 + n * 0.05, spacing=0.5)
    return c


# ---- README / preview -----------------------------------------------------------------
def page(d, ver, src):
    u = lambda n: f'{src}{n}.svg' + (f'?v={ver}' if ver else '')
    tiles = "".join(f'<a href="{t[5]}"><img src="{u(t[0])}" width="33.333%" alt="{t[2].title()}: {t[3]}" /></a>' for t in TILES)
    repos = "<br>\n".join(f'<a href="{r["url"]}"><img src="{u("repo-" + r["name"])}" width="100%" alt="{r["name"]}" /></a>'
                          for r in d["repos"])
    return f"""<!-- Every card is an animated SVG drawn by scripts/render_cards.py and refreshed daily by
     .github/workflows/refresh-cards.yml. Spacing is baked into the SVGs, so keep the cards in a
     row on one line with no spaces between them. -->
<div align="center">
<a href="{SITE[1]}"><img src="{u('hero')}" width="100%" alt="{d['name']}. {ALT_ABOUT}" /></a><br>
<img src="{u('activity')}" width="100%" alt="Flight log: contributions per month for the last 12 months, with streak, active days and busiest day" /><br>
<img src="{u('graph')}" width="100%" alt="Contribution star map for the last year, one star per day, refreshed daily" /><br>
{tiles}<br>
<picture><source media="(prefers-color-scheme: dark)" srcset="{u('title-building-dark')}" /><img src="{u('title-building-light')}" width="100%" alt="What I'm launching" /></picture><br>
{repos}
</div>

<p align="center">
<sub>— transmitting from Earth —</sub><br>
<a href="{SITE[1]}">{SITE[0]}</a> &nbsp;/&nbsp; <a href="{LINKEDIN[1]}">linkedin</a> &nbsp;/&nbsp; <a href="mailto:{EMAIL}">email</a>
</p>
"""


def main():
    d = load()
    s = stats(d["calendar"])
    if not STATIC and os.path.isdir(OUT):
        for n in os.listdir(OUT):  # drop cards left over from older designs
            if n.endswith(".svg"):
                os.remove(os.path.join(OUT, n))
    cards = [hero(d), activity(s), graph(d, s)] + [tile(i, t) for i, t in enumerate(TILES)]
    cards += [heading("light"), heading("dark")] + [repo_card(i, r, len(d["repos"])) for i, r in enumerate(d["repos"])]
    for c in cards:
        print(f"{c.name:28s}{c.save():>8,} bytes")
    if STATIC:
        with open(os.path.join(OUT, "index.html"), "w") as f:
            f.write('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                    '<title>Preview</title><style>body{max-width:830px;margin:24px auto;background:#0d1117;'
                    'font-family:sans-serif;color:#9aa}a{color:#6ea8ff}img{vertical-align:top}</style>'
                    + page(d, "", "").replace("title-building-light", "title-building-dark"))  # preview page is dark
        print(f"\nStatic preview: open {os.path.join(OUT, 'index.html')}")
        return
    h = hashlib.sha1()
    for n in sorted(os.listdir(OUT)):
        h.update(open(os.path.join(OUT, n), "rb").read())
    with open(os.path.join(ROOT, "README.md"), "w") as f:
        f.write(page(d, h.hexdigest()[:8], "cards/"))  # ?v= busts GitHub's image cache


if __name__ == "__main__":
    main()
