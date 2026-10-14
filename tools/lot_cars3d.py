"""Lot car sprites rendered from each lot view's own camera, parked nose-in in that view's stalls.

The lot stalls of a view are fanned so every stall in a row shows its car at the same angle to the camera
(tools/dealership3d.py, lot_stalls), so one render per (view, row, car) serves the whole row: it is rendered in the
row's middle stall from the view's exact camera (position, look-at, 50 mm lens) under the lot's sun (SUN_EL / SUN_AZ),
as a crop of the full 2560x1440 frame. The game moves it to another stall of the row and scales it by that stall's
pixels per metre.

Per sprite: <out>/<view>_r<row>_<slug>_paint.png (body paint in light grey, tinted by the game) and _detail.png
(everything else, plus a light, soft contact shadow from a shadow catcher, cut out under the paint). Layout in
<out>/lotcars_<view>.json.

Reads the stalls and cameras from a copy of tools/dealership3d.py (D3D env, default tools/dealership3d.py).
Usage (bpy venv):  python tools/lot_cars3d.py <out_dir> <view> [slug ...]       (view: lot, lot_t1, lot_t2)
Env: SAMPLES (32), SHADOW (0.55, contact shadow strength).
"""
import importlib.util
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True

import bpy  # noqa: E402,I001
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import car_restyle  # noqa: E402
import car_sprites_real as R  # noqa: E402

SAMPLES = int(os.environ.get("SAMPLES", 32))
SHADOW = float(os.environ.get("SHADOW", 0.55))
IMAGE = (2560, 1440)
NOSE_GAP = 0.15      # the nose stops this far past the rear-clearance line of a nose-out stall (over the wheel stop)
FLIP = set()   # models whose headlight objects sit at the back (none since the 2026-10-14 rebuild; toyoda_camri was wrongly here)
GLB = os.path.join(HERE, "..", "assets", "cars3d")
PAINT_PARTS = ("part_hood", "part_door", "part_fender", "part_quarter", "part_roof", "part_trunk",
               "part_front_bumper", "part_rear_bumper", "part_tailgate", "part_bed", "part_rocker")


def d3d():
    path = os.environ.get("D3D", os.path.join(HERE, "dealership3d.py"))
    spec = importlib.util.spec_from_file_location("d3d_ro", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load_glb(slug):
    """A game model (assets/cars3d) turned to face +X, centred, standing on z=0. Returns meshes, dims, paint set."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(GLB, slug + ".glb"))
    for m in bpy.data.materials:   # render backfaces: single-sided doors and panels must not show see-through holes
        m.use_backface_culling = False
        if hasattr(m, "use_backface_culling_shadow"):
            m.use_backface_culling_shadow = False
    new = [o for o in bpy.data.objects if o not in before]
    bpy.context.view_layer.update()
    meshes = [o for o in new if o.type == "MESH"]
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for o in meshes:
        for c in o.bound_box:
            p = o.matrix_world @ Vector(c)
            lo, hi = Vector(map(min, lo, p)), Vector(map(max, hi, p))
    size, centre = hi - lo, (lo + hi) / 2
    along_x = size.x >= size.y
    front = 1.0
    heads = [o for o in new if o.name.startswith("headlight")]
    if heads:
        hp = sum((heads[0].matrix_world @ Vector(c) for c in heads[0].bound_box), Vector()) / 8
        front = 1.0 if ((hp.x - centre.x) if along_x else (hp.y - centre.y)) > 0 else -1.0
    if slug in FLIP:
        front = -front
    yaw = (0.0 if along_x else math.pi / 2) + (0.0 if front > 0 else math.pi)
    for o in meshes:
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    for o in new:
        if o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    xf = Matrix.Rotation(-yaw, 4, "Z") @ Matrix.Translation(-Vector((centre.x, centre.y, lo.z)))
    for o in meshes:
        o.matrix_world = xf @ o.matrix_world
    dims = Vector((max(size.x, size.y), min(size.x, size.y), size.z))
    return meshes, dims, {o for o in meshes if o.name.startswith(PAINT_PARTS)}


def prepare(slug):
    """Loads a car (the realistic model when there is one) and returns (meshes, dims, set_mode)."""
    hold = R.holdout_mat()
    if slug in R.CARS:
        cfg = R.CARS[slug]
        meshes, dims = R.load_car(cfg)
        if os.environ.get("RESTYLE", "1") != "0":
            meshes, dims = car_restyle.restyle(meshes, slug, dims, cfg)
        rc = car_restyle.RECIPES.get(slug, {})
        R.polish(meshes, rc.get("glass"), rc.get("glass_transmission", 0.3), rc.get("glass_spec", 0.55))
        slots = R.classify(meshes, cfg)
        originals = {o: [sl.material for sl in o.material_slots] for o in meshes}
        grey = R.paint_material()

        def set_mode(mode):
            for o in meshes:
                o.visible_camera = mode != "shadow"
            R.set_pass(meshes, slots, originals, "detail" if mode == "shadow" else mode, grey, hold)
        return meshes, dims, set_mode
    meshes, dims, paint = load_glb(slug)
    grey = R.paint_material()
    for o in paint:
        o.data.materials.clear()
        o.data.materials.append(grey)

    def set_mode(mode):
        for o in meshes:
            o.visible_camera = mode != "shadow"
            o.is_holdout = (o not in paint) if mode == "paint" else (o in paint and mode == "detail")
    return meshes, dims, set_mode


def aim_sun(yaw, el, az):
    """Turns the studio's sun lamp and sky to the lot's sun, seen from the car's own frame (car faces +X)."""
    sc = bpy.context.scene
    a = math.radians(az) + yaw
    e = math.radians(el)
    d = Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
    so = bpy.data.objects["sun"]
    so.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    for n in sc.world.node_tree.nodes:
        if n.type == "TEX_SKY":
            n.sun_rotation = a
            n.sun_elevation = e
    return so


def main():
    out, view = sys.argv[1], sys.argv[2]
    slugs = sys.argv[3:] or sorted(f[:-4] for f in os.listdir(GLB) if f.endswith(".glb"))
    os.makedirs(out, exist_ok=True)
    D = d3d()
    pos, tgt, lens, _ = D.VIEWS[view]
    pos, tgt = Vector(pos), Vector(tgt)
    stalls = D.lot_stalls(view)
    rows = sorted({st["row"] for st in stalls})
    reps = {}
    for r in rows:
        row = [i for i, st in enumerate(stalls) if st["row"] == r]
        reps[r] = row[len(row) // 2]
    lay_path = os.path.join(out, "lotcars_%s.json" % view)
    lay = json.load(open(lay_path)) if os.path.exists(lay_path) else {}
    lay.update({"view": view, "image": list(IMAGE), "nose_gap": NOSE_GAP,
                "about": "Nose-in lot car sprites. rep: per row, the stall index (lot_stalls order, see stall_index in the "
                         "stalls json) each row's sprites were rendered in. Per sprite key <row>/<slug>: rect [u0, v0, u1, v1] "
                         "of the crop in the full image (fractions), anchor: the car's ground centre (fractions), ppm of "
                         "that stall. Car centre: wall + fwd * (d + nose_gap + L/2)."})
    lay["rep"] = {str(r): reps[r] for r in rows}
    lay.setdefault("sprites", {})
    lay.setdefault("dims", {})
    for slug in slugs:
        cam, ground = R.setup()
        sc = bpy.context.scene
        sc.cycles.samples = SAMPLES
        sc.render.resolution_x, sc.render.resolution_y = IMAGE
        sc.render.resolution_percentage = 100
        cam.data.lens = lens
        meshes, dims, set_mode = prepare(slug)
        length, width, height = dims
        lay["dims"][slug] = [round(length, 3), round(width, 3), round(height, 3)]
        sun = bpy.data.objects["sun"]
        for r in rows:
            st = stalls[reps[r]]
            fwd = st["fwd"]
            base = Vector(((st["x0"] + st["x1"]) / 2, st["wall_y"], 0))
            centre = base + fwd * (st["d"] + NOSE_GAP + length / 2)
            head = -fwd                           # nose-in: the car faces the wall
            yaw = math.atan2(head.y, head.x)
            to_local = Matrix.Rotation(-yaw, 4, "Z") @ Matrix.Translation(-centre)
            cam.location = to_local @ pos
            look = Matrix.Rotation(-yaw, 3, "Z") @ (tgt - pos)
            cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
            aim_sun(yaw, D.SUN_EL, D.SUN_AZ)
            bpy.context.view_layer.update()
            # crop: the car's box plus a margin for the contact shadow
            us, vs = [], []
            m = 0.45
            for x in (-length / 2 - m, length / 2 + m):
                for y in (-width / 2 - m, width / 2 + m):
                    for z in (0.0, height + 0.05):
                        q = world_to_camera_view(sc, cam, Vector((x, y, z)))
                        us.append(q.x)
                        vs.append(q.y)
            u0, u1 = max(0.0, min(us)), min(1.0, max(us))
            v0, v1 = max(0.0, min(vs)), min(1.0, max(vs))
            # snap to whole pixels so the game's rect is exact
            px0, px1 = math.floor(u0 * IMAGE[0]), math.ceil(u1 * IMAGE[0])
            py0, py1 = math.floor(v0 * IMAGE[1]), math.ceil(v1 * IMAGE[1])
            sc.render.use_border = True
            sc.render.use_crop_to_border = True
            sc.render.border_min_x, sc.render.border_max_x = px0 / IMAGE[0], px1 / IMAGE[0]
            sc.render.border_min_y, sc.render.border_max_y = py0 / IMAGE[1], py1 / IMAGE[1]
            gq = world_to_camera_view(sc, cam, Vector((0, 0, 0)))
            name = "%s_r%d_%s" % (view, r, slug)
            files = {}
            for mode in ("paint", "detail", "shadow"):
                set_mode(mode)
                ground.hide_render = mode != "shadow"
                sun.data.angle = math.radians(28 if mode == "shadow" else 6)
                sun.data.energy = R.SUN * (0.45 if mode == "shadow" else 1.0)
                files[mode] = os.path.join(out, "_tmp_%s_%s.png" % (name, mode))
                sc.render.filepath = files[mode]
                bpy.ops.render.render(write_still=True)
            compose(files, os.path.join(out, name))
            lay["sprites"]["%d/%s" % (r, slug)] = {
                "rect": [round(px0 / IMAGE[0], 6), round(1 - py1 / IMAGE[1], 6), round(px1 / IMAGE[0], 6), round(1 - py0 / IMAGE[1], 6)],
                "anchor": [round(gq.x, 6), round(1 - gq.y, 6)],
                "px": [px1 - px0, py1 - py0]}
            print("done", name, flush=True)
            with open(lay_path, "w") as f:
                json.dump(lay, f, indent=1, sort_keys=True)


def compose(files, stem):
    """paint as rendered; detail over a light contact shadow that is cut out wherever the car is."""
    import numpy as np
    from PIL import Image
    p = np.asarray(Image.open(files["paint"]).convert("RGBA")).astype(np.float32) / 255
    d = np.asarray(Image.open(files["detail"]).convert("RGBA")).astype(np.float32) / 255
    s = np.asarray(Image.open(files["shadow"]).convert("RGBA")).astype(np.float32) / 255
    car = 1 - (1 - p[..., 3]) * (1 - d[..., 3])
    sa = np.clip(s[..., 3] * SHADOW, 0, 1) * (1 - car)
    a = d[..., 3] + sa * (1 - d[..., 3])
    rgb = np.where(a[..., None] > 1e-4, d[..., :3] * d[..., 3:4] / np.maximum(a[..., None], 1e-4), 0)
    out = np.concatenate([rgb, a[..., None]], -1)
    Image.fromarray((p * 255 + 0.5).astype(np.uint8), "RGBA").save(stem + "_paint.png", optimize=True)
    Image.fromarray((out * 255 + 0.5).astype(np.uint8), "RGBA").save(stem + "_detail.png", optimize=True)
    for f in files.values():
        os.remove(f)


if __name__ == "__main__":
    main()
