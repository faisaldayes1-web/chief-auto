extends Node
## Fresh-save first-day walkthrough with screenshots: godot res://tests/_firstday_shot.tscn -- out_dir
## Uses the real screens and actions a new player hits: intro, coach, AutoBidz buy, garage repair, showroom.
## Run with APPDATA pointed at a scratch folder so the real save is untouched.
var n := 0
var m: Node
var steps := []
var si := 0
var wait := 0

func _shot(name: String) -> void:
	var out: String = OS.get_cmdline_user_args()[0]
	get_viewport().get_texture().get_image().save_png("%s/%s.png" % [out, name])
	print("shot ", name, " money ", Game.money, " cars ", Game.cars.size(), " tutorial ", Game.tutorial, " sold ", Game.stats.sold)

func _car() -> Dictionary:
	return Game.cars[0] if not Game.cars.is_empty() else {}

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
			["title", func(): pass],
			["start", func(): m._start_game()],
			["intro2", func(): m._close_overlay(); Game.seen_intro = true; m._intro(); m._show_next_line()],
			["intro_end", func():
				for i in 12: m._show_next_line()],
			["lot_coach", func(): m.show_screen("lot"); m._update_coach()],
			["pc", func(): m.pc_tab = "auction"; m.show_screen("pc")],
			["listing", func():
				var ls: Array = Game.listings.filter(func(l): return not l.sold and l.buy_now > 0 and l.buy_now < Game.money)
				print("affordable buy-now listings: ", ls.size(), " of ", Game.listings.size())
				if not ls.is_empty(): m._open_listing(ls[0])],
			["bought", func():
				var ls: Array = Game.listings.filter(func(l): return not l.sold and l.buy_now > 0 and l.buy_now < Game.money)
				if not ls.is_empty(): m._buy_now(ls[0])],
			["garage", func(): m.show_screen("garage")],
			["repaired", func():
				var c := _car()
				if not c.is_empty():
					for p in ["engine", "tires", "body"]:
						if c.parts.has(p): m._repair(c, p, Game.MECHANICS[0])
					print("car value ", Game.value(c), " sale_value ", Game.sale_value(c), " paid ", c.paid, " spent ", c.spent, " sticker ", c.get("sticker", 0))
				m.show_screen("garage")],
			["showroom", func(): Game.clock = Game.OPEN_MIN + 180; m.show_screen("showroom")],
			["customer", func():
				if not m.lobby.is_empty(): m._open_customer(m.lobby[0])
				else: print("no customers in lobby")],
			["marco", func(): m._close_overlay(); m.show_screen("marco")],
			["home", func(): m.show_screen("home")],
		]
		wait = 5
	if steps.is_empty():
		return
	wait -= 1
	if wait == 0:
		steps[si][1].call()
		wait = -120
	elif wait == -240:
		_shot("%02d_%s" % [si + 1, steps[si][0]])
		si += 1
		if si >= steps.size():
			print("firstday done")
			get_tree().quit()
			return
		wait = 3
