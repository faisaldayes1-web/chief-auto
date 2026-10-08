"""Builds 3D car models from real-world dimensions with Blender (bpy).

Each car is lofted from cross-sections along its length, smoothed with subdivision, cut for the wheel
arches and split into clickable body panels (hood, doors, fenders, bumpers, roof, trunk) with real panel
gaps. Wheels, glass, lights, grille, mirrors, plates and trim are separate named objects.

Usage (inside the bpy venv):
    python tools/car3d.py build <out_dir> [model ...]      # .glb per car for the Godot garage
    python tools/car3d.py render <out_dir> [model ...]     # Cycles sprites: paint + detail layers
"""
import bisect
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


# ================================================================== v2: hand-measured bodies
# The cars that have no realistic third-party model (see car_sprites_real.py) are built from measured profiles
# instead of the generic dimension table: the centreline silhouette, the shoulder (belt) line and the sill line
# in side view, the plan-view width, the greenhouse stations and the panel cut lines, all in metres back from
# the front bumper. Lamps, grilles, vents and trim are drawn as thin shells projected onto the body.

def pchip(pts):
    """Monotone cubic through [(x, y)] (no overshoot between control points)."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])

    def f(x):
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = min(n - 2, bisect.bisect_right(xs, x) - 1)
        t = (x - xs[i]) / h[i]
        return ((2 * t ** 3 - 3 * t ** 2 + 1) * ys[i] + (t ** 3 - 2 * t ** 2 + t) * h[i] * m[i] +
                (-2 * t ** 3 + 3 * t ** 2) * ys[i + 1] + (t ** 3 - t ** 2) * h[i] * m[i + 1])
    return f


class Shape2:
    """Same role as Shape, driven by a V2 spec."""

    def __init__(self, name):
        sp = V2[name]
        self.sp = sp
        self.m = sp
        self.name = name
        self.type = sp["type"]
        self.L, self.W, self.H = sp["L"], sp["W"], sp["H"]
        self.r = sp["D"] / 2
        self.fw = sp["FO"]
        self.rw = sp["FO"] + sp["WB"]
        self.top = pchip(sp["top"])
        self.belt = pchip(sp["belt"])
        self.bot = pchip(sp["bottom"])
        g = sp["gh"]
        self.g0, self.a_top, self.c_top, self.g1 = g["g0"], g["a_top"], g["c_top"], g["g1"]
        self.roof_plan = pchip(g["roof_hw"]) if "roof_hw" in g else None
        self.cab = None
        self.rear_glass = self.g1

    def hw(self, x):
        p = self.sp["plan"]
        L = self.L
        W = p.get("body_w", self.W)
        f = 1.0
        if x < p["cf"]:
            u = 1 - x / p["cf"]
            f = (1 - u ** p["nf"]) ** (1 / p["nf"])
        elif x > L - p["cr"]:
            u = (x - (L - p["cr"])) / p["cr"]
            f = (1 - u ** p["nr"]) ** (1 / p["nr"])
        flare = 0.0
        for wx, k in ((self.fw, p.get("flare_f", 0.012)), (self.rw, p.get("flare_r", 0.018))):
            flare += k * math.exp(-((x - wx) / p.get("flare_len", 0.55)) ** 2)
        taper = p.get("taper_f", 0.0) * max(0.0, 1 - x / (L * 0.45)) + p.get("taper_r", 0.0) * max(0.0, (x - L * 0.6) / (L * 0.4))
        return max(0.003, (W / 2 - taper) * f + flare * f)

    def roof_hw(self, x):
        if self.roof_plan:
            return self.roof_plan(x)
        return self.hw(x) - self.sp["gh"]["tumble"]

    def in_gh(self, x):
        return self.g0 < x < self.g1

    def section(self, x):
        sp = self.sp
        sec = sp["sec"]
        hw = self.hw(x)
        zb = self.bot(x)
        zt = max(self.top(x), zb + 0.05)
        zbelt = min(self.belt(x), zt)
        zbelt = max(zbelt, zb + 0.04)
        hh = zbelt - zb
        k = min(1.0, hw / 0.35)   # shrink the insets where the body narrows at the ends
        tuck, rk, sh = sec["tuck"] * k, sec["rocker"], sec["shoulder"] * k
        pts = [
            (0.0, zb),
            (max(0.0, hw - tuck - 0.1 * k), zb),
            (hw - tuck * 0.5, zb + min(0.03, hh * 0.12)),
            (hw - tuck * 0.12, zb + min(rk, hh * 0.3)),
            (hw, zb + sec["maxw"] * hh),
            (hw - sh * 0.4, zbelt - min(sec.get("upper", 0.08), hh * 0.2)),
            (hw - sh, zbelt),
        ]
        y6 = hw - sh
        p = sec.get("hood_p", 2.2)

        def hood_z(y):
            u = 1 - y / max(1e-4, y6)
            return zbelt + (zt - zbelt) * (1 - (1 - u) ** p)
        flat = [(y6 * f, hood_z(y6 * f)) for f in (0.955, 0.85, 0.6, 0.3, 0.0)]
        if not self.in_gh(x):
            return pts + flat
        rh = min(self.roof_hw(x), y6 - 0.04)
        gb = y6 - sec.get("glass_inset", 0.03) * k
        zr = zt
        gtop = max(zbelt + 0.03, zr - sec.get("drip", 0.07))
        gh = [(gb, zbelt + 0.012), (rh, gtop), (rh - 0.035, max(gtop + 0.004, zr - 0.016)), (rh * 0.5, zr - 0.003), (0.0, zr)]
        full = max(0.1, self.H - zbelt)
        t = smooth((zr - zbelt) / (full * sec.get("blend", 0.3)))
        return pts + [(lerp(a[0], b[0], t), lerp(a[1], b[1], t)) for a, b in zip(flat, gh)]

    def stations(self):
        sp = self.sp
        L = self.L
        xs = set()
        x = 0.003
        while x < L - 0.003:
            xs.add(round(x, 4))
            near_end = x < 0.35 or x > L - 0.35
            x += (0.016 if near_end else 0.05) * (1.0 if LOD >= 2 else 1.6)
        xs.add(round(L - 0.003, 4))
        g = sp["gh"]
        breaks = [g["g0"], g["a_top"], g["c_top"], g["g1"], g["dlo_f"], g["dlo_r"]] + list(g.get("pillars", []))
        cuts = sp["cuts"]
        breaks += [cuts[k] for k in ("fb", "rb", "hood0", "door0", "bpil", "rdoor") if cuts.get(k)]
        for b in breaks:
            for d in (-0.012, 0.0, 0.012):
                if 0.01 < b + d < L - 0.01:
                    xs.add(round(b + d, 4))
        # windshield and back light need dense stations so the pillars and window edges stay clean
        for a, b in ((g["g0"], g["a_top"]), (g["c_top"], g["g1"])):
            n = max(2, int((b - a) / (0.025 if LOD >= 2 else 0.04)))
            for i in range(n + 1):
                xs.add(round(a + (b - a) * i / n, 4))
        return sorted(xs)


def classify_v2(s, x, jj, side, z=0.0):
    """Panel name of the face between half-section points jj and jj+1 at station x (face centre height z)."""
    sp = s.sp
    c = sp["cuts"]
    g = sp["gh"]
    L = s.L
    if jj <= 1:
        return "underbody"
    if c.get("gate") and x > c["gate"][0] and z > c["gate"][1] and not s.in_gh(x):
        return "trunk"   # trunk lid / tailgate down the rear face
    in_gh = s.in_gh(x)

    def side_panel():
        if x < c["door0"]:
            return "fender_f" + side
        if x < c["bpil"]:
            return "door_f" + side
        if c.get("rdoor") and x < c["rdoor"]:
            return "door_r" + side
        return "quarter_r" + side
    if jj <= 6:
        if x < c["fb"]:
            return "front_bumper"
        if x > c["rb"]:
            return "rear_bumper"
        if jj == 2:
            if s.fw + s.r * 0.8 < x < s.rw - s.r * 0.8:
                return "rocker_" + side
            return side_panel()
        if jj == 6 and in_gh and g["dlo_f"] - 0.02 < x < g["dlo_r"] + 0.02:
            return "beltline"
        return side_panel()
    if not in_gh:
        if x < c["hood0"]:
            return "front_bumper"
        if x <= s.g0:
            return "hood"
        if x > c.get("tail", L + 1):
            return "rear_bumper"
        return "trunk"
    pil = g.get("pillar_w", 0.045)
    if jj == 7:
        if g["dlo_f"] < x < g["dlo_r"]:
            if any(abs(x - p) < pil for p in g.get("pillars", [])):
                return "pillars"
            return "glass"
        if x <= g["dlo_f"]:
            return "pillars" if g.get("a_black") else "fender_f" + side
        return "pillars" if g.get("c_black") else "quarter_r" + side
    if jj == 8:
        if x < s.a_top:
            return "pillars" if g.get("a_black") else "roof"
        if x > s.c_top:
            return "pillars" if g.get("c_black") else "roof"
        return "pillars" if (g.get("glass_roof") or g.get("frame_black")) else "roof"
    if x < s.a_top or x > s.c_top:
        return "glass"
    if g.get("glass_roof") and s.a_top + g.get("header", 0.06) < x < s.c_top - 0.02:
        return "glass"
    return "roof"


def build_car2(name, mats):
    s = Shape2(name)
    sp = s.sp
    _CUR.clear()
    _CUR.update(sp)
    tune_mats(mats, sp)
    xs = s.stations()
    secs = [s.section(x) for x in xs]
    npts = len(secs[0])
    bm = bmesh.new()
    crease = bm.edges.layers.float.new("crease_edge")
    rings = []
    for x, sec in zip(xs, secs):
        ring = [(-y, z) for y, z in sec] + [(y, z) for y, z in reversed(sec[1:-1])]
        rings.append([bm.verts.new((s.L / 2 - x, y, z)) for y, z in ring])
    nring = len(rings[0])
    faces_meta = []
    for i in range(len(rings) - 1):
        a, b = rings[i], rings[i + 1]
        for j in range(nring):
            k = (j + 1) % nring
            f = bm.faces.new((a[j], a[k], b[k], b[j]))
            faces_meta.append((f, (xs[i] + xs[i + 1]) / 2, j))
    for ring in (rings[0], rings[-1]):
        cvert = bm.verts.new(sum((v.co for v in ring), Vector()) / len(ring))
        for j in range(nring):
            f = bm.faces.new((ring[j], ring[(j + 1) % nring], cvert))
            faces_meta.append((f, 0.0 if ring is rings[0] else s.L, -1))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # crisp shoulder line and window edges
    cr = sp["sec"].get("creases", {6: 0.7})
    for i in range(len(rings) - 1):
        for jj, val in cr.items():
            for j in (jj, nring - jj):
                e = bm.edges.get((rings[i][j % nring], rings[i + 1][j % nring]))
                if e:
                    e[crease] = val
    panel_of = {}
    gate = sp["cuts"].get("gate")
    for f, x, j in faces_meta:
        if j < 0:
            panel_of[f] = "front_bumper" if x < 1 else (
                "trunk" if gate and f.calc_center_median().z > gate[1] else "rear_bumper")
            continue
        side = "l" if j >= npts - 1 else "r"
        jj = j if j < npts - 1 else (nring - 1 - j)
        panel_of[f] = classify_v2(s, x, jj, side, f.calc_center_median().z)
    names = sorted(set(panel_of.values()))
    body = new_obj("body_" + slug(name), bm, None)
    for n in names:
        body.data.materials.append(bpy.data.materials.get("panel_" + n) or _panel_mat(n, mats))
    idx = {n: i for i, n in enumerate(names)}
    order = [panel_of[f] for f, _, _ in faces_meta]
    for p, n in zip(body.data.polygons, order):
        p.material_index = idx[n]
    sub = body.modifiers.new("sub", "SUBSURF")
    sub.levels = max(1, LOD)
    sub.render_levels = max(1, LOD)
    apply_mods(body)
    # wheel arches
    for wx in (s.fw, s.rw):
        bpy.ops.mesh.primitive_cylinder_add(vertices=72, radius=s.r + sp.get("arch_gap", 0.035), depth=s.W * 1.4,
                                            location=(s.L / 2 - wx, 0, s.r + sp.get("arch_lift", 0.015)),
                                            rotation=(math.pi / 2, 0, 0))
        cut = bpy.context.object
        cut.data.materials.append(_liner_panel(mats))
        bo = body.modifiers.new("arch", "BOOLEAN")
        bo.material_mode = "TRANSFER"
        bo.object = cut
        bo.operation = "DIFFERENCE"
        bo.solver = "EXACT"
        apply_mods(body)
        bpy.data.objects.remove(cut)
    names = [mt.name[6:] for mt in body.data.materials]
    parts = separate_panels(body, names)
    # the dark core only shows through the panel gaps: keep it light
    dec = body.modifiers.new("dec", "DECIMATE")
    dec.ratio = 0.3 if LOD < 2 else 0.6
    apply_mods(body)
    car = {"shape": s, "parts": parts}
    car["bvh"] = body_bvh(car)
    D2(car, mats).run()
    return car


def tune_mats(mats, sp):
    """v2 look: dark tinted glass, gloss-black trim, chrome or black window line."""
    def setp(m, **kw):
        b = m.node_tree.nodes["Principled BSDF"]
        for k, v in kw.items():
            b.inputs[k].default_value = v
    setp(mats["glass"], **{"Base Color": (0.004, 0.005, 0.007, 1), "Roughness": 0.04, "Coat Weight": 0.0, "Metallic": 0.35})
    setp(mats["black"], **{"Base Color": (0.008, 0.008, 0.009, 1), "Roughness": 0.12})
    # blacks: a little metallic so the sky reflection takes on the dark base colour instead of washing it grey
    setp(mats["plastic"], **{"Base Color": (0.0, 0.0, 0.0, 1), "Roughness": 0.5, "Metallic": 0.6})
    setp(mats["liner"], **{"Base Color": (0.01, 0.01, 0.01, 1), "Metallic": 1.0})
    extra = {
        "lamp_housing": mat("lamp_housing", (0.02, 0.022, 0.026), metallic=0.7, rough=0.12, coat=1.0),
        "lamp_chrome": mat("lamp_chrome", (0.85, 0.86, 0.88), metallic=1.0, rough=0.08),
        "lamp_lens": mat("lamp_lens", (0.55, 0.58, 0.62), metallic=0.9, rough=0.06, coat=1.0),
        "drl": mat("drl", (1.0, 1.0, 1.0), rough=0.2, emit=((0.9, 0.95, 1.0), 6.0)),
        "tail_red": mat("tail_red", (0.4, 0.01, 0.008), rough=0.08, coat=1.0, emit=((1.0, 0.03, 0.02), 1.2)),
        "tail_dark": mat("tail_dark", (0.07, 0.004, 0.004), rough=0.06, coat=1.0),
        "tail_led": mat("tail_led", (1.0, 0.1, 0.06), rough=0.2, emit=((1.0, 0.05, 0.02), 7.0)),
        "amber": mat("amber", (0.9, 0.35, 0.02), rough=0.1, coat=1.0, emit=((1.0, 0.4, 0.0), 0.6)),
        "reverse": mat("reverse", (0.8, 0.82, 0.85), rough=0.08, coat=1.0),
        "gloss_black": mat("gloss_black", (0.006, 0.006, 0.007), rough=0.1, coat=1.0),
        "grille_mesh": grille_mat("grille_mesh", sp.get("grille_pattern", "hex")),
        "rim_dark": mat("rim_dark", (0.03, 0.032, 0.035), metallic=0.6, rough=0.4),
        "chrome": mat("chrome", (0.85, 0.86, 0.88), metallic=1.0, rough=0.06),
        "satin": mat("satin", (0.35, 0.36, 0.38), metallic=1.0, rough=0.3),
    }
    mats.update(extra)
    rc = sp.get("rim_color", (0.72, 0.73, 0.75))
    setp(mats["rim"], **{"Base Color": (*rc, 1), "Roughness": sp.get("rim_rough", 0.25)})
    setp(mats["rubber"], **{"Base Color": (0.0, 0.0, 0.0, 1), "Roughness": 0.45, "Metallic": 0.6})
    setp(mats["disc"], **{"Base Color": (0.16, 0.16, 0.17, 1), "Roughness": 0.5})


def grille_mat(name, pattern):
    """Black grille with a procedural mesh pattern (renders in Cycles; the .glb keeps the plain black)."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = mat(name, (0.006, 0.006, 0.007), metallic=1.0, rough=0.45)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    if pattern == "slats":
        tex = nt.nodes.new("ShaderNodeTexWave")
        tex.wave_type = "BANDS"
        tex.bands_direction = "Z"
        tex.inputs["Scale"].default_value = 30.0
        tex.inputs["Distortion"].default_value = 0.0
        fac = tex.outputs["Fac"]
    else:
        tex = nt.nodes.new("ShaderNodeTexVoronoi")
        tex.feature = "DISTANCE_TO_EDGE"
        tex.inputs["Scale"].default_value = 55.0
        fac = tex.outputs["Distance"]
    nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.04 if pattern != "slats" else 0.45
    ramp.color_ramp.elements[0].color = (0.03, 0.03, 0.032, 1)
    ramp.color_ramp.elements[1].position = 0.12 if pattern != "slats" else 0.6
    ramp.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1)
    nt.links.new(fac, ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


# ------------------------------------------------------------------ v2 detail helpers

def rounded_poly(pts, r, seg=4):
    """Closed polygon with every corner rounded (r: radius or list of radii)."""
    n = len(pts)
    rr = r if isinstance(r, (list, tuple)) else [r] * n
    out = []
    for i in range(n):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % n])
        if rr[i] <= 0:
            out.append(tuple(p1))
            continue
        a = p1 + (p0 - p1).normalized() * min(rr[i], (p0 - p1).length * 0.45)
        b = p1 + (p2 - p1).normalized() * min(rr[i], (p2 - p1).length * 0.45)
        for k in range(seg + 1):
            t = k / seg
            q = a * (1 - t) ** 2 + p1 * 2 * t * (1 - t) + b * t * t
            out.append((q.x, q.y))
    return out


def resample(pts, n, closed=True):
    P = [Vector(p) for p in pts] + ([Vector(pts[0])] if closed else [])
    seg = [(P[i + 1] - P[i]).length for i in range(len(P) - 1)]
    tot = sum(seg)
    out = []
    count = n if closed else n + 1
    for k in range(count):
        d = tot * k / n
        i = 0
        while i < len(seg) - 1 and d > seg[i]:
            d -= seg[i]
            i += 1
        t = d / seg[i] if seg[i] else 0
        q = P[i].lerp(P[i + 1], min(1, t))
        out.append((q.x, q.y))
    return out


def ellipse(cx, cy, rx, ry, n=32, a0=0.0):
    return [(cx + rx * math.cos(a0 + 2 * math.pi * i / n), cy + ry * math.sin(a0 + 2 * math.pi * i / n)) for i in range(n)]


def join(objs, name):
    objs = [o for o in objs if o]
    if not objs:
        return None
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    ob = objs[0]
    ob.name = name
    ob.data.name = name
    return ob


class D2:
    """Draws the details of a v2 car (lamps, grilles, trim, wheels, mirrors) onto its body."""

    VIEWS = {
        "front": ((-1, 0, 0), lambda s, a, b: Vector((s.L / 2 + 1.5, a, b))),
        "rear": ((1, 0, 0), lambda s, a, b: Vector((-s.L / 2 - 1.5, a, b))),
        "left": ((0, -1, 0), lambda s, a, b: Vector((s.L / 2 - a, 3.0, b))),
        "right": ((0, 1, 0), lambda s, a, b: Vector((s.L / 2 - a, -3.0, b))),
        "top": ((0, 0, -1), lambda s, a, b: Vector((s.L / 2 - a, b, 4.0))),
    }

    def __init__(self, car, mats):
        self.car = car
        self.s = car["shape"]
        self.sp = self.s.sp
        self.mats = mats
        self.parts = car["parts"]
        self.bvh = car["bvh"]
        self.extra = {}   # target part name -> [objects to join into it]

    def X(self, x):
        return self.s.L / 2 - x

    # -- primitives
    def blob(self, name, outline, view, material, off=0.004, rings=4, skirt=0.012, bulge=0.0, n=40, dirn=None):
        """Fills a closed outline (view-plane coordinates) and projects it onto the body."""
        d, org = self.VIEWS[view]
        d = Vector(dirn or d).normalized()
        if LOD < 2:
            n = max(12, int(n * 0.7))
            rings = max(2, rings - 1)
        outline = resample(outline, n)
        cx = sum(p[0] for p in outline) / len(outline)
        cy = sum(p[1] for p in outline) / len(outline)
        bm = bmesh.new()

        def proj(a, b, lift):
            hit = self.bvh.ray_cast(org(self.s, a, b), d, 20.0)
            if hit[0] is None:
                return None
            return bm.verts.new(hit[0] - d * lift)
        centre = proj(cx, cy, off + bulge)
        grid = []
        for k in range(1, rings + 1):
            t = k / rings
            grid.append([proj(cx + (a - cx) * t, cy + (b - cy) * t, off + bulge * (1 - t * t)) for a, b in outline])
        m = len(outline)
        if centre:
            for i in range(m):
                q = (centre, grid[0][i], grid[0][(i + 1) % m])
                if all(q):
                    bm.faces.new(q)
        for k in range(rings - 1):
            for i in range(m):
                q = (grid[k][i], grid[k + 1][i], grid[k + 1][(i + 1) % m], grid[k][(i + 1) % m])
                if all(q):
                    bm.faces.new(q)
        if skirt:
            outer = grid[-1]
            low = [bm.verts.new(v.co + d * (off + skirt)) if v else None for v in outer]
            for i in range(m):
                q = (outer[i], low[i], low[(i + 1) % m], outer[(i + 1) % m])
                if all(q):
                    bm.faces.new(q)
        return self._finish(name, bm, d, material)

    def band(self, name, path, width, view, material, off=0.004, closed=False, n=None, skirt=0.008, dirn=None):
        """A strip of the given width along a path (view-plane coordinates) projected onto the body."""
        d, org = self.VIEWS[view]
        d = Vector(dirn or d).normalized()
        if n:
            path = resample(path, n, closed)
        P = [Vector(p) for p in path]
        cnt = len(P)
        ws = width if isinstance(width, (list, tuple)) else [width] * cnt
        if n and isinstance(width, (list, tuple)):
            ws = [width[min(len(width) - 1, int(i * len(width) / cnt))] for i in range(cnt)]
        bm = bmesh.new()
        rows = []
        for i in range(cnt):
            a = P[(i - 1) % cnt] if (closed or i > 0) else P[i]
            b = P[(i + 1) % cnt] if (closed or i < cnt - 1) else P[i]
            t = (b - a)
            t = t.normalized() if t.length > 1e-9 else Vector((1, 0))
            nrm = Vector((-t.y, t.x))
            row = []
            for f in (-0.5, 0.0, 0.5):
                q = P[i] + nrm * ws[i] * f
                hit = self.bvh.ray_cast(org(self.s, q.x, q.y), d, 20.0)
                row.append(bm.verts.new(hit[0] - d * off) if hit[0] is not None else None)
            rows.append(row)
        segs = cnt if closed else cnt - 1
        for i in range(segs):
            r0, r1 = rows[i], rows[(i + 1) % cnt]
            for k in range(2):
                q = (r0[k], r1[k], r1[k + 1], r0[k + 1])
                if all(q):
                    bm.faces.new(q)
        if skirt:
            for k in (0, 2):
                low = [bm.verts.new(r[k].co + d * (off + skirt)) if r[k] else None for r in rows]
                for i in range(segs):
                    q = (rows[i][k], low[i], low[(i + 1) % cnt], rows[(i + 1) % cnt][k])
                    if all(q):
                        bm.faces.new(q)
        return self._finish(name, bm, d, material)

    def _finish(self, name, bm, d, material):
        if not bm.faces:
            bm.free()
            return None
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        flip = sum((f.normal.dot(d) for f in bm.faces)) > 0
        if flip:
            for f in bm.faces:
                f.normal_flip()
        return new_obj(name, bm, material)

    def mirror_y(self, pts):
        return [(-a, b) for a, b in pts]

    def both(self, fn, *a, **kw):
        """Calls fn for the left side (outline as given) and the right side (mirrored); returns (left, right)."""
        return fn(1, *a, **kw), fn(-1, *a, **kw)

    def add(self, target, ob):
        if ob:
            self.extra.setdefault(target, []).append(ob)
        return ob

    def box(self, name, lo, hi, material, bevel=0.01, segs=2):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co = Vector((lerp(lo[0], hi[0], v.co.x + 0.5), lerp(lo[1], hi[1], v.co.y + 0.5), lerp(lo[2], hi[2], v.co.z + 0.5)))
        ob = new_obj(name, bm, material, smooth_shade=False)
        if bevel:
            bv = ob.modifiers.new("bevel", "BEVEL")
            bv.width = bevel
            bv.segments = segs
            apply_mods(ob)
            for p in ob.data.polygons:
                p.use_smooth = True
        return ob

    def tube(self, name, path3d, radius, material, segs=10):
        """Round tube along a 3D polyline."""
        bm = bmesh.new()
        P = [Vector(p) for p in path3d]
        rings = []
        for i, p in enumerate(P):
            t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
            up = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((0, 1, 0))
            u = t.cross(up).normalized()
            v = u.cross(t).normalized()
            rings.append([bm.verts.new(p + (u * math.cos(2 * math.pi * k / segs) + v * math.sin(2 * math.pi * k / segs)) * radius)
                          for k in range(segs)])
        for i in range(len(rings) - 1):
            for k in range(segs):
                bm.faces.new((rings[i][k], rings[i][(k + 1) % segs], rings[i + 1][(k + 1) % segs], rings[i + 1][k]))
        for ring, rev in ((rings[0], True), (rings[-1], False)):
            bm.faces.new(list(reversed(ring)) if rev else ring)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        return new_obj(name, bm, material)

    def arch_flare(self, wx, side, r0, r1, y0, y1, material, a0=-8, a1=188, segs=28, zc=None):
        """Wheel-arch cladding / flare: a band around the arch from radius r0 to r1, from y0 (inner) to y1 (outer)."""
        s = self.s
        zc = s.r + 0.01 if zc is None else zc
        bm = bmesh.new()
        rows = []
        for i in range(segs + 1):
            a = math.radians(lerp(a0, a1, i / segs))
            ca, sa = math.cos(a), math.sin(a)
            # a: 0 = rear of the wheel... measured from +X of the car (front)
            pts = []
            for rad, y in ((r0, y0), (r1, y0), (r1, y1), (r0 + (r1 - r0) * 0.15, y1)):
                pts.append(bm.verts.new((self.X(wx) + ca * rad, side * y, zc + sa * rad)))
            rows.append(pts)
        for i in range(segs):
            for k in range(4):
                bm.faces.new((rows[i][k], rows[i][(k + 1) % 4], rows[i + 1][(k + 1) % 4], rows[i + 1][k]))
        bm.faces.new(rows[0])
        bm.faces.new(list(reversed(rows[-1])))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        ob = new_obj("flare", bm, material)
        bv = ob.modifiers.new("bevel", "BEVEL")
        bv.width = 0.012
        bv.segments = 2
        apply_mods(ob)
        return ob

    def roof_rails(self, x0, x1, inset, height, material, r=0.016):
        s = self.s
        out = []
        for side in (-1, 1):
            path = []
            n = 14
            for i in range(n + 1):
                x = lerp(x0, x1, i / n)
                y = side * (s.roof_hw(x) - inset)
                z = s.top(x) - 0.02 + height * (math.sin(math.pi * min(1, max(0, (i / n - 0.02) / 0.96))) ** 0.15)
                path.append((self.X(x), y, z))
            out.append(self.tube("rail", path, r, material))
            for x in (x0 + 0.08, x1 - 0.08):
                y = side * (s.roof_hw(x) - inset)
                out.append(self.box("rail_foot", (self.X(x) - 0.06, y - 0.02, s.top(x) - 0.03), (self.X(x) + 0.06, y + 0.02, s.top(x) + height),
                                    material, bevel=0.008))
        return out

    def spare(self, x, z, r_scale=1.0):
        """Spare wheel on the tailgate (wheel_spare): a road wheel turned to face backward."""
        s = self.s
        saved = dict(self.parts)
        ob = wheel2(self.car, self.mats, Vector((0, 0, 0)), -1, self.sp)
        self.parts.clear()
        self.parts.update(saved)
        ob.name = "wheel_spare"
        ob.rotation_euler = (0, 0, -math.pi / 2)
        ob.scale = (r_scale, r_scale, r_scale)
        ob.location = (self.X(x) - self.sp.get("tyre_w", 0.235) * 0.5, 0, z)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        self.parts["wheel_spare"] = ob
        return ob

    # -- standard pieces
    def wheels(self):
        s = self.s
        for wx in (s.fw, s.rw):
            for side in (-1, 1):
                wheel2(self.car, self.mats, Vector((self.X(wx), side * (s.W / 2 - self.sp.get("wheel_in", 0.125)), s.r)), side, self.sp)
        for wx in (s.fw, s.rw):
            for side in (-1, 1):
                bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=s.r + 0.05, depth=0.02,
                                                    location=(self.X(wx), side * (s.W / 2 - 0.36), s.r + 0.01),
                                                    rotation=(math.pi / 2, 0, 0))
                lo = bpy.context.object
                lo.name = "liner"
                lo.data.materials.append(self.mats["liner"])

    def mirrors(self, x, z, size=(0.22, 0.12, 0.13), material=None, out=0.16):
        """Door mirrors: a rounded housing on a short black arm. x: metres from the front, z: bottom of the housing."""
        s = self.s
        for side in (-1, 1):
            hw = s.hw(x)
            yo = side * (hw + out)
            yi = side * (hw + out - size[1])
            lo = (self.X(x) - size[0] / 2, min(yo, yi), z)
            hi = (self.X(x) + size[0] / 2, max(yo, yi), z + size[2])
            ob = self.box("mirror_" + ("l" if side > 0 else "r"), lo, hi,
                          material or self.parts["door_fl"].data.materials[0], bevel=0.045, segs=3)
            # narrow the housing toward the car and rake its face back
            for v in ob.data.vertices:
                t = (v.co.y * side - abs(yi)) / size[1]   # 0 at the inner end, 1 at the outer end
                v.co.z = lerp(z + size[2] * 0.5, v.co.z, 0.7 + 0.3 * t)
                if v.co.x > self.X(x):
                    v.co.x -= 0.05 * (1 - t)
            self.parts[ob.name] = ob
            y0, y1 = sorted((side * (hw - 0.04), yi + side * 0.01))
            arm = self.box("mirror_stalk", (self.X(x) - 0.06, y0, z + 0.005), (self.X(x) + 0.04, y1, z + 0.055),
                           self.mats["black"], bevel=0.01)
            arm.name = "mirror_stalk"

    def handles(self, z, length=0.2, height=0.032, material=None, flush=False):
        s = self.s
        c = self.sp["cuts"]
        doors = [("f", c["door0"], c["bpil"])]
        if c.get("rdoor"):
            doors.append(("r", c["bpil"], c["rdoor"]))
        for key, x0, x1 in doors:
            hx = x1 - 0.12 - length / 2 if not flush else x1 - 0.1 - length / 2
            for side, view in ((1, "left"), (-1, "right")):
                outline = rounded_poly([(hx - length / 2, z - height / 2), (hx + length / 2, z - height / 2),
                                        (hx + length / 2, z + height / 2), (hx - length / 2, z + height / 2)], height * 0.45)
                ob = self.blob("handle_" + key + ("l" if side > 0 else "r"), outline, view,
                               material or self.mats["black"], off=0.004 if flush else 0.012, rings=2, skirt=0.014, n=24)
                if ob:
                    self.parts[ob.name] = ob

    def plate(self, name, view, cy, cz, w=0.52, h=0.115):
        outline = rounded_poly([(cy - w / 2, cz - h / 2), (cy + w / 2, cz - h / 2), (cy + w / 2, cz + h / 2), (cy - w / 2, cz + h / 2)], 0.01)
        ob = self.blob(name, outline, view, self.mats["plate"], off=0.006, rings=2, skirt=0.01, n=24)
        if ob:
            self.parts[name] = ob

    def run(self):
        self.wheels()
        FEATURES[self.s.name](self)
        # join the decorative extras into the named parts the game knows about
        for target, objs in self.extra.items():
            base = self.parts.get(target)
            name = base.name if base else (("part_" + target) if target in PANEL_NAMES + ["underbody", "pillars", "beltline"] else target)
            self.parts[target] = join(([base] if base else []) + objs, name)


def orient(ob, outward):
    """Flips all faces of ob if most of them point against outward(face centre)."""
    score = sum(p.normal.dot(outward(p.center)) * p.area for p in ob.data.polygons)
    if score < 0:
        for p in ob.data.polygons:
            p.flip()
        ob.data.update()
    return ob


def wheel2(car, mats, center, side, sp):
    s = car["shape"]
    r = s.r
    tw = sp.get("tyre_w", 0.235)
    rim_r = sp["rim"] * 0.0254 / 2 + 0.012
    sg = side
    seg = SEG
    # tyre: rounded shoulders, bulging sidewall
    prof = [(rim_r - 0.005, -tw * 0.40), (rim_r + 0.012, -tw * 0.47), (r - 0.05, -tw * 0.5), (r - 0.012, -tw * 0.46),
            (r, -tw * 0.36), (r, tw * 0.36), (r - 0.012, tw * 0.46), (r - 0.05, tw * 0.5), (rim_r + 0.012, tw * 0.47),
            (rim_r - 0.005, tw * 0.40)]
    tire = orient(lathe("tire", [(a, b * sg) for a, b in prof], seg, mats["rubber"]), lambda c: Vector((c.x, 0, c.z)))
    face = sg * tw * 0.40
    # rim lip and dark barrel
    lip = lathe("rim_lip", [(rim_r - 0.004, face - sg * 0.004), (rim_r + 0.004, face + sg * 0.002), (rim_r - 0.014, face + sg * 0.004),
                            (rim_r - 0.022, face - sg * 0.006)], seg, mats["rim"])
    barrel = lathe("rim_barrel", [(rim_r - 0.02, face - sg * 0.01), (rim_r - 0.03, -sg * tw * 0.35), (0.06, -sg * tw * 0.35)], seg, mats["rim_dark"])
    style = sp.get("rim_style", "split5")
    bm = bmesh.new()
    conc = sp.get("rim_concave", 0.035)

    def spoke(a, w0, w1, r0, r1, depth=0.022, mid_bulge=0.0, twist=0.0):
        def pt(rad, w, k):
            # twist: the outer end of the spoke turns by this many radians (curved / turbine spokes)
            aa = a + twist * (rad - r0) / max(0.01, r1 - r0)
            ca, sa = math.cos(aa), math.sin(aa)
            return (ca * rad - sa * w / 2 * k, sa * rad + ca * w / 2 * k)
        top = []
        bot = []
        for rad, w in ((r0, w0), (r1, w1)):
            yface = face - sg * conc * (1 - (rad - r0) / max(0.01, r1 - r0)) - sg * 0.006
            for k in (-1, 1):
                x, z = pt(rad, w, k)
                top.append(bm.verts.new((x, yface + sg * 0.002, z)))
                bot.append(bm.verts.new((x, yface - sg * depth, z)))
        order = [0, 1, 3, 2]
        T = [top[i] for i in order]
        B = [bot[i] for i in order]
        bm.faces.new(T)
        bm.faces.new(list(reversed(B)))
        for k in range(4):
            bm.faces.new((T[k], T[(k + 1) % 4], B[(k + 1) % 4], B[k]))
    hub_r = 0.075
    rr = rim_r - 0.018
    if style == "split5":
        for i in range(5):
            a = 2 * math.pi * i / 5
            for d in (-1, 1):
                spoke(a + d * 0.14, 0.055, 0.05, hub_r * 0.8, rr)
                # the two arms of a pair meet at the hub
    elif style == "spoke10":
        for i in range(10):
            spoke(2 * math.pi * i / 10, 0.04, 0.022, hub_r * 0.8, rr)
    elif style == "six":
        for i in range(6):
            spoke(2 * math.pi * i / 6, 0.06, 0.05, hub_r * 0.8, rr)
    elif style == "five":
        for i in range(5):
            spoke(2 * math.pi * i / 5, 0.085, 0.07, hub_r * 0.8, rr, depth=0.03)
    elif style == "y5":
        for i in range(5):
            a = 2 * math.pi * i / 5
            spoke(a, 0.05, 0.04, hub_r * 0.8, rr * 0.55)
            for d in (-1, 1):
                spoke(a + d * 0.16, 0.03, 0.026, rr * 0.5, rr)
    elif style == "aero":
        pass
    # styles used by the restyled third-party cars (tools/car_restyle.py)
    elif style == "mesh":
        # cross-laced mesh: two sets of thin spokes leaning opposite ways
        for i in range(10):
            a = 2 * math.pi * i / 10
            for tw in (-0.55, 0.55):
                spoke(a, 0.022, 0.016, hub_r * 0.9, rr, depth=0.016, twist=tw)
    elif style == "star7":
        for i in range(7):
            spoke(2 * math.pi * i / 7, 0.07, 0.03, hub_r * 0.8, rr, depth=0.026)
    elif style == "twin6":
        for i in range(6):
            a = 2 * math.pi * i / 6
            for d in (-1, 1):
                spoke(a + d * 0.09, 0.032, 0.03, hub_r * 0.8, rr)
    elif style == "turbine":
        for i in range(12):
            spoke(2 * math.pi * i / 12, 0.045, 0.03, hub_r * 0.9, rr, depth=0.02, twist=0.5)
    elif style == "dish8":
        # deep dish: short spokes on a small centre, wide flat lip around them
        for i in range(8):
            spoke(2 * math.pi * i / 8, 0.05, 0.045, hub_r * 0.8, rr * 0.72, depth=0.03)
    elif style == "blade4":
        # four wide paddle spokes
        for i in range(4):
            spoke(2 * math.pi * i / 4 + 0.4, 0.07, 0.13, hub_r * 0.8, rr, depth=0.028)
    elif style == "steel":
        # plain steel wheel: a flat face with eight round-ish vent holes left between short webs
        for i in range(8):
            a = 2 * math.pi * i / 8
            spoke(a, 0.07, 0.11, hub_r * 0.9, rr * 0.62, depth=0.012)
            spoke(a + math.pi / 8, 0.12, 0.13, rr * 0.6, rr, depth=0.012)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    spokes = new_obj("spokes", bm, mats["rim"], smooth_shade=False)
    for ob in (lip,):
        orient(ob, lambda c: Vector((0, sg, 0)))
    parts = [tire, lip, barrel, spokes]
    if style == "aero":
        # flat aero cover with five dark slots
        cover = lathe("cover", [(rr, face - sg * 0.004), (rr * 0.6, face + sg * 0.002), (0.06, face - sg * 0.006)], seg, mats["rim"])
        parts.append(orient(cover, lambda c: Vector((0, sg, 0))))
        bm = bmesh.new()
        for i in range(5):
            a = 2 * math.pi * i / 5
            pts = []
            for rad, aa in ((rr * 0.45, a - 0.12), (rr * 0.92, a - 0.3), (rr * 0.92, a + 0.05), (rr * 0.45, a + 0.12)):
                pts.append(bm.verts.new((math.cos(aa) * rad, face + sg * 0.004 + sg * (0.002 if rad > rr * 0.6 else 0.004), math.sin(aa) * rad)))
            bm.faces.new(pts)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        parts.append(new_obj("slots", bm, mats["rim_dark"], smooth_shade=False))
    if style in ("dish8", "steel"):
        # flat ring between the short spokes and the rim lip
        r_in = rr * (0.7 if style == "dish8" else 0.58)
        ring = lathe("dish", [(rr + 0.004, face - sg * conc * 0.2), (r_in, face - sg * conc * 0.35),
                              (r_in - 0.006, face - sg * conc * 0.45)], seg, mats["rim"])
        parts.append(orient(ring, lambda c: Vector((0, sg, 0))))
    if sp.get("tread") == "at":
        # all-terrain tread: staggered blocks standing proud of the tyre
        bm = bmesh.new()
        n = 40 if LOD >= 2 else 30
        for i in range(n):
            for half in (-1, 1):
                a = 2 * math.pi * (i + (0.5 if half > 0 else 0.0)) / n
                da = math.pi / n * 0.7
                y0, y1 = (0.02, tw * 0.47) if half > 0 else (-tw * 0.47, -0.02)
                vs = []
                for rad in (r - 0.004, r + 0.012):
                    for aa in (a - da, a + da):
                        for y in (y0, y1):
                            vs.append(bm.verts.new((math.cos(aa) * rad, y, math.sin(aa) * rad)))
                bmesh.ops.convex_hull(bm, input=vs)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        parts.append(new_obj("tread", bm, mats["rubber"], smooth_shade=False))
    # hub cap and lug nuts
    cap = lathe("cap", [(hub_r, face - sg * conc - sg * 0.004), (hub_r * 0.85, face - sg * conc + sg * 0.008), (0.0, face - sg * conc + sg * 0.012)],
                24, mats["rim"] if style != "aero" else mats["rim_dark"])
    parts.append(orient(cap, lambda c: Vector((0, sg, 0))))
    # brake disc and caliper behind the spokes
    disc = lathe("disc", [(0.06, -sg * 0.0), (rim_r * 0.82, -sg * 0.0), (rim_r * 0.82, -sg * 0.026), (0.06, -sg * 0.026)], seg // 2, mats["disc"])
    parts.append(disc)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    cal = new_obj("caliper", bm, None, smooth_shade=False)
    cal.data.materials.append(_caliper_mat(sp, mats))
    for v in cal.data.vertices:
        v.co = Vector((v.co.x * 0.16, v.co.y * 0.06 + sg * 0.01, v.co.z * rim_r * 0.4 + rim_r * 0.55))
    # behind the axle, toward the rear of the car
    for v in cal.data.vertices:
        a = math.radians(-35)
        x, z = v.co.x, v.co.z
        v.co.x, v.co.z = x * math.cos(a) - z * math.sin(a), x * math.sin(a) + z * math.cos(a)
    parts.append(cal)
    key = ("wheel_f" if center.x > 0 else "wheel_r") + ("l" if side > 0 else "r")
    for ob in parts:
        ob.location = center + Vector(ob.location)
    bpy.ops.object.select_all(action="DESELECT")
    for ob in parts:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = tire
    bpy.ops.object.join()
    tire.name = key
    car["parts"][key] = tire
    return tire


# ------------------------------------------------------------------ v2 specs (metres; x back from the front bumper)

V2 = {
    # Toyota Camry XV70 (2018-2024): low sleek sedan, long hood, fast C-pillar, huge lower grille
    "Toyoda Camri": dict(
        type="sedan", L=4.885, W=1.84, H=1.445, WB=2.825, FO=0.96, D=0.67, rim=18, tyre_w=0.235,
        bottom=[(0.0, 0.36), (0.05, 0.27), (0.2, 0.2), (0.6, 0.16), (1.0, 0.155), (3.7, 0.155), (4.3, 0.2), (4.65, 0.28),
                (4.83, 0.36), (4.885, 0.44)],
        top=[(0.0, 0.47), (0.025, 0.6), (0.07, 0.7), (0.15, 0.755), (0.45, 0.8), (0.9, 0.855), (1.3, 0.905), (1.6, 0.95),
             (1.9, 1.08), (2.2, 1.225), (2.45, 1.34), (2.65, 1.405), (2.9, 1.438), (3.15, 1.445), (3.4, 1.425),
             (3.65, 1.36), (3.9, 1.26), (4.1, 1.165), (4.26, 1.095), (4.5, 1.075), (4.72, 1.065), (4.82, 1.05),
             (4.865, 1.0), (4.885, 0.92)],
        belt=[(0.0, 0.45), (0.04, 0.6), (0.13, 0.71), (0.45, 0.775), (0.9, 0.83), (1.3, 0.885), (1.65, 0.955),
              (1.9, 0.985), (2.8, 1.015), (3.8, 1.045), (4.4, 1.055), (4.75, 1.045), (4.85, 1.0), (4.885, 0.9)],
        plan=dict(cf=0.42, nf=2.2, cr=0.4, nr=2.6, flare_f=0.012, flare_r=0.02),
        sec=dict(tuck=0.08, rocker=0.12, maxw=0.72, shoulder=0.05, hood_p=2.0, upper=0.07, creases={6: 0.85, 7: 0.6}),
        gh=dict(g0=1.6, a_top=2.66, c_top=3.42, g1=4.27, tumble=0.25, dlo_f=1.78, dlo_r=4.02, pillars=[2.87, 3.72],
                pillar_w=0.045, frame_black=True),
        cuts=dict(fb=0.4, hood0=0.17, door0=1.72, bpil=2.87, rdoor=3.66, rb=4.52, tail=4.84, gate=(4.7, 0.8)),
        rim_style="split5", rim_color=(0.32, 0.33, 0.35), caliper=None, grille_pattern="slats",
    ),
    # Dodge Charger LD (2015-2023): long, tall-shouldered four-door, blunt nose, recessed grille, racetrack tail lamp
    "Dodgy Charjer": dict(
        type="sedan", L=5.04, W=1.905, H=1.48, WB=3.05, FO=0.95, D=0.73, rim=20, tyre_w=0.245,
        bottom=[(0.0, 0.4), (0.04, 0.28), (0.2, 0.2), (0.6, 0.17), (1.0, 0.16), (3.8, 0.16), (4.4, 0.21), (4.8, 0.3),
                (4.99, 0.38), (5.04, 0.46)],
        top=[(0.0, 0.52), (0.02, 0.68), (0.06, 0.79), (0.13, 0.835), (0.5, 0.865), (1.0, 0.905), (1.5, 0.945), (1.88, 0.99),
             (2.1, 1.1), (2.35, 1.24), (2.6, 1.37), (2.8, 1.44), (3.05, 1.475), (3.3, 1.48), (3.55, 1.46), (3.8, 1.39),
             (4.05, 1.28), (4.25, 1.17), (4.42, 1.1), (4.7, 1.085), (4.95, 1.092), (5.0, 1.088), (5.025, 1.04), (5.04, 0.95)],
        belt=[(0.0, 0.5), (0.03, 0.66), (0.12, 0.81), (0.5, 0.845), (1.0, 0.88), (1.5, 0.93), (1.9, 0.99), (2.2, 1.03),
              (3.5, 1.06), (4.4, 1.08), (4.9, 1.078), (5.0, 1.05), (5.04, 0.94)],
        plan=dict(cf=0.34, nf=3.0, cr=0.3, nr=3.2, flare_f=0.014, flare_r=0.03, flare_len=0.65),
        sec=dict(tuck=0.07, rocker=0.13, maxw=0.7, shoulder=0.06, hood_p=2.0, upper=0.07, creases={6: 0.9, 7: 0.6}),
        gh=dict(g0=1.88, a_top=2.85, c_top=3.6, g1=4.42, tumble=0.27, dlo_f=2.05, dlo_r=4.02, pillars=[3.0],
                pillar_w=0.05, frame_black=True),
        cuts=dict(fb=0.38, hood0=0.12, door0=2.0, bpil=3.0, rdoor=3.78, rb=4.62, tail=4.98, gate=(4.85, 0.84)),
        rim_style="y5", rim_color=(0.16, 0.165, 0.17), rim_rough=0.35, caliper="#c62828", grille_pattern="hex",
    ),
    # Tesla Model 3: low grille-less nose, cab-forward glass canopy, fastback tail, flush handles
    "Teslo Model 3": dict(
        type="fastback", L=4.694, W=1.849, H=1.443, WB=2.875, FO=0.84, D=0.67, rim=18, tyre_w=0.235,
        bottom=[(0.0, 0.32), (0.05, 0.24), (0.2, 0.18), (0.5, 0.15), (1.0, 0.145), (3.7, 0.145), (4.2, 0.2), (4.55, 0.3),
                (4.694, 0.4)],
        top=[(0.0, 0.43), (0.02, 0.53), (0.07, 0.615), (0.16, 0.675), (0.4, 0.725), (0.8, 0.795), (1.2, 0.875), (1.45, 0.93),
             (1.7, 1.05), (2.0, 1.2), (2.3, 1.33), (2.55, 1.41), (2.8, 1.44), (3.0, 1.443), (3.2, 1.43), (3.45, 1.38),
             (3.7, 1.3), (3.95, 1.2), (4.15, 1.12), (4.3, 1.075), (4.5, 1.06), (4.62, 1.055), (4.67, 1.03), (4.694, 0.95)],
        belt=[(0.0, 0.42), (0.03, 0.52), (0.14, 0.64), (0.5, 0.71), (1.0, 0.82), (1.45, 0.92), (1.7, 0.96), (2.5, 0.99),
              (3.5, 1.02), (4.2, 1.04), (4.6, 1.035), (4.68, 0.99), (4.694, 0.92)],
        plan=dict(cf=0.45, nf=2.3, cr=0.42, nr=2.4, flare_f=0.012, flare_r=0.018),
        sec=dict(tuck=0.08, rocker=0.11, maxw=0.66, shoulder=0.045, hood_p=2.2, upper=0.08, creases={6: 0.6, 7: 0.6}),
        gh=dict(g0=1.45, a_top=2.5, c_top=3.25, g1=4.3, tumble=0.27, dlo_f=1.62, dlo_r=4.0, pillars=[2.78],
                pillar_w=0.045, glass_roof=True, header=0.03, a_black=True, frame_black=True),
        cuts=dict(fb=0.36, hood0=0.1, door0=1.6, bpil=2.78, rdoor=3.6, rb=4.35, tail=4.66, gate=(4.5, 0.86)),
        rim_style="aero", rim_color=(0.05, 0.052, 0.055), rim_rough=0.35, caliper=None, wheel_in=0.13,
    ),
    # Subaru Outback (2020+): raised wagon, black arch and sill cladding, roof rails, sloped tailgate
    "Subaro Outbuck": dict(
        type="suv", L=4.87, W=1.855, H=1.62, WB=2.745, FO=0.96, D=0.727, rim=18, tyre_w=0.225, cladding=True,
        bottom=[(0.0, 0.45), (0.05, 0.35), (0.25, 0.28), (0.6, 0.25), (1.0, 0.24), (3.6, 0.24), (4.1, 0.27), (4.55, 0.36),
                (4.8, 0.43), (4.87, 0.5)],
        top=[(0.0, 0.58), (0.03, 0.74), (0.1, 0.86), (0.2, 0.905), (0.6, 0.95), (1.0, 0.99), (1.35, 1.04), (1.55, 1.08),
             (1.8, 1.24), (2.05, 1.4), (2.25, 1.52), (2.45, 1.585), (2.7, 1.61), (3.5, 1.62), (4.2, 1.605), (4.42, 1.585),
             (4.55, 1.5), (4.66, 1.36), (4.74, 1.22), (4.8, 1.12), (4.835, 1.06), (4.86, 0.98), (4.87, 0.85)],
        belt=[(0.0, 0.56), (0.04, 0.72), (0.15, 0.87), (0.6, 0.93), (1.0, 0.97), (1.5, 1.05), (1.75, 1.08), (3.0, 1.11),
              (4.2, 1.14), (4.6, 1.13), (4.8, 1.1), (4.87, 0.85)],
        plan=dict(cf=0.4, nf=2.6, cr=0.3, nr=3.5, flare_f=0.012, flare_r=0.015),
        sec=dict(tuck=0.06, rocker=0.14, maxw=0.7, shoulder=0.05, hood_p=2.2, upper=0.07, creases={6: 0.8, 7: 0.7}),
        gh=dict(g0=1.55, a_top=2.55, c_top=4.42, g1=4.8, tumble=0.19, dlo_f=1.72, dlo_r=4.56, pillars=[2.75, 3.72],
                pillar_w=0.045, frame_black=True),
        cuts=dict(fb=0.42, hood0=0.18, door0=1.68, bpil=2.75, rdoor=3.62, rb=4.55, tail=4.86, gate=(4.7, 0.62)),
        rim_style="y5", rim_color=(0.2, 0.205, 0.215), rim_rough=0.3, caliper=None, grille_pattern="hex", arch_gap=0.04,
    ),
    # Jeep Wrangler JL four-door: flat grille panel with seven slots and round lamps, exposed flared fenders,
    # upright windscreen, boxy hardtop, spare wheel on the tailgate. x=0 is the grille face (steel bumpers stick out).
    "Jeap Wrangle": dict(
        type="boxy", L=4.5, W=1.894, H=1.84, WB=3.008, FO=0.62, D=0.8, rim=17, tyre_w=0.255, cladding=True,
        bottom=[(0.0, 0.66), (0.03, 0.6), (0.15, 0.55), (0.45, 0.52), (1.0, 0.48), (3.2, 0.48), (3.9, 0.5), (4.3, 0.52), (4.5, 0.55)],
        top=[(0.0, 1.12), (0.02, 1.17), (0.06, 1.185), (0.3, 1.2), (1.0, 1.215), (1.52, 1.225), (1.6, 1.33), (1.7, 1.48),
             (1.78, 1.6), (1.85, 1.71), (1.93, 1.79), (2.05, 1.835), (2.3, 1.84), (4.2, 1.84), (4.38, 1.835), (4.44, 1.8),
             (4.47, 1.72), (4.488, 1.5), (4.5, 1.2)],
        belt=[(0.0, 1.1), (0.03, 1.16), (0.1, 1.18), (1.0, 1.2), (1.55, 1.22), (4.4, 1.225), (4.5, 1.15)],
        plan=dict(body_w=1.74, cf=0.1, nf=5.0, cr=0.08, nr=5.0, flare_f=0.0, flare_r=0.0),
        sec=dict(tuck=0.03, rocker=0.08, maxw=0.6, shoulder=0.02, hood_p=4.0, upper=0.04, glass_inset=0.02, drip=0.045,
                 blend=0.12, creases={6: 1.0, 7: 0.9, 8: 0.6}),
        gh=dict(g0=1.52, a_top=2.0, c_top=4.42, g1=4.494, tumble=0.075, dlo_f=1.63, dlo_r=4.36, pillars=[2.62, 3.6],
                pillar_w=0.05, frame_black=True),
        cuts=dict(fb=0.12, hood0=0.025, door0=1.55, bpil=2.62, rdoor=3.5, rb=4.42, tail=4.47, gate=(4.46, 0.6)),
        arch_gap=0.1, arch_lift=0.04, wheel_in=0.14,
        rim_style="five", rim_color=(0.18, 0.185, 0.19), rim_rough=0.35, caliper=None, rim_concave=0.05, tread="at",
    ),
    # Chevrolet Tahoe (2021+): tall boxy full-size SUV, chrome grille bar, long rear quarter glass
    "Chevro Tahoma": dict(
        type="suv", L=5.35, W=2.06, H=1.93, WB=3.07, FO=1.0, D=0.84, rim=20, tyre_w=0.275,
        bottom=[(0.0, 0.5), (0.05, 0.4), (0.3, 0.33), (0.6, 0.3), (1.0, 0.3), (3.8, 0.3), (4.4, 0.33), (4.9, 0.4), (5.3, 0.48),
                (5.35, 0.55)],
        top=[(0.0, 0.72), (0.02, 1.0), (0.06, 1.17), (0.15, 1.24), (0.5, 1.27), (1.0, 1.3), (1.65, 1.335), (1.9, 1.5),
             (2.1, 1.66), (2.3, 1.79), (2.5, 1.875), (2.75, 1.92), (3.0, 1.93), (4.9, 1.925), (5.15, 1.91), (5.24, 1.86),
             (5.3, 1.6), (5.33, 1.35), (5.345, 1.2), (5.35, 1.0)],
        belt=[(0.0, 0.7), (0.03, 0.98), (0.12, 1.2), (0.5, 1.24), (1.0, 1.28), (1.6, 1.33), (1.8, 1.36), (5.0, 1.38),
              (5.3, 1.35), (5.35, 1.0)],
        plan=dict(cf=0.22, nf=4.0, cr=0.2, nr=5.0, flare_f=0.012, flare_r=0.012),
        sec=dict(tuck=0.05, rocker=0.14, maxw=0.75, shoulder=0.045, hood_p=3.0, upper=0.07, creases={6: 0.9, 7: 0.8}),
        gh=dict(g0=1.65, a_top=2.75, c_top=5.2, g1=5.33, tumble=0.15, dlo_f=1.85, dlo_r=5.05, pillars=[2.95, 3.95],
                pillar_w=0.05, frame_black=True),
        cuts=dict(fb=0.45, hood0=0.12, door0=1.8, bpil=2.95, rdoor=3.85, rb=5.0, tail=5.3, gate=(5.2, 0.68)),
        rim_style="six", rim_color=(0.6, 0.61, 0.63), caliper=None, grille_pattern="hex",
    ),
}


def feat_camry(D):
    M = D.mats
    for sd in (1, -1):
        sfx = "l" if sd > 0 else "r"
        hl = [(0.36, 0.655), (0.56, 0.645), (0.74, 0.655), (0.86, 0.68), (0.93, 0.725), (0.935, 0.8), (0.82, 0.808),
              (0.64, 0.79), (0.48, 0.765), (0.37, 0.725)]
        house = D.blob("hl", rounded_poly([(sd * a, b) for a, b in hl], 0.02), "front", M["lamp_lens"])
        inner = D.blob("hl", rounded_poly([(sd * a, b) for a, b in [(0.5, 0.672), (0.84, 0.69), (0.88, 0.75), (0.52, 0.735)]], 0.02),
                       "front", M["lamp_housing"], off=0.006, skirt=0)
        p1 = D.blob("hl", ellipse(sd * 0.62, 0.705, 0.036, 0.028, 16), "front", M["lamp_chrome"], off=0.008, rings=2, skirt=0)
        p2 = D.blob("hl", ellipse(sd * 0.75, 0.715, 0.036, 0.028, 16), "front", M["lamp_chrome"], off=0.008, rings=2, skirt=0)
        drl = D.band("hl", [(sd * 0.42, 0.715), (sd * 0.5, 0.74), (sd * 0.62, 0.765), (sd * 0.78, 0.778), (sd * 0.9, 0.785)],
                     0.012, "front", M["drl"], off=0.008, n=24, skirt=0)
        house = join([house, inner], "hl")
        ob = join([house, p1, p2, drl], "headlight_" + sfx)
        D.parts[ob.name] = ob
        tl = [(0.38, 0.935), (0.6, 0.925), (0.8, 0.905), (0.915, 0.9), (0.93, 0.955), (0.89, 1.005), (0.7, 1.015),
              (0.5, 1.005), (0.38, 0.985)]
        t0 = D.blob("tl", rounded_poly([(sd * a, b) for a, b in tl], 0.015), "rear", M["tail_red"])
        t1 = D.band("tl", [(sd * 0.42, 0.965), (sd * 0.6, 0.968), (sd * 0.78, 0.96), (sd * 0.9, 0.95)], 0.01, "rear", M["tail_led"],
                    off=0.007, n=20, skirt=0)
        t2 = D.blob("tl", rounded_poly([(sd * 0.7, 0.915), (sd * 0.82, 0.91), (sd * 0.82, 0.935), (sd * 0.7, 0.94)], 0.008),
                    "rear", M["reverse"], off=0.007, rings=2, skirt=0)
        ob = join([t0, t1, t2], "taillight_" + sfx)
        D.parts[ob.name] = ob
        # lower bumper fang intakes
        # exhaust tips
        D.add("underbody", D.blob("ex", rounded_poly([(sd * 0.48, 0.3), (sd * 0.66, 0.3), (sd * 0.66, 0.36), (sd * 0.48, 0.36)], 0.025),
                                  "rear", M["chrome"], off=0.008))
        D.add("underbody", D.blob("ex", rounded_poly([(sd * 0.495, 0.307), (sd * 0.645, 0.307), (sd * 0.645, 0.353), (sd * 0.495, 0.353)], 0.02),
                                  "rear", M["gloss_black"], off=0.011, skirt=0))
    upper = D.blob("grille_u", rounded_poly([(-0.37, 0.698), (0.37, 0.698), (0.37, 0.735), (-0.37, 0.735)], 0.012), "front", M["gloss_black"])
    lower = D.blob("grille_l", rounded_poly([(-0.5, 0.6), (0.5, 0.6), (0.7, 0.63), (0.82, 0.56), (0.8, 0.3), (0.6, 0.26), (-0.6, 0.26),
                                             (-0.8, 0.3), (-0.82, 0.56), (-0.7, 0.63)], [0.04, 0.04, 0.03, 0.04, 0.06, 0.06, 0.06, 0.06, 0.04, 0.03]),
                   "front", M["grille_mesh"], n=72)
    bar = D.band("grille_bar", [(-0.6, 0.47), (0.6, 0.47)], 0.022, "front", M["gloss_black"], off=0.008, n=20, skirt=0)
    D.parts["grille"] = join([upper, lower, bar], "grille")
    D.add("underbody", D.blob("diff", rounded_poly([(-0.78, 0.29), (0.78, 0.29), (0.74, 0.39), (-0.74, 0.39)], 0.03), "rear", M["plastic"]))
    D.plate("plate_r", "rear", 0.0, 0.79)
    D.mirrors(1.86, 0.985)
    D.handles(0.945, material=D.parts["door_fl"].data.materials[0])


def sym(sd, pts):
    return [(sd * a, b) for a, b in pts]


def rect(y0, z0, y1, z1, r=0.01):
    return rounded_poly([(y0, z0), (y1, z0), (y1, z1), (y0, z1)], r)


def feat_charger(D):
    M = D.mats
    for sd in (1, -1):
        sfx = "l" if sd > 0 else "r"
        house = D.blob("hl", rounded_poly(sym(sd, [(0.58, 0.69), (0.87, 0.7), (0.915, 0.74), (0.91, 0.815), (0.6, 0.81)]), 0.02), "front",
                       M["lamp_housing"], off=0.006)
        lens = D.blob("hl", ellipse(sd * 0.71, 0.752, 0.055, 0.032, 20), "front", M["lamp_lens"], off=0.009, rings=2, skirt=0)
        lens2 = D.blob("hl", ellipse(sd * 0.83, 0.755, 0.04, 0.03, 20), "front", M["lamp_chrome"], off=0.009, rings=2, skirt=0)
        ring = D.band("hl", rounded_poly(sym(sd, [(0.61, 0.705), (0.88, 0.712), (0.9, 0.8), (0.62, 0.797)]), 0.03), 0.012, "front",
                      M["drl"], off=0.011, closed=True, n=48, skirt=0)
        ob = join([house, lens, lens2, ring], "headlight_" + sfx)
        D.parts[ob.name] = ob
        # racetrack tail lamp: each half is the smoked lens plus its half of the LED ring
        base = D.blob("tl", rounded_poly(sym(sd, [(0.0, 0.905), (0.9, 0.9), (0.93, 0.96), (0.9, 1.035), (0.0, 1.035)]), [0, 0.03, 0.03, 0.03, 0]),
                      "rear", M["tail_dark"], n=48)
        led = D.band("tl", sym(sd, [(0.0, 0.925), (0.6, 0.924), (0.84, 0.925), (0.885, 0.945), (0.89, 0.97), (0.885, 0.995),
                                    (0.84, 1.013), (0.6, 1.014), (0.0, 1.013)]), 0.02, "rear", M["tail_led"], off=0.008, n=50, skirt=0)
        ob = join([base, led], "taillight_" + sfx)
        D.parts[ob.name] = ob
        D.add("underbody", D.blob("ex", ellipse(sd * 0.6, 0.31, 0.055, 0.045, 24), "rear", M["chrome"], off=0.008))
        D.add("underbody", D.blob("ex", ellipse(sd * 0.6, 0.31, 0.042, 0.033, 24), "rear", M["gloss_black"], off=0.011, skirt=0))
        D.add("underbody", D.blob("side_in", rounded_poly(sym(sd, [(0.68, 0.3), (0.86, 0.32), (0.87, 0.5), (0.7, 0.47)]), 0.03),
                                  "front", M["grille_mesh"]))
    # one wide recessed opening across the whole nose: grille in the middle, lamps at the ends
    g1 = D.blob("grille", rounded_poly([(-0.92, 0.68), (0.92, 0.68), (0.94, 0.82), (-0.94, 0.82)], 0.03), "front", M["grille_mesh"], n=80)
    surround = D.band("grille", rounded_poly([(-0.93, 0.675), (0.93, 0.675), (0.95, 0.825), (-0.95, 0.825)], 0.03), 0.012, "front",
                      M["gloss_black"], closed=True, n=80, off=0.007)
    g2 = D.blob("grille", rounded_poly([(-0.6, 0.26), (0.6, 0.26), (0.66, 0.52), (-0.66, 0.52)], [0.04, 0.04, 0.05, 0.05]), "front",
                M["grille_mesh"], n=60)
    D.parts["grille"] = join([g1, surround, g2], "grille")
    D.add("underbody", D.blob("splitter", rounded_poly([(-0.8, 0.2), (0.8, 0.2), (0.82, 0.25), (-0.82, 0.25)], 0.02), "front", M["plastic"]))
    D.add("underbody", D.blob("diff", rounded_poly([(-0.8, 0.27), (0.8, 0.27), (0.76, 0.37), (-0.76, 0.37)], 0.03), "rear", M["plastic"]))
    # hood: a pair of black heat extractors on the power bulge
    for sd in (1, -1):
        D.add("underbody", D.blob("vent", rounded_poly([(0.75, sd * 0.2), (1.05, sd * 0.22), (1.05, sd * 0.32), (0.75, sd * 0.3)], 0.02),
                                  "top", M["grille_mesh"], off=0.004))
    D.plate("plate_r", "rear", 0.0, 0.78)
    D.mirrors(2.1, 1.0, size=(0.22, 0.12, 0.13))
    D.handles(0.97, material=D.parts["door_fl"].data.materials[0])


def feat_tesla(D):
    M = D.mats
    for sd in (1, -1):
        sfx = "l" if sd > 0 else "r"
        hl = [(0.46, 0.605), (0.7, 0.612), (0.86, 0.635), (0.93, 0.68), (0.92, 0.72), (0.78, 0.712), (0.6, 0.685), (0.46, 0.65)]
        house = D.blob("hl", rounded_poly(sym(sd, hl), 0.015), "front", M["lamp_housing"])
        lens = D.blob("hl", ellipse(sd * 0.75, 0.66, 0.06, 0.026, 20), "front", M["lamp_lens"], off=0.007, rings=2, skirt=0)
        lens2 = D.blob("hl", ellipse(sd * 0.62, 0.645, 0.045, 0.022, 20), "front", M["lamp_chrome"], off=0.007, rings=2, skirt=0)
        drl = D.band("hl", sym(sd, [(0.49, 0.625), (0.66, 0.634), (0.82, 0.66), (0.9, 0.7)]), 0.008, "front", M["drl"], off=0.008, n=16, skirt=0)
        lens = join([lens, lens2], "hl")
        ob = join([house, lens, drl], "headlight_" + sfx)
        D.parts[ob.name] = ob
        tl = [(0.42, 0.93), (0.65, 0.915), (0.86, 0.9), (0.93, 0.94), (0.915, 0.99), (0.7, 1.0), (0.5, 0.995), (0.42, 0.975)]
        t0 = D.blob("tl", rounded_poly(sym(sd, tl), 0.015), "rear", M["tail_dark"])
        t1 = D.band("tl", sym(sd, [(0.47, 0.96), (0.62, 0.95), (0.78, 0.938), (0.89, 0.935)]), 0.012, "rear", M["tail_led"], off=0.007, n=16, skirt=0)
        t2 = D.blob("tl", ellipse(sd * 0.82, 0.965, 0.04, 0.018, 16), "rear", M["tail_red"], off=0.007, rings=2, skirt=0)
        ob = join([t0, t1, t2], "taillight_" + sfx)
        D.parts[ob.name] = ob
        D.add("underbody", D.blob("fog", rounded_poly(sym(sd, [(0.66, 0.29), (0.8, 0.3), (0.79, 0.36), (0.67, 0.35)]), 0.025), "front", M["plastic"]))
    D.parts["grille"] = D.blob("grille", rounded_poly([(-0.42, 0.22), (0.42, 0.22), (0.46, 0.28), (-0.46, 0.28)], 0.025), "front",
                               M["grille_mesh"], n=40)
    D.add("underbody", D.blob("diff", rounded_poly([(-0.72, 0.3), (0.72, 0.3), (0.7, 0.36), (-0.7, 0.36)], 0.025), "rear", M["gloss_black"]))
    D.plate("plate_r", "rear", 0.0, 0.62)
    D.mirrors(1.66, 0.95, size=(0.2, 0.11, 0.12), out=0.14)
    D.handles(0.94, length=0.17, height=0.026, material=M["gloss_black"], flush=True)


def feat_outback(D):
    M = D.mats
    s = D.s
    for sd in (1, -1):
        sfx = "l" if sd > 0 else "r"
        hl = [(0.5, 0.78), (0.78, 0.785), (0.88, 0.8), (0.9, 0.86), (0.82, 0.885), (0.54, 0.855)]
        house = D.blob("hl", rounded_poly(sym(sd, hl), 0.02), "front", M["lamp_housing"])
        lens = D.blob("hl", ellipse(sd * 0.72, 0.83, 0.045, 0.03, 20), "front", M["lamp_lens"], off=0.007, rings=2, skirt=0)
        drl = D.band("hl", sym(sd, [(0.56, 0.8), (0.8, 0.8), (0.87, 0.82), (0.86, 0.86), (0.78, 0.875)]), 0.012, "front", M["drl"],
                     off=0.008, n=24, skirt=0)
        ob = join([house, lens, drl], "headlight_" + sfx)
        D.parts[ob.name] = ob
        tl = [(0.6, 0.95), (0.86, 0.94), (0.9, 1.0), (0.86, 1.12), (0.72, 1.12), (0.7, 1.0)]
        t0 = D.blob("tl", rounded_poly(sym(sd, tl), 0.02), "rear", M["tail_red"])
        t1 = D.band("tl", sym(sd, [(0.72, 1.1), (0.75, 0.99), (0.86, 0.975)]), 0.016, "rear", M["tail_led"], off=0.008, n=16, skirt=0)
        ob = join([t0, t1], "taillight_" + sfx)
        D.parts[ob.name] = ob
        D.add("underbody", D.blob("fog", rounded_poly(sym(sd, [(0.6, 0.42), (0.82, 0.44), (0.8, 0.58), (0.62, 0.55)]), 0.03),
                                  "front", M["plastic"]))
        # black cladding: wheel arches and sills
        for wx in (s.fw, s.rw):
            D.add("rocker_" + sfx, D.arch_flare(wx, sd, s.r + 0.035, s.r + 0.11, s.hw(wx) - 0.06, s.hw(wx) + 0.018, M["plastic"],
                                                a0=-5, a1=185))
    hexg = [(-0.38, 0.56), (0.38, 0.56), (0.48, 0.66), (0.42, 0.8), (-0.42, 0.8), (-0.48, 0.66)]
    g = D.blob("grille", rounded_poly(hexg, 0.03), "front", M["grille_mesh"], n=60)
    trim = D.band("grille", rounded_poly(hexg, 0.03), 0.018, "front", M["chrome"], closed=True, n=60, off=0.008)
    wing = D.band("grille", [(-0.62, 0.79), (-0.4, 0.74), (0.4, 0.74), (0.62, 0.79)], 0.02, "front", M["chrome"], off=0.009, n=30, skirt=0)
    D.parts["grille"] = join([g, trim, wing], "grille")
    # lower black bumpers with a silver skid plate
    D.add("underbody", D.blob("lowf", rounded_poly([(-0.82, 0.3), (0.82, 0.3), (0.84, 0.46), (-0.84, 0.46)], 0.04), "front", M["plastic"], off=0.003))
    D.add("underbody", D.blob("skid", rounded_poly([(-0.36, 0.3), (0.36, 0.3), (0.32, 0.38), (-0.32, 0.38)], 0.02), "front", M["satin"], off=0.007))
    D.add("underbody", D.blob("lowr", rounded_poly([(-0.86, 0.36), (0.86, 0.36), (0.86, 0.55), (-0.86, 0.55)], 0.04), "rear", M["plastic"], off=0.003))
    for sd, view in ((1, "left"), (-1, "right")):
        D.add("rocker_" + ("l" if sd > 0 else "r"),
              D.blob("sill", rounded_poly([(s.fw + s.r + 0.08, 0.26), (s.rw - s.r - 0.08, 0.26), (s.rw - s.r - 0.08, 0.42),
                                           (s.fw + s.r + 0.08, 0.42)], 0.03), view, M["plastic"], off=0.003, n=40))
    D.add("pillars", None)
    for ob in D.roof_rails(1.95, 4.3, 0.07, 0.06, M["satin"]):
        D.add("pillars", ob)
    D.plate("plate_r", "rear", 0.0, 0.66)
    D.mirrors(1.82, 1.07, size=(0.22, 0.12, 0.14))
    D.handles(1.02, material=D.parts["door_fl"].data.materials[0])


def feat_wrangler(D):
    M = D.mats
    s = D.s
    # seven-slot grille and round headlamps on the flat grille panel
    slots = []
    for i in range(-3, 4):
        y = i * 0.1
        slots.append(D.blob("slot", rect(y - 0.032, 0.79, y + 0.032, 1.08, 0.03), "front", M["grille_mesh"], off=0.004, n=28))
    D.parts["grille"] = join(slots, "grille")
    for sd in (1, -1):
        sfx = "l" if sd > 0 else "r"
        y = sd * 0.5
        bezel = D.blob("hl", ellipse(y, 0.94, 0.11, 0.11, 32), "front", M["gloss_black"], off=0.006)
        lens = D.blob("hl", ellipse(y, 0.94, 0.09, 0.09, 32), "front", M["lamp_lens"], off=0.009, skirt=0, bulge=0.01)
        ring = D.band("hl", ellipse(y, 0.94, 0.078, 0.078, 32), 0.012, "front", M["drl"], off=0.012, closed=True, skirt=0)
        ob = join([bezel, lens, ring], "headlight_" + sfx)
        D.parts[ob.name] = ob
        # vertical tail lamps at the rear corners
        t0 = D.blob("tl", rect(sd * 0.7 - 0.07, 0.78, sd * 0.7 + 0.07, 1.12, 0.02), "rear", M["tail_dark"])
        t1 = D.band("tl", [(sd * 0.7, 0.81), (sd * 0.7, 1.09)], 0.03, "rear", M["tail_led"], off=0.008, n=12, skirt=0)
        t2 = D.blob("tl", rect(sd * 0.7 - 0.05, 0.84, sd * 0.7 + 0.05, 0.9, 0.01), "rear", M["reverse"], off=0.007, skirt=0)
        ob = join([t0, t1, t2], "taillight_" + sfx)
        D.parts[ob.name] = ob
        # exposed fender flares (black plastic) with an amber marker at the front
        for wx, a0, a1 in ((s.fw, -12, 195), (s.rw, -15, 192)):
            D.add("rocker_" + sfx, D.arch_flare(wx, sd, s.r + 0.08, s.r + 0.2, 0.8, 0.947, M["plastic"], a0=a0, a1=a1))
        D.add("rocker_" + sfx, D.box("marker", (D.X(s.fw) + (s.r + 0.12) * math.cos(math.radians(25)) - 0.02, sd * 0.93 - 0.02,
                                                 s.r + 0.01 + (s.r + 0.12) * math.sin(math.radians(25)) - 0.03),
                                     (D.X(s.fw) + (s.r + 0.12) * math.cos(math.radians(25)) + 0.04, sd * 0.93 + 0.02,
                                      s.r + 0.01 + (s.r + 0.12) * math.sin(math.radians(25)) + 0.03), M["amber"], bevel=0.008))
        # rock rail under the doors
        D.add("rocker_" + sfx, D.box("rail", (D.X(s.rw - s.r - 0.12), sd * 0.8 - 0.06, 0.4), (D.X(s.fw + s.r + 0.12), sd * 0.8 + 0.06, 0.5),
                                     M["plastic"], bevel=0.02))
        # exposed door hinges
        for xh in (1.6, 2.68):
            for zh in (0.72, 1.05):
                D.add("pillars", D.box("hinge", (D.X(xh) - 0.02, sd * (s.hw(xh) - 0.01) - 0.015, zh - 0.04),
                                       (D.X(xh) + 0.05, sd * (s.hw(xh) - 0.01) + 0.015, zh + 0.04), M["black"], bevel=0.006))
    # steel bumpers
    D.add("underbody", D.box("bumper_f", (D.X(0.06), -0.9, 0.47), (D.X(-0.14), 0.9, 0.71), M["plastic"], bevel=0.025))
    D.add("underbody", D.box("bumper_r", (D.X(4.62), -0.88, 0.5), (D.X(4.44), 0.88, 0.72), M["plastic"], bevel=0.025))
    # hood vents
    for sd in (1, -1):
        D.add("underbody", D.blob("vent", rounded_poly([(0.25, sd * 0.42), (0.55, sd * 0.44), (0.55, sd * 0.6), (0.25, sd * 0.58)], 0.02),
                                  "top", M["grille_mesh"], off=0.004))
    D.spare(4.5, 1.06)
    D.plate("plate_r", "rear", 0.55, 0.62, w=0.3, h=0.15)
    D.mirrors(1.66, 1.12, size=(0.16, 0.12, 0.2), material=M["plastic"], out=0.15)
    D.handles(1.08, length=0.13, height=0.035, material=M["black"])


def feat_tahoe(D):
    M = D.mats
    for sd in (1, -1):
        sfx = "l" if sd > 0 else "r"
        upper = D.blob("hl", rounded_poly(sym(sd, [(0.6, 1.13), (0.95, 1.15), (0.97, 1.2), (0.62, 1.19)]), 0.02), "front", M["lamp_housing"])
        drl = D.band("hl", sym(sd, [(0.62, 1.165), (0.94, 1.175)]), 0.016, "front", M["drl"], off=0.008, n=12, skirt=0)
        main = D.blob("hl", rounded_poly(sym(sd, [(0.7, 0.93), (0.96, 0.93), (0.97, 1.08), (0.7, 1.08)]), 0.02), "front", M["lamp_housing"])
        lens = D.blob("hl", ellipse(sd * 0.83, 1.0, 0.06, 0.05, 20), "front", M["lamp_lens"], off=0.008, rings=2, skirt=0)
        vdrl = D.band("hl", sym(sd, [(0.95, 1.12), (0.955, 0.95)]), 0.014, "front", M["drl"], off=0.009, n=10, skirt=0)
        ob = join([upper, drl, main, lens, vdrl], "headlight_" + sfx)
        D.parts[ob.name] = ob
        t0 = D.blob("tl", rounded_poly(sym(sd, [(0.8, 1.0), (0.97, 0.99), (0.98, 1.36), (0.82, 1.36)]), 0.02), "rear", M["tail_red"])
        t1 = D.band("tl", sym(sd, [(0.85, 1.33), (0.85, 1.03), (0.95, 1.02)]), 0.022, "rear", M["tail_led"], off=0.008, n=16, skirt=0)
        ob = join([t0, t1], "taillight_" + sfx)
        D.parts[ob.name] = ob
        D.add("underbody", D.blob("fog", rounded_poly(sym(sd, [(0.66, 0.5), (0.9, 0.52), (0.9, 0.66), (0.68, 0.64)]), 0.03), "front", M["plastic"]))
    grid = D.blob("grille", rounded_poly([(-0.66, 0.68), (0.66, 0.68), (0.68, 1.12), (-0.68, 1.12)], 0.04), "front", M["grille_mesh"], n=60)
    bar = D.blob("grille", rounded_poly([(-0.7, 0.97), (0.7, 0.97), (0.7, 1.05), (-0.7, 1.05)], 0.03), "front", M["chrome"], off=0.012, n=60)
    surround = D.band("grille", rounded_poly([(-0.67, 0.675), (0.67, 0.675), (0.69, 1.125), (-0.69, 1.125)], 0.04), 0.02, "front",
                      M["chrome"], closed=True, n=60, off=0.008)
    D.parts["grille"] = join([grid, bar, surround], "grille")
    D.add("underbody", D.blob("skid", rounded_poly([(-0.6, 0.36), (0.6, 0.36), (0.55, 0.48), (-0.55, 0.48)], 0.03), "front", M["satin"]))
    D.add("underbody", D.blob("lowr", rounded_poly([(-0.95, 0.5), (0.95, 0.5), (0.95, 0.62), (-0.95, 0.62)], 0.03), "rear", M["plastic"]))
    D.add("underbody", D.blob("tbar", rounded_poly([(-0.55, 1.1), (0.55, 1.1), (0.55, 1.15), (-0.55, 1.15)], 0.02), "rear", M["chrome"], off=0.007))
    s = D.s
    for sd in (1, -1):
        sfx = "l" if sd > 0 else "r"
        D.add("rocker_" + sfx, D.box("step", (D.X(s.rw - s.r - 0.08), sd * (s.W / 2 - 0.2) - 0.1, 0.32),
                                     (D.X(s.fw + s.r + 0.08), sd * (s.W / 2 - 0.2) + 0.1, 0.37), M["plastic"], bevel=0.015))
    for ob in D.roof_rails(2.3, 5.05, 0.07, 0.07, M["plastic"]):
        D.add("pillars", ob)
    D.plate("plate_r", "rear", 0.0, 0.92)
    D.mirrors(1.95, 1.36, size=(0.26, 0.13, 0.2))
    D.handles(1.3, length=0.24, material=M["chrome"])


FEATURES = {"Toyoda Camri": feat_camry, "Dodgy Charjer": feat_charger, "Teslo Model 3": feat_tesla,
            "Subaro Outbuck": feat_outback, "Jeap Wrangle": feat_wrangler, "Chevro Tahoma": feat_tahoe}


# ------------------------------------------------------------------ v2 sprites (same camera and light as car_sprites_real.py)

def v2_render(name, out, mode):
    """mode 'sprites': <slug>_paint/_detail (side) and <slug>_q_paint/_q_detail (three-quarter) like the realistic cars;
    mode 'test': full-colour previews <slug>_v2_side.png / <slug>_v2_q.png."""
    sys.dont_write_bytecode = True
    sys.path.insert(0, HERE)
    import car_sprites_real as R
    cam, ground = R.setup()
    studio_objs = set(bpy.context.scene.objects)   # ground, reflector cards, reflection floor
    mats = materials()
    car = build_car2(name, mats)
    s = car["shape"]
    sc = bpy.context.scene
    meshes = [o for o in sc.objects if o.type == "MESH" and o not in studio_objs]
    paint = [o for o in meshes if is_paint(o)]
    sl = slug(name)
    dims = (s.L, s.W, s.H)
    if mode == "test":
        sc.cycles.samples = int(os.environ.get("SAMPLES", 24))
        col = R.simple_mat("paint_test", (0.08, 0.2, 0.45), rough=0.22, metal=0.45, coat=0.6)
        for o in paint:
            for i in range(len(o.material_slots)):
                o.material_slots[i].link = "OBJECT"
                o.material_slots[i].material = col
        R.side_cam(cam)
        R.render(os.path.join(out, sl + "_v2_side.png"), (1200, 480))
        R.quarter_cam(cam, dims)
        R.render(os.path.join(out, sl + "_v2_q.png"), (1280, 720))
        # rear three-quarter from the other side
        cam.location = Vector((-cam.location.x, -cam.location.y, cam.location.z))
        cam.rotation_euler = (Vector((0, 0, s.H * 0.42)) - cam.location).to_track_quat("-Z", "Y").to_euler()
        R.render(os.path.join(out, sl + "_v2_rear.png"), (1280, 720))
        return
    grey = R.paint_material()
    for o in paint:
        for i in range(len(o.material_slots)):
            o.material_slots[i].link = "OBJECT"
            o.material_slots[i].material = grey

    def set_mode(layer):
        for o in meshes:
            o.is_holdout = (o not in paint) if layer == "paint" else (o in paint)

    # same studio, 2x supersampling and sizes as the realistic cars
    R.render_layers(out, sl, cam, ground, dims, set_mode)


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
    by_slug = {slug(n): n for n in MODELS}
    names = [by_slug.get(n, n) for n in sys.argv[3:]] or list(MODELS)
    os.makedirs(out, exist_ok=True)
    for name in names:
        if name in V2 and cmd in ("test", "sprites"):
            v2_render(name, out, cmd)
            continue
        reset()
        mats = materials()
        car = build_car2(name, mats) if name in V2 else build_car(name, mats)
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
