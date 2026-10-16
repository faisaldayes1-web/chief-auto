extends Node
## Screenshot tour of every area: godot res://tests/_tour_shot.tscn -- out_dir
## Starts a mid-game save (level 6, flagship-ready money, cars on the lot, staff) and visits each screen.
var n := 0
var m: Node
var steps := []
var si := 0
var wait := 0

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS

func _shot(name: String) -> void:
	var out: String = OS.get_cmdline_user_args()[0]
	get_viewport().get_texture().get_image().save_png("%s/%s.png" % [out, name])
	print("shot ", name)

func _process(_d: float) -> void:
	n += 1
	if n == 2:
		seed(5)
		m = load("res://scenes/main.tscn").instantiate()
		add_child(m)
	if n == 30:
		_shot("01_title")
		Game.new_game()
		Game.seen_intro = true
		Game.tutorial = 99
		Game.level = 6
		Game.money = 180000
		for i in 5:
			var c: Dictionary = Game.make_car(18000 + i * 9000)
			Game.ensure_damage(c)
			c["sticker"] = int(c.get("base", 20000) * 1.25 / 100) * 100
			Game.cars.append(c)
		steps = [
			["home", func(): m.show_screen("home")],
			["lot", func(): m.show_screen("lot")],
			["garage", func(): m.show_screen("garage")],
			["showroom", func(): m.show_screen("showroom")],
			["marco", func(): m.show_screen("marco")],
			["staff", func(): m.show_screen("staff")],
			["pc_auction", func(): m.pc_tab = "auction"; m.show_screen("pc")],
			["pc_desk", func(): m.pc_tab = "desk"; m.show_screen("pc")],
			["pc_showroom", func(): m.pc_tab = "showroom"; m.show_screen("pc")],
			["pc_ads", func(): m.pc_tab = "ads"; m.show_screen("pc")],
			["pc_staff", func(): m.pc_tab = "staff"; m.show_screen("pc")],
			["pc_reviews", func(): m.pc_tab = "reviews"; m.show_screen("pc")],
			["pc_bank", func(): m.pc_tab = "bank"; m.show_screen("pc")],
			["lot_flagship", func(): Game.dealership = 3; m.show_screen("lot")],
			["showroom_flagship", func(): m.show_screen("showroom")],
		]
		wait = 5
	if steps.is_empty():
		return
	wait -= 1
	if wait == 0:
		Game.clock = Game.OPEN_MIN + 60.0 * (1 + si % 8)   # keep the day going; no closing report mid-tour
		steps[si][1].call()
		wait = -150     # let 3D views build and fade in
	elif wait == -300:
		_shot("%02d_%s" % [si + 2, steps[si][0]])
		si += 1
		if si >= steps.size():
			print("tour done")
			get_tree().quit()
			return
		wait = 3
