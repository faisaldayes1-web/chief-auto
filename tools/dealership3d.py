"""One Chief Auto dealership in Tewport Beach, built in Blender: every background in the game is rendered from it.

The site: a glass showroom on the harbour. The lot faces the street (south), the showroom looks out over the
marina (north), the service bay is the wing on the east side, Marco's office is the glass corner room at the
back west, and the owner's apartment sits on the roof. Apartment tiers (1-3) toggle furniture and finish, so
the same room can be upgraded visually in the game; the showroom tiers work the same way.

Usage (bpy venv):  python tools/dealership3d.py <out_dir> [view ...]
Views: lot, showroom, office, garage, desk, dealdesk, apartment1, apartment2, apartment3.  SAMPLES env sets quality.
"""
import math
import os
import random
import sys

import bpy  # noqa: I001
from mathutils import Vector

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


def noise_mat(name, c1, c2, scale, rough, detail=6, bump=0.0, metal=0.0, veins=False, stretch=(1, 1, 1)):
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
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
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
    sky.sun_elevation = math.radians(5)
    sky.sun_rotation = math.radians(-60)   # sun over the harbour, low in the west-north-west
    sky.altitude = 30
    sky.air_density = 1.3
    sky.aerosol_density = 2.2
    nt.links.new(sky.outputs[0], nt.nodes["Background"].inputs[0])
    nt.nodes["Background"].inputs["Strength"].default_value = 0.35
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 3.2
    sun.color = (1.0, 0.78, 0.55)
    sun.angle = math.radians(1.2)
    so = bpy.data.objects.new("sun", sun)
    # direction matching the sky texture's sun
    el, az = math.radians(5), math.radians(-60)
    d = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    so.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(so)


def build_ground():
    asphalt = noise_mat("asphalt", (0.05, 0.05, 0.055), (0.11, 0.11, 0.115), 60, 0.85, bump=0.15)
    concrete = noise_mat("concrete", (0.55, 0.53, 0.5), (0.68, 0.66, 0.62), 8, 0.7, bump=0.05)
    paint = mat("stripe", (0.92, 0.92, 0.88), rough=0.6)
    box("lot", (-60, -60, -0.1), (60, 0, 0), asphalt)
    box("street", (-200, -90, -0.12), (200, -60, -0.02), noise_mat("street", (0.04, 0.04, 0.045), (0.08, 0.08, 0.085), 40, 0.8))
    box("sidewalk", (-200, -60, -0.1), (200, -57, 0.08), concrete)
    box("pad", (-40, 0, -0.1), (40, 30, 0.02), concrete)
    # parking stalls on the lot
    for x in range(-24, 26, 3):
        box("stall", (x - 0.06, -14, 0), (x + 0.06, -8.5, 0.012), paint)
        box("stall", (x - 0.06, -27, 0), (x + 0.06, -21.5, 0.012), paint)
    box("lane", (-24, -15.3, 0), (24, -15.15, 0.012), mat("yellow", (0.85, 0.65, 0.1), rough=0.6))
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
    # bunting flags over the front row
    flag_cols = [mat("flag_r", (0.8, 0.1, 0.1)), mat("flag_w", (0.95, 0.95, 0.95)), mat("flag_b", (0.1, 0.25, 0.7)),
                 mat("flag_g", (0.9, 0.65, 0.15))]
    for x in (-24, -8, 8, 24):
        cyl("flagpole", (x, -18, 3.0), 0.07, 6.0, mat("rail", (0.75, 0.75, 0.76), rough=0.3, metal=1), verts=8)
    for k in range(48):
        x = -24 + k
        sag = 5.6 - 0.35 * math.sin((k % 16) / 16 * math.pi)
        bpy.ops.mesh.primitive_cone_add(vertices=3, radius1=0.28, depth=0.01, location=(x + 0.5, -18, sag - 0.25),
                                        rotation=(math.pi / 2, 0, 0))
        fl = bpy.context.object
        fl.data.materials.append(flag_cols[k % 4])
        _link(fl)
    for i, x in enumerate(range(-150, 160, 22)):
        palm((x, -58.5, 0), h=10 + (i % 4), seed=30 + i)


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
    hill = noise_mat("hills", (0.25, 0.27, 0.2), (0.42, 0.38, 0.28), 0.02, 0.9)
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


def tier_collection(t):
    c = bpy.data.collections.new("apt_tier%d" % t)
    bpy.context.scene.collection.children.link(c)
    TIER_COLLECTIONS[t] = c
    return c


def build_apartment_tiers():
    """Tier 1: a mattress in a bare room. Tier 2: a proper condo. Tier 3: the Tewport penthouse."""
    global COL
    lamp = mat("lamp", (1, 1, 1), emit=12, ecol=(1.0, 0.86, 0.68))
    # tier 1
    COL = tier_collection(1)
    box("t1_floor", (AX0, AY0, AZ0 + 0.06), (AX1, AY1, AZ0 + 0.07), noise_mat("t1_concrete", (0.45, 0.44, 0.42), (0.55, 0.54, 0.5), 5, 0.8))
    box("t1_mattress", (-11.5, 6.0, AZ0 + 0.07), (-9.5, 8.2, AZ0 + 0.32), mat("t1_sheet", (0.75, 0.76, 0.8), rough=0.9), bevel=0.08)
    box("t1_pillow", (-11.3, 6.1, AZ0 + 0.32), (-9.7, 6.6, AZ0 + 0.45), mat("t1_pillow", (0.9, 0.9, 0.9), rough=0.9), bevel=0.06)
    for i in range(4):
        box("t1_box", (-4 + i * 0.7, 4.0, AZ0 + 0.07), (-3.4 + i * 0.7, 4.6, AZ0 + 0.07 + 0.4 + (i % 2) * 0.35), mat("cardboard", (0.55, 0.4, 0.24), rough=0.9))
    box("t1_table", (-6.2, 9.8, AZ0 + 0.07), (-5.0, 10.6, AZ0 + 0.75), mat("t1_plastic", (0.9, 0.9, 0.88), rough=0.5))
    cyl("t1_bulb", (-7, 9, AZ1 - 0.4), 0.08, 0.15, lamp)
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


def show_tier(t):
    for k, c in TIER_COLLECTIONS.items():
        c.hide_render = k != t


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
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = 0.0
    cam = bpy.data.cameras.new("cam")
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return co


VIEWS = {
    # name: (camera position, look-at target, lens mm, exposure)
    "lot": ((-3.0, -34.0, 1.7), (2.0, 6.0, 4.6), 24, 0.0),
    "showroom": ((0.0, 0.8, 1.65), (0.0, 16.0, 1.45), 18, -0.3),
    "office": ((-8.6, 9.6, 1.55), (-13.0, 15.5, 1.3), 18, -0.3),
    "garage": ((24.5, 0.9, 1.7), (24.5, 16.0, 1.6), 17, -0.2),
    "desk": ((11.5, 12.6, 1.25), (11.5, 16.0, 1.05), 24, -0.3),
    "apartment": ((-12.5, 4.6, AZ0 + 1.6), (-3.0, 16.0, AZ0 + 1.2), 17, -0.2),
    "dealdesk": ((-3.4, 4.3, 1.3), (1.5, 16.0, 0.9), 20, -0.3),
}


def render_view(cam, name, out):
    key = "apartment" if name.startswith("apartment") else name
    pos, tgt, lens, exp = VIEWS[key]
    if key == "apartment":
        show_tier(int(name[-1]))
    elif key == "dealdesk":
        show_tier(9)
    else:
        show_tier(0)
    cam.location = pos
    cam.data.lens = lens
    cam.data.clip_end = 5000
    cam.rotation_euler = (Vector(tgt) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.view_settings.exposure = exp
    bpy.context.scene.render.filepath = os.path.join(out, "bg_%s.jpg" % name)
    bpy.ops.render.render(write_still=True)


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    build_world()
    build_ground()
    build_harbour()
    build_dealership()
    build_apartment_tiers()
    build_deal_props()
    # interior fill so rooms are not black against the bright sky
    for loc, size, e in (((0, 8, 5.5), (28, 14), 2400), ((-11.5, 12.5, 5.5), (6, 6), 500),
                         ((24, 8, 5.8), (16, 14), 2600), ((-6, 9.5, AZ1 - 0.3), (16, 11), 1300)):
        ld = bpy.data.lights.new("fill", "AREA")
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = size
        ld.energy = e
        ld.color = (1.0, 0.9, 0.78)
        lo = bpy.data.objects.new("fill", ld)
        lo.location = loc
        bpy.context.scene.collection.objects.link(lo)


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    views = sys.argv[2:] or ["lot", "showroom", "office", "garage", "desk", "apartment1", "apartment2", "apartment3", "dealdesk"]
    build()
    cam = setup_render()
    for v in views:
        render_view(cam, v, out)


if __name__ == "__main__":
    main()
