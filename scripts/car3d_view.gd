class_name Car3DView
extends SubViewportContainer
## Real-time 3D car for the service bay. Drag to orbit, scroll or pinch to zoom, click a part to select it.
## Loads res://assets/cars3d/<slug>.glb (built by tools/car3d.py, or any uploaded model with the same node names).

signal part_clicked(part: String)
signal part_hovered(part: String)

const PAINT_SHADER := preload("res://shaders/car_paint.gdshader")
const PAINT_PARTS := ["front_bumper", "hood", "fender_fl", "fender_fr", "door_fl", "door_fr", "door_rl", "door_rr",
	"quarter_rl", "quarter_rr", "roof", "trunk", "rear_bumper", "bed", "rocker_l", "rocker_r"]
const TRIM_PARTS := ["beltline", "grille"]
const RIM_COLORS := {"silver": Color(0.78, 0.79, 0.81), "black": Color(0.07, 0.07, 0.08), "gunmetal": Color(0.25, 0.27, 0.3), "gold": Color(0.55, 0.42, 0.22)}

var car: Dictionary = {}
var selected := ""
var hovered := ""
var yaw := -0.75
var pitch := 0.22
var dist := 7.5
var _vp: SubViewport
var _cam: Camera3D
var _pivot: Node3D
var _model: Node3D
var _meshes := {}       # part name -> MeshInstance3D
var _paint_mats := {}   # part name -> ShaderMaterial
var _pickables := []    # [MeshInstance3D, mesh key] for every clickable mesh
var _pick_cache := {}   # MeshInstance3D -> [faces: PackedVector3Array, chunk boxes: Array[AABB]]
var _mat_cache := {}    # reused materials so hover/refresh never allocates or recompiles shaders
var _hover_pos := Vector2.ZERO
var _hover_dirty := false
var _hover_next_ms := 0
var _frames_seen := 0
var _slow_frames := 0
var _dragging := false
var _drag_moved := 0.0
var _smoke: CPUParticles3D
var _floor: MeshInstance3D
var _auto_spin := true


func _init() -> void:
	stretch = true
	mouse_filter = Control.MOUSE_FILTER_STOP
	_vp = SubViewport.new()
	_vp.transparent_bg = true
	_vp.own_world_3d = true
	_vp.msaa_3d = Viewport.MSAA_4X
	_vp.physics_object_picking = false
	add_child(_vp)
	var env := Environment.new()
	env.background_mode = Environment.BG_CLEAR_COLOR
	var sky := Sky.new()
	var sm := ProceduralSkyMaterial.new()
	sm.sky_top_color = Color(0.55, 0.62, 0.75)
	sm.sky_horizon_color = Color(0.95, 0.85, 0.72)
	sm.ground_bottom_color = Color(0.12, 0.11, 0.1)
	sm.ground_horizon_color = Color(0.32, 0.3, 0.28)
	sky.sky_material = sm
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.ambient_light_energy = 0.55
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.tonemap_exposure = 0.9
	var we := WorldEnvironment.new()
	we.environment = env
	_vp.add_child(we)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55, -35, 0)
	sun.light_energy = 1.05
	sun.light_color = Color(1.0, 0.95, 0.88)
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 25.0
	_vp.add_child(sun)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-20, 140, 0)
	fill.light_energy = 0.45
	fill.light_color = Color(0.75, 0.85, 1.0)
	_vp.add_child(fill)
	# rim light from behind so the outline separates from the garage
	var rim := DirectionalLight3D.new()
	rim.rotation_degrees = Vector3(-15, 200, 0)
	rim.light_energy = 0.35
	rim.light_color = Color(0.85, 0.92, 1.0)
	_vp.add_child(rim)
	# floor: catches the car's shadow and a soft contact shadow, fades out at the edges
	var floor := MeshInstance3D.new()
	_floor = floor
	var pm := PlaneMesh.new()
	pm.size = Vector2(14, 10)
	floor.mesh = pm
	var fmat := ShaderMaterial.new()
	var fsh := Shader.new()
	fsh.code = """
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_disabled, unshaded;
uniform vec2 car_size = vec2(4.8, 1.9);
varying vec3 wp;
void vertex() { wp = VERTEX; }
void fragment() {
	vec2 q = abs(wp.xz) / (car_size * 0.5 + vec2(0.35));
	float contact = 1.0 - smoothstep(0.55, 1.15, length(pow(q, vec2(3.0))) );
	float edge = 1.0 - smoothstep(3.0, 6.5, length(wp.xz));
	ALBEDO = vec3(0.0);
	ALPHA = edge * (0.25 + contact * 0.6);
}
"""
	fmat.shader = fsh
	floor.material_override = fmat
	_vp.add_child(floor)
	_pivot = Node3D.new()
	_vp.add_child(_pivot)
	_cam = Camera3D.new()
	_cam.fov = 38
	_vp.add_child(_cam)
	_place_camera()


func set_car(c: Dictionary) -> void:
	car = c
	Game.ensure_damage(car)
	if _model:
		_model.queue_free()
	_meshes.clear()
	_paint_mats.clear()
	_pickables.clear()
	_pick_cache.clear()
	_mat_cache.clear()
	var path := "res://assets/cars3d/%s.glb" % CarArt.slug(car.get("model", ""))
	if not ResourceLoader.exists(path):
		return
	var scene: PackedScene = load(path)
	_model = scene.instantiate()
	_pivot.add_child(_model)
	_collect(_model)
	# Read every clickable mesh's triangles now, before the car is drawn. get_faces() reads the vertex
	# buffers back from the GPU; done later (on the first hover) each read stalls behind a rendered frame.
	for pk in _pickables:
		_pick_data(pk[0])
	# center and size the floor shadow to the car
	var aabb := AABB()
	var first := true
	for n in _meshes:
		var mi: MeshInstance3D = _meshes[n]
		var a: AABB = mi.global_transform * mi.get_aabb() if mi.is_inside_tree() else mi.get_aabb()
		aabb = a if first else aabb.merge(a)
		first = false
	(_floor.material_override as ShaderMaterial).set_shader_parameter("car_size", Vector2(aabb.size.x, aabb.size.z))
	dist = max(7.0, aabb.size.x * 1.95)
	_pivot.position.y = 0.0
	refresh()


func _collect(node: Node) -> void:
	for ch in node.get_children():
		if ch is MeshInstance3D:
			var nm := String(ch.name)
			var key := nm.trim_prefix("part_")
			_meshes[key] = ch
			if key != "underbody" and key != "core" and not key.begins_with("liner") and not key.begins_with("mirror_stalk"):
				# No physics bodies: 40k-triangle trimesh shapes cost memory and load time, and the old
				# physics query (on _vp.world_3d, which is null with own_world_3d) crashed release web
				# builds on the first mouse move. _pick() tests triangles on the CPU instead.
				_pickables.append([ch, key])
		_collect(ch)


## Re-applies paint color, trim, rims and every panel's damage from the car's data.
func refresh() -> void:
	if car.is_empty() or _meshes.is_empty():
		return
	var paint := CarArt.paint_for(car)
	var seed_i := 0
	for key in _meshes:
		var mi: MeshInstance3D = _meshes[key]
		seed_i += 1
		if key in PAINT_PARTS or key.begins_with("mirror_l") or key.begins_with("mirror_r"):
			var base: Material = mi.get_active_material(0)
			if key.begins_with("rocker") and base is BaseMaterial3D and (base as BaseMaterial3D).albedo_color.r < 0.1:
				continue  # plastic cladding stays black
			var sm: ShaderMaterial = _paint_mats.get(key)
			if sm == null:
				sm = ShaderMaterial.new()
				sm.shader = PAINT_SHADER
				_paint_mats[key] = sm
				mi.material_override = sm
			var panel: String = key
			if key.begins_with("mirror"):
				panel = "door_f" + key.substr(7, 1)
			var d: Dictionary = car.damage.get(panel, {})
			sm.set_shader_parameter("paint_color", paint.srgb_to_linear() if false else paint)
			sm.set_shader_parameter("rust", d.get("rust", 0.0))
			sm.set_shader_parameter("scratch", d.get("scratch", 0.0))
			sm.set_shader_parameter("dent", d.get("dent", 0.0))
			sm.set_shader_parameter("dirt", 0.0 if car.get("detailed", false) else 0.6)
			sm.set_shader_parameter("seed", float(seed_i))
			sm.set_shader_parameter("highlight", _hl(key, panel))
		elif key in TRIM_PARTS or key.begins_with("handle_"):
			var kind: String = car.get("trim", "chrome")
			if key == "grille" and kind == "body":
				kind = "black"
			var tm := _trim_mat(kind, paint)
			if mi.material_override != tm:
				mi.material_override = tm
		elif key.begins_with("headlight") or key.begins_with("taillight"):
			var broken: bool = car.damage.has(key)
			# one cached material per light; emission stays enabled (black when off) so highlighting
			# only changes uniforms and never compiles a new shader variant
			var m: StandardMaterial3D = _cached_mat("light:" + key)
			m.emission_enabled = true
			if key.begins_with("head"):
				m.albedo_color = Color(0.25, 0.25, 0.27) if broken else Color(0.92, 0.94, 0.98)
				m.metallic = 0.0 if broken else 0.7
				m.roughness = 0.8 if broken else 0.05
				m.emission = Color.BLACK if broken else Color(0.9, 0.95, 1.0)
				m.emission_energy_multiplier = 0.25
			else:
				m.albedo_color = Color(0.2, 0.05, 0.05) if broken else Color(0.75, 0.04, 0.03)
				m.roughness = 0.8 if broken else 0.1
				m.emission = Color.BLACK if broken else Color(0.8, 0.0, 0.0)
				m.emission_energy_multiplier = 0.3
			var h := _hl(key, key)
			if h.a > 0:
				m.emission = h
				m.emission_energy_multiplier = 0.6
			if mi.material_override != m:
				mi.material_override = m
		elif key.begins_with("wheel_"):
			_style_wheel(mi, key)
		elif key == "glass":
			var h := _hl(key, "interior")
			if h.a > 0:
				var gm: StandardMaterial3D = _cached_mat("glass")
				gm.albedo_color = Color(0.05, 0.08, 0.1)
				gm.metallic = 0.2
				gm.roughness = 0.05
				gm.emission_enabled = true
				gm.emission = h
				gm.emission_energy_multiplier = 0.3
				mi.material_override = gm
			elif mi.material_override != null:
				mi.material_override = null
	# engine smoke from under the hood when the engine is in bad shape
	var smoke_on: bool = car.parts.engine < 35
	if smoke_on and _smoke == null and _meshes.has("hood"):
		_smoke = CPUParticles3D.new()
		_smoke.amount = 40
		_smoke.lifetime = 2.2
		_smoke.direction = Vector3(0, 1, 0)
		_smoke.spread = 25
		_smoke.initial_velocity_min = 0.4
		_smoke.initial_velocity_max = 0.8
		_smoke.gravity = Vector3(0, 0.2, 0)
		_smoke.scale_amount_min = 0.4
		_smoke.scale_amount_max = 1.2
		var qm := QuadMesh.new()
		qm.size = Vector2(0.35, 0.35)
		var smm := StandardMaterial3D.new()
		smm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		smm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		smm.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
		smm.albedo_color = Color(0.6, 0.6, 0.62, 0.22)
		smm.vertex_color_use_as_albedo = true
		qm.material = smm
		_smoke.mesh = qm
		var grad := Gradient.new()
		grad.set_color(0, Color(1, 1, 1, 0.8))
		grad.set_color(1, Color(1, 1, 1, 0.0))
		_smoke.color_ramp = grad
		var hood: MeshInstance3D = _meshes["hood"]
		var ab := hood.get_aabb()
		_smoke.position = ab.get_center() + Vector3(0, ab.size.y * 0.5, 0)
		_smoke.emission_shape = CPUParticles3D.EMISSION_SHAPE_BOX
		_smoke.emission_box_extents = Vector3(ab.size.x * 0.3, 0.02, ab.size.z * 0.3)
		_pivot.add_child(_smoke)
	if _smoke:
		_smoke.emitting = smoke_on


func _hl(key: String, panel: String) -> Color:
	if key == selected or panel == selected:
		return Color(1.0, 0.78, 0.25, 0.9)
	if key == hovered or panel == hovered:
		return Color(0.2, 0.85, 1.0, 0.7)
	return Color(0, 0, 0, 0)


func _cached_mat(id: String) -> StandardMaterial3D:
	var m: StandardMaterial3D = _mat_cache.get(id)
	if m == null:
		m = StandardMaterial3D.new()
		_mat_cache[id] = m
	return m


func _trim_mat(kind: String, paint: Color) -> StandardMaterial3D:
	var id := "trim:%s:%s" % [kind, paint.to_html() if kind != "chrome" and kind != "black" else ""]
	if _mat_cache.has(id):
		return _mat_cache[id]
	var m := _cached_mat(id)
	match kind:
		"chrome":
			m.albedo_color = Color(0.8, 0.81, 0.84)
			m.metallic = 1.0
			m.roughness = 0.12
		"black":
			m.albedo_color = Color(0.03, 0.03, 0.035)
			m.metallic = 0.2
			m.roughness = 0.15
		_:
			m.albedo_color = paint
			m.metallic = 0.35
			m.roughness = 0.28
	return m


func _style_wheel(mi: MeshInstance3D, key: String) -> void:
	var worn: float = 1.0 - car.parts.tires / 100.0
	var hl := _hl(key, "tires")
	for i in mi.mesh.get_surface_count():
		var base: Material = mi.mesh.surface_get_material(i)
		var name := String(base.resource_name) if base else ""
		var cid := "wheel:%s:%d" % [key, i]
		var m: StandardMaterial3D = _mat_cache.get(cid)
		if m == null:
			m = (base.duplicate() if base is StandardMaterial3D else StandardMaterial3D.new())
			_mat_cache[cid] = m
			if not m.emission_enabled:
				# keep emission on (black) so the hover glow is a uniform change, not a shader recompile
				m.emission_enabled = true
				m.emission = Color.BLACK
				m.emission_energy_multiplier = 0.0
			_mat_cache[cid + ":base"] = [m.emission, m.emission_energy_multiplier]
		var eb: Array = _mat_cache[cid + ":base"]
		m.emission = eb[0]
		m.emission_energy_multiplier = eb[1]
		if name == "rim":
			m.albedo_color = RIM_COLORS.get(car.get("rims", "silver"), RIM_COLORS.silver)
			m.metallic = 0.9 if car.get("rims", "silver") in ["silver", "gold"] else 0.5
			m.roughness = 0.2 if car.get("rims", "silver") != "black" else 0.45
		elif name == "rubber":
			# bald tires go grey and shiny, flat ones sag
			m.albedo_color = Color(0.03, 0.03, 0.03).lerp(Color(0.16, 0.16, 0.16), worn)
			m.roughness = lerp(0.9, 0.55, worn)
		elif name == "disc":
			m.albedo_color = Color(0.35, 0.35, 0.36).lerp(Color(0.42, 0.22, 0.1), clamp(worn * 1.4 - 0.4, 0, 1))
			m.metallic = lerp(0.9, 0.2, worn)
		if hl.a > 0:
			m.emission_enabled = true
			m.emission = hl
			m.emission_energy_multiplier = 0.25
		if mi.get_surface_override_material(i) != m:
			mi.set_surface_override_material(i, m)
	var flat: bool = car.parts.tires < 25 and key == "wheel_fl"
	mi.scale = Vector3(1, 0.93, 1) if flat else Vector3.ONE


func _process(delta: float) -> void:
	# software GL / weak GPUs: 4x MSAA alone can double the frame time, so drop it if most frames are slow
	if _vp.msaa_3d != Viewport.MSAA_DISABLED:
		_frames_seen += 1
		if delta > 0.08:
			_slow_frames += 1
		if _frames_seen >= 20:
			if _slow_frames >= 15:
				_vp.msaa_3d = Viewport.MSAA_DISABLED
			_frames_seen = 0
			_slow_frames = 0
	if _auto_spin and not _dragging and selected == "":
		yaw += delta * 0.12
		_place_camera()
	# hover picking: at most one pick per frame and ~20 per second, however many motion events arrive
	if _hover_dirty and not _dragging and Time.get_ticks_msec() >= _hover_next_ms:
		_hover_dirty = false
		_hover_next_ms = Time.get_ticks_msec() + 50
		_set_hover(_pick(_hover_pos))


func _set_hover(p: String) -> void:
	if p != hovered:
		hovered = p
		part_hovered.emit(p)
		refresh()


func _place_camera() -> void:
	var tgt := Vector3(0, 0.65, 0)
	var off := Vector3(cos(pitch) * sin(yaw), sin(pitch), cos(pitch) * cos(yaw)) * dist
	_cam.position = tgt + off
	if _cam.is_inside_tree():
		_cam.look_at(tgt, Vector3.UP)
	else:
		_cam.basis = Basis.looking_at(-off, Vector3.UP)


func _gui_input(ev: InputEvent) -> void:
	if ev is InputEventMouseButton:
		if ev.button_index == MOUSE_BUTTON_LEFT:
			if ev.pressed:
				_dragging = true
				_drag_moved = 0.0
			else:
				_dragging = false
				if _drag_moved < 6.0:
					var p := _pick(ev.position)
					select(p)
					part_clicked.emit(p)
			accept_event()
		elif ev.button_index == MOUSE_BUTTON_WHEEL_UP and ev.pressed:
			dist = max(3.5, dist * 0.92)
			_place_camera()
			accept_event()
		elif ev.button_index == MOUSE_BUTTON_WHEEL_DOWN and ev.pressed:
			dist = min(14.0, dist * 1.08)
			_place_camera()
			accept_event()
	elif ev is InputEventMouseMotion:
		if _dragging:
			_drag_moved += ev.relative.length()
			_auto_spin = false
			yaw -= ev.relative.x * 0.008
			pitch = clamp(pitch + ev.relative.y * 0.006, 0.02, 1.2)
			_place_camera()
		else:
			_hover_pos = ev.position
			_hover_dirty = true
	elif ev is InputEventMagnifyGesture:
		dist = clamp(dist / ev.factor, 3.5, 14.0)
		_place_camera()


func select(p: String) -> void:
	selected = p
	if p != "":
		_auto_spin = false
	refresh()


## The game part under a point in this control ("" for none).
## Pure CPU ray cast: mesh AABBs first, then boxes of PICK_CHUNK triangles, then the triangles inside the boxes hit.
func _pick(pos: Vector2) -> String:
	if size.x <= 0 or size.y <= 0 or _pickables.is_empty():
		return ""
	var vp_pos := pos * Vector2(_vp.size) / size
	var from := _cam.project_ray_origin(vp_pos)
	var to := from + _cam.project_ray_normal(vp_pos) * 50.0
	# candidate meshes whose box the ray crosses, nearest first (t runs 0..1 along the segment, the same in every space)
	var cands := []
	for pk in _pickables:
		var mi: MeshInstance3D = pk[0]
		if not is_instance_valid(mi) or not mi.is_visible_in_tree() or mi.mesh == null:
			continue
		var inv := mi.global_transform.affine_inverse()
		var lf := inv * from
		var lt := inv * to
		var box := mi.get_aabb()
		var t := 0.0
		if not box.has_point(lf):
			var hit = box.intersects_segment(lf, lt)
			if hit == null:
				continue
			t = _seg_t(lf, lt, hit)
		cands.append([t, mi, pk[1], lf, lt])
	cands.sort_custom(func(a, b): return a[0] < b[0])
	var best_t := INF
	var best_key := ""
	for c in cands:
		if c[0] >= best_t:
			break
		var t := _ray_mesh(c[1], c[3], c[4], best_t)
		if t < best_t:
			best_t = t
			best_key = c[2]
	return part_of(best_key)


const PICK_CHUNK := 32


## Nearest hit of a local-space segment on a mesh, as t in 0..1 (best_t when nothing nearer). Builds its boxes on first use.
func _ray_mesh(mi: MeshInstance3D, lf: Vector3, lt: Vector3, best_t: float) -> float:
	var data := _pick_data(mi)
	var faces: PackedVector3Array = data[0]
	var boxes: Array = data[1]
	var n := faces.size()
	for bi in boxes.size():
		var b: AABB = boxes[bi]
		if not b.has_point(lf):
			var bh = b.intersects_segment(lf, lt)
			if bh == null or _seg_t(lf, lt, bh) >= best_t:
				continue
		var i0: int = bi * PICK_CHUNK * 3
		for i in range(i0, mini(i0 + PICK_CHUNK * 3, n), 3):
			var p = Geometry3D.segment_intersects_triangle(lf, lt, faces[i], faces[i + 1], faces[i + 2])
			if p != null:
				var t := _seg_t(lf, lt, p)
				if t < best_t:
					best_t = t
	return best_t


## [triangle corners, one box per PICK_CHUNK triangles] for a mesh, cached for this car.
func _pick_data(mi: MeshInstance3D) -> Array:
	var data: Array = _pick_cache.get(mi, [])
	if data.is_empty():
		var faces := mi.mesh.get_faces()
		var boxes := []
		var n := faces.size()
		var step := PICK_CHUNK * 3
		for i in range(0, n, step):
			var b := AABB(faces[i], Vector3.ZERO)
			for k in range(i + 1, mini(i + step, n)):
				b = b.expand(faces[k])
			boxes.append(b.grow(0.001))
		data = [faces, boxes]
		_pick_cache[mi] = data
	return data


static func _seg_t(a: Vector3, b: Vector3, p: Vector3) -> float:
	var d := b - a
	return (p - a).dot(d) / d.length_squared()


## Maps a mesh to what you repair: panels and lights are body work, wheels are tires, glass is the interior.
static func part_of(key: String) -> String:
	if key.begins_with("wheel_"):
		return "tires"
	if key in ["glass", "pillars", "beltline"]:
		return "interior"
	if key == "grille" or key.begins_with("plate"):
		return "engine"
	if key.begins_with("mirror"):
		return "door_f" + key.substr(7, 1)
	if key.begins_with("handle_"):
		return "door_" + key.substr(7)
	if key.begins_with("rocker") or key == "underbody":
		return "transmission"
	return key
