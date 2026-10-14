extends Node
## UI-free renders for store art: godot --resolution 2560x1440 res://tests/_keyart_shot.tscn -- out_prefix
## Saves <prefix>_lot.png (flagship lot, full of cars) and <prefix>_lot_eve.png (late afternoon).
var n := 0
var m: Node
func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
func _hide_ui() -> void:
	m.hud.get_parent().visible = false
	m.nav.get_parent().visible = false
	for c in m.content.get_children():
		if c is VBoxContainer:
			c.visible = false
	m.overlay.visible = false
	for c in m.get_children():
		if c is PanelContainer:
			c.visible = false   # toasts
func _process(_d: float) -> void:
	n += 1
	var out: String = OS.get_cmdline_user_args()[0]
	if n == 2:
		seed(5)
		Game.reset_save()
		Game.debug = true
		Game.debug_tier = 3
		Game.debug_level = 8
		Game.debug_cars = 99
		Game.seen_intro = true
		m = load("res://scenes/main.tscn").instantiate()
		add_child(m)
	if n == 10:
		m._start_game()
		Game.flagship_day = -100   # past the grand-opening week: no bunting
		Game.clock = 13 * 60
		m.show_screen("lot")
	if n == 50:
		_hide_ui()
	if n == 70:
		get_viewport().get_texture().get_image().save_png(out + "_lot.png")
		Game.clock = 17 * 60 + 40
		m.show_screen("lot")
	if n == 110:
		_hide_ui()
	if n == 130:
		get_viewport().get_texture().get_image().save_png(out + "_lot_eve.png")
		print("saved keyart")
		get_tree().quit()
