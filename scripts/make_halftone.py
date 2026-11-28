#!/usr/bin/env python3
"""Turn a prepped portrait into an ordered-dither halftone, stored as SVG path data (one-time, local).

    pip install opencv-python-headless pillow numpy
    python3 scripts/prep_photo.py photo.jpeg prepped.png --keep ... --crop ...   # cut-out on white
    python3 scripts/make_halftone.py prepped.png [--cols 145 --rows 170] [--gamma 0.9] [--preview out.svg]

Writes assets/portrait-halftone.json: {"cols","rows","p","bands":[path,...]}. Each band is a few rows of
1-cell-tall rectangles, run-length encoded, so the daily render needs no image libraries and the
hero can reveal the portrait band by band. Only the subject is dithered; the backdrop is drawn
by the renderer as a flat dot grid, like a printed halftone.
"""
import argparse, json, os

import cv2
import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ap = argparse.ArgumentParser()
ap.add_argument("image")
ap.add_argument("--cols", type=int, default=145)
ap.add_argument("--rows", type=int, default=170)
ap.add_argument("--p", type=float, default=2, help="pixel size of one dither cell in the card")
ap.add_argument("--gamma", type=float, default=0.9, help=">1 darkens mid-tones (more ink), <1 lightens")
ap.add_argument("--lift", type=float, default=0.0, help="add to brightness before dithering")
ap.add_argument("--band", type=int, default=4, help="rows per animated band")
ap.add_argument("--anchor", type=float, default=0.5, help="0..1: which part of the width to keep when cropping")
ap.add_argument("--preview", help="also write a standalone SVG preview here")
a = ap.parse_args()

gray = cv2.imread(a.image, cv2.IMREAD_GRAYSCALE)
h, w = gray.shape

# background = near-white pixels connected to the border (inner highlights stay subject)
white = (gray >= 250).astype(np.uint8)
flood = white.copy()
ff = np.zeros((h + 2, w + 2), np.uint8)
for seed in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
    if flood[seed[1], seed[0]] == 1:
        cv2.floodFill(flood, ff, seed, 2)
bg = (flood == 2).astype(np.uint8)
bg = cv2.morphologyEx(bg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

# crop to the card's aspect, then resample to the dither grid
aspect = a.cols / a.rows
cw = min(w, int(h * aspect))
x0 = int((w - cw) * a.anchor)
gray, bg = gray[:, x0:x0 + cw], bg[:, x0:x0 + cw]
ch = min(h, int(cw / aspect))
gray, bg = gray[:ch], bg[:ch]
g = cv2.resize(gray, (a.cols, a.rows), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
bgm = cv2.resize(bg.astype(np.float32), (a.cols, a.rows), interpolation=cv2.INTER_AREA) > 0.5

g = np.clip(g + a.lift, 0, 1) ** a.gamma

# 8x8 Bayer matrix -> threshold map in (0,1)
def bayer(n):
    if n == 1:
        return np.array([[0]])
    m = bayer(n // 2)
    return np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])

B = (bayer(8) + 0.5) / 64
thr = np.tile(B, (a.rows // 8 + 1, a.cols // 8 + 1))[:a.rows, :a.cols]
ink = (g < thr) & ~bgm  # True = black cell, only inside the subject

p = a.p
bands = []
# Three nested loops, one job each:
#   1. for b0: group the grid's rows into bands of `--band` rows; each band becomes one SVG
#      path, so the hero can fade the portrait in band by band.
#   2. for y: walk the rows inside that band.
#   3. while x: scan the row left to right and run-length encode it: each run of adjacent
#      ink cells becomes a single rectangle instead of one rectangle per cell, which keeps
#      the path data (and the card) much smaller.
for b0 in range(0, a.rows, a.band):
    d = []
    for y in range(b0, min(b0 + a.band, a.rows)):
        x = 0
        row = ink[y]
        while x < a.cols:
            if row[x]:
                s = x  # start of a run; extend it while the cells stay ink
                while x < a.cols and row[x]:
                    x += 1
                d.append(f"M{s * p} {y * p}h{(x - s) * p}v{p}h-{(x - s) * p}z")
            else:
                x += 1
    bands.append("".join(d))

out = os.path.join(ROOT, "assets", "portrait-halftone.json")
with open(out, "w") as f:
    json.dump({"cols": a.cols, "rows": a.rows, "p": p, "bands": bands}, f, separators=(",", ":"))
print(f"wrote {out}: {a.cols}x{a.rows} cells, {sum(map(len, bands)) / 1024:.0f} KB of path data, "
      f"{ink.mean() * 100:.0f}% ink")

if a.preview:
    W, H = a.cols * p, a.rows * p
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
           f'<rect width="{W}" height="{H}" fill="#f4f2ec"/><path d="{"".join(bands)}" fill="#141413"/></svg>')
    open(a.preview, "w").write(svg)
