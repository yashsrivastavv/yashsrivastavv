#!/usr/bin/env python3
"""Prepare a photo for clean ASCII conversion (one-time, local; not needed in CI).

    pip install "rembg[cpu]" opencv-python-headless pillow numpy
    python3 scripts/prep_photo.py photo.jpeg prepped.png [--size 0.8] [--line 0.6]
    python3 scripts/make_portrait.py prepped.png

Steps, so a busy real-world photo behaves like clean line art:
  1. cut out the subject with rembg, so walls and paintings vanish;
  2. bilateral-smooth skin and fabric texture while keeping edges;
  3. stretch tones over the subject only, so skin lands near white and hair stays dark;
  4. darken thin features (eyelids, pupils, brows, mouth) with difference-of-gaussians ridges,
     because plain luminance washes them out at ASCII resolution;
  5. add local contrast (CLAHE), composite on white and crop to head and shoulders.
"""
import argparse

import cv2
import numpy as np
from PIL import Image
from rembg import new_session, remove

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("--size", type=float, default=0.8, help="crop side as a fraction of the subject's width")
ap.add_argument("--line", type=float, default=0.6, help="how hard thin features are pushed toward black")
ap.add_argument("--model", default="u2netp", help="rembg model: u2netp (5 MB), silueta (43 MB), u2net_human_seg (176 MB)")
ap.add_argument("--crop", help="x,y,side in source pixels; overrides the automatic head-and-shoulders crop")
ap.add_argument("--clahe", type=float, default=2.0, help="local contrast clip limit (0 = off)")
a = ap.parse_args()

cut = remove(Image.open(a.src).convert("RGBA"), session=new_session(a.model))
alpha = np.array(cut.split()[-1])
gray = cv2.cvtColor(np.array(cut.convert("RGB")), cv2.COLOR_RGB2GRAY)

smooth = gray
for _ in range(3):
    smooth = cv2.bilateralFilter(smooth, 9, 40, 9)

subject = alpha > 128
lo, hi = np.percentile(smooth[subject], [2, 92])
tone = np.clip((smooth.astype(np.float32) - lo) / (hi - lo), 0, 1)

ridge = cv2.GaussianBlur(tone, (0, 0), 6) - cv2.GaussianBlur(tone, (0, 0), 1.2)  # >0 where a thin dark line sits
tone = np.clip(tone - a.line * np.clip(ridge * 3, 0, 1), 0, 1)

out = (tone * 255).astype(np.uint8)
if a.clahe:
    out = cv2.createCLAHE(clipLimit=a.clahe, tileGridSize=(8, 8)).apply(out)
white = np.where(alpha[..., None] > 128, out[..., None], 255)[..., 0].astype(np.uint8)

if a.crop:
    x0, y0, side = (int(v) for v in a.crop.split(","))
else:
    ys, xs = np.where(subject)
    top, left, right = ys.min(), xs.min(), xs.max()
    side = int((right - left) * a.size)
    cx = int(xs[ys < top + side].mean())  # centre on the head, not the shoulders
    x0 = max(0, min(white.shape[1] - side, cx - side // 2))
    y0 = max(0, min(white.shape[0] - side, top - side // 12))
Image.fromarray(white[y0:y0 + side, x0:x0 + side]).save(a.out)
print(f"wrote {a.out}: {side}x{side}px crop from ({x0},{y0})")
