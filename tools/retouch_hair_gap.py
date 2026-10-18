"""Retouch: fill the dark gap a hair-card mesh leaves between hair and scalp in a baked people render.

The Rocketbox render of Jeff (tools/people3d.py) shows black scalp through a gap at the hairline, as a dark band
across his head in jeff_portrait/face/body.png. Re-rendering needs the Rocketbox library, so this paints over the
gap instead: inside a box around it, near-black opaque pixels (and their dark anti-aliased rim) take the hair
texture mirrored upward from just above the gap, then the seam is softened a little. Alpha is untouched.

Usage: python -I tools/retouch_hair_gap.py <src.png> <dst.png> <x0,y0,x1,y1>
Boxes used for Jeff (2026-10-17): portrait 188,78,314,126; face_* 108,30,157,48; body 133,9,171,25.
"""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage

src, dst = sys.argv[1], sys.argv[2]
a = np.array(Image.open(src).convert("RGBA")).astype(float)
h, w = a.shape[:2]
x0, y0b, x1, y1b = (int(v) for v in sys.argv[3].split(","))   # box around the gap, from a gridded zoom
lum = a[..., 0] * 0.3 + a[..., 1] * 0.59 + a[..., 2] * 0.11
op = a[..., 3] > 200
box = np.zeros((h, w), bool)
box[y0b:y1b + 1, x0:x1 + 1] = True
mask = (lum < 70) & op & box
mask = mask | (ndimage.binary_dilation(mask, iterations=1) & (lum < 100) & op & box)
print(src, "filled px", int(mask.sum()))
out = a.copy()
for x in range(w):
    col = np.nonzero(mask[:, x])[0]
    if col.size == 0:
        continue
    # runs of masked rows in this column
    runs = np.split(col, np.nonzero(np.diff(col) > 1)[0] + 1)
    for r in runs:
        y0, y1 = r[0], r[-1]
        L = y1 - y0 + 1
        for k in range(L):
            sy = y0 - 1 - k  # mirror upward from the run's top edge
            while sy >= 0 and mask[sy, x]:
                sy -= 1
            if sy < 0 or a[sy, x, 3] < 200:
                sy = y0 - 1
            out[y0 + k, x, :3] = a[max(sy, 0), x, :3]
# soften the seam a touch inside the filled area only
blur = ndimage.uniform_filter(out[..., :3], size=(3, 3, 1))
mm = ndimage.binary_dilation(mask, iterations=1)
out[mm, :3] = out[mm, :3] * 0.5 + blur[mm] * 0.5
Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA").save(dst)
