"""One Chief Auto dealership in Tewport Beach, built in Blender: every background in the game is rendered from it.

The site: a glass showroom on the harbour. The lot faces the street (south), the showroom looks out over the
marina (north), the service bay is the wing on the east side, Marco's office is the glass corner room at the
back west, and the owner's apartment sits on the roof. Apartment tiers (1-3) toggle furniture and finish, so
the same room can be upgraded visually in the game; the showroom tiers work the same way.

Usage (bpy venv):  python tools/dealership3d.py <out_dir> [view ...]
Views: lot, showroom, office, garage, desk, dealdesk (add _t1 / _t2 for the starting and mid-size
dealerships), apartment1, apartment2, apartment3.  SAMPLES env sets quality, PREVIEW=1 renders 640x360.
NIGHT=1 renders the same views at night as bg_<view>_night.jpg (make_night: dark blue starry sky, no sun, lit
street lamps, pole sign and lot lights, interiors at full light); the game crossfades day to night by the clock.
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
# 2560x1440 so the backgrounds stay sharp on big fullscreen monitors (the game stretches its 1280x720 canvas)
RES = (640, 360) if os.environ.get("PREVIEW") else ((1920, 1080) if os.environ.get("HD") else (2560, 1440))
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


# ---------------------------------------------------------------- planting: leaf textures drawn here, cards in Blender

def _pil_image(name, draw, size, ss=2, bg=(60, 100, 36)):
    """A packed RGBA image drawn with PIL (draw(img, scale) paints at ss times the size, then it is downsampled).
    The transparent background carries a leaf colour so filtering at the cut edges does not darken them."""
    if name in bpy.data.images:
        return bpy.data.images[name]
    import numpy as np
    from PIL import Image
    big = Image.new("RGBA", (size[0] * ss, size[1] * ss), bg + (0,))
    draw(big, ss)
    img = big.resize(size, Image.LANCZOS)
    a = np.asarray(img, dtype=np.float32)[::-1] / 255.0
    im = bpy.data.images.new(name, size[0], size[1], alpha=True)
    im.pixels.foreach_set(a.ravel())
    im.pack()
    return im


def _leaf_poly(d, base, tip, w0, col):
    """A tapered leaf from base to tip, w0 wide at the base, slightly fuller a third of the way out."""
    bx, by = base
    tx, ty = tip
    dx, dy = tx - bx, ty - by
    ln = math.hypot(dx, dy) or 1
    nx, ny = -dy / ln, dx / ln
    pts = []
    for t, w in ((0.0, 0.5), (0.3, 1.0), (0.7, 0.6), (1.0, 0.0)):
        pts.append((bx + dx * t + nx * w0 * w, by + dy * t + ny * w0 * w))
    pts += [(bx + dx * t - nx * w0 * w, by + dy * t - ny * w0 * w) for t, w in ((0.7, 0.6), (0.3, 1.0), (0.0, 0.5))]
    d.polygon(pts, fill=col)


def frond_image(kind="green"):
    """A pinnate palm frond, base at the left, tip at the right, rib along the middle (1024 x 256)."""
    def draw(img, s):
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        rnd = random.Random(7 if kind == "green" else 8)
        W, H = img.size
        cy = H / 2
        if kind == "green":
            pal = [(52, 92, 30), (66, 108, 36), (80, 120, 42), (44, 80, 26), (96, 128, 50)]
        else:
            pal = [(150, 112, 62), (128, 92, 50), (170, 134, 80), (110, 80, 44)]
        n = 70
        for i in range(n):
            u = 0.05 + 0.94 * i / n
            for side in (-1, 1):
                ln = (0.47 * math.sin(math.pi * min(1.0, u * 1.05)) ** 0.55 + 0.03) * H
                bx = u * W
                tip = (bx + ln * rnd.uniform(0.7, 1.0) * 1.1, cy + side * ln * rnd.uniform(0.85, 1.0))
                _leaf_poly(d, (bx, cy), tip, 2.6 * s + 3.5 * s * math.sin(math.pi * u), rnd.choice(pal) + (255,))
        d.line([(0, cy), (W, cy)], fill=(120, 110, 60, 255) if kind == "green" else (120, 90, 50, 255), width=int(5 * s))
    return _pil_image("tex_frond_" + kind, draw, (1024, 256))


FAN_C, FAN_R = (0.5, 0.03), 0.93    # fan texture: centre (u, v) and radius (fraction of the image height)


def fan_image(kind="green"):
    """A Washingtonia fan leaf: radiating split segments from the petiole at the bottom middle (1024 x 512)."""
    def draw(img, s):
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        rnd = random.Random(11 if kind == "green" else 12)
        W, H = img.size
        cx, cy, R = W * FAN_C[0], H * (1 - FAN_C[1]), H * FAN_R
        pal = [(60, 100, 40), (74, 116, 46), (88, 126, 52), (54, 92, 36)] if kind == "green" else \
              [(160, 124, 72), (140, 104, 60), (176, 142, 90)]
        segs = 46
        for j in range(segs):
            a0 = math.radians(-100 + 200 * j / segs)
            a1 = math.radians(-100 + 200 * (j + 1) / segs)
            am = (a0 + a1) / 2
            r_split = R * rnd.uniform(0.55, 0.7)
            r_tip = R * rnd.uniform(0.92, 1.0)
            col = rnd.choice(pal) + (255,)
            p = lambda a, r: (cx + r * math.sin(a), cy - r * math.cos(a))  # noqa: E731
            d.polygon([p(am, R * 0.06), p(a0, r_split), p(am - 0.01, r_tip), p(am + 0.01, r_tip), p(a1, r_split)], fill=col)
            # the split tips hang as thin threads
            d.line([p(am, r_split), p(am + rnd.uniform(-0.05, 0.05), r_tip * 1.0)], fill=col, width=int(2 * s))
    return _pil_image("tex_fan_" + kind, draw, (1024, 512))


def foliage_image(kind="shrub"):
    """A clump of leaves (shrub, hedge, house plant) or bougainvillea bracts for leaf cards (512 x 512)."""
    def draw(img, s):
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        rnd = random.Random({"shrub": 21, "bouga": 22, "fig": 23}[kind])
        W, H = img.size
        greens = [(40, 80, 28), (54, 98, 34), (70, 112, 40), (34, 66, 24), (86, 120, 46)]
        n = 160 if kind != "fig" else 40
        for i in range(n):
            r = (rnd.random() ** 0.6) * 0.46
            a = rnd.uniform(0, math.tau)
            cx, cy = W * (0.5 + r * math.cos(a)), H * (0.5 + r * math.sin(a))
            ang = rnd.uniform(0, math.tau)
            ln = (0.07 if kind != "fig" else 0.16) * W * rnd.uniform(0.7, 1.2)
            tip = (cx + ln * math.cos(ang), cy + ln * math.sin(ang))
            _leaf_poly(d, (cx, cy), tip, ln * (0.28 if kind != "fig" else 0.4), rnd.choice(greens) + (255,))
        if kind == "bouga":
            mag = [(205, 30, 120), (225, 50, 140), (180, 20, 100), (235, 90, 165)]
            for i in range(210):
                r = (rnd.random() ** 0.5) * 0.45
                a = rnd.uniform(0, math.tau)
                cx, cy = W * (0.5 + r * math.cos(a)), H * (0.5 + r * math.sin(a))
                rr = W * rnd.uniform(0.008, 0.016)
                col = rnd.choice(mag) + (255,)
                for k in range(3):
                    aa = k / 3 * math.tau + rnd.uniform(0, 1)
                    d.ellipse([cx + rr * math.cos(aa) - rr, cy + rr * math.sin(aa) - rr, cx + rr * math.cos(aa) + rr,
                               cy + rr * math.sin(aa) + rr], fill=col)
    return _pil_image("tex_foliage_" + kind, draw, (512, 512))


def card_mat(name, img, tint=(1.0, 1.0, 1.0), trans=0.3, rough=0.55, vary=0.15):
    """Alpha-cut leaf card material: the image's colour (tinted, varied per object) over a translucent leaf."""
    if name in _mats:
        return _mats[name]
    m, nt, b = _node_mat(name)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Linear"
    nt.links.new(_coords(nt, "UV"), tex.inputs["Vector"])
    info = nt.nodes.new("ShaderNodeObjectInfo")
    shade = _ramp(nt, info.outputs["Random"], ((0.0, tuple(c * (1 - vary) for c in tint)), (1.0, tuple(min(2, c * (1 + vary)) for c in tint))))
    col = _mix(nt, 1.0, tex.outputs["Color"], shade, "MULTIPLY")
    nt.links.new(col, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = rough
    tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
    nt.links.new(col, tr.inputs["Color"])
    leaf = nt.nodes.new("ShaderNodeMixShader")
    leaf.inputs["Fac"].default_value = trans
    nt.links.new(b.outputs[0], leaf.inputs[1])
    nt.links.new(tr.outputs[0], leaf.inputs[2])
    clear = nt.nodes.new("ShaderNodeBsdfTransparent")
    cut = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(_math(nt, "GREATER_THAN", tex.outputs["Alpha"], 0.4), cut.inputs["Fac"])
    nt.links.new(clear.outputs[0], cut.inputs[1])
    nt.links.new(leaf.outputs[0], cut.inputs[2])
    nt.links.new(cut.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    _mats[name] = m
    return m


def cards_obj(name, quads, m, smooth=False):
    """One mesh of textured cards: quads is a list of (4 corner points, 4 uvs) or ribbons (rows of points, uvs)."""
    vs, fs, uvs = [], [], []
    for pts, uv in quads:
        base = len(vs)
        vs.extend(pts)
        uvs.extend(uv)
        fs.append(tuple(range(base, base + len(pts))))
    return _uv_mesh(name, vs, fs, uvs, m, smooth)


def _uv_mesh(name, vs, fs, uvs, m, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in vs], [], fs)
    lay = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            lay.data[li].uv = uvs[me.loops[li].vertex_index]
    me.materials.append(m)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    _link(ob)
    return ob


def _ribbon(vs, fs, uvs, rows):
    """Adds a ribbon (list of rows of (point, uv)) as quads between consecutive rows."""
    base = len(vs)
    w = len(rows[0])
    for row in rows:
        for p, uv in row:
            vs.append(p)
            uvs.append(uv)
    for i in range(len(rows) - 1):
        for j in range(w - 1):
            a = base + i * w + j
            fs.append((a, a + 1, a + w + 1, a + w))


def palm(loc, h=9.0, seed=0, kind="date", lod=False):
    """A palm: a ringed, slightly curved trunk and a crown of textured frond cards.
    kind "date": stout date palm with long arching pinnate fronds; "queen": slim, soft drooping fronds;
    "fan": the tall skinny Washingtonia fan palm of the Southern California streets, with a skirt of dead fronds."""
    rnd = random.Random(seed)
    loc = Vector(loc)
    kind = {"fan": "fan"}.get(kind, kind)
    lean_dir = Vector((math.cos(rnd.uniform(0, math.tau)), math.sin(rnd.uniform(0, math.tau)), 0))
    lean = rnd.uniform(0.02, 0.07 if kind != "fan" else 0.05) * h
    r0 = {"date": 0.38, "queen": 0.2, "fan": 0.22}[kind]
    pts, radii = [], []
    nseg = 6 if lod else 15
    for k in range(nseg):
        t = k / (nseg - 1)
        pts.append(loc + lean_dir * lean * t ** 1.7 + Vector((0, 0, h * t)))
        flare = 1.0 + (0.7 if kind == "fan" else 0.5) * max(0.0, 1 - t * 8)
        radii.append(r0 * flare * (1 - 0.22 * t) * (1.3 if kind == "date" and t > 0.92 else 1.0))
    trunk = tube("palm_trunk", pts, radii, bark_mat("bark_" + kind, (0.27, 0.23, 0.19), (0.42, 0.37, 0.3),
                                                    ring=0.08 if kind == "fan" else 0.16), sides=6 if lod else 12)
    top = pts[-1]
    vs, fs, uvs = [], [], []
    dvs, dfs, duvs = [], [], []

    def frond(az, elev, length, droop, dead=False, segs=None):
        segs = segs or (4 if lod else 10)
        hd = Vector((math.cos(az), math.sin(az), 0))
        sd = Vector((-hd.y, hd.x, 0))
        half = length * 0.17
        rows = []
        for i in range(segs + 1):
            s = i / segs
            d = s * length
            p = top + hd * (math.cos(elev) * d) + Vector((0, 0, math.sin(elev) * d - droop * d * d))
            fold = math.radians(28 - 55 * s)              # leaflets V up near the base, hang at the tip
            wv = sd * math.cos(fold) * half
            up = Vector((0, 0, math.sin(fold) * half))
            twist = Vector((0, 0, 0))
            rows.append([(p - wv + up + twist, (s, 0.0)), (p, (s, 0.5)), (p + wv + up, (s, 1.0))])
        _ribbon(dvs if dead else vs, dfs if dead else fs, duvs if dead else uvs, rows)

    def fan_leaf(az, elev, dead=False):
        hd = Vector((math.cos(az), math.sin(az), 0))
        sd = Vector((-hd.y, hd.x, 0))
        out = hd * math.cos(elev) + Vector((0, 0, math.sin(elev)))
        stem = top + out * 0.9
        R = 1.25
        nrm = (out.cross(sd)).normalized()          # leaf plane: spanned by out and sd
        tvs, tfs, tuvs = (dvs, dfs, duvs) if dead else (vs, fs, uvs)
        base = len(tvs)
        tvs.append(stem)
        tuvs.append(FAN_C)
        segs = 10 if lod else 22
        for j in range(segs + 1):
            a = math.radians(-100 + 200 * j / segs)
            v = out * math.cos(a) + sd * math.sin(a)
            fold = (0.09 if j % 2 else -0.05) * R
            p = stem + v * R + nrm * fold + Vector((0, 0, -0.3 * R * abs(math.sin(a)) ** 1.5))
            tvs.append(p)
            tuvs.append((FAN_C[0] + FAN_R * 0.5 * math.sin(a), FAN_C[1] + FAN_R * math.cos(a)))
        for j in range(segs):
            tfs.append((base, base + 1 + j, base + 2 + j))
        # petiole
        pv, pf = tube_geo([top, stem], [0.04, 0.03], 4)
        b2 = len(tvs)
        tvs.extend(pv)
        tuvs.extend([(0.5, 0.01)] * len(pv))
        tfs.extend(tuple(b2 + q for q in f) for f in pf)

    if kind == "fan":
        for i in range(10 if lod else 20):
            fan_leaf(i / (10 if lod else 20) * math.tau + rnd.uniform(-0.2, 0.2), math.radians(rnd.uniform(-20, 60)))
        # the skirt of old fronds hanging down the trunk under the crown
        for i in range(0 if lod else 12):
            az = i / 12 * math.tau + rnd.uniform(-0.2, 0.2)
            hd = Vector((math.cos(az), math.sin(az), 0))
            frond(az, math.radians(-80), rnd.uniform(1.4, 2.2), 0.02, dead=True, segs=3)
    else:
        n = (12 if lod else 24) if kind == "date" else (10 if lod else 18)
        for i in range(n):
            ring = i % 3
            if kind == "queen":
                elev = math.radians((45, 12, -22)[ring] + rnd.uniform(-8, 8))
                fl = rnd.uniform(3.0, 3.6)
                droop = (0.13, 0.2, 0.26)[ring]
            else:
                elev = math.radians((55, 22, -10)[ring] + rnd.uniform(-10, 10))
                fl = rnd.uniform(3.6, 4.4) if h > 6 else h * 0.55
                droop = (0.07, 0.12, 0.17)[ring]
            frond(i / n * math.tau + ring * 0.35 + rnd.uniform(-0.12, 0.12), elev, fl, droop)
        for i in range(0 if lod else 4):
            frond(rnd.uniform(0, math.tau), math.radians(-70), 2.2, 0.03, dead=True, segs=4)
    green = card_mat("palm_" + ("fan" if kind == "fan" else "frond"), fan_image() if kind == "fan" else frond_image(),
                     trans=0.35)
    dead = card_mat("palm_dead_" + ("fan" if kind == "fan" else "frond"), fan_image("dead") if kind == "fan" else frond_image("dead"),
                    trans=0.15)
    _uv_mesh("palm_crown", vs, fs, uvs, green)
    if dvs:
        _uv_mesh("palm_dead", dvs, dfs, duvs, dead)
    sphere("palm_head", top, (radii[-1] * 1.05, radii[-1] * 1.05, 0.5), bark_mat("bark_" + kind, (0.3, 0.26, 0.21), (0.52, 0.46, 0.38)), seg=10)
    return trunk


def _card_cluster(name, centre, rx, ry, rz, n, size, m, rnd, droop=0.0):
    """n square leaf cards scattered through an ellipsoid, facing roughly outward."""
    quads = []
    c = Vector(centre)
    for _ in range(n):
        while True:
            q = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1)))
            if q.length <= 1:
                break
        p = c + Vector((q.x * rx, q.y * ry, q.z * rz - droop * (q.x * q.x + q.y * q.y)))
        nrm = (q + Vector((rnd.uniform(-0.6, 0.6), rnd.uniform(-0.6, 0.6), rnd.uniform(-0.3, 0.8)))).normalized()
        a = nrm.cross(Vector((0, 0, 1)) if abs(nrm.z) < 0.9 else Vector((1, 0, 0))).normalized()
        b = nrm.cross(a)
        rot = rnd.uniform(0, math.tau)
        a, b = a * math.cos(rot) + b * math.sin(rot), b * math.cos(rot) - a * math.sin(rot)
        s = size * rnd.uniform(0.75, 1.25) / 2
        quads.append(([p - a * s - b * s, p + a * s - b * s, p + a * s + b * s, p - a * s + b * s],
                      [(0, 0), (1, 0), (1, 1), (0, 1)]))
    return cards_obj(name, quads, m)


def shrub(x, y, r=0.7, h=None, seed=0, m=None, z=0.0, kind="shrub"):
    """A leafy bush: a dark core with leaf cards over it."""
    rnd = random.Random(seed or int(x * 13 + y * 7))
    h = h or r * 1.2
    core = mat("shrub_core", (0.03, 0.07, 0.02), rough=0.9)
    sphere("shrub_core", (x, y, z + h * 0.45), (r * 0.75, r * 0.75, h * 0.38), core, seg=10)
    lm = card_mat("leaf_" + kind, foliage_image(kind), tint=(1.0, 1.0, 1.0) if kind != "bouga" else (1, 1, 1), trans=0.3)
    n = int(40 + 90 * r * h)
    _card_cluster("shrub", (x, y, z + h * 0.5), r, r, h * 0.5, n, max(0.3, r * 0.65), lm, rnd)


def bougainvillea(a, b, z, out, seed=0, hang=1.2):
    """Bougainvillea spilling over a wall top from a to b (out: the side it falls down, as a unit vector)."""
    rnd = random.Random(seed)
    a, b, out = Vector(a), Vector(b), Vector(out)
    lm = card_mat("leaf_bouga", foliage_image("bouga"), trans=0.3)
    ln = (b - a).length
    for k in range(max(1, int(ln / 1.4))):
        t = (k + rnd.uniform(0.2, 0.8)) / max(1, int(ln / 1.4))
        p = a + (b - a) * t + out * 0.25
        _card_cluster("bouga", (p.x, p.y, z + 0.2), 0.75, 0.75, 0.45, 40, 0.5, lm, rnd)
        _card_cluster("bouga_fall", (p.x + out.x * 0.15, p.y + out.y * 0.15, z - hang * 0.5), 0.55, 0.25 if abs(out.y) else 0.55,
                      hang * 0.5, 26, 0.42, lm, rnd)


def agave(x, y, r=0.6, z=0.0, seed=0):
    """An agave rosette: thick, pointed blue-green leaves curving out from the middle."""
    rnd = random.Random(seed or int(x * 31 + y * 17))
    m, nt, b = _node_mat("agave") if "agave" not in _mats else (_mats["agave"], None, None)
    if nt:
        co = _coords(nt)
        nt.links.new(_ramp(nt, _noise(nt, co, 3.0, 3.0).outputs["Fac"], ((0.3, (0.2, 0.32, 0.28)), (0.7, (0.3, 0.42, 0.36)))), b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.45
        b.inputs["Coat Weight"].default_value = 0.3
        _mats["agave"] = m
    vs, fs = [], []
    for k in range(22):
        az = k * 2.4 + rnd.uniform(-0.15, 0.15)
        elev = math.radians(75 - 55 * (k / 22) + rnd.uniform(-8, 8))
        hd = Vector((math.cos(az), math.sin(az), 0))
        sd = Vector((-hd.y, hd.x, 0))
        ln = r * rnd.uniform(0.9, 1.25) * (0.7 + 0.5 * k / 22)
        base = len(vs)
        segs = 5
        for i in range(segs + 1):
            s = i / segs
            p = Vector((x, y, z)) + hd * (math.cos(elev) * ln * s) + Vector((0, 0, math.sin(elev) * ln * s - 0.25 * ln * s * s))
            w = ln * 0.2 * (1 - s) ** 0.7
            vs += [p - sd * w, p + Vector((0, 0, w * 0.5)), p + sd * w]
        for i in range(segs):
            for j in range(2):
                q = base + i * 3 + j
                fs.append((q, q + 1, q + 4, q + 3))
    mesh_obj("agave", vs, fs, m, smooth=True)


def street_lamp(x, y, h=4.2):
    """A black cast-iron acorn street lamp."""
    iron = mat("cast_iron", (0.02, 0.025, 0.03), rough=0.4, metal=0.6)
    cyl("lamp_base", (x, y, 0.35), 0.16, 0.7, iron, r2=0.1, verts=12)
    cyl("lamp_post", (x, y, h / 2), 0.06, h, iron, r2=0.045, verts=10)
    cyl("lamp_collar", (x, y, h + 0.05), 0.12, 0.1, iron, verts=12)
    sphere("lamp_globe", (x, y, h + 0.4), (0.22, 0.22, 0.32), mat("lamp_glass", (0.95, 0.93, 0.85), rough=0.2, emit=0.4, ecol=(1.0, 0.9, 0.7)), seg=12)
    cyl("lamp_cap", (x, y, h + 0.78), 0.16, 0.12, iron, r2=0.03, verts=12)


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
    """A potted fiddle-leaf fig: a tapered pot, a stem and a column of big leaf cards."""
    cyl("pot", (x, y, z + 0.25), 0.26, 0.5, mat("pot_cer", (0.85, 0.84, 0.8), rough=0.3), r2=0.2, verts=20)
    cyl("stem", (x, y, z + h * 0.45), 0.02, h * 0.6, mat("stem", (0.25, 0.18, 0.1)), verts=6)
    rnd = random.Random(int(x * 7 + y * 3))
    lm = card_mat("leaf_fig", foliage_image("fig"), trans=0.3)
    sphere("plant_core", (x, y, z + h * 0.72), (0.18, 0.18, h * 0.22), mat("shrub_core", (0.03, 0.07, 0.02), rough=0.9), seg=10)
    _card_cluster("fig", (x, y, z + h * 0.72), 0.36, 0.36, h * 0.3, 34, 0.42, lm, rnd)


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
    """The glass sales pavilion inside: warm wainscot and taupe walls, framed car prints, a credenza, a plant."""
    taupe = mat("wall_taupe", (0.55, 0.47, 0.38), rough=0.85)
    w = walnut()
    x0, x1, yf = OX0 + 0.2, OX1 - 0.2, OY0 + 0.2
    # west wall: taupe above a walnut wainscot and chair rail, whiteboard on it
    wall_box("y", x0, yf, OY1 - 0.2, TZ, 1.0, 0.0, 0.015, 1, w, "wainscot")
    wall_box("y", x0, yf, OY1 - 0.2, 1.0, OH - 0.6, 0.0, 0.005, 1, taupe, "accent")
    wall_box("y", x0, yf, OY1 - 0.2, 0.98, 1.04, 0.0, 0.03, 1, w, "chair_rail")
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
    """Coastal bluff under gardens: dark tree canopy over patches of green-gold grass, thicker in the gullies."""
    if "hills" in _mats:
        return _mats["hills"]
    m, nt, b = _node_mat("hills")
    co = _coords(nt)
    grass = _noise(nt, co, 0.05, 6.0, 0.6)
    base = _ramp(nt, grass.outputs["Fac"], ((0.25, (0.2, 0.22, 0.1)), (0.75, (0.36, 0.34, 0.18))))
    # chaparral: irregular dark patches where a fine and a coarse noise agree, thicker on some slopes than others
    scrub = _noise(nt, co, 0.08, 10.0, 0.7)
    dens = _noise(nt, co, 0.004, 3.0)
    thr = _math(nt, "MULTIPLY_ADD", dens.outputs["Fac"], -0.35, 0.6)
    clump = _math(nt, "GREATER_THAN", scrub.outputs["Fac"], thr)
    col = _mix(nt, _math(nt, "MULTIPLY", clump, 0.9), base, (0.05, 0.09, 0.03))
    # gullies (faces turned away from straight up) hold more scrub
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sep.inputs[0])
    gully = _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", 0.8, sep.outputs["Z"], clamp=True), 4.0, clamp=True)
    col = _mix(nt, _math(nt, "MULTIPLY", gully, 0.5), col, (0.07, 0.1, 0.04))
    nt.links.new(col, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.95
    _bump(nt, b, _math(nt, "ADD", clump, _math(nt, "MULTIPLY", scrub.outputs["Fac"], 0.5)), 0.5, 1.5)
    _mats["hills"] = m
    return m


# white stucco and cream, the odd pale blue or sand: the colours of a Southern California beach town
TOWN_COLOURS = ((0.95, 0.94, 0.9), (0.93, 0.9, 0.84), (0.96, 0.95, 0.92), (0.9, 0.86, 0.78), (0.82, 0.87, 0.9),
                (0.94, 0.92, 0.86), (0.88, 0.8, 0.68), (0.96, 0.96, 0.94))


def lifeguard_tower(x, y, z=0.0):
    """A blue-and-white beach lifeguard hut on stilts."""
    white = mat("lg_white", (0.95, 0.95, 0.93), rough=0.5)
    blue = mat("lg_blue", (0.15, 0.45, 0.75), rough=0.5)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box("lg_leg", (x + sx * 1.0 - 0.08, y + sy * 1.0 - 0.08, z), (x + sx * 1.0 + 0.08, y + sy * 1.0 + 0.08, z + 2.2), white)
    box("lg_deck", (x - 1.6, y - 1.6, z + 2.2), (x + 1.6, y + 1.6, z + 2.35), white)
    box("lg_hut", (x - 1.2, y - 1.2, z + 2.35), (x + 1.2, y + 1.2, z + 4.3), blue)
    box("lg_win", (x - 1.0, y - 1.22, z + 3.2), (x + 1.0, y - 1.2, z + 4.0), mat("win_glass", (0.02, 0.03, 0.04), rough=0.05))
    hip_roof("lg_roof", x - 1.2, y - 1.2, x + 1.2, y + 1.2, z + 4.3, 0.6, white, over=0.3)
    box("lg_ramp", (x - 0.5, y - 4.5, z), (x + 0.5, y - 1.6, z + 0.2), white)


# The sun: the parked-car sprites (tools/car_sprites_real.py) are lit by a sun 50 degrees up, behind the
# three-quarter camera and to its left (140 degrees round from the view direction). The lot cameras look
# north-north-east (headings 68..82 degrees), so the same light here is a sun 50 degrees up in the south-west, behind
# the cameras: the storefronts and the dealership facing the camera are in direct sun, and shadows fall away from the
# camera and to the right, as they do in the sprites.
SUN_EL, SUN_AZ = 50.0, -124.0


def sun_vector():
    el, az = math.radians(SUN_EL), math.radians(SUN_AZ)
    return Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))


GOLDEN = {}


def golden_hour(on):
    """Showroom renders only: warm the sky and turn the shared midday sun down and amber, so the low golden_sun
    through the front glass carries the picture. SUN_EL/SUN_AZ (lot views, car sprites) are untouched."""
    if "warm" not in GOLDEN or NIGHT:
        return
    GOLDEN["warm"].inputs[0].default_value = 1.0 if on else 0.0
    sun = bpy.data.objects.get("sun")
    if sun:
        sun.data.energy = 1.6 if on else 6.2
        sun.data.color = (1.0, 0.62, 0.34) if on else (1.0, 0.9, 0.76)
    for o in bpy.data.objects:      # dimmer room fills so the sunlight on the floor stands out
        if o.type == "LIGHT" and o.name.startswith("fill"):
            o.data.energy = o.data["day"] * (0.45 if on else 1.0) if "day" in o.data else o.data.energy


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
    sky.aerosol_density = 0.2     # a clear coastal day, not haze
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
    cloud.inputs["From Min"].default_value = 0.57      # a few soft clouds, mostly open blue
    cloud.inputs["From Max"].default_value = 0.72
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
    blue = _mix(nt, seen, sky.outputs[0], _mix(nt, 1.0, sky.outputs[0], (0.66, 0.88, 1.25), "MULTIPLY"))
    col = _mix(nt, _math(nt, "MULTIPLY", cf, 0.95), blue, shade)
    # showroom-only golden hour: a warm multiply on the sky (GOLDEN["warm"]), off for every other view
    # (a late-afternoon sky: bright peach at the horizon to a dusty violet overhead, warming the light it casts too)
    dusk = _ramp(nt, sep.outputs["Z"], ((0.0, (1.0, 0.58, 0.27)), (0.06, (0.72, 0.4, 0.21)), (0.2, (0.36, 0.26, 0.21)),
                                        (0.6, (0.145, 0.14, 0.18))))
    dusk = _mix(nt, _math(nt, "MULTIPLY", cf, 0.7), dusk, _mix(nt, 1.0, dusk, (1.0, 0.8, 0.66), "MULTIPLY"))
    up = nt.nodes.new("ShaderNodeVectorMath")      # ramps stop at 1.0; scale up to sky brightness
    up.operation = "SCALE"
    up.inputs["Scale"].default_value = 3.6
    nt.links.new(dusk, up.inputs[0])
    dusk = up.outputs["Vector"]
    warm = nt.nodes.new("ShaderNodeMix")
    warm.data_type = "RGBA"
    warm.inputs[0].default_value = 0.0
    nt.links.new(col, warm.inputs[6])
    nt.links.new(dusk, warm.inputs[7])
    GOLDEN["warm"] = warm
    nt.links.new(warm.outputs[2], nt.nodes["Background"].inputs[0])
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
    box("lot", (-26.3, -60, -0.1), (60, 0, 0), asphalt)
    box("street", (-30.0, -90, -0.12), (200, -60, -0.02), asphalt_mat("street", (0.04, 0.04, 0.045), (0.085, 0.085, 0.09), cracks=0.3))
    box("sidewalk", (-26.3, -60, -0.1), (200, -57, 0.08), concrete)
    box("pad", (-26.3, 0, -0.1), (60, HILL_FOOT_Y, 0.02), concrete)
    # patched and stained asphalt across the open lot (each site adds its own stains in the stalls)
    patch = asphalt_mat("asphalt_patch", (0.075, 0.072, 0.07), (0.14, 0.135, 0.125), cracks=0.0, rough=0.75)
    seal = mat("crack_seal", (0.02, 0.02, 0.022), rough=0.4)
    rnd = random.Random(12)
    for i in range(9):
        x, y = rnd.uniform(-24, 30), rnd.uniform(-44, -6)
        w, d = rnd.uniform(1.2, 3.4), rnd.uniform(0.8, 2.2)
        box("asphalt_patch", (x, y, 0.0), (x + w, y + d, 0.004), patch)
        box("patch_seal", (x - 0.04, y - 0.04, 0.0), (x + w + 0.04, y + d + 0.04, 0.003), seal)
    for i in range(26):
        stain((rnd.uniform(-24, 30), rnd.uniform(-44, -4)), rnd.uniform(0.5, 1.6), rnd)
    for i, x in enumerate(range(-18, 160, 22)):
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
    for x in (-9, 9, 27):
        box("planter", (x - 2.2, -4.8, 0), (x + 2.2, -3.0, 0.55), concrete, bevel=0.04)
        box("planter_soil", (x - 2.05, -4.65, 0.5), (x + 2.05, -3.15, 0.53), mat("bark_mulch", (0.16, 0.1, 0.06), rough=0.95))
        for k, dx in enumerate((-1.4, 1.4)):
            shrub(x + dx, -3.9, 0.6, 0.8, seed=k + x * 3, z=0.5)
    for i, x in enumerate((-22, -9, 9, 27, 44)):
        palm((x, -3.9 if abs(x) < 40 else 6, 0), h=9 + (i % 3) * 1.4, seed=i)
    light_pole(-22.5, -4.2, 8.0, ((0, -1),))
    pole_sign(19.0, -8.0, h=10.0, w=4.0, sh=3.2)
    # bunting along the showroom front between two poles, under the fascia and behind the parked cars (the game
    # draws the cars over the render, so nothing may stand between the lot camera and a stall)
    t0, t1 = flag_pole(-21.0, -4.4, 6.4), flag_pole(13.5, -4.4, 6.4)
    bunting_line(t0, t1, sag=0.9)
    bunting_line(t1, (16.5, -2.6, 6.6), sag=0.15)


# ---------------------------------------------------------------- the PCH site: road, ocean, planted hillside, villas
# Laid out like the owner's reference photo of the real lot: the dealership sits on Pacific Coast Highway, the
# highway runs along the west side of the lot and curves away north-west along the coast, the Pacific is beyond it on
# the left of the lot views, and behind the lot a steep, densely planted hillside climbs to white Mediterranean villas.

PCH_W = 15.0          # kerb to kerb: two lanes each way and a double yellow line
PCH_WALK = 3.2        # sidewalk on each side


def pch_points(step=4.0):
    """Centre line of the highway, south to north: straight past the lot, then bending north-west with the coast."""
    pts, p, bend = [], Vector((-37.0, -260.0, 0.0)), 0.0
    while len(pts) * step < 1100:
        if p.y > 5.0:
            bend += step
        head = math.radians(90 + 60 * min(1.0, bend / 300.0))
        pts.append(p.copy())
        p += Vector((math.cos(head), math.sin(head), 0)) * step
    return pts


def _road_frame(pts):
    """Unit tangents and left normals (pointing west of a northbound driver) for a polyline."""
    out = []
    for i, p in enumerate(pts):
        a, b = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
        t = (b - a).normalized()
        out.append((t, Vector((-t.y, t.x, 0))))
    return out


def road_ribbon(name, pts, frames, off0, off1, z, m, dash=None):
    """A strip along the road between two offsets (metres to the left of the centre line); dash = (on, period)."""
    vs, fs = [], []
    run = 0.0
    for i, (p, (t, n)) in enumerate(zip(pts, frames)):
        vs += [p + n * off0 + Vector((0, 0, z)), p + n * off1 + Vector((0, 0, z))]
        if i:
            run += (p - pts[i - 1]).length
            if dash is None or (run % dash[1]) < dash[0]:
                k = len(vs) - 4
                fs.append((k, k + 2, k + 3, k + 1) if off1 > off0 else (k, k + 1, k + 3, k + 2))
    return mesh_obj(name, vs, fs, m)


def _road_dist(px, py, pts):
    """Signed distance (numpy arrays) from points to the road centre line: positive to the east (the lot's side)."""
    import numpy as np
    P = np.array([(p.x, p.y) for p in pts])
    A, B = P[:-1], P[1:]
    D = B - A
    L2 = (D ** 2).sum(1)
    best = np.full(px.shape, 1e9)
    sign = np.ones(px.shape)
    for k in range(0, len(A), 64):
        a, d, l2 = A[k:k + 64], D[k:k + 64], L2[k:k + 64]
        rx = px[..., None] - a[:, 0]
        ry = py[..., None] - a[:, 1]
        t = np.clip((rx * d[:, 0] + ry * d[:, 1]) / l2, 0, 1)
        ex, ey = rx - t * d[:, 0], ry - t * d[:, 1]
        dist = np.sqrt(ex * ex + ey * ey)
        j = dist.argmin(-1)
        dm = np.take_along_axis(dist, j[..., None], -1)[..., 0]
        cr = d[j, 0] * np.take_along_axis(ry, j[..., None], -1)[..., 0] - d[j, 1] * np.take_along_axis(rx, j[..., None], -1)[..., 0]
        upd = dm < best
        best = np.where(upd, dm, best)
        sign = np.where(upd, np.where(cr > 0, -1.0, 1.0), sign)
    return best * sign


HILL_FOOT_Y = 20.0     # the planted slope starts behind the dealership pad (a stone retaining wall at its foot)


def terrain_height(x, y, sd):
    """Ground height (numpy) from position and signed road distance: the hillside east of the highway, the bluff and
    beach west of it. Flat (just under the paving) on the road and the lot."""
    import numpy as np
    half = PCH_W / 2 + PCH_WALK
    # east: how far into the hill (from the pad's back edge and from the highway's east sidewalk)
    q = np.minimum(y - HILL_FOOT_Y, sd - half - 6.0)
    top = np.clip(4.5 + 0.05 * (x + 10.0), 3.0, 12.0) + 0.8 * np.sin(x * 0.045 + 1.0) + 0.5 * np.sin(x * 0.11)
    # the hill ends a little west of the lot: beyond the bend the land is low and the ocean shows over it
    fw = np.clip((x + 150.0) / 90.0, 0, 1)
    top = top * fw * fw * (3 - 2 * fw)
    t = np.clip(q / 30.0, 0, 1)
    face = 1 - (1 - t) ** 2            # steep just behind the wall, easing toward the top
    gul = 0.5 * np.sin(x * 0.21 + np.sin(y * 0.13) * 2) * np.sin(math.pi * t)
    east = top * face + gul * fw + np.maximum(0, q - 30.0) * 0.04 * fw
    east = np.where(q > 0, east + 1.3 * np.clip(q, 0, 1) * np.clip((x + 26.3) * 10, 0, 1), 0.0) - 0.06
    # west: a low planted bank dropping to the sand, then the beach shelving into the sea
    w = -sd - half
    west = np.where(w < 8, -0.4 * np.clip(w / 8, 0, 1), -0.4 - 0.006 * (w - 8) - 0.0004 * np.maximum(0, w - 60) ** 2) - 0.06
    return np.where(sd > 0, east, west)


def pampas_image():
    """Pampas grass plumes: cream feathery panicles on a few green blades (256 x 512, base at the bottom)."""
    def draw(img, s):
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        rnd = random.Random(31)
        W, H = img.size
        for i in range(26):
            bx = W * rnd.uniform(0.3, 0.7)
            _leaf_poly(d, (bx, H), (bx + W * rnd.uniform(-0.45, 0.45), H * rnd.uniform(0.35, 0.6)), 3 * s,
                       rnd.choice([(70, 96, 40), (90, 110, 50), (60, 80, 34)]) + (255,))
        for i in range(7):
            bx = W * rnd.uniform(0.35, 0.65)
            tx, ty = bx + W * rnd.uniform(-0.2, 0.2), H * rnd.uniform(0.05, 0.15)
            d.line([(bx, H), (tx, ty + H * 0.25)], fill=(150, 140, 100, 255), width=int(2 * s))
            for k in range(140):
                u = rnd.random()
                cx = tx + (bx - tx) * 0.0 + rnd.gauss(0, W * 0.035) * (1 - abs(u - 0.4))
                cy = ty + u * H * 0.32
                ln = W * rnd.uniform(0.03, 0.07)
                c = rnd.choice([(236, 226, 196), (224, 210, 176), (246, 240, 220), (210, 196, 160)]) + (255,)
                d.line([(cx, cy), (cx + rnd.uniform(-ln, ln), cy + ln)], fill=c, width=int(2 * s))
    return _pil_image("tex_pampas", draw, (256, 512), bg=(220, 210, 180))


class Cards:
    """Leaf cards for many plants gathered into a few meshes (one object per chunk, so per-object colour variation
    still breaks them up) instead of one object per plant."""

    def __init__(self, name, m, chunk=6000):
        self.name, self.m, self.chunk = name, m, chunk
        self.quads = []

    def cluster(self, centre, rx, ry, rz, n, size, rnd, droop=0.0, upright=False):
        c = Vector(centre)
        for _ in range(n):
            while True:
                q = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1)))
                if q.length <= 1:
                    break
            p = c + Vector((q.x * rx, q.y * ry, q.z * rz - droop * (q.x * q.x + q.y * q.y)))
            nrm = (q + Vector((rnd.uniform(-0.6, 0.6), rnd.uniform(-0.6, 0.6), rnd.uniform(-0.3, 0.8)))).normalized()
            a = nrm.cross(Vector((0, 0, 1)) if abs(nrm.z) < 0.9 else Vector((1, 0, 0))).normalized()
            b = nrm.cross(a)
            rot = rnd.uniform(0, math.tau)
            a, b = a * math.cos(rot) + b * math.sin(rot), b * math.cos(rot) - a * math.sin(rot)
            s = size * rnd.uniform(0.75, 1.25) / 2
            self.quads.append(([p - a * s - b * s, p + a * s - b * s, p + a * s + b * s, p - a * s + b * s],
                               [(0, 0), (1, 0), (1, 1), (0, 1)]))
            if len(self.quads) >= self.chunk:
                self.flush()

    def upright(self, base, w, h, rnd, n=3):
        """Crossed vertical cards standing on base (grasses, plumes), bottom of the texture at the ground."""
        for k in range(n):
            a = rnd.uniform(0, math.pi) + k * math.pi / n
            d = Vector((math.cos(a), math.sin(a), 0)) * w / 2
            p = Vector(base)
            up = Vector((rnd.uniform(-0.1, 0.1) * h, rnd.uniform(-0.1, 0.1) * h, h))
            self.quads.append(([p - d, p + d, p + d + up, p - d + up], [(0, 0), (1, 0), (1, 1), (0, 1)]))
        if len(self.quads) >= self.chunk:
            self.flush()

    def flush(self):
        if self.quads:
            cards_obj(self.name, self.quads, self.m)
            self.quads = []


def villa(x, y, z, w, d, rnd, walls, tiles, face=-1):
    """A white Mediterranean hillside villa facing the view (-y): stepped stucco blocks, deep balconies with white
    rails and glass, tile hip roofs, a chimney, and a terrace wall below it."""
    rail = mat("villa_rail", (0.96, 0.96, 0.94), rough=0.5)
    glass_rail = mat("villa_glass", (0.5, 0.6, 0.65), rough=0.05, alpha=0.45)
    wall = rnd.choice(walls)
    floors = rnd.choice((2, 2, 3))
    fh = 3.3
    box("villa", (x, y, z - 3), (x + w, y + d, z + floors * fh), wall)
    hip_roof("villa_roof", x, y, x + w, y + d, z + floors * fh, min(2.8, d * 0.28), tiles, over=0.7)
    # a lower wing stepping down the slope in front
    if rnd.random() < 0.7:
        wx0 = x + rnd.uniform(-0.2, 0.4) * w
        wx1 = min(x + w + 3, wx0 + w * rnd.uniform(0.5, 0.8))
        box("villa_wing", (wx0, y - 5.5, z - 4), (wx1, y + 1, z + fh * (floors - 1)), rnd.choice(walls))
        hip_roof("villa_roof", wx0, y - 5.5, wx1, y + 1, z + fh * (floors - 1), 1.8, tiles, over=0.6)
    # balconies across the front on each upper floor
    for f in range(1, floors):
        zb = z + f * fh
        bx0, bx1 = x + rnd.uniform(0, 0.25) * w, x + w - rnd.uniform(0, 0.25) * w
        box("villa_balcony", (bx0, y - 1.6, zb - 0.25), (bx1, y, zb), rail)
        box("villa_glassrail", (bx0, y - 1.6, zb), (bx1, y - 1.5, zb + 1.05), glass_rail)
        box("villa_toprail", (bx0, y - 1.62, zb + 1.0), (bx1, y - 1.48, zb + 1.1), rail)
    # big dark openings on the ground floor (the painted windows do the rest)
    for k in range(int(w // 4)):
        ox = x + 1 + k * 4
        box("villa_door", (ox, y - 0.05, z), (ox + 2.2, y + 0.05, z + 2.6), mat("win_glass", (0.02, 0.03, 0.04), rough=0.05))
    if rnd.random() < 0.6:
        cx = x + rnd.uniform(0.2, 0.8) * w
        box("villa_chimney", (cx, y + d * 0.5, z + floors * fh), (cx + 1.0, y + d * 0.5 + 1.0, z + floors * fh + 3.2), wall)
    # terrace wall
    box("villa_terrace", (x - 3, y - 8, z - 6), (x + w + 3, y - 7.6, z + 0.9), rnd.choice(walls))


def build_coast():
    """Pacific Coast Highway along the lot's west side, the ocean and beach beyond it, the planted hillside behind the
    lot with villas on top, palms along the road, and a small row of beach-town shops down the highway."""
    import numpy as np
    rnd = random.Random(5)
    pts = pch_points()
    frames = _road_frame(pts)
    # the sea: a wide ocean to the horizon, west of the coast
    m, nt, b = _node_mat("water")
    co = _coords(nt, scale=(1, 2.5, 1))
    ripple = _noise(nt, co, 1.6, 6.0, 0.6)
    swell = _noise(nt, co, 0.08, 3.0)
    nt.links.new(_ramp(nt, swell.outputs["Fac"], ((0.3, (0.0, 0.05, 0.12)), (0.7, (0.02, 0.1, 0.2)))), b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.16
    _bump(nt, b, _math(nt, "ADD", ripple.outputs["Fac"], _math(nt, "MULTIPLY", swell.outputs["Fac"], 2.0)), 0.25, 0.1)
    box("sea", (-12000, -12000, -1.2), (12000, 12000, -0.7), m)
    # terrain: one grid, hill material east of the highway, ice plant then sand west of it
    xs = np.concatenate([np.linspace(-700, -150, 56, endpoint=False), np.linspace(-150, 220, 186, endpoint=False), np.linspace(220, 700, 41)])
    ys = np.concatenate([np.linspace(-300, -20, 30, endpoint=False), np.linspace(-20, 200, 147, endpoint=False), np.linspace(200, 900, 71)])
    X, Y = np.meshgrid(xs, ys)
    SD = _road_dist(X, Y, pts)
    Z = terrain_height(X, Y, SD)
    nx, ny = len(xs), len(ys)
    vs = [(float(X[j, i]), float(Y[j, i]), float(Z[j, i])) for j in range(ny) for i in range(nx)]
    fs, idx = [], []
    half = PCH_W / 2 + PCH_WALK
    for j in range(ny - 1):
        for i in range(nx - 1):
            a0 = j * nx + i
            fs.append((a0, a0 + 1, a0 + nx + 1, a0 + nx))
            sd = SD[j, i]
            idx.append(0 if sd > 0 else (1 if -sd - half < 7.5 else 2))
    sand = noise_mat("sand", (0.74, 0.66, 0.5), (0.84, 0.77, 0.62), 2.0, 0.95, bump=0.1, macro=0.2)
    ice = noise_mat("iceplant", (0.16, 0.26, 0.08), (0.36, 0.4, 0.14), 4.0, 0.7, bump=0.4, macro=0.4)
    mesh_obj("terrain", vs, fs, [hill_mat(), ice, sand], smooth=True, mat_idx=idx)

    def tz(x, y):
        sd = _road_dist(np.array([x]), np.array([y]), pts)
        return float(terrain_height(np.array([x]), np.array([y]), sd)[0]), float(sd[0])

    # the highway: asphalt, double yellow centre line, dashed lane lines, kerbs and sidewalks
    road = asphalt_mat("pch", (0.05, 0.05, 0.055), (0.1, 0.1, 0.105), cracks=0.15)
    road_ribbon("pch", pts, frames, -PCH_W / 2, PCH_W / 2, 0.0, road)
    yellow = mat("line_yellow", (0.85, 0.62, 0.08), rough=0.6)
    white = mat("line_white", (0.88, 0.88, 0.85), rough=0.6)
    for o in (-0.12, 0.12):
        road_ribbon("pch_yellow", pts, frames, o - 0.06, o + 0.06, 0.006, yellow)
    for o in (-3.7, 3.7):
        road_ribbon("pch_lane", pts, frames, o - 0.06, o + 0.06, 0.006, white, dash=(3.0, 12.0))
    for o in (-PCH_W / 2 + 0.3, PCH_W / 2 - 0.3):
        road_ribbon("pch_edge", pts, frames, o - 0.07, o + 0.07, 0.006, white)
    walk = noise_mat("walk_pch", (0.62, 0.6, 0.56), (0.72, 0.7, 0.66), 8, 0.75, bump=0.05)
    red = kerb_paint()
    for side in (1, -1):
        # side 1 = east (the lot's side): offsets are measured to the left (west), so east is negative
        e0 = -side * PCH_W / 2
        e1 = -side * (PCH_W / 2 + PCH_WALK)
        road_ribbon("pch_walk", pts, frames, min(e0, e1), max(e0, e1), 0.15, walk)
        road_ribbon("pch_kerb", pts, frames, e0 - 0.22 if side == -1 else e0, e0 if side == -1 else e0 + 0.22, 0.152, red if side == 1 else walk)
        # kerb face
        vs, fs2 = [], []
        for i, (p, (t, n)) in enumerate(zip(pts, frames)):
            vs += [p + n * e0, p + n * e0 + Vector((0, 0, 0.15))]
            if i:
                k = len(vs) - 4
                fs2.append((k, k + 2, k + 3, k + 1))
        mesh_obj("pch_kerb_face", vs, fs2, red if side == 1 else walk)
    # a white rail along the ocean side, palms both sides, cobra-head street lights on the lot side
    rail = mat("rail_white", (0.92, 0.92, 0.9), rough=0.5)
    vs, fs2 = [], []
    for i, (p, (t, n)) in enumerate(zip(pts, frames)):
        q = p + n * (PCH_W / 2 + PCH_WALK - 0.1)
        vs += [q + Vector((0, 0, 0.75)), q + Vector((0, 0, 0.95))]
        if i:
            k = len(vs) - 4
            fs2.append((k, k + 2, k + 3, k + 1))
    mesh_obj("pch_rail", vs, fs2, rail)
    run = 0.0
    for i in range(1, len(pts)):
        run += (pts[i] - pts[i - 1]).length
        p, (t, n) = pts[i], frames[i]
        if p.y < -120 or p.y > 520:
            continue
        if i % 3 == 0:
            q = p + n * (PCH_W / 2 + PCH_WALK - 0.4)
            box("rail_post", (q.x - 0.06, q.y - 0.06, 0.1), (q.x + 0.06, q.y + 0.06, 0.95), rail)
        if i % 4 == 0:
            q = p + n * (PCH_W / 2 + 1.6)
            palm((q.x, q.y, 0.15), rnd.uniform(14, 21), seed=400 + i, kind="fan", lod=p.y > 160)
        if i % 4 == 2 and p.y > -10:
            q = p - n * (PCH_W / 2 + 1.6)
            if p.y > 30:
                palm((q.x, q.y, 0.15), rnd.uniform(13, 19), seed=500 + i, kind="fan" if i % 3 else "queen", lod=p.y > 160)
        if i % 10 == 5 and -60 < p.y < 260:
            q = p - n * (PCH_W / 2 + 0.6)
            cyl("cobra_pole", (q.x, q.y, 4.5), 0.09, 9.0, mat("galv", (0.6, 0.62, 0.63), rough=0.4, metal=0.9), r2=0.06, verts=10)
            arm = q + n * 2.4 + Vector((0, 0, 8.9))
            tube("cobra_arm", [q + Vector((0, 0, 8.7)), q + n * 1.2 + Vector((0, 0, 9.1)), arm], 0.05,
                 mat("galv", (0.6, 0.62, 0.63), rough=0.4, metal=0.9), sides=6)
            box("cobra_head", (arm.x - 0.35, arm.y - 0.35, arm.z - 0.15), (arm.x + 0.35, arm.y + 0.35, arm.z + 0.05),
                mat("galv", (0.6, 0.62, 0.63), rough=0.4, metal=0.9))
    # a stone retaining wall at the foot of the slope, behind the dealership pad
    stone = block_mat("retain", (0.55, 0.5, 0.42), (0.64, 0.58, 0.5), (0.46, 0.43, 0.38), (0.9, 0.45), split=0.5)
    box("retaining_wall", (-26.3, HILL_FOOT_Y - 0.2, 0), (240, HILL_FOOT_Y + 0.35, 1.3), stone)
    box("retaining_cap", (-26.3, HILL_FOOT_Y - 0.25, 1.3), (240, HILL_FOOT_Y + 0.4, 1.4), mat("wall_cap", (0.78, 0.76, 0.72), rough=0.7))
    # the lot's chain-link fence along the highway sidewalk
    chain_fence([(-26.0, -38.0), (-26.0, 28.0)], h=1.8)
    # a lifeguard tower and a few boats out on the water
    for y in (60.0, 210.0):
        h, sd = tz(-80.0, y)
        if sd < -half - 20:
            lifeguard_tower(-80.0 - (y - 60) * 0.5, y, -1.6)
    for i in range(7):
        boat(rnd.uniform(-1600, -500), rnd.uniform(-200, 900), rnd.uniform(9, 16), "sail" if i % 3 else "motor", rnd, bow=rnd.choice((1, -1)))
    # ---- the hillside: dense shrubs and trees, bougainvillea, agave, pampas grass, palms, villas along the top
    leaf = Cards("hill_leaf", card_mat("leaf_shrub", foliage_image("shrub"), trans=0.3))
    dark = Cards("hill_leaf_dark", card_mat("leaf_shrub_dark", foliage_image("shrub"), tint=(0.6, 0.72, 0.55), trans=0.25, vary=0.25))
    bouga = Cards("hill_bouga", card_mat("leaf_bouga", foliage_image("bouga"), trans=0.3))
    pampas = Cards("hill_pampas", card_mat("pampas", pampas_image(), trans=0.4, rough=0.8, vary=0.1))
    core_v, core_f = [], []
    walls = [window_mat("town_%d" % i, c, shade=(0.55, 0.52, 0.45) if i % 2 else None, bay=2.8) for i, c in enumerate(TOWN_COLOURS)]
    tiles = tile_mat()
    # sample the visible slope (x -140..160 behind the lot, y 30..200) densely, the rest sparsely
    n_plants = 5200
    PX = np.array([rnd.uniform(-170, 180) for _ in range(n_plants)])
    PY = np.array([HILL_FOOT_Y + 1 + 60 * rnd.random() ** 1.2 for _ in range(n_plants)])
    PSD = _road_dist(PX, PY, pts)
    PZ = terrain_height(PX, PY, PSD)
    for x, y, z, sd in zip(PX, PY, PZ, PSD):
        if sd < half + 7 or z < 0.2:
            continue
        r = rnd.random()
        dist = math.hypot(x + 15, y + 45)
        fine = dist < 140
        if r < 0.62:
            rr = rnd.uniform(0.8, 1.7) * (1.0 if fine else 1.3)
            hh = rr * rnd.uniform(0.8, 1.3)
            sphere_v = (x, y, z + hh * 0.4)
            # a dark core so the gaps between cards read as depth, not ground
            k = len(core_v)
            for a in range(6):
                ang = a / 6 * math.tau
                core_v.append((x + math.cos(ang) * rr * 0.7, y + math.sin(ang) * rr * 0.7, z))
            core_v.append((x, y, z + hh * 0.85))
            core_f.extend((k + a, k + (a + 1) % 6, k + 6) for a in range(6))
            (dark if rnd.random() < 0.45 else leaf).cluster(sphere_v, rr, rr, hh * 0.5, int(30 + 22 * rr * hh) if fine else 26,
                                                           max(0.7, rr * 0.75), rnd)
        elif r < 0.74:
            rr = rnd.uniform(0.9, 1.6)
            bouga.cluster((x, y, z + rr * 0.5), rr, rr * 0.8, rr * 0.55, int(40 + 20 * rr) if fine else 24, max(0.6, rr * 0.6), rnd)
        elif r < 0.82:
            for k in range(rnd.randint(1, 3)):
                pampas.upright((x + rnd.uniform(-1, 1), y + rnd.uniform(-1, 1), z - 0.1), rnd.uniform(1.6, 2.4), rnd.uniform(2.2, 3.2), rnd)
        elif r < 0.9 and fine:
            agave(x, y, rnd.uniform(0.6, 1.1), z - 0.05, seed=rnd.randrange(99999))
        elif r < 0.97:
            # a tree: a trunk and a big rounded canopy
            th = rnd.uniform(2.0, 3.5)
            cyl("tree_trunk", (x, y, z + th / 2), 0.18, th, bark_mat("bark_tree", (0.25, 0.2, 0.15), (0.38, 0.31, 0.24)), verts=6)
            rr = rnd.uniform(1.6, 2.6)
            dark.cluster((x, y, z + th + rr * 0.4), rr, rr, rr * 0.7, int(60 + 25 * rr) if fine else 40, max(0.9, rr * 0.5), rnd)
        else:
            palm((x, y, z - 0.1), rnd.uniform(6, 11), seed=rnd.randrange(99999), kind=rnd.choice(("queen", "fan", "date")), lod=not fine)
    mesh_obj("hill_cores", core_v, core_f, mat("shrub_core", (0.03, 0.07, 0.02), rough=0.9))
    # villas along the top of the slope and further up, with garden trees between them
    x = -150.0
    while x < 200:
        w = rnd.uniform(14, 24)
        y = HILL_FOOT_Y + 32 + rnd.uniform(-2, 8)
        h, sd = tz(x + w / 2, y)
        if sd > half + 20 and h > 2.5:
            villa(x, y, h, w, rnd.uniform(11, 15), rnd, walls, tiles)
            for k in range(rnd.randint(1, 3)):
                tx = x + rnd.uniform(-4, w + 4)
                dark.cluster((tx, y - rnd.uniform(4, 9), h + rnd.uniform(1, 3)), rnd.uniform(2, 3.5), 2.5, 2.2, 70, 1.2, rnd)
            if rnd.random() < 0.5:
                palm((x + w + 2, y - 2, h), rnd.uniform(10, 16), seed=rnd.randrange(9999), kind="fan", lod=True)
        x += w + rnd.uniform(3, 9)
    for i in range(220):
        x, y = rnd.uniform(-120, 500), rnd.uniform(HILL_FOOT_Y + 70, 400)
        h, sd = tz(x, y)
        if sd < half + 25 or h < 2.5:
            continue
        villa(x, y, h, rnd.uniform(12, 22), rnd.uniform(10, 14), rnd, walls, tiles)
        dark.cluster((x - 4, y - 4, h + 2), 3.5, 3.5, 3.0, 40, 1.6, rnd)
    for c in (leaf, dark, bouga, pampas):
        c.flush()
    build_beach_shops(pts, frames, rnd)


def build_beach_shops(pts, frames, rnd):
    """A small row of beach-town shops on the lot's side of the highway, down the road where it bends: white stucco,
    a tile pent roof, a surf shop with boards out front and a cafe with umbrellas."""
    # find the road point at y ~ 70 and build along the east sidewalk there
    i = min(range(len(pts)), key=lambda k: abs(pts[k].y - 72))
    p, (t, n) = pts[i], frames[i]
    east = -n
    origin = p + east * (PCH_W / 2 + PCH_WALK + 0.4)
    yaw = math.atan2(t.y, t.x)
    stucco = noise_mat("stucco_shop", (0.93, 0.92, 0.88), (0.97, 0.96, 0.93), 30, 0.85, bump=0.15)
    tiles = tile_mat()
    glass_m = mat("win_glass", (0.02, 0.03, 0.04), rough=0.05)
    L, D, H = 26.0, 12.0, 5.2

    def w2(u, v, z=0.0):
        """Shop-local (u along the road, v away from it) to world."""
        q = origin + t * u + east * v
        return Vector((q.x, q.y, z))

    def lbox(name, u0, v0, z0, u1, v1, z1, m):
        corners = [w2(u0, v0), w2(u1, v0), w2(u1, v1), w2(u0, v1)]
        vs = [Vector((c.x, c.y, z0)) for c in corners] + [Vector((c.x, c.y, z1)) for c in corners]
        fs = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        return mesh_obj(name, vs, fs, m)

    lbox("shop_body", -L / 2, 0.8, 0, L / 2, 0.8 + D, H, stucco)
    c = [w2(-L / 2 - 0.4, 0.4, H), w2(L / 2 + 0.4, 0.4, H), w2(L / 2 + 0.4, 1.2 + D, H), w2(-L / 2 + -0.4, 1.2 + D, H)]
    r0, r1 = w2(-L / 2 + D / 2, 0.8 + D / 2, H + 2.4), w2(L / 2 - D / 2, 0.8 + D / 2, H + 2.4)
    mesh_obj("shop_roof", c + [r0, r1], [(0, 1, 5, 4), (1, 2, 5), (2, 3, 4, 5), (3, 0, 4)], tiles)
    for k in range(4):
        u0 = -L / 2 + 1.2 + k * (L / 4)
        lbox("shop_window", u0, 0.75, 0.5, u0 + L / 4 - 2.4, 0.8, 3.0, glass_m)
        # round-arched tops read as a dark lunette over each window
        lbox("shop_arch", u0 + 0.6, 0.76, 3.0, u0 + L / 4 - 3.0, 0.8, 3.5, glass_m)
    # tile pent roof over the shopfronts and a parapet with signs
    vs = [w2(-L / 2 - 0.3, -0.6, 3.7), w2(L / 2 + 0.3, -0.6, 3.7), w2(L / 2 + 0.3, 0.8, 4.4), w2(-L / 2 - 0.3, 0.8, 4.4)]
    mesh_obj("shop_pent", vs, [(0, 1, 2, 3)], tiles)
    blue = mat("surf_blue", (0.05, 0.3, 0.55), rough=0.5)
    signm = mat("white_lit", (1, 1, 1), emit=2.0)
    for u, label, col in ((-L / 4, "TEWPORT SURF CO.", (0.05, 0.3, 0.55)), (L / 4, "BEACH CAFE", (0.75, 0.2, 0.1))):
        pos = w2(u, 0.7, 4.75)
        text("shop_sign", label, (pos.x, pos.y, pos.z), 0.55, mat("sign_" + label[:4], col, rough=0.4), rot=(math.pi / 2, 0, yaw), extrude=0.03)
    # surfboards leaning by the surf shop door, umbrellas and tables by the cafe
    for k in range(5):
        q = w2(-L / 2 + 2 + k * 0.7, 0.5)
        col = [(0.95, 0.85, 0.2), (0.1, 0.55, 0.75), (0.95, 0.95, 0.92), (0.9, 0.35, 0.2), (0.2, 0.7, 0.5)][k]
        cyl("surfboard", (q.x, q.y, 1.15), 0.28, 2.3, mat("board%d" % k, col, rough=0.3), r2=0.12, verts=10, rot=(0.12, 0, yaw))
    for k in range(3):
        q = w2(L / 4 - 4 + k * 4, -1.8)
        cyl("umbrella_pole", (q.x, q.y, 1.2), 0.03, 2.4, mat("cast_iron", (0.02, 0.025, 0.03), rough=0.4, metal=0.6), verts=6)
        cyl("umbrella", (q.x, q.y, 2.5), 1.4, 0.45, mat("umbrella", (0.95, 0.94, 0.9), rough=0.6), r2=0.05, verts=12)
        cyl("cafe_table", (q.x, q.y, 0.72), 0.4, 0.04, mat("cast_iron", (0.02, 0.025, 0.03), rough=0.4, metal=0.6), verts=12)
    _ = blue, signm


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
    # flagship exterior (Faisal's flagship mockup): one dark charcoal volume, full-height glass, a deep fascia
    # with the name in white light, a cantilevered entry canopy, the service wing in the same cladding
    clad = mat("clad", (0.045, 0.048, 0.052), rough=0.32, metal=0.45)
    box("roof", (-16.5, -2.5, 6), (16.5, 17, 6.8), clad)
    box("fascia", (-16.7, -2.75, 5.7), (16.7, -2.4, 7.4), clad)
    box("fascia_lip", (-16.7, -2.8, 5.62), (16.7, -2.4, 5.7), mat("fascia_led", (1, 1, 1), emit=3.0, ecol=(1.0, 0.92, 0.8)))
    box("ceil", (-15, 0, 5.9), (15, 16, 6.0), ceiling)
    for x in range(-12, 14, 4):
        for y in (3, 7, 11, 14):
            cyl("downlight", (x, y, 5.88), 0.18, 0.02, lamp, verts=16)
    glass_wall("front", (-15, 0), (15, 0), 0, 6, every=3)
    glass_wall("rear", (-8, 16), (15, 16), 0, 6, every=3)
    box("west", (-15.3, 0, 0), (-15, 16, 6), white)
    box("east", (15, 0, 0), (15.3, 16, 6), white)
    box("west_clad", (-15.6, -2.4, 0), (-15.3, 17, 6.0), clad)
    box("east_clad", (15.3, -2.4, 0), (15.6, 17, 6.0), clad)
    for x in (-15.45, 15.45):   # corner piers carrying the fascia, like the mockup
        box("pier", (x - 0.35, -2.75, 0), (x + 0.35, -2.4, 5.7), clad)
    sign_lit = mat("sign_white_lit", (1, 1, 1), emit=6.0, ecol=(1.0, 0.98, 0.94))
    text("sign", "CHIEF AUTO", (1.5, -2.8, 6.05), 1.15, sign_lit, extrude=0.06)
    text("sign_sub", "TEWPORT BEACH", (12.2, -2.8, 6.3), 0.3, sign_lit)
    # entry doors
    for x0, x1 in ((-1.6, -1.5), (-0.03, 0.03), (1.5, 1.6)):
        box("door_frame", (x0, -0.08, 0), (x1, 0.08, 3.1), dark)
    box("door_frame", (-1.6, -0.08, 3.0), (1.6, 0.08, 3.1), dark)
    box("door_handle", (-0.25, -0.12, 0.9), (-0.2, -0.08, 1.9), mat("chrome", (0.8, 0.8, 0.82), rough=0.15, metal=1.0))
    box("door_handle", (0.2, -0.12, 0.9), (0.25, -0.08, 1.9), mat("chrome", (0.8, 0.8, 0.82), rough=0.15, metal=1.0))
    g = box("door_glass", (-1.5, -0.03, 0.05), (1.5, 0.03, 3.0), glass())
    g.visible_shadow = False
    box("canopy", (-4.5, -4.2, 3.5), (4.5, 0, 3.8), clad)
    box("canopy_glow", (-4.3, -4.0, 3.48), (4.3, -0.2, 3.5), mat("canopy_led", (1, 1, 1), emit=2.5, ecol=(1.0, 0.9, 0.75)))
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
    box("bay_roof", (15, -0.5, 6.2), (33.5, 16.5, 6.9), clad)
    box("bay_back", (15.3, 15.7, 0), (33, 16, 6.2), mat("block", (0.62, 0.62, 0.6), rough=0.8))
    box("bay_east", (33, 0, 0), (33.3, 16, 6.2), clad)
    box("bay_ceil", (15.3, 0, 6.1), (33, 16, 6.2), ceiling)
    for x in (19, 24, 29):
        for y in (4, 9, 13):
            box("tube", (x - 1.2, y - 0.1, 5.9), (x + 1.2, y + 0.1, 5.98), lamp)
    # front with three roll-up doors (open)
    box("bay_front_l", (15.3, -0.15, 0), (16.2, 0.15, 6.2), clad)
    for i, x in enumerate((16.2, 22.0, 27.8)):
        box("door_post", (x + 5.0, -0.15, 0), (x + 5.8, 0.15, 6.2), clad)
        box("door_head", (x, -0.15, 4.6), (x + 5.0, 0.15, 6.2), clad)
        box("door_roll", (x, -0.3, 4.3), (x + 5.0, 0.0, 4.6), mat("rollup", (0.7, 0.72, 0.75), rough=0.4, metal=0.6))
        text("bay_num", str(i + 1), (x + 2.5, -0.2, 5.0), 0.7, mat("bay_txt", (0.95, 0.75, 0.2), emit=1.0))
    text("bay_sign", "SERVICE", (24.5, -0.55, 6.25), 0.7, sign_lit)
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
    # the roof-top apartment wears the same dark cladding outside (its rooms stay white inside)
    box("apt_clad_w_lo", (AX0 - 0.45, AY0 - 0.15, AZ0), (AX0 - 0.25, AY1 + 3.5, AZ0 + 0.45), clad)
    box("apt_clad_w_hi", (AX0 - 0.45, AY0 - 0.15, AZ1 - 0.35), (AX0 - 0.25, AY1 + 3.5, AZ1 + 0.4), clad)
    box("apt_clad_e", (AX1 + 0.25, AY0 - 0.15, AZ0), (AX1 + 0.55, AY1 + 3.5, AZ1 + 0.4), clad)
    box("apt_clad_roof", (AX0 - 0.65, AY0 - 0.7, AZ1 + 0.02), (AX1 + 0.65, AY0 - 0.55, AZ1 + 0.45), clad)
    box("apt_clad_sill", (AX0, AY0 - 0.05, AZ0), (AX1, AY0, AZ0 + 0.45), clad)
    box("apt_clad_head", (AX0, AY0 - 0.05, AZ1 - 0.35), (AX1, AY0, AZ1), clad)


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
    box("apt_back", (AX0, AY0, AZ0), (AX1, AY0 + 0.25, AZ0 + 0.45), white)   # low sill: the ocean view
    box("apt_back_top", (AX0, AY0, AZ1 - 0.35), (AX1, AY0 + 0.25, AZ1), white)
    glass_wall("apt_front_glass", (AX0, AY0 + 0.12), (AX1, AY0 + 0.12), AZ0 + 0.45, AZ1 - 0.35, every=2.0)
    # the west side looks over Pacific Coast Highway to the ocean: glass above a low sill
    box("apt_west", (AX0 - 0.25, AY0, AZ0), (AX0, AY1, AZ0 + 0.45), white)
    box("apt_west_top", (AX0 - 0.25, AY0, AZ1 - 0.35), (AX0, AY1, AZ1), white)
    glass_wall("apt_west_glass", (AX0 - 0.12, AY0), (AX0 - 0.12, AY1), AZ0 + 0.45, AZ1 - 0.35, every=2.5)
    box("apt_east", (AX1, AY0, AZ0), (AX1 + 0.25, AY1, AZ1), white)
    glass_wall("apt_glass", (AX0, AY1), (AX1, AY1), AZ0, AZ1, every=2.8)
    railm = mat("rail", (0.75, 0.75, 0.76), rough=0.3, metal=1)
    gr = box("balcony_glass", (AX0, AY1 + 3.4, AZ0), (AX1, AY1 + 3.45, AZ0 + 1.05), glass())
    gr.visible_shadow = False
    box("balcony_rail", (AX0, AY1 + 3.38, AZ0 + 1.05), (AX1, AY1 + 3.48, AZ0 + 1.1), railm)


def pole_sign(x, y, h=8.5, w=3.4, sh=2.8):
    """The tall roadside pole sign from the reference photo: a dark steel post and a lit white box sign facing the
    street, CHIEF AUTO in red with TEWPORT BEACH under it, and a lamp on top."""
    steel = mat("alu", (0.08, 0.08, 0.09), rough=0.35, metal=0.8)
    box("pole_sign_post", (x - 0.2, y - 0.2, 0), (x + 0.2, y + 0.2, h - sh), steel)
    box("pole_sign_box", (x - w / 2 - 0.12, y - 0.32, h - sh - 0.1), (x + w / 2 + 0.12, y + 0.32, h + 0.1), steel)
    box("pole_sign_face", (x - w / 2, y - 0.34, h - sh), (x + w / 2, y - 0.32, h),
        mat("sign_face_lit", (0.95, 0.94, 0.9), rough=0.4, emit=0.5, ecol=(1.0, 0.97, 0.9)))
    red = mat("sign_red", (0.75, 0.08, 0.06), rough=0.4)
    text("pole_sign_txt", "CHIEF\nAUTO", (x, y - 0.36, h - sh * 0.36), w * 0.27, red, extrude=0.02)
    text("pole_sign_sub", "TEWPORT BEACH", (x, y - 0.36, h - sh + 0.22), w * 0.075, mat("sign_dark", (0.1, 0.1, 0.12)), extrude=0.01)
    box("pole_sign_lamp", (x - 0.15, y - 0.5, h + 0.1), (x + 0.15, y - 0.2, h + 0.3), steel)
    sphere("pole_sign_bulb", (x, y - 0.55, h + 0.15), (0.12, 0.12, 0.08), mat("lamp", (1, 1, 1), emit=12, ecol=(1.0, 0.86, 0.68)), seg=8)


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
OX0, OX1, OY0, OY1, OH = -16.0, 1.5, -1.0, 12.0, 4.2
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
    stucco = noise_mat("stucco1", (0.3, 0.31, 0.32), (0.36, 0.37, 0.38), 30, 0.6, bump=0.08)    # dark grey panel walls
    trim = mat("trim1", (0.12, 0.13, 0.15), rough=0.5)
    navy = mat("fascia1", (0.05, 0.08, 0.16), rough=0.45)
    gold = mat("gold", (0.85, 0.62, 0.22), rough=0.25, metal=1.0, emit=0.6, ecol=(1.0, 0.7, 0.3))
    # shell
    box("o_slab", (OX0 - 0.6, OY0 - 1.2, 0), (OX1 + 0.6, OY1, TZ), noise_mat("walk1", (0.55, 0.53, 0.5), (0.65, 0.63, 0.6), 8, 0.8))
    box("o_west", (OX0, OY0, 0), (OX0 + 0.2, OY1, OH), stucco)
    box("o_east", (OX1 - 0.2, OY0, 0), (OX1, OY1, OH), stucco)
    box("o_back", (OX0, OY1 - 0.2, 0), (OX1, OY1, OH), stucco)
    lining = mat("o_plaster", (0.86, 0.82, 0.74), rough=0.85)
    box("o_lining_w", (OX0 + 0.2, OY0 + 0.2, 0), (OX0 + 0.21, OY1 - 0.2, OH), lining)
    box("o_lining_e", (OX1 - 0.21, OY0 + 0.2, 0), (OX1 - 0.2, OY1 - 0.2, OH), lining)
    box("o_lining_b", (OX0 + 0.2, OY1 - 0.21, 0), (OX1 - 0.2, OY1 - 0.2, OH), lining)
    box("o_ceiling", (OX0, OY0, OH - 0.6), (OX1, OY1, OH - 0.55), mat("ceiling_tile", (0.85, 0.84, 0.8), rough=0.9))
    # a low glass pavilion like the reference photo: floor-to-ceiling glass in dark mullions across the front and
    # down the east side, under a flat dark standing-seam metal roof with a deep overhang
    dark_frame = mat("alu", (0.08, 0.08, 0.09), rough=0.35, metal=0.8)
    glass_wall("o_front_w", (OX0 + 0.2, OY0 + 0.1), (-6.4, OY0 + 0.1), TZ, OH - 0.6, every=1.6, frame=dark_frame)
    glass_wall("o_front_e", (-5.2, OY0 + 0.1), (OX1 - 0.2, OY0 + 0.1), TZ, OH - 0.6, every=1.6, frame=dark_frame)
    box("o_door", (-6.4, OY0 + 0.06, TZ), (-5.2, OY0 + 0.14, 2.5), dark_frame)
    g = box("o_door_glass", (-6.3, OY0 + 0.04, TZ + 0.1), (-5.3, OY0 + 0.16, 2.4), glass())
    g.visible_shadow = False
    box("o_transom", (-6.4, OY0 + 0.04, 2.5), (-5.2, OY0 + 0.16, OH - 0.6), dark_frame)
    box("o_header", (OX0, OY0, OH - 0.6), (OX1, OY0 + 0.2, OH), dark_frame)
    box("o_door_bar", (-6.3, OY0 - 0.06, 1.0), (-5.3, OY0 - 0.02, 1.05), mat("chrome", (0.8, 0.8, 0.82), rough=0.15, metal=1.0))
    seam = stripe_mat("seam_roof", (0.1, 0.11, 0.12), (0.15, 0.16, 0.17), 0.22, rough=0.4)
    box("o_roof_metal", (OX0 - 1.4, OY0 - 1.6, OH), (OX1 + 1.4, OY1 + 0.8, OH + 0.25), seam)
    box("o_roof_fascia", (OX0 - 1.45, OY0 - 1.65, OH - 0.05), (OX1 + 1.45, OY0 - 1.55, OH + 0.3), dark_frame)
    text("o_sign", "CHIEF AUTO", ((OX0 + OX1) / 2, OY0 - 1.68, OH + 0.02), 0.22, gold, extrude=0.01)
    for x in (-10.5, -7.0, -3.5):
        cyl("o_soffit_light", (x, OY0 - 0.8, OH - 0.02), 0.12, 0.03, mat("lamp", (1, 1, 1), emit=12, ecol=(1.0, 0.86, 0.68)), verts=12)
    box("o_curb_slab", (OX0 - 1.4, OY0 - 1.6, 0), (OX1 + 1.4, OY0, 0.1), noise_mat("walk1", (0.55, 0.53, 0.5), (0.65, 0.63, 0.6), 8, 0.8))
    COL = tier_collection("s1o")    # the sales office furniture (office/desk views only; the showroom view shows the lounge)
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
    COL = TIER_COLLECTIONS["s1"]
    tube = mat("tube_lit", (1, 1, 1), emit=8, ecol=(0.95, 0.97, 1.0))
    for x in (-13.0, -9.5, -6.0, -2.5):
        for y in (2.8, 8.0):
            box("o_light", (x - 0.6, y, OH - 0.62), (x + 0.6, y + 0.6, OH - 0.6), tube)
    # bunting strung between poles at the ends of the block wall and the office roof, all behind the stalls (the
    # game draws the parked cars over the render, so nothing may stand between the lot camera and a stall)
    top = [flag_pole(x, y, h) for x, y, h in ((-21.6, -1.9, 7.2), (5.5, -1.9, 7.2))]
    roof_w, roof_e = Vector((OX0 - 1.45, OY0 - 1.65, OH + 0.28)), Vector((OX1 + 1.45, OY0 - 1.65, OH + 0.28))
    bunting_line(top[0], roof_w, sag=0.6)
    bunting_line(roof_e, top[1], sag=0.6)
    bunting_line(top[0], top[1], sag=1.3)
    light_pole(-20.2, -8.0, 7.5, ((1, 0),))
    light_pole(3.2, -1.6, 7.5, ((0, -1),))
    palm((-20.5, -0.6, 0), h=10.5, seed=91)
    palm((-17.6, 3.0, 0), h=9.0, seed=93, kind="fan")
    palm((3.2, 8.5, 0), h=9.6, seed=94, kind="fan")
    palm((19.5, -2.0, 0), h=9.0, seed=92, kind="fan")
    for x in (-20.6, -19.2, -21.2):
        shrub(x, -1.2 + (x + 20) * 0.6, 0.7, 0.9)
    pole_sign(1.6, -4.2)
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
    pole_sign(16.5, -6.0, h=9.0)
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
    box("t1_wall_tint", (AX1 - 0.02, AY0, AZ0), (AX1 - 0.01, AY1, AZ1), mat("t1_wall", (0.62, 0.55, 0.47), rough=0.85))
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


# ---------------------------------------------------------------- showroom sets (showroom views only)

def screen_image(seed):
    """A blue holographic spec screen: a glowing car wireframe over a grid, with spec bars."""
    def draw(img, ss):
        from PIL import Image, ImageDraw, ImageFilter
        W, H = img.size
        d = ImageDraw.Draw(img)
        for yy in range(H):
            t = yy / H
            d.line([(0, yy), (W, yy)], fill=(int(6 + 10 * t), int(16 + 22 * t), int(40 + 40 * t), 255))
        for gx in range(0, W, 28 * ss):
            d.line([(gx, 0), (gx, H)], fill=(30, 70, 120, 255), width=ss)
        for gy in range(0, H, 28 * ss):
            d.line([(0, gy), (W, gy)], fill=(30, 70, 120, 255), width=ss)
        glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        g = ImageDraw.Draw(glow)
        rnd = random.Random(seed)
        cx, base, L = W * 0.42, H * 0.7, W * 0.62
        roof = rnd.uniform(0.2, 0.3)
        prof = [(-0.5, 0.0), (-0.5, 0.16), (-0.42, 0.22), (-0.2, 0.26), (-0.08, 0.26 + roof), (0.18, 0.26 + roof),
                (0.3, 0.28), (0.48, 0.22), (0.5, 0.1), (0.5, 0.0)]
        pts = [(cx + x * L, base - y * L) for x, y in prof]
        for off in (0.0, 0.035):
            q = [(x + off * L, y - off * L * 0.6) for x, y in pts]
            g.line(q + [q[0]], fill=(90, 210, 255, 255), width=3 * ss)
        for x, y in pts[1:-1]:
            g.line([(x, y), (x + 0.035 * L, y - 0.021 * L)], fill=(90, 210, 255, 200), width=2 * ss)
        for wx in (-0.3, 0.32):
            r = 0.09 * L
            g.ellipse([cx + wx * L - r, base - r, cx + wx * L + r, base + r], outline=(140, 230, 255, 255), width=3 * ss)
        for k in range(4):
            y = H * (0.12 + 0.07 * k)
            g.rectangle([W * 0.76, y, W * (0.78 + rnd.uniform(0.06, 0.18)), y + 6 * ss], fill=(90, 210, 255, 230))
        g.rectangle([W * 0.05, H * 0.08, W * 0.4, H * 0.08 + 10 * ss], fill=(220, 240, 255, 255))
        img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(6 * ss)))
        img.alpha_composite(glow)
    return _pil_image("spec_screen_%d" % seed, draw, (640, 360), bg=(6, 16, 40))


def screen_mat(seed):
    name = "spec_screen_m%d" % seed
    if name in _mats:
        return _mats[name]
    m, nt, b = _node_mat(name)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = screen_image(seed)
    nt.links.new(_coords(nt, "UV"), tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(tex.outputs["Color"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 4.0
    b.inputs["Roughness"].default_value = 0.08
    _mats[name] = m
    return m


def wall_screen(x, y, z, w, h, axis, face, seed):
    """A wall-mounted spec monitor; axis 'x' runs along x (on a y wall), face is +1/-1 toward the room."""
    bez = mat("bezel", (0.02, 0.02, 0.025), rough=0.3)
    if axis == "x":
        box("screen_bezel", (x - w / 2 - 0.04, y, z - 0.04), (x + w / 2 + 0.04, y + 0.05 * face, z + h + 0.04), bez)
        yy = y + 0.055 * face
        vs = [(x - w / 2, yy, z), (x + w / 2, yy, z), (x + w / 2, yy, z + h), (x - w / 2, yy, z + h)]
        if face > 0:
            vs = [vs[1], vs[0], vs[3], vs[2]]
    else:
        box("screen_bezel", (x, y - w / 2 - 0.04, z - 0.04), (x + 0.05 * face, y + w / 2 + 0.04, z + h + 0.04), bez)
        xx = x + 0.055 * face
        vs = [(xx, y + w / 2, z), (xx, y - w / 2, z), (xx, y - w / 2, z + h), (xx, y + w / 2, z + h)]
        if face < 0:
            vs = [vs[1], vs[0], vs[3], vs[2]]
    _uv_mesh("spec_screen", vs, [(0, 1, 2, 3)], [(0, 0), (1, 0), (1, 1), (0, 1)], screen_mat(seed))
    # a cool glow on the wall around it
    ld = bpy.data.lights.new("screen_glow", "AREA")
    ld.size, ld.energy, ld.color = max(w, h), 60, (0.35, 0.65, 1.0)
    lo = bpy.data.objects.new("screen_glow", ld)
    lo.location = (x, y + 0.3 * face, z + h / 2) if axis == "x" else (x + 0.3 * face, y, z + h / 2)
    lo.rotation_euler = (math.pi / 2 * face, 0, 0) if axis == "x" else (0, -math.pi / 2 * face, 0)
    _link(lo)


def totem_screen(x, y, seed):
    """A free-standing spec monitor on a slim post, facing into the room (+y)."""
    post = mat("alu", (0.08, 0.08, 0.09))
    box("totem_base", (x - 0.35, y - 0.25, 0.05), (x + 0.35, y + 0.25, 0.1), post)
    box("totem_post", (x - 0.05, y - 0.05, 0.1), (x + 0.05, y + 0.05, 2.0), post)
    wall_screen(x, y + 0.06, 2.0, 1.9, 1.07, "x", 1, seed)


def sofa(x, y, yaw, width, m, seats=True):
    pivot = bpy.data.objects.new("sofa", None)
    pivot.location = (x, y, 0.05)
    pivot.rotation_euler.z = yaw
    _link(pivot)
    leg = mat("alu", (0.08, 0.08, 0.09))
    w = width / 2
    parts = [box("sofa_base", (-w, -0.45, 0.1), (w, 0.45, 0.42), m, bevel=0.06),
             box("sofa_back", (-w, 0.22, 0.42), (w, 0.45, 0.85), m, bevel=0.07),
             box("sofa_arm", (-w - 0.18, -0.45, 0.1), (-w, 0.45, 0.62), m, bevel=0.06),
             box("sofa_arm", (w, -0.45, 0.1), (w + 0.18, 0.45, 0.62), m, bevel=0.06)]
    n = max(1, round(width / 0.8))
    for i in range(n):
        a = -w + i * width / n
        parts.append(box("sofa_cushion", (a + 0.02, -0.42, 0.42), (a + width / n - 0.02, 0.2, 0.55), m, bevel=0.05))
    for sx in (-w - 0.1, w + 0.1):
        for sy in (-0.38, 0.38):
            parts.append(box("sofa_leg", (sx - 0.03, sy - 0.03, 0), (sx + 0.03, sy + 0.03, 0.1), leg))
    for o in parts:
        o.parent = pivot


def lounge(x, y, yaw):
    """Tan leather sofa and armchair round a low table on a rug (x, y is the table)."""
    tan = noise_mat("tan_leather", (0.42, 0.22, 0.1), (0.55, 0.32, 0.16), 40, 0.42, bump=0.05)
    c, s_ = math.cos(yaw), math.sin(yaw)
    def at(dx, dy):
        return x + dx * c - dy * s_, y + dx * s_ + dy * c
    sofa(*at(0, 1.25), yaw, 2.2, tan)
    sofa(*at(1.9, 0.1), yaw + math.pi / 2, 0.8, tan)
    box("rug_show", (x - 2.0, y - 1.2, 0.05), (x + 2.0, y + 1.9, 0.062), mat("rug_show", (0.62, 0.58, 0.52), rough=0.95))
    box("low_table", (x - 0.7, y - 0.35, 0.06), (x + 0.7, y + 0.35, 0.36), noise_mat("walnut_t", (0.18, 0.1, 0.05), (0.26, 0.15, 0.08), 6, 0.35, stretch=(1, 14, 1)), bevel=0.02)
    box("low_table_top", (x - 0.72, y - 0.37, 0.36), (x + 0.72, y + 0.37, 0.38), mat("black_glass", (0.02, 0.02, 0.02), rough=0.08))
    box("brochure", (x - 0.3, y - 0.15, 0.38), (x + 0.0, y + 0.08, 0.39), mat("brochure", (0.9, 0.88, 0.84), rough=0.4))


def counter(x0, y0, x1, y1, h=1.05):
    white = mat("counter_white", (0.92, 0.91, 0.88), rough=0.35)
    box("counter", (x0, y0, 0.05), (x1, y1, h), white, bevel=0.03)
    box("counter_top", (x0 - 0.05, y0 - 0.05, h), (x1 + 0.05, y1 + 0.05, h + 0.05), noise_mat("oak_top", (0.36, 0.22, 0.12), (0.48, 0.32, 0.18), 6, 0.35, stretch=(1, 14, 1)))
    box("counter_glow", (x0, y0 - 0.01, 0.08), (x1, y0, 0.12), mat("led_strip", (1, 1, 1), emit=6, ecol=(1.0, 0.8, 0.55)))


def showroom_floor(x0, y0, x1, y1, z):
    m = noise_mat("show_floor", (0.17, 0.16, 0.15), (0.27, 0.26, 0.24), 2.5, 0.16, macro=0.4)
    box("show_floor", (x0, y0, z), (x1, y1, z + 0.004), m)


def golden_sun(energy=34.0, el=16.0, az=-148.0):
    """Low warm sun through the front glass (showroom views only; the lot keeps the shared midday sun)."""
    ld = bpy.data.lights.new("golden_sun", "SUN")
    ld.energy = energy
    ld.color = (1.0, 0.48, 0.17)
    ld.angle = math.radians(0.6)    # crisp long light patches on the floor
    e, a = math.radians(el), math.radians(az)
    v = Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
    lo = bpy.data.objects.new("golden_sun", ld)
    lo.rotation_euler = (-v).to_track_quat("-Z", "Y").to_euler()
    _link(lo)


def build_showroom_sets():
    global COL
    # tier 3: the glass flagship (x -15..15, y 0..16), looking out the front glass at the lot and the coast
    COL = tier_collection("show3")
    showroom_floor(-15, 0, 15, 16, 0.05)
    golden_sun()
    lounge(-4.6, 11.6, 0.0)
    for i, y in enumerate((2.2, 5.2, 8.2)):
        wall_screen(-14.95, y, 1.9, 2.3, 1.3, "y", 1, 30 + i)
    for i, y in enumerate((3.0, 6.0)):
        wall_screen(14.95, y, 1.9, 2.3, 1.3, "y", -1, 40 + i)
    planter(-14.0, 1.0)
    planter(-6.5, 1.0)
    planter(5.5, 1.0)
    for i, x in enumerate((-12.5, 0.5, 11.5)):
        totem_screen(x, 1.3, 70 + i)
    # tier 2: the street showroom (x -10..6, y 0..12)
    COL = tier_collection("show2")
    showroom_floor(-10, 0, 6, 12, 0.05)
    golden_sun()
    lounge(-7.4, 5.6, 0.0)
    wall_screen(-9.98, 5.0, 1.8, 2.0, 1.15, "y", 1, 50)
    wall_screen(-9.98, 2.2, 1.8, 2.0, 1.15, "y", 1, 51)
    planter(-9.2, 0.8)
    # tier 1: the glass pavilion on the PCH lot (x -16..1.5, y -1..12)
    COL = tier_collection("show1")
    showroom_floor(OX0 + 0.2, OY0 + 0.2, OX1 - 0.2, OY1 - 0.2, TZ + 0.012)
    golden_sun()
    lounge(-11.2, 8.2, 0.0)
    counter(-4.8, 8.4, -1.8, 9.2)
    chair(-3.3, 9.9, math.pi, mat("leather_brown", (0.16, 0.08, 0.04), rough=0.35))
    wall_screen(OX0 + 0.22, 2.6, 1.6, 2.0, 1.15, "y", 1, 60)
    wall_screen(OX0 + 0.22, 5.6, 1.6, 2.0, 1.15, "y", 1, 61)
    wall_screen(OX1 - 0.22, 4.0, 1.6, 2.0, 1.15, "y", -1, 62)
    box("show1_back_feature", (-9.0, OY1 - 0.26, TZ), (-5.0, OY1 - 0.21, OH - 0.6), noise_mat("oak_feature", (0.32, 0.2, 0.11), (0.45, 0.3, 0.17), 6, 0.45, stretch=(1, 14, 1)))
    text("show1_logo", "CHIEF AUTO", (-7.0, OY1 - 0.27, 2.4), 0.35, mat("gold", (0.85, 0.62, 0.22), rough=0.25, metal=1.0, emit=0.6, ecol=(1.0, 0.7, 0.3)), rot=(math.pi / 2, 0, math.pi))
    planter(OX0 + 0.8, OY0 + 0.8)
    planter(OX1 - 0.8, OY0 + 0.8)
    COL = None


# display row per showroom view: ground points of the leftmost and rightmost car (the game spaces its cars between)
SHOW_ROWS = {
    "showroom": ((-10.5, 4.5), (9.0, 4.5)),
    "showroom_t2": ((-7.5, 4.6), (3.5, 4.6)),
    "showroom_t1": ((-12.2, 2.6), (-2.3, 2.6)),
}


def export_showroom(view, cam, path):
    """Screen positions for the game's showroom sprites (fractions of the image, u right, v down)."""
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    bpy.context.view_layer.update()
    length, width, height = REF_CAR

    def uv(p):
        q = world_to_camera_view(sc, cam, Vector(p))
        return q, [round(q.x, 5), round(1.0 - q.y, 5)]

    pos = cam.location
    fwd = (cam.matrix_world.to_quaternion() @ Vector((0, 0, -1)))
    flat = Vector((fwd.x, fwd.y, 0)).normalized()
    eye = uv(pos + flat * 200.0)[1][1]
    row = []
    for gx, gy in SHOW_ROWS[view]:
        g = Vector((gx, gy, 0.05))
        tq, t = uv(g + Vector((0, 0, 0.42 * height)))
        ppm = (cam.data.lens / 36.0) / tq.z
        row.append({"ground": uv(g)[1], "target": t, "frame_w": round(ppm * sprite_frame_m(length), 5),
                    "ppm": round(ppm, 6)})
    data = {"view": view, "eye": eye, "floor": uv(Vector((pos.x, 0.0 if view != "showroom_t1" else OY0, 0.05)))[1][1],
            "row": row, "about": "eye: horizon line; floor: where the floor meets the front glass; row: the leftmost "
            "and rightmost display car (ground point, sprite frame centre, frame width as a fraction of image width)."}
    import json
    with open(path, "w") as f:
        json.dump(data, f, indent=1)


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
    # keep detail through the denoiser: OIDN guided by albedo and normal passes, accurate prefilter
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    sc.cycles.denoising_prefilter = "ACCURATE"
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.015
    sc.cycles.max_bounces = 6
    sc.cycles.transmission_bounces = 6
    sc.cycles.transparent_max_bounces = 16
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.render.resolution_x, sc.render.resolution_y = RES
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 92
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
    "showroom": ((-0.75, 15.2, 1.65), (-0.75, -10.0, 1.3), 18, -0.3),     # inside, looking out the front glass
    "office": ((-8.6, 9.6, 1.55), (-13.0, 15.5, 1.3), 18, -0.3),
    "garage": ((24.5, 0.9, 1.7), (24.5, 16.0, 1.6), 17, -0.2),
    "desk": ((11.5, 12.6, 1.25), (11.5, 16.0, 1.05), 24, -0.3),
    "dealdesk": ((-3.4, 4.3, 1.3), (1.5, 16.0, 0.9), 20, -0.3),
    "apartment": ((-1.0, 11.5, AZ0 + 1.65), (-30.0, -6.0, AZ0 + 1.0), 17, -0.2),    # from the back of the room, south over PCH to the ocean
    "lot_t1": ((-10.5, -43.0, 5.68), (-10.5, -23.0, 4.28), 50, 0.2),
    "showroom_t1": ((-7.25, 11.4, 1.65), (-7.25, -10.0, 1.3), 18, 0.0),
    "office_t1": ((-3.5, 5.4, 1.6), (-9.0, -1.0, 1.3), 18, 0.0),
    "garage_t1": ((11.0, -12.0, 1.7), (11.0, 2.0, 1.6), 18, -0.5),
    "desk_t1": ((-7.9, 5.25, 1.3), (-7.9, -1.0, 1.05), 24, 0.0),     # seated at the desk (desk_seat)
    "dealdesk_t1": ((-4.3, 5.6, 1.35), (-9.5, -1.0, 0.9), 20, 0.0),
    "lot_t2": ((-14.5, -46.0, 6.46), (-10.34, -26.44, 5.06), 50, 0.2),
    "showroom_t2": ((-2.0, 11.6, 1.65), (-2.0, -10.0, 1.3), 18, -0.2),
    "office_t2": ((-6.0, 8.6, 1.55), (-9.8, 12.0, 1.3), 18, -0.2),
    "garage_t2": ((9.6, 0.9, 1.7), (9.6, 12.0, 1.6), 17, -0.2),
    "desk_t2": ((4.7, 9.6, 1.25), (4.7, 12.0, 1.05), 24, -0.2),
    "dealdesk_t2": ((-8.6, 1.6, 1.3), (-4.0, 12.0, 0.9), 20, -0.2),
}


def desk_seat(on):
    """desk_t1 is seen from the chair: hide the chair and what stands on the desk top (the game draws its own
    desk, monitor and collectibles over the lower half of this view)."""
    for o in TIER_COLLECTIONS["s1o"].all_objects:
        bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
        c = sum(bb, Vector()) / 8
        top = min(p.z for p in bb) > TZ + 0.74 and -9.8 < c.x < -6.2 and 3.4 < c.y < 4.7
        seat = -8.5 < c.x < -7.3 and 4.6 < c.y < 5.7
        if top or seat:
            o.hide_render = on


def render_view(cam, name, out):
    if name.startswith("apartment"):
        key, sets = "apartment", {"s3", int(name[-1])}
    else:
        key = name
        tier = name[-1] if name[-3:-1] == "_t" else "3"
        sets = {"s" + tier}
        if name == "dealdesk":
            sets.add(9)
        if name.startswith("showroom"):
            sets.add("show" + tier)
        elif tier == "1":
            sets.add("s1o")
    pos, tgt, lens, exp = VIEWS[key]
    show_sets(sets)
    desk_seat(name == "desk_t1")
    golden_hour(name.startswith("showroom"))
    cam.location = pos
    cam.data.lens = lens
    cam.data.clip_end = 5000
    cam.rotation_euler = (Vector(tgt) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.view_settings.exposure = exp - 0.6   # daylight is bright; keep whites from blowing out
    bpy.context.scene.render.filepath = os.path.join(out, "bg_%s%s.jpg" % (name, "_night" if NIGHT else ""))
    if NIGHT:
        bpy.context.scene.view_settings.exposure = exp - 0.2
        bpy.ops.render.render(write_still=True)
        return
    if name in LOT_ROWS:
        export_stalls(name, cam, os.path.join(out, "stalls_%s.json" % name))
    if name in SHOW_ROWS:
        export_showroom(name, cam, os.path.join(out, "%s.json" % name))
    bpy.ops.render.render(write_still=True)


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    build_world()
    build_ground()
    build_coast()
    global COL
    COL = tier_collection("s3")
    build_site3_front()
    build_dealership()
    COL = None
    build_site1()
    build_site2()
    build_apartment_tiers()
    build_deal_props()
    build_showroom_sets()
    # interior fill so rooms are not black against the bright sky, per dealership
    fills = {"s3": (((0, 8, 5.5), (28, 14), 2400), ((-11.5, 12.5, 5.5), (6, 6), 500),
                    ((24, 8, 5.8), (16, 14), 2600), ((-6, 9.5, AZ1 - 0.3), (16, 11), 1300)),
             "s1": (((-7.25, 5.5, OH - 0.7), (16, 12), 1500),),
             "s2": (((-2, 6, 4.8), (15, 11), 1500), ((-7.8, 10, 2.9), (4, 3.5), 250), ((9.6, 6, 4.4), (6, 11), 1200))}
    for key, rows in fills.items():
        for loc, size, e in rows:
            ld = bpy.data.lights.new("fill", "AREA")
            ld.shape = "RECTANGLE"
            ld.size, ld.size_y = size
            ld.energy = e
            ld["day"] = e
            ld.color = (1.0, 0.9, 0.78)
            lo = bpy.data.objects.new("fill", ld)
            lo.location = loc
            TIER_COLLECTIONS[key].objects.link(lo)


NIGHT = bool(os.environ.get("NIGHT"))
GLOW = {"lamp": 3.0, "lamp_glass": 14.0, "lp_lens": 18.0, "sign_face_lit": 5.0, "white_lit": 2.5, "screen": 2.0}


def make_night():
    """Turns the built day scene into night: the sky becomes a dark blue gradient with faint stars (seen by the
    camera only), the sun lamps go, lamp glass and signs glow and get a real light each, interior fills brighten."""
    sc = bpy.context.scene
    for name in [o.name for o in bpy.data.objects if o.type == "LIGHT" and o.data.type == "SUN"]:
        bpy.data.objects.remove(bpy.data.objects[name])
    w = bpy.data.worlds.new("night")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    grad = _ramp(nt, sep.outputs["Z"], ((0.0, (0.035, 0.05, 0.11)), (0.12, (0.012, 0.02, 0.06)), (0.5, (0.003, 0.005, 0.02))))
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 260.0
    nt.links.new(tc.outputs["Generated"], vor.inputs["Vector"])
    star = _ramp(nt, vor.outputs["Distance"], ((0.0, (1.6, 1.6, 1.7)), (0.06, (0, 0, 0))))
    pick = _n(nt, "ShaderNodeTexNoise", Scale=90.0, Detail=0.0)
    nt.links.new(tc.outputs["Generated"], pick.inputs["Vector"])
    keep = _ramp(nt, pick.outputs["Fac"], ((0.62, (0, 0, 0)), (0.66, (1, 1, 1))))
    stars = _mix(nt, 1.0, star, keep, "MULTIPLY")
    lp = nt.nodes.new("ShaderNodeLightPath")
    hi = _ramp(nt, sep.outputs["Z"], ((0.03, (0, 0, 0)), (0.12, (1, 1, 1))))
    sv = _mix(nt, 1.0, stars, hi, "MULTIPLY")
    seen = _mix(nt, 1.0, sv, lp.outputs["Is Camera Ray"], "MULTIPLY")
    col = _mix(nt, 1.0, grad, seen, "ADD")
    nt.links.new(col, nt.nodes["Background"].inputs[0])
    nt.nodes["Background"].inputs["Strength"].default_value = 1.0
    moon = bpy.data.lights.new("moon", "SUN")
    moon.energy, moon.color, moon.angle = 0.12, (0.55, 0.65, 1.0), math.radians(2)
    mo = bpy.data.objects.new("moon", moon)
    mo.rotation_euler = (math.radians(35), 0, math.radians(-30))
    sc.collection.objects.link(mo)
    for m in bpy.data.materials:
        k = GLOW.get(m.name.split(".")[0])
        if k and m.use_nodes:
            b = m.node_tree.nodes.get("Principled BSDF")
            if b:
                b.inputs["Emission Strength"].default_value *= k
    dg = bpy.context.evaluated_depsgraph_get()
    for o in list(bpy.data.objects):
        base = o.name.split(".")[0]
        spec = {"lamp_globe": ("POINT", 320, (1.0, 0.8, 0.55), 0.3), "lp_lens": ("SPOT", 2200, (1.0, 0.93, 0.82), 0.4),
                "pole_sign_face": ("AREA", 400, (1.0, 0.95, 0.88), 2.5)}.get(base)
        if not spec or o.type != "MESH":
            continue
        bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
        c = sum(bb, Vector()) / 8
        ld = bpy.data.lights.new("night_" + base, spec[0])
        ld.energy, ld.color = spec[1], spec[2]
        if spec[0] == "AREA":
            ld.size = spec[3]
        else:
            ld.shadow_soft_size = spec[3]
        if spec[0] == "SPOT":
            ld.spot_size = math.radians(120)
            ld.spot_blend = 0.6
        lo = bpy.data.objects.new(ld.name, ld)
        if base == "pole_sign_face":
            lo.location = c + Vector((0, -1.2, 0))
            lo.rotation_euler = (math.radians(90), 0, 0)
        else:
            lo.location = c - Vector((0, 0, 0.12))
        for col_ in o.users_collection:
            col_.objects.link(lo)
    for o in bpy.data.objects:
        if o.type == "LIGHT" and o.name.startswith("fill"):
            o.data.energy *= 1.35
    # the tier-1 carport gets its work lights on (two tubes under the corrugated roof)
    global COL
    COL = TIER_COLLECTIONS["s1"]
    tube = mat("tube_lit", (1, 1, 1), emit=8, ecol=(0.95, 0.97, 1.0))
    for x in (8.5, 13.5):
        box("cp_tube", (x - 0.7, -4.1, 3.22), (x + 0.7, -3.95, 3.28), tube)
        ld = bpy.data.lights.new("cp_light", "AREA")
        ld.shape, ld.size, ld.size_y, ld.energy, ld.color = "RECTANGLE", 1.4, 0.3, 420, (0.95, 0.96, 1.0)
        lo = bpy.data.objects.new("cp_light", ld)
        lo.location = (x, -4.0, 3.18)
        TIER_COLLECTIONS["s1"].objects.link(lo)
    COL = None


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    views = sys.argv[2:] or [v + t for t in ("", "_t1", "_t2") for v in ("lot", "showroom", "office", "garage", "desk", "dealdesk")] + \
        ["apartment1", "apartment2", "apartment3"]
    build()
    if NIGHT:
        make_night()
    cam = setup_render()
    for v in views:
        render_view(cam, v, out)


if __name__ == "__main__":
    main()
