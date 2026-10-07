class_name CarArt
extends Control
## Side-view car drawing for any car in the game. Paint color, body style and wear come from the car's data.
## Drop a picture at res://assets/cars/<model_slug>.png to replace the drawing with a real render.

const W := 200.0
const H := 80.0

const SHAPES := {
	"economy": {
		"body": [Vector2(6, 60), Vector2(6, 48), Vector2(14, 44), Vector2(55, 40), Vector2(76, 24), Vector2(130, 23), Vector2(152, 38), Vector2(186, 42), Vector2(194, 50), Vector2(194, 60)],
		"windows": [[Vector2(64, 40), Vector2(80, 28), Vector2(102, 28), Vector2(102, 40)], [Vector2(106, 40), Vector2(106, 28), Vector2(127, 28), Vector2(144, 40)]],
		"wheels": [Vector2(44, 60), Vector2(156, 60)], "r": 12.0, "door": 104.0,
	},
	"suv": {
		"body": [Vector2(6, 62), Vector2(6, 40), Vector2(12, 36), Vector2(40, 34), Vector2(52, 16), Vector2(150, 15), Vector2(166, 32), Vector2(190, 36), Vector2(195, 46), Vector2(195, 62)],
		"windows": [[Vector2(58, 33), Vector2(66, 20), Vector2(98, 20), Vector2(98, 33)], [Vector2(102, 33), Vector2(102, 20), Vector2(146, 20), Vector2(156, 33)]],
		"wheels": [Vector2(42, 61), Vector2(160, 61)], "r": 13.5, "door": 100.0,
	},
	"truck": {
		"body": [Vector2(6, 62), Vector2(6, 38), Vector2(12, 36), Vector2(98, 36), Vector2(98, 34), Vector2(104, 15), Vector2(150, 15), Vector2(160, 34), Vector2(190, 37), Vector2(196, 46), Vector2(196, 62)],
		"windows": [[Vector2(108, 33), Vector2(112, 20), Vector2(146, 20), Vector2(154, 33)]],
		"wheels": [Vector2(40, 61), Vector2(160, 61)], "r": 13.5, "door": 128.0,
	},
	"sport": {
		"body": [Vector2(6, 60), Vector2(6, 50), Vector2(20, 46), Vector2(60, 42), Vector2(84, 28), Vector2(124, 27), Vector2(160, 42), Vector2(188, 45), Vector2(195, 52), Vector2(194, 60)],
		"windows": [[Vector2(72, 41), Vector2(89, 31), Vector2(108, 31), Vector2(108, 41)], [Vector2(112, 41), Vector2(112, 31), Vector2(122, 31), Vector2(146, 41)]],
		"wheels": [Vector2(44, 60), Vector2(158, 60)], "r": 12.0, "door": 110.0,
	},
	"exotic": {
		"body": [Vector2(6, 60), Vector2(8, 52), Vector2(30, 48), Vector2(78, 40), Vector2(100, 27), Vector2(128, 27), Vector2(176, 44), Vector2(194, 48), Vector2(196, 56), Vector2(194, 60)],
		"windows": [[Vector2(90, 39), Vector2(105, 30), Vector2(126, 30), Vector2(146, 40)]],
		"wheels": [Vector2(46, 60), Vector2(158, 60)], "r": 12.5, "door": 118.0,
	},
}

const PAINTS := ["c0392b", "1f4e9c", "f2f2f2", "1b1b1f", "8e9aa6", "d4a017", "2e7d4f", "e67e22", "5b2c83", "7a1f2b", "33a1c9"]

var car: Dictionary = {}
var shine := true
var _tex: Texture2D
var _paint: Texture2D
var _detail: Texture2D


static func paint_for(c: Dictionary) -> Color:
	if c.has("color"):
		return Color(c.color)
	return Color(PAINTS[int(c.get("id", 0)) % PAINTS.size()])


static func slug(model: String) -> String:
	return model.to_lower().replace(" ", "_").replace("-", "_")


func set_car(c: Dictionary) -> void:
	car = c
	var sl := slug(c.get("model", ""))
	var path := "res://assets/cars/%s.png" % sl
	_tex = load(path) if ResourceLoader.exists(path) else null
	# rendered side views: a grey paint layer we tint, plus glass, wheels and trim on top
	var pp := "res://assets/cars/%s_paint.png" % sl
	_paint = load(pp) if ResourceLoader.exists(pp) else null
	var dp := "res://assets/cars/%s_detail.png" % sl
	_detail = load(dp) if ResourceLoader.exists(dp) else null
	queue_redraw()


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	resized.connect(queue_redraw)


func _draw() -> void:
	if car.is_empty():
		return
	if _tex:
		var ts := _tex.get_size()
		var sc: float = min(size.x / ts.x, size.y / ts.y)
		var sz := ts * sc
		draw_texture_rect(_tex, Rect2((size - sz) / 2.0, sz), false)
		return
	var s: float = min(size.x / W, size.y / H)
	var off := (size - Vector2(W, H) * s) / 2.0
	if _paint and _detail:
		var rect := Rect2(off, Vector2(W, H) * s)
		var col := paint_for(car)
		# the grey layer peaks around 0.85, so lift the paint a little to keep colours true
		draw_texture_rect(_paint, rect, false, Color(min(col.r * 1.12, 1.0), min(col.g * 1.12, 1.0), min(col.b * 1.12, 1.0)))
		draw_set_transform(off, 0.0, Vector2(s, s))
		_draw_wear()
		draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
		draw_texture_rect(_detail, rect, false)
		return
	draw_set_transform(off, 0.0, Vector2(s, s))
	draw_car(self, car, shine)
	draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)


## Rust and scuffs on top of a rendered car when the body is in bad shape.
func _draw_wear() -> void:
	var parts: Dictionary = car.get("parts", {})
	var body_score: int = parts.get("body", 80)
	if body_score >= 55:
		return
	var rng := RandomNumberGenerator.new()
	rng.seed = int(car.get("id", 1)) * 7919
	for i in int((55 - body_score) / 6) + 2:
		var p := Vector2(rng.randf_range(30, 170), rng.randf_range(52, 62))
		draw_circle(p, rng.randf_range(1.2, 3.0), Color(0.42, 0.24, 0.1, 0.8))
		draw_circle(p + Vector2(1, 1), rng.randf_range(0.6, 1.4), Color(0.25, 0.13, 0.05, 0.8))


## Draws a car in a 200 x 80 box on any CanvasItem (also used for the model car on the desk).
static func draw_car(ci: CanvasItem, c: Dictionary, with_shine := true) -> void:
	var shape: Dictionary = SHAPES.get(c.get("cls", "economy"), SHAPES.economy)
	var paint := paint_for(c)
	var body := PackedVector2Array(shape.body)
	# ground shadow
	var sh := PackedVector2Array()
	for i in 24:
		var a := TAU * i / 24.0
		sh.append(Vector2(100 + cos(a) * 96, 72 + sin(a) * 5))
	ci.draw_colored_polygon(sh, Color(0, 0, 0, 0.35))
	ci.draw_colored_polygon(body, paint)
	# lower shading and upper highlight
	var low := Geometry2D.intersect_polygons(body, PackedVector2Array([Vector2(0, 50), Vector2(W, 50), Vector2(W, H), Vector2(0, H)]))
	for p in low:
		ci.draw_colored_polygon(p, paint.darkened(0.3))
	var mid := Geometry2D.intersect_polygons(body, PackedVector2Array([Vector2(0, 41), Vector2(W, 41), Vector2(W, 45), Vector2(0, 45)]))
	if with_shine:
		for p in mid:
			ci.draw_colored_polygon(p, paint.lightened(0.25))
	ci.draw_polyline(body + PackedVector2Array([body[0]]), paint.darkened(0.45), 1.0, true)
	# windows
	for w in shape.windows:
		var wp := PackedVector2Array(w)
		ci.draw_colored_polygon(wp, Color(0.12, 0.17, 0.24))
		if with_shine and wp.size() >= 3:
			ci.draw_line(wp[1] + Vector2(3, 2), wp[1] + Vector2(10, 9), Color(1, 1, 1, 0.35), 1.5)
	# door seam and handle
	var dx: float = shape.door
	ci.draw_line(Vector2(dx, 41), Vector2(dx, 58), paint.darkened(0.4), 0.8)
	ci.draw_line(Vector2(dx + 6, 45), Vector2(dx + 12, 45), paint.darkened(0.5), 1.4)
	# lights
	var front: Vector2 = body[body.size() - 2]
	ci.draw_rect(Rect2(front.x - 7, front.y + 1, 7, 4), Color("fff3c4"))
	ci.draw_rect(Rect2(6, 47 if c.get("cls", "") != "suv" and c.get("cls", "") != "truck" else 41, 4, 4), Color("e0302a"))
	# wear: rust and dents when the body is in bad shape
	var parts: Dictionary = c.get("parts", {})
	var body_score: int = parts.get("body", 80)
	if body_score < 55:
		var rng := RandomNumberGenerator.new()
		rng.seed = int(c.get("id", 1)) * 7919
		var spots := int((55 - body_score) / 8) + 1
		for i in spots:
			var p := Vector2(rng.randf_range(20, 180), rng.randf_range(46, 57))
			ci.draw_circle(p, rng.randf_range(1.5, 3.5), Color(0.45, 0.25, 0.1, 0.85))
	# wheels
	var r: float = shape.r
	var tires: int = parts.get("tires", 80)
	for wc in shape.wheels:
		ci.draw_circle(wc, r, Color(0.07, 0.07, 0.08))
		ci.draw_circle(wc, r * 0.62, Color(0.72, 0.74, 0.78) if tires >= 50 else Color(0.45, 0.42, 0.38))
		ci.draw_circle(wc, r * 0.18, Color(0.3, 0.3, 0.33))
		for k in 5:
			var a := TAU * k / 5.0
			ci.draw_line(wc, wc + Vector2(cos(a), sin(a)) * r * 0.55, Color(0.4, 0.4, 0.44), 1.2)
