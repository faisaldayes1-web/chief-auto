"""One Chief Auto dealership in Tewport Beach, built in Blender: every background in the game is rendered from it.

The site: a glass showroom on the harbour. The lot faces the street (south), the showroom looks out over the
marina (north), the service bay is the wing on the east side, Marco's office is the glass corner room at the
back west, and the owner's apartment sits on the roof. Apartment tiers (1-3) toggle furniture and finish, so
the same room can be upgraded visually in the game; the showroom tiers work the same way.

Usage (bpy venv):  python tools/dealership3d.py <out_dir> [view ...]
Views: lot, showroom, office, garage, desk, dealdesk (add _t1 / _t2 for the starting and mid-size
dealerships), apartment1, apartment2, apartment3.  SAMPLES env sets quality, PREVIEW=1 renders 640x360.
The lot views also write stalls_<view>.json next to the render: where the game parks each owned car (see LOT_ROWS).
"""
import math
import os
import random
import sys

import bpy  # noqa: I001
import bmesh  # bpy must load first
from mathutils import Matrix, Vector

SAMPLES = int(os.environ.get("SAMPLES", 96))
RES = (640, 360) if os.environ.get("PREVIEW") else (1600, 900)
TIER_COLLECTIONS = {}


# ---------------------------------------------------------------- materials

_mats = {}


def mat(name, color=(0.8, 0.8, 0.8), rough=0.5, metal=0.0, trans=0.0, emit=0.0, ecol=None, alpha=1.0):
    key = name
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Transmission Weight"].default_value = trans
    if trans > 0:
        b.inputs["IOR"].default_value = 1.45
    if emit > 0:
        b.inputs["Emission Color"].default_value = (*(ecol or color), 1)
        b.inputs["Emission Strength"].default_value = emit
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
    _mats[key] = m
    return m


def noise_mat(name, c1, c2, scale, rough, detail=6, bump=0.0, metal=0.0, veins=False, stretch=(1, 1, 1), macro=0.0):
    """Two-colour material driven by noise (asphalt, marble, concrete, water)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = stretch
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = detail
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*c1, 1)
    ramp.color_ramp.elements[1].color = (*c2, 1)
    if veins:
        # thin grey veins where the noise crosses its middle value, like Calacatta stone
        nz.inputs["Distortion"].default_value = 2.5
        nz.inputs["Roughness"].default_value = 0.6
        els = ramp.color_ramp.elements
        els[0].position, els[0].color = 0.47, (*c1, 1)
        els[1].position, els[1].color = 0.53, (*c1, 1)
        mid = els.new(0.5)
        mid.color = (*c2, 1)
        nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    else:
        nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    col = ramp.outputs["Color"]
    if macro > 0:
        # large blotches (wear, stains, patching) so big surfaces don't read as one flat colour
        mz = nt.nodes.new("ShaderNodeTexNoise")
        mz.inputs["Scale"].default_value = scale / 40.0
        mz.inputs["Detail"].default_value = 3
        nt.links.new(mp.outputs["Vector"], mz.inputs["Vector"])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value = 1.0 - macro
        mr.inputs["To Max"].default_value = 1.0 + macro * 0.4
        nt.links.new(mz.outputs["Fac"], mr.inputs["Value"])
        mul = nt.nodes.new("ShaderNodeMix")
        mul.data_type = "RGBA"
        mul.blend_type = "MULTIPLY"
        mul.inputs["Factor"].default_value = 1.0
        nt.links.new(col, mul.inputs["A"])
        nt.links.new(mr.outputs["Result"], mul.inputs["B"])
        col = mul.outputs["Result"]
        rr = nt.nodes.new("ShaderNodeMapRange")
        rr.inputs["To Min"].default_value = rough + 0.08
        rr.inputs["To Max"].default_value = rough - 0.15
        nt.links.new(mz.outputs["Fac"], rr.inputs["Value"])
        nt.links.new(rr.outputs["Result"], b.inputs["Roughness"])
    nt.links.new(col, b.inputs["Base Color"])
    if macro <= 0:
        b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if bump > 0:
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = bump
        bp.inputs["Distance"].default_value = 0.05
        nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def glass():
    m = mat("glass", (0.85, 0.92, 0.95), rough=0.02, trans=1.0)
    return m


# ---------------------------------------------------------------- geometry helpers

COL = None


def _link(ob):
    target = COL or bpy.context.scene.collection
    if target not in ob.users_collection:
        target.objects.link(ob)
    for c in list(ob.users_collection):
        if c is not target:
            c.objects.unlink(ob)
    return ob


def _bm_obj(name, bm, m, loc=(0, 0, 0), smooth=False):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(m)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    _link(ob)
    return ob


def box(name, lo, hi, m, bevel=0.0):
    """Axis-aligned box from corner lo to corner hi (origin at its centre)."""
    lo, hi = Vector(lo), Vector(hi)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=hi - lo, verts=bm.verts)
    ob = _bm_obj(name, bm, m, (lo + hi) / 2)
    if bevel > 0:
        md = ob.modifiers.new("b", "BEVEL")
        md.width = bevel
        md.segments = 3
    return ob


def cyl(name, loc, r, h, m, r2=None, verts=24, rot=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=r, radius2=r if r2 is None else r2, depth=h)
    ob = _bm_obj(name, bm, m, loc, smooth=True)
    ob.rotation_euler = rot
    return ob


def sphere(name, loc, scale, m, seg=24):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=1.0)
    ob = _bm_obj(name, bm, m, loc, smooth=True)
    ob.scale = scale
    return ob


def text(name, body, loc, size, m, rot=(math.pi / 2, 0, 0), extrude=0.05, align="CENTER"):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.align_x = align
    ob = bpy.data.objects.new(name, cu)
    ob.location = loc
    ob.rotation_euler = rot
    cu.materials.append(m)
    _link(ob)
    return ob


def glass_wall(name, a, b, z0, z1, every=2.0, frame=None):
    """A curtain wall of glass between floor points a and b with slim mullions."""
    a, b = Vector(a), Vector(b)
    frame = frame or mat("alu", (0.08, 0.08, 0.09), rough=0.35, metal=0.8)
    d = b - a
    n = Vector((-d.y, d.x, 0)).normalized() * 0.01
    g = box(name, Vector((min(a.x, b.x), min(a.y, b.y), z0)) - n, Vector((max(a.x, b.x), max(a.y, b.y), z1)) + n, glass())
    g.visible_shadow = False
    count = max(1, int(d.length / every))
    for i in range(count + 1):
        p = a + d * (i / count)
        box(name + "_m", (p.x - 0.04, p.y - 0.04, z0), (p.x + 0.04, p.y + 0.04, z1), frame)
    for z in (z0, z1):
        box(name + "_t", (min(a.x, b.x) - 0.04, min(a.y, b.y) - 0.05, z - 0.06), (max(a.x, b.x) + 0.04, max(a.y, b.y) + 0.05, z + 0.06), frame)
    return g


# ---------------------------------------------------------------- set dressing (palms, buildings, boats, lot detail)

def _node_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    return m, nt, nt.nodes["Principled BSDF"]


def _n(nt, kind, **inputs):
    """Adds a shader node and sets its input defaults by name (or by index for duplicate names)."""
    nd = nt.nodes.new(kind)
    for k, v in inputs.items():
        nd.inputs[k.replace("_", " ")].default_value = v
    return nd


def _math(nt, op, *vals, clamp=False):
    nd = nt.nodes.new("ShaderNodeMath")
    nd.operation = op
    nd.use_clamp = clamp
    for i, v in enumerate(vals):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            nd.inputs[i].default_value = v
        else:
            nt.links.new(v, nd.inputs[i])
    return nd.outputs[0]


def _mix(nt, fac, a, b, blend="MIX"):
    nd = nt.nodes.new("ShaderNodeMix")
    nd.data_type = "RGBA"
    nd.blend_type = blend
    for sock, v in (("Factor", fac), ("A", a), ("B", b)):
        if isinstance(v, (int, float)):
            nd.inputs[sock].default_value = v
        elif isinstance(v, tuple):
            nd.inputs[sock].default_value = (*v, 1) if len(v) == 3 else v
        else:
            nt.links.new(v, nd.inputs[sock])
    return nd.outputs["Result"]


def _ramp(nt, fac, stops, constant=False):
    r = nt.nodes.new("ShaderNodeValToRGB")
    if constant:
        r.color_ramp.interpolation = "CONSTANT"
    els = r.color_ramp.elements
    while len(els) < len(stops):
        els.new(0.5)
    for el, (pos, col) in zip(els, stops):
        el.position = pos
        el.color = (*col, 1) if len(col) == 3 else col
    nt.links.new(fac, r.inputs["Fac"])
    return r.outputs["Color"]


def _coords(nt, space="Object", scale=None):
    tc = nt.nodes.new("ShaderNodeTexCoord")
    out = tc.outputs[space]
    if scale is not None:
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = scale
        nt.links.new(out, mp.inputs["Vector"])
        out = mp.outputs["Vector"]
    return out


def _face_uv(nt):
    """(x + y, z, 0) in object space: runs along any axis-aligned wall and up it, in metres."""
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(_coords(nt), sep.inputs[0])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(_math(nt, "ADD", sep.outputs["X"], sep.outputs["Y"]), comb.inputs["X"])
    nt.links.new(sep.outputs["Z"], comb.inputs["Y"])
    return comb.outputs[0], sep


def _noise(nt, vec, scale, detail=4.0, rough=0.55):
    nz = _n(nt, "ShaderNodeTexNoise", Scale=scale, Detail=detail, Roughness=rough)
    nt.links.new(vec, nz.inputs["Vector"])
    return nz


def _bump(nt, b, height, strength, distance=0.02, invert=False):
    bp = _n(nt, "ShaderNodeBump", Strength=strength, Distance=distance)
    bp.invert = invert
    nt.links.new(height, bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return bp


def asphalt_mat(name, c1, c2, cracks=0.5, rough=0.82):
    """Asphalt: fine aggregate, big wear blotches and dark sealed cracks in patches."""
    if name in _mats:
        return _mats[name]
    m, nt, b = _node_mat(name)
    co = _coords(nt)
    fine = _noise(nt, co, 90.0, 8.0, 0.7)
    col = _ramp(nt, fine.outputs["Fac"], ((0.3, c1), (0.7, c2)))
    macro = _noise(nt, co, 0.09, 4.0, 0.6)
    wear = _ramp(nt, macro.outputs["Fac"], ((0.3, (0.78, 0.78, 0.8)), (0.72, (1.18, 1.17, 1.15))))
    col = _mix(nt, 1.0, col, wear, "MULTIPLY")
    # sealed cracks: thin Voronoi cell edges, only where a second noise says so
    vo = nt.nodes.new("ShaderNodeTexVoronoi")
    vo.voronoi_dimensions = "2D"
    vo.feature = "DISTANCE_TO_EDGE"
    vo.inputs["Scale"].default_value = 0.32
    vo.inputs["Randomness"].default_value = 0.9
    warp = _noise(nt, co, 0.6, 2.0)
    wv = _mix(nt, 0.25, co, warp.outputs["Color"])
    nt.links.new(wv, vo.inputs["Vector"])
    line = _math(nt, "LESS_THAN", vo.outputs["Distance"], 0.018)
    mask = _math(nt, "GREATER_THAN", _noise(nt, co, 0.05, 2.0).outputs["Fac"], 1.0 - cracks * 0.6)
    crack = _math(nt, "MULTIPLY", line, mask)
    col = _mix(nt, crack, col, (0.012, 0.012, 0.013))
    nt.links.new(col, b.inputs["Base Color"])
    r = _math(nt, "MULTIPLY_ADD", macro.outputs["Fac"], -0.25, rough + 0.12)
    nt.links.new(r, b.inputs["Roughness"])
    _bump(nt, b, fine.outputs["Fac"], 0.25, 0.01)
    _mats[name] = m
    return m


def stain_mat(name, col, alpha=0.85, rough=0.3, scale=3.0):
    """A blotch for a 1 x 1 m plane (oil drips, tyre marks, water stains): dark in the middle, ragged at the edge."""
    if name in _mats:
        return _mats[name]
    m, nt, b = _node_mat(name)
    co = _coords(nt)
    gr = nt.nodes.new("ShaderNodeTexGradient")
    gr.gradient_type = "SPHERICAL"
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (2.0, 2.0, 2.0)
    nt.links.new(co, mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], gr.inputs["Vector"])
    nz = _noise(nt, co, scale, 6.0, 0.65)
    a = _math(nt, "MULTIPLY", gr.outputs["Fac"], nz.outputs["Fac"])
    a = _math(nt, "MULTIPLY_ADD", a, 3.2, -0.45)
    a = _math(nt, "MULTIPLY", _math(nt, "MINIMUM", _math(nt, "MAXIMUM", a, 0.0), 1.0), alpha)
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = rough
    nt.links.new(a, b.inputs["Alpha"])
    _mats[name] = m
    return m


def block_mat(name, c1, c2, mortar=(0.62, 0.6, 0.56), block=(0.4, 0.2), split=0.5):
    """Concrete masonry units with mortar joints (split-face when split > 0)."""
    if name in _mats:
        return _mats[name]
    m, nt, b = _node_mat(name)
    uv, _ = _face_uv(nt)
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset = 0.5
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.012
    br.inputs["Mortar Smooth"].default_value = 0.2
    br.inputs["Brick Width"].default_value = block[0]
    br.inputs["Row Height"].default_value = block[1]
    br.inputs["Color1"].default_value = (*c1, 1)
    br.inputs["Color2"].default_value = (*c2, 1)
    br.inputs["Mortar"].default_value = (*mortar, 1)
    nt.links.new(uv, br.inputs["Vector"])
    co = _coords(nt)
    grain = _noise(nt, co, 25.0, 8.0, 0.7)
    dirt = _noise(nt, co, 0.6, 3.0)
    tone = _ramp(nt, grain.outputs["Fac"], ((0.35, (0.82, 0.82, 0.82)), (0.65, (1.1, 1.1, 1.08))))
    col = _mix(nt, 1.0, br.outputs["Color"], tone, "MULTIPLY")
    # grime creeping up from the ground
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(_coords(nt, "Generated"), sep.inputs[0])
    low = _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", 1.0, _math(nt, "MULTIPLY", sep.outputs["Z"], 3.0), clamp=True),
                dirt.outputs["Fac"])
    col = _mix(nt, _math(nt, "MULTIPLY", low, 0.6), col, (0.25, 0.23, 0.2), "MULTIPLY")
    nt.links.new(col, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.88
    h = _math(nt, "ADD", _math(nt, "MULTIPLY", br.outputs["Fac"], -1.0), _math(nt, "MULTIPLY", grain.outputs["Fac"], split * 0.6))
    _bump(nt, b, h, 0.55, 0.012)
    _mats[name] = m
    return m


def stripe_mat(name, c1, c2, width=0.5, axis="X", rough=0.75):
    """Alternating colour bands (awning canvas, kerb paint)."""
    if name in _mats:
        return _mats[name]
    m, nt, b = _node_mat(name)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(_coords(nt, "Object"), sep.inputs[0])
    s = sep.outputs[axis]
    band = _math(nt, "FLOORED_MODULO", _math(nt, "FLOOR", _math(nt, "DIVIDE", s, width)), 2.0)
    nt.links.new(_mix(nt, band, c1, c2), b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = rough
    _mats[name] = m
    return m


def window_mat(name, wall, glass_col=(0.03, 0.045, 0.06), bay=2.6, storey=3.3, frac=(0.62, 0.5), shade=None):
    """Distant buildings: a wall colour with a grid of dark windows painted on (no geometry)."""
    if name in _mats:
        return _mats[name]
    m, nt, b = _node_mat(name)
    uv, _ = _face_uv(nt)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uv, sep.inputs[0])
    fu = _math(nt, "FRACT", _math(nt, "DIVIDE", sep.outputs["X"], bay))
    fv = _math(nt, "FRACT", _math(nt, "DIVIDE", sep.outputs["Y"], storey))
    wu = _math(nt, "LESS_THAN", _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT", fu, 0.5)), frac[0] / 2)
    wv = _math(nt, "LESS_THAN", _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT", fv, 0.55)), frac[1] / 2)
    win = _math(nt, "MULTIPLY", wu, wv)
    co = _coords(nt)
    tone = _ramp(nt, _noise(nt, co, 0.8, 3.0).outputs["Fac"], ((0.3, (0.85, 0.85, 0.85)), (0.7, (1.05, 1.05, 1.05))))
    wallc = _mix(nt, 1.0, wall, tone, "MULTIPLY")
    glassc = glass_col
    if shade:
        # some windows have blinds or awnings drawn: lighter panes in a random pattern
        cell = nt.nodes.new("ShaderNodeTexWhiteNoise")
        cell.noise_dimensions = "2D"
        comb = nt.nodes.new("ShaderNodeCombineXYZ")
        nt.links.new(_math(nt, "FLOOR", _math(nt, "DIVIDE", sep.outputs["X"], bay)), comb.inputs["X"])
        nt.links.new(_math(nt, "FLOOR", _math(nt, "DIVIDE", sep.outputs["Y"], storey)), comb.inputs["Y"])
        nt.links.new(comb.outputs[0], cell.inputs["Vector"])
        glassc = _mix(nt, _math(nt, "GREATER_THAN", cell.outputs["Value"], 0.6), glass_col, shade)
    nt.links.new(_mix(nt, win, wallc, glassc), b.inputs["Base Color"])
    nt.links.new(_math(nt, "MULTIPLY_ADD", win, -0.75, 0.85), b.inputs["Roughness"])
    _mats[name] = m
    return m


def leaf_mat(name, c1, c2, trans=0.3):
    if name in _mats:
        return _mats[name]
    m, nt, b = _node_mat(name)
    co = _coords(nt)
    col = _ramp(nt, _noise(nt, co, 1.4, 3.0).outputs["Fac"], ((0.3, c1), (0.75, c2)))
    nt.links.new(col, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.55
    out = nt.nodes["Material Output"]
    tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
    nt.links.new(col, tr.inputs["Color"])
    mx = nt.nodes.new("ShaderNodeMixShader")
    mx.inputs["Fac"].default_value = trans
    nt.links.new(b.outputs[0], mx.inputs[1])
    nt.links.new(tr.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    _mats[name] = m
    return m


def bark_mat(name, c1, c2, ring=0.12):
    """Palm trunk: grey-brown with the rings left by old frond bases."""
    if name in _mats:
        return _mats[name]
    m, nt, b = _node_mat(name)
    co = _coords(nt)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 1.0 / ring / 6.0
    wave.inputs["Distortion"].default_value = 2.0
    wave.inputs["Detail"].default_value = 3.0
    nt.links.new(co, wave.inputs["Vector"])
    nz = _noise(nt, co, 6.0, 6.0)
    col = _ramp(nt, _math(nt, "MULTIPLY_ADD", wave.outputs["Fac"], 0.6, _math(nt, "MULTIPLY", nz.outputs["Fac"], 0.4)),
                ((0.35, c1), (0.75, c2)))
    nt.links.new(col, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.92
    _bump(nt, b, wave.outputs["Fac"], 0.8, 0.03)
    _mats[name] = m
    return m


def mesh_obj(name, verts, faces, mats, smooth=False, mat_idx=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    for mm in (mats if isinstance(mats, (list, tuple)) else [mats]):
        me.materials.append(mm)
    if mat_idx is not None:
        for p, k in zip(me.polygons, mat_idx):
            p.material_index = k
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    _link(ob)
    return ob


def tube_geo(pts, radii, sides=8):
    """Vertices and quads of a tube along a polyline (cables, trunks, masts)."""
    pts = [Vector(p) for p in pts]
    if not isinstance(radii, (list, tuple)):
        radii = [radii] * len(pts)
    vs, fs = [], []
    n = len(pts)
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
        up = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
        a = t.cross(up).normalized()
        c = t.cross(a)
        for k in range(sides):
            ang = k / sides * math.tau
            vs.append(p + (a * math.cos(ang) + c * math.sin(ang)) * radii[i])
    for i in range(n - 1):
        for k in range(sides):
            k2 = (k + 1) % sides
            fs.append((i * sides + k, i * sides + k2, (i + 1) * sides + k2, (i + 1) * sides + k))
    return vs, fs


def tube(name, pts, radii, m, sides=8, smooth=True):
    vs, fs = tube_geo(pts, radii, sides)
    return mesh_obj(name, vs, fs, m, smooth=smooth)


def catenary(a, b, sag, n=16):
    a, b = Vector(a), Vector(b)
    return [a + (b - a) * (k / n) - Vector((0, 0, sag * 4 * (k / n) * (1 - k / n))) for k in range(n + 1)]


def bunting_line(a, b, sag=None, spacing=0.52):
    """A rope of red, white and blue pennants between two tie points (pole tops, roof corners), sagging."""
    cols = [mat("flag_r", (0.72, 0.05, 0.05), rough=0.5), mat("flag_w", (0.92, 0.92, 0.9), rough=0.5),
            mat("flag_b", (0.04, 0.12, 0.5), rough=0.5)]
    a, b = Vector(a), Vector(b)
    span = (b - a).length
    sag = sag if sag is not None else 0.035 * span + 0.15
    rope = catenary(a, b, sag, 24)
    tube("bunting_rope", rope, 0.011, mat("rope", (0.12, 0.12, 0.12), rough=0.6), sides=5)
    d = (b - a).normalized()
    side = Vector((-d.y, d.x, 0)).normalized()
    rnd = random.Random(int(a.x * 31 + a.y * 17 + b.x * 7))
    vs, fs, idx = [], [], []
    n = max(2, int(span / spacing))
    for k in range(n):
        t0, t1 = (k + 0.12) / n, (k + 0.88) / n

        def at(t):
            return a + (b - a) * t - Vector((0, 0, sag * 4 * t * (1 - t)))
        p0, p1 = at(t0), at(t1)
        tip = (p0 + p1) / 2 - Vector((0, 0, 0.42)) + side * rnd.uniform(-0.12, 0.12) + d * rnd.uniform(-0.05, 0.05)
        base = len(vs)
        vs += [p0, p1, tip]
        fs.append((base, base + 1, base + 2))
        idx.append(k % 3)
    mesh_obj("bunting", vs, fs, cols, mat_idx=idx)


def flag_pole(x, y, h=7.0, m=None):
    """A painted steel pole with a base plate and a ball on top; returns the tie point for bunting."""
    m = m or mat("pole_white", (0.85, 0.85, 0.83), rough=0.35, metal=0.3)
    cyl("flagpole", (x, y, h / 2), 0.085, h, m, r2=0.055, verts=12)
    box("flagpole_base", (x - 0.22, y - 0.22, 0), (x + 0.22, y + 0.22, 0.05), mat("galv", (0.6, 0.62, 0.63), rough=0.4, metal=0.9))
    sphere("flagpole_ball", (x, y, h + 0.08), (0.11, 0.11, 0.11), mat("gold", (0.85, 0.62, 0.22), rough=0.25, metal=1.0))
    return Vector((x, y, h - 0.15))


def light_pole(x, y, h=7.5, dirs=((1, 0),)):
    """Parking-lot light: square steel pole on a concrete pier with shoebox LED heads."""
    steel = mat("pole_bronze", (0.09, 0.085, 0.08), rough=0.45, metal=0.7)
    cyl("lp_pier", (x, y, 0.35), 0.32, 0.7, mat("pier", (0.62, 0.6, 0.57), rough=0.8), verts=16)
    box("lp_pole", (x - 0.08, y - 0.08, 0.7), (x + 0.08, y + 0.08, h), steel)
    lens = mat("lp_lens", (0.95, 0.95, 0.9), rough=0.3, emit=0.6, ecol=(1.0, 0.95, 0.85))
    for dx, dy in dirs:
        ax, ay = x + dx * 1.1, y + dy * 1.1
        box("lp_arm", (min(x, ax) - 0.04, min(y, ay) - 0.04, h - 0.18), (max(x, ax) + 0.04, max(y, ay) + 0.04, h - 0.08), steel)
        hx, hy = (0.42, 0.22) if dx else (0.22, 0.42)
        cx, cy = x + dx * 1.45, y + dy * 1.45
        box("lp_head", (cx - hx, cy - hy, h - 0.25), (cx + hx, cy + hy, h - 0.05), steel, bevel=0.02)
        box("lp_lens", (cx - hx + 0.04, cy - hy + 0.04, h - 0.27), (cx + hx - 0.04, cy + hy - 0.04, h - 0.25), lens)


def palm(loc, h=9.0, seed=0, kind="date"):
    """A palm: curved ringed trunk and a crown of pinnate fronds with a few dead ones hanging under it: a stout
    date palm, or for kind "fan" the slim, taller-looking queen palm of the Southern California streets."""
    rnd = random.Random(seed)
    loc = Vector(loc)
    fan = kind == "fan"
    lean_dir = Vector((math.cos(rnd.uniform(0, math.tau)), math.sin(rnd.uniform(0, math.tau)), 0))
    lean = rnd.uniform(0.03, 0.09) * h
    pts, radii = [], []
    r0 = 0.2 if fan else 0.36
    for k in range(15):
        t = k / 14
        pts.append(loc + lean_dir * lean * t ** 1.7 + Vector((0, 0, h * t)))
        flare = 1.0 + 0.6 * max(0.0, 1 - t * 9)
        radii.append(r0 * flare * (1 - 0.25 * t) * (1.25 if not fan and t > 0.9 else 1.0))
    trunk = tube("palm_trunk", pts, radii, bark_mat("bark_fan" if fan else "bark_date", (0.28, 0.24, 0.2), (0.48, 0.42, 0.34),
                                                    ring=0.09 if fan else 0.16), sides=12)
    top = pts[-1]
    green = leaf_mat("palm_leaf", (0.06, 0.16, 0.035), (0.2, 0.32, 0.07))
    dead = leaf_mat("palm_dead", (0.3, 0.22, 0.12), (0.5, 0.4, 0.24), trans=0.1)
    vs, fs, idx = [], [], []

    def add_tri(a, b, c, k):
        base = len(vs)
        vs.extend((a, b, c))
        fs.append((base, base + 1, base + 2))
        idx.append(k)

    def frond(az, elev, length, k, leaflets=26, droop=0.18):
        hd = Vector((math.cos(az), math.sin(az), 0))
        sd = Vector((-hd.y, hd.x, 0))
        prev = top
        rib = []
        for i in range(leaflets + 1):
            s = (i / leaflets) * length
            p = top + hd * (math.cos(elev) * s) + Vector((0, 0, math.sin(elev) * s - droop * s * s))
            rib.append(p)
        for i in range(1, leaflets + 1):
            s = i / leaflets
            p, q = rib[i - 1], rib[i]
            along = (q - p).normalized()
            ll = (0.85 * math.sin(math.pi * min(1.0, s * 1.08)) ** 0.6 + 0.12) * length / 4.0
            if s < 0.12:
                continue
            for side in (-1, 1):
                # leaflets angle forward and fold up into a V, then hang a little
                dirv = (sd * side * 0.8 + along * 0.55 + Vector((0, 0, 0.25 - 0.5 * s))).normalized()
                w = along * 0.075 * length / 4.0
                tip = p + dirv * ll + Vector((0, 0, -0.08 * ll))
                add_tri(p - w, p + w, tip, k)
        # rib itself
        rv, rf = tube_geo(rib, [0.04 * (1 - j / (len(rib))) + 0.01 for j in range(len(rib))], 4)
        base = len(vs)
        vs.extend(rv)
        for f in rf:
            fs.append(tuple(base + v for v in f))
            idx.append(k)

    n = 18 if fan else 22
    for i in range(n):
        ring = i % 3
        if fan:
            # queen palm: a slim trunk and long, soft, drooping fronds
            elev = math.radians((45, 12, -22)[ring] + rnd.uniform(-8, 8))
            fl = rnd.uniform(3.0, 3.6)
            droop = (0.13, 0.2, 0.26)[ring]
        else:
            elev = math.radians((55, 20, -15)[ring] + rnd.uniform(-10, 10))
            fl = h * 0.42 + rnd.uniform(-0.4, 0.4) if h < 9 else rnd.uniform(3.6, 4.4)
            droop = (0.09, 0.16, 0.22)[ring]
        frond(i / n * math.tau + ring * 0.35 + rnd.uniform(-0.12, 0.12), elev, fl, 0, leaflets=34, droop=droop)
    for i in range(5 if fan else 4):
        frond(rnd.uniform(0, math.tau), math.radians(-65), 2.4, 1, leaflets=14, droop=0.05)
    crown = mesh_obj("palm_crown", vs, fs, [green, dead], mat_idx=idx)
    sphere("palm_head", top, (radii[-1] * 1.1, radii[-1] * 1.1, 0.45), bark_mat("bark_date", (0.28, 0.24, 0.2), (0.48, 0.42, 0.34)), seg=12)
    return trunk


def shrub(x, y, r=0.7, h=None, seed=0, m=None, z=0.0):
    """A leafy bush: a few lumpy displaced spheres."""
    rnd = random.Random(seed or int(x * 13 + y * 7))
    m = m or leaf_mat("shrub_leaf", (0.04, 0.12, 0.03), (0.13, 0.24, 0.06), trans=0.15)
    h = h or r * 1.2
    tex = bpy.data.textures.get("shrub_clouds") or bpy.data.textures.new("shrub_clouds", "CLOUDS")
    tex.noise_scale = 0.18
    for k in range(3):
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0)
        ob = _bm_obj("shrub", bm, m, (x + rnd.uniform(-r, r) * 0.4, y + rnd.uniform(-r, r) * 0.4, z + h * 0.5), smooth=True)
        ob.scale = (r * rnd.uniform(0.7, 1.0), r * rnd.uniform(0.7, 1.0), h * 0.5 * rnd.uniform(0.8, 1.0))
        md = ob.modifiers.new("d", "DISPLACE")
        md.texture = tex
        md.strength = 0.35
        md.texture_coords = "GLOBAL"


def hip_roof(name, x0, y0, x1, y1, z, h, m, over=0.4):
    x0, y0, x1, y1 = x0 - over, y0 - over, x1 + over, y1 + over
    if x1 - x0 >= y1 - y0:
        r = (y1 - y0) / 2
        ridge = [(x0 + r, (y0 + y1) / 2, z + h), (x1 - r, (y0 + y1) / 2, z + h)]
        vs = [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)] + ridge
        fs = [(0, 1, 5, 4), (1, 2, 5), (2, 3, 4, 5), (3, 0, 4)]
    else:
        r = (x1 - x0) / 2
        ridge = [((x0 + x1) / 2, y0 + r, z + h), ((x0 + x1) / 2, y1 - r, z + h)]
        vs = [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)] + ridge
        fs = [(0, 1, 4), (1, 2, 5, 4), (2, 3, 5), (3, 0, 4, 5)]
    return mesh_obj(name, vs, fs, m)


def tile_mat():
    if "roof_tile" in _mats:
        return _mats["roof_tile"]
    m, nt, b = _node_mat("roof_tile")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(_coords(nt), sep.inputs[0])
    wave = _math(nt, "SINE", _math(nt, "MULTIPLY", _math(nt, "ADD", sep.outputs["X"], sep.outputs["Y"]), 25.0))
    nz = _noise(nt, _coords(nt), 3.0, 4.0)
    col = _ramp(nt, nz.outputs["Fac"], ((0.3, (0.42, 0.13, 0.06)), (0.7, (0.6, 0.24, 0.12))))
    nt.links.new(col, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.7
    _bump(nt, b, wave, 0.3, 0.02)
    _mats["roof_tile"] = m
    return m


SHOP_COLOURS = [(0.86, 0.8, 0.68), (0.78, 0.62, 0.48), (0.62, 0.72, 0.74), (0.9, 0.88, 0.82), (0.72, 0.5, 0.38),
                (0.8, 0.76, 0.56), (0.55, 0.6, 0.52)]


def shop_block(x0, x1, y0, depth, floors, wall, shops, sides=(), seed=0, trim=(0.15, 0.15, 0.16), tile=False,
               face=-1, side_sign=None):
    """A neighbouring commercial building with its front on the y = y0 side (face -1: front faces -y, toward the
    street). shops: (fraction of the frontage, sign text, sign colour, awning colours or None). sides: "w" / "e" put
    windows on those end walls."""
    rnd = random.Random(seed)
    ST = 3.6
    H = floors * ST + 0.7
    stucco = noise_mat("stucco_%d" % seed, wall, tuple(min(1, c * 1.08) for c in wall), 18, 0.85, bump=0.12, macro=0.15)
    trimm = mat("trim_%d" % seed, trim, rough=0.5)
    alu = mat("alu", (0.08, 0.08, 0.09), rough=0.35, metal=0.8)
    win = mat("win_glass", (0.02, 0.03, 0.04), rough=0.05)
    yb = y0 + depth if face < 0 else y0 - depth
    ylo, yhi = min(y0, yb), max(y0, yb)
    box("nb_body", (x0, ylo, 0), (x1, yhi, H), stucco)
    out = face  # the front's outward normal along y
    fy = y0 + out * 0.0

    def fbox(name, xa, xb, za, zb, d0, d1, m):
        """A box on the front, d0..d1 metres out from the wall."""
        ya, yb2 = fy + out * d0, fy + out * d1
        return box(name, (xa, min(ya, yb2), za), (xb, max(ya, yb2), zb), m)
    # coping round the parapet and a cornice band between floors
    for name, za, zb, d in (("nb_coping", H - 0.02, H + 0.12, 0.12), ("nb_band", ST - 0.1, ST + 0.15, 0.08)):
        box(name, (x0 - d, ylo - d, za), (x1 + d, yhi + d, zb), trimm)
    if tile:
        box("nb_parapet_fill", (x0, ylo, H), (x1, yhi, H + 0.01), stucco)
        hip_roof("nb_roof", x0, ylo, x1, yhi, H + 0.12, min(3.0, (yhi - ylo) * 0.3), tile_mat())
    else:
        for k in range(rnd.randint(1, 3)):
            ax = rnd.uniform(x0 + 1.5, x1 - 2.5)
            ay = rnd.uniform(ylo + 2, yhi - 2)
            box("nb_ac", (ax, ay, H - 0.5), (ax + 1.4, ay + 1.0, H + 0.6), mat("ac_unit", (0.7, 0.7, 0.68), rough=0.5, metal=0.3), bevel=0.03)
    # storefronts
    x = x0 + 0.4
    total = x1 - x0 - 0.8
    for frac_, sign, sign_col, awning in shops:
        w = total * frac_
        sx0, sx1 = x, x + w
        x += w
        fbox("nb_glass", sx0 + 0.25, sx1 - 0.25, 0.45, 2.9, 0.0, 0.06, win)
        fbox("nb_kick", sx0 + 0.25, sx1 - 0.25, 0.0, 0.45, 0.0, 0.1, alu)
        n = max(2, int((sx1 - sx0 - 0.5) / 1.6))
        for i in range(n + 1):
            mx = sx0 + 0.25 + (sx1 - sx0 - 0.5) * i / n
            fbox("nb_mullion", mx - 0.04, mx + 0.04, 0.0, 2.95, 0.0, 0.1, alu)
        fbox("nb_transom", sx0 + 0.25, sx1 - 0.25, 2.25, 2.32, 0.0, 0.1, alu)
        fbox("nb_head", sx0 + 0.2, sx1 - 0.2, 2.9, 3.0, 0.0, 0.12, alu)
        # a lit shop interior glimpse: a pale back panel and a counter behind the glass is too costly; posters instead
        for i in range(rnd.randint(1, 3)):
            px = rnd.uniform(sx0 + 0.5, sx1 - 1.2)
            fbox("nb_poster", px, px + 0.6, 1.2, 2.0, 0.07, 0.075, mat("poster_%d" % (i % 3), [(0.85, 0.75, 0.2), (0.75, 0.15, 0.1), (0.9, 0.9, 0.88)][i % 3], rough=0.6))
        if awning:
            canvas = stripe_mat("awning_%s_%s" % awning, awning[0], awning[1], 0.45, "X")
            ya, yb2 = fy, fy + out * 1.3
            vs = [(sx0 + 0.1, ya, 3.25), (sx1 - 0.1, ya, 3.25), (sx1 - 0.1, yb2, 2.75), (sx0 + 0.1, yb2, 2.75),
                  (sx1 - 0.1, yb2, 2.45), (sx0 + 0.1, yb2, 2.45)]
            mesh_obj("nb_awning", vs, [(0, 1, 2, 3), (3, 2, 4, 5)], canvas)
        if sign:
            panel = mat("sign_panel_%d" % (sum(map(ord, sign)) % 5), [(0.95, 0.95, 0.92), (0.08, 0.1, 0.16), (0.6, 0.08, 0.06), (0.9, 0.75, 0.2), (0.1, 0.3, 0.2)][sum(map(ord, sign)) % 5], rough=0.4)
            fbox("nb_sign", sx0 + 0.4, sx1 - 0.4, 3.35, 4.15, 0.0, 0.12, panel)
            ty = fy + out * 0.14
            tsize = min(0.55, (sx1 - sx0 - 1.0) / max(4, len(sign)) * 1.5)
            text("nb_sign_txt", sign, ((sx0 + sx1) / 2, ty, 3.75 - tsize * 0.35), tsize, mat("sign_ink_%s" % (sign_col,), sign_col, rough=0.4),
                 rot=(math.pi / 2, 0, 0 if out < 0 else math.pi), extrude=0.02)
    # upper floor windows on the front
    for f in range(1, floors):
        z0 = f * ST + 0.8
        n = max(1, int((x1 - x0) / 2.8))
        for i in range(n):
            cx = x0 + (x1 - x0) * (i + 0.5) / n
            fbox("nb_win", cx - 0.7, cx + 0.7, z0, z0 + 1.6, 0.0, 0.04, win)
            fbox("nb_frame", cx - 0.78, cx + 0.78, z0 - 0.08, z0, 0.0, 0.14, trimm)
            fbox("nb_frame", cx - 0.78, cx + 0.78, z0 + 1.6, z0 + 1.68, 0.0, 0.08, trimm)
            fbox("nb_mull", cx - 0.03, cx + 0.03, z0, z0 + 1.6, 0.0, 0.06, trimm)
    # end walls: punched windows, a downpipe and an electrical box
    for s in sides:
        xs = x1 if s == "e" else x0
        o = 1 if s == "e" else -1
        n = max(1, int((yhi - ylo) / 3.2))
        for f in range(floors):
            z0 = f * ST + (1.0 if f == 0 else 0.8)
            for i in range(n):
                cy = ylo + (yhi - ylo) * (i + 0.5) / n
                if f == 0 and i % 2:
                    continue
                box("nb_win", (min(xs, xs + o * 0.04), cy - 0.7, z0), (max(xs, xs + o * 0.04), cy + 0.7, z0 + 1.5), win)
                box("nb_sill", (min(xs, xs + o * 0.14), cy - 0.78, z0 - 0.08), (max(xs, xs + o * 0.14), cy + 0.78, z0), trimm)
        box("nb_pipe", (min(xs, xs + o * 0.14), ylo + 0.4, 0), (max(xs, xs + o * 0.14), ylo + 0.52, H), trimm)
        box("nb_meter", (min(xs, xs + o * 0.2), yhi - 2.5, 1.0), (max(xs, xs + o * 0.2), yhi - 1.8, 1.9), mat("galv", (0.6, 0.62, 0.63), rough=0.4, metal=0.9))
        if side_sign:
            body, ink, panel = side_sign
            zc = H - 1.4
            box("nb_side_sign", (min(xs, xs + o * 0.12), ylo + 1.2, zc - 0.8), (max(xs, xs + o * 0.12), yhi - 1.2, zc + 0.8), mat("side_panel_%d" % seed, panel, rough=0.5))
            text("nb_side_txt", body, (xs + o * 0.14, (ylo + yhi) / 2, zc - 0.35), 1.0, mat("side_ink_%d" % seed, ink, rough=0.4),
                 rot=(math.pi / 2, 0, math.pi / 2 * o), extrude=0.02)
    return H


# ---------------------------------------------------------------- office furnishing (Marco's screen background)

def wall_box(axis, plane, a0, a1, z0, z1, d0, d1, out, m, name="wall_item"):
    """A box against a wall: axis "x" is a wall along x at y = plane, "y" a wall along y at x = plane; d0..d1 is the
    distance out from the wall into the room, out (+1 / -1) the room side."""
    p0, p1 = plane + out * d0, plane + out * d1
    if axis == "x":
        return box(name, (min(a0, a1), min(p0, p1), z0), (max(a0, a1), max(p0, p1), z1), m)
    return box(name, (min(p0, p1), min(a0, a1), z0), (max(p0, p1), max(a0, a1), z1), m)



def walnut():
    return noise_mat("walnut_office", (0.17, 0.09, 0.05), (0.28, 0.16, 0.09), 6, 0.35, stretch=(1, 14, 1))


def framed_photo(axis, plane, out, ac, zc, w, h, seed, frame=None):
    """A framed print of a car on a wall: frame, white mat, then sky, road and a car in profile."""
    rnd = random.Random(seed)
    frame = frame or (walnut() if seed % 2 else mat("frame_black", (0.02, 0.02, 0.02), rough=0.3))
    wall_box(axis, plane, ac - w / 2, ac + w / 2, zc - h / 2, zc + h / 2, 0.0, 0.035, out, frame, "frame")
    wall_box(axis, plane, ac - w / 2 + 0.04, ac + w / 2 - 0.04, zc - h / 2 + 0.04, zc + h / 2 - 0.04, 0.0, 0.04, out,
             mat("photo_mat", (0.92, 0.91, 0.88), rough=0.8), "mount")
    pw, ph = w - 0.2, h - 0.2
    a0, z0 = ac - pw / 2, zc - ph / 2
    sky = mat("photo_sky%d" % (seed % 3), [(0.35, 0.55, 0.8), (0.8, 0.55, 0.35), (0.5, 0.6, 0.7)][seed % 3], rough=0.4)
    wall_box(axis, plane, a0, a0 + pw, z0 + ph * 0.38, z0 + ph, 0.0, 0.043, out, sky, "photo")
    wall_box(axis, plane, a0, a0 + pw, z0, z0 + ph * 0.38, 0.0, 0.043, out, mat("photo_road", (0.12, 0.12, 0.13), rough=0.5), "photo")
    hill = mat("photo_hill", (0.42, 0.36, 0.22), rough=0.8)
    wall_box(axis, plane, a0, a0 + pw * 0.55, z0 + ph * 0.38, z0 + ph * 0.55, 0.0, 0.045, out, hill, "photo")
    paint = mat("photo_car%d" % (seed % 5), [(0.7, 0.05, 0.04), (0.9, 0.9, 0.9), (0.05, 0.05, 0.06), (0.9, 0.6, 0.05), (0.1, 0.25, 0.6)][seed % 5], rough=0.3)
    cx = a0 + pw * rnd.uniform(0.45, 0.55)
    cl = pw * 0.62
    wall_box(axis, plane, cx - cl / 2, cx + cl / 2, z0 + ph * 0.28, z0 + ph * 0.44, 0.0, 0.05, out, paint, "photo_car")
    wall_box(axis, plane, cx - cl * 0.25, cx + cl * 0.2, z0 + ph * 0.44, z0 + ph * 0.56, 0.0, 0.05, out, mat("photo_glass", (0.05, 0.07, 0.1), rough=0.2), "photo_car")
    for k in (-0.32, 0.3):
        wall_box(axis, plane, cx + cl * k - pw * 0.06, cx + cl * k + pw * 0.06, z0 + ph * 0.2, z0 + ph * 0.32, 0.0, 0.052, out,
                 mat("photo_tyre", (0.02, 0.02, 0.02), rough=0.6), "photo_car")


def bookcase(axis, plane, out, a0, a1, h, seed, depth=0.38):
    """A walnut bookcase with books, binders and a few ornaments on its shelves."""
    rnd = random.Random(seed)
    w = walnut()
    wall_box(axis, plane, a0, a1, 0.0, h, 0.0, 0.03, out, w, "bc_back")
    for a in (a0, a1 - 0.04):
        wall_box(axis, plane, a, a + 0.04, 0.0, h, 0.0, depth, out, w, "bc_side")
    shelves = [0.08 + k * (h - 0.12) / 5 for k in range(6)]
    cols = [(0.45, 0.08, 0.06), (0.08, 0.15, 0.32), (0.75, 0.6, 0.3), (0.12, 0.25, 0.15), (0.85, 0.83, 0.78), (0.08, 0.08, 0.08)]
    for i, z in enumerate(shelves):
        wall_box(axis, plane, a0, a1, z - 0.03, z, 0.0, depth, out, w, "bc_shelf")
        if i == len(shelves) - 1:
            continue
        a = a0 + 0.06
        top = shelves[i + 1] - 0.05
        while a < a1 - 0.1:
            if rnd.random() < 0.05:
                # an ornament: a vase, a trophy or a model car's box
                kind = rnd.random()
                pos_a, d = a + 0.12, depth * 0.5
                p = (plane + out * d, pos_a) if axis == "y" else (pos_a, plane + out * d)
                if kind < 0.5:
                    cyl("vase", (p[0], p[1], z + 0.1), 0.05, 0.2, mat("vase", (0.85, 0.83, 0.78), rough=0.2), r2=0.05, verts=16)
                else:
                    cyl("trophy", (p[0], p[1], z + 0.12), 0.05, 0.24, mat("gold", (0.85, 0.62, 0.22), rough=0.25, metal=1.0), r2=0.08, verts=12)
                a += 0.3
                continue
            bw = rnd.uniform(0.025, 0.06)
            bh = rnd.uniform(0.6, 0.95) * (top - z)
            wall_box(axis, plane, a, a + bw, z, z + bh, 0.04, depth - rnd.uniform(0.02, 0.08), out,
                     mat("book_%d" % rnd.randrange(len(cols)), cols[rnd.randrange(len(cols))], rough=0.6), "book")
            a += bw + 0.004
            if rnd.random() < 0.08:
                a += rnd.uniform(0.1, 0.25)


def blinds(axis, plane, out, a0, a1, ztop, drop, d=0.12):
    """Aluminium slat blinds lowered part way down a window."""
    m = mat("blind", (0.88, 0.87, 0.84), rough=0.45, metal=0.1)
    wall_box(axis, plane, a0 - 0.03, a1 + 0.03, ztop - 0.06, ztop, d - 0.03, d + 0.05, out, m, "blind_rail")
    z = ztop - 0.08
    while z > ztop - drop:
        wall_box(axis, plane, a0, a1, z - 0.004, z, d - 0.025, d + 0.025, out, m, "blind_slat")
        z -= 0.045
    wall_box(axis, plane, a0, a1, z - 0.02, z, d - 0.03, d + 0.03, out, m, "blind_bar")


def floor_plant(x, y, h=1.6, z=0.0):
    """A potted fiddle-leaf style plant: a tapered pot and a column of leafy clumps."""
    cyl("pot", (x, y, z + 0.25), 0.26, 0.5, mat("pot_cer", (0.85, 0.84, 0.8), rough=0.3), r2=0.2, verts=20)
    leaf = leaf_mat("house_plant", (0.04, 0.14, 0.04), (0.12, 0.26, 0.07), trans=0.2)
    cyl("stem", (x, y, z + h * 0.45), 0.02, h * 0.6, mat("stem", (0.25, 0.18, 0.1)), verts=6)
    rnd = random.Random(int(x * 7 + y * 3))
    for k in range(9):
        t = k / 8
        r = 0.2 - 0.06 * t
        spread = 0.28 * (1 - 0.5 * t)
        shrub(x + rnd.uniform(-spread, spread), y + rnd.uniform(-spread, spread), r, r * 1.5, seed=rnd.randrange(999), m=leaf,
              z=z + h * (0.45 + 0.5 * t) - r)


def office_desk_props(x0, x1, y, z, face, seed):
    """Second monitor, desk lamp, papers and a nameplate on an office desk (face: the side the sitter faces, -1/+1 y)."""
    rnd = random.Random(seed)
    scr = mat("screen", (0.02, 0.05, 0.1), rough=0.1, emit=0.6, ecol=(0.3, 0.55, 0.9))
    dark = mat("trim1", (0.12, 0.13, 0.15), rough=0.5)
    paper = mat("paper", (0.93, 0.93, 0.9), rough=0.8)
    for i in range(3):
        px = rnd.uniform(x0 + 0.3, x1 - 0.6)
        box("paper", (px, y - 0.15, z + 0.001 + i * 0.002), (px + 0.21, y + 0.15, z + 0.004 + i * 0.002), paper)
    lx = x1 - 0.25
    cyl("lamp_base", (lx, y + face * -0.2, z + 0.01), 0.08, 0.02, dark, verts=16)
    cyl("lamp_arm", (lx, y + face * -0.2, z + 0.25), 0.012, 0.5, dark, verts=6)
    cyl("lamp_shade", (lx - 0.1, y + face * -0.2, z + 0.5), 0.09, 0.14, mat("brass", (0.8, 0.6, 0.3), rough=0.25, metal=1.0), r2=0.04, verts=16)
    box("nameplate", (x0 + 0.3, y + face * 0.32 - 0.03, z), (x0 + 0.7, y + face * 0.32 + 0.03, z + 0.07), mat("brass", (0.8, 0.6, 0.3), rough=0.25, metal=1.0))
    return scr


def build_office_t1():
    """The corner-lot sales office: warm wainscot and taupe walls, framed car prints, blinds, a credenza, a plant."""
    taupe = mat("wall_taupe", (0.55, 0.47, 0.38), rough=0.85)
    w = walnut()
    x0, x1, yf = OX0 + 0.2, OX1 - 0.2, OY0 + 0.2
    # west wall: taupe above a walnut wainscot and chair rail, whiteboard on it
    wall_box("y", x0, yf, OY1 - 0.2, TZ, 1.0, 0.0, 0.015, 1, w, "wainscot")
    wall_box("y", x0, yf, OY1 - 0.2, 1.0, OH - 0.6, 0.0, 0.005, 1, taupe, "accent")
    wall_box("y", x0, yf, OY1 - 0.2, 0.98, 1.04, 0.0, 0.03, 1, w, "chair_rail")
    # front wall: wainscot under the windows and round the door
    for a, b in ((x0, -6.4), (-5.2, x1)):
        wall_box("x", yf, a, b, TZ, 0.78, 0.0, 0.015, 1, w, "wainscot")
        wall_box("x", yf, a, b, 0.76, 0.8, 0.0, 0.03, 1, w, "chair_rail")
    # credenza under the whiteboard with binders, a trophy and a little plant
    wall_box("y", x0, 1.5, 4.3, TZ, TZ + 0.72, 0.0, 0.45, 1, w, "credenza")
    wall_box("y", x0, 1.48, 4.32, TZ + 0.72, TZ + 0.75, 0.0, 0.47, 1, w, "credenza_top")
    rnd = random.Random(4)
    yy = 1.6
    for k in range(9):
        wall_box("y", x0, yy, yy + 0.06, TZ + 0.75, TZ + 1.05, 0.08, 0.36, 1,
                 mat("binder_%d" % (k % 3), [(0.08, 0.15, 0.32), (0.45, 0.08, 0.06), (0.1, 0.1, 0.1)][k % 3], rough=0.6), "binder")
        yy += 0.065
    cyl("trophy", (x0 + 0.22, 3.2, TZ + 0.88), 0.05, 0.26, mat("gold", (0.85, 0.62, 0.22), rough=0.25, metal=1.0), r2=0.08, verts=12)
    cyl("small_pot", (x0 + 0.22, 3.9, TZ + 0.85), 0.1, 0.2, mat("pot_cer", (0.85, 0.84, 0.8), rough=0.3), verts=16)
    shrub(x0 + 0.22, 3.9, 0.2, 0.3, seed=7, m=leaf_mat("house_plant", (0.04, 0.14, 0.04), (0.12, 0.26, 0.07), trans=0.2), z=TZ + 0.92)
    # framed car prints above the whiteboard and beside the door
    for k, yc in enumerate((1.85, 2.9, 3.95)):
        framed_photo("y", x0, 1, yc, 3.08, 0.8, 0.5, 20 + k)
    framed_photo("x", yf, 1, -7.0, 1.75, 0.75, 1.0, 31)
    # blinds part way down the two windows
    for a, b in ((-11.2, -7.6), (-4.4, -2.8)):
        blinds("x", OY0, 1, a, b, 2.6, 0.55, d=0.25)
    floor_plant(-6.95, -0.35, 1.7, TZ)
    office_desk_props(-9.6, -6.3, 4.05, TZ + 0.8, 1, 5)
    box("o_monitor2", (-9.45, 4.12, TZ + 0.85), (-8.55, 4.16, TZ + 1.4), mat("screen", (0.02, 0.05, 0.1), rough=0.1, emit=0.6, ecol=(0.3, 0.55, 0.9)))
    box("o_rug", (-10.4, 1.6, TZ + 0.01), (-5.6, 6.2, TZ + 0.02), noise_mat("rug1", (0.42, 0.32, 0.24), (0.52, 0.42, 0.32), 40, 0.95, bump=0.2))


def build_office_t2():
    """The street showroom's office: carpet, a bookcase, car prints, blinds, a plant and a proper desk setup."""
    w = walnut()
    taupe = mat("wall_taupe", (0.55, 0.47, 0.38), rough=0.85)
    box("b2_office_carpet", (-10.0, 8.05, 0.05), (-5.6, 12.0, 0.06), noise_mat("carpet2", (0.3, 0.26, 0.22), (0.37, 0.32, 0.26), 220, 0.95, bump=0.3))
    wall_box("y", -10.0, 8.05, 12.0, 0.05, 4.9, 0.0, 0.005, 1, taupe, "accent")
    wall_box("y", -10.0, 8.05, 12.0, 0.05, 1.0, 0.0, 0.015, 1, w, "wainscot")
    wall_box("y", -10.0, 8.05, 12.0, 0.98, 1.04, 0.0, 0.03, 1, w, "chair_rail")
    bookcase("y", -10.0, 1, 8.15, 9.75, 2.1, 41)
    for k, yc in enumerate((8.55, 9.4)):
        framed_photo("y", -10.0, 1, yc, 2.75, 0.7, 0.5, 42 + k)
    framed_photo("x", 12.0, -1, -8.0, 1.95, 1.3, 0.85, 45)
    blinds("x", 12.0, -1, -7.0, -5.6, 3.0, 0.7, d=0.08)
    cyl("small_pot", (-9.75 + 0.2, 9.0, 2.2), 0.1, 0.2, mat("pot_cer", (0.85, 0.84, 0.8), rough=0.3), verts=16)
    shrub(-9.55, 9.0, 0.22, 0.32, seed=8, m=leaf_mat("house_plant", (0.04, 0.14, 0.04), (0.12, 0.26, 0.07), trans=0.2), z=2.27)
    box("b2_exec_top", (-9.5, 10.1, 0.76), (-7.3, 11.1, 0.8), w)
    office_desk_props(-9.5, -7.3, 10.6, 0.8, 1, 6)
    box("b2_exec_mon2", (-9.35, 10.78, 0.85), (-8.65, 10.82, 1.3), mat("screen", (0.02, 0.05, 0.1), rough=0.1, emit=0.6, ecol=(0.3, 0.55, 0.9)))


def build_office_t3():
    """Marco's glass office on the harbour: walnut slat wall with a big print, a full bookcase, a second screen."""
    w = walnut()
    bookcase("y", -15.0, 1, 9.3, 12.3, 2.6, 51, depth=0.42)
    for k in range(40):
        y = 12.55 + k * 0.08
        wall_box("y", -15.0, y, y + 0.05, 0.07, 3.4, 0.0, 0.05, 1, w, "slat")
    framed_photo("y", -15.0, 1, 14.15, 1.75, 1.9, 1.15, 54, frame=mat("frame_black", (0.02, 0.02, 0.02), rough=0.3))
    framed_photo("y", -15.0, 1, 10.8, 3.2, 1.2, 0.7, 53)
    box("monitor2", (-10.9, 12.85, 0.85), (-10.3, 12.9, 1.35), mat("screen", (0.02, 0.05, 0.1), rough=0.1, emit=0.6, ecol=(0.3, 0.55, 0.9)))
    office_desk_props(-13.3, -10.1, 12.7, 0.81, 1, 7)
    floor_plant(-8.75, 15.1, 1.9, 0.07)


def boat(x, y, length, kind, rnd, bow=1):
    """A moored boat lying along y with its bow toward +y (bow=1) or -y: a lofted hull with a sheer line, a coloured
    boot stripe and antifouling, then a cabin, and a mast with rigging (sail) or a flybridge (motor)."""
    beam = length * rnd.uniform(0.3, 0.34)
    wl = -0.6
    keel, deck = wl - 0.45, wl + length * 0.085 + 0.25
    hullc = rnd.choice([(0.92, 0.92, 0.9)] * 4 + [(0.06, 0.1, 0.2), (0.82, 0.78, 0.68)])
    stripe = rnd.choice([(0.04, 0.12, 0.35), (0.05, 0.05, 0.06), (0.55, 0.06, 0.05), (0.1, 0.35, 0.45)])
    key = "hull_%d" % (hash((hullc, stripe)) % 10000)
    if key in _mats:
        hm = _mats[key]
    else:
        hm, nt, b = _node_mat(key)
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(_coords(nt), sep.inputs[0])
        z = sep.outputs["Z"]
        col = _mix(nt, _math(nt, "LESS_THAN", z, wl + 0.12), hullc, (0.25, 0.05, 0.04) if rnd.random() < 0.5 else (0.04, 0.06, 0.12))
        band = _math(nt, "MULTIPLY", _math(nt, "GREATER_THAN", z, deck - 0.32), _math(nt, "LESS_THAN", z, deck - 0.2))
        col = _mix(nt, band, col, stripe)
        nt.links.new(col, b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.12
        b.inputs["Coat Weight"].default_value = 0.6
        _mats[key] = hm
    secs = 14
    vs, fs = [], []
    across = [-1.0, -0.94, -0.6, 0.0, 0.6, 0.94, 1.0]
    for i in range(secs + 1):
        t = i / secs
        hb = beam / 2 * (1 - (max(0.0, t - 0.5) / 0.5) ** 1.7) * (0.92 + 0.08 * min(1, t * 5))
        hb = max(hb, 0.02)
        sheer = deck + 0.35 * (max(0.0, t - 0.6) / 0.4) ** 2
        kz = keel + (wl + 0.1 - keel) * (max(0.0, t - 0.75) / 0.25) ** 1.5
        for a in across:
            if abs(a) == 1.0:
                zz = sheer
            elif abs(a) > 0.9:
                zz = wl + 0.1
            elif abs(a) > 0.5:
                zz = kz + 0.18
            else:
                zz = kz
            vs.append((x + a * hb, y + bow * (t - 0.5) * length, zz))
    na = len(across)
    for i in range(secs):
        for j in range(na - 1):
            fs.append((i * na + j, i * na + j + 1, (i + 1) * na + j + 1, (i + 1) * na + j))
        fs.append((i * na + na - 1, i * na, (i + 1) * na, (i + 1) * na + na - 1))   # deck
    fs.append(tuple(range(na))[::-1])  # transom
    mesh_obj("hull", vs, fs, hm, smooth=True)
    white = mat("gelcoat", (0.9, 0.9, 0.88), rough=0.2)
    dark = mat("boat_window", (0.02, 0.025, 0.03), rough=0.05)
    canvas = mat("boat_canvas_%d" % (rnd.random() < 0.5), rnd.choice([(0.04, 0.1, 0.28), (0.08, 0.2, 0.3)]), rough=0.8)
    yc = y - bow * length * 0.05
    cl = length * (0.35 if kind == "sail" else 0.45)
    cw = beam * 0.62
    ch = 0.55 if kind == "sail" else 1.0
    box("cabin", (x - cw / 2, yc - cl / 2, deck - 0.05), (x + cw / 2, yc + cl / 2, deck + ch), white, bevel=0.12)
    box("cabin_win", (x - cw / 2 - 0.02, yc - cl * 0.35, deck + ch * 0.45), (x + cw / 2 + 0.02, yc + cl * 0.4, deck + ch * 0.8), dark, bevel=0.03)
    rail = mat("rail", (0.75, 0.75, 0.76), rough=0.3, metal=1)
    if kind == "sail":
        mz = rnd.uniform(10, 14)
        mx, my = x, yc + bow * cl * 0.45
        tube("mast", [(mx, my, deck), (mx, my, deck + mz)], [0.07, 0.05], rail, sides=8)
        tube("boom", [(mx, my, deck + 1.3), (mx, my - bow * length * 0.4, deck + 1.35)], 0.05, rail, sides=6)
        tube("sail_cover", [(mx, my - bow * 0.2, deck + 1.5), (mx, my - bow * length * 0.38, deck + 1.47)], [0.2, 0.1], canvas, sides=8)
        wire = mat("rigging", (0.2, 0.2, 0.2), rough=0.4, metal=0.8)
        tip = (mx, my, deck + mz)
        tube("forestay", [tip, (x, y + bow * length * 0.5, deck + 0.3)], 0.012, wire, sides=4)
        tube("backstay", [tip, (x, y - bow * length * 0.5, deck + 0.4)], 0.012, wire, sides=4)
        for s in (-1, 1):
            tube("shroud", [(mx, my, deck + mz * 0.75), (x + s * beam * 0.45, my, deck)], 0.008, wire, sides=4)
        box("spreader", (mx - beam * 0.35, my - 0.03, deck + mz * 0.55), (mx + beam * 0.35, my + 0.03, deck + mz * 0.55 + 0.05), rail)
    else:
        fl = cl * 0.6
        box("flybridge", (x - cw * 0.45, yc - fl / 2, deck + ch), (x + cw * 0.45, yc + fl / 2, deck + ch + 0.5), white, bevel=0.08)
        box("bimini", (x - cw * 0.5, yc - fl * 0.55, deck + ch + 1.6), (x + cw * 0.5, yc + fl * 0.35, deck + ch + 1.7), canvas, bevel=0.05)
        for sx in (-1, 1):
            for sy in (-1, 1):
                tube("bimini_post", [(x + sx * cw * 0.45, yc + sy * fl * 0.3, deck + ch + 0.5), (x + sx * cw * 0.45, yc + sy * fl * 0.3, deck + ch + 1.6)], 0.02, rail, sides=4)
        tube("antenna", [(x, yc, deck + ch + 1.7), (x, yc, deck + ch + 3.2)], 0.015, rail, sides=4)
    # bow rail
    pts = [(x + s * beam * 0.4, y + bow * length * 0.2, deck + 0.6) for s in (-1,)] + [(x, y + bow * length * 0.48, deck + 0.75)] + \
          [(x + beam * 0.4, y + bow * length * 0.2, deck + 0.6)]
    tube("pulpit", pts, 0.018, rail, sides=4)


def hill_mat():
    """Dry Southern California hillside: golden grass with dark chaparral clumps, greener in the gullies."""
    if "hills" in _mats:
        return _mats["hills"]
    m, nt, b = _node_mat("hills")
    co = _coords(nt)
    grass = _noise(nt, co, 0.05, 6.0, 0.6)
    base = _ramp(nt, grass.outputs["Fac"], ((0.25, (0.45, 0.35, 0.18)), (0.75, (0.66, 0.53, 0.3))))
    # chaparral: irregular dark patches where a fine and a coarse noise agree, thicker on some slopes than others
    scrub = _noise(nt, co, 0.08, 10.0, 0.7)
    dens = _noise(nt, co, 0.004, 3.0)
    thr = _math(nt, "MULTIPLY_ADD", dens.outputs["Fac"], -0.35, 0.78)
    clump = _math(nt, "GREATER_THAN", scrub.outputs["Fac"], thr)
    col = _mix(nt, _math(nt, "MULTIPLY", clump, 0.85), base, (0.12, 0.13, 0.06))
    # gullies (faces turned away from straight up) hold more scrub
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sep.inputs[0])
    gully = _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", 0.8, sep.outputs["Z"], clamp=True), 4.0, clamp=True)
    col = _mix(nt, _math(nt, "MULTIPLY", gully, 0.5), col, (0.2, 0.19, 0.09))
    nt.links.new(col, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.95
    _bump(nt, b, _math(nt, "ADD", clump, _math(nt, "MULTIPLY", scrub.outputs["Fac"], 0.5)), 0.5, 1.5)
    _mats["hills"] = m
    return m


def hill_height(x, y):
    """Height of the far-shore ridge (0 at the shoreline, y = 1240)."""
    j = (y - 1240) / 520.0
    if j <= 0:
        return -2.0
    ridge = 75 + 45 * math.sin(x * 0.004 + 1.3) + 25 * math.sin(x * 0.011 + 0.4) + 10 * math.sin(x * 0.031)
    gul = 6 * math.sin(x * 0.07 + 2 * math.sin(y * 0.02)) + 3 * math.sin(x * 0.19 + y * 0.05)
    return (ridge + gul * min(1.0, j * 3)) * math.sin(math.pi * min(1.0, j * 1.6)) ** 0.8 - 2.0 if j < 1 else -2.0


# ---------------------------------------------------------------- the site

# The sun: the parked-car sprites (tools/car_sprites_real.py) are lit by a sun 50 degrees up, from the camera's left
# and a little behind it (sky.sun_rotation -140 with the camera off the car's front-right). The lot cameras look
# north-north-east, so the same light here is a sun 50 degrees up in the west: shadows fall to the right of the
# cars in the sprites and to the right of everything in the renders. The azimuth splits the three lot views
# (each wants -79..-94 degrees; see the sprite camera in lot_stalls).
SUN_EL, SUN_AZ = 50.0, -88.0


def sun_vector():
    el, az = math.radians(SUN_EL), math.radians(SUN_AZ)
    return Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))


def build_world():
    sc = bpy.context.scene
    w = bpy.data.worlds.new("sky")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_elevation = math.radians(SUN_EL)
    sky.sun_rotation = math.radians(SUN_AZ)
    sky.sun_disc = False          # the sun lamp is the sun; a disc as well doubles it
    sky.altitude = 30
    sky.air_density = 1.0
    sky.aerosol_density = 0.35    # a clear coastal day, not haze
    sky.ozone_density = 1.5       # a little deeper blue overhead
    # fair-weather cumulus: noise projected on a cloud deck, thinning toward the horizon
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    zz = _math(nt, "MAXIMUM", sep.outputs["Z"], 0.04)
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(_math(nt, "DIVIDE", sep.outputs["X"], zz), comb.inputs["X"])
    nt.links.new(_math(nt, "DIVIDE", sep.outputs["Y"], zz), comb.inputs["Y"])
    puff = _n(nt, "ShaderNodeTexNoise", Scale=0.9, Detail=10.0, Roughness=0.6, Distortion=0.2)
    nt.links.new(comb.outputs[0], puff.inputs["Vector"])
    field = _n(nt, "ShaderNodeTexNoise", Scale=0.18, Detail=2.0)
    nt.links.new(comb.outputs[0], field.inputs["Vector"])
    dens = _math(nt, "ADD", puff.outputs["Fac"], _math(nt, "MULTIPLY_ADD", field.outputs["Fac"], 0.45, -0.22))
    cloud = nt.nodes.new("ShaderNodeMapRange")
    cloud.interpolation_type = "SMOOTHSTEP"
    cloud.inputs["From Min"].default_value = 0.5
    cloud.inputs["From Max"].default_value = 0.66
    nt.links.new(dens, cloud.inputs["Value"])
    hor = nt.nodes.new("ShaderNodeMapRange")
    hor.interpolation_type = "SMOOTHSTEP"
    hor.inputs["From Min"].default_value = 0.02
    hor.inputs["From Max"].default_value = 0.16
    nt.links.new(sep.outputs["Z"], hor.inputs["Value"])
    cf = _math(nt, "MULTIPLY", cloud.outputs["Result"], hor.outputs["Result"])
    # clouds are a sunlit white a couple of times brighter than the sky behind them, greyer where they are thick
    lum = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(sky.outputs[0], lum.inputs[0])
    gain = _ramp(nt, puff.outputs["Fac"], ((0.5, (1.5, 1.52, 1.58)), (0.8, (2.6, 2.55, 2.45))))
    shade = _mix(nt, 1.0, gain, lum.outputs[0], "MULTIPLY")
    # a deeper blue where the sky is seen, without tinting the light it casts
    lp = nt.nodes.new("ShaderNodeLightPath")
    seen = _math(nt, "MAXIMUM", lp.outputs["Is Camera Ray"], lp.outputs["Is Glossy Ray"])
    blue = _mix(nt, seen, sky.outputs[0], _mix(nt, 1.0, sky.outputs[0], (0.84, 0.95, 1.14), "MULTIPLY"))
    col = _mix(nt, _math(nt, "MULTIPLY", cf, 0.95), blue, shade)
    nt.links.new(col, nt.nodes["Background"].inputs[0])
    nt.nodes["Background"].inputs["Strength"].default_value = 0.19
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 6.2
    sun.color = (1.0, 0.9, 0.76)
    sun.angle = math.radians(1.5)
    so = bpy.data.objects.new("sun", sun)
    so.rotation_euler = (-sun_vector()).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(so)


def build_ground():
    asphalt = asphalt_mat("asphalt", (0.1, 0.096, 0.09), (0.19, 0.18, 0.165))
    concrete = noise_mat("concrete", (0.5, 0.48, 0.45), (0.64, 0.62, 0.58), 8, 0.7, bump=0.05, macro=0.25)
    box("lot", (-60, -60, -0.1), (60, 0, 0), asphalt)
    box("street", (-200, -90, -0.12), (200, -60, -0.02), asphalt_mat("street", (0.04, 0.04, 0.045), (0.085, 0.085, 0.09), cracks=0.3))
    box("sidewalk", (-200, -60, -0.1), (200, -57, 0.08), concrete)
    box("pad", (-40, 0, -0.1), (40, 30, 0.02), concrete)
    # patched and stained asphalt across the open lot (each site adds its own stains in the stalls)
    patch = asphalt_mat("asphalt_patch", (0.075, 0.072, 0.07), (0.14, 0.135, 0.125), cracks=0.0, rough=0.75)
    seal = mat("crack_seal", (0.02, 0.02, 0.022), rough=0.4)
    rnd = random.Random(12)
    for i in range(9):
        x, y = rnd.uniform(-34, 30), rnd.uniform(-44, -6)
        w, d = rnd.uniform(1.2, 3.4), rnd.uniform(0.8, 2.2)
        box("asphalt_patch", (x, y, 0.0), (x + w, y + d, 0.004), patch)
        box("patch_seal", (x - 0.04, y - 0.04, 0.0), (x + w + 0.04, y + d + 0.04, 0.003), seal)
    for i in range(26):
        stain((rnd.uniform(-34, 30), rnd.uniform(-44, -4)), rnd.uniform(0.5, 1.6), rnd)
    for i, x in enumerate(range(-150, 160, 22)):
        palm((x, -58.5, 0), h=13 + (i % 4) * 1.5, seed=30 + i, kind="fan")


def stain(xy, size, rnd, kind=None):
    """A dark blotch on the asphalt: oil drips (glossy), or old water stains (matt)."""
    kind = kind or ("oil" if rnd.random() < 0.6 else "water")
    m = stain_mat("stain_oil", (0.01, 0.01, 0.011), 0.6, 0.25, scale=4.5) if kind == "oil" else \
        stain_mat("stain_water", (0.04, 0.038, 0.036), 0.45, 0.8, scale=2.0)
    ob = mesh_obj("stain", [(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)], [(0, 1, 2, 3)], m)
    ob.location = (xy[0], xy[1], 0.005 + rnd.uniform(0, 0.002))
    ob.scale = (size * rnd.uniform(0.7, 1.3), size * rnd.uniform(0.7, 1.3), 1)
    ob.rotation_euler.z = rnd.uniform(0, math.pi)
    ob.visible_shadow = False


def stall_stains(view, seed):
    """Oil drips where the engines of years of parked cars sat."""
    rnd = random.Random(seed)
    for st in lot_stalls(view):
        for _ in range(rnd.choice((0, 1, 1, 2))):
            p = st["centre"] + st["fwd"] * rnd.uniform(0.6, 1.6) + Vector((rnd.uniform(-0.4, 0.4), rnd.uniform(-0.4, 0.4), 0))
            stain(p, rnd.uniform(0.5, 1.2), rnd, "oil")


def arrow(x, y, yaw, m, size=1.0):
    """A painted traffic arrow on the asphalt."""
    pts = [(-0.18, -1.6), (0.18, -1.6), (0.18, 0.2), (0.55, 0.2), (0.0, 1.2), (-0.55, 0.2), (-0.18, 0.2)]
    c, s = math.cos(yaw), math.sin(yaw)
    vs = [(x + (px * c - py * s) * size, y + (px * s + py * c) * size, 0.008) for px, py in pts]
    mesh_obj("arrow", vs, [tuple(range(len(vs)))], m)


def curb(a, b, m, h=0.15, w=0.25):
    """A concrete kerb between two points on an axis."""
    (ax, ay), (bx, by) = a, b
    if abs(ax - bx) > abs(ay - by):
        return box("curb", (min(ax, bx), ay - w / 2, 0), (max(ax, bx), ay + w / 2, h), m, bevel=0.03)
    return box("curb", (ax - w / 2, min(ay, by), 0), (ax + w / 2, max(ay, by), h), m, bevel=0.03)


def kerb_paint():
    return stripe_mat("kerb_red", (0.62, 0.07, 0.05), (0.66, 0.1, 0.07), 20.0, rough=0.7)


def build_site3_front():
    """The flagship's lot dressing: angled stalls, planters, palms, pylon sign and bunting."""
    concrete = noise_mat("concrete3", (0.55, 0.53, 0.5), (0.68, 0.66, 0.62), 8, 0.7, bump=0.05)  # noqa: F841
    paint = mat("stripe", (0.92, 0.92, 0.88), rough=0.6)
    build_lot_stalls("lot", paint, block_mat("stone3", (0.7, 0.66, 0.6), (0.76, 0.72, 0.66), (0.6, 0.58, 0.54), (0.6, 0.3), split=0.2))
    stall_stains("lot", 3)
    arrow(-24.0, -30.0, math.radians(-10), mat("stripe_worn", (0.7, 0.7, 0.66), rough=0.7), 1.2)
    # the walk along the showroom front, with a red fire-lane kerb by the service bays
    walk = noise_mat("walk3", (0.6, 0.58, 0.55), (0.7, 0.68, 0.64), 8, 0.7, bump=0.05)
    box("walk3", (-16.5, -3.0, 0), (33.5, 0.0, 0.14), walk)
    box("walk3_kerb", (14.0, -3.12, 0), (33.5, -2.98, 0.14), kerb_paint())
    # planters along the front with palms and clipped shrubs
    for x in (-27, -9, 9, 27):
        box("planter", (x - 2.2, -4.8, 0), (x + 2.2, -3.0, 0.55), concrete, bevel=0.04)
        box("planter_soil", (x - 2.05, -4.65, 0.5), (x + 2.05, -3.15, 0.53), mat("bark_mulch", (0.16, 0.1, 0.06), rough=0.95))
        for k, dx in enumerate((-1.4, 1.4)):
            shrub(x + dx, -3.9, 0.6, 0.8, seed=k + x * 3, z=0.5)
    for i, x in enumerate((-27, -9, 9, 27, -44, 44)):
        palm((x, -3.9 if abs(x) < 40 else 6, 0), h=9 + (i % 3) * 1.4, seed=i)
    light_pole(-22.5, -4.2, 8.0, ((0, -1),))
    # street pylon sign
    dark = mat("alu", (0.08, 0.08, 0.09), rough=0.35, metal=0.8)
    box("pylon", (-33, -40, 0), (-31.2, -39.4, 9.5), dark)
    box("pylon_face", (-33.4, -40.1, 6.4), (-30.8, -39.3, 9.3), mat("pylon_lit", (0.05, 0.07, 0.12), rough=0.3))
    text("pylon_txt", "CHIEF\nAUTO", (-32.1, -40.15, 8.35), 0.95, mat("gold", (0.85, 0.62, 0.22)), extrude=0.03)
    text("pylon_sub", "PRE-OWNED · SERVICE", (-32.1, -40.15, 6.6), 0.2, mat("white_lit", (1, 1, 1), emit=2.0), extrude=0.01)
    # bunting along the showroom front between two poles, under the fascia and behind the parked cars (the game
    # draws the cars over the render, so nothing may stand between the lot camera and a stall)
    t0, t1 = flag_pole(-21.0, -4.4, 6.4), flag_pole(13.5, -4.4, 6.4)
    bunting_line(t0, t1, sag=0.9)
    bunting_line(t1, (16.5, -2.6, 6.6), sag=0.15)


def build_harbour():
    m, nt, b = _node_mat("water")
    co = _coords(nt, scale=(1, 2.5, 1))
    ripple = _noise(nt, co, 1.6, 6.0, 0.6)
    swell = _noise(nt, co, 0.08, 3.0)
    nt.links.new(_ramp(nt, swell.outputs["Fac"], ((0.3, (0.012, 0.05, 0.07)), (0.7, (0.03, 0.1, 0.13)))), b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.06
    _bump(nt, b, _math(nt, "ADD", ripple.outputs["Fac"], _math(nt, "MULTIPLY", swell.outputs["Fac"], 2.0)), 0.25, 0.1)
    box("sea", (-2500, 30, -1.2), (2500, 1400, -0.6), m)
    wood = noise_mat("deck", (0.35, 0.25, 0.17), (0.45, 0.33, 0.22), 30, 0.7, stretch=(1, 12, 1))
    box("boardwalk", (-60, 25, -0.4), (60, 31, 0.02), wood)
    railm = mat("rail", (0.75, 0.75, 0.76), rough=0.3, metal=1)
    box("rail", (-60, 30.8, 0.9), (60, 30.9, 0.96), railm)
    for x in range(-60, 61, 2):
        box("post", (x - 0.03, 30.82, 0), (x + 0.03, 30.88, 0.95), railm)
    piling = noise_mat("piling", (0.22, 0.17, 0.12), (0.34, 0.27, 0.2), 12, 0.85, stretch=(1, 1, 6))
    cap = mat("piling_cap", (0.9, 0.9, 0.88), rough=0.5)
    rnd = random.Random(5)
    for dock_x in (-48, -20, 8, 36):
        box("dock", (dock_x - 0.9, 31, -0.75), (dock_x + 0.9, 95, -0.45), wood)
        for j in range(6):
            yf = 32.5 + j * 11
            for side in (-1, 1):
                box("finger", (min(dock_x + side * 0.9, dock_x + side * 7.0), yf - 0.4, -0.72),
                    (max(dock_x + side * 0.9, dock_x + side * 7.0), yf + 0.4, -0.5), wood)
                px = dock_x + side * 7.0
                cyl("piling", (px, yf, -0.3), 0.16, 2.2, piling, verts=10)
                cyl("piling_cap", (px, yf, 0.82), 0.17, 0.04, cap, verts=10)
        for j in range(5):
            for side in (-1, 1):
                if rnd.random() < 0.15:
                    continue
                y = 38 + j * 11 + rnd.uniform(-0.3, 0.3)
                x = dock_x + side * rnd.uniform(4.0, 4.4)
                boat(x, y, rnd.uniform(8.0, 9.8), "sail" if rnd.random() < 0.55 else "motor", rnd, bow=rnd.choice((1, -1)))
        boat(dock_x, 102, rnd.uniform(14, 18), "motor", rnd, bow=1)
    # a few boats on moorings out in the bay
    for i in range(14):
        boat(rnd.uniform(-400, 400), rnd.uniform(160, 700), rnd.uniform(8, 13), "sail" if i % 3 else "motor", rnd, bow=rnd.choice((1, -1)))
    # Tewport's far shore: a waterfront town under a ridge of dry hills
    me_v, me_f = [], []
    nx, ny = 360, 36
    for j in range(ny + 1):
        for i in range(nx + 1):
            x = -2600 + 5200 * i / nx
            y = 1236 + 560 * j / ny
            me_v.append((x, y, hill_height(x, y)))
    for j in range(ny):
        for i in range(nx):
            a0 = j * (nx + 1) + i
            me_f.append((a0, a0 + 1, a0 + nx + 2, a0 + nx + 1))
    mesh_obj("ridge", me_v, me_f, hill_mat(), smooth=True)
    box("shore", (-2600, 1130, -1.0), (2600, 1240, -0.2), noise_mat("shore", (0.55, 0.5, 0.4), (0.65, 0.6, 0.5), 0.5, 0.9))
    box("seawall", (-2600, 1128, -1.2), (2600, 1131, 0.2), mat("seawall", (0.6, 0.58, 0.54), rough=0.85))
    walls = [window_mat("town_%d" % i, c, shade=(0.55, 0.52, 0.45) if i % 2 else None, bay=rnd.uniform(2.4, 3.2))
             for i, c in enumerate(((0.9, 0.86, 0.78), (0.82, 0.7, 0.56), (0.7, 0.78, 0.82), (0.95, 0.94, 0.9),
                                    (0.78, 0.56, 0.44), (0.86, 0.82, 0.62), (0.62, 0.66, 0.6), (0.92, 0.9, 0.86)))]
    tree = leaf_mat("tree_far", (0.05, 0.1, 0.035), (0.11, 0.17, 0.06), trans=0.0)
    tiles = tile_mat()
    x = -1100.0
    while x < 1100:
        w = rnd.uniform(8, 24)
        y0 = 1134 + rnd.uniform(0, 6)
        rows = 3 if abs(x) < 500 else 2
        yy = y0
        for r in range(rows):
            d = rnd.uniform(8, 18)
            hgt = rnd.choice((4.5, 7.5, 7.5, 10.5)) + (rnd.choice((0, 0, 6, 12)) if abs(x) < 260 and r == 1 else 0)
            box("house", (x, yy, -0.3), (x + w, yy + d, hgt), rnd.choice(walls))
            if rnd.random() < 0.45:
                hip_roof("roof", x, yy, x + w, yy + d, hgt, min(3.5, d * 0.3), tiles, over=0.6)
            yy += d + rnd.uniform(4, 14)
        if rnd.random() < 0.6:
            sphere("tree", (x + w + 2, y0 + rnd.uniform(2, 30), 4), (rnd.uniform(3, 5), rnd.uniform(3, 5), rnd.uniform(3.5, 5)), tree, seg=10)
        x += w + rnd.uniform(1.5, 7)
    # houses climbing the lower slopes
    for i in range(160):
        x, y = rnd.uniform(-900, 900), rnd.uniform(1250, 1420)
        z = hill_height(x, y)
        if z > 45:
            continue
        w, d = rnd.uniform(9, 16), rnd.uniform(8, 12)
        box("hill_house", (x, y, z - 3), (x + w, y + d, z + 4.5), rnd.choice(walls))
        hip_roof("roof", x, y, x + w, y + d, z + 4.5, 2.4, tiles, over=0.5)
        if rnd.random() < 0.5:
            sphere("tree", (x - 4, y + 4, z + 3), (4, 4, 4.5), tree, seg=10)


def build_dealership():
    global COL
    white = mat("render", (0.9, 0.89, 0.86), rough=0.6)
    dark = mat("alu", (0.08, 0.08, 0.09), rough=0.35, metal=0.8)
    gold = mat("gold", (0.85, 0.62, 0.22), rough=0.25, metal=1.0, emit=0.6, ecol=(1.0, 0.7, 0.3))
    wood = noise_mat("oak", (0.32, 0.2, 0.11), (0.45, 0.3, 0.17), 6, 0.45, stretch=(1, 14, 1))
    marble = noise_mat("marble", (0.93, 0.92, 0.9), (0.42, 0.4, 0.4), 1.6, 0.12, veins=True)
    ceiling = mat("ceiling", (0.95, 0.95, 0.95), rough=0.8)
    lamp = mat("lamp", (1, 1, 1), emit=12, ecol=(1.0, 0.86, 0.68))
    # ---- showroom shell (x -15..15, y 0..16, z 0..6)
    box("floor", (-15, 0, 0), (15, 16, 0.05), marble)
    box("roof", (-16.5, -2.5, 6), (16.5, 17, 6.8), white)
    box("fascia", (-16.5, -2.6, 6.0), (16.5, -2.4, 7.0), dark)
    box("ceil", (-15, 0, 5.9), (15, 16, 6.0), ceiling)
    for x in range(-12, 14, 4):
        for y in (3, 7, 11, 14):
            cyl("downlight", (x, y, 5.88), 0.18, 0.02, lamp, verts=16)
    glass_wall("front", (-15, 0), (15, 0), 0, 6, every=3)
    glass_wall("rear", (-8, 16), (15, 16), 0, 6, every=3)
    box("west", (-15.3, 0, 0), (-15, 16, 6), white)
    box("east", (15, 0, 0), (15.3, 16, 6), white)
    text("sign", "CHIEF AUTO", (0, -2.65, 6.15), 0.75, gold)
    text("sign_sub", "TEWPORT BEACH", (8.8, -2.65, 6.25), 0.25, mat("white_lit", (1, 1, 1), emit=2.0))
    # entry doors
    for x0, x1 in ((-1.6, -1.5), (-0.03, 0.03), (1.5, 1.6)):
        box("door_frame", (x0, -0.08, 0), (x1, 0.08, 3.1), dark)
    box("door_frame", (-1.6, -0.08, 3.0), (1.6, 0.08, 3.1), dark)
    box("door_handle", (-0.25, -0.12, 0.9), (-0.2, -0.08, 1.9), mat("chrome", (0.8, 0.8, 0.82), rough=0.15, metal=1.0))
    box("door_handle", (0.2, -0.12, 0.9), (0.25, -0.08, 1.9), mat("chrome", (0.8, 0.8, 0.82), rough=0.15, metal=1.0))
    g = box("door_glass", (-1.5, -0.03, 0.05), (1.5, 0.03, 3.0), glass())
    g.visible_shadow = False
    box("canopy", (-3, -3, 3.4), (3, 0, 3.55), white)
    # back wall feature: logo wall left of the rear glass, behind the office
    box("logo_wall", (-8, 15.6, 0), (-7.7, 16, 6), wood)
    # reception desk
    box("desk", (2, 11.5, 0), (7, 12.4, 1.1), white, bevel=0.05)
    box("desk_top", (1.9, 11.4, 1.1), (7.1, 12.5, 1.16), wood)
    text("desk_logo", "CHIEF AUTO", (4.5, 11.38, 0.45), 0.32, gold)
    planter(13.6, 14.6)     # (Marco's office gets its own plant in build_office_t3)
    planter(13.6, 1.4)
    # display podiums (cars are drawn by the game on top)
    # ---- Marco's office (x -15..-8, y 9..16), glass front, window to the harbour
    box("office_floor", (-15, 9, 0.05), (-8, 16, 0.07), wood)
    glass_wall("office_front", (-15, 9), (-8, 9), 0, 6, every=2.3)
    glass_wall("office_side", (-8, 9), (-8, 15.6), 0, 6, every=2.2)
    glass_wall("office_rear", (-15, 16), (-8, 16), 0, 6, every=3.5)
    box("exec_desk", (-13.2, 12.2, 0), (-10.2, 13.2, 0.76), wood, bevel=0.02)
    box("exec_top", (-13.3, 12.1, 0.76), (-10.1, 13.3, 0.81), mat("black_glass", (0.02, 0.02, 0.02), rough=0.08))
    box("monitor", (-12.0, 12.9, 0.85), (-11.0, 12.95, 1.45), mat("screen", (0.02, 0.05, 0.1), rough=0.1, emit=0.6, ecol=(0.3, 0.55, 0.9)))
    chair(-11.7, 13.9, math.pi, mat("leather", (0.06, 0.05, 0.05), rough=0.35))
    for k, x in enumerate((-13.9, -9.0)):
        chair(x, 10.6, math.pi * 0.25 * (1 if k else -1), mat("leather_tan", (0.45, 0.27, 0.15), rough=0.4))
    build_office_t3()
    box("rug", (-13.8, 10.0, 0.07), (-9.6, 14.8, 0.085), mat("rug", (0.55, 0.5, 0.42), rough=0.95))
    # ---- service bay wing (x 15..33, y 0..16)
    epoxy = noise_mat("epoxy", (0.33, 0.35, 0.37), (0.4, 0.42, 0.44), 12, 0.25)
    box("bay_floor", (15.3, 0, 0), (33, 16, 0.04), epoxy)
    box("bay_roof", (15, -0.5, 6.2), (33.5, 16.5, 6.9), white)
    box("bay_back", (15.3, 15.7, 0), (33, 16, 6.2), mat("block", (0.62, 0.62, 0.6), rough=0.8))
    box("bay_east", (33, 0, 0), (33.3, 16, 6.2), white)
    box("bay_ceil", (15.3, 0, 6.1), (33, 16, 6.2), ceiling)
    for x in (19, 24, 29):
        for y in (4, 9, 13):
            box("tube", (x - 1.2, y - 0.1, 5.9), (x + 1.2, y + 0.1, 5.98), lamp)
    # front with three roll-up doors (open)
    box("bay_front_l", (15.3, -0.15, 0), (16.2, 0.15, 6.2), white)
    for i, x in enumerate((16.2, 22.0, 27.8)):
        box("door_post", (x + 5.0, -0.15, 0), (x + 5.8, 0.15, 6.2), white)
        box("door_head", (x, -0.15, 4.6), (x + 5.0, 0.15, 6.2), white)
        box("door_roll", (x, -0.3, 4.3), (x + 5.0, 0.0, 4.6), mat("rollup", (0.7, 0.72, 0.75), rough=0.4, metal=0.6))
        text("bay_num", str(i + 1), (x + 2.5, -0.2, 5.0), 0.7, mat("bay_txt", (0.95, 0.75, 0.2), emit=1.0))
    text("bay_sign", "SERVICE", (24.5, -0.55, 6.25), 0.6, gold)
    tool_red = mat("toolbox", (0.62, 0.05, 0.04), rough=0.3, metal=0.4)
    for x in (16.5, 18.6, 30.0):
        box("toolbox", (x, 14.9, 0), (x + 2.0, 15.6, 1.0), tool_red, bevel=0.02)
        for d in range(5):
            box("drawer", (x + 0.05, 14.86, 0.1 + d * 0.18), (x + 1.95, 14.9, 0.24 + d * 0.18), mat("chrome", (0.8, 0.8, 0.82), rough=0.15, metal=1.0))
    box("pegboard", (20.8, 15.62, 1.2), (27.5, 15.7, 3.2), mat("peg", (0.65, 0.5, 0.33), rough=0.8))
    rnd = random.Random(3)
    for i in range(22):
        x, z = rnd.uniform(21.0, 27.2), rnd.uniform(1.4, 3.0)
        box("tool", (x, 15.5, z), (x + 0.05, 15.6, z + rnd.uniform(0.2, 0.45)), mat("chrome", (0.8, 0.8, 0.82)))
    yellow = mat("lift", (0.95, 0.72, 0.05), rough=0.4)
    for lx in (19.1, 24.9, 30.7):
        for side in (-1.55, 1.55):
            box("lift_post", (lx + side - 0.14, 12.0, 0), (lx + side + 0.14, 12.3, 3.6), yellow)
            box("lift_base", (lx + side - 0.3, 11.9, 0), (lx + side + 0.3, 12.4, 0.08), yellow)
            box("lift_arm", (lx + side * 0.55 - 0.08, 10.6, 0.3), (lx + side * 0.55 + 0.08, 12.1, 0.38), yellow)
        box("lane_paint", (lx - 2.4, 2, 0.04), (lx - 2.3, 15.5, 0.05), mat("yellow", (0.85, 0.65, 0.1)))
        box("lane_paint", (lx + 2.3, 2, 0.04), (lx + 2.4, 15.5, 0.05), mat("yellow", (0.85, 0.65, 0.1)))
    box("tires", (31.8, 13.5, 0), (32.8, 14.5, 1.6), mat("rubber", (0.03, 0.03, 0.03), rough=0.8))
    text("bay_wall_logo", "CHIEF AUTO SERVICE", (24.2, 15.65, 4.2), 0.55, mat("bay_logo", (0.15, 0.17, 0.2), rough=0.5))
    # ---- PC desk nook (back of showroom, east), the game's office PC view
    box("pc_desk", (9.5, 14.0, 0), (13.5, 15.2, 0.76), wood)
    box("pc_top", (9.4, 13.9, 0.76), (13.6, 15.3, 0.8), wood)
    # ---- roof-top apartment: shell is shared, furniture is per tier
    build_apartment_shell(white, dark, wood)


def planter(x, y):
    pot = mat("pot", (0.12, 0.12, 0.12), rough=0.4)
    cyl("pot", (x, y, 0.45), 0.45, 0.9, pot, r2=0.35)
    leaf = mat("fig", (0.1, 0.28, 0.08), rough=0.6)
    rnd = random.Random(int(x * 10 + y))
    for i in range(14):
        sphere("leaves", (x + rnd.uniform(-0.4, 0.4), y + rnd.uniform(-0.4, 0.4), 1.3 + rnd.uniform(0, 1.3)),
               (0.35, 0.35, 0.3), leaf, seg=10)


def chair(x, y, yaw, m):
    """Office chair built at the origin and parented to a rotated empty."""
    base = mat("alu", (0.08, 0.08, 0.09))
    pivot = bpy.data.objects.new("chair", None)
    pivot.location = (x, y, 0)
    pivot.rotation_euler.z = yaw
    _link(pivot)
    for o in (cyl("chair_post", (0, 0, 0.22), 0.04, 0.44, base, verts=8),
              box("seat", (-0.32, -0.3, 0.42), (0.32, 0.3, 0.55), m, bevel=0.05),
              box("back", (-0.32, 0.24, 0.55), (0.32, 0.34, 1.25), m, bevel=0.05)):
        o.parent = pivot


# apartment sits on the roof over the west half: x -15..3, y 3..16, z 6.8..10.4
AX0, AX1, AY0, AY1, AZ0, AZ1 = -14.5, 2.5, 3.5, 16.0, 6.8, 10.3


def build_apartment_shell(white, dark, wood):
    box("apt_slab", (AX0, AY0, AZ0), (AX1, AY1 + 3.5, AZ0 + 0.06), wood)
    box("apt_roof", (AX0 - 0.6, AY0 - 0.6, AZ1), (AX1 + 0.6, AY1 + 4.0, AZ1 + 0.4), white)
    box("apt_ceil", (AX0, AY0, AZ1 - 0.05), (AX1, AY1, AZ1), mat("ceiling", (0.95, 0.95, 0.95)))
    box("apt_back", (AX0, AY0, AZ0), (AX1, AY0 + 0.25, AZ0 + 1.0), white)
    box("apt_back_top", (AX0, AY0, AZ1 - 0.35), (AX1, AY0 + 0.25, AZ1), white)
    glass_wall("apt_front_glass", (AX0, AY0 + 0.12), (AX1, AY0 + 0.12), AZ0 + 1.0, AZ1 - 0.35, every=2.0)
    box("apt_west", (AX0 - 0.25, AY0, AZ0), (AX0, AY1, AZ1), white)
    box("apt_east", (AX1, AY0, AZ0), (AX1 + 0.25, AY1, AZ1), white)
    glass_wall("apt_glass", (AX0, AY1), (AX1, AY1), AZ0, AZ1, every=2.8)
    railm = mat("rail", (0.75, 0.75, 0.76), rough=0.3, metal=1)
    gr = box("balcony_glass", (AX0, AY1 + 3.4, AZ0), (AX1, AY1 + 3.45, AZ0 + 1.05), glass())
    gr.visible_shadow = False
    box("balcony_rail", (AX0, AY1 + 3.38, AZ0 + 1.05), (AX1, AY1 + 3.48, AZ0 + 1.1), railm)


def chain_fence(pts, h=1.8):
    post = mat("galv", (0.6, 0.62, 0.63), rough=0.4, metal=0.9)
    wire = mat("chainlink", (0.55, 0.57, 0.58), rough=0.5, metal=0.6, alpha=0.28)
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        a, b = Vector((ax, ay, 0)), Vector((bx, by, 0))
        d = b - a
        n = max(1, int(d.length / 3))
        for i in range(n + 1):
            p = a + d * (i / n)
            cyl("fence_post", (p.x, p.y, h / 2), 0.04, h, post, verts=8)
        box("fence_rail", (min(ax, bx) - 0.03, min(ay, by) - 0.03, h - 0.04), (max(ax, bx) + 0.03, max(ay, by) + 0.03, h), post)
        w = box("fence_wire", (min(ax, bx), min(ay, by) - 0.005, 0.05), (max(ax, bx), max(ay, by) + 0.005, h - 0.05), wire)
        w.visible_shadow = False


def power_line(x0, x1, y, every=32.0):
    """Wooden utility poles with sagging wires along the street."""
    wood = mat("pole_wood", (0.3, 0.22, 0.15), rough=0.9)
    wire = mat("wire", (0.05, 0.05, 0.05), rough=0.6)
    xs = [x0 + i * every for i in range(int((x1 - x0) / every) + 1)]
    for x in xs:
        cyl("pole", (x, y, 5.5), 0.14, 11.0, wood, verts=10)
        box("crossarm", (x - 1.3, y - 0.07, 10.0), (x + 1.3, y + 0.07, 10.15), wood)
    for a, b in zip(xs, xs[1:]):
        for dx in (-1.1, 0.0, 1.1):
            tube("wire", catenary((a + dx, y, 10.2), (b + dx, y, 10.2), 0.9, 12), 0.012, wire, sides=6)


# ---------------------------------------------------------------- lot stalls

# The game parks the owned cars on the lot render as three-quarter sprites (tools/car_sprites_real.py and
# car_sprites3d.py): 50 mm lens, camera 1.7 car lengths away and 1.15 m up, seen from the front-right with the camera
# Q_TURN clockwise of the nose. Every stall is turned so that a car parked in it, nose-out, shows exactly that angle
# to its view's camera, which fans the stalls a little along a row. The lot cameras use the same lens and look down
# about as steeply as the sprites, so a sprite drawn over a stall matches the render.
# Rows per lot view: (y of the wall the stall backs touch, x of the first stall's left edge, stalls, wall) where wall
# is True for a low block wall behind the row, False when the row backs onto the building, or the (x0, x1) gaps
# where the wall stops (the building or a planter is the wall there). The first row is the front one and the game
# fills the stalls in this order. Nothing may stand between the camera and a stall: the cars are drawn on top.
Q_TURN = math.atan2(0.78, 0.62)
STALL_W = 2.7
REF_CAR = (4.7, 1.85, 1.45)      # length, width, height of the car the stall positions are exported for
LOT_ROWS = {
    "lot_t1": ((-13.0, -15.0, 3, True), (-2.4, -16.0, 4, ((-12.6, -1.4),))),            # 7: front of the office
    "lot_t2": ((-13.5, -12.0, 4, True), (-0.8, -10.5, 4, False)),                       # 8: against the showroom
    "lot": ((-17.0, -19.0, 5, True), (-5.2, -17.5, 5, ((-11.4, -6.6),))),               # 10: by the planters
}
LOW_WALL = 0.55


def lot_stalls(view):
    """Stall layout for a lot view, from its camera position: one dict per stall, in the order the game fills them."""
    cam = Vector(VIEWS[view][0])
    length, width, _ = REF_CAR
    turn = Matrix.Rotation(Q_TURN, 3, "Z")
    out = []
    for ri, (wall_y, x, n, wall) in enumerate(LOT_ROWS[view]):
        for _ in range(n):
            xc, fwd, d, pitch = x + 1.6, Vector((0, -1, 0)), 1.0, STALL_W
            for _ in range(8):
                centre = Vector((xc, wall_y, 0)) + fwd * (d + length / 2)
                fwd = turn @ Vector((cam.x - centre.x, cam.y - centre.y, 0)).normalized()
                phi = math.acos(max(-1.0, min(1.0, -fwd.y)))      # angle off straight out from the wall
                pitch = STALL_W / math.cos(phi)
                xc = x + pitch / 2
                d = (0.3 + width / 2 * math.sin(phi)) / math.cos(phi)   # rear corners clear the wall by 30 cm
            centre = Vector((xc, wall_y, 0)) + fwd * (d + length / 2)
            out.append(dict(row=ri, x0=x, x1=x + pitch, wall_y=wall_y, wall=wall, fwd=fwd, d=d, centre=centre))
            x += pitch
    return out


def strip(name, a, b, width, height, m):
    """A flat bar on the ground from a to b (stall stripes, wheel stops)."""
    a, b = Vector(a).to_2d(), Vector(b).to_2d()
    d = b - a
    mid = (a + b) / 2
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(d.length, width, height), verts=bm.verts)
    bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.atan2(d.y, d.x), 3, "Z"), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(mid.x, mid.y, height / 2), verts=bm.verts)
    return _bm_obj(name, bm, m)


def build_lot_stalls(view, paint, wall_mat, back_h=None):
    """Painted stall stripes, wheel stops and the low walls for a lot view's rows (see LOT_ROWS). back_h makes the
    back row's wall a full-height block wall (nothing stands behind that row's cars, so it can be tall)."""
    stop = noise_mat("wheel_stop", (0.55, 0.54, 0.5), (0.68, 0.66, 0.62), 20, 0.8, bump=0.1)
    cap = mat("wall_cap", (0.78, 0.76, 0.72), rough=0.7)
    stalls = lot_stalls(view)
    for ri in range(len(LOT_ROWS[view])):
        row = [st for st in stalls if st["row"] == ri]
        wall_y = row[0]["wall_y"]
        # stripes on every stall edge, along the mean heading of the stalls either side
        for k in range(len(row) + 1):
            near = row[max(0, k - 1):k + 1]
            fwd = sum((st["fwd"] for st in near), Vector()).normalized()
            reach = sum(st["d"] for st in near) / len(near) + REF_CAR[0] + 0.5
            a = Vector((row[k]["x0"] if k < len(row) else row[-1]["x1"], wall_y, 0))
            strip("stall_line", a, a + fwd * reach, 0.12, 0.012, paint)
        for st in row:
            base = Vector(((st["x0"] + st["x1"]) / 2, wall_y, 0))
            side = Vector((-st["fwd"].y, st["fwd"].x, 0))
            c = base + st["fwd"] * (st["d"] + 0.35)
            strip("wheel_stop", c - side * 0.85, c + side * 0.85, 0.16, 0.11, stop)
        wall = row[0]["wall"]
        if wall:
            x0, x1 = row[0]["x0"] - 0.6, row[-1]["x1"] + 0.6
            spans = [(x0, x1)]
            for g0, g1 in (wall if wall is not True else ()):
                spans = [p for a, b in spans for p in ((a, min(b, g0)), (max(a, g1), b)) if p[1] - p[0] > 0.3]
            top = back_h if back_h and ri == len(LOT_ROWS[view]) - 1 else LOW_WALL
            for a, b in spans:
                box("low_wall", (a, wall_y, 0), (b, wall_y + 0.3, top - 0.06), wall_mat)
                box("low_wall_cap", (a - 0.04, wall_y - 0.04, top - 0.06), (b + 0.04, wall_y + 0.34, top), cap)


def export_stalls(view, cam, path):
    """Screen positions of the view's stalls for the game (normalized image coordinates, 0..1 from the top left)."""
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    dims = car_dims()
    sc.camera = cam
    bpy.context.view_layer.update()
    lens = cam.data.lens
    length, width, height = REF_CAR

    def uv(p):
        q = world_to_camera_view(sc, cam, Vector(p))
        return q, [round(q.x, 5), round(1.0 - q.y, 5)]

    stalls = []
    for i, st in enumerate(lot_stalls(view)):
        g = st["centre"]
        fwd = st["fwd"]
        side = Vector((-fwd.y, fwd.x, 0))
        t = g + Vector((0, 0, 0.42 * height))
        tq, tuv = uv(t)
        _, a = uv(t + fwd)
        _, b = uv(t + Vector((0, 0, 1)))
        ppm = (lens / 36.0) / tq.z          # image widths per metre at the car's depth
        stalls.append({
            "row": st["row"],
            "ground": uv(g)[1],
            "target": tuv,
            "nose": [uv(g + fwd * length / 2 + side * width / 2)[1], uv(g + fwd * length / 2 - side * width / 2)[1]],
            "fwd": [round(a[0] - tuv[0], 5), round(a[1] - tuv[1], 5)],
            "up": [round(b[0] - tuv[0], 5), round(b[1] - tuv[1], 5)],
            "ppm": round(ppm, 6),
            "px_per_m": round(ppm * sc.render.resolution_x, 3),
            "frame_w": round(ppm * sprite_frame_m(length), 5),
            "depth": round(tq.z, 3),
            "x": round(st["centre"].x, 3),
        })
    # back rows first, and in a row right to left: each car's nose overlaps its right-hand neighbour's flank
    order = sorted(range(len(stalls)), key=lambda k: (-stalls[k]["row"], -stalls[k]["x"]))
    for k in range(len(stalls)):
        stalls[k]["order"] = order.index(k)
        del stalls[k]["x"]
    data = {
        "view": view,
        "image": [sc.render.resolution_x, sc.render.resolution_y],
        "about": "Stalls in fill order. Coordinates are fractions of the image (u right, v down). target is where the "
                 "middle of a sprite frame goes for the reference car (its centre at 0.42 of its height); frame_w is "
                 "that car's 640x360 sprite frame width as a fraction of the image width; ppm is image widths per "
                 "metre there; fwd and up are image offsets per metre along the car's heading and straight up. "
                 "For another car: move target by fwd * (L - ref L) / 2 (its tail stays at the wheel stop) and by "
                 "up * 0.42 * (H - ref H), and use frame_w = ppm * hypot(1.7 L, 1.15) * 36 / 50. order is the draw order.",
        "ref_car": {"length": length, "width": width, "height": height},
        "sprite": {"lens": 50, "dist_per_length": 1.7, "rise": 1.15, "target_height": 0.42, "frame": [640, 360], "flip": False},
        "cars": dims,
        "stalls": stalls,
    }
    import json
    with open(path, "w") as f:
        json.dump(data, f, indent=1)


def sprite_frame_m(length):
    """Width in metres that a car sprite's 640 px frame covers at the car (see car_sprites_real.quarter_cam)."""
    return math.hypot(1.7 * length, 1.15) * 36.0 / 50.0


_dims = {}


def car_dims():
    """Length, width and height of every car model in assets/cars3d, measured once (imports and removes each one)."""
    if not _dims:
        folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "cars3d")
        for fn in sorted(os.listdir(folder)):
            if not fn.endswith(".glb"):
                continue
            before = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=os.path.join(folder, fn))
            new = [o for o in bpy.data.objects if o not in before]
            lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
            for o in new:
                if o.type == "MESH":
                    for c in o.bound_box:
                        p = o.matrix_world @ Vector(c)
                        lo, hi = Vector(map(min, lo, p)), Vector(map(max, hi, p))
            sz = hi - lo
            _dims[fn[:-4]] = [round(max(sz.x, sz.y), 2), round(min(sz.x, sz.y), 2), round(sz.z, 2)]
            for o in new:
                bpy.data.objects.remove(o, do_unlink=True)
    return _dims


# Tier 1 sales office: a small stucco box at the back of the lot, front facing the street (-y)
OX0, OX1, OY0, OY1, OH = -12.0, -2.0, -1.0, 7.0, 4.2
TZ = 0.05   # floor height inside


def build_site1():
    """Starting dealership: a striped corner lot, a little sales office with a big sign, flags and a carport."""
    global COL
    COL = tier_collection("s1")
    paint = mat("stripe_worn", (0.7, 0.7, 0.66), rough=0.7)
    block = block_mat("cmu1", (0.5, 0.46, 0.4), (0.58, 0.54, 0.47), (0.66, 0.64, 0.6))
    build_lot_stalls("lot_t1", paint, block, back_h=1.8)
    stall_stains("lot_t1", 1)
    arrow(-12.5, -23.5, math.radians(8), paint, 1.1)
    # the block wall carries on behind the back row to the west fence and east to the carport
    cap = mat("wall_cap", (0.78, 0.76, 0.72), rough=0.7)
    for a, b in ((-22.0, -16.6), (-0.18, 5.8)):    # the back row's own wall runs -16.6..-12.6 and -1.4..-0.18
        box("block_wall", (a, -2.4, 0), (b, -2.1, 1.74), block)
        box("block_wall_cap", (a - 0.04, -2.44, 1.74), (b + 0.04, -2.06, 1.8), cap)
    box("o_kerb", (-12.6, -2.45, 0), (-1.4, -2.2, 0.15), kerb_paint())
    stucco = noise_mat("stucco1", (0.86, 0.82, 0.74), (0.92, 0.88, 0.8), 30, 0.85, bump=0.15)
    trim = mat("trim1", (0.12, 0.13, 0.15), rough=0.5)
    navy = mat("fascia1", (0.05, 0.08, 0.16), rough=0.45)
    gold = mat("gold", (0.85, 0.62, 0.22), rough=0.25, metal=1.0, emit=0.6, ecol=(1.0, 0.7, 0.3))
    # shell
    box("o_slab", (OX0 - 0.6, OY0 - 1.2, 0), (OX1 + 0.6, OY1, TZ), noise_mat("walk1", (0.55, 0.53, 0.5), (0.65, 0.63, 0.6), 8, 0.8))
    box("o_west", (OX0, OY0, 0), (OX0 + 0.2, OY1, OH), stucco)
    box("o_east", (OX1 - 0.2, OY0, 0), (OX1, OY1, OH), stucco)
    box("o_back", (OX0, OY1 - 0.2, 0), (OX1, OY1, OH), stucco)
    box("o_roof", (OX0 - 0.3, OY0 - 0.3, OH), (OX1 + 0.3, OY1 + 0.3, OH + 0.3), stucco)
    box("o_ceiling", (OX0, OY0, OH - 0.6), (OX1, OY1, OH - 0.55), mat("ceiling_tile", (0.85, 0.84, 0.8), rough=0.9))
    # storefront: window, glass door, window
    holes = [(-11.2, -7.6, 0.8, 2.6), (-6.4, -5.2, TZ, 2.4), (-4.4, -2.8, 0.8, 2.6)]
    xs = [OX0] + [v for h in holes for v in h[:2]] + [OX1]
    for i in range(0, len(xs), 2):
        box("o_front", (xs[i], OY0, 0), (xs[i + 1], OY0 + 0.2, OH), stucco)
    for hx0, hx1, z0, z1 in holes:
        if z0 > TZ:
            box("o_front_low", (hx0, OY0, 0), (hx1, OY0 + 0.2, z0), stucco)
        box("o_front_high", (hx0, OY0, z1), (hx1, OY0 + 0.2, OH), stucco)
        g = box("o_glass", (hx0, OY0 + 0.09, z0), (hx1, OY0 + 0.11, z1), glass())
        g.visible_shadow = False
        for z in (z0, z1):
            box("o_frame", (hx0, OY0 - 0.02, z - 0.04), (hx1, OY0 + 0.22, z + 0.04), trim)
        for x in (hx0, hx1):
            box("o_frame", (x - 0.04, OY0 - 0.02, z0), (x + 0.04, OY0 + 0.22, z1), trim)
    box("o_door_bar", (-6.3, OY0 - 0.06, 1.0), (-5.3, OY0 - 0.02, 1.05), mat("chrome", (0.8, 0.8, 0.82), rough=0.15, metal=1.0))
    # ledgestone wainscot along the front and round the corners
    ledge = block_mat("ledgestone", (0.5, 0.44, 0.36), (0.62, 0.56, 0.46), (0.38, 0.35, 0.3), (0.55, 0.12), split=1.0)
    for hx0, hx1, z0, z1 in [(OX0 - 0.06, -11.2, 0, 0.8), (-7.6, -6.4, 0, 0.8), (-5.2, -4.4, 0, 0.8), (-2.8, OX1 + 0.06, 0, 0.8)]:
        box("o_stone", (hx0, OY0 - 0.08, 0), (hx1, OY0, z1), ledge)
    for hx0, hx1 in ((-11.2, -7.6), (-4.4, -2.8)):
        box("o_stone", (hx0, OY0 - 0.08, 0), (hx1, OY0, 0.8), ledge)
    for xs in (OX0 - 0.08, OX1):
        box("o_stone_side", (xs, OY0 - 0.08, 0), (xs + 0.08, OY1, 0.8), ledge)
    # the big sign on the fascia
    box("o_fascia", (OX0 - 0.4, OY0 - 0.45, 2.85), (OX1 + 0.4, OY0 - 0.15, OH + 0.35), navy)
    text("o_sign", "CHIEF AUTO", ((OX0 + OX1) / 2, OY0 - 0.5, 3.45), 0.78, gold)
    text("o_sign_sub", "USED CARS", ((OX0 + OX1) / 2, OY0 - 0.5, 3.05), 0.3, mat("white_lit", (1, 1, 1), emit=2.0))
    box("o_awning", (OX0 - 0.4, OY0 - 1.3, 2.7), (OX1 + 0.4, OY0 - 0.15, 2.85), navy)
    # inside: carpet, a desk facing the windows, PC, filing cabinet, whiteboard with goals, poster, plant
    carpet = noise_mat("carpet", (0.3, 0.26, 0.22), (0.37, 0.32, 0.26), 220, 0.95, bump=0.3)
    box("o_carpet", (OX0 + 0.2, OY0 + 0.2, TZ), (OX1 - 0.2, OY1 - 0.2, TZ + 0.01), carpet)
    wood = noise_mat("desk_wood1", (0.3, 0.18, 0.09), (0.4, 0.25, 0.13), 6, 0.4, stretch=(1, 14, 1))
    box("o_desk", (-9.6, 3.6, TZ), (-6.4, 4.5, TZ + 0.76), wood)
    box("o_desk_top", (-9.7, 3.5, TZ + 0.76), (-6.3, 4.6, TZ + 0.8), wood)
    box("o_monitor", (-8.4, 4.1, TZ + 0.85), (-7.3, 4.14, TZ + 1.5), mat("screen", (0.02, 0.05, 0.1), rough=0.1, emit=0.6, ecol=(0.3, 0.55, 0.9)))
    box("o_monitor_stand", (-7.92, 4.15, TZ + 0.8), (-7.78, 4.25, TZ + 0.9), trim)
    box("o_keyboard", (-8.3, 3.7, TZ + 0.8), (-7.4, 3.9, TZ + 0.82), trim)
    box("o_phone", (-9.4, 3.8, TZ + 0.8), (-9.0, 4.1, TZ + 0.88), trim)
    box("o_mug", (-6.7, 3.8, TZ + 0.8), (-6.6, 3.9, TZ + 0.9), mat("mug", (0.08, 0.08, 0.1)))
    chair(-7.9, 5.1, math.pi, mat("leather_brown", (0.16, 0.08, 0.04), rough=0.35))
    for x in (-9.0, -6.9):
        chair(x, 2.7, 0.0, noise_mat("guest_fabric", (0.05, 0.08, 0.16), (0.08, 0.12, 0.22), 300, 0.95, bump=0.2))
    box("o_filing", (-11.75, 5.6, TZ), (-11.2, 6.7, TZ + 1.35), mat("filing", (0.4, 0.42, 0.45), metal=0.6, rough=0.4))
    box("o_whiteboard", (OX0 + 0.2, 1.4, 1.2), (OX0 + 0.23, 4.4, 2.6), mat("whiteboard", (0.95, 0.95, 0.94), rough=0.25))
    box("o_wb_frame", (OX0 + 0.19, 1.35, 1.15), (OX0 + 0.21, 4.45, 2.65), mat("galv", (0.6, 0.62, 0.63)))
    ink = mat("marker", (0.1, 0.12, 0.2), rough=0.6)
    text("o_goals", "GOALS", (OX0 + 0.24, 2.9, 2.3), 0.22, ink, rot=(math.pi / 2, 0, math.pi / 2), extrude=0.0)
    for i, line in enumerate(("[ ] Sell 3 cars", "[ ] Make $10,000 profit", "[ ] Hire 1 salesperson", "[ ] Upgrade the lot")):
        text("o_goal", line, (OX0 + 0.24, 1.6, 2.0 - i * 0.2), 0.12, ink, rot=(math.pi / 2, 0, math.pi / 2), extrude=0.0, align="LEFT")
    box("o_poster", (OX1 - 0.23, 2.0, 1.4), (OX1 - 0.2, 4.0, 2.4), mat("poster", (0.1, 0.12, 0.18), emit=0.15, ecol=(0.6, 0.2, 0.15)))
    planter(-2.8, 6.3)
    build_office_t1()
    tube = mat("tube_lit", (1, 1, 1), emit=8, ecol=(0.95, 0.97, 1.0))
    for x in (-9.5, -4.5):
        box("o_light", (x - 0.6, 2.8, OH - 0.62), (x + 0.6, 3.4, OH - 0.6), tube)
    # bunting strung between poles at the ends of the block wall and the office roof, all behind the stalls (the
    # game draws the parked cars over the render, so nothing may stand between the lot camera and a stall)
    top = [flag_pole(x, y, h) for x, y, h in ((-21.6, -1.9, 7.2), (5.5, -1.9, 7.2))]
    roof_w, roof_e = Vector((OX0 - 0.3, OY0 - 0.3, OH + 0.3)), Vector((OX1 + 0.3, OY0 - 0.3, OH + 0.3))
    bunting_line(top[0], roof_w, sag=0.6)
    bunting_line(roof_e, top[1], sag=0.6)
    bunting_line(top[0], top[1], sag=1.3)
    light_pole(-20.2, -8.0, 7.5, ((1, 0),))
    light_pole(3.2, -1.6, 7.5, ((0, -1),))
    palm((-20.5, -0.6, 0), h=10.5, seed=91)
    palm((-16.0, 3.0, 0), h=9.0, seed=93, kind="fan")
    palm((-0.8, 7.5, 0), h=9.6, seed=94, kind="fan")
    palm((19.5, -2.0, 0), h=9.0, seed=92, kind="fan")
    for x in (-20.6, -19.2, -21.2):
        shrub(x, -1.2 + (x + 20) * 0.6, 0.7, 0.9)
    # the neighbours: a taqueria and a laundromat to the west, an insurance office and a dentist behind the carport
    shop_block(-40.0, -23.0, -2.0, 18.0, 2, SHOP_COLOURS[1], ((0.45, "TACOS", (0.95, 0.85, 0.3), ((0.7, 0.1, 0.06), (0.95, 0.9, 0.8))),
                                                            (0.55, "LAUNDROMAT", (0.08, 0.2, 0.5), None)), sides=("e",), seed=11,
               side_sign=("TACOS  BURRITOS", (0.95, 0.85, 0.3), (0.6, 0.08, 0.05)))
    shop_block(1.0, 21.0, 9.0, 12.0, 2, SHOP_COLOURS[2], ((0.55, "TEWPORT INSURANCE", (0.08, 0.1, 0.16), None),
                                                        (0.45, "DENTAL", (0.95, 0.95, 0.92), ((0.1, 0.3, 0.2), (0.85, 0.85, 0.8)))),
               sides=("w",), seed=12)
    power_line(-110, 110, -57.0)
    # carport for repairs on the east side
    galv = mat("galv", (0.6, 0.62, 0.63), rough=0.4, metal=0.9)
    concrete = noise_mat("oilpad", (0.38, 0.37, 0.35), (0.55, 0.53, 0.5), 9, 0.8, bump=0.1)
    box("cp_pad", (6, -8, 0.0), (16, 0, 0.04), concrete)
    for x in (6.2, 15.8):
        for y in (-7.8, -0.2):
            box("cp_post", (x - 0.06, y - 0.06, 0), (x + 0.06, y + 0.06, 3.3), galv)
    box("cp_roof", (5.8, -8.4, 3.3), (16.2, 0.4, 3.36), mat("corrugated", (0.55, 0.57, 0.58), rough=0.45, metal=0.8))
    box("oil_stain", (9.5, -5.5, 0.041), (12.5, -2.5, 0.042), mat("oil", (0.08, 0.08, 0.08), rough=0.3))
    laminate = mat("laminate", (0.55, 0.42, 0.28), rough=0.5)
    box("cp_bench", (14.4, -1.0, 0), (15.8, -0.2, 0.9), laminate)
    box("cp_toolbox", (13.0, -0.9, 0), (14.2, -0.2, 0.8), mat("toolbox", (0.62, 0.05, 0.04), rough=0.3, metal=0.4))
    for i in range(4):
        cyl("tire", (7.2, -0.8, 0.12 + i * 0.22), 0.34, 0.2, mat("rubber", (0.03, 0.03, 0.03), rough=0.8), verts=20)
    box("jack", (10.5, -6.5, 0.04), (11.3, -6.0, 0.23), mat("jack", (0.75, 0.1, 0.08), rough=0.4))
    COL = None


def build_site2():
    """Second dealership: a small block showroom with one service bay and a striped lot."""
    global COL
    COL = tier_collection("s2")
    white = mat("stucco", (0.86, 0.84, 0.8), rough=0.8)
    dark = mat("alu", (0.08, 0.08, 0.09))
    paint = mat("stripe", (0.92, 0.92, 0.88))
    build_lot_stalls("lot_t2", paint, block_mat("cmu2", (0.66, 0.65, 0.62), (0.72, 0.71, 0.68)))
    stall_stains("lot_t2", 2)
    arrow(-16.0, -27.0, math.radians(-6), paint, 1.1)
    for x in (-14, 12):
        box("planter2", (x - 1.5, -4.5, 0), (x + 1.5, -3.2, 0.5), mat("planter_c", (0.6, 0.58, 0.55)))
        box("planter2_soil", (x - 1.35, -4.35, 0.45), (x + 1.35, -3.35, 0.48), mat("bark_mulch", (0.16, 0.1, 0.06), rough=0.95))
        for dx in (-0.8, 0.8):
            shrub(x + dx, -3.85, 0.55, 0.75, z=0.45)
    palm((-18, -3.5, 0), h=9.0, seed=71)
    palm((15, -3.5, 0), h=10.0, seed=72)
    palm((-21.5, 1.0, 0), h=12.0, seed=73, kind="fan")
    light_pole(-17.0, -3.2, 7.5, ((0, -1),))
    shop_block(-36.0, -17.0, 2.0, 15.0, 1, SHOP_COLOURS[0], ((0.5, "SURF SHOP", (0.05, 0.25, 0.45), ((0.05, 0.25, 0.45), (0.92, 0.92, 0.88))),
                                                           (0.5, "DONUTS", (0.75, 0.1, 0.3), ((0.85, 0.35, 0.45), (0.95, 0.9, 0.85)))),
               sides=("e",), seed=21, side_sign=("SURF  SKATE", (0.95, 0.95, 0.92), (0.05, 0.25, 0.45)))
    shop_block(16.0, 34.0, 3.0, 14.0, 2, SHOP_COLOURS[4], ((1.0, "TIRES  BRAKES  SMOG", (0.95, 0.85, 0.3), None),), sides=("w",), seed=22)
    # small pylon
    box("pylon2", (-24, -28, 0), (-23.6, -27.6, 5.0), dark)
    box("pylon2_face", (-25.4, -28.1, 3.4), (-22.2, -27.5, 5.0), mat("pylon2_face", (0.95, 0.95, 0.93), rough=0.4))
    text("pylon2_txt", "CHIEF AUTO", (-23.8, -28.15, 4.05), 0.45, mat("sign_red", (0.75, 0.08, 0.06)), extrude=0.01)
    power_line(-110, 110, -57.0)
    # bunting along the roofline, behind the parked cars
    t0, t1 = flag_pole(-12.2, -1.6, 6.8), flag_pole(14.6, -1.6, 6.8)
    bunting_line(t0, t1, sag=1.0)
    # building shell x -10..6, y 0..12, 5 m tall, flat roof with a parapet
    B0, B1, D0, D1, H = -10.0, 6.0, 0.0, 12.0, 5.0
    floor = noise_mat("polished_concrete", (0.55, 0.55, 0.54), (0.66, 0.65, 0.63), 3, 0.25)
    box("b2_floor", (B0, D0, 0), (B1, D1, 0.05), floor)
    box("b2_roof", (B0 - 0.3, D0 - 0.3, H), (B1 + 0.3, D1 + 0.3, H + 0.5), white)
    box("b2_ceil", (B0, D0, H - 0.08), (B1, D1, H), mat("ceiling_tile", (0.85, 0.84, 0.8)))
    box("b2_west", (B0 - 0.25, D0, 0), (B0, D1, H), white)
    # storefront: glass between block piers
    for x0, x1 in ((B0, -8.6), (-1.6, 0.4), (4.6, B1)):
        box("b2_pier", (x0, D0 - 0.25, 0), (x1, D0, H), white)
    glass_wall("b2_front_a", (-8.6, D0 - 0.12), (-1.6, D0 - 0.12), 0, 3.4, every=2.4)
    glass_wall("b2_front_b", (0.4, D0 - 0.12), (4.6, D0 - 0.12), 0, 3.4, every=2.1)
    box("b2_band", (B0, D0 - 0.3, 3.4), (B1, D0, H), mat("acm_grey", (0.32, 0.34, 0.36), rough=0.35, metal=0.4))
    ledge = block_mat("ledgestone", (0.5, 0.44, 0.36), (0.62, 0.56, 0.46), (0.38, 0.35, 0.3), (0.55, 0.12), split=1.0)
    for x0, x1 in ((B0, -8.6), (-1.6, 0.4), (4.6, B1)):
        box("b2_stone", (x0 - 0.02, D0 - 0.33, 0), (x1 + 0.02, D0 - 0.25, 3.4), ledge)
    box("b2_stone_side", (B0 - 0.33, D0 - 0.33, 0), (B0 - 0.25, D1, 1.0), ledge)
    box("b2_fascia", (-8.6, D0 - 0.45, 3.7), (4.6, D0 - 0.3, 4.6), mat("navy_panel", (0.06, 0.1, 0.22), rough=0.4))
    text("b2_sign", "CHIEF AUTO", (-2.0, D0 - 0.48, 3.85), 0.6, mat("white_lit", (1, 1, 1), emit=2.0))
    # rear wall with two window strips onto the harbour
    for x0, x1 in ((B0, -7.0), (-3.0, -1.0), (3.0, B1)):
        box("b2_rear", (x0, D1, 0), (x1, D1 + 0.25, H), white)
    for x0, x1 in ((-7.0, -3.0), (-1.0, 3.0)):
        box("b2_rear_low", (x0, D1, 0), (x1, D1 + 0.25, 0.9), white)
        box("b2_rear_high", (x0, D1, 3.0), (x1, D1 + 0.25, H), white)
        g = box("b2_rear_glass", (x0, D1 + 0.11, 0.9), (x1, D1 + 0.14, 3.0), glass())
        g.visible_shadow = False
    lamp = mat("lamp", (1, 1, 1), emit=12, ecol=(1.0, 0.86, 0.68))
    for x in (-7, -3, 1, 4):
        for y in (3, 7, 10):
            box("b2_panel_light", (x - 0.5, y - 0.5, H - 0.1), (x + 0.5, y + 0.5, H - 0.08), lamp)
    # office partition at the back west corner (x -10..-5.5, y 8..12)
    box("b2_office_wall", (-5.6, 8.0, 0), (-5.5, 12.0, 3.0), white)
    box("b2_office_front", (B0, 7.95, 0), (-8.6, 8.05, 3.0), white)
    g = box("b2_office_glass", (-8.6, 7.98, 0.9), (-5.6, 8.02, 2.2), glass())
    g.visible_shadow = False
    box("b2_office_front_low", (-8.6, 7.95, 0), (-5.6, 8.05, 0.9), white)
    box("b2_office_front_hi", (-8.6, 7.95, 2.2), (-5.6, 8.05, 3.0), white)
    wood = noise_mat("oak2", (0.4, 0.27, 0.15), (0.5, 0.35, 0.2), 6, 0.45, stretch=(1, 14, 1))
    box("b2_exec_desk", (-9.4, 10.2, 0), (-7.4, 11.0, 0.76), wood)
    box("b2_exec_mon", (-8.8, 10.8, 0.8), (-8.0, 10.84, 1.3), mat("screen", (0.02, 0.05, 0.1), emit=0.6, ecol=(0.3, 0.55, 0.9)))
    chair(-8.4, 11.5, math.pi, mat("leather_brown", (0.16, 0.08, 0.04), rough=0.35))
    build_office_t2()
    box("b2_filing", (-6.2, 11.3, 0), (-5.7, 11.9, 1.3), mat("filing", (0.5, 0.52, 0.55), metal=0.6, rough=0.4))
    # reception and the PC desk
    box("b2_reception", (1.0, 8.5, 0), (4.0, 9.2, 1.05), white)
    box("b2_reception_top", (0.9, 8.4, 1.05), (4.1, 9.3, 1.1), wood)
    box("b2_pc_desk", (3.6, 10.8, 0), (5.8, 11.8, 0.76), wood)
    box("b2_pc_mon", (4.3, 11.5, 0.8), (5.1, 11.54, 1.3), mat("screen", (0.02, 0.05, 0.1)))
    box("b2_sales_desk", (-9.4, 2.8, 0.72), (-7.4, 3.7, 0.76), wood)
    for x in (-9.3, -7.5):
        box("b2_sd_leg", (x - 0.03, 2.85, 0), (x + 0.03, 3.65, 0.72), dark)
    planter(5.4, 1.0)
    planter(-9.4, 7.2)
    # one service bay on the east (x 6..13)
    block = mat("block", (0.62, 0.62, 0.6), rough=0.8)
    epoxy = noise_mat("epoxy2", (0.33, 0.35, 0.37), (0.4, 0.42, 0.44), 12, 0.3)
    box("bay2_floor", (6.0, 0, 0), (13.0, 12.0, 0.04), epoxy)
    box("bay2_roof", (6.0, -0.3, 4.6), (13.3, 12.3, 5.0), white)
    box("bay2_ceil", (6.0, 0, 4.5), (13.0, 12.0, 4.6), mat("ceiling_tile", (0.85, 0.84, 0.8)))
    box("bay2_east", (13.0, 0, 0), (13.3, 12.0, 4.6), block)
    box("bay2_back", (6.0, 11.8, 0), (13.0, 12.0, 4.6), block)
    box("bay2_divider", (6.0, 0.3, 0), (6.25, 12.0, 4.6), block)
    box("bay2_head", (6.25, -0.15, 3.9), (13.0, 0.15, 4.6), white)
    box("bay2_roll", (6.6, -0.3, 3.7), (12.6, 0.0, 3.9), mat("rollup", (0.7, 0.72, 0.75), metal=0.6, rough=0.4))
    text("bay2_txt", "SERVICE", (9.6, -0.2, 4.05), 0.4, mat("bay_txt", (0.95, 0.75, 0.2), emit=1.0))
    yellow = mat("lift", (0.95, 0.72, 0.05), rough=0.4)
    for side in (-1.5, 1.5):
        box("lift2_post", (9.6 + side - 0.14, 8.0, 0), (9.6 + side + 0.14, 8.3, 3.4), yellow)
    for x in range(7, 12):
        box("tube2", (x - 0.4, 6.0, 4.4), (x + 0.4, 6.2, 4.45), lamp)
    tool_red = mat("toolbox", (0.62, 0.05, 0.04), rough=0.3, metal=0.4)
    box("toolbox2", (11.0, 11.0, 0), (12.8, 11.7, 1.0), tool_red, bevel=0.02)
    box("peg2", (7.0, 11.75, 1.2), (10.5, 11.8, 2.9), mat("peg", (0.65, 0.5, 0.33), rough=0.8))
    cyl("tires2", (7.4, 10.8, 0.6), 0.36, 1.2, mat("rubber", (0.03, 0.03, 0.03)), verts=20)
    COL = None


def tier_collection(t):
    c = bpy.data.collections.new("set_%s" % t)
    bpy.context.scene.collection.children.link(c)
    TIER_COLLECTIONS[t] = c
    return c


def build_apartment_tiers():
    """Tier 1: a mattress in a bare room. Tier 2: a proper condo. Tier 3: the Tewport penthouse."""
    global COL
    lamp = mat("lamp", (1, 1, 1), emit=12, ecol=(1.0, 0.86, 0.68))
    # tier 1: a small starter apartment (bed, a two-seat sofa, a kitchenette, warm lamps)
    COL = tier_collection(1)
    floor1 = noise_mat("t1_laminate", (0.3, 0.2, 0.13), (0.38, 0.26, 0.17), 6, 0.45, stretch=(1, 14, 1))
    box("t1_floor", (AX0, AY0, AZ0 + 0.06), (AX1, AY1, AZ0 + 0.075), floor1)
    box("t1_wall_tint", (AX0 + 0.01, AY0, AZ0), (AX0 + 0.02, AY1, AZ1), mat("t1_wall", (0.62, 0.55, 0.47), rough=0.85))
    grey = mat("t1_fabric", (0.22, 0.22, 0.24), rough=0.9)
    box("t1_bed", (-14.0, 9.0, AZ0 + 0.07), (-11.8, 11.2, AZ0 + 0.55), mat("t1_sheet", (0.82, 0.8, 0.76), rough=0.9), bevel=0.08)
    box("t1_blanket", (-14.0, 9.9, AZ0 + 0.5), (-11.8, 11.25, AZ0 + 0.6), mat("t1_blanket", (0.45, 0.4, 0.33), rough=0.95), bevel=0.05)
    box("t1_pillow", (-13.9, 9.05, AZ0 + 0.55), (-11.9, 9.5, AZ0 + 0.7), mat("t1_pillow", (0.9, 0.9, 0.9), rough=0.9), bevel=0.06)
    box("t1_sofa", (-9.0, 11.3, AZ0 + 0.07), (-6.8, 12.1, AZ0 + 0.48), grey, bevel=0.08)
    box("t1_sofa_back", (-9.0, 11.1, AZ0 + 0.07), (-6.8, 11.35, AZ0 + 0.9), grey, bevel=0.08)
    box("t1_coffee", (-8.6, 12.5, AZ0 + 0.07), (-7.2, 13.2, AZ0 + 0.42), mat("t1_walnut", (0.2, 0.12, 0.07), rough=0.4))
    box("t1_rug", (-9.4, 11.0, AZ0 + 0.075), (-6.4, 13.8, AZ0 + 0.085), mat("t1_rug", (0.6, 0.55, 0.48), rough=0.95))
    white = mat("t1_cabinet", (0.9, 0.9, 0.88), rough=0.4)
    box("t1_counter", (-4.0, 4.0, AZ0 + 0.07), (1.5, 4.7, AZ0 + 0.92), white)
    box("t1_counter_top", (-4.05, 3.95, AZ0 + 0.92), (1.55, 4.75, AZ0 + 0.96), mat("t1_stone", (0.25, 0.25, 0.26), rough=0.3))
    box("t1_island", (-3.0, 6.2, AZ0 + 0.07), (0.5, 6.9, AZ0 + 0.95), white)
    for x in (-2.4, -1.3, -0.2):
        cyl("t1_stool", (x, 7.3, AZ0 + 0.38), 0.18, 0.7, mat("t1_stool", (0.15, 0.12, 0.1)), verts=12)
    box("t1_fridge", (1.6, 3.9, AZ0 + 0.07), (2.4, 4.7, AZ0 + 1.9), mat("t1_steel", (0.6, 0.6, 0.62), metal=0.8, rough=0.3))
    box("t1_upper", (-4.0, 3.75, AZ0 + 1.6), (1.5, 4.1, AZ0 + 2.3), white)
    lampm = mat("t1_lamp", (1, 0.85, 0.65), emit=6, ecol=(1, 0.8, 0.55))
    cyl("t1_floorlamp", (-10.2, 11.9, AZ0 + 0.8), 0.03, 1.5, mat("t1_stool", (0.15, 0.12, 0.1)), verts=8)
    cyl("t1_shade", (-10.2, 11.9, AZ0 + 1.6), 0.22, 0.3, lampm, r2=0.15)
    for x in (-3.0, -1.0):
        cyl("t1_pendant", (x, 6.5, AZ1 - 0.5), 0.12, 0.2, lampm, r2=0.04)
    box("t1_tv", (-5.2, 12.0, AZ0 + 0.6), (-5.15, 13.4, AZ0 + 1.4), mat("t2_screen", (0.01, 0.01, 0.01), rough=0.05))
    planter_at(-5.6, 15.2)
    # tier 2
    COL = tier_collection(2)
    oak = noise_mat("t2_oak", (0.5, 0.36, 0.22), (0.62, 0.46, 0.3), 6, 0.4, stretch=(1, 14, 1))
    box("t2_floor", (AX0, AY0, AZ0 + 0.06), (AX1, AY1, AZ0 + 0.075), oak)
    navy = mat("t2_fabric", (0.12, 0.17, 0.3), rough=0.85)
    box("t2_bed", (-13.5, 4.0, AZ0 + 0.07), (-11.0, 6.4, AZ0 + 0.6), mat("t2_duvet", (0.9, 0.9, 0.92), rough=0.9), bevel=0.1)
    box("t2_headboard", (-13.5, 3.8, AZ0), (-11.0, 4.0, AZ0 + 1.3), navy, bevel=0.03)
    box("t2_sofa", (-7.5, 10.5, AZ0 + 0.07), (-4.0, 11.4, AZ0 + 0.5), navy, bevel=0.1)
    box("t2_sofa_back", (-7.5, 10.3, AZ0 + 0.07), (-4.0, 10.6, AZ0 + 0.95), navy, bevel=0.1)
    box("t2_coffee", (-6.5, 12.2, AZ0 + 0.07), (-5.0, 13.0, AZ0 + 0.45), oak)
    box("t2_tv_unit", (-1.5, 9.5, AZ0 + 0.07), (0.5, 12.5, AZ0 + 0.55), mat("t2_white", (0.92, 0.92, 0.9), rough=0.4))
    box("t2_tv", (0.2, 9.8, AZ0 + 0.9), (0.26, 12.2, AZ0 + 2.1), mat("t2_screen", (0.01, 0.01, 0.01), rough=0.05))
    box("t2_rug", (-8.0, 11.6, AZ0 + 0.075), (-3.5, 14.2, AZ0 + 0.085), mat("t2_rug", (0.7, 0.66, 0.6), rough=0.95))
    for x in (-10, -4, 0):
        cyl("t2_pendant", (x, 8, AZ1 - 0.6), 0.22, 0.3, lamp, r2=0.05)
    planter_at(1.6, 15.2)
    # tier 3
    COL = tier_collection(3)
    stone = noise_mat("t3_marble", (0.95, 0.94, 0.92), (0.35, 0.32, 0.3), 1.4, 0.1, veins=True)
    box("t3_floor", (AX0, AY0, AZ0 + 0.06), (AX1, AY1, AZ0 + 0.08), stone)
    cream = mat("t3_leather", (0.88, 0.84, 0.76), rough=0.45)
    box("t3_bed", (-14.0, 3.8, AZ0 + 0.08), (-10.6, 6.9, AZ0 + 0.7), mat("t3_duvet", (0.96, 0.95, 0.93), rough=0.9), bevel=0.12)
    box("t3_headboard", (-14.2, 3.6, AZ0), (-10.4, 3.85, AZ0 + 1.7), mat("t3_velvet", (0.22, 0.12, 0.08), rough=0.8), bevel=0.04)
    # sectional sofa facing the harbour
    box("t3_sofa_a", (-9.0, 11.0, AZ0 + 0.08), (-3.0, 12.1, AZ0 + 0.5), cream, bevel=0.12)
    box("t3_sofa_ab", (-9.0, 10.7, AZ0 + 0.08), (-3.0, 11.1, AZ0 + 0.95), cream, bevel=0.12)
    box("t3_sofa_b", (-9.0, 11.0, AZ0 + 0.08), (-7.9, 14.5, AZ0 + 0.5), cream, bevel=0.12)
    box("t3_table", (-6.6, 12.7, AZ0 + 0.08), (-4.4, 14.0, AZ0 + 0.4), mat("t3_brass", (0.8, 0.6, 0.3), rough=0.2, metal=1.0))
    # bar with stools
    walnut = noise_mat("t3_walnut", (0.18, 0.1, 0.06), (0.28, 0.16, 0.09), 6, 0.3, stretch=(1, 14, 1))
    box("t3_bar", (-1.5, 6.0, AZ0 + 0.08), (1.8, 6.9, AZ0 + 1.1), walnut, bevel=0.02)
    box("t3_bar_top", (-1.6, 5.9, AZ0 + 1.1), (1.9, 7.0, AZ0 + 1.15), stone)
    for i in range(6):
        box("t3_bottle", (-1.2 + i * 0.5, 4.0, AZ0 + 1.6), (-1.1 + i * 0.5, 4.1, AZ0 + 1.95),
            mat("t3_glassb%d" % (i % 3), [(0.3, 0.12, 0.05), (0.1, 0.3, 0.12), (0.8, 0.6, 0.2)][i % 3], rough=0.05, trans=0.6))
    box("t3_shelf", (-1.6, 3.8, AZ0 + 1.55), (1.9, 4.2, AZ0 + 1.6), mat("t3_brass", (0.8, 0.6, 0.3)))
    for x in (-1.0, 0.2, 1.4):
        cyl("t3_stool", (x, 7.3, AZ0 + 0.4), 0.2, 0.75, mat("t3_brass", (0.8, 0.6, 0.3)), verts=12)
    # balcony hot tub and loungers
    box("t3_tub", (-3.5, AY1 + 0.6, AZ0), (-0.5, AY1 + 3.0, AZ0 + 0.7), mat("t3_tub", (0.85, 0.85, 0.83), rough=0.3), bevel=0.1)
    box("t3_tub_water", (-3.3, AY1 + 0.8, AZ0 + 0.55), (-0.7, AY1 + 2.8, AZ0 + 0.66),
        mat("t3_tubwater", (0.2, 0.6, 0.7), rough=0.02, trans=0.8, emit=1.5, ecol=(0.3, 0.8, 0.9)))
    for x in (-12.0, -9.6):
        box("t3_lounger", (x, AY1 + 0.8, AZ0 + 0.06), (x + 0.8, AY1 + 2.9, AZ0 + 0.4), mat("t3_cushion", (0.95, 0.95, 0.93), rough=0.8), bevel=0.05)
    for x in (-11, -6, -1):
        sphere("t3_globe", (x, 9, AZ1 - 0.6), (0.16, 0.16, 0.16), mat("t3_globe_lit", (1, 0.9, 0.75), emit=4, ecol=(1, 0.85, 0.6)))
    box("t3_art", (AX1 - 0.02, 7.0, AZ0 + 1.2), (AX1, 11.0, AZ0 + 2.8), mat("t3_art", (0.7, 0.25, 0.1), rough=0.6, emit=0.2))
    planter_at(-14.0, 15.3)
    planter_at(2.0, 15.3)
    COL = None


def planter_at(x, y):
    """Planter sitting on the apartment floor."""
    pot = mat("pot", (0.12, 0.12, 0.12), rough=0.4)
    cyl("pot", (x, y, AZ0 + 0.4), 0.35, 0.7, pot, r2=0.28)
    leaf = mat("fig", (0.1, 0.28, 0.08))
    rnd = random.Random(int(x * 10 + y))
    for i in range(10):
        sphere("leaves", (x + rnd.uniform(-0.3, 0.3), y + rnd.uniform(-0.3, 0.3), AZ0 + 1.0 + rnd.uniform(0, 1.0)), (0.28, 0.28, 0.24), leaf, seg=10)


def import_car(slug, loc, yaw, color):
    """Places one of the game's own cars (assets/cars3d/<slug>.glb) with a fresh paint material."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "cars3d", slug + ".glb")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    paint = mat("paint_" + slug, color, rough=0.15, metal=0.6)
    pivot = bpy.data.objects.new("car_" + slug, None)
    pivot.location = loc
    pivot.rotation_euler.z = yaw
    _link(pivot)
    for o in new:
        _link(o)
        if o.parent is None:
            o.parent = pivot
        if o.type == "MESH" and o.name.startswith(("part_hood", "part_door", "part_fender", "part_quarter", "part_roof", "part_trunk", "part_front_bumper", "part_rear_bumper")):
            o.data.materials.clear()
            o.data.materials.append(paint)


def build_deal_props():
    """Only for the deal-desk view: a sales desk in the showroom and two cars on display."""
    global COL
    COL = tier_collection(9)
    glass_top = mat("desk_glass", (0.75, 0.85, 0.85), rough=0.03, trans=0.85)
    dark = mat("alu", (0.08, 0.08, 0.09))
    box("sales_desk_top", (-4.6, 5.6, 0.74), (-1.0, 6.6, 0.77), glass_top).visible_shadow = False
    for x in (-4.5, -1.1):
        box("sales_desk_leg", (x - 0.03, 5.65, 0), (x + 0.03, 6.55, 0.74), dark)
    leather = noise_mat("folio", (0.25, 0.14, 0.07), (0.33, 0.19, 0.1), 40, 0.45)
    box("folio", (-3.3, 5.75, 0.77), (-2.5, 6.25, 0.8), leather, bevel=0.01)
    box("card_tray", (-1.9, 5.9, 0.77), (-1.5, 6.2, 0.83), leather, bevel=0.01)
    cyl("pen_cup", (-1.25, 6.3, 0.84), 0.05, 0.14, mat("chrome", (0.8, 0.8, 0.82)), verts=16)
    import_car("porsha_911", (1.6, 10.8, 0.05), math.radians(-28), (0.62, 0.63, 0.65))
    import_car("rang_rovah", (8.5, 11.5, 0.05), math.radians(-38), (0.03, 0.03, 0.035))
    COL = None


def show_sets(keys):
    for k, c in TIER_COLLECTIONS.items():
        c.hide_render = k not in keys


# ---------------------------------------------------------------- render

def setup_render():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 6
    sc.cycles.transmission_bounces = 6
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.render.resolution_x, sc.render.resolution_y = RES
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 88
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Punchy"
    sc.view_settings.exposure = 0.0
    cam = bpy.data.cameras.new("cam")
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return co


VIEWS = {
    # name: (camera position, look-at target, lens mm, exposure). Names ending in _t1/_t2 are the smaller dealerships.
    # lot cameras: 50 mm like the car sprites, high enough to look down on the stalls at the sprites' angle
    "lot": ((-26.0, -56.0, 7.88), (-20.82, -36.68, 6.48), 50, 0.2),
    "showroom": ((0.0, 0.8, 1.65), (0.0, 16.0, 1.45), 18, -0.3),
    "office": ((-8.6, 9.6, 1.55), (-13.0, 15.5, 1.3), 18, -0.3),
    "garage": ((24.5, 0.9, 1.7), (24.5, 16.0, 1.6), 17, -0.2),
    "desk": ((11.5, 12.6, 1.25), (11.5, 16.0, 1.05), 24, -0.3),
    "dealdesk": ((-3.4, 4.3, 1.3), (1.5, 16.0, 0.9), 20, -0.3),
    "apartment": ((-12.5, 4.6, AZ0 + 1.6), (-3.0, 16.0, AZ0 + 1.2), 17, -0.2),
    "lot_t1": ((-10.5, -43.0, 5.68), (-10.5, -23.0, 4.28), 50, 0.2),
    "showroom_t1": ((-1.0, -26.0, 1.65), (-1.0, -10.0, 1.45), 18, 0.0),   # customers browse outside on the lot
    "office_t1": ((-3.5, 5.4, 1.6), (-9.0, -1.0, 1.3), 18, 0.0),
    "garage_t1": ((11.0, -12.0, 1.7), (11.0, 2.0, 1.6), 18, -0.5),
    "desk_t1": ((-7.9, 5.9, 1.35), (-7.9, -1.0, 1.2), 24, 0.0),
    "dealdesk_t1": ((-4.3, 5.6, 1.35), (-9.5, -1.0, 0.9), 20, 0.0),
    "lot_t2": ((-14.5, -46.0, 6.46), (-10.34, -26.44, 5.06), 50, 0.2),
    "showroom_t2": ((-2.0, 0.6, 1.65), (-2.0, 12.0, 1.45), 18, -0.2),
    "office_t2": ((-6.0, 8.6, 1.55), (-9.8, 12.0, 1.3), 18, -0.2),
    "garage_t2": ((9.6, 0.9, 1.7), (9.6, 12.0, 1.6), 17, -0.2),
    "desk_t2": ((4.7, 9.6, 1.25), (4.7, 12.0, 1.05), 24, -0.2),
    "dealdesk_t2": ((-8.6, 1.6, 1.3), (-4.0, 12.0, 0.9), 20, -0.2),
}


def render_view(cam, name, out):
    if name.startswith("apartment"):
        key, sets = "apartment", {"s3", int(name[-1])}
    else:
        key = name
        tier = name[-1] if name[-3:-1] == "_t" else "3"
        sets = {"s" + tier}
        if name == "dealdesk":
            sets.add(9)
    pos, tgt, lens, exp = VIEWS[key]
    show_sets(sets)
    cam.location = pos
    cam.data.lens = lens
    cam.data.clip_end = 5000
    cam.rotation_euler = (Vector(tgt) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.view_settings.exposure = exp - 0.6   # daylight is bright; keep whites from blowing out
    bpy.context.scene.render.filepath = os.path.join(out, "bg_%s.jpg" % name)
    if name in LOT_ROWS:
        export_stalls(name, cam, os.path.join(out, "stalls_%s.json" % name))
    bpy.ops.render.render(write_still=True)


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    build_world()
    build_ground()
    build_harbour()
    global COL
    COL = tier_collection("s3")
    build_site3_front()
    build_dealership()
    COL = None
    build_site1()
    build_site2()
    build_apartment_tiers()
    build_deal_props()
    # interior fill so rooms are not black against the bright sky, per dealership
    fills = {"s3": (((0, 8, 5.5), (28, 14), 2400), ((-11.5, 12.5, 5.5), (6, 6), 500),
                    ((24, 8, 5.8), (16, 14), 2600), ((-6, 9.5, AZ1 - 0.3), (16, 11), 1300)),
             "s1": (((-7.0, 3.0, OH - 0.7), (9, 7), 700),),
             "s2": (((-2, 6, 4.8), (15, 11), 1500), ((-7.8, 10, 2.9), (4, 3.5), 250), ((9.6, 6, 4.4), (6, 11), 1200))}
    for key, rows in fills.items():
        for loc, size, e in rows:
            ld = bpy.data.lights.new("fill", "AREA")
            ld.shape = "RECTANGLE"
            ld.size, ld.size_y = size
            ld.energy = e
            ld.color = (1.0, 0.9, 0.78)
            lo = bpy.data.objects.new("fill", ld)
            lo.location = loc
            TIER_COLLECTIONS[key].objects.link(lo)


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    views = sys.argv[2:] or [v + t for t in ("", "_t1", "_t2") for v in ("lot", "showroom", "office", "garage", "desk", "dealdesk")] + \
        ["apartment1", "apartment2", "apartment3"]
    build()
    cam = setup_render()
    for v in views:
        render_view(cam, v, out)


if __name__ == "__main__":
    main()
