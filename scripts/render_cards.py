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
"""
import base64, datetime as dt, hashlib, html, json, os, subprocess, sys, tempfile
from collections import OrderedDict

from fontTools.ttLib import TTFont

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
STATIC = os.environ.get("STATIC") == "1"
OUT = os.path.join(ROOT, "preview" if STATIC else "cards")

# ---- identity ---------------------------------------------------------------
# Fonts/colours follow https://yashsrivastav.vercel.app (its style.css): Fira Code,
# --color-purple #8000ff, --color-dark-mode #11111b, --color-light-mode #ece7e1.
BRAND = "#8000ff"        # light theme
BRAND_DARK = "#a566ff"   # dark theme (site purple lifted for contrast on #11111b)
ABOUT = "Senior Software Engineer at Naukri.com. CS and AI graduate from India."
LINKS = [  # (file, kicker, title, href, icon)
    ("tile-portfolio", "PORTFOLIO", "See my work", "https://yashsrivastav.vercel.app/", "globe"),
    ("tile-linkedin", "LINKEDIN", "Say hello", "https://www.linkedin.com/in/yash-stv/", "in"),
    ("tile-email", "EMAIL", "Write to me", "mailto:iyashsrivastav@gmail.com", "mail"),
]
W = 830  # card width in user units; <img width=100%> scales it

FONTS = {  # face -> (source file, css weight, css style). Fira Code has no italic.
    "r": ("FiraCode-Regular.ttf", 400, "normal"),
    "b": ("FiraCode-Bold.ttf", 700, "normal"),
}
FONT_DIR = os.path.join(ROOT, "assets", "fonts")
_ttf = {k: TTFont(os.path.join(FONT_DIR, v[0])) for k, v in FONTS.items()}


def measure(s, size, face="r"):
    f = _ttf[face]
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    return sum(hmtx[cmap.get(ord(c), ".notdef")][0] for c in s) * size / upm


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
                        "--desubroutinize", f"--output-file={out}"], check=True)
        return "data:font/woff2;base64," + base64.b64encode(open(out, "rb").read()).decode()


CSS_BASE = f"""
svg{{--paper:#ece7e1;--ink:#11111b;--muted:#5f5a66;--line:#d3ccc2;--brand:{BRAND};--cell:#11111b14}}
@media (prefers-color-scheme:dark){{svg{{--paper:#11111b;--ink:#ece7e1;--muted:#9c9aab;--line:#27273a;--brand:{BRAND_DARK};--cell:#ece7e112}}}}
.card{{fill:var(--paper);stroke:var(--line)}}
text{{fill:var(--ink);font-family:'Fira Code',ui-monospace,Menlo,Consolas,monospace}}
.m{{fill:var(--muted)}} .br{{fill:var(--brand)}}
.st{{fill:none;stroke:var(--ink);stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}}
"""
CSS_ANIM = """
@keyframes rise{from{opacity:0;transform:translateY(10px)}}
@keyframes grow{from{transform:scaleY(0)}}
@keyframes pop{from{opacity:0;transform:scale(.2)}}
@keyframes draw{from{stroke-dashoffset:1}}
@keyframes fade{from{opacity:0}}
.rise{animation:rise .7s cubic-bezier(.2,.7,.2,1) both}
.fade{animation:fade .8s ease-out both}
.grow{animation:grow .8s cubic-bezier(.2,.7,.2,1) both;transform-box:fill-box;transform-origin:50% 100%}
.pop{animation:pop .45s cubic-bezier(.3,1.4,.5,1) both;transform-box:fill-box;transform-origin:center}
.draw{stroke-dasharray:1;animation:draw .9s ease-out both}
@media (prefers-reduced-motion:reduce){*{animation:none!important}.smil{display:none}}
"""


class Card:
    def __init__(self, name, w, h, title, desc):
        self.name, self.w, self.h, self.title, self.desc = name, w, h, title, desc
        self.parts, self.chars = [], {k: set() for k in FONTS}

    def add(self, s):
        self.parts.append(s)

    def a(self, cls, delay):  # animation class + delay attributes (no-ops in STATIC)
        return "" if STATIC else f' class="{cls}" style="animation-delay:{delay:.2f}s"'

    def text(self, x, y, s, size, face="r", cls="", anchor="start", delay=None, spacing=0):
        if not s:
            return
        face = "r" if face == "i" else face  # no italic in Fira Code; "m" colour carries the emphasis
        self.chars[face].update(s)
        fam = {"r": "", "b": ' font-weight="700"'}[face]
        c = f' class="{cls}"' if cls else ""
        ls = f' letter-spacing="{spacing}"' if spacing else ""
        t = (f'<text x="{x}" y="{y}" font-size="{size}"{fam}{ls} text-anchor="{anchor}"{c}>'
             f'{html.escape(s)}</text>')
        self.add(self.wrapg(t, "rise", delay) if delay is not None else t)

    def wrapg(self, inner, cls, delay):
        return f'<g{self.a(cls, delay)}>{inner}</g>' if not STATIC else inner

    def svg(self):
        faces = "".join(
            f'@font-face{{font-family:"Fira Code";font-weight:{FONTS[k][1]};font-style:{FONTS[k][2]};'
            f'src:url({subset_font(k, chars | {" "})}) format("woff2")}}'
            for k, chars in self.chars.items() if chars)
        css = faces + CSS_BASE + ("" if STATIC else CSS_ANIM)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" role="img" aria-labelledby="t d">'
                f'<title id="t">{html.escape(self.title)}</title><desc id="d">{html.escape(self.desc)}</desc>'
                f'<style>{css}</style>'
                f'<rect class="card" x=".5" y=".5" width="{self.w-1}" height="{self.h-1}" rx="16"/>'
                + "".join(self.parts) + "</svg>")

    def save(self):
        os.makedirs(OUT, exist_ok=True)
        data = self.svg()
        with open(os.path.join(OUT, self.name + ".svg"), "w") as f:
            f.write(data)
        return len(data)


def pulse(cx, cy, r0, r1, begin=1.2, extra=""):
    """Decorative SMIL ring. Hidden under prefers-reduced-motion; omitted in STATIC."""
    if STATIC:
        return ""
    return (f'<circle class="smil" cx="{cx}" cy="{cy}" r="{r0}" fill="none" stroke="var(--brand)" stroke-width="2" opacity="0" {extra}>'
            f'<animate attributeName="r" values="{r0};{r1}" dur="2.8s" repeatCount="indefinite" begin="{begin}s"/>'
            f'<animate attributeName="opacity" values="0.55;0" dur="2.8s" repeatCount="indefinite" begin="{begin}s"/></circle>')


# ---- data -----------------------------------------------------------------------
def load():
    with open(os.path.join(ROOT, "data", "github.json")) as f:
        d = json.load(f)
    for x in d["calendar"]:
        x["d"] = dt.date.fromisoformat(x["date"])
    d["calendar"].sort(key=lambda x: x["d"])
    return d


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
    busiest = max(cal, key=lambda x: x["count"])
    return dict(streak=streak, longest=best, active=sum(1 for x in cal if x["count"]),
                total=sum(x["count"] for x in cal), busiest=busiest)


def fmt_day(d):
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b %Y')}"


def plural(n, w):
    return f"{n} {w}" + ("" if n == 1 else "s")


# ---- cards ------------------------------------------------------------------------
def hero(d):
    c = Card("hero", W, 240, d["name"], f"{d['name']}. {ABOUT}")
    has_p = bool(d.get("portrait"))
    c.text(48, 68, "Namaste();", 20, "r", "m", delay=0.0)
    c.text(46, 128, d["name"], 54, "b", delay=0.15)
    c.add(f'<path{c.a("draw", 0.55)} d="M48 148H{48 + min(measure(d["name"], 54, "b"), 380) * 0.6:.0f}" pathLength="1" '
          f'stroke="var(--brand)" stroke-width="4" stroke-linecap="round" fill="none"/>')
    for n, line in enumerate(wrap(ABOUT, 18, "r", 540 if has_p else 700, 2)):
        c.text(48, 188 + n * 28, line, 18, "r", "m", delay=0.35 + n * 0.1)
    if has_p:
        cx, cy, r = 706, 120, 76
        c.add(f'<defs><clipPath id="p"><circle cx="{cx}" cy="{cy}" r="{r}"/></clipPath></defs>')
        c.add(c.wrapg(f'<image href="{d["portrait"]}" x="{cx-r}" y="{cy-r}" width="{2*r}" height="{2*r}" '
                      f'clip-path="url(#p)" preserveAspectRatio="xMidYMid slice"/>'
                      f'<circle cx="{cx}" cy="{cy}" r="{r+5}" fill="none" stroke="var(--brand)" stroke-width="2.5"/>'
                      + pulse(cx, cy, r + 5, r + 20), "fade", 0.25))
    return c


ICONS = {
    "doc": '<path class="st" d="M6 3h8l4 4v14H6zM14 3v4h4M9 12h6M9 16h6"/>',
    "in": '<rect class="st" x="3" y="3" width="18" height="18" rx="4"/>',
    "globe": '<circle class="st" cx="12" cy="12" r="9"/><path class="st" d="M3 12h18M12 3c3.5 3 3.5 15 0 18M12 3c-3.5 3-3.5 15 0 18"/>',
    "mail": '<rect class="st" x="3" y="5" width="18" height="14" rx="2"/><path class="st" d="M3 7l9 6 9-6"/>',
}


def tile(i, spec):
    name, kicker, title, href, icon = spec
    c = Card(name, 270, 104, f"{title} ({kicker.title()})", f"Link: {title}")
    base = 0.45 + i * 0.12
    g = f'<g transform="translate(28 30) scale(1.5)">{ICONS[icon]}</g>'
    c.add(c.wrapg(g, "rise", base))
    if icon == "in":
        c.text(46, 55, "in", 17, "b", anchor="middle", delay=base)  # sits in the rounded square
    c.text(86, 44, kicker, 12, "b", "m", delay=base + 0.05, spacing=1.5)
    c.text(86, 74, title, 19, "b", delay=base + 0.1)
    arrow = '<path class="st" d="M232 52h16M242 45l7 7-7 7" stroke="var(--brand)"/>'
    c.add(c.wrapg(arrow, "rise", base + 0.2))
    return c


def activity(d, s):
    cal = d["calendar"]
    last = cal[-1]["d"]
    months = []  # last 12 calendar months ending with the latest data point
    y, m = last.year, last.month
    for _ in range(12):
        months.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    months.reverse()
    tot = OrderedDict((k, 0) for k in months)
    for x in cal:
        k = (x["d"].year, x["d"].month)
        if k in tot:
            tot[k] += x["count"]
    total = sum(tot.values())
    c = Card("activity", W, 310, "Contributions per month",
             f"{total} contributions in the last 12 months; current streak {plural(s['streak'], 'day')}, "
             f"{s['active']} active days, busiest day {s['busiest']['count']} on {fmt_day(s['busiest']['d'])}.")
    c.text(40, 52, "Contributions per month", 22, "b", delay=0.8)
    c.text(40, 78, f"{plural(total, 'contribution')} over the last 12 months", 15, "i", "m", delay=0.85)
    x0, x1, base_y, top = 40, 560, 258, 116
    mx = max(max(tot.values()), 1)
    slot = (x1 - x0) / 12
    c.add(f'<path d="M{x0} {base_y + .5}H{x1}" stroke="var(--line)" stroke-width="1.5"/>')
    for i, ((yy, mm), v) in enumerate(tot.items()):
        bx, bw = x0 + i * slot + (slot - 26) / 2, 26
        hgt = max(v / mx * (base_y - top), 3)
        dl = 0.95 + i * 0.06
        col = "br" if v else "m"
        op = "" if v else ' opacity=".35"'
        bar = f'<rect class="{col}" x="{bx:.1f}" y="{base_y - hgt:.1f}" width="{bw}" height="{hgt:.1f}" rx="3"{op}/>'
        c.add(f'<g{c.a("grow", dl)}>{bar}</g>' if not STATIC else bar)
        if v:
            c.text(f"{bx + bw / 2:.1f}", f"{base_y - hgt - 8:.1f}", str(v), 14, "b", anchor="middle", delay=dl + 0.3)
        c.text(f"{bx + bw / 2:.1f}", base_y + 24, dt.date(yy, mm, 1).strftime("%b"), 13, "r", "m", "middle", delay=dl)
    # stat column
    sx = 612
    c.add(f'<path d="M{sx - 26} 40V{base_y + 14}" stroke="var(--line)" stroke-width="1.5"/>')
    b = s["busiest"]
    items = [
        ("CURRENT STREAK", plural(s["streak"], "day"), f"longest {plural(s['longest'], 'day')}"),
        ("ACTIVE DAYS", str(s["active"]), "days contributed"),
        ("BUSIEST DAY", str(b["count"]) if b["count"] else "none", fmt_day(b["d"]) if b["count"] else "yet"),
    ]
    for i, (lab, val, sub) in enumerate(items):
        y0 = 62 + i * 78
        dl = 1.1 + i * 0.15
        c.text(sx, y0, lab, 12, "b", "m", delay=dl, spacing=1.5)
        c.text(sx, y0 + 34, val, 34, "b", "br" if i == 0 else "", delay=dl + 0.05)
        c.text(sx, y0 + 55, sub, 13, "i", "m", delay=dl + 0.1)
    if s["streak"]:
        tx = sx + measure(items[0][1], 34, "b") + 14
        c.add(f'<circle cx="{tx:.0f}" cy="{62 + 34 - 11}" r="5" fill="var(--brand)"/>'
              + pulse(f"{tx:.0f}", 62 + 34 - 11, 5, 14))
    return c


def lang_dot(c, x, y, lang, delay):
    c.add(c.wrapg(f'<circle cx="{x}" cy="{y - 5}" r="6" fill="var(--brand)"/>', "pop", delay))
    c.text(x + 16, y, lang, 15, "r", "m", delay=delay)


def repo_card(i, r):
    desc = r["description"] or "No description yet. The code is the documentation."
    lines = wrap(desc, 15, "r", W - 80, 3)
    foot_y = 90 + len(lines) * 23 + 22
    c = Card("repo-" + r["name"], W, foot_y + 30, r["name"], f"{r['name']}: {r['description'] or 'repository'}")
    base = 1.45 + i * 0.28
    bar = f'<rect class="br" x="0" y="24" width="6" height="{foot_y - 50}" rx="3"/>'
    c.add(f'<g{c.a("grow", base)}>{bar}</g>' if not STATIC else bar)
    book = '<path class="st" d="M5 4h12a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2zM5 18a2 2 0 0 1 2-2h12"/>'
    c.add(c.wrapg(f'<g transform="translate(36 28) scale(1.15)">{book}</g>', "rise", base))
    c.text(72, 50, r["name"], 22, "b", "br", delay=base)
    star = '<path class="st" d="M12 2.5l2.9 6.2 6.6.8-4.9 4.6 1.3 6.6-5.9-3.3-5.9 3.3 1.3-6.6L2.5 9.5l6.6-.8z"/>'
    fork = ('<circle class="st" cx="6" cy="5" r="2.2"/><circle class="st" cx="18" cy="5" r="2.2"/>'
            '<circle class="st" cx="12" cy="19" r="2.2"/><path class="st" d="M6 7.2v1.8a3 3 0 0 0 3 3h6a3 3 0 0 0 3-3V7.2M12 12v4.8"/>')
    sx = W - 40
    for glyph, n in ((fork, r["forks"]), (star, r["stars"])):
        s = str(n)
        sx -= measure(s, 16, "b")
        c.text(f"{sx:.0f}", 49, s, 16, "b", delay=base + 0.1)
        sx -= 28
        c.add(c.wrapg(f'<g transform="translate({sx:.0f} 31) scale(.95)">{glyph}</g>', "rise", base + 0.1))
        sx -= 22
    for n, line in enumerate(lines):
        c.text(36, 90 + n * 23, line, 15, "r", "m" if not r["description"] else "", delay=base + 0.15 + n * 0.08)
    if r["language"]:
        lang_dot(c, 42, foot_y, r["language"], base + 0.3)
        px = 42 + 16 + measure(r["language"], 15) + 28
    else:
        px = 36
    pushed = dt.date.fromisoformat(r["pushed"])
    c.text(f"{px:.0f}", foot_y, f"Updated {pushed.strftime('%b %Y')}", 15, "i", "m", delay=base + 0.35)
    return c


def graph(d, s):
    cal = d["calendar"]
    last = cal[-1]["d"]
    start = last - dt.timedelta(days=364)
    start -= dt.timedelta(days=(start.weekday() + 1) % 7)  # back to Sunday
    by = {x["d"]: x["count"] for x in cal}
    cell, gap, gx, gy = 11, 3, 58, 98
    ncols = ((last - start).days // 7) + 1
    c = Card("graph", W, 250, "Contribution graph",
             f"Contribution graph for the last year: {s['total']} contributions on {s['active']} active days.")
    c.text(40, 50, "Contribution graph", 22, "b", delay=2.1)
    c.text(W - 40, 50, f"{plural(s['total'], 'contribution')} in the last year", 15, "i", "m", "end", delay=2.15)
    nonzero = sorted(v for v in by.values() if v)
    def level(v):
        if not v:
            return 0
        q = [nonzero[int(len(nonzero) * p)] for p in (0.25, 0.5, 0.75)] if nonzero else [1, 1, 1]
        return 1 + sum(v > t for t in q) if len(nonzero) > 3 else min(4, 1 + v // 3)
    ops = {1: .32, 2: .55, 3: .78, 4: 1}
    for dow, lab in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        c.text(gx - 12, gy + dow * (cell + gap) + cell - 2, lab, 12, "r", "m", "end", delay=2.2)
    lastm = None
    for col in range(ncols):
        wk = start + dt.timedelta(days=7 * col)
        if wk.month != lastm and (col == 0 or wk.day <= 7) and col < ncols - 1:
            c.text(gx + col * (cell + gap), gy - 12, wk.strftime("%b"), 12, "r", "m", delay=2.2 + col * 0.02)
            lastm = wk.month
        rects = []
        for row in range(7):
            day = wk + dt.timedelta(days=row)
            if day > last or day < last - dt.timedelta(days=370):
                continue
            lv = level(by.get(day, 0))
            fill = f'fill="var(--brand)" opacity="{ops[lv]}"' if lv else 'fill="var(--cell)"'
            rects.append(f'<rect x="{gx + col * (cell + gap)}" y="{gy + row * (cell + gap)}" width="{cell}" '
                         f'height="{cell}" rx="3" {fill}/>')
        c.add(c.wrapg("".join(rects), "pop", 2.25 + col * 0.03))
    # today marker (decorative pulse)
    tcol, trow = (last - start).days // 7, (last - start).days % 7
    if not STATIC:
        tx, ty = gx + tcol * (cell + gap) + cell / 2, gy + trow * (cell + gap) + cell / 2
        c.add(pulse(tx, ty, 6, 15, begin=4.0))
    # legend
    lx, ly = W - 40 - 5 * 17 - 40 - 36, 228
    c.text(lx - 8, ly + 1, "Less", 13, "r", "m", "end", delay=3.7)
    for k in range(5):
        r = (f'<rect x="{lx + k * 17}" y="{ly - 11}" width="{cell}" height="{cell}" rx="3" '
             + (f'fill="var(--brand)" opacity="{ops[k]}"/>' if k else 'fill="var(--cell)"/>'))
        c.add(c.wrapg(r, "pop", 3.7 + k * 0.05))
    c.text(lx + 5 * 17 + 4, ly + 1, "More", 13, "r", "m", delay=3.7)
    c.text(40, ly + 1, f"Updated {d['generated']}", 13, "i", "m", delay=3.7)
    return c


# ---- README / preview ---------------------------------------------------------------
def page(d, cards, ver, src):
    """Markdown/HTML body shared by README.md (src=cards/…?v=) and preview/index.html."""
    u = lambda n: f'{src}{n}.svg' + (f'?v={ver}' if ver else '')
    tiles = "\n".join(
        f'  <a href="{href}"><img src="{u(name)}" width="32.5%" alt="{kick.title()}: {title}"></a>'
        for name, kick, title, href, _ in LINKS)
    repos = "\n".join(
        f'<a href="{r["url"]}"><img src="{u("repo-" + r["name"])}" width="100%" alt="Repository {r["name"]}"></a>'
        for r in d["repos"])
    return f"""<p align="center">
<img src="{u('hero')}" width="100%" alt="{d['name']}. {ABOUT}">
</p>

<p align="center">
{tiles}
</p>

<p align="center">
<img src="{u('activity')}" width="100%" alt="Contributions per month, with streak, active days and busiest day">
</p>

<p align="center">
{repos}
</p>

<p align="center">
<img src="{u('graph')}" width="100%" alt="Contribution graph for the last year">
</p>
"""


def main():
    d = load()
    s = stats(d["calendar"])
    cards = [hero(d)] + [tile(i, sp) for i, sp in enumerate(LINKS)] + [activity(d, s)] \
        + [repo_card(i, r) for i, r in enumerate(d["repos"])] + [graph(d, s)]
    for c in cards:
        print(f"{c.name:28s}{c.save():>8,} bytes")
    if STATIC:
        body = page(d, cards, "", "")
        with open(os.path.join(OUT, "index.html"), "w") as f:
            f.write('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                    '<title>Preview</title><style>body{max-width:830px;margin:24px auto;background:#fff;'
                    'font-family:sans-serif}img{vertical-align:top}p{margin:0 0 12px}'
                    '@media(prefers-color-scheme:dark){body{background:#0d1117}}</style>' + body)
        print(f"\nStatic preview: open {os.path.join(OUT, 'index.html')}")
        return
    h = hashlib.sha1()
    for n in sorted(os.listdir(OUT)):
        h.update(open(os.path.join(OUT, n), "rb").read())
    with open(os.path.join(ROOT, "README.md"), "w") as f:
        f.write(page(d, cards, h.hexdigest()[:8], "cards/"))  # ?v= busts GitHub's image cache


if __name__ == "__main__":
    main()
