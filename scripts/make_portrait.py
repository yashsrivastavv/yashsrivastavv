#!/usr/bin/env python3
"""Convert a prepped greyscale portrait to ASCII once, so CI never needs the photo.

    python3 scripts/make_portrait.py prepped.png [--cols 180] [--gamma 1.18] [--white-floor 0.8] [--preview]

Run scripts/prep_photo.py first (background removal + local contrast).
Writes assets/portrait.txt, which scripts/render_cards.py draws in the hero.
Delete that file to fall back to an ASCII version of your GitHub avatar.
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageEnhance  # noqa: E402
import render_cards as R  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("image")
ap.add_argument("--cols", type=int, default=180, help="more columns = more detail (eyes need ~6+ across)")
ap.add_argument("--gamma", type=float, default=1.18, help=">1 brightens mid-tones: the face lands in sparser glyphs")
ap.add_argument("--white-floor", type=float, default=0.80, help="luminance above this becomes blank")
ap.add_argument("--contrast", type=float, default=1.05)
ap.add_argument("--preview", action="store_true", help="print instead of writing")
a = ap.parse_args()

img = ImageEnhance.Contrast(Image.open(a.image).convert("L")).enhance(a.contrast)
rows = round(a.cols * img.height / img.width / R.ROW_ASPECT)
art = R.to_ascii(img, a.cols, rows, gamma=a.gamma, white_floor=a.white_floor)
text = "\n".join(l.rstrip() for l in art).strip("\n")
if a.preview:
    print(text)
else:
    with open(R.PORTRAIT_TXT, "w") as f:
        f.write(text)
    print(f"wrote {R.PORTRAIT_TXT}: {a.cols} cols x {len(text.splitlines())} rows")
