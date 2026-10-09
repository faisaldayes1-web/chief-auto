"""Product renders for everything you can buy on the Office PC: desk furniture, collectibles for the desk,
ShowroomPro fit-outs and AdSpace campaigns. Procedural geometry only (plus the game's own car .glb files
for the model car and the lot dioramas), lit by the same warm studio as tools/people3d.py, rendered on a
transparent background with a soft contact shadow, then framed to a consistent 256x256 (base of the item
at the same height in every picture, so the desk view can anchor them by their bottom).

    /root/bpyenv/bin/python tools/props3d.py                  # every item -> assets/props/<id>.png
    /root/bpyenv/bin/python tools/props3d.py mug trophy       # just these
    /root/bpyenv/bin/python tools/props3d.py --sheet out.png  # contact sheet of what's rendered
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "assets", "props")
SAMPLES = int(os.environ.get("SAMPLES", 64))
RES = int(os.environ.get("RES", 512))
FINAL = 256
MARCO_REF = "/mnt/project-files/chief-auto/references/marco-office-render.jpg"
LOT_BG = os.path.join(ROOT, "assets", "world", "bg_lot.jpg")
TMP = os.path.join(os.environ.get("PROPS_TMP", "/tmp"), "props3d")


def sheet(out):
    """Contact sheet of assets/props for a quick look."""
    from PIL import Image, ImageDraw
    names = sorted(f[:-4] for f in os.listdir(OUT) if f.endswith(".png"))
    cols = 8
    cell = 150
    rows = (len(names) + cols - 1) // cols
    im = Image.new("RGB", (cols * cell, rows * (cell + 22)), (34, 36, 42))
    d = ImageDraw.Draw(im)
    for i, n in enumerate(names):
        x, y = (i % cols) * cell, (i // cols) * (cell + 22)
        p = Image.open(os.path.join(OUT, n + ".png")).convert("RGBA").resize((cell - 20, cell - 20), Image.LANCZOS)
        d.rounded_rectangle((x + 5, y + 5, x + cell - 5, y + cell - 5), 10, fill=(58, 60, 68))
        im.paste(p, (x + 10, y + 10), p)
        d.text((x + 10, y + cell + 2), n, fill=(230, 220, 200))
    im.save(out)
    print("sheet", out, len(names))


if len(sys.argv) > 1 and sys.argv[1] == "--sheet":
    sheet(sys.argv[2])
    sys.exit(0)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

D90 = math.pi / 2


# ------------------------------------------------------------------ materials

def mat(name, rgb, rough=0.5, metal=0.0, emit=0.0, ecol=None, spec=0.5, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Specular IOR Level"].default_value = spec
    b.inputs["Coat Weight"].default_value = coat
    if emit:
        b.inputs["Emission Color"].default_value = (*(ecol or rgb), 1)
        b.inputs["Emission Strength"].default_value = emit
    return m


def glass(name, rgb=(0.9, 0.97, 1.0), rough=0.03):
    m = mat(name, rgb, rough)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["IOR"].default_value = 1.45
    return m


def img_mat(name, path, rough=0.6):
    m = mat(name, (1, 1, 1), rough)
    nt = m.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path)
    nt.links.new(tex.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
    return m


def noise_mat(name, a, b, scale, rough=0.5, detail=2.0):
    m = mat(name, a, rough)
    nt = m.node_tree
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*a, 1)
    ramp.color_ramp.elements[0].position = 0.42
    ramp.color_ramp.elements[1].color = (*b, 1)
    ramp.color_ramp.elements[1].position = 0.55
    nt.links.new(n.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
    return m


WALNUT = lambda: noise_mat("walnut", (0.26, 0.13, 0.055), (0.34, 0.19, 0.08), 9, 0.35)
CHROME = lambda: mat("chrome", (0.9, 0.9, 0.92), 0.12, 1.0)
GOLD = lambda: mat("gold", (1.0, 0.78, 0.32), 0.2, 1.0)
BLACK = lambda: mat("black", (0.03, 0.03, 0.035), 0.4)
SKIN = lambda t=0.0: mat("skin", (0.86 - t * 0.25, 0.64 - t * 0.22, 0.5 - t * 0.2), 0.55)


# ------------------------------------------------------------------ geometry

def _link(ob, m):
    bpy.context.scene.collection.objects.link(ob)
    if m is not None:
        ob.data.materials.append(m)
    return ob


def _smooth(ob, angle=35):
    for p in ob.data.polygons:
        p.use_smooth = True
    try:
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))
    except Exception:
        pass


def box(name, mn, mx, m, bevel=0.0, rot=(0, 0, 0)):
    mn, mx = Vector(mn), Vector(mx)
    c = (mn + mx) / 2
    h = (mx - mn) / 2
    vs = [Vector((sx * h.x, sy * h.y, sz * h.z)) for sz in (-1, 1) for sy in (-1, 1) for sx in (-1, 1)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in vs], [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.location = c
    ob.rotation_euler = rot
    _link(ob, m)
    if bevel > 0:
        md = ob.modifiers.new("b", "BEVEL")
        md.width = bevel
        md.segments = 4
        _smooth(ob, 40)
    return ob


def cyl(name, c, r, h, m, rot=(0, 0, 0), verts=48, r2=None):
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=c, rotation=rot)
    else:
        bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r2, depth=h, location=c, rotation=rot)
    ob = bpy.context.object
    ob.name = name
    ob.data.materials.append(m)
    _smooth(ob)
    return ob


def sphere(name, c, r, m, scale=(1, 1, 1), rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=c, segments=48, ring_count=24, rotation=rot)
    ob = bpy.context.object
    ob.name = name
    ob.scale = scale
    ob.data.materials.append(m)
    _smooth(ob, 80)
    return ob


def torus(name, c, R, r, m, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, location=c, rotation=rot, major_segments=48, minor_segments=16)
    ob = bpy.context.object
    ob.name = name
    ob.data.materials.append(m)
    _smooth(ob, 80)
    return ob


def text(name, s, c, size, m, rot=(D90, 0, 0), extrude=0.004, bold=True):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = s
    cu.size = size
    cu.extrude = extrude
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    if bold:
        cu.offset = size * 0.02
    ob = bpy.data.objects.new(name, cu)
    ob.location = c
    ob.rotation_euler = rot
    return _link(ob, m)


def plane(name, c, w, h, m, rot=(D90, 0, 0)):
    """A w x h picture standing upright (facing -y) at c."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0)], [], [(0, 1, 2, 3)])
    me.uv_layers.new()
    uv = me.uv_layers[0].data
    for i, (u, v) in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
        uv[i].uv = (u, v)
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.location = c
    ob.rotation_euler = rot
    return _link(ob, m)


def spring(name, c, r, h, turns, wire, m):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = wire
    cu.bevel_resolution = 4
    sp = cu.splines.new("POLY")
    n = int(turns * 24)
    sp.points.add(n)
    for i in range(n + 1):
        a = i / 24.0 * math.tau
        sp.points[i].co = (c[0] + math.cos(a) * r, c[1] + math.sin(a) * r, c[2] + h * i / n, 1)
    ob = bpy.data.objects.new(name, cu)
    return _link(ob, m)


def frame(name, c, w, h, depth, m, lip=0.02):
    """A picture frame (four bevelled bars) around a w x h opening, standing upright at c, facing -y."""
    x, y, z = c
    box(name + "_l", (x - w / 2 - lip, y - depth / 2, z - h / 2 - lip), (x - w / 2, y + depth / 2, z + h / 2 + lip), m, 0.004)
    box(name + "_r", (x + w / 2, y - depth / 2, z - h / 2 - lip), (x + w / 2 + lip, y + depth / 2, z + h / 2 + lip), m, 0.004)
    box(name + "_t", (x - w / 2, y - depth / 2, z + h / 2), (x + w / 2, y + depth / 2, z + h / 2 + lip), m, 0.004)
    box(name + "_b", (x - w / 2, y - depth / 2, z - h / 2 - lip), (x + w / 2, y + depth / 2, z - h / 2), m, 0.004)
    box(name + "_back", (x - w / 2, y + depth * 0.2, z - h / 2), (x + w / 2, y + depth / 2, z + h / 2), mat("back", (0.1, 0.1, 0.1), 0.8))


def import_car(glb, scale, at, yaw=0.0):
    """One of the game's cars, shrunk to a model, standing on z=at[2] (its wheels touch the ground at z=0 in the file)."""
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, "assets", "cars3d", glb))
    new = [o for o in bpy.context.scene.objects if o not in before]
    bpy.ops.object.select_all(action="DESELECT")
    for o in new:
        o.select_set(True)
    bpy.context.view_layer.objects.active = new[0]
    bpy.ops.object.join() if len([o for o in new if o.type == "MESH"]) > 1 else None
    car = bpy.context.view_layer.objects.active
    for o in bpy.context.scene.objects:
        if o not in before and o != car:
            bpy.data.objects.remove(o)
    car.scale = (scale, scale, scale)
    car.rotation_euler = (0, 0, yaw)
    car.location = at
    return car


def star_base(c, m, r=0.3, z=0.0):
    """Five-leg office chair base with a gas lift."""
    for i in range(5):
        a = i / 5 * math.tau
        box("leg", (-r, -0.02, z + 0.01), (0, 0.02, z + 0.04), m)
        bpy.context.object.location = (c[0], c[1], 0) if False else bpy.context.object.location
        ob = bpy.context.scene.objects["leg"]
        ob.name = "leg%d" % i
        ob.location = (c[0] + math.cos(a) * r / 2, c[1] + math.sin(a) * r / 2, z + 0.025)
        ob.rotation_euler = (0, 0, a)
        cyl("wheel%d" % i, (c[0] + math.cos(a) * r, c[1] + math.sin(a) * r, z + 0.02), 0.025, 0.02, BLACK(), rot=(0, D90, a))
    cyl("lift", (c[0], c[1], z + 0.2), 0.03, 0.36, m)


# ------------------------------------------------------------------ the items

def b_folding():
    grey = mat("grey", (0.62, 0.63, 0.66), 0.5)
    leg = mat("leg", (0.25, 0.26, 0.28), 0.4, 0.6)
    box("top", (-0.9, -0.35, 0.72), (0.9, 0.35, 0.75), grey, 0.008)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl("leg", (sx * 0.78, sy * 0.28, 0.36), 0.015, 0.72, leg, rot=(sy * 0.12, -sx * 0.12, 0))
        cyl("bar", (sx * 0.78, 0, 0.05), 0.012, 0.6, leg, rot=(D90, 0, 0))


def b_oak():
    w = WALNUT()
    box("top", (-0.95, -0.4, 0.72), (0.95, 0.4, 0.76), w, 0.01)
    box("ped", (0.3, -0.36, 0), (0.9, 0.36, 0.72), w, 0.006)
    box("ped2", (-0.9, -0.36, 0), (-0.55, 0.36, 0.72), w, 0.006)
    box("modesty", (-0.55, 0.2, 0.15), (0.3, 0.26, 0.72), w)
    br = mat("brass", (0.85, 0.65, 0.3), 0.3, 1.0)
    for i in range(3):
        z = 0.12 + i * 0.22
        box("drawer%d" % i, (0.32, -0.37, z), (0.88, -0.355, z + 0.18), mat("dk", (0.22, 0.11, 0.05), 0.4))
        cyl("knob%d" % i, (0.6, -0.385, z + 0.09), 0.012, 0.02, br, rot=(D90, 0, 0))


def b_glass():
    g = glass("glass")
    ch = CHROME()
    box("top", (-0.95, -0.42, 0.74), (0.95, 0.42, 0.755), g)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl("leg", (sx * 0.85, sy * 0.34, 0.37), 0.02, 0.74, ch)
    box("cab", (0.25, -0.3, 0.05), (0.85, 0.34, 0.68), mat("white", (0.9, 0.9, 0.92), 0.25, coat=0.5), 0.01)
    box("shelf", (-0.9, -0.3, 0.3), (0.0, 0.3, 0.315), g)


def b_carbon():
    cf = mat("carbon", (0.04, 0.04, 0.045), 0.22, 0.3, coat=1.0)
    red = mat("red", (0.85, 0.08, 0.1), 0.35, coat=0.6)
    box("top", (-0.95, -0.42, 0.72), (0.95, 0.42, 0.76), cf, 0.012)
    box("stripe", (-0.95, -0.1, 0.761), (0.95, -0.02, 0.763), red)
    box("stripe2", (-0.95, 0.0, 0.761), (0.95, 0.03, 0.763), red)
    for sx in (-1, 1):
        box("leg", (sx * 0.9 - 0.04, -0.3, 0), (sx * 0.9 + 0.04, 0.3, 0.72), cf, 0.01, rot=(0, sx * 0.08, 0))
        box("foot", (sx * 0.9 - 0.12, -0.36, 0), (sx * 0.9 + 0.12, 0.36, 0.04), red, 0.01)


def b_plastic():
    wh = mat("white", (0.92, 0.92, 0.9), 0.4)
    box("seat", (-0.24, -0.24, 0.42), (0.24, 0.24, 0.45), wh, 0.015)
    box("back", (-0.24, 0.2, 0.45), (0.24, 0.24, 0.88), wh, 0.015, rot=(-0.12, 0, 0))
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl("leg", (sx * 0.2, sy * 0.2, 0.21), 0.018, 0.42, wh, rot=(sy * 0.06, -sx * 0.06, 0))
        box("arm", (sx * 0.26 - 0.02, -0.2, 0.62), (sx * 0.26 + 0.02, 0.22, 0.65), wh, 0.01)
        cyl("armpost", (sx * 0.26, -0.18, 0.54), 0.014, 0.18, wh)


def b_office():
    bk = mat("mesh", (0.08, 0.1, 0.14), 0.7)
    seat = mat("seat", (0.1, 0.12, 0.16), 0.8)
    star_base((0, 0), mat("alu", (0.6, 0.6, 0.62), 0.3, 0.8), 0.32)
    box("seat", (-0.25, -0.25, 0.42), (0.25, 0.25, 0.5), seat, 0.03)
    box("back", (-0.23, 0.2, 0.5), (0.23, 0.24, 1.0), bk, 0.03, rot=(-0.08, 0, 0))
    box("head", (-0.14, 0.2, 1.0), (0.14, 0.23, 1.12), bk, 0.02, rot=(-0.12, 0, 0))
    for sx in (-1, 1):
        box("arm", (sx * 0.27 - 0.03, -0.15, 0.66), (sx * 0.27 + 0.03, 0.15, 0.69), seat, 0.01)
        box("armpost", (sx * 0.27 - 0.015, -0.02, 0.5), (sx * 0.27 + 0.015, 0.02, 0.66), seat)


def b_leather():
    lt = mat("leather", (0.3, 0.14, 0.07), 0.35, coat=0.4)
    star_base((0, 0), mat("blk", (0.1, 0.1, 0.1), 0.3, 0.7), 0.34)
    box("seat", (-0.28, -0.28, 0.42), (0.28, 0.28, 0.52), lt, 0.04)
    box("back", (-0.28, 0.2, 0.52), (0.28, 0.28, 1.2), lt, 0.04, rot=(-0.06, 0, 0))
    for i in range(4):
        box("groove%d" % i, (-0.26, 0.19, 0.64 + i * 0.13), (0.26, 0.2, 0.65 + i * 0.13), mat("dark", (0.12, 0.05, 0.02), 0.6))
    for sx in (-1, 1):
        box("arm", (sx * 0.3 - 0.035, -0.2, 0.66), (sx * 0.3 + 0.035, 0.2, 0.71), lt, 0.02)
        box("armpost", (sx * 0.3 - 0.02, -0.02, 0.52), (sx * 0.3 + 0.02, 0.02, 0.66), mat("wd", (0.2, 0.1, 0.05), 0.4))


def b_racing():
    bl = mat("alc", (0.04, 0.04, 0.04), 0.8)
    red = mat("red", (0.8, 0.06, 0.08), 0.5)
    star_base((0, 0), mat("blk", (0.1, 0.1, 0.1), 0.3, 0.7), 0.34)
    box("seat", (-0.26, -0.26, 0.42), (0.26, 0.26, 0.5), bl, 0.03)
    box("back", (-0.26, 0.18, 0.5), (0.26, 0.26, 1.15), bl, 0.03, rot=(-0.1, 0, 0))
    for sx in (-1, 1):
        box("wing", (sx * 0.24 - 0.06, 0.1, 0.5), (sx * 0.24 + 0.06, 0.3, 1.0), red, 0.03, rot=(-0.1, 0, 0))
        box("bolster", (sx * 0.22 - 0.06, -0.26, 0.5), (sx * 0.22 + 0.06, 0.1, 0.6), red, 0.025)
        cyl("hole", (sx * 0.08, 0.14, 1.02), 0.02, 0.02, mat("hole", (0.01, 0.01, 0.01), 0.9), rot=(D90, 0, 0))
    box("stripe", (-0.04, 0.165, 0.5), (0.04, 0.17, 1.15), red, rot=(-0.1, 0, 0))


def _screen_mat(name="screen"):
    return mat(name, (0.05, 0.14, 0.3), 0.15, emit=1.6, ecol=(0.25, 0.5, 0.95))


def b_crt():
    beige = mat("beige", (0.8, 0.76, 0.62), 0.5)
    box("body", (-0.2, -0.05, 0.08), (0.2, 0.38, 0.4), beige, 0.015)
    box("bezel", (-0.22, -0.08, 0.05), (0.22, -0.04, 0.42), beige, 0.012)
    box("screen", (-0.18, -0.085, 0.09), (0.18, -0.08, 0.38), _screen_mat())
    box("foot", (-0.14, 0.05, 0.0), (0.14, 0.33, 0.08), beige, 0.01)
    text("logo", "TEWTRON", (0.0, -0.082, 0.065), 0.018, mat("lg", (0.3, 0.28, 0.2), 0.6), extrude=0.001)


def b_lcd():
    blk = BLACK()
    box("panel", (-0.28, -0.01, 0.12), (0.28, 0.01, 0.46), blk, 0.006)
    box("screen", (-0.265, -0.011, 0.135), (0.265, -0.0105, 0.445), _screen_mat())
    box("stand", (-0.02, 0.0, 0.02), (0.02, 0.03, 0.14), blk)
    cyl("foot", (0, 0.03, 0.01), 0.1, 0.02, blk)


def b_dual():
    blk = BLACK()
    for sx, yaw in ((-0.29, 0.12), (0.29, -0.12)):
        box("panel", (-0.27, -0.01, 0.12), (0.27, 0.01, 0.44), blk, 0.006, rot=(0, 0, yaw))
        bpy.context.object.location = (sx, 0.05, 0.28)
        box("screen", (-0.255, -0.011, 0.135), (0.255, -0.0105, 0.425), _screen_mat(), rot=(0, 0, yaw))
        bpy.context.object.location = (sx, 0.05, 0.28)
        box("stand", (-0.02, 0.0, 0.02), (0.02, 0.03, 0.14), blk)
        bpy.context.object.location = (sx, 0.065, 0.08)
        cyl("foot", (sx, 0.08, 0.01), 0.09, 0.02, blk)


def b_ultra():
    blk = BLACK()
    scr = _screen_mat()
    n = 14
    R = 1.5
    for i in range(n):
        a0 = -0.3 + 0.6 * i / n
        a1 = -0.3 + 0.6 * (i + 1) / n
        am = (a0 + a1) / 2
        w = R * (a1 - a0) * 1.02
        p = (math.sin(am) * R, R - math.cos(am) * R, 0.3)
        box("seg%d" % i, (-w / 2, -0.01, -0.17), (w / 2, 0.012, 0.17), blk, rot=(0, 0, -am))
        bpy.context.object.location = p
        box("scr%d" % i, (-w / 2, -0.0115, -0.155), (w / 2, -0.0105, 0.155), scr, rot=(0, 0, -am))
        bpy.context.object.location = p
    box("stand", (-0.03, 0.02, 0.02), (0.03, 0.05, 0.14), blk)
    box("foot", (-0.2, -0.05, 0.0), (0.2, 0.12, 0.02), blk, 0.006)


def b_neon():
    tube = mat("neon", (1.0, 0.3, 0.55), 0.3, emit=12, ecol=(1.0, 0.2, 0.5))
    text("chief", "CHIEF", (0, 0.0, 0.14), 0.26, tube, extrude=0.012)
    box("board", (-0.42, 0.02, 0.0), (0.42, 0.03, 0.3), mat("bd", (0.05, 0.05, 0.06), 0.8))
    box("wire", (0.36, 0.0, 0.0), (0.38, 0.012, 0.3), BLACK())


def b_aquarium():
    g = glass("tank", (0.92, 0.98, 1.0), 0.02)
    water = mat("water", (0.15, 0.45, 0.7), 0.05)
    water.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = 0.55
    water.surface_render_method = "BLENDED" if hasattr(water, "surface_render_method") else None
    box("base", (-0.3, -0.15, 0), (0.3, 0.15, 0.03), BLACK())
    box("water", (-0.29, -0.14, 0.03), (0.29, 0.14, 0.32), water)
    box("tank", (-0.3, -0.15, 0.03), (0.3, 0.15, 0.38), g)
    box("lid", (-0.31, -0.16, 0.38), (0.31, 0.16, 0.41), BLACK(), 0.006)
    gravel = noise_mat("gravel", (0.5, 0.4, 0.3), (0.3, 0.25, 0.2), 60, 0.9)
    box("gravel", (-0.29, -0.14, 0.03), (0.29, 0.14, 0.06), gravel)
    for i, (x, z, col) in enumerate(((-0.12, 0.18, (1.0, 0.45, 0.1)), (0.08, 0.25, (1.0, 0.85, 0.2)), (0.18, 0.12, (0.9, 0.25, 0.3)))):
        fm = mat("fish%d" % i, col, 0.4)
        sphere("fish%d" % i, (x, 0.0, z), 0.035, fm, scale=(1.3, 0.5, 0.8))
        box("fin%d" % i, (x + 0.04, -0.002, z - 0.02), (x + 0.07, 0.002, z + 0.02), fm)
    for x in (-0.2, 0.2):
        for k in range(5):
            a = k / 5 * math.tau
            cyl("weed", (x + math.cos(a) * 0.015, math.sin(a) * 0.015, 0.14), 0.006, 0.2, mat("weed", (0.1, 0.5, 0.2), 0.6), rot=(0.25 * math.cos(a), 0.25 * math.sin(a), 0))


# ---- collectibles

def bobble(skin, shirt, pants, hair=None, glasses=False, goatee=False, cap=None, extras=None, tan=0.0):
    """A bobblehead: little body, spring neck, big head. ~0.19 m tall on a disc base."""
    base = cyl("base", (0, 0, 0.008), 0.05, 0.016, mat("basem", (0.12, 0.12, 0.14), 0.3, coat=0.8))
    sk = SKIN(tan)
    for sx in (-1, 1):
        cyl("legm", (sx * 0.014, 0, 0.038), 0.012, 0.045, pants)
        cyl("shoe", (sx * 0.014, -0.006, 0.019), 0.013, 0.012, BLACK(), r2=0.011)
    cyl("torso", (0, 0, 0.09), 0.03, 0.06, shirt, r2=0.034)
    sphere("shoulders", (0, 0, 0.12), 0.034, shirt, scale=(1, 0.8, 0.5))
    for sx in (-1, 1):
        cyl("arm", (sx * 0.04, -0.005, 0.088), 0.01, 0.055, shirt, rot=(0.15, sx * 0.25, 0))
        sphere("hand", (sx * 0.047, -0.01, 0.06), 0.011, sk)
    spring("neck", (0, 0, 0.125), 0.012, 0.028, 4, 0.0025, CHROME())
    hz = 0.2
    sphere("head", (0, 0, hz), 0.046, sk)
    sphere("nose", (0, -0.045, hz - 0.004), 0.006, sk)
    for sx in (-1, 1):
        sphere("eye", (sx * 0.017, -0.041, hz + 0.008), 0.0055, mat("eyew", (0.95, 0.95, 0.95), 0.2))
        sphere("pupil", (sx * 0.017, -0.0455, hz + 0.008), 0.003, BLACK())
        sphere("ear", (sx * 0.046, 0, hz), 0.009, sk, scale=(0.5, 1, 1))
    cyl("smile", (0, -0.044, hz - 0.018), 0.012, 0.002, mat("lip", (0.6, 0.2, 0.2), 0.5), rot=(D90, 0, 0), verts=24)
    sphere("smilecover", (0, -0.044, hz - 0.012), 0.013, sk, scale=(1, 0.3, 0.6))
    if hair:
        sphere("hair", (0, 0.006, hz + 0.012), 0.047, hair, scale=(1, 1, 0.9))
        sphere("hairmask", (0, -0.004, hz - 0.012), 0.0462, sk, scale=(1, 1, 1))
    if cap:
        sphere("cap", (0, 0.004, hz + 0.014), 0.048, cap, scale=(1, 1, 0.8))
        box("peak", (-0.03, -0.085, hz + 0.018), (0.03, -0.035, hz + 0.024), cap, 0.004)
    if glasses:
        fr = mat("frame", (0.1, 0.1, 0.1), 0.3, 0.6)
        for sx in (-1, 1):
            torus("rim", (sx * 0.018, -0.045, hz + 0.008), 0.011, 0.0012, fr, rot=(D90, 0, 0))
        cyl("bridge", (0, -0.046, hz + 0.008), 0.001, 0.012, fr, rot=(0, D90, 0))
    if goatee:
        sphere("goatee", (0, -0.038, hz - 0.03), 0.013, mat("gt", (0.08, 0.06, 0.05), 0.8), scale=(1, 0.6, 0.9))
    if extras:
        extras(hz)
    return base


def b_bobble_marco():
    bobble(SKIN(0.3), mat("polo", (0.06, 0.08, 0.2), 0.7), BLACK(), hair=mat("hair", (0.12, 0.1, 0.09), 0.7), glasses=True, goatee=True, tan=0.25)
    box("collar", (-0.02, -0.03, 0.115), (0.02, -0.022, 0.13), mat("polo2", (0.06, 0.08, 0.2), 0.7))


def b_bobble_jeff():
    bobble(SKIN(0.0), mat("henley", (0.9, 0.35, 0.3), 0.7), mat("jeans", (0.2, 0.25, 0.4), 0.8), hair=mat("hair", (0.3, 0.18, 0.1), 0.7))


def b_bobble_surfer():
    def extras(hz):
        bd = mat("board", (0.98, 0.85, 0.2), 0.25, coat=0.8)
        sphere("board", (0.055, 0.03, 0.11), 0.03, bd, scale=(0.45, 0.4, 3.5), rot=(0.08, 0.0, 0))
        box("stripe", (0.04, -0.006, 0.02), (0.07, -0.004, 0.2), mat("st", (0.1, 0.5, 0.8), 0.3))
    bobble(SKIN(0.4), mat("tank", (0.95, 0.95, 0.95), 0.7), mat("shorts", (0.1, 0.6, 0.6), 0.7), hair=mat("hair", (0.9, 0.78, 0.4), 0.6), extras=extras, tan=0.4)


def b_bobble_lifeguard():
    def extras(hz):
        box("can", (-0.075, -0.02, 0.07), (-0.045, 0.0, 0.14), mat("can", (0.9, 0.1, 0.1), 0.4), 0.008)
        cyl("whistle", (0, -0.03, 0.1), 0.004, 0.012, CHROME(), rot=(0, D90, 0))
    bobble(SKIN(0.45), mat("tank", (0.9, 0.1, 0.1), 0.7), mat("shorts", (0.9, 0.1, 0.1), 0.7), cap=mat("cap", (0.85, 0.1, 0.1), 0.6), extras=extras, tan=0.45)
    text("lg", "LIFEGUARD", (0, -0.0325, 0.095), 0.007, mat("tx", (1, 1, 1), 0.6), extrude=0.0003)


def b_hula():
    wood = WALNUT()
    cyl("base", (0, 0, 0.008), 0.045, 0.016, wood)
    sk = SKIN(0.35)
    grass = mat("grass", (0.65, 0.55, 0.2), 0.8)
    for sx in (-1, 1):
        cyl("legm", (sx * 0.012, 0, 0.04), 0.011, 0.05, sk)
    for i in range(40):
        a = i / 40 * math.tau
        r = 0.028
        box("strip%d" % i, (-0.004, -0.0015, 0.0), (0.004, 0.0015, 0.06), grass, rot=(0.12 * math.sin(a * 3), 0, a))
        bpy.context.object.location = (math.cos(a) * r, math.sin(a) * r, 0.055)
    cyl("torso", (0, 0, 0.11), 0.024, 0.06, sk, r2=0.027)
    for sx in (-1, 1):
        cyl("arm", (sx * 0.05, 0, 0.13), 0.009, 0.06, sk, rot=(0, D90 - sx * 0.25, 0))
        sphere("hand", (sx * 0.078, 0, 0.138), 0.01, sk)
        sphere("coco", (sx * 0.013, -0.02, 0.12), 0.013, mat("coco", (0.35, 0.2, 0.1), 0.6))
    torus("lei", (0, 0, 0.14), 0.03, 0.009, mat("lei", (0.95, 0.3, 0.5), 0.6), rot=(0.2, 0, 0))
    hz = 0.185
    sphere("head", (0, 0, hz), 0.03, sk)
    sphere("hair", (0, 0.008, hz + 0.004), 0.032, mat("hair", (0.06, 0.04, 0.03), 0.6), scale=(1, 1, 1.1))
    sphere("hairmask", (0, -0.006, hz - 0.004), 0.0305, sk)
    sphere("flower", (0.028, -0.012, hz + 0.014), 0.012, mat("fl", (1.0, 0.2, 0.3), 0.5))
    sphere("flower2", (0.028, -0.012, hz + 0.014), 0.005, mat("fl2", (1.0, 0.9, 0.3), 0.5))
    for sx in (-1, 1):
        sphere("eye", (sx * 0.011, -0.027, hz + 0.004), 0.003, BLACK())
    cyl("smile", (0, -0.029, hz - 0.012), 0.007, 0.002, mat("lip", (0.7, 0.2, 0.25), 0.5), rot=(D90, 0, 0), verts=24)


def _photo(path, crop, out):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    if crop:
        im = im.crop(crop)
    im.thumbnail((512, 512), Image.LANCZOS)
    im.save(out, quality=92)
    return out


def b_photo_marco():
    os.makedirs(TMP, exist_ok=True)
    p = _photo(MARCO_REF, (560, 60, 800, 380), os.path.join(TMP, "marco_face.jpg"))
    w, h = 0.12, 0.16
    frame("f", (0, 0, 0.1), w, h, 0.016, WALNUT(), 0.014)
    plane("pic", (0, -0.0075, 0.1), w, h, img_mat("pic", p))
    box("strut", (-0.03, 0.008, 0.0), (0.03, 0.012, 0.11), mat("strut", (0.2, 0.1, 0.05), 0.6), rot=(-0.25, 0, 0))


def b_photo_lot():
    os.makedirs(TMP, exist_ok=True)
    p = _photo(LOT_BG, (150, 150, 1450, 900), os.path.join(TMP, "lot_photo.jpg"))
    w, h = 0.17, 0.098
    frame("f", (0, 0, 0.07), w, h, 0.016, BLACK(), 0.012)
    plane("pic", (0, -0.0075, 0.07), w, h, img_mat("pic", p))
    box("strut", (-0.03, 0.008, 0.0), (0.03, 0.012, 0.08), mat("strut", (0.15, 0.15, 0.15), 0.6), rot=(-0.25, 0, 0))


def b_first_dollar():
    from PIL import Image, ImageDraw
    os.makedirs(TMP, exist_ok=True)
    p = os.path.join(TMP, "dollar.png")
    im = Image.new("RGB", (512, 220), (214, 222, 196))
    d = ImageDraw.Draw(im)
    d.rectangle((10, 10, 501, 209), outline=(70, 95, 60), width=4)
    d.rectangle((22, 22, 489, 197), outline=(70, 95, 60), width=2)
    d.ellipse((196, 40, 316, 180), fill=(190, 200, 170), outline=(70, 95, 60), width=3)
    for x, y in ((40, 36), (430, 36), (40, 150), (430, 150)):
        d.text((x, y), "1", fill=(40, 60, 35))
    d.text((200, 190), "ONE DOLLAR", fill=(40, 60, 35))
    im.save(p)
    w, h = 0.19, 0.11
    frame("f", (0, 0, 0.075), w, h, 0.014, GOLD(), 0.012)
    plane("mat", (0, -0.0065, 0.075), w, h, mat("matte", (0.1, 0.12, 0.2), 0.8))
    plane("bill", (0, -0.0068, 0.08), 0.13, 0.056, img_mat("bill", p))
    text("cap", "FIRST DOLLAR", (0, -0.0069, 0.038), 0.011, GOLD(), extrude=0.0005)
    box("strut", (-0.03, 0.007, 0.0), (0.03, 0.011, 0.085), BLACK(), rot=(-0.25, 0, 0))


def b_globe():
    br = mat("brass", (0.8, 0.6, 0.28), 0.3, 1.0)
    cyl("base", (0, 0, 0.006), 0.05, 0.012, br)
    cyl("post", (0, 0, 0.04), 0.006, 0.06, br)
    sphere("globe", (0, 0, 0.14), 0.07, noise_mat("earth", (0.1, 0.35, 0.75), (0.25, 0.55, 0.2), 2.2, 0.35, 3.0))
    torus("meridian", (0, 0, 0.14), 0.076, 0.004, br, rot=(0, 0.4, 0.3))
    sphere("cap", (0, 0, 0.21), 0.008, br)


def b_lamp():
    br = mat("brass", (0.8, 0.6, 0.28), 0.25, 1.0)
    gr = mat("green", (0.05, 0.4, 0.2), 0.1, emit=0.6, ecol=(0.2, 0.9, 0.4))
    box("base", (-0.09, -0.05, 0), (0.09, 0.05, 0.015), br, 0.006)
    cyl("post", (0, 0.02, 0.1), 0.007, 0.18, br)
    cyl("arm", (0, 0.01, 0.19), 0.006, 0.05, br, rot=(D90, 0, 0))
    # half-cylinder shade: a cylinder cut by a box is fiddly; use a flattened cylinder lying along x
    cyl("shade", (0, -0.01, 0.2), 0.045, 0.22, gr, rot=(0, D90, 0))
    box("shadecut", (-0.12, -0.07, 0.14), (0.12, 0.05, 0.2), mat("inner", (0.95, 0.9, 0.6), 0.5, emit=3.0, ecol=(1.0, 0.85, 0.5)))
    bpy.context.object.scale = (1, 1, 0.01)
    bpy.context.object.location = (0, -0.01, 0.2)
    cyl("knob", (0.0, -0.03, 0.1), 0.006, 0.02, br, rot=(D90, 0, 0))


def b_polesign():
    pole = mat("pole", (0.75, 0.75, 0.78), 0.3, 1.0)
    red = mat("red", (0.85, 0.08, 0.1), 0.35)
    white = mat("white", (0.95, 0.95, 0.95), 0.4, emit=0.4, ecol=(1, 1, 1))
    cyl("base", (0, 0, 0.006), 0.05, 0.012, BLACK())
    cyl("pole", (0, 0, 0.1), 0.008, 0.19, pole)
    box("sign", (-0.1, -0.012, 0.19), (0.1, 0.012, 0.3), red, 0.006)
    box("face", (-0.095, -0.0125, 0.195), (0.095, -0.012, 0.295), white)
    text("t1", "CHIEF", (0, -0.0135, 0.262), 0.038, red, extrude=0.0005)
    text("t2", "AUTO", (0, -0.0135, 0.225), 0.038, mat("navy", (0.05, 0.1, 0.3), 0.4), extrude=0.0005)
    box("face2", (-0.095, 0.012, 0.195), (0.095, 0.0125, 0.295), white)


def b_modelcar():
    box("plinth", (-0.17, -0.09, 0), (0.17, 0.09, 0.025), BLACK(), 0.005)
    box("plaque", (-0.05, -0.0905, 0.006), (0.05, -0.089, 0.02), GOLD())
    import_car("ferrano_488.glb", 1 / 18, (0, 0, 0.025), yaw=0.35)
    g = glass("case", (0.95, 0.98, 1.0), 0.02)
    box("case", (-0.165, -0.085, 0.025), (0.165, 0.085, 0.13), g)


def b_trophy():
    g = GOLD()
    box("base", (-0.07, -0.07, 0), (0.07, 0.07, 0.03), mat("marble", (0.08, 0.08, 0.1), 0.2, coat=1.0), 0.005)
    box("plaque", (-0.05, -0.0705, 0.007), (0.05, -0.069, 0.023), g)
    cyl("stem", (0, 0, 0.055), 0.016, 0.05, g, r2=0.02)
    cyl("cup", (0, 0, 0.13), 0.028, 0.1, g, r2=0.05)
    sphere("lip", (0, 0, 0.18), 0.05, g, scale=(1, 1, 0.12))
    for sx in (-1, 1):
        torus("handle", (sx * 0.055, 0, 0.14), 0.025, 0.004, g, rot=(D90, 0, 0))
    sphere("star", (0, 0, 0.2), 0.012, g)


def b_mug():
    wh = mat("white", (0.95, 0.95, 0.95), 0.2, coat=0.8)
    cyl("mug", (0, 0, 0.045), 0.04, 0.09, wh)
    cyl("inner", (0, 0, 0.088), 0.034, 0.012, mat("coffee", (0.2, 0.1, 0.05), 0.2))
    torus("handle", (0.047, 0, 0.045), 0.022, 0.006, wh, rot=(D90, 0, 0))
    text("one", "#1", (0, -0.041, 0.055), 0.03, mat("red", (0.8, 0.1, 0.1), 0.5), extrude=0.0005)
    text("closer", "CLOSER", (0, -0.041, 0.028), 0.014, mat("red2", (0.8, 0.1, 0.1), 0.5), extrude=0.0005)


def b_plant():
    tc = mat("terracotta", (0.7, 0.35, 0.2), 0.7)
    cyl("pot", (0, 0, 0.06), 0.055, 0.12, tc, r2=0.07)
    cyl("rim", (0, 0, 0.125), 0.075, 0.015, tc)
    cyl("soil", (0, 0, 0.126), 0.06, 0.01, mat("soil", (0.15, 0.1, 0.06), 0.9))
    cyl("trunk", (0, 0, 0.2), 0.012, 0.16, mat("trunk", (0.45, 0.3, 0.15), 0.8), r2=0.009)
    leaf = mat("leaf", (0.12, 0.5, 0.18), 0.5)
    for i in range(9):
        a = i / 9 * math.tau + 0.3
        tilt = 0.9 + 0.25 * (i % 3)
        sphere("frond%d" % i, (math.cos(a) * 0.09, math.sin(a) * 0.09, 0.3 - 0.03 * (i % 3)), 0.11, leaf, scale=(1, 0.25, 0.08), rot=(0, tilt, a))


def b_cradle():
    ch = CHROME()
    box("base", (-0.08, -0.05, 0), (0.08, 0.05, 0.012), BLACK(), 0.004)
    for sy in (-1, 1):
        for sx in (-1, 1):
            cyl("post", (sx * 0.07, sy * 0.04, 0.08), 0.003, 0.14, ch)
        cyl("rail", (0, sy * 0.04, 0.15), 0.003, 0.146, ch, rot=(0, D90, 0))
    for i in range(5):
        x = -0.044 + i * 0.022
        z = 0.045
        if i == 0:
            x, z = -0.085, 0.09
        for sy in (-1, 1):
            cyl("str", (x, sy * 0.02, (z + 0.15) / 2 + 0.005), 0.0006, 0.1, mat("string", (0.8, 0.8, 0.8), 0.6), rot=(sy * -0.2 if i else sy * -0.2, 0.0 if i else 0.4, 0))
        sphere("ball%d" % i, (x, 0, z), 0.011, ch)


def b_magazines():
    random.seed(7)
    cols = [(0.9, 0.1, 0.1), (0.1, 0.3, 0.8), (0.95, 0.75, 0.1), (0.1, 0.1, 0.12), (0.9, 0.9, 0.9), (0.1, 0.6, 0.3)]
    z = 0.0
    for i in range(6):
        c = mat("cover%d" % i, cols[i], 0.3, coat=0.8)
        box("mag%d" % i, (-0.105, -0.14, 0), (0.105, 0.14, 0.006), c, rot=(0, 0, random.uniform(-0.25, 0.25)))
        bpy.context.object.location = (random.uniform(-0.01, 0.01), random.uniform(-0.01, 0.01), z + 0.003)
        z += 0.006
    text("title", "AUTO", (-0.0, -0.0, z + 0.0005), 0.05, mat("white", (1, 1, 1), 0.4), rot=(0, 0, 0.1), extrude=0.0003)
    text("title2", "WEEKLY", (0.0, -0.045, z + 0.0005), 0.02, mat("white2", (1, 1, 1), 0.4), rot=(0, 0, 0.1), extrude=0.0003)
    import_car("porsha_911.glb", 1 / 48, (0.0, 0.055, z + 0.0005), yaw=-0.5)


# ---- ShowroomPro

def b_coffee():
    ch = CHROME()
    blk = mat("black", (0.05, 0.05, 0.06), 0.25, coat=0.8)
    box("body", (-0.3, -0.2, 0.0), (0.3, 0.2, 0.42), blk, 0.015)
    box("top", (-0.32, -0.22, 0.42), (0.32, 0.22, 0.46), ch, 0.01)
    box("front", (-0.28, -0.205, 0.2), (0.28, -0.2, 0.4), ch)
    for x in (-0.15, 0.12):
        box("group", (x - 0.05, -0.28, 0.17), (x + 0.05, -0.2, 0.24), ch, 0.008)
        cyl("pf", (x, -0.27, 0.16), 0.03, 0.02, ch)
        cyl("pfh", (x, -0.34, 0.16), 0.008, 0.12, blk, rot=(D90, 0, 0))
        cyl("cup", (x, -0.28, 0.075), 0.028, 0.06, mat("cup", (0.95, 0.95, 0.95), 0.3))
    box("tray", (-0.26, -0.33, 0.04), (0.26, -0.2, 0.05), ch)
    cyl("wand", (0.26, -0.26, 0.08), 0.006, 0.18, ch, rot=(0.3, 0, 0))
    cyl("dial", (0.0, -0.205, 0.33), 0.03, 0.02, ch, rot=(D90, 0, 0))
    box("light", (-0.2, -0.206, 0.35), (-0.08, -0.2, 0.36), mat("led", (0.3, 0.9, 0.4), 0.3, emit=4))
    text("esp", "ESPRESSO", (0, -0.21, 0.29), 0.03, mat("gold", (0.9, 0.7, 0.3), 0.3, 1.0), extrude=0.001)


def b_lights():
    blk = BLACK()
    box("track", (-0.6, -0.03, 0.56), (0.6, 0.03, 0.6), blk, 0.006)
    for i, x in enumerate((-0.4, 0, 0.4)):
        cyl("stem", (x, 0, 0.5), 0.012, 0.12, blk)
        cyl("can", (x, 0, 0.38), 0.045, 0.14, blk, rot=(0.3 * (i - 1), 0, 0), r2=0.05)
        cyl("lens", (x, 0.0, 0.31), 0.047, 0.01, mat("lens", (1, 0.95, 0.8), 0.1, emit=12, ecol=(1, 0.92, 0.75)), rot=(0.3 * (i - 1), 0, 0))
    box("plate", (-0.6, -0.08, 0.6), (0.6, 0.08, 0.62), mat("ceil", (0.9, 0.9, 0.9), 0.6))
    for i, x in enumerate((-0.4, 0, 0.4)):
        cyl("cone", (x, 0.3 * (i - 1) * 0.4, 0.15), 0.02, 0.3, mat("beam", (1, 0.95, 0.8), 0.5, emit=0.8), rot=(0.3 * (i - 1), 0, 0), r2=0.14)
        bpy.context.object.data.materials[0].node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = 0.12


def b_lounge():
    lt = mat("leather", (0.32, 0.15, 0.07), 0.35, coat=0.5)
    dk = mat("leatherd", (0.22, 0.1, 0.05), 0.4)
    box("seatbase", (-0.9, -0.4, 0.15), (0.9, 0.4, 0.4), lt, 0.04)
    for i in range(3):
        box("cushion%d" % i, (-0.88 + i * 0.6, -0.42, 0.4), (-0.3 + i * 0.6, 0.3, 0.52), lt, 0.05)
        box("back%d" % i, (-0.88 + i * 0.6, 0.3, 0.4), (-0.3 + i * 0.6, 0.45, 0.85), lt, 0.05)
    for sx in (-1, 1):
        box("arm", (sx * 0.98 - 0.08, -0.4, 0.15), (sx * 0.98 + 0.08, 0.45, 0.6), dk, 0.04)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl("foot", (sx * 0.85, sy * 0.35, 0.075), 0.03, 0.15, BLACK())
    box("table", (-0.3, -0.95, 0.4), (0.3, -0.55, 0.43), WALNUT(), 0.008)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl("tleg", (sx * 0.25, -0.75 + sy * 0.15, 0.2), 0.015, 0.4, BLACK())
    cyl("vase", (0, -0.75, 0.5), 0.04, 0.14, glass("vase"))


def b_turntable():
    g = GOLD()
    cyl("disc", (0, 0, 0.06), 1.4, 0.12, g)
    cyl("ring", (0, 0, 0.125), 1.3, 0.01, mat("ring", (1, 0.9, 0.6), 0.2, emit=3))
    cyl("top", (0, 0, 0.13), 1.25, 0.02, mat("gloss", (0.1, 0.1, 0.12), 0.08, coat=1.0))
    import_car("lamborgo_aventa.glb", 0.45, (0, 0, 0.14), yaw=0.5)


def _lot(n, size):
    asphalt = mat("asphalt", (0.16, 0.16, 0.17), 0.9)
    box("slab", (-size, -0.3, 0), (size, 0.3, 0.02), asphalt, 0.004)
    paint = mat("paint", (0.95, 0.95, 0.9), 0.6)
    cars = ["hondo_civix.glb", "mazdo_miota.glb", "chevro_tahoma.glb", "toyoda_camri.glb", "forde_mustank.glb", "subaro_outbuck.glb"]
    for i in range(n + 1):
        x = -size + 0.06 + i * (2 * size - 0.12) / n
        box("line%d" % i, (x - 0.004, -0.2, 0.021), (x + 0.004, 0.2, 0.022), paint)
    for i in range(n):
        x = -size + 0.06 + (i + 0.5) * (2 * size - 0.12) / n
        import_car(cars[i % len(cars)], 1 / 30, (x, 0.0, 0.022), yaw=D90 + random.uniform(-0.1, 0.1))
    pole = mat("pole", (0.75, 0.75, 0.78), 0.3, 1.0)
    cyl("pole", (-size + 0.06, 0.27, 0.12), 0.006, 0.2, pole)
    box("sign", (-size - 0.0, 0.26, 0.22), (-size + 0.12, 0.28, 0.28), mat("red", (0.85, 0.08, 0.1), 0.35), 0.004)
    text("t", "CHIEF", (-size + 0.06, 0.258, 0.25), 0.03, mat("white", (1, 1, 1), 0.4, emit=0.4), extrude=0.0005)
    cyl("palm", (size - 0.05, 0.25, 0.14), 0.008, 0.24, mat("trunk", (0.5, 0.35, 0.2), 0.8), r2=0.005)
    for k in range(6):
        a = k / 6 * math.tau
        sphere("leaf", (size - 0.05 + math.cos(a) * 0.05, 0.25 + math.sin(a) * 0.05, 0.25), 0.07, mat("leaf", (0.15, 0.5, 0.2), 0.5), scale=(1, 0.3, 0.08), rot=(0, 1.0, a))


def b_expand1():
    random.seed(1)
    _lot(2, 0.5)


def b_expand2():
    random.seed(2)
    _lot(4, 0.75)


# ---- AdSpace

def b_flyers():
    yel = mat("paper", (1.0, 0.85, 0.15), 0.7)
    for i in range(12):
        box("sheet%d" % i, (-0.105, -0.14, 0), (0.105, 0.14, 0.0015), yel, rot=(0, 0, random.uniform(-0.05, 0.05)))
        bpy.context.object.location = (0, 0, i * 0.0015)
    top = 0.018
    box("front", (-0.105, -0.0012, 0.0), (0.105, 0.0012, 0.28), mat("paper2", (1.0, 0.3, 0.2), 0.7), rot=(0.2, 0, 0))
    bpy.context.object.location = (0.02, 0.12, 0.14)
    text("sale", "SALE!", (0.02, 0.09, 0.23), 0.06, mat("white", (1, 1, 1), 0.5), rot=(D90 + 0.2, 0, 0), extrude=0.0005)
    text("sale2", "CHIEF AUTO", (0.02, 0.1, 0.17), 0.025, mat("navy", (0.05, 0.1, 0.3), 0.5), rot=(D90 + 0.2, 0, 0), extrude=0.0005)
    text("sale3", "0% APR", (0.0, -0.01, top + 0.001), 0.04, mat("navy2", (0.05, 0.1, 0.3), 0.5), rot=(0, 0, 0), extrude=0.0003)
    box("wiper", (-0.16, -0.02, 0.0), (0.16, 0.0, 0.012), BLACK(), rot=(0, 0, -0.35))
    bpy.context.object.location = (0.1, -0.1, 0.006)


def b_insta():
    blk = mat("phone", (0.05, 0.05, 0.06), 0.2, 0.4, coat=1.0)
    box("body", (-0.038, -0.004, 0), (0.038, 0.004, 0.16), blk, 0.005, rot=(0.15, 0, 0))
    bpy.context.object.location = (0, 0.02, 0.082)
    scr = mat("scr", (0.9, 0.3, 0.5), 0.1, emit=1.8, ecol=(0.95, 0.35, 0.45))
    box("screen", (-0.035, -0.0045, 0.004), (0.035, -0.004, 0.156), scr, rot=(0.15, 0, 0))
    bpy.context.object.location = (0, 0.02, 0.082)
    wh = mat("white", (1, 1, 1), 0.3, emit=2.0)
    torus("ring", (0, -0.0047, 0.11), 0.016, 0.0022, wh, rot=(D90 + 0.15, 0, 0))
    bpy.context.object.location = (0, 0.02 - 0.0047 - 0.03 * 0.15, 0.082 + 0.03)
    sphere("dot", (0.012, 0.0, 0.0), 0.0025, wh)
    bpy.context.object.location = (0.011, 0.02 - 0.0047 - 0.041 * 0.15, 0.082 + 0.041)
    text("ad", "SPONSORED", (0, 0.02 - 0.005 + 0.04 * 0.15, 0.082 - 0.04), 0.009, wh, rot=(D90 + 0.15, 0, 0), extrude=0.0003)
    box("stand", (-0.03, 0.02, 0), (0.03, 0.05, 0.01), blk, 0.003)


def b_radio():
    ch = CHROME()
    blk = BLACK()
    cyl("base", (0, 0, 0.01), 0.07, 0.02, blk)
    cyl("stem", (0, 0, 0.11), 0.008, 0.2, ch)
    sphere("mic", (0, 0, 0.26), 0.045, mat("grille", (0.6, 0.6, 0.62), 0.5, 0.9), scale=(1, 1, 1.3))
    torus("ring", (0, 0, 0.26), 0.052, 0.006, ch, rot=(0, D90, 0))
    cyl("body", (0, 0, 0.2), 0.03, 0.06, ch, r2=0.02)
    box("onair", (-0.08, 0.03, 0.26), (0.08, 0.045, 0.32), blk, 0.004)
    bpy.context.object.location = (0.12, 0.04, 0.3)
    text("on", "ON AIR", (0.12, 0.0315 + 0.0, 0.3), 0.03, mat("red", (1, 0.15, 0.1), 0.3, emit=8, ecol=(1, 0.15, 0.1)), extrude=0.0005)
    bpy.context.object.location = (0.12, 0.0225, 0.3)
    cyl("post", (0.12, 0.04, 0.13), 0.006, 0.26, blk)


def b_billboard():
    pole = mat("pole", (0.4, 0.4, 0.42), 0.4, 0.7)
    for sx in (-0.3, 0.3):
        cyl("post", (sx, 0.02, 0.2), 0.015, 0.4, pole)
    box("board", (-0.55, 0.0, 0.4), (0.55, 0.03, 0.9), BLACK(), 0.006)
    box("face", (-0.53, -0.001, 0.42), (0.53, 0.0, 0.88), mat("face", (0.96, 0.96, 0.96), 0.5, emit=0.3, ecol=(1, 1, 1)))
    box("band", (-0.53, -0.0015, 0.42), (0.53, 0.0, 0.56), mat("red", (0.85, 0.08, 0.1), 0.4))
    text("t1", "CHIEF AUTO", (0, -0.002, 0.74), 0.11, mat("navy", (0.05, 0.1, 0.3), 0.5), extrude=0.001)
    text("t2", "Coast Highway · Tewport Beach", (0, -0.002, 0.63), 0.045, mat("grey", (0.3, 0.3, 0.32), 0.5), extrude=0.0005)
    text("t3", "WE BUY. WE SELL. WE CLOSE.", (0, -0.0025, 0.49), 0.05, mat("white", (1, 1, 1), 0.5), extrude=0.0005)
    import_car("porsha_911.glb", 0.09, (-0.4, -0.05, 0.42), yaw=0.2)
    for sx in (-0.45, 0.45):
        cyl("lamp", (sx, -0.08, 0.92), 0.012, 0.03, pole, rot=(D90 * 0.5, 0, 0))


ITEMS = {
    "folding": b_folding, "oak": b_oak, "glass": b_glass, "carbon": b_carbon,
    "plastic": b_plastic, "office": b_office, "leather": b_leather, "racing": b_racing,
    "crt": b_crt, "lcd": b_lcd, "dual": b_dual, "ultra": b_ultra,
    "neon": b_neon, "aquarium": b_aquarium,
    "bobble_marco": b_bobble_marco, "bobble_jeff": b_bobble_jeff, "bobble_surfer": b_bobble_surfer,
    "bobble_lifeguard": b_bobble_lifeguard, "hula": b_hula,
    "photo_marco": b_photo_marco, "photo_lot": b_photo_lot, "first_dollar": b_first_dollar,
    "globe": b_globe, "lamp": b_lamp, "polesign": b_polesign, "modelcar": b_modelcar, "trophy": b_trophy,
    "mug": b_mug, "plant": b_plant, "cradle": b_cradle, "magazines": b_magazines,
    "coffee": b_coffee, "lights": b_lights, "lounge": b_lounge, "turntable": b_turntable,
    "expand1": b_expand1, "expand2": b_expand2,
    "flyers": b_flyers, "insta": b_insta, "radio": b_radio, "billboard": b_billboard,
}


# ------------------------------------------------------------------ studio, camera, render

def studio():
    """Same warm key / cool rim / soft fill as tools/people3d.py, scaled to the item (see frame_and_light)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    sc.render.film_transparent = True
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = -0.2
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.5, 0.45, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.5
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -0.0005))
    ground = bpy.context.object
    ground.name = "ground"
    ground.is_shadow_catcher = True
    ground.data.materials.append(mat("groundm", (0.8, 0.8, 0.8), 0.9))
    cam = bpy.data.cameras.new("cam")
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return co


def frame_and_light(cam):
    mn = Vector((1e9, 1e9, 1e9))
    mx = -mn
    for o in bpy.context.scene.objects:
        if o.name == "ground" or o.type not in ("MESH", "CURVE", "FONT"):
            continue
        for c in o.bound_box:
            p = o.matrix_world @ Vector(c)
            mn = Vector(map(min, mn, p))
            mx = Vector(map(max, mx, p))
    mn.z = min(mn.z, 0.0)
    centre = (mn + mx) / 2
    dims = mx - mn
    size = max(dims)
    radius = dims.length / 2
    # three-quarter view from the front-right, a little above
    d = Vector((0.8, -1.0, 0.62)).normalized()
    lens = 55.0
    fov = 2 * math.atan(36 / (2 * lens))
    dist = radius / math.sin(fov / 2) * 1.08
    cam.location = centre + d * dist
    cam.data.lens = lens
    cam.data.clip_start = dist * 0.01
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    s = max(size / 1.8, 0.2)
    sc = bpy.context.scene
    for loc, energy, lsize, col in (((2.2, -3.0, 2.8), 700, 4.5, (1.0, 0.86, 0.72)),
                                    ((-2.5, 2.0, 2.6), 450, 1.5, (0.65, 0.78, 1.0)),
                                    ((-2.5, -2.5, 1.5), 200, 4.0, (1, 0.97, 0.95))):
        ld = bpy.data.lights.new("l", "AREA")
        ld.energy = energy * s * s
        ld.size = lsize * s
        ld.color = col
        lo = bpy.data.objects.new("l", ld)
        lo.location = centre + Vector(loc) * s - Vector((0, 0, 1.2 * s)) + Vector((0, 0, dims.z * 0.3))
        lo.rotation_euler = (centre - lo.location).to_track_quat("-Z", "Y").to_euler()
        sc.collection.objects.link(lo)


def finish(src, dst):
    """Crop to what was drawn and frame it: biggest side 220 px, bottom of the shadow at y=244 of 256."""
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    a = im.getchannel("A").point(lambda v: 255 if v > 12 else 0)
    bb = a.getbbox()
    if bb is None:
        print("EMPTY", src)
        return
    im = im.crop(bb)
    w, h = im.size
    k = 220 / max(w, h)
    im = im.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
    out = Image.new("RGBA", (FINAL, FINAL), (0, 0, 0, 0))
    out.paste(im, ((FINAL - im.width) // 2, 244 - im.height), im)
    out.save(dst, optimize=True)


def render_item(name):
    cam = studio()
    ITEMS[name]()
    frame_and_light(cam)
    os.makedirs(TMP, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    raw = os.path.join(TMP, name + "_raw.png")
    bpy.context.scene.render.filepath = raw
    bpy.ops.render.render(write_still=True)
    finish(raw, os.path.join(OUT, name + ".png"))
    print("rendered", name, flush=True)


if __name__ == "__main__":
    names = sys.argv[1:] or list(ITEMS)
    for n in names:
        render_item(n)
