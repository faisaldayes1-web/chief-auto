"""Exports a few Rocketbox avatars (MIT) as light, rigged, animated GLBs for the real-time showroom.

Each GLB keeps the Bip01 skeleton and carries three looping actions keyed procedurally here: "idle" (breathing,
weight shift), "walk" (1.0 s stride) and "browse" (hands behind back, head lowered toward a car).
Meshes are decimated and textures shrunk to 512 px so the web build stays light.

Usage (bpy venv):  python -I tools/people_glb.py <rocketbox_dir>:<extra_dir> <out_dir> [Avatar_Name ...]
Writes <out>/<pid>.glb with pid from tools/people_map.json.
"""
import json
import math
import os
import sys

import bpy  # noqa: I001
from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = ["Female_Adult_01", "Female_Adult_04", "Female_Adult_08", "Female_Adult_11",
           "Male_Adult_02", "Male_Adult_04", "Male_Adult_08", "Business_Male_02"]
TEX = 512
RATIO = 0.45
FPS = 30


def find_folder(roots, name):
    for r in roots:
        p = os.path.join(r, name)
        if os.path.isdir(p):
            return p
    raise SystemExit("no avatar " + name)


def small_image(path, tmp):
    img = bpy.data.images.load(path)
    img.scale(TEX, TEX)
    has_alpha = "opacity" in os.path.basename(path)
    out = os.path.join(tmp, os.path.basename(path).rsplit(".", 1)[0] + (".png" if has_alpha else ".jpg"))
    img.filepath_raw = out
    img.file_format = "PNG" if has_alpha else "JPEG"
    img.save()
    bpy.data.images.remove(img)
    return bpy.data.images.load(out)


def simple_material(m, folder, tmp):
    base = m.name.split(".")[0]
    part = base.split("_")[-1]
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    bsdf.inputs["Roughness"].default_value = 0.75 if part != "opacity" else 0.6
    bsdf.inputs["Specular IOR Level"].default_value = 0.3
    col = os.path.join(folder, f"{base}_color.tga")
    if os.path.exists(col):
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = small_image(col, tmp)
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if part == "opacity":
            nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
            m.blend_method = "CLIP"
            m.alpha_threshold = 0.5


def facing(arm):
    mw = arm.matrix_world
    pel = mw @ arm.pose.bones["Bip01 Pelvis"].head
    lx = mw @ arm.pose.bones["Bip01 L UpperArm"].head
    rx = mw @ arm.pose.bones["Bip01 R UpperArm"].head
    right = (rx - lx).normalized()
    fwd = right.cross(Vector((0, 0, 1))).normalized()
    eye = mw @ arm.pose.bones["Bip01 Head"].head + Vector((0, 0, 0))
    nose = mw @ arm.pose.bones["Bip01 LEye"].head
    if (nose - eye).dot(fwd) < 0:
        fwd = -fwd
    right = Vector((0, 0, 1)).cross(fwd).normalized() * -1  # right-handed: right x up = fwd
    if right.cross(Vector((0, 0, 1))).dot(fwd) < 0:
        right = -right
    return fwd, right


def rot_about(arm, bone, axis_w, angle):
    """Rotates a pose bone about its head, around a world axis (armature has identity-ish world rotation)."""
    pb = arm.pose.bones[bone]
    bpy.context.view_layer.update()
    mw3 = arm.matrix_world.to_3x3()
    ax = (mw3.inverted() @ axis_w).normalized()
    rot = Matrix.Rotation(angle, 4, ax)
    h = pb.head.copy()
    pb.matrix = Matrix.Translation(h) @ rot @ Matrix.Translation(-h) @ pb.matrix
    bpy.context.view_layer.update()


def aim(arm, bone, child, direction):
    pb = arm.pose.bones[bone]
    bpy.context.view_layer.update()
    mw = arm.matrix_world
    cur = ((mw @ arm.pose.bones[child].head) - (mw @ pb.head)).normalized()
    q = cur.rotation_difference(direction.normalized())
    rot = (mw.inverted().to_3x3() @ q.to_matrix() @ mw.to_3x3()).to_4x4()
    h = pb.head.copy()
    pb.matrix = Matrix.Translation(h) @ rot @ Matrix.Translation(-h) @ pb.matrix
    bpy.context.view_layer.update()


ANIM_BONES = ["Bip01 Pelvis", "Bip01 Spine", "Bip01 Spine1", "Bip01 Head",
              "Bip01 L Thigh", "Bip01 R Thigh", "Bip01 L Calf", "Bip01 R Calf", "Bip01 L Foot", "Bip01 R Foot",
              "Bip01 L UpperArm", "Bip01 R UpperArm", "Bip01 L Forearm", "Bip01 R Forearm"]


def rest_arms(arm, fwd, right, behind=False):
    for side, sgn in (("L", -1), ("R", 1)):
        if behind:
            aim(arm, f"Bip01 {side} UpperArm", f"Bip01 {side} Forearm", right * 0.18 * sgn - fwd * 0.35 + Vector((0, 0, -1)))
            aim(arm, f"Bip01 {side} Forearm", f"Bip01 {side} Hand", -right * 0.9 * sgn - fwd * 0.4 + Vector((0, 0, -0.2)))
        else:
            aim(arm, f"Bip01 {side} UpperArm", f"Bip01 {side} Forearm", right * 0.16 * sgn + fwd * 0.03 + Vector((0, 0, -1)))
            aim(arm, f"Bip01 {side} Forearm", f"Bip01 {side} Hand", right * 0.06 * sgn + fwd * 0.3 + Vector((0, 0, -1)))


def make_action(arm, name, frames, pose_fn, pelvis_z0):
    act = bpy.data.actions.new(name)
    arm.animation_data.action = act
    for f in range(frames + 1):
        t = f / frames
        bpy.ops.pose.select_all(action="SELECT")
        bpy.ops.pose.transforms_clear()
        bpy.context.view_layer.update()
        pose_fn(t)
        for bn in ANIM_BONES:
            pb = arm.pose.bones.get(bn)
            if pb is None:
                continue
            pb.keyframe_insert("rotation_quaternion", frame=f + 1)
            if bn == "Bip01 Pelvis":
                pb.keyframe_insert("location", frame=f + 1)
    arm.animation_data.action = None
    act.use_fake_user = True
    trk = arm.animation_data.nla_tracks.new()
    trk.name = name
    trk.strips.new(name, 1, act)
    return act


def build(folder, out_path, tmp):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=os.path.join(folder, os.path.basename(folder) + ".fbx"))
    arm = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"][0]
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for ob in meshes:
        if ob.data.shape_keys:
            ob.shape_key_clear()
        for slot in ob.material_slots:
            if slot.material:
                simple_material(slot.material, folder, tmp)
        for p in ob.data.polygons:
            p.use_smooth = True
        mod = ob.modifiers.new("dec", "DECIMATE")
        mod.ratio = RATIO
        bpy.context.view_layer.objects.active = ob
        # the decimate must sit before the armature modifier
        while ob.modifiers.find("dec") > 0:
            bpy.ops.object.modifier_move_up(modifier="dec")
        bpy.ops.object.modifier_apply(modifier="dec")
    bpy.context.view_layer.objects.active = arm
    arm.animation_data_create()
    bpy.ops.object.mode_set(mode="POSE")
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
    fwd, right = facing(arm)
    pel = arm.pose.bones["Bip01 Pelvis"]

    def walk(t):
        ph = t * math.tau
        s = math.sin(ph)
        pel.location = pel.location + Vector((0, 0, 0))
        rot_about(arm, "Bip01 Pelvis", Vector((0, 0, 1)), 0.06 * s)
        rest_arms(arm, fwd, right)
        # legs: positive angle about `right` swings a hanging limb backward
        rot_about(arm, "Bip01 L Thigh", right, -0.42 * s)
        rot_about(arm, "Bip01 R Thigh", right, 0.42 * s)
        rot_about(arm, "Bip01 L Calf", right, 0.15 + 0.55 * max(0.0, math.sin(ph + 1.3)))
        rot_about(arm, "Bip01 R Calf", right, 0.15 + 0.55 * max(0.0, math.sin(ph + 1.3 + math.pi)))
        rot_about(arm, "Bip01 L Foot", right, -0.15 * s)
        rot_about(arm, "Bip01 R Foot", right, 0.15 * s)
        rot_about(arm, "Bip01 L UpperArm", right, 0.32 * s)
        rot_about(arm, "Bip01 R UpperArm", right, -0.32 * s)
        rot_about(arm, "Bip01 L Forearm", right, -0.25)
        rot_about(arm, "Bip01 R Forearm", right, -0.25)
        rot_about(arm, "Bip01 Spine1", Vector((0, 0, 1)), -0.08 * s)

    def idle(t):
        ph = t * math.tau
        rest_arms(arm, fwd, right)
        rot_about(arm, "Bip01 Spine", right, 0.015 * math.sin(ph))
        rot_about(arm, "Bip01 Pelvis", fwd, 0.025 * math.sin(ph))
        rot_about(arm, "Bip01 Head", Vector((0, 0, 1)), 0.12 * math.sin(ph))

    def browse(t):
        ph = t * math.tau
        rest_arms(arm, fwd, right, behind=True)
        rot_about(arm, "Bip01 Spine1", right, -0.12)
        rot_about(arm, "Bip01 Head", right, -0.22)
        rot_about(arm, "Bip01 Head", Vector((0, 0, 1)), 0.25 * math.sin(ph))

    z0 = pel.location.z
    make_action(arm, "walk", 30, walk, z0)
    make_action(arm, "idle", 120, idle, z0)
    make_action(arm, "browse", 150, browse, z0)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB", export_animations=True,
                              export_animation_mode="NLA_TRACKS", export_image_format="AUTO",
                              export_morph=False, export_apply=False, export_yup=True)


def main():
    roots = sys.argv[1].split(":")
    out = sys.argv[2]
    names = sys.argv[3:] or DEFAULT
    pmap = json.load(open(os.path.join(HERE, "people_map.json")))
    tmp = os.path.join(out, "_tex")
    os.makedirs(tmp, exist_ok=True)
    for n in names:
        build(find_folder(roots, n), os.path.join(out, pmap[n] + ".glb"), tmp)
        print("wrote", pmap[n], flush=True)


main()
