"""Prepares people3d.py renders for the game.

Bodies are cropped to the figure so the feet sit exactly on the bottom edge (the game stands that edge on the
floor), then scaled to 600 px tall. Faces are scaled to 256 px. Portraits (one per person, the same framing for
everyone) are scaled to 480 x 600 with a transparent background. Heroes (PARTS=hero) are cropped to the figure and
scaled to 1300 px tall.

Usage:  python3 tools/people_post.py <render_dir> <assets/people> [src_pid=dst_pid ...]
With no pairs every pid in the render dir is copied under its own name. Missing renders are skipped, so a
portrait-only render (PARTS=portrait) only updates portraits.

  --dialogue <assets_dir>   also writes <assets_dir>/portrait_<pid>.jpg for marco and maruchan: the portrait on a dark
                            panel-coloured backdrop (the dialogue box loads these by name).
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

PORTRAIT = (480, 600)


def body(src, dst):
    """Crops to the figure with its feet on the bottom edge. The ground shadow people3d.py bakes in (dark,
    semi-transparent pixels) is kept: the faint shadow-catcher floor is cleared, the shadow fades out with distance
    from the feet so the disc edge never shows, and the crop widens symmetrically (figure stays centred) to keep it."""
    import numpy as np
    im = Image.open(src).convert("RGBA")
    px = np.asarray(im).astype(np.float32)
    a = px[..., 3]
    shadow = (a < 235) & (px[..., :3].max(-1) < 40)
    solid = (a > 24) & ~shadow
    ys, xs = np.nonzero(solid)
    t, b = ys.min(), ys.max() + 1
    l, r = xs.min(), xs.max() + 1
    feet = solid[max(t, b - 40):b]
    fx = np.nonzero(feet.any(0))[0].mean() if feet.any() else (l + r) / 2
    hgt = b - t
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    d = np.sqrt(((xx - fx) / (0.42 * hgt)) ** 2 + ((yy - b) / (0.17 * hgt)) ** 2)
    fade = np.clip(1.15 - d, 0, 1) ** 1.2
    sa = np.minimum(np.where(a < 14, 0, a) * fade * 1.35, 220)
    px[..., 3] = np.where(shadow, sa, a)
    px[..., :3] = np.where(shadow[..., None], 0, px[..., :3])
    im = Image.fromarray(px.clip(0, 255).astype(np.uint8))
    cx = (l + r) / 2
    sh = np.nonzero((px[t:b, :, 3] > 6).any(0))[0]
    half = max(cx - l, r - cx, cx - sh.min(), sh.max() - cx) + 4
    half = min(half, 0.45 * hgt, cx, im.width - cx)
    half = max(half, (r - l) / 2 + 2)
    im = im.crop((round(cx - half), max(0, t - 4), round(cx + half), b))
    h = 600
    im = im.resize((round(im.width * h / im.height), h), Image.LANCZOS)
    im.save(dst, optimize=True)


def face(src, dst):
    im = Image.open(src).convert("RGBA").resize((256, 256), Image.LANCZOS)
    im.save(dst, optimize=True)


def portrait(src, dst):
    im = Image.open(src).convert("RGBA").resize(PORTRAIT, Image.LANCZOS)
    im.save(dst, optimize=True)


HERO_H = 1300


def hero(src, dst):
    """The Marco-screen figure: cropped tight to the figure, scaled to 1300 px tall. Prints the head's pixel box
    (from people3d.py's <pid>_hero_head.json) in the output image."""
    im = Image.open(src).convert("RGBA")
    l, t, r, b = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    im = im.crop((l, t, r, b))
    k = HERO_H / im.height
    im = im.resize((round(im.width * k), HERO_H), Image.LANCZOS)
    im.save(dst, optimize=True)
    meta = src.replace("_hero.png", "_hero_head.json")
    if os.path.exists(meta):
        import json
        x0, y0, x1, y1 = json.load(open(meta))["head"]
        box = [round((x0 - l) * k), max(0, round((y0 - t) * k)), round((x1 - l) * k), round((y1 - t) * k)]
        print("  %s: %dx%d, head box x0,y0,x1,y1 = %s" % (os.path.basename(dst), im.width, im.height, box))


def dialogue_jpg(src, dst):
    """The portrait over a navy gradient with a soft glow behind the head, 416 x 480 (cropped at the chest)."""
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    bg = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(bg)
    for y in range(h):
        t = y / (h - 1)
        d.line([(0, y), (w, y)], fill=(round(22 - 12 * t), round(34 - 18 * t), round(56 - 26 * t)))
    glow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(glow).ellipse((w * 0.12, h * 0.02, w * 0.88, h * 0.62), fill=110)
    glow = glow.filter(ImageFilter.GaussianBlur(w * 0.12))
    bg = Image.composite(Image.new("RGB", (w, h), (70, 96, 140)), bg, glow)
    bg.paste(im, (0, 0), im)
    ch = round(w * 480 / 416)
    bg = bg.crop((0, 0, w, ch)).resize((416, 480), Image.LANCZOS)
    bg.save(dst, quality=88, optimize=True)


def main():
    args = sys.argv[1:]
    dialogue = None
    if "--dialogue" in args:
        i = args.index("--dialogue")
        dialogue = args[i + 1]
        del args[i:i + 2]
    src, out = args[0], args[1]
    pairs = [a.split("=") for a in args[2:]]
    if not pairs:
        ids = sorted({f.rsplit("_", 1)[0] for f in os.listdir(src) if f.endswith("_portrait.png")} |
                     {f.split("_")[0] for f in os.listdir(src) if f.endswith("_body.png")})
        pairs = [(i, i) for i in ids]
    for s, d in pairs:
        jobs = [(body, "%s_body.png"), (portrait, "%s_portrait.png"), (hero, "%s_hero.png")] + \
               [(face, "%%s_face_%s.png" % m) for m in ("neutral", "happy", "angry")]
        done = []
        for fn, pat in jobs:
            p = os.path.join(src, pat % s)
            if os.path.exists(p):
                fn(p, os.path.join(out, pat % d))
                done.append(pat.split("%s_")[1])
        if dialogue and d in ("marco", "maruchan") and os.path.exists(os.path.join(src, s + "_portrait.png")):
            dialogue_jpg(os.path.join(src, s + "_portrait.png"), os.path.join(dialogue, "portrait_%s.jpg" % d))
            done.append("dialogue jpg")
        print(s, "->", d, ", ".join(done))


if __name__ == "__main__":
    main()
