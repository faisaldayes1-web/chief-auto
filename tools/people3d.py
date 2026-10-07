"""Renders the game's people from the Microsoft Rocketbox avatar library (MIT license) with Blender Cycles.

For every avatar: a full-body standing render (transparent, with contact shadow) and head-and-shoulders
portraits in three moods (happy / neutral / angry) made by moving the face rig.

Usage (bpy venv):  python tools/people3d.py <rocketbox_dir> <out_dir> [Avatar_Name ...]
Writes <out>/<pid>_body.png and <out>/<pid>_face_<mood>.png; pid comes from tools/people_map.json.
"""
import json
import math
import os
import sys

import bpy  # noqa: I001
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = int(os.environ.get("SAMPLES", 64))


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def load_avatar(folder):
    name = os.path.basename(folder.rstrip("/"))
    bpy.ops.import_scene.fbx(filepath=os.path.join(folder, name + ".fbx"))
    arm = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"][0]
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for ob in meshes:
        for slot in ob.material_slots:
            m = slot.material
            base = m.name.split(".")[0]
            tex = os.path.join(folder, base + "_color.tga")
            m.use_nodes = True
            nt = m.node_tree
            nt.nodes.clear()
            out = nt.nodes.new("ShaderNodeOutputMaterial")
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
            nt.links.new(bsdf.outputs[0], out.inputs[0])
            bsdf.inputs["Roughness"].default_value = 0.55
            if os.path.exists(tex):
                img = nt.nodes.new("ShaderNodeTexImage")
                img.image = bpy.data.images.load(tex)
                nt.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])
                if base.endswith("opacity"):
                    nt.links.new(img.outputs["Alpha"], bsdf.inputs["Alpha"])
                    bsdf.inputs["Roughness"].default_value = 0.45
            if base.endswith("head"):
                bsdf.inputs["Subsurface Weight"].default_value = 0.12
                bsdf.inputs["Subsurface Radius"].default_value = (0.9, 0.35, 0.2)
                bsdf.inputs["Subsurface Scale"].default_value = 0.008
                bsdf.inputs["Roughness"].default_value = 0.45
            for p in ob.data.polygons:
                p.use_smooth = True
    return arm, meshes


def _aim_bone(arm, bone, child, direction):
    """Rotates a pose bone (about its head) so the limb towards `child` points along a world direction.
    FBX bone tails are arbitrary, so the limb runs from this bone's head to the child's head."""
    pb = arm.pose.bones[bone]
    bpy.context.view_layer.update()
    mw = arm.matrix_world
    head = mw @ pb.head
    tail = mw @ arm.pose.bones[child].head
    cur = (tail - head).normalized()
    want = direction.normalized()
    q = cur.rotation_difference(want)
    # rotation in armature space about the bone head
    rot = (mw.inverted().to_3x3() @ q.to_matrix() @ mw.to_3x3()).to_4x4()
    h = pb.head.copy()
    m = Matrix.Translation(h) @ rot @ Matrix.Translation(-h) @ pb.matrix
    pb.matrix = m
    bpy.context.view_layer.update()


def relax_pose(arm, seed=0):
    """T-pose -> natural standing pose with the arms down."""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    # find which side is +X in world space
    mw = arm.matrix_world
    lx = (mw @ arm.pose.bones["Bip01 L UpperArm"].head).x
    fwd, _ = facing(arm)
    fy = 1 if fwd.y > 0 else -1
    for side, sgn in (("L", 1 if lx > 0 else -1), ("R", -1 if lx > 0 else 1)):
        _aim_bone(arm, f"Bip01 {side} UpperArm", f"Bip01 {side} Forearm", Vector((0.16 * sgn, fy * 0.05, -1)))
        _aim_bone(arm, f"Bip01 {side} Forearm", f"Bip01 {side} Hand", Vector((0.08 * sgn, fy * 0.3, -1)))
    bpy.ops.object.mode_set(mode="OBJECT")


FACE_BONES = ("Bip01 LMouthCorner", "Bip01 RMouthCorner", "Bip01 LInnerEyebrow", "Bip01 RInnerEyebrow",
              "Bip01 LOuterEyebrow", "Bip01 ROuterEyebrow", "Bip01 LCheek", "Bip01 RCheek")


def set_mood(arm, mood):
    """Moves the mouth corners and brows (offsets in metres, world up): +1 happy, -1 angry."""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    to_arm = arm.matrix_world.inverted().to_3x3()
    moves = {}
    if mood > 0:
        moves = {"MouthCorner": Vector((0, 0, 0.006)), "InnerEyebrow": Vector((0, 0, 0.002)), "Cheek": Vector((0, 0, 0.003))}
    elif mood < 0:
        moves = {"MouthCorner": Vector((0, 0, -0.005)), "InnerEyebrow": Vector((0, 0, -0.005)),
                 "OuterEyebrow": Vector((0, 0, 0.002))}
    for b in FACE_BONES:
        if b not in arm.pose.bones:
            continue
        for key, v in moves.items():
            if key in b:
                d = to_arm @ v
                if key == "MouthCorner" and mood > 0:
                    # smile corners also pull outwards
                    side = 1 if b.startswith("Bip01 L") else -1
                    d = d + to_arm @ (Vector((0.003 * side, 0, 0)))
                pb = arm.pose.bones[b]
                pb.matrix = Matrix.Translation(d) @ pb.matrix
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()


def reset_face(arm):
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    for b in FACE_BONES:
        if b in arm.pose.bones:
            arm.pose.bones[b].location = (0, 0, 0)
    bpy.ops.object.mode_set(mode="OBJECT")


def studio(res):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    sc.render.film_transparent = True
    sc.cycles.transparent_max_bounces = 128   # layered hair cards need many alpha bounces
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.5, 0.45, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    # warm key (golden hour), cool rim, soft fill
    for loc, energy, size, col in (((2.2, -3.0, 2.8), 650, 2.5, (1.0, 0.88, 0.75)),
                                   ((-2.5, 2.0, 2.6), 450, 1.5, (0.65, 0.78, 1.0)),
                                   ((-2.5, -2.5, 1.5), 180, 3.0, (1, 1, 1))):
        ld = bpy.data.lights.new("l", "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        lo = bpy.data.objects.new("l", ld)
        lo.location = loc
        lo.rotation_euler = (Vector((0, 0, 1.2)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        sc.collection.objects.link(lo)
    cam = bpy.data.cameras.new("cam")
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return co


def look(cam, pos, target, lens):
    cam.location = pos
    cam.data.lens = lens
    cam.rotation_euler = (Vector(target) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()


def render(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def head_pos(arm):
    mw = arm.matrix_world
    return mw @ arm.pose.bones["Bip01 Head"].head


def facing(arm):
    """World direction the avatar faces (from the eyes)."""
    mw = arm.matrix_world
    pel = mw @ arm.pose.bones["Bip01 Pelvis"].head
    lx = mw @ arm.pose.bones["Bip01 L UpperArm"].head
    rx = mw @ arm.pose.bones["Bip01 R UpperArm"].head
    right = (rx - lx).normalized()
    fwd = right.cross(Vector((0, 0, 1))).normalized()
    eye = mw @ arm.pose.bones["Bip01 LEye"].head
    if (eye - pel).dot(fwd) < 0:
        fwd = -fwd
    return fwd, pel


def do_avatar(folder, out, pid):
    reset()
    arm, meshes = load_avatar(folder)
    relax_pose(arm)
    cam = studio((520, 1100))
    fwd, pel = facing(arm)
    side = fwd.cross(Vector((0, 0, 1))).normalized()
    hz = head_pos(arm).z
    # full body: eye-level-ish camera, slight three-quarter
    tgt = Vector((pel.x, pel.y, hz * 0.52))
    pos = tgt + fwd * 4.7 + side * 1.1 + Vector((0, 0, 0.35))
    look(cam, pos, tgt, 85)
    set_mood(arm, 0)
    render(os.path.join(out, f"{pid}_body.png"))
    # portraits
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 384, 384
    hp = head_pos(arm)
    ftgt = hp + Vector((0, 0, 0.05)) - Vector((0, 0, 0.09))
    fpos = ftgt + fwd * 1.6 + side * 0.28 + Vector((0, 0, 0.04))
    look(cam, fpos, ftgt, 85)
    for mood, val in (("neutral", 0), ("happy", 1), ("angry", -1)):
        reset_face(arm)
        set_mood(arm, val)
        render(os.path.join(out, f"{pid}_face_{mood}.png"))


def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    mapping = json.load(open(os.path.join(HERE, "people_map.json")))
    names = sys.argv[3:] or list(mapping)
    for name in names:
        do_avatar(os.path.join(src, name), out, mapping[name])


if __name__ == "__main__":
    main()
