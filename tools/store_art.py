"""Steam store and library art from an in-game key-art render plus the Chief Auto logo.

    python3 tools/store_art.py <keyart_lot.png> [out_dir]     # default store/

The key art comes from tests/_keyart_shot.tscn rendered at 2560x1440 (UI hidden).
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def logo_rgba():
    """The logo sits on a flat navy square; key the navy out into alpha so it floats on the art."""
    im = np.asarray(Image.open(os.path.join(ROOT, "assets", "logo.png")).convert("RGB")).astype(np.float32)
    bg = np.median(np.concatenate([im[:6].reshape(-1, 3), im[-6:].reshape(-1, 3)]), axis=0)
    d = np.sqrt(((im - bg) ** 2).sum(axis=2))
    a = np.clip((d - 14) / 40, 0, 1)
    a = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))) / 255.0
    rgba = np.dstack([im, a * 255]).astype(np.uint8)
    img = Image.fromarray(rgba, "RGBA")
    return img.crop(img.getbbox())


def cover(src, w, h, cx=0.5, cy=0.5, zoom=1.0):
    """Crop src to w:h around (cx, cy) (fractions), then resize."""
    sw, sh = src.size
    scale = max(w / sw, h / sh) * zoom
    cw, ch = w / scale, h / scale
    x0 = min(max(cx * sw - cw / 2, 0), sw - cw)
    y0 = min(max(cy * sh - ch / 2, 0), sh - ch)
    return src.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((w, h), Image.LANCZOS)


def vignette(img, side="left", strength=0.75):
    w, h = img.size
    x = np.linspace(0, 1, w)[None, :]
    g = (1 - x) if side == "left" else (x if side == "right" else np.linspace(0, 1, h)[:, None] * np.ones((1, w)))
    if side == "bottom":
        g = np.linspace(0, 1, h)[:, None] * np.ones((1, w))
    m = np.clip(g * 1.4 - 0.2, 0, 1) ** 1.5 * strength
    arr = np.asarray(img.convert("RGB")).astype(np.float32)
    navy = np.array([4, 10, 28], np.float32)
    arr = arr * (1 - m[..., None]) + navy * m[..., None]
    return Image.fromarray(arr.astype(np.uint8))


def put_logo(img, logo, height, x, y):
    lw = int(logo.width * height / logo.height)
    l2 = logo.resize((lw, height), Image.LANCZOS)
    img = img.convert("RGBA")
    img.alpha_composite(l2, (int(x), int(y)))
    return img.convert("RGB")


def main(key_path, out):
    os.makedirs(out, exist_ok=True)
    key = Image.open(key_path).convert("RGB")
    logo = logo_rgba()
    logo.save(os.path.join(out, "library_logo_1280x720.png"))   # resized below to the exact canvas
    canvas = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    lh = 640
    lw = int(logo.width * lh / logo.height)
    canvas.alpha_composite(logo.resize((lw, lh), Image.LANCZOS), ((1280 - lw) // 2, 40))
    canvas.save(os.path.join(out, "library_logo_1280x720.png"))

    def capsule(name, w, h, cx, cy, zoom, logo_h, lx, ly, side="left", strength=0.8):
        img = vignette(cover(key, w, h, cx, cy, zoom), side, strength)
        img = put_logo(img, logo, int(h * logo_h), w * lx, h * ly)
        img.save(os.path.join(out, name), quality=92)

    capsule("header_capsule_920x430.jpg", 920, 430, 0.62, 0.55, 1.15, 0.92, 0.03, 0.04)
    capsule("small_capsule_462x174.jpg", 462, 174, 0.62, 0.55, 1.3, 0.96, 0.02, 0.02, strength=0.9)
    capsule("main_capsule_1232x706.jpg", 1232, 706, 0.6, 0.55, 1.05, 0.9, 0.03, 0.05)
    # vertical / library: logo up top, cars below
    for name, w, h in (("vertical_capsule_748x896.jpg", 748, 896), ("library_capsule_600x900.jpg", 600, 900)):
        img = cover(key, w, h, 0.76, 0.35, 1.3)
        arr = np.asarray(img).astype(np.float32)
        m = np.clip(1 - np.linspace(0, 1, h) * 2.2, 0, 1)[:, None, None] * 0.85
        arr = arr * (1 - m) + np.array([4, 10, 28]) * m
        img = put_logo(Image.fromarray(arr.astype(np.uint8)), logo, int(h * 0.36), (w - int(logo.width * h * 0.36 / logo.height)) / 2, h * 0.015)
        img.save(os.path.join(out, name), quality=92)
    # hero and page background carry no logo or text (Steam's rules)
    cover(key, 3840, 1240, 0.55, 0.5, 1.0).save(os.path.join(out, "library_hero_3840x1240.jpg"), quality=90)
    bgp = cover(key, 1438, 810, 0.5, 0.5, 1.0).filter(ImageFilter.GaussianBlur(3))
    vignette(bgp, "bottom", 0.6).save(os.path.join(out, "page_background_1438x810.jpg"), quality=90)
    # icons: the shield on navy
    ic = Image.new("RGBA", (256, 256), (4, 10, 28, 255))
    s = logo.resize((int(logo.width * 240 / logo.height), 240), Image.LANCZOS)
    ic.alpha_composite(s, ((256 - s.width) // 2, 8))
    ic.save(os.path.join(out, "icon_256.png"))
    ic.save(os.path.join(out, "client_icon.ico"), sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    ic.convert("RGB").resize((184, 184), Image.LANCZOS).save(os.path.join(out, "community_icon_184.jpg"), quality=92)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "store"))
