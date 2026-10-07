"""Three-quarter-view car sprites from the game's 3D cars (assets/cars3d/*.glb) for the lot and the showroom.

Each car is rendered twice in daylight: <slug>_q_paint.png holds only the painted body panels in light grey (the game
tints it with the car's colour) and <slug>_q_detail.png holds everything else (glass, wheels, lights, trim and the
ground shadow) with the paint cut out. The game draws paint first, then detail.

Usage (bpy venv):  python tools/car_sprites3d.py <out_dir> [slug ...]
"""
import math
import os
import sys

import bpy  # noqa: I001
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
CARS = os.path.join(HERE, "..", "assets", "cars3d")
SAMPLES = int(os.environ.get("SAMPLES", 48))
RES = (640, 360)
PAINT_PARTS = ("part_hood", "part_door", "part_fender", "part_quarter", "part_roof", "part_trunk",
               "part_front_bumper", "part_rear_bumper", "part_tailgate", "part_bed", "part_rocker")


def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    sc.render.film_transparent = True
    sc.render.resolution_x, sc.render.resolution_y = RES
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    w = bpy.data.worlds.new("sky")
    sc.world = w
    w.use_nodes = True
    sky = w.node_tree.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_elevation = math.radians(58)
    sky.sun_rotation = math.radians(-140)
    w.node_tree.links.new(sky.outputs[0], w.node_tree.nodes["Background"].inputs[0])
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.4
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 3.0
    sun.angle = math.radians(14)
    so = bpy.data.objects.new("sun", sun)
    el, az = math.radians(58), math.radians(-140)
    d = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    so.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(so)
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = "ground"
    ground.is_shadow_catcher = True
    cam = bpy.data.cameras.new("cam")
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return co, ground


def paint_mat():
    m = bpy.data.materials.new("paint_grey")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.75, 0.75, 0.75, 1)
    b.inputs["Metallic"].default_value = 0.45
    b.inputs["Roughness"].default_value = 0.22
    b.inputs["Coat Weight"].default_value = 0.6
    return m


def render_car(slug, out, cam, ground):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(CARS, slug + ".glb"))
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    paint = [o for o in meshes if o.name.startswith(PAINT_PARTS)]
    pm = paint_mat()
    for o in paint:
        o.data.materials.clear()
        o.data.materials.append(pm)
    bpy.context.view_layer.update()
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in meshes:
        for c in o.bound_box:
            p = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, p))
            hi = Vector(map(max, hi, p))
    size = hi - lo
    centre = (lo + hi) / 2
    along_x = size.x >= size.y
    # the headlights mark the front of the car
    front = 1.0
    heads = [o for o in new if o.name.startswith("headlight")]
    if heads:
        hp = sum((heads[0].matrix_world @ Vector(c) for c in heads[0].bound_box), Vector()) / 8
        front = 1.0 if ((hp.x - centre.x) if along_x else (hp.y - centre.y)) > 0 else -1.0
    fwd = Vector((front, 0, 0)) if along_x else Vector((0, front, 0))
    side = Vector((-fwd.y, fwd.x, 0))
    length = max(size.x, size.y)
    # three-quarter front view from a person's eye height a little above the roof line
    target = Vector((centre.x, centre.y, size.z * 0.42))
    pos = target + (fwd * 0.62 + side * 0.78).normalized() * length * 1.7 + Vector((0, 0, 1.15))
    cam.location = pos
    cam.data.lens = 50
    cam.rotation_euler = (target - pos).to_track_quat("-Z", "Y").to_euler()
    ground.location = (centre.x, centre.y, lo.z)
    sc = bpy.context.scene
    # pass 1: paint only (everything else cuts it out)
    for o in meshes:
        o.is_holdout = o not in paint
    ground.hide_render = True
    sc.render.filepath = os.path.join(out, slug + "_q_paint.png")
    bpy.ops.render.render(write_still=True)
    # pass 2: everything but the paint, plus the ground shadow
    for o in meshes:
        o.is_holdout = o in paint
    ground.hide_render = False
    sc.render.filepath = os.path.join(out, slug + "_q_detail.png")
    bpy.ops.render.render(write_still=True)
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    slugs = sys.argv[2:] or sorted(f[:-4] for f in os.listdir(CARS) if f.endswith(".glb"))
    cam, ground = setup()
    for s in slugs:
        render_car(s, out, cam, ground)


if __name__ == "__main__":
    main()
