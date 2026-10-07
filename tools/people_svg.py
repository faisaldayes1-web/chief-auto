"""Generates illustrated people (customers and salespeople) as SVG.

For each person: <id>_body.svg (full standing figure, neutral face) and <id>_face_<mood>.svg
(head and shoulders) for moods happy / neutral / angry. tools/render_svgs.js rasterises them.
The random pool is seeded, so the same id always produces the same person.
"""
import os, random, sys, json

W, H = 600, 1400
SKINS = [("#f6d2b8", "#d9a98a"), ("#eebf9a", "#c99673"), ("#d9a066", "#b37a45"), ("#b97a4a", "#8f5732"),
         ("#8d5530", "#6a3c1f"), ("#5e3a22", "#432814")]
HAIRS = ["#16120f", "#2d1d14", "#5a3a22", "#8a5a33", "#c9a063", "#e3c98f", "#7a2e1b", "#8e8e8e", "#d8d8d8"]
EYES = ["#3b2a1a", "#4a3220", "#2f5d7c", "#4b6b3a", "#6b5a3a"]
SHIRTS = ["#2d5d9f", "#b03a2e", "#3c7d4f", "#f2f2f2", "#6c3483", "#d68910", "#1f2a44", "#17a589", "#e8dfcf", "#222428", "#8e1f3b", "#5d6d7e"]
PANTS = ["#1f2430", "#2b2f3a", "#3a3f4a", "#5b4a36", "#2c3e50", "#4a4a4a", "#1b1b1b", "#6b6255"]
JACKETS = ["#1d2433", "#2b2b2f", "#3b3f46", "#6b5440", "#14213d", "#3d2b1f"]
SHOES = ["#151515", "#3b2416", "#e9e9e9", "#5a3b26"]


def shade(hexc, f):
    h = hexc.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if f < 0:
        r, g, b = [int(c * (1 + f)) for c in (r, g, b)]
    else:
        r, g, b = [int(c + (255 - c) * f) for c in (r, g, b)]
    return "#%02x%02x%02x" % (r, g, b)


def random_person(seed):
    rnd = random.Random(seed)
    fem = rnd.random() < 0.5
    age = rnd.choice(["young", "young", "mid", "mid", "old"])
    skin = rnd.randrange(len(SKINS))
    hair = rnd.choice(HAIRS[:7]) if age != "old" else rnd.choice(HAIRS[6:] + HAIRS[:2])
    if fem:
        style = rnd.choice(["long", "long", "bun", "ponytail", "bob", "curly_long", "wavy"])
    else:
        style = rnd.choice(["short", "side", "buzz", "curly", "bald", "short", "slick", "fade"])
    if age == "old" and not fem and rnd.random() < 0.4:
        style = "bald"
    outfit = rnd.choice(["polo", "tee", "shirt", "suit", "hoodie", "blouse" if fem else "shirt_tie", "jacket"])
    return {
        "fem": fem, "age": age, "skin": skin, "hair": hair, "style": style,
        "eyes": rnd.choice(EYES), "outfit": outfit, "shirt": rnd.choice(SHIRTS), "pants": rnd.choice(PANTS),
        "jacket": rnd.choice(JACKETS), "shoes": rnd.choice(SHOES),
        "beard": (None if fem else rnd.choice([None, None, "stubble", "beard", "goatee", "mustache"])),
        "glasses": rnd.random() < 0.15, "sunglasses": False, "earrings": fem and rnd.random() < 0.5,
        "build": rnd.uniform(0.92, 1.12), "badge": False, "tie": rnd.choice(["#8e1f1f", "#1f3a8e", "#2e2e2e", "#a07d2c"]),
    }


NAMED = {
    "amna": {"fem": True, "age": "young", "skin": 3, "hair": "#16120f", "style": "long", "eyes": "#3b2a1a", "outfit": "suit",
             "shirt": "#f4f1ec", "pants": "#14213d", "jacket": "#14213d", "shoes": "#151515", "beard": None, "glasses": False,
             "sunglasses": False, "earrings": True, "build": 0.96, "badge": True, "tie": "#222222"},
    "jeff": {"fem": False, "age": "young", "skin": 0, "hair": "#e3c98f", "style": "spiky", "eyes": "#2f5d7c", "outfit": "shirt_tie",
             "shirt": "#e67e22", "pants": "#5b4a36", "jacket": "#222222", "shoes": "#3b2416", "beard": None, "glasses": False,
             "sunglasses": False, "earrings": False, "build": 1.06, "badge": True, "tie": "#1f3a8e"},
    "maruchan": {"fem": False, "age": "young", "skin": 3, "hair": "#16120f", "style": "curly", "eyes": "#3b2a1a", "outfit": "polo",
                 "shirt": "#1d2f5e", "pants": "#1f2430", "jacket": "#222222", "shoes": "#151515", "beard": "goatee", "glasses": False,
                 "sunglasses": True, "earrings": False, "build": 1.0, "badge": True, "tie": "#222222"},
    "marco": {"fem": False, "age": "mid", "skin": 2, "hair": "#2d1d14", "style": "short", "eyes": "#3b2a1a", "outfit": "polo",
              "shirt": "#1b1b1f", "pants": "#1f2430", "jacket": "#222222", "shoes": "#151515", "beard": "goatee", "glasses": True,
              "sunglasses": False, "earrings": False, "build": 1.04, "badge": False, "tie": "#222222"},
}

DEFS = """
<filter id="soft"><feGaussianBlur stdDeviation="6"/></filter>
<filter id="soft2"><feGaussianBlur stdDeviation="2.5"/></filter>
<filter id="soft12"><feGaussianBlur stdDeviation="12"/></filter>
"""


def grad(id_, c1, c2, vertical=True, x1=0, y1=0, x2=0, y2=1):
    if vertical:
        return f'<linearGradient id="{id_}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"><stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient>'
    return f'<linearGradient id="{id_}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient>'


def person_svg(p, mood="neutral", body=True, view=None):
    skin, skin_d = SKINS[p["skin"]]
    hair = p["hair"]
    b = p["build"]
    fem = p["fem"]
    o = []
    defs = [DEFS]
    defs.append(f'<radialGradient id="face" cx="0.42" cy="0.38" r="0.7"><stop offset="0" stop-color="{shade(skin, 0.12)}"/><stop offset="0.7" stop-color="{skin}"/><stop offset="1" stop-color="{skin_d}"/></radialGradient>')
    defs.append(grad("neck", skin_d, shade(skin_d, -0.15)))
    defs.append(grad("hair", shade(hair, 0.25), shade(hair, -0.3)))
    defs.append(grad("shirt", shade(p["shirt"], 0.12), shade(p["shirt"], -0.28)))
    defs.append(grad("jacket", shade(p["jacket"], 0.15), shade(p["jacket"], -0.35)))
    defs.append(grad("pants", shade(p["pants"], 0.1), shade(p["pants"], -0.3)))
    defs.append(grad("skinarm", skin, skin_d))
    defs.append(f'<radialGradient id="iris" cx="0.5" cy="0.4" r="0.6"><stop offset="0" stop-color="{shade(p["eyes"], 0.35)}"/><stop offset="1" stop-color="{shade(p["eyes"], -0.3)}"/></radialGradient>')
    defs.append(grad("lip", shade("#b5574f" if not fem else "#c0485a", 0.1), shade("#8c3b35" if not fem else "#94303f", -0.1)))

    sw = 150 * b  # half shoulder width
    hx, hy = 300, 250  # head centre

    if body:
        # shadow on the floor
        o.append(f'<ellipse cx="300" cy="1372" rx="150" ry="18" fill="#000" opacity="0.35" filter="url(#soft)"/>')
        # legs
        lw = 52 * b
        pants = "url(#pants)"
        if p["outfit"] == "blouse" and fem and p["pants"] in ("#5b4a36", "#6b6255"):
            pants = "url(#pants)"
        o.append(f'<path d="M {300 - sw * 0.62} 820 L {300 + sw * 0.62} 820 L {300 + sw * 0.58} 1340 L {300 + 12} 1340 L 300 900 L {300 - 12} 1340 L {300 - sw * 0.58} 1340 Z" fill="{pants}"/>')
        o.append(f'<path d="M 300 905 L 300 1330" stroke="#000" stroke-opacity="0.25" stroke-width="3"/>')
        # shoes
        sh = p["shoes"]
        o.append(f'<path d="M {300 - sw * 0.6} 1330 q -10 30 -46 38 q 50 10 104 2 l -4 -40 z" fill="{sh}"/>')
        o.append(f'<path d="M {300 + sw * 0.6} 1330 q 10 30 46 38 q -50 10 -104 2 l 4 -40 z" fill="{sh}"/>')
        # belt
        o.append(f'<rect x="{300 - sw * 0.64}" y="806" width="{sw * 1.28}" height="22" rx="4" fill="#1a1512"/><rect x="290" y="808" width="22" height="18" rx="3" fill="#b9a46a"/>')
        torso_bottom = 820
    else:
        torso_bottom = 900

    # back hair for long styles
    if p["style"] in ("long", "curly_long", "wavy"):
        length = 600 if body else 600
        o.append(f'<path d="M {hx - 112} {hy - 30} Q {hx - 150} {hy + 200} {hx - 120} {length} L {hx + 120} {length} Q {hx + 150} {hy + 200} {hx + 112} {hy - 30} Z" fill="url(#hair)"/>')

    # torso and arms
    shirt_fill = "url(#shirt)"
    jacket = p["outfit"] in ("suit", "jacket")
    top_fill = "url(#jacket)" if jacket else shirt_fill
    if p["outfit"] == "hoodie":
        top_fill = shirt_fill
    torso = f'M {300 - sw * 0.42} 395 Q {300 - sw} 400 {300 - sw} 470 L {300 - sw * 0.98} 560 Q {300 - sw * 0.72} 700 {300 - sw * 0.66} {torso_bottom} L {300 + sw * 0.66} {torso_bottom} Q {300 + sw * 0.72} 700 {300 + sw * 0.98} 560 L {300 + sw} 470 Q {300 + sw} 400 {300 + sw * 0.42} 395 Z'
    # arms
    if body:
        for side in (-1, 1):
            ax = 300 + side * sw * 0.93
            o.append(f'<path d="M {ax - 34 * side} 440 Q {ax + 30 * side} 470 {ax + 26 * side} 600 L {ax + 30 * side} 790 L {ax - 18 * side} 795 L {ax - 26 * side} 610 Z" fill="{top_fill}"/>')
            o.append(f'<path d="M {ax + 28 * side} 600 L {ax + 30 * side} 790" stroke="#000" stroke-opacity="0.18" stroke-width="6"/>')
            # hand
            o.append(f'<ellipse cx="{ax + 6 * side}" cy="822" rx="25" ry="36" fill="url(#skinarm)"/>')
            o.append(f'<path d="M {ax - 10 * side} 830 q 8 18 22 16" stroke="{skin_d}" stroke-width="3" fill="none"/>')
    o.append(f'<path d="{torso}" fill="{top_fill}"/>')
    # neck
    o.append(f'<path d="M {hx - 38} {hy + 80} L {hx - 40} {hy + 158} Q {hx} {hy + 185} {hx + 40} {hy + 158} L {hx + 38} {hy + 80} Z" fill="url(#neck)"/>')
    o.append(f'<ellipse cx="{hx}" cy="{hy + 104}" rx="40" ry="18" fill="#000" opacity="0.18" filter="url(#soft2)"/>')
    # collar / shirt details
    out = p["outfit"]
    if jacket:
        # shirt visible in a V with lapels
        o.append(f'<path d="M {hx - 46} 400 L {hx} {560 if out == "suit" else 520} L {hx + 46} 400 Z" fill="{shirt_fill}"/>')
        if out == "suit" and not fem:
            o.append(f'<path d="M {hx - 12} 410 L {hx + 12} 410 L {hx + 18} 560 L {hx} 590 L {hx - 18} 560 Z" fill="{p["tie"]}"/>')
        o.append(f'<path d="M {hx - 50} 396 L {hx - 4} 600 L {hx - 82} 470 L {hx - 66} 430 Z" fill="{shade(p["jacket"], -0.2)}"/>')
        o.append(f'<path d="M {hx + 50} 396 L {hx + 4} 600 L {hx + 82} 470 L {hx + 66} 430 Z" fill="{shade(p["jacket"], -0.2)}"/>')
        for k in range(2):
            o.append(f'<circle cx="{hx + 8}" cy="{650 + k * 60}" r="6" fill="{shade(p["jacket"], -0.45)}"/>')
    elif out == "polo":
        o.append(f'<path d="M {hx - 50} 392 L {hx - 18} 440 L {hx} 410 L {hx + 18} 440 L {hx + 50} 392 Z" fill="{shade(p["shirt"], -0.15)}"/>')
        o.append(f'<path d="M {hx} 412 L {hx} 500" stroke="{shade(p["shirt"], -0.35)}" stroke-width="3"/>')
        for k in range(2):
            o.append(f'<circle cx="{hx}" cy="{440 + k * 30}" r="4" fill="{shade(p["shirt"], 0.3)}"/>')
    elif out in ("shirt", "shirt_tie"):
        o.append(f'<path d="M {hx - 48} 390 L {hx - 14} 450 L {hx} 412 L {hx + 14} 450 L {hx + 48} 390 Z" fill="{shade(p["shirt"], 0.2)}"/>')
        if out == "shirt_tie":
            o.append(f'<path d="M {hx - 12} 412 L {hx + 12} 412 L {hx + 20} 640 L {hx} 680 L {hx - 20} 640 Z" fill="{p["tie"]}"/>')
        else:
            o.append(f'<path d="M {hx} 420 L {hx} 800" stroke="{shade(p["shirt"], -0.3)}" stroke-width="2"/>')
    elif out == "hoodie":
        o.append(f'<path d="M {hx - 70} 390 Q {hx} 470 {hx + 70} 390" stroke="{shade(p["shirt"], -0.3)}" stroke-width="16" fill="none"/>')
        o.append(f'<path d="M {hx - 16} 430 L {hx - 20} 540 M {hx + 16} 430 L {hx + 20} 540" stroke="#ddd" stroke-width="4"/>')
        o.append(f'<path d="M {hx - 80} 680 L {hx + 80} 680 L {hx + 70} 770 L {hx - 70} 770 Z" fill="{shade(p["shirt"], -0.15)}"/>')
    else:  # tee / blouse
        o.append(f'<path d="M {hx - 46} 392 Q {hx} {440 if out == "tee" else 470} {hx + 46} 392" stroke="{shade(p["shirt"], -0.25)}" stroke-width="7" fill="none"/>')
    if p.get("badge"):
        o.append(f'<rect x="{hx + sw * 0.32}" y="470" width="58" height="22" rx="3" fill="#e8b64c"/><rect x="{hx + sw * 0.32 + 6}" y="477" width="46" height="4" fill="#5a4211"/>')
    # torso shading
    o.append(f'<path d="{torso}" fill="#000" opacity="0.10" transform="translate(14,0)" filter="url(#soft12)"/>')

    # ---------- head
    jaw = 92 if fem else 100
    o.append(f'<ellipse cx="{hx - 104}" cy="{hy + 8}" rx="20" ry="32" fill="{skin_d}"/><ellipse cx="{hx + 104}" cy="{hy + 8}" rx="20" ry="32" fill="{skin_d}"/>')
    face = f'M {hx - 104} {hy - 40} Q {hx - 108} {hy + 60} {hx - jaw * 0.75} {hy + 100} Q {hx - 40} {hy + 150} {hx} {hy + 152} Q {hx + 40} {hy + 150} {hx + jaw * 0.75} {hy + 100} Q {hx + 108} {hy + 60} {hx + 104} {hy - 40} Q {hx + 100} {hy - 145} {hx} {hy - 148} Q {hx - 100} {hy - 145} {hx - 104} {hy - 40} Z'
    o.append(f'<path d="{face}" fill="url(#face)"/>')
    # cheek and jaw shading
    o.append(f'<path d="M {hx - 92} {hy + 40} Q {hx - 70} {hy + 130} {hx} {hy + 150} Q {hx - 40} {hy + 110} {hx - 92} {hy + 40} Z" fill="{skin_d}" opacity="0.35" filter="url(#soft2)"/>')
    o.append(f'<path d="M {hx + 92} {hy + 40} Q {hx + 70} {hy + 130} {hx} {hy + 150} Q {hx + 40} {hy + 110} {hx + 92} {hy + 40} Z" fill="{skin_d}" opacity="0.45" filter="url(#soft2)"/>')
    if mood == "happy" or fem:
        o.append(f'<ellipse cx="{hx - 58}" cy="{hy + 52}" rx="22" ry="12" fill="#e2766a" opacity="{0.28 if mood == "happy" else 0.15}" filter="url(#soft2)"/>')
        o.append(f'<ellipse cx="{hx + 58}" cy="{hy + 52}" rx="22" ry="12" fill="#e2766a" opacity="{0.28 if mood == "happy" else 0.15}" filter="url(#soft2)"/>')
    if mood == "angry":
        o.append(f'<path d="{face}" fill="#d0302a" opacity="0.16"/>')
    # beard
    bc = shade(hair, -0.05)
    if p["beard"] == "stubble":
        o.append(f'<path d="M {hx - 95} {hy + 50} Q {hx - 70} {hy + 140} {hx} {hy + 152} Q {hx + 70} {hy + 140} {hx + 95} {hy + 50} Q {hx + 50} {hy + 110} {hx} {hy + 108} Q {hx - 50} {hy + 110} {hx - 95} {hy + 50} Z" fill="{bc}" opacity="0.28"/>')
    elif p["beard"] == "beard":
        o.append(f'<path d="M {hx - 100} {hy + 20} Q {hx - 80} {hy + 170} {hx} {hy + 175} Q {hx + 80} {hy + 170} {hx + 100} {hy + 20} Q {hx + 60} {hy + 100} {hx} {hy + 96} Q {hx - 60} {hy + 100} {hx - 100} {hy + 20} Z" fill="{bc}"/>')
    elif p["beard"] == "goatee":
        o.append(f'<path d="M {hx - 34} {hy + 108} Q {hx} {hy + 170} {hx + 34} {hy + 108} Q {hx} {hy + 124} {hx - 34} {hy + 108} Z" fill="{bc}"/>')
    if p["beard"] in ("mustache", "goatee", "beard"):
        o.append(f'<path d="M {hx - 38} {hy + 82} Q {hx} {hy + 66} {hx + 38} {hy + 82} Q {hx} {hy + 76} {hx - 38} {hy + 82} Z" fill="{bc}"/>')
    # eyes
    ey = hy + 4
    squint = {"happy": 0.75, "neutral": 1.0, "angry": 0.8}[mood]
    for side in (-1, 1):
        ex = hx + side * 42
        o.append(f'<ellipse cx="{ex}" cy="{ey}" rx="22" ry="{12 * squint}" fill="#fbfaf7"/>')
        o.append(f'<circle cx="{ex + 2}" cy="{ey + 1}" r="{10 * min(1, squint + 0.1)}" fill="url(#iris)"/>')
        o.append(f'<circle cx="{ex + 2}" cy="{ey + 1}" r="4.5" fill="#111"/>')
        o.append(f'<circle cx="{ex + 6}" cy="{ey - 3}" r="2.6" fill="#fff"/>')
        # upper lid and lashes
        o.append(f'<path d="M {ex - 24} {ey + 1} Q {ex} {ey - 16 * squint} {ex + 24} {ey + 1}" stroke="#2a1d16" stroke-width="{4 if fem else 3}" fill="none"/>')
        if fem:
            o.append(f'<path d="M {ex + side * 22} {ey - 2} l {side * 8} -6" stroke="#2a1d16" stroke-width="3"/>')
        # lower lid shading
        o.append(f'<path d="M {ex - 20} {ey + 9} Q {ex} {ey + 15} {ex + 20} {ey + 9}" stroke="{skin_d}" stroke-width="2" fill="none" opacity="0.7"/>')
        # brows
        by = ey - 30
        if mood == "angry":
            inner, outer = by + 14, by - 2
        elif mood == "happy":
            inner, outer = by - 4, by + 2
        else:
            inner, outer = by, by + 2
        bw = 7 if not fem else 5
        o.append(f'<path d="M {ex - side * 26} {outer if side < 0 else inner} Q {ex} {by - 8} {ex + side * 26} {inner if side < 0 else outer}" stroke="{shade(hair, -0.1) if p["style"] != "bald" else shade(skin_d, -0.4)}" stroke-width="{bw}" stroke-linecap="round" fill="none"/>')
    # nose
    o.append(f'<path d="M {hx - 4} {hy + 6} Q {hx - 10} {hy + 44} {hx - 18} {hy + 56} Q {hx} {hy + 66} {hx + 16} {hy + 56}" stroke="{skin_d}" stroke-width="3.5" fill="none" stroke-linecap="round"/>')
    o.append(f'<path d="M {hx + 4} {hy + 10} Q {hx + 8} {hy + 34} {hx + 6} {hy + 46}" stroke="#fff" stroke-opacity="0.25" stroke-width="4" fill="none"/>')
    # mouth
    my = hy + 96
    if mood == "happy":
        o.append(f'<path d="M {hx - 34} {my - 4} Q {hx} {my + 30} {hx + 34} {my - 4} Q {hx} {my + 6} {hx - 34} {my - 4} Z" fill="#5a1e1a"/>')
        o.append(f'<path d="M {hx - 26} {my} Q {hx} {my + 10} {hx + 26} {my} L {hx + 22} {my + 6} Q {hx} {my + 14} {hx - 22} {my + 6} Z" fill="#fff"/>')
        o.append(f'<path d="M {hx - 34} {my - 4} Q {hx} {my + 30} {hx + 34} {my - 4}" stroke="url(#lip)" stroke-width="5" fill="none"/>')
    elif mood == "angry":
        o.append(f'<path d="M {hx - 30} {my + 8} Q {hx} {my - 10} {hx + 30} {my + 8}" stroke="url(#lip)" stroke-width="8" fill="none" stroke-linecap="round"/>')
    else:
        o.append(f'<path d="M {hx - 28} {my} Q {hx} {my + 8} {hx + 28} {my}" stroke="url(#lip)" stroke-width="8" fill="none" stroke-linecap="round"/>')
        o.append(f'<path d="M {hx - 22} {my + 10} Q {hx} {my + 16} {hx + 22} {my + 10}" stroke="#fff" stroke-opacity="0.15" stroke-width="3" fill="none"/>')
    # front hair
    st = p["style"]
    hf = "url(#hair)"
    top = hy - 150
    if st in ("short", "side", "slick", "fade"):
        part = {"short": 0, "side": -40, "slick": 0, "fade": 0}[st]
        o.append(f'<path d="M {hx - 108} {hy - 10} Q {hx - 120} {top - 20} {hx + part} {top - 14} Q {hx + 120} {top - 20} {hx + 108} {hy - 10} Q {hx + 100} {hy - 80} {hx + 60} {hy - 96} Q {hx + part} {hy - 70 if st != "slick" else hy - 110} {hx - 60} {hy - 96} Q {hx - 100} {hy - 80} {hx - 108} {hy - 10} Z" fill="{hf}"/>')
        if st == "fade":
            o.append(f'<path d="M {hx - 108} {hy - 10} Q {hx - 104} {hy - 60} {hx - 96} {hy - 80} L {hx - 104} {hy + 30} Z" fill="{hair}" opacity="0.35"/>')
    elif st == "buzz":
        o.append(f'<path d="M {hx - 104} {hy - 30} Q {hx - 104} {top - 4} {hx} {top - 4} Q {hx + 104} {top - 4} {hx + 104} {hy - 30} Q {hx} {hy - 100} {hx - 104} {hy - 30} Z" fill="{hair}" opacity="0.8"/>')
    elif st == "spiky":
        pts = f"{hx - 110},{hy - 20} {hx - 120},{top + 10} {hx - 80},{top - 10} {hx - 70},{top - 50} {hx - 30},{top - 10} {hx - 10},{top - 60} {hx + 20},{top - 12} {hx + 50},{top - 54} {hx + 66},{top - 4} {hx + 110},{top - 30} {hx + 108},{top + 30} {hx + 112},{hy - 20} {hx + 60},{hy - 92} {hx - 60},{hy - 92}"
        o.append(f'<polygon points="{pts}" fill="{hf}"/>')
    elif st in ("curly", "curly_long"):
        import math
        rnd = random.Random(hash(hair) + p["skin"])
        for k in range(26):
            a = math.pi * (1.05 + k / 25 * 0.9)
            rr = 118 + rnd.uniform(-6, 10)
            cx = hx + math.cos(a) * rr * 0.98
            cy = hy - 40 + math.sin(a) * rr * 0.95
            o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rnd.uniform(26, 36):.1f}" fill="{shade(hair, rnd.uniform(-0.2, 0.15))}"/>')
        o.append(f'<path d="M {hx - 100} {hy - 40} Q {hx} {hy - 140} {hx + 100} {hy - 40} Q {hx} {hy - 92} {hx - 100} {hy - 40} Z" fill="{hair}"/>')
    elif st in ("long", "wavy", "bob", "bun", "ponytail"):
        o.append(f'<path d="M {hx - 112} {hy + (60 if st in ("long", "wavy") else 30)} Q {hx - 126} {top - 30} {hx} {top - 18} Q {hx + 126} {top - 30} {hx + 112} {hy + (60 if st in ("long", "wavy") else 30)} Q {hx + 100} {hy - 70} {hx + 40} {hy - 100} Q {hx - 20} {hy - 60} {hx - 90} {hy - 70} Q {hx - 104} {hy - 20} {hx - 112} {hy + 60} Z" fill="{hf}"/>')
        if st == "bob":
            o.append(f'<path d="M {hx - 112} {hy + 30} Q {hx - 116} {hy + 110} {hx - 80} {hy + 120} L {hx - 96} {hy - 20} Z M {hx + 112} {hy + 30} Q {hx + 116} {hy + 110} {hx + 80} {hy + 120} L {hx + 96} {hy - 20} Z" fill="{hf}"/>')
        if st == "bun":
            o.append(f'<circle cx="{hx}" cy="{top - 40}" r="46" fill="{hf}"/>')
        if st == "ponytail":
            o.append(f'<path d="M {hx + 90} {top + 40} Q {hx + 170} {hy} {hx + 120} {hy + 200} Q {hx + 140} {hy + 40} {hx + 70} {top + 60} Z" fill="{hf}"/>')
        # shine
        o.append(f'<path d="M {hx - 60} {top + 2} Q {hx} {top - 14} {hx + 50} {top + 4}" stroke="#fff" stroke-opacity="0.22" stroke-width="10" fill="none" stroke-linecap="round"/>')
    if st not in ("bald", "buzz", "curly", "curly_long", "spiky"):
        o.append(f'<path d="M {hx - 50} {top + 4} Q {hx} {top - 10} {hx + 46} {top + 6}" stroke="#fff" stroke-opacity="0.18" stroke-width="8" fill="none" stroke-linecap="round"/>')
    if st == "bald":
        o.append(f'<ellipse cx="{hx - 30}" cy="{top + 30}" rx="40" ry="18" fill="#fff" opacity="0.2"/>')
        o.append(f'<path d="M {hx - 108} {hy - 10} Q {hx - 112} {hy - 50} {hx - 100} {hy - 60} L {hx - 104} {hy + 10} Z M {hx + 108} {hy - 10} Q {hx + 112} {hy - 50} {hx + 100} {hy - 60} L {hx + 104} {hy + 10} Z" fill="{hair}" opacity="0.7"/>')
    # earrings
    if p["earrings"]:
        o.append(f'<circle cx="{hx - 106}" cy="{hy + 44}" r="7" fill="#e8c35a"/><circle cx="{hx + 106}" cy="{hy + 44}" r="7" fill="#e8c35a"/>')
    # glasses
    if p["sunglasses"]:
        for side in (-1, 1):
            o.append(f'<path d="M {hx + side * 10} {ey - 16} L {hx + side * 72} {ey - 18} Q {hx + side * 74} {ey + 22} {hx + side * 42} {ey + 24} Q {hx + side * 12} {ey + 22} {hx + side * 10} {ey - 16} Z" fill="#0b0c10"/>')
            o.append(f'<path d="M {hx + side * 24} {ey - 8} L {hx + side * 50} {ey - 10}" stroke="#fff" stroke-opacity="0.35" stroke-width="4"/>')
        o.append(f'<path d="M {hx - 12} {ey - 12} Q {hx} {ey - 18} {hx + 12} {ey - 12}" stroke="#0b0c10" stroke-width="5" fill="none"/>')
    elif p["glasses"]:
        for side in (-1, 1):
            o.append(f'<rect x="{hx + side * 42 - 30}" y="{ey - 20}" width="60" height="40" rx="12" fill="#fff" fill-opacity="0.08" stroke="#1b1b1f" stroke-width="5"/>')
        o.append(f'<path d="M {hx - 12} {ey - 6} Q {hx} {ey - 12} {hx + 12} {ey - 6}" stroke="#1b1b1f" stroke-width="5" fill="none"/>')
    vb = view or (0, 0, W, H)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{vb[2]}" height="{vb[3]}" viewBox="{vb[0]} {vb[1]} {vb[2]} {vb[3]}">'
            f'<defs>{"".join(defs)}</defs>{"".join(o)}</svg>')


POOL = 40

if __name__ == "__main__":
    out = sys.argv[1]
    for sub in ("body", "face"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)
    people = {k: v for k, v in NAMED.items()}
    for i in range(POOL):
        people["p%02d" % i] = random_person(1000 + i * 7)
    for pid, p in people.items():
        open(os.path.join(out, "body", f"{pid}_body.svg"), "w").write(person_svg(p, "neutral", True))
        for mood in ("happy", "neutral", "angry"):
            open(os.path.join(out, "face", f"{pid}_face_{mood}.svg"), "w").write(person_svg(p, mood, False, (100, 0, 400, 480)))
    json.dump({k: {"fem": v["fem"]} for k, v in people.items()}, open(os.path.join(out, "people.json"), "w"))
    print(len(people), "people")
