extends Node
## Screenshot harness for the 3D showroom: godot res://tests/_showroom_shot.tscn -- out_prefix
## Saves <prefix>_wide.png, <prefix>_inspect.png and <prefix>_customer.png.
var n := 0
var sr: Showroom3D
var lobby: Array = []
func _process(_d: float) -> void:
	n += 1
	if n == 3:
		seed(11)
		Game.level = 6
		var cars: Array = []
		for i in 4:
			var c: Dictionary = Game.make_car(60000)
			c["sticker"] = 20000 + i * 6500
			Game.ensure_damage(c)
			cars.append(c)
		sr = Showroom3D.new()
		add_child(sr)
		sr.size = Vector2(1280, 720)
		sr._quality = 3   # keep full quality: software GL would otherwise drop to half resolution
		sr.set_cars(cars)
		for i in 4:
			lobby.append({"id": 100 + i, "pid": "p%02d" % [i * 7 % 24], "look_seed": i * 3, "car_id": cars[i % 4].id, "arrived": -100.0})
		var st := {}
		for c in lobby:
			st[c.id] = "browsing" if c.id % 2 == 0 else "assist"
		sr.sync(lobby, st)
		sr.set_time(0.0, 0.0)
	var out: String = OS.get_cmdline_user_args()[0]
	if n == 240:
		get_viewport().get_texture().get_image().save_png(out + "_wide.png")
		sr.set_preset("inspect", sr.cars[1].car)
	if n == 330:
		get_viewport().get_texture().get_image().save_png(out + "_inspect.png")
		sr.set_preset("customer", lobby[1])
	if n == 420:
		get_viewport().get_texture().get_image().save_png(out + "_customer.png")
		sr.set_preset("wide")
		sr._cam_goal_pos = Vector3(2.0, 2.2, 1.0)
		sr._cam_goal_tgt = Vector3(8.0, 0.8, 4.8)
	if n == 510:
		get_viewport().get_texture().get_image().save_png(out + "_lounge.png")
		print("saved ", out, " fplus=", RenderQuality.is_forward_plus())
		get_tree().quit()
