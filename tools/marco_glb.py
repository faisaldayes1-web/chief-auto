"""Marco from his 3D model (Faisal's Tripo scan, /mnt/project-files/human+figure+3d+model.glb).

The GLB is a Tripo turnaround sheet: three copies of the full standing figure side by side along X (front at
x < -0.145, profile in the middle, three-quarter on the right), 0.63 m tall, one textured mesh, no rig (tools/marco_rig.py skins and poses it). We keep the
front copy, scale it to 1.78 m, and render every Marco picture from it (body, hero, portrait, faces, dialogue).

Steps:
  1. import the GLB, delete the two other copies, decimate to 35% (~120k verts; the 2048 maps carry the detail),
     stand him at the origin, 1.78 m tall, facing -Y
  2. light it like the game's interiors: warm Newport key (same colour as dealership3d.py's sun, 1.0/0.9/0.76) high
     to his right, cool window rim, soft fill; AgX Medium High Contrast like the other people renders
  3. render with a transparent film: hero (whole bust, slight three-quarter), portrait (480x600 framing, face centred)
  4. post: people_post.py-style crops -> assets/people/marco_{hero,portrait,face_*}.png, assets/portrait_marco.jpg

Usage:  /root/bpyenv/bin/python tools/marco_glb.py <out_dir> [preview]
        python3 tools/people_post.py <out_dir> assets/people marco=marco --dialogue assets
"""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import marco_rig  # noqa: E402  proximity-weighted skinning: arms down / hand at the pocket, head tilt, brows, smile

GLB = "/mnt/project-files/human+figure+3d+model.glb"
OUT = sys.argv[1]
PREVIEW = len(sys.argv) > 2
SAMPLES = 16 if PREVIEW else 128
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
ob = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
import bmesh
bm = bmesh.new()
bm.from_mesh(ob.data)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.x > -0.145], context="VERTS")
xs = [v.co.x for v in bm.verts]
ys = [v.co.y for v in bm.verts]
cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
k = 1.78 / max(v.co.z for v in bm.verts)
for v in bm.verts:
    v.co = Vector(((v.co.x - cx) * k, (v.co.y - cy) * k, v.co.z * k))
bm.to_mesh(ob.data)
bm.free()
ob.location = (0, 0, 0)
dec = ob.modifiers.new("dec", "DECIMATE")
dec.ratio = 0.35
bpy.context.view_layer.objects.active = ob
bpy.ops.object.modifier_apply(modifier="dec")
for p in ob.data.polygons:
    p.use_smooth = True
_BASE = np.empty(len(ob.data.vertices) * 3)
ob.data.vertices.foreach_get("co", _BASE)
_BASE = _BASE.reshape(-1, 3)


def set_pose(arms, mood="neutral", **head):
    """Poses the scan from its A-pose: arms {side: directions} (marco_rig.relaxed / pocket), mood, head angles."""
    co = marco_rig.pose(marco_rig.expression(_BASE, mood), arms, **head)
    ob.data.vertices.foreach_set("co", co.ravel())
    ob.data.update()


RELAXED = {1: marco_rig.relaxed(1), -1: marco_rig.relaxed(-1)}
HERO = {1: marco_rig.pocket(1), -1: marco_rig.relaxed(-1)}
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
sc.render.film_transparent = True
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
sc.view_settings.exposure = -0.1
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.5, 0.45, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
TOP = 1.78
FRONT = Vector((0, -1, 0))     # the scan faces -Y
for loc, energy, size, col in (((2.1, -2.8, 3.4), 1250, 2.0, (1.0, 0.9, 0.76)),
                               ((-2.5, 2.0, 2.6), 450, 1.5, (0.65, 0.78, 1.0)),
                               ((-2.5, -2.5, 1.5), 140, 4.0, (1, 0.97, 0.95))):
    ld = bpy.data.lights.new("l", "AREA")
    ld.energy, ld.size, ld.color = energy, size, col
    lo = bpy.data.objects.new("l", ld)
    lo.location = loc
    lo.rotation_euler = (Vector((0, 0, 1.2)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(lo)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.sensor_fit = "VERTICAL"
cam.data.sensor_height = 24


def shot(name, res, span, centre_z, turn, lens=85, ortho_up=0.05):
    sc.render.resolution_x, sc.render.resolution_y = res
    if PREVIEW:
        sc.render.resolution_x, sc.render.resolution_y = res[0] // 3, res[1] // 3
    d = (span / 2) / (12 / lens)
    a = math.radians(turn)
    fwd = Vector((math.sin(a), -math.cos(a), 0))
    tgt = Vector((0, 0, centre_z))
    cam.location = tgt + fwd * d + Vector((0, 0, ortho_up))
    cam.data.lens = lens
    cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(OUT, name)
    bpy.ops.render.render(write_still=True)


# contact shadow: a shadow-catcher disc under the feet (only on the body render)
bpy.ops.mesh.primitive_circle_add(radius=1.3, fill_type="NGON", location=(0, 0, 0.001))
ground = bpy.context.active_object
ground.is_shadow_catcher = True
ground.visible_glossy = ground.visible_diffuse = False
# sun as in dealership3d.py (warm, 50 degrees up) so his shadow falls like the parked cars'
sun = bpy.data.lights.new("sun", "SUN")
sun.energy, sun.color, sun.angle = 1.6, (1.0, 0.9, 0.76), math.radians(3)
so = bpy.data.objects.new("sun", sun)
so.rotation_euler = (math.radians(40), 0, math.radians(-150))
sc.collection.objects.link(so)
# full body: eye-level-ish camera, slight three-quarter (people3d.py's framing); arms relaxed at his sides
set_pose(RELAXED, head_roll=2.5)
shot("marco_body.png", (680, 1100), 2.05, 0.93, 13, ortho_up=0.35)
ground.hide_render = True
# hero: head to mid-thigh, slight three-quarter, one hand at his pocket, head a touch tilted
set_pose(HERO, head_roll=3.5, head_pitch=1.5)
shot("marco_hero.png", (1100, 1500), 1.32, TOP + 0.03 - 0.66, 15)
# portrait: head and shoulders, face centred, same span as people3d.py portraits
set_pose(RELAXED, head_roll=2.5)
shot("marco_portrait.png", (720, 900), 0.62, TOP + 0.05 - 0.31, 10)
# faces: neutral; happy = chin up, mouth corners lifted, warmer key; angry = brows down and knit, head down, cooler key
key = [o for o in sc.objects if o.type == "LIGHT" and o.data.type == "AREA"][0]
for mood, head, col, energy in (("neutral", dict(head_roll=2.5), (1.0, 0.9, 0.76), 1250),
                                ("happy", dict(head_roll=4.0, head_pitch=5.0), (1.0, 0.84, 0.64), 1400),
                                ("angry", dict(head_roll=-1.0, head_pitch=-7.0, head_yaw=-3.0), (0.9, 0.9, 0.95), 1100)):
    set_pose(RELAXED, mood, **head)
    key.data.color, key.data.energy = col, energy
    shot("marco_face_%s.png" % mood, (384, 384), 0.34, TOP - 0.13 - (0.01 if mood == "angry" else 0.0), 10)
