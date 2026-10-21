class_name Car3DView
extends SubViewportContainer
## Real-time 3D car for the service bay. Drag to orbit, scroll or pinch to zoom, click a part to select it.
## Loads res://assets/cars3d/<slug>.glb (built by tools/car3d.py, or any uploaded model with the same node names).

signal part_clicked(part: String)
signal part_hovered(part: String)

const PAINT_SHADER := preload("res://shaders/car_paint.gdshader")
const SURFACE_SHADER := preload("res://shaders/env_surface.gdshader")
const GLASS_SHADER := preload("res://shaders/env_glass.gdshader")
const TIRE_SHADER := preload("res://shaders/car_tire.gdshader")
const GARAGE_HDR := "res://assets/cc0/sky/autoshop_1k.hdr"     # Poly Haven "Autoshop 01" (CC0): desktop sky light
const GARAGE_ENV := "res://assets/cc0/sky/autoshop_env.jpg"    # same, tone-mapped: hand-rolled paint reflections on the web
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
var pickable := true   # false: skip reading triangles for picking (showroom display cars)
var _env: Texture2D     # web only: the garage HDRI the hand-rolled reflections sample
var _base_dist := 7.5   # the framing set_car picked for this car, before any zoom
var prewarming := false   # rendered behind the title: those frames say nothing about this view's own cost


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
	if RenderQuality.is_forward_plus() and ResourceLoader.exists(GARAGE_HDR):
		# desktop: a real workshop HDRI lights the car and shows in its paint, glass and chrome
		var pm := PanoramaSkyMaterial.new()
		pm.panorama = load(GARAGE_HDR)
		sky.sky_material = pm
		sky.radiance_size = Sky.RADIANCE_SIZE_256
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
	RenderQuality.apply_environment(env, _vp, sun)
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
	if _smoke:
		_smoke.queue_free()   # sized and placed for the last car's hood
		_smoke = null
	var path := model_path(CarArt.slug(car.get("model", "")))
	if not ResourceLoader.exists(path):
		return
	var scene: PackedScene = load(path)
	_model = scene.instantiate()
	_pivot.add_child(_model)
	_collect(_model)
	# Read every clickable mesh's triangles now, before the car is drawn. get_faces() reads the vertex
	# buffers back from the GPU; done later (on the first hover) each read stalls behind a rendered frame.
	if pickable:
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
	_base_dist = dist
	_pivot.position.y = 0.0
	refresh()


## A styled copy of the car's model (paint, damage, trim, rims, glass) for another 3D scene, e.g. the showroom.
## The model's local origin sits at the car's footprint centre on the ground.
static func build_model(c: Dictionary) -> Node3D:
	var v := Car3DView.new()
	v.pickable = false
	v.set_car(c)
	var m := v._model
	if m:
		v._pivot.remove_child(m)
	v.free()
	return m


## The PC build ships a high-detail set (about 3x the triangles, 1k textures) in assets/cars3d_hd, left out of the
## web export to keep the download small; everything else uses assets/cars3d.
static func model_path(slug: String) -> String:
	var hd := "res://assets/cars3d_hd/%s.glb" % slug
	if Settings.is_desktop() and ResourceLoader.exists(hd):
		return hd
	return "res://assets/cars3d/%s.glb" % slug


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
				if _env_map():
					sm.set_shader_parameter("env_map", _env_map())
					sm.set_shader_parameter("env_strength", 0.45)
					sm.set_shader_parameter("clearcoat_k", 0.0)
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
			var tm: Material = _trim_mat(kind, paint)
			if key == "grille" and tm is ShaderMaterial:
				# grilles sit flush inside the bumper skin; tucked a few millimetres in, only the parts that
				# stand proud show instead of z-fighting through the paint
				tm = _env_surf("trim:grille:" + kind, Color(0.82, 0.83, 0.86) if kind == "chrome" else Color(0.025, 0.025, 0.03),
					1.0 if kind == "chrome" else 0.0, 0.06 if kind == "chrome" else 0.1)
				tm.set_shader_parameter("grow", -0.004)
			if mi.material_override != tm:
				mi.material_override = tm
		elif key.begins_with("headlight") or key.begins_with("taillight"):
			_style_light(mi, key)
		elif key.begins_with("wheel_"):
			_style_wheel(mi, key)
		elif key == "glass":
			# tinted, glossy safety glass: dark enough to read as glass, reflective at grazing angles
			var h := _hl(key, "interior")
			var gl := _glass_mat()
			gl.set_shader_parameter("tint", Color(0.05, 0.08, 0.1, 0.85) if h.a > 0 else Color(0.03, 0.045, 0.055, 0.66))
			gl.set_shader_parameter("glow", _glow(h, 0.3))
			for i in mi.mesh.get_surface_count():
				if mi.get_surface_override_material(i) != gl:
					mi.set_surface_override_material(i, gl)
		elif key == "core" or key.begins_with("liner") or key in ["underbody", "pillars", "arch", "plate_r"]:
			_style_detail(mi, key, paint)
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


## Web builds sample this for reflections; desktop (Forward+) has real sky reflections, so null there.
func _env_map() -> Texture2D:
	if _env == null and not RenderQuality.is_forward_plus() and ResourceLoader.exists(GARAGE_ENV):
		_env = load(GARAGE_ENV)
	return _env


## A cached glossy surface (chrome, alloy, lamp reflector, gloss plastic) that reflects the garage.
## "env_k" meta marks it so the showroom can point it at its own hall reflections.
func _env_surf(id: String, color: Color, metal: float, rough: float, tex: Texture2D = null) -> ShaderMaterial:
	var m: ShaderMaterial = _mat_cache.get(id)
	if m == null:
		m = ShaderMaterial.new()
		m.shader = SURFACE_SHADER
		var env := _env_map()
		m.set_shader_parameter("env_map", env)
		m.set_shader_parameter("env_strength", 0.8 if env else 0.0)
		m.set_meta("env_k", 0.8)
		_mat_cache[id] = m
	m.set_shader_parameter("albedo", color)
	m.set_shader_parameter("albedo_tex", tex)
	m.set_shader_parameter("metallic_v", metal)
	m.set_shader_parameter("rough_v", rough)
	return m


func _glass_mat() -> ShaderMaterial:
	var m: ShaderMaterial = _mat_cache.get("glass")
	if m == null:
		m = ShaderMaterial.new()
		m.shader = GLASS_SHADER
		var env := _env_map()
		m.set_shader_parameter("env_map", env)
		m.set_shader_parameter("env_strength", 0.9 if env else 0.0)
		m.set_shader_parameter("rough_v", 0.02)
		m.set_meta("env_k", 0.9)
		_mat_cache["glass"] = m
	return m


func _glow(h: Color, k: float) -> Vector3:
	return Vector3(h.r, h.g, h.b) * h.a * k


## Lamps per surface: dark housing, mirror reflector behind a clear lens, glowing LED strips.
## Broken lamps go dull and dark. Models with a single lamp surface get the lens-over-reflector look.
func _style_light(mi: MeshInstance3D, key: String) -> void:
	var broken: bool = car.damage.has(key)
	var head := key.begins_with("head")
	var g := _glow(_hl(key, key), 0.6)
	for i in mi.mesh.get_surface_count():
		var base: Material = mi.mesh.surface_get_material(i)
		var nm := String(base.resource_name) if base else ""
		var id := "light:%s:%d" % [key, i]
		var m: ShaderMaterial
		if broken:
			m = _env_surf(id, Color(0.2, 0.2, 0.21) if head else Color(0.18, 0.05, 0.05), 0.0, 0.75)
			m.set_shader_parameter("glow", g)
		elif nm == "lamp_housing" or nm == "gloss_black":
			m = _env_surf(id, Color(0.025, 0.026, 0.03), 0.0, 0.25)
			m.set_shader_parameter("glow", g)
		elif nm == "drl" or nm == "tail_led":
			m = _env_surf(id, Color(1, 1, 1) if nm == "drl" else Color(1.0, 0.1, 0.06), 0.0, 0.2)
			m.set_shader_parameter("glow", (Vector3(0.95, 0.97, 1.0) * 1.6 if nm == "drl" else Vector3(1.0, 0.05, 0.02) * 1.3) + g)
		elif nm == "tail_dark":
			m = _env_surf(id, Color(0.16, 0.01, 0.01), 0.0, 0.06)
			m.set_shader_parameter("glow", Vector3(0.12, 0.0, 0.0) + g)
		elif nm == "reverse":
			m = _env_surf(id, Color(0.75, 0.76, 0.78), 0.6, 0.05)
			m.set_shader_parameter("glow", g)
		elif head:
			# lens over a chrome reflector: mirror-bright with a faint cool glow
			m = _env_surf(id, Color(0.86, 0.88, 0.92), 1.0, 0.05)
			m.set_shader_parameter("glow", Vector3(0.16, 0.17, 0.19) + g)
		else:
			# red lens: glossy, deep, lit from inside
			m = _env_surf(id, Color(0.55, 0.03, 0.02), 0.0, 0.05)
			m.set_shader_parameter("glow", Vector3(0.42, 0.0, 0.0) + g)
		if mi.get_surface_override_material(i) != m:
			mi.set_surface_override_material(i, m)
	if mi.material_override:
		mi.material_override = null


## Trim, interior and underbody bits that came from source models with flat or placeholder colours:
## chrome and alloy reflect, gloss black shines, carbon and carpet go dark, panel-gap seams take a
## shadowed paint colour so they read as gaps rather than drawn black lines. Unknown materials stay as made.
func _style_detail(mi: MeshInstance3D, key: String, paint: Color) -> void:
	for i in mi.mesh.get_surface_count():
		var base := mi.mesh.surface_get_material(i) as BaseMaterial3D
		if base == null:
			continue
		var nm := String(base.resource_name).to_lower()
		var tex := base.albedo_texture
		var id := "detail:%s:%d" % [key, i]
		var m: Material = null
		if nm == "seam":
			var sm := _cached_mat(id)
			sm.albedo_color = paint.darkened(0.8)
			sm.roughness = 0.6
			m = sm
		elif key == "underbody":
			if not nm.contains("chrome"):
				continue
			# its chrome strips sit flush with the bumper skin and z-fight through the paint: tuck them a
			# few millimetres inside so only the parts that stand proud show
			var um := _cached_mat(id)
			um.albedo_color = Color(0.7, 0.71, 0.74)
			um.metallic = 1.0
			um.roughness = 0.15
			um.grow = true
			um.grow_amount = -0.004
			m = um
		elif nm.contains("chrome") or nm.contains("miroir") or nm == "mirror" or nm.contains("metal_alu"):
			var c := base.albedo_color
			if c.get_luminance() < 0.3 or tex == null:
				c = Color(0.82, 0.83, 0.86)   # source "Chrome" materials are often black placeholders
			m = _env_surf(id, c, 1.0, 0.18 if nm.contains("blurry") else 0.06, tex)
		elif nm.contains("satin"):
			m = _env_surf(id, base.albedo_color, 1.0, 0.32, tex)
		elif nm.contains("gloss") and nm.contains("black"):
			m = _env_surf(id, Color(0.02, 0.02, 0.024), 0.0, 0.08)
		elif nm.contains("carbon"):
			m = _env_surf(id, Color(0.05, 0.05, 0.055), 0.2, 0.3, tex if base.albedo_color.get_luminance() < 0.5 else null)
		elif nm.contains("carpet"):
			var cm := _cached_mat(id)
			cm.albedo_color = Color(0.06, 0.06, 0.065)
			cm.roughness = 1.0
			m = cm
		if m and mi.get_surface_override_material(i) != m:
			mi.set_surface_override_material(i, m)


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


func _trim_mat(kind: String, paint: Color) -> Material:
	match kind:
		"chrome":
			return _env_surf("trim:chrome", Color(0.82, 0.83, 0.86), 1.0, 0.06)
		"black":
			return _env_surf("trim:black", Color(0.025, 0.025, 0.03), 0.0, 0.1)
	var id := "trim:body:" + paint.to_html()
	if _mat_cache.has(id):
		return _mat_cache[id]
	var m := _cached_mat(id)
	m.albedo_color = paint
	m.metallic = 0.35
	m.roughness = 0.28
	return m


func _style_wheel(mi: MeshInstance3D, key: String) -> void:
	var worn: float = 1.0 - car.parts.tires / 100.0
	var g := _glow(_hl(key, "tires"), 0.25)
	var rims: String = car.get("rims", "silver")
	for i in mi.mesh.get_surface_count():
		var base: Material = mi.mesh.surface_get_material(i)
		var name := String(base.resource_name) if base else ""
		var cid := "wheel:%s:%d" % [key, i]
		var m: Material
		if name == "rim":
			# polished alloy (or painted black / gunmetal / gold) that reflects the garage
			m = _env_surf(cid, RIM_COLORS.get(rims, RIM_COLORS.silver), 1.0 if rims in ["silver", "gold"] else 0.6,
				0.12 if rims != "black" else 0.35)
		elif name == "rim_dark":
			m = _env_surf(cid, Color(0.06, 0.06, 0.07), 0.5, 0.3)
		elif name == "disc":
			# brake disc: machined steel, rusting as the tyres and brakes wear
			m = _env_surf(cid, Color(0.42, 0.42, 0.43).lerp(Color(0.4, 0.21, 0.1), clamp(worn * 1.4 - 0.4, 0, 1)),
				lerp(0.9, 0.2, worn), 0.35)
		elif name == "rubber":
			var tm: ShaderMaterial = _mat_cache.get(cid)
			if tm == null:
				tm = ShaderMaterial.new()
				tm.shader = TIRE_SHADER
				# the axle is the wheel's thinnest dimension; tread width and radius follow from the bounds
				var ab := mi.mesh.get_aabb()
				var sz := ab.size
				var ax := Vector3.RIGHT if sz.x <= sz.y and sz.x <= sz.z else (Vector3.FORWARD if sz.z <= sz.y else Vector3.UP)
				tm.set_shader_parameter("center", ab.get_center())
				tm.set_shader_parameter("axis", ax.abs())
				tm.set_shader_parameter("half_width", sz.dot(ax.abs()) * 0.5)
				tm.set_shader_parameter("radius", maxf(sz.x, maxf(sz.y, sz.z)) * 0.5)
				_mat_cache[cid] = tm
			tm.set_shader_parameter("wear", worn)
			m = tm
		else:
			# calipers and anything else keep their own look; hover glow on a cached copy
			var sm: StandardMaterial3D = _mat_cache.get(cid)
			if sm == null:
				sm = (base.duplicate() if base is StandardMaterial3D else StandardMaterial3D.new())
				sm.emission_enabled = true
				sm.emission = Color.BLACK
				_mat_cache[cid] = sm
			sm.emission = Color(g.x, g.y, g.z)
			sm.emission_energy_multiplier = 1.0
			m = sm
		if m is ShaderMaterial:
			(m as ShaderMaterial).set_shader_parameter("glow", g)
		if mi.get_surface_override_material(i) != m:
			mi.set_surface_override_material(i, m)
	var flat: bool = car.parts.tires < 25 and key == "wheel_fl"
	mi.scale = Vector3(1, 0.93, 1) if flat else Vector3.ONE


func _process(delta: float) -> void:
	# software GL / weak GPUs: 4x MSAA alone can double the frame time, so drop it if most frames are slow
	if _vp.msaa_3d != Viewport.MSAA_DISABLED and not prewarming:
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


## Back to how a new view starts: spinning from the default angle and distance, nothing selected, hovered or
## held, full quality. The garage keeps one view for the session (main.gd _park_3d_views) and calls this on
## every visit.
func reset_view() -> void:
	yaw = -0.75
	pitch = 0.22
	dist = _base_dist
	_auto_spin = true
	_dragging = false
	_drag_moved = 0.0
	selected = ""
	hovered = ""
	_hover_dirty = false
	_vp.msaa_3d = Viewport.MSAA_4X
	_frames_seen = 0
	_slow_frames = 0
	_place_camera()
	refresh()


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
