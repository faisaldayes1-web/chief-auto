extends Node
## Screenshots of the title, settings and pause menu: godot res://tests/_menu_shot.tscn -- out_prefix
var n := 0
var m: Node
func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
func _process(_d: float) -> void:
	n += 1
	var out: String = OS.get_cmdline_user_args()[0]
	if n == 2:
		m = load("res://scenes/main.tscn").instantiate()
		add_child(m)
	if n == 40:
		get_viewport().get_texture().get_image().save_png(out + "_title.png")
		m.pause_menu.open(true)
	if n == 60:
		get_viewport().get_texture().get_image().save_png(out + "_settings.png")
		m.pause_menu.close()
		Game.seen_intro = true
		m._start_game()
	if n == 120:
		m.pause_menu.open()
	if n == 140:
		get_viewport().get_texture().get_image().save_png(out + "_pause.png")
		print("saved menus")
		get_tree().quit()
