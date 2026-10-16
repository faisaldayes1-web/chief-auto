"""python3 replay.py <tree.json> <out.npy>: draws a recorded PIL shim image with the real Pillow."""
import json, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def tup(v):
    return tuple(tup(x) for x in v) if isinstance(v, list) else v


def build(t):
    if "new" in t:
        mode, size, col = t["new"]
        im = Image.new(mode, tuple(size), tup(col))
    else:
        src = build(t["from"])
        kind, arg = t["op"]
        im = src.resize(tuple(arg), Image.LANCZOS) if kind == "resize" else src.filter(ImageFilter.GaussianBlur(arg))
    for op in t.get("ops", []):
        if op[0] == "composite":
            im.alpha_composite(build(op[1]))
        else:
            _, name, xy, kw = op
            getattr(ImageDraw.Draw(im), name)(tup(xy), **{k: tup(v) for k, v in kw.items()})
    return im


np.save(sys.argv[2], np.asarray(build(json.load(open(sys.argv[1])))))
