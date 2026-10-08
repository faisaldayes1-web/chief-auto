"""Builds the textures for the named staff (Marco, Maruchan) out of Microsoft Rocketbox avatar textures (MIT).

Everyone in the game is rendered by tools/people3d.py; Marco and Maruchan are Rocketbox avatars whose head textures are
recombined (all Rocketbox adult male heads share one UV layout) and whose clothes are repainted to match the owner's art:

  Marco     Male_Adult_17 face (goatee, greyed) + Male_Adult_05 short combed-back greying hair, black polo with a round
            chest badge, charcoal trousers, black shoes.
  Maruchan  Male_Adult_15 face, beard trimmed to moustache + chin beard (cheeks from Male_Adult_17), navy polo with small
            white CHIEF AUTO chest text. people3d.py gives him Female_Adult_03's long hair cards, dyed black.

Both wear Male_Adult_01's polo body (repainted); people3d.py swaps its shorts for Business_Male_01's trousers and shoes
and adds the glasses, sunglasses and watch as geometry.

Usage (bpy venv, isolated):  python -I tools/people_staff_tex.py <rocketbox_dir> <rocketbox_extra_dir> <out_dir>
Writes <out>/<pid>/{head,body}_color.png.
"""
import glob
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def tex(folder, kind):
    return np.asarray(Image.open(glob.glob(os.path.join(folder, "*_%s_color.tga" % kind))[0]).convert("RGB"), np.float32)


def blur(a, r):
    """Gaussian blur of a float array (H, W) or (H, W, 3) in 0..255."""
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(r)), np.float32)


def soft_box(shape, x0, y0, x1, y1, feather):
    h, w = shape
    m = np.zeros((h, w), np.float32)
    m[max(0, y0):y1, max(0, x0):x1] = 255
    return blur(m, feather) / 255.0


def ellipse(shape, cx, cy, rx, ry, feather):
    h, w = shape
    im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(im).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
    return np.asarray(im.filter(ImageFilter.GaussianBlur(feather)), np.float32) / 255.0


def lum(a):
    return a[..., 0] * 0.3 + a[..., 1] * 0.59 + a[..., 2] * 0.11


def mean_rgb(a, x0, y0, x1, y1):
    return a[y0:y1, x0:x1].reshape(-1, 3).mean(0)


def mix(a, b, m):
    return a * (1 - m[..., None]) + b * m[..., None]


def noise(shape, seed, streak=(1, 6)):
    """Hair-strand-like noise in 0..1: random pixels smeared vertically."""
    rng = np.random.default_rng(seed)
    n = rng.random(shape).astype(np.float32) * 255
    im = Image.fromarray(n.astype(np.uint8)).filter(ImageFilter.BoxBlur(1))
    im = im.resize((shape[1] // streak[0], shape[0] // streak[1])).resize((shape[1], shape[0]), Image.BILINEAR)
    a = np.asarray(im, np.float32)
    return (a - a.min()) / (a.max() - a.min() + 1e-6)


# ---------------------------------------------------------------- heads (2048 px, shared Rocketbox male layout)

SKIN_REF = (700, 640, 860, 720)    # a cheek patch above any beard
FACE_KEEP_TOP = 450                # above this (the brows are at ~520) the head is forehead, scalp and hair


def marco_head(rb, rbx):
    face = tex(os.path.join(rbx, "Male_Adult_17"), "head")
    hair = tex(os.path.join(rb, "Male_Adult_05"), "head")
    shape = face.shape[:2]
    # tone Male_Adult_05's skin (pale) to Male_Adult_17's before borrowing its scalp
    k = mean_rgb(face, *SKIN_REF) / mean_rgb(hair, *SKIN_REF)
    hl = lum(hair)
    skinness = np.clip((hair[..., 0] - hair[..., 2] - 18) / 30.0, 0, 1) * np.clip((hl - 85) / 35.0, 0, 1)
    hair_t = mix(hair, hair * k, skinness)
    # darken the hair (dark brown-black, greying at the temples comes through from the source)
    hairness = 1 - skinness
    hair_t = mix(hair_t, hair_t * np.array([0.42, 0.4, 0.38]), hairness * 0.85)
    # Male_Adult_05 above the brows (hairline, forehead, scalp) and the hair around the ears; Male_Adult_17 below
    top = soft_box(shape, 0, 0, 2048, FACE_KEEP_TOP, 45)
    sides = (soft_box(shape, 0, 0, 660, 640, 40) + soft_box(shape, 1390, 0, 2048, 640, 40)).clip(0, 1)
    m = np.maximum(top, sides * hairness)
    out = mix(face, hair_t, m)
    # where people3d.py grows strand hair (scalp hair only, not the forehead), and where it greys (temples)
    hair_mask = blur(m * hairness * np.clip((215 - hl) / 40, 0, 1) * 255, 6) / 255.0
    temples = hair_mask * (soft_box(shape, 480, 300, 760, 820, 40) + soft_box(shape, 1290, 300, 1570, 820, 40)).clip(0, 1)
    # grey the goatee and moustache (salt and pepper)
    beard = np.maximum(ellipse(shape, 1024, 960, 170, 190, 25), ellipse(shape, 1024, 785, 150, 45, 12))
    dark = np.clip((95 - lum(out)) / 60, 0, 1) * beard
    n = noise(shape, 5)
    grey = np.stack([lum(out) * 1.2 + 70] * 3, -1) * np.array([1.0, 0.98, 0.95])
    out = mix(out, grey, dark * np.clip(n * 1.6 - 0.2, 0, 1) * 0.9)
    # a little grey in the sideburns
    sb = (soft_box(shape, 520, 380, 720, 780, 30) + soft_box(shape, 1330, 380, 1530, 780, 30)).clip(0, 1)
    sdark = np.clip((80 - lum(out)) / 50, 0, 1) * sb
    out = mix(out, grey, sdark * np.clip(n * 1.7 - 0.3, 0, 1) * 0.85)
    # age (~50): under-eye bags and nasolabial folds, as soft shading
    age = np.zeros(shape, np.float32)
    for cx in (905, 1143):
        age = np.maximum(age, ellipse(shape, cx, 628, 70, 20, 14) * 0.55)
    im = Image.new("L", (shape[1], shape[0]), 0)
    d = ImageDraw.Draw(im)
    d.line([(958, 712), (930, 770), (918, 835)], fill=255, width=14)
    d.line([(1090, 712), (1118, 770), (1130, 835)], fill=255, width=14)
    age = np.maximum(age, np.asarray(im.filter(ImageFilter.GaussianBlur(10)), np.float32) / 255.0 * 0.6)
    out = mix(out, out * np.array([0.8, 0.76, 0.76]), age)
    out = flush(out)
    out = fill_chest(out, rb)
    # Male_Adult_17 keeps its eyeballs and mouth pieces elsewhere on the sheet; take them from Male_Adult_15, which has
    # them where Male_Adult_01's mesh looks (brown eyes)
    eyes = tex(os.path.join(rbx, "Male_Adult_15"), "head")
    m = soft_box(shape, 0, 1150, 860, 2048, 3) * (1 - soft_box(shape, 240, 1300, 860, 1540, 3))
    return mix(out, eyes, m), hair_mask, temples


def maruchan_head(rb, rbx):
    face = tex(os.path.join(rbx, "Male_Adult_15"), "head")
    cheek = tex(os.path.join(rbx, "Male_Adult_17"), "head")
    shape = face.shape[:2]
    k = mean_rgb(face, *SKIN_REF) / mean_rgb(cheek, *SKIN_REF)
    cheek = cheek * k
    # replace the full beard on the jaw and cheeks, keep the moustache and a chin beard
    jaw = soft_box(shape, 560, 690, 1490, 1230, 30)
    keep = np.maximum(ellipse(shape, 1024, 790, 160, 52, 10), ellipse(shape, 1024, 975, 120, 150, 22))
    m = np.clip(jaw - keep, 0, 1)
    out = mix(face, cheek, m)
    # blacken the chin beard a touch so it reads like the art
    out = mix(out, out * 0.8, keep * np.clip((90 - lum(out)) / 60, 0, 1))
    return fill_chest(flush(out), rb)


def flush(out):
    """A little living redness at the nose, cheeks and ears."""
    shape = out.shape[:2]
    m = np.maximum.reduce([ellipse(shape, 1024, 715, 45, 40, 18) * 0.8,
                           ellipse(shape, 860, 700, 85, 65, 40) * 0.6, ellipse(shape, 1188, 700, 85, 65, 40) * 0.6,
                           ellipse(shape, 490, 640, 60, 110, 25) * 0.7, ellipse(shape, 1558, 640, 60, 110, 25) * 0.7])
    return mix(out, out * np.array([1.07, 0.93, 0.9]), m * 0.6)


def fill_chest(out, rb):
    """Male_Adult_01's head mesh carries a V of chest skin under the collar that the other heads' sheets use for caps
    or robe trims: below each source's neck, continue with Male_Adult_01's chest skin toned to this face."""
    base = tex(os.path.join(rb, "Male_Adult_01"), "head")
    neck = mean_rgb(out, 900, 1150, 1150, 1250)
    k = neck / mean_rgb(base, 900, 1150, 1150, 1250)
    h, w = out.shape[:2]
    skin = np.abs(blur(out, 4) - neck).max(-1) < 70
    stops = np.full(w, h)
    for x in range(560, w - 40):
        col = skin[1150:, x]
        stops[x] = 1150 + (np.argmin(col) if not col.all() else len(col))
    # smooth the boundary across columns so it never steps
    sm = np.array([np.median(stops[max(0, x - 40):x + 40]) for x in range(w)])
    yy = np.arange(h)[:, None]
    # only Male_Adult_01's chest V (its eyes and mouth pieces sit lower left, below 1700)
    m = ((yy >= sm[None, :]) & (np.arange(w)[None, :] >= 560) & (yy < 1700) & (lum(base) > 8)).astype(np.float32)
    m *= (lum(base) > 8)
    m = blur(m * 255, 6) / 255.0
    return mix(out, base * k, m)


# ---------------------------------------------------------------- body (Male_Adult_01 polo outfit)

def regions(shape):
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    outer = (xx < 620) | (xx > 1430)
    return {
        "shorts": outer & (yy < 512),
        "calves": outer & (yy >= 512) & (yy < 890),
        "sleeves": outer & (yy >= 890) & (yy < 1270),
        "lower": outer & (yy >= 1270),
        "torso": (xx >= 620) & (xx <= 1430) & (yy < 1900),
        "shoebox": (yy > 1400) & (((xx > 430) & (xx < 830)) | ((xx > 1210) & (xx < 1620))),
    }


def cloth(src, mask, rgb, close=11, contrast=1.15, lo=0.4, hi=1.25):
    """Repaints fabric in one flat colour, keeping the folds (thin stripes are closed away first)."""
    L = Image.fromarray(np.clip(lum(src), 0, 255).astype(np.uint8))
    L = L.filter(ImageFilter.MaxFilter(close)).filter(ImageFilter.MinFilter(close)).filter(ImageFilter.GaussianBlur(2))
    Lc = np.asarray(L, np.float32)
    ref = np.percentile(Lc[mask], 60) if mask.any() else 128
    shade = np.clip(Lc / max(ref, 1), lo, hi) ** contrast
    return np.array(rgb, np.float32) * shade[..., None]


def body(rb, head_rgb, shirt, trousers, shoes, decal):
    src = tex(os.path.join(rb, "Male_Adult_01"), "body")
    shape = src.shape[:2]
    R = regions(shape)
    filled = lum(src) > 4
    hsv = np.asarray(Image.fromarray(src.astype(np.uint8)).convert("HSV"), np.float32)
    lowsat = hsv[..., 1] < 50
    shoe = R["shoebox"] & lowsat & filled
    out = src.copy()
    shirt_m = (R["torso"] | R["sleeves"]) & filled
    out[shirt_m] = cloth(src, shirt_m, shirt)[shirt_m]
    tr = (R["shorts"] | R["calves"]) & filled
    out[tr] = cloth(src, tr, trousers, close=3, contrast=1.3)[tr]
    out[shoe] = cloth(src, shoe, shoes, close=3, contrast=1.4, lo=0.3)[shoe]
    # arms and hands: tone to the face's skin
    skin = R["lower"] & filled & ~shoe
    k = head_rgb / mean_rgb(src, 120, 1400, 460, 1700)
    out[skin] = (src * k)[skin]
    out = np.clip(out, 0, 255)
    im = Image.fromarray(out.astype(np.uint8))
    if decal:
        decal(im)
    return im


# chest position on Male_Adult_01's front torso panel (wearer's left = right of the sheet)
CHEST = (1135, 1085)


def marco_badge(im):
    s = 4
    cx, cy, r = CHEST[0], CHEST[1], 21
    big = Image.new("RGBA", (r * 2 * s + 8, r * 2 * s + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    c = r * s + 4
    d.ellipse((c - r * s, c - r * s, c + r * s, c + r * s), fill=(232, 226, 210, 255))
    d.ellipse((c - r * s * 0.78, c - r * s * 0.78, c + r * s * 0.78, c + r * s * 0.78), outline=(60, 50, 45, 255), width=s * 2)
    d.polygon([(c - r * s * 0.4, c + r * s * 0.35), (c, c - r * s * 0.45), (c + r * s * 0.4, c + r * s * 0.35)], fill=(170, 40, 40, 255))
    d.rectangle((c - r * s * 0.12, c - r * s * 0.1, c + r * s * 0.12, c + r * s * 0.35), fill=(40, 60, 120, 255))
    small = big.resize((big.width // s, big.height // s), Image.LANCZOS)
    im.paste(small, (cx - small.width // 2, cy - small.height // 2), small)


def maruchan_text(im):
    s = 4
    f = ImageFont.truetype(FONT, 15 * s)
    w = int(f.getlength("CHIEF AUTO")) + 8 * s
    big = Image.new("RGBA", (w, 26 * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.text((4 * s, 6 * s), "CHIEF AUTO", font=f, fill=(238, 240, 245, 255))
    # a little car-roof swoosh over the text, like the art
    d.arc((14 * s, 1 * s, w - 14 * s, 18 * s), 200, 340, fill=(238, 240, 245, 255), width=s)
    small = big.resize((big.width // s, big.height // s), Image.LANCZOS)
    im.paste(small, (CHEST[0] - small.width // 2, CHEST[1] - small.height // 2), small)


def main():
    rb, rbx, out = sys.argv[1:4]
    for pid in ("marco", "maruchan"):
        os.makedirs(os.path.join(out, pid), exist_ok=True)
    mh, hm, tm = marco_head(rb, rbx)
    Image.fromarray((hm * 255).astype(np.uint8)).save(os.path.join(out, "marco", "hair_mask.png"))
    Image.fromarray((tm * 255).astype(np.uint8)).save(os.path.join(out, "marco", "grey_mask.png"))
    Image.fromarray(np.clip(mh, 0, 255).astype(np.uint8)).save(os.path.join(out, "marco", "head_color.png"))
    body(rb, mean_rgb(mh, *SKIN_REF), (17, 17, 19), (20, 20, 22), (26, 22, 20), marco_badge).save(
        os.path.join(out, "marco", "body_color.png"))
    uh = maruchan_head(rb, rbx)
    Image.fromarray(np.clip(uh, 0, 255).astype(np.uint8)).save(os.path.join(out, "maruchan", "head_color.png"))
    body(rb, mean_rgb(uh, *SKIN_REF), (22, 32, 70), (20, 20, 22), (28, 26, 26), maruchan_text).save(
        os.path.join(out, "maruchan", "body_color.png"))
    print("wrote", out)


if __name__ == "__main__":
    main()
