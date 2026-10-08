"""Turns the realistic third-party car models into Chief Auto's own parody designs.

Runs right after car_sprites_real.load_car() in both tools/car_sprites_real.py (sprites) and tools/car_glb_real.py
(garage models), so the two always match. Everything is driven by the per-car RECIPES table below:

  drop_obj / drop_mat     objects (by name) or materials removed outright (badges, wings, spare wheels ...)
  scrub                   boxes [x0, x1, y0, y1, z0, z1] (metres, car axes, before reshaping) where every face that is not
                          body paint gets deleted ("delete"), painted body colour ("paint") or turned plain black ("black").
                          This is how logos baked into textures and badges modelled as geometry go away.
  swap                    {material regex: our material} for lamp lenses, plates, logo textures ...
  wheels                  every original wheel is cut out and replaced with our own procedural one (car3d.wheel2):
                          rim size in inches, spoke style, colours; the tyre keeps the measured size
  shape                   subtle global reshaping: nose / tail overhang stretch, greenhouse height, body width, roof rake
  grille                  a new grille insert (outline, pattern, frame, bars) projected onto the nose; the old grille
                          behind the outline is cut away first
  decals                  thin shells projected onto the body from the front, rear, side or top: light bars, DRLs,
                          blacked-out lamp panels, vents, emblems, stripes; a height turns them into raised parts
                          (scoops, lips, ducktails) with walls down to the body
  wings                   rear wings on stands

Axes and units are the ones load_car() leaves: metres, +X is the front, +Y the car's left, Z up, wheels on z=0.
Front / rear decals use (u, v) = (y, z); side decals (x, z) on the left side (sym mirrors them to the right);
top decals (x, y).

Our own materials are all named rs_*: rs_lamp_* count as lamps and rs_rubber as the tyres in car_glb_real.py.
"""
import math
import os
import re
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy  # noqa: E402,I001
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

DEBUG = bool(os.environ.get("DEBUG"))


# ------------------------------------------------------------------ our materials

MATS = {
    # name: (base colour, roughness, metallic, coat, emission colour, emission strength)
    "black": ((0.012, 0.012, 0.013), 0.35, 0.3, 0.6, None, 0),
    "gloss_black": ((0.004, 0.004, 0.005), 0.08, 0.5, 1.0, None, 0),
    "satin_black": ((0.02, 0.02, 0.022), 0.45, 0.4, 0.0, None, 0),
    "chrome": ((0.86, 0.87, 0.89), 0.05, 1.0, 0.0, None, 0),
    "satin": ((0.42, 0.43, 0.45), 0.28, 1.0, 0.0, None, 0),
    "bronze": ((0.45, 0.3, 0.14), 0.25, 1.0, 0.0, None, 0),
    "gold": ((0.75, 0.55, 0.22), 0.2, 1.0, 0.0, None, 0),
    "carbon": ((0.03, 0.03, 0.034), 0.25, 0.6, 1.0, None, 0),
    "plate": ((0.85, 0.85, 0.83), 0.6, 0.0, 0.0, None, 0),
    "khaki": ((0.18, 0.17, 0.12), 0.6, 0.0, 0.0, None, 0),
    # lamps (rs_lamp_* are treated as head / tail lights by car_glb_real.py)
    "lamp_drl": ((1.0, 1.0, 1.0), 0.2, 0.0, 0.0, (0.85, 0.93, 1.0), 6.0),
    "lamp_warm": ((1.0, 0.95, 0.85), 0.2, 0.0, 0.0, (1.0, 0.9, 0.7), 4.0),
    "lamp_ice": ((0.75, 0.9, 1.0), 0.2, 0.0, 0.0, (0.45, 0.75, 1.0), 5.0),
    "lamp_amber": ((1.0, 0.45, 0.03), 0.15, 0.0, 0.5, (1.0, 0.42, 0.0), 2.5),
    "lamp_tail": ((0.6, 0.01, 0.01), 0.1, 0.0, 1.0, (1.0, 0.03, 0.02), 5.0),
    "lamp_tail_dim": ((0.35, 0.01, 0.01), 0.08, 0.0, 1.0, (1.0, 0.02, 0.01), 0.8),
    "lamp_smoke": ((0.025, 0.026, 0.03), 0.04, 0.6, 1.0, None, 0),
    "lamp_smoke_red": ((0.09, 0.005, 0.005), 0.05, 0.3, 1.0, None, 0),
    "lamp_clear": ((0.75, 0.77, 0.8), 0.05, 0.9, 1.0, None, 0),
    "lamp_blue": ((0.05, 0.1, 0.2), 0.05, 0.7, 1.0, None, 0),
    "rubber": ((0.018, 0.018, 0.019), 0.85, 0.0, 0.0, None, 0),
}


def material(name, car=None):
    """Our material by short name (rs_<name>); 'paint' is the car's own paint material."""
    if name == "paint":
        return car.paint_mat
    full = "rs_" + name
    m = bpy.data.materials.get(full)
    if m:
        return m
    if name.startswith("grille_"):
        return grille_material(full, name[7:])
    col, rough, metal, coat, emit, strength = MATS[name]
    m = bpy.data.materials.new(full)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Coat Roughness"].default_value = 0.03
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = strength
    if name == "rubber":
        # matt tyre rubber: no grey sheen on the sidewalls
        b.inputs["Specular IOR Level"].default_value = 0.2
    return m


def pattern_image(kind, n=128):
    """Grille pattern as a tiling image: dark openings, lighter frame (one tile = one UV unit)."""
    y, x = np.mgrid[0:n, 0:n] / n
    if kind == "hex":
        # honeycomb from the distance to the nearest hex-lattice centre
        s = 2.0
        px, py = x * s, y * s * 2 / math.sqrt(3)
        pts = []
        for i in range(-1, 4):
            for j in range(-1, 5):
                pts.append((i + (0.5 if j % 2 else 0.0), j * math.sqrt(3) / 2 * 2 / math.sqrt(3)))
        d = np.full(x.shape, 9.0)
        d2 = np.full(x.shape, 9.0)
        for cx, cy in pts:
            dd = np.hypot(px - cx, (py - cy) * math.sqrt(3) / 2)
            d2 = np.minimum(np.maximum(d, dd), d2)
            d = np.minimum(d, dd)
        edge = (d2 - d) < 0.09
    elif kind == "mesh":
        a = (x + y) % 0.25
        b = (x - y) % 0.25
        edge = (a < 0.035) | (b < 0.035)
    elif kind == "slats":
        edge = (y % 0.25) < 0.08
    elif kind == "vslats":
        edge = (x % 0.125) < 0.04
    elif kind == "squares":
        edge = ((x % 0.25) < 0.05) | ((y % 0.25) < 0.05)
    elif kind == "dots":
        edge = np.hypot((x % 0.25) - 0.125, (y % 0.25) - 0.125) > 0.08
    elif kind == "chevron":
        edge = ((y + np.abs((x % 0.5) - 0.25)) % 0.25) < 0.07
    else:
        edge = np.zeros(x.shape, bool)
    col = np.where(edge[..., None], np.array([0.11, 0.115, 0.125]), np.array([0.008, 0.008, 0.009]))
    img = np.concatenate([col, np.ones(x.shape + (1,))], axis=2)
    im = bpy.data.images.new("rs_pattern_" + kind, n, n, alpha=False)
    im.pixels.foreach_set(img.astype(np.float32).ravel())
    im.pack()
    return im


def grille_material(full, kind):
    m = bpy.data.materials.new(full)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = pattern_image(kind)
    tex.interpolation = "Linear"
    nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.32
    b.inputs["Metallic"].default_value = 0.55
    return m


# ------------------------------------------------------------------ shapes (2D outlines in view coordinates)

def rrect(u0, v0, u1, v1, r=0.02, seg=4):
    r = min(r, abs(u1 - u0) / 2 - 1e-4, abs(v1 - v0) / 2 - 1e-4)
    pts = []
    for cu, cv, a0 in ((u1 - r, v1 - r, 0), (u0 + r, v1 - r, 90), (u0 + r, v0 + r, 180), (u1 - r, v0 + r, 270)):
        for k in range(seg + 1):
            a = math.radians(a0 + 90 * k / seg)
            pts.append((cu + r * math.cos(a), cv + r * math.sin(a)))
    return pts


def poly(pts, r=0.0):
    """Polygon with optionally rounded corners."""
    if r <= 0:
        return [tuple(p) for p in pts]
    out = []
    n = len(pts)
    for i in range(n):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % n])
        a = (p0 - p1)
        b = (p2 - p1)
        rr = min(r, a.length / 2.2, b.length / 2.2)
        s, e = p1 + a.normalized() * rr, p1 + b.normalized() * rr
        for k in range(5):
            t = k / 4
            q = (1 - t) ** 2 * s + 2 * (1 - t) * t * p1 + t ** 2 * e
            out.append((q.x, q.y))
    return out


def ellipse(cu, cv, ru, rv, n=28):
    return [(cu + ru * math.cos(2 * math.pi * i / n), cv + rv * math.sin(2 * math.pi * i / n)) for i in range(n)]


def hexagon(cu, v0, v1, w_top, w_mid, w_bot, mid=0.5):
    vm = v0 + (v1 - v0) * mid
    return [(cu - w_bot / 2, v0), (cu + w_bot / 2, v0), (cu + w_mid / 2, vm), (cu + w_top / 2, v1),
            (cu - w_top / 2, v1), (cu - w_mid / 2, vm)]


def shape(spec):
    """Outline from a recipe entry: ('rrect', u0, v0, u1, v1, r) | ('poly', pts, r) | ('ellipse', cu, cv, ru, rv)
    | ('hex', cu, v0, v1, w_top, w_mid, w_bot)."""
    k = spec[0]
    if k == "rrect":
        return rrect(*spec[1:])
    if k == "poly":
        return poly(*spec[1:])
    if k == "ellipse":
        return ellipse(*spec[1:])
    if k == "hex":
        return poly(hexagon(*spec[1:7]), spec[7] if len(spec) > 7 else 0.0)
    raise ValueError(k)


def inside(pts, u, v):
    """Point-in-polygon for arrays of points."""
    p = np.asarray(pts)
    res = np.zeros(np.shape(u), bool)
    j = len(p) - 1
    for i in range(len(p)):
        ui, vi = p[i]
        uj, vj = p[j]
        c = ((vi > v) != (vj > v)) & (u < (uj - ui) * (v - vi) / ((vj - vi) + 1e-12) + ui)
        res ^= c
        j = i
    return res


def resample(pts, step, closed=True):
    p = [Vector(q) for q in pts]
    if closed:
        p = p + [p[0]]
    out = []
    for a, b in zip(p[:-1], p[1:]):
        n = max(1, int((b - a).length / step))
        for k in range(n):
            q = a.lerp(b, k / n)
            out.append((q.x, q.y))
    if not closed:
        out.append(tuple(p[-1]))
    return out


# ------------------------------------------------------------------ the car being restyled

class Car:
    def __init__(self, ob, cfg, recipe):
        self.ob = ob
        self.cfg = cfg
        self.recipe = recipe
        me = ob.data
        names = [m.name if m else "" for m in me.materials]
        pre = re.compile(cfg["paint"])
        bre = re.compile(cfg["badge"]) if cfg.get("badge") else None
        self.paint_idx = {i for i, n in enumerate(names) if pre.search(n) or (bre and bre.search(n))}
        self.paint_mat = next((me.materials[i] for i in sorted(self.paint_idx) if pre.search(names[i])), None)
        glass = recipe.get("glass", r"(?i)glass|window|windshield|vitre")
        self.glass_idx = {i for i, n in enumerate(names) if re.search(glass, n)}
        self.new_objects = []
        self.cast_extra = []
        self.wheels = []
        self.xf = None

    # -- mesh arrays
    def arrays(self):
        me = self.ob.data
        n = len(me.polygons)
        c = np.empty(n * 3, np.float32)
        me.polygons.foreach_get("center", c)
        mi = np.empty(n, np.int32)
        me.polygons.foreach_get("material_index", mi)
        return c.reshape(-1, 3), mi

    def verts(self):
        me = self.ob.data
        v = np.empty(len(me.vertices) * 3, np.float64)
        me.vertices.foreach_get("co", v)
        return v.reshape(-1, 3)

    def face_verts(self):
        me = self.ob.data
        n = len(me.polygons)
        ls = np.empty(n, np.int32)
        lt = np.empty(n, np.int32)
        me.polygons.foreach_get("loop_start", ls)
        me.polygons.foreach_get("loop_total", lt)
        lv = np.empty(len(me.loops), np.int32)
        me.loops.foreach_get("vertex_index", lv)
        return ls, lt, lv

    def mat_index(self, m):
        mats = self.ob.data.materials
        for i, x in enumerate(mats):
            if x == m:
                return i
        mats.append(m)
        return len(mats) - 1

    def set_face_material(self, mask, m):
        if not mask.any():
            return
        me = self.ob.data
        k = self.mat_index(m)
        mi = np.empty(len(me.polygons), np.int32)
        me.polygons.foreach_get("material_index", mi)
        mi[mask] = k
        me.polygons.foreach_set("material_index", mi)
        me.update()

    def delete_faces(self, mask):
        if not mask.any():
            return
        bm = bmesh.new()
        bm.from_mesh(self.ob.data)
        bm.faces.ensure_lookup_table()
        idx = np.flatnonzero(mask)
        bmesh.ops.delete(bm, geom=[bm.faces[int(i)] for i in idx], context="FACES_ONLY")
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
        bm.to_mesh(self.ob.data)
        bm.free()
        self.ob.data.update()

    # -- ray casting onto the body
    def cast(self, origin, d, skip=(), maxd=12.0):
        """First hit along d from origin on the body (ignoring faces whose material index is in skip) or on one of
        our parts that decals may sit on (grille panels). (point, normal, material index or -1)."""
        o0 = Vector(origin)
        o = o0
        best = None
        for _ in range(8):
            ok, loc, nrm, idx = self.ob.ray_cast(o, d, distance=maxd)
            if not ok:
                break
            mi = self.ob.data.polygons[idx].material_index
            if mi not in skip:
                best = (loc, nrm, mi)
                break
            o = loc + d * 1e-4
        for ob in self.cast_extra:
            ok, loc, nrm, idx = ob.ray_cast(o0, d, distance=maxd)
            if ok and (best is None or (loc - o0).length < (best[0] - o0).length):
                best = (loc, nrm, -1)
        return best

    def view(self, view):
        """(ray origin from (u, v), ray direction, 3D point from (u, v, depth))."""
        lo, hi = self.bbox()
        if view == "front":
            return (lambda u, v: Vector((hi.x + 1, u, v))), Vector((-1, 0, 0))
        if view == "rear":
            return (lambda u, v: Vector((lo.x - 1, u, v))), Vector((1, 0, 0))
        if view == "side":
            return (lambda u, v: Vector((u, hi.y + 1, v))), Vector((0, -1, 0))
        if view == "side_r":
            return (lambda u, v: Vector((u, lo.y - 1, v))), Vector((0, 1, 0))
        if view == "top":
            return (lambda u, v: Vector((u, v, hi.z + 1))), Vector((0, 0, -1))
        raise ValueError(view)

    def bbox(self):
        v = self.verts()
        return Vector(v.min(0)), Vector(v.max(0))

    def add_object(self, name, verts, faces, m, uvs=None, smooth=True):
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
        if uvs is not None:
            uvl = me.uv_layers.new(name="UVMap")
            lv = np.empty(len(me.loops), np.int32)
            me.loops.foreach_get("vertex_index", lv)
            uv = np.asarray(uvs, np.float32)[lv]
            uvl.data.foreach_set("uv", uv.ravel())
        me.materials.append(m)
        me.polygons.foreach_set("use_smooth", np.full(len(me.polygons), smooth))
        me.validate()
        me.update()
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        self.new_objects.append(ob)
        return ob


# ------------------------------------------------------------------ steps

def join(meshes):
    """All meshes into one object (single-user data, no shape keys or modifiers, one UV map named UVMap)."""
    for o in meshes:
        if o.data.users > 1:
            o.data = o.data.copy()
        if o.data.shape_keys:
            o.shape_key_clear()
        for md in list(o.modifiers):
            o.modifiers.remove(md)
        uvs = o.data.uv_layers
        while len(uvs) > 1:
            uvs.remove(uvs[-1])
        if len(uvs):
            uvs[0].name = "UVMap"
        for sl in o.material_slots:
            if sl.link == "OBJECT":
                m = sl.material
                sl.link = "DATA"
                sl.material = m
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.name = "car_body"
    return ob


def drop_objects(meshes, rx):
    keep = []
    for o in meshes:
        if re.search(rx, o.name):
            bpy.data.objects.remove(o, do_unlink=True)
        else:
            keep.append(o)
    return keep


def measure_wheels(car, tyre_rx):
    me = car.ob.data
    names = [m.name if m else "" for m in me.materials]
    tyre = np.array([bool(re.search(tyre_rx, n)) for n in names] + [False])
    c, mi = car.arrays()
    is_t = tyre[np.minimum(mi, len(names))] & (c[:, 2] < 1.3)
    comp = components(car)
    out = []
    for xs in (1, -1):
        for ys in (1, -1):
            q = is_t & (c[:, 0] * xs > 0.3) & (c[:, 1] * ys > 0.2)
            if q.sum() < 20:
                raise RuntimeError("no tyre faces for wheel %d %d" % (xs, ys))
            # the tyre is the biggest connected piece of tyre material in this corner (by extent, then faces)
            ids, cnt = np.unique(comp[q], return_counts=True)
            best, best_k = None, -1
            for cid, n in zip(ids, cnt):
                pp = c[q & (comp == cid)]
                k = np.ptp(pp[:, 0]) * np.ptp(pp[:, 2]) * 1000 + n * 1e-6
                if k > best_k:
                    best, best_k = cid, k
            sel = q & (comp == best)
            if sel.sum() < 8:
                # unwelded mesh (every face its own piece): the corner's tyre faces are the tyre
                sel = q
            # the other pieces of the same tyre (sidewalls, tread split at seams): tyre pieces in this corner whose
            # centre lies inside the best piece's side-on box and within a tyre width of it
            pb = c[sel]
            lo, hi = pb.min(0) - 0.03, pb.max(0) + 0.03
            ymid = pb[:, 1].mean()
            for cid in ids:
                pm = c[q & (comp == cid)].mean(0)
                if lo[0] <= pm[0] <= hi[0] and lo[2] <= pm[2] <= hi[2] and abs(pm[1] - ymid) < 0.4:
                    sel |= q & (comp == cid)
            p = c[sel]
            x0, x1 = np.percentile(p[:, 0], [0.5, 99.5])
            z0, z1 = np.percentile(p[:, 2], [0.2, 99.8])
            y0, y1 = np.percentile(p[:, 1], [3, 97])
            r = max((x1 - x0) / 2, (z1 - z0) / 2)
            w = dict(x=(x0 + x1) / 2, y=(y0 + y1) / 2, z=r, r=r, hw=(y1 - y0) / 2, side=ys, front=xs > 0)
            if w["hw"] < 0.25 * r:
                # only the outer sidewall carries the tyre material: the tyre reaches inwards from it
                w["y"] = y1 - 0.25 * r if ys > 0 else y0 + 0.25 * r
                w["hw"] = 0.25 * r
            out.append(w)
            if DEBUG:
                print("  wheel %+d%+d centre (%.3f %.3f %.3f) r=%.3f w=%.3f" % (xs, ys, w["x"], w["y"], w["z"], r, 2 * w["hw"]))
    # a car stands on its tyres: same radius per axle, centres at the radius
    for front in (True, False):
        ax = [w for w in out if w["front"] == front]
        r = sum(w["r"] for w in ax) / 2
        for w in ax:
            w["r"] = r
            w["z"] = r
    return out


def cut_wheels(car, wheels, extra=0.0):
    """Deletes the original wheels: everything inside each tyre's cylinder (paint only well inside the rim)."""
    c, mi = car.arrays()
    V = car.verts()
    ls, lt, lv = car.face_verts()
    is_paint = np.isin(mi, list(car.paint_idx))
    dele = np.zeros(len(c), bool)
    for w in wheels:
        d = V - np.array([w["x"], w["y"], w["z"]])
        rad = np.hypot(d[:, 0], d[:, 2])
        out = d[:, 1] * w["side"]
        inn = (out <= w["hw"] + 0.05) & (out >= -w["hw"] - 0.3 - extra)

        def face_all(vm):
            return np.logical_and.reduceat(vm[lv], ls)
        dele |= face_all(inn & (rad <= w["r"] * 1.03)) & ~is_paint
        dele |= face_all(inn & (rad <= w["r"] * 0.9)) & is_paint
    car.delete_faces(dele)


def components(car):
    """Connected-component label per face (faces sharing a vertex are connected)."""
    ls, lt, lv = car.face_verts()
    nv = len(car.ob.data.vertices)
    face_of_loop = np.repeat(np.arange(len(ls)), lt)
    a = lv
    b = lv[ls][face_of_loop]
    lab = np.arange(nv)
    while True:
        m = np.minimum(lab[a], lab[b])
        new = lab.copy()
        np.minimum.at(new, a, m)
        np.minimum.at(new, b, m)
        new = new[new]
        new = new[new]
        if np.array_equal(new, lab):
            break
        lab = new
    return lab[lv[ls]]


def parts_in_boxes(car, boxes):
    """Faces of every loose part that lies entirely inside one of the boxes (any material)."""
    comp = components(car)
    V = car.verts()
    ls, lt, lv = car.face_verts()
    fc = np.repeat(comp, lt)
    n = comp.max() + 1
    lo = np.full((n, 3), 1e9)
    hi = np.full((n, 3), -1e9)
    for k in range(3):
        np.minimum.at(lo[:, k], fc, V[lv, k])
        np.maximum.at(hi[:, k], fc, V[lv, k])
    hit = np.zeros(n, bool)
    for b in list(boxes) + [[b[0], b[1], -b[3], -b[2], b[4], b[5]] for b in boxes if len(b) > 7 and b[7]]:
        x0, x1, y0, y1, z0, z1 = b[:6]
        hit |= (lo[:, 0] >= x0) & (hi[:, 0] <= x1) & (lo[:, 1] >= y0) & (hi[:, 1] <= y1) & (lo[:, 2] >= z0) & (hi[:, 2] <= z1)
    return hit[comp]


def scrub(car, boxes):
    """Boxes [x0, x1, y0, y1, z0, z1, mode, (sym)]: non-paint faces with centres inside get deleted / painted / blacked."""
    c, mi = car.arrays()
    is_paint = np.isin(mi, list(car.paint_idx))
    dele = np.zeros(len(c), bool)
    pb = [b for b in boxes if len(b) > 6 and b[6] == "parts"]
    if pb:
        dele |= parts_in_boxes(car, pb)
    for b in boxes:
        if len(b) > 6 and b[6] == "parts":
            continue
        x0, x1, y0, y1, z0, z1 = b[:6]
        mode = b[6] if len(b) > 6 else "delete"
        sym = b[7] if len(b) > 7 else False
        m = (c[:, 0] >= x0) & (c[:, 0] <= x1) & (c[:, 2] >= z0) & (c[:, 2] <= z1)
        my = (c[:, 1] >= y0) & (c[:, 1] <= y1)
        if sym:
            my |= (-c[:, 1] >= y0) & (-c[:, 1] <= y1)
        m &= my
        if mode == "delete_all":
            dele |= m
            continue
        if mode.startswith("all:"):
            # recolour everything in the box, paint included (lettering modelled in body paint)
            car.set_face_material(m, material(mode[4:], car))
            continue
        m &= ~is_paint
        m &= ~np.isin(mi, list(car.glass_idx))
        if mode == "delete":
            dele |= m
        else:
            car.set_face_material(m, material(mode, car))
    car.delete_faces(dele)


def swap(car, table):
    me = car.ob.data
    for rx, name in table.items():
        for i, m in enumerate(me.materials):
            if m and re.search(rx, m.name) and not m.name.startswith("rs_"):
                me.materials[i] = material(name, car)
                if name == "paint":
                    car.paint_idx.add(i)


def drop_materials(car, rx):
    me = car.ob.data
    names = [m.name if m else "" for m in me.materials]
    bad = [i for i, n in enumerate(names) if re.search(rx, n)]
    c, mi = car.arrays()
    car.delete_faces(np.isin(mi, bad))


# ---- reshaping

def softramp(t, w):
    t = np.asarray(t, np.float64)
    return np.where(t <= 0, 0.0, np.where(t < w, t * t / (2 * w), t - w / 2))


def smoothstep(a, b, x):
    t = np.clip((np.asarray(x) - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def make_deform(sh, wheels, H):
    """Point transform for the shape recipe (numpy (n,3) -> (n,3))."""
    fx = max(w["x"] + w["r"] * 1.05 for w in wheels if w["front"])
    rx = min(w["x"] - w["r"] * 1.05 for w in wheels if not w["front"])
    belt = sh.get("belt", 0.55) * H

    def f(p):
        p = np.array(p, np.float64, copy=True).reshape(-1, 3)
        x, y, z = p[:, 0].copy(), p[:, 1].copy(), p[:, 2].copy()
        p[:, 0] = x + sh.get("nose", 0) * softramp(x - fx, 0.25) - sh.get("tail", 0) * softramp(rx - x, 0.25)
        p[:, 1] = y * (1 + sh.get("width", 0))
        zz = z + sh.get("roof", 0) * softramp(z - belt, 0.12)
        # rake tilts the upper body (positive drops the front of the roof line); hood raises the bonnet
        zz += sh.get("rake", 0) * x * smoothstep(belt - 0.2, belt + 0.25, z)
        if sh.get("hood"):
            zz += sh["hood"] * smoothstep(fx - 0.6, fx + 0.1, x) * smoothstep(belt - 0.35, belt, z) * \
                (1 - smoothstep(belt + 0.05, belt + 0.3, z))
        p[:, 2] = zz
        return p
    return f


def reshape(car, sh, wheels, cfg):
    V = car.verts()
    H = V[:, 2].max()
    f = make_deform(sh, wheels, H)
    V2 = f(V)
    # back to the real length, centred, on the ground (the game lays the sprites out by size)
    lo, hi = V2.min(0), V2.max(0)
    s = cfg["length"] / (hi[0] - lo[0])
    cx = (lo[0] + hi[0]) / 2

    def xf(p):
        q = f(p)
        q[:, 0] -= cx
        return q * s
    car.ob.data.vertices.foreach_set("co", xf(V).astype(np.float32).ravel())
    car.ob.data.update()
    for w in wheels:
        q = xf([[w["x"], w["y"], w["z"]]])[0]
        w["x"], w["y"] = q[0], q[1]
        w["r"] *= s
        w["z"] = w["r"]
        w["hw"] *= s
    car.xf = xf
    car.scale = s


def to_view(car, view, u, v):
    """Maps recipe coordinates (measured on the original model) through the reshape."""
    if car.xf is None:
        return u, v
    lo, hi = car.bbox_orig
    if view in ("front", "rear"):
        x = hi.x - 0.05 if view == "front" else lo.x + 0.05
        q = car.xf([[x, u, v]])[0]
        return q[1], q[2]
    if view in ("side", "side_r"):
        q = car.xf([[u, 0.0, v]])[0]
        return q[0], q[2]
    q = car.xf([[u, v, hi.z * 0.6]])[0]
    return q[0], q[1]


# ---- projected shells

def project_grid(car, view, outline, res, skip):
    """Grid of ray hits covering outline: (U, V, hit points (nu, nv, 3) or nan, normals, ray dir)."""
    org, d = car.view(view)
    pts = np.asarray(outline)
    u0, v0 = pts.min(0) - res
    u1, v1 = pts.max(0) + res
    nu = max(2, int(math.ceil((u1 - u0) / res)) + 1)
    nv = max(2, int(math.ceil((v1 - v0) / res)) + 1)
    U, Vv = np.meshgrid(np.linspace(u0, u1, nu), np.linspace(v0, v1, nv), indexing="ij")
    P = np.full((nu, nv, 3), np.nan)
    for i in range(nu):
        for j in range(nv):
            h = car.cast(org(U[i, j], Vv[i, j]), d, skip)
            if h:
                P[i, j] = h[0]
    return U, Vv, P, d


def snap_outline(U, Vv, inside_mask, outline):
    """Moves grid vertices next to the outline onto it so the shell edge is smooth, not stair-stepped."""
    pts = np.asarray(resample(outline, 0.002))
    Uc, Vc = U.copy(), Vv.copy()
    nu, nv = U.shape
    # vertices used by an inside cell but lying outside the outline
    used = np.zeros((nu, nv), bool)
    used[:-1, :-1] |= inside_mask
    used[1:, :-1] |= inside_mask
    used[:-1, 1:] |= inside_mask
    used[1:, 1:] |= inside_mask
    vin = inside(outline, U, Vv)
    out = used & ~vin
    for i, j in zip(*np.nonzero(out)):
        k = np.argmin((pts[:, 0] - U[i, j]) ** 2 + (pts[:, 1] - Vv[i, j]) ** 2)
        Uc[i, j], Vc[i, j] = pts[k]
    return Uc, Vc, used


REACH = {"front": 0.3, "rear": 0.3, "side": 0.3, "side_r": 0.3, "top": 0.15}


def shell(car, view, outline, m, offset=0.004, res=0.012, skip=None, height=None, skirt=None, uv_scale=None,
          flat=None, name="rs_shell", reach="auto"):
    """A thin surface following the body under outline (view coordinates), offset outward along the view ray.
    height: extra offset as a function (u, v) -> metres (raised parts). skirt: material for walls down to the body.
    flat: (fit_ring, inset): replace the hit surface by a smooth fit through the hits on a ring just outside the
    outline (grilles: the old grille behind is gone, so the hits inside are meaningless)."""
    skip = () if skip is None else skip
    reach = REACH.get(view) if reach == "auto" else reach
    U, Vv, P, d = project_grid(car, view, outline, res, skip)
    nu, nv = U.shape
    cu = (U[:-1, :-1] + U[1:, 1:]) / 2
    cv = (Vv[:-1, :-1] + Vv[1:, 1:]) / 2
    # a cell is in when its centre or any corner is inside the outline
    cell_in = inside(outline, cu, cv)
    corner_in = inside(outline, U, Vv)
    cell_in |= corner_in[:-1, :-1] | corner_in[1:, :-1] | corner_in[:-1, 1:] | corner_in[1:, 1:]
    Uc, Vc, used = snap_outline(U, Vv, cell_in, outline)
    dvec = np.array(d)
    # depth along the ray at every grid vertex
    org, _ = car.view(view)
    O = np.array([[tuple(org(U[i, j], Vv[i, j])) for j in range(nv)] for i in range(nu)])
    depth = np.einsum("ijk,k->ij", P - O, dvec)
    if flat is not None:
        ring = resample(grow(outline, flat.get("ring", 0.03)), res)
        rr = []
        for (u, v) in ring:
            h = car.cast(org(u, v), d, skip)
            if h:
                rr.append((u, v, (Vector(h[0]) - org(u, v)).dot(d)))
        rr = np.array(rr)
        # depth ~ a + b u^2 + c v + e v^2 (+ f u for one-sided shapes)
        A = np.stack([np.ones(len(rr)), rr[:, 0] ** 2, rr[:, 1], rr[:, 1] ** 2, rr[:, 0]], 1)
        coef, *_ = np.linalg.lstsq(A, rr[:, 2], rcond=None)
        fit = coef[0] + coef[1] * Uc ** 2 + coef[2] * Vc + coef[3] * Vc ** 2 + coef[4] * Uc + flat.get("inset", 0.0)
        # never stand proud of the body around it
        fit = np.clip(fit, rr[:, 2].min() + flat.get("inset", 0.0), rr[:, 2].max() + 0.05)
        if flat.get("level"):
            # a flat face square to the view, level with the frontmost body around it
            fit = np.full_like(Uc, rr[:, 2].min() + flat.get("inset", 0.0))
        # never sink the panel behind body surface that comes forward inside the outline
        dd = np.where(np.isnan(depth), np.inf, depth)
        depth = np.minimum(fit, dd - 0.003) if flat.get("cover", True) else fit
    # recompute depth at snapped positions: interpolate by re-casting the moved vertices
    moved = (Uc != U) | (Vc != Vv)
    for i, j in zip(*np.nonzero(moved & used)):
        if flat is not None:
            continue
        h = car.cast(org(Uc[i, j], Vc[i, j]), d, skip)
        depth[i, j] = (Vector(h[0]) - org(Uc[i, j], Vc[i, j])).dot(d) if h else np.nan
    if reach is not None and flat is None:
        # drop hits far behind the nearest one (rays that slipped past the body's edge onto a side further away)
        dmin = np.nanmin(np.where(used, depth, np.nan)) if np.any(used & ~np.isnan(depth)) else 0
        depth = np.where(depth > dmin + reach, np.nan, depth)
    off = np.full((nu, nv), offset)
    if height is not None:
        off = off + np.vectorize(height)(Uc, Vc)
    verts = {}
    vlist = []
    uvs = []

    def vid(i, j, extra=0.0, key=0):
        k = (i, j, key)
        if k not in verts:
            p = np.array(tuple(org(Uc[i, j], Vc[i, j]))) + dvec * (depth[i, j] - off[i, j] - extra)
            verts[k] = len(vlist)
            vlist.append(p)
            uvs.append((Uc[i, j] * (uv_scale or 1), Vc[i, j] * (uv_scale or 1)))
        return verts[k]
    faces = []
    ok = ~np.isnan(depth)
    for i in range(nu - 1):
        for j in range(nv - 1):
            if not cell_in[i, j]:
                continue
            if not (ok[i, j] and ok[i + 1, j] and ok[i + 1, j + 1] and ok[i, j + 1]):
                continue
            f = [vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)]
            faces.append(f)
    if not faces:
        print("  shell %s: nothing hit" % name)
        return None
    # walls down to the surface along the shell's border (raised parts)
    if skirt is not None:
        from collections import Counter
        ec = Counter()
        for f in faces:
            for a, b in zip(f, f[1:] + f[:1]):
                ec[tuple(sorted((a, b)))] += 1
        border = [e for e, n in ec.items() if n == 1]
        keyof = {v: k for k, v in verts.items()}
        sk_faces = []
        sk_verts = []
        for a, b in border:
            ia, ib = keyof[a], keyof[b]
            pa = np.array(tuple(org(Uc[ia[0], ia[1]], Vc[ia[0], ia[1]]))) + dvec * (depth[ia[:2]] - 0.0005)
            pb = np.array(tuple(org(Uc[ib[0], ib[1]], Vc[ib[0], ib[1]]))) + dvec * (depth[ib[:2]] - 0.0005)
            n0 = len(vlist) + len(sk_verts)
            sk_verts += [vlist[a], vlist[b], pb, pa]
            sk_faces.append([n0, n0 + 1, n0 + 2, n0 + 3])
    ob = car.add_object(name, vlist, faces, m if not isinstance(m, str) else material(m, car),
                        uvs=uvs if uv_scale else None)
    if skirt is not None and sk_faces:
        car.add_object(name + "_wall", sk_verts, [[k - len(vlist) for k in f] for f in sk_faces],
                       material(skirt, car), smooth=False)
    return ob


def grow(outline, dist):
    """Offsets a closed outline outward by dist (simple vertex-normal offset)."""
    p = np.asarray(outline, np.float64)
    c = p.mean(0)
    out = []
    n = len(p)
    area = 0.5 * np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1])
    sgn = 1 if area > 0 else -1
    for i in range(n):
        a, b = p[i - 1], p[(i + 1) % n]
        t = b - a
        nrm = np.array([t[1], -t[0]]) * sgn
        ln = np.linalg.norm(nrm)
        nrm = nrm / ln if ln > 1e-9 else (p[i] - c) / max(1e-9, np.linalg.norm(p[i] - c))
        out.append(tuple(p[i] + nrm * dist))
    return out


def ribbon(car, view, path, width, m, offset=0.006, closed=False, step=0.008, skip=None, name="rs_ribbon",
           depth_fn=None, reach="auto"):
    """A strip of the given width along path (view coordinates), following the body."""
    skip = () if skip is None else skip
    org, d = car.view(view)
    pts = resample(path, step, closed)
    if closed:
        pts.append(pts[0])
    dvec = np.array(d)
    verts, faces = [], []
    prev = None
    reach = REACH.get(view) if reach == "auto" else reach
    dmin = None
    if reach is not None and depth_fn is None:
        ds = []
        for (u, v) in pts:
            h = car.cast(org(u, v), d, skip)
            if h:
                ds.append((Vector(h[0]) - org(u, v)).dot(d))
        dmin = min(ds) if ds else None
    for k, (u, v) in enumerate(pts):
        a = Vector(pts[max(0, k - 1)])
        b = Vector(pts[min(len(pts) - 1, k + 1)])
        t = (b - a)
        if t.length < 1e-9:
            continue
        t.normalize()
        n2 = Vector((-t.y, t.x)) * width / 2
        pair = []
        for s in (-1, 1):
            q = Vector((u, v)) + n2 * s
            if depth_fn is not None:
                dep = depth_fn(q.x, q.y)
                p = np.array(tuple(org(q.x, q.y))) + dvec * (dep - offset) if dep is not None else None
            else:
                h = car.cast(org(q.x, q.y), d, skip)
                if h and dmin is not None and (Vector(h[0]) - org(q.x, q.y)).dot(d) > dmin + reach:
                    h = None
                p = np.array(tuple(h[0])) - dvec * offset if h else None
            pair.append(p)
        if pair[0] is None or pair[1] is None:
            prev = None
            continue
        i0 = len(verts)
        verts += pair
        if prev is not None:
            faces.append([prev, prev + 1, i0 + 1, i0])
        prev = i0
    if not faces:
        print("  ribbon %s: nothing hit" % name)
        return None
    return car.add_object(name, verts, faces, m if not isinstance(m, str) else material(m, car))


# ---- recipe parts

def mirror_outline(view, outline):
    if view in ("front", "rear"):
        return [(-u, v) for u, v in outline]
    if view == "top":
        return [(u, -v) for u, v in outline]
    return outline


def mapped(car, view, pts):
    return [to_view(car, view, u, v) for u, v in pts]


def do_decal(car, dc):
    view = dc.get("view", "front")
    views = [(view, False)]
    if dc.get("sym"):
        views.append(("side_r", True) if view == "side" else (view, True))
    for vw, mir in views:
        out = shape(dc["shape"]) if "shape" in dc else None
        path = dc.get("path")
        if mir and vw != "side_r":
            out = mirror_outline(vw, out) if out else None
            path = mirror_outline(vw, path) if path else None
        if out:
            out = mapped(car, vw, out)
        if path:
            path = mapped(car, vw, path)
        name = "rs_" + dc.get("name", "decal")
        if path is not None:
            ribbon(car, vw, path, dc["width"], dc["mat"], offset=dc.get("offset", 0.006), closed=dc.get("closed", False),
                   name=name)
            continue
        h = dc.get("height")
        height = None
        if h:
            # raised part: height ramps up along u (or v) from 'from' to 'to'
            hu0, hu1 = dc.get("ramp", (None, None))
            axis = dc.get("ramp_axis", 0)

            def height(u, v, h=h, hu0=hu0, hu1=hu1, axis=axis):
                if hu0 is None:
                    return h
                t = ((u if axis == 0 else v) - hu0) / (hu1 - hu0)
                return h * float(np.clip(t, 0, 1)) ** dc.get("ramp_pow", 1.0)
        flat = dict(ring=dc.get("ring", 0.03), inset=0.0, cover=dc.get("cover", True),
                    level=dc.get("level", False)) if dc.get("flat") else None
        ob = shell(car, vw, out, dc["mat"], offset=dc.get("offset", 0.004), res=dc.get("res", 0.012), height=height,
                   skirt=dc.get("skirt"), uv_scale=dc.get("uv"), flat=flat, name=name, reach=dc.get("reach", "auto"))
        if ob is not None and dc.get("support"):
            # later decals (lamps on a panel) sit on this one
            car.cast_extra.append(ob)


def do_grille(car, g):
    _grille(car, g, False)
    if g.get("sym"):
        _grille(car, g, True)


def _grille(car, g, mirror):
    view = g.get("view", "front")
    out = shape(g["shape"])
    if mirror:
        out = mirror_outline(view, out)
    out = mapped(car, view, out)
    # cut away the old grille (anything that isn't paint or lamp) behind the outline
    c, mi = car.arrays()
    lo, hi = car.bbox()
    if view == "front":
        u, v, dep = c[:, 1], c[:, 2], hi.x - c[:, 0]
    else:
        u, v, dep = c[:, 1], c[:, 2], c[:, 0] - lo.x
    keep = set(car.paint_idx) | car.glass_idx
    lamp_rx = car.recipe.get("lamps")
    names = [m.name if m else "" for m in car.ob.data.materials]
    if lamp_rx and not g.get("cut_lamps"):
        keep |= {i for i, n in enumerate(names) if re.search(lamp_rx, n)}
    keep |= {i for i, n in enumerate(names) if n.startswith("rs_")}
    cut_shape = grow(out, -g.get("cut_in", 0.01))
    m = inside(cut_shape, u, v) & (dep < g.get("depth", 0.5)) & ~np.isin(mi, list(keep))
    if g.get("cut_paint"):
        cp = grow(out, -0.03)
        if isinstance(g["cut_paint"], tuple):
            # only the old grille's body-colour surround, well inside the new outline
            cp = mapped(car, view, mirror_outline(view, shape(g["cut_paint"])) if mirror else shape(g["cut_paint"]))
        m |= inside(cp, u, v) & (dep < g.get("depth", 0.5)) & np.isin(mi, list(car.paint_idx))
    car.delete_faces(m)
    pat = material("grille_" + g.get("pattern", "hex"))
    shell(car, view, out, pat, offset=g.get("offset", 0.0), res=g.get("res", 0.012), uv_scale=g.get("scale", 12),
          flat=dict(ring=g.get("ring", 0.035), inset=g.get("inset", 0.015), cover=g.get("cover", True)),
          name="rs_grille")
    grille_ob = car.new_objects[-1] if car.new_objects else None
    if grille_ob is not None:
        car.cast_extra.append(grille_ob)
    # frame and bars sit on the panel surface: cast against the new panel only
    if grille_ob is not None and (g.get("frame") or g.get("bars")):
        org, d = car.view(view)
        dvec = Vector(d)

        def depth_on_panel(uu, vv):
            o = org(uu, vv)
            ok, loc, nrm, idx = grille_ob.ray_cast(o, dvec, distance=20)
            if ok:
                return (loc - o).dot(dvec)
            h = car.cast(o, d)
            return (Vector(h[0]) - o).dot(dvec) if h else None
        if g.get("frame"):
            fw, fm = g["frame"]
            ribbon(car, view, out, fw, fm, offset=0.008, closed=True, name="rs_grille_frame", depth_fn=depth_on_panel)
        for b in g.get("bars", []):
            path, bw, bm_ = b
            if mirror:
                path = mirror_outline(view, path)
            ribbon(car, view, mapped(car, view, path), bw, bm_, offset=0.012, name="rs_grille_bar",
                   depth_fn=depth_on_panel)


def box_mesh(car, name, centre, size, m, rot=(0, 0, 0), bevel=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    if bevel:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=2, affect="EDGES")
    from mathutils import Euler
    R = Euler(rot).to_matrix()
    for v in bm.verts:
        v.co = R @ v.co + Vector(centre)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(m if not isinstance(m, str) else material(m, car))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    car.new_objects.append(ob)
    return ob


def do_wing(car, w):
    """Rear wing: blade at x (centre of chord), height above the deck, span, chord; two stands; end plates."""
    x, _ = to_view(car, "side", w["x"], 1.0)
    span = w["span"] * (1 + car.recipe.get("shape", {}).get("width", 0)) * car.scale
    org, d = car.view("top")
    deck = []
    for s in (-1, 1):
        h = car.cast(org(x, s * w.get("stand_y", span * 0.3)), d)
        deck.append(h[0].z if h else 1.0)
    zb = max(deck) + w["height"]
    m = w.get("mat", "gloss_black")
    pitch = math.radians(w.get("pitch", 6))
    box_mesh(car, "rs_wing", (x, 0, zb), (w["chord"], span, w.get("thick", 0.025)), m, rot=(0, pitch, 0), bevel=0.008)
    if w.get("plates", True):
        for s in (-1, 1):
            box_mesh(car, "rs_wing_plate", (x - 0.01, s * span / 2, zb - 0.02), (w["chord"] * 1.1, 0.008, w.get("plate_h", 0.08)), m,
                     bevel=0.003)
    for s, dz in zip((-1, 1), deck):
        ys = s * w.get("stand_y", span * 0.3)
        hgt = zb - dz + 0.02
        box_mesh(car, "rs_wing_stand", (x + 0.02, ys, dz + hgt / 2 - 0.01), (w["chord"] * 0.45, 0.014, hgt),
                 w.get("stand_mat", m), rot=(0, math.radians(w.get("stand_lean", -12)), 0), bevel=0.004)


def build_wheels(car, wheels, spec):
    import car3d
    mats = {
        "rubber": material("rubber"),
        "rim": rim_material(spec.get("color", (0.75, 0.76, 0.78)), spec.get("rough", 0.22), spec.get("metal", 1.0)),
        "rim_dark": material("satin_black"),
        "disc": disc_material(),
    }
    out = []
    for w in wheels:
        sp = dict(tyre_w=min(0.34, max(0.5 * w["r"], 2 * w["hw"] * 0.98)), rim=spec.get("inches", 18), rim_style=spec.get("style", "five"),
                  rim_concave=spec.get("concave", 0.035), caliper=spec.get("caliper"), tread=spec.get("tread"))
        # keep a sensible sidewall whatever rim size the recipe asks for
        max_in = (w["r"] - 0.055 - 0.012) * 2 / 0.0254
        sp["rim"] = min(sp["rim"], max_in)
        cd = {"shape": SimpleNamespace(r=w["r"]), "parts": {}}
        ob = car3d.wheel2(cd, mats, Vector((w["x"], w["y"], w["z"])), w["side"], sp)
        ob.name = "rs_wheel"
        out.append(ob)
    car.new_objects += out


def rim_material(col, rough, metal):
    name = "rs_rim_%02x%02x%02x" % tuple(int(c * 255) for c in col)
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    # a fully metallic rim mirrors the bright sky: keep its base a little below the paint swatch so it reads as
    # metal, not white plastic
    b.inputs["Base Color"].default_value = (*(c * 0.8 for c in col), 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = 0.4
    return m


def disc_material():
    m = bpy.data.materials.get("rs_disc")
    if m:
        return m
    m = bpy.data.materials.new("rs_disc")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.3, 0.3, 0.31, 1)
    b.inputs["Roughness"].default_value = 0.4
    b.inputs["Metallic"].default_value = 1.0
    return m


# ------------------------------------------------------------------ main entry

def restyle(meshes, slug, dims, cfg=None):
    """Applies RECIPES[slug] to the loaded model. Returns (meshes, dims): one joined body plus our new parts."""
    import car_sprites_real as R
    cfg = cfg or R.CARS[slug]
    rc = RECIPES.get(slug)
    if not rc:
        return meshes, dims
    if rc.get("drop_obj"):
        meshes = drop_objects(meshes, rc["drop_obj"])
    ob = join(meshes)
    car = Car(ob, cfg, rc)
    car.bbox_orig = car.bbox()
    if rc.get("drop_mat"):
        drop_materials(car, rc["drop_mat"])
    wheels = measure_wheels(car, rc["tyre"])
    cut_wheels(car, wheels, rc.get("wheel_cut_extra", 0.0))
    if rc.get("scrub"):
        scrub(car, rc["scrub"])
    if rc.get("swap"):
        swap(car, rc["swap"])
    reshape(car, rc.get("shape", {}), wheels, cfg)
    for g in rc.get("grilles", []):
        do_grille(car, g)
    for dc in rc.get("decals", []):
        do_decal(car, dc)
    for w in rc.get("wings", []):
        do_wing(car, w)
    build_wheels(car, wheels, rc.get("wheels", {}))
    objs = [car.ob] + [o for o in car.new_objects if o.name in bpy.data.objects]
    bpy.context.view_layer.update()
    from mathutils import Matrix
    for o in objs:
        if o.matrix_world != Matrix.Identity(4):
            o.data.transform(o.matrix_world)
            o.matrix_world = Matrix.Identity(4)
    lo = np.full(3, 1e9)
    hi = np.full(3, -1e9)
    for o in objs:
        v = np.empty(len(o.data.vertices) * 3)
        o.data.vertices.foreach_get("co", v)
        v = v.reshape(-1, 3)
        if len(v):
            lo = np.minimum(lo, v.min(0))
            hi = np.maximum(hi, v.max(0))
    # keep the overall length exact (added parts can poke out a little): uniform scale about the middle, on the ground
    k = cfg["length"] / (hi[0] - lo[0])
    cx = (lo[0] + hi[0]) / 2
    if abs(k - 1) > 0.001:
        for o in objs:
            v = np.empty(len(o.data.vertices) * 3)
            o.data.vertices.foreach_get("co", v)
            v = v.reshape(-1, 3)
            v[:, 0] -= cx
            o.data.vertices.foreach_set("co", (v * k).ravel())
            o.data.update()
        lo, hi = lo * k, hi * k
        lo[0], hi[0] = -cfg["length"] / 2, cfg["length"] / 2
    dims = Vector((hi[0] - lo[0], hi[1] - lo[1], hi[2]))
    if DEBUG:
        print("  restyled %s: %d objects, dims %.2f %.2f %.2f" % (slug, len(objs), *dims))
    return objs, dims


# ------------------------------------------------------------------ the recipes
# Coordinates are measured on the original models after load_car (metres): x forward from the car's middle,
# y to the left, z up from the ground. Front / rear decals and grilles take (y, z) outlines; side (x, z); top (x, y).

RECIPES = {
    # ---------------------------------------------------------------- Porsha 911: 930 Turbo -> our air-cooled coupe
    # whale tail out (a fitted engine lid instead) and a slim wing on stands; split LED bars across the round lamps;
    # a gloss-black tail panel with one thin light bar; cross-laced gold rims; longer nose, lower roof
    "porsha_911": dict(
        glass=r"^glass$",
        tyre=r"^930_tire$", lamps=r"930_lights",
        scrub=[
            [-2.15, -1.5, -0.8, 0.8, 0.78, 1.02, "parts"],        # whale tail rubber lip
            [-2.1, -1.5, -0.62, 0.62, 0.87, 1.0, "delete_all"],   # whale tail
            [1.9, 2.3, -0.12, 0.12, 0.5, 0.8, "paint"],           # bonnet crest
            [-2.12, -1.98, -0.45, 0.15, 0.63, 0.7, "parts"],      # "Turbo" script on the engine lid
        ],
        swap={r"^930_lights_refraction$": "lamp_smoke", r"^930_stickers$": "paint", r"^930_wunderbaum$": "black"},
        shape=dict(nose=0.07, roof=-0.035, width=0.025, rake=0.012),
        decals=[
            dict(name="lid", view="top", shape=("rrect", -2.08, -0.62, -1.5, 0.62, 0.08), mat="paint", flat=True,
                 cover=False, offset=0.0, ring=0.04, res=0.015),
            dict(name="drl", view="front", shape=("rrect", 0.5, 0.655, 0.74, 0.68, 0.012), mat="lamp_drl", sym=True,
                 offset=0.012, res=0.006),
            dict(name="tail_panel", view="rear", shape=("rrect", -0.8, 0.47, 0.8, 0.62, 0.02), mat="gloss_black",
                 offset=0.01, flat=True, support=True),
            dict(name="tail_bar", view="rear", shape=("rrect", -0.78, 0.565, 0.78, 0.59, 0.01), mat="lamp_tail",
                 offset=0.012, res=0.006),
            dict(name="tail_ends", view="rear", shape=("rrect", 0.6, 0.49, 0.77, 0.545, 0.012), mat="lamp_tail_dim",
                 offset=0.012, sym=True, res=0.006),
            dict(name="emblem", view="top", shape=("poly", [(2.08, 0), (2.02, 0.035), (1.96, 0), (2.02, -0.035)], 0.004),
                 mat="chrome", offset=0.004, res=0.005),
            dict(name="stripe", view="side", path=[(-1.2, 0.36), (1.45, 0.36)], width=0.035, mat="gloss_black",
                 sym=True),
        ],
        wings=[dict(x=-1.9, height=0.1, span=1.42, chord=0.24, mat="gloss_black", stand_y=0.42, plate_h=0.06)],
        wheels=dict(inches=17, style="mesh", color=(0.72, 0.6, 0.35), rough=0.3, caliper="#1565c0"),
    ),
    # ---------------------------------------------------------------- Forde Mustank: GT500 -> our muscle coupe
    # badges, wing and "SHELBY" lettering out; a split grille with a body-colour bar; tri-bar tails covered by one bar
    # and square end lamps; vents filled, bonnet stripes, a small boot lip; turbine rims
    "forde_mustank": dict(
        glass=r"^tinted_glass$",
        tyre=r"^tire$", lamps=r"^(light|rearlight|orange)$",
        drop_obj=r"Badge|Wing_",
        drop_mat=r"^white_gloss$",
        scrub=[
            [2.1, 2.7, -0.7, 0.7, 0.05, 0.26, "black"],           # splitter
            [2.25, 2.7, -0.45, 0.45, 0.05, 0.265, "all:gloss_black"],  # "SHELBY" letters (modelled in body paint)
            [0.7, 2.0, -0.45, 0.45, 0.85, 1.2, "paint"],          # bonnet vents
        ],
        swap={r"^rearlight$": "lamp_smoke_red", r"^orange$": "lamp_smoke", r"^light$": "lamp_clear"},
        shape=dict(nose=0.05, tail=-0.03, roof=0.03, width=0.02, hood=0.02),
        grilles=[dict(shape=("poly", [(-0.5, 0.75), (0.5, 0.75), (0.57, 0.6), (0.5, 0.29), (0.38, 0.23), (-0.38, 0.23),
                                      (-0.5, 0.29), (-0.57, 0.6)], 0.05),
                      pattern="squares", scale=10, depth=0.45, frame=(0.03, "satin"),
                      bars=[([(-0.56, 0.52), (0.56, 0.52)], 0.07, "paint")])],
        decals=[
            dict(name="tail_panel", view="rear", shape=("rrect", -0.8, 0.79, 0.8, 0.975, 0.03), mat="gloss_black",
                 offset=0.012, flat=True, support=True),
            dict(name="tail_bar", view="rear", shape=("rrect", -0.76, 0.92, 0.76, 0.945, 0.01), mat="lamp_tail",
                 offset=0.014, res=0.006),
            dict(name="tail_sq", view="rear", shape=("rrect", 0.5, 0.82, 0.72, 0.89, 0.015), mat="lamp_tail_dim",
                 offset=0.014, sym=True, res=0.008),
            dict(name="drl", view="front", path=[(0.55, 0.61), (0.84, 0.66)], width=0.02, mat="lamp_drl", sym=True,
                 offset=0.012),
            dict(name="stripe", view="top", shape=("rrect", 0.95, -0.07, 2.15, 0.07, 0.0), mat="gloss_black",
                 offset=0.004, res=0.015, reach=0.06),
            dict(name="lip", view="top", shape=("rrect", -2.36, -0.66, -2.14, 0.66, 0.05), mat="paint", height=0.05,
                 ramp=(-2.14, -2.36), skirt="gloss_black", offset=0.002),
            dict(name="emblem", view="front", shape=("poly", [(0.0, 0.66), (0.1, 0.62), (0.0, 0.58), (-0.1, 0.62)],
                                                         0.006), mat="chrome", offset=0.02, res=0.005),
        ],
        wheels=dict(inches=20, style="turbine", color=(0.25, 0.26, 0.28), rough=0.3, caliper="#f9a825"),
    ),
    # ---------------------------------------------------------------- Mazdo Miota: NA roadster -> our little roadster
    # a wide trapezoid mouth with a mesh, clear parking lamps with DRL brows, oval tails joined by a light bar,
    # a ducktail on the boot, deep-dish rims, wider and with a taller screen
    "mazdo_miota": dict(
        glass=r"^Material\.(004|010)$",
        tyre=r"^Material\.014$", lamps=r"^Material\.(008|009|012)$",
        scrub=[[1.4, 2.2, -0.9, 0.9, 0.35, 0.75, "lamp_clear"]],  # amber parking lamps -> clear
        shape=dict(nose=0.04, tail=0.03, roof=0.05, width=0.04),
        grilles=[dict(shape=("poly", [(-0.42, 0.37), (0.42, 0.37), (0.36, 0.17), (-0.36, 0.17)], 0.04),
                      pattern="mesh", scale=9, depth=0.35, frame=(0.022, "satin"))],
        decals=[
            dict(name="drl", view="front", path=[(0.4, 0.615), (0.64, 0.6)], width=0.016, mat="lamp_drl", sym=True,
                 offset=0.01),
            dict(name="tail_panel", view="rear", shape=("rrect", -0.8, 0.585, 0.8, 0.745, 0.03), mat="gloss_black",
                 offset=0.01, flat=True, support=True),
            dict(name="tail_bar", view="rear", shape=("rrect", -0.76, 0.655, 0.76, 0.675, 0.008), mat="lamp_tail",
                 offset=0.006, res=0.005),
            dict(name="tail_ends", view="rear", shape=("ellipse", 0.62, 0.665, 0.1, 0.045), mat="lamp_tail_dim",
                 offset=0.004, sym=True, res=0.006),
            dict(name="duck", view="top", shape=("rrect", -1.9, -0.6, -1.66, 0.6, 0.05), mat="paint", height=0.05,
                 ramp=(-1.66, -1.9), skirt="paint", offset=0.002, reach=0.06),
            dict(name="emblem", view="front", path=ellipse(0.0, 0.47, 0.035, 0.025), closed=True, width=0.008,
                 mat="chrome", offset=0.004),
        ],
        wheels=dict(inches=15, style="dish8", color=(0.8, 0.81, 0.83), rough=0.18),
    ),
    # ---------------------------------------------------------------- Ferrano 488: 458 Spider -> our mid-engine spider
    # one wide hex-mesh mouth, smoked lamps with a DRL blade, the round tail lamps covered by flat black pods with
    # a light bar, a small wing; twin-spoke black rims; longer tail
    "ferrano_488": dict(
        glass=r"^Glass_Gray$",
        tyre=r"^Tires$", lamps=r"^(Taillight_Glass|Projector_Glass|Turn_Signal_LED)$",
        scrub=[
            [2.0, 2.45, -0.15, 0.15, 0.2, 0.6, "parts"],          # front horse
            [-2.4, -2.0, -0.55, 0.55, 0.6, 1.0, "parts"],         # rear horse and script
        ],
        swap={r"^Projector_Glass$": "lamp_smoke", r"^Turn_Signal_LED$": "lamp_smoke"},
        shape=dict(tail=0.05, roof=-0.02, width=0.02, rake=-0.008),
        grilles=[dict(shape=("rrect", -0.66, 0.22, 0.66, 0.43, 0.08), pattern="hex", scale=14, depth=0.4,
                      frame=(0.018, "gloss_black"))],
        decals=[
            dict(name="drl", view="front", path=[(0.58, 0.63), (0.72, 0.7), (0.8, 0.78)], width=0.016, mat="lamp_drl",
                 sym=True, offset=0.01),
            dict(name="tail_pod", view="rear", shape=("rrect", 0.58, 0.8, 0.92, 0.94, 0.03), mat="gloss_black",
                 offset=0.01, sym=True),
            dict(name="tail_bar", view="rear", shape=("rrect", 0.6, 0.86, 0.9, 0.885, 0.01), mat="lamp_tail",
                 offset=0.016, sym=True, res=0.006),
            dict(name="emblem", view="front", shape=("poly", [(-0.04, 0.5), (0.04, 0.5), (0.04, 0.47), (0.0, 0.44),
                                                               (-0.04, 0.47)], 0.003), mat="chrome", offset=0.004,
                 res=0.004),
        ],
        wings=[dict(x=-1.98, height=0.09, span=1.3, chord=0.2, mat="carbon", stand_y=0.4, plate_h=0.05)],
        wheels=dict(inches=20, style="twin6", color=(0.06, 0.06, 0.065), rough=0.35, caliper="#c62828"),
    ),
    # ---------------------------------------------------------------- Lamborgo Aventa: Aventador -> our wedge supercar
    # bull badges and lettering out, Y-shaped lamps smoked with straight DRL blades and honeycomb intakes,
    # tails turned into twin light bars, a fixed wing on stands, seven-spoke rims
    "lamborgo_aventa": dict(
        glass=r"^Vitre$",
        tyre=r"^Pneu$", lamps=r"^(Phare|Feux)",
        scrub=[[-2.45, -2.1, -0.35, 0.35, 0.7, 0.95, "parts"]],   # rear lettering
        swap={r"^Phare_optique$": "lamp_smoke", r"^Feux_(rouge|rouge_c|orange)$": "lamp_smoke_red",
              r"^Feux_blanc$": "lamp_smoke", r"^Logo": "paint", r"^LP_700$": "paint"},
        shape=dict(nose=0.04, roof=0.03, width=0.025),
        grilles=[dict(shape=("poly", [(0.33, 0.45), (0.8, 0.45), (0.8, 0.17), (0.4, 0.17)], 0.03), pattern="hex",
                      scale=16, depth=0.45, sym=True, frame=(0.016, "gloss_black"))],
        decals=[
            dict(name="drl", view="front", path=[(0.5, 0.71), (0.76, 0.68)], width=0.014, mat="lamp_drl", sym=True,
                 offset=0.01),
            dict(name="drl2", view="front", path=[(0.52, 0.665), (0.7, 0.648)], width=0.01, mat="lamp_drl", sym=True,
                 offset=0.01),
            dict(name="tail_bar", view="rear", shape=("rrect", 0.4, 0.82, 0.9, 0.84, 0.008), mat="lamp_tail",
                 offset=0.012, sym=True, res=0.006),
            dict(name="tail_bar2", view="rear", shape=("rrect", 0.5, 0.79, 0.9, 0.805, 0.006), mat="lamp_tail",
                 offset=0.012, sym=True, res=0.005),
            dict(name="emblem", view="front", shape=("hex", 0.0, 0.58, 0.64, 0.05, 0.07, 0.05, 0.5), mat="chrome",
                 offset=0.004, res=0.004),
        ],
        wings=[dict(x=-2.0, height=0.2, span=1.75, chord=0.3, mat="carbon", stand_y=0.5, plate_h=0.1)],
        wheels=dict(inches=20, style="star7", color=(0.2, 0.21, 0.22), rough=0.3, caliper="#2e7d32"),
    ),
    # ---------------------------------------------------------------- Hondo Civix: Civic Type R -> our hot hatch
    # H and TYPE R badges out, two new grilles, the swan-neck wing replaced by a roof spoiler lip, a light bar
    # between the tail lamps, ten-spoke silver rims
    "hondo_civix": dict(
        glass=r"^Windshield",
        tyre=r"^Tyre0[12]", lamps=r"^Lamp",
        drop_mat=r"^Rimbadge",
        drop_obj=r"^Object_53$",                                  # wing stands
        scrub=[
            [-2.4, -1.85, -1.1, 1.1, 1.05, 1.45, "delete"],       # rear wing
            [-2.4, -2.0, -0.25, 0.25, 0.6, 0.85, "plate"],        # TYPE R plaque -> blank plate
            [-2.4, -2.0, 0.25, 0.65, 0.7, 0.9, "parts"],          # CIVIC lettering
            [-2.4, -2.0, 0.25, 0.7, 0.68, 0.86, "paint", True],   # lettering pieces left over
            [2.1, 2.3, 0.22, 0.42, 0.54, 0.62, "gloss_black"],    # red R badge in the grille
        ],
        shape=dict(roof=0.03, width=0.02, tail=0.02),
        grilles=[
            dict(shape=("rrect", -0.5, 0.56, 0.5, 0.71, 0.03), pattern="slats", scale=14, depth=0.4,
                 frame=(0.014, "gloss_black")),
            dict(shape=("poly", [(-0.5, 0.52), (0.5, 0.52), (0.42, 0.18), (-0.42, 0.18)], 0.04), pattern="hex", scale=12,
                 depth=0.45, frame=(0.02, "gloss_black"), bars=[([(-0.46, 0.4), (0.46, 0.4)], 0.02, "satin")]),
        ],
        decals=[
            dict(name="drl", view="front", path=[(0.47, 0.69), (0.84, 0.72)], width=0.014, mat="lamp_drl", sym=True,
                 offset=0.01),
            dict(name="tail_bar", view="rear", shape=("rrect", -0.82, 0.935, 0.82, 0.955, 0.008), mat="lamp_tail",
                 offset=0.012, res=0.006),
            dict(name="emblem", view="front", shape=("poly", [(-0.055, 0.66), (0.055, 0.66), (0.0, 0.61)], 0.006),
                 mat="chrome", offset=0.02, res=0.004),
        ],
        wheels=dict(inches=19, style="spoke10", color=(0.6, 0.61, 0.63), rough=0.22, caliper="#c62828"),
    ),
    # ---------------------------------------------------------------- BMV M4: G82 M4 -> our sports coupe
    # the kidneys go: one wide shield grille with a mesh; roundels and M badges out; DRL blades over smoked lamps;
    # new tail bars; a boot lip; bronze split-five rims; longer nose and taller roof
    "bmv_m4": dict(
        glass=r"^Material_699$",
        tyre=r"^Material_75[12]$", lamps=r"^Material_(775|776|718|161|716|708|707|739|738|740|701\.001)$",
        scrub=[[-2.45, -2.1, -0.5, -0.15, 0.85, 1.05, "parts"]],  # M4 badge on the boot
        swap={r"^Material_(538|574|786|787|790|1063)$": "paint", r"^Material_826$": "plate",
              r"^Material_(776|708|707)$": "lamp_smoke", r"^Material_(738|739|740)$": "lamp_smoke_red"},
        shape=dict(nose=0.045, roof=0.03, width=0.02),
        grilles=[dict(shape=("poly", [(-0.44, 0.785), (0.44, 0.785), (0.5, 0.5), (0.44, 0.25), (-0.44, 0.25),
                                      (-0.5, 0.5)], 0.05),
                      pattern="mesh", scale=11, depth=0.45, frame=(0.024, "chrome"), cut_lamps=True, cover=False,
                      inset=-0.03, cut_paint=("rrect", -0.41, 0.44, 0.41, 0.765, 0.08),
                      bars=[([(-0.49, 0.5), (0.49, 0.5)], 0.022, "chrome")])],
        decals=[
            dict(name="drl", view="front", path=[(0.45, 0.735), (0.86, 0.715)], width=0.014, mat="lamp_drl", sym=True,
                 offset=0.01),
            dict(name="tail_bar", view="rear", shape=("rrect", 0.38, 0.9, 0.86, 0.925, 0.01), mat="lamp_tail",
                 offset=0.012, sym=True, res=0.006),
            dict(name="lip", view="top", shape=("rrect", -2.38, -0.62, -2.18, 0.62, 0.05), mat="paint", height=0.035,
                 ramp=(-2.18, -2.38), skirt="paint", offset=0.002),
            dict(name="emblem", view="front", shape=("rrect", -0.07, 0.62, 0.07, 0.655, 0.012), mat="chrome",
                 offset=0.03, res=0.004),
        ],
        wheels=dict(inches=19, style="split5", color=(0.45, 0.32, 0.17), rough=0.28, caliper="#1b1b1f"),
    ),
    # ---------------------------------------------------------------- Ramm 1500: '90s Ram -> our full-size pickup
    # bull bar and ram's head out, the crosshair grille replaced by a three-bar grille, LED bars under the lamps,
    # a bonnet power bulge, new tail lamps; six-spoke chrome rims on all-terrain tyres
    "ramm_1500": dict(
        glass=r"^Glass$",
        tyre=r"^Tires$", lamps=r"^(hl_lamps|plexiglass|taillight_red_pl|hl_blinkers)$",
        drop_obj=r"^Object_(84|87)$",
        drop_mat=r"^0-",
        swap={r"^taillight_red_pl$": "lamp_smoke_red"},
        shape=dict(nose=0.03, roof=0.04, width=0.02, hood=0.03),
        grilles=[dict(shape=("rrect", -0.66, 0.8, 0.66, 1.26, 0.06), pattern="squares", scale=8, depth=0.5,
                      frame=(0.04, "chrome"),
                      bars=[([(-0.64, 1.1), (0.64, 1.1)], 0.035, "chrome"), ([(-0.64, 0.95), (0.64, 0.95)], 0.035,
                                                                            "chrome")])],
        decals=[
            dict(name="drl", view="front", path=[(0.68, 0.895), (0.96, 0.895)], width=0.022, mat="lamp_drl",
                 sym=True, offset=0.01),
            dict(name="bulge", view="top", shape=("rrect", 1.5, -0.38, 2.45, 0.38, 0.12), mat="paint", height=0.035,
                 ramp=(2.45, 1.9), skirt="paint", offset=0.002, res=0.02),
            dict(name="tail_bar", view="rear", shape=("rrect", 0.885, 0.93, 0.975, 0.96, 0.01), mat="lamp_tail",
                 offset=0.012, sym=True, res=0.006),
            dict(name="tail_bar2", view="rear", shape=("rrect", 0.885, 1.1, 0.975, 1.13, 0.01), mat="lamp_tail",
                 offset=0.012, sym=True, res=0.006),
            dict(name="emblem", view="front", shape=("poly", [(0.0, 1.06), (0.09, 1.025), (0.0, 0.99), (-0.09, 1.025)],
                                                         0.004), mat="chrome", offset=0.03, res=0.005),
        ],
        wheels=dict(inches=17, style="six", color=(0.82, 0.83, 0.85), rough=0.12, tread="at"),
    ),
    # ---------------------------------------------------------------- Forde Rangler: 2001 Ranger -> our compact pickup
    # Ford ovals and plates out, a bigger three-slat grille with chrome bars, DRL bars, new tail lamps,
    # five-spoke rims, a taller cab
    "forde_rangler": dict(
        glass=r"^material_2[23]$",
        tyre=r"^material_20$", lamps=r"^material_(15|16|17|2|5|6)$",
        drop_mat=r"^material_18$",                                 # oval badges
        scrub=[
            [-2.5, -2.38, -0.65, -0.2, 0.86, 0.98, "parts"],       # tailgate oval
            [1.15, 1.45, 0.8, 1.2, 0.95, 1.03, "parts", True],    # fender lettering
        ],
        swap={r"^material_11$": "plate", r"^material_[56]$": "lamp_smoke_red"},
        shape=dict(nose=0.03, roof=0.035, width=0.02),
        grilles=[dict(shape=("rrect", -0.44, 0.75, 0.44, 1.06, 0.04), pattern="slats", scale=10, depth=0.45,
                      frame=(0.035, "chrome"),
                      bars=[([(-0.42, 0.905), (0.42, 0.905)], 0.03, "chrome")])],
        decals=[
            dict(name="drl", view="front", path=[(0.46, 0.79), (0.8, 0.79)], width=0.018, mat="lamp_drl", sym=True,
                 offset=0.01),
            dict(name="tail_bar", view="rear", shape=("rrect", 0.7, 0.98, 0.83, 1.0, 0.006), mat="lamp_tail",
                 offset=0.012, sym=True, res=0.005),
            dict(name="tail_bar2", view="rear", shape=("rrect", 0.7, 0.9, 0.83, 0.92, 0.006), mat="lamp_tail",
                 offset=0.012, sym=True, res=0.005),
            dict(name="emblem", view="front", shape=("rrect", -0.11, 0.88, 0.11, 0.93, 0.004), mat="chrome",
                 offset=0.035, res=0.004),
            dict(name="stripe", view="side", path=[(-2.4, 0.95), (1.9, 0.95)], width=0.04, mat="gloss_black", sym=True),
        ],
        wheels=dict(inches=16, style="five", color=(0.3, 0.31, 0.33), rough=0.3, tread="at"),
    ),
    # ---------------------------------------------------------------- Rang Rovah: Range Rover Sport -> our luxury SUV
    # lettering and badges out, a hex grille with vertical slats, DRL blades, a tail light bar across the tailgate,
    # Y-spoke rims, lower roof
    "rang_rovah": dict(
        tyre=r"^Tire", glass=r"^Windows$",
        lamps=r"(?i)taillight|front_led|drl|clear_glass|brake_light|hamna|^Material\.0(04|07|08|09|10|15|16)$",
        scrub=[[-2.5, -2.15, -0.62, 0.62, 0.95, 1.2, "parts"]],
        swap={r"^Material\.0(09|15)$": "paint", r"^Mat\.001$": "paint", r"^Brake_Light_Cover$": "paint"},
        shape=dict(nose=0.04, roof=-0.03, width=0.02, rake=0.01),
        grilles=[dict(shape=("hex", 0.0, 0.86, 1.07, 0.92, 1.0, 0.86, 0.5, 0.03), pattern="vslats", scale=10, depth=0.45,
                      frame=(0.02, "chrome"))],
        decals=[
            dict(name="drl", view="front", path=[(0.48, 0.905), (0.86, 0.92)], width=0.016, mat="lamp_drl", sym=True,
                 offset=0.01),
            dict(name="tail_bar", view="rear", shape=("rrect", -0.62, 1.12, 0.62, 1.14, 0.008), mat="lamp_tail",
                 offset=0.012, res=0.006),
            dict(name="tail_panel", view="rear", shape=("rrect", -0.62, 1.08, 0.62, 1.18, 0.02), mat="gloss_black",
                 offset=0.006),
        ],
        wheels=dict(inches=22, style="y5", color=(0.22, 0.23, 0.25), rough=0.3),
    ),
    # ---------------------------------------------------------------- Mercedez G-Wagon: Brabus G900 -> our boxy 4x4
    # B grille, badges, roof spoiler and spare wheel out; a horizontal three-bar grille, light bars through the
    # round lamps, new tail lamps, four-blade rims, longer bonnet
    "mercedez_g_wagon": dict(
        tyre=r"^plastic5_16$", glass=r"^(IntWindows|ExtWindowsGlass_0)$",
        glass_transmission=0.05, glass_spec=0.2,                  # flat upright windows: keep them dark
        lamps=r"^(ExtWindowsGlass|ExtWindowsGlass_1|leather02_weave_18)$",
        drop_obj=r"sparewheel|spare_wheel|text_Brabus|logo_brabus|logo1_brabus|doortags|setlogo01x|8001_symbols",
        scrub=[
            [-2.6, -2.0, -0.7, 0.7, 0.68, 1.68, "parts"],         # spare wheel
            [-2.6, -2.0, 0.4, 0.95, 0.9, 1.15, "parts", True],    # rear badges
            [0.55, 2.0, 0.9, 1.25, 0.45, 1.1, "parts", True],       # fender badges
            [0.45, 0.85, 0.9, 1.3, 0.74, 0.9, "parts", True],       # model badge behind the front wheel
            [-2.5, -1.4, -1.2, 1.2, 1.9, 2.15, "parts"],          # roof spoiler
        ],
        swap={r"^ExtWindowsGlass_1$": "lamp_smoke_red"},
        shape=dict(nose=0.05, roof=0.025, width=0.02),
        grilles=[dict(shape=("rrect", -0.44, 0.76, 0.44, 1.08, 0.03), pattern="slats", scale=9, depth=0.45,
                      frame=(0.03, "gloss_black"),
                      bars=[([(-0.42, 0.98), (0.42, 0.98)], 0.03, "chrome"), ([(-0.42, 0.87), (0.42, 0.87)], 0.03,
                                                                            "chrome")])],
        decals=[
            dict(name="lamp_cover", view="front", shape=("rrect", 0.55, 0.86, 0.81, 1.11, 0.035), mat="lamp_smoke",
                 sym=True, offset=0.02, flat=True, level=True, cover=False, support=True, res=0.008,
                 skirt="gloss_black"),
            dict(name="drl", view="front", path=[(0.585, 1.07), (0.775, 1.07), (0.775, 0.91)], width=0.02,
                 mat="lamp_drl", sym=True, offset=0.012),
            dict(name="projector", view="front", shape=("rrect", 0.6, 0.93, 0.72, 1.03, 0.02), mat="lamp_clear",
                 sym=True, offset=0.012, res=0.004),
            dict(name="tail_bar", view="rear", shape=("rrect", 0.62, 0.79, 0.9, 0.81, 0.006), mat="lamp_tail",
                 offset=0.012, sym=True, res=0.005),
            dict(name="emblem", view="front", shape=("rrect", -0.04, 0.905, 0.04, 0.945, 0.006), mat="chrome",
                 offset=0.03, res=0.004),
            dict(name="tailgate", view="rear", shape=("rrect", -0.45, 0.85, 0.45, 1.55, 0.06), mat="gloss_black",
                 offset=0.004, res=0.02),
        ],
        wheels=dict(inches=22, style="blade4", color=(0.32, 0.33, 0.35), rough=0.3),
    ),
    # ---------------------------------------------------------------- Chevro Tahoma: Prado stand-in -> our full-size SUV
    # Toyota grille and C-ring lamps out: a wide grille with a chrome bar running through the lamps, split LED
    # lamps, vertical tail bars, twin-spoke rims
    "chevro_tahoma": dict(
        tyre=r"^tire$", glass=r"^WorldGridMaterial\.024$",
        lamps=r"^(WorldGridMaterial\.0(21|27|28|39)|Material\.002)$",
        swap={r"^Material\.002$": "lamp_smoke", r"^WorldGridMaterial\.0(21|28)$": "lamp_smoke_red"},
        shape=dict(nose=0.03, roof=0.02, width=0.02),
        grilles=[dict(shape=("rrect", -0.52, 0.89, 0.52, 1.14, 0.03), pattern="squares", scale=9, depth=0.45,
                      frame=(0.025, "chrome"))],
        decals=[
            dict(name="bar", view="front", path=[(-0.86, 1.015), (0.86, 1.015)], width=0.045, mat="chrome",
                 offset=0.02),
            dict(name="lamp_cover", view="front", shape=("rrect", 0.56, 0.925, 0.87, 1.115, 0.02), mat="lamp_smoke",
                 sym=True, offset=0.008, flat=True, support=True, res=0.008),
            dict(name="projector", view="front", shape=("ellipse", 0.7, 1.015, 0.045, 0.035), mat="lamp_clear",
                 sym=True, offset=0.01, res=0.004),
            dict(name="drl", view="front", path=[(0.56, 1.075), (0.84, 1.075)], width=0.016, mat="lamp_drl",
                 sym=True, offset=0.012),
            dict(name="drl2", view="front", path=[(0.56, 0.955), (0.84, 0.955)], width=0.016, mat="lamp_drl",
                 sym=True, offset=0.012),
            dict(name="tail_cover", view="rear", shape=("rrect", 0.74, 0.9, 0.92, 1.27, 0.02), mat="lamp_smoke_red",
                 sym=True, offset=0.008, support=True, res=0.008, reach=0.08),
            dict(name="tail_bar", view="rear", shape=("rrect", 0.76, 0.96, 0.8, 1.21, 0.008), mat="lamp_tail",
                 offset=0.012, sym=True, res=0.005),
            dict(name="emblem", view="front", shape=("poly", [(-0.06, 1.04), (0.06, 1.04), (0.04, 0.99), (-0.04, 0.99)],
                                                         0.004), mat="gold", offset=0.03, res=0.004),
        ],
        wheels=dict(inches=20, style="twin6", color=(0.78, 0.79, 0.81), rough=0.2),
    ),
}
