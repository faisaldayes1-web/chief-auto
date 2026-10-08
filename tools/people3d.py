"""Renders the game's people from the Microsoft Rocketbox avatar library (MIT license) with Blender Cycles.

For every avatar: a full-body standing render (transparent), head-and-shoulders faces in three moods
(happy / neutral / angry) made by moving the face rig, and one upper-body portrait (head to mid-chest, same camera
framing and lights for everyone) used for dialogue, thumbnails and cards.

Usage (bpy venv):  python -I tools/people3d.py <rocketbox_dir>[:<more_dirs>] <out_dir> [Avatar_Name | staff_pid ...]
Writes <out>/<pid>_body.png, <out>/<pid>_face_<mood>.png and <out>/<pid>_portrait.png; pid comes from
tools/people_map.json. Staff pids (marco, maruchan; see STAFF) need STAFF_TEX=<dir written by people_staff_tex.py>.
PARTS=body,face,portrait (default all) limits what is rendered. PARTS=hero alone renders <pid>_hero.png instead:
the person large, head to mid-thigh, arms crossed (the Marco screen).
"""
import json
import math
import os
import sys

import bpy  # noqa: I001
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = int(os.environ.get("SAMPLES", 64))
PARTS = os.environ.get("PARTS", "body,face,portrait").split(",")

# Named staff built on a Rocketbox base avatar with recombined textures (tools/people_staff_tex.py) and props.
STAFF = {
    "marco": {"base": "Male_Adult_01", "legs": "Business_Male_01", "hair_cards": False, "glasses": "clear",
              "watch": True},
    "maruchan": {"base": "Male_Adult_01", "legs": "Business_Male_01", "hair_cards": False,
                 "hair_from": "Female_Adult_03", "glasses": "sun", "watch": False},
}
SRCS = []


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def load_avatar(folder, override=None):
    """override: {"head"|"body"|"opacity": texture path} replaces those textures."""
    override = override or {}
    name = os.path.basename(folder.rstrip("/"))
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.fbx(filepath=os.path.join(folder, name + ".fbx"))
    new = [o for o in bpy.context.scene.objects if o not in before]
    arm = [o for o in new if o.type == "ARMATURE"][0]
    meshes = [o for o in new if o.type == "MESH"]
    for ob in meshes:
        for slot in ob.material_slots:
            m = slot.material
            base = m.name.split(".")[0]
            tex = os.path.join(folder, base + "_color.tga")
            part = base.split("_")[-1]
            if part in override:
                tex = override[part]
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


def cross_arms(arm, seed=0):
    """T-pose -> arms crossed over the chest (the Marco screen's hero pose): upper arms down and a little forward,
    forearms across the body, the left one in front of and above the right."""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    mw = arm.matrix_world
    lx = (mw @ arm.pose.bones["Bip01 L UpperArm"].head).x
    fwd, _ = facing(arm)
    fy = 1 if fwd.y > 0 else -1
    for side, sgn in (("L", 1 if lx > 0 else -1), ("R", -1 if lx > 0 else 1)):
        front = side == "L"
        _aim_bone(arm, f"Bip01 {side} UpperArm", f"Bip01 {side} Forearm",
                  Vector((0.1 * sgn, fy * (0.8 if front else 0.7), -1)))
        _aim_bone(arm, f"Bip01 {side} Forearm", f"Bip01 {side} Hand",
                  Vector((-sgn, fy * (0.14 if front else -0.06), 0.24 if front else 0.12)))
        _aim_bone(arm, f"Bip01 {side} Hand", f"Bip01 {side} Finger2",
                  Vector((-sgn * 0.5, -fy * (0.25 if front else 0.55), -0.2 if front else 0.05)))
    bpy.ops.object.mode_set(mode="OBJECT")


FACE_BONES = ("Bip01 LMouthCorner", "Bip01 RMouthCorner", "Bip01 LInnerEyebrow", "Bip01 RInnerEyebrow",
              "Bip01 LOuterEyebrow", "Bip01 ROuterEyebrow", "Bip01 LCheek", "Bip01 RCheek")


def set_mood(arm, mood):
    """Moves the mouth corners and brows (offsets in metres, world up): +1 happy, -1 angry, in between scales."""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    to_arm = arm.matrix_world.inverted().to_3x3()
    moves = {}
    if mood > 0:
        moves = {"MouthCorner": Vector((0, 0, 0.006)), "InnerEyebrow": Vector((0, 0, 0.002)), "Cheek": Vector((0, 0, 0.003))}
    elif mood < 0:
        moves = {"MouthCorner": Vector((0, 0, -0.005)), "InnerEyebrow": Vector((0, 0, -0.005)),
                 "OuterEyebrow": Vector((0, 0, 0.002))}
    amt = min(1.0, abs(mood))
    for b in FACE_BONES:
        if b not in arm.pose.bones:
            continue
        for key, v in moves.items():
            if key in b:
                d = to_arm @ (v * amt)
                if key == "MouthCorner" and mood > 0:
                    # smile corners also pull outwards
                    side = 1 if b.startswith("Bip01 L") else -1
                    d = d + to_arm @ (Vector((0.003 * side * amt, 0, 0)))
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


# ------------------------------------------------------------------ props for the named staff

def _mat(name, rgb, rough, metal=0.0, alpha=1.0, spec=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Alpha"].default_value = alpha
    b.inputs["Specular IOR Level"].default_value = spec
    return m


def _mesh(name, verts, faces, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.data.materials.append(mat)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _beam(name, a, b, w, h, up, mat):
    """A box from a to b, w wide (across, perpendicular to up) and h tall (along up)."""
    d = (b - a).normalized()
    u = (up - d * up.dot(d)).normalized()
    r = d.cross(u).normalized()
    vs = []
    for p in (a, b):
        for su, sr in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
            vs.append(p + u * (h / 2) * su + r * (w / 2) * sr)
    faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    return _mesh(name, vs, faces, mat)


def add_glasses(arm, kind):
    """Rectangular glasses ('clear', thin dark frame) or sunglasses ('sun', dark lenses) in front of the eyes."""
    bpy.context.view_layer.update()
    mw = arm.matrix_world
    le = mw @ arm.pose.bones["Bip01 LEye"].head
    re = mw @ arm.pose.bones["Bip01 REye"].head
    fwd, _ = facing(arm)
    up = Vector((0, 0, 1))
    across = (le - re).normalized()
    fwd = (fwd - across * fwd.dot(across)).normalized()
    if kind == "sun":
        lw, lh, ft, dz, ahead = 0.054, 0.04, 0.0045, -0.003, 0.03
        frame = _mat("sunframe", (0.012, 0.012, 0.014), 0.25, spec=0.6)
        lens = _mat("sunlens", (0.006, 0.006, 0.008), 0.16, alpha=0.97, spec=0.6)
    else:
        lw, lh, ft, dz, ahead = 0.05, 0.03, 0.0032, 0.0, 0.03
        frame = _mat("frame", (0.02, 0.018, 0.018), 0.3, spec=0.6)
        lens = _mat("lens", (0.8, 0.85, 0.9), 0.05, alpha=0.05, spec=0.8)
    wrap = 0.007   # outer edges sit further back, following the face
    corners = {}
    for eye, out in ((le, across), (re, -across)):
        c = eye + fwd * ahead + up * dz
        inner = c - out * (lw / 2 - 0.002)
        outer = c + out * (lw / 2 + 0.002) - fwd * wrap
        cut = 0.006
        pts = [inner + up * (lh / 2 - cut), inner + out * cut * 0.5 + up * (lh / 2),
               outer - out * cut + up * (lh / 2), outer + up * (lh / 2 - cut),
               outer + up * (-lh / 2 + cut), outer - out * cut * 1.5 - up * (lh / 2),
               inner + out * cut * 1.5 - up * (lh / 2), inner + up * (-lh / 2 + cut)]
        for i in range(len(pts)):
            _beam("rim", pts[i], pts[(i + 1) % len(pts)], ft * 0.7, ft, fwd, frame)
        lv = [p - fwd * 0.0005 for p in pts]
        _mesh("lens", lv, [tuple(range(len(lv)))], lens)
        corners[out is across] = (inner + up * (lh / 2 - 0.008), outer + up * (lh / 2 - 0.004), out)
    # bridge and temple arms back to the ears
    _beam("bridge", corners[True][0], corners[False][0], ft * 0.8, ft * 0.8, fwd, frame)
    for k in (True, False):
        _, outer, out = corners[k]
        hinge = outer + out * 0.006 - fwd * 0.006
        _beam("hinge", outer, hinge, ft, ft, up, frame)
        _beam("temple", hinge, hinge - fwd * 0.1 + out * 0.004 - up * 0.008, ft * 0.8, ft * 1.1, up, frame)


def add_watch(arm):
    """A gold watch on the left wrist, face outwards."""
    bpy.context.view_layer.update()
    mw = arm.matrix_world
    hand = mw @ arm.pose.bones["Bip01 L Hand"].head
    fore = mw @ arm.pose.bones["Bip01 L Forearm"].head
    axis = (hand - fore).normalized()
    c = hand - axis * 0.03
    fwd, pel = facing(arm)
    lat = (c - pel)
    lat = (lat - axis * lat.dot(axis) - Vector((0, 0, lat.z))).normalized()
    b = lat.cross(axis).normalized()
    gold = _mat("gold", (0.9, 0.68, 0.3), 0.22, metal=1.0)
    dial = _mat("dial", (0.85, 0.82, 0.74), 0.3, spec=0.6)
    n = 24
    vs, faces = [], []
    rx, ry, wdt = 0.03, 0.024, 0.016
    for i in range(n):
        t = 2 * math.pi * i / n
        rad = lat * math.cos(t) * rx + b * math.sin(t) * ry
        for s_ in (-1, 1):
            vs.append(c + rad + axis * (wdt / 2) * s_)
    for i in range(n):
        j = (i + 1) % n
        faces.append((2 * i, 2 * j, 2 * j + 1, 2 * i + 1))
    _mesh("band", vs, faces, gold)
    # watch head: a short gold cylinder with a pale dial on the outside of the wrist
    top = c + lat * (rx + 0.002)
    vs, faces = [], []
    for i in range(n):
        t = 2 * math.pi * i / n
        rad = axis * math.cos(t) * 0.017 + b * math.sin(t) * 0.017
        vs += [top + rad - lat * 0.004, top + rad + lat * 0.005]
    for i in range(n):
        j = (i + 1) % n
        faces.append((2 * i, 2 * j, 2 * j + 1, 2 * i + 1))
    _mesh("case", vs, faces, gold)
    _mesh("dial", [v + lat * 0.0003 for v in vs[1::2]], [tuple(range(n))], dial)


def drop_hair_cards(meshes):
    """Removes the alpha hair cards (the *_opacity material), leaving the hair painted on the head texture."""
    import bmesh
    for ob in meshes:
        idx = {i for i, sl in enumerate(ob.material_slots) if sl.material.name.split(".")[0].endswith("opacity")}
        if not idx:
            continue
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in idx], context="FACES")
        bm.to_mesh(ob.data)
        bm.free()


def swap_legs(arm, meshes, donor_folder):
    """Replaces the legs (everything below the shirt hem, in the rest pose) with another avatar's, so a polo-and-shorts
    body can wear long trousers and shoes. Rocketbox avatars share one skeleton, and the legs are not posed."""
    import bmesh
    ob = meshes[0]
    mw = ob.matrix_world
    body = [i for i, sl in enumerate(ob.material_slots) if sl.material.name.split(".")[0].endswith("body")][0]
    uv = ob.data.uv_layers.active.data
    # shirt hem: lowest point of the torso panel (the middle column of the body texture)
    hem = min((mw @ ob.data.vertices[ob.data.loops[li].vertex_index].co).z
              for p in ob.data.polygons if p.material_index == body for li in p.loop_indices
              if 0.42 < uv[li].uv.x < 0.58)
    cut = hem - 0.012
    # the shorts (top corners of the body sheet) are wider than the shirt hem: remove them altogether
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    shorts = [f for f in bm.faces if f.material_index == body and
              all(lp[uvl].uv.y > 0.74 and (lp[uvl].uv.x < 0.31 or lp[uvl].uv.x > 0.69) for lp in f.loops)]
    bmesh.ops.delete(bm, geom=shorts, context="FACES")
    bm.to_mesh(ob.data)
    bm.free()
    d_arm, d_meshes = load_avatar(donor_folder)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if all((mw @ v.co).z < cut for v in f.verts)], context="FACES")
    bm.to_mesh(ob.data)
    bm.free()
    # the donor keeps its trousers (the outer columns of its sheet) up to a little above the cut, under the shirt, so no
    # gap shows at the hem; of the rest (jacket in the middle columns) only what is well below, i.e. the shoes
    legs = d_meshes[0]
    lmw = legs.matrix_world
    bm = bmesh.new()
    bm.from_mesh(legs.data)
    uvl = bm.loops.layers.uv.active

    def keep(f):
        zmax = max((lmw @ v.co).z for v in f.verts)
        trousers = all(lp[uvl].uv.x < 0.28 or lp[uvl].uv.x > 0.72 for lp in f.loops)
        if trousers:
            return zmax <= cut + 0.05
        return zmax <= cut - 0.15   # the jacket skirt and its pocket flaps go; shoes stay
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not keep(f)], context="FACES")
    bm.to_mesh(legs.data)
    bm.free()
    wm = legs.matrix_world.copy()
    legs.parent = arm
    legs.matrix_world = wm
    for m in legs.modifiers:
        if m.type == "ARMATURE":
            m.object = arm
    bpy.data.objects.remove(d_arm)
    for o in d_meshes[1:]:
        bpy.data.objects.remove(o)
    meshes.append(legs)


def transplant_hair(arm, meshes, donor_folder, tint=(0.05, 0.047, 0.045)):
    """Gives the avatar another avatar's hair cards (Maruchan's long hair), fitted to this skull and dyed near-black.
    Run in the rest pose, before relax_pose."""
    import bmesh
    hp = head_pos(arm)
    top = head_top(meshes, hp)
    d_arm, d_meshes = load_avatar(donor_folder)
    dhp = head_pos(d_arm)
    dob = d_meshes[0]
    dmw = dob.matrix_world
    slots = [sl.material.name.split(".")[0] for sl in dob.material_slots]
    hidx = [i for i, n in enumerate(slots) if n.endswith("head")][0]
    oidx = [i for i, n in enumerate(slots) if n.endswith("opacity")][0]
    dtop = max((dmw @ dob.data.vertices[v].co).z for p in dob.data.polygons if p.material_index == hidx
               for v in p.vertices)
    scale = (top - hp.z) / (dtop - dhp.z) * 1.03
    bm = bmesh.new()
    bm.from_mesh(dob.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != oidx], context="FACES")
    bm.to_mesh(dob.data)
    bm.free()
    inv = dmw.inverted()
    for v in dob.data.vertices:
        v.co = inv @ (hp + (dmw @ v.co - dhp) * scale)
    nt = dob.material_slots[oidx].material.node_tree
    bsdf = [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"][0]
    img = [n for n in nt.nodes if n.type == "TEX_IMAGE"][0]
    mul = nt.nodes.new("ShaderNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1
    mul.inputs[2].default_value = (*tint, 1)
    nt.links.new(img.outputs["Color"], mul.inputs[1])
    nt.links.new(mul.outputs[0], bsdf.inputs["Base Color"])
    wm = dob.matrix_world.copy()
    dob.parent = arm
    dob.matrix_world = wm
    for m in dob.modifiers:
        if m.type == "ARMATURE":
            m.object = arm
    bpy.data.objects.remove(d_arm)
    for o in d_meshes[1:]:
        bpy.data.objects.remove(o)
    meshes.append(dob)


def head_top(meshes, hp):
    """Highest point of the posed mesh (hair included) above the head."""
    dg = bpy.context.evaluated_depsgraph_get()
    top = hp.z
    for ob in meshes:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        mw = ob.matrix_world
        for v in me.vertices:
            w = mw @ v.co
            if (w.x - hp.x) ** 2 + (w.y - hp.y) ** 2 < 0.04 and w.z > top:
                top = w.z
        ev.to_mesh_clear()
    return top


PORTRAIT_SPAN = 0.62     # metres from just above the head down to mid-chest, the same for everyone
PORTRAIT_LENS = 85


def render_portrait(arm, meshes, cam, out, pid):
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 720, 900
    cam.data.sensor_fit = "VERTICAL"
    cam.data.sensor_height = 24
    fwd, _ = facing(arm)
    side = fwd.cross(Vector((0, 0, 1))).normalized()
    hp = head_pos(arm)
    top = head_top(meshes, hp)
    tgt = Vector((hp.x, hp.y, top + 0.05 - PORTRAIT_SPAN / 2))
    d = (PORTRAIT_SPAN / 2) / (12 / PORTRAIT_LENS)
    eye_z = (arm.matrix_world @ arm.pose.bones["Bip01 LEye"].head).z
    pos = tgt + fwd * d + side * d * 0.17
    pos.z = eye_z   # camera at eye height looking slightly down at the frame centre
    look(cam, pos, tgt, PORTRAIT_LENS)
    reset_face(arm)
    set_mood(arm, 0.45)
    render(os.path.join(out, f"{pid}_portrait.png"))
    cam.data.sensor_fit = "AUTO"
    cam.data.sensor_width = 36


HERO_SPAN = 1.32   # metres from just above the head to about mid-thigh


def render_hero(arm, meshes, cam, out, pid):
    """Large standing figure for the Marco screen: head to mid-thigh, slight three-quarter turn, arms crossed."""
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 1100, 1500
    cam.data.sensor_fit = "VERTICAL"
    cam.data.sensor_height = 24
    fwd, _ = facing(arm)
    side = fwd.cross(Vector((0, 0, 1))).normalized()
    hp = head_pos(arm)
    top = head_top(meshes, hp)
    tgt = Vector((hp.x, hp.y, top + 0.03 - HERO_SPAN / 2))
    d = (HERO_SPAN / 2) / (12 / PORTRAIT_LENS)
    eye_z = (arm.matrix_world @ arm.pose.bones["Bip01 LEye"].head).z
    pos = tgt + fwd * d + side * d * 0.26
    pos.z = eye_z - 0.1
    look(cam, pos, tgt, PORTRAIT_LENS)
    reset_face(arm)
    set_mood(arm, 0.6)
    render(os.path.join(out, f"{pid}_hero.png"))
    # head box in render pixels (top of hair to chin, ear to ear), for placing the figure in the UI
    from bpy_extras.object_utils import world_to_camera_view
    dg = bpy.context.evaluated_depsgraph_get()
    chin = (arm.matrix_world @ arm.pose.bones["Bip01 Neck"].head).z + 0.035
    pts = []
    for ob in meshes:
        heads = {i for i, sl in enumerate(ob.material_slots) if sl.material.name.split(".")[0].endswith(("head", "opacity"))}
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        for poly in me.polygons:
            if poly.material_index in heads:
                for vi in poly.vertices:
                    w = ob.matrix_world @ me.vertices[vi].co
                    if w.z > chin:
                        pts.append(world_to_camera_view(sc, cam, w))
        ev.to_mesh_clear()
    rx, ry = sc.render.resolution_x, sc.render.resolution_y
    xs = [p.x * rx for p in pts]
    ys = [(1 - p.y) * ry for p in pts]
    with open(os.path.join(out, f"{pid}_hero_head.json"), "w") as f:
        json.dump({"head": [min(xs), min(ys), max(xs), max(ys)], "size": [rx, ry]}, f)


def do_avatar(folder, out, pid, staff=None):
    reset()
    override = {}
    if staff:
        tdir = os.path.join(os.environ["STAFF_TEX"], pid)
        for part in ("head", "body", "opacity"):
            f = os.path.join(tdir, part + "_color.png")
            if os.path.exists(f):
                override[part] = f
    arm, meshes = load_avatar(folder, override)
    if staff and not staff["hair_cards"]:
        drop_hair_cards(meshes)
    if staff and staff.get("legs"):
        swap_legs(arm, meshes, find(SRCS, staff["legs"]))
    if staff and staff.get("hair_from"):
        transplant_hair(arm, meshes, find(SRCS, staff["hair_from"]))
    if PARTS == ["hero"]:
        cross_arms(arm)
    else:
        relax_pose(arm)
    if staff and staff.get("glasses"):
        add_glasses(arm, staff["glasses"])
    if staff and staff.get("watch"):
        add_watch(arm)
    cam = studio((520, 1100))
    fwd, pel = facing(arm)
    side = fwd.cross(Vector((0, 0, 1))).normalized()
    hz = head_pos(arm).z
    # full body: eye-level-ish camera, slight three-quarter
    tgt = Vector((pel.x, pel.y, hz * 0.52))
    pos = tgt + fwd * 4.7 + side * 1.1 + Vector((0, 0, 0.35))
    look(cam, pos, tgt, 85)
    set_mood(arm, 0)
    if PARTS == ["hero"]:
        render_hero(arm, meshes, cam, out, pid)
        return
    if "body" in PARTS:
        render(os.path.join(out, f"{pid}_body.png"))
    if "portrait" in PARTS:
        render_portrait(arm, meshes, cam, out, pid)
    if "face" not in PARTS:
        return
    # faces
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


def find(srcs, name):
    for d in srcs:
        if os.path.isdir(os.path.join(d, name)):
            return os.path.join(d, name)
    raise SystemExit("avatar not found: " + name)


def main():
    srcs, out = sys.argv[1].split(":"), sys.argv[2]
    SRCS[:] = srcs
    os.makedirs(out, exist_ok=True)
    mapping = json.load(open(os.path.join(HERE, "people_map.json")))
    names = sys.argv[3:] or list(mapping) + list(STAFF)
    for name in names:
        if name in STAFF:
            do_avatar(find(srcs, STAFF[name]["base"]), out, name, STAFF[name])
        else:
            do_avatar(find(srcs, name), out, mapping[name])


if __name__ == "__main__":
    main()
