extends Node
var n := 0
func _process(_d: float) -> void:
	n += 1
	if n == 3:
		seed(7)
		var car: Dictionary = Game.make_car(30000)
		Game.ensure_damage(car)
		var v := Car3DView.new()
		add_child(v)
		v.size = Vector2(1280, 720)
		v.set_car(car)
	if n == 150:
		var out: String = OS.get_cmdline_user_args()[0]
		get_viewport().get_texture().get_image().save_png(out)
		print("saved ", out, " fplus=", RenderQuality.is_forward_plus())
		get_tree().quit()
