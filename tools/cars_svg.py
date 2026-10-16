"""Generates side-view car renders as SVG for every model in the game.

Each model is written twice: <slug>_paint.svg (body panels in neutral grey, tinted in-game to the
car's paint colour) and <slug>_detail.svg (glass, wheels, lights, trim, highlights and shadow).
tools/render_svgs.js rasterises them to assets/cars/*.png with Chromium.
"""
import math, os, sys

W, H = 1000, 400
GROUND = 372

# ---------------------------------------------------------------- geometry helpers

def rounded_path(pts, radii):
    """Closed path through pts with each corner rounded by a quadratic curve of the given radius."""
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        r = radii[i]
        if r <= 0:
            out.append(("L", p1))
            continue
        def toward(a, b, d):
            dx, dy = b[0] - a[0], b[1] - a[1]
            l = math.hypot(dx, dy) or 1
            d = min(d, l * 0.48)
            return (a[0] + dx / l * d, a[1] + dy / l * d)
        a = toward(p1, p0, r)
        b = toward(p1, p2, r)
        out.append(("L", a))
        out.append(("Q", p1, b))
    d = "M %.1f %.1f " % out[-1][-1] if out[-1][0] == "Q" else "M %.1f %.1f " % out[-1][1]
    for seg in out:
        if seg[0] == "L":
            d += "L %.1f %.1f " % seg[1]
        else:
            d += "Q %.1f %.1f %.1f %.1f " % (seg[1][0], seg[1][1], seg[2][0], seg[2][1])
    return d + "Z"


def body_outline(m):
    """Upper outline points (rear bottom -> over the top -> front bottom), each with a corner radius."""
    t = m["type"]
    x0, x1 = m["x0"], m["x1"]
    rb, fb = m["rb"], m["fb"]
    pts = []
    if t == "truck":
        pts = [
            ((x0 + 10, rb), 10), ((x0, rb - 30), 12), ((x0 + 2, m["bed"]), 6), ((m["cab"] - 6, m["bed"]), 4),
            ((m["cab"], m["bed"] - 4), 6), ((m["cab"] + 6, m["roofY"]), 22), ((m["rx1"], m["roofY"]), 26),
            ((m["cowlX"], m["hoodY"]), 30), ((x1 - 30, m["noseY"]), 30), ((x1, m["noseY"] + 18), 16),
            ((x1 + 2, fb - 20), 14), ((x1 - 12, fb), 10),
        ]
    elif t == "boxy":
        pts = [
            ((x0 + 8, rb), 10), ((x0, rb - 40), 10), ((x0 + 2, m["roofY"] + 20), 18), ((x0 + 20, m["roofY"]), 18),
            ((m["rx1"], m["roofY"]), 14), ((m["cowlX"], m["hoodY"]), 18), ((x1 - 20, m["noseY"]), 18),
            ((x1, m["noseY"] + 15), 10), ((x1 + 2, fb - 20), 10), ((x1 - 10, fb), 8),
        ]
    elif t == "suv":
        pts = [
            ((x0 + 10, rb), 12), ((x0, rb - 40), 16), ((x0 + 8, m["deckY"]), 24), ((m["rx0"], m["roofY"]), 40),
            ((m["rx1"], m["roofY"]), 40), ((m["cowlX"], m["hoodY"]), 40), ((x1 - 40, m["noseY"]), 34),
            ((x1, m["noseY"] + 22), 18), ((x1 + 2, fb - 22), 14), ((x1 - 14, fb), 10),
        ]
    elif t == "wedge":
        pts = [
            ((x0 + 12, rb), 10), ((x0, rb - 30), 12), ((x0 + 10, m["deckY"]), 14), ((m["rearGlassX"], m["deckY"] - 14), 60),
            ((m["rx0"], m["roofY"]), 60), ((m["rx1"], m["roofY"]), 60), ((m["cowlX"], m["hoodY"]), 120),
            ((x1 - 20, m["noseY"]), 40), ((x1, m["noseY"] + 12), 8), ((x1 - 2, fb - 10), 8), ((x1 - 16, fb), 6),
        ]
    else:  # sedan, coupe, fastback, hatch
        pts = [
            ((x0 + 22, rb), 14), ((x0 + 2, rb - 34), 22), ((x0, m["deckY"] + 16), 22), ((x0 + 36, m["deckY"]), 30),
            ((m["rearGlassX"], m["deckY"] - 4), 40 if t != "fastback" else 80), ((m["rx0"], m["roofY"]), 70 if t != "fastback" else 110),
            ((m["rx1"], m["roofY"]), 60), ((m["cowlX"], m["hoodY"]), 50), ((x1 - 60, m["noseY"]), 60),
            ((x1, m["noseY"] + 30), 34), ((x1 - 6, fb - 22), 26), ((x1 - 30, fb), 14),
        ]
    return pts


def car_path(m):
    """Full body outline: upper outline plus the lower edge with wheel arches cut out."""
    upper = body_outline(m)
    r = m["r"]
    ar = r + 9
    cy = GROUND - r
    rx, fx = m["rw"], m["fw"]
    pts = [p for p, _ in upper]
    radii = [rad for _, rad in upper]
    d = rounded_path(pts, radii)
    # the closed outline runs front-bottom -> rear-bottom along a straight line; replace with arches
    # by subtracting arch circles via a mask instead (simpler, smooth): done in the SVG with a mask.
    return d, (rx, cy, ar), (fx, cy, ar)


def window_path(m):
    t = m["type"]
    belt = m["belt"]
    ry = m["roofY"] + m.get("glassTop", 12)
    if t == "truck":
        pts = [(m["cab"] + 16, belt), (m["cab"] + 18, ry), (m["rx1"] - 4, ry), (m["cowlX"] - 26, belt)]
        rad = [4, 14, 16, 4]
    elif t == "boxy":
        pts = [(m["x0"] + 26, belt), (m["x0"] + 28, ry), (m["rx1"] - 4, ry), (m["cowlX"] - 18, belt)]
        rad = [4, 10, 10, 4]
    elif t == "wedge":
        pts = [(m["rearGlassX"] + 30, belt), (m["rx0"] + 6, ry), (m["rx1"], ry + 2), (m["cowlX"] - 70, belt)]
        rad = [4, 50, 50, 6]
    else:
        rg = m.get("rearGlassX", m["x0"] + 8)
        pts = [(rg + 20, belt), (m["rx0"] + 6, ry), (m["rx1"] - 4, ry), (m["cowlX"] - 30, belt)]
        rad = [4, 46 if t != "fastback" else 70, 40, 4]
    return rounded_path(pts, rad), pts


def svg_wheel(cx, cy, r, m, idx):
    spokes = m.get("spokes", 5)
    rim = r * m.get("rimScale", 0.66)
    o = []
    o.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#tire)"/>')
    o.append(f'<circle cx="{cx}" cy="{cy}" r="{r - 3}" fill="none" stroke="#2a2a2e" stroke-width="2"/>')
    o.append(f'<circle cx="{cx}" cy="{cy}" r="{rim + 3}" fill="#101012"/>')
    o.append(f'<circle cx="{cx}" cy="{cy}" r="{rim}" fill="url(#rim{m.get("rimStyle", "")})"/>')
    # brake disc and caliper behind the spokes
    o.append(f'<circle cx="{cx}" cy="{cy}" r="{rim * 0.78}" fill="url(#disc)"/>')
    if m.get("caliper"):
        a0 = -2.2
        o.append(f'<path d="{arc_band(cx, cy, rim * 0.6, rim * 0.8, a0, a0 + 0.9)}" fill="{m["caliper"]}"/>')
    rim_c = m.get("rimColor", "#d9dde3")
    rim_d = m.get("rimDark", "#7d838c")
    for k in range(spokes):
        a = 2 * math.pi * k / spokes + idx * 0.3
        w = m.get("spokeW", 0.16)
        pts = []
        for (rr, aa) in [(rim * 0.2, a - w * 1.6), (rim * 0.96, a - w * 0.55), (rim * 0.96, a + w * 0.55), (rim * 0.2, a + w * 1.6)]:
            pts.append((cx + math.cos(aa) * rr, cy + math.sin(aa) * rr))
        dpts = " ".join("%.1f,%.1f" % p for p in pts)
        o.append(f'<polygon points="{dpts}" fill="{rim_c}" stroke="{rim_d}" stroke-width="1.2"/>')
    o.append(f'<circle cx="{cx}" cy="{cy}" r="{rim * 0.22}" fill="url(#hub)"/>')
    o.append(f'<circle cx="{cx}" cy="{cy}" r="{rim}" fill="none" stroke="#f4f6f8" stroke-opacity="0.6" stroke-width="2"/>')
    o.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#tireshine)"/>')
    return "\n".join(o)


def arc_band(cx, cy, r0, r1, a0, a1):
    p = lambda r, a: (cx + math.cos(a) * r, cy + math.sin(a) * r)
    s0, e0, s1, e1 = p(r1, a0), p(r1, a1), p(r0, a1), p(r0, a0)
    return f"M {s0[0]:.1f} {s0[1]:.1f} A {r1} {r1} 0 0 1 {e0[0]:.1f} {e0[1]:.1f} L {s1[0]:.1f} {s1[1]:.1f} A {r0} {r0} 0 0 0 {e1[0]:.1f} {e1[1]:.1f} Z"


DEFS = """
<linearGradient id="paint" x1="0" y1="0" x2="0" y2="1" gradientUnits="userSpaceOnUse" x2_="0">
</linearGradient>
<radialGradient id="tire" cx="0.5" cy="0.5" r="0.5">
  <stop offset="0.62" stop-color="#1c1c1f"/><stop offset="0.9" stop-color="#2b2b30"/><stop offset="1" stop-color="#121214"/>
</radialGradient>
<radialGradient id="tireshine" cx="0.35" cy="0.25" r="0.75">
  <stop offset="0" stop-color="#ffffff" stop-opacity="0.10"/><stop offset="0.5" stop-color="#ffffff" stop-opacity="0"/>
</radialGradient>
<radialGradient id="rim" cx="0.4" cy="0.35" r="0.75">
  <stop offset="0" stop-color="#3a3e45"/><stop offset="1" stop-color="#16181c"/>
</radialGradient>
<radialGradient id="rimgold" cx="0.4" cy="0.35" r="0.75">
  <stop offset="0" stop-color="#3a3428"/><stop offset="1" stop-color="#15130f"/>
</radialGradient>
<radialGradient id="disc" cx="0.5" cy="0.5" r="0.5">
  <stop offset="0.3" stop-color="#55585e"/><stop offset="0.85" stop-color="#8b9097"/><stop offset="1" stop-color="#4b4e54"/>
</radialGradient>
<radialGradient id="hub" cx="0.4" cy="0.35" r="0.7">
  <stop offset="0" stop-color="#f2f3f5"/><stop offset="1" stop-color="#8e949c"/>
</radialGradient>
<linearGradient id="glass" x1="0" y1="0" x2="0.35" y2="1">
  <stop offset="0" stop-color="#3d4b5c"/><stop offset="0.45" stop-color="#1a2330"/><stop offset="1" stop-color="#0b1017"/>
</linearGradient>
<linearGradient id="chrome" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#ffffff"/><stop offset="0.5" stop-color="#9aa1aa"/><stop offset="1" stop-color="#e6e9ed"/>
</linearGradient>
<linearGradient id="head" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#ffffff"/><stop offset="0.6" stop-color="#e8eef5"/><stop offset="1" stop-color="#9fb2c6"/>
</linearGradient>
<linearGradient id="tail" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#ff5a4f"/><stop offset="0.6" stop-color="#b3120c"/><stop offset="1" stop-color="#5c0805"/>
</linearGradient>
<filter id="blur8"><feGaussianBlur stdDeviation="8"/></filter>
<filter id="blur3"><feGaussianBlur stdDeviation="3"/></filter>
<filter id="blur1"><feGaussianBlur stdDeviation="1.2"/></filter>
"""


def paint_gradient(m):
    top, belt, bot = m["roofY"], m["belt"], m["rb"]
    def off(y):
        return max(0.0, min(1.0, (y - top) / (bot - top)))
    b = off(belt)
    return f"""<linearGradient id="paintg" x1="0" y1="{top}" x2="0" y2="{bot}" gradientUnits="userSpaceOnUse">
  <stop offset="0" stop-color="#f4f4f4"/>
  <stop offset="{max(0, b - 0.12):.3f}" stop-color="#dcdcdc"/>
  <stop offset="{b:.3f}" stop-color="#cfcfcf"/>
  <stop offset="{min(1, b + 0.04):.3f}" stop-color="#ffffff"/>
  <stop offset="{min(1, b + 0.12):.3f}" stop-color="#c4c4c4"/>
  <stop offset="{min(1, b + 0.4):.3f}" stop-color="#9a9a9a"/>
  <stop offset="1" stop-color="#4a4a4a"/>
</linearGradient>"""


def build(m):
    body_d, rear_arch, front_arch = car_path(m)
    win_d, win_pts = window_path(m)
    r = m["r"]
    cy = GROUND - r
    mask = f"""<mask id="arches" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">
  <rect width="{W}" height="{H}" fill="white"/>
  <circle cx="{rear_arch[0]}" cy="{rear_arch[1]}" r="{rear_arch[2]}" fill="black"/>
  <circle cx="{front_arch[0]}" cy="{front_arch[1]}" r="{front_arch[2]}" fill="black"/>
</mask>"""
    clip = f'<clipPath id="bodyclip"><path d="{body_d}"/></clipPath>'
    belt = m["belt"]
    x0, x1 = m["x0"], m["x1"]

    # ---------- paint layer (neutral grey, tinted in game)
    paint = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><defs>{DEFS}{paint_gradient(m)}{mask}{clip}</defs>']
    paint.append(f'<g mask="url(#arches)"><path d="{body_d}" fill="url(#paintg)"/></g>')
    paint.append("</svg>")

    # ---------- detail layer
    d = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><defs>{DEFS}{mask}{clip}</defs>']
    # ground shadow (under everything)
    d.append(f'<ellipse cx="{(x0 + x1) / 2}" cy="{GROUND + 2}" rx="{(x1 - x0) / 2 + 10}" ry="13" fill="#000" opacity="0.55" filter="url(#blur8)"/>')
    d.append(f'<ellipse cx="{(x0 + x1) / 2}" cy="{GROUND}" rx="{(x1 - x0) / 2 - 40}" ry="5" fill="#000" opacity="0.7" filter="url(#blur3)"/>')
    # dark wheel-well interiors
    for a in (rear_arch, front_arch):
        d.append(f'<circle cx="{a[0]}" cy="{a[1]}" r="{a[2] - 1}" fill="#0c0c0e"/>')
    # body-clipped shading and trim
    d.append('<g clip-path="url(#bodyclip)" mask="url(#arches)">')
    # rocker / lower cladding
    clad = m.get("cladding", "#141416")
    d.append(f'<rect x="0" y="{m["rb"] - m.get("rocker", 16)}" width="{W}" height="60" fill="{clad}" opacity="0.92"/>')
    # arch lips
    for a in (rear_arch, front_arch):
        d.append(f'<circle cx="{a[0]}" cy="{a[1]}" r="{a[2] + 4}" fill="none" stroke="#000" stroke-opacity="0.35" stroke-width="6"/>')
        if m.get("archFlare"):
            d.append(f'<circle cx="{a[0]}" cy="{a[1]}" r="{a[2] + 7}" fill="none" stroke="{clad}" stroke-width="10"/>')
    # character line highlight + shadow
    cl = belt + m.get("charLine", 30)
    d.append(f'<path d="M {x0} {cl} L {x1} {cl - m.get("charRise", 6)}" stroke="#fff" stroke-opacity="0.35" stroke-width="2.5"/>')
    d.append(f'<path d="M {x0} {cl + 3} L {x1} {cl + 3 - m.get("charRise", 6)}" stroke="#000" stroke-opacity="0.18" stroke-width="3"/>')
    # soft reflection of the sky on the upper body and the ground on the lower body
    d.append(f'<rect x="0" y="{m["rb"] - 50}" width="{W}" height="50" fill="#000" opacity="0.18" filter="url(#blur8)"/>')
    # door seams
    for sx in m.get("doors", []):
        d.append(f'<path d="M {sx} {belt + 2} C {sx - 3} {belt + 40}, {sx - 2} {m["rb"] - 30}, {sx + 2} {m["rb"] - m.get("rocker", 16)}" stroke="#000" stroke-opacity="0.45" stroke-width="1.6" fill="none"/>')
    for hx in m.get("handles", []):
        d.append(f'<rect x="{hx}" y="{belt + 18}" width="34" height="7" rx="3.5" fill="url(#chrome)" opacity="0.85"/>')
        d.append(f'<rect x="{hx}" y="{belt + 25}" width="34" height="2" rx="1" fill="#000" opacity="0.35"/>')
    # fuel door
    if m.get("fuel"):
        d.append(f'<circle cx="{m["fuel"]}" cy="{belt + 22}" r="11" fill="none" stroke="#000" stroke-opacity="0.35" stroke-width="1.5"/>')
    # side vents (sports cars)
    if m.get("vent"):
        vx, vy = m["vent"]
        d.append(f'<path d="M {vx} {vy} q 50 -6 90 -20 l -8 44 q -40 6 -82 -2 z" fill="#0d0d0f" opacity="0.92"/>')
    d.append("</g>")
    # bed / tailgate lines for trucks
    if m["type"] == "truck":
        d.append(f'<path d="M {x0 + 4} {m["bed"] + 10} L {m["cab"] - 8} {m["bed"] + 10}" stroke="#000" stroke-opacity="0.35" stroke-width="2"/>')
        d.append(f'<rect x="{x0 - 2}" y="{m["bed"] - 4}" width="{m["cab"] - x0}" height="6" rx="3" fill="#18181a" opacity="0.9"/>')
    # glass
    d.append(f'<path d="{win_d}" fill="#070a0e"/>')
    inset = win_d
    d.append(f'<path d="{inset}" fill="url(#glass)" transform="translate(0,1.5)"/>')
    # pillars
    for px in m.get("pillars", []):
        d.append(f'<path d="M {px[0]} {belt + 1} L {px[1]} {m["roofY"] + m.get("glassTop", 12) - 1}" stroke="#08090b" stroke-width="{px[2] if len(px) > 2 else 12}"/>')
    # window chrome trim
    if m.get("chromeTrim"):
        d.append(f'<path d="{win_d}" fill="none" stroke="url(#chrome)" stroke-width="3" opacity="0.8"/>')
    # glass reflection streak
    gx0 = min(p[0] for p in win_pts)
    gx1 = max(p[0] for p in win_pts)
    d.append(f'<clipPath id="wclip"><path d="{win_d}"/></clipPath>')
    d.append(f'<g clip-path="url(#wclip)"><path d="M {gx0 + (gx1 - gx0) * 0.25} {belt} L {gx0 + (gx1 - gx0) * 0.42} {m["roofY"]} L {gx0 + (gx1 - gx0) * 0.5} {m["roofY"]} L {gx0 + (gx1 - gx0) * 0.33} {belt} Z" fill="#fff" opacity="0.10"/>'
             f'<path d="M {gx0 + (gx1 - gx0) * 0.55} {belt} L {gx0 + (gx1 - gx0) * 0.68} {m["roofY"]} L {gx0 + (gx1 - gx0) * 0.71} {m["roofY"]} L {gx0 + (gx1 - gx0) * 0.58} {belt} Z" fill="#fff" opacity="0.07"/></g>')
    # mirror
    if m.get("mirror"):
        mx, my = m["mirror"]
        d.append(f'<path d="M {mx} {my} q 6 -18 30 -16 q 8 2 6 16 q -16 6 -36 0 z" fill="#0f0f11"/>')
        d.append(f'<path d="M {mx - 6} {my + 2} l 10 0 l 0 8 l -10 0 z" fill="#0f0f11"/>')
    # headlight
    hl = m.get("headlight")
    if hl:
        shape = hl.get("shape", "swept")
        hx, hy = hl["x"], hl["y"]
        if shape == "round":
            d.append(f'<circle cx="{hx}" cy="{hy}" r="{hl.get("r", 16)}" fill="#1a1d22"/><circle cx="{hx}" cy="{hy}" r="{hl.get("r", 16) - 4}" fill="url(#head)"/>')
        else:
            w_, h_ = hl.get("w", 70), hl.get("h", 18)
            d.append(f'<path d="M {hx} {hy} q {w_ * 0.6} -{h_ * 0.35} {w_} -{h_ * 0.1} l -4 {h_} q -{w_ * 0.5} 2 -{w_ - 6} -{h_ * 0.35} z" fill="#1a1d22"/>')
            d.append(f'<path d="M {hx + 5} {hy + 1} q {w_ * 0.55} -{h_ * 0.3} {w_ - 10} -{h_ * 0.08} l -3 {h_ * 0.7} q -{w_ * 0.45} 0 -{w_ - 16} -{h_ * 0.3} z" fill="url(#head)"/>')
            d.append(f'<path d="M {hx + 8} {hy + h_ * 0.5} l {w_ - 20} -{h_ * 0.2}" stroke="#e8f6ff" stroke-width="2.5" opacity="0.9"/>')
    tl = m.get("taillight")
    if tl:
        tx, ty = tl["x"], tl["y"]
        w_, h_ = tl.get("w", 34), tl.get("h", 18)
        d.append(f'<rect x="{tx}" y="{ty}" width="{w_}" height="{h_}" rx="{tl.get("rx", 5)}" fill="url(#tail)"/>')
        d.append(f'<rect x="{tx + 2}" y="{ty + 2}" width="{w_ - 4}" height="3" rx="1.5" fill="#ffb3ad" opacity="0.7"/>')
    # front grille / intake
    g = m.get("grille")
    if g:
        d.append(f'<rect x="{g[0]}" y="{g[1]}" width="{g[2]}" height="{g[3]}" rx="4" fill="#0e0f11"/>')
        for k in range(1, int(g[3] // 6)):
            d.append(f'<line x1="{g[0] + 1}" y1="{g[1] + k * 6}" x2="{g[0] + g[2] - 1}" y2="{g[1] + k * 6}" stroke="#3a3d42" stroke-width="1.2"/>')
    # spare tyre on the tailgate (Wrangler)
    if m.get("spare"):
        sx, sy, sr = m["spare"]
        d.append(f'<ellipse cx="{sx}" cy="{sy}" rx="{sr * 0.35}" ry="{sr}" fill="#18181b"/><ellipse cx="{sx - 3}" cy="{sy}" rx="{sr * 0.18}" ry="{sr * 0.6}" fill="#3a3d42"/>')
    # roof rails
    if m.get("rails"):
        d.append(f'<rect x="{m["rx0"] + 10}" y="{m["roofY"] - 7}" width="{m["rx1"] - m["rx0"] - 20}" height="6" rx="3" fill="#1b1c1f"/>')
    # rear wing
    if m.get("wing"):
        wx, wy = m["wing"]
        d.append(f'<path d="M {wx} {wy} l 90 -6 l 4 8 l -92 6 z" fill="#111214"/><rect x="{wx + 30}" y="{wy}" width="8" height="22" fill="#111214"/>')
    # top highlight glints on the paint
    d.append(f'<g clip-path="url(#bodyclip)" mask="url(#arches)"><path d="{body_d}" fill="none" stroke="#fff" stroke-opacity="0.55" stroke-width="2.4" transform="translate(0,1.5)"/></g>')
    # wheels
    d.append(svg_wheel(rear_arch[0], cy, r, m, 0))
    d.append(svg_wheel(front_arch[0], cy, r, m, 1))
    d.append("</svg>")
    return "\n".join(paint), "\n".join(d)


# ---------------------------------------------------------------- the models
# Coordinates: 1000 x 400, car faces right, ground at y=372. rw/fw = rear/front wheel centres.

def base(**kw):
    m = dict(x0=60, x1=940, rb=346, fb=346, r=60, spokes=5, mirror=None, doors=[], handles=[], pillars=[])
    m.update(kw)
    return m

U = 0.0058  # metres per SVG unit


def real(type, L, H, WB, FO, D, belt, hood, nose, cowl, roofF, roofR, bottom=0.17, deck=None, rearGlass=None,
         doors=4, cab=None, bed=None, **extra):
    """Builds model geometry from real-world dimensions in metres (x measured back from the front bumper)."""
    x0 = (W - L / U) / 2
    x1 = x0 + L / U
    fx = lambda m: x1 - m / U
    hy = lambda m: GROUND - m / U
    r = D / 2 / U
    m = dict(type=type, x0=x0, x1=x1, rb=hy(bottom), fb=hy(bottom + 0.02), r=r,
             fw=fx(FO), rw=fx(FO + WB), roofY=hy(H), rx0=fx(roofR), rx1=fx(roofF), cowlX=fx(cowl),
             hoodY=hy(hood), noseY=hy(nose), belt=hy(belt), deckY=hy(deck if deck else belt),
             rearGlassX=fx(rearGlass) if rearGlass else x0 + 10, spokes=5, pillars=[], doors=[], handles=[])
    if cab:
        m["cab"] = fx(cab)
        m["bed"] = hy(bed)
    # doors, handles and the B-pillar from the greenhouse
    bpil = fx((roofF + roofR) / 2 - 0.1) if doors == 4 else None
    if type in ("truck",):
        bpil = fx(roofF + 0.95)
    front_door_end = bpil if bpil else fx(cowl + 1.25)
    m["doors"] = [front_door_end]
    m["handles"] = [front_door_end - 0.32 / U]
    if doors == 4:
        rear_end = m["rw"] + r * 0.95 if type != "truck" else m["cab"] + 4
        m["doors"].append(rear_end)
        m["handles"].append(rear_end - 0.3 / U)
        m["pillars"].append((bpil, bpil - 3, 12))
    m["mirror"] = (m["cowlX"] - 18, m["belt"] - 4)
    m["headlight"] = {"x": x1 - 0.55 / U, "y": m["noseY"] + 4, "w": 0.5 / U, "h": 16}
    m["taillight"] = {"x": x0 + 2, "y": m["deckY"] + 6, "w": 0.22 / U, "h": 16}
    m["grille"] = (x1 - 14, m["noseY"] + 26, 12, max(16, (m["fb"] - m["noseY"]) * 0.45))
    m.update(extra)
    if extra.get("headlight_round"):
        m["headlight"] = {"shape": "round", "x": x1 - 0.18 / U, "y": m["noseY"] + 22, "r": 15}
    return m


MODELS = {
    "Hondo Civix": real("sedan", 4.67, 1.41, 2.73, 0.95, 0.66, belt=1.0, hood=0.95, nose=0.76, cowl=1.85, roofF=2.4,
        roofR=3.4, deck=1.0, rearGlass=4.05, spokes=10, spokeW=0.08, fuel=None),
    "Toyoda Camri": real("sedan", 4.88, 1.445, 2.825, 0.98, 0.68, belt=1.02, hood=0.97, nose=0.8, cowl=1.95, roofF=2.5,
        roofR=3.6, deck=1.03, rearGlass=4.25, chromeTrim=True),
    "Teslo Model 3": real("fastback", 4.69, 1.44, 2.875, 0.85, 0.68, belt=1.0, hood=0.86, nose=0.7, cowl=1.6, roofF=2.25,
        roofR=3.3, deck=1.0, rearGlass=4.3, grille=None, spokeW=0.24, rimColor="#5b6068", rimDark="#2e3136", charLine=34, charRise=2),
    "Mazdo Miota": real("coupe", 3.91, 1.23, 2.31, 0.75, 0.62, belt=0.92, hood=0.84, nose=0.7, cowl=1.6, roofF=1.95,
        roofR=2.5, deck=0.93, rearGlass=2.85, doors=2, spokes=6, spokeW=0.12, glassTop=8),
    "Subaro Outbuck": real("suv", 4.87, 1.67, 2.75, 0.95, 0.72, belt=1.13, hood=1.04, nose=0.9, cowl=1.8, roofF=2.3,
        roofR=4.55, deck=1.5, bottom=0.3, rails=True, cladding="#1a1a1c", archFlare=True, rocker=26),
    "Forde Rangler": real("truck", 5.37, 1.85, 3.27, 0.9, 0.8, belt=1.28, hood=1.25, nose=1.18, cowl=1.6, roofF=2.0,
        roofR=3.05, cab=3.15, bed=1.27, bottom=0.42, cladding="#1b1b1d", rocker=24, spokes=6),
    "Jeap Wrangle": real("boxy", 4.88, 1.85, 3.01, 0.75, 0.84, belt=1.28, hood=1.25, nose=1.2, cowl=1.25, roofF=1.3,
        roofR=4.75, bottom=0.48, headlight_round=True, spare=None, cladding="#121214", archFlare=True, rocker=22, spokeW=0.2,
        rimColor="#2f3237", rimDark="#111214", glassTop=10),
    "Dodgy Charjer": real("sedan", 5.1, 1.48, 3.05, 0.98, 0.7, belt=1.07, hood=1.0, nose=0.86, cowl=2.05, roofF=2.6,
        roofR=3.7, deck=1.06, rearGlass=4.35, caliper="#c62828", charLine=24, charRise=0),
    "Forde Mustank": real("fastback", 4.81, 1.39, 2.72, 0.95, 0.7, belt=1.0, hood=0.95, nose=0.82, cowl=2.0, roofF=2.5,
        roofR=3.15, deck=1.0, rearGlass=4.2, doors=2, spokes=10, spokeW=0.07, caliper="#1565c0"),
    "Chevro Tahoma": real("suv", 5.35, 1.93, 3.07, 1.0, 0.82, belt=1.32, hood=1.3, nose=1.2, cowl=1.75, roofF=2.2,
        roofR=5.2, deck=1.85, bottom=0.45, rails=True, chromeTrim=True, rocker=22, spokes=6),
    "Ramm 1500": real("truck", 5.6, 1.97, 3.57, 0.95, 0.82, belt=1.38, hood=1.35, nose=1.3, cowl=1.65, roofF=2.05,
        roofR=3.35, cab=3.45, bed=1.36, bottom=0.45, chromeTrim=True, rocker=20, spokes=6),
    "BMV M4": real("coupe", 4.79, 1.39, 2.86, 0.85, 0.68, belt=1.0, hood=0.92, nose=0.75, cowl=1.85, roofF=2.4,
        roofR=3.25, deck=0.98, rearGlass=4.0, doors=2, spokes=7, spokeW=0.1, caliper="#1e88e5"),
    "Rang Rovah": real("suv", 5.0, 1.87, 3.0, 0.95, 0.82, belt=1.3, hood=1.25, nose=1.16, cowl=1.75, roofF=2.2,
        roofR=4.85, deck=1.82, bottom=0.45, rocker=18, spokes=10, spokeW=0.07, glassTop=14),
    "Porsha 911": real("fastback", 4.52, 1.3, 2.45, 1.0, 0.68, belt=0.93, hood=0.84, nose=0.68, cowl=1.75, roofF=2.2,
        roofR=2.85, deck=0.95, rearGlass=4.15, doors=2, headlight_round=True, grille=None, spokeW=0.2, caliper="#d32f2f",
        charLine=26, charRise=0, glassTop=10),
    "Mercedez G-Wagon": real("boxy", 4.82, 1.97, 2.89, 0.85, 0.82, belt=1.37, hood=1.3, nose=1.28, cowl=1.35, roofF=1.45,
        roofR=4.75, bottom=0.45, headlight_round=True, chromeTrim=True, rocker=22, glassTop=10),
    "Ferrano 488": real("wedge", 4.57, 1.21, 2.65, 1.05, 0.68, belt=0.9, hood=0.82, nose=0.55, cowl=1.45, roofF=2.05,
        roofR=2.65, deck=0.98, rearGlass=3.35, bottom=0.13, doors=2, grille=None, spokeW=0.14, caliper="#f9a825", glassTop=8),
    "Lamborgo Aventa": real("wedge", 4.78, 1.14, 2.7, 1.1, 0.7, belt=0.86, hood=0.76, nose=0.48, cowl=1.4, roofF=2.1,
        roofR=2.65, deck=0.95, rearGlass=3.4, bottom=0.12, doors=2, grille=None, spokeW=0.2, caliper="#c8a200",
        glassTop=8, rimColor="#2c2f34", rimDark="#0d0e10"),
}
# features that depend on the computed geometry
MODELS["Jeap Wrangle"]["spare"] = (MODELS["Jeap Wrangle"]["x0"] - 8, MODELS["Jeap Wrangle"]["belt"] + 40, 70)
MODELS["Mercedez G-Wagon"]["spare"] = (MODELS["Mercedez G-Wagon"]["x0"] - 8, MODELS["Mercedez G-Wagon"]["belt"] + 40, 66)
MODELS["Lamborgo Aventa"]["wing"] = (MODELS["Lamborgo Aventa"]["x0"] + 20, MODELS["Lamborgo Aventa"]["deckY"] - 10)
for k in ("Forde Mustank", "BMV M4"):
    m = MODELS[k]
    m["vent"] = (m["fw"] + m["r"] + 14, m["belt"] + 34)
for k in ("Ferrano 488", "Lamborgo Aventa"):
    m = MODELS[k]
    m["vent"] = (m["rw"] + m["r"] + 20, m["belt"] + 14)


def slug(name):
    return name.lower().replace(" ", "_").replace("-", "_")


if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for name, m in MODELS.items():
        p, d = build(m)
        open(os.path.join(out, slug(name) + "_paint.svg"), "w").write(p)
        open(os.path.join(out, slug(name) + "_detail.svg"), "w").write(d)
    print(len(MODELS), "models")
