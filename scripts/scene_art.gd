class_name SceneArt
extends Control
## Drawn backdrops built around the OC Chief Auto photos: the office desk, the showroom lobby and the service bay.
## Windows look out on the real lot photo, tinted for the time of day.

const LOT := preload("res://assets/bg_lot.jpg")
const SHOWROOM := preload("res://assets/bg_showroom.jpg")

var mode := "lobby"
var monitor_rect := Rect2()   # where the PC screen sits (desk mode), set in _compute()
var podiums: Array = []       # floor spots for display cars (lobby mode), Vector2 centers


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_PASS
	resized.connect(func():
		_compute()
		queue_redraw())
	_compute()


func _process(_d: float) -> void:
	# The sky changes with the clock; redraw a few times a second.
	if Engine.get_process_frames() % 20 == 0:
		queue_redraw()


func _compute() -> void:
	var w := size.x
	var h := size.y
	if mode == "desk":
		var mon: String = Game.equipped.get("monitor", "crt")
		if mon == "ultra":
			monitor_rect = Rect2(w * 0.05, h * 0.04, w * 0.9, h * 0.76)
		else:
			monitor_rect = Rect2(w * 0.15, h * 0.04, w * 0.7, h * 0.76)
	elif mode == "lobby":
		podiums = []
		var n: int = max(1, Game.lot_capacity())
		var per_row: int = min(n, 4)
		for i in per_row:
			podiums.append(Vector2(w * (i + 0.5) / per_row, h * 0.8))


func _draw() -> void:
	match mode:
		"desk": _draw_desk()
		"lobby": _draw_lobby()
		"garage": _draw_garage()


# ---------- shared pieces ----------

func _window(rect: Rect2, src: Rect2, mullions := 0) -> void:
	draw_texture_rect_region(LOT, rect, src, Game.sky_tint())
	var night: float = Game.night_amount()
	if night > 0.0:
		draw_rect(rect, Color(0.02, 0.04, 0.12, night * 0.55))
		var rng := RandomNumberGenerator.new()
		rng.seed = int(rect.position.x * 13 + rect.size.y)
		for i in int(rect.size.x * rect.size.y / 3000.0):
			var p := rect.position + Vector2(rng.randf() * rect.size.x, rng.randf() * rect.size.y * 0.45)
			draw_circle(p, rng.randf_range(0.6, 1.4), Color(1, 1, 1, night * rng.randf_range(0.4, 0.9)))
	var frame := Color(0.08, 0.08, 0.09)
	draw_rect(rect, frame, false, 6.0)
	for i in range(1, mullions + 1):
		var x := rect.position.x + rect.size.x * i / float(mullions + 1)
		draw_line(Vector2(x, rect.position.y), Vector2(x, rect.end.y), frame, 5.0)


func _vgrad(rect: Rect2, top: Color, bottom: Color) -> void:
	draw_polygon(PackedVector2Array([rect.position, Vector2(rect.end.x, rect.position.y), rect.end, Vector2(rect.position.x, rect.end.y)]),
		PackedColorArray([top, top, bottom, bottom]))


func _ellipse(c: Vector2, rx: float, ry: float, col: Color) -> void:
	var pts := PackedVector2Array()
	for i in 32:
		var a := TAU * i / 32.0
		pts.append(c + Vector2(cos(a) * rx, sin(a) * ry))
	draw_colored_polygon(pts, col)


func _plant(base: Vector2, sc := 1.0) -> void:
	draw_rect(Rect2(base + Vector2(-14, -26) * sc, Vector2(28, 26) * sc), Color("8a5a3b"))
	for k in 7:
		var a := -PI / 2 + (k - 3) * 0.35
		var tip := base + Vector2(cos(a) * 46, -26 + sin(a) * 46) * sc
		draw_line(base + Vector2(0, -26) * sc, tip, Color("2f7d32"), 6.0 * sc)
		draw_circle(tip, 7 * sc, Color("3f9a43"))


func _text(pos: Vector2, text: String, size_px: int, col: Color) -> void:
	draw_string(get_theme_default_font(), pos, text, HORIZONTAL_ALIGNMENT_LEFT, -1, size_px, col)


# ---------- showroom lobby ----------

func _draw_lobby() -> void:
	var w := size.x
	var h := size.y
	# the real showroom photo, bottom-aligned so the marble floor is always in view
	var ts := SHOWROOM.get_size()
	var sc: float = max(w / ts.x, h / ts.y)
	var dsz := ts * sc
	var dst := Rect2(Vector2((w - dsz.x) / 2.0, h - dsz.y), dsz)
	draw_texture_rect(SHOWROOM, dst, false, Game.sky_tint())
	var night: float = Game.night_amount()
	if night > 0.0:
		draw_rect(Rect2(0, 0, w, h), Color(0.02, 0.03, 0.1, night * 0.35))
	var horizon := dst.position.y + dsz.y * 0.69
	# upgrades
	if Game.has_upgrade("coffee"):
		draw_rect(Rect2(w * 0.005, horizon - 70, w * 0.09, 70), Color("2b2b2f"))
		draw_rect(Rect2(w * 0.005, horizon - 74, w * 0.09, 6), Color("b08d57"))
		draw_rect(Rect2(w * 0.025, horizon - 104, 34, 30), Color("9aa0a6"))
		_text(Vector2(w * 0.012, horizon - 82), "ESPRESSO", 11, Color("e8b64c"))
	if Game.has_upgrade("lounge"):
		var sx := w * 0.82
		draw_rect(Rect2(sx, horizon - 30, w * 0.16, 50), Color("6b3e26"))
		draw_rect(Rect2(sx, horizon - 58, w * 0.16, 32), Color("7d4a2e"))
		draw_rect(Rect2(sx - 10, horizon - 40, 18, 60), Color("5a321f"))
		draw_rect(Rect2(sx + w * 0.16 - 8, horizon - 40, 18, 60), Color("5a321f"))
	if Game.has_upgrade("lights"):
		for p in podiums:
			draw_colored_polygon(PackedVector2Array([Vector2(p.x - 18, h * 0.06), Vector2(p.x + 18, h * 0.06), Vector2(p.x + 140, p.y + 10), Vector2(p.x - 140, p.y + 10)]), Color(1, 0.95, 0.75, 0.07))
	# podiums for the display cars
	for p in podiums:
		var glow := Game.has_upgrade("turntable")
		_ellipse(p + Vector2(0, 6), 150, 22, Color(0, 0, 0, 0.25))
		_ellipse(p, 146, 18, Color(1, 1, 1, 0.22) if not glow else Color(0.95, 0.85, 0.6, 0.5))
		if glow:
			draw_arc(p, 146, 0, TAU, 48, Color("e8b64c"), 2.0)


# ---------- office desk ----------

func _draw_desk() -> void:
	var w := size.x
	var h := size.y
	_vgrad(Rect2(0, 0, w, h), Color("2a2420"), Color("1e1a17"))
	var m := monitor_rect
	# side window onto the coast
	if m.position.x > w * 0.1:
		_window(Rect2(w * 0.015, h * 0.08, m.position.x - w * 0.04, h * 0.5), Rect2(0, 0, 500, 420), 1)
		# right wall shelf
		var sx := m.end.x + w * 0.015
		draw_rect(Rect2(sx, h * 0.36, w - sx - w * 0.01, 8), Color("6b4a2f"))
		if Game.has_decor("trophy"):
			draw_rect(Rect2(sx + 20, h * 0.36 - 14, 30, 14), Color("8a6a2a"))
			draw_colored_polygon(PackedVector2Array([Vector2(sx + 22, h * 0.36 - 14), Vector2(sx + 48, h * 0.36 - 14), Vector2(sx + 54, h * 0.36 - 56), Vector2(sx + 16, h * 0.36 - 56)]), Color("e8b64c"))
		if Game.has_decor("modelcar"):
			draw_set_transform(Vector2(sx + 6, h * 0.36 - 30), 0, Vector2(0.4, 0.4))
			CarArt.draw_car(self, {"cls": "exotic", "id": 3, "color": "c0392b", "parts": {}})
			draw_set_transform(Vector2.ZERO, 0, Vector2.ONE)
	if Game.has_decor("neon"):
		var glow := Color(1.0, 0.25, 0.45)
		_text(Vector2(w * 0.02, h * 0.72), "CHIEF", 34, Color(glow, 0.35))
		_text(Vector2(w * 0.02 + 1, h * 0.72 - 1), "CHIEF", 34, glow.lightened(0.4))
	# desk surface
	var desk: String = Game.equipped.get("desk", "folding")
	var top := m.end.y + h * 0.07
	var col: Color = {"folding": Color("8c8f94"), "oak": Color("8a5a35"), "glass": Color(0.75, 0.88, 0.95, 0.55), "carbon": Color("1c1c1e")}[desk]
	draw_rect(Rect2(0, top, w, h - top), col)
	draw_rect(Rect2(0, top, w, 5), col.lightened(0.25))
	match desk:
		"oak":
			for i in 6:
				var y := top + 10 + i * 7
				draw_line(Vector2(0, y), Vector2(w, y + (i % 2) * 3), Color(0, 0, 0, 0.12), 1.5)
		"carbon":
			for x in range(0, int(w), 10):
				for y in range(int(top) + 6, int(h), 10):
					if (x / 10 + y / 10) % 2 == 0:
						draw_rect(Rect2(x, y, 10, 10), Color(1, 1, 1, 0.04))
			draw_rect(Rect2(0, top + 4, w, 3), Color("c0392b"))
		"glass":
			draw_rect(Rect2(0, top, w, 2), Color(1, 1, 1, 0.8))
		"folding":
			draw_line(Vector2(w * 0.1, top), Vector2(w * 0.14, h), Color("4a4d52"), 4.0)
			draw_line(Vector2(w * 0.9, top), Vector2(w * 0.86, h), Color("4a4d52"), 4.0)
	# monitor(s)
	var mon: String = Game.equipped.get("monitor", "crt")
	if mon == "dual":
		var side := Rect2(m.end.x - 10, m.position.y + 30, w - m.end.x - 4, m.size.y - 50)
		draw_rect(side.grow(10), Color("111214"))
		draw_rect(side, Color("0f2a44"))
		_text(side.position + Vector2(12, 28), "AutoBidz watchlist", 13, Color("9cc7f0"))
		for i in 5:
			draw_rect(Rect2(side.position + Vector2(12, 44 + i * 26), Vector2(side.size.x - 30, 16)), Color(0.4, 0.6, 0.9, 0.25))
	var bezel: float = {"crt": 22.0, "lcd": 12.0, "dual": 12.0, "ultra": 10.0}[mon]
	var bezel_col := Color("cfc6a8") if mon == "crt" else Color("111214")
	draw_rect(m.grow(bezel), bezel_col)
	if mon == "crt":
		draw_rect(m.grow(bezel), Color(0, 0, 0, 0.2), false, 3.0)
		_text(Vector2(m.get_center().x - 30, m.end.y + bezel - 5), "TEWTRON", 12, Color("6a6450"))
	# stand
	draw_rect(Rect2(m.get_center().x - 18, m.end.y + bezel, 36, top - m.end.y - bezel), bezel_col.darkened(0.2))
	draw_rect(Rect2(m.get_center().x - 70, top - 8, 140, 10), bezel_col.darkened(0.3))
	# keyboard
	draw_rect(Rect2(m.get_center().x - 160, top + 18, 320, 34), Color("26282c"))
	for r in 3:
		for k in 14:
			draw_rect(Rect2(m.get_center().x - 152 + k * 22.5, top + 22 + r * 10, 19, 7), Color("3d4046"))
	# desk decor
	if Game.has_decor("plant"):
		_plant(Vector2(w * 0.06, top + 40), 1.0)
	if Game.has_decor("mug"):
		var mx := m.get_center().x + 200
		draw_rect(Rect2(mx, top + 6, 26, 32), Color("f2f2f2"))
		draw_arc(Vector2(mx + 28, top + 20), 8, -PI / 2, PI / 2, 10, Color("f2f2f2"), 4.0)
		_text(Vector2(mx + 2, top + 28), "#1", 12, Color("c0392b"))
	if Game.has_decor("aquarium"):
		var ax := w * 0.83
		draw_rect(Rect2(ax, top - 70, 150, 76), Color(0.2, 0.55, 0.8, 0.6))
		draw_rect(Rect2(ax, top - 70, 150, 76), Color(0.8, 0.9, 1.0, 0.6), false, 2.0)
		var t := Time.get_ticks_msec() / 1000.0
		for i in 3:
			var fx := ax + 20 + fmod(t * (18 + i * 7) + i * 40, 110)
			var fy := top - 50 + i * 18
			draw_colored_polygon(PackedVector2Array([Vector2(fx, fy), Vector2(fx + 12, fy - 5), Vector2(fx + 12, fy + 5)]), Color(["ff7f27", "ffd23f", "e8505b"][i]))
	# chair back in the corner
	var chair: String = Game.equipped.get("chair", "plastic")
	var ccol: Color = {"plastic": Color("d9d9d9"), "office": Color("2c3e50"), "leather": Color("5a321f"), "racing": Color("111111")}[chair]
	var cx := w * 0.035
	draw_rect(Rect2(cx - 40, h - 70, 110, 90), ccol)
	if chair == "racing":
		draw_rect(Rect2(cx - 10, h - 70, 14, 90), Color("c0392b"))
		draw_rect(Rect2(cx + 26, h - 70, 14, 90), Color("c0392b"))
	elif chair == "leather":
		for i in 3:
			draw_line(Vector2(cx - 40, h - 50 + i * 18), Vector2(cx + 70, h - 50 + i * 18), ccol.darkened(0.3), 2.0)


# ---------- service bay ----------

func _draw_garage() -> void:
	var w := size.x
	var h := size.y
	var horizon := h * 0.62
	_vgrad(Rect2(0, 0, w, horizon), Color("5b5f66"), Color("4a4e55"))
	for i in 12:
		draw_line(Vector2(0, i * horizon / 12.0), Vector2(w, i * horizon / 12.0), Color(0, 0, 0, 0.12), 1.0)
	# roll-up door, half open onto the lot
	var door := Rect2(w * 0.04, h * 0.12, w * 0.3, horizon - h * 0.12)
	_window(Rect2(door.position + Vector2(0, door.size.y * 0.45), Vector2(door.size.x, door.size.y * 0.55)), Rect2(500, 200, 700, 300), 0)
	for i in 9:
		var y := door.position.y + i * door.size.y * 0.05
		draw_rect(Rect2(door.position.x, y, door.size.x, door.size.y * 0.05 - 2), Color("aab0b8"))
	draw_rect(door, Color("2c2f34"), false, 8.0)
	# pegboard with tools
	var pb := Rect2(w * 0.38, h * 0.12, w * 0.2, h * 0.3)
	draw_rect(pb, Color("b98b5e"))
	for x in range(int(pb.position.x) + 10, int(pb.end.x), 16):
		for y in range(int(pb.position.y) + 10, int(pb.end.y), 16):
			draw_circle(Vector2(x, y), 1.5, Color(0, 0, 0, 0.35))
	draw_line(pb.position + Vector2(30, 20), pb.position + Vector2(30, 90), Color("c0392b"), 6.0)
	draw_line(pb.position + Vector2(70, 20), pb.position + Vector2(70, 80), Color("7f8c8d"), 5.0)
	draw_circle(pb.position + Vector2(70, 84), 8, Color("7f8c8d"))
	draw_rect(Rect2(pb.position + Vector2(110, 30), Vector2(60, 16)), Color("2471a3"))
	_text(Vector2(w * 0.38, h * 0.08), "SERVICE BAY", 22, Color("f1c40f"))
	# floor
	_vgrad(Rect2(0, horizon, w, h - horizon), Color("3a3d42"), Color("2a2c30"))
	draw_line(Vector2(0, horizon + (h - horizon) * 0.55), Vector2(w, horizon + (h - horizon) * 0.55), Color("f1c40f"), 4.0)
	# lift posts around the car spot
	var cxp := w * 0.3
	draw_rect(Rect2(cxp - w * 0.22, horizon - h * 0.25, 18, h * 0.42), Color("c0392b"))
	draw_rect(Rect2(cxp + w * 0.22 - 18, horizon - h * 0.25, 18, h * 0.42), Color("c0392b"))
	draw_rect(Rect2(cxp - w * 0.2, horizon + h * 0.12, w * 0.4, 10), Color("7f8c8d"))
	# lamp light at night
	var night: float = Game.night_amount()
	draw_rect(Rect2(0, 0, w, h), Color(0, 0, 0.05, night * 0.25))
