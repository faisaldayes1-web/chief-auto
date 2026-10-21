extends Node
func _ready() -> void:
	if not OS.get_environment("APPDATA").contains("ory-pm-chief"):
		push_error("Capture requires isolated APPDATA")
		get_tree().quit(2)
		return
	seed(5)
	Game.new_game()
	Game.seen_intro = true
	Game.tutorial = 99
	Game.level = 6
	Game.money = 180000
	for i in 4:
		var c: Dictionary = Game.make_car(18000 + i * 9000)
		Game.ensure_damage(c)
		c["sticker"] = int(c.get("base", 20000) * 1.25 / 100) * 100
		Game.cars.append(c)
	var main: Node = load("res://scenes/main.tscn").instantiate()
	add_child(main)
	await get_tree().process_frame
	Game.clock = 720.0
	main.show_screen("showroom")
	await get_tree().create_timer(8.0).timeout
	await RenderingServer.frame_post_draw
	var out := OS.get_cmdline_user_args()[0]
	get_viewport().get_texture().get_image().save_png(out + "/showroom-day.png")
	Game.set_process(false)
	main.set_process(false)
	main.lobby_3d.set_time(1.0, 0.0)
	await get_tree().create_timer(3.0).timeout
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(out + "/showroom-night.png")
	print("showroom capture complete")
	get_tree().quit()
