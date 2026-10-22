"""Pick D "noon sun, blue sky" relight of the day backgrounds (lot, office, desk, sales desk), without re-rendering.

The renders came from tools/dealership3d.py with a hazy late-afternoon sky. Re-rendering needs the CC0 scan pack
(not on the build machines), so this regrades the existing renders instead:
  1. sky: pixels that read as sky (bright, clearly bluer than red) are pulled toward a deep noon blue that
     lightens to the horizon; clouds and haze highlights keep their brightness, so the texture survives.
  2. the whole frame: a noon grade (more contrast and saturation, warm sunlit highlights, clean cool shadows).
Originals are kept in assets/world/raw/ (ignored by Godot); the script always reads from there, so re-running it
never compounds.  Usage:  python tools/sunny_relight.py [key ...]   (default: every lot/office/desk/dealdesk tier)
Night renders (bg_*_night.jpg) are untouched.
"""
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(HERE, "..", "assets", "world")
RAW = os.path.join(WORLD, "raw")
KEYS = [v + t for v in ("lot", "office", "desk", "dealdesk") for t in ("", "_t1", "_t2")]


def relight(im: Image.Image) -> Image.Image:
    a = np.asarray(im.convert("RGB")).astype(np.float32) / 255.0
    h, w, _ = a.shape
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    luma = a @ np.array([0.299, 0.587, 0.114], np.float32)
    # sky: bright, bluer than red, mostly in the upper part of the frame
    blue = np.clip((b - r - 0.06) / 0.12, 0, 1)
    bright = np.clip((luma - 0.42) / 0.15, 0, 1)
    ys = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    upper = np.clip((0.78 - ys) / 0.2, 0, 1)
    m = blue * bright * upper
    m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.5))).astype(np.float32) / 255.0
    # target: deep noon blue at the top of the frame to a pale clear blue at the horizon
    top = np.array([0.22, 0.48, 0.9], np.float32)
    hor = np.array([0.6, 0.8, 0.97], np.float32)
    t = np.clip(ys / 0.6, 0, 1)[..., None]
    target = top * (1 - t) + hor * t
    # keep the cloud and haze texture: scale by the pixel's brightness relative to the sky's typical brightness
    ref = float(np.median(luma[m > 0.5])) if (m > 0.5).any() else 0.7
    detail = np.clip(luma / max(ref, 1e-3), 0.6, 1.6)[..., None]
    whiteness = np.clip((luma - ref - 0.06) / 0.18, 0, 1)[..., None]   # clouds stay white
    sky = target * detail
    sky = sky * (1 - whiteness) + np.minimum(a * 1.08, 1.0) * whiteness
    out = a * (1 - m[..., None]) + sky * m[..., None]
    # noon grade on everything
    L = (out @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
    out = L + (out - L) * 1.22                                   # saturation
    out = 0.5 + (out - 0.5) * 1.08                               # contrast
    hi = np.clip((L - 0.45) / 0.5, 0, 1)
    out = out * (1 + hi * np.array([0.06, 0.03, -0.04], np.float32))   # warm sunlit highlights
    lo = np.clip((0.3 - L) / 0.3, 0, 1)
    out = out + lo * np.array([-0.005, 0.0, 0.015], np.float32)        # cool, clean shadows
    out = out * 1.02 + 0.005                                     # a touch brighter overall: midday
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8))


def main():
    os.makedirs(RAW, exist_ok=True)
    for key in sys.argv[1:] or KEYS:
        src = os.path.join(WORLD, f"bg_{key}.jpg")
        raw = os.path.join(RAW, f"bg_{key}.jpg")
        if not os.path.exists(raw):
            if not os.path.exists(src):
                continue
            shutil.copy2(src, raw)
        relight(Image.open(raw)).save(src, quality=92, subsampling=0)
        print("relit", key)


if __name__ == "__main__":
    main()
