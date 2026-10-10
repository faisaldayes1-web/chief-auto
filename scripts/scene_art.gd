class_name SceneArt
extends Control
## Drawn backdrops built around the OC Chief Auto photos: the office desk, the showroom lobby and the service bay.
## Each one is a render of the same dealership (tools/dealership3d.py), tinted for the time of day.


const SHOWROOM_EYE := 0.48     # camera eye level in the showroom render (tools/dealership3d.py "showroom" view)
const SHOWROOM_FLOOR := 0.58   # where the showroom floor meets the back glass, as a fraction of the render height
var mode := "lobby"
var monitor_rect := Rect2()   # where the PC screen sits (desk mode), set in _compute()
var podiums: Array = []       # floor spots for display cars (lobby mode), Vector2 ground points
var podium_targets: Array = [] # sprite frame centres for those cars (lobby mode)
var car_w := 0.0               # display car sprite frame width in pixels (lobby mode), 0 = let the caller choose
var _spots := {}
var desk_view := false        # desk mode: pull back from the PC to show the whole desk and its collectible slots
var desk_top := 0.0           # y of the desk's back edge (desk mode), set in _compute()


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_PASS
	material = WorldLook.new_material()
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
		if desk_view:
			# pulled back: the monitor is a smaller thing in the middle of the desk
			var mw: float = {"crt": 0.26, "lcd": 0.3, "dual": 0.28, "ultra": 0.44}[mon]
			monitor_rect = Rect2(w * (0.5 - mw / 2), h * 0.1, w * mw, h * (0.3 if mon == "crt" else 0.32))
		elif mon == "ultra":
			monitor_rect = Rect2(w * 0.05, h * 0.04, w * 0.9, h * 0.76)
		else:
			monitor_rect = Rect2(w * 0.15, h * 0.04, w * 0.7, h * 0.76)
		desk_top = monitor_rect.end.y + h * (0.1 if desk_view else 0.07)
	elif mode == "lobby":
		podiums = []
		podium_targets = []
		car_w = 0.0
		var n: int = max(1, Game.lot_capacity())
		var per_row: int = min(n, 4)
		var sp := showroom_spots()
		var tex := _tex("showroom")
		if not sp.is_empty() and tex != null:
			# the display row exported with the render (tools/dealership3d.py export_showroom)
			var r := cover_rect(tex)
			# left to right on screen (the camera looks down -y, so the exported row runs right to left)
			var a: Dictionary = sp.row[0]
			var b: Dictionary = sp.row[1]
			if a.ground[0] > b.ground[0]:
				var sw := a
				a = b
				b = sw
			for i in per_row:
				var t: float = 0.5 if per_row == 1 else float(i) / (per_row - 1)
				if per_row == 2:
					t = 0.2 + 0.6 * t
				podiums.append(r.position + _lerp2(a.ground, b.ground, t) * r.size)
				podium_targets.append(r.position + _lerp2(a.target, b.target, t) * r.size)
			car_w = lerpf(a.frame_w, b.frame_w, 0.5) * r.size.x
			_fit_row(w)
		else:
			for i in per_row:
				podiums.append(Vector2(w * (i + 0.5) / per_row, h * 0.62))   # back of the showroom floor, sized to match the render perspective


## Shrink the display row about the screen centre so the outer cars (body and windshield price) stay in frame.
func _fit_row(w: float) -> void:
	if podium_targets.is_empty():
		return
	var cx := w * 0.5
	var margin := 14.0
	var half_body := car_w * 0.43   # the car body spans about 0.15-0.92 of its sprite frame
	var need := 0.0
	for t in podium_targets:
		need = maxf(need, absf(t.x - cx) + half_body)
	var s := (cx - margin) / need if need > 0.0 else 1.0
	if s >= 1.0:
		return
	for i in podiums.size():
		var g: Vector2 = podiums[i]
		var t: Vector2 = podium_targets[i]
		var g2 := Vector2(cx + (g.x - cx) * s, g.y)
		podiums[i] = g2
		podium_targets[i] = g2 + (t - g) * s
	car_w *= s


func _draw() -> void:
	match mode:
		"desk": _draw_desk()
		"lobby": _draw_lobby()
		"garage": _draw_garage()


# ---------- shared pieces ----------

var _texs := {}


## This tier's render for a view, loaded once per stage.
func _tex(view: String) -> Texture2D:
	var key: String = view + Game.world_suffix()
	if not _texs.has(key):
		_texs[key] = load("res://assets/world/bg_%s.jpg" % key)
	return _texs[key]


static func _lerp2(a: Array, b: Array, t: float) -> Vector2:
	return Vector2(lerpf(a[0], b[0], t), lerpf(a[1], b[1], t))


## This tier's showroom camera data (assets/world/showroom*.json): horizon, floor line and the display row.
func showroom_spots() -> Dictionary:
	var key: String = "showroom" + Game.world_suffix()
	if not _spots.has(key):
		var path := "res://assets/world/%s.json" % key
		var res = load(path) if ResourceLoader.exists(path) else null
		var d = res.data if res is JSON else null
		_spots[key] = d if d is Dictionary else {}
	return _spots[key]


func cover_rect(tex: Texture2D) -> Rect2:
	var ts := tex.get_size()
	var sc: float = max(size.x / ts.x, size.y / ts.y)
	var dsz := ts * sc
	return Rect2(Vector2((size.x - dsz.x) / 2.0, size.y - dsz.y), dsz)


## Screen height of a person standing with their feet at feet_y in the showroom render
## (the camera is at eye level, so a 1.75 m person's head lands just above the horizon line).
func person_height(feet_y: float) -> float:
	var r := cover_rect(_tex("showroom"))
	var eye := r.position.y + r.size.y * float(showroom_spots().get("eye", SHOWROOM_EYE))
	return max(40.0, (feet_y - eye) * 1.06)


## Draws one of the dealership renders to cover the whole stage, bottom-aligned, tinted for the time of day.
func _cover(tex: Texture2D, dim := 0.35) -> Rect2:
	var dst := cover_rect(tex)
	var key := tex.resource_path.get_file().get_basename().trim_prefix("bg_")
	var nt := WorldLook.night_tex(key)
	var night: float = Game.night_amount()
	if nt == null:
		draw_texture_rect(tex, dst, false, Game.sky_tint())
		if night > 0.0:
			draw_rect(Rect2(Vector2.ZERO, size), Color(0.02, 0.03, 0.1, night * dim))
		return dst
	# only the sky and outdoors darken: crossfade to the night render (interiors stay lit)
	draw_texture_rect(tex, dst, false, Color(1, 1, 1).lerp(Color(1.0, 0.84, 0.72), Game.sunset_amount()))
	if night > 0.0:
		draw_texture_rect(nt, dst, false, Color(1, 1, 1, night))
	return dst


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
	# the showroom render, bottom-aligned so the marble floor is always in view
	var dst := _cover(_tex("showroom"))
	var horizon := dst.position.y + dst.size.y * float(showroom_spots().get("floor", SHOWROOM_FLOOR))
	# upgrades
	# the espresso bar and lounge are TextureRect children added by main.gd (_lobby_props): this canvas item
	# draws through the WorldLook material, which would wash a product render out to a white box
	if Game.has_upgrade("lights"):
		for p in podiums:
			draw_colored_polygon(PackedVector2Array([Vector2(p.x - 18, h * 0.06), Vector2(p.x + 18, h * 0.06), Vector2(p.x + 140, p.y + 10), Vector2(p.x - 140, p.y + 10)]), Color(1, 0.95, 0.75, 0.07))
	# podiums for the display cars (the corner lot has none: its cars sit on the asphalt)
	if Game.dealership <= 1:
		return
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
	_cover(_tex("desk"))
	var m := monitor_rect
	if desk_view or m.position.x > w * 0.1:
		# right wall shelf
		var sr := shelf_rect()
		draw_rect(sr, Color("6b4a2f"))
		draw_rect(Rect2(sr.position + Vector2(0, sr.size.y), Vector2(sr.size.x, 4)), Color(0, 0, 0, 0.25))
	# desk surface
	var desk: String = Game.equipped.get("desk", "folding")
	var top := desk_top
	var col: Color = {"folding": Color("8c8f94"), "oak": Color("8a5a35"), "glass": Color(0.75, 0.88, 0.95, 0.55), "carbon": Color("1c1c1e")}[desk]
	var dtex := _deskview("desk_" + desk)
	if dtex != null:
		# rendered from the chair (tools/deskview3d.py): its back edge lands on the desk line
		var edge: float = float(_deskview_meta().get("edge_" + desk, 0.42))
		var dh: float = max(w * 9.0 / 16.0, (h - top) / (1.0 - edge))
		var dw := dh * 16.0 / 9.0
		draw_texture_rect(dtex, Rect2((w - dw) / 2.0, top - edge * dh, dw, dh), false)
	else:
		_draw_flat_desk(desk, col, top, w, h)
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
	if desk_view:
		# the PC is on: a dim desktop with the logo while you look at the desk
		var g := m.grow(-2)
		_vgrad(g, Color("1d3550"), Color("0b1522"))
		_text(Vector2(g.get_center().x - 58, g.get_center().y + 8), "CHIEF AUTO", 22, Color(1, 0.85, 0.6, 0.55))
	# stand
	draw_rect(Rect2(m.get_center().x - 18, m.end.y + bezel, 36, top - m.end.y - bezel), bezel_col.darkened(0.2))
	draw_rect(Rect2(m.get_center().x - 70, top - 8, 140, 10), bezel_col.darkened(0.3))
	# keyboard
	draw_rect(Rect2(m.get_center().x - 160, top + 18, 320, 34), Color("26282c"))
	for r in 3:
		for k in 14:
			draw_rect(Rect2(m.get_center().x - 152 + k * 22.5, top + 22 + r * 10, 19, 7), Color("3d4046"))
	# collectibles in their slots, back row first so the front ones overlap them
	for slot in Game.DESK_SLOTS:
		var id: String = Game.desk_slots.get(slot, "")
		var tex := prop_tex(id)
		if tex == null:
			continue
		var r := slot_rect(slot)
		if r.size.x <= 0:
			continue
		draw_texture_rect(tex, r, false, Color(0.96, 0.93, 0.88) if desk_view else Color(0.9, 0.87, 0.82))
	if desk_view and dtex == null:
		# front edge of the desk, so it reads as a top seen from the chair
		draw_rect(Rect2(0, h - h * 0.035, w, h * 0.035), col.darkened(0.35))
		draw_rect(Rect2(0, h - h * 0.035, w, 2), col.lightened(0.2))
	# the chair, seen from behind in the corner
	var chair: String = Game.equipped.get("chair", "plastic")
	var ctex := _deskview("chair_" + chair)
	if ctex != null:
		# its back in the corner, partly behind the bottom bar
		var ch := h * (0.4 if desk_view else 0.32)
		var cw := ch * ctex.get_width() / ctex.get_height()
		draw_texture_rect(ctex, Rect2(-cw * 0.22, h - ch * 0.8, cw, ch), false)
		return
	var ccol: Color = {"plastic": Color("d9d9d9"), "office": Color("2c3e50"), "leather": Color("5a321f"), "racing": Color("111111")}[chair]
	var cx := w * 0.035
	draw_rect(Rect2(cx - 40, h - 70, 110, 90), ccol)
	if chair == "racing":
		draw_rect(Rect2(cx - 10, h - 70, 14, 90), Color("c0392b"))
		draw_rect(Rect2(cx + 26, h - 70, 14, 90), Color("c0392b"))
	elif chair == "leather":
		for i in 3:
			draw_line(Vector2(cx - 40, h - 50 + i * 18), Vector2(cx + 70, h - 50 + i * 18), ccol.darkened(0.3), 2.0)


## The flat-colour desk top (only when the rendered one is missing).
func _draw_flat_desk(desk: String, col: Color, top: float, w: float, h: float) -> void:
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


var _dv := {}
var _dv_meta = null


## A desk-view furniture render (assets/deskview/<name>.png from tools/deskview3d.py), or null.
func _deskview(name: String) -> Texture2D:
	if not _dv.has(name):
		var p := "res://assets/deskview/%s.png" % name
		_dv[name] = load(p) if ResourceLoader.exists(p) else null
	return _dv[name]


func _deskview_meta() -> Dictionary:
	if _dv_meta == null:
		var res = load("res://assets/deskview/deskview.json") if ResourceLoader.exists("res://assets/deskview/deskview.json") else null
		_dv_meta = res.data if res is JSON and res.data is Dictionary else {}
	return _dv_meta


# ---------- service bay ----------

## Wall shelf to the right of the monitor (desk mode).
func shelf_rect() -> Rect2:
	var sx := monitor_rect.end.x + size.x * 0.03
	var y := size.y * (0.3 if desk_view else 0.36)
	return Rect2(sx, y, size.x - sx - size.x * 0.01, 8)


var _props := {}
## Renders are all framed to the same size; small things are drawn smaller on the desk.
const PROP_SCALE := {"mug": 0.6, "magazines": 0.7, "cradle": 0.75, "hula": 0.7, "bobble_marco": 0.8, "bobble_jeff": 0.8,
	"bobble_surfer": 0.8, "bobble_lifeguard": 0.8, "first_dollar": 0.75, "modelcar": 0.95, "aquarium": 1.15, "lamp": 1.1}


## The product render for a shop item (assets/props/<id>.png), or null.
func prop_tex(id: String) -> Texture2D:
	if id == "":
		return null
	if not _props.has(id):
		var p := "res://assets/props/%s.png" % id
		_props[id] = load(p) if ResourceLoader.exists(p) else null
	return _props[id]


## Where a slot's item is drawn: a square the size of the 256px render, whose bottom (the item's base sits at
## 244/256) rests on the desk. Back slots are smaller (further away). At the PC the front slots shrink to fit
## below the screen and a slot that would cover the PC window gets an empty rect.
func slot_rect(slot: String) -> Rect2:
	var w := size.x
	var h := size.y
	var m := monitor_rect
	var top := desk_top
	var base := Vector2.ZERO
	var px := 0.0
	var desk_scale: float = {"folding": 0.92, "oak": 1.0, "glass": 1.0, "carbon": 1.06}.get(Game.equipped.get("desk", "folding"), 1.0)
	if slot == "shelf":
		var sr := shelf_rect()
		if sr.size.x < 40:
			return Rect2()
		base = Vector2(sr.get_center().x, sr.position.y)
		px = min(h * 0.24, sr.size.x * 0.9)
	elif desk_view:
		var back := slot.ends_with("b")
		var left := slot.begins_with("l")
		var fx: float = (0.2 if back else 0.11) * desk_scale
		base = Vector2(w * (fx if left else 1.0 - fx), top + (h - top) * (0.22 if back else 0.86))
		px = h * (0.34 if back else 0.46)
	else:
		# at the PC only the strip of desk under the screen shows
		var back := slot.ends_with("b")
		var left := slot.begins_with("l")
		var room_l := m.position.x - 12
		var free_w: float = room_l
		if free_w < 70:
			if back:
				return Rect2()
			base = Vector2(w * (0.06 if left else 0.94), h - 2)
			px = min(h - top + 30, 120)
		else:
			base = Vector2(free_w * (0.5 if back else 0.4) if left else w - free_w * (0.5 if back else 0.4), top + (h - top) * (0.25 if back else 0.95))
			px = min(free_w * (0.95 if back else 1.15), h * (0.2 if back else 0.27))
	px *= desk_scale if slot != "shelf" else 1.0
	px *= PROP_SCALE.get(Game.desk_slots.get(slot, ""), 1.0)
	var r := Rect2(base.x - px / 2, base.y - px * 244.0 / 256.0, px, px)
	if not desk_view and slot != "shelf" and r.intersects(m.grow(10)) and r.position.x < m.end.x and r.end.x > m.position.x:
		# never cover the PC window: squeeze it into the gap beside the screen instead
		var gap: float = (m.position.x - 14) if r.get_center().x < m.get_center().x else (w - m.end.x - 14)
		if gap < 36:
			return Rect2()
		var k := gap / r.size.x
		r = Rect2(base.x - gap / 2, base.y - r.size.y * k * 244.0 / 256.0, gap, r.size.y * k)
	return r


func _draw_garage() -> void:
	_cover(_tex("garage"), 0.25)
