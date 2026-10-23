class_name Showroom3D
extends SubViewportContainer
## The real-time showroom: a glass hall with the Newport hillside outside, the display cars on low plinths and
## Rocketbox customers (CharacterBody3D + NavigationAgent3D + AnimationTree) who walk in, browse, wait and leave.
## Fixed camera with three presets: overview, customer and close-up vehicle inspection.
## Game logic stays in main.gd: this node only shows the lobby and reports clicks.
##
## Web build (gl_compatibility): no SDFGI/SSR/SSAO and no sky radiance. Light is one sun through the glass plus
## unshadowed ceiling lights, ACES tone mapping, and hand-rolled reflections (shaders/env_*.gdshader) from an
## equirect of the hall with the beach photo in the glass. Desktop (Forward+) lights and reflects from the HDRI.
##
## Art is CC0 from Poly Haven (assets/cc0, see CREDITS.md): Spiaggia di Mondello HDRI for the view through the
## glass, Large Floor Tiles 02 stone, walnut veneer, stucco and concrete tile walls, and scanned furniture/plants.

signal customer_clicked(c: Dictionary)
signal car_clicked(car: Dictionary)
signal empty_clicked

const VIEW_TEX := "res://assets/cc0/sky/showroom_view.jpg"     # beach photo, azimuth -70..+130 deg, elevation -15..+35
const SKY_HDR := "res://assets/cc0/sky/beach_1k.hdr"            # same place as the view: desktop sky light + reflections
const ENV_TEX := "res://assets/cc0/sky/showroom_env.jpg"        # equirect of the hall + view, for web reflections
const TEX := "res://assets/cc0/textures/%s_%s.jpg"             # Poly Haven maps: <name>_Diffuse / _nor_gl / _Rough
const PROPS := "res://assets/cc0/models/%s/%s.gltf"
const BAKE_INDEX := "res://assets/bake/hall_index.json"         # UV2 meshes of the hall baked in Cycles
const BAKE_LIGHTMAP := "res://assets/bake/hall_lightmap.jpg"   # their lighting (0.5 = neutral)
const BAKE_K := 0.7     # how much of the floor lightmap to use
const BAKE_WALL := 1.7  # walls and ceiling: albedo gain under the lightmap multiply
const SURFACE_SHADER := preload("res://shaders/env_surface.gdshader")
const GLASS_SHADER := preload("res://shaders/env_glass.gdshader")
const FLOOR_SHADER := preload("res://shaders/env_floor.gdshader")
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
var avoid: Array = []           # Controls over the hall (the activity panel): price cards keep clear of them
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
var _rays_mat: ShaderMaterial
var _view_mat: StandardMaterial3D
var _pending_nav := true
var _frames_seen := 0
var _slow_frames := 0
var _yaw_off := 0.0
var _quality := 0
var prewarming := false   # rendered behind the title: those frames say nothing about the hall's own cost


## Everything _build_room loads from disk: the title prefetches it on worker threads (main._prefetch) and the
## prewarm waits for it, so building the hall is just node work (it was a ~270 ms frame on the title).
static func room_resources() -> Array:
	var out := []
	for t in ["large_floor_tiles_02", "marble_01", "smoked_walnut_veneer", "white_stucco"]:
		for k in ["Diffuse", "Rough", "nor_gl"]:
			out.append(TEX % [t, k])
	for p in ["bar_chair_round_01", "calathea_orbifolia_01", "modern_arm_chair_01", "modern_ceiling_lamp_01",
			"modern_coffee_table_01", "pachira_aquatica_01", "sofa_02"]:
		out.append(PROPS % [p, p])
	for f in ["showroom_floor_albedo.png", "showroom_floor_normal.png", "showroom_floor_rough.png"]:
		out.append("res://assets/world/" + f)
	out.append_array([VIEW_TEX, SKY_HDR, ENV_TEX, BAKE_LIGHTMAP])
	return out


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
	_apply_bake()
	_cam = Camera3D.new()
	_cam.fov = 52
	_vp.add_child(_cam)
	_apply_cam()


# ---------------------------------------------------------------- room

func _build_env() -> void:
	_env = Environment.new()
	_env.background_mode = Environment.BG_COLOR
	_env.background_color = Color(0.05, 0.05, 0.06)
	_env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	_env.ambient_light_color = Color(0.72, 0.64, 0.54)
	_env.ambient_light_energy = 0.6
	_env.tonemap_mode = Environment.TONE_MAPPER_ACES
	_env.tonemap_exposure = 1.0
	_env.tonemap_white = 6.0
	# pick B's golden warmth: a warm per-channel grade (mids and highlights toward honey, shadows kept clean) and
	# a little more saturation, after tonemapping, so every surface in the hall shares it
	_env.adjustment_enabled = true
	_env.adjustment_saturation = 1.12
	_env.adjustment_contrast = 1.04
	var g := Gradient.new()
	g.offsets = PackedFloat32Array([0.0, 0.5, 1.0])
	g.colors = PackedColorArray([Color(0.0, 0.0, 0.0), Color(0.56, 0.49, 0.4), Color(1.0, 0.95, 0.84)])
	var lut := GradientTexture1D.new()
	lut.gradient = g
	lut.width = 256
	_env.adjustment_color_correction = lut
	_env.glow_enabled = false
	if RenderQuality.is_forward_plus() and ResourceLoader.exists(SKY_HDR):
		# desktop: the beach HDRI (the same place as the view through the glass) lights and reflects in the hall
		var sky := Sky.new()
		var pm := PanoramaSkyMaterial.new()
		pm.panorama = load(SKY_HDR)
		sky.sky_material = pm
		sky.radiance_size = Sky.RADIANCE_SIZE_256
		_env.sky = sky
		_env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
		_env.ambient_light_sky_contribution = 0.55
		_env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	else:
		# web/compatibility: filtering a panorama sky's radiance map fails on WebGL (glBlitFramebuffer
		# "missing color attachment") and the canvas stops presenting, freezing the game on this screen.
		# Glossy surfaces use the hand-rolled env map instead (_env_tex).
		_env.reflected_light_source = Environment.REFLECTION_SOURCE_DISABLED
		_env.sky = null
	var we := WorldEnvironment.new()
	we.environment = _env
	_vp.add_child(we)
	# afternoon sun from where it sits in the beach photo (back right, about 40 degrees up)
	_sun = DirectionalLight3D.new()
	# pick B: a low sun behind the back glass, so the mullions throw long warm shafts across the floor toward
	# the overview camera (the old yaw, 128, came in through the side glass)
	_sun.rotation_degrees = Vector3(-18, 166, 0)
	_sun.light_color = Color(1.0, 0.9, 0.78)
	# no shadow map on the web: it gave acne stripes and a hard lit/unlit split across the floor.
	# Cars and people sit on soft contact-shadow decals instead.
	_sun.shadow_enabled = RenderQuality.is_forward_plus()
	_sun.shadow_bias = 0.03
	_sun.shadow_normal_bias = 1.0
	_sun.light_energy = 0.75
	_sun.light_specular = 0.35   # overview glare; set_preset eases it per camera view (GLARE)
	_vp.add_child(_sun)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-60, -30, 0)
	fill.light_energy = 0.3
	fill.light_color = Color(1.0, 0.9, 0.78)   # warm bounce, not a cool sky fill (pick B)
	_vp.add_child(fill)
	# warm downlights over the display floor and the lounge (no shadows: cheap on the web)
	for p in [Vector3(-4.0, 4.2, -2.5), Vector3(2.0, 4.2, -3.0), Vector3(7.0, 4.2, -1.5), Vector3(7.5, 4.0, 4.5)]:
		var l := OmniLight3D.new()
		l.position = p
		l.omni_range = 8.5
		l.light_energy = 0.75
		l.light_color = Color(1.0, 0.82, 0.6)
		_vp.add_child(l)
	# desktop Forward+ gets SSR/SSAO and a box-projected reflection probe of the hall
	RenderQuality.apply_environment(_env, _vp, _sun, Vector3(22, 5, 15))
	# Approved showroom target: readable materials without ceiling bloom or temporal smear.
	_env.glow_enabled = false
	_vp.use_taa = false
	_env.ssao_intensity = 1.0
	_env.ssr_enabled = false  # Avoid noisy screen-space reflections across car plinths.


var _env_cache: Texture2D

## The equirect the web build reflects (the hall, its ceiling lights and the beach through the glass).
func _env_tex() -> Texture2D:
	if _env_cache == null and ResourceLoader.exists(ENV_TEX):
		_env_cache = load(ENV_TEX)
	return _env_cache


## How much hand-rolled reflection glossy surfaces add: all of it on the web, none where real reflections exist.
func _env_strength() -> float:
	return 0.0 if RenderQuality.is_forward_plus() else 1.0


## A Poly Haven PBR material (albedo, OpenGL normal, roughness). `tile` is the texture's size in metres;
## triplanar mapping in world space so boxes of any size get the right scale on every face.
func _pbr(name: String, tile: float, rough_mul := 1.0, tint := Color(1, 1, 1), normal_scale := 1.0) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_texture = load(TEX % [name, "Diffuse"])
	m.albedo_color = tint
	m.roughness_texture = load(TEX % [name, "Rough"])
	m.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED
	m.roughness = rough_mul
	m.normal_enabled = true
	m.normal_texture = load(TEX % [name, "nor_gl"])
	m.normal_scale = normal_scale
	m.uv1_triplanar = true
	m.uv1_world_triplanar = true
	m.uv1_scale = Vector3.ONE / tile
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	return m


## A scanned Poly Haven model standing on the floor at `pos` (its lowest point at y = pos.y), or hung from `pos`
## when `hang` (its top at pos.y). Scaled so its height is `height` metres when given.
func _prop(name: String, pos: Vector3, yaw := 0.0, height := 0.0, hang := false) -> Node3D:
	var path := PROPS % [name, name]
	if not ResourceLoader.exists(path):
		return null
	var n: Node3D = (load(path) as PackedScene).instantiate()
	var holder := Node3D.new()
	holder.add_child(n)
	var ab := _model_aabb(n)
	var k := height / ab.size.y if height > 0.0 and ab.size.y > 0.001 else 1.0
	n.scale = Vector3.ONE * k
	var c := ab.get_center() * k
	n.position = Vector3(-c.x, -(ab.end.y * k) if hang else -(ab.position.y * k), -c.z)
	holder.position = pos
	holder.rotation.y = deg_to_rad(yaw)
	_vp.add_child(holder)
	return holder


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


func _floor_material() -> Material:
	# one stone for the whole hall: large-format grey limestone tiles (about 1.2 m), honed to a soft polish.
	# Its own shader so the web build still gets the hall's reflections in it.
	var m := ShaderMaterial.new()
	m.shader = FLOOR_SHADER
	_floor_mat = m
	m.set_shader_parameter("albedo_tex", load("res://assets/world/showroom_floor_albedo.png"))
	m.set_shader_parameter("normal_tex", load("res://assets/world/showroom_floor_normal.png"))
	m.set_shader_parameter("rough_tex", load("res://assets/world/showroom_floor_rough.png"))
	m.set_shader_parameter("tint", Color(0.84, 0.76, 0.66))   # pick B: warm sand limestone
	m.set_shader_parameter("tile", 2.8)
	m.set_shader_parameter("rough_mul", 0.38)   # pick B's floor is polished: window and car reflections read in it
	m.set_shader_parameter("normal_depth", 0.22)
	m.set_shader_parameter("env_map", _env_tex())
	m.set_shader_parameter("env_strength", _env_strength() * 0.7)
	return m


## Swaps the hall's floor, ceiling, beams, walls and desk for the same shapes with a lightmap UV (exported by
## tests/_export_hall.tscn, baked in Blender Cycles) and multiplies in the baked shadows and bounce light.
## Matches by position and size, so a moved or resized box just stays unbaked.
func _apply_bake() -> void:
	if not FileAccess.file_exists(BAKE_INDEX) or not ResourceLoader.exists(BAKE_LIGHTMAP):
		return
	var index = JSON.parse_string(FileAccess.get_file_as_string(BAKE_INDEX))
	if typeof(index) != TYPE_ARRAY:
		return
	var lm: Texture2D = load(BAKE_LIGHTMAP)
	for c in _vp.get_children():
		var mi := c as MeshInstance3D
		if mi == null or mi.mesh == null or mi.position.y > 4.7:
			continue
		var size := mi.mesh.get_aabb().size
		for e in index:
			var o := Vector3(e.origin[0], e.origin[1], e.origin[2])
			var sz := Vector3(e.size[0], e.size[1], e.size[2])
			var dv := (size - sz).abs()
			if mi.position.distance_to(o) > 0.02 or maxf(dv.x, maxf(dv.y, dv.z)) > 0.05:
				continue
			mi.mesh = load(e.res)
			var m := mi.material_override
			if m is ShaderMaterial:
				m.set_shader_parameter("lightmap", lm)
				m.set_shader_parameter("lightmap_k", BAKE_K)
			elif m is StandardMaterial3D:
				var d := (m as StandardMaterial3D).duplicate() as StandardMaterial3D
				d.detail_enabled = true
				d.detail_uv_layer = BaseMaterial3D.DETAIL_UV_2
				d.detail_blend_mode = BaseMaterial3D.BLEND_MODE_MUL
				d.detail_albedo = lm
				var a := d.albedo_color
				d.albedo_color = Color(a.r * BAKE_WALL, a.g * BAKE_WALL, a.b * BAKE_WALL, a.a)   # 0.5 in the lightmap is about neutral
				mi.material_override = d
			break


## A soft dark ellipse on the floor under a car (stands in for the shadow map the web build can't afford).
func _contact_shadow(size: Vector2, alpha := 0.6) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var qm := QuadMesh.new()
	qm.size = size
	qm.orientation = PlaneMesh.FACE_Y
	mi.mesh = qm
	var sm := ShaderMaterial.new()
	var sh := Shader.new()
	sh.code = "shader_type spatial;\nrender_mode unshaded, blend_mix, depth_draw_never, cull_disabled;\nuniform float strength = 0.6;\nvoid fragment() { vec2 q = abs(UV - 0.5) * 2.0; float d = length(pow(q, vec2(2.5))); ALBEDO = vec3(0.0); ALPHA = strength * (1.0 - smoothstep(0.35, 1.0, d)); }"
	sm.shader = sh
	sm.set_shader_parameter("strength", alpha)
	mi.material_override = sm
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return mi


func _build_room() -> void:
	var frame := _mat(Color(0.04, 0.04, 0.045), 0.35, 0.6)
	var walnut := _pbr("smoked_walnut_veneer", 1.6, 0.6, Color(0.62, 0.5, 0.42))
	var feature := _pbr("smoked_walnut_veneer", 2.0, 0.8, Color(0.85, 0.72, 0.6))
	var stucco := _pbr("white_stucco", 2.5, 1.0, Color(0.93, 0.92, 0.9), 0.6)
	# floor
	var fl := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(24, 17)
	fl.mesh = pm
	fl.position = Vector3(0, 0, -0.5)
	fl.material_override = _floor_material()
	fl.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_vp.add_child(fl)
	# ceiling: white plaster with a walnut soffit along the glass and recessed light discs
	_box(Vector3(24, 0.2, 17), Vector3(0, 4.9, -0.5), stucco, 0, false)
	_box(Vector3(18, 0.08, 1.1), Vector3(1.5, 4.76, -7.2), walnut, 0, false)
	_box(Vector3(1.1, 0.08, 15.0), Vector3(11.0, 4.76, -0.4), walnut, 0, false)
	var glow := StandardMaterial3D.new()
	glow.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	glow.albedo_color = Color(1.0, 0.95, 0.84)
	var rim_m := _mat(Color(0.75, 0.75, 0.76), 0.3, 0.8)
	# Recessed panels reuse existing lights; no additional light or reflection passes.
	for x in [-8.0, -2.0, 4.0, 10.0]:
		for z in [-5.0, 1.0, 5.0]:
			_box(Vector3(0.85, 0.035, 0.55), Vector3(x, 4.78, z), rim_m, 0, false)
			_box(Vector3(0.73, 0.04, 0.43), Vector3(x, 4.755, z), glow, 0, false)
	# back-left: grooved concrete feature wall with the dealer sign; the left wall is plaster
	_box(Vector3(7.0, 4.8, 0.4), Vector3(-7.7, 2.4, -7.9), feature)
	_box(Vector3(0.4, 4.8, 15.6), Vector3(-11.4, 2.4, -0.4), stucco)
	# front wall behind the lounge: one-sided (faces into the hall) so the wide camera outside it sees through
	var fw := MeshInstance3D.new()
	var fq := QuadMesh.new()
	fq.size = Vector2(23.1, 4.8)
	fw.mesh = fq
	fw.material_override = stucco
	fw.position = Vector3(0.15, 2.4, 7.4)
	fw.rotation.y = PI   # quad faces +z by default; turn it to face -z, into the room
	fw.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_vp.add_child(fw)
	_box(Vector3(7.0, 0.12, 0.42), Vector3(-7.7, 0.06, -7.68), frame, 0, false)
	var sign := Label3D.new()
	sign.text = "CHIEF AUTO"
	sign.font = UI.head_font()
	sign.font_size = 96
	sign.pixel_size = 0.006
	sign.modulate = Color(1.0, 0.86, 0.55)   # pick B: a warm brass sign on the wood wall
	sign.outline_size = 0
	sign.position = Vector3(-7.7, 2.65, -7.58)
	sign.shaded = false
	sign.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_vp.add_child(sign)
	var sub := Label3D.new()
	sub.text = "TEWPORT BEACH"
	sub.font_size = 36
	sub.pixel_size = 0.005
	sub.modulate = Color(0.9, 0.73, 0.38)
	sub.outline_size = 0
	sub.position = Vector3(-7.7, 2.08, -7.58)
	sub.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_vp.add_child(sub)
	# glass: the back wall right of the sign and the whole right wall. Faint green-grey tint, more reflective
	# at grazing angles (fresnel), slim black mullions with a head and sill rail.
	var glass := ShaderMaterial.new()
	var gsh := Shader.new()
	gsh.code = """
shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, specular_schlick_ggx;
void fragment() {
	float f = pow(1.0 - clamp(abs(dot(NORMAL, VIEW)), 0.0, 1.0), 4.0);
	ALBEDO = vec3(0.55, 0.62, 0.62);
	ROUGHNESS = 0.03;
	METALLIC = 0.0;
	SPECULAR = 0.9;
	ALPHA = 0.05 + 0.35 * f;
}
"""
	glass.shader = gsh
	var gb := _box(Vector3(15.8, 4.6, 0.04), Vector3(3.8, 2.3, -7.9), glass, 0, false)
	gb.sorting_offset = -1.0
	_box(Vector3(0.04, 4.6, 15.6), Vector3(11.7, 2.3, -0.4), glass, 0, false)
	# the mullions cast the low sun's stripes across the floor (pick B's long light shafts)
	for x in range(-4, 12, 3):
		_box(Vector3(0.08, 4.8, 0.14), Vector3(x, 2.4, -7.9), frame, 0, true)
	for z in range(-7, 8, 3):
		_box(Vector3(0.14, 4.8, 0.08), Vector3(11.7, 2.4, z), frame, 0, true)
	for y in [0.06, 4.55]:
		_box(Vector3(15.8, 0.12, 0.16), Vector3(3.8, y, -7.9), frame, 0, false)
		_box(Vector3(0.16, 0.12, 15.6), Vector3(11.7, y, -0.4), frame, 0, false)
	# outside: one continuous curved backdrop of the beach photo (Spiaggia di Mondello HDRI, tone-mapped),
	# far enough that parallax between panes is small, at the photo's own aspect (200 x 50 degrees) with its
	# horizon at eye level; a stone terrace runs out to it
	_view_mat = StandardMaterial3D.new()
	_view_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_view_mat.albedo_texture = load(VIEW_TEX) if ResourceLoader.exists(VIEW_TEX) else null
	_view_mat.albedo_color = Color(1, 1, 1)
	_view_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	_view_mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	var bd := MeshInstance3D.new()
	bd.mesh = _backdrop_mesh(42.0, deg_to_rad(-70.0), deg_to_rad(130.0), 4.0, 2.2, 0.7)
	bd.material_override = _view_mat
	bd.position = Vector3(1.0, 0, -1.0)
	bd.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_vp.add_child(bd)
	var terrace := _pbr("large_floor_tiles_02", 3.6, 1.0, Color(1.35, 1.32, 1.26), 0.7)
	_box(Vector3(30, 0.1, 9), Vector3(2, -0.06, -12.5), terrace, 0, false)
	_box(Vector3(9, 0.1, 26), Vector3(16.3, -0.06, -1), terrace, 0, false)
	# reception counter (walnut with a stone top) at the feature wall, two bar stools and a pendant pair over it
	_box(Vector3(3.6, 1.05, 0.9), Vector3(-8.4, 0.525, -5.6), walnut)
	_box(Vector3(3.8, 0.06, 1.0), Vector3(-8.4, 1.08, -5.6), _pbr("marble_01", 2.0, 0.25, Color(1.1, 1.08, 1.05)) if ResourceLoader.exists(TEX % ["marble_01", "Diffuse"]) else _mat(Color(0.9, 0.88, 0.84), 0.2))
	_prop("calathea_orbifolia_01", Vector3(-9.6, 1.11, -5.6), 30.0, 0.45)
	for x in [-9.3, -7.6]:
		_prop("bar_chair_round_01", Vector3(x, 0, -4.7), 10.0, 0.78)
	for x in [-9.2, -7.6]:
		_prop("modern_ceiling_lamp_01", Vector3(x, 4.8, -5.6), 0.0, 1.05, true)
	# lounge front right: a scanned sofa, two lounge chairs and a coffee table on the same footprints the
	# customers' navigation already walks around
	_prop("sofa_02", Vector3(7.4, 0, 6.0), 180.0, 0.0)
	for z in [3.3, 4.6]:
		_prop("modern_arm_chair_01", Vector3(9.9, 0, z), -90.0, 0.0)
	_prop("modern_coffee_table_01", Vector3(7.3, 0, 4.2), 90.0, 0.0)
	# planting: a money tree in each corner, leafy pots along the glass
	for p in [[Vector3(-10.0, 0, -6.1), 20.0], [Vector3(10.0, 0, -6.1), 140.0], [Vector3(10.0, 0, 6.2), 250.0]]:
		_box(Vector3(0.65, 0.65, 0.65), p[0] + Vector3(0, 0.325, 0), frame)
		_prop("calathea_orbifolia_01", p[0] + Vector3(0, 0.45, 0), p[1], 1.3)
	for p in [[Vector3(-1.0, 0, -6.4), 0.0], [Vector3(-10.4, 0, 5.5), 70.0], [Vector3(5.2, 0, -6.4), 200.0]]:
		_box(Vector3(0.45, 0.5, 0.45), p[0] + Vector3(0, 0.25, 0), frame)
		_prop("calathea_orbifolia_01", p[0] + Vector3(0, 0.35, 0), p[1], 0.85)
	_coastal_dressing()
	_nav = NavigationRegion3D.new()
	_vp.add_child(_nav)


## Faisal's showroom pick B ("warm coastal comedy", 2026-10-22): warm walnut slats behind the sign, a brass sign
## plate, surfboards leaning by the reception desk, a planter row of palms along the glass and warm wall washes.
## New geometry only (the baked boxes keep their exact positions and sizes, so the lightmap still matches them).
func _coastal_dressing() -> void:
	var slat := _pbr("smoked_walnut_veneer", 0.8, 0.55, Color(1.05, 0.72, 0.46))
	for i in 27:
		var x := -11.0 + 0.25 * i
		_box(Vector3(0.12, 4.6, 0.06), Vector3(x, 2.4, -7.66), slat, 0, false)
	var brass := _mat(Color(0.78, 0.56, 0.24), 0.32, 0.85)
	_box(Vector3(3.9, 1.35, 0.05), Vector3(-7.7, 2.45, -7.61), _mat(Color(0.07, 0.06, 0.05), 0.5), 0, false)
	_box(Vector3(4.0, 0.05, 0.07), Vector3(-7.7, 3.15, -7.6), brass, 0, false)
	_box(Vector3(4.0, 0.05, 0.07), Vector3(-7.7, 1.76, -7.6), brass, 0, false)
	# surfboards leaning on the left wall beside the reception desk
	var boards := [[Vector3(-10.95, 1.15, -3.6), Color(0.16, 0.62, 0.66), Color(0.98, 0.95, 0.88)],
		[Vector3(-10.95, 1.05, -2.85), Color(0.98, 0.93, 0.82), Color(0.93, 0.45, 0.22)],
		[Vector3(-10.95, 1.1, -2.1), Color(0.95, 0.72, 0.28), Color(0.15, 0.32, 0.55)]]
	for b in boards:
		var mi := MeshInstance3D.new()
		var cm := CapsuleMesh.new()
		cm.radius = 0.27
		cm.height = 2.3 if b[0].y > 1.1 else 2.1
		mi.mesh = cm
		mi.material_override = _mat(b[1], 0.28)
		mi.scale = Vector3(1.0, 1.0, 0.13)
		mi.rotation = Vector3(0, PI / 2, deg_to_rad(-10))
		mi.position = b[0]
		_vp.add_child(mi)
		var stripe := MeshInstance3D.new()
		var sm := BoxMesh.new()
		sm.size = Vector3(0.1, cm.height * 0.8, 0.075)
		stripe.mesh = sm
		stripe.material_override = _mat(b[2], 0.3)
		stripe.rotation = mi.rotation
		stripe.position = b[0] + Vector3(0.02, 0, 0)
		_vp.add_child(stripe)
	# palms in walnut planters along the back glass and the right glass
	var planter := _pbr("smoked_walnut_veneer", 1.0, 0.7, Color(0.7, 0.5, 0.36))
	for p in [[Vector3(1.9, 0, -6.95), 30.0], [Vector3(8.2, 0, -6.95), 160.0], [Vector3(10.95, 0, -2.4), 260.0], [Vector3(10.95, 0, 1.8), 80.0]]:
		_box(Vector3(0.7, 0.55, 0.7), p[0] + Vector3(0, 0.275, 0), planter)
		_prop("pachira_aquatica_01", p[0] + Vector3(0, 0.5, 0), p[1], 2.9)
	# a palm-lined promenade outside the glass, between the hall and the beach photo (two draw calls in all)
	# (far enough out that their crowns clear the window head from eye height)
	var bases := []
	for i in 9:
		bases.append(Vector3(-8.0 + i * 3.6, 0, -17.0 - 2.2 * (i % 2)))
	for i in 5:
		bases.append(Vector3(22.0 + 2.0 * (i % 2), 0, -9.0 + i * 4.2))
	# heights chosen so the crowns land inside the glass from the overview camera (eye 2.7 m, sightline over the
	# 4.6 m window head reaches ~5.6 m at the promenade): young palms, 4.2-5.4 m
	var palms := PalmMesh.row(bases, 7, 4.2, 5.4)
	for c in palms.get_children():
		(c as GeometryInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_vp.add_child(palms)
	_sun_rays()
	# warm washes: grazing light down the slat wall and over the desk (no shadows, so the cost stays flat)
	for p in [Vector3(-9.2, 4.2, -6.6), Vector3(-6.2, 4.2, -6.6)]:
		var w := SpotLight3D.new()
		w.position = p
		w.rotation_degrees = Vector3(-80, 0, 0)
		w.spot_range = 6.0
		w.spot_angle = 38.0
		w.light_energy = 2.2
		w.light_color = Color(1.0, 0.78, 0.5)
		_vp.add_child(w)


## Faint light shafts in the air, one per back-glass bay: additive unshaded cards along the sun direction that
## fade along their length and at their edges (pick B's visible rays). Cheap: one material, five quads, no shadows.
func _sun_rays() -> void:
	var m := ShaderMaterial.new()
	var sh := Shader.new()
	sh.code = """
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled;
uniform float strength = 0.18;
void fragment() {
	float across = 1.0 - abs(UV.x - 0.5) * 2.0;
	float along = smoothstep(0.0, 0.15, UV.y) * (1.0 - smoothstep(0.35, 1.0, UV.y));
	ALBEDO = vec3(1.0, 0.82, 0.55) * strength * smoothstep(0.0, 0.7, across) * along;
}
"""
	m.shader = sh
	_rays_mat = m
	var dir := -_sun.global_transform.basis.z if _sun.is_inside_tree() else -Basis.from_euler(_sun.rotation).z
	for x in [-2.5, 0.5, 3.5, 6.5, 9.5]:
		var q := MeshInstance3D.new()
		var qm := QuadMesh.new()
		qm.size = Vector2(1.9, 9.5)
		q.mesh = qm
		q.material_override = m
		q.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		# the card starts at the window head and runs down the sun direction, facing the camera side
		var top := Vector3(x, 4.3, -7.85)
		var centre := top + dir * 4.75
		q.basis = Basis(Vector3.RIGHT, -dir, Vector3.RIGHT.cross(-dir)).orthonormalized()
		q.position = centre
		_vp.add_child(q)


## An open vertical cylinder segment (inside faces) carrying the view photo once, left to right.
## a0/a1: azimuth range (0 = straight down -z, positive towards +x); aspect: image width / height;
## eye_top: the y where the image row `top_frac` should sit (keeps the horizon at a sane height).
func _backdrop_mesh(r: float, a0: float, a1: float, aspect: float, eye_top: float, top_frac: float) -> ArrayMesh:
	var h := r * (a1 - a0) / aspect
	var y_top := eye_top + top_frac * h
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var seg := 48
	for i in seg:
		var u0 := float(i) / seg
		var u1 := float(i + 1) / seg
		var p0 := Vector3(sin(lerp(a0, a1, u0)) * r, 0, -cos(lerp(a0, a1, u0)) * r)
		var p1 := Vector3(sin(lerp(a0, a1, u1)) * r, 0, -cos(lerp(a0, a1, u1)) * r)
		var quad := [[p0, u0, 0.0], [p1, u1, 0.0], [p1, u1, 1.0], [p0, u0, 0.0], [p1, u1, 1.0], [p0, u0, 1.0]]
		for v in quad:
			st.set_uv(Vector2(v[1], v[2]))
			st.add_vertex(v[0] + Vector3(0, y_top - v[2] * h, 0))
	st.generate_normals()
	return st.commit()


## Day/night: the view card and light follow Game.night_amount().
func set_time(night: float, sunset: float) -> void:
	# brighter than 1.0: the unshaded photo goes through ACES, which greyed it into haze next to pick B's sunny view
	_view_mat.albedo_color = Color(1.42, 1.3, 1.08).lerp(Color(0.12, 0.14, 0.24), night).lerp(Color(1.0, 0.82, 0.66), sunset * 0.5)
	_sun.light_energy = lerp(1.85, 0.0, night)
	if _rays_mat:
		_rays_mat.set_shader_parameter("strength", 0.18 * (1.0 - night))   # strong enough that the mullion shafts read on the floor
	_sun.light_color = Color(1.0, 0.74, 0.48).lerp(Color(1.0, 0.64, 0.38), sunset)
	_env.ambient_light_energy = lerp(0.46, 0.42, night)


# ---------------------------------------------------------------- display cars

func set_cars(shown: Array) -> void:
	for d in cars:
		if d.node.has_meta("downlight"):
			(d.node.get_meta("downlight") as Node).queue_free()
		d.node.queue_free()
		d.card.queue_free()
		d.plinth.queue_free()
	cars.clear()
	var plinth_m: Material = _mat(Color(0.2, 0.2, 0.21), 0.2, 0.35)
	if _env_strength() > 0.0 and _env_tex():
		plinth_m = ShaderMaterial.new()
		plinth_m.shader = SURFACE_SHADER
		plinth_m.set_shader_parameter("albedo", Color(0.26, 0.26, 0.27))
		plinth_m.set_shader_parameter("metallic_v", 0.0)
		plinth_m.set_shader_parameter("rough_v", 0.12)
		plinth_m.set_shader_parameter("env_map", _env_tex())
		plinth_m.set_shader_parameter("env_strength", 1.0)
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
			_polish(model)
		var cs := _contact_shadow(Vector2(aabb.size.x + 0.5, aabb.size.z + 0.4), 0.42)
		cs.position = Vector3(aabb.get_center().x, 0.008, aabb.get_center().z)
		holder.add_child(cs)
		var plinth := MeshInstance3D.new()   # dark polished stone disc
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
		# a warm display downlight per car (no shadow map, so it costs a light, not a pass): the paint gets a
		# highlight along its shoulder line like a lit showroom car
		var dl := SpotLight3D.new()
		dl.position = pos + Vector3(0, 4.4, 0.6)
		dl.rotation_degrees = Vector3(-82, 0, 0)
		dl.spot_range = 6.0
		dl.spot_angle = 30.0
		dl.light_energy = 2.6
		dl.light_color = Color(1.0, 0.9, 0.76)
		holder.get_parent().add_child(dl)
		holder.set_meta("downlight", dl)
		cars.append({"car": car, "node": holder, "plinth": plinth, "card": card, "pos": pos, "yaw": deg_to_rad(sp[2]), "aabb": aabb})
	_pending_nav = true


## Showroom finish on a display car: deeper gloss and metal flake in the paint, darker tinted glass, chrome
## or alloy rims, matte rubber and lit lamps. Every material here belongs to this car's own copy.
## On the web (no sky radiance) the paint, glass and bright metal also reflect the hall's env map.
func _polish(n: Node) -> void:
	var env_k := _env_strength()
	var env := _env_tex()
	var stack: Array = [n]
	while not stack.is_empty():
		var x: Node = stack.pop_back()
		stack.append_array(x.get_children())
		if not x is MeshInstance3D:
			continue
		var mi := x as MeshInstance3D
		var key := String(mi.name).trim_prefix("part_")
		var mo := mi.material_override
		if mo is ShaderMaterial and (mo as ShaderMaterial).shader == Car3DView.PAINT_SHADER:
			mo.set_shader_parameter("rough_v", 0.16)
			mo.set_shader_parameter("metallic_v", 0.55)
			mo.set_shader_parameter("env_map", env)
			mo.set_shader_parameter("env_strength", env_k * 0.9)
		elif mo is StandardMaterial3D and (mo as StandardMaterial3D).metallic >= 0.8 and env_k > 0.0:
			mi.material_override = _env_metal(mo, 0.12, env, env_k)   # chrome grille, handles, mirrors, trim
		# the garage styled glass, lamps, rims and chrome to reflect the workshop: point them at the hall
		for i in mi.get_surface_override_material_count():
			var sm := mi.get_surface_override_material(i) as ShaderMaterial
			if sm == null or not sm.has_meta("env_k"):
				continue
			sm.set_shader_parameter("env_map", env)
			sm.set_shader_parameter("env_strength", env_k * float(sm.get_meta("env_k")))
			if key == "glass":
				sm.set_shader_parameter("tint", Color(0.015, 0.02, 0.025, 0.8))


## A StandardMaterial3D's metal look rebuilt on the env-map shader (keeps its colour and texture).
func _env_metal(m: StandardMaterial3D, rough: float, env: Texture2D, k: float) -> ShaderMaterial:
	var sm := ShaderMaterial.new()
	sm.shader = SURFACE_SHADER
	sm.set_shader_parameter("albedo", m.albedo_color)
	if m.albedo_texture:
		sm.set_shader_parameter("albedo_tex", m.albedo_texture)
	sm.set_shader_parameter("metallic_v", m.metallic)
	sm.set_shader_parameter("rough_v", rough)
	sm.set_shader_parameter("env_map", env)
	sm.set_shader_parameter("env_strength", k)
	return sm


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

## The hall is kept between visits (main.gd _park_3d_views), so each visit starts it like a new one: no crowd
## (the next sync places everyone on their spot; customer ids restart at 1 on a new game or load), the wide
## shot without a glide from the last camera, and full quality.
func reset_floor() -> void:
	for ch in _vp.get_children():
		if ch is Customer3D:
			if ch.marker:
				ch.marker.queue_free()
			ch.queue_free()
	npcs.clear()
	focus_customer = {}
	focus_car = {}
	_yaw_off = 0.0
	set_preset("wide")
	_cam_pos = _cam_goal_pos
	_cam_tgt = _cam_goal_tgt
	_apply_cam()
	_quality = 0
	_frames_seen = 0
	_slow_frames = 0
	_vp.msaa_3d = Viewport.MSAA_2X
	stretch_shrink = 1
	_sun.shadow_enabled = RenderQuality.is_forward_plus()


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
		npc.blockers = cars
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

## Sun glare on the polished floor per camera view: the overview looks straight down the sun's reflection, so
## its specular is held back there (pick B's streak, not a white blob at the bottom of the frame); the close
## customer and car views look across it and keep the full highlight on paint and floor. Eased in _process.
const GLARE := {"wide": 0.35, "customer": 0.8, "inspect": 1.0}
var _glare_goal := 0.35
var _glare := 0.35
var _floor_mat: ShaderMaterial


func set_preset(p: String, target = null) -> void:
	preset = p
	_glare_goal = GLARE.get(p, 1.0)
	match p:
		"wide":
			focus_car = {}
			_cam_goal_pos = Vector3(0.5, 2.7, 9.4)
			_cam_goal_tgt = Vector3(0.3, 1.45, -2.2)   # a little more of the glass and the palms beyond it
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
	if absf(_glare - _glare_goal) > 0.005:
		_glare = lerpf(_glare, _glare_goal, k)
		if _sun:
			_sun.light_specular = _glare
		if _floor_mat:
			_floor_mat.set_shader_parameter("spec_k", _glare)
	# software GL / weak GPUs: step quality down while most frames are slow
	# (1: no MSAA, 2: half-resolution 3D, 3: no sun shadows)
	if _quality < 3 and not prewarming:
		_frames_seen += 1
		if delta > 0.06:
			_slow_frames += 1
		# judged over 90 frames (1.5 s at 60): the old 20-frame window also tripped on a screen-switch hitch
		# plus a few loading frames, which halved the hall's resolution for the rest of the session
		if _frames_seen >= 90:
			if _slow_frames >= 72:
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
			_keep_clear(card)
	for id in npcs:
		var npc: Customer3D = npcs[id]
		if npc.marker == null:
			continue
		var head := npc.position + Vector3(0, 2.05, 0)
		npc.marker.visible = npc.visible and _visible(head) and npc.marker.text != ""
		if npc.marker.visible:
			npc.marker.reset_size()
			npc.marker.position = _to_screen(head) - Vector2(npc.marker.size.x / 2.0, npc.marker.size.y)


## A car at the edge of the hall can put its price card under the activity panel or off screen: keep the card
## on screen, and drop it below any panel it would sit under.
func _keep_clear(card: Control) -> void:
	card.position.x = clampf(card.position.x, 8.0, maxf(8.0, size.x - card.size.x - 8.0))
	for c in avoid:
		if not is_instance_valid(c) or not c.is_visible_in_tree():
			continue
		var r := Rect2(c.global_position - global_position, c.size)
		if r.intersects(Rect2(card.position, card.size)):
			card.position.y = r.end.y + 6.0
			if card.position.y + card.size.y > size.y - 8.0:
				# no room below a tall panel in a short window: beside it instead
				card.position = Vector2(r.end.x + 6.0, clampf(card.position.y, 8.0, maxf(8.0, size.y - card.size.y - 8.0)))


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
	var blockers: Array = []   # the showroom's display cars: [{pos, yaw, aabb}]
	const SPEED := 1.25
	const CLEAR := 0.45        # body radius kept clear of a car's footprint

	## p moved out of any car footprint (rotated box plus CLEAR), along the shortest way out.
	func off_cars(p: Vector3) -> Vector3:
		for cd in blockers:
			var ab: AABB = cd.aabb
			var l: Vector3 = (p - cd.pos * Vector3(1, 0, 1)).rotated(Vector3.UP, -cd.yaw)
			var lo := Vector2(ab.position.x - CLEAR, ab.position.z - CLEAR)
			var hi := Vector2(ab.end.x + CLEAR, ab.end.z + CLEAR)
			if l.x > lo.x and l.x < hi.x and l.z > lo.y and l.z < hi.y:
				var outs := [lo.x - l.x, hi.x - l.x, lo.y - l.z, hi.y - l.z]
				var best := 0
				for i in 4:
					if absf(outs[i]) < absf(outs[best]):
						best = i
				if best < 2:
					l.x += outs[best] + signf(outs[best]) * 0.02
				else:
					l.z += outs[best] + signf(outs[best]) * 0.02
				p = cd.pos * Vector3(1, 0, 1) + l.rotated(Vector3.UP, cd.yaw)
				p.y = 0
		return p

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
		spot = off_cars(spot)
		if s == state and home.distance_to(spot) < 0.1:
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
			var nxt := goal   # map not ready yet or no path: walk straight
			# a hall's navigation map syncs on the physics frame after it is created; asking for a path before
			# that logs "NavigationServer navigation map query failed ... before first map synchronization"
			if NavigationServer3D.map_get_iteration_id(agent.get_navigation_map()) > 0:
				nxt = agent.get_next_path_position()
				if agent.is_navigation_finished() or nxt.distance_to(position) < 0.05:
					nxt = goal
			if Vector2(nxt.x - position.x, nxt.z - position.z).length() < 0.05:
				nxt = goal
			var dir := nxt - position
			dir.y = 0
			if dir.length() > 0.01:
				dir = dir.normalized()
				velocity = dir * SPEED
				move_and_slide()
				position.y = 0
				if state != "leaving":
					position = off_cars(position)
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
					goal = off_cars(home + side)
					agent.target_position = goal
		visible = not (state == "test" and not far)
