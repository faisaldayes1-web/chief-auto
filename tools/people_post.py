"""Prepares people3d.py renders for the game.

Bodies are cropped to the figure so the feet sit exactly on the bottom edge (the game stands that edge on the
floor), then scaled to 600 px tall. Faces are scaled to 256 px. Portraits (one per person, the same framing for
everyone) are scaled to 480 x 600 with a transparent background.

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
    im = Image.open(src).convert("RGBA")
    alpha = im.getchannel("A").point(lambda a: 255 if a > 24 else 0)
    l, t, r, b = alpha.getbbox()
    im = im.crop((max(0, l - 4), max(0, t - 4), min(im.width, r + 4), b))
    h = 600
    im = im.resize((round(im.width * h / im.height), h), Image.LANCZOS)
    im.save(dst, optimize=True)


def face(src, dst):
    im = Image.open(src).convert("RGBA").resize((256, 256), Image.LANCZOS)
    im.save(dst, optimize=True)


def portrait(src, dst):
    im = Image.open(src).convert("RGBA").resize(PORTRAIT, Image.LANCZOS)
    im.save(dst, optimize=True)


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
        jobs = [(body, "%s_body.png"), (portrait, "%s_portrait.png")] + \
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
