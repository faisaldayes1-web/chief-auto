class_name WorldLook
## The shared look of the world renders (shaders/world_look.gdshader): crossfades each background to its night render
## (bg_<view>_night.jpg from tools/dealership3d.py NIGHT=1) by the game clock, so only the sky and outdoors go dark,
## plus a colour grade, bloom and vignette. Views without a night render fall back to the old whole-picture tint.

const SHADER := preload("res://shaders/world_look.gdshader")

static var _night := {}


## The night render for a full background key like "lot_t1", or null when none was rendered.
static func night_tex(full_key: String) -> Texture2D:
	if not _night.has(full_key):
		var p := "res://assets/world/bg_%s_night.jpg" % full_key
		_night[full_key] = load(p) if ResourceLoader.exists(p) else null
	return _night[full_key]


static func new_material() -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = SHADER
	return m


## Points the material at a background (day texture `day`, key like "showroom_t2") and the current time of day.
static func update(m: ShaderMaterial, day: Texture2D, full_key: String) -> void:
	var nt := night_tex(full_key)
	var n: float = Game.night_amount()
	if nt == null:
		m.set_shader_parameter("night_tex", day)
		m.set_shader_parameter("night", 0.0)
		m.set_shader_parameter("tint", Game.sky_tint())
	else:
		m.set_shader_parameter("night_tex", nt)
		m.set_shader_parameter("night", n)
		m.set_shader_parameter("tint", Color(1, 1, 1).lerp(Color(1.0, 0.84, 0.72), Game.sunset_amount()))
	if day:
		m.set_shader_parameter("texel", Vector2.ONE / day.get_size())
