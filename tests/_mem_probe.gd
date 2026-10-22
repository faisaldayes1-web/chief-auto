extends Node
## Texture-memory probe: which 3D view costs what. godot --path . res://tests/_mem_probe.tscn
var n := 0
var v: Control
func _tm() -> String:
	return "tex %.0f MB vram %.0f MB" % [Performance.get_monitor(Performance.RENDER_TEXTURE_MEM_USED) / 1048576.0, Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED) / 1048576.0]
func _process(_d: float) -> void:
	n += 1
	var which: String = OS.get_cmdline_user_args()[0]
	if n == 5:
		print("empty ", _tm())
		Game.new_game()
		var car: Dictionary = Game.make_car(30000)
		if which == "garage":
			v = Car3DView.new()
			add_child(v); v.size = Vector2(1280, 720)
			v.set_car(car)
		else:
			v = Showroom3D.new()
			add_child(v); v.size = Vector2(1280, 720)
	if n in [6, 20, 60, 120]:
		print(which, " frame ", n, " ", _tm())
	if n == 121:
		get_tree().quit()
