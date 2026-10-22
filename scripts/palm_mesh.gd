class_name PalmMesh
## Procedural coastal palms for the 3D views (showroom window, garage door). A whole row is built into two
## ArrayMeshes, trunks and fronds, so any number of palms costs two draw calls. No assets, so no licence.

const TRUNK_SIDES := 7
const TRUNK_RINGS := 10
const FRONDS := 11
const FROND_SEGS := 6


## One node holding the trunks and fronds of a palm at each base position (heights 7-10 m by default).
## `seed_i` makes the row repeatable between visits.
static func row(bases: Array, seed_i := 1, h_min := 7.0, h_max := 10.5) -> Node3D:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_i
	var trunk := SurfaceTool.new()
	trunk.begin(Mesh.PRIMITIVE_TRIANGLES)
	var leaves := SurfaceTool.new()
	leaves.begin(Mesh.PRIMITIVE_TRIANGLES)
	for b in bases:
		var h := rng.randf_range(h_min, h_max)
		var lean := Vector3(rng.randf_range(-1, 1), 0, rng.randf_range(-1, 1)).normalized() * rng.randf_range(0.4, 1.4)
		var top := _trunk(trunk, b, h, lean, rng)
		_crown(leaves, top, rng)
	trunk.generate_normals()
	var root := Node3D.new()
	root.name = "Palms"
	var tm := MeshInstance3D.new()
	tm.mesh = trunk.commit()
	tm.material_override = _trunk_mat()
	root.add_child(tm)
	var lm := MeshInstance3D.new()
	lm.mesh = leaves.commit()
	lm.material_override = _leaf_mat()
	root.add_child(lm)
	return root


static func _trunk(st: SurfaceTool, base: Vector3, h: float, lean: Vector3, rng: RandomNumberGenerator) -> Vector3:
	var prev: Array = []
	var top := base
	for r in TRUNK_RINGS + 1:
		var t := float(r) / TRUNK_RINGS
		# a gentle curve: the lean grows with the square of the height, the classic coastal palm bow
		var c := base + Vector3(0, h * t, 0) + lean * t * t
		var rad := lerpf(0.26, 0.15, t) * (1.0 + 0.08 * sin(t * 40.0))   # ringed bark
		var ring: Array = []
		for s in TRUNK_SIDES:
			var a := TAU * s / TRUNK_SIDES
			ring.append(c + Vector3(cos(a) * rad, 0, sin(a) * rad))
		if r > 0:
			var shade := Color(0.55, 0.45, 0.34).lerp(Color(0.66, 0.56, 0.42), t)
			for s in TRUNK_SIDES:
				var s2 := (s + 1) % TRUNK_SIDES
				st.set_color(shade)
				for v in [prev[s], ring[s], ring[s2], prev[s], ring[s2], prev[s2]]:
					st.add_vertex(v)
		prev = ring
		top = c
	return top


static func _crown(st: SurfaceTool, top: Vector3, rng: RandomNumberGenerator) -> void:
	var spin := rng.randf() * TAU
	for f in FRONDS:
		var a := spin + TAU * f / FRONDS + rng.randf_range(-0.15, 0.15)
		var dir := Vector3(cos(a), 0, sin(a))
		var side := Vector3(-dir.z, 0, dir.x)
		var length := rng.randf_range(2.6, 3.6)
		var rise := rng.randf_range(0.5, 1.3)    # fronds rise, then droop under their own weight
		var col := Color(0.2, 0.42, 0.16).lerp(Color(0.36, 0.56, 0.2), rng.randf())
		var pts: Array = []
		for k in FROND_SEGS + 1:
			var t := float(k) / FROND_SEGS
			var p := top + dir * length * t + Vector3(0, rise * t - (rise + 1.8) * t * t, 0)
			var w := 0.55 * sin(PI * minf(1.0, t * 1.15 + 0.08))
			pts.append([p, w])
		for k in FROND_SEGS:
			var a0: Vector3 = pts[k][0]
			var a1: Vector3 = pts[k + 1][0]
			var w0: float = pts[k][1]
			var w1: float = pts[k + 1][1]
			# a shallow V across the frond (the midrib sits higher) so it reads from below and from the side
			var l0 := a0 - side * w0 - Vector3(0, w0 * 0.25, 0)
			var r0 := a0 + side * w0 - Vector3(0, w0 * 0.25, 0)
			var l1 := a1 - side * w1 - Vector3(0, w1 * 0.25, 0)
			var r1 := a1 + side * w1 - Vector3(0, w1 * 0.25, 0)
			var c := col.darkened(0.12 * float(k) / FROND_SEGS)
			for tri in [[l0, a0, a1], [l0, a1, l1], [a0, r0, r1], [a0, r1, a1]]:
				var n: Vector3 = (tri[1] - tri[0]).cross(tri[2] - tri[0]).normalized()
				if n.y < 0.0:
					n = -n
				for v in tri:
					st.set_color(c)
					st.set_normal(n)
					st.add_vertex(v)


static var _tm: StandardMaterial3D
static var _lm: StandardMaterial3D


static func _trunk_mat() -> StandardMaterial3D:
	if _tm == null:
		_tm = StandardMaterial3D.new()
		_tm.vertex_color_use_as_albedo = true
		_tm.vertex_color_is_srgb = true
		_tm.roughness = 0.9
	return _tm


static func _leaf_mat() -> StandardMaterial3D:
	if _lm == null:
		_lm = StandardMaterial3D.new()
		_lm.vertex_color_use_as_albedo = true
		_lm.vertex_color_is_srgb = true
		_lm.roughness = 0.7
		_lm.cull_mode = BaseMaterial3D.CULL_DISABLED
		_lm.backlight_enabled = true      # sun through the fronds, the bright green rim in the picks
		_lm.backlight = Color(0.35, 0.5, 0.15)
	return _lm
