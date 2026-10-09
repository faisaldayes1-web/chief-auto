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


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    names = sys.argv[1:] or list(DESKS + CHAIRS)
    jp = os.path.join(OUT, "deskview.json")
    meta = json.load(open(jp)) if os.path.exists(jp) else {}
    for n in names:
        if n in DESKS:
            meta["edge_" + n] = render_desk(n)
            json.dump(meta, open(jp, "w"), indent=1)
        else:
            render_chair(n)
        print("rendered", n, flush=True)
