class_name PersonArt
extends Control
## A simple drawn character (head and shoulders, or full standing figure) whose face follows their mood.
## mood: -1 = furious, 0 = neutral, 1 = thrilled.

const SKINS := ["f1c7a5", "e0ac69", "c68642", "8d5524", "5c3a21", "ffdbac"]
const HAIRS := ["1b1b1b", "4a2c17", "8b5a2b", "d6b370", "a33a1f", "6e6e6e"]
const SHIRTS := ["2d5d9f", "b03a2e", "3c7d4f", "e0e0e0", "6c3483", "d68910", "1f2a44", "17a589"]

var look := {}
## When set, draws the rendered illustration res://assets/people/<pid>_body.png / _face_<mood>.png instead.
var pid := "":
	set(v):
		pid = v
		_load()
var mood := 0.0:
	set(v):
		mood = clamp(v, -1.0, 1.0)
		_load()
var full_body := false:
	set(v):
		full_body = v
		_load()
var _tex: Texture2D
const POOL := 24   # rendered Rocketbox people p00..p23 (tools/people3d.py)


const STAFF_LOOKS := [4, 17]   # p04 is Amna, p17 is Jeff: walk-ins never share their faces


## Rocketbox pool: p00-p11 are women, p12-p23 are men.
const FEMALE_NAMES := ["Kayla", "Priya", "Monica", "Tiffany", "Mei", "Jasmine", "Sofia", "Brooke", "Leila", "Nadia",
	"Marisol", "Brianna", "Tasha", "Caitlin", "Hana", "Imani", "Rosa", "Kiara", "Ava", "Amna", "Sarah", "Eliza", "Maya", "Elena"]


## Picks a face from the pool. With a first name, the face matches it (women's names get a woman, and so on).
static func pool_pid(n: int, name := "") -> String:
	var lo := 0
	var hi := POOL
	if name != "":
		var first := name.split(" ")[0].rstrip(".")
		if first in FEMALE_NAMES:
			hi = POOL / 2
		else:
			lo = POOL / 2
	var options := []
	for i in range(lo, hi):
		if not i in STAFF_LOOKS:
			options.append(i)
	return "p%02d" % options[absi(n) % options.size()]


func _load() -> void:
	_tex = null
	if pid.begins_with("p") and pid.substr(1).is_valid_int() and int(pid.substr(1)) >= POOL:
		pid = pool_pid(int(pid.substr(1)))   # saves from before the 24-person pool
	if pid != "":
		var path := "res://assets/people/%s_body.png" % pid
		if not full_body:
			var m := "happy" if mood > 0.3 else ("angry" if mood < -0.3 else "neutral")
			path = "res://assets/people/%s_face_%s.png" % [pid, m]
		if ResourceLoader.exists(path):
			_tex = load(path)
	queue_redraw()
var highlight := false:
	set(v):
		highlight = v
		queue_redraw()


static func random_look(rng_seed: int) -> Dictionary:
	var rng := RandomNumberGenerator.new()
	rng.seed = rng_seed
	return {
		"skin": SKINS[rng.randi() % SKINS.size()],
		"hair": HAIRS[rng.randi() % HAIRS.size()],
		"style": ["short", "long", "bun", "bald", "curly", "short"][rng.randi() % 6],
		"shirt": SHIRTS[rng.randi() % SHIRTS.size()],
		"jacket": "" if rng.randf() < 0.6 else ["2c3e50", "7f6a4f", "34495e"][rng.randi() % 3],
		"glasses": rng.randf() < 0.25,
	}


const AMNA := {"skin": "c68642", "hair": "1b1b1b", "style": "long", "shirt": "f4f1ec", "jacket": "14213d", "glasses": false, "badge": true}
const JEFF := {"skin": "f1c7a5", "hair": "e3c16f", "style": "spiky", "shirt": "e67e22", "jacket": "", "glasses": false, "badge": true}
const MARUCHAN := {"skin": "c99063", "hair": "141414", "style": "curly", "shirt": "1d2f5e", "jacket": "", "glasses": false, "sunglasses": true, "goatee": true, "badge": true}
const MARCO := {"skin": "d9a066", "hair": "2b1d14", "style": "short", "shirt": "1b1b1f", "jacket": "", "glasses": true, "goatee": true}


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	resized.connect(queue_redraw)


func _draw() -> void:
	if _tex:
		var ts := _tex.get_size()
		var sc: float = min(size.x / ts.x, size.y / ts.y)
		var sz := ts * sc
		if highlight:
			draw_circle(Vector2(size.x / 2, size.y - sz.y * 0.75), sz.x * 0.45, Color(1, 0.85, 0.3, 0.18))
		if full_body:
			# feet sit on the bottom edge (renders are cropped to the figure); ground them with a soft contact shadow
			var foot := Vector2(size.x / 2.0, size.y - sz.y * 0.012)
			for k in 4:
				var f := 1.0 - k * 0.22
				_shadow(foot, sz.x * 0.62 * f, sz.y * 0.022 * f, 0.13)
		draw_texture_rect(_tex, Rect2(Vector2((size.x - sz.x) / 2.0, size.y - sz.y), sz), false)
		return
	if look.is_empty():
		return
	# Drawn in a 100 x 130 box (bust) or 100 x 240 box (full body).
	var bw := 100.0
	var bh := 240.0 if full_body else 130.0
	var s: float = min(size.x / bw, size.y / bh)
	var off := Vector2((size.x - bw * s) / 2.0, size.y - bh * s)
	draw_set_transform(off, 0.0, Vector2(s, s))
	var y0 := 0.0
	if full_body:
		_draw_legs()
	if highlight:
		draw_circle(Vector2(50, 70), 52, Color(1, 0.85, 0.3, 0.18))
	_draw_bust(y0)
	draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)


func _shadow(c: Vector2, rx: float, ry: float, a: float) -> void:
	var pts := PackedVector2Array()
	for i in 28:
		var t := TAU * i / 28.0
		pts.append(c + Vector2(cos(t) * rx, sin(t) * ry))
	draw_colored_polygon(pts, Color(0, 0, 0, a))


func _draw_legs() -> void:
	var pants := Color("2b2f3a")
	draw_colored_polygon(PackedVector2Array([Vector2(30, 128), Vector2(70, 128), Vector2(68, 230), Vector2(54, 230), Vector2(50, 150), Vector2(46, 230), Vector2(32, 230)]), pants)
	draw_rect(Rect2(28, 228, 20, 8), Color("111111"))
	draw_rect(Rect2(52, 228, 20, 8), Color("111111"))


func _draw_bust(_y0: float) -> void:
	var skin := Color(look.skin)
	var hair := Color(look.hair)
	var shirt := Color(look.shirt)
	# torso
	var torso := PackedVector2Array([Vector2(14, 130), Vector2(18, 92), Vector2(32, 82), Vector2(68, 82), Vector2(82, 92), Vector2(86, 130)])
	draw_colored_polygon(torso, shirt)
	if look.get("jacket", "") != "":
		var jc := Color(look.jacket)
		draw_colored_polygon(PackedVector2Array([Vector2(14, 130), Vector2(18, 92), Vector2(32, 82), Vector2(44, 84), Vector2(48, 130)]), jc)
		draw_colored_polygon(PackedVector2Array([Vector2(86, 130), Vector2(82, 92), Vector2(68, 82), Vector2(56, 84), Vector2(52, 130)]), jc)
	if look.get("badge", false):
		draw_rect(Rect2(60, 98, 14, 8), Color("e8b64c"))
	# neck
	draw_rect(Rect2(43, 70, 14, 14), skin.darkened(0.08))
	# back hair (long styles)
	if look.style == "long":
		draw_colored_polygon(PackedVector2Array([Vector2(26, 40), Vector2(74, 40), Vector2(80, 96), Vector2(20, 96)]), hair)
	# head
	draw_circle(Vector2(50, 46), 26, skin)
	# hair on top
	match look.style:
		"short", "long":
			draw_colored_polygon(PackedVector2Array([Vector2(24, 44), Vector2(26, 28), Vector2(38, 19), Vector2(58, 18), Vector2(72, 26), Vector2(76, 44), Vector2(70, 34), Vector2(50, 30), Vector2(32, 34)]), hair)
		"bun":
			draw_colored_polygon(PackedVector2Array([Vector2(24, 42), Vector2(28, 26), Vector2(50, 18), Vector2(72, 26), Vector2(76, 42), Vector2(50, 30)]), hair)
			draw_circle(Vector2(50, 15), 9, hair)
		"curly":
			for p in [Vector2(30, 30), Vector2(40, 22), Vector2(52, 19), Vector2(64, 23), Vector2(72, 32), Vector2(26, 40), Vector2(75, 41)]:
				draw_circle(p, 9, hair)
		"spiky":
			draw_colored_polygon(PackedVector2Array([Vector2(24, 40), Vector2(26, 22), Vector2(34, 28), Vector2(38, 12), Vector2(46, 24), Vector2(52, 8), Vector2(58, 23), Vector2(66, 12), Vector2(68, 27), Vector2(76, 22), Vector2(76, 40), Vector2(50, 30)]), hair)
		"bald":
			pass
	if look.get("goatee", false):
		draw_colored_polygon(PackedVector2Array([Vector2(42, 62), Vector2(58, 62), Vector2(55, 72), Vector2(45, 72)]), hair)
	_draw_face()


func _draw_face() -> void:
	var ink := Color(0.12, 0.1, 0.1)
	var ey := 46.0
	# eyebrows tilt with anger
	var tilt: float = clamp(-mood, 0.0, 1.0) * 4.0
	draw_line(Vector2(36, 38 - 0.0), Vector2(46, 38 + tilt), ink, 2.0)
	draw_line(Vector2(54, 38 + tilt), Vector2(64, 38), ink, 2.0)
	draw_circle(Vector2(41, ey), 2.6, ink)
	draw_circle(Vector2(59, ey), 2.6, ink)
	if look.get("sunglasses", false):
		draw_rect(Rect2(33, ey - 5, 15, 9), Color(0.05, 0.05, 0.07))
		draw_rect(Rect2(52, ey - 5, 15, 9), Color(0.05, 0.05, 0.07))
		draw_line(Vector2(48, ey - 2), Vector2(52, ey - 2), ink, 1.6)
		draw_line(Vector2(35, ey - 3), Vector2(40, ey - 3), Color(1, 1, 1, 0.3), 1.2)
	elif look.get("glasses", false):
		draw_arc(Vector2(41, ey), 6.5, 0, TAU, 20, ink, 1.4)
		draw_arc(Vector2(59, ey), 6.5, 0, TAU, 20, ink, 1.4)
		draw_line(Vector2(47.5, ey), Vector2(52.5, ey), ink, 1.4)
	# mouth: smile, flat or frown
	var curve: float = mood * 7.0
	var pts := PackedVector2Array()
	for i in 9:
		var t := i / 8.0
		var x: float = lerp(40.0, 60.0, t)
		var y: float = 59.0 + curve * (1.0 - pow(2.0 * t - 1.0, 2)) - curve * 0.3
		pts.append(Vector2(x, y))
	draw_polyline(pts, Color(0.45, 0.15, 0.15), 2.2, true)
	if mood < -0.6:
		# steam of anger
		draw_line(Vector2(80, 22), Vector2(86, 14), Color(0.9, 0.3, 0.2), 2.0)
		draw_line(Vector2(84, 26), Vector2(92, 20), Color(0.9, 0.3, 0.2), 2.0)
