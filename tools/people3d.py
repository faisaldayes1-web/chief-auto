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
SAMPLES = int(os.environ.get("SAMPLES", 64))                       # bodies and faces
PORTRAIT_SAMPLES = int(os.environ.get("PORTRAIT_SAMPLES", SAMPLES * 3))  # portraits and the hero, seen large
PARTS = os.environ.get("PARTS", "body,face,portrait").split(",")

# Named staff built on a Rocketbox base avatar with recombined textures (tools/people_staff_tex.py) and props.
STAFF = {
    # Marco: short combed-back strand hair (dark, grey at the temples) grown where his texture has hair,
    # Male_Adult_05's older skin detail (normal/specular maps), a stockier build, thin metal glasses, gold watch
    "marco": {"base": "Male_Adult_01", "legs": "Business_Male_01", "legs_tint": 0.6, "hair_cards": False,
              "strand_hair": True, "head_maps": "Male_Adult_05",
              "stocky": True, "glasses": "clear", "watch": True},
    # Maruchan: long straight dark strand hair to the shoulders, combed from a crown parting (long_hair), sunglasses
    "maruchan": {"base": "Male_Adult_01", "legs": "Business_Male_01", "legs_tint": 0.7, "hair_cards": False,
                 "long_hair": True, "head_maps": "Male_Adult_15",
                 "glasses": "sun", "watch": False},
}
SRCS = []


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _img(nt, path, non_color=False):
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = bpy.data.images.load(path, check_existing=True)
    if non_color:
        n.image.colorspace_settings.name = "Non-Color"
    return n


def _map(nt, src, lo_in, hi_in, lo_out, hi_out):
    n = nt.nodes.new("ShaderNodeMapRange")
    n.clamp = True
    n.inputs["From Min"].default_value = lo_in
    n.inputs["From Max"].default_value = hi_in
    n.inputs["To Min"].default_value = lo_out
    n.inputs["To Max"].default_value = hi_out
    nt.links.new(src, n.inputs["Value"])
    return n.outputs["Result"]


# Per material part: roughness where the Rocketbox specular map is 0 -> where it is high, specular level likewise,
# normal-map strength, subsurface, sheen. Skin is soft and translucent, cloth matte with a little sheen, hair glossy
# along the strands.
SURFACES = {
    "head": dict(rough=(0.6, 0.32), spec=(0.3, 0.85), normal=0.75, sss=0.85, sss_radius=(1.0, 0.42, 0.25),
                 sss_scale=0.0045, sheen=0.0),
    "body": dict(rough=(0.88, 0.42), spec=(0.06, 0.6), normal=0.9, sss=0.2, sss_radius=(1.0, 0.42, 0.25),
                 sss_scale=0.004, sheen=0.15),
    "opacity": dict(rough=(0.52, 0.52), spec=(0.4, 0.4), normal=0.0, sss=0.0, sss_radius=(1, 1, 1),
                    sss_scale=0.0, sheen=0.0),
}


def setup_material(m, folder, base, override):
    """Rocketbox textures -> a Principled surface: colour, tangent-space normal map and the specular map driving
    roughness and specular level. override: {"head": colour path, "head_normal": path, ...}."""
    part = base.split("_")[-1]
    cfg = SURFACES.get(part, SURFACES["body"])

    def find(kind):
        p = override.get(part if kind == "color" else part + "_" + kind) or os.path.join(folder, f"{base}_{kind}.tga")
        return p if os.path.exists(p) else None

    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    bsdf.inputs["Roughness"].default_value = cfg["rough"][0]
    bsdf.inputs["Specular IOR Level"].default_value = cfg["spec"][0]
    color = find("color")
    if color:
        img = _img(nt, color)
        nt.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])
        if part == "opacity":
            nt.links.new(img.outputs["Alpha"], bsdf.inputs["Alpha"])
    spec = find("specular")
    if spec and part != "opacity":
        sp = _img(nt, spec, True).outputs["Color"]
        nt.links.new(_map(nt, sp, 0.0, 0.22, *cfg["rough"]), bsdf.inputs["Roughness"])
        nt.links.new(_map(nt, sp, 0.0, 0.22, *cfg["spec"]), bsdf.inputs["Specular IOR Level"])
    normal = find("normal")
    if normal and cfg["normal"] > 0:
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = cfg["normal"]
        tex = _img(nt, normal, True)
        if FLIP_GREEN:
            sep = nt.nodes.new("ShaderNodeSeparateColor")
            comb = nt.nodes.new("ShaderNodeCombineColor")
            inv = nt.nodes.new("ShaderNodeMath")
            inv.operation = "SUBTRACT"
            inv.inputs[0].default_value = 1.0
            nt.links.new(tex.outputs["Color"], sep.inputs[0])
            nt.links.new(sep.outputs[0], comb.inputs[0])
            nt.links.new(sep.outputs[1], inv.inputs[1])
            nt.links.new(inv.outputs[0], comb.inputs[1])
            nt.links.new(sep.outputs[2], comb.inputs[2])
            nt.links.new(comb.outputs[0], nm.inputs["Color"])
        else:
            nt.links.new(tex.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])
    if cfg["sss"]:
        bsdf.subsurface_method = "RANDOM_WALK_SKIN"
        bsdf.inputs["Subsurface Weight"].default_value = cfg["sss"]
        bsdf.inputs["Subsurface Radius"].default_value = cfg["sss_radius"]
        bsdf.inputs["Subsurface Scale"].default_value = cfg["sss_scale"]
    if cfg["sheen"]:
        bsdf.inputs["Sheen Weight"].default_value = cfg["sheen"]
        bsdf.inputs["Sheen Roughness"].default_value = 0.5
    if part == "opacity":
        # strands: anisotropic highlight running along the hair cards
        bsdf.inputs["Anisotropic"].default_value = 0.35
        tg = nt.nodes.new("ShaderNodeTangent")
        tg.direction_type = "UV_MAP"
        nt.links.new(tg.outputs[0], bsdf.inputs["Tangent"])
    return bsdf


FLIP_GREEN = os.environ.get("FLIP_GREEN", "0") == "1"


def load_avatar(folder, override=None):
    """override: {"head"|"body"|"opacity": colour texture, "head_normal", "head_specular", ...} replaces textures."""
    override = override or {}
    name = os.path.basename(folder.rstrip("/"))
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.fbx(filepath=os.path.join(folder, name + ".fbx"))
    new = [o for o in bpy.context.scene.objects if o not in before]
    arm = [o for o in new if o.type == "ARMATURE"][0]
    meshes = [o for o in new if o.type == "MESH"]
    for ob in meshes:
        for slot in ob.material_slots:
            setup_material(slot.material, folder, slot.material.name.split(".")[0], override)
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
    sc.view_settings.exposure = -0.2      # keeps lit skin from blowing out
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.5, 0.45, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.32
    # warm key (golden hour) high and to the figure's left, small enough to throw real form shadows, a cool rim and a
    # weak soft fill so the shadow side keeps some detail
    for loc, energy, size, col in (((2.1, -2.8, 3.4), 1250, 2.0, (1.0, 0.86, 0.72)),
                                   ((-2.5, 2.0, 2.6), 450, 1.5, (0.65, 0.78, 1.0)),
                                   ((-2.5, -2.5, 1.5), 120, 4.0, (1, 0.97, 0.95))):
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


def ground_shadow(meshes, radius=1.3):
    """A shadow-catcher disc under the feet (Cycles writes only the shadow it receives into the alpha channel, the
    film being transparent): the figure gets a soft contact shadow baked into its PNG."""
    import bmesh
    dg = bpy.context.evaluated_depsgraph_get()
    floor = 10.0
    cx = cy = 0.0
    n = 0
    for ob in meshes:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        mw = ob.matrix_world
        for v in me.vertices:
            w = mw @ v.co
            floor = min(floor, w.z)
            cx += w.x
            cy += w.y
            n += 1
        ev.to_mesh_clear()
    me = bpy.data.meshes.new("ground")
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, radius=radius, segments=48)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("ground", me)
    ob.location = (cx / max(n, 1), cy / max(n, 1), floor - 0.002)
    ob.is_shadow_catcher = True
    ob.visible_glossy = False
    ob.visible_diffuse = False
    bpy.context.scene.collection.objects.link(ob)
    return ob


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


def _glass(name, see_through, rough, ior=1.5, refl=1.0):
    """A thin lens or a wet film: see-through (tinted) with a Fresnel reflection (scaled by refl, e.g. an
    anti-reflective coating) and no refraction."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    tr.inputs["Color"].default_value = (*see_through, 1)
    gl = nt.nodes.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = rough
    fr = nt.nodes.new("ShaderNodeFresnel")
    fr.inputs["IOR"].default_value = ior
    mix = nt.nodes.new("ShaderNodeMixShader")
    k = nt.nodes.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    k.inputs[1].default_value = refl
    nt.links.new(fr.outputs[0], k.inputs[0])
    nt.links.new(k.outputs[0], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(gl.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    return m


def add_corneas(arm, meshes):
    """A wet, clear film over each eyeball (Rocketbox eyes are matte): gives catchlights and a living look."""
    import bmesh
    ob = meshes[0]
    mw = ob.matrix_world
    wet = _glass("cornea", (1, 1, 1), 0.015, ior=1.376)
    for side in ("L", "R"):
        g = ob.vertex_groups.get(f"Bip01 {side}Eye")
        if g is None:
            continue
        c = arm.matrix_world @ arm.pose.bones[f"Bip01 {side}Eye"].head
        pts = []
        for v in ob.data.vertices:
            for ge in v.groups:
                if ge.group == g.index and ge.weight > 0.6:
                    pts.append(mw @ v.co)
        if len(pts) < 8:
            continue
        r = sorted((p - c).length for p in pts)[int(len(pts) * 0.9)]
        me = bpy.data.meshes.new("cornea")
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=r * 1.035)
        bm.to_mesh(me)
        bm.free()
        for p in me.polygons:
            p.use_smooth = True
        o = bpy.data.objects.new("cornea", me)
        o.location = c
        o.data.materials.append(wet)
        bpy.context.scene.collection.objects.link(o)


def _mask_weights(ob, mask_path, part="head"):
    """Per-vertex weights from a greyscale UV mask (the head texture's layout) on one material part."""
    import numpy as np
    img = bpy.data.images.load(mask_path, check_existing=True)
    w, h = img.size
    px = np.empty(w * h * img.channels, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, img.channels)[..., 0]
    idx = [i for i, sl in enumerate(ob.material_slots) if sl.material.name.split(".")[0].endswith(part)][0]
    uv = ob.data.uv_layers.active.data
    acc = {}
    for p in ob.data.polygons:
        if p.material_index != idx:
            continue
        for li in p.loop_indices:
            u, v = uv[li].uv
            val = px[min(h - 1, max(0, int(v * h))), min(w - 1, max(0, int(u * w)))]
            acc.setdefault(ob.data.loops[li].vertex_index, []).append(val)
    return {vi: sum(vs) / len(vs) for vi, vs in acc.items()}


def strand_hair(ob, fwd, mask_path, grey_path=None, length=0.022, count=60000, melanin=0.9, seed=1):
    """Short strand hair (Cycles curves, Principled Hair) grown on the scalp where the mask is white, combed back
    (grown along the scalp normal plus backwards and down); a second, sparse grey/white system where grey_path is
    white (salt and pepper at the temples)."""
    inv = ob.matrix_world.to_3x3().inverted()
    comb = inv @ (-fwd * 1.0 + Vector((0, 0, -0.5)))
    comb = comb.normalized() * 0.9

    def system(name, weights, n, mel, rnd_col, length):
        vg = ob.vertex_groups.new(name=name)
        for vi, wt in weights.items():
            if wt > 0.02:
                vg.add([vi], min(1.0, wt * 1.3), "REPLACE")
        mod = ob.modifiers.new(name, "PARTICLE_SYSTEM")
        psys = mod.particle_system
        psys.vertex_group_density = name
        psys.vertex_group_length = name
        psys.seed = seed
        st = psys.settings
        st.type = "HAIR"
        st.count = n
        st.emit_from = "FACE"
        st.use_emit_random = True
        # hair length follows the emit velocities; on Rocketbox's 0.01-scaled meshes 1.0 grows ~4.15 m
        k = length / 4.15
        st.normal_factor = 0.55 * k
        st.tangent_factor = 0.0
        st.object_align_factor = comb * k
        st.child_type = "INTERPOLATED"
        st.rendered_child_count = 5
        st.child_length = 0.9
        st.roughness_1 = 0.002
        st.roughness_endpoint = 0.003
        st.clump_factor = 0.15
        st.root_radius = 1.0
        st.tip_radius = 0.2
        st.radius_scale = 0.00028 / max(ob.matrix_world.to_scale())
        st.display_step = 3
        st.render_step = 4
        m = bpy.data.materials.new(name + "_mat")
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        hb = nt.nodes.new("ShaderNodeBsdfHairPrincipled")
        hb.parametrization = "MELANIN"
        hb.inputs["Melanin"].default_value = mel
        hb.inputs["Melanin Redness"].default_value = 0.35
        hb.inputs["Roughness"].default_value = 0.32
        hb.inputs["Radial Roughness"].default_value = 0.4
        hb.inputs["Random Color"].default_value = rnd_col
        hb.inputs["Random Roughness"].default_value = 0.2
        nt.links.new(hb.outputs[0], out.inputs[0])
        ob.data.materials.append(m)
        st.material_slot = m.name
        return psys

    system("scalp_hair", _mask_weights(ob, mask_path), count, melanin, 0.15, length)
    if grey_path:
        system("grey_hair", _mask_weights(ob, grey_path), count // 5, 0.35, 0.25, length * 0.9)


def stocky(arm, waist=1.1, chest=1.08, shoulders=1.06, limbs=1.07):
    """A broader, heavier build by scaling the spine, neck, clavicle and arm bones across (not along) their length.
    Children keep their own scale so the head, hands and legs stay the same size."""
    bones = arm.data.bones
    mw3 = arm.matrix_world.to_3x3()
    plan = {"Bip01 Spine": (waist, waist * 1.04), "Bip01 Spine1": (waist, waist), "Bip01 Spine2": (chest, chest * 0.98),
            "Bip01 Neck": (1.06, 1.06), "Bip01 L UpperArm": (limbs, limbs), "Bip01 R UpperArm": (limbs, limbs),
            "Bip01 L Forearm": (limbs * 0.98, limbs * 0.98), "Bip01 R Forearm": (limbs * 0.98, limbs * 0.98)}
    for name in list(plan) + ["Bip01 L Clavicle", "Bip01 R Clavicle"]:
        for ch in bones[name].children:
            ch.inherit_scale = "NONE"
    for name, (lat, dep) in plan.items():
        b = bones[name]
        axes = [(mw3 @ b.matrix_local.to_3x3().col[i]).normalized() for i in range(3)]
        sc = [1.0, 1.0, 1.0]
        along = max(range(3), key=lambda i: abs(axes[i].z) if "Arm" not in name else abs(axes[i].x))
        for i in range(3):
            if i == along:
                continue
            if "Arm" in name:
                sc[i] = lat
            else:
                sc[i] = lat if abs(axes[i].x) > abs(axes[i].y) else dep
        arm.pose.bones[name].scale = sc
    for side in ("L", "R"):   # wider shoulders: longer clavicles
        b = bones[f"Bip01 {side} Clavicle"]
        axes = [(mw3 @ b.matrix_local.to_3x3().col[i]).normalized() for i in range(3)]
        along = max(range(3), key=lambda i: abs(axes[i].x))
        sc = [1.0, 1.0, 1.0]
        sc[along] = shoulders
        arm.pose.bones[b.name].scale = sc
    bpy.context.view_layer.update()


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
        lens = _glass("sunlens", (0.025, 0.025, 0.03), 0.3, refl=0.35)
    else:
        lw, lh, ft, dz, ahead = 0.05, 0.03, 0.0026, 0.0, 0.03
        frame = _mat("frame", (0.06, 0.06, 0.065), 0.28, metal=1.0)
        lens = _glass("lens", (0.97, 0.98, 1.0), 0.02, refl=0.2)
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


def swap_legs(arm, meshes, donor_folder, tint=1.0):
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
    if tint != 1.0:   # darker trousers
        for sl in legs.material_slots:
            nt = sl.material.node_tree
            bsdf = [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"][0]
            link = bsdf.inputs["Base Color"].links
            if link:
                mul = nt.nodes.new("ShaderNodeMixRGB")
                mul.blend_type = "MULTIPLY"
                mul.inputs[0].default_value = 1
                mul.inputs[2].default_value = (tint, tint, tint, 1)
                nt.links.new(link[0].from_socket, mul.inputs[1])
                nt.links.new(mul.outputs[0], bsdf.inputs["Base Color"])
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
    """Gives the avatar another avatar's hair cards, fitted to this skull and multiplied by tint (dyed).
    Run in the rest pose, before relax_pose."""
    import bmesh

    def skull(ob, hp):
        """Bounding box of the head-material vertices above the head bone (world): min, max."""
        mw = ob.matrix_world
        hidx = [i for i, sl in enumerate(ob.material_slots) if sl.material.name.split(".")[0].endswith("head")][0]
        vids = {v for p in ob.data.polygons if p.material_index == hidx for v in p.vertices}
        pts = [mw @ ob.data.vertices[v].co for v in vids]
        pts = [p for p in pts if p.z > hp.z]
        return (Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)]))

    hp = head_pos(arm)
    t0, t1 = skull(meshes[0], hp)
    d_arm, d_meshes = load_avatar(donor_folder)
    dhp = head_pos(d_arm)
    dob = d_meshes[0]
    dmw = dob.matrix_world
    d0, d1 = skull(dob, dhp)
    slots = [sl.material.name.split(".")[0] for sl in dob.material_slots]
    oidx = [i for i, n in enumerate(slots) if n.endswith("opacity")][0]
    bm = bmesh.new()
    bm.from_mesh(dob.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != oidx], context="FACES")
    bm.to_mesh(dob.data)
    bm.free()
    # fit the donor skull box onto this skull box (per axis; height measured up from the head bone), 2% proud
    tc, dc = (t0 + t1) / 2, (d0 + d1) / 2
    k = [(t1[i] - t0[i]) / (d1[i] - d0[i]) * 1.02 for i in range(2)] + [(t1.z - hp.z) / (d1.z - dhp.z) * 1.02]
    inv = dmw.inverted()
    for v in dob.data.vertices:
        w = dmw @ v.co
        v.co = inv @ Vector((tc.x + (w.x - dc.x) * k[0], tc.y + (w.y - dc.y) * k[1], hp.z + (w.z - dhp.z) * k[2]))
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


def long_hair(arm, meshes, count=42000, points=26, seed=7, melanin=0.96):
    """Long straight dark hair as real curves (a Curves object, Principled Hair): roots on an ellipsoid fitted to the
    posed skull (forehead and face left bare), each strand combed away from a crown parting, hugging the skull and
    then falling straight to the shoulders. Parented to the head bone so moods and poses carry it."""
    import random
    rnd = random.Random(seed)
    bpy.context.view_layer.update()
    hp = head_pos(arm)
    fwd, _ = facing(arm)
    up = Vector((0, 0, 1))
    side = fwd.cross(up).normalized()
    fwd = up.cross(side).normalized()
    # skull ellipsoid from the posed head-material vertices above the head bone
    ob = meshes[0]
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    hidx = [i for i, sl in enumerate(ob.material_slots) if sl.material.name.split(".")[0].endswith("head")][0]
    vids = {v for p in me.polygons if p.material_index == hidx for v in p.vertices}
    mw = ob.matrix_world
    pts = [mw @ me.vertices[v].co for v in vids]
    # the real skull surface (head polygons, world space) in hair-frame coordinates, for ray casts from the centre
    from mathutils.bvhtree import BVHTree
    hpolys = [list(p.vertices) for p in me.polygons if p.material_index == hidx]
    hverts_w = [mw @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    pts = [p for p in pts if p.z > hp.z + 0.02]
    loc = [Vector(((p - hp).dot(side), (p - hp).dot(fwd), (p - hp).dot(up))) for p in pts]
    lo = Vector([min(q[i] for q in loc) for i in range(3)])
    hi = Vector([max(q[i] for q in loc) for i in range(3)])
    ctr = (lo + hi) / 2
    rad = (hi - lo) / 2
    ctr.z = hi.z - rad.x * 1.05            # a skull is about as tall above its centre as it is wide
    rad.z = hi.z - ctr.z
    rad.y *= 0.98

    hverts = [Vector(((p - hp).dot(side), (p - hp).dot(fwd), (p - hp).dot(up))) for p in hverts_w]
    bvh = BVHTree.FromPolygons(hverts, hpolys)

    def surface(q, shell):
        """q pushed out to shell x the skull surface along the ray from the centre (unchanged if already outside)."""
        dv = q - ctr
        L = dv.length
        if L < 1e-6:
            return q
        hit = bvh.ray_cast(ctr, dv / L)
        if hit[0] is None:
            return q
        dh = (hit[0] - ctr).length * shell
        return ctr + dv / L * dh if L < dh else q

    def world(q):
        return hp + side * q.x + fwd * q.y + up * q.z

    def g(q):
        d = q - ctr
        return (d.x / rad.x) ** 2 + (d.y / rad.y) ** 2 + (d.z / rad.z) ** 2

    def normal(q):
        d = q - ctr
        return Vector((d.x / rad.x ** 2, d.y / rad.y ** 2, d.z / rad.z ** 2)).normalized()

    crown = ctr + Vector((0, -rad.y * 0.25, rad.z))
    bottom = -(ctr.z + rad.z) * 0.0 - 0.13      # shoulder length: 13 cm below the head bone
    step = 0.0085
    strands = []
    while len(strands) < count:
        u = Vector((rnd.gauss(0, 1), rnd.gauss(0, 1), rnd.gauss(0, 1))).normalized()
        if u.z < -0.05:
            continue
        # bare forehead and face; hairline a little higher at the temples
        if u.y > 0.3 and u.z < 0.32 + 0.12 * abs(u.x):
            continue
        if u.y > 0.6 and u.z < 0.5:
            continue
        shell = 1.012 + rnd.random() ** 1.5 * 0.06
        q = surface(ctr + Vector((u.x, u.y, u.z)) * 0.001, shell)
        d = q - crown
        if q.y > crown.y:
            # centre parting: hair in front of the crown is swept to the sides and back, never over the face
            d = Vector((math.copysign(1.0, u.x if abs(u.x) > 1e-3 else rnd.random() - 0.5), -0.35, -0.25))
        n = normal(q)
        d = (d - n * d.dot(n))
        if d.length < 1e-6:
            d = -Vector((0, 1, 0))
        d.normalize()
        path = [q.copy()]
        for i in range(points - 1):
            n = normal(q)
            hanging = q.z < ctr.z - rad.z * 0.15
            down = Vector((0, 0, -1))
            if hanging:
                d = (d * 0.08 + down * 0.92).normalized()
                d.y = min(d.y, 0.0) if q.y < ctr.y + rad.y * 0.2 else d.y
            else:
                d = (d + down * 0.18)
                d = (d - n * d.dot(n)).normalized()
            q = q + d * step * (1.6 if hanging else 1.0)
            q = surface(q, shell)
            # hanging strands stay beside the face: anything in front of the ears is pushed out to the cheek line
            if q.z < ctr.z and q.y > ctr.y - rad.y * 0.1 and abs(q.x - ctr.x) < rad.x * 0.96:
                q.x = ctr.x + math.copysign(rad.x * 0.96, q.x - ctr.x)
            if q.z < bottom - rnd.random() * 0.025:
                q.z = bottom - rnd.random() * 0.025
            path.append(q.copy())
        strands.append([world(p) for p in path])
    cv = bpy.data.hair_curves.new("long_hair")
    cv.add_curves([points] * len(strands))
    flat = [c for s_ in strands for p in s_ for c in p]
    cv.attributes["position"].data.foreach_set("vector", flat)
    if "radius" not in cv.attributes:
        cv.attributes.new("radius", "FLOAT", "POINT")
    rads = []
    for s_ in strands:
        for i in range(points):
            rads.append(0.00045 * (1.0 - 0.6 * i / (points - 1)))
    cv.attributes["radius"].data.foreach_set("value", rads)
    m = bpy.data.materials.new("long_hair_mat")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    hb = nt.nodes.new("ShaderNodeBsdfHairPrincipled")
    hb.parametrization = "MELANIN"
    hb.inputs["Melanin"].default_value = melanin
    hb.inputs["Melanin Redness"].default_value = 0.3
    hb.inputs["Roughness"].default_value = 0.26
    hb.inputs["Radial Roughness"].default_value = 0.35
    hb.inputs["Random Color"].default_value = 0.1
    hb.inputs["Random Roughness"].default_value = 0.15
    nt.links.new(hb.outputs[0], out.inputs[0])
    cv.materials.append(m)
    hob = bpy.data.objects.new("long_hair", cv)
    bpy.context.scene.collection.objects.link(hob)
    wm = hob.matrix_world.copy()
    hob.parent = arm
    hob.parent_type = "BONE"
    hob.parent_bone = "Bip01 Head"
    bpy.context.view_layer.update()
    hob.matrix_world = wm
    return hob


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
    sc.cycles.samples = PORTRAIT_SAMPLES
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
    sc.cycles.samples = SAMPLES
    cam.data.sensor_fit = "AUTO"
    cam.data.sensor_width = 36


HERO_SPAN = 1.32   # metres from just above the head to about mid-thigh


def render_hero(arm, meshes, cam, out, pid):
    """Large standing figure for the Marco screen: head to mid-thigh, slight three-quarter turn, arms crossed."""
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 1100, 1500
    sc.cycles.samples = PORTRAIT_SAMPLES
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
        if staff.get("head_maps"):
            src = find(SRCS, staff["head_maps"])
            for kind in ("normal", "specular"):
                hits = [f for f in os.listdir(src) if f.endswith("_head_%s.tga" % kind)]
                if hits:
                    override["head_" + kind] = os.path.join(src, hits[0])
    arm, meshes = load_avatar(folder, override)
    if staff and not staff["hair_cards"]:
        drop_hair_cards(meshes)
    if staff and staff.get("legs"):
        swap_legs(arm, meshes, find(SRCS, staff["legs"]), staff.get("legs_tint", 1.0))
    if staff and staff.get("hair_from"):
        transplant_hair(arm, meshes, find(SRCS, staff["hair_from"]), staff.get("hair_tint", (0.05, 0.047, 0.045)))
    if staff and staff.get("strand_hair"):
        tdir = os.path.join(os.environ["STAFF_TEX"], pid)
        grey = os.path.join(tdir, "grey_mask.png")
        strand_hair(meshes[0], facing(arm)[0], os.path.join(tdir, "hair_mask.png"), grey if os.path.exists(grey) else None)
    if staff and staff.get("stocky"):
        stocky(arm)
    add_corneas(arm, meshes)
    if PARTS == ["hero"]:
        cross_arms(arm)
    else:
        relax_pose(arm)
    if staff and staff.get("glasses"):
        add_glasses(arm, staff["glasses"])
    if staff and staff.get("long_hair"):
        long_hair(arm, meshes)
    if staff and staff.get("watch"):
        add_watch(arm)
    cam = studio((520, 1100))
    ground = ground_shadow(meshes)
    if PARTS == ["hero"]:
        ground.hide_render = True
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
