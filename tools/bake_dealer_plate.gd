extends Node
## Bakes assets/cars3d/dealer_plate.png, the CHIEF AUTO dealer plate texture used on every car (Car3DView._add_plates):
## one textured quad per plate instead of two boxes and two Label3Ds. Uses the game's own fonts (Barlow, OFL).
##   godot --path . res://tools/bake_dealer_plate.tscn      (needs rendering, not --headless)
const W := 512
const H := 256

func _ready() -> void:
	var vp := SubViewport.new()
	vp.size = Vector2i(W, H)
	vp.transparent_bg = false
	vp.render_target_update_mode = SubViewport.UPDATE_ONCE
	add_child(vp)
	var bg := ColorRect.new()
	bg.color = Color(0.78, 0.79, 0.81)            # chrome frame
	bg.size = Vector2(W, H)
	vp.add_child(bg)
	var face := Panel.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.95, 0.95, 0.92)
	sb.set_corner_radius_all(14)
	sb.border_color = Color(0.55, 0.56, 0.6)
	sb.set_border_width_all(3)
	face.add_theme_stylebox_override("panel", sb)
	face.position = Vector2(16, 16)
	face.size = Vector2(W - 32, H - 32)
	vp.add_child(face)
	for spec in [["TEWPORT BEACH", 26, Color(0.12, 0.22, 0.5), 30, false],
			["CHIEF AUTO", 98, Color(0.74, 0.08, 0.06), 70, true],
			["DEALER", 28, Color(0.12, 0.22, 0.5), 196, false]]:
		var l := Label.new()
		l.text = spec[0]
		l.add_theme_font_size_override("font_size", spec[1])
		l.add_theme_color_override("font_color", spec[2])
		l.add_theme_font_override("font", load("res://assets/fonts/BarlowCondensed-SemiBold.woff2") if spec[4] else load("res://assets/fonts/Barlow-Medium.woff2"))
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		l.position = Vector2(0, spec[3])
		l.size = Vector2(W, spec[1] * 1.2)
		vp.add_child(l)
	for x in [40.0, W - 52.0]:   # the two bolt heads
		var b := ColorRect.new()
		b.color = Color(0.6, 0.6, 0.63)
		b.position = Vector2(x, 38)
		b.size = Vector2(12, 12)
		vp.add_child(b)
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	vp.get_texture().get_image().save_png("res://assets/cars3d/dealer_plate.png")
	print("baked dealer_plate.png")
	get_tree().quit()
