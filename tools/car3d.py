"""Builds 3D car models from real-world dimensions with Blender (bpy).

Each car is lofted from cross-sections along its length, smoothed with subdivision, cut for the wheel
arches and split into clickable body panels (hood, doors, fenders, bumpers, roof, trunk) with real panel
gaps. Wheels, glass, lights, grille, mirrors, plates and trim are separate named objects.

Usage (inside the bpy venv):
    python tools/car3d.py build <out_dir> [model ...]      # .glb per car for the Godot garage
    python tools/car3d.py render <out_dir> [model ...]     # Cycles sprites: paint + detail layers
"""
import math
import os
import re
import sys

import bpy  # noqa: I001  (bpy must load before bmesh/mathutils)
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------ model table (metres)

def _load_models():
    src = open(os.path.join(HERE, "cars_svg.py")).read()
    start = src.index("MODELS = {")
    end = src.index("# features that depend")

    def real(type, L, H, WB, FO, D, belt, hood, nose, cowl, roofF, roofR, bottom=0.17, deck=None, rearGlass=None,
             doors=4, cab=None, bed=None, **extra):
        return dict(type=type, L=L, H=H, WB=WB, FO=FO, D=D, belt=belt, hood=hood, nose=nose, cowl=cowl,
                    roofF=roofF, roofR=roofR, bottom=bottom, deck=deck, rearGlass=rearGlass, doors=doors,
                    cab=cab, bed=bed, **extra)

    ns = {"real": real}
    exec(src[start:end], ns)
    return ns["MODELS"]


MODELS = _load_models()
WIDTH = {"Hondo Civix": 1.80, "Toyoda Camri": 1.84, "Teslo Model 3": 1.85, "Mazdo Miota": 1.74,
         "Subaro Outbuck": 1.86, "Forde Rangler": 1.87, "Jeap Wrangle": 1.89, "Dodgy Charjer": 1.91,
         "Forde Mustank": 1.92, "Chevro Tahoma": 2.06, "Ramm 1500": 2.08, "BMV M4": 1.89, "Rang Rovah": 2.05,
         "Porsha 911": 1.85, "Mercedez G-Wagon": 1.98, "Ferrano 488": 1.95, "Lamborgo Aventa": 2.03}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


# ------------------------------------------------------------------ body shape

class Shape:
    """Side profile, plan view and cross-section of one car. x = metres back from the front bumper."""

    def __init__(self, name):
        m = dict(MODELS[name])
        self.m = m
        self.name = name
        self.type = m["type"]
        self.L = m["L"]
        self.W = WIDTH[name]
        self.H = m["H"]
        self.r = m["D"] / 2
        self.fw = m["FO"]
        self.rw = m["FO"] + m["WB"]
        self.deck = m["deck"] or m["belt"]
        if self.type in ("suv", "boxy"):
            self.deck = m["deck"] or (m["belt"] + 0.1)
        self.rear_glass = m["rearGlass"] or (self.L - (0.06 if self.type == "boxy" else 0.18))
        self.cab = m["cab"]
        self.bed = m["bed"]

    # plan view: half width at x
    def hw(self, x):
        L, W = self.L, self.W
        nf = {"boxy": 9, "truck": 6, "suv": 5, "wedge": 3.2}.get(self.type, 4.2)
        nr = {"boxy": 9, "truck": 8, "suv": 6, "wedge": 4}.get(self.type, 4.5)
        cf = {"boxy": 0.25, "wedge": 0.95}.get(self.type, 0.6)
        cr = {"boxy": 0.2, "truck": 0.2}.get(self.type, 0.5)
        f = 1.0
        if x < cf:
            u = 1 - x / cf
            f = (1 - u ** nf) ** (1 / nf)
        elif x > L - cr:
            u = (x - (L - cr)) / cr
            f = (1 - u ** nr) ** (1 / nr)
        # the body is a touch narrower at the front and rear than at the wheels
        mid = 1.0 - 0.025 * (1 - math.sin(math.pi * min(1, max(0, x / L))))
        # fender flares over the wheels
        flare = 0.0
        for wx in (self.fw, self.rw):
            flare += math.exp(-((x - wx) / 0.5) ** 2)
        k = {"boxy": 0.01, "wedge": 0.035, "coupe": 0.025, "fastback": 0.025}.get(self.type, 0.018)
        return W / 2 * f * mid + k * flare * f

    def bottom(self, x):
        b = self.m["bottom"]
        lift = 0.0
        if x < self.fw - self.r:
            lift = 0.12 * smooth(1 - x / max(0.01, self.fw - self.r))
        elif x > self.rw + self.r:
            lift = 0.16 * smooth((x - self.rw - self.r) / max(0.01, self.L - self.rw - self.r))
        return b + lift

    def shoulder(self, x):
        m = self.m
        nose, hood, belt = m["nose"], m["hood"], m["belt"]
        cowl = m["cowl"]
        if self.type == "boxy":
            nose_round = 0.08
        else:
            nose_round = 0.5
        if x <= cowl:
            z = lerp(nose, hood, smooth(x / nose_round)) if x < nose_round else hood
            # hood rises to the base of the windshield
            z += (belt - hood) * smooth((x - nose_round) / max(0.01, cowl - nose_round)) * 0.9
            return z
        end_cabin = self.cab if self.cab else self.rear_glass
        if x <= end_cabin:
            return belt + 0.03 * (x - cowl) / max(0.1, end_cabin - cowl)
        if self.cab:
            return self.bed
        # trunk / deck, rounding off at the tail
        z = lerp(belt + 0.03, self.deck, smooth((x - end_cabin) / 0.25))
        tail = 0.22 if self.type != "boxy" else 0.06
        drop = 0.16 if self.type in ("sedan", "coupe", "fastback", "wedge") else 0.05
        if x > self.L - tail:
            z -= drop * smooth((x - (self.L - tail)) / tail) ** 1.5
        return z

    def roof(self, x):
        """Top of the greenhouse (None outside the cabin)."""
        m = self.m
        cowl, rf, rr, H = m["cowl"], m["roofF"], m["roofR"], self.H
        end = self.cab if self.cab else self.rear_glass
        if x < cowl or x > end:
            return None
        zs = self.shoulder(x)
        if x < rf:
            t = (x - cowl) / max(0.01, rf - cowl)
            # windshield: straight with a soft curve into the roof
            k = 1 - (1 - t) ** 1.35 if self.type != "boxy" else t
            return lerp(self.shoulder(cowl), H - 0.015, k)
        if x <= rr:
            t = (x - rf) / max(0.01, rr - rf)
            return H - 0.015 + 0.015 * math.sin(math.pi * t)
        t = (x - rr) / max(0.01, end - rr)
        if self.type in ("fastback", "wedge"):
            k = t ** 1.15
        elif self.type in ("suv", "boxy") or self.cab:
            k = t ** 2.5
        else:
            k = t ** 0.9
        return lerp(H - 0.015, zs, k)

    def greenhouse_top_frac(self):
        return {"boxy": 0.9, "suv": 0.8, "truck": 0.84, "wedge": 0.6, "coupe": 0.66, "fastback": 0.66}.get(self.type, 0.7)

    def section(self, x):
        """Half cross-section, bottom centre to top centre: list of (y, z)."""
        hw = max(0.004, self.hw(x))
        zb = self.bottom(x)
        zs = max(zb + 0.12, self.shoulder(x))
        h = zs - zb
        # round the nose and tail in side view
        rn = {"boxy": 0.07, "wedge": 0.3, "truck": 0.12, "suv": 0.16}.get(self.type, 0.22)
        rt = {"boxy": 0.05, "truck": 0.06, "suv": 0.1}.get(self.type, 0.16)
        u = max(0.0, 1 - x / rn, 1 - (self.L - x) / rt)
        if u > 0:
            c = 1 - math.sqrt(max(0.0, 1 - u * u))
            zb += c * h * 0.35
            zs -= c * h * 0.18
            h = zs - zb
        boxy = self.type in ("boxy",)
        pts = [
            (0.0, zb),
            (0.78 * hw, zb),
            ((0.93 if not boxy else 0.97) * hw, zb + min(0.09, h * 0.22)),
            (1.0 * hw, zb + 0.4 * h),
            ((0.993 if not boxy else 1.0) * hw, zb + 0.8 * h),
            ((0.94 if not boxy else 0.99) * hw, zs),
        ]
        zr = self.roof(x)
        crown = 0.035 if not boxy else 0.012
        flat = [(0.86 * hw, zs + crown * 0.45), (0.6 * hw, zs + crown * 0.8), (0.3 * hw, zs + crown * 0.95), (0.0, zs + crown)]
        if zr is None or zr <= zs + 0.002:
            pts += flat
            return pts
        g = self.greenhouse_top_frac()
        gb = 0.9 if not boxy else 0.97
        cab = [(gb * hw, zs + 0.02), (g * hw, zr - 0.05), (g * 0.82 * hw, zr - 0.005), (0.0, zr + 0.01)]
        full = self.H - 0.015 - self.m["belt"]
        t = smooth((zr - zs) / max(0.05, full * 0.35))
        for a, b in zip(flat, cab):
            pts.append((lerp(a[0], b[0], t), lerp(a[1], b[1], t)))
        return pts

    def stations(self, n=72):
        # cosine spacing packs stations near the bumpers where the shape turns fastest
        xs = []
        for i in range(n + 1):
            u = i / n
            xs.append(self.L * (0.5 - 0.5 * math.cos(math.pi * u)))
        xs[0] = 0.004
        xs[-1] = self.L - 0.004
        # extra stations at the profile breaks
        for k in (self.m["cowl"], self.m["roofF"], self.m["roofR"], self.rear_glass, self.cab or 0):
            if 0.05 < k < self.L - 0.05:
                xs += [k - 0.03, k, k + 0.03]
        return sorted(set(round(x, 4) for x in xs))


# ------------------------------------------------------------------ materials

def mat(name, color, metallic=0.0, rough=0.5, coat=0.0, emit=None, alpha=1.0, transmission=0.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Metallic"].default_value = metallic
    p.inputs["Roughness"].default_value = rough
    if coat:
        p.inputs["Coat Weight"].default_value = coat
        p.inputs["Coat Roughness"].default_value = 0.03
    if emit:
        p.inputs["Emission Color"].default_value = (*emit[0], 1)
        p.inputs["Emission Strength"].default_value = emit[1]
    if transmission:
        p.inputs["Transmission Weight"].default_value = transmission
    if alpha < 1:
        p.inputs["Alpha"].default_value = alpha
    return m


def materials():
    return {
        "paint": mat("paint", (0.8, 0.8, 0.8), metallic=0.35, rough=0.32, coat=1.0),
        "seam": mat("seam", (0.015, 0.015, 0.015), rough=0.8),
        "glass": mat("glass", (0.01, 0.012, 0.016), rough=0.04, coat=1.0),
        "trim": mat("trim", (0.62, 0.63, 0.66), metallic=1.0, rough=0.18),
        "black": mat("black", (0.02, 0.02, 0.022), rough=0.45),
        "plastic": mat("plastic", (0.035, 0.035, 0.038), rough=0.6),
        "rubber": mat("rubber", (0.025, 0.025, 0.025), rough=0.85),
        "rim": mat("rim", (0.75, 0.76, 0.78), metallic=1.0, rough=0.22),
        "disc": mat("disc", (0.35, 0.35, 0.36), metallic=1.0, rough=0.45),
        "caliper": mat("caliper", (0.6, 0.05, 0.04), rough=0.35, coat=0.6),
        "headlight": mat("headlight", (0.9, 0.92, 0.95), metallic=0.8, rough=0.08, coat=1.0),
        "taillight": mat("taillight", (0.5, 0.01, 0.01), rough=0.1, coat=1.0, emit=((0.6, 0.0, 0.0), 0.6)),
        "plate": mat("plate", (0.92, 0.92, 0.9), rough=0.5),
        "liner": mat("liner", (0.012, 0.012, 0.012), rough=0.95),
    }


# ------------------------------------------------------------------ geometry helpers

def new_obj(name, bm, material=None, smooth_shade=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    if material:
        ob.data.materials.append(material)
    if smooth_shade:
        for p in ob.data.polygons:
            p.use_smooth = True
    return ob


def apply_mods(ob):
    bpy.context.view_layer.objects.active = ob
    for md in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=md.name)


def lathe(name, profile, segs=48, material=None, y_axis=True):
    """Revolve [(radius, axial)] around the Y axis."""
    bm = bmesh.new()
    rings = []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        ring = []
        for r, ax in profile:
            ring.append(bm.verts.new((r * math.cos(a), ax, r * math.sin(a))))
        rings.append(ring)
    for i in range(segs):
        a, b = rings[i], rings[(i + 1) % segs]
        for j in range(len(profile) - 1):
            bm.faces.new((a[j], b[j], b[j + 1], a[j + 1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_obj(name, bm, material)


# ------------------------------------------------------------------ build one car

PANEL_NAMES = ["front_bumper", "hood", "fender_fl", "fender_fr", "door_fl", "door_fr", "door_rl", "door_rr",
               "quarter_rl", "quarter_rr", "roof", "trunk", "rear_bumper", "pillars", "rocker_l", "rocker_r", "bed"]


_CUR = {}
LOD = int(os.environ.get("LOD", 2))
SEG = 64 if LOD >= 2 else 32


def build_car(name, mats):
    s = Shape(name)
    m = s.m
    _CUR.clear()
    _CUR.update(m)
    xs = s.stations()
    secs = [s.section(x) for x in xs]
    npts = len(secs[0])  # half section incl. both centre points
    bm = bmesh.new()
    rings = []
    for x, sec in zip(xs, secs):
        ring = []
        # right side (negative y) bottom->top, then left side top->bottom, sharing the centre points
        for y, z in sec:
            ring.append((-y, z))
        for y, z in reversed(sec[1:-1]):
            ring.append((y, z))
        rings.append([bm.verts.new((s.L / 2 - x, y, z)) for y, z in ring])
    nring = len(rings[0])
    faces_meta = []
    for i in range(len(rings) - 1):
        a, b = rings[i], rings[i + 1]
        for j in range(nring):
            k = (j + 1) % nring
            f = bm.faces.new((a[j], a[k], b[k], b[j]))
            faces_meta.append((f, (xs[i] + xs[i + 1]) / 2, j))
    # end caps
    for ring in (rings[0], rings[-1]):
        c = bm.verts.new(sum((v.co for v in ring), Vector()) / len(ring))
        for j in range(nring):
            f = bm.faces.new((ring[j], ring[(j + 1) % nring], c))
            faces_meta.append((f, 0.0 if ring is rings[0] else s.L, -1))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    # panel assignment by station and ring index (ring index: 0 bottom centre .. npts-1 top centre)
    cowl, rf, rr = m["cowl"], m["roofF"], m["roofR"]
    end_cab = s.cab if s.cab else s.rear_glass
    four = m["doors"] == 4
    bpil = (rf + rr) / 2 - 0.1 if four else None
    if s.type == "truck":
        bpil = rf + 0.95
    door_end = bpil if bpil else min(cowl + 1.25, s.rw - s.r - 0.05)
    rdoor_end = (s.rw - s.r * 0.95) if four and s.type != "truck" else ((s.cab - 0.04) if four else None)
    front_bumper_x = min(0.42, s.fw - s.r - 0.02)
    rear_bumper_x = max(s.L - 0.42, s.rw + s.r + 0.02)
    glass_idx = set()
    panel_of = {}
    for f, x, j in faces_meta:
        if j < 0:
            panel_of[f] = "front_bumper" if x < 1 else "rear_bumper"
            continue
        side = "l" if j >= npts - 1 else "r"
        jj = j if j < npts - 1 else (nring - 1 - j)  # index along the half section from the bottom
        top = jj >= 5
        zr = s.roof(x)
        in_cab = zr is not None and zr > s.shoulder(x) + 0.03
        if jj <= 1:
            panel_of[f] = "underbody"
        elif x < front_bumper_x and jj <= 5:
            panel_of[f] = "front_bumper"
        elif x > rear_bumper_x and jj <= 5:
            panel_of[f] = "rear_bumper"
        elif top and in_cab:
            # greenhouse: glass with pillars
            is_side = jj in (5, 6)
            if jj == 5:
                panel_of[f] = "beltline"
            elif is_side and bpil and abs(x - bpil) < 0.06:
                panel_of[f] = "pillars"
            elif is_side and (x < cowl + 0.14 or x > end_cab - 0.1):
                panel_of[f] = "pillars"
            elif not is_side and x > rf + 0.02 and x < rr - 0.02:
                panel_of[f] = "roof"
            elif not is_side and (x < cowl + 0.04 or x > end_cab - 0.04):
                panel_of[f] = "pillars"
            else:
                panel_of[f] = "glass"
        elif top:
            if x < cowl:
                panel_of[f] = "hood"
            elif s.cab and x > s.cab:
                panel_of[f] = "bed"
            else:
                panel_of[f] = "trunk"
        else:
            if jj == 2:
                panel_of[f] = "rocker_" + side if cowl < x < s.rw - s.r else (
                    "fender_f" + side if x < cowl else "quarter_r" + side)
            elif x < cowl:
                panel_of[f] = "fender_f" + side
            elif x < door_end:
                panel_of[f] = "door_f" + side
            elif rdoor_end and x < rdoor_end:
                panel_of[f] = "door_r" + side
            else:
                panel_of[f] = "quarter_r" + side
    names = sorted(set(panel_of.values()))
    for n in names:
        if n not in mats:
            mats[n] = mats["glass"] if n == "glass" else (mats["plastic"] if n == "underbody" else mats["paint"])
    body = new_obj("body_" + slug(name), bm, None)
    # one material slot per panel so we can separate after smoothing
    for n in names:
        body.data.materials.append(bpy.data.materials.get("panel_" + n) or _panel_mat(n, mats))
    me = body.data
    idx = {n: i for i, n in enumerate(names)}
    # bmesh faces are freed; map by face order
    order = [panel_of[f] for f, _, _ in faces_meta]
    for p, n in zip(me.polygons, order):
        p.material_index = idx[n]
    sub = body.modifiers.new("sub", "SUBSURF")
    sub.levels = LOD
    sub.render_levels = LOD
    apply_mods(body)

    # wheel arches
    for wx in (s.fw, s.rw):
        bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=s.r + 0.05, depth=s.W * 1.4,
                                            location=(s.L / 2 - wx, 0, s.r + 0.01), rotation=(math.pi / 2, 0, 0))
        cut = bpy.context.object
        cut.data.materials.append(_liner_panel(mats))
        bo = body.modifiers.new("arch", "BOOLEAN")
        bo.material_mode = "TRANSFER"
        bo.object = cut
        bo.operation = "DIFFERENCE"
        bo.solver = "EXACT"
        apply_mods(body)
        bpy.data.objects.remove(cut)
    if s.cab:
        # open the pickup bed
        bpy.ops.mesh.primitive_cube_add(size=1, location=(s.L / 2 - (s.cab + s.L) / 2 - 0.02, 0, s.bed + 0.3))
        cut = bpy.context.object
        cut.scale = ((s.L - s.cab) - 0.2, s.W - 0.16, 0.95)
        apply_mods_scale(cut)
        cut.location.z = s.bed - 0.45 + 0.5
        cut.data.materials.append(_liner_panel(mats, "bedliner"))
        bo = body.modifiers.new("bed", "BOOLEAN")
        bo.material_mode = "TRANSFER"
        bo.object = cut
        bo.operation = "DIFFERENCE"
        bo.solver = "EXACT"
        apply_mods(body)
        bpy.data.objects.remove(cut)

    names = [mt.name[6:] for mt in body.data.materials]
    parts = separate_panels(body, names)
    car = {"shape": s, "parts": parts}
    add_details(car, mats)
    return car


def _liner_panel(mats, n="arch"):
    m = bpy.data.materials.get("panel_" + n)
    if not m:
        m = mats["liner"].copy()
        m.name = "panel_" + n
    return m


def apply_mods_scale(ob):
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)


def _panel_mat(n, mats):
    base = {"glass": "glass", "underbody": "plastic", "pillars": "black", "beltline": "black"}.get(n, "paint")
    if n == "beltline" and _CUR.get("chromeTrim"):
        base = "trim"
    if n.startswith("rocker") and (_CUR.get("cladding") or _CUR.get("type") in ("truck",)):
        base = "plastic"
    m = mats[base].copy()
    m.name = "panel_" + n
    return m


def separate_panels(body, names):
    """Split the smoothed body into one object per panel and open real panel gaps."""
    bm = bmesh.new()
    bm.from_mesh(body.data)
    parts = {}
    for i, n in enumerate(names):
        pbm = bmesh.new()
        vmap = {}
        for f in bm.faces:
            if f.material_index != i:
                continue
            vs = []
            for v in f.verts:
                if v.index not in vmap:
                    vmap[v.index] = pbm.verts.new(v.co)
                vs.append(vmap[v.index])
            try:
                pbm.faces.new(vs)
            except ValueError:
                pass
        if not pbm.faces:
            pbm.free()
            continue
        pbm.normal_update()
        # pull the panel edge in by a few millimetres so a dark gap shows between panels
        if n not in ("underbody",):
            gap = 0.0035
            moves = {}
            for v in pbm.verts:
                if v.is_boundary:
                    inner = [e.other_vert(v) for e in v.link_edges if not e.other_vert(v).is_boundary]
                    if inner:
                        d = sum((u.co for u in inner), Vector()) / len(inner) - v.co
                        if d.length > 1e-6:
                            moves[v] = d.normalized() * gap
            for v, d in moves.items():
                v.co += d
        ob = new_obj("part_" + n, pbm, body.data.materials[i])
        parts[n] = ob
    bm.free()
    # dark core under the panels (shows in the gaps)
    core = body
    core.name = "core"
    core.data.materials.clear()
    core.data.materials.append(bpy.data.materials["seam"])
    disp = core.modifiers.new("shrink", "DISPLACE")
    disp.strength = -0.004
    disp.mid_level = 0
    apply_mods(core)
    return parts


def surface_patch(name, bvh, origin_fn, u_range, v_range, nu, nv, direction, offset, material, bulge=0.0):
    """Projects a grid onto the body along `direction` (lights, grilles, plates, trim)."""
    bm = bmesh.new()
    grid = []
    for i in range(nu + 1):
        row = []
        for j in range(nv + 1):
            u = lerp(u_range[0], u_range[1], i / nu)
            v = lerp(v_range[0], v_range[1], j / nv)
            o = origin_fn(u, v)
            hit = bvh.ray_cast(o, direction)
            if hit[0] is None:
                row.append(None)
                continue
            p = hit[0] - direction * offset
            # slight dome in the middle
            k = math.sin(math.pi * i / nu) * math.sin(math.pi * j / nv)
            p = p - direction * bulge * k
            row.append(bm.verts.new(p))
        grid.append(row)
    for i in range(nu):
        for j in range(nv):
            q = (grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1])
            if all(q):
                bm.faces.new(q)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        if f.normal.dot(direction) > 0:
            f.normal_flip()
    return new_obj(name, bm, material)


def body_bvh(car):
    bm = bmesh.new()
    for ob in car["parts"].values():
        bm.from_mesh(ob.data)
    bvh = BVHTree.FromBMesh(bm)
    bm.free()
    return bvh


def add_details(car, mats):
    s = car["shape"]
    m = s.m
    parts = car["parts"]
    bvh = body_bvh(car)
    X = lambda x: s.L / 2 - x  # noqa: E731
    fwd = Vector((-1, 0, 0))   # ray from the front toward the body
    back = Vector((1, 0, 0))
    nose, hood = m["nose"], m["hood"]
    zb = s.bottom(0)
    # ---- wheels
    for wx in (s.fw, s.rw):
        for side in (-1, 1):
            add_wheel(car, mats, Vector((X(wx), side * (s.W / 2 - 0.13), s.r)), side, m)
    # wheel-well liners
    for wx in (s.fw, s.rw):
        prof = [(s.r + 0.05, -s.W / 2 + 0.02), (s.r + 0.05, s.W / 2 - 0.02)]
        for side in (-1, 1):
            bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=s.r + 0.05, depth=0.02,
                                                location=(X(wx), side * (s.W / 2 - 0.33), s.r + 0.01),
                                                rotation=(math.pi / 2, 0, 0))
            lo = bpy.context.object
            lo.name = "liner"
            lo.data.materials.append(mats["liner"])
    # ---- headlights
    hl_w = 0.42 if s.type not in ("wedge",) else 0.5
    hz = (nose + hood) / 2 + (0.0 if s.type != "wedge" else 0.0)
    for side in (-1, 1):
        y0 = side * (s.W / 2 - 0.12)
        y1 = side * (s.W / 2 - 0.12 - hl_w)
        if m.get("headlight_round"):
            ob = surface_patch("headlight_" + ("l" if side > 0 else "r"), bvh,
                               lambda u, v, side=side: Vector((X(-1), side * (s.W / 2 - 0.3) + 0.12 * math.cos(u) * v,
                                                               hz + 0.12 * math.sin(u) * v)),
                               (0, 2 * math.pi), (0.0, 1.0), 24, 4, Vector((-1, 0, 0)), 0.004, mats["headlight"], bulge=0.01)
        else:
            dirn = Vector((-1, -side * 0.45, 0)).normalized()
            ob = surface_patch("headlight_" + ("l" if side > 0 else "r"), bvh,
                               lambda u, v, y0=y0, y1=y1, side=side: Vector((X(-1.5), lerp(y0, y1, u) + side * 0.62,
                                                                             hz + v - 0.03 * u)),
                               (0, 1), (-0.05, 0.05), 12, 4, dirn, 0.002, mats["headlight"], bulge=0.006)
        parts["headlight_" + ("l" if side > 0 else "r")] = ob
    # ---- taillights
    tz = s.shoulder(s.L - 0.05) - 0.09
    for side in (-1, 1):
        y0 = side * (s.W / 2 - 0.06)
        y1 = side * (s.W / 2 - 0.06 - (0.42 if s.type not in ("boxy",) else 0.14))
        dirn = Vector((1, -side * 0.35, 0)).normalized()
        ob = surface_patch("taillight_" + ("l" if side > 0 else "r"), bvh,
                           lambda u, v, y0=y0, y1=y1, side=side: Vector((X(s.L + 1.5), lerp(y0, y1, u) + side * 0.52, tz + v)),
                           (0, 1), (-0.045, 0.045) if s.type != "boxy" else (-0.12, 0.12), 12, 4, dirn, 0.002,
                           mats["taillight"], bulge=0.004)
        parts["taillight_" + ("l" if side > 0 else "r")] = ob
    # ---- grille and plates
    if m.get("grille", True) is not None:
        gw = s.W * (0.3 if s.type not in ("truck", "suv", "boxy") else 0.42)
        gz0, gz1 = zb + 0.18, hz - 0.04 if s.type in ("truck", "suv", "boxy") else hz - 0.06
        parts["grille"] = surface_patch("grille", bvh, lambda u, v: Vector((X(-1), u, v)), (-gw / 2, gw / 2),
                                        (gz0, max(gz0 + 0.06, gz1)), 12, 4, Vector((-1, 0, 0)),
                                        0.003, mats["black"])
    parts["plate_f"] = surface_patch("plate_f", bvh, lambda u, v: Vector((X(-1), u, v)), (-0.26, 0.26),
                                     (zb + 0.1, zb + 0.21), 6, 2, Vector((-1, 0, 0)), 0.006, mats["plate"])
    parts["plate_r"] = surface_patch("plate_r", bvh, lambda u, v: Vector((X(s.L + 1), u, v)), (-0.26, 0.26),
                                     (tz - 0.27, tz - 0.16), 6, 2, Vector((1, 0, 0)), 0.006, mats["plate"])
    # ---- mirrors
    for side in (-1, 1):
        x = m["cowl"] + 0.12
        z = m["belt"] + 0.06
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.09,
                                             location=(X(x), side * (s.hw(x) + 0.07), z))
        mo = bpy.context.object
        mo.scale = (0.75, 1.1, 0.65)
        apply_mods_scale(mo)
        mo.name = "mirror_" + ("l" if side > 0 else "r")
        mo.data.materials.append(parts["door_fl"].data.materials[0] if "door_fl" in parts else mats["paint"])
        for p in mo.data.polygons:
            p.use_smooth = True
        parts[mo.name] = mo
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.018, depth=0.09,
                                            location=(X(x) - 0.03, side * (s.hw(x) + 0.0), z - 0.03),
                                            rotation=(math.pi / 2, 0, 0))
        st = bpy.context.object
        st.name = "mirror_stalk"
        st.data.materials.append(mats["black"])
    # ---- door handles
    doors = [n for n in parts if n.startswith("door_")]
    for n in doors:
        ob = parts[n]
        xs_ = [s.L / 2 - v.co.x for v in ob.data.vertices]
        hx = max(xs_) - 0.32
        side = 1 if n.endswith("l") else -1
        hz = m["belt"] - 0.09
        parts["handle_" + n[5:]] = surface_patch("handle_" + n[5:], bvh,
            lambda u, v, side=side: Vector((X(u), side * 3, v)), (hx - 0.1, hx + 0.1), (hz - 0.018, hz + 0.018), 4, 1,
            Vector((0, -side, 0)), 0.004, mats["trim"] if m.get("chromeTrim") else mats["black"], bulge=0.004)
    car["bvh"] = bvh


def add_wheel(car, mats, center, side, m):
    r = car["shape"].r
    tw = 0.24 if r > 0.38 else 0.22
    rim_r = r * 0.64
    s = side
    prof = [(rim_r - 0.01, -tw / 2 + 0.01), (r - 0.04, -tw / 2), (r - 0.006, -tw / 2 + 0.03),
            (r, -tw / 2 + 0.06), (r, tw / 2 - 0.06), (r - 0.006, tw / 2 - 0.03), (r - 0.04, tw / 2),
            (rim_r - 0.01, tw / 2 - 0.01)]
    tire = lathe("tire", prof, SEG, mats["rubber"])
    rim_prof = [(rim_r, tw / 2 - 0.005), (rim_r - 0.03, tw / 2 - 0.02), (rim_r - 0.035, -tw / 2 + 0.02)]
    rim = lathe("rim_barrel", rim_prof, SEG, mats["rim"])
    # spokes
    n = m.get("spokes", 5)
    sw = m.get("spokeW", 0.12) * r * 1.4
    bm = bmesh.new()
    face_y = s * (tw / 2 - 0.02)
    for i in range(n):
        a = 2 * math.pi * i / n
        ca, sa = math.cos(a), math.sin(a)
        px, pz = -sa, ca
        pts = []
        for rad, w, dy in ((0.07, sw * 0.6, 0.035), (rim_r - 0.035, sw, 0.0)):
            for k in (-1, 1):
                pts.append((ca * rad + px * w / 2 * k, pz * w / 2 * k + sa * rad, dy))
        quad = [pts[0], pts[1], pts[3], pts[2]]
        top = [bm.verts.new((x, face_y + s * dy, z)) for x, z, dy in [(p[0], p[1], p[2]) for p in quad]]
        bot = [bm.verts.new((x, face_y + s * (dy - 0.03), z)) for x, z, dy in [(p[0], p[1], p[2]) for p in quad]]
        bm.faces.new(top)
        bm.faces.new(list(reversed(bot)))
        for k in range(4):
            bm.faces.new((top[k], top[(k + 1) % 4], bot[(k + 1) % 4], bot[k]))
    # hub
    hub = bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=0.085, radius2=0.07, depth=0.05)
    for v in hub["verts"]:
        v.co = Vector((v.co.x, face_y + s * (0.02 + v.co.z), v.co.y))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    spokes = new_obj("spokes", bm, mats["rim"], smooth_shade=False)
    disc = lathe("disc", [(0.05, -0.012), (rim_r - 0.06, -0.012), (rim_r - 0.06, 0.012), (0.05, 0.012)], SEG // 2, mats["disc"])
    disc.location.y = s * 0.0
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    cal = new_obj("caliper", bm, None, smooth_shade=False)
    cal.data.materials.append(_caliper_mat(m, mats))
    cal.scale = (0.12, 0.06, rim_r * 0.55)
    cal.location = (0.0 if True else 0, s * 0.03, rim_r * 0.55)
    apply_mods_scale(cal)
    cal.location = (0, s * 0.03, 0)
    for v in cal.data.vertices:
        v.co.z += rim_r * 0.55
    group = [tire, rim, spokes, disc, cal]
    key = ("wheel_f" if center.x > 0 else "wheel_r") + ("l" if side > 0 else "r")
    for ob in group:
        ob.location = center + Vector(ob.location)
    # join into one object per wheel
    bpy.ops.object.select_all(action="DESELECT")
    for ob in group:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = tire
    bpy.ops.object.join()
    tire.name = key
    car["parts"][key] = tire


def _caliper_mat(m, mats):
    c = m.get("caliper")
    if not c:
        return mats["disc"]
    name = "caliper_" + c
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    rgb = tuple(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return mat(name, tuple(v ** 2.2 for v in rgb), rough=0.35, coat=0.6)


# ------------------------------------------------------------------ scene / render

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def studio(view="side", res=(900, 380)):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = int(os.environ.get('SAMPLES', 48))
    sc.cycles.use_denoising = True
    sc.render.film_transparent = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Punchy"
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    sky = nt.nodes.new("ShaderNodeTexGradient")
    # soft studio: bright overhead, darker horizon
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, -math.pi / 2, 0)
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.08, 0.085, 0.1, 1)
    ramp.color_ramp.elements[1].position = 0.55
    ramp.color_ramp.elements[1].color = (1.0, 0.98, 0.95, 1)
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], sky.inputs["Vector"])
    nt.links.new(sky.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.9
    # key + rim lights
    for loc, energy, size in (((2, -4, 6), 900, 6), ((-4, 3, 4), 400, 5), ((0, 0, 7), 600, 8)):
        ld = bpy.data.lights.new("l", "AREA")
        ld.energy = energy
        ld.size = size
        lo = bpy.data.objects.new("l", ld)
        lo.location = loc
        d = Vector((0, 0, 0.6)) - Vector(loc)
        lo.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        sc.collection.objects.link(lo)
    # shadow catcher floor
    bpy.ops.mesh.primitive_plane_add(size=40)
    fl = bpy.context.object
    fl.is_shadow_catcher = True
    cam = bpy.data.cameras.new("cam")
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return co


def aim(cam, view, s):
    L = s.L
    if view == "side":
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = max(L * 1.12, s.H * 2.6)
        cam.location = (0, -20, s.H / 2 + 0.06 + 20 * math.tan(math.radians(1.5)))
        cam.rotation_euler = (math.radians(88.5), 0, 0)
    else:
        cam.data.lens = 70
        d = 11.5
        ang = math.radians(-35)
        cam.location = (d * math.cos(ang) * 0.95, d * math.sin(ang), 2.6)
        tgt = Vector((0, 0, 0.62))
        cam.rotation_euler = (tgt - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()


def render_still(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


PAINT_PARTS = ("front_bumper", "hood", "fender_", "door_", "quarter_", "roof", "trunk", "rear_bumper", "rocker_", "bed",
               "mirror_l", "mirror_r")


def is_paint(ob):
    if ob.type != "MESH" or not ob.data.materials:
        return False
    mname = ob.data.materials[0].name
    return mname.startswith("panel_") and mname[6:].startswith(PAINT_PARTS) and \
        ob.data.materials[0].node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value < 0.9 and \
        mname[6:] not in ("glass", "underbody", "pillars", "beltline", "arch", "bedliner") and \
        not (mname[6:].startswith("rocker") and ob.data.materials[0].node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value[0] < 0.1)


def sprites(car, out, slug_):
    """Side view at the same scale as the old SVG art (600x240, ground at y=223): paint + detail layers."""
    sc = bpy.context.scene
    cam = studio(res=(1200, 480))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 5.8
    cam.location = (0, -20, 0.998)
    cam.rotation_euler = (math.radians(90), 0, 0)
    sc.render.resolution_percentage = 100
    meshes = [o for o in sc.objects if o.type == "MESH" and not o.is_shadow_catcher]
    paint = [o for o in meshes if o.name.startswith("part_") and is_paint(o)] + \
            [o for o in meshes if o.name.startswith("mirror_") and o.name != "mirror_stalk" and not o.name.startswith("mirror_stalk")]
    floor = [o for o in sc.objects if o.is_shadow_catcher][0]
    # paint layer: everything else is a holdout, paint is plain light grey so the game can tint it
    for o in meshes:
        o.is_holdout = o not in paint
    floor.hide_render = True
    for o in paint:
        for m in o.data.materials:
            m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.62, 0.62, 0.62, 1)
    tmp = os.path.join(out, "_tmp_paint.png")
    render_still(tmp)
    _shrink(tmp, os.path.join(out, slug_ + "_paint.png"))
    for o in meshes:
        o.is_holdout = o in paint
    floor.hide_render = False
    tmp2 = os.path.join(out, "_tmp_detail.png")
    render_still(tmp2)
    _shrink(tmp2, os.path.join(out, slug_ + "_detail.png"))
    os.remove(tmp)
    os.remove(tmp2)


def _shrink(src, dst):
    im = bpy.data.images.load(src)
    im.scale(600, 240)
    im.filepath_raw = dst
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/car3d"
    names = sys.argv[3:] or list(MODELS)
    os.makedirs(out, exist_ok=True)
    for name in names:
        reset()
        mats = materials()
        car = build_car(name, mats)
        if cmd == "test":
            cam = studio()
            for view in ("side", "three"):
                aim(cam, view, car["shape"])
                render_still(os.path.join(out, f"{slug(name)}_{view}.png"))
        elif cmd == "sprites":
            sprites(car, out, slug(name))
        elif cmd == "build":
            bpy.ops.export_scene.gltf(filepath=os.path.join(out, slug(name) + ".glb"), export_format="GLB",
                                      export_apply=True, export_draco_mesh_compression_enable=False)


if __name__ == "__main__":
    main()
