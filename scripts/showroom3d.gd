class_name Showroom3D
extends SubViewportContainer
## The real-time showroom: a glass hall with the Newport hillside outside, the display cars on low plinths and
## Rocketbox customers (CharacterBody3D + NavigationAgent3D + AnimationTree) who walk in, browse, wait and leave.
## Fixed camera with three presets: overview, customer and close-up vehicle inspection.
## Game logic stays in main.gd: this node only shows the lobby and reports clicks.
##
## Web build (gl_compatibility): no SDFGI/SSR/SSAO. Light is one soft-shadowed sun through the glass plus
## unshadowed ceiling lights, ACES tone mapping, and reflections from a panorama sky made of the hillside view.

signal customer_clicked(c: Dictionary)
signal car_clicked(car: Dictionary)
signal empty_clicked

const VIEW_TEX := "res://assets/world/view_hills.jpg"
const PEOPLE := {"f": ["p00", "p03", "p07", "p10"], "m": ["p12", "p13", "p15", "p19"]}
const SPOTS := [  # display car positions (x, z) and yaw in degrees, back row first
	[-5.2, -3.6, 24.0], [1.4, -4.3, -8.0], [6.6, -2.9, -34.0], [-7.4, 1.8, 58.0]]
const DOOR := Vector3(9.6, 0, -6.6)
const LOUNGE := [Vector3(5.5, 0, 4.6), Vector3(8.9, 0, 2.5), Vector3(6.3, 0, 3.0)]
const DESK := Vector3(-8.6, 0, -4.4)
const ROOM := Rect2(-11.0, -7.6, 22.4, 14.6)   # x, z, width, depth of the walkable hall

var preset := "wide"
var focus_customer: Dictionary = {}
var focus_car: Dictionary = {}
var cars: Array = []            # [{car, node, card, pos, yaw, aabb}]
var npcs := {}                  # customer id -> Customer3D
var _vp: SubViewport
var _cam: Camera3D
var _cam_pos := Vector3(0.5, 2.7, 9.4)
var _cam_tgt := Vector3(0.3, 1.1, -2.2)
var _cam_goal_pos := _cam_pos
var _cam_goal_tgt := _cam_tgt
var _nav: NavigationRegion3D
var _overlay: Control
var _env: Environment
var _sun: DirectionalLight3D
var _view_mat: StandardMaterial3D
var _pending_nav := true
var _frames_seen := 0
var _slow_frames := 0
var _yaw_off := 0.0
var _quality := 0


func _init() -> void:
	stretch = true
	mouse_filter = Control.MOUSE_FILTER_STOP
	_vp = SubViewport.new()
	_vp.own_world_3d = true
	_vp.msaa_3d = Viewport.MSAA_2X
	_vp.physics_object_picking = false
	add_child(_vp)
	_overlay = Control.new()
	_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(_overlay)
	_build_env()
	_build_room()
	_cam = Camera3D.new()
	_cam.fov = 52
	_vp.add_child(_cam)
	_apply_cam()


# ---------------------------------------------------------------- room

func _build_env() -> void:
	var view: Texture2D = load(VIEW_TEX) if ResourceLoader.exists(VIEW_TEX) else null
	_env = Environment.new()
	_env.background_mode = Environment.BG_COLOR
	_env.background_color = Color(0.05, 0.05, 0.06)
	var sky := Sky.new()
	if view:
		var pm := PanoramaSkyMaterial.new()
		pm.panorama = view
		sky.sky_material = pm
	else:
		sky.sky_material = ProceduralSkyMaterial.new()
	_env.sky = sky
	_env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	_env.ambient_light_color = Color(0.62, 0.6, 0.58)
	_env.ambient_light_energy = 0.55
	_env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	_env.tonemap_mode = Environment.TONE_MAPPER_ACES
	_env.tonemap_exposure = 0.95
	_env.tonemap_white = 6.0
	_env.glow_enabled = false
	var we := WorldEnvironment.new()
	we.environment = _env
	_vp.add_child(we)
	# late-afternoon sun through the glass: the only shadow caster, soft
	_sun = DirectionalLight3D.new()
	_sun.rotation_degrees = Vector3(-34, 150, 0)
	_sun.light_energy = 0.9
	_sun.light_color = Color(1.0, 0.86, 0.7)
	_sun.shadow_enabled = true
	_sun.shadow_blur = 2.2
	_sun.shadow_bias = 0.08
	_sun.shadow_normal_bias = 2.5
	_sun.directional_shadow_mode = DirectionalLight3D.SHADOW_ORTHOGONAL
	_sun.directional_shadow_max_distance = 26.0
	_vp.add_child(_sun)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-60, -30, 0)
	fill.light_energy = 0.35
	fill.light_color = Color(0.85, 0.9, 1.0)
	_vp.add_child(fill)
	# warm downlights over the display floor (no shadows: cheap on the web)
	for p in [Vector3(-3.5, 4.2, -2.5), Vector3(4.0, 4.2, -2.5)]:
		var l := OmniLight3D.new()
		l.position = p
		l.omni_range = 10.0
		l.light_energy = 0.7
		l.light_color = Color(1.0, 0.88, 0.72)
		_vp.add_child(l)
	# Forward+ / Godot 4.4+ Compatibility use this; the 4.3 web build falls back to the panorama sky reflections
	var probe := ReflectionProbe.new()
	probe.size = Vector3(22, 5, 15)
	probe.position = Vector3(0, 2.5, -0.5)
	probe.box_projection = true
	probe.update_mode = ReflectionProbe.UPDATE_ONCE
	probe.interior = true
	_vp.add_child(probe)


func _mat(col: Color, rough := 0.6, metal := 0.0) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = col
	m.roughness = rough
	m.metallic = metal
	return m


func _box(size: Vector3, pos: Vector3, m: Material, rot_y := 0.0, shadow := true) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	mi.material_override = m
	mi.position = pos
	mi.rotation.y = deg_to_rad(rot_y)
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if shadow else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_vp.add_child(mi)
	return mi


func _floor_material() -> ShaderMaterial:
	var sh := Shader.new()
	sh.code = """
shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;
varying vec3 wp;
float h(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float n(vec2 p) { vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);
	return mix(mix(h(i), h(i + vec2(1, 0)), f.x), mix(h(i + vec2(0, 1)), h(i + vec2(1, 1)), f.x), f.y); }
void vertex() { wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz; }
void fragment() {
	vec2 p = wp.xz;
	vec2 tile = floor(p / 1.2);
	vec2 g = abs(fract(p / 1.2) - 0.5);
	float joint = smoothstep(0.488, 0.497, max(g.x, g.y));
	float v = n(p * 1.7 + tile * 3.1) * 0.6 + n(p * 5.0) * 0.3;
	float vein = 0.0;
	vec3 base = mix(vec3(0.52, 0.5, 0.47), vec3(0.6, 0.58, 0.55), v) * (1.0 - 0.06 * h(tile));
	base = mix(base, vec3(0.3, 0.29, 0.28), vein);
	ALBEDO = mix(base, vec3(0.2, 0.19, 0.18), joint);
	ROUGHNESS = mix(0.16, 0.5, joint) + v * 0.06;
	SPECULAR = 0.6;
}
"""
	var m := ShaderMaterial.new()
	m.shader = sh
	return m


func _build_room() -> void:
	var dark := _mat(Color(0.07, 0.07, 0.075), 0.55)
	var stone := _mat(Color(0.13, 0.125, 0.12), 0.7)
	var frame := _mat(Color(0.04, 0.04, 0.045), 0.35, 0.6)
	var wood := _mat(Color(0.23, 0.15, 0.09), 0.45)
	# floor
	var fl := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(24, 17)
	fl.mesh = pm
	fl.position = Vector3(0, 0, -0.5)
	fl.material_override = _floor_material()
	fl.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_vp.add_child(fl)
	# ceiling: dark slats with a warm wood soffit and recessed light discs
	_box(Vector3(24, 0.2, 17), Vector3(0, 4.8, -0.5), dark, 0, false)
	_box(Vector3(18, 0.06, 0.9), Vector3(1.5, 4.66, -6.6), wood, 0, false)
	var glow := StandardMaterial3D.new()
	glow.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	glow.albedo_color = Color(1.0, 0.92, 0.78)
	for x in range(-9, 10, 3):
		for z in [-5.0, -1.5, 2.0, 5.0]:
			var d := MeshInstance3D.new()
			var cm := CylinderMesh.new()
			cm.top_radius = 0.11
			cm.bottom_radius = 0.11
			cm.height = 0.02
			cm.radial_segments = 12
			d.mesh = cm
			d.material_override = glow
			d.position = Vector3(x, 4.69, z)
			d.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			_vp.add_child(d)
	# back-left: dark stone feature wall with the dealer sign
	_box(Vector3(7.0, 4.8, 0.4), Vector3(-7.7, 2.4, -7.9), stone)
	_box(Vector3(0.4, 4.8, 15.6), Vector3(-11.4, 2.4, -0.4), stone)
	var sign := Label3D.new()
	sign.text = "OC\nCHIEF AUTO"
	sign.font = UI.head_font()
	sign.font_size = 96
	sign.pixel_size = 0.006
	sign.modulate = Color(0.95, 0.93, 0.9)
	sign.outline_size = 0
	sign.position = Vector3(-7.7, 2.9, -7.68)
	sign.shaded = false
	sign.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_vp.add_child(sign)
	var sub := Label3D.new()
	sub.text = "NEWPORT BEACH"
	sub.font_size = 36
	sub.pixel_size = 0.005
	sub.modulate = Color(0.85, 0.2, 0.18)
	sub.outline_size = 0
	sub.position = Vector3(-7.7, 1.85, -7.68)
	sub.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_vp.add_child(sub)
	# glass: the back wall right of the sign and the whole right wall, with slim black mullions
	var glass := StandardMaterial3D.new()
	glass.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	glass.albedo_color = Color(0.75, 0.85, 0.9, 0.07)
	glass.roughness = 0.02
	glass.metallic_specular = 1.0
	glass.cull_mode = BaseMaterial3D.CULL_DISABLED
	var gb := _box(Vector3(15.8, 4.6, 0.04), Vector3(3.8, 2.3, -7.9), glass, 0, false)
	gb.sorting_offset = -1.0
	_box(Vector3(0.04, 4.6, 15.6), Vector3(11.7, 2.3, -0.4), glass, 0, false)
	for x in range(-4, 12, 3):
		_box(Vector3(0.12, 4.8, 0.14), Vector3(x, 2.4, -7.9), frame, 0, false)
	for z in range(-7, 8, 3):
		_box(Vector3(0.14, 4.8, 0.12), Vector3(11.7, 2.4, z), frame, 0, false)
	_box(Vector3(15.8, 0.12, 0.14), Vector3(3.8, 0.06, -7.9), frame)
	_box(Vector3(0.14, 0.12, 15.6), Vector3(11.7, 0.06, -0.4), frame)
	# outside: the hillside photo on two big cards beyond the glass, with a paved apron and a kerb in front
	var view: Texture2D = load(VIEW_TEX) if ResourceLoader.exists(VIEW_TEX) else null
	_view_mat = StandardMaterial3D.new()
	_view_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_view_mat.albedo_texture = view
	_view_mat.albedo_color = Color(1, 1, 1)
	for spec in [[Vector3(-2, 7.6, -40), 0.0, Vector2(74, 29.6)], [Vector3(44, 7.6, 0), -90.0, Vector2(74, 29.6)]]:
		var q := MeshInstance3D.new()
		var qm := QuadMesh.new()
		qm.size = spec[2]
		q.mesh = qm
		q.material_override = _view_mat
		q.position = spec[0]
		q.rotation.y = deg_to_rad(spec[1])
		q.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		_vp.add_child(q)
	var paving := _mat(Color(0.32, 0.31, 0.3), 0.85)
	_box(Vector3(60, 0.1, 30), Vector3(0, -0.12, -23.5), paving, 0, false)
	_box(Vector3(30, 0.1, 60), Vector3(27.5, -0.12, 0), paving, 0, false)
	# outdoor palms just past the glass: trunks and frond fans
	var trunk := _mat(Color(0.42, 0.34, 0.25), 0.9)
	var frond := _mat(Color(0.18, 0.3, 0.12), 0.8)
	for p in [Vector3(-1.5, 0, -12.0), Vector3(7.0, 0, -14.5), Vector3(15.0, 0, -6.0), Vector3(16.5, 0, 6.0)]:
		var t := MeshInstance3D.new()
		var cm := CylinderMesh.new()
		cm.top_radius = 0.16
		cm.bottom_radius = 0.26
		cm.height = 9.0
		cm.radial_segments = 8
		t.mesh = cm
		t.material_override = trunk
		t.position = p + Vector3(0, 4.5, 0)
		_vp.add_child(t)
		for k in 9:
			var leaf := MeshInstance3D.new()
			var lm := BoxMesh.new()
			lm.size = Vector3(0.5, 0.04, 3.0)
			leaf.mesh = lm
			leaf.material_override = frond
			leaf.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			leaf.position = p + Vector3(0, 9.0, 0)
			leaf.rotation = Vector3(deg_to_rad(28 + (k % 3) * 9), TAU * k / 9.0, 0)
			leaf.translate_object_local(Vector3(0, 0, 1.4))
			_vp.add_child(leaf)
	# reception counter at the feature wall, a lounge corner front right, planters
	_box(Vector3(3.6, 1.05, 0.9), Vector3(-8.4, 0.525, -5.6), wood)
	_box(Vector3(3.8, 0.06, 1.0), Vector3(-8.4, 1.08, -5.6), _mat(Color(0.9, 0.88, 0.84), 0.2))
	var leather := _mat(Color(0.13, 0.1, 0.08), 0.5)
	for s in [[Vector3(7.4, 0.24, 5.9), 0.0, 3.4], [Vector3(9.9, 0.24, 3.9), 90.0, 2.6]]:
		_box(Vector3(s[2], 0.48, 0.95), s[0], leather, s[1])
		var back: Vector3 = s[0] + (Vector3(0, 0.3, 0.42) if s[1] == 0.0 else Vector3(0.42, 0.3, 0))
		_box(Vector3(s[2], 0.62, 0.22), back, leather, s[1])
	_box(Vector3(1.6, 0.36, 0.9), Vector3(7.3, 0.18, 4.2), _mat(Color(0.03, 0.03, 0.035), 0.08, 0.3))
	var pot := _mat(Color(0.86, 0.85, 0.82), 0.5)
	var leaf_m := _mat(Color(0.16, 0.32, 0.12), 0.75)
	for p in [Vector3(-10.4, 0, -6.9), Vector3(-1.0, 0, -7.2), Vector3(10.8, 0, -7.0), Vector3(10.8, 0, 6.2), Vector3(-10.4, 0, 5.5)]:
		_box(Vector3(0.7, 0.8, 0.7), p + Vector3(0, 0.4, 0), pot)
		for k in 5:
			var s := MeshInstance3D.new()
			var sm := SphereMesh.new()
			sm.radius = 0.45 - k * 0.04
			sm.height = sm.radius * 2.0
			sm.radial_segments = 10
			sm.rings = 6
			s.mesh = sm
			s.material_override = leaf_m
			s.position = p + Vector3(sin(k * 2.3) * 0.25, 1.15 + k * 0.32, cos(k * 2.3) * 0.25)
			_vp.add_child(s)
	_nav = NavigationRegion3D.new()
	_vp.add_child(_nav)


## Day/night: the view card and light follow Game.night_amount().
func set_time(night: float, sunset: float) -> void:
	_view_mat.albedo_color = Color(1, 1, 1).lerp(Color(0.12, 0.14, 0.24), night).lerp(Color(1.0, 0.82, 0.66), sunset * 0.5)
	_sun.light_energy = lerp(0.9, 0.0, night)
	_sun.light_color = Color(1.0, 0.86, 0.7).lerp(Color(1.0, 0.68, 0.42), sunset)
	_env.ambient_light_energy = lerp(0.55, 0.42, night)


# ---------------------------------------------------------------- display cars

func set_cars(shown: Array) -> void:
	for d in cars:
		d.node.queue_free()
		d.card.queue_free()
		d.plinth.queue_free()
	cars.clear()
	var plinth_m := _mat(Color(0.32, 0.32, 0.34), 0.28, 0.35)
	for i in min(shown.size(), SPOTS.size()):
		var car: Dictionary = shown[i]
		var sp: Array = SPOTS[i]
		var pos := Vector3(sp[0], 0.06, sp[1])
		var holder := Node3D.new()
		holder.position = pos
		holder.rotation.y = deg_to_rad(sp[2])
		_vp.add_child(holder)
		var model := Car3DView.build_model(car)
		var aabb := AABB(Vector3(-2.3, 0, -1), Vector3(4.6, 1.4, 2))
		if model:
			holder.add_child(model)
			aabb = _model_aabb(model)
		var plinth := MeshInstance3D.new()
		var cm := CylinderMesh.new()
		cm.top_radius = max(aabb.size.x, aabb.size.z) * 0.5
		cm.bottom_radius = cm.top_radius + 0.05
		cm.height = 0.06
		cm.radial_segments = 40
		plinth.mesh = cm
		plinth.material_override = plinth_m
		plinth.position = Vector3(pos.x, 0.03, pos.z)
		_vp.add_child(plinth)
		var card := _price_card(car)
		_overlay.add_child(card)
		cars.append({"car": car, "node": holder, "plinth": plinth, "card": card, "pos": pos, "yaw": deg_to_rad(sp[2]), "aabb": aabb})
	_pending_nav = true


func _model_aabb(n: Node) -> AABB:
	var out := AABB()
	var first := true
	var stack: Array = [n]
	while not stack.is_empty():
		var x: Node = stack.pop_back()
		if x is MeshInstance3D:
			var a: AABB = (x as MeshInstance3D).get_aabb()
			var t: Transform3D = Transform3D.IDENTITY
			var p: Node = x
			while p != n and p is Node3D:
				t = (p as Node3D).transform * t
				p = p.get_parent()
			a = t * a
			out = a if first else out.merge(a)
			first = false
		stack.append_array(x.get_children())
	return out


## The dark glass price card that floats over each display car (year, model, sticker).
func _price_card(car: Dictionary) -> PanelContainer:
	var p := PanelContainer.new()
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var sb := UI.box(Color(0.03, 0.035, 0.045, 0.86), Color(1, 1, 1, 0.16), 6, 1, 0)
	sb.content_margin_left = 14
	sb.content_margin_right = 14
	sb.content_margin_top = 5
	sb.content_margin_bottom = 6
	p.add_theme_stylebox_override("panel", sb)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", -2)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	p.add_child(v)
	var t := UI.label("%d %s" % [car.year, car.model], 13, Color(0.9, 0.9, 0.92))
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(t)
	var pr := UI.label(Game.money_str(car.get("sticker", 0)), 20, Color.WHITE, true)
	pr.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(pr)
	return p


func _bake_nav() -> void:
	_pending_nav = false
	var nm := NavigationMesh.new()
	nm.agent_radius = 0.5
	nm.agent_height = 1.75
	nm.agent_max_climb = 0.25
	nm.cell_size = 0.25
	nm.cell_height = 0.25
	nm.geometry_parsed_geometry_type = NavigationMesh.PARSED_GEOMETRY_MESH_INSTANCES
	var src := NavigationMeshSourceGeometryData3D.new()
	var fv := PackedVector3Array()
	var r := ROOM
	# baked surfaces come out half a voxel up: sink the source floor so paths run at y = 0
	var a := Vector3(r.position.x, -0.45, r.position.y)
	var b := Vector3(r.end.x, -0.45, r.position.y)
	var c := Vector3(r.end.x, -0.45, r.end.y)
	var d := Vector3(r.position.x, -0.45, r.end.y)
	fv.append_array([a, b, c, a, c, d])
	src.add_faces(fv, Transform3D.IDENTITY)
	# cars, plinths and furniture are 1 m tall blocks the agents walk around
	var blocks: Array = []
	for cd in cars:
		var ab: AABB = cd.aabb
		blocks.append([Transform3D(Basis(Vector3.UP, cd.yaw), cd.pos + Vector3(ab.get_center().x, 0.5, ab.get_center().z).rotated(Vector3.UP, cd.yaw) * Vector3(1, 0, 1) + Vector3(0, 1.25, 0)), Vector3(ab.size.x + 0.2, 2.5, ab.size.z + 0.2)])
	for f in [[Vector3(-8.4, 1.25, -5.6), Vector3(3.8, 2.5, 1.0)], [Vector3(7.4, 1.25, 5.9), Vector3(3.4, 2.5, 1.0)],
			[Vector3(9.9, 1.25, 3.9), Vector3(1.0, 2.5, 2.6)], [Vector3(7.3, 1.25, 4.2), Vector3(1.6, 2.5, 0.9)]]:
		blocks.append([Transform3D(Basis(), f[0]), f[1]])
	for blk in blocks:
		# raw triangles (no BoxMesh: reading a mesh back from the GPU stalls the frame)
		var h: Vector3 = blk[1] / 2.0
		var q := PackedVector3Array()
		for k in 8:
			q.append(Vector3(h.x if k & 1 else -h.x, h.y if k & 2 else -h.y, h.z if k & 4 else -h.z))
		var tris := PackedVector3Array()
		for f in [[0, 1, 5, 4], [2, 6, 7, 3], [0, 4, 6, 2], [1, 3, 7, 5], [0, 2, 3, 1], [4, 5, 7, 6]]:
			tris.append_array([q[f[0]], q[f[1]], q[f[2]], q[f[0]], q[f[2]], q[f[3]]])
		src.add_faces(tris, blk[0])
	NavigationServer3D.bake_from_source_geometry_data(nm, src)
	_nav.navigation_mesh = nm


# ---------------------------------------------------------------- customers

## Brings the 3D crowd in line with the lobby list: new arrivals walk in, people who left walk out.
func sync(lobby: Array, states: Dictionary) -> void:
	var keep := {}
	for c in lobby:
		var id: int = c.id
		keep[id] = true
		var npc: Customer3D = npcs.get(id)
		if npc == null:
			npc = Customer3D.new()
			npc.cust = c
			npc.model_pid = _model_for(c)
			_vp.add_child(npc)
			# people already inside when the screen opens are placed straight on their spot
			var fresh: bool = Game.clock - float(c.get("arrived", 0.0)) < 6.0
			npc.position = DOOR if fresh else _spot_for(c, states.get(id, "browsing"))
			npc.marker = _marker()
			_overlay.add_child(npc.marker)
			npcs[id] = npc
		npc.cust = c
		npc.set_state(states.get(id, "browsing"), _spot_for(c, states.get(id, "browsing")), _look_for(c))
	for id in npcs.keys():
		if not keep.has(id):
			var gone: Customer3D = npcs[id]
			npcs.erase(id)
			gone.leave(DOOR)
			if gone.marker:
				gone.marker.queue_free()
				gone.marker = null


func _model_for(c: Dictionary) -> String:
	var pid: String = str(c.get("pid", "p00"))
	var n := int(pid.substr(1)) if pid.begins_with("p") and pid.substr(1).is_valid_int() else int(c.get("look_seed", 0))
	var pool: Array = PEOPLE.f if n < 12 else PEOPLE.m
	return pool[abs(int(c.get("look_seed", n))) % pool.size()]


func _car_index(c: Dictionary) -> int:
	var want: int = c.get("car_id", -1)
	for i in cars.size():
		if cars[i].car.id == want:
			return i
	for i in cars.size():
		if cars[i].car.cls == c.get("wants_cls", ""):
			return i
	return int(c.id) % max(1, cars.size()) if not cars.is_empty() else -1


## Where a customer stands for their state: beside their car (browsing, waiting), at the lounge
## (negotiating, closing), out the door (test drive).
func _spot_for(c: Dictionary, state: String) -> Vector3:
	var id: int = c.id
	match state:
		"test":
			return DOOR + Vector3(2.5, 0, -1.0)
		"negotiating", "closing":
			return LOUNGE[id % LOUNGE.size()]
	var i := _car_index(c)
	if i < 0:
		return Vector3(-2 + (id % 5) * 1.3, 0, 3.0)
	var cd: Dictionary = cars[i]
	var side := -1.0 if id % 2 == 0 else 1.0
	var ab: AABB = cd.aabb
	# stand beside the car on the side that faces the camera, so nobody hides behind it
	var c0 := ab.get_center()
	var gap := 0.8 + (id % 3) * 0.2
	var cands := [Vector3(c0.x + side * ab.size.x * 0.2, 0, ab.end.z + gap), Vector3(c0.x + side * ab.size.x * 0.2, 0, ab.position.z - gap),
		Vector3(ab.end.x + gap, 0, c0.z + side * ab.size.z * 0.2), Vector3(ab.position.x - gap, 0, c0.z + side * ab.size.z * 0.2)]
	var out: Vector3 = Vector3.ZERO
	var best := -1e9
	for local in cands:
		var w: Vector3 = cd.pos * Vector3(1, 0, 1) + (local as Vector3).rotated(Vector3.UP, cd.yaw)
		var score: float = w.z - absf(w.x) * 0.15
		if ROOM.has_point(Vector2(w.x, w.z)) and score > best:
			best = score
			out = w
	return out


func _look_for(c: Dictionary) -> Vector3:
	var i := _car_index(c)
	return cars[i].pos if i >= 0 else Vector3(0, 0, -4)


func _marker() -> Label:
	var l := Label.new()
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	l.add_theme_font_size_override("font_size", 13)
	l.add_theme_font_override("font", UI.head_font())
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var sb := UI.box(Color(0.03, 0.035, 0.045, 0.82), UI.GOLD, 10, 1, 0)
	sb.content_margin_left = 8
	sb.content_margin_right = 8
	sb.content_margin_top = 1
	sb.content_margin_bottom = 2
	l.add_theme_stylebox_override("normal", sb)
	return l


# ---------------------------------------------------------------- camera

func set_preset(p: String, target = null) -> void:
	preset = p
	match p:
		"wide":
			focus_car = {}
			_cam_goal_pos = Vector3(0.5, 2.7, 9.4)
			_cam_goal_tgt = Vector3(0.3, 1.1, -2.2)
		"customer":
			if target is Dictionary and not target.is_empty():
				focus_customer = target
			if focus_customer.is_empty() and not npcs.is_empty():
				focus_customer = npcs.values()[0].cust
			var npc: Customer3D = npcs.get(focus_customer.get("id", -999))
			var at: Vector3 = npc.position if npc else Vector3(0, 0, 0)
			_cam_goal_tgt = at + Vector3(0, 1.2, 0)
			# from in front of them, looking past them at the car they're on
			var away: Vector3 = at - (npc.look_at_pt if npc else Vector3(0, 0, -4))
			away.y = 0
			if away.length() < 0.1:
				away = Vector3(0, 0, 1)
			# three-quarter view: their face and the car they're looking at, from the open-floor side
			var a1: Vector3 = away.normalized().rotated(Vector3.UP, 1.15)
			var a2: Vector3 = away.normalized().rotated(Vector3.UP, -1.15)
			away = a1 if a1.z > a2.z else a2
			_cam_goal_pos = at + away * 3.6 + Vector3(0, 1.55, 0)
			_cam_goal_tgt = _cam_goal_tgt.lerp(npc.look_at_pt + Vector3(0, 0.8, 0) if npc else _cam_goal_tgt, 0.25)
		"inspect":
			if target is Dictionary and not target.is_empty():
				focus_car = target
			var cd: Dictionary = {}
			for d in cars:
				if focus_car.is_empty() or d.car.id == focus_car.get("id", -1):
					cd = d
					break
			if cd.is_empty():
				return
			focus_car = cd.car
			var ab: AABB = cd.aabb
			var centre: Vector3 = cd.pos + ab.get_center().rotated(Vector3.UP, cd.yaw) * Vector3(1, 0, 1) + Vector3(0, 0.6, 0)
			# front three-quarter view of the car
			var dir := Vector3(0.55, 0, 1).rotated(Vector3.UP, cd.yaw + _yaw_off).normalized()
			_cam_goal_tgt = centre
			_cam_goal_pos = centre + dir * max(5.4, ab.size.x * 1.2) + Vector3(0, 1.7, 0)


func _apply_cam() -> void:
	_cam.position = _cam_pos
	if _cam_pos.distance_to(_cam_tgt) > 0.01:
		_cam.basis = Basis.looking_at(_cam_tgt - _cam_pos, Vector3.UP)


func _process(delta: float) -> void:
	if _pending_nav and is_inside_tree():
		_bake_nav()
	if preset == "customer" and not focus_customer.is_empty():
		set_preset("customer")   # follow them as they walk
	var k: float = 1.0 - exp(-delta * 3.2)
	_cam_pos = _cam_pos.lerp(_cam_goal_pos, k)
	_cam_tgt = _cam_tgt.lerp(_cam_goal_tgt, k)
	_apply_cam()
	# software GL / weak GPUs: step quality down while most frames are slow
	# (1: no MSAA, 2: half-resolution 3D, 3: no sun shadows)
	if _quality < 3:
		_frames_seen += 1
		if delta > 0.06:
			_slow_frames += 1
		if _frames_seen >= 20:
			if _slow_frames >= 14:
				_quality += 1
				match _quality:
					1: _vp.msaa_3d = Viewport.MSAA_DISABLED
					2: stretch_shrink = 2
					3: _sun.shadow_enabled = false
			_frames_seen = 0
			_slow_frames = 0
	_place_overlays()


func _to_screen(p: Vector3) -> Vector2:
	var s: Vector2 = _cam.unproject_position(p)
	return s * size / Vector2(_vp.size) if _vp.size.x > 0 else s


func _visible(p: Vector3) -> bool:
	return not _cam.is_position_behind(p)


func _place_overlays() -> void:
	for d in cars:
		var card: Control = d.card
		var ab: AABB = d.aabb
		var top: Vector3 = d.pos + ab.get_center().rotated(Vector3.UP, d.yaw) * Vector3(1, 0, 1) + Vector3(0, ab.size.y + 0.75, 0)
		card.visible = _visible(top) and preset != "customer"
		if card.visible:
			card.reset_size()
			card.position = _to_screen(top) - Vector2(card.size.x / 2.0, card.size.y)
	for id in npcs:
		var npc: Customer3D = npcs[id]
		if npc.marker == null:
			continue
		var head := npc.position + Vector3(0, 2.05, 0)
		npc.marker.visible = npc.visible and _visible(head) and npc.marker.text != ""
		if npc.marker.visible:
			npc.marker.reset_size()
			npc.marker.position = _to_screen(head) - Vector2(npc.marker.size.x / 2.0, npc.marker.size.y)


## Marker text and colour over a customer's head.
func set_marker(id: int, text: String, col: Color) -> void:
	var npc: Customer3D = npcs.get(id)
	if npc == null or npc.marker == null:
		return
	npc.marker.text = text
	npc.marker.add_theme_color_override("font_color", col)
	var sb: StyleBoxFlat = npc.marker.get_theme_stylebox("normal")
	sb.border_color = col


# ---------------------------------------------------------------- input

func _gui_input(ev: InputEvent) -> void:
	if ev is InputEventMouseButton and ev.pressed and ev.button_index == MOUSE_BUTTON_LEFT:
		var hit = _pick(ev.position)
		if hit is Customer3D:
			focus_customer = hit.cust
			customer_clicked.emit(hit.cust)
		elif hit is Dictionary:
			car_clicked.emit(hit)
		else:
			empty_clicked.emit()
		accept_event()
	elif ev is InputEventMouseButton and ev.pressed and preset == "inspect" and ev.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]:
		_yaw_off += 0.25 if ev.button_index == MOUSE_BUTTON_WHEEL_UP else -0.25
		set_preset("inspect")
		accept_event()


## The customer (screen-space box from feet to head) or display car (projected bounding box) under a point.
func _pick(pos: Vector2):
	var best = null
	var best_d := 1e9
	for id in npcs:
		var npc: Customer3D = npcs[id]
		if not npc.visible or not _visible(npc.position):
			continue
		var feet := _to_screen(npc.position)
		var head := _to_screen(npc.position + Vector3(0, 1.85, 0))
		var h: float = feet.y - head.y
		var r := Rect2(head.x - h * 0.2, head.y - 30, h * 0.4, h + 30)
		var dist := _cam.global_position.distance_to(npc.position)
		if r.has_point(pos) and dist < best_d:
			best = npc
			best_d = dist
	if best != null:
		return best
	for d in cars:
		var ab: AABB = d.aabb
		var rect := Rect2()
		var first := true
		for k in 8:
			var corner: Vector3 = d.pos + ab.get_endpoint(k).rotated(Vector3.UP, d.yaw)
			if not _visible(corner):
				continue
			var s := _to_screen(corner)
			rect = Rect2(s, Vector2.ZERO) if first else rect.expand(s)
			first = false
		rect = rect.grow(-rect.size.x * 0.12)
		var dist := _cam.global_position.distance_to(d.pos)
		if not first and rect.has_point(pos) and dist < best_d:
			best = d.car
			best_d = dist
	return best


# =====================================================================

## One customer on the floor. Movement: NavigationAgent3D paths over the baked floor, CharacterBody3D moves.
## Animation: an AnimationTree state machine over the GLB's idle / walk / browse clips.
class Customer3D extends CharacterBody3D:
	var cust: Dictionary = {}
	var model_pid := "p13"
	var marker: Label
	var state := ""
	var goal := Vector3.ZERO
	var home := Vector3.ZERO
	var look_at_pt := Vector3.ZERO
	var leaving := false
	var agent: NavigationAgent3D
	var tree: AnimationTree
	var playback: AnimationNodeStateMachinePlayback
	var _anim := ""
	var _wander_t := 0.0
	const SPEED := 1.25

	func _ready() -> void:
		motion_mode = CharacterBody3D.MOTION_MODE_FLOATING
		collision_layer = 2
		collision_mask = 0
		var shape := CollisionShape3D.new()
		var cap := CapsuleShape3D.new()
		cap.radius = 0.3
		cap.height = 1.75
		shape.shape = cap
		shape.position.y = 0.9
		add_child(shape)
		agent = NavigationAgent3D.new()
		agent.radius = 0.5
		agent.path_desired_distance = 0.4
		agent.target_desired_distance = 0.25
		agent.avoidance_enabled = false
		add_child(agent)
		var path := "res://assets/people3d/%s.glb" % model_pid
		if ResourceLoader.exists(path):
			var m: Node3D = (load(path) as PackedScene).instantiate()
			add_child(m)
			var ap: AnimationPlayer = m.find_child("AnimationPlayer", true, false)
			if ap:
				for n in ap.get_animation_list():
					ap.get_animation(n).loop_mode = Animation.LOOP_LINEAR
				tree = AnimationTree.new()
				var sm := AnimationNodeStateMachine.new()
				for n in ["idle", "walk", "browse"]:
					var a := AnimationNodeAnimation.new()
					a.animation = n
					sm.add_node(n, a)
				for x in ["idle", "walk", "browse"]:
					for y in ["idle", "walk", "browse"]:
						if x != y:
							var tr := AnimationNodeStateMachineTransition.new()
							tr.xfade_time = 0.3
							sm.add_transition(x, y, tr)
				var st := AnimationNodeStateMachineTransition.new()
				sm.add_transition("Start", "idle", st)
				tree.tree_root = sm
				m.add_child(tree)
				tree.anim_player = tree.get_path_to(ap)
				tree.active = true
				playback = tree.get("parameters/playback")
		# a soft contact shadow so they sit on the marble
		var blob := MeshInstance3D.new()
		var qm := QuadMesh.new()
		qm.size = Vector2(0.9, 0.9)
		qm.orientation = PlaneMesh.FACE_Y
		blob.mesh = qm
		blob.position.y = 0.012
		var bm := ShaderMaterial.new()
		var sh := Shader.new()
		sh.code = "shader_type spatial;\nrender_mode unshaded, blend_mix, depth_draw_never, cull_disabled;\nvoid fragment() { float d = length(UV - 0.5) * 2.0; ALBEDO = vec3(0.0); ALPHA = 0.45 * (1.0 - smoothstep(0.2, 1.0, d)); }"
		bm.shader = sh
		blob.material_override = bm
		blob.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(blob)
		_wander_t = randf_range(6.0, 14.0)
		if goal != Vector3.ZERO:
			agent.target_position = goal

	func set_state(s: String, spot: Vector3, look: Vector3) -> void:
		look_at_pt = look
		if s == state and goal.distance_to(spot) < 0.1:
			return
		state = s
		goal = spot
		home = spot
		if agent:
			agent.target_position = spot

	func leave(door: Vector3) -> void:
		leaving = true
		state = "leaving"
		goal = door
		if agent:
			agent.target_position = door

	func _play(n: String) -> void:
		if playback and n != _anim:
			_anim = n
			playback.travel(n)

	func _physics_process(delta: float) -> void:
		if agent == null:
			return
		var far: bool = position.distance_to(goal) > 0.3
		if far:
			var nxt := agent.get_next_path_position()
			if agent.is_navigation_finished() or nxt.distance_to(position) < 0.05:
				nxt = goal   # map not ready yet or no path: walk straight
			if Vector2(nxt.x - position.x, nxt.z - position.z).length() < 0.05:
				nxt = goal
			var dir := nxt - position
			dir.y = 0
			if dir.length() > 0.01:
				dir = dir.normalized()
				velocity = dir * SPEED
				move_and_slide()
				position.y = 0
				rotation.y = lerp_angle(rotation.y, atan2(dir.x, dir.z), min(1.0, delta * 8.0))
			_play("walk")
		else:
			velocity = Vector3.ZERO
			if leaving:
				queue_free()
				return
			# face the car (or the room) and settle into the state's pose
			var to := look_at_pt - position
			if state in ["negotiating", "closing"]:
				to = Vector3(-0.5, 0, 1)   # turned to the salesperson's desk side, open to the room
			if to.length() > 0.1:
				rotation.y = lerp_angle(rotation.y, atan2(to.x, to.z), min(1.0, delta * 4.0))
			_play("browse" if state == "browsing" else "idle")
			# browsing customers drift a little along the car now and then
			if state == "browsing":
				_wander_t -= delta
				if _wander_t <= 0.0:
					_wander_t = randf_range(8.0, 16.0)
					var side := Vector3(randf_range(-1.2, 1.2), 0, randf_range(-0.4, 0.4))
					goal = home + side
					agent.target_position = goal
		visible = not (state == "test" and not far)
