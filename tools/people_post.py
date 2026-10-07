"""Prepares people3d.py renders for the game.

Bodies are cropped to the figure so the feet sit exactly on the bottom edge (the game stands that edge on the
floor), then scaled to 600 px tall. Faces are scaled to 256 px.

Usage:  python3 tools/people_post.py <render_dir> <assets/people> [src_pid=dst_pid ...]
With no pairs every pNN in the render dir is copied under its own name.
"""
import os
import sys

from PIL import Image


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


def main():
    src, out = sys.argv[1], sys.argv[2]
    pairs = [a.split("=") for a in sys.argv[3:]]
    if not pairs:
        ids = sorted({f.split("_")[0] for f in os.listdir(src) if f.endswith("_body.png")})
        pairs = [(i, i) for i in ids]
    for s, d in pairs:
        body(os.path.join(src, s + "_body.png"), os.path.join(out, d + "_body.png"))
        for mood in ("neutral", "happy", "angry"):
            face(os.path.join(src, "%s_face_%s.png" % (s, mood)), os.path.join(out, "%s_face_%s.png" % (d, mood)))
        print(s, "->", d)


if __name__ == "__main__":
    main()
