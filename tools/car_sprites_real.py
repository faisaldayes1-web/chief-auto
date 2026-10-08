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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True

import bpy  # noqa: E402,I001
from mathutils import Matrix, Vector  # noqa: E402

import car_restyle  # noqa: E402

SRC = os.environ.get("CARSRC", "/root/carsrc")
SAMPLES = int(os.environ.get("SAMPLES", 96))
SKY = float(os.environ.get("SKY", 0.3))
HORIZON = float(os.environ.get("HORIZON", 0.22))   # environment brightness below the horizon (1 = plain sky)
SUN = float(os.environ.get("SUN", 14.0))   # no sun disc in the sky: the lamp carries all of it
PAINT = float(os.environ.get("PAINT", 0.75))
GROUND = float(os.environ.get("GROUND", 0.12))     # floor colour for the light it bounces under the car
EXPOSURE = float(os.environ.get("EXPOSURE", 0.6))
# The sun: 50 degrees up, behind the three-quarter camera and to its left (140 degrees round from the view direction),
# so the faces the camera sees are in sunlight and the shadow falls back and to the right. tools/dealership3d.py
# turns its sun the same way relative to the lot cameras (SUN_EL / SUN_AZ there), so parked sprites match the renders.
SUN_EL, SUN_AZ = 50.0, -178.0

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
    # stand-in for the Tahoe: a boxy full-size Toyota SUV, scaled to Tahoe length. prado_clean.glb is the Sketchfab
    # export with draco stripped (gltf-transform) and the quarter-panel lettering given its own material ("decal_text")
    "chevro_tahoma": dict(src="prado2025_sultan/prado_clean.glb", length=5.2,
                          paint=r"^WorldGridMaterial(\.001|\.007|\.019|\.020)?$",
                          badge=r"^decal_text$", drop_mat=r"^WorldGridMaterial\.030$", front=-1),
}


def setup():
    """Daylight studio: sky + sun for the light and the contact shadow, plus soft reflector cards that only show up
    in reflections, so clear-coat paint, glass and rims get real highlights."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.max_bounces = 6
    sc.cycles.glossy_bounces = 3
    sc.cycles.transmission_bounces = 4
    sc.cycles.transparent_max_bounces = 32
    sc.cycles.sample_clamp_indirect = 8.0
    sc.cycles.blur_glossy = 0.5
    sc.render.film_transparent = True
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Punchy"
    sc.view_settings.exposure = EXPOSURE
    w = bpy.data.worlds.new("sky")
    sc.world = w
    w.use_nodes = True
    sky = w.node_tree.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_elevation = math.radians(SUN_EL)
    sky.sun_rotation = math.radians(SUN_AZ)
    # the sun lamp does the sun; a sun disc in the sky texture as well turns every rough black part (tyres, trim)
    # into a grey reflection of it
    sky.sun_disc = False
    # environment gradient: full sky overhead, darker towards the horizon and dark below it, so the paint's
    # reflections and the ambient light give a bright roof and shoulders over darker sills (a studio "horizon")
    nt = w.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.interpolation_type = "SMOOTHSTEP"
    mr.inputs["From Min"].default_value = -0.12
    mr.inputs["From Max"].default_value = 0.55
    mr.inputs["To Min"].default_value = HORIZON
    mr.inputs["To Max"].default_value = 1.0
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(sky.outputs[0], mul.inputs["A"])
    nt.links.new(mr.outputs["Result"], mul.inputs["B"])
    nt.links.new(mul.outputs["Result"], nt.nodes["Background"].inputs[0])
    nt.nodes["Background"].inputs["Strength"].default_value = SKY
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = SUN
    sun.angle = math.radians(6)
    so = bpy.data.objects.new("sun", sun)
    el, az = math.radians(SUN_EL), math.radians(SUN_AZ)
    d = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    so.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(so)
    # reflector cards (seen only in reflections): an overhead softbox, a long strip low on the camera side that
    # draws a highlight along the flanks, and a card off the front corner for the three-quarter view
    for name, loc, size, strength in (("card_top", (0, 0, 5.0), (7.0, 3.2), 2.2),
                                      ("card_side", (0.5, -6.5, 1.3), (9.0, 1.1), 1.6),
                                      ("card_front", (6.5, -3.0, 2.2), (2.6, 2.6), 1.6),
                                      ("card_rear", (-6.0, 2.5, 2.5), (3.0, 2.0), 1.0)):
        card(sc, name, Vector(loc), size, strength)
    # the road the paint reflects: a darker floor seen only in reflections, so the lower body picks up the usual
    # dark-below / light-above horizon line (the shadow catcher itself is hidden in the paint pass)
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, -0.003))
    floor = bpy.context.object
    floor.name = "refl_floor"
    floor.data.materials.append(simple_mat("refl_floor", (0.05, 0.05, 0.052), rough=0.9))
    floor.visible_camera = False
    floor.visible_diffuse = False
    floor.visible_shadow = False
    floor.visible_transmission = False
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = "ground"
    ground.is_shadow_catcher = True
    # asphalt-coloured for the light it bounces up under the car (the default white floor greys out tyres and
    # black trim from below)
    ground.data.materials.append(simple_mat("ground", (GROUND, GROUND, GROUND), rough=0.9))
    cam = bpy.data.cameras.new("cam")
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return co, ground


def card(sc, name, loc, size, strength):
    me = bpy.data.meshes.new(name)
    a, b = size[0] / 2, size[1] / 2
    me.from_pydata([(-a, -b, 0), (a, -b, 0), (a, b, 0), (-a, b, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    # face the car (the plane's normal is +Z)
    ob.rotation_euler = (Vector((0, 0, 0.6)) - loc).to_track_quat("Z", "Y").to_euler()
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = strength
    # soft edges: brightest in the middle of the card
    tc = nt.nodes.new("ShaderNodeTexCoord")
    gr = nt.nodes.new("ShaderNodeTexGradient")
    gr.gradient_type = "QUADRATIC_SPHERE"
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0 / a * 1.05, 1.0 / b * 1.05, 1)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], gr.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
    ramp.color_ramp.elements[1].position = 0.35
    ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
    nt.links.new(gr.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    me.materials.append(m)
    ob.visible_camera = False
    ob.visible_diffuse = False
    ob.visible_shadow = False
    ob.visible_volume_scatter = False
    sc.collection.objects.link(ob)
    return ob


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
    """Downscale a supersampled render (premultiplied, Lanczos) and save it as an optimised PNG."""
    import numpy as np
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    a = np.asarray(im).astype(np.float32) / 255.0
    rgb = a[..., :3] * a[..., 3:4]
    chans = [Image.fromarray(rgb[..., k]).resize(size, Image.LANCZOS) for k in range(3)]
    alpha = Image.fromarray(a[..., 3]).resize(size, Image.LANCZOS)
    al = np.clip(np.asarray(alpha), 0, 1)
    out = np.stack([np.asarray(c) for c in chans], -1)
    out = np.where(al[..., None] > 1e-4, out / np.maximum(al[..., None], 1e-4), 0)
    res = np.concatenate([np.clip(out, 0, 1), al[..., None]], -1)
    res[al < 1.5 / 255] = 0
    Image.fromarray((res * 255 + 0.5).astype(np.uint8), "RGBA").save(dst, optimize=True)
    os.remove(src)


def paint_material():
    """Light grey clear-coat paint for the tint layer: a satin base under a glossy coat, so the reflector cards
    and the sky leave real highlights in the layer the game tints."""
    m = simple_mat("paint_grey", (PAINT, PAINT, PAINT), rough=0.32, metal=0.25, coat=1.0)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Coat Roughness"].default_value = 0.025
    b.inputs["Coat IOR"].default_value = 1.5
    return m


def glass_material(transmission=0.3, spec=0.55):
    """Tinted, slightly see-through window glass with a strong reflection."""
    m = bpy.data.materials.get("rs_glass")
    if m:
        return m
    m = simple_mat("rs_glass", (0.006, 0.008, 0.011), rough=0.02, metal=0.0, coat=0.0)
    m.name = "rs_glass"
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Transmission Weight"].default_value = transmission
    b.inputs["IOR"].default_value = 1.52
    b.inputs["Specular IOR Level"].default_value = spec
    return m


def polish(meshes, glass_rx, transmission=0.3, spec=0.55):
    """Swaps the model's window materials for our tinted glass."""
    if not glass_rx:
        return
    g = glass_material(transmission, spec)
    for o in meshes:
        for sl in o.material_slots:
            if sl.material and re.search(glass_rx, sl.material.name):
                sl.material = g


def do_car(slug, out, test):
    cfg = CARS[slug]
    cam, ground = setup()
    meshes, dims = load_car(cfg)
    if os.environ.get("RESTYLE", "1") != "0":
        meshes, dims = car_restyle.restyle(meshes, slug, dims, cfg)
    rc = car_restyle.RECIPES.get(slug, {})
    polish(meshes, rc.get("glass"), rc.get("glass_transmission", 0.3), rc.get("glass_spec", 0.55))
    slots = classify(meshes, cfg)
    originals = {o: [sl.material for sl in o.material_slots] for o in meshes}
    grey = paint_material()
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
    render_layers(out, slug, cam, ground, dims, lambda mode: set_pass(meshes, slots, originals, mode, grey, hold))


def render_layers(out, slug, cam, ground, dims, set_mode):
    """The four sprites, each rendered at twice the size and scaled down: side 600x240, three-quarter 640x360."""
    for view, size, prefix in (("side", (600, 240), ""), ("q", (640, 360), "_q")):
        if view == "side":
            side_cam(cam)
        else:
            quarter_cam(cam, dims)
        for mode in ("paint", "detail"):
            set_mode(mode)
            ground.hide_render = mode == "paint"
            tmp = os.path.join(out, "_tmp_%s_%s.png" % (slug, mode))
            render(tmp, (size[0] * 2, size[1] * 2))
            shrink(tmp, os.path.join(out, "%s%s_%s.png" % (slug, prefix, mode)), size)


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
