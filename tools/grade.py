"""python3 tools/grade.py <img.jpg>: the warm Southern California day grade for daytime backgrounds, in place.
Warmer white balance, a little lift in the shadows' warmth and richer colour (saturation +40%), a deeper black point and a gentle contrast curve."""
import sys

import numpy as np
from PIL import Image, ImageEnhance

p = sys.argv[1]
im = Image.open(p).convert("RGB")
a = np.asarray(im, dtype=np.float32) / 255.0
a *= np.array([1.05, 1.0, 0.9], dtype=np.float32)                # warmer white balance
lum = a.mean(axis=2, keepdims=True)
a += (1 - lum) * lum * np.array([0.05, 0.02, -0.02], dtype=np.float32)   # golden mid-tones
a = np.clip((np.clip(a, 0, 1) - 0.06) / 0.94, 0, 1)                # clear the haze: a deeper black point
a = a * a * (3 - 2 * a) * 0.35 + a * 0.65                            # a gentle S-curve for contrast
im = Image.fromarray((a * 255 + 0.5).astype(np.uint8))
im = ImageEnhance.Color(im).enhance(1.4)
im.save(p, quality=92)
