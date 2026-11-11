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
"""
import base64, datetime as dt, hashlib, html, io, json, os, subprocess, sys, tempfile
from collections import OrderedDict

from fontTools.ttLib import TTFont

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
STATIC = os.environ.get("STATIC") == "1"
OUT = os.path.join(ROOT, "preview" if STATIC else "cards")

# ---- identity ---------------------------------------------------------------------
KICKER = "SENIOR SOFTWARE ENGINEER AT NAUKRI.COM"
ABOUT = "I build software at Naukri.com and explore machine learning, blockchain and AR/VR on the side."
SITE = ("yashsrivastav.vercel.app", "https://yashsrivastav.vercel.app/")
LINKEDIN = "https://www.linkedin.com/in/yash-stv/"
EMAIL = "iyashsrivastav@gmail.com"
# Palette: off-white cards, one ink, one blue, plus red and yellow for the tiles.
PAPER, INK, MUTED, LINE = "#f4f4f2", "#111111", "#6f6f6a", "#e2e2dd"
BLUE, RED, YELLOW = "#3a55f5", "#e04e3b", "#f5c94a"
CELLS = ["#e2e2dd", "#c8cffb", "#93a2f9", "#5d74f7", "#2a40e0"]  # contribution levels 0..4
TILES = [  # (file, kicker, roman, italic, text, href, background, text colour)
    ("tile-portfolio", "PORTFOLIO", "See my ", "work", "Projects, experience and skills in one place.", SITE[1], BLUE, "#ffffff"),
    ("tile-linkedin", "LINKEDIN", "Say ", "hello", "My experience, projects and professional network.", LINKEDIN, RED, "#ffffff"),
    ("tile-email", "EMAIL", "Write to ", "me", EMAIL, "mailto:" + EMAIL, YELLOW, INK),
]
W = 830          # full-width canvas
PAD = 8          # transparent gutter baked around every card
THIRD = 277      # canvas width of a card shown at 33.333%

FONT_DIR = os.path.join(ROOT, "assets", "fonts")
FONTS = {  # face -> (file, family, css weight, css style)
    "d": ("instrument-serif-latin-400-normal.woff2", "Instrument Serif", 400, "normal"),
    "di": ("instrument-serif-latin-400-italic.woff2", "Instrument Serif", 400, "italic"),
    "s": ("inter-latin-400-normal.woff2", "Inter", 400, "normal"),
    "sb": ("inter-latin-600-normal.woff2", "Inter", 600, "normal"),
    "m": ("ibm-plex-mono-latin-400-normal.woff2", "IBM Plex Mono", 400, "normal"),
}
_ttf = {k: TTFont(os.path.join(FONT_DIR, v[0])) for k, v in FONTS.items()}


def measure(s, size, face="s", spacing=0):
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
                        "--flavor=woff2", "--layout-features=kern,liga", "--no-hinting",
                        f"--output-file={out}"], check=True)
        return "data:font/woff2;base64," + base64.b64encode(open(out, "rb").read()).decode()


CSS_BASE = f"""
text{{fill:{INK};white-space:pre}}
.f-d{{font-family:'Instrument Serif',Georgia,serif}}
.f-di{{font-family:'Instrument Serif',Georgia,serif;font-style:italic}}
.f-s{{font-family:Inter,system-ui,sans-serif}} .f-sb{{font-family:Inter,system-ui,sans-serif;font-weight:600}}
.f-m{{font-family:'IBM Plex Mono',ui-monospace,Menlo,monospace}}
.mu{{fill:{MUTED}}} .bl{{fill:{BLUE}}} .wh{{fill:#fff}}
.st{{fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}}
"""
CSS_ANIM = """
@keyframes rise{from{opacity:0;transform:translateY(12px)}}
@keyframes grow{from{transform:scaleY(0)}}
@keyframes pop{from{opacity:0;transform:scale(.3)}}
@keyframes fade{from{opacity:0}}
.rise{animation:rise .75s cubic-bezier(.2,.7,.2,1) both}
.fade{animation:fade .6s ease-out both}
.grow{animation:grow .85s cubic-bezier(.2,.7,.2,1) both;transform-box:fill-box;transform-origin:50% 100%}
.pop{animation:pop .45s cubic-bezier(.3,1.4,.5,1) both;transform-box:fill-box;transform-origin:center}
@media (prefers-reduced-motion:reduce){*{animation:none!important}.smil{display:none}}
"""


class Card:
    """A canvas of w x h with a card inset by PAD (bg=None for a bare heading)."""

    def __init__(self, name, w, h, title, desc, bg=PAPER, ink=INK):
        self.name, self.w, self.h, self.title, self.desc, self.bg, self.ink = name, w, h, title, desc, bg, ink
        self.parts, self.chars = [], {k: set() for k in FONTS}

    def add(self, s):
        self.parts.append(s)

    def anim(self, inner, cls, delay):
        return inner if STATIC else f'<g class="{cls}" style="animation-delay:{delay:.2f}s">{inner}</g>'

    def text(self, x, y, s, size, face="s", cls="", anchor="start", delay=None, spacing=0):
        if not s:
            return
        self.chars[face].update(s)
        c = " ".join(filter(None, [f"f-{face}", cls]))
        ls = f' letter-spacing="{spacing}"' if spacing else ""
        t = f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}"{ls} text-anchor="{anchor}" class="{c}">{html.escape(s)}</text>'
        self.add(self.anim(t, "rise", delay) if delay is not None else t)

    def mixed(self, x, y, size, parts, delay=None):
        """Consecutive runs [(text, face, cls)] on one baseline; returns the end x."""
        for s, face, cls in parts:
            self.text(x, y, s, size, face, cls, delay=delay)
            x += measure(s, size, face)
        return x

    def svg(self):
        faces = "".join(
            f'@font-face{{font-family:"{FONTS[k][1]}";font-weight:{FONTS[k][2]};font-style:{FONTS[k][3]};'
            f'src:url({subset_font(k, chars | {" "})}) format("woff2")}}'
            for k, chars in self.chars.items() if chars)
        css = faces + CSS_BASE.replace(f"fill:{INK};white", f"fill:{self.ink};white") + ("" if STATIC else CSS_ANIM)
        rect = (f'<rect x="{PAD}" y="{PAD}" width="{self.w - 2*PAD}" height="{self.h - 2*PAD}" rx="28" '
                f'fill="{self.bg}" stroke="{LINE}"/>') if self.bg else ""
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


def pulse(cx, cy, r0, r1, begin):
    """Decorative SMIL ring. Hidden under prefers-reduced-motion; omitted in STATIC."""
    if STATIC:
        return ""
    return (f'<circle class="smil" cx="{cx:.1f}" cy="{cy:.1f}" r="{r0}" fill="none" stroke="{BLUE}" stroke-width="2" opacity="0">'
            f'<animate attributeName="r" values="{r0};{r1}" dur="2.8s" repeatCount="indefinite" begin="{begin}s"/>'
            f'<animate attributeName="opacity" values="0.6;0" dur="2.8s" repeatCount="indefinite" begin="{begin}s"/></circle>')


def arrow(x, y, color):
    return f'<g transform="translate({x:.1f} {y:.1f})" style="color:{color}"><path class="st" d="M4 14L14 4M6 4h8v8"/></g>'


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


# ---- ASCII portrait -----------------------------------------------------------------
RAMP = " .`:-=+*cs#%@"  # sparse -> dense
ROW_ASPECT = 15 / 8  # row pitch / character width of one ASCII cell
PORTRAIT_SECS = 2.0  # how long the portrait takes to print
PORTRAIT_TXT = os.path.join(ROOT, "assets", "portrait.txt")  # made once by scripts/make_portrait.py


def to_ascii(lum, cols, rows, dense_dark=True, gamma=1.18, white_floor=0.80):
    """Greyscale image -> rows of characters. Near-white is forced blank so backgrounds vanish."""
    from PIL import Image
    img = lum.resize((cols, rows), Image.LANCZOS)
    out = []
    for y in range(rows):
        line = ""
        for x in range(cols):
            v = (img.getpixel((x, y)) / 255) ** gamma
            if not dense_dark:
                v = 1 - v
            line += " " if v >= white_floor else RAMP[max(0, min(len(RAMP) - 1, int((1 - v) * (len(RAMP) - 1) + 0.5)))]
        out.append(line)
    return out


def avatar_rows(data_uri, cols, rows):
    """Fallback: ASCII of the GitHub avatar, weighting brightness by (1 - saturation) so pale subjects
    stand out from glowing coloured backdrops."""
    try:
        from PIL import ImageChops, Image
    except ImportError:
        return None
    src = Image.open(io.BytesIO(base64.b64decode(data_uri.split(",", 1)[1]))).convert("RGB")
    hsv = src.convert("HSV")
    lum = ImageChops.multiply(hsv.getchannel("V"), hsv.getchannel("S").point(lambda v: 255 - int(0.95 * v)))
    w, h = lum.size
    s = int(min(w, h) * 0.86)
    lum = lum.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
    return to_ascii(lum, cols, rows, dense_dark=False, gamma=1.0, white_floor=0.99)


def portrait_rows(d, cols, rows):
    if os.path.exists(PORTRAIT_TXT):  # your own photo, converted once; no image needed in CI
        return open(PORTRAIT_TXT).read().split("\n")
    return avatar_rows(d["portrait"], cols, rows) if d.get("portrait") else None


# ---- cards ----------------------------------------------------------------------------
def hero(d):
    c = Card("hero", W, 440, d["name"], f"{d['name']}. {KICKER.title()}. {ABOUT}")
    c.add(c.anim(f'<rect x="40" y="48" width="14" height="14" rx="4" fill="{CELLS[1]}"/>', "fade", 0))
    c.text(68, 61, KICKER, 13, "m", "mu", delay=0.05, spacing=2)
    first, last = (d["name"].split(" ", 1) + [""])[:2]
    size = min(104, 380 / measure(last, 1, "di")) if last else 104
    c.text(38, 168, first, size, "d", delay=0.15)
    c.text(38, 168 + size * 0.88, last, size, "di", delay=0.3)
    ty = 168 + size * 0.88 + 46
    for n, line in enumerate(wrap(ABOUT, 17, "s", 370, 4)):
        c.text(40, ty + n * 25, line, 17, "s", "mu", delay=0.5 + n * 0.08)
    ly = ty + 25 * 3 + 40
    c.text(40, ly, SITE[0], 15, "m", delay=0.8)
    c.add(c.anim(arrow(40 + measure(SITE[0], 15, "m") + 12, ly - 14, BLUE), "rise", 0.85))
    art = portrait_rows(d, 120, round(120 / ROW_ASPECT))
    if art:
        cols, rows = max(len(x) for x in art), len(art)
        c.chars["m"].update("".join(art))
        cw = min(316 / cols, 372 / (rows * ROW_ASPECT))  # cell width: fit a 316 x 372 box
        ch = cw * ROW_ASPECT
        x0, y0, fs = 474, (440 - rows * ch) / 2, ch * 0.86
        rd = PORTRAIT_SECS / rows
        for r, line in enumerate(art):
            if not line.strip():
                continue
            ty = y0 + r * ch
            c.add(f'<text x="{x0}" y="{ty + ch * 0.74:.1f}" font-size="{fs:.2f}" class="f-m" opacity=".9" '
                  f'textLength="{len(line) * cw:.1f}" lengthAdjust="spacing">{html.escape(line)}</text>')
            if not STATIC:  # a paper-coloured cover shrinks away left to right, with a cursor on its edge
                t0 = 0.3 + r * rd
                c.add(f'<rect class="smil" x="{x0}" y="{ty:.1f}" height="{ch + .6:.2f}" width="{cols * cw:.1f}" fill="{PAPER}">'
                      f'<animate attributeName="x" from="{x0}" to="{x0 + cols * cw:.1f}" begin="{t0:.3f}s" dur="{rd:.3f}s" fill="freeze"/>'
                      f'<animate attributeName="width" from="{cols * cw:.1f}" to="0" begin="{t0:.3f}s" dur="{rd:.3f}s" fill="freeze"/></rect>'
                      f'<rect class="smil" y="{ty + .5:.1f}" width="{max(cw * 2, 3):.1f}" height="{ch - 1:.2f}" fill="{INK}" opacity="0">'
                      f'<animate attributeName="x" from="{x0}" to="{x0 + cols * cw:.1f}" begin="{t0:.3f}s" dur="{rd:.3f}s" fill="freeze"/>'
                      f'<set attributeName="opacity" to=".8" begin="{t0:.3f}s"/><set attributeName="opacity" to="0" begin="{t0 + rd:.3f}s"/></rect>')
    return c


def graph(d, s):
    cal = d["calendar"]
    last = cal[-1]["d"]
    start = last - dt.timedelta(days=364)
    start -= dt.timedelta(days=(start.weekday() + 1) % 7)  # back to Sunday
    by = {x["d"]: x["count"] for x in cal}
    ncols = (last - start).days // 7 + 1
    gx, gy = 40, 112
    pitch = (W - 80) / ncols
    cell = pitch - 3
    c = Card("graph", W, 290, "Every day, in blue",
             f"Contribution graph for the last year, {plural(s['total'], 'contribution')} in the last 12 months.")
    b = 2.5
    c.mixed(38, 78, 44, [("Every day, ", "d", ""), ("in blue", "di", "bl")], delay=b)
    c.text(W - 40, 70, "REFRESHED DAILY", 12, "m", "mu", "end", delay=b + 0.05, spacing=2)
    nz = sorted(v for v in by.values() if v)

    def level(v):
        if not v:
            return 0
        if len(nz) < 4:
            return min(4, 1 + v // 3)
        q = [nz[int(len(nz) * p)] for p in (0.25, 0.5, 0.75)]
        return 1 + sum(v > t for t in q)

    label_y = gy + 7 * pitch + 22
    lastm = None
    for col in range(ncols):
        wk = start + dt.timedelta(days=7 * col)
        rects = []
        for row in range(7):
            day = wk + dt.timedelta(days=row)
            if day > last:
                continue
            rects.append(f'<rect x="{gx + col * pitch:.1f}" y="{gy + row * pitch:.1f}" width="{cell:.1f}" '
                         f'height="{cell:.1f}" rx="3.5" fill="{CELLS[level(by.get(day, 0))]}"/>')
        c.add(c.anim("".join(rects), "pop", b + 0.2 + col * 0.025))
        first = next((wk + dt.timedelta(days=i) for i in range(7) if (wk + dt.timedelta(days=i)).day == 1), None)
        if first and 0 < col < ncols - 3 and first.month != lastm:
            c.text(gx + col * pitch, label_y, first.strftime("%b"), 13, "m", "mu", delay=b + 0.3 + col * 0.02)
            lastm = first.month
    tcol, trow = (last - start).days // 7, (last - start).days % 7
    c.add(pulse(gx + tcol * pitch + cell / 2, gy + trow * pitch + cell / 2, 6, 16, begin=b + 2.2))
    ly = label_y + 30  # legend: less [5 swatches] more
    x = W - 40 - measure("more", 13, "m") - 8 - 5 * 18 - 4 - measure("less", 13, "m") - 8
    c.text(x, ly, "less", 13, "m", "mu", delay=b + 1.8)
    x += measure("less", 13, "m") + 10
    for k in range(5):
        c.add(c.anim(f'<rect x="{x + k * 18:.1f}" y="{ly - 11}" width="14" height="14" rx="4" fill="{CELLS[k]}"/>',
                     "pop", b + 1.8 + k * 0.05))
    c.text(x + 5 * 18 + 4, ly, "more", 13, "m", "mu", delay=b + 1.8)
    return c


def activity(s):
    months = s["months"]
    c = Card("activity", W, 456, "Contributions in the last 12 months",
             f"{plural(s['total'], 'contribution')} in the last 12 months. Current streak {plural(s['streak'], 'day')}, "
             f"{s['active']} of {s['days']} days active, busiest day {s['busiest']}.")
    b = 4.1
    c.text(40, 66, "THE LAST 12 MONTHS ON GITHUB", 13, "m", "mu", delay=b, spacing=2)
    n, word = f"{s['total']:,} ", "contribution" + ("" if s["total"] == 1 else "s")
    size = min(78, 540 / (measure(n, 1, "d") + measure(word, 1, "di")))
    c.mixed(38, 90 + size * 0.78, size, [(n, "d", ""), (word, "di", "")], delay=b + 0.1)
    x0, x1, base_y, top = 40, 566, 392, 176
    mx = max(max(months.values()), 1)
    slot = (x1 - x0) / 12
    for i, ((yy, mm), v) in enumerate(months.items()):
        bw, bx = slot - 9, x0 + i * slot + 4.5
        hgt = max(v / mx * (base_y - top), 10 if not v else 8)
        fill = BLUE if v == mx and v else (INK if v else "#cfcfc9")
        dl = b + 0.35 + i * 0.06
        bar = f'<rect x="{bx:.1f}" y="{base_y - hgt:.1f}" width="{bw:.1f}" height="{hgt:.1f}" rx="5" fill="{fill}"/>'
        c.add(bar if STATIC else f'<g class="grow" style="animation-delay:{dl:.2f}s">{bar}</g>')
        if v == mx and v:
            c.text(bx + bw / 2, base_y - hgt - 10, f"{v:,}", 14, "m", "bl", "middle", delay=dl + 0.3)
        c.text(bx + bw / 2, base_y + 28, dt.date(yy, mm, 1).strftime("%b"), 13, "m", "mu", "middle", delay=dl)
    sx = 628
    day_word = "day" if s["streak"] == 1 else "days"
    blocks = [
        ([(f"{s['streak']} ", "d", ""), (day_word, "di", "")], f"current streak, longest {s['longest']}"),
        ([(f"{s['active']}", "d", ""), (f" / {s['days']}", "d", "mu")], "days with a contribution"),
        ([(f"{s['busiest']}", "d", "")], "on the busiest day"),
    ]
    for i, (parts, sub) in enumerate(blocks):
        y, dl = 128 + i * 124, b + 0.4 + i * 0.18
        c.mixed(sx, y, 56, parts, delay=dl)
        c.text(sx, y + 28, sub, 14, "s", "mu", delay=dl + 0.1)
        if i < 2:
            c.add(f'<path d="M{sx} {y + 52}H{W - 40}" stroke="{LINE}" stroke-width="1.5"/>')
    if s["streak"]:
        tx = sx + measure(f"{s['streak']} {day_word}", 56, "d") + 18
        c.add(f'<circle cx="{tx:.0f}" cy="104" r="5" fill="{BLUE}"/>' + pulse(tx, 104, 5, 15, b + 1.4))
    return c


def tile(i, spec):
    name, kicker, roman, ital, text, href, bg, fg = spec
    c = Card(name, THIRD, 216, f"{kicker.title()}: {roman}{ital}", text, bg=bg)
    cls = "wh" if fg == "#ffffff" else ""
    b = 4.8 + i * 0.12
    c.text(32, 58, kicker, 12, "m", cls, delay=b, spacing=2)
    c.add(c.anim(arrow(THIRD - 32 - 18, 42, fg), "rise", b))
    size = 50
    while size > 20 and measure(roman, size, "d") + measure(ital, size, "di") > THIRD - 64:
        size -= 1
    c.mixed(30, 128, size, [(roman, "d", cls), (ital, "di", cls)], delay=b + 0.1)
    for n, line in enumerate(wrap(text, 14, "s", THIRD - 64, 3)):
        c.text(32, 164 + n * 20, line, 14, "s", cls, delay=b + 0.2 + n * 0.06)
    return c


def heading(theme):
    ink = PAPER if theme == "dark" else INK
    c = Card(f"title-building-{theme}", W, 100, "What I'm building", "Section heading", bg=None, ink=ink)
    c.mixed(20, 70, 48, [("What I'm ", "d", ""), ("building", "di", "")], delay=5.4)
    return c


def repo_card(i, r, H):
    dot = [BLUE, RED, YELLOW][i % 3]
    c = Card("repo-" + r["name"], THIRD, H, r["name"], f"{r['name']}: {r['description'] or 'repository'}")
    b = 5.7 + i * 0.15
    c.add(c.anim(f'<rect x="32" y="49" width="12" height="12" rx="3.5" fill="{dot}"/>', "pop", b))
    c.text(54, 61, r["name"], 17, "sb", delay=b)
    for n, line in enumerate(wrap(r["description"] or "No description yet.", 14, "s", THIRD - 64, 4)):
        c.text(32, 98 + n * 21, line, 14, "s", "" if r["description"] else "mu", delay=b + 0.1 + n * 0.06)
    tail = plural(r["stars"], "star") if r["stars"] else dt.date.fromisoformat(r["pushed"]).strftime("%b %Y")
    c.text(32, H - 36, " · ".join(x for x in [r["language"], tail] if x), 12, "m", "mu", delay=b + 0.3)
    return c


# ---- README / preview -----------------------------------------------------------------
def page(d, ver, src):
    u = lambda n: f'{src}{n}.svg' + (f'?v={ver}' if ver else '')
    tiles = "".join(f'<a href="{t[5]}"><img src="{u(t[0])}" width="33.333%" alt="{t[1].title()}: {t[2]}{t[3]}" /></a>'
                    for t in TILES)
    repos = "".join(f'<a href="{r["url"]}"><img src="{u("repo-" + r["name"])}" width="33.333%" alt="{r["name"]}" /></a>'
                    for r in d["repos"])
    return f"""<!-- Every card is an animated SVG drawn by scripts/render_cards.py and refreshed daily by
     .github/workflows/refresh-cards.yml. Spacing is baked into the SVGs, so keep the cards in a
     row on one line with no spaces between them. -->
<div align="center">
<a href="{SITE[1]}"><img src="{u('hero')}" width="100%" alt="{d['name']}. {KICKER.title()}. {ABOUT}" /></a><br>
<img src="{u('graph')}" width="100%" alt="Contribution graph for the last year, in blue, refreshed daily" /><br>
<img src="{u('activity')}" width="100%" alt="Contributions per month for the last 12 months, with streak, active days and busiest day" /><br>
{tiles}<br>
<picture><source media="(prefers-color-scheme: dark)" srcset="{u('title-building-dark')}" /><img src="{u('title-building-light')}" width="100%" alt="What I'm building" /></picture><br>
{repos}
</div>

<p align="center">
<a href="{SITE[1]}">{SITE[0]}</a> &nbsp;/&nbsp; <a href="{LINKEDIN}">linkedin</a> &nbsp;/&nbsp; <a href="mailto:{EMAIL}">email</a>
</p>
"""


def main():
    d = load()
    s = stats(d["calendar"])
    if not STATIC and os.path.isdir(OUT):
        for n in os.listdir(OUT):  # drop cards left over from older designs
            if n.endswith(".svg"):
                os.remove(os.path.join(OUT, n))
    maxlines = max(len(wrap(r["description"] or "No description yet.", 14, "s", THIRD - 64, 4)) for r in d["repos"])
    H = 98 + (maxlines - 1) * 21 + 24 + 36 + 14  # equal height so the row lines up
    cards = [hero(d), graph(d, s), activity(s)] + [tile(i, t) for i, t in enumerate(TILES)]
    cards += [heading("light"), heading("dark")] + [repo_card(i, r, H) for i, r in enumerate(d["repos"])]
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
