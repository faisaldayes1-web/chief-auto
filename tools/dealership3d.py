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


def box(name, lo, hi, m, bevel=0.0):
    """Axis-aligned box from corner lo to corner hi."""
    lo, hi = Vector(lo), Vector(hi)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(lo + hi) / 2)
    ob = bpy.context.object
    ob.name = name
    ob.scale = hi - lo
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ob.data.materials.append(m)
    if bevel > 0:
        md = ob.modifiers.new("b", "BEVEL")
        md.width = bevel
        md.segments = 3
    _link(ob)
    return ob


def cyl(name, loc, r, h, m, r2=None, verts=24, rot=(0, 0, 0)):
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, location=loc, vertices=verts, rotation=rot)
    else:
        bpy.ops.mesh.primitive_cone_add(radius1=r, radius2=r2, depth=h, location=loc, vertices=verts, rotation=rot)
    ob = bpy.context.object
    ob.name = name
    ob.data.materials.append(m)
    for p in ob.data.polygons:
        p.use_smooth = True
    _link(ob)
    return ob


def sphere(name, loc, scale, m, seg=24):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=loc, segments=seg, ring_count=seg // 2)
    ob = bpy.context.object
    ob.name = name
    ob.scale = scale
    ob.data.materials.append(m)
    for p in ob.data.polygons:
        p.use_smooth = True
    _link(ob)
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


def palm(loc, h=9.0, seed=0):
    rnd = random.Random(seed)
    trunk = mat("palm_trunk", (0.36, 0.28, 0.2), rough=0.9)
    leaf = mat("palm_leaf", (0.12, 0.3, 0.08), rough=0.6)
    lean = rnd.uniform(-0.12, 0.12)
    t = cyl("palm", (loc[0], loc[1], h / 2), 0.28, h, trunk, r2=0.17, verts=10, rot=(lean, 0, 0))
    top = Vector((loc[0], loc[1] - math.sin(lean) * h / 2 * 2, h * math.cos(lean)))
    top = Vector(loc) + Vector((0, -math.sin(lean) * h, math.cos(lean) * h))
    for k in range(16):
        a = k / 8 * math.tau + rnd.uniform(-0.2, 0.2) + (0.4 if k >= 8 else 0)
        droop = 0.09 if k < 8 else 0.16
        bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
        f = bpy.context.object
        f.scale = (3.6, 0.6, 1)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.subdivide(number_cuts=8)
        bpy.ops.object.mode_set(mode="OBJECT")
        for v in f.data.vertices:
            x = v.co.x + 1.8          # 0..3.6 along the frond
            v.co.x = x
            v.co.y *= max(0.05, 1 - x / 3.8)
            v.co.z = -droop * x * x + 0.35 * x
            v.co.z += abs(v.co.y) * 0.5      # V-shaped fold along the rib
        f.location = top
        f.rotation_euler = (0, 0, a)
        f.data.materials.append(leaf)
        _link(f)
    cyl("palm_nut", top, 0.35, 0.5, trunk, verts=8)
    return t


# ---------------------------------------------------------------- the site

def build_world():
    sc = bpy.context.scene
    w = bpy.data.worlds.new("sky")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_elevation = math.radians(34)
    sky.sun_rotation = math.radians(-130)   # afternoon sun from the south-west, lighting the street side
    sky.altitude = 30
    sky.air_density = 1.0
    sky.aerosol_density = 0.7
    nt.links.new(sky.outputs[0], nt.nodes["Background"].inputs[0])
    nt.nodes["Background"].inputs["Strength"].default_value = 0.2
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 2.0
    sun.color = (1.0, 0.9, 0.76)
    sun.angle = math.radians(1.2)
    so = bpy.data.objects.new("sun", sun)
    # direction matching the sky texture's sun
    el, az = math.radians(34), math.radians(-130)
    d = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    so.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(so)


def build_ground():
    asphalt = noise_mat("asphalt", (0.045, 0.045, 0.05), (0.1, 0.1, 0.105), 60, 0.85, bump=0.15, macro=0.45)
    concrete = noise_mat("concrete", (0.5, 0.48, 0.45), (0.64, 0.62, 0.58), 8, 0.7, bump=0.05, macro=0.25)
    paint = mat("stripe", (0.92, 0.92, 0.88), rough=0.6)
    box("lot", (-60, -60, -0.1), (60, 0, 0), asphalt)
    box("street", (-200, -90, -0.12), (200, -60, -0.02), noise_mat("street", (0.04, 0.04, 0.045), (0.08, 0.08, 0.085), 40, 0.8))
    box("sidewalk", (-200, -60, -0.1), (200, -57, 0.08), concrete)
    box("pad", (-40, 0, -0.1), (40, 30, 0.02), concrete)
    for i, x in enumerate(range(-150, 160, 22)):
        palm((x, -58.5, 0), h=10 + (i % 4), seed=30 + i)


def build_site3_front():
    """The flagship's lot dressing: angled stalls, planters, palms, pylon sign and bunting."""
    concrete = noise_mat("concrete3", (0.55, 0.53, 0.5), (0.68, 0.66, 0.62), 8, 0.7, bump=0.05)  # noqa: F841
    paint = mat("stripe", (0.92, 0.92, 0.88), rough=0.6)
    build_lot_stalls("lot", paint, concrete)
    # planters along the front with palms
    hedge = noise_mat("hedge", (0.06, 0.16, 0.04), (0.14, 0.3, 0.08), 30, 0.8, bump=0.6)
    for x in (-27, -9, 9, 27):
        box("planter", (x - 2.2, -4.8, 0), (x + 2.2, -3.0, 0.55), concrete, bevel=0.04)
        box("hedge", (x - 2.0, -4.6, 0.5), (x + 2.0, -3.2, 0.9), hedge)
    for i, x in enumerate((-27, -9, 9, 27, -44, 44)):
        palm((x, -3.9 if abs(x) < 40 else 6, 0), h=9 + (i % 3) * 1.4, seed=i)
    # street pylon sign
    dark = mat("alu", (0.08, 0.08, 0.09), rough=0.35, metal=0.8)
    box("pylon", (-33, -40, 0), (-31.2, -39.4, 9.5), dark)
    box("pylon_face", (-33.4, -40.1, 6.4), (-30.8, -39.3, 9.3), mat("pylon_lit", (0.05, 0.07, 0.12), rough=0.3))
    text("pylon_txt", "CHIEF\nAUTO", (-32.1, -40.15, 8.35), 0.95, mat("gold", (0.85, 0.62, 0.22)), extrude=0.03)
    text("pylon_sub", "PRE-OWNED · SERVICE", (-32.1, -40.15, 6.6), 0.2, mat("white_lit", (1, 1, 1), emit=2.0), extrude=0.01)
    # bunting along the showroom front, under the fascia and behind the parked cars (the game draws the cars over
    # the render, so nothing may stand between the lot camera and a stall)
    for x in (-21.0, 13.5):
        cyl("flagpole", (x, -4.4, 3.0), 0.07, 6.0, mat("rail", (0.75, 0.75, 0.76), rough=0.3, metal=1), verts=8)
    bunting_line((-21.0, -4.4, 5.8), (13.5, -4.4, 5.8))


def build_harbour():
    water = noise_mat("water", (0.02, 0.07, 0.1), (0.04, 0.13, 0.17), 2.5, 0.04, bump=0.25, stretch=(1, 3, 1))
    box("sea", (-800, 30, -1.2), (800, 1400, -0.6), water)
    wood = noise_mat("deck", (0.35, 0.25, 0.17), (0.45, 0.33, 0.22), 30, 0.7, stretch=(1, 12, 1))
    box("boardwalk", (-60, 25, -0.4), (60, 31, 0.02), wood)
    railm = mat("rail", (0.75, 0.75, 0.76), rough=0.3, metal=1)
    box("rail", (-60, 30.8, 0.9), (60, 30.9, 0.96), railm)
    for x in range(-60, 61, 2):
        box("post", (x - 0.03, 30.82, 0), (x + 0.03, 30.88, 0.95), railm)
    hull = mat("hull", (0.92, 0.93, 0.94), rough=0.25)
    navy = mat("hull_navy", (0.05, 0.08, 0.16), rough=0.3)
    rnd = random.Random(5)
    for dock_x in (-48, -20, 8, 36):
        box("dock", (dock_x - 0.9, 31, -0.75), (dock_x + 0.9, 95, -0.45), wood)
        for j in range(5):
            for side in (-1, 1):
                if rnd.random() < 0.2:
                    continue
                y = 38 + j * 11 + rnd.uniform(-1, 1)
                x = dock_x + side * rnd.uniform(4.2, 5.2)
                ln = rnd.uniform(9, 14)
                hm = navy if rnd.random() < 0.25 else hull
                hb = sphere("hull", (x, y, -0.55), (1.8, ln / 2, 0.9), hm, seg=20)
                box("deck_" + str(j), (x - 1.3, y - ln * 0.3, -0.1), (x + 1.3, y + ln * 0.2, 0.25), hull, bevel=0.1)
                box("cabin", (x - 0.9, y - ln * 0.15, 0.25), (x + 0.9, y + ln * 0.12, 1.0), hull, bevel=0.15)
                if rnd.random() < 0.6:
                    cyl("mast", (x, y, 6), 0.06, 12 + rnd.uniform(-2, 4), railm, verts=8)
                hb.visible_shadow = True
    # Tewport's far shore: a long ridge of hills across the harbour
    hill = noise_mat("hills", (0.09, 0.11, 0.05), (0.36, 0.31, 0.2), 0.12, 0.9, detail=10, macro=0.35)   # sage scrub and dry grass
    me = bpy.data.meshes.new("ridge")
    verts, faces = [], []
    nx, ny = 160, 8
    for j in range(ny + 1):
        for i in range(nx + 1):
            x = -2200 + 4400 * i / nx
            y = 1250 + 500 * j / ny
            hgt = (70 + 45 * math.sin(x * 0.004 + 1.3) + 25 * math.sin(x * 0.011 + 0.4) + 10 * math.sin(x * 0.031))
            hgt *= math.sin(math.pi * min(1.0, j / ny * 1.6)) if j < ny else 0.0
            verts.append((x, y, hgt - 2))
    for j in range(ny):
        for i in range(nx):
            a0 = j * (nx + 1) + i
            faces.append((a0, a0 + 1, a0 + nx + 2, a0 + nx + 1))
    me.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new("ridge", me)
    ob.data.materials.append(hill)
    for p in ob.data.polygons:
        p.use_smooth = True
    _link(ob)
    town = mat("town", (0.85, 0.8, 0.72), rough=0.8)
    for i in range(70):
        x = rnd.uniform(-700, 700)
        box("house", (x, 1150 + rnd.uniform(0, 60), -1), (x + rnd.uniform(6, 20), 1160 + rnd.uniform(0, 60), rnd.uniform(4, 14)), town)


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
    for x in (-13.6, 13.6):
        planter(x, 14.6)
    planter(13.6, 1.4)
    # display podiums (cars are drawn by the game on top)
    # ---- Marco's office (x -15..-8, y 9..16), glass front, window to the harbour
    box("office_floor", (-15, 9, 0.05), (-8, 16, 0.07), wood)
    glass_wall("office_front", (-15, 9), (-8, 9), 0, 6, every=2.3)
    glass_wall("office_side", (-8, 9), (-8, 15.6), 0, 6, every=2.2)
    glass_wall("office_rear", (-15, 16), (-8, 16), 0, 6, every=3.5)
    box("exec_desk", (-13.2, 12.2, 0), (-10.2, 13.2, 0.76), wood, bevel=0.02)
    box("exec_top", (-13.3, 12.1, 0.76), (-10.1, 13.3, 0.81), mat("black_glass", (0.02, 0.02, 0.02), rough=0.08))
    box("monitor", (-12.2, 12.9, 0.85), (-11.0, 12.95, 1.55), mat("screen", (0.02, 0.05, 0.1), rough=0.1, emit=0.6, ecol=(0.3, 0.55, 0.9)))
    chair(-11.7, 13.9, math.pi, mat("leather", (0.06, 0.05, 0.05), rough=0.35))
    for k, x in enumerate((-14.4, -9.0)):
        chair(x, 10.6, math.pi * 0.25 * (1 if k else -1), mat("leather_tan", (0.45, 0.27, 0.15), rough=0.4))
    box("shelf", (-14.9, 9.6, 0), (-14.55, 12.2, 2.4), wood)
    for i in range(6):
        box("book", (-14.85, 9.7 + i * 0.4, 1.0 + (i % 3) * 0.5), (-14.6, 9.95 + i * 0.4, 1.35 + (i % 3) * 0.5),
            mat("book%d" % i, [(0.5, 0.1, 0.1), (0.1, 0.2, 0.4), (0.8, 0.6, 0.2)][i % 3], rough=0.6))
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
            pts = 12
            for k in range(pts):
                t0, t1 = k / pts, (k + 1) / pts
                z0 = 10.2 - 0.9 * math.sin(math.pi * t0)
                z1 = 10.2 - 0.9 * math.sin(math.pi * t1)
                p0 = Vector((a + (b - a) * t0 + dx, y, z0))
                p1 = Vector((a + (b - a) * t1 + dx, y, z1))
                mid = (p0 + p1) / 2
                d = p1 - p0
                bpy.ops.mesh.primitive_cylinder_add(radius=0.012, depth=d.length, location=mid, vertices=6)
                w = bpy.context.object
                w.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
                w.data.materials.append(wire)
                _link(w)


def bunting_line(a, b, n=None):
    """A string of pennants between two points, sagging in the middle."""
    cols = [mat("flag_r", (0.8, 0.1, 0.1)), mat("flag_w", (0.95, 0.95, 0.95)), mat("flag_b", (0.1, 0.25, 0.7)),
            mat("flag_g", (0.9, 0.65, 0.15))]
    a, b = Vector(a), Vector(b)
    d = b - a
    n = n or max(4, int(d.length / 0.9))
    yaw = math.atan2(d.y, d.x)
    for k in range(n):
        t = (k + 0.5) / n
        p = a + d * t - Vector((0, 0, 0.8 * math.sin(math.pi * t)))
        bpy.ops.mesh.primitive_cone_add(vertices=3, radius1=0.24, depth=0.01, location=p - Vector((0, 0, 0.22)),
                                        rotation=(math.pi / 2, 0, yaw))
        fl = bpy.context.object
        fl.data.materials.append(cols[k % 4])
        _link(fl)


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
    bpy.ops.mesh.primitive_cube_add(size=1, location=(mid.x, mid.y, height / 2))
    ob = bpy.context.object
    ob.name = name
    ob.scale = (d.length, width, height)
    ob.rotation_euler.z = math.atan2(d.y, d.x)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    ob.data.materials.append(m)
    _link(ob)
    return ob


def build_lot_stalls(view, paint, wall_mat):
    """Painted stall stripes, wheel stops and the low walls for a lot view's rows (see LOT_ROWS)."""
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
            for a, b in spans:
                box("low_wall", (a, wall_y, 0), (b, wall_y + 0.3, LOW_WALL - 0.06), wall_mat)
                box("low_wall_cap", (a - 0.04, wall_y - 0.04, LOW_WALL - 0.06), (b + 0.04, wall_y + 0.34, LOW_WALL), cap)


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
    build_lot_stalls("lot_t1", paint, noise_mat("block1", (0.5, 0.49, 0.46), (0.62, 0.6, 0.56), 14, 0.85, bump=0.1))
    chain_fence([(-22, -30), (-22, 6)])
    chain_fence([(22, -30), (22, 6)])
    chain_fence([(-22, 6), (22, 6)])
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
    # the big sign on the fascia
    box("o_fascia", (OX0 - 0.4, OY0 - 0.45, 2.85), (OX1 + 0.4, OY0 - 0.15, OH + 0.35), navy)
    text("o_sign", "CHIEF AUTO", ((OX0 + OX1) / 2, OY0 - 0.5, 3.45), 0.78, gold)
    text("o_sign_sub", "USED CARS", ((OX0 + OX1) / 2, OY0 - 0.5, 3.05), 0.3, mat("white_lit", (1, 1, 1), emit=2.0))
    box("o_awning", (OX0 - 0.4, OY0 - 1.3, 2.7), (OX1 + 0.4, OY0 - 0.15, 2.85), navy)
    # inside: carpet, a desk facing the windows, PC, filing cabinet, whiteboard with goals, poster, plant
    carpet = noise_mat("carpet", (0.2, 0.22, 0.26), (0.27, 0.29, 0.33), 220, 0.95, bump=0.3)
    box("o_carpet", (OX0 + 0.2, OY0 + 0.2, TZ), (OX1 - 0.2, OY1 - 0.2, TZ + 0.01), carpet)
    wood = noise_mat("desk_wood1", (0.3, 0.18, 0.09), (0.4, 0.25, 0.13), 6, 0.4, stretch=(1, 14, 1))
    box("o_desk", (-9.6, 3.6, TZ), (-6.4, 4.5, TZ + 0.76), wood)
    box("o_desk_top", (-9.7, 3.5, TZ + 0.76), (-6.3, 4.6, TZ + 0.8), wood)
    box("o_monitor", (-8.4, 4.1, TZ + 0.85), (-7.3, 4.14, TZ + 1.5), mat("screen", (0.02, 0.05, 0.1), rough=0.1, emit=0.6, ecol=(0.3, 0.55, 0.9)))
    box("o_monitor_stand", (-7.92, 4.15, TZ + 0.8), (-7.78, 4.25, TZ + 0.9), trim)
    box("o_keyboard", (-8.3, 3.7, TZ + 0.8), (-7.4, 3.9, TZ + 0.82), trim)
    box("o_phone", (-9.4, 3.8, TZ + 0.8), (-9.0, 4.1, TZ + 0.88), trim)
    box("o_mug", (-6.7, 3.8, TZ + 0.8), (-6.6, 3.9, TZ + 0.9), mat("mug", (0.08, 0.08, 0.1)))
    chair(-7.9, 5.1, math.pi, mat("leather", (0.06, 0.05, 0.05), rough=0.35))
    for x in (-9.0, -6.9):
        chair(x, 2.7, 0.0, mat("guest_chair", (0.2, 0.2, 0.22), rough=0.7))
    box("o_filing", (-11.75, 5.6, TZ), (-11.2, 6.7, TZ + 1.35), mat("filing", (0.4, 0.42, 0.45), metal=0.6, rough=0.4))
    box("o_whiteboard", (OX0 + 0.2, 1.4, 1.2), (OX0 + 0.23, 4.4, 2.6), mat("whiteboard", (0.95, 0.95, 0.94), rough=0.25))
    box("o_wb_frame", (OX0 + 0.19, 1.35, 1.15), (OX0 + 0.21, 4.45, 2.65), mat("galv", (0.6, 0.62, 0.63)))
    ink = mat("marker", (0.1, 0.12, 0.2), rough=0.6)
    text("o_goals", "GOALS", (OX0 + 0.24, 2.9, 2.3), 0.22, ink, rot=(math.pi / 2, 0, math.pi / 2), extrude=0.0)
    for i, line in enumerate(("[ ] Sell 3 cars", "[ ] Make $10,000 profit", "[ ] Hire 1 salesperson", "[ ] Upgrade the lot")):
        text("o_goal", line, (OX0 + 0.24, 1.6, 2.0 - i * 0.2), 0.12, ink, rot=(math.pi / 2, 0, math.pi / 2), extrude=0.0, align="LEFT")
    box("o_poster", (OX1 - 0.23, 2.0, 1.4), (OX1 - 0.2, 4.0, 2.4), mat("poster", (0.1, 0.12, 0.18), emit=0.15, ecol=(0.6, 0.2, 0.15)))
    planter(-2.8, 6.3)
    tube = mat("tube_lit", (1, 1, 1), emit=8, ecol=(0.95, 0.97, 1.0))
    for x in (-9.5, -4.5):
        box("o_light", (x - 0.6, 2.8, OH - 0.62), (x + 0.6, 3.4, OH - 0.6), tube)
    # flags strung from the roof to poles behind the stall rows and at the street corners (kept out of the lot
    # camera's way, since the game draws the parked cars over the render), a few palms and the utility line
    galv = mat("galv", (0.6, 0.62, 0.63), rough=0.4, metal=0.9)
    poles = ((-21.0, -3.0), (4.8, -1.2), (-21.5, -28.0), (21.5, -28.0))
    for x, y in poles:
        cyl("flagpole1", (x, y, 3.5), 0.06, 7.0, galv, verts=8)
    top = [Vector((x, y, 6.9)) for x, y in poles]
    bunting_line(top[0], (OX0, OY0 - 0.3, OH + 0.3))
    bunting_line((OX1, OY0 - 0.3, OH + 0.3), top[1])
    bunting_line(top[0], top[1])
    bunting_line(top[2], top[0])
    bunting_line(top[3], top[1])
    palm((-20.5, -1.0, 0), h=10.5, seed=91)
    palm((-16.0, 3.0, 0), h=12.0, seed=93)
    palm((19.5, -2.0, 0), h=11.0, seed=92)
    power_line(-110, 110, -57.0)
    # carport for repairs on the east side
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
    build_lot_stalls("lot_t2", paint, mat("block", (0.62, 0.62, 0.6), rough=0.8))
    for x in (-14, 12):
        box("planter2", (x - 1.5, -4.5, 0), (x + 1.5, -3.2, 0.5), mat("planter_c", (0.6, 0.58, 0.55)))
        box("hedge2", (x - 1.3, -4.3, 0.45), (x + 1.3, -3.4, 0.85), mat("shrub", (0.1, 0.25, 0.07), rough=0.8))
    palm((-18, -3.5, 0), h=9.0, seed=71)
    palm((15, -3.5, 0), h=10.0, seed=72)
    # small pylon
    box("pylon2", (-24, -28, 0), (-23.6, -27.6, 5.0), dark)
    box("pylon2_face", (-25.4, -28.1, 3.4), (-22.2, -27.5, 5.0), mat("pylon2_face", (0.95, 0.95, 0.93), rough=0.4))
    text("pylon2_txt", "CHIEF AUTO", (-23.8, -28.15, 4.05), 0.45, mat("sign_red", (0.75, 0.08, 0.06)), extrude=0.01)
    power_line(-110, 110, -57.0)
    # bunting along the roofline, behind the parked cars
    for x in (-12.2, 14.6):
        cyl("flagpole2", (x, -1.6, 3.3), 0.06, 6.6, mat("rail", (0.75, 0.75, 0.76)), verts=8)
    bunting_line((-12.2, -1.6, 6.5), (14.6, -1.6, 6.5))
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
    box("b2_band", (B0, D0 - 0.3, 3.4), (B1, D0, H), white)
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
    chair(-8.4, 11.5, math.pi, mat("leather", (0.06, 0.05, 0.05), rough=0.35))
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
    "lot": ((-26.0, -56.0, 7.88), (-20.82, -36.68, 6.48), 50, 0.0),
    "showroom": ((0.0, 0.8, 1.65), (0.0, 16.0, 1.45), 18, -0.3),
    "office": ((-8.6, 9.6, 1.55), (-13.0, 15.5, 1.3), 18, -0.3),
    "garage": ((24.5, 0.9, 1.7), (24.5, 16.0, 1.6), 17, -0.2),
    "desk": ((11.5, 12.6, 1.25), (11.5, 16.0, 1.05), 24, -0.3),
    "dealdesk": ((-3.4, 4.3, 1.3), (1.5, 16.0, 0.9), 20, -0.3),
    "apartment": ((-12.5, 4.6, AZ0 + 1.6), (-3.0, 16.0, AZ0 + 1.2), 17, -0.2),
    "lot_t1": ((-10.5, -43.0, 5.68), (-10.5, -23.0, 4.28), 50, 0.0),
    "showroom_t1": ((-1.0, -26.0, 1.65), (-1.0, -10.0, 1.45), 18, 0.0),   # customers browse outside on the lot
    "office_t1": ((-3.5, 5.4, 1.6), (-9.0, -1.0, 1.3), 18, 0.0),
    "garage_t1": ((11.0, -12.0, 1.7), (11.0, 2.0, 1.6), 18, -0.5),
    "desk_t1": ((-7.9, 5.9, 1.35), (-7.9, -1.0, 1.2), 24, 0.0),
    "dealdesk_t1": ((-4.3, 5.6, 1.35), (-9.5, -1.0, 0.9), 20, 0.0),
    "lot_t2": ((-14.5, -46.0, 6.46), (-10.34, -26.44, 5.06), 50, 0.0),
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
