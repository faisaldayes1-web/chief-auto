"""Garage .glb files from the realistic third-party car models (CC-BY, see assets/cars/CREDITS.md).

Writes assets/cars3d/<slug>.glb with the node names scripts/car3d_view.gd expects, in the same axes and
scale as tools/car3d.py `build` (Blender: +X front, +Y left, Z up, metres, wheels on z=0):
  part_<panel>        body paint split into panels by position (hood, fender_fl, door_fl, quarter_rl, roof,
                      trunk or bed, front_bumper, rear_bumper ...), plain grey (the game paints them)
  part_glass          windows
  headlight_l/r, taillight_l/r
  wheel_fl/fr/rl/rr   origin at the wheel centre, surfaces named rubber / rim / disc
  mirror_l/r          mirror housings (painted like the front doors)
  core                everything else (interior, trim, underbody), not clickable
Models are loaded with car_sprites_real.load_car (scaled to real length, pointing down +X, on z=0),
badges become paint and plates are blanked like in the sprites, then decimated and textures shrunk.

Usage (bpy venv):  python -I tools/car_glb_real.py <out_dir> [test] [slug ...]
`test` also writes <slug>_parts_*.png renders with every node in its own colour.
"""
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True

import bpy  # noqa: E402,I001
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import car_restyle  # noqa: E402
import car_sprites_real as R  # noqa: E402
import cars_svg  # noqa: E402

RESTYLE = os.environ.get("RESTYLE", "1") != "0"

# Per car: glass / light / tyre materials (regex), drop: materials removed outright,
# keep: least fraction of a paint panel's triangles to keep (dense parts fold when decimated hard),
# budget / tex: smaller triangle budgets or texture size for the heavier models (see BUDGET).
GLASS = r"(?i)glass|window|windshield|vitre"
LIGHT = r"(?i)light|lamp|phare|feux|lens|led|drl|blinker|projector|signal"
TYRE = r"(?i)tire|tyre|pneu"
CFG = {
    "porsha_911": dict(drop=r"^coat$", glass=r"^glass$", light=r"^930_lights", tyre=r"^930_tire$"),
    "forde_mustank": dict(glass=r"^tinted_glass$", light=r"^(light|rearlight|orange)$", tyre=r"^tire$"),
    "mazdo_miota": dict(glass=r"^Material\.(004|010)$", light=r"^Material\.(008|009|012)$", tyre=r"^Material\.014$"),
    "ferrano_488": dict(glass=r"^Glass_Gray$", light=r"^(Taillight_Glass|Projector_Glass|Turn_Signal_LED)$",
                        tyre=r"^Tires$"),
    "lamborgo_aventa": dict(glass=r"^Vitre$", light=r"^(Phare|Feux)", tyre=r"^Pneu$"),
    "hondo_civix": dict(glass=r"^Windshield", light=r"^Lamp", tyre=r"^Tyre0[12]"),
    "bmv_m4": dict(glass=r"^Material_699$", light=r"^Material_(775|776|718|161|716|708|707|739|738|740|701\.001)$",
                   tyre=r"^Material_75[12]$"),
    "ramm_1500": dict(drop=r"^0-", glass=r"^Glass$", light=r"^(hl_lamps|plexiglass|taillight_red_pl|hl_blinkers)$",
                      tyre=r"^Tires$"),
    "forde_rangler": dict(glass=r"^material_2[23]$", light=r"^material_(15|16|17|2|5|6)$", tyre=r"^material_20$"),
    "rang_rovah": dict(weld=1e-6, drop=r"^None$", budget=dict(core=6500, wheel=6000, paint=13000), keep=0.03, glass=r"^Windows$", light=r"(?i)taillight|front_led|drl|clear_glass|brake_light|hamna|"
                       r"^Material\.0(04|07|08|09|10|15|16)$", tyre=r"^Tire"),
    "mercedez_g_wagon": dict(budget=dict(core=11000), tex=128, glass=r"^(IntWindows|ExtWindowsGlass_0)$", light=r"^(ExtWindowsGlass|ExtWindowsGlass_1|"
                             r"leather02_weave_18)$", tyre=r"^plastic5_16$"),
    "chevro_tahoma": dict(budget=dict(core=9000), glass=r"^WorldGridMaterial\.024$", tyre=r"^tire$",
                          light=r"^(WorldGridMaterial\.0(21|27|28|39)|Material\.002)$"),
}
BUDGET = dict(paint=17000, core=13000, wheel=8000, glass=1500, light=2500)
TEX_MAX = int(os.environ.get("TEX_MAX", 256))
MODEL_NAME = {cars_svg.slug(n): n for n in cars_svg.MODELS}


def spec(slug, dims):
    """Body landmarks in metres from cars_svg's real-world table, scaled to this model's size.
    x is measured back from the front bumper, z up from the ground."""
    m = cars_svg.MODELS[MODEL_NAME[slug]]
    U, G = cars_svg.U, cars_svg.GROUND
    L0 = (m["x1"] - m["x0"]) * U
    H0 = (G - m["roofY"]) * U
    sx, sz = dims.x / L0, dims.z / H0
    fx = lambda v: (m["x1"] - v) * U * sx  # noqa: E731
    hz = lambda v: (G - v) * U * sz  # noqa: E731
    s = dict(type=m["type"], L=dims.x, cowl=fx(m["cowlX"]), roofF=fx(m["rx1"]), roofR=fx(m["rx0"]),
             belt=hz(m["belt"]), hood=hz(m["hoodY"]), nose=hz(m["noseY"]), deck=hz(m["deckY"]),
             rear_glass=fx(m["rearGlassX"]), fw=fx(m["fw"]), rw=fx(m["rw"]), r=m["r"] * U * sx,
             doors=[fx(d) for d in m["doors"]], cab=fx(m["cab"]) if "cab" in m else None)
    if len(s["doors"]) > 1 and s["type"] != "truck":
        # B-pillar a bit past half way between the windscreen base and the rear door's end
        s["doors"][0] = s["cowl"] + (s["doors"][1] - s["cowl"]) * 0.55
    if s["type"] in ("suv", "boxy"):
        s["end_cab"] = s["roofR"]
    elif s["cab"]:
        s["end_cab"] = s["cab"]
    else:
        s["end_cab"] = s["rear_glass"]
    return s


# ------------------------------------------------------------------ blender helpers

def select_only(objs, active=None):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or objs[0]


def face_arrays(me):
    n = len(me.polygons)
    c = np.empty(n * 3, np.float32)
    me.polygons.foreach_get("center", c)
    nr = np.empty(n * 3, np.float32)
    me.polygons.foreach_get("normal", nr)
    mi = np.empty(n, np.int32)
    me.polygons.foreach_get("material_index", mi)
    return c.reshape(-1, 3), nr.reshape(-1, 3), mi


def vert_array(me):
    v = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", v)
    return v.reshape(-1, 3)


def face_verts(me):
    """(loop_start, loop_total, loop vertex indices) for every face."""
    n = len(me.polygons)
    ls = np.empty(n, np.int32)
    lt = np.empty(n, np.int32)
    me.polygons.foreach_get("loop_start", ls)
    me.polygons.foreach_get("loop_total", lt)
    lv = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", lv)
    return ls, lt, lv


def components(me):
    """Connected-component label per face (faces sharing a vertex are connected)."""
    ls, lt, lv = face_verts(me)
    nv = len(me.vertices)
    face_of_loop = np.repeat(np.arange(len(ls)), lt)
    # union vertices of each face with the face's first vertex
    a = lv
    b = lv[ls][face_of_loop]
    lab = np.arange(nv)
    while True:
        m = np.minimum(lab[a], lab[b])
        new = lab.copy()
        np.minimum.at(new, a, m)
        np.minimum.at(new, b, m)
        new = new[new]
        new = new[new]
        if np.array_equal(new, lab):
            break
        lab = new
    return np.unique(lab[lv[ls]], return_inverse=True)[1].ravel()


def separate_faces(ob, mask, name):
    """Moves the faces in mask out of ob into a new object called name."""
    select_only([ob])
    before = set(bpy.data.objects)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type="FACE")
    bpy.ops.mesh.select_all(action="DESELECT")
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    for i in np.flatnonzero(mask):
        bm.faces[int(i)].select_set(True)
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.mesh.separate(type="SELECTED")
    bpy.ops.object.mode_set(mode="OBJECT")
    new = [o for o in bpy.data.objects if o not in before]
    new[0].name = name
    new[0].data.name = name
    return new[0]


def decimate(ob, target):
    for _ in range(4):
        n = tris(ob)
        if n <= target * 1.08:
            return
        select_only([ob])
        md = ob.modifiers.new("dec", "DECIMATE")
        md.decimate_type = "COLLAPSE"
        md.ratio = max(0.02, target / n)
        md.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=md.name)
        remove_duplicate_faces(ob)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.dissolve_degenerate(threshold=0.0005)
        bpy.ops.object.mode_set(mode="OBJECT")
        if os.environ.get("DEBUG"):
            print("    decimate", ob.name, n, "->", tris(ob), "verts", len(ob.data.vertices), "target", int(target))
        if tris(ob) > n * 0.95:
            # many tiny loose bits the collapse can't merge: drop the smallest parts
            drop_small_parts(ob, target)


def drop_small_parts(ob, target):
    """Deletes the smallest loose parts until the object is near its triangle budget."""
    me = ob.data
    comp = components(me)
    V = vert_array(me)
    ls, lt, lv = face_verts(me)
    ncomp = comp.max() + 1
    lo = np.full((ncomp, 3), 1e9)
    hi = np.full((ncomp, 3), -1e9)
    fc = np.repeat(comp, lt)
    for k in range(3):
        np.minimum.at(lo[:, k], fc, V[lv, k])
        np.maximum.at(hi[:, k], fc, V[lv, k])
    size = np.linalg.norm(hi - lo, axis=1)
    ft = np.bincount(comp, weights=lt - 2, minlength=ncomp)
    order = np.argsort(size)
    excess = ft.sum() - target
    cut = np.cumsum(ft[order]) <= excess
    drop = order[cut & (size[order] < 0.15)]
    if os.environ.get("DEBUG"):
        print("    parts", ncomp, "tris", int(ft.sum()), "dropping", len(drop), int(ft[drop].sum()),
              "size pct", np.percentile(size, [10, 50, 90]).round(3), "tris in parts <5cm", int(ft[size < 0.05].sum()))
    mask = np.isin(comp, drop)
    if mask.any():
        bpy.data.objects.remove(separate_faces(ob, mask, "small"), do_unlink=True)


def remove_duplicate_faces(ob):
    """Drops faces that reuse another face's vertices (double-sided shells); they stall the decimator."""
    ls, lt, lv = face_verts(ob.data)
    k = np.full((len(ls), 4), -1, np.int64)
    for j in range(4):
        ok = lt > j
        k[ok, j] = lv[ls[ok] + j]
    k[lt > 4] = -np.arange(1, (lt > 4).sum() + 1)[:, None] - 10  # n-gons: never duplicates
    k.sort(axis=1)
    _, first = np.unique(k, axis=0, return_index=True)
    dup = np.ones(len(ls), bool)
    dup[first] = False
    if dup.any():
        if os.environ.get("DEBUG"):
            print("    %s: removing %d duplicate faces" % (ob.name, dup.sum()))
        bpy.data.objects.remove(separate_faces(ob, dup, "dups"), do_unlink=True)


def tris(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def mat_simple(name, color, rough=0.5, metal=0.0, emit=None):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = R.simple_mat(name, color, rough=rough, metal=metal)
    m.name = name
    if emit:
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = 0.6
    return m


def set_materials(ob, mats, per_face=None):
    ob.data.materials.clear()
    for m in mats:
        ob.data.materials.append(m)
    n = len(ob.data.polygons)
    idx = np.zeros(n, np.int32) if per_face is None else per_face.astype(np.int32)
    ob.data.polygons.foreach_set("material_index", idx)


def drop_uvs(ob):
    while ob.data.uv_layers:
        ob.data.uv_layers.remove(ob.data.uv_layers[0])


def shade(ob, angle=40, consistent=False):
    select_only([ob])
    if consistent:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")
    try:
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    except RuntimeError:
        pass
    ob.data.polygons.foreach_set("use_smooth", np.ones(len(ob.data.polygons), bool))
    ob.data.set_sharp_from_angle(angle=math.radians(angle))


def slim_material(m):
    """Keeps only base colour / alpha textures (no normal, roughness or occlusion maps) to save space."""
    if not m or not m.node_tree:
        return
    nt = m.node_tree
    keep_inputs = {"Base Color", "Alpha"}

    def feeds(node, depth=0):
        for out in node.outputs:
            for ln in out.links:
                to = ln.to_node
                if to.type == "BSDF_PRINCIPLED":
                    if ln.to_socket.name in keep_inputs:
                        return True
                elif depth < 4 and feeds(to, depth + 1):
                    return True
        return False
    for nd in list(nt.nodes):
        if nd.type == "TEX_IMAGE" and not feeds(nd):
            nt.nodes.remove(nd)


def shrink_images(limit):
    used = set()
    for m in bpy.data.materials:
        if m.users and m.node_tree:
            for nd in m.node_tree.nodes:
                if nd.type == "TEX_IMAGE" and nd.image:
                    used.add(nd.image)
    for im in used:
        w, h = im.size
        if max(w, h) > limit:
            k = limit / max(w, h)
            im.scale(max(4, int(w * k)), max(4, int(h * k)))


# ------------------------------------------------------------------ build one car

def load(slug):
    cfg = R.CARS[slug]
    c3 = CFG[slug]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    meshes, dims = R.load_car(cfg)
    if RESTYLE:
        # our own design on top of the model (tools/car_restyle.py), the same as the sprites
        meshes, dims = car_restyle.restyle(meshes, slug, dims, cfg)
    for o in meshes:
        if o.data.users > 1:
            o.data = o.data.copy()
        o.data.shape_keys and o.shape_key_clear()
    R.classify(meshes, cfg)
    paint_re = re.compile(cfg["paint"])
    paint_mat = None
    for o in meshes:
        for sl in o.material_slots:
            if sl.material and paint_re.search(sl.material.name) and not (
                    c3.get("drop") and re.search(c3["drop"], sl.material.name)):
                paint_mat = paint_mat or sl.material
    badge_re = re.compile(cfg["badge"]) if cfg.get("badge") else None
    for o in meshes:
        for sl in o.material_slots:
            m = sl.material
            if sl.link == "OBJECT":
                sl.link = "DATA"
                sl.material = m
            if m and badge_re and badge_re.search(m.name):
                sl.material = paint_mat
    for o in meshes:
        for md in list(o.modifiers):
            o.modifiers.remove(md)
        while len(o.data.color_attributes):
            o.data.color_attributes.remove(o.data.color_attributes[0])
        # one UV map (TEXCOORD_0) per object, all under the same name, so the join doesn't stack them
        uvs = o.data.uv_layers
        while len(uvs) > 1:
            uvs.remove(uvs[-1])
        if len(uvs):
            uvs[0].name = "UVMap"
    select_only(meshes)
    bpy.ops.object.join()
    car = bpy.context.view_layer.objects.active
    car.name = "car"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    # drop unwanted materials
    me = car.data
    names = [m.name if m else "" for m in me.materials]
    if c3.get("drop"):
        bad = {i for i, n in enumerate(names) if re.search(c3["drop"], n)}
        _, _, mi = face_arrays(me)
        mask = np.isin(mi, list(bad))
        if mask.any():
            ob = separate_faces(car, mask, "dropped")
            bpy.data.objects.remove(ob, do_unlink=True)
    # weld UV-seam splits so the decimator and the loose-part search see whole parts
    select_only([car])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=c3.get("weld", 0.0002))
    bpy.ops.object.mode_set(mode="OBJECT")
    remove_duplicate_faces(car)
    return car, dims, paint_re


def category(names, paint_re, c3):
    """Material index -> paint / glass / light / other."""
    cat = []
    for n in names:
        if paint_re.search(n) and not (c3.get("drop") and re.search(c3["drop"], n)):
            cat.append("paint")
        elif n.startswith("rs_lamp") or re.search(c3.get("light", LIGHT), n):
            cat.append("light")
        elif n == "rs_glass" or re.search(c3.get("glass", GLASS), n):
            cat.append("glass")
        else:
            cat.append("other")
    return cat


def build(slug, out, test=False):
    c3 = dict(CFG[slug])
    if RESTYLE and slug in car_restyle.RECIPES:
        c3["tyre"] = r"^rs_rubber$"
    car, dims, paint_re = load(slug)
    s = spec(slug, dims)
    L = dims.x
    me = car.data
    names = [m.name if m else "" for m in me.materials]
    cats = np.array(category(names, paint_re, c3) + ["other"])
    c, nrm, mi = face_arrays(me)
    fcat = cats[np.minimum(mi, len(names))]
    V = vert_array(me)
    ls, lt, lv = face_verts(me)
    src_tris = int((lt - 2).sum())

    def face_all(vmask):
        return np.logical_and.reduceat(vmask[lv], ls)

    # ---- wheel centres from the tyre faces
    tyre_idx = [i for i, n in enumerate(names) if re.search(c3.get("tyre", TYRE), n)]
    is_tyre = np.isin(mi, tyre_idx)
    comp = components(me)
    wheels = {}
    for key, xs, ys in (("wheel_fl", 1, 1), ("wheel_fr", 1, -1), ("wheel_rl", -1, 1), ("wheel_rr", -1, -1)):
        # tyre faces near where the spec puts the wheel (some models reuse the tyre material elsewhere)
        x0 = L / 2 - (s["fw"] if xs > 0 else s["rw"])
        q = is_tyre & (np.abs(c[:, 0] - x0) < s["r"] * 1.6) & (c[:, 2] < s["r"] * 2.3) & (c[:, 1] * ys > 0.3)
        if q.any():
            # the biggest connected piece of tyre is the tyre (wipers, grilles etc. may share its material)
            ids, cnt = np.unique(comp[q], return_counts=True)
            big = ids[cnt >= cnt.max() * 0.5]
            q &= np.isin(comp, big)
        v = c[q]
        if len(v) < 20:
            wheels[key] = dict(c=Vector((x0, ys * (dims.y / 2 - 0.2), s["r"])), r=s["r"], hw=0.13, side=ys)
            print("  no tyre faces for", key, "- using the spec")
            continue
        # robust centre: middle of the tyre's length, radius from the spread of distances around it
        cx = float(np.percentile(v[:, 0], [1, 99]).mean())
        r = s["r"]
        for _ in range(3):
            r = float(np.percentile(np.hypot(v[:, 0] - cx, v[:, 2] - r), 96))
        ylo, yhi = np.percentile(v[:, 1], [2, 98])
        wheels[key] = dict(c=Vector((cx, (ylo + yhi) / 2, r)), r=r * 1.03, hw=(yhi - ylo) / 2, side=ys)
    for k, w in wheels.items():
        print("  %s centre=(%.2f %.2f %.2f) r=%.3f hw=%.3f" % (k, *w["c"], w["r"], w["hw"]))

    # cut the paint along the panel boundaries so seams come out straight on coarse meshes
    cut_seams(car, s, wheels, [i for i, ct in enumerate(cats[:-1]) if ct == "paint"])
    c, nrm, mi = face_arrays(me)
    fcat = cats[np.minimum(mi, len(names))]
    V = vert_array(me)
    ls, lt, lv = face_verts(me)
    comp = components(me)

    label = np.full(len(c), "", dtype=object)
    is_paint = fcat == "paint"
    for k, w in wheels.items():
        d = V - np.array(w["c"])
        rad = np.hypot(d[:, 0], d[:, 2])
        ofs = d[:, 1] * w["side"]
        inside = face_all((rad <= w["r"] * 1.03) & (ofs <= w["hw"] + 0.04) & (ofs >= -w["hw"] - 0.22))
        # paint (badges) only as whole parts
        bad = np.unique(comp[is_paint & ~inside])
        inside &= ~(is_paint & np.isin(comp, bad))
        label[inside & (label == "")] = k

    # ---- body width and mirrors (paint parts sticking out past the body near the A-pillar)
    belt = s["belt"]
    free = label == ""
    body = is_paint & free & (c[:, 2] < belt - 0.08) & (np.abs(c[:, 0]) < L / 2 - 0.6)
    hw = float(np.percentile(np.abs(c[body, 1]), 99.5)) if body.any() else dims.y / 2
    xf = L / 2 - c[:, 0]
    cand = is_paint & free & (np.abs(c[:, 1]) > hw + 0.02) & (c[:, 2] > belt - 0.25) & \
        (xf > s["cowl"] - 0.5) & (xf < s["cowl"] + 1.0)
    for cid in np.unique(comp[cand]):
        f = (comp == cid) & is_paint
        p = c[f]
        if np.ptp(p[:, 0]) < 0.5 and np.ptp(p[:, 2]) < 0.4 and np.ptp(p[:, 1]) < 0.45:
            label[f & free] = "mirror_" + ("l" if p[:, 1].mean() > 0 else "r")
    # ---- paint panels
    free = label == ""
    pm = is_paint & free
    label[pm] = ["part_" + n for n in assign_panels(c[pm], nrm[pm], s, wheels, hw, slug)]
    # ---- lights: light faces (and glass low in the nose or tail) near either end; the rest is trim
    zone = 0.8
    ends = (xf < zone) | (xf > L - zone)
    lights = free & ((fcat == "light") | ((fcat == "glass") & (c[:, 2] < belt - 0.02))) & ends
    sd = np.where(c[:, 1] >= 0, "_l", "_r")
    label[lights & (xf < zone)] = np.char.add("headlight", sd[lights & (xf < zone)].astype(str))
    label[lights & (xf > L - zone)] = np.char.add("taillight", sd[lights & (xf > L - zone)].astype(str))
    free = label == ""
    label[free & (fcat == "glass")] = "part_glass"
    # everything else: textured materials -> core (keeps UVs), plain ones -> liner_trim (no UVs)
    textured = np.array([bool(m and m.node_tree and any(nd.type == "TEX_IMAGE" and nd.image for nd in m.node_tree.nodes))
                         for m in me.materials] + [False])
    free = label == ""
    label[free & textured[np.minimum(mi, len(names))]] = "core"
    label[label == ""] = "liner_trim"

    # ---- split: label -> temporary material index, separate by material, restore the real materials
    groups = sorted(set(label))
    gi = np.array([groups.index(x) for x in label], np.int32)
    attr = me.attributes.new("omat", "INT", "FACE")
    attr.data.foreach_set("value", mi)
    me.attributes.new("grp", "INT", "FACE").data.foreach_set("value", gi)
    nslots = len(me.materials)
    orig_mats = list(me.materials)
    for _ in range(max(0, len(groups) - nslots)):
        me.materials.append(None)
    me.polygons.foreach_set("material_index", gi)
    me.update()
    select_only([car])
    before = set(bpy.data.objects) - {car}
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="MATERIAL")
    bpy.ops.object.mode_set(mode="OBJECT")
    pieces = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    final = {}
    for ob in pieces:
        m2 = ob.data
        if not len(m2.polygons):
            bpy.data.objects.remove(ob, do_unlink=True)
            continue
        g = m2.attributes["grp"].data[0].value
        m2.attributes.remove(m2.attributes["grp"])
        om = np.empty(len(m2.polygons), np.int32)
        m2.attributes["omat"].data.foreach_get("value", om)
        m2.materials.clear()
        for m in orig_mats:
            m2.materials.append(m)
        m2.polygons.foreach_set("material_index", om)
        m2.attributes.remove(m2.attributes["omat"])
        m2.update()
        name = groups[g]
        ob.name = name
        m2.name = name
        final[name] = ob
        select_only([ob])
        bpy.ops.object.material_slot_remove_unused()

    # ---- decimate every piece by its category's budget
    cat_of = lambda n: ("paint" if n.startswith(("part_", "mirror_")) and n != "part_glass" else  # noqa: E731
                        "glass" if n == "part_glass" else "light" if n.startswith(("head", "tail")) else
                        "wheel" if n.startswith("wheel_") else "core")
    # paint is shared out by surface area (a detailed badge mustn't starve the doors), the rest by triangle count
    def weight(n, ob):
        if cat_of(n) != "paint":
            return tris(ob)
        a = np.empty(len(ob.data.polygons), np.float32)
        ob.data.polygons.foreach_get("area", a)
        return float(a.sum())
    have = {}
    wsum = {}
    for n, ob in final.items():
        have[cat_of(n)] = have.get(cat_of(n), 0) + tris(ob)
        wsum[cat_of(n)] = wsum.get(cat_of(n), 0) + weight(n, ob)
    for n, ob in final.items():
        k = cat_of(n)
        target = c3.get("budget", {}).get(k, BUDGET[k]) * weight(n, ob) / max(1e-9, wsum[k])
        floor = tris(ob) * c3.get("keep", 0.0) if k == "paint" else 0
        decimate(ob, max(target, floor, min(tris(ob), 150)))
        shade(ob, 50 if k == "paint" else 80, consistent=k in ("core", "wheel"))
    print("  " + "  ".join("%s %d->%d" % (k, have[k], sum(tris(o) for n, o in final.items() if cat_of(n) == k))
                           for k in sorted(have)))

    # ---- materials
    grey = mat_simple("paint", (0.8, 0.8, 0.8), rough=0.3, metal=0.35)
    head = mat_simple("headlight", (0.9, 0.92, 0.95), rough=0.08, metal=0.8)
    tail = mat_simple("taillight", (0.5, 0.01, 0.01), rough=0.1, emit=(0.6, 0.0, 0.0))
    rubber = mat_simple("rubber", (0.025, 0.025, 0.025), rough=0.85)
    rim = mat_simple("rim", (0.75, 0.76, 0.78), rough=0.22, metal=1.0)
    disc = mat_simple("disc", (0.35, 0.35, 0.36), rough=0.45, metal=1.0)
    for name, ob in final.items():
        if cat_of(name) == "paint":
            set_materials(ob, [grey])
            drop_uvs(ob)
        elif name.startswith("headlight"):
            set_materials(ob, [head])
            drop_uvs(ob)
        elif name.startswith("taillight"):
            set_materials(ob, [tail])
            drop_uvs(ob)
        elif name.startswith("wheel_"):
            w = wheels[name]
            style_wheel(ob, w, [rubber, rim, disc], c3)
            drop_uvs(ob)
            # origin at the wheel centre (the view squashes a flat tyre about it)
            ob.data.transform(Matrix.Translation(-w["c"]))
            ob.location = w["c"]
        elif name == "liner_trim":
            drop_uvs(ob)
    for m in bpy.data.materials:
        slim_material(m)
    shrink_images(c3.get("tex", TEX_MAX))
    # ---- report and export
    objs = [o for o in bpy.data.objects if o.type == "MESH"]
    for o in objs:
        o.data.validate()
        if os.environ.get("DEBUG"):
            print("   ", o.name, len(o.data.vertices), tris(o), [a.name for a in o.data.attributes],
                  o.data.normals_domain)
    tot = sum(tris(o) for o in objs)
    panels = sorted(n[5:] for n in final if n.startswith("part_") and n != "part_glass")
    print("  objects:", " ".join(sorted(final)))
    print("  source tris %d, total tris %d" % (src_tris, tot))
    path = os.path.join(out, slug + ".glb")
    select_only(objs)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True,
                              export_draco_mesh_compression_enable=False, export_image_format="JPEG",
                              export_jpeg_quality=80, export_tangents=False, export_animations=False)
    if test:
        test_render(slug, out, final, final.get("core"))
    return dict(tris=tot, size=os.path.getsize(path), panels=panels, objects=sorted(final))


def bounds(s, wheels):
    """Panel boundaries: x measured back from the front bumper, z up from the ground."""
    L = s["L"]
    b = dict(fwx=L / 2 - (wheels["wheel_fl"]["c"].x + wheels["wheel_fr"]["c"].x) / 2,
             rwx=L / 2 - (wheels["wheel_rl"]["c"].x + wheels["wheel_rr"]["c"].x) / 2,
             r=(wheels["wheel_fl"]["r"] + wheels["wheel_rl"]["r"]) / 2, belt=s["belt"], cowl=s["cowl"],
             end_cab=s["end_cab"], door_end=s["doors"][0], rdoor_end=s["doors"][1] if len(s["doors"]) > 1 else None)
    b["fb_top"] = min(s["nose"] - 0.02, b["belt"] * 0.72)
    b["rb_top"] = b["belt"] * 0.62
    return b


def cut_seams(ob, s, wheels, paint_idx):
    b = bounds(s, wheels)
    L = s["L"]
    planes = [((L / 2 - x, 0, 0), (1, 0, 0)) for x in
              (b["cowl"], b["door_end"], b["rdoor_end"], b["end_cab"]) if x]
    planes += [((0, 0, z), (0, 0, 1)) for z in (b["fb_top"], b["rb_top"], b["belt"] + 0.06)]
    paint_idx = set(paint_idx)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    for co, no in planes:
        faces = [f for f in bm.faces if f.material_index in paint_idx]
        edges = list({e for f in faces for e in f.edges})
        verts = list({v for f in faces for v in f.verts})
        bmesh.ops.bisect_plane(bm, geom=faces + edges + verts, plane_co=co, plane_no=no, dist=0.002)
    bm.to_mesh(ob.data)
    bm.free()


def assign_panels(c, n, s, wheels, hw, slug):
    """Panel name per paint face from its position on the body."""
    L = s["L"]
    xf = L / 2 - c[:, 0]
    z = c[:, 2]
    side = np.where(c[:, 1] >= 0, "l", "r")
    b = bounds(s, wheels)
    fwx, rwx, r, belt, cowl, end_cab = b["fwx"], b["rwx"], b["r"], b["belt"], b["cowl"], b["end_cab"]
    door_end, rdoor_end, fb_top, rb_top = b["door_end"], b["rdoor_end"], b["fb_top"], b["rb_top"]
    truck = s["type"] == "truck"
    back = "bed" if truck else "trunk"
    top = n[:, 2] > 0.5
    outer = np.abs(c[:, 1]) > hw * 0.8
    out = np.empty(len(c), dtype=object)
    for i in range(len(c)):
        x, zz = xf[i], z[i]
        sd = side[i]
        if x < fwx - 0.8 * r and zz < fb_top:
            p = "front_bumper"
        elif x > rwx + 0.8 * r and zz < rb_top:
            p = "rear_bumper"
        elif not truck and n[i, 0] < -0.55 and x > L - 0.7:
            p = back
        elif truck and x > end_cab + 0.05:
            p = "bed" if (top[i] and not outer[i]) or n[i, 0] < -0.55 or abs(c[i, 1]) < hw * 0.85 else "quarter_r" + sd
            if zz > belt + 0.25 and abs(c[i, 1]) < hw * 0.85:
                p = "bed"
        elif zz > belt + 0.06 and cowl - 0.05 < x < end_cab + 0.05:
            p = "roof"
        elif x < cowl:
            if (top[i] and not outer[i]) or (abs(c[i, 1]) < hw * 0.6 and n[i, 0] > -0.3):
                p = "hood"
            else:
                p = "fender_f" + sd
        elif x > end_cab:
            p = back if (top[i] and not outer[i]) or (abs(c[i, 1]) < hw * 0.6 and n[i, 0] < 0.3) else "quarter_r" + sd
        elif top[i] and not outer[i] and x < cowl + 0.25:
            p = "hood"
        elif x < door_end:
            p = "door_f" + sd
        elif rdoor_end and x < rdoor_end:
            p = "door_r" + sd
        else:
            p = "quarter_r" + sd
        out[i] = p
    return out.astype(str)


def style_wheel(ob, w, mats, c3):
    """Surface roles the view restyles: rubber (tyre), rim, disc (brakes and hub, inboard)."""
    me = ob.data
    names = [m.name if m else "" for m in me.materials]
    c, _, mi = face_arrays(me)
    d = c - np.array(w["c"])
    rad = np.hypot(d[:, 0], d[:, 2])
    out = d[:, 1] * w["side"]
    comp = components(me)
    V = vert_array(me)
    ls, lt, lv = face_verts(me)
    vd = V - np.array(w["c"])
    vrad = np.hypot(vd[:, 0], vd[:, 2])
    vout = vd[:, 1] * w["side"]
    # per component: smallest radius and how far out it reaches
    vcomp = np.zeros(len(V), np.int64)
    vcomp[lv] = np.repeat(comp, lt)
    ncomp = comp.max() + 1 if len(comp) else 0
    cmin = np.full(ncomp, 9.0)
    np.minimum.at(cmin, vcomp[lv], vrad[lv])
    cout = np.full(ncomp, -9.0)
    np.maximum.at(cout, vcomp[lv], vout[lv])
    tyre_mat = np.array([bool(re.search(c3.get("tyre", TYRE), n)) for n in names] + [False])
    role = np.where(cout[comp] >= w["hw"] * 0.25, 1, 2)
    role[(cmin[comp] > w["r"] * 0.55)] = 0
    role[tyre_mat[mi]] = 0
    role[rad > w["r"] * 0.9] = 0
    set_materials(ob, mats, role)


# ------------------------------------------------------------------ debug renders

COLORS = {
    "hood": (0.9, 0.2, 0.2), "front_bumper": (0.9, 0.6, 0.1), "rear_bumper": (0.6, 0.4, 0.1), "roof": (0.2, 0.5, 0.9),
    "trunk": (0.6, 0.2, 0.8), "bed": (0.6, 0.2, 0.8), "fender_fl": (0.2, 0.8, 0.3), "fender_fr": (0.2, 0.8, 0.3),
    "door_fl": (0.95, 0.9, 0.2), "door_fr": (0.95, 0.9, 0.2), "door_rl": (0.2, 0.9, 0.9), "door_rr": (0.2, 0.9, 0.9),
    "quarter_rl": (0.9, 0.4, 0.7), "quarter_rr": (0.9, 0.4, 0.7), "glass": (0.6, 0.85, 1.0),
}


def test_render(slug, out, final, core):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 6
    sc.cycles.use_denoising = False
    sc.cycles.max_bounces = 2
    sc.render.resolution_x, sc.render.resolution_y = 800, 420
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.color = (0.8, 0.8, 0.8)
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.9, 0.9, 1)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3
    sun.rotation_euler = (0.6, 0.3, 0.8)
    sc.collection.objects.link(sun)

    def colour(ob, col):
        m = R.simple_mat("dbg", col, rough=0.6)
        ob.data.materials.clear()
        ob.data.materials.append(m)
    for name, ob in final.items():
        k = name[5:] if name.startswith("part_") else name
        col = COLORS.get(k)
        if col is None:
            col = (0.1, 0.1, 0.1) if k.startswith("wheel") else (1, 1, 1) if k.startswith("head") else \
                (1, 0, 0) if k.startswith("tail") else (0.3, 0.9, 0.5) if k.startswith("mirror") else (1, 0, 1)
        if k.endswith("r") and (k.startswith("door") or k.startswith("fender") or k.startswith("quarter")):
            col = tuple(v * 0.6 for v in col)
        if k in ("core", "liner_trim"):
            col = (0.45, 0.45, 0.45)
        colour(ob, col)
    cam = bpy.data.objects.get("cam") or bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    sc.camera = cam
    for view, pos in (("front", (5.5, 5.0, 2.6)), ("rear", (-5.5, -5.0, 3.2)), ("side", (0, 9, 0.9))):
        cam.location = pos
        tgt = Vector((0, 0, 0.6))
        cam.rotation_euler = (tgt - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = 40
        sc.render.filepath = os.path.join(out, "%s_parts_%s.png" % (slug, view))
        bpy.ops.render.render(write_still=True)


def main():
    out = sys.argv[1]
    args = sys.argv[2:]
    test = bool(args) and args[0] == "test"
    if test:
        args = args[1:]
    os.makedirs(out, exist_ok=True)
    for slug in args or list(CFG):
        print("==", slug, flush=True)
        res = build(slug, out, test)
        print("done %s tris=%d size=%.2fMB panels=%s" % (slug, res["tris"], res["size"] / 1e6, ",".join(res["panels"])),
              flush=True)


if __name__ == "__main__":
    main()
