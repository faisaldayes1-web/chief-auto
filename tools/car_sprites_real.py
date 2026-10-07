"""Sprites from realistic third-party car models (CC-BY, see assets/cars/CREDITS.md) for the cars that have one.

Same outputs as car3d.py `sprites` and car_sprites3d.py, so the game picks them up unchanged:
  <slug>_paint.png / <slug>_detail.png       side view, 600x240, front to the right, ground at y=223
  <slug>_q_paint.png / <slug>_q_detail.png   three-quarter front view, 640x360
The paint layer holds only the body paint in light grey (the game tints it); the detail layer is everything else
with the paint cut out. Badges and emblems are painted over with the body colour, number plates are blanked.

Usage (bpy venv):  python tools/car_sprites_real.py <out_dir> [test] [slug ...]
`test` writes plain colour renders (<slug>_test_side.png, <slug>_test_q.png) to check orientation and paint picks.
"""
import math
import os
import re
import sys

import bpy  # noqa: I001
from mathutils import Matrix, Vector

SRC = os.environ.get("CARSRC", "/root/carsrc")
SAMPLES = int(os.environ.get("SAMPLES", 48))

# slug: source file, real length in metres, paint materials (regex), badge/plate materials (regex),
# drop_mat: objects using these materials are removed (shadow planes), front: which way the car faces along its long axis after import (+1 / -1)
CARS = {
    "porsha_911": dict(src="porsche930_miklas/scene.gltf", length=4.52, paint=r"^(paint|coat)$", drop_mat=r"^material_0$",
                       badge=r"stickers|wunderbaum", plate=r"^plate$", front=-1),
    "forde_mustank": dict(src="mustang_gt500_full/scene.gltf", length=4.81, paint=r"^carpaint$", plate=r"^plate$",
                          front=-1),
    "mazdo_miota": dict(src="miata_na_lexyc16/scene.gltf", length=3.97, paint=r"^Material\.002$", front=-1),
    "ferrano_488": dict(src="threejs_ferrari_decoded/ferrari_nodraco.glb", length=4.57, paint=r"^Body_Color$",
                        badge=r"Ferrari_Yellow|DodgerBlue", front=1),
    "lamborgo_aventa": dict(src="aventador_lp700/scene.gltf", length=4.78, paint=r"^Body$",
                            badge=r"^Logo|LP_700", front=-1),
    "hondo_civix": dict(src="civic_typer_jumpingjax/scene.gltf", length=4.6, paint=r"^Paintid9490011Mtl$",
                        badge=r"Rimbadge", front=-1),
    "bmv_m4": dict(src="bmw_m4comp2021/scene.gltf", length=4.79, paint=r"^Material_692$", front=-1),
    "ramm_1500": dict(src="ram1500/scene.gltf", length=5.6, paint=r"^(Base|0-body\d*)$", front=-1),
    "forde_rangler": dict(src="ranger2001_badkarma/scene.gltf", length=5.15, paint=r"^material_0$", front=-1),
    "rang_rovah": dict(src="rrsport_custom/scene.gltf", length=4.88, paint=r"^Car_Paint$", front=-1),
    "mercedez_g_wagon": dict(src="g900_dasauto/scene.gltf", length=4.82, paint=r"^bodypaint", front=-1),
}


def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    sc.cycles.transparent_max_bounces = 32
    sc.render.film_transparent = True
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Punchy"
    w = bpy.data.worlds.new("sky")
    sc.world = w
    w.use_nodes = True
    sky = w.node_tree.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_elevation = math.radians(50)
    sky.sun_rotation = math.radians(-140)
    w.node_tree.links.new(sky.outputs[0], w.node_tree.nodes["Background"].inputs[0])
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 2.6
    sun.angle = math.radians(10)
    so = bpy.data.objects.new("sun", sun)
    el, az = math.radians(50), math.radians(-140)
    d = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    so.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(so)
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = "ground"
    ground.is_shadow_catcher = True
    cam = bpy.data.cameras.new("cam")
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return co, ground


def simple_mat(name, color, rough=0.5, metal=0.0, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    return m


def holdout_mat():
    m = bpy.data.materials.new("holdout")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    h = nt.nodes.new("ShaderNodeHoldout")
    nt.links.new(h.outputs[0], out.inputs["Surface"])
    return m


def load_car(cfg):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(SRC, cfg["src"]))
    new = [o for o in bpy.data.objects if o not in before]
    def dropped(o):
        if o.type != "MESH":
            return False
        names = [sl.material.name for sl in o.material_slots if sl.material]
        # stray helpers (a sphere with no material) and baked ground-shadow planes
        return not names or bool(cfg.get("drop_mat") and any(re.search(cfg["drop_mat"], n) for n in names))
    for o in [o for o in new if dropped(o)]:
        new.remove(o)
        bpy.data.objects.remove(o, do_unlink=True)
    meshes = [o for o in new if o.type == "MESH"]
    # bake every transform into the meshes so the car can be measured and moved as one
    root = bpy.data.objects.new("car_root", None)
    bpy.context.scene.collection.objects.link(root)
    bpy.context.view_layer.update()
    for o in meshes:
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    for o in new:
        if o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.update()
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in meshes:
        for v in o.data.vertices:
            p = o.matrix_world @ v.co
            lo = Vector(map(min, lo, p))
            hi = Vector(map(max, hi, p))
    size = hi - lo
    centre = (lo + hi) / 2
    along_x = size.x >= size.y
    length = max(size.x, size.y)
    s = cfg["length"] / length
    # turn the car so it points down +X, scale it to its real length, centre it and stand it on z=0
    yaw = 0.0 if along_x else math.pi / 2
    if cfg.get("front", 1) < 0:
        yaw += math.pi
    xf = Matrix.Rotation(-yaw, 4, "Z") @ Matrix.Scale(s, 4) @ Matrix.Translation(-Vector((centre.x, centre.y, lo.z)))
    for o in meshes:
        o.matrix_world = xf @ o.matrix_world
    return meshes, Vector((cfg["length"], (size.y if along_x else size.x) * s, size.z * s))


def classify(meshes, cfg):
    """Swap badge and plate materials for paint / blank plate. Returns {object: [is_paint per slot]}."""
    paint_re = re.compile(cfg["paint"])
    badge_re = re.compile(cfg["badge"]) if cfg.get("badge") else None
    plate_re = re.compile(cfg["plate"]) if cfg.get("plate") else None
    blank = simple_mat("plate_blank", (0.85, 0.85, 0.83), rough=0.6)
    slots = {}
    for o in meshes:
        flags = []
        for sl in o.material_slots:
            n = sl.material.name if sl.material else ""
            is_paint = bool(paint_re.search(n))
            if badge_re and badge_re.search(n):
                is_paint = True
            if plate_re and plate_re.search(n):
                sl.link = "OBJECT"
                sl.material = blank
            flags.append(is_paint)
        slots[o] = flags
    return slots


def set_pass(meshes, slots, originals, mode, paint_grey, hold):
    """mode: 'paint' (paint grey, rest holdout), 'detail' (paint holdout, rest original), 'test' (all original)."""
    for o in meshes:
        for i, sl in enumerate(o.material_slots):
            orig = originals[o][i]
            if orig is None:
                continue
            sl.link = "OBJECT"
            if mode == "test":
                sl.material = orig
            elif mode == "paint":
                sl.material = paint_grey if slots[o][i] else hold
            else:
                sl.material = hold if slots[o][i] else orig


def render(path, res):
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def side_cam(cam):
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 5.8
    cam.location = (0, -20, 0.998)
    cam.rotation_euler = (math.radians(90), 0, 0)


def quarter_cam(cam, dims):
    length, width, height = dims
    cam.data.type = "PERSP"
    cam.data.lens = 50
    target = Vector((0, 0, height * 0.42))
    fwd = Vector((1, 0, 0))
    side = Vector((0, -1, 0))
    pos = target + (fwd * 0.62 + side * 0.78).normalized() * length * 1.7 + Vector((0, 0, 1.15))
    cam.location = pos
    cam.rotation_euler = (target - pos).to_track_quat("-Z", "Y").to_euler()


def shrink(src, dst, size):
    im = bpy.data.images.load(src)
    im.scale(*size)
    im.filepath_raw = dst
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)
    os.remove(src)


def do_car(slug, out, test):
    cfg = CARS[slug]
    cam, ground = setup()
    meshes, dims = load_car(cfg)
    slots = classify(meshes, cfg)
    originals = {o: [sl.material for sl in o.material_slots] for o in meshes}
    grey = simple_mat("paint_grey", (0.75, 0.75, 0.75), rough=0.22, metal=0.45, coat=0.6)
    hold = holdout_mat()
    sc = bpy.context.scene
    if test:
        sc.cycles.samples = 16
        side_cam(cam)
        set_pass(meshes, slots, originals, "paint", grey, hold)
        render(os.path.join(out, slug + "_test_paint.png"), (600, 240))
        set_pass(meshes, slots, originals, "test", grey, hold)
        render(os.path.join(out, slug + "_test_side.png"), (600, 240))
        quarter_cam(cam, dims)
        render(os.path.join(out, slug + "_test_q.png"), (640, 360))
        return
    side_cam(cam)
    for mode in ("paint", "detail"):
        set_pass(meshes, slots, originals, mode, grey, hold)
        ground.hide_render = mode == "paint"
        tmp = os.path.join(out, "_tmp_%s.png" % mode)
        render(tmp, (1200, 480))
        shrink(tmp, os.path.join(out, "%s_%s.png" % (slug, mode)), (600, 240))
    quarter_cam(cam, dims)
    for mode in ("paint", "detail"):
        set_pass(meshes, slots, originals, mode, grey, hold)
        ground.hide_render = mode == "paint"
        render(os.path.join(out, "%s_q_%s.png" % (slug, mode)), (640, 360))


def main():
    out = sys.argv[1]
    args = sys.argv[2:]
    test = bool(args) and args[0] == "test"
    if test:
        args = args[1:]
    os.makedirs(out, exist_ok=True)
    for slug in args or list(CARS):
        do_car(slug, out, test)
        print("done", slug, flush=True)


if __name__ == "__main__":
    main()
