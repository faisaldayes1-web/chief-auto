extends Node
## Locked visual-comparison shots for the six overhaul screens (claude-faisal/chief).
##   godot --path . res://tests/_visual_shots.tscn -- <out_dir>
## Same fresh-save seed-7 first-day route as _firstday_shot.gd, so before/after frames line up.
## Run with APPDATA pointed at a scratch folder so the real save is untouched; needs rendering (not --headless).
var n := 0
var m: Node
var steps := []
var si := 0
var wait := 0

func _shot(name: String) -> void:
	var out: String = OS.get_cmdline_user_args()[0]
	get_viewport().get_texture().get_image().save_png("%s/%s.png" % [out, name])
	print("visual shot ", name)

func _buyable() -> Array:
	return Game.listings.filter(func(l): return not l.sold and l.buy_now > 0 and l.buy_now < Game.money)

func _process(_d: float) -> void:
	n += 1
	if n == 2:
		seed(7)
		Game.new_game()
		Game.save_game()
		m = load("res://scenes/main.tscn").instantiate()
		add_child(m)
	if n == 30:
		steps = [
			["", func(): m._start_game()],
			["", func(): m._close_overlay(); Game.seen_intro = true; m._intro(); m._show_next_line()],
			["", func():
				for i in 12: m._show_next_line()],
			["lot-exterior", func(): m.show_screen("lot"); m._update_coach()],
			["office-autobidz", func(): m.pc_tab = "auction"; m.show_screen("pc")],
			["", func():
				var ls := _buyable()
				if not ls.is_empty(): m._buy_now(ls[0])],
			["garage-repair", func(): m.show_screen("garage")],
			["showroom-customer", func(): Game.clock = Game.OPEN_MIN + 180; m.show_screen("showroom")],
			["sales-pitch", func():
				if not m.lobby.is_empty(): m._sale_game(m.lobby[0], "pitch")
				else: print("no customers in lobby")],
		]
		wait = 5
	if steps.is_empty():
		return
	wait -= 1
	if wait == 0:
		steps[si][1].call()
		wait = -120
	elif wait == -240:
		if steps[si][0] != "":
			_shot(steps[si][0])
		si += 1
		if si >= steps.size():
			print("visual shots done")
			get_tree().quit()
			return
		wait = 3
