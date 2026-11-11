#!/usr/bin/env python3
"""Convert a photo to ASCII once, so CI never needs the photo itself.

    python3 scripts/make_portrait.py photo.jpeg --box 190,170,710,690 [--cols 78] [--preview]

Writes assets/portrait.txt, which scripts/render_cards.py draws in the hero.
Delete that file to fall back to an ASCII version of your GitHub avatar.
--box is x0,y0,x1,y1 in pixels (default: the whole image).
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image  # noqa: E402
import render_cards as R  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("image")
ap.add_argument("--box")
ap.add_argument("--cols", type=int, default=78)
ap.add_argument("--gamma", type=float, default=1.3)
ap.add_argument("--floor", type=float, default=0.12, help="values below this stay blank")
ap.add_argument("--light-on-dark", action="store_true", help="bright subject on a dark backdrop")
ap.add_argument("--keep", action="append", metavar="CX,CY,RX,RY",
                help="ellipse (source pixels) to keep; everything outside fades to blank. Repeatable.")
ap.add_argument("--blur", type=int, default=30, help="softness of the --keep edge")
ap.add_argument("--equalize", action="store_true", help="histogram-equalise the subject (shows facial features)")
ap.add_argument("--preview", action="store_true", help="print instead of writing")
a = ap.parse_args()

img = Image.open(a.image).convert("L")
if a.keep:  # soft mask: busy backgrounds fade to blank so the subject reads clearly
    from PIL import ImageDraw, ImageFilter
    mask = Image.new("L", img.size, 0)
    for e in a.keep:
        cx, cy, rx, ry = (float(v) for v in e.split(","))
        ImageDraw.Draw(mask).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(a.blur))
    subject = mask.point(lambda v: 255 if v > 128 else 0)
    img = Image.composite(img, Image.new("L", img.size, 255 if not a.light_on_dark else 0), mask)
if a.box:
    box = tuple(int(v) for v in a.box.split(","))
    img = img.crop(box)
    if a.keep:
        subject = subject.crop(box)
if a.equalize:  # spread the subject's tones over the whole glyph ramp so a mid-tone face keeps its features
    from PIL import ImageOps
    img = ImageOps.equalize(img, mask=subject) if a.keep else ImageOps.equalize(img)
rows = round(a.cols * img.height / img.width / R.ROW_ASPECT)
art = R.to_ascii(img, a.cols, rows, dense_dark=not a.light_on_dark, gamma=a.gamma, floor=a.floor)
text = "\n".join(l.rstrip() for l in art).strip("\n")
if a.preview:
    print(text)
else:
    with open(R.PORTRAIT_TXT, "w") as f:
        f.write(text)
    print(f"wrote {R.PORTRAIT_TXT}: {a.cols} cols x {rows} rows")
