"""The "Look at desk" view's furniture, rendered from the seat (scripts/scene_art.gd desk mode draws these):

    assets/deskview/desk_<id>.png   the desk top seen from the chair, full width, transparent above the back edge
    assets/deskview/chair_<id>.png  the chair, a three-quarter back view cropped tight (drawn in the corner)
    assets/deskview/deskview.json   where the desk's back edge lands (fraction of the image height)

The furniture is the same procedural geometry as the shop renders (tools/props3d.py b_<id>), the desk stretched
wide so its top fills the view.  Usage: /root/bpyenv/bin/python tools/deskview3d.py [id ...]
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import props3d as P  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

OUT = os.path.join(P.ROOT, "assets", "deskview")
DESKS = ("folding", "oak", "glass", "carbon")
MONITORS = ("crt", "lcd", "dual", "ultra")
EXTRAS = ("keyboard", "shelfunit")             # desk view: keyboard, freestanding shelf for the shelf slot
HOME = ("tv", "couch", "homepc")               # apartment furniture (assets/home/<id>.png)
CHAIRS = ("plastic", "office", "leather", "racing")
W, H = 2560, 1440
EYE, LOOK, LENS = (0.0, -0.78, 1.2), (0.0, 0.3, 0.7), 22.0


def scene(samples=int(os.environ.get("SAMPLES", 64))):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    sc.cycles.denoising_prefilter = "ACCURATE"
    sc.render.film_transparent = True
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = -1.6
    sc.render.film_transparent = True
    sc.cycles.film_transparent_glass = True   # the room shows through the glass desk
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.62, 0.55, 0.48, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    # office light: a warm ceiling panel overhead-behind and a cool window to the left
    for loc, rot, e, size, col in (((0.4, -0.6, 2.8), (0.2, 0, 0), 260, 2.5, (1.0, 0.88, 0.74)),
                                   ((-2.8, 0.6, 1.6), (0, -1.3, 0), 160, 2.0, (0.75, 0.85, 1.0))):
        ld = bpy.data.lights.new("l", "AREA")
        ld.energy, ld.size, ld.color = e, size, col
        lo = bpy.data.objects.new("l", ld)
        lo.location, lo.rotation_euler = loc, rot
        sc.collection.objects.link(lo)
    cam = bpy.data.cameras.new("cam")
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return sc, co


def render_desk(name):
    sc, cam = scene()
    sc.render.resolution_x, sc.render.resolution_y = W, H
    getattr(P, "b_" + name)()
    for o in list(sc.objects):
        if o.type == "MESH":
            o.scale.x *= 2.8      # the top runs past both sides of the view
            o.location.x *= 2.8
    world_grain()
    if name == "oak":
        sc.objects["top"].data.materials[0] = oak_grain()
    if name == "glass":
        # tinted glass with alpha (so the room render shows through it) and a clear coat for the reflections
        for o in sc.objects:
            if o.type == "MESH" and o.name.startswith(("top", "shelf")):
                g = bpy.data.materials.new("desk_glass")
                g.use_nodes = True
                b = g.node_tree.nodes["Principled BSDF"]
                b.inputs["Base Color"].default_value = (0.55, 0.75, 0.78, 1)
                b.inputs["Roughness"].default_value = 0.04
                b.inputs["Alpha"].default_value = 0.22
                b.inputs["Coat Weight"].default_value = 1.0
                o.data.materials[0] = g
    cam.location = EYE
    cam.data.lens = LENS
    cam.rotation_euler = (Vector(LOOK) - Vector(EYE)).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(OUT, "desk_%s.png" % name)
    bpy.ops.render.render(write_still=True)
    from bpy_extras.object_utils import world_to_camera_view
    bpy.context.view_layer.update()
    top = {"folding": 0.75, "oak": 0.76, "glass": 0.755, "carbon": 0.76}[name]
    back = {"folding": 0.35, "oak": 0.4, "glass": 0.42, "carbon": 0.42}[name]
    return round(1.0 - world_to_camera_view(sc, cam, Vector((0, back, top))).y, 4)


def oak_grain():
    """Long walnut grain running across the desk (wave bands warped by noise), satin finish."""
    m = bpy.data.materials.new("oak_top")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    g = nt.nodes.new("ShaderNodeNewGeometry")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.08, 3.0, 1.0)
    nt.links.new(g.outputs["Position"], mp.inputs["Vector"])
    w = nt.nodes.new("ShaderNodeTexNoise")       # streaky grain: noise squashed along the desk
    w.inputs["Scale"].default_value = 3.0
    w.inputs["Detail"].default_value = 12.0
    w.inputs["Roughness"].default_value = 0.62
    w.inputs["Distortion"].default_value = 0.4
    nt.links.new(mp.outputs["Vector"], w.inputs["Vector"])
    r = nt.nodes.new("ShaderNodeValToRGB")
    r.color_ramp.elements[0].color = (0.15, 0.07, 0.028, 1)
    r.color_ramp.elements[0].position = 0.35
    r.color_ramp.elements[1].color = (0.38, 0.21, 0.095, 1)
    r.color_ramp.elements[1].position = 0.65
    nt.links.new(w.outputs["Fac"], r.inputs["Fac"])
    nt.links.new(r.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.32
    b.inputs["Coat Weight"].default_value = 0.3
    return m


def world_grain():
    """Noise textures follow world position, so stretching the desk does not stretch its grain."""
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        nt = m.node_tree
        for n in list(nt.nodes):
            if n.type == "TEX_NOISE" and not n.inputs["Vector"].is_linked:
                g = nt.nodes.new("ShaderNodeNewGeometry")
                nt.links.new(g.outputs["Position"], n.inputs["Vector"])


def render_chair(name):
    sc, cam = scene()
    sc.render.resolution_x, sc.render.resolution_y = 1200, 1200
    getattr(P, "b_" + name)()
    for o in list(sc.objects):
        if o.type == "MESH" and o.parent is None:
            o.rotation_euler.z += math.radians(200)   # its back to us, turned a little toward the desk
            o.location = _rot(o.location, math.radians(200))
    cam.location = (0.55, -1.9, 1.35)
    cam.data.lens = 50
    cam.rotation_euler = (Vector((0, 0, 0.62)) - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()
    raw = os.path.join(P.TMP, "chair_%s_raw.png" % name)
    os.makedirs(P.TMP, exist_ok=True)
    sc.render.filepath = raw
    bpy.ops.render.render(write_still=True)
    from PIL import Image
    im = Image.open(raw).convert("RGBA")
    bb = im.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    im.crop(bb).save(os.path.join(OUT, "chair_%s.png" % name), optimize=True)


def _rot(v, a):
    return Vector((v.x * math.cos(a) - v.y * math.sin(a), v.x * math.sin(a) + v.y * math.cos(a), v.z))


def render_cut(build, look, d, lens, out, pts=(), res=1000, dist=3.0):
    """Renders build() on transparent, camera along direction d from look; crops to the drawn pixels and
    returns where each 3D point in pts lands in the cropped image, as (x, y) fractions."""
    from bpy_extras.object_utils import world_to_camera_view
    from PIL import Image
    sc, cam = scene()
    sc.render.resolution_x = sc.render.resolution_y = res
    build()
    look, d = Vector(look), Vector(d).normalized()
    cam.data.lens = lens
    cam.location = look + d * dist
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    raw = os.path.join(P.TMP, os.path.basename(out) + "_raw.png")
    os.makedirs(P.TMP, exist_ok=True)
    sc.render.filepath = raw
    bpy.ops.render.render(write_still=True)
    im = Image.open(raw).convert("RGBA")
    bb = im.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    im = im.crop(bb)
    im.save(out, optimize=True)
    fr = []
    for q in pts:
        v = world_to_camera_view(sc, cam, Vector(q))
        px, py = v.x * res, (1 - v.y) * res
        fr.append([round((px - bb[0]) / im.width, 4), round((py - bb[1]) / im.height, 4)])
    return fr


def _screen_box(name):
    """Corners of a monitor's (main) screen in world space, for the screen rect in the cut-out."""
    lo = {"crt": ((-0.18, -0.085, 0.09), (0.18, -0.085, 0.38)), "lcd": ((-0.265, -0.011, 0.135), (0.265, -0.011, 0.445)),
          "dual": ((-0.29 - 0.25, 0.02, 0.145), (-0.29 + 0.25, 0.02, 0.415)), "ultra": ((-0.43, -0.03, 0.145), (0.43, -0.03, 0.455))}[name]
    return [(lo[0][0], lo[0][1], lo[1][2]), (lo[1][0], lo[1][1], lo[0][2])]


def render_monitor(name):
    """The monitor seen from the chair, nearly straight on (long lens so the screen stays rectangular)."""
    out = os.path.join(OUT, "monitor_%s.png" % name)
    pts = _screen_box(name)
    if name == "dual":
        pts += [(0.04, 0.02, 0.415), (0.54, 0.02, 0.145)]
    def build():
        getattr(P, "b_" + name)()
        # props3d's dual/ultra move the screen to the panel's centre (inside it): push it out the front
        if name in ("dual", "ultra"):
            from mathutils import Matrix
            for o in bpy.context.scene.objects:
                if o.name.startswith("scr"):
                    o.location += Matrix.Rotation(o.rotation_euler.z, 3, "Z") @ Vector((0, -0.0125, 0))
    fr = render_cut(build, (0, 0, 0.25), (0, -1, 0.12), 120, out, pts, dist=4.0)
    return {"screen": fr[0] + fr[1], "screen2": (fr[2] + fr[3]) if name == "dual" else None}


def b_keyboard():
    blk = P.mat("kb", (0.05, 0.05, 0.055), 0.45)
    key = P.mat("key", (0.13, 0.13, 0.14), 0.5)
    P.box("base", (-0.22, -0.07, 0), (0.22, 0.07, 0.018), blk, 0.004)
    for r in range(5):
        for k in range(15):
            P.box("k", (-0.205 + k * 0.0275, -0.06 + r * 0.025, 0.018), (-0.205 + k * 0.0275 + 0.023, -0.06 + r * 0.025 + 0.021, 0.026), key, 0.002)
    P.box("space", (-0.07, -0.085, 0.018), (0.07, -0.066, 0.026), key, 0.002)
    P.box("mouse", (0.3, -0.04, 0), (0.355, 0.05, 0.03), blk, 0.012)


def b_shelfunit():
    """A freestanding walnut etagere: two posts, four shelves; the trophy stands on the third."""
    wal = P.WALNUT()
    for sx in (-0.4, 0.37):
        for sy in (-0.15, 0.12):
            P.box("post", (sx, sy, 0), (sx + 0.03, sy + 0.03, 1.8), wal, 0.004)
    for z in SHELF_Z:
        P.box("shelf", (-0.42, -0.17, z), (0.42, 0.17, z + 0.03), wal, 0.004)
    P.box("back", (-0.4, 0.13, 0.0), (0.4, 0.15, 1.8), P.mat("backp", (0.16, 0.09, 0.05), 0.7))


SHELF_Z = (0.08, 0.6, 1.12, 1.62)


def render_extra(name):
    out = os.path.join(OUT, name + ".png")
    if name == "keyboard":
        render_cut(b_keyboard, (0.06, 0, 0), (0, -1, 1.1), 90, out, dist=2.0)
        return {}
    fr = render_cut(b_shelfunit, (0, 0, 0.9), (0, -1, 0.1), 60, out, dist=4.5, pts=[(-0.42, -0.17, z + 0.03) for z in SHELF_Z] + [(0.42, -0.17, SHELF_Z[0])])
    return {"shelves": [f[1] for f in fr[:-1]], "shelf_l": fr[0][0], "shelf_r": fr[-1][0]}


def b_tv():
    blk = P.BLACK()
    P.box("cab", (-0.8, -0.22, 0), (0.8, 0.22, 0.45), P.WALNUT(), 0.01)
    P.box("panel", (-0.62, -0.03, 0.55), (0.62, 0.0, 1.27), blk, 0.008)
    P.box("scr", (-0.6, -0.031, 0.57), (0.6, -0.03, 1.25), P.mat("tvs", (0.05, 0.1, 0.2), 0.1, emit=1.2, ecol=(0.3, 0.55, 0.9)))
    P.box("leg", (-0.04, -0.02, 0.45), (0.04, 0.02, 0.56), blk)


def b_couch():
    fab = P.mat("fabric", (0.25, 0.32, 0.42), 0.85)
    P.box("seat", (-1.0, -0.42, 0.12), (1.0, 0.42, 0.45), fab, 0.06)
    P.box("backr", (-1.0, 0.18, 0.4), (1.0, 0.42, 0.85), fab, 0.07)
    for sx in (-1, 1):
        P.box("arm", (sx * 1.0 - 0.14, -0.42, 0.12), (sx * 1.0 + 0.14, 0.42, 0.62), fab, 0.06)
    for sx in (-0.5, 0.5):
        P.box("cush", (sx - 0.47, -0.4, 0.45), (sx + 0.47, 0.2, 0.55), fab, 0.05)
    P.box("rug", (-1.4, -1.6, 0), (1.4, 0.5, 0.012), P.mat("rug", (0.75, 0.68, 0.55), 0.95))
    P.box("table", (-0.45, -1.2, 0.3), (0.45, -0.75, 0.36), P.WALNUT(), 0.01)
    for sx in (-0.4, 0.4):
        for sy in (-1.15, -0.8):
            P.cyl("tl", (sx, sy, 0.15), 0.02, 0.3, P.BLACK())


def b_homepc():
    blk = P.BLACK()
    wood = P.mat("deskw", (0.85, 0.82, 0.76), 0.5)
    P.box("top", (-0.6, -0.3, 0.72), (0.6, 0.3, 0.76), wood, 0.006)
    for sx in (-0.57, 0.54):
        P.box("leg", (sx, -0.27, 0), (sx + 0.03, 0.27, 0.72), wood)
    P.box("panel", (-0.3, 0.05, 0.86), (0.3, 0.07, 1.2), blk, 0.006)
    P.box("scr", (-0.285, 0.049, 0.875), (0.285, 0.05, 1.185), P._screen_mat())
    P.box("stand", (-0.02, 0.07, 0.76), (0.02, 0.1, 0.87), blk)
    P.box("tower", (0.38, -0.05, 0.76), (0.56, 0.25, 1.2), blk, 0.01)
    P.box("rgb", (0.379, -0.04, 0.8), (0.381, 0.2, 1.15), P.mat("rgb", (0.6, 0.2, 0.9), 0.3, emit=3.0, ecol=(0.6, 0.3, 1.0)))
    P.box("kb", (-0.22, -0.2, 0.76), (0.22, -0.06, 0.78), blk, 0.003)
    chair = P.mat("chairm", (0.12, 0.12, 0.14), 0.6)
    P.box("cseat", (-0.25, -0.75, 0.45), (0.25, -0.3, 0.52), chair, 0.03)
    P.box("cback", (-0.24, -0.82, 0.5), (0.24, -0.74, 1.05), chair, 0.03)
    P.cyl("cpost", (0, -0.52, 0.24), 0.025, 0.42, blk)
    P.cyl("cbase", (0, -0.52, 0.03), 0.28, 0.04, blk)


def render_home(name):
    d = os.path.join(P.ROOT, "assets", "home")
    os.makedirs(d, exist_ok=True)
    build = {"tv": b_tv, "couch": b_couch, "homepc": b_homepc}[name]
    # the apartment camera stands at eye level; seen a little from above and from the left
    render_cut(build, (0, 0, 0.5), (-0.35, -1, 0.42), 40, os.path.join(d, name + ".png"), res=800, dist=7.0)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    names = sys.argv[1:] or list(DESKS + CHAIRS + MONITORS + EXTRAS + HOME)
    jp = os.path.join(OUT, "deskview.json")
    meta = json.load(open(jp)) if os.path.exists(jp) else {}
    for n in names:
        if n in DESKS:
            meta["edge_" + n] = render_desk(n)
            json.dump(meta, open(jp, "w"), indent=1)
        elif n in MONITORS:
            meta["monitor_" + n] = render_monitor(n)
            json.dump(meta, open(jp, "w"), indent=1)
        elif n in EXTRAS:
            meta[n] = render_extra(n)
            json.dump(meta, open(jp, "w"), indent=1)
        elif n in HOME:
            render_home(n)
        else:
            render_chair(n)
        print("rendered", n, flush=True)
