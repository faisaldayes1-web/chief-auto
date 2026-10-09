extends Control
## Chief Auto prototype: one script drives every screen of the dealership.
## Office PC (auctions + shops) -> Garage -> Showroom walk-ins -> negotiation -> paperwork -> grow.

const LOGO := preload("res://assets/logo.png")
const CASH_ICON := preload("res://assets/icons/cash.png")
const MINUTES_PER_SECOND := 3.5   # game clock speed: a 13-hour day takes about 4 minutes
const MAX_IN_LOBBY := 4

var bg: TextureRect
var dim: ColorRect
var hud: HBoxContainer
var content: MarginContainer
var nav: HBoxContainer
var overlay: Control
var current := ""

# HUD
var hud_money: Label
var hud_day: Label
var hud_clock: Label
var hud_level: Label
var hud_xp: ProgressBar
var hud_rep: Label
var hud_lobby: Label
var hud_rent: Label

# Auction
var auction: Dictionary = {}
var auction_timer := 0.0
var rival_timer := 0.0
var auction_view: Dictionary = {}
var pc_tab := "auction"
var desk_look := false   # Office PC: pulled back to look at (and arrange) the desk

# Garage
var selected_car_id := -1
var mechanic_index := 0
var garage_log := ""
var garage_view: Car3DView
var garage_box: VBoxContainer
var garage_part := ""
var sleeping := false   # true between the closing report and the Sleep button

# Showroom
var lobby: Array = []          # customers standing in the showroom
var lobby_stage: SceneArt
var customer: Dictionary = {}  # customer in the menu right now
var sale: Dictionary = {}      # paperwork state

# Dialogue
var dialogue_queue: Array = []
var dialogue_done: Callable
var closing := false


func _ready() -> void:
	theme = UI.make_theme()
	bg = TextureRect.new()
	bg.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	bg.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(bg)
	dim = ColorRect.new()
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(dim)

	var root := UI.vbox(0)
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(root)
	root.add_child(_build_hud())
	content = MarginContainer.new()
	content.size_flags_vertical = Control.SIZE_EXPAND_FILL
	root.add_child(content)
	root.add_child(_build_nav())

	overlay = Control.new()
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(overlay)

	Game.changed.connect(_refresh_hud)
	_refresh_hud()
	show_screen("title")


func _overlay_open() -> bool:
	return overlay.get_child_count() > 0


func _process(delta: float) -> void:
	if current == "title":
		return
	_tick_auction(delta)
	if _overlay_open() or closing:
		return
	# the clock only runs while nothing is waiting on the player
	Game.clock += delta * MINUTES_PER_SECOND
	_tick_walkins()
	if Game.clock >= Game.CLOSE_MIN:
		Game.clock = Game.CLOSE_MIN
		_close_for_night()
	if Engine.get_process_frames() % 15 == 0:
		_refresh_clock()
		_update_bg_look()


# =====================================================================
# Shell: HUD, nav, backgrounds
# =====================================================================

func _build_hud() -> Control:
	var p := UI.panel(Color(0.03, 0.05, 0.1, 0.92), UI.GOLD_DIM, 10)
	hud = UI.hbox(16)
	p.add_child(hud)
	var logo := TextureRect.new()
	logo.texture = LOGO
	logo.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	logo.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	logo.custom_minimum_size = Vector2(44, 44)
	hud.add_child(logo)
	var nv := UI.vbox(-4)
	nv.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	hud_name = UI.label(Game.dealer_name.to_upper(), 20, UI.GOLD, true)
	nv.add_child(hud_name)
	var sub := UI.label("TEWPORT BEACH", 11, UI.MUTED, true)
	nv.add_child(sub)
	hud.add_child(nv)
	hud.add_child(UI.spacer())
	hud_lobby = UI.label("", 16, UI.BLUE)
	hud.add_child(hud_lobby)
	var dv := UI.vbox(0)
	hud_day = UI.label("", 15, UI.MUTED)
	hud_clock = UI.label("", 17, UI.TEXT, true)
	dv.add_child(hud_day)
	dv.add_child(hud_clock)
	hud.add_child(dv)
	# funds: big cash icon and balance, the number you watch all game
	var cash := UI.panel(Color(0.02, 0.09, 0.05, 0.85), Color(0.37, 0.82, 0.48, 0.6), 4)
	var ch := UI.hbox(8)
	cash.add_child(ch)
	var icon := TextureRect.new()
	icon.texture = CASH_ICON
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.custom_minimum_size = Vector2(62, 48)
	ch.add_child(icon)
	var mv := UI.vbox(-4)
	mv.add_child(UI.label("FUNDS", 11, Color(0.6, 0.85, 0.65), true))
	hud_money = UI.label("", 28, UI.GOOD, true)
	hud_rent = UI.label("", 12, UI.MUTED)
	mv.add_child(hud_money)
	mv.add_child(hud_rent)
	ch.add_child(mv)
	hud.add_child(cash)
	var lv := UI.vbox(2)
	hud_level = UI.label("", 15, UI.TEXT)
	lv.add_child(hud_level)
	hud_xp = UI.bar(0, 100, UI.BLUE, 6)
	hud_xp.custom_minimum_size = Vector2(110, 6)
	lv.add_child(hud_xp)
	hud.add_child(lv)
	hud_rep = UI.label("", 18, UI.GOLD)
	hud.add_child(hud_rep)
	return p


func _refresh_hud() -> void:
	if hud_money == null:
		return
	hud_name.text = Game.dealer_name.to_upper()
	if Game.tutorial_active() and current != "title" and Game.check_tutorial():
		_update_coach.call_deferred()
	var old := hud_money.text
	hud_money.text = Game.money_str(Game.money)
	if old != "" and old != hud_money.text:
		hud_money.pivot_offset = hud_money.size / 2
		var tw := hud_money.create_tween()
		hud_money.scale = Vector2(1.12, 1.12)
		tw.tween_property(hud_money, "scale", Vector2.ONE, 0.35).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	hud_money.add_theme_color_override("font_color", UI.GOOD if Game.money >= 0 else UI.BAD)
	hud_level.text = "Level %d" % Game.level
	hud_xp.max_value = Game.xp_to_next()
	hud_xp.value = Game.xp
	hud_rep.text = "%s %.1f" % [UI.stars(Game.reputation), Game.reputation]
	_refresh_clock()


func _refresh_clock() -> void:
	hud_day.text = Game.date_str()
	hud_clock.text = "%s · %s" % [Game.clock_str(), Game.day_phase()]
	var dl := Game.days_until_bills()
	hud_rent.text = "Rent & bills %s in %d day%s" % [Game.money_str(Game.monthly_bills().total), dl, "" if dl == 1 else "s"]
	hud_rent.add_theme_color_override("font_color", UI.BAD if dl <= 3 else UI.MUTED)
	hud_lobby.text = ("Showroom: %d waiting" % lobby.size()) if lobby.size() > 0 else ""


func _build_nav() -> Control:
	var p := UI.panel(Color(0.03, 0.05, 0.1, 0.92), UI.GOLD_DIM, 8)
	nav = UI.hbox(8)
	nav.alignment = BoxContainer.ALIGNMENT_CENTER
	p.add_child(nav)
	for item in [["Lot", "lot"], ["Office PC", "pc"], ["Garage", "garage"], ["Showroom", "showroom"], ["Marco", "marco"], ["Staff", "staff"], ["Home", "home"]]:
		var b := UI.button(item[0], show_screen.bind(item[1]), 120, 52)
		b.set_meta("screen", item[1])
		b.icon = icon_tex(item[1])
		b.expand_icon = false
		b.add_theme_constant_override("icon_max_width", 22)
		b.add_theme_constant_override("h_separation", 6)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		nav.add_child(b)
	var end := UI.gold_button("Close & sleep", _close_for_night, 160, 52)
	end.icon = icon_tex("sleep")
	end.add_theme_constant_override("icon_max_width", 22)
	end.add_theme_constant_override("h_separation", 6)
	end.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	nav.add_child(end)
	return p


## A background render of the dealership the player owns right now (apartments are the same at every tier).
static func world_tex(key: String) -> Texture2D:
	var suffix := "" if key.begins_with("apartment") else Game.world_suffix()
	return load("res://assets/world/bg_%s%s.jpg" % [key, suffix])


var bg_key := ""


func set_bg(key: String, darkness: float) -> void:
	bg.visible = key != ""
	bg_key = key
	if key != "":
		bg.texture = world_tex(key)
		bg.modulate = Color.WHITE
		if bg.material == null:
			bg.material = WorldLook.new_material()
		_update_bg_look()
	dim.color = Color(0, 0, 0, darkness)


## Day/dusk/night crossfade and the shared grade on the current background (see WorldLook).
func _update_bg_look() -> void:
	if bg_key == "" or bg.material == null:
		return
	var suffix := "" if bg_key.begins_with("apartment") else Game.world_suffix()
	WorldLook.update(bg.material, bg.texture, bg_key + suffix)


func _margins(px: int) -> void:
	for side in ["left", "right", "top", "bottom"]:
		content.add_theme_constant_override("margin_" + side, px)


func show_screen(name: String) -> void:
	if sleeping and name != "home":
		# leaving home without pressing Sleep still starts the new day
		sleeping = false
		closing = false
	current = name
	auction_view = {}
	lobby_stage = null
	UI.clear(content)
	_margins(16)
	hud.get_parent().visible = name != "title"
	nav.get_parent().visible = name != "title"
	match name:
		"title": _screen_title()
		"lot": _screen_lot()
		"pc": _screen_pc()
		"garage": _screen_garage()
		"showroom": _screen_showroom()
		"marco": _screen_marco()
		"staff": _screen_staff()
		"home": _screen_home()
	_refresh_clock()
	if Game.seen_intro or name == "title":
		_update_coach()


func _stage(mode: String) -> SceneArt:
	set_bg("", 0.0)
	_margins(0)
	var s := SceneArt.new()
	s.clip_contents = true
	s.mode = mode
	s.size_flags_vertical = Control.SIZE_EXPAND_FILL
	s.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content.add_child(s)
	return s


# =====================================================================
# Title
# =====================================================================

func _screen_title() -> void:
	set_bg("lot", 0.5)
	var center := CenterContainer.new()
	content.add_child(center)
	var v := UI.vbox(14)
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	center.add_child(v)
	var logo := TextureRect.new()
	logo.texture = LOGO
	logo.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	logo.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	logo.custom_minimum_size = Vector2(380, 420)
	v.add_child(logo)
	var has_save := Game.day > 1 or Game.cars.size() > 0 or Game.seen_intro
	if has_save:
		v.add_child(UI.gold_button("Continue (%s)" % Game.date_str(), _start_game, 320))
		v.add_child(UI.button("New Game", func():
			Game.reset_save()
			_start_game(), 320))
	else:
		v.add_child(UI.gold_button("Start", _start_game, 320))
	v.add_child(UI.button("Leaderboard", _leaderboard, 320))
	var tag := UI.label("Prototype build · %s, Tewport Beach" % Game.dealer_name if has_save else "Prototype build · Tewport Beach", 14, UI.MUTED)
	tag.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(tag)


func _start_game() -> void:
	if not Game.bankrupt.is_empty():
		_closed_down()
		return
	if Game.debug and Game.cars.is_empty():
		Game.seen_intro = true
		if Game.debug_day > 0:
			Game.day = Game.debug_day
		if Game.debug_broke:
			Game.money = -150000
		if Game.debug_level > 0:
			Game.level = Game.debug_level
			Game.money += 50000
		if Game.debug_tier > 0:
			Game.dealership = clampi(Game.debug_tier, 1, 3)
		for l in Game.listings.slice(0, 3):
			Game.add_car(l.car, int(Game.value(l.car) * 0.6))
		lobby.append(Game.make_customer())
		lobby.append(Game.make_customer())
	show_screen(Game.debug_screen if Game.debug_screen != "" else "lot")
	if not Game.seen_intro:
		_name_dealership()
	else:
		_update_coach()


## New game: the player names the dealership, then Marco's welcome, then the first-day coach.
func _name_dealership() -> void:
	var p := _modal(UI.NAVY, 0)
	p.custom_minimum_size = Vector2(560, 0)
	var v := UI.vbox(12)
	p.add_child(v)
	v.add_child(UI.header("Name your dealership"))
	v.add_child(UI.para("This goes on your contracts, your Yolp page and the top of every screen. You can't change it later, so make it count.", 15, UI.MUTED))
	var edit := LineEdit.new()
	edit.text = "Chief Auto"
	edit.max_length = 28
	edit.custom_minimum_size = Vector2(0, 52)
	edit.add_theme_font_size_override("font_size", 24)
	edit.select_all_on_focus = true
	v.add_child(edit)
	var ideas := UI.hbox(8)
	for idea in ["Chief Auto", "Tewport Motors", "Harbour Auto Gallery", "Coastline Cars"]:
		var b := UI.button(idea, func(): edit.text = idea, 0, 36)
		b.add_theme_font_size_override("font_size", 13)
		ideas.add_child(b)
	v.add_child(ideas)
	var go := func(_t := ""):
		var n := edit.text.strip_edges()
		if n.length() < 2:
			toast("Give it a name first.")
			return
		Game.dealer_name = n
		Game.seen_intro = true
		Game.save_game()
		_refresh_hud()
		_close_overlay()
		_intro()
	edit.text_submitted.connect(go)
	v.add_child(UI.gold_button("Open for business", go, 0, 52))
	edit.grab_focus.call_deferred()


func _intro() -> void:
	var m := ["Marco", "CEO & Financial Advisor"]
	play_dialogue([
		m + ["Welcome to %s. I'm Marco. I run the money here, and I watch every dollar." % Game.dealer_name],
		m + ["Win cars at auction on your office PC, fix them in the garage, and sell them to the walk-ins in the showroom."],
		m + ["We're starting small: a gravel lot and a trailer. Rent is %s a month, plus staff and advertising. Bills hit on the 1st, so watch the countdown up top. October is paid." % Game.money_str(Game.dealership_info().rent)],
		m + ["Make money and we move up: a real showroom on the street, then the glass flagship on the harbour. Upgrades are on the PC under ShowroomPro."],
		["Jeff", "Sales Associate", "And I'm Jeff! Your entire sales team. One star, but it's a really shiny star."],
		m + ["We need real salespeople. Amna is a closer and Maruchan works the VIPs. Both are on StaffHire this week, if you can afford them."],
		m + ["We open at 8 and close at 9. Push a customer past their bad-deal line and they storm out. Cut corners on paperwork and we get sued."],
		m + ["First day, so I'll walk you through it. Follow the card in the corner. Skip it if you already know the business."],
	], _update_coach)


# ---------- first-day coach ----------

var coach: PanelContainer
var hud_name: Label


## Shows (or hides) the tutorial card for the current step and lights up the nav button it points at.
func _update_coach() -> void:
	Game.check_tutorial()
	if coach:
		coach.queue_free()
		coach = null
	for b in nav.get_children():
		if b is Button:
			b.modulate = Color.WHITE
	if not Game.tutorial_active() or current == "title":
		return
	var step: Array = Game.TUTORIAL[Game.tutorial]
	coach = UI.panel(Color(0.03, 0.06, 0.12, 0.94), UI.GOLD, 14)
	coach.mouse_filter = Control.MOUSE_FILTER_STOP
	var v := UI.vbox(6)
	coach.add_child(v)
	v.add_child(UI.label("FIRST DAY · STEP %d OF %d" % [Game.tutorial + 1, Game.TUTORIAL.size()], 12, UI.GOLD, true))
	v.add_child(UI.label(step[0], 20, UI.TEXT, true))
	var hint := UI.para(step[1], 14, UI.MUTED)
	hint.custom_minimum_size.x = 330
	v.add_child(hint)
	var row := UI.hbox(8)
	if current != step[2]:
		row.add_child(UI.gold_button("Take me there", show_screen.bind(step[2]), 150, 36))
	row.add_child(UI.spacer())
	var skip := UI.button("Skip tutorial", func():
		Game.tutorial = Game.TUTORIAL.size()
		Game.save_game()
		_update_coach(), 120, 36)
	skip.add_theme_font_size_override("font_size", 13)
	row.add_child(skip)
	v.add_child(row)
	add_child(coach)
	move_child(coach, overlay.get_index())   # below popups and dialogue
	coach.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	coach.position = Vector2(14, size.y - 100 - 230)
	coach.size = Vector2(380, 0)
	coach.reset_size()
	coach.position.y = size.y - 96 - coach.size.y
	for b in nav.get_children():
		if b is Button and b.get_meta("screen", "") == step[2]:
			b.modulate = Color(1.4, 1.25, 0.7)


# =====================================================================
# Lot
# =====================================================================

func _screen_lot() -> void:
	set_bg("lot", 0.0)
	var yard := Control.new()
	yard.mouse_filter = Control.MOUSE_FILTER_PASS
	content.add_child(yard)
	var col := UI.vbox(12)
	col.mouse_filter = Control.MOUSE_FILTER_IGNORE
	content.add_child(col)
	var menu := _menu_panel(Game.dealership_info().name.to_upper(), [
		["tag", "Manage Cars", _manage_cars_popup],
		["chat", "Talk to Customers", show_screen.bind("showroom")],
		["garage", "Repair in Garage", show_screen.bind("garage")],
		["staff", "Hire Staff", show_screen.bind("staff")],
		["upgrades", "Upgrade Dealership", _upgrade_popup],
		["pc", "Go to Office PC", show_screen.bind("pc")],
	])
	col.add_child(menu)
	col.add_child(_lot_summary())
	_park_cars(yard)


## A compact menu like the reference HUD: gold title, then icon rows that act as buttons.
func _menu_panel(title: String, rows: Array, w := 270) -> PanelContainer:
	var p := _glass_panel()
	p.custom_minimum_size = Vector2(w, 0)
	p.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	p.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
	var v := UI.vbox(2)
	p.add_child(v)
	v.add_child(UI.label(title, 20, UI.GOLD, true))
	for r in rows:
		v.add_child(_menu_row(r[0], r[1], r[2], r[3] if r.size() > 3 else ""))
	return p


func _menu_row(icon: String, text: String, cb: Variant, right := "") -> Control:
	var b := Button.new()
	b.focus_mode = Control.FOCUS_NONE
	b.custom_minimum_size = Vector2(0, 34)
	b.add_theme_stylebox_override("normal", UI.box(Color.TRANSPARENT, Color.TRANSPARENT, 4, 0, 6))
	b.add_theme_stylebox_override("hover", UI.box(Color(UI.GOLD, 0.16), Color(UI.GOLD, 0.5), 4, 1, 6))
	b.add_theme_stylebox_override("pressed", UI.box(Color(UI.GOLD, 0.3), UI.GOLD, 4, 1, 6))
	b.add_theme_stylebox_override("disabled", UI.box(Color.TRANSPARENT, Color.TRANSPARENT, 4, 0, 6))
	if cb is Callable:
		b.pressed.connect(cb)
	else:
		b.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var r := UI.hbox(10)
	r.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	r.offset_left = 6
	r.offset_right = -8
	r.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(r)
	var ic := _icon(icon, 20, UI.TEXT)
	ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	r.add_child(ic)
	var l := UI.label(text, 15, UI.TEXT)
	l.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	r.add_child(l)
	if right != "":
		var rl := UI.label(right, 15, UI.TEXT)
		rl.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		r.add_child(rl)
	return b


## "LOT (3 / 7 CARS)": what's parked, by class, and what it's worth.
func _lot_summary() -> PanelContainer:
	var rows := []
	var counts := {}
	var total := 0
	for car in Game.cars:
		counts[car.cls] = counts.get(car.cls, 0) + 1
		total += int(car.get("sticker", Game.sale_value(car)))
	for c in ["economy", "suv", "truck", "sport", "exotic"]:
		if counts.has(c):
			rows.append(["truck" if c in ["truck", "suv"] else "car_side", _class_name(c), null, str(counts[c])])
	if Game.cars.is_empty():
		rows.append(["gavel", "Empty: buy one at AutoBidz", show_screen.bind("pc")])
	else:
		rows.append(["money", "Total sticker value", null, Game.money_str(total)])
	var hot := _class_name(Game.hot_class)
	rows.append(["insights", "%s are hot today (+10%%)" % hot, null])
	return _menu_panel("LOT (%d / %d CARS)" % [Game.cars.size(), Game.lot_capacity()], rows)


func _manage_cars_popup() -> void:
	var c := _modal()
	c.custom_minimum_size = Vector2(560, 0)
	var v := UI.vbox(10)
	c.add_child(v)
	var top := UI.hbox(8)
	top.add_child(_icon("tag", 26))
	top.add_child(UI.label("MANAGE CARS  (%d / %d)" % [Game.cars.size(), Game.lot_capacity()], 24, UI.GOLD, true))
	v.add_child(top)
	var list := UI.vbox(8)
	var sc := UI.scroll(list)
	sc.custom_minimum_size = Vector2(0, min(420, max(1, Game.cars.size()) * 112))
	v.add_child(sc)
	if Game.cars.is_empty():
		list.add_child(UI.para("The lot is empty. Win something at AutoBidz on the Office PC.", 16, UI.MUTED))
	for car in Game.cars:
		list.add_child(_car_card(car))
	v.add_child(UI.button("Close", _close_overlay, 0, 42))


func _upgrade_popup() -> void:
	var c := _modal()
	c.custom_minimum_size = Vector2(480, 0)
	var v := UI.vbox(10)
	c.add_child(v)
	var top := UI.hbox(8)
	top.add_child(_icon("upgrades", 26))
	top.add_child(UI.label("UPGRADE DEALERSHIP", 24, UI.GOLD, true))
	v.add_child(top)
	v.add_child(_dealership_card(false))
	v.add_child(UI.button("Close", _close_overlay, 0, 42))


## Small menu by a parked car: inspect in the garage, details, or set the sticker.
func _car_menu(car: Dictionary, at: Vector2) -> void:
	UI.clear(overlay)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	var catcher := Button.new()
	catcher.flat = true
	catcher.focus_mode = Control.FOCUS_NONE
	catcher.set_anchors_preset(Control.PRESET_FULL_RECT)
	for st in ["normal", "hover", "pressed"]:
		catcher.add_theme_stylebox_override(st, StyleBoxEmpty.new())
	catcher.pressed.connect(_close_overlay)
	overlay.add_child(catcher)
	var p := _menu_panel("%d %s" % [car.year, car.model], [
		["garage", "Inspect & repair", func():
			_close_overlay()
			selected_car_id = car.id
			show_screen("garage")],
		["info", "View details", func():
			_close_overlay()
			_car_details(car)],
		["tag", "Set price", func():
			_close_overlay()
			_price_popup(car), Game.money_str(car.get("sticker", 0))],
	], 250)
	overlay.add_child(p)
	p.reset_size()
	var vs := get_viewport_rect().size
	p.position = Vector2(clamp(at.x + 12, 8, vs.x - 262), clamp(at.y - 40, 80, vs.y - 260))


func _car_details(car: Dictionary) -> void:
	var c := _modal()
	var v := UI.vbox(8)
	c.add_child(v)
	v.add_child(UI.label("%d %s" % [car.year, car.model], 24, UI.GOLD, true))
	v.add_child(_car_art(car, Vector2(420, 170)))
	var cond := Game.condition(car)
	_icon_stat(v, "garage", "Condition", "%d%%" % cond, cond)
	v.add_child(UI.label("%s · %s mi" % [_class_name(car.cls), _num(car.miles)], 15, UI.MUTED))
	v.add_child(UI.label("Paid %s · Repairs %s · Sticker %s" % [Game.money_str(car.paid), Game.money_str(car.spent), Game.money_str(car.get("sticker", 0))], 15, UI.TEXT))
	v.add_child(UI.label("Marco's fair price: %s" % Game.money_str(Game.sale_value(car)), 15, UI.BLUE))
	v.add_child(UI.button("Close", _close_overlay, 0, 42))


## The cars you own, parked nose-out in the stalls painted on the lot render, with yellow price stickers on the
## windshields (click one to price it). Stall positions come from the render's camera (see _lot_stalls).
func _park_cars(yard: Control) -> void:
	var lot := _lot_stalls()
	var stalls: Array = lot.stalls
	var ref: Dictionary = lot.ref_car
	var items := []
	for i in min(Game.cars.size(), stalls.size()):
		var car: Dictionary = Game.cars[i]
		var b := Button.new()
		b.flat = true
		b.focus_mode = Control.FOCUS_NONE
		b.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
		b.add_theme_stylebox_override("hover", StyleBoxEmpty.new())
		b.add_theme_stylebox_override("pressed", StyleBoxEmpty.new())
		b.pressed.connect(func(): _car_menu(car, b.get_global_mouse_position()))
		b.tooltip_text = "%d %s · click for options" % [car.year, car.model]
		var art := CarArt.new()
		art.quarter = true
		art.set_car(car)
		b.add_child(art)
		# dealer-style windshield price: big yellow numbers with a dark outline, painted at a slight slant
		var tag := UI.label(Game.money_str(car.get("sticker", 0)), 18, Color("ffe14a"), true)
		tag.add_theme_constant_override("outline_size", 7)
		tag.add_theme_color_override("font_outline_color", Color(0.05, 0.04, 0.02, 0.95))
		tag.add_theme_constant_override("shadow_offset_x", 2)
		tag.add_theme_constant_override("shadow_offset_y", 3)
		tag.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.45))
		tag.rotation_degrees = -5.0
		tag.mouse_filter = Control.MOUSE_FILTER_IGNORE
		b.add_child(tag)
		# a longer car keeps its tail at the wheel stop, a taller one is centred higher (the sprites are framed on
		# each car's own length and on 0.42 of its height)
		var dims: Array = lot.cars.get(CarArt.slug(car.get("model", "")), [ref.length, ref.width, ref.height])
		var st: Dictionary = stalls[i]
		var target: Vector2 = _v2(st.target) + _v2(st.fwd) * (dims[0] - ref.length) / 2.0 + _v2(st.up) * 0.42 * (dims[2] - ref.height)
		var frame_w: float = st.ppm * Vector2(1.7 * dims[0], 1.15).length() * 36.0 / 50.0
		# the car's footprint on the ground (centre, half length, half width as image fractions) for its shadow pad
		var pad := []
		if st.has("ground") and st.has("nose"):
			var n0 := _v2(st.nose[0])
			var n1 := _v2(st.nose[1])
			pad = [_v2(st.ground) + _v2(st.fwd) * (dims[0] - ref.length) / 2.0,
				((n0 + n1) / 2.0 - _v2(st.ground)) * dims[0] / ref.length, (n0 - n1) / 2.0 * dims[1] / ref.width]
		items.append({"button": b, "art": art, "tag": tag, "target": target, "frame_w": frame_w, "order": int(st.get("order", i)), "pad": pad})
	# a soft dark pad under every car, drawn before the sprites, so they sit on the asphalt of the render
	var pads := Control.new()
	pads.mouse_filter = Control.MOUSE_FILTER_IGNORE
	pads.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	pads.draw.connect(func():
		var cover := _bg_cover_rect()
		var origin := cover.position - pads.global_position
		for it in items:
			if it.pad.is_empty():
				continue
			var c: Vector2 = origin + it.pad[0] * cover.size
			var ax: Vector2 = it.pad[1] * cover.size
			var ay: Vector2 = it.pad[2] * cover.size
			for k in 5:
				var poly := PackedVector2Array()
				for j in 24:
					var a := TAU * j / 24.0
					poly.append(c + (ax * cos(a) + ay * sin(a)) * (1.3 - k * 0.1))
				pads.draw_colored_polygon(poly, Color(0, 0, 0, 0.11))
			# a tight dark core where the tyres meet the asphalt
			for k in 3:
				var core := PackedVector2Array()
				for j in 24:
					var a := TAU * j / 24.0
					core.append(c + (ax * cos(a) * (0.95 - k * 0.08) + ay * sin(a) * (0.75 - k * 0.12)))
				pads.draw_colored_polygon(core, Color(0, 0, 0, 0.16))
	)
	yard.add_child(pads)
	# a faint mirror image of each car on the asphalt (the same fade as the showroom floor, much weaker)
	for it in items:
		var r := CarArt.new()
		r.quarter = true
		r.set_car(it.art.car)
		r.mouse_filter = Control.MOUSE_FILTER_IGNORE
		r.scale = Vector2(1, -1)
		r.modulate = Color(1, 1, 1, 0.35)
		r.material = _floor_reflection_material()
		it["refl"] = r
		yard.add_child(r)
	# back to front: back row first, and in a row each car's nose overlaps its right-hand neighbour
	var drawn := items.duplicate()
	drawn.sort_custom(func(a, b): return a.order < b.order)
	for it in drawn:
		yard.add_child(it.button)
	var place := func():
		var cover := _bg_cover_rect()
		if cover.size == Vector2.ZERO:
			return
		var origin := cover.position - yard.global_position
		pads.queue_redraw()
		for it in items:
			var w: float = it.frame_w * cover.size.x
			var frame := Rect2(origin + it.target * cover.size - Vector2(w, w * 0.5625) / 2.0, Vector2(w, w * 0.5625))
			# the button covers the car body, not the sprite's empty margins, so clicks go to the car you point at
			var body := Rect2(frame.position + frame.size * Vector2(0.15, 0.22), frame.size * Vector2(0.77, 0.58))
			it.button.position = body.position
			it.button.size = body.size
			it.art.position = frame.position - body.position
			it.art.size = frame.size
			if it.has("refl") and not it.pad.is_empty():
				var gy: float = origin.y + it.pad[0].y * cover.size.y
				it.refl.size = frame.size
				it.refl.position = Vector2(frame.position.x, 2.0 * gy - frame.position.y + frame.size.y * 0.04)
			var tag: Label = it.tag
			tag.add_theme_font_size_override("font_size", clampi(roundi(w * 0.085), 16, 34))
			tag.pivot_offset = tag.get_combined_minimum_size() / 2.0
			tag.reset_size()
			tag.position = frame.position - body.position + frame.size * Vector2(0.52, 0.32) - tag.get_combined_minimum_size() / 2.0
	yard.resized.connect(place)
	place.call_deferred()
	_lot_traffic(yard, lot)


## Now and then a car passes on PCH behind the lot (lanes projected from the render camera by tools/lot_road.py).
func _lot_traffic(yard: Control, lot: Dictionary) -> void:
	var path := "res://assets/world/road_lot%s.json" % Game.world_suffix()
	var res = load(path) if ResourceLoader.exists(path) else null
	if not (res is JSON and res.data is Dictionary):
		return
	var lanes: Array = res.data.get("lanes", []).filter(func(l): return l.size() > 4)
	var models: Array = lot.get("cars", {}).keys()
	if lanes.is_empty() or models.is_empty():
		return
	var road := Control.new()
	road.mouse_filter = Control.MOUSE_FILTER_IGNORE
	road.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	road.clip_contents = true
	yard.add_child(road)
	yard.move_child(road, 0)
	var send := func(again: Callable):
		if not is_instance_valid(road):
			return
		var lane: Array = lanes.pick_random()
		var art := CarArt.new()
		art.quarter = true
		art.set_car({"model": models.pick_random(), "color": Color.from_hsv(randf(), randf_range(0.0, 0.7), randf_range(0.25, 0.95))})
		art.mouse_filter = Control.MOUSE_FILTER_IGNORE
		road.add_child(art)
		var toward: bool = randf() < 0.5
		var at := func(t: float):
			var cover := _bg_cover_rect()
			if not is_instance_valid(art) or cover.size == Vector2.ZERO:
				return
			var f: float = (1.0 - t if toward else t) * (lane.size() - 1)
			var i: int = mini(int(f), lane.size() - 2)
			var a: Array = lane[i]
			var b: Array = lane[i + 1]
			var k: float = f - i
			var p := Vector2(lerpf(a[0], b[0], k), lerpf(a[1], b[1], k))
			var w: float = lerpf(a[2], b[2], k) * 8.07 * 0.72 * cover.size.x
			art.size = Vector2(w, w * 0.5625)
			art.position = cover.position - road.global_position + p * cover.size - Vector2(w * 0.5, w * 0.36)
		var tw := art.create_tween()
		tw.tween_method(at, 0.0, 1.0, randf_range(5.0, 8.0))
		tw.tween_callback(art.queue_free)
		road.get_tree().create_timer(randf_range(7.0, 16.0)).timeout.connect(again.bind(again))
	road.get_tree().create_timer(randf_range(1.0, 4.0)).timeout.connect(send.bind(send))


static func _v2(a: Array) -> Vector2:
	return Vector2(a[0], a[1])


## Where the background render is drawn, in global coordinates (bg covers the window, centred and cropped).
func _bg_cover_rect() -> Rect2:
	if bg.texture == null:
		return Rect2()
	var ts := bg.texture.get_size()
	var sc: float = max(bg.size.x / ts.x, bg.size.y / ts.y)
	return Rect2(bg.global_position + (bg.size - ts * sc) / 2.0, ts * sc)


var _stall_cache := {}


## The stalls of this tier's lot render (assets/world/stalls_lot*.json, written by tools/dealership3d.py with the
## render): per stall, in fill order, the sprite frame centre and size for a reference car as fractions of the image.
func _lot_stalls() -> Dictionary:
	var key := "lot" + Game.world_suffix()
	if not _stall_cache.has(key):
		var path := "res://assets/world/stalls_%s.json" % key
		var res = load(path) if ResourceLoader.exists(path) else null
		var data = res.data if res is JSON else null
		if not (data is Dictionary and data.has("stalls")):
			push_warning("No stall layout at %s, parking cars in a plain row" % path)
			data = {"stalls": [], "cars": {}, "ref_car": {"length": 4.7, "width": 1.85, "height": 1.45}}
			for i in 10:
				data.stalls.append({"target": [0.47 + (i % 5) * 0.11, 0.8 - floori(i / 5.0) * 0.12], "fwd": [0, 0], "up": [0, 0],
					"ppm": 0.034 - floori(i / 5.0) * 0.008, "order": 9 - i})
		_stall_cache[key] = data
	return _stall_cache[key]


func _car_art(car: Dictionary, sz: Vector2) -> CarArt:
	var a := CarArt.new()
	a.custom_minimum_size = sz
	a.set_car(car)
	return a


func _car_card(car: Dictionary) -> Control:
	var p := UI.panel(UI.PANEL_LIGHT, UI.GOLD_DIM, 10)
	var row := UI.hbox(10)
	p.add_child(row)
	row.add_child(_car_art(car, Vector2(130, 56)))
	var v := UI.vbox(3)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(v)
	v.add_child(UI.label("%d %s" % [car.year, car.model], 18, UI.TEXT, true))
	var cond := Game.condition(car)
	v.add_child(UI.label("Condition %d · Sticker %s" % [cond, Game.money_str(car.get("sticker", 0))], 14, UI.cond_color(cond)))
	v.add_child(UI.label("Paid %s · Repairs %s" % [Game.money_str(car.paid), Game.money_str(car.spent)], 13, UI.MUTED))
	var btns := UI.hbox(6)
	btns.add_child(UI.button("Repair", func():
		selected_car_id = car.id
		show_screen("garage"), 0, 34))
	btns.add_child(UI.button("Price", func():
		_price_popup(car), 0, 34))
	v.add_child(btns)
	return p


func _class_name(c: String) -> String:
	return {"economy": "Economy cars", "truck": "Trucks", "suv": "SUVs", "sport": "Sports cars", "exotic": "Exotics"}[c]


# =====================================================================
# Office PC: a desk with a computer. Browser tabs: auctions and shops.
# Every tab is its own website: a brand with a logo (assets/web), a palette and a layout that parodies the real thing.
# =====================================================================

const PC_TABS := [["auction", "AutoBidz"], ["desk", "DeskDepot"], ["showroom", "ShowroomPro"], ["ads", "AdSpace"], ["staff", "StaffHire"], ["reviews", "Yolp"], ["bank", "TewportBank"]]
const PC_URLS := {
	"auction": "https://www.autobidz.ca/live?region=orange-county",
	"desk": "https://www.deskdepot.ca/office",
	"showroom": "https://www.showroompro.ca/upgrades",
	"ads": "https://www.adspace.ca/campaigns",
	"staff": "https://www.staffhire.ca/sales",
	"bank": "https://online.tewportbank.ca/business",
	"reviews": "https://www.yolp.ca/biz/oc-chief-auto-tewport-beach",
}
var auction_house := "autobidz"

## Browser chrome.
const CHROME := Color(0.16, 0.18, 0.22)
const CHROME_TEXT := Color(0.82, 0.85, 0.9)

## Auction lanes inside AutoBidz, each co-branded: header bar and its text, the lane band and its text,
## a lane badge, the logo (assets/web/<logo>_logo.svg) and the colour of the lane's buttons.
const LANES := {
	"autobidz": {"bar": Color("1b1f24"), "bar_ink": Color.WHITE, "band": Color("e0262b"), "ink": Color.WHITE, "badge": "PUBLIC AUCTION", "logo": "autobidz", "btn": Color("e0262b"), "btn_ink": Color.WHITE, "seller": "Private seller · Orange County"},
	"salvage": {"bar": Color("f5c400"), "bar_ink": Color("161616"), "band": Color("161616"), "ink": Color("f5c400"), "badge": "SALVAGE YARD", "logo": "salvage", "btn": Color("161616"), "btn_ink": Color("f5c400"), "seller": "Insurance salvage · sold as-is"},
	"dealer": {"bar": Color("0f2f5a"), "bar_ink": Color.WHITE, "band": Color("1f6fb2"), "ink": Color.WHITE, "badge": "DEALER EXCHANGE", "logo": "mannheim", "btn": Color("1f6fb2"), "btn_ink": Color.WHITE, "seller": "Franchise dealer trade-in"},
	"exotic": {"bar": Color("070707"), "bar_ink": Color("d4a84a"), "band": Color("1c1a14"), "ink": Color("d4a84a"), "badge": "THE VAULT", "logo": "exotic", "btn": Color("d4a84a"), "btn_ink": Color("161206"), "seller": "Collector consignment · Coast Highway"},
}


func _screen_pc() -> void:
	if Game.debug_desk:
		Game.debug_furnish()
	var stage := _stage("desk")
	if desk_look:
		stage.desk_view = true
		_desk_overlay(stage)
		return
	var win := UI.panel(Color(0.93, 0.94, 0.96, 1.0), Color(0.1, 0.1, 0.1), 0)
	win.clip_contents = true
	stage.add_child(win)
	var place := func():
		stage._compute()
		win.position = stage.monitor_rect.position
		win.size = stage.monitor_rect.size
	stage.resized.connect(place)
	# wrapped labels report a tall minimum on their first pass and a Control never shrinks back on its own,
	# so the window is re-fitted to the monitor whenever its minimum size settles
	win.minimum_size_changed.connect(place)
	place.call_deferred()
	var v := UI.vbox(0)
	win.add_child(v)
	# tab strip: dark chrome, rounded tabs with each site's favicon
	var strip := _flat(CHROME, 0, 6)
	var tabs := UI.hbox(2)
	strip.add_child(tabs)
	v.add_child(strip)
	for t in PC_TABS:
		var active: bool = t[0] == pc_tab
		var b := UI.button(t[1], func():
			pc_tab = t[0]
			show_screen("pc"), 0, 30)
		b.add_theme_font_size_override("font_size", 13)
		for st in ["normal", "hover", "pressed"]:
			var sb := UI.box(Color.WHITE if active else (Color.TRANSPARENT if st == "normal" else Color(1, 1, 1, 0.1)), Color.TRANSPARENT, 8, 0, 10)
			sb.corner_radius_bottom_left = 0
			sb.corner_radius_bottom_right = 0
			b.add_theme_stylebox_override(st, sb)
		for c in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color"]:
			b.add_theme_color_override(c, INK if active else CHROME_TEXT)
		b.icon = web_tex(t[1].to_lower() + "_icon")
		b.add_theme_constant_override("icon_max_width", 16)
		b.add_theme_constant_override("h_separation", 6)
		tabs.add_child(b)
	tabs.add_child(UI.label("+", 16, CHROME_TEXT))
	# address bar: a pill with a lock, like any modern browser
	var addr_wrap := _flat(Color.WHITE, 0, 10)
	var ar := UI.hbox(10)
	addr_wrap.add_child(ar)
	for g in ["←", "→", "↻"]:
		ar.add_child(UI.label(g, 15, Color(0.5, 0.52, 0.58)))
	var pill := _flat(Color(0.93, 0.94, 0.96), 15, 10)
	pill.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var ph := UI.hbox(6)
	pill.add_child(ph)
	ph.add_child(_web_img("lock", 12, Color(0.3, 0.55, 0.38)))
	var url: String = PC_URLS[pc_tab]
	if pc_tab == "auction":
		url = "https://www." + Game.auction(auction_house).url
	elif pc_tab == "reviews":
		url = "https://www.yolp.ca/biz/%s-tewport-beach" % Game.dealer_name.to_lower().validate_filename().replace(" ", "-")
	ph.add_child(UI.label(url, 13, Color(0.25, 0.27, 0.32)))
	ar.add_child(pill)
	ar.add_child(UI.label("☆", 15, Color(0.5, 0.52, 0.58)))
	ar.add_child(UI.label("⋮", 15, Color(0.5, 0.52, 0.58)))
	v.add_child(addr_wrap)
	var body := MarginContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(body)
	var inner := UI.vbox(0)
	body.add_child(inner)
	var look := _glass_btn("Look at desk", func():
		desk_look = true
		show_screen("pc"))
	stage.add_child(look)
	var place_look := func():
		look.position = Vector2(stage.size.x - look.size.x - 16, stage.size.y - look.size.y - 14)
	stage.resized.connect(place_look)
	place_look.call_deferred()
	match pc_tab:
		"auction": _tab_auction(inner)
		"desk": _tab_desk(inner)
		"showroom": _tab_showroom_shop(inner)
		"ads": _tab_ads(inner)
		"staff": _tab_staff(inner)
		"bank": _tab_bank(inner)
		"reviews": _tab_reviews(inner)


const INK := Color(0.12, 0.12, 0.16)
const GREY := Color(0.4, 0.4, 0.45)
const WEB_LINE := Color(0.85, 0.86, 0.9)   # card borders on light pages
const WEB_GOOD := Color("1e7e34")
const WEB_BAD := Color("c0392b")
const WEB_LINK := Color("1f6fb2")


## Flat coloured panel for web pages. (UI.panel turns dark colours into smoked glass; the sites keep their own.)
func _flat(bg: Color, radius := 0, pad := 12, border := Color.TRANSPARENT, border_w := 0) -> PanelContainer:
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", UI.box(bg, border, radius, border_w, pad))
	return p


## White card on a light page.
func _web_box() -> PanelContainer:
	return _flat(Color.WHITE, 8, 12, WEB_LINE, 1)


## Brand art: logos, favicons and white line pictograms in assets/web (falls back to assets/icons).
static func web_tex(name: String) -> Texture2D:
	for dir in ["web", "icons"]:
		var p := "res://assets/%s/%s.svg" % [dir, name]
		if ResourceLoader.exists(p):
			return load(p)
	return null


func _web_img(name: String, h: float, tint := Color.WHITE) -> TextureRect:
	var t := TextureRect.new()
	var tex := web_tex(name)
	t.texture = tex
	t.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	t.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	t.custom_minimum_size = Vector2(h * tex.get_width() / tex.get_height() if tex else h, h)
	t.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	t.modulate = tint
	t.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return t


## A website: brand header bar over a page body. Returns {"bar": HBox in the header, "col": the page column, "body": VBox for content}.
func _site(inner: Control, bg: Color, bar_c: Color, logo: String, pad := 12) -> Dictionary:
	var page := _flat(bg, 0, 0)
	page.size_flags_vertical = Control.SIZE_EXPAND_FILL
	inner.add_child(page)
	var col := UI.vbox(0)
	page.add_child(col)
	var head := _flat(bar_c, 0, 14)
	col.add_child(head)
	var bar := UI.hbox(14)
	head.add_child(bar)
	if logo != "":
		bar.add_child(_web_img(logo + "_logo", 30))
	var body_m := MarginContainer.new()
	body_m.size_flags_vertical = Control.SIZE_EXPAND_FILL
	for side in ["left", "right", "top", "bottom"]:
		body_m.add_theme_constant_override("margin_" + side, pad)
	col.add_child(body_m)
	var body := UI.vbox(8)
	body_m.add_child(body)
	return {"bar": bar, "col": col, "body": body}


## Full-width strip between a site's header and its body (nav rows, sale banners, lane bands).
func _site_strip(site: Dictionary, bg: Color, pad := 12) -> HBoxContainer:
	var strip := _flat(bg, 0, pad)
	site.col.add_child(strip)
	site.col.move_child(strip, site.col.get_child_count() - 2)
	var h := UI.hbox(10)
	strip.add_child(h)
	return h


## Decorative search box, the way every site has one: a light field and a coloured button, nothing to click.
func _fake_search(placeholder: String, btn: String, col: Color, ink := Color.WHITE, w := 300) -> Control:
	var h := UI.hbox(0)
	var field := _flat(Color.WHITE, 6, 10, Color(0, 0, 0, 0.12), 1)
	var fsb: StyleBoxFlat = field.get_theme_stylebox("panel")
	fsb.corner_radius_top_right = 0
	fsb.corner_radius_bottom_right = 0
	field.custom_minimum_size.x = w
	var fh := UI.hbox(6)
	field.add_child(fh)
	fh.add_child(_web_img("search", 14, Color(0.55, 0.57, 0.62)))
	fh.add_child(UI.label(placeholder, 12, Color(0.5, 0.52, 0.58)))
	h.add_child(field)
	var b := _flat(col, 6, 12)
	var bsb: StyleBoxFlat = b.get_theme_stylebox("panel")
	bsb.corner_radius_top_left = 0
	bsb.corner_radius_bottom_left = 0
	b.add_child(UI.label(btn, 12, ink, true))
	h.add_child(b)
	return h


## Small rounded label: status, category, badge.
func _pill(text: String, bg: Color, fg: Color, size := 12) -> PanelContainer:
	var p := _flat(bg, 10, 7)
	p.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	p.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	p.add_child(UI.label(text, size, fg, true))
	return p


## Brand-coloured web button. outline = white with a coloured border and coloured text.
func _web_btn(text: String, cb: Callable, col: Color, min_w := 0, min_h := 34, outline := false, ink := Color.WHITE, radius := 6) -> Button:
	var b := UI.button(text, cb, min_w, min_h)
	b.add_theme_font_size_override("font_size", 14)
	var bw := 1 if outline else 0
	b.add_theme_stylebox_override("normal", UI.box(Color.WHITE if outline else col, col, radius, bw, 12))
	b.add_theme_stylebox_override("hover", UI.box(Color(col, 0.1) if outline else col.lightened(0.12), col, radius, bw, 12))
	b.add_theme_stylebox_override("pressed", UI.box(col.darkened(0.2), col, radius, bw, 12))
	b.add_theme_stylebox_override("disabled", UI.box(Color(0.88, 0.89, 0.92), Color.TRANSPARENT, radius, 0, 12))
	for c in ["font_color", "font_hover_color", "font_focus_color"]:
		b.add_theme_color_override(c, col if outline else ink)
	b.add_theme_color_override("font_pressed_color", Color.WHITE)
	b.add_theme_color_override("font_disabled_color", Color(0.55, 0.56, 0.6))
	return b


## Disabled look for buttons on a dark page.
func _dark_btn(b: Button) -> void:
	b.add_theme_stylebox_override("disabled", UI.box(Color(1, 1, 1, 0.07), Color(1, 1, 1, 0.12), 6, 1, 12))
	b.add_theme_color_override("font_disabled_color", Color(0.55, 0.62, 0.65))


# ---------- AutoBidz (and the lanes inside it) ----------

func _tab_auction(inner: Control) -> void:
	var house := Game.auction(auction_house)
	var lane: Dictionary = LANES.get(auction_house, LANES.autobidz)
	var site := _auction_site(inner, house, lane)
	var body: VBoxContainer = site.body
	if not auction_house in Game.memberships:
		body.add_child(_auction_join_card(house, lane))
		return
	var n := 0
	for l in Game.listings:
		if l.get("house", "autobidz") == auction_house:
			n += 1
	var tools := UI.hbox(10)
	tools.add_child(UI.label("%d vehicles in today's lane" % n, 13, INK, true))
	tools.add_child(UI.label("Sort: Ending soonest  ·  View: Grid", 12, GREY))
	tools.add_child(UI.spacer())
	tools.add_child(UI.label("Buy It Now prices are firm unless you make an offer.", 12, GREY))
	body.add_child(tools)
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 10)
	body.add_child(UI.scroll(grid))
	for l in Game.listings:
		if l.get("house", "autobidz") == auction_house:
			grid.add_child(_listing_card(l, lane))
	if n == 0:
		body.add_child(UI.label("New lanes open tomorrow morning.", 15, GREY))


## AutoBidz chrome: a header bar with search, the lane tabs (every auction house is a lane), then a band in the lane's colours.
func _auction_site(inner: Control, house: Dictionary, lane: Dictionary, with_lanes := true) -> Dictionary:
	var site := _site(inner, Color("f3f3f5"), lane.bar, lane.logo, 10)
	var bar: HBoxContainer = site.bar
	bar.add_child(_fake_search("Search %s vehicles" % _num(2400 + Game.listings.size() * 7), "Search", lane.btn, lane.btn_ink, 250))
	bar.add_child(UI.spacer())
	bar.add_child(UI.label("Balance " + Game.money_str(Game.money), 13, lane.bar_ink, true))
	bar.add_child(UI.label("My bids  ·  Watchlist  ·  Help", 12, Color(lane.bar_ink, 0.75)))
	var band := _site_strip(site, lane.band, 12)
	band.add_child(_pill(lane.badge, Color(lane.ink, 0.18), lane.ink))
	band.add_child(UI.label(house.name, 17, lane.ink, true))
	band.add_child(UI.label(house.desc, 13, Color(lane.ink, 0.85)))
	if not with_lanes:
		band.add_child(UI.spacer())
		band.add_child(UI.label("%s  ·  Lot space %d/%d" % [Game.date_str(), Game.cars.size(), Game.lot_capacity()], 12, Color(lane.ink, 0.85)))
		return site
	var lanes := _site_strip(site, Color.WHITE, 8)
	site.col.move_child(lanes.get_parent(), 1)
	lanes.add_theme_constant_override("separation", 4)
	for a in Game.AUCTIONS:
		var on: bool = a.id == auction_house
		var member: bool = a.id in Game.memberships
		var lp: Dictionary = LANES.get(a.id, LANES.autobidz)
		var b := UI.button(a.name, func():
			auction_house = a.id
			show_screen("pc"), 0, 30)
		b.add_theme_font_size_override("font_size", 13)
		for st in ["normal", "hover", "pressed"]:
			var sb := UI.box(lp.band if on else (Color(0.95, 0.95, 0.97) if st == "normal" else Color(0.9, 0.9, 0.93)), lp.band, 6, 0, 10)
			sb.border_width_bottom = 3
			b.add_theme_stylebox_override(st, sb)
		for c in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color"]:
			b.add_theme_color_override(c, lp.ink if on else INK)
		b.icon = web_tex(lp.logo + "_icon") if member else web_tex("lock")
		b.add_theme_constant_override("icon_max_width", 16)
		b.add_theme_constant_override("h_separation", 6)
		if not member:
			for c in ["icon_normal_color", "icon_hover_color", "icon_pressed_color", "icon_focus_color"]:
				b.add_theme_color_override(c, lp.ink if on else GREY)
		lanes.add_child(b)
	lanes.add_child(UI.spacer())
	lanes.add_child(UI.label("%s  ·  Lot space %d/%d" % [Game.date_str(), Game.cars.size(), Game.lot_capacity()], 12, GREY))
	return site


func _auction_join_card(a: Dictionary, lane: Dictionary) -> Control:
	var box := _web_box()
	var h := UI.hbox(16)
	box.add_child(h)
	h.add_child(_web_img(lane.logo + "_mark", 48))
	var v := UI.vbox(6)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(v)
	var top := UI.hbox(10)
	top.add_child(UI.label("Members only", 20, INK, true))
	top.add_child(_pill(lane.badge, lane.band, lane.ink))
	v.add_child(top)
	var perks := {
		"salvage": "Wrecks and floods from 10 to 20 cents on the dollar. Expect extra faults, so a strong mechanic pays for himself.",
		"dealer": "Dealer-only lanes with clean history reports, fewer faults and fewer rival bidders. Buy-now prices around 75% of value.",
		"exotic": "Porshas, Ferranos and Lamborgos from Coast Highway collectors. Big money in, bigger money out.",
	}
	v.add_child(UI.para(perks.get(a.id, a.desc), 14, INK))
	var ok_lvl: bool = Game.level >= a.level
	var ok_rep: bool = Game.reputation >= a.rep
	v.add_child(UI.label("%s  Dealer level %d (you are %d)" % ["✓" if ok_lvl else "✗", a.level, Game.level], 14, WEB_GOOD if ok_lvl else WEB_BAD))
	if a.rep > 0:
		v.add_child(UI.label("%s  Yolp rating %.1f★ (you have %.1f★)" % ["✓" if ok_rep else "✗", a.rep, Game.reputation], 14, WEB_GOOD if ok_rep else WEB_BAD))
	v.add_child(UI.label("Membership fee: %s, one time" % Game.money_str(a.fee), 14, INK, true))
	var join := _web_btn("Join " + a.name, func():
		if not Game.auction_unlocked(a):
			toast("They won't take you yet.")
			return
		if Game.money < a.fee:
			toast("Not enough money.")
			return
		Game.spend(a.fee, "other")
		Game.memberships.append(a.id)
		var used := []
		for l in Game.listings:
			used.append(l)
		Game.generate_listings()
		# keep the lanes you already had today; add only the new house
		var fresh := Game.listings.filter(func(l): return l.get("house", "autobidz") == a.id)
		Game.listings = used + fresh
		Game.save_game()
		toast("Welcome to %s." % a.name)
		show_screen("pc"), lane.btn, 240, 38, false, lane.btn_ink)
	join.disabled = not Game.auction_unlocked(a)
	v.add_child(join)
	return box


## Listing card: photo with the lot number and a time-left badge, title, bid line and the lane-coloured button.
func _listing_card(l: Dictionary, lane: Dictionary) -> Control:
	var car: Dictionary = l.car
	var p := _flat(Color.WHITE, 8, 0, WEB_LINE, 1)
	p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var v := UI.vbox(0)
	p.add_child(v)
	var photo := _flat(Color(0.94, 0.95, 0.97), 8, 8)
	var psb: StyleBoxFlat = photo.get_theme_stylebox("panel")
	psb.corner_radius_bottom_left = 0
	psb.corner_radius_bottom_right = 0
	var pv := UI.vbox(0)
	photo.add_child(pv)
	var tags := UI.hbox(6)
	tags.add_child(UI.label("Lot %05d" % (int(car.get("id", 0)) % 100000), 12, GREY))
	tags.add_child(UI.spacer())
	var live: bool = auction == l
	if l.sold:
		tags.add_child(_pill("WON" if l.winner == "you" else "SOLD", WEB_GOOD if l.winner == "you" else GREY, Color.WHITE))
	else:
		tags.add_child(_pill("LIVE · %ds" % ceil(auction_timer) if live else "Ends today", WEB_BAD if live else Color(0.2, 0.2, 0.25), Color.WHITE))
	pv.add_child(tags)
	pv.add_child(_car_art(car, Vector2(0, 56)))
	v.add_child(photo)
	var m := MarginContainer.new()
	for side in ["left", "right"]:
		m.add_theme_constant_override("margin_" + side, 10)
	m.add_theme_constant_override("margin_top", 6)
	m.add_theme_constant_override("margin_bottom", 10)
	v.add_child(m)
	var tv := UI.vbox(2)
	m.add_child(tv)
	tv.add_child(UI.label("%d %s" % [car.year, car.model], 15, INK, true))
	tv.add_child(UI.label("%s mi · Grade %s · %s" % [_num(car.miles), _grade(Game.condition(car)), _class_name(car.cls).trim_suffix("s")], 12, GREY))
	if l.sold:
		tv.add_child(UI.label(("Won by you · " if l.winner == "you" else "Sold to %s · " % l.winner) + Game.money_str(l.current), 14, WEB_GOOD if l.winner == "you" else GREY, true))
	else:
		var price := UI.hbox(6)
		price.add_child(UI.label(Game.money_str(l.current), 18, INK, true))
		price.add_child(UI.label("current bid" if l.leader != "" else "opening bid", 12, GREY))
		tv.add_child(price)
		tv.add_child(UI.label("Buy It Now " + Game.money_str(l.buy_now) if l.buy_now > 0 else "Auction only · no reserve", 12, WEB_LINK if l.buy_now > 0 else GREY))
	var gap := Control.new()
	gap.custom_minimum_size.y = 4
	tv.add_child(gap)
	tv.add_child(_web_btn("View listing" if l.sold else "Bid now", _open_listing.bind(l), lane.btn, 0, 32, l.sold, lane.btn_ink))
	return p


func _num(n: int) -> String:
	return Game.money_str(n).substr(1)


func _grade(cond: int) -> String:
	# auction-house condition grades
	for g in [[90, "A1"], [80, "A2"], [70, "B1"], [60, "B2"], [45, "C1"]]:
		if cond >= g[0]:
			return g[1]
	return "C2"


func _open_listing(l: Dictionary) -> void:
	_screen_pc_frame_then(func(inner: Control): _listing_detail(inner, l))


## A small smoked-glass button for floating over scene art.
func _glass_btn(text: String, cb: Callable, min_w := 0) -> Button:
	var b := UI.button(text, cb, min_w, 40)
	b.add_theme_font_size_override("font_size", 15)
	for st in ["normal", "hover", "pressed"]:
		var sb := UI.box(Color(0.05, 0.06, 0.08, {"normal": 0.7, "hover": 0.82, "pressed": 0.9}[st]), Color(1, 0.85, 0.6, 0.45), 10, 1, 14)
		b.add_theme_stylebox_override(st, sb)
	return b


## Prop render for a shop item, or null when it has not been rendered.
func _prop_tex(id: String) -> Texture2D:
	var p := "res://assets/props/%s.png" % id
	return load(p) if ResourceLoader.exists(p) else null


## "Look at desk": the browser goes away and the desk shows whole, with a hotspot on every collectible slot.
func _desk_overlay(stage: SceneArt) -> void:
	var spots: Array = []
	for slot in Game.DESK_SLOTS:
		var b := Button.new()
		b.flat = true
		b.focus_mode = Control.FOCUS_NONE
		b.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		b.tooltip_text = Game.DESK_SLOT_NAMES[slot]
		var empty: bool = not Game.desk_slots.has(slot)
		var hover := UI.box(Color(1, 0.85, 0.6, 0.12), Color(1, 0.85, 0.6, 0.8), 12, 2, 0)
		var normal := UI.box(Color(0.05, 0.06, 0.08, 0.25) if empty else Color.TRANSPARENT, Color(1, 0.85, 0.6, 0.55) if empty else Color.TRANSPARENT, 12, 2 if empty else 0, 0)
		b.add_theme_stylebox_override("normal", normal)
		b.add_theme_stylebox_override("hover", hover)
		b.add_theme_stylebox_override("pressed", hover)
		if empty:
			b.text = "+  " + Game.DESK_SLOT_NAMES[slot]
			b.add_theme_font_size_override("font_size", 13)
			b.add_theme_color_override("font_color", Color(1, 0.92, 0.8))
		b.pressed.connect(_desk_picker.bind(stage, slot))
		stage.add_child(b)
		spots.append([slot, b])
	var bar := UI.hbox(10)
	stage.add_child(bar)
	bar.add_child(_glass_btn("‹ Back to PC", func():
		desk_look = false
		show_screen("pc")))
	var hint := _glass_panel()
	var hl := UI.label("My desk · tap a spot to put something there. Desk, chair and monitor come from DeskDepot.", 14, UI.TEXT)
	hint.add_child(hl)
	bar.add_child(hint)
	var place := func():
		stage._compute()
		bar.position = Vector2(16, 14)
		for sp in spots:
			var r: Rect2 = stage.slot_rect(sp[0])
			var empty: bool = not Game.desk_slots.has(sp[0])
			if empty:
				# an empty slot is a dashed-looking tile where the item's base would sit
				var tw: float = max(r.size.x * 0.8, 120.0)
				r = Rect2(r.get_center().x - tw / 2, r.end.y - r.size.y * 0.3, tw, max(r.size.y * 0.26, 40.0))
			else:
				r = r.grow(-r.size.x * 0.12)
			sp[1].position = r.position
			sp[1].size = r.size
	stage.resized.connect(place)
	place.call_deferred()


## Glass picker for one desk slot: every collectible you own (with its picture), plus Clear.
func _desk_picker(stage: SceneArt, slot: String) -> void:
	var old := stage.get_node_or_null("picker")
	if old:
		old.queue_free()
	var dim := ColorRect.new()
	dim.name = "picker"
	dim.color = Color(0, 0, 0, 0.35)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	dim.gui_input.connect(func(e):
		if e is InputEventMouseButton and e.pressed:
			dim.queue_free())
	stage.add_child(dim)
	var p := _glass_panel()
	p.custom_minimum_size = Vector2(640, 0)
	dim.add_child(p)
	var v := UI.vbox(10)
	p.add_child(v)
	var hd := UI.hbox(10)
	hd.add_child(UI.label(Game.DESK_SLOT_NAMES[slot], 20, UI.GOLD, true))
	hd.add_child(UI.spacer())
	var cur: String = Game.desk_slots.get(slot, "")
	var clear := _glass_btn("Clear", func():
		Game.place_decor(slot, "")
		Game.save_game()
		show_screen("pc"))
	clear.disabled = cur == ""
	hd.add_child(clear)
	hd.add_child(_glass_btn("✕", func(): dim.queue_free()))
	v.add_child(hd)
	var grid := GridContainer.new()
	grid.columns = 5
	grid.add_theme_constant_override("h_separation", 8)
	grid.add_theme_constant_override("v_separation", 8)
	var n := 0
	for it in Game.DESK_ITEMS:
		if it.slot != "decor" or not (it.id in Game.owned):
			continue
		n += 1
		var where := ""
		for s in Game.desk_slots:
			if Game.desk_slots[s] == it.id:
				where = s
		var b := Button.new()
		b.custom_minimum_size = Vector2(112, 132)
		b.focus_mode = Control.FOCUS_NONE
		b.tooltip_text = it.name + ("" if where == "" else "  (now: %s)" % Game.DESK_SLOT_NAMES[where])
		var on := where == slot
		for st in ["normal", "hover", "pressed"]:
			var a := 0.08 if st == "normal" else 0.16
			b.add_theme_stylebox_override(st, UI.box(Color(1, 0.9, 0.75, a), UI.GOLD if on else Color(1, 1, 1, 0.15), 10, 2 if on else 1, 6))
		var bv := UI.vbox(2)
		bv.mouse_filter = Control.MOUSE_FILTER_IGNORE
		bv.set_anchors_preset(Control.PRESET_FULL_RECT)
		b.add_child(bv)
		var t := TextureRect.new()
		t.texture = _prop_tex(it.id)
		t.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		t.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		t.custom_minimum_size = Vector2(100, 96)
		t.mouse_filter = Control.MOUSE_FILTER_IGNORE
		bv.add_child(t)
		var l := UI.label(it.name, 11, UI.TEXT)
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		l.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		l.custom_minimum_size.x = 104
		bv.add_child(l)
		b.pressed.connect(func():
			Game.place_decor(slot, it.id)
			Game.save_game()
			show_screen("pc"))
		grid.add_child(b)
	if n == 0:
		v.add_child(UI.para("You don't own any desk collectibles yet. Bobbleheads, frames and more are on DeskDepot under Decor.", 15, UI.MUTED))
	else:
		v.add_child(UI.scroll(grid) if n > 10 else grid)
		if n > 10:
			v.get_child(v.get_child_count() - 1).custom_minimum_size.y = 290
	var centre := func():
		p.position = (dim.size - p.size) / 2
	p.resized.connect(centre)
	dim.resized.connect(centre)
	centre.call_deferred()


func _screen_pc_frame_then(fill: Callable) -> void:
	# Rebuild the PC screen and swap the browser body for a detail page.
	pc_tab = "auction"
	desk_look = false
	show_screen("pc")
	var stage: SceneArt = content.get_child(0)
	var win: PanelContainer = stage.get_child(0)
	var body: MarginContainer = win.get_child(0).get_child(2)
	var inner: VBoxContainer = body.get_child(0)
	UI.clear(inner)
	fill.call(inner)


## Listing page: the lane's chrome, the car's report on the left and an eBay-style bid box on the right.
func _listing_detail(inner: Control, l: Dictionary) -> void:
	auction_view = {}
	var car: Dictionary = l.car
	var house := Game.auction(auction_house)
	var lane: Dictionary = LANES.get(auction_house, LANES.autobidz)
	var site := _auction_site(inner, house, lane, false)
	var body: VBoxContainer = site.body
	var top := UI.hbox(10)
	top.add_child(_web_btn("‹ Back to lane", func(): show_screen("pc"), INK, 0, 30, true))
	top.add_child(UI.label("%d %s" % [car.year, car.model], 20, INK, true))
	top.add_child(UI.label("Lot %05d" % (int(car.get("id", 0)) % 100000), 13, GREY))
	top.add_child(UI.spacer())
	top.add_child(UI.label(lane.seller, 12, GREY))
	body.add_child(top)
	var cols := UI.hbox(12)
	body.add_child(UI.scroll(cols))
	var left := _web_box()
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cols.add_child(left)
	var lv := UI.vbox(3)
	left.add_child(lv)
	var top_row := UI.hbox(12)
	var photo := _flat(Color(0.94, 0.95, 0.97), 6, 6)
	photo.add_child(_car_art(car, Vector2(200, 76)))
	top_row.add_child(photo)
	var facts := UI.vbox(2)
	facts.add_child(UI.label("%s mi" % _num(car.miles), 14, GREY))
	facts.add_child(UI.label(_class_name(car.cls).trim_suffix("s"), 14, GREY))
	facts.add_child(UI.label("Seller grade %s" % _grade(Game.condition(car)), 14, GREY))
	facts.add_child(UI.label("Est. retail %s" % Game.money_str(Game.value(car)), 15, INK, true))
	top_row.add_child(facts)
	lv.add_child(top_row)
	lv.add_child(UI.label("CONDITION REPORT", 12, GREY, true))
	for part in Game.PARTS:
		var row := UI.hbox(8)
		var name_l := UI.label(Game.PART_NAMES[part], 13, INK)
		name_l.custom_minimum_size = Vector2(130, 0)
		row.add_child(name_l)
		row.add_child(UI.bar(car.parts[part], 100, UI.cond_color(car.parts[part]), 8))
		row.add_child(UI.label(str(car.parts[part]), 13, INK))
		lv.add_child(row)
	var hist := UI.vbox(4)
	lv.add_child(hist)
	_fill_history(hist, car)
	var right := _web_box()
	right.custom_minimum_size = Vector2(290, 0)
	cols.add_child(right)
	var rv := UI.vbox(6)
	right.add_child(rv)
	if l.sold:
		rv.add_child(UI.label("Auction closed", 20, INK, true))
		rv.add_child(UI.para("Won by %s for %s" % ["you" if l.winner == "you" else l.winner, Game.money_str(l.current)], 14, GREY))
		return
	var cur := UI.label("", 26, INK, true)
	var lead := UI.label("", 14, GREY)
	var time_l := UI.label("", 14, WEB_BAD)
	var feed := UI.label("", 12, GREY)
	var cur_row := UI.hbox(8)
	cur_row.add_child(UI.label("Current bid", 13, GREY))
	cur_row.add_child(UI.spacer())
	cur_row.add_child(_pill("LIVE" if auction == l else "OPEN", WEB_BAD if auction == l else GREY, Color.WHITE))
	rv.add_child(cur_row)
	rv.add_child(cur)
	rv.add_child(lead)
	rv.add_child(time_l)
	var bid_btn := _web_btn("", _place_bid.bind(l), lane.btn, 0, 42, false, lane.btn_ink, 21)
	bid_btn.add_theme_font_size_override("font_size", 16)
	rv.add_child(bid_btn)
	if l.buy_now > 0:
		rv.add_child(_web_btn("Buy It Now  %s" % Game.money_str(l.buy_now), _buy_now.bind(l), WEB_LINK, 0, 38, true, Color.WHITE, 19))
		if not l.haggled:
			rv.add_child(_web_btn("Make an offer", _haggle.bind(l), GREY, 0, 34, true, Color.WHITE, 17))
	rv.add_child(UI.rule(WEB_LINE))
	rv.add_child(UI.label("BID HISTORY", 12, GREY, true))
	rv.add_child(feed)
	auction_view = {"listing": l, "cur": cur, "lead": lead, "time": time_l, "bid": bid_btn, "feed": feed}
	_refresh_auction_view()


func _fill_history(hist: VBoxContainer, car: Dictionary) -> void:
	UI.clear(hist)
	if car.history_known:
		var col := WEB_GOOD if car.history == "Clean" else WEB_BAD
		hist.add_child(UI.label("History report: %s" % car.history, 14, col, true))
		if car.has("faults_found"):
			var f: Array = car.faults_found
			hist.add_child(UI.para("Inspection: " + ("no hidden problems." if f.is_empty() else "hidden problems in " + ", ".join(f) + "."), 13, INK))
	else:
		var b := _web_btn("Buy history + inspection report ($150)", func():
			if Game.spend(150, "repairs"):
				car.history_known = true
				car.faults_found = Game.reveal_faults(car)
				Game.save_game()
				_fill_history(hist, car)
			else:
				toast("Not enough money."), WEB_LINK, 0, 32, true)
		b.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		hist.add_child(b)


func bid_increment(l: Dictionary) -> int:
	return max(100, int(round(Game.value(l.car) * 0.03 / 100.0)) * 100)


func _place_bid(l: Dictionary) -> void:
	if Game.cars.size() >= Game.lot_capacity():
		toast("Your lot is full. Sell a car first, or expand the lot at ShowroomPro.")
		return
	if not auction.is_empty() and auction != l:
		toast("You're already bidding on the %s. One lane at a time." % auction.car.model)
		return
	var next: int = l.current + (bid_increment(l) if l.leader != "" else 0)
	if next > Game.money:
		toast("You can't cover that bid.")
		return
	l.current = next
	l.leader = "you"
	if auction != l:
		auction = l
		auction_timer = 12.0
		rival_timer = randf_range(1.0, 2.0)
	auction_timer = max(auction_timer, 5.0)
	_auction_note("You bid %s" % Game.money_str(l.current))
	_refresh_auction_view()


func _tick_auction(delta: float) -> void:
	if auction.is_empty():
		return
	auction_timer -= delta
	rival_timer -= delta
	if rival_timer <= 0:
		rival_timer = randf_range(0.8, 2.2)
		var inc := bid_increment(auction)
		if auction.leader != auction.rival and auction.current + inc <= auction.rival_max:
			auction.current += inc if auction.leader != "" else 0
			auction.leader = auction.rival
			auction_timer = max(auction_timer, 4.0)
			_auction_note("%s bids %s" % [auction.rival, Game.money_str(auction.current)])
	if auction_timer <= 0:
		_finish_auction()
	else:
		_refresh_auction_view()


func _auction_note(text: String) -> void:
	if not auction.has("feed_log"):
		auction.feed_log = []
	auction.feed_log.push_front(text)
	auction.feed_log = auction.feed_log.slice(0, 3)


func _refresh_auction_view() -> void:
	if auction_view.is_empty() or not is_instance_valid(auction_view.cur):
		return
	var l: Dictionary = auction_view.listing
	auction_view.cur.text = Game.money_str(l.current)
	auction_view.lead.text = "No bids yet" if l.leader == "" else "Leading: " + ("YOU" if l.leader == "you" else l.leader)
	auction_view.time.text = ("Closes in %ds" % ceil(auction_timer)) if auction == l else "Place a bid to start the clock"
	var next: int = l.current + (bid_increment(l) if l.leader != "" else 0)
	auction_view.bid.text = "Bid %s" % Game.money_str(next)
	auction_view.bid.disabled = l.leader == "you"
	auction_view.feed.text = "\n".join(l.get("feed_log", []))


func _finish_auction() -> void:
	var l := auction
	auction = {}
	l.sold = true
	l.winner = l.leader
	if l.winner == "you":
		if Game.cars.size() < Game.lot_capacity() and Game.spend(l.current, "cars"):
			Game.add_car(l.car, l.current)
			toast("You won the %s for %s! It's on your lot." % [l.car.model, Game.money_str(l.current)])
		else:
			l.winner = l.rival
			toast("You couldn't take the %s (no money or no room), so it went to %s." % [l.car.model, l.rival])
	else:
		toast("%s won the %s." % [l.rival, l.car.model])
	Game.save_game()
	if auction_view.get("listing") == l:
		_open_listing(l)


func _buy_now(l: Dictionary) -> void:
	if Game.cars.size() >= Game.lot_capacity():
		toast("Your lot is full. Sell a car first.")
		return
	if not Game.spend(l.buy_now, "cars"):
		toast("Not enough money.")
		return
	if auction == l:
		auction = {}
	l.sold = true
	l.winner = "you"
	l.current = l.buy_now
	Game.add_car(l.car, l.buy_now)
	Game.save_game()
	toast("Bought the %s outright." % l.car.model)
	_open_listing(l)


func _haggle(l: Dictionary) -> void:
	l.haggled = true
	if randf() < 0.5:
		l.buy_now = int(round(l.buy_now * 0.93 / 100.0)) * 100
		toast("Seller: \"Fine. %s, final offer.\"" % Game.money_str(l.buy_now))
	else:
		toast("Seller: \"Price is the price, pal.\"")
	_open_listing(l)


# ---------- shops ----------

## Product card for the shops: a pictogram "photo" with an optional badge, name, blurb, price and the action button.
## pal: card, line, photo, pict, ink, muted, price colours.
func _product_card(name: String, desc: String, pict: String, pal: Dictionary, price: String, btn: Button, badge := "", img := "") -> Control:
	var p := _flat(pal.card, 8, 0, pal.line, 1)
	p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var v := UI.vbox(0)
	p.add_child(v)
	var photo := _flat(pal.photo, 8, 8)
	var sb: StyleBoxFlat = photo.get_theme_stylebox("panel")
	sb.corner_radius_bottom_left = 0
	sb.corner_radius_bottom_right = 0
	var pv := UI.vbox(0)
	photo.add_child(pv)
	var tags := UI.hbox(0)
	tags.custom_minimum_size.y = 22
	tags.add_child(UI.spacer())
	if badge != "":
		tags.add_child(_pill(badge, pal.price, Color.WHITE))
	pv.add_child(tags)
	var tex := _prop_tex(img) if img != "" else null
	if tex:
		# product shot on a soft studio sweep; hover for a bigger look
		sb.content_margin_left = 0
		sb.content_margin_right = 0
		sb.content_margin_bottom = 0
		var g := Gradient.new()
		var c: Color = pal.photo
		g.set_color(0, c.lightened(0.22))
		g.set_color(1, c.darkened(0.12))
		var gt := GradientTexture2D.new()
		gt.gradient = g
		gt.fill = GradientTexture2D.FILL_RADIAL
		gt.fill_from = Vector2(0.5, 0.35)
		gt.fill_to = Vector2(1.1, 1.0)
		var stack := Control.new()
		stack.custom_minimum_size = Vector2(0, 118)
		stack.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var bg := TextureRect.new()
		bg.texture = gt
		bg.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		bg.stretch_mode = TextureRect.STRETCH_SCALE
		bg.set_anchors_preset(Control.PRESET_FULL_RECT)
		stack.add_child(bg)
		var t := TextureRect.new()
		t.texture = tex
		t.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		t.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		t.set_anchors_preset(Control.PRESET_FULL_RECT)
		t.offset_top = -14
		t.offset_bottom = -2
		stack.add_child(t)
		pv.add_child(stack)
		pv.remove_child(tags)
		tags.set_anchors_preset(Control.PRESET_TOP_WIDE)
		tags.offset_left = 6
		tags.offset_right = -6
		tags.offset_top = 6
		stack.add_child(tags)
		stack.mouse_filter = Control.MOUSE_FILTER_PASS
		stack.mouse_entered.connect(_show_prop_preview.bind(stack, tex, pal))
		stack.mouse_exited.connect(_hide_prop_preview)
	else:
		var centre := CenterContainer.new()
		centre.add_child(_web_img(pict, 40, pal.pict))
		pv.add_child(centre)
	v.add_child(photo)
	var m := MarginContainer.new()
	for side in ["left", "right"]:
		m.add_theme_constant_override("margin_" + side, 10)
	m.add_theme_constant_override("margin_top", 6)
	m.add_theme_constant_override("margin_bottom", 10)
	v.add_child(m)
	var tv := UI.vbox(2)
	m.add_child(tv)
	tv.add_child(UI.label(name, 14, pal.ink, true))
	tv.add_child(UI.para(desc, 12, pal.muted))
	tv.add_child(UI.label(price, 16, pal.price, true))
	btn.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	tv.add_child(btn)
	return p


var _preview: Control = null


## Bigger product shot floating beside a shop card while the mouse is over its photo.
func _show_prop_preview(over: Control, tex: Texture2D, pal: Dictionary) -> void:
	_hide_prop_preview()
	var p := _flat(pal.card, 12, 10, pal.line, 1)
	var sb: StyleBoxFlat = p.get_theme_stylebox("panel")
	sb.shadow_color = Color(0, 0, 0, 0.35)
	sb.shadow_size = 14
	var t := TextureRect.new()
	t.texture = tex
	t.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	t.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	t.custom_minimum_size = Vector2(240, 240)
	p.add_child(t)
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	t.mouse_filter = Control.MOUSE_FILTER_IGNORE
	p.top_level = true
	p.z_index = 50
	over.add_child(p)
	var r := over.get_global_rect()
	var vp := get_viewport_rect().size
	var x := r.end.x + 8 if r.end.x + 270 < vp.x else r.position.x - 268
	p.global_position = Vector2(x, clamp(r.position.y - 40, 8, vp.y - 270))
	_preview = p


func _hide_prop_preview() -> void:
	if is_instance_valid(_preview):
		_preview.queue_free()
	_preview = null


func _small_btn(text: String, cb: Callable, gold := false) -> Button:
	var b := UI.gold_button(text, cb, 130, 36) if gold else UI.button(text, cb, 130, 36)
	b.add_theme_font_size_override("font_size", 15)
	return b


const DEPOT_RED := Color("cc0000")
const DEPOT_YELLOW := Color("ffd200")
const DEPOT_PAL := {"card": Color.WHITE, "line": Color(0.85, 0.86, 0.9), "photo": Color(0.955, 0.955, 0.965), "pict": Color(0.33, 0.35, 0.4), "ink": Color(0.12, 0.12, 0.16), "muted": Color(0.4, 0.4, 0.45), "price": Color("cc0000")}
const DESK_PICTS := {"desk": "desk", "chair": "chair", "monitor": "monitor", "plant": "plant", "mug": "mug", "modelcar": "car_side", "trophy": "trophy", "neon": "neon", "aquarium": "fish"}


func _tab_desk(inner: Control) -> void:
	var site := _site(inner, Color("f4f4f4"), DEPOT_RED, "deskdepot", 10)
	var bar: HBoxContainer = site.bar
	bar.add_child(_fake_search("Search desks, chairs, monitors…", "Search", DEPOT_YELLOW, INK, 270))
	bar.add_child(UI.spacer())
	bar.add_child(UI.label("Deliver to: " + Game.dealer_name, 12, Color(1, 1, 1, 0.85)))
	bar.add_child(UI.label("Balance " + Game.money_str(Game.money), 13, Color.WHITE, true))
	var cart := UI.hbox(4)
	cart.add_child(_web_img("cart", 18))
	cart.add_child(UI.label("Cart (0)", 12, Color.WHITE))
	bar.add_child(cart)
	var nav := _site_strip(site, Color.WHITE, 10)
	nav.add_theme_constant_override("separation", 16)
	for n in ["Desks", "Chairs", "Monitors", "Decor", "Weekly Ad", "Services"]:
		nav.add_child(UI.label(n, 13, INK))
	nav.add_child(UI.label("Deals", 13, DEPOT_RED, true))
	nav.add_child(UI.spacer())
	nav.add_child(UI.label("Free next-day delivery to Tewport Beach", 12, GREY))
	var sale := _site_strip(site, DEPOT_YELLOW, 10)
	sale.add_child(UI.label("BACK TO BUSINESS SALE", 13, INK, true))
	sale.add_child(UI.label("Make the office yours. Changes show on your desk right away, and bigger monitors show more auction listings.", 12, Color(0.3, 0.24, 0.05)))
	var list := UI.vbox(8)
	site.body.add_child(UI.scroll(list))
	var slots := {"decor": "Desk collectibles", "desk": "Desks", "chair": "Chairs", "monitor": "Monitors"}
	for slot in slots:
		var hd := UI.hbox(10)
		hd.add_child(UI.label(slots[slot], 16, INK, true))
		hd.add_child(UI.label("Shop all ›", 12, WEB_LINK))
		list.add_child(hd)
		var grid := GridContainer.new()
		grid.columns = 4
		grid.add_theme_constant_override("h_separation", 8)
		grid.add_theme_constant_override("v_separation", 8)
		grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		list.add_child(grid)
		for it in Game.DESK_ITEMS:
			if it.slot != slot:
				continue
			var owned: bool = it.id in Game.owned
			var btn: Button
			var badge := ""
			if not owned:
				btn = _web_btn("Add to cart", _buy_desk_item.bind(it), DEPOT_RED, 0, 32)
			elif slot == "decor":
				var on: bool = Game.has_decor(it.id)
				badge = "ON DESK" if on else "OWNED"
				btn = _web_btn("Arrange desk", func():
					desk_look = true
					show_screen("pc"), INK, 0, 32, true)
			elif Game.equipped[slot] == it.id:
				badge = "IN USE"
				btn = _web_btn("In use", func(): pass, INK, 0, 32, true)
				btn.disabled = true
			else:
				badge = "OWNED"
				btn = _web_btn("Use", func():
					Game.equipped[slot] = it.id
					Game.save_game()
					show_screen("pc"), INK, 0, 32, true)
			var price: String = "Owned" if owned else (Game.money_str(it.price) if it.price > 0 else "Included")
			grid.add_child(_product_card(it.name, it.desc, DESK_PICTS.get(it.id, DESK_PICTS.get(it.slot, "desk")), DEPOT_PAL, price, btn, badge, it.id))


func _buy_desk_item(it: Dictionary) -> void:
	if not Game.spend(it.price, "shop"):
		toast("Not enough money.")
		return
	Game.owned.append(it.id)
	if it.slot == "decor":
		Game.auto_place(it.id)
		toast("On your desk. Use \"Look at desk\" to move it." if Game.has_decor(it.id) else "Bought. The desk is full: use \"Look at desk\" to swap it in.")
	else:
		Game.equipped[it.slot] = it.id
	if it.slot == "monitor":
		toast("Installed. More auction listings show up from tomorrow.")
	Game.save_game()
	show_screen("pc")


## ShowroomPro: a dark teal B2B catalogue.
const SP_BG := Color("0e1b21")
const SP_BAR := Color("09141a")
const SP_CARD := Color("142830")
const SP_TEAL := Color("22c1b0")
const SP_TEXT := Color("e6f1f3")
const SP_MUTED := Color("8aa3ab")
const SP_PAL := {"card": Color("142830"), "line": Color(1, 1, 1, 0.08), "photo": Color("1b3a44"), "pict": Color("22c1b0"), "ink": Color("e6f1f3"), "muted": Color("8aa3ab"), "price": Color("22c1b0")}
const SP_PICTS := {"coffee": "coffee", "lights": "spotlight", "lounge": "lounge", "turntable": "turntable", "expand1": "lot", "expand2": "lot"}


func _tab_showroom_shop(inner: Control) -> void:
	var site := _site(inner, SP_BG, SP_BAR, "showroompro", 12)
	var bar: HBoxContainer = site.bar
	for n in ["Catalogue", "Installations", "Financing", "Support"]:
		bar.add_child(UI.label(n, 13, SP_TEAL if n == "Catalogue" else SP_MUTED))
	bar.add_child(UI.spacer())
	bar.add_child(UI.label("Account: " + Game.dealer_name, 12, SP_MUTED))
	bar.add_child(UI.label("Balance " + Game.money_str(Game.money), 13, SP_TEXT, true))
	bar.add_child(_pill("B2B · NET 30", Color(SP_TEAL, 0.15), SP_TEAL))
	var hero := _site_strip(site, Color("112229"), 12)
	hero.add_child(UI.label("Dealership fit-outs, installed overnight.", 15, SP_TEXT, true))
	hero.add_child(UI.label("Grow your dealership, then fit it out. Crews from Tewport Beach to the harbour.", 12, SP_MUTED))
	var cols := UI.hbox(12)
	cols.size_flags_vertical = Control.SIZE_EXPAND_FILL
	site.body.add_child(cols)
	var left := UI.vbox(6)
	var left_scroll := UI.scroll(left)
	left_scroll.custom_minimum_size.x = 280
	left_scroll.size_flags_horizontal = Control.SIZE_FILL
	cols.add_child(left_scroll)
	left.add_child(UI.label("YOUR DEALERSHIP", 12, SP_TEAL, true))
	left.add_child(_dealership_card(true))
	var right := UI.vbox(6)
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cols.add_child(right)
	var hd := UI.hbox(10)
	hd.add_child(UI.label("CATALOGUE", 12, SP_TEAL, true))
	hd.add_child(UI.label("%d products · showroom and lot" % Game.SHOWROOM_UPGRADES.size(), 12, SP_MUTED))
	right.add_child(hd)
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 8)
	grid.add_theme_constant_override("v_separation", 8)
	right.add_child(UI.scroll(grid))
	for it in Game.SHOWROOM_UPGRADES:
		var btn: Button
		var badge := ""
		if Game.has_upgrade(it.id):
			badge = "INSTALLED"
			btn = _web_btn("Installed", func(): pass, SP_TEAL, 0, 32)
			btn.disabled = true
		elif Game.dealership < it.get("tier", 1):
			btn = _web_btn("Needs %s" % Game.dealership_info(it.tier).name, func(): pass, SP_TEAL, 0, 32)
			btn.disabled = true
		elif it.has("needs") and not Game.has_upgrade(it.needs):
			btn = _web_btn("Needs first", func(): pass, SP_TEAL, 0, 32)
			btn.disabled = true
		else:
			btn = _web_btn("Request install", func():
				if Game.spend(it.price, "shop"):
					Game.upgrades.append(it.id)
					Game.save_game()
					toast("%s installed." % it.name)
					show_screen("pc")
				else:
					toast("Not enough money."), SP_TEAL, 0, 32, false, Color("06201e"))
		_dark_btn(btn)
		grid.add_child(_product_card(it.name, it.desc, SP_PICTS.get(it.id, "lot"), SP_PAL, Game.money_str(it.price), btn, badge, it.id))


## Current dealership and the next one to buy. web = styled for ShowroomPro's dark page.
func _dealership_card(web: bool) -> Control:
	var ink: Color = SP_TEXT if web else UI.TEXT
	var sub: Color = SP_MUTED if web else UI.MUTED
	var box := _flat(SP_CARD, 8, 12, Color(SP_TEAL, 0.35), 1) if web else UI.panel(Color(0.03, 0.05, 0.1, 0.85), UI.GOLD_DIM, 12)
	var v := UI.vbox(4)
	box.add_child(v)
	var cur := Game.dealership_info()
	var steps := ""
	for i in Game.DEALERSHIPS.size():
		steps += ("■ " if i < Game.dealership else "□ ")
	var top := UI.hbox(8)
	top.add_child(UI.label(cur.name, 19, ink, true))
	top.add_child(UI.label(steps.strip_edges(), 15, SP_TEAL if web else Color("d4a017")))
	v.add_child(top)
	var extra: int = Game.lot_capacity() - cur.cars
	v.add_child(UI.label("%d car spots%s · rent %s a month" % [Game.lot_capacity(), " (%d + %d expansion)" % [cur.cars, extra] if extra > 0 else "", Game.money_str(cur.rent)], 13, sub))
	if Game.dealership >= Game.DEALERSHIPS.size():
		v.add_child(UI.label("You own the flagship on the harbour.", 14, SP_TEAL if web else UI.GOOD, true))
		return box
	var nxt := Game.dealership_info(Game.dealership + 1)
	v.add_child(UI.rule(Color(1, 1, 1, 0.1) if web else UI.GOLD_DIM))
	v.add_child(UI.label("NEXT: " + nxt.name.to_upper(), 14, SP_TEAL if web else UI.GOLD, true))
	var d := UI.para(nxt.desc, 13, sub)
	v.add_child(d)
	v.add_child(UI.label("%d car spots · rent %s a month · needs level %d" % [nxt.cars + extra, Game.money_str(nxt.rent), nxt.level], 13, sub))
	var why := Game.dealership_blocker()
	var move := func():
		if Game.upgrade_dealership():
			toast("Welcome to the %s!" % nxt.name)
			show_screen(current)
		else:
			toast(Game.dealership_blocker())
	var b: Button
	if web:
		b = _web_btn("Move up · %s" % Game.money_str(nxt.price), move, SP_TEAL, 0, 34, false, Color("06201e"))
		_dark_btn(b)
	else:
		b = _small_btn("Move up · %s" % Game.money_str(nxt.price), move, true)
	b.disabled = why != ""
	var row := UI.hbox(8)
	row.add_child(b)
	if why != "":
		row.add_child(UI.label(why, 13, Color("ff8a7a") if web else UI.BAD))
	v.add_child(row)
	return box


## AdSpace: an ad-platform dashboard with a sidebar, KPI tiles and campaign cards.
const ADS_BLUE := Color("1a73e8")
const ADS_BG := Color("f1f3f4")
const ADS_INK := Color("202124")
const ADS_GREY := Color("5f6368")
const ADS_GREEN := Color("1e8e3e")
const ADS_PICTS := {"flyers": "flyer", "insta": "camera", "radio": "radio", "billboard": "billboard"}


func _tab_ads(inner: Control) -> void:
	var site := _site(inner, ADS_BG, Color.WHITE, "adspace", 0)
	var bar: HBoxContainer = site.bar
	bar.add_child(UI.label("Campaigns", 14, ADS_INK))
	bar.add_child(UI.spacer())
	bar.add_child(_pill("+ New campaign", ADS_BLUE, Color.WHITE))
	bar.add_child(UI.label("%s · ID 418-227-9031" % Game.dealer_name, 12, ADS_GREY))
	bar.add_child(UI.label("Balance " + Game.money_str(Game.money), 13, ADS_INK, true))
	var cols := UI.hbox(0)
	cols.size_flags_vertical = Control.SIZE_EXPAND_FILL
	site.body.add_child(cols)
	var side := _flat(Color.WHITE, 0, 8)
	side.custom_minimum_size.x = 150
	cols.add_child(side)
	var sv := UI.vbox(2)
	side.add_child(sv)
	for item in [["home", "Overview"], ["bars", "Campaigns"], ["person", "Audiences"], ["card", "Billing"], ["clock", "Reports"]]:
		var on: bool = item[1] == "Campaigns"
		var row := _flat(Color("e8f0fe") if on else Color.TRANSPARENT, 16, 10)
		var rh := UI.hbox(8)
		row.add_child(rh)
		rh.add_child(_web_img(item[0], 16, ADS_BLUE if on else ADS_GREY))
		rh.add_child(UI.label(item[1], 13, ADS_BLUE if on else ADS_INK))
		sv.add_child(row)
	var main := MarginContainer.new()
	main.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for s in ["left", "right", "top", "bottom"]:
		main.add_theme_constant_override("margin_" + s, 12)
	cols.add_child(main)
	var mv := UI.vbox(8)
	main.add_child(mv)
	var spend := 0
	for a in Game.ADS:
		if a.id in Game.ads_active:
			spend += a.monthly
	var kpis := UI.hbox(8)
	for k in [["Walk-ins expected today", str(Game.walkins_today()), ADS_BLUE], ["Active campaigns", str(Game.ads_active.size()), ADS_GREEN], ["Monthly ad spend", Game.money_str(spend), ADS_INK], ["Next billing", Game.next_bill_date(), ADS_GREY]]:
		var tile := _flat(Color.WHITE, 8, 12, Color(0.86, 0.87, 0.89), 1)
		tile.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var tv := UI.vbox(0)
		tile.add_child(tv)
		tv.add_child(UI.label(k[0], 12, ADS_GREY))
		tv.add_child(UI.label(k[1], 20, k[2], true))
		kpis.add_child(tile)
	mv.add_child(kpis)
	var hd := UI.hbox(10)
	hd.add_child(UI.label("All campaigns", 15, ADS_INK, true))
	hd.add_child(UI.label("Billed monthly on the 1st · the first charge is prorated for the rest of this month", 12, ADS_GREY))
	mv.add_child(hd)
	var list := UI.vbox(6)
	mv.add_child(UI.scroll(list))
	for a in Game.ADS:
		var on: bool = a.id in Game.ads_active
		var btn: Button
		if on:
			btn = _web_btn("Pause", func():
				Game.ads_active.erase(a.id)
				Game.save_game()
				show_screen("pc"), ADS_GREY, 120, 32, true, Color.WHITE, 16)
		else:
			var left: int = Game.days_in_month() - Game.date_dict().day + 1
			var now_cost := int(round(a.monthly * left / float(Game.days_in_month()) / 10.0)) * 10
			btn = _web_btn("Enable · %s" % Game.money_str(now_cost), func():
				if Game.spend(now_cost, "ads"):
					Game.ads_active.append(a.id)
					Game.save_game()
					toast("%s is live. More customers from tomorrow." % a.name)
					show_screen("pc")
				else:
					toast("Not enough money."), ADS_BLUE, 120, 32, false, Color.WHITE, 16)
		list.add_child(_campaign_card(a, on, btn))


func _campaign_card(a: Dictionary, on: bool, btn: Button) -> Control:
	var card := _flat(Color.WHITE, 8, 12, Color(0.86, 0.87, 0.89), 1)
	var h := UI.hbox(12)
	card.add_child(h)
	var ic := _flat(Color("e8f0fe") if on else Color(0.94, 0.95, 0.96), 8, 4 if _prop_tex(a.id) else 8)
	ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var ptex := _prop_tex(a.id)
	if ptex:
		var t := TextureRect.new()
		t.texture = ptex
		t.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		t.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		t.custom_minimum_size = Vector2(96, 96)
		t.mouse_filter = Control.MOUSE_FILTER_PASS
		t.mouse_entered.connect(_show_prop_preview.bind(t, ptex, {"card": Color.WHITE, "line": Color(0.86, 0.87, 0.89)}))
		t.mouse_exited.connect(_hide_prop_preview)
		ic.add_child(t)
	else:
		ic.add_child(_web_img(ADS_PICTS.get(a.id, "flyer"), 26, ADS_BLUE if on else ADS_GREY))
	h.add_child(ic)
	var v := UI.vbox(2)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(v)
	var top := UI.hbox(8)
	top.add_child(UI.label(a.name, 14, ADS_INK, true))
	top.add_child(_pill("● Active" if on else "○ Paused", Color("e6f4ea") if on else Color(0.93, 0.93, 0.94), ADS_GREEN if on else ADS_GREY))
	v.add_child(top)
	v.add_child(UI.label(a.desc + ("  Running." if on else ""), 12, ADS_GREY))
	var reach := UI.hbox(6)
	reach.add_child(UI.label("Reach", 12, ADS_GREY))
	var bar := UI.bar(a.walkins, 5, ADS_BLUE if on else Color(0.7, 0.72, 0.76), 8)
	bar.size_flags_horizontal = Control.SIZE_FILL
	bar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	bar.custom_minimum_size.x = 160
	bar.add_theme_stylebox_override("background", UI.box(Color(0.9, 0.91, 0.93), Color.TRANSPARENT, 4, 0, 0))
	reach.add_child(bar)
	reach.add_child(UI.label("+%d walk-ins / day" % a.walkins, 12, ADS_INK))
	v.add_child(reach)
	var cost := UI.vbox(0)
	cost.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var cl := UI.label(Game.money_str(a.monthly), 16, ADS_INK, true)
	cl.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	cost.add_child(cl)
	var pm := UI.label("per month", 12, ADS_GREY)
	pm.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	cost.add_child(pm)
	h.add_child(cost)
	btn.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	h.add_child(btn)
	return card


func _staff_art(s: Dictionary, sz := Vector2(56, 64)) -> PersonArt:
	var p := PersonArt.new()
	p.custom_minimum_size = sz
	p.pid = Game.staff_pid(s)
	p.mood = 0.6
	return p


func _stars(n: int) -> String:
	return "★".repeat(n) + "☆".repeat(5 - n)


## StaffHire: a job board. Candidates are the existing portrait cards, framed as listings.
const SH_BLUE := Color("2557a7")
const SH_BG := Color("f3f2f1")


func _tab_staff(inner: Control) -> void:
	var site := _site(inner, SH_BG, SH_BLUE, "staffhire", 10)
	var bar: HBoxContainer = site.bar
	for n in ["Find candidates", "Company reviews", "Salaries"]:
		bar.add_child(UI.label(n, 13, Color.WHITE if n == "Find candidates" else Color(1, 1, 1, 0.75)))
	bar.add_child(UI.spacer())
	bar.add_child(UI.label("Employer: " + Game.dealer_name, 12, Color(1, 1, 1, 0.8)))
	bar.add_child(UI.label("Balance " + Game.money_str(Game.money), 13, Color.WHITE, true))
	bar.add_child(_pill("Post a job", Color.WHITE, SH_BLUE))
	var search := _site_strip(site, Color.WHITE, 10)
	for f in [["What", "Salesperson"], ["Where", "Tewport Beach, CA"]]:
		var field := _flat(Color(0.96, 0.96, 0.97), 6, 10, Color(0, 0, 0, 0.15), 1)
		field.custom_minimum_size.x = 210
		var fh := UI.hbox(6)
		field.add_child(fh)
		fh.add_child(UI.label(f[0], 12, GREY))
		fh.add_child(UI.label(f[1], 13, INK))
		search.add_child(field)
	var go := _flat(SH_BLUE, 6, 14)
	go.add_child(UI.label("Find candidates", 13, Color.WHITE, true))
	search.add_child(go)
	search.add_child(UI.spacer())
	search.add_child(UI.label("%d salespeople hired on StaffHire this month" % (37 + Game.day % 20), 12, GREY))
	var filters := _site_strip(site, Color.WHITE, 8)
	filters.add_theme_constant_override("separation", 6)
	for f in ["Full-time", "Sales floor", "Available now", "4★ and up", "Commission", "Within 10 mi"]:
		filters.add_child(_pill(f, Color(0.93, 0.94, 0.96), INK))
	filters.add_child(UI.spacer())
	filters.add_child(UI.label("Sorted by: rating", 12, GREY))
	var col := UI.vbox(8)
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	site.body.add_child(UI.scroll(col))
	var h2 := UI.hbox(10)
	h2.add_child(UI.label("Applicants this week", 16, INK, true))
	h2.add_child(UI.label("%d candidates" % Game.candidates.size(), 12, GREY))
	h2.add_child(UI.spacer())
	h2.add_child(UI.label("Salespeople take walk-ins when you're busy. Better people cost more. Salaries are monthly.", 12, GREY))
	col.add_child(h2)
	var g2 := _card_grid()
	col.add_child(g2)
	for c in Game.candidates:
		g2.add_child(_staff_card(c, true))
	if Game.candidates.is_empty():
		col.add_child(UI.label("No new applicants until Monday.", 13, GREY))
	var h1 := UI.hbox(10)
	h1.add_child(UI.label("Your team", 16, INK, true))
	h1.add_child(UI.label("%d/5 on the sales floor" % Game.staff.size(), 12, GREY))
	col.add_child(h1)
	var g1 := _card_grid()
	col.add_child(g1)
	for s in Game.staff:
		g1.add_child(_staff_card(s, false))
	if Game.level < 3 and Game.reputation < 3.8:
		col.add_child(UI.label("Top-tier closers only apply to dealerships at level 3 or with a 3.8★ Yolp rating.", 12, GREY))


func _card_grid() -> GridContainer:
	var g := GridContainer.new()
	g.columns = 4
	g.add_theme_constant_override("h_separation", 8)
	g.add_theme_constant_override("v_separation", 8)
	g.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return g


const SKILL_COLORS := {"closing": Color("c0392b"), "rapport": Color("e67e22"), "finance": Color("1f6fb2"), "upsell": Color("8e44ad")}


const CARD_BG := Color(0.06, 0.1, 0.14, 0.96)
const CARD_TEXT := Color(0.9, 0.95, 0.98)
const CARD_MUTED := Color(0.55, 0.65, 0.72)
const CARD_CYAN := Color("2fd4e8")


## Portrait window like the team cards: the rendered face over a glowing gradient, framed in the accent colour.
func _portrait_frame(pid: String, mood: float, accent: Color, h := 120.0) -> PanelContainer:
	var frame := PanelContainer.new()
	var sb := UI.box(Color(0.1, 0.2, 0.26), Color(accent, 0.8), 10, 2, 2)
	sb.shadow_color = Color(accent, 0.35)
	sb.shadow_size = 8
	frame.add_theme_stylebox_override("panel", sb)
	frame.custom_minimum_size = Vector2(0, h)
	frame.clip_contents = true
	var glow := GlowBack.new()
	glow.accent = accent
	frame.add_child(glow)
	var tex := _person_tex(pid)
	if tex:
		frame.add_child(_face_rect(pid))
	else:
		var art := PersonArt.new()
		art.pid = pid
		art.mood = mood
		frame.add_child(art)
	return frame


## Radial light behind a portrait.
class GlowBack extends Control:
	var accent := Color.WHITE

	func _ready() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE
		resized.connect(queue_redraw)

	func _draw() -> void:
		var c := Vector2(size.x / 2.0, size.y * 0.42)
		for i in 10:
			var r: float = size.x * 0.75 * (1.0 - i / 10.0)
			draw_circle(c, r, Color(accent, 0.05))
		draw_rect(Rect2(0, size.y * 0.7, size.x, size.y * 0.3), Color(0, 0, 0, 0.18))


## Skill row on a StaffHire card (light page).
func _skill_bar(parent: Control, name: String, val: int, col: Color) -> void:
	var row := UI.hbox(4)
	var nm := UI.label(name, 12, GREY)
	nm.custom_minimum_size.x = 78
	row.add_child(nm)
	var bar := ProgressBar.new()
	bar.max_value = 100
	bar.value = val
	bar.show_percentage = false
	bar.custom_minimum_size = Vector2(0, 7)
	bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	bar.add_theme_stylebox_override("background", UI.box(Color(0.9, 0.91, 0.93), Color.TRANSPARENT, 3, 0, 0))
	bar.add_theme_stylebox_override("fill", UI.box(col, Color.TRANSPARENT, 3, 0, 0))
	row.add_child(bar)
	var vl := UI.label(str(val), 12, INK, true)
	vl.custom_minimum_size.x = 24
	vl.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	row.add_child(vl)
	parent.add_child(row)


## Candidate card on StaffHire: the rendered portrait over a white job-board listing.
func _staff_card(s: Dictionary, applicant: bool) -> Control:
	var accent: Color = UI.GOLD if s.stars >= 4.5 else (CARD_CYAN if not applicant else Color("e04fa0"))
	var box := _flat(Color.WHITE, 8, 10, WEB_LINE, 1)
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var v := UI.vbox(4)
	box.add_child(v)
	v.add_child(_portrait_frame(Game.staff_pid(s), 0.6, accent, 132))
	var nm := UI.hbox(6)
	nm.add_child(UI.label(s.name, 16, INK, true))
	nm.add_child(UI.spacer())
	nm.add_child(UI.label(_stars(s.stars), 13, Color("e39b1c")))
	v.add_child(nm)
	v.add_child(UI.label("Salesperson · Tewport Beach, CA", 12, GREY))
	v.add_child(_pill(s.trait.to_upper(), Color(accent, 0.15), accent.darkened(0.25)))
	v.add_child(UI.label(Game.TRAIT_DESC.get(s.trait, ""), 12, GREY))
	for k in Game.SKILLS:
		_skill_bar(v, Game.SKILL_NAMES[k], Game.skill(s, k), SH_BLUE.lerp(Color("e04fa0"), Game.SKILLS.find(k) / 3.0))
	v.add_child(UI.label("Closes ~%d%% of walk-ins" % int(Game.staff_close_chance(s) * 100), 12, INK))
	v.add_child(UI.label("%s / month" % Game.money_str(s.salary), 15, WEB_GOOD, true))
	if applicant:
		v.add_child(UI.label("Signing fee %s" % Game.money_str(s.get("hire_fee", 0)), 12, GREY))
		v.add_child(_web_btn("Hire now", func():
			if Game.staff.size() >= 5:
				toast("Your sales floor is full (5 people).")
				return
			var fee: int = s.get("hire_fee", 0)
			if Game.money < fee:
				toast("You can't cover the signing fee.")
				return
			Game.spend(fee, "payroll")
			Game.staff.append(s)
			Game.candidates.erase(s)
			Game.save_game()
			toast("%s joins the team. First salary on the 1st." % s.name)
			show_screen("pc"), SH_BLUE, 0, 34))
	elif s.fixed:
		v.add_child(UI.label("%d cars sold" % s.get("sales", 0), 12, GREY))
		var b := _web_btn("Marco says no", func(): pass, GREY, 0, 34, true)
		b.disabled = true
		v.add_child(b)
	else:
		v.add_child(UI.label("%d cars sold" % s.get("sales", 0), 12, GREY))
		v.add_child(_web_btn("Let go", func():
			Game.staff.erase(s)
			Game.save_game()
			toast("%s has left the dealership." % s.name)
			show_screen("pc"), WEB_BAD, 0, 34, true))
	return box


# ---------- Yolp ----------

const YOLP_RED := Color("d32323")


func _tab_reviews(inner: Control) -> void:
	var red := YOLP_RED
	var site := _site(inner, Color("f7f7f7"), red, "yolp", 10)
	var bar: HBoxContainer = site.bar
	var find := UI.hbox(0)
	for f in [["Find", "used car dealers"], ["Near", "Tewport Beach, CA"]]:
		var field := _flat(Color.WHITE, 6, 10, Color(0, 0, 0, 0.12), 1)
		field.custom_minimum_size.x = 170
		var fsb: StyleBoxFlat = field.get_theme_stylebox("panel")
		fsb.corner_radius_top_right = 0
		fsb.corner_radius_bottom_right = 0
		if f[0] == "Near":
			fsb.corner_radius_top_left = 0
			fsb.corner_radius_bottom_left = 0
		var fh := UI.hbox(6)
		field.add_child(fh)
		fh.add_child(UI.label(f[0], 12, GREY))
		fh.add_child(UI.label(f[1], 12, INK))
		find.add_child(field)
	var go := _flat(Color("b11b1b"), 6, 10)
	var gsb: StyleBoxFlat = go.get_theme_stylebox("panel")
	gsb.corner_radius_top_left = 0
	gsb.corner_radius_bottom_left = 0
	go.add_child(_web_img("search", 16))
	find.add_child(go)
	bar.add_child(find)
	bar.add_child(UI.spacer())
	bar.add_child(UI.label("For Businesses", 12, Color(1, 1, 1, 0.85)))
	bar.add_child(_pill("Write a Review", Color.WHITE, red))
	bar.add_child(UI.label("Log In", 12, Color.WHITE))
	var nav := _site_strip(site, Color.WHITE, 8)
	nav.add_theme_constant_override("separation", 18)
	for n in ["Restaurants", "Home Services", "Auto Services", "More ▾"]:
		nav.add_child(UI.label(n, 13, red if n == "Auto Services" else INK))
	var body: VBoxContainer = site.body
	var avg := Game.reputation
	var bh := UI.hbox(12)
	var bv := UI.vbox(2)
	bv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bv.add_child(UI.label(Game.dealer_name, 24, INK, true))
	var rating := UI.hbox(8)
	rating.add_child(UI.label(_stars(int(round(avg))), 20, red))
	rating.add_child(UI.label("%.1f (%d reviews)" % [avg, Game.reviews.size()], 14, INK, true))
	bv.add_child(rating)
	var meta := UI.hbox(6)
	meta.add_child(UI.label("✓ Claimed", 12, WEB_GOOD))
	meta.add_child(UI.label("· $$ · Used Car Dealers, Auto Loan Providers · Tewport Beach", 12, GREY))
	bv.add_child(meta)
	bh.add_child(bv)
	var acts := UI.hbox(6)
	acts.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	acts.add_child(_pill("★ Write a review", red, Color.WHITE, 13))
	for a in ["Add photo", "Share", "Save"]:
		acts.add_child(_pill(a, Color.WHITE, INK, 13))
		var p: PanelContainer = acts.get_child(acts.get_child_count() - 1)
		p.add_theme_stylebox_override("panel", UI.box(Color.WHITE, Color(0, 0, 0, 0.2), 10, 1, 7))
	bh.add_child(acts)
	body.add_child(bh)
	body.add_child(UI.rule(WEB_LINE))
	var cols := UI.hbox(12)
	cols.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(cols)
	var list := UI.vbox(8)
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cols.add_child(UI.scroll(list))
	list.add_child(UI.label("Recommended Reviews", 15, INK, true))
	var shown := Game.reviews.duplicate()
	shown.reverse()
	for r in shown.slice(0, 40):
		list.add_child(_review_card(r, red))
	# business info sidebar
	var side := _web_box()
	side.custom_minimum_size.x = 250
	cols.add_child(side)
	var sv := UI.vbox(4)
	side.add_child(UI.scroll(sv))
	sv.add_child(UI.label("Location & Hours", 14, INK, true))
	var addr := UI.hbox(6)
	addr.add_child(_web_img("pin", 14, red))
	addr.add_child(UI.label("1 Harbour Blvd\nTewport Beach, CA 92661", 12, INK))
	sv.add_child(addr)
	sv.add_child(UI.label("Get directions  ·  (949) 555-0142", 12, WEB_LINK))
	var hrs := "%d:00 AM – %d:00 PM" % [Game.OPEN_MIN / 60, Game.CLOSE_MIN / 60 - 12]
	for d in [["Mon – Fri", hrs], ["Sat", hrs], ["Sun", "Closed"]]:
		var row := UI.hbox()
		row.add_child(UI.label(d[0], 12, GREY))
		row.add_child(UI.spacer())
		row.add_child(UI.label(d[1], 12, INK))
		sv.add_child(row)
	sv.add_child(UI.rule(WEB_LINE))
	sv.add_child(UI.label("Overall rating", 14, INK, true))
	var counts := [0, 0, 0, 0, 0]
	for r in Game.reviews:
		counts[r.stars - 1] += 1
	for st in [5, 4, 3, 2, 1]:
		var row := UI.hbox(4)
		row.add_child(UI.label("%d★" % st, 12, GREY))
		var bar2 := ProgressBar.new()
		bar2.max_value = max(1, Game.reviews.size())
		bar2.value = counts[st - 1]
		bar2.show_percentage = false
		bar2.custom_minimum_size = Vector2(0, 9)
		bar2.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		bar2.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		bar2.add_theme_stylebox_override("background", UI.box(Color(0.9, 0.9, 0.92), Color.TRANSPARENT, 3, 0, 0))
		bar2.add_theme_stylebox_override("fill", UI.box(red, Color.TRANSPARENT, 3, 0, 0))
		row.add_child(bar2)
		row.add_child(UI.label(str(counts[st - 1]), 12, GREY))
		sv.add_child(row)
	sv.add_child(UI.rule(WEB_LINE))
	var help := UI.label("Your rating sets how many people walk in (4★ and up brings one more), whether Cash Whales show up (3.5★), and which auctions will have you. 5★ customers send friends the next day.", 12, GREY)
	help.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	help.custom_minimum_size.x = 210
	sv.add_child(help)
	if Game.referrals > 0:
		sv.add_child(UI.label("%d referral(s) coming in tomorrow" % Game.referrals, 13, WEB_GOOD, true))


func _review_card(r: Dictionary, red: Color) -> Control:
	var box := _web_box()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var h := UI.hbox(10)
	box.add_child(h)
	var av := _flat(Color(0.93, 0.94, 0.96), 22, 0)
	av.custom_minimum_size = Vector2(44, 44)
	av.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
	av.clip_contents = true
	var face := PersonArt.new()
	face.custom_minimum_size = Vector2(44, 44)
	face.pid = r.get("pid", "p00")
	face.mood = (r.stars - 3) * 0.5
	av.add_child(face)
	h.add_child(av)
	var v := UI.vbox(2)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(v)
	var top := UI.hbox(8)
	top.add_child(UI.label(r.name, 14, INK, true))
	top.add_child(UI.label("Tewport Beach, CA · %d friends · %d reviews" % [r.name.length() * 3 % 40 + 2, r.name.length() % 9 + 1], 12, GREY))
	v.add_child(top)
	var sr := UI.hbox(8)
	sr.add_child(UI.label(_stars(r.stars), 14, red))
	sr.add_child(UI.label("Day %d" % r.day if r.day > 0 else "Before you took over", 12, GREY))
	v.add_child(sr)
	var t := UI.label(r.text, 13, INK)
	t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(t)
	v.add_child(UI.label("Useful  ·  Funny  ·  Cool", 12, GREY))
	if r.get("fixed", false):
		v.add_child(UI.label("Owner response: we reached out and made it right.", 12, WEB_GOOD))
	elif r.stars <= 2 and r.day > 0:
		var b := _web_btn("Make it right ($250 gift card)", func():
			if Game.money < 250:
				toast("Not enough money.")
				return
			Game.spend(250, "other")
			r.stars = min(5, r.stars + 2)
			r.fixed = true
			Game._recompute_rep()
			Game.save_game()
			toast("%s bumped their review to %d★." % [r.name, r.stars])
			show_screen("pc"), red, 0, 32, true)
		b.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		v.add_child(b)
	return box


# ---------- TewportBank ----------

const BANK_NAVY := Color("0b2a4a")
const BANK_BG := Color("eef2f6")
const BANK_GOLD := Color("c9a227")


func _tab_bank(inner: Control) -> void:
	var site := _site(inner, BANK_BG, BANK_NAVY, "tewportbank", 12)
	var bar: HBoxContainer = site.bar
	for n in ["Accounts", "Payments", "Credit", "Help"]:
		bar.add_child(UI.label(n, 13, Color.WHITE if n == "Accounts" else Color(1, 1, 1, 0.7)))
	bar.add_child(UI.spacer())
	bar.add_child(UI.label("Welcome, " + Game.dealer_name, 12, Color(1, 1, 1, 0.85)))
	bar.add_child(UI.label("Last login " + Game.date_str(), 12, Color(1, 1, 1, 0.55)))
	bar.add_child(_pill("Sign out", Color(1, 1, 1, 0.12), Color.WHITE))
	var b := Game.monthly_bills()
	var cols := UI.hbox(12)
	cols.size_flags_vertical = Control.SIZE_EXPAND_FILL
	site.body.add_child(cols)
	var left := UI.vbox(10)
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cols.add_child(left)
	# account balance card
	var acct := _flat(BANK_NAVY, 10, 14)
	var av := UI.vbox(2)
	acct.add_child(av)
	var at := UI.hbox(8)
	at.add_child(UI.label("BUSINESS CHEQUING", 12, Color(1, 1, 1, 0.7), true))
	at.add_child(UI.label("···· 4421", 12, Color(1, 1, 1, 0.6)))
	at.add_child(UI.spacer())
	at.add_child(_web_img("shield", 18, BANK_GOLD))
	av.add_child(at)
	av.add_child(UI.label(Game.money_str(Game.money), 30, Color.WHITE, true))
	var al := UI.hbox(10)
	al.add_child(UI.label("Available balance", 12, Color(1, 1, 1, 0.7)))
	al.add_child(UI.label("Next bills %s · %s" % [Game.next_bill_date(), Game.money_str(b.total)], 12, BANK_GOLD.lightened(0.25), true))
	av.add_child(al)
	left.add_child(acct)
	# upcoming payments
	var bills := _web_box()
	var bv := UI.vbox(3)
	bills.add_child(bv)
	var bt := UI.hbox(8)
	bt.add_child(UI.label("UPCOMING PAYMENTS", 12, BANK_NAVY, true))
	bt.add_child(UI.spacer())
	bt.add_child(UI.label("Due " + Game.next_bill_date(), 12, WEB_BAD))
	bv.add_child(bt)
	for row in [["Rent (%s lot)" % Game.dealer_name, b.rent], ["Staff salaries (%d people)" % Game.staff.size(), b.salaries], ["Advertising", b.ads], ["Loan interest", b.interest]]:
		var h := UI.hbox()
		h.add_child(UI.label(row[0], 13, INK))
		h.add_child(UI.spacer())
		h.add_child(UI.label(Game.money_str(row[1]), 13, INK))
		bv.add_child(h)
	bv.add_child(UI.rule(WEB_LINE))
	var tot := UI.hbox()
	tot.add_child(UI.label("Total each month", 14, INK, true))
	tot.add_child(UI.spacer())
	tot.add_child(UI.label(Game.money_str(b.total), 14, INK, true))
	bv.add_child(tot)
	bv.add_child(UI.label("Cars sold: %d · Total profit: %s · Customers who walked out: %d" % [Game.stats.sold, Game.money_str(Game.stats.profit), Game.stats.get("walked", 0)], 12, GREY))
	left.add_child(bills)
	# line of credit
	var right := UI.vbox(10)
	right.custom_minimum_size.x = 330
	cols.add_child(right)
	var lb := _web_box()
	right.add_child(lb)
	var lv := UI.vbox(6)
	lb.add_child(lv)
	var lt := UI.hbox(8)
	lt.add_child(UI.label("BUSINESS LINE OF CREDIT", 12, BANK_NAVY, true))
	lt.add_child(UI.spacer())
	lt.add_child(_pill("%d%% / month" % int(Game.LOAN_RATE * 100), Color(0.93, 0.94, 0.96), GREY))
	lv.add_child(lt)
	var owe := UI.hbox(6)
	owe.add_child(UI.label(Game.money_str(Game.loan), 24, WEB_BAD if Game.loan > 0 else INK, true))
	owe.add_child(UI.label("owed of %s" % Game.money_str(Game.loan_limit()), 13, GREY))
	lv.add_child(owe)
	var meter := UI.bar(Game.loan, max(1, Game.loan_limit()), BANK_GOLD, 10)
	meter.add_theme_stylebox_override("background", UI.box(Color(0.9, 0.91, 0.93), Color.TRANSPARENT, 5, 0, 0))
	lv.add_child(meter)
	var room := Game.loan_limit() - Game.loan
	lv.add_child(UI.label("%s available · interest billed on the 1st" % Game.money_str(room), 12, GREY))
	var borrow := func(amt: int):
		if Game.borrow(amt):
			toast("%s deposited. Spend it on cars that sell." % Game.money_str(amt))
		show_screen("pc")
	var repay := func(amt: int):
		if Game.repay(amt):
			toast("Payment sent.")
		show_screen("pc")
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 6)
	grid.add_theme_constant_override("v_separation", 6)
	var b1 := _web_btn("Borrow $5,000", borrow.bind(5000), BANK_NAVY, 0, 34)
	b1.disabled = room < 5000
	var b2 := _web_btn("Borrow %s" % Game.money_str(room), borrow.bind(room), BANK_NAVY, 0, 34)
	b2.disabled = room <= 0
	var r1 := _web_btn("Repay $5,000", repay.bind(5000), BANK_NAVY, 0, 34, true)
	r1.disabled = Game.loan <= 0 or Game.money < min(5000, Game.loan)
	var r2 := _web_btn("Repay all", repay.bind(Game.loan), BANK_NAVY, 0, 34, true)
	r2.disabled = Game.loan <= 0 or Game.money < Game.loan
	for btn in [b1, b2, r1, r2]:
		btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		grid.add_child(btn)
	lv.add_child(grid)
	# security footer
	var foot := _flat(Color.WHITE, 0, 12)
	site.col.add_child(foot)
	var fh := UI.hbox(8)
	foot.add_child(fh)
	fh.add_child(_web_img("lock", 14, WEB_GOOD))
	fh.add_child(UI.label("Secured with 256-bit encryption", 12, INK))
	fh.add_child(UI.label("·  Member TDIC  ·  Equal Credit Lender  ·  © TewportBank Financial Group, Tewport Beach", 12, GREY))


# =====================================================================
# Garage
# =====================================================================

func _find_car(id: int) -> Dictionary:
	for c in Game.cars:
		if c.id == id:
			return c
	return {}


func _screen_garage() -> void:
	var stage := _stage("garage")
	if Game.cars.is_empty():
		var c := CenterContainer.new()
		c.set_anchors_preset(Control.PRESET_FULL_RECT)
		stage.add_child(c)
		var p := UI.panel()
		c.add_child(p)
		var v0 := UI.vbox(12)
		p.add_child(v0)
		v0.add_child(UI.para("The service bay is empty. Win a car on the Office PC first.", 20))
		v0.add_child(UI.gold_button("Open Office PC", show_screen.bind("pc")))
		return
	if _find_car(selected_car_id).is_empty():
		selected_car_id = Game.cars[0].id
	var car := _find_car(selected_car_id)
	Game.ensure_damage(car)
	garage_view = Car3DView.new()
	stage.add_child(garage_view)
	garage_view.set_car(car)
	garage_view.part_clicked.connect(func(p: String):
		garage_part = p
		_fill_garage_panel())
	var tip := UI.label("", 15, UI.TEXT, true)
	tip.add_theme_constant_override("outline_size", 5)
	tip.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.85))
	tip.mouse_filter = Control.MOUSE_FILTER_IGNORE
	stage.add_child(tip)
	garage_view.part_hovered.connect(func(p: String): tip.text = _garage_part_title(car, p) if p != "" else "")
	var hint := UI.label("Drag to turn the car · scroll to zoom · click any part to inspect and fix it", 14, UI.MUTED)
	hint.mouse_filter = Control.MOUSE_FILTER_IGNORE
	stage.add_child(hint)
	var panel := UI.panel()
	stage.add_child(panel)
	var place := func():
		var w := stage.size.x
		var h := stage.size.y
		garage_view.position = Vector2(0, 0)
		garage_view.size = Vector2(w * 0.6, h)
		tip.position = Vector2(20, 16)
		hint.position = Vector2(20, h - 30)
		panel.position = Vector2(w * 0.6, 10)
		panel.size = Vector2(w * 0.4 - 10, h - 20)
	stage.resized.connect(place)
	place.call_deferred()
	var sc := UI.scroll(UI.vbox(8))
	panel.add_child(sc)
	garage_box = sc.get_child(0)
	garage_part = ""
	_fill_garage_panel()


func _garage_part_title(car: Dictionary, p: String) -> String:
	if Game.PART_NAMES.has(p):
		return "%s · %d/100" % [Game.PART_NAMES[p], car.parts[p]]
	var d: Dictionary = car.damage.get(p, {})
	var name: String = Game.PANEL_NAMES.get(p, p.capitalize())
	if d.is_empty():
		return name + " · no damage"
	var kinds := []
	for k in d:
		kinds.append("broken" if k == "broken" else Game.DAMAGE_KINDS[k].to_lower())
	return name + " · " + ", ".join(kinds)


func _garage_refresh() -> void:
	Game.save_game()
	if garage_view and is_instance_valid(garage_view):
		garage_view.refresh()
	_fill_garage_panel()


func _fill_garage_panel() -> void:
	if garage_box == null or not is_instance_valid(garage_box):
		return
	var v: VBoxContainer = garage_box
	UI.clear(v)
	var car := _find_car(selected_car_id)
	var picker := UI.hbox(6)
	for c in Game.cars:
		var b := UI.button(c.model, func():
			selected_car_id = c.id
			garage_log = ""
			show_screen("garage"), 0, 34)
		b.add_theme_font_size_override("font_size", 14)
		if c.id == selected_car_id:
			b.add_theme_stylebox_override("normal", UI.box(Color(0.3, 0.24, 0.1, 0.95), UI.GOLD, 8, 2, 10))
		picker.add_child(b)
	var ps := ScrollContainer.new()
	ps.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	ps.custom_minimum_size = Vector2(0, 44)
	ps.add_child(picker)
	v.add_child(ps)
	v.add_child(UI.label("%d %s" % [car.year, car.model], 22, UI.GOLD, true))
	v.add_child(UI.para("Condition %d · Value %s · Repairs so far %s · %d damage spots" % [Game.condition(car), Game.money_str(Game.value(car)), Game.money_str(car.spent), Game.damage_count(car)], 14, UI.MUTED))
	if not car.history_known:
		v.add_child(UI.button("Run history + inspection report ($150)", func():
			if Game.spend(150, "repairs"):
				car.history_known = true
				car.faults_found = Game.reveal_faults(car)
				var f: Array = car.faults_found
				garage_log = "History: %s. " % car.history + ("No hidden problems." if f.is_empty() else "Hidden problems in " + ", ".join(f).to_lower() + ".")
				_garage_refresh()
			else:
				toast("Not enough money."), 0, 34))
	else:
		v.add_child(UI.label("History: %s" % car.history, 14, UI.GOOD if car.history == "Clean" else UI.BAD))
	var opt := OptionButton.new()
	opt.custom_minimum_size = Vector2(0, 38)
	for i in Game.MECHANICS.size():
		var m: Dictionary = Game.MECHANICS[i]
		if Game.level >= m.level:
			opt.add_item("%s · +%d-%d · %d%% botch" % [m.name, m.min, m.max, int(m.botch * 100)], i)
		else:
			opt.add_item("%s · Level %d" % [m.name, m.level], i)
			opt.set_item_disabled(opt.get_item_index(i), true)
	if Game.level < Game.MECHANICS[mechanic_index].level:
		mechanic_index = 0
	opt.select(opt.get_item_index(mechanic_index))
	opt.item_selected.connect(func(idx):
		mechanic_index = opt.get_item_id(idx)
		_fill_garage_panel())
	v.add_child(opt)
	var mech: Dictionary = Game.MECHANICS[mechanic_index]
	if garage_log != "":
		v.add_child(UI.para(garage_log, 14, UI.GOOD))
	# ---- the part you clicked
	var card := UI.panel(Color(0.05, 0.08, 0.14, 0.9), UI.GOLD, 10)
	v.add_child(card)
	var cv := UI.vbox(6)
	card.add_child(cv)
	var p := garage_part
	if p == "":
		cv.add_child(UI.label("INSPECT", 14, UI.GOLD, true))
		cv.add_child(UI.para("Click a panel, light, wheel, the glass or the grille on the car. Damaged panels show dents, rust and scratches.", 14, UI.MUTED))
	elif Game.PART_NAMES.has(p):
		cv.add_child(UI.label(Game.PART_NAMES[p].to_upper(), 16, UI.GOLD, true))
		var where := {"engine": "Under the hood", "transmission": "Underneath the car", "interior": "Seats, dash and headliner", "tires": "All four wheels, brakes and rotors", "body": "Every panel"}
		cv.add_child(UI.label(where.get(p, ""), 13, UI.MUTED))
		_system_row(cv, car, p, mech)
	else:
		cv.add_child(UI.label(Game.PANEL_NAMES.get(p, p.capitalize()).to_upper(), 16, UI.GOLD, true))
		var d: Dictionary = car.damage.get(p, {})
		if d.is_empty():
			cv.add_child(UI.label("No damage here.", 14, UI.GOOD))
		for k in d.keys():
			var row := UI.hbox(8)
			var label: String = "Broken lens" if k == "broken" else "%s · %d%%" % [Game.DAMAGE_KINDS[k], int(d[k] * 100)]
			var l := UI.label(label, 15)
			l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			row.add_child(l)
			var cost := Game.panel_fix_cost(car, k, mech)
			var verb: String = {"dent": "Pull dent", "rust": "Cut out rust", "scratch": "Buff out", "broken": "Replace"}[k]
			row.add_child(UI.button("%s %s" % [verb, Game.money_str(cost)], _fix_panel.bind(car, p, k, cost, mech), 0, 34))
			cv.add_child(row)
		if p in Game.PANELS and (d.has("scratch") or d.has("rust")):
			var cost := Game.panel_fix_cost(car, "repaint", mech)
			cv.add_child(UI.button("Repaint this panel %s" % Game.money_str(cost), _fix_panel.bind(car, p, "repaint", cost, mech), 0, 34))
		if p == "hood":
			cv.add_child(UI.rule())
			cv.add_child(UI.label("Under the hood", 13, UI.MUTED))
			_system_row(cv, car, "engine", mech)
	# ---- all systems
	v.add_child(UI.label("ALL SYSTEMS", 14, UI.GOLD, true))
	for part in Game.PARTS:
		_system_row(v, car, part, mech)
	# ---- paint, trim and wheels
	v.add_child(UI.label("PAINT, TRIM & WHEELS", 14, UI.GOLD, true))
	var sw := HFlowContainer.new()
	sw.add_theme_constant_override("h_separation", 6)
	sw.add_theme_constant_override("v_separation", 6)
	var repaint := int(round(car.base * 0.03 / 100.0)) * 100 + 1200
	for col in CarArt.PAINTS:
		var b := Button.new()
		b.custom_minimum_size = Vector2(34, 34)
		b.tooltip_text = "Full respray %s" % Game.money_str(repaint)
		var on: bool = car.get("color", "") == col
		b.add_theme_stylebox_override("normal", UI.box(Color(col), UI.GOLD if on else Color(1, 1, 1, 0.3), 17, 3 if on else 1, 0))
		b.add_theme_stylebox_override("hover", UI.box(Color(col).lightened(0.15), UI.CYAN, 17, 2, 0))
		b.pressed.connect(func():
			if car.get("color", "") == col:
				return
			if not Game.spend(repaint, "repairs"):
				toast("A full respray costs %s." % Game.money_str(repaint))
				return
			car.spent += repaint
			car.color = col
			for pn in car.damage.keys():
				var dd: Dictionary = car.damage[pn]
				dd.erase("scratch")
				dd.erase("rust")
				if dd.is_empty():
					car.damage.erase(pn)
			car.parts.body = min(100, car.parts.body + 8)
			garage_log = "Full respray done. Scratches and surface rust are gone."
			_garage_refresh())
		sw.add_child(b)
	v.add_child(UI.label("Full respray %s (clears scratches and surface rust)" % Game.money_str(repaint), 13, UI.MUTED))
	v.add_child(sw)
	_choice_row(v, "Trim", Game.TRIMS, car.get("trim", "chrome"), 350, func(k):
		car.trim = k
		garage_log = "Trim swapped to %s." % Game.TRIMS[k].to_lower())
	v.add_child(UI.label("Refinished wheels catch the eye: +4 customer interest.", 12, UI.MUTED))
	_choice_row(v, "Wheels", Game.RIMS, car.get("rims", "silver"), 600, func(k):
		car.rims = k
		garage_log = "Wheels refinished in %s." % Game.RIMS[k].to_lower())
	var det_cost := _detail_cost(car)
	var det := UI.button("Detailing %s" % Game.money_str(det_cost) if not car.detailed else "Detailed ✓", func():
		if Game.spend(det_cost, "repairs"):
			car.detailed = true
			car.spent += det_cost
			garage_log = "The detailer made it sparkle. Customers will notice."
			_garage_refresh()
		else:
			toast("Not enough money."), 0, 38)
	det.disabled = car.detailed
	v.add_child(det)


func _system_row(parent: Control, car: Dictionary, part: String, mech: Dictionary) -> void:
	var row := UI.hbox(8)
	var nl := UI.label(Game.PART_NAMES[part], 15)
	nl.custom_minimum_size = Vector2(120, 0)
	row.add_child(nl)
	var val: int = car.parts[part]
	row.add_child(UI.bar(val, 100, UI.cond_color(val), 12))
	var vl := UI.label(str(val), 15, UI.cond_color(val))
	vl.custom_minimum_size = Vector2(32, 0)
	row.add_child(vl)
	var b := UI.button("Fix " + Game.money_str(_repair_cost(car, mech)), _repair.bind(car, part, mech), 116, 34)
	b.add_theme_font_size_override("font_size", 14)
	b.disabled = val >= 100
	row.add_child(b)
	parent.add_child(row)


func _choice_row(parent: Control, title: String, options: Dictionary, current: String, cost: int, apply: Callable) -> void:
	var row := UI.hbox(6)
	var t := UI.label(title, 14)
	t.custom_minimum_size = Vector2(64, 0)
	row.add_child(t)
	for k in options:
		var b := UI.button(options[k], func():
			if k == current:
				return
			if not Game.spend(cost, "repairs"):
				toast("That costs %s." % Game.money_str(cost))
				return
			var car := _find_car(selected_car_id)
			car.spent += cost
			apply.call(k)
			_garage_refresh(), 0, 32)
		b.add_theme_font_size_override("font_size", 13)
		b.tooltip_text = Game.money_str(cost)
		if k == current:
			b.add_theme_stylebox_override("normal", UI.box(Color(0.3, 0.24, 0.1, 0.95), UI.GOLD, 6, 2, 8))
		row.add_child(b)
	parent.add_child(row)


func _fix_panel(car: Dictionary, panel: String, kind: String, cost: int, mech: Dictionary) -> void:
	if not Game.spend(cost, "repairs"):
		toast("Not enough money for that job.")
		return
	car.spent += cost
	var gain := Game.fix_panel(car, panel, kind)
	var name: String = Game.PANEL_NAMES.get(panel, panel)
	if randf() < mech.botch * 0.6:
		# a botched job leaves a little behind
		car.damage[panel] = car.damage.get(panel, {})
		car.damage[panel]["scratch"] = 0.5
		garage_log = "%s botched the %s a bit. Body +%d." % [mech.name, name.to_lower(), gain]
	else:
		garage_log = "%s on the %s is done. Body +%d." % [{"dent": "Dent repair", "rust": "Rust repair", "scratch": "Polishing", "broken": "New light", "repaint": "Respray"}[kind], name.to_lower(), gain]
	car.sticker = max(car.get("sticker", 0), int(round(Game.sale_value(car) * 1.05 / 100.0)) * 100)
	_garage_refresh()


func _repair_cost(car: Dictionary, mech: Dictionary) -> int:
	return max(100, int(round(car.base * mech.cost / 50.0)) * 50)


func _detail_cost(car: Dictionary) -> int:
	return max(150, int(round(car.base * 0.004 / 50.0)) * 50)


func _repair(car: Dictionary, part: String, mech: Dictionary) -> void:
	var cost := _repair_cost(car, mech)
	if not Game.spend(cost, "repairs"):
		toast("Not enough money for that job.")
		return
	car.spent += cost
	var gain := randi_range(mech.min, mech.max)
	var msg := ""
	if car.hidden.has(part) and randf() < mech.find:
		msg = "%s found a hidden problem in the %s and fixed it. " % [mech.name, Game.PART_NAMES[part].to_lower()]
		car.hidden.erase(part)
	car.parts[part] = min(100, car.parts[part] + gain)
	if part == "body":
		Game.clear_some_damage(car, gain)
	if randf() < mech.botch:
		var bad: String = Game.PARTS.pick_random()
		car.hidden[bad] = car.hidden.get(bad, 0) + randi_range(10, 20)
	var lines := {
		"Cousin Ray": ["\"Good as new, cuz. Mostly.\"", "\"I used the good duct tape.\"", "\"Don't worry about that noise.\""],
		"Strip-Mall Auto": ["\"Done. Cash or card?\"", "\"All fixed, boss.\""],
		"Harbor Certified": ["\"Serviced to spec.\"", "\"Torqued and tested.\""],
		"Euro Specialist": ["\"Perfetto.\"", "\"She sings now.\""],
	}
	garage_log = msg + "%s +%d. %s" % [Game.PART_NAMES[part], gain, lines[mech.name].pick_random()]
	car.sticker = max(car.get("sticker", 0), int(round(Game.sale_value(car) * 1.05 / 100.0)) * 100)
	_garage_refresh()


# =====================================================================
# Showroom lobby: cars on podiums, walk-in customers
# =====================================================================

func _screen_showroom() -> void:
	var stage := _stage("lobby")
	lobby_stage = stage
	_build_lobby(stage)


const CLASS_WORDS := {"economy": "a commuter", "suv": "an SUV", "truck": "a truck", "sport": "something sporty", "exotic": "an exotic"}


func _build_lobby(stage: SceneArt) -> void:
	for ch in stage.get_children():
		ch.queue_free()
	var displays := []
	var shown: Array = Game.cars.slice(0, 4)
	# contact shadows under cars and people, drawn on the polished floor before any sprite
	var floor_fx := Control.new()
	floor_fx.mouse_filter = Control.MOUSE_FILTER_IGNORE
	floor_fx.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	stage.add_child(floor_fx)
	for car in shown:
		var box := Control.new()
		stage.add_child(box)
		# a faint mirror image on the polished floor, fading out below the tyres
		var refl := CarArt.new()
		refl.quarter = true
		refl.set_car(car)
		refl.scale = Vector2(1, -1)
		refl.material = _floor_reflection_material()
		refl.mouse_filter = Control.MOUSE_FILTER_IGNORE
		box.add_child(refl)
		var art := _car_art(car, Vector2.ZERO)
		art.quarter = true
		art.set_car(car)
		box.add_child(art)
		var hit := Button.new()
		hit.flat = true
		hit.focus_mode = Control.FOCUS_NONE
		for st in ["normal", "hover", "pressed"]:
			hit.add_theme_stylebox_override(st, StyleBoxEmpty.new())
		hit.tooltip_text = "%d %s · click to set the price" % [car.year, car.model]
		hit.pressed.connect(_price_popup.bind(car))
		box.add_child(hit)
		# dealer-style windshield price, as on the lot
		var tag := UI.label(Game.money_str(car.get("sticker", 0)), 22, Color("ffe14a"), true)
		tag.add_theme_constant_override("outline_size", 7)
		tag.add_theme_color_override("font_outline_color", Color(0.05, 0.04, 0.02, 0.95))
		tag.add_theme_constant_override("shadow_offset_x", 2)
		tag.add_theme_constant_override("shadow_offset_y", 3)
		tag.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.45))
		tag.rotation_degrees = -5.0
		tag.mouse_filter = Control.MOUSE_FILTER_IGNORE
		box.add_child(tag)
		displays.append([box, art, tag, refl, hit])
	var people := []
	for c in lobby:
		var btn := Button.new()
		btn.flat = true
		btn.focus_mode = Control.FOCUS_NONE
		btn.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
		btn.add_theme_stylebox_override("hover", UI.box(Color(1, 1, 1, 0.08), UI.GOLD, 10, 1, 0))
		btn.add_theme_stylebox_override("pressed", StyleBoxEmpty.new())
		btn.pressed.connect(_open_customer.bind(c))
		stage.add_child(btn)
		# customers stand in front of the display cars (the cars sit further back on the floor)
		var p := PersonArt.new()
		p.full_body = true
		p.pid = Game.customer_pid(c)
		p.mood = c.happiness * 2.0 - 1.0
		p.set_anchors_preset(Control.PRESET_FULL_RECT)
		btn.add_child(p)
		var name_tag := UI.label(c.name + "  · tap to help", 14, UI.TEXT, true)
		name_tag.add_theme_constant_override("outline_size", 4)
		name_tag.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.8))
		name_tag.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		btn.add_child(name_tag)
		# speech bubble: who they are and what they want
		var bubble := UI.panel(Color(0.97, 0.97, 0.95, 0.95), Color.TRANSPARENT, 6)
		bubble.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var bv := UI.vbox(0)
		bubble.add_child(bv)
		var badge: String = Game.BUYER_TYPES[c.type].title
		if c.get("referral", false):
			badge = "★ Referral · " + badge
		var badge_col: Color = {"influencer": Color("8e44ad"), "whale": Color("b8860b"), "lowballer": Color("c0392b")}.get(c.type, Color("1f6fb2"))
		bv.add_child(UI.label(badge, 12, badge_col, true))
		bv.add_child(UI.label("Wants: %s · %s" % [CLASS_WORDS.get(c.wants_cls, c.wants_cls), "cash" if not c.finance else "financing"], 11, Color(0.15, 0.15, 0.2)))
		btn.add_child(bubble)
		# patience drains while they wait
		var waited: float = max(0.0, Game.clock - c.arrived)
		var limit := 240.0 if Game.has_upgrade("lounge") else 120.0
		var pat := ProgressBar.new()
		pat.show_percentage = false
		pat.max_value = 1.0
		pat.value = clamp(1.0 - waited / limit, 0.0, 1.0)
		var pcol := UI.GOOD if pat.value > 0.5 else (UI.GOLD if pat.value > 0.25 else UI.BAD)
		pat.add_theme_stylebox_override("background", UI.box(Color(0, 0, 0, 0.6), Color.TRANSPARENT, 3, 0, 0))
		pat.add_theme_stylebox_override("fill", UI.box(pcol, Color.TRANSPARENT, 3, 0, 0))
		pat.mouse_filter = Control.MOUSE_FILTER_IGNORE
		btn.add_child(pat)
		# the name tag and bubble sit above the button's rect; give them their own hit area so
		# "tap to help" actually opens the conversation
		var head_hit := Button.new()
		head_hit.flat = true
		head_hit.focus_mode = Control.FOCUS_NONE
		head_hit.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		for st in ["normal", "hover", "pressed"]:
			head_hit.add_theme_stylebox_override(st, StyleBoxEmpty.new())
		head_hit.pressed.connect(_open_customer.bind(c))
		btn.add_child(head_hit)
		btn.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		people.append([btn, name_tag, bubble, pat, c, p, head_hit])
	var info := UI.panel(UI.DIALOG_NAVY, UI.DIALOG_RIM, 12)
	stage.add_child(info)
	var iv := UI.vbox(4)
	info.add_child(iv)
	iv.add_child(UI.label("Showroom", 20, UI.GOLD, true))
	var left := Game.walkin_schedule.size()
	iv.add_child(UI.label("Waiting: %d · Still coming today: about %d" % [lobby.size(), left], 14))
	if Game.cars.is_empty():
		iv.add_child(UI.label("No cars to show. Customers will leave.", 14, UI.BAD))
	elif Game.cars.size() > 4:
		iv.add_child(UI.label("+%d more cars outside on the lot" % (Game.cars.size() - 4), 14, UI.MUTED))
	iv.add_child(UI.label("Click a car to change its sticker price.", 13, UI.MUTED))
	iv.add_child(UI.rule(UI.GOLD_DIM))
	iv.add_child(UI.label("ON THE FLOOR", 13, UI.GOLD, true))
	for st in Game.staff:
		var row := UI.hbox(6)
		row.add_child(_thumb(Game.staff_pid(st), 30))
		row.add_child(UI.label("%s %s" % [st.name, _stars(st.stars)], 13))
		row.add_child(UI.spacer())
		var free: bool = st.get("busy_until", 0.0) <= Game.clock or st.get("busy_day", 0) != Game.day
		row.add_child(UI.label("Free" if free else "With a customer", 12, UI.GOOD if free else UI.MUTED))
		iv.add_child(row)
	var rv := UI.hbox(6)
	rv.add_child(UI.label("Yolp %.1f★" % Game.reputation, 13, UI.GOLD))
	if Game.pending_referrals > 0:
		rv.add_child(UI.label("· %d referral(s) still coming" % Game.pending_referrals, 12, UI.GOOD))
	iv.add_child(rv)
	var place := func():
		stage._compute()
		var w := stage.size.x
		var h := stage.size.y
		var pods: Array = stage.podiums
		var shadows := []
		for i in displays.size():
			var d: Array = displays[i]
			var c: Vector2 = pods[i] if i < pods.size() else Vector2(w * 0.5, h * 0.62)
			var cw: float = stage.car_w if stage.car_w > 0.0 else min(340.0, w / max(1, pods.size()) - 16)
			var fh: float = cw * 0.5625
			# the frame centre: from the render's camera when it was exported, else just above the floor spot
			var centre: Vector2 = stage.podium_targets[i] if i < stage.podium_targets.size() else c - Vector2(0, fh * 0.29)
			var ground: Vector2 = c if i < stage.podium_targets.size() else centre + Vector2(0, fh * 0.29)
			d[0].position = centre - Vector2(cw / 2.0, fh / 2.0)
			d[0].size = Vector2(cw, fh)
			d[1].position = Vector2.ZERO
			d[1].size = Vector2(cw, fh)
			# mirrored about the tyre contact line
			var contact: float = ground.y - d[0].position.y
			d[3].size = Vector2(cw, fh)
			d[3].position = Vector2(0, contact * 2.0)
			d[4].position = Vector2(cw * 0.15, fh * 0.22)
			d[4].size = Vector2(cw * 0.77, fh * 0.58)
			var tag: Label = d[2]
			tag.add_theme_font_size_override("font_size", clampi(roundi(cw * 0.085), 16, 30))
			tag.reset_size()
			tag.pivot_offset = tag.get_combined_minimum_size() / 2.0
			tag.position = Vector2(cw * 0.52, fh * 0.32) - tag.get_combined_minimum_size() / 2.0
			shadows.append([ground, Vector2(cw * 0.34, 0), Vector2(0, fh * 0.075)])
		# clear floor spots: the gaps between the display cars first, then open marble in the
		# middle of the room (never the lounge sofa on the right or the counter on the left)
		var shown_pods: Array = pods.slice(0, max(1, displays.size()))
		var xs := []
		for k in range(shown_pods.size() - 1):
			xs.append((shown_pods[k].x + shown_pods[k + 1].x) / 2.0)
		for f in [0.5, 0.3, 0.62, 0.2, 0.42]:
			var ok := true
			for x in xs:
				if abs(x - w * f) < w * 0.09:
					ok = false
			if ok:
				xs.append(w * f)
		for i in people.size():
			var pr: Array = people[i]
			# stand on the marble at slightly different depths; size follows the camera's perspective
			var feet: float = h * (0.74 + 0.035 * (i % 2))
			var ph: float = stage.person_height(feet)
			var pw: float = ph * 0.42
			var gx: float = clamp(xs[i % xs.size()], w * 0.17, w * 0.66)
			var target := Vector2(gx - pw / 2.0, feet - ph)
			var cust: Dictionary = pr[4]
			var btn: Button = pr[0]
			var fig: Control = pr[5]
			pr[1].position = Vector2(-40, -22)
			pr[1].size = Vector2(pw + 80, 20)
			pr[2].position = Vector2(-30, -66)
			pr[2].size = Vector2(pw + 60, 0)
			pr[3].position = Vector2(pw * 0.1, 0)
			pr[3].size = Vector2(pw * 0.8, 7)
			pr[6].position = Vector2(-30, -70)
			pr[6].size = Vector2(pw + 60, 70)
			if not cust.get("entered", false):
				# new arrivals come in through the glass doors at the back and walk forward to
				# their spot between the cars, bobbing and swaying, then settle into idle
				cust.entered = true
				var start_feet: float = h * 0.635
				var start := Vector2(w * 0.5 + (w * 0.08 if gx >= w * 0.5 else -w * 0.08), start_feet)
				var dir: float = sign(gx - start.x)
				fig.pivot_offset = Vector2(pw / 2.0, ph)
				fig.scale.x = -1.0 if dir < 0 else 1.0
				for k in [1, 2, 3]:
					pr[k].modulate.a = 0.0
				btn.modulate.a = 0.0
				var walk := func(t: float):
					var fy: float = lerp(start_feet, feet, t)
					var hh: float = stage.person_height(fy)
					var ww: float = hh * 0.42
					var fx: float = lerp(start.x, gx, t)
					var bob: float = abs(sin(t * PI * 7.0)) * hh * 0.025 * (1.0 - t * t)
					btn.size = Vector2(ww, hh)
					btn.position = Vector2(fx - ww / 2.0, fy - hh - bob)
					fig.pivot_offset = Vector2(ww / 2.0, hh)
					fig.rotation = sin(t * PI * 7.0) * 0.045 * (1.0 - t)
					btn.modulate.a = clamp(t * 5.0, 0.0, 1.0)
				walk.call(0.0)
				var tw: Tween = btn.create_tween()
				tw.tween_method(walk, 0.0, 1.0, 2.0)
				tw.tween_callback(func():
					fig.rotation = 0.0
					fig.scale.x = 1.0
					btn.size = Vector2(pw, ph)
					btn.position = target)
				tw.set_parallel(true)
				for k in [1, 2, 3]:
					tw.tween_property(pr[k], "modulate:a", 1.0, 0.35)
			else:
				btn.size = Vector2(pw, ph)
				btn.position = target
			shadows.append([target + Vector2(pw / 2.0, ph * 0.985), Vector2(pw * 0.42, 0), Vector2(0, pw * 0.09)])
		floor_fx.set_meta("pads", shadows)
		floor_fx.queue_redraw()
		info.position = Vector2(w - 360, 12)
		info.size = Vector2(348, 0)
	floor_fx.draw.connect(func():
		for pad in floor_fx.get_meta("pads", []):
			_shadow_pad(floor_fx, pad[0], pad[1], pad[2]))
	stage.resized.connect(place)
	place.call_deferred()


## A soft contact shadow: stacked translucent ellipses (centre, half-axis vectors) on any canvas item.
static func _shadow_pad(ci: CanvasItem, c: Vector2, ax: Vector2, ay: Vector2, alpha := 0.11, rings := 5) -> void:
	for k in rings:
		var poly := PackedVector2Array()
		for j in 28:
			var a := TAU * j / 28.0
			poly.append(c + (ax * cos(a) + ay * sin(a)) * (1.3 - k * 0.1))
		ci.draw_colored_polygon(poly, Color(0, 0, 0, alpha))


static var _refl_mat: ShaderMaterial


## Fades a vertically flipped sprite into the floor: strongest at the tyres, gone a third of the way down.
static func _floor_reflection_material() -> ShaderMaterial:
	if _refl_mat == null:
		var sh := Shader.new()
		sh.code = "shader_type canvas_item;\nvoid fragment() { vec4 c = texture(TEXTURE, UV) * COLOR; c.a *= 0.2 * smoothstep(0.45, 0.85, UV.y); COLOR = c; }"
		_refl_mat = ShaderMaterial.new()
		_refl_mat.shader = sh
	return _refl_mat


func _price_popup(car: Dictionary) -> void:
	var c := _modal(Color(0.04, 0.07, 0.13, 0.98))
	var v := UI.vbox(10)
	c.add_child(v)
	v.add_child(UI.label("Sticker price · %d %s" % [car.year, car.model], 22, UI.GOLD, true))
	v.add_child(_car_art(car, Vector2(360, 140)))
	var fair := Game.sale_value(car)
	v.add_child(UI.label("Marco's fair price: %s%s" % [Game.money_str(fair), "  (hot today +10%)" if car.cls == Game.hot_class else ""], 16, UI.BLUE))
	v.add_child(UI.label("You've put in %s" % Game.money_str(car.paid + car.spent), 15, UI.MUTED))
	var lab := UI.label("", 22, UI.TEXT, true)
	var marg := UI.label("", 15)
	var s := HSlider.new()
	s.min_value = int(fair * 0.8 / 100) * 100
	s.max_value = int(fair * 1.5 / 100) * 100
	s.step = 100
	s.custom_minimum_size = Vector2(420, 32)
	s.value = car.get("sticker", fair)
	var upd := func(val):
		lab.text = "Sticker: " + Game.money_str(val)
		var m: int = int(val) - car.paid - car.spent
		marg.text = "Margin if sold at sticker: %s" % Game.money_str(m)
		marg.add_theme_color_override("font_color", UI.GOOD if m >= 0 else UI.BAD)
	s.value_changed.connect(upd)
	upd.call(s.value)
	v.add_child(lab)
	v.add_child(s)
	v.add_child(marg)
	v.add_child(UI.para("A high sticker sets a high anchor, but customers start less interested and haggle harder.", 14, UI.MUTED))
	var h := UI.hbox(10)
	h.add_child(UI.gold_button("Save price", func():
		car.sticker = int(s.value)
		Game.save_game()
		_close_overlay()
		show_screen(current), 180))
	h.add_child(UI.button("Cancel", func(): _close_overlay(), 140))
	v.add_child(h)


# ---------- walk-ins over the day ----------

func _tick_walkins() -> void:
	while not Game.walkin_schedule.is_empty() and Game.clock >= Game.walkin_schedule[0] and lobby.size() < MAX_IN_LOBBY:
		Game.walkin_schedule.pop_front()
		var c := Game.make_customer()
		lobby.append(c)
		Game.stats.buyers += 1
		if current != "showroom":
			toast("%s just walked into the showroom." % c.name)
		elif lobby_stage:
			_build_lobby(lobby_stage)
	# waiting customers: staff step in after 40 minutes, others give up after 2 hours
	for c in lobby.duplicate():
		var waited: float = Game.clock - c.arrived
		var patience := 240.0 if Game.has_upgrade("lounge") else 120.0
		if waited > 40 and _free_staff() != {}:
			_staff_handles(c, _free_staff(), true)
		elif waited > patience:
			lobby.erase(c)
			Game.stats.walked += 1
			Game.month_walked += 1
			Game.add_review(c, 2 if randf() < 0.5 else 1, "", "", ["Stood in the showroom forever. Nobody helped me. Left.", "Waited %d minutes and not one salesperson said hi." % int(waited)].pick_random())
			toast("%s got tired of waiting, left, and posted a bad Yolp review." % c.name)
			if lobby_stage:
				_build_lobby(lobby_stage)


func _free_staff() -> Dictionary:
	for s in Game.staff:
		if s.get("busy_until", 0.0) <= Game.clock or s.get("busy_day", 0) != Game.day:
			return s
	return {}


func _pick_car_for(c: Dictionary) -> Dictionary:
	var best := {}
	var best_score := -1e9
	for car in Game.cars:
		var max_price := _max_price(c, car, 50.0)
		var score := 0.0
		if car.cls == c.wants_cls:
			score += 30000
		score -= abs(car.get("sticker", 0) - max_price)
		if max_price < car.get("sticker", 0) * 0.7:
			continue
		if score > best_score:
			best_score = score
			best = car
	return best


func _max_price(c: Dictionary, car: Dictionary, interest: float) -> int:
	var v: float = float(Game.value(car, true)) * c.budget
	if car.cls == Game.hot_class:
		v *= 1.1
	if Game.has_perk("vip") and car.cls in ["sport", "exotic"]:
		v *= 1.1
	return int(round(v * (0.85 + interest / 400.0) / 100.0)) * 100


func _staff_handles(c: Dictionary, s: Dictionary, auto := false) -> void:
	lobby.erase(c)
	s.busy_until = Game.clock + 60
	s.busy_day = Game.day
	var car := _pick_car_for(c)
	if car.is_empty():
		toast("%s talked to %s, but nothing on the lot fit their budget." % [s.name, c.name])
	elif randf() < _handoff_chance(c, s):
		# closing skill sets the price they get, finance skill the dealer reserve, upselling the warranty
		var factor: float = 0.86 + Game.skill(s, "closing") / 700.0
		var price: int = min(car.get("sticker", 0), _max_price(c, car, 50)) * min(1.0, factor * randf_range(0.97, 1.03))
		price = int(round(price / 100.0)) * 100
		var income := {"sales": price}
		if c.finance:
			income.finance = int(price * 0.004 * (Game.skill(s, "finance") / 20.0) * (1.5 if s.trait == "Finance whiz" else 1.0))
		if randf() < Game.skill(s, "upsell") / 180.0 + (0.25 if s.trait == "Upsells warranties" else 0.0):
			income.addons = 1200
		var happy: float = clamp(0.3 + Game.skill(s, "rapport") / 180.0 + randf_range(-0.1, 0.1) + (0.12 if s.trait == "Smooth talker" else 0.0), 0.0, 1.0)
		if s.trait == "Stretches the truth" and randf() < 0.4:
			happy = 0.2
			Game.add_liability(c.name, "promises %s made about the %s" % [s.name, car.model], 0.35, 4000)
		Game.staff_practice(s)
		_complete_sale(car, income, happy, s.name, {"customer": c.name, "cust": c})
		return
	else:
		var lines := {
			"Jeff": "Jeff tried to sell %s a car and called them \"bro\" eleven times. They left." % c.name,
			"Maruchan": "Maruchan got %s's Instagram but not a sale." % c.name,
		}
		toast(lines.get(s.name, "%s couldn't close %s today." % [s.name, c.name]))
		if Game.skill(s, "rapport") < 40 and randf() < 0.5:
			Game.add_review(c, 2, "", s.name, "%s was pushy and clueless. Didn't buy." % s.name)
	if lobby_stage:
		_build_lobby(lobby_stage)


# ---------- customer menu: pitch, negotiate price, negotiate finance ----------

## Close chance when you hand a walk-in to someone: their closing skill, plus rapport for picky buyers.
func _handoff_chance(c: Dictionary, s: Dictionary) -> float:
	var p := Game.staff_close_chance(s)
	p += (Game.skill(s, "rapport") - 50) / 500.0 * (1.0 - Game.BUYER_TYPES[c.type].tolerance + 0.5)
	if c.type == "lowballer":
		p -= 0.1
	if c.type == "whale" or c.get("referral", false):
		p += 0.08
	match s.trait:
		"Great with families":
			if c.type in ["parent", "first"]: p += 0.12
		"Car nerd":
			if c.type == "nerd": p += 0.15
		"VIP Relations":
			if c.type in ["whale", "influencer", "local"]: p += 0.1
	return clamp(p, 0.03, 0.95)


func _open_customer(c: Dictionary) -> void:
	customer = c
	if not c.has("stage"):
		c.stage = "browse"
		c.car_id = -1
		c.used = []
		# waiting for a salesperson costs patience and a bit of mood
		var waited: float = max(0.0, Game.clock - c.arrived)
		c.patience = clamp(1.0 - waited / 200.0, 0.35, 1.0)
		c.happiness = clamp(c.happiness - waited / 600.0, 0.2, 1.0)
		var car := _pick_car_for(c)
		if not car.is_empty():
			c.car_id = car.id
			var fair := float(Game.sale_value(car))
			var interest := 0.5 * Game.condition(car) + (10 if car.detailed else 0) + (5 if Game.has_upgrade("lights") else 0) + (10 if Game.has_upgrade("turntable") else 0)
			interest += 4 if car.get("rims", "silver") != "silver" else 0
			interest -= 40.0 * (car.get("sticker", fair) - fair) / fair
			c.interest = clamp(interest, 5.0, 90.0)
			c.log = ["%s: \"%s\"" % [c.name, Game.BUYER_TYPES[c.type].intro], "%s: \"I'm looking at the %s.\"" % [c.name, car.model]]
			if waited > 30:
				c.log.push_front("%s: \"I've been standing here %d minutes, you know.\"" % [c.name, int(waited)])
		else:
			c.log = ["%s: \"Nothing here is in my budget. Maybe next time.\"" % c.name]
	_render_customer()


func _cust_car() -> Dictionary:
	return _find_car(customer.get("car_id", -1))


func _mood_word(h: float) -> String:
	if h >= 0.85: return "Thrilled"
	if h >= 0.65: return "Happy"
	if h >= 0.45: return "Okay"
	if h >= 0.25: return "Annoyed"
	return "Angry"


func _modal(bg_c := Color(0.04, 0.07, 0.13, 0.97), margin := 0) -> PanelContainer:
	UI.clear(overlay)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	var shade := ColorRect.new()
	shade.color = Color(0, 0, 0, 0.55)
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(shade)
	var p := UI.panel(bg_c, UI.GOLD, 20)
	if margin > 0:
		var m := MarginContainer.new()
		m.set_anchors_preset(Control.PRESET_FULL_RECT)
		for side in ["left", "right", "top", "bottom"]:
			m.add_theme_constant_override("margin_" + side, margin)
		overlay.add_child(m)
		m.add_child(p)
	else:
		var cc := CenterContainer.new()
		cc.set_anchors_preset(Control.PRESET_FULL_RECT)
		overlay.add_child(cc)
		cc.add_child(p)
	return p


func _close_overlay() -> void:
	UI.clear(overlay)
	overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE


func _meter(parent: Control, name: String, val: float, note := "") -> void:
	var col: Color = UI.GOOD if val >= 0.65 else (UI.GOLD if val >= 0.35 else UI.BAD)
	var row := UI.hbox(8)
	if name != "":
		var nl := UI.label(name, 15)
		nl.custom_minimum_size = Vector2(88, 0)
		row.add_child(nl)
	var m := MeterBar.new()
	m.value = val
	m.red_line = 0.15
	m.custom_minimum_size = Vector2(120, 18)
	m.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(m)
	var vl := UI.label("%d%%%s" % [int(val * 100), note], 15, col, true)
	vl.custom_minimum_size = Vector2(54, 0)
	row.add_child(vl)
	parent.add_child(row)


func _place(c: Control, x: float, y: float, w: float, h := 0.0) -> void:
	c.position = Vector2(x, y)
	c.size = Vector2(w, h)
	c.custom_minimum_size = Vector2(w, h)


func _render_customer() -> void:
	var c := customer
	UI.clear(overlay)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	var W := size.x
	var H := size.y
	var back := TextureRect.new()
	back.texture = world_tex("dealdesk")
	back.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	back.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	back.set_anchors_preset(Control.PRESET_FULL_RECT)
	back.modulate = Color(0.87, 0.87, 0.87)
	back.material = WorldLook.new_material()
	WorldLook.update(back.material, back.texture, "dealdesk" + Game.world_suffix())
	overlay.add_child(back)
	var vign := ColorRect.new()
	vign.color = Color(0, 0, 0, 0.25)
	vign.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(vign)
	# top bar: clock chip and dealership financial chip
	var clock_chip := UI.panel(UI.NAVY, UI.GLASS_EDGE, 10)
	var cv := UI.vbox(0)
	clock_chip.add_child(cv)
	cv.add_child(UI.label("%s · %s" % [Game.clock_str(), Game.day_phase().to_upper()], 18, UI.TEXT, true))
	cv.add_child(UI.label(Game.date_str().to_upper() + (" · TRADING HOURS ENDING" if Game.clock > 19 * 60 else ""), 12, UI.MUTED))
	overlay.add_child(clock_chip)
	_place(clock_chip, 20, 16, 250)
	var fin := UI.panel(UI.NAVY, UI.GLASS_EDGE, 10)
	var fv := UI.vbox(2)
	fin.add_child(fv)
	fv.add_child(UI.label("DEALERSHIP FINANCIAL", 14, UI.GOLD, true))
	fv.add_child(UI.label("Monthly rent & bills %s in %d days" % [Game.money_str(Game.monthly_bills().total), Game.days_until_bills()], 13))
	fv.add_child(UI.label("Bank balance %s" % Game.money_str(Game.money), 13, UI.GOOD))
	overlay.add_child(fin)
	_place(fin, W - 290, 16, 270)
	# left: customer menu
	var left := UI.panel(UI.NAVY, UI.GLASS_EDGE, 14)
	overlay.add_child(left)
	_place(left, 20, 96, 310, H - 116)
	var lv := UI.vbox(6)
	left.add_child(lv)
	var top := UI.hbox(6)
	top.add_child(UI.label("CUSTOMER MENU", 20, UI.TEXT, true))
	top.add_child(UI.spacer())
	var x := UI.button("✕", _step_away, 36, 30)
	x.tooltip_text = "Step away (they keep waiting)"
	top.add_child(x)
	lv.add_child(top)
	lv.add_child(UI.rule(UI.GOLD))
	var who := UI.hbox(10)
	var face := _portrait_frame(Game.customer_pid(c), c.happiness * 2.0 - 1.0, CARD_CYAN, 124)
	face.custom_minimum_size.x = 110
	who.add_child(face)
	var wv := UI.vbox(1)
	wv.add_child(UI.label(c.name.to_upper(), 22, UI.GOLD, true))
	var tier: Array = Game.CREDIT[c.credit]
	wv.add_child(UI.label(Game.BUYER_TYPES[c.type].title, 14, UI.MUTED))
	wv.add_child(UI.label("%s credit" % tier[0], 14, UI.MUTED))
	wv.add_child(UI.label("Wants financing" if c.finance else "Paying cash", 14, UI.MUTED))
	wv.add_child(UI.label(_mood_word(c.happiness), 15, UI.GOOD if c.happiness >= 0.65 else (UI.GOLD if c.happiness >= 0.35 else UI.BAD), true))
	who.add_child(wv)
	lv.add_child(who)
	lv.add_child(UI.label("CUSTOMER HAPPINESS", 13, UI.MUTED, true))
	_meter(lv, "", c.happiness)
	lv.add_child(UI.label("CUSTOMER PATIENCE", 13, UI.MUTED, true))
	_meter(lv, "", c.patience)
	if c.has("interest"):
		lv.add_child(UI.label("INTEREST IN THE CAR", 13, UI.MUTED, true))
		var ib := UI.bar(c.interest, 100, UI.CYAN, 8)
		lv.add_child(ib)
	lv.add_child(UI.rule())
	var log_box := UI.vbox(5)
	for line in c.log.slice(max(0, c.log.size() - 6)):
		log_box.add_child(UI.para(line, 14, UI.TEXT if not line.begins_with("You") else UI.GOLD))
	lv.add_child(UI.scroll(log_box))
	# right: the car card
	var car := _cust_car()
	if not car.is_empty():
		var right := UI.panel(UI.NAVY, UI.GLASS_EDGE, 14)
		overlay.add_child(right)
		_place(right, W - 330, 96, 310)
		var rv := UI.vbox(4)
		right.add_child(rv)
		rv.add_child(UI.label(("%d %s" % [car.year, car.model]).to_upper(), 19, UI.TEXT, true))
		rv.add_child(UI.rule(UI.GOLD))
		rv.add_child(_car_art(car, Vector2(0, 100)))
		for row in [["Sticker price", Game.money_str(car.get("sticker", 0))], ["You're in for", Game.money_str(car.paid + car.spent)],
				["Condition", "%d / 100" % Game.condition(car)], ["Mileage", _num(car.miles) + " mi"],
				["History", car.history if car.history_known else "Not checked"], ["Detailed", "Yes" if car.detailed else "No"]]:
			var hr := UI.hbox()
			hr.add_child(UI.label(row[0].to_upper(), 13, UI.MUTED))
			hr.add_child(UI.spacer())
			hr.add_child(UI.label(row[1], 14))
			rv.add_child(hr)
	# bottom center: what you can do now
	var act := UI.panel(UI.NAVY, UI.GLASS_EDGE, 14)
	overlay.add_child(act)
	var aw: float = W - 700
	act.custom_minimum_size = Vector2(aw, 0)
	act.position = Vector2(350, 0)
	act.size = Vector2(aw, 0)
	var av := UI.vbox(8)
	act.add_child(av)
	match c.stage:
		"browse": _actions_browse(av)
		"negotiate": _actions_negotiate(av)
		"finance": _actions_finance(av)
		"done":
			av.add_child(UI.label(c.log[-1] if not c.log.is_empty() else "", 16, UI.BAD, true, true))
	var dock := func():
		act.size.y = 0
		act.position.y = H - 20 - act.get_combined_minimum_size().y
	dock.call_deferred()


func _step_away() -> void:
	customer = {}
	_close_overlay()
	if current == "showroom" and lobby_stage:
		_build_lobby(lobby_stage)


func _act(parent: Control, title: String, desc: String, cb: Callable, disabled := false) -> void:
	var b := UI.button(title.to_upper() + ("\n" + desc if desc != "" else ""), cb, 0, 50 if desc != "" else 40)
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	b.add_theme_font_size_override("font_size", 14)
	b.disabled = disabled
	parent.add_child(b)


func _act_grid() -> GridContainer:
	var g := GridContainer.new()
	g.columns = 2
	g.add_theme_constant_override("h_separation", 8)
	g.add_theme_constant_override("v_separation", 6)
	return g


func _actions_browse(r: Control) -> void:
	var c := customer
	r.add_child(UI.label("TALK TO %s" % c.name.to_upper(), 19, UI.GOLD, true))
	var g := _act_grid()
	r.add_child(g)
	if _cust_car().is_empty():
		_act(g, "Say goodbye", "", _customer_leaves.bind("%s: \"Maybe next time.\"" % c.name))
		return
	var used: Array = c.used
	if Game.has_staff("Maruchan"):
		_act(g, "Have Maruchan say hi", "VIP charm: +15% happiness", _pitch.bind("maruchan"), "maruchan" in used)
	if Game.has_upgrade("coffee"):
		_act(g, "Offer an espresso", "Lounge espresso: +15% happiness", _pitch.bind("espresso"), "espresso" in used)
	_act(g, "Take a test drive", "+15% happiness. Can expose faults.", _pitch.bind("test_drive"), "test_drive" in used)
	_act(g, "Talk up features", "Raises interest", _pitch.bind("features"), "features" in used)
	_act(g, "Show the history report", "Hiding bad history risks a lawsuit", _pitch.bind("history"), "history" in used)
	_act(g, "Throw in extras ($300)", "Floor mats and oil changes", _pitch.bind("extras"), "extras" in used)
	var row := UI.hbox(6)
	var talk := UI.gold_button("Talk numbers", func(): _start_negotiation(), 200, 44)
	row.add_child(talk)
	for s in Game.staff:
		var free: bool = s.get("busy_until", 0.0) <= Game.clock or s.get("busy_day", 0) != Game.day
		var b := UI.button("Hand to %s · %d%%" % [s.name, int(_handoff_chance(c, s) * 100)], func():
			_close_overlay()
			customer = {}
			_staff_handles(c, s), 0, 44)
		b.add_theme_font_size_override("font_size", 14)
		b.disabled = not free
		row.add_child(b)
	r.add_child(row)


func _pitch(id: String) -> void:
	var c := customer
	var car := _cust_car()
	var likes: Array = Game.BUYER_TYPES[c.type].likes
	var boost := 1.5 if id in likes else 1.0
	c.used.append(id)
	c.patience -= 0.04
	match id:
		"maruchan":
			c.happiness += 0.15
			c.patience += 0.1
			c.log.append("Maruchan: \"Welcome to " + Game.dealer_name + ", my friend. You want a water? You look like a Porsha guy.\"  (+15% happiness)")
		"espresso":
			c.happiness += 0.15
			c.patience += 0.15
			c.log.append("%s: \"Oh, that's actually good espresso.\"  (+15% happiness)" % c.name)
		"features":
			var g := randi_range(5, 15) if (id in likes or car.cls in ["sport", "exotic"]) else randi_range(1, 6)
			c.interest += g * boost
			c.log.append("You: \"Heated seats, great sound, and it turns heads on Coast Highway.\"  (+%d interest)" % int(g * boost))
		"test_drive":
			var finds: bool = c.type == "nerd" or randf() < 0.6
			if Game.hidden_total(car) > 0 and finds:
				var found := Game.reveal_faults(car)
				c.interest -= 20
				c.happiness -= 0.1
				c.log.append("%s: \"Why is the %s doing THAT?\"  The test drive exposed a problem." % [c.name, found[0].to_lower()])
			else:
				var g2 := Game.condition(car) / 6.0 * boost
				c.interest += g2
				c.happiness += 0.15
				c.log.append("%s: \"Oh, this drives nice.\"  (+15%% happiness, +%d interest)" % [c.name, int(g2)])
		"history":
			car.history_known = true
			if car.history == "Clean":
				c.interest += 10 * boost
				c.log.append("%s: \"Clean history. I like that.\"  (+%d interest)" % [c.name, int(10 * boost)])
			else:
				c.interest -= 12
				c.log.append("%s: \"%s? Hmm. Thanks for being upfront.\"  (-12 interest)" % [c.name, car.history])
		"extras":
			c.extras = c.get("extras", 0) + 300
			c.interest += 6 * boost
			c.happiness += 0.08
			c.log.append("You: \"I'll throw in floor mats and a year of oil changes.\"")
	c.interest = clamp(c.interest, 0, 100)
	c.happiness = clamp(c.happiness, 0.0, 1.0)
	c.patience = clamp(c.patience, 0.0, 1.0)
	_render_customer()


func _tol() -> float:
	return Game.BUYER_TYPES[customer.type].tolerance * (1.25 if Game.has_upgrade("lounge") else 1.0)


func _start_negotiation() -> void:
	var c := customer
	var car := _cust_car()
	c.stage = "negotiate"
	c.max_price = _max_price(c, car, c.interest)
	# the red line: ask more than this and they storm out
	c.threshold = int(round(c.max_price * (1.06 + 0.06 * _tol()) / 100.0)) * 100
	var sticker: int = car.get("sticker", Game.sale_value(car))
	c.offer = int(round(min(sticker, c.max_price) * randf_range(0.8, 0.9) / 100.0)) * 100
	c.counter = min(sticker, c.threshold - 100)
	c.rounds = 0
	c.log.append("%s: \"I'll be honest. I can do %s.\"" % [c.name, Game.money_str(c.offer)])
	_render_customer()


func _actions_negotiate(r: Control) -> void:
	var c := customer
	var car := _cust_car()
	var cost: int = car.paid + car.spent + c.get("extras", 0)
	r.add_child(UI.label("PRICE NEGOTIATION · %s" % car.model.to_upper(), 19, UI.GOLD, true))
	var bar := DealBar.new()
	bar.custom_minimum_size = Vector2(0, 64)
	bar.offer = c.offer
	bar.threshold = c.threshold
	bar.cost = cost
	bar.lo = min(cost, c.offer) * 0.95
	bar.hi = c.threshold * 1.1
	r.add_child(bar)
	if Game.has_perk("insights"):
		r.add_child(UI.label("Market Insights: they'll happily go to about %s" % Game.money_str(c.max_price), 14, UI.GOOD))
	var lab := UI.label("", 17, UI.TEXT, true)
	var marg := UI.label("", 14)
	var react := UI.label("", 14, UI.MUTED)
	var s := HSlider.new()
	s.min_value = c.offer
	s.max_value = int(c.threshold * 1.1 / 100) * 100
	s.step = 100
	s.value = clamp(c.counter, s.min_value, s.max_value)
	s.custom_minimum_size = Vector2(0, 30)
	var upd := func(val):
		bar.counter = val
		bar.queue_redraw()
		lab.text = "Your counter: " + Game.money_str(val)
		var m: int = int(val) - cost
		var pct: float = 100.0 * m / max(1.0, float(val))
		marg.text = "Your margin: %s (%.0f%%)" % [Game.money_str(m), pct]
		marg.add_theme_color_override("font_color", UI.GOOD if m >= 0 else UI.BAD)
		if val > c.threshold:
			react.text = "Past their bad-deal line. They will storm out."
			react.add_theme_color_override("font_color", UI.BAD)
		else:
			var squeeze: float = (float(val) - c.offer) / max(100.0, float(c.threshold - c.offer))
			react.text = "Bigger margin, angrier customer. " + ("They'll feel good about this." if squeeze < 0.3 else ("They'll grumble." if squeeze < 0.7 else "This will really upset them."))
			react.add_theme_color_override("font_color", UI.MUTED)
	s.value_changed.connect(upd)
	upd.call(s.value)
	r.add_child(s)
	var info := UI.hbox(16)
	info.add_child(lab)
	info.add_child(marg)
	r.add_child(info)
	r.add_child(react)
	var btns := UI.hbox(8)
	for b in [["Confirm %s" % Game.money_str(c.offer), func(): _price_agreed(c.offer, 0.0)], ["Counter-offer", func(): _counter(int(s.value))],
			["Walk away", _customer_leaves.bind("%s: \"Fine, I'll take my business elsewhere.\"" % c.name)]]:
		var bt := UI.gold_button(b[0], b[1], 0, 44) if b[0] == "Counter-offer" else UI.button(b[0].to_upper(), b[1], 0, 44)
		bt.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		btns.add_child(bt)
	r.add_child(btns)


func _counter(p: int) -> void:
	var c := customer
	c.counter = p
	c.rounds += 1
	var tol := _tol()
	if p <= c.offer:
		_price_agreed(c.offer, 0.0)
		return
	c.log.append("You: \"I can do %s.\"" % Game.money_str(p))
	if p > c.threshold:
		_storm_out("%s slams the desk. \"%s?! That's a rip-off. Enjoy your one-star review.\"" % [c.name, Game.money_str(p)])
		return
	c.patience -= 0.16 / tol
	if p <= c.max_price:
		var room: float = max(100.0, float(c.max_price - c.offer))
		var squeeze: float = (p - c.offer) / room
		if randf() < 0.35 + (1.0 - squeeze) * 0.5 or c.rounds >= 3:
			_price_agreed(p, squeeze)
			return
		c.happiness -= 0.06 / tol
		c.offer = int(round((c.offer + (p - c.offer) * 0.5) / 100.0)) * 100
		c.log.append("%s: \"Meet me in the middle? %s.\"" % [c.name, Game.money_str(c.offer)])
	else:
		var over: float = float(p - c.max_price) / c.max_price
		c.happiness -= (0.1 + over * 1.5) / tol
		c.offer = int(round((c.offer + (c.max_price - c.offer) * 0.6) / 100.0)) * 100
		var line := "That's way too much. Best I can do is %s." if over > 0.04 else "Too rich for me. %s."
		c.log.append("%s: \"%s\"" % [c.name, line % Game.money_str(c.offer)])
	if _check_walkout():
		return
	_render_customer()


## Returns true (and sends them off) when happiness or patience has hit the red line.
func _check_walkout() -> bool:
	var c := customer
	if c.happiness <= 0.15:
		_storm_out("%s: \"You know what? Forget it. I'm going to Costa Mesa Motors.\"" % c.name)
		return true
	if c.patience <= 0.0:
		_customer_leaves("%s: \"I've been here all day. I'm done.\"" % c.name)
		return true
	return false


func _storm_out(line: String) -> void:
	customer.happiness = 0.0
	Game.add_review(customer, 1)
	_customer_leaves(line + "  (1★ review posted on Yolp)")


func _price_agreed(price: int, squeeze: float) -> void:
	var c := customer
	c.price = price
	c.happiness = clamp(c.happiness + 0.15 - squeeze * 0.35, 0.0, 1.0)
	c.log.append("%s: \"Deal at %s.\"" % [c.name, Game.money_str(price)])
	if c.finance:
		c.stage = "finance"
		c.term = 60
		c.apr = Game.CREDIT[c.credit][1] + 2.0
		c.finance_tries = 0
		c.log.append("%s: \"I'll need financing. What rate can you get me?\"" % c.name)
		_render_customer()
	else:
		c.reserve = 0
		c.apr = 0.0
		_go_paperwork()


func _payment(amount: float, apr: float, months: int) -> float:
	var r := apr / 100.0 / 12.0
	if r <= 0:
		return amount / months
	return amount * r / (1.0 - pow(1.0 + r, -months))


func _reserve(amount: float, apr: float, months: int) -> int:
	var buy: float = Game.CREDIT[customer.credit][1]
	return max(0, int(round(amount * max(0.0, apr - buy) / 100.0 * months / 12.0 * 0.5 / 10.0)) * 10)


func _apr_line() -> float:
	return Game.CREDIT[customer.credit][2] + 3.0


func _actions_finance(r: Control) -> void:
	var c := customer
	var tier: Array = Game.CREDIT[c.credit]
	var head := UI.hbox(8)
	head.add_child(UI.label("FINANCE RATE NEGOTIATION", 19, UI.GOLD, true))
	head.add_child(UI.spacer())
	r.add_child(head)
	r.add_child(UI.para("%s credit. The bank lends to you at %.1f%%; everything above it is your profit." % [tier[0], tier[1]], 14, UI.MUTED))
	var terms := head
	for t in [36, 60, 72]:
		var b := UI.button("%d mo" % t, func():
			c.term = t
			_render_customer(), 0, 36)
		if c.term == t:
			b.add_theme_stylebox_override("normal", UI.box(Color(0.3, 0.24, 0.1, 0.95), UI.GOLD, 8, 2, 10))
		terms.add_child(b)
	var bar := DealBar.new()
	bar.custom_minimum_size = Vector2(0, 64)
	bar.percent = true
	bar.offer = tier[1]
	bar.cost = tier[1]
	bar.threshold = _apr_line()
	bar.lo = tier[1] - 0.5
	bar.hi = _apr_line() + 2.0
	r.add_child(bar)
	var lab := UI.label("", 17, UI.TEXT, true)
	var pay := UI.label("", 15)
	var res := UI.label("", 15, UI.GOOD)
	var s := HSlider.new()
	s.min_value = tier[1]
	s.max_value = _apr_line() + 2.0
	s.step = 0.1
	s.value = c.apr
	s.custom_minimum_size = Vector2(0, 30)
	var upd := func(val):
		bar.counter = val
		bar.queue_redraw()
		lab.text = "Rate: %.1f%% APR" % val
		pay.text = "Their payment: %s/month for %d months" % [Game.money_str(_payment(c.price, val, c.term)), c.term]
		res.text = "Your finance profit: %s" % Game.money_str(_reserve(c.price, val, c.term))
	s.value_changed.connect(upd)
	upd.call(s.value)
	r.add_child(s)
	var info := UI.hbox(16)
	info.add_child(lab)
	info.add_child(res)
	r.add_child(info)
	r.add_child(pay)
	var btns := UI.hbox(8)
	var o := UI.gold_button("Offer this rate", func(): _offer_rate(s.value), 0, 44)
	o.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	btns.add_child(o)
	var bk := UI.button("GIVE THEM THE BANK RATE", func(): _offer_rate(tier[1]), 0, 44)
	bk.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	btns.add_child(bk)
	r.add_child(btns)


func _offer_rate(apr: float) -> void:
	var c := customer
	var tier: Array = Game.CREDIT[c.credit]
	var tol := _tol()
	c.apr = apr
	c.log.append("You: \"I can get you %.1f%% for %d months.\"" % [apr, c.term])
	if apr > _apr_line():
		_storm_out("%s slams the desk. \"%.1f%%?! That's loan-shark money!\"" % [c.name, apr])
		return
	if apr <= tier[2]:
		var greed: float = (apr - tier[1]) / max(0.1, tier[2] - tier[1])
		c.happiness = clamp(c.happiness + 0.1 - greed * 0.25 / tol, 0.0, 1.0)
		c.reserve = _reserve(c.price, apr, c.term)
		c.log.append("%s: \"%s a month? I can do that.\"" % [c.name, Game.money_str(_payment(c.price, apr, c.term))])
		_go_paperwork()
		return
	c.finance_tries += 1
	c.happiness -= (0.12 + (apr - tier[2]) * 0.03) / tol
	c.patience -= 0.15 / tol
	if _check_walkout():
		return
	if c.finance_tries >= 3:
		c.reserve = 0
		c.apr = 0.0
		c.log.append("%s: \"Forget it, I'll get a loan from my credit union and pay you cash.\"" % c.name)
		_go_paperwork()
		return
	c.log.append("%s: \"That's crazy. My cousin got %.1f%%.\"" % [c.name, tier[2] - randf_range(0.5, 2.0)])
	_render_customer()


func _customer_leaves(line: String) -> void:
	var c := customer
	if line != "":
		c.log.append(line)
		Game.stats.walked += 1
		Game.month_walked += 1
		if c.happiness < 0.25:
			Game.add_review(c, 2)
	c.stage = "done"
	sale = {}
	_render_customer()
	await get_tree().create_timer(1.6 if line != "" else 0.1).timeout
	lobby.erase(c)
	customer = {}
	_close_overlay()
	Game.save_game()
	if line != "":
		toast("%s walked out of the dealership." % c.name)
	if current == "showroom" and lobby_stage:
		_build_lobby(lobby_stage)


# =====================================================================
# Paperwork: a real contract on the desk
# =====================================================================

const PAPER := Color(0.98, 0.97, 0.92)
const PAPER_INK := Color(0.08, 0.08, 0.12)
const PAPER_RED := Color(0.75, 0.12, 0.12)


func _vin(car: Dictionary) -> String:
	var chars := "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
	var rng := RandomNumberGenerator.new()
	rng.seed = int(car.id) * 104729
	var v := ""
	for i in 17:
		v += chars[rng.randi() % chars.length()]
	return v


func _go_paperwork() -> void:
	var c := customer
	var car := _cust_car()
	_render_customer()
	await get_tree().create_timer(0.9).timeout
	if customer != c:
		return
	var financed: bool = c.get("reserve", 0) > 0 or c.get("apr", 0.0) > 0.0
	var fields := {
		"price": {"ok": Game.money_str(c.price), "bad": Game.money_str(c.price - randi_range(10, 40) * 100)},
		"odometer": {"ok": _num(car.miles), "bad": _num(max(1000, car.miles - randi_range(20, 60) * 1000))},
		"buyer": {"ok": "%s · ID verified" % c.name, "bad": "%s · ID not checked" % c.name},
	}
	if financed:
		fields.apr = {"ok": "%.1f" % c.apr, "bad": "%.1f" % (c.apr + randf_range(1.5, 3.0))}
	var error := ""
	if randf() < 0.6:
		error = fields.keys().pick_random()
	sale = {"car": car, "customer": c, "price": c.price, "financed": financed, "fields": fields, "error": error,
		"signed": {"buyer": false, "seller": false, "odometer": false},
		"addons": {"warranty": false, "protect": false, "pack": false}, "time": 40.0, "flags": 0}
	_render_paperwork()
	_paper_tick()


func _paper_tick() -> void:
	while not sale.is_empty() and sale.time > 0:
		await get_tree().create_timer(1.0).timeout
		if sale.is_empty():
			return
		sale.time -= 1
		if sale.has("time_label") and is_instance_valid(sale.time_label):
			sale.time_label.text = "Buyer patience: %ds" % int(sale.time)
	if not sale.is_empty():
		toast("You took too long. The buyer is annoyed.")
		sale.customer.happiness -= 0.15
		_finish_paperwork()


func _pbox(title: String, value: String, key := "", min_w := 0.0, big := false) -> PanelContainer:
	var sb := StyleBoxFlat.new()
	sb.bg_color = PAPER
	sb.border_color = PAPER_INK
	sb.set_border_width_all(1)
	sb.content_margin_left = 5
	sb.content_margin_right = 5
	sb.content_margin_top = 2
	sb.content_margin_bottom = 3
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", sb)
	p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	p.custom_minimum_size = Vector2(min_w, 0)
	var v := UI.vbox(0)
	p.add_child(v)
	v.add_child(UI.label(title.to_upper(), 10, PAPER_INK, true))
	var vl := UI.label(value, 17 if big else 15, Color(0.1, 0.15, 0.45))
	v.add_child(vl)
	if key != "":
		p.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		p.mouse_entered.connect(func(): sb.bg_color = Color(1.0, 0.95, 0.7))
		p.mouse_exited.connect(func(): sb.bg_color = PAPER)
		p.gui_input.connect(func(ev):
			if ev is InputEventMouseButton and ev.pressed and ev.button_index == MOUSE_BUTTON_LEFT:
				_flag_field(key))
	return p


func _dots() -> Control:
	var r := ColorRect.new()
	r.color = Color(0, 0, 0, 0.12)
	r.custom_minimum_size = Vector2(0, 1)
	return r


func _field_val(key: String) -> String:
	var f: Dictionary = sale.fields[key]
	return f.bad if sale.error == key else f.ok


func _flag_field(key: String) -> void:
	if sale.error == key:
		sale.error = ""
		toast("Good catch. Corrected and initialed.")
	else:
		sale.time -= 3
		toast("That field was right. (-3s)")
	_render_paperwork()


func _sig_box(title: String, key: String) -> Control:
	var v := UI.vbox(0)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var signed: bool = sale.signed[key]
	var name: String = sale.customer.name if key == "buyer" else Game.dealer_name
	var line := UI.hbox(4)
	line.add_child(UI.label("X", 20, PAPER_INK, true))
	if signed:
		var sig := UI.label(name, 22, Color(0.1, 0.2, 0.6))
		sig.add_theme_constant_override("outline_size", 0)
		sig.rotation_degrees = -3
		line.add_child(sig)
	else:
		var b := UI.button("Sign here", func():
			sale.signed[key] = true
			_render_paperwork(), 150, 34)
		b.add_theme_font_size_override("font_size", 14)
		b.add_theme_stylebox_override("normal", UI.box(Color(1.0, 0.85, 0.2), PAPER_INK, 3, 1, 8))
		b.add_theme_color_override("font_color", PAPER_INK)
		line.add_child(b)
	v.add_child(line)
	var rule := ColorRect.new()
	rule.color = PAPER_INK
	rule.custom_minimum_size = Vector2(0, 1)
	v.add_child(rule)
	v.add_child(UI.label(title, 11, PAPER_INK))
	return v


func _render_paperwork() -> void:
	var c: Dictionary = sale.customer
	var car: Dictionary = sale.car
	var root := _modal(Color(0.2, 0.15, 0.1, 0.98), 16)
	var h := UI.hbox(14)
	root.add_child(h)
	# ---------- the contract ----------
	var paper := UI.panel(PAPER, Color(0.6, 0.55, 0.45), 14)
	paper.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(paper)
	var v := UI.vbox(5)
	paper.add_child(v)
	var top := UI.hbox(8)
	var brand := UI.vbox(0)
	brand.add_child(UI.label(Game.dealer_name.to_upper(), 15, PAPER_RED, true))
	brand.add_child(UI.label("1500 Coast Hwy · Tewport Beach, Canioria", 10, PAPER_INK))
	top.add_child(brand)
	top.add_child(UI.spacer())
	var title := "RETAIL INSTALLMENT SALE CONTRACT" if sale.financed else "VEHICLE PURCHASE CONTRACT (CASH)"
	var tv := UI.vbox(0)
	tv.add_child(UI.label(title, 17, PAPER_INK, true))
	tv.add_child(UI.label("Form CN-553 (Rev. 10/26) · Contract No. %d-%04d" % [Game.day, car.id], 10, PAPER_INK))
	top.add_child(tv)
	v.add_child(top)
	var r1 := UI.hbox(0)
	r1.add_child(_pbox("Buyer's name", _field_val("buyer"), "buyer", 250))
	r1.add_child(_pbox("Co-buyer", "None"))
	r1.add_child(_pbox("Seller / creditor", Game.dealer_name + ", Tewport Beach"))
	v.add_child(r1)
	var r2 := UI.hbox(0)
	r2.add_child(_pbox("New/Used", "USED", "", 60))
	r2.add_child(_pbox("Year", str(car.year), "", 50))
	r2.add_child(_pbox("Make / model", car.model, "", 150))
	r2.add_child(_pbox("Odometer", _field_val("odometer"), "odometer", 90))
	r2.add_child(_pbox("Vehicle identification number", _vin(car), "", 200))
	v.add_child(r2)
	var bar := ColorRect.new()
	bar.color = PAPER_INK
	bar.custom_minimum_size = Vector2(0, 20)
	var bl := UI.label("  FEDERAL TRUTH-IN-LENDING DISCLOSURES" if sale.financed else "  PRICE DISCLOSURE", 12, PAPER, true)
	bar.add_child(bl)
	v.add_child(bar)
	var r3 := UI.hbox(0)
	var price := _field_val("price")
	if sale.financed:
		var apr: float = float(_field_val("apr"))
		var pay := _payment(c.price, c.apr, c.term)
		r3.add_child(_pbox("Annual percentage rate", "%s %%" % _field_val("apr"), "apr", 0, true))
		r3.add_child(_pbox("Finance charge", Game.money_str(pay * c.term - c.price), "", 0, true))
		r3.add_child(_pbox("Amount financed", price, "price", 0, true))
		r3.add_child(_pbox("Total of payments", Game.money_str(_payment(c.price, apr, c.term) * c.term), "", 0, true))
		v.add_child(r3)
		var r4 := UI.hbox(0)
		r4.add_child(_pbox("Payment schedule", "%d payments of %s, monthly" % [c.term, Game.money_str(_payment(c.price, apr, c.term))]))
		r4.add_child(_pbox("Late charge", "5% of the late amount"))
		v.add_child(r4)
	else:
		r3.add_child(_pbox("Cash price of vehicle", price, "price", 0, true))
		r3.add_child(_pbox("Document fee", "$85", "", 0, true))
		r3.add_child(_pbox("Sales tax (paid to state)", "7.75%", "", 0, true))
		v.add_child(r3)
	# itemization, like the back half of a real retail installment contract
	var item := UI.hbox(14)
	item.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var lcol := UI.vbox(1)
	lcol.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lcol.add_child(UI.label("ITEMIZATION OF AMOUNT FINANCED", 12, PAPER_INK, true))
	var warranty := 1200 if (sale.addons.warranty or sale.addons.pack) else 0
	var protect := 400 if sale.addons.protect else 0
	var tax := int(c.price * 0.0775)
	for row in [["1. Cash price of vehicle", price], ["   A. Document processing charge (not a gov't fee)", "$85"],
			["   B. Emissions testing charge", "$50"], ["   C. Service contract, paid to %s Warranty Co." % Game.dealer_name, Game.money_str(warranty) if warranty > 0 else "$ ______"],
			["   D. Surface protection product", Game.money_str(protect) if protect > 0 else "$ ______"],
			["   E. Sales tax (7.75%)", Game.money_str(tax)], ["2. Amounts paid to public officials (license, registration)", "$412"],
			["3. Total down payment (trade-in, cash, rebate)", "$0"]]:
		var rr := UI.hbox(4)
		var nl := UI.label(row[0], 12, PAPER_INK)
		nl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		nl.clip_text = true
		rr.add_child(nl)
		rr.add_child(UI.label(row[1], 12, Color(0.1, 0.15, 0.45)))
		lcol.add_child(rr)
		lcol.add_child(_dots())
	item.add_child(lcol)
	var rcol := UI.vbox(4)
	rcol.custom_minimum_size = Vector2(290, 0)
	rcol.add_child(UI.label("STATEMENT OF INSURANCE", 12, PAPER_INK, true))
	rcol.add_child(UI.label("No person is required, as a condition of financing the purchase of a motor vehicle, to purchase or negotiate any insurance through a particular insurance company, agent or broker.", 10, PAPER_INK, false, true))
	var stop := UI.panel(PAPER, PAPER_INK, 6)
	var sv0 := UI.vbox(1)
	stop.add_child(sv0)
	sv0.add_child(UI.label("STOP AND READ", 13, PAPER_INK, true))
	sv0.add_child(UI.label("You cannot be required to buy a GAP waiver, service contract or any optional add-on product to get financing. It is unlawful to require the purchase of any optional add-on product.", 10, PAPER_INK, false, true))
	rcol.add_child(stop)
	item.add_child(rcol)
	v.add_child(item)
	var fine := UI.label("THERE IS NO COOLING-OFF PERIOD. Canioria law does not give you a right to cancel this contract after you sign it. Optional add-on products are not required to buy this vehicle or to get financing.", 10, PAPER_RED, true, true)
	v.add_child(fine)
	var sigs := UI.hbox(16)
	sigs.add_child(_sig_box("Buyer's signature", "buyer"))
	sigs.add_child(_sig_box("Seller's signature", "seller"))
	sigs.add_child(_sig_box("Odometer certification", "odometer"))
	v.add_child(sigs)
	v.add_child(UI.label("Tap any box that doesn't match the deal to correct it before signing.", 12, Color(0.35, 0.35, 0.4)))
	# ---------- deal jacket ----------
	var side := UI.panel(Color(0.04, 0.07, 0.13, 0.98), UI.GOLD, 14)
	side.custom_minimum_size = Vector2(330, 0)
	h.add_child(side)
	var sv := UI.vbox(7)
	side.add_child(sv)
	sale.time_label = UI.label("Buyer patience: %ds" % int(sale.time), 18, UI.BAD, true)
	sv.add_child(sale.time_label)
	sv.add_child(UI.label("Deal jacket (what you agreed)", 16, UI.GOLD, true))
	var deal := "%s · %d %s\n%s mi on the dash\nBuyer %s, ID checked" % [Game.money_str(c.price), car.year, car.model, _num(car.miles), c.name]
	if sale.financed:
		deal += "\n%.1f%% APR, %d months" % [c.apr, c.term]
	else:
		deal += "\nPaying cash"
	sv.add_child(UI.para(deal, 15))
	_meter(sv, "Happiness", c.happiness)
	sv.add_child(UI.label("Add-ons", 16, UI.GOLD, true))
	for a in [["warranty", "Offer extended warranty (+$1,200)"], ["protect", "Offer paint protection (+$400)"], ["pack", "Slip the warranty into the payment without mentioning it"]]:
		var cb := CheckBox.new()
		cb.text = a[1]
		cb.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		cb.custom_minimum_size = Vector2(300, 0)
		cb.add_theme_font_size_override("font_size", 14)
		cb.button_pressed = sale.addons[a[0]]
		cb.toggled.connect(func(on):
			sale.addons[a[0]] = on
			_render_paperwork())
		sv.add_child(cb)
	sv.add_child(UI.para("Each pitch costs a little happiness. The sneaky one pays for sure, but it's how dealers get sued.", 12, UI.MUTED))
	sv.add_child(UI.spacer())
	var all_signed: bool = sale.signed.values().all(func(x): return x)
	var done := UI.gold_button("Hand over the keys", _finish_paperwork, 0, 52)
	done.disabled = not all_signed
	sv.add_child(done)


func _finish_paperwork() -> void:
	var s := sale
	sale = {}
	var c: Dictionary = s.customer
	var car: Dictionary = s.car
	var addon_total := 0
	var vals := {"warranty": 1200, "protect": 400}
	for k in ["warranty", "protect"]:
		if s.addons[k]:
			c.happiness -= 0.05
			if randf() < 0.25 + c.happiness * 0.45:
				addon_total += vals[k]
	var notes := []
	var costs: int = -c.get("extras", 0)
	# anything shady you leave in the deal can come back as a lawsuit
	if s.addons.pack:
		addon_total += 1200
		Game.add_liability(c.name, "a warranty slipped into their payment", 0.45, 10000)
		notes.append("Slipping the warranty in pays %s today, but if %s reads the contract we're getting sued." % [Game.money_str(1200), c.name])
	match s.error:
		"price":
			var diff: int = c.price - int(s.fields.price.bad.replace("$", "").replace(",", ""))
			costs -= diff
			notes.append("You signed the wrong price. We ate the %s difference." % Game.money_str(diff))
		"odometer":
			Game.add_liability(c.name, "a wrong odometer reading (odometer fraud)", 0.6, 15000)
			notes.append("The odometer number on that contract was wrong. That's odometer fraud if they notice.")
		"buyer":
			Game.add_liability(c.name, "a sale without checking ID", 0.3, 6000)
			notes.append("We sold a car without checking ID. Lawyers love that.")
		"apr":
			Game.add_liability(c.name, "a contract APR that didn't match the deal", 0.5, 9000)
			notes.append("The contract showed a higher APR than we quoted. Truth-in-lending violation.")
	if car.history != "Clean" and not ("history" in c.get("used", [])):
		Game.add_liability(c.name, "an undisclosed %s history" % car.history.to_lower(), 0.3, 6000)
		notes.append("You never told them about the %s history. That can come back on us." % car.history.to_lower())
	if Game.hidden_total(car) > 0:
		Game.add_liability(c.name, "hidden mechanical problems", 0.4, 2000 + Game.hidden_total(car) * 80)
		notes.append("That car still had a hidden problem. Expect an angry call, maybe a lawyer.")
	lobby.erase(c)
	customer = {}
	_close_overlay()
	_complete_sale(car, {"sales": s.price, "finance": c.get("reserve", 0), "addons": addon_total, "other": costs},
		c.happiness, "you", {"customer": c.name, "cust": c, "reserve": c.get("reserve", 0), "notes": notes})


# =====================================================================
# Completing a sale
# =====================================================================

func _complete_sale(car: Dictionary, income: Dictionary, happiness: float, seller: String, info := {}) -> void:
	var total := 0
	for k in income:
		if income[k] != 0:
			if income[k] > 0:
				Game.earn(income[k], k)
			else:
				Game.money += income[k]
				Game.log_money(k, income[k])
			total += income[k]
	var price: int = income.get("sales", 0)
	var profit: int = total - car.paid - car.spent
	Game.stats.sold += 1
	Game.month_sold += 1
	Game.stats.goal_sold_today += 1
	Game.stats.profit += profit
	Game.stats.days_held += Game.day - car.day_bought
	var stars := Game.stars_from_happiness(happiness)
	Game.add_review(info.get("cust", {"name": info.get("customer", "Customer")}), stars, car.model, seller if seller != "you" else "")
	info.review = stars
	Game.remove_car(car)
	var leveled := Game.add_xp(Game.sale_xp(profit))
	Game.save_game()
	if seller != "you":
		toast("%s sold the %s to %s for %s. Profit %s. %d★ review." % [seller, car.model, info.get("customer", "a customer"), Game.money_str(price), Game.money_str(profit), info.review])
		if leveled:
			play_dialogue([["Marco", "CEO & Financial Advisor", "You hit Level %d. %s" % [Game.level, _unlock_text()]]], _back_to_current)
		elif current == "showroom" and lobby_stage:
			_build_lobby(lobby_stage)
		return
	var summary := "Sold the %s to %s for %s." % [car.model, info.get("customer", "the buyer"), Game.money_str(price)]
	if info.get("reserve", 0) > 0:
		summary += " Finance profit %s." % Game.money_str(info.reserve)
	summary += " Total profit: %s. They left %s." % [Game.money_str(profit), _mood_word(happiness).to_lower()]
	summary += " They gave us %d★ on Yolp." % info.review
	if info.review == 5:
		summary += " And they're sending a friend tomorrow."
	var reaction := "Not bad. Keep that margin up."
	if profit > 5000 and happiness >= 0.5:
		reaction = "Big margin AND a happy customer. That's how we do it at %s." % Game.dealer_name
	elif profit > 5000:
		reaction = "Big margin, but that customer won't send their friends."
	elif profit < 0:
		reaction = "We lost money on that one. Buy smarter or fix smarter."
	if current == "showroom" and lobby_stage:
		_build_lobby(lobby_stage)
	var m := ["Marco", "CEO & Financial Advisor"]
	var lines := [m + [summary + " " + reaction]]
	for n in info.get("notes", []):
		lines.append(m + [n])
	if leveled:
		lines.append(m + ["You hit Level %d. %s" % [Game.level, _unlock_text()]])
	play_dialogue(lines, _back_to_current)



func _back_to_current() -> void:
	show_screen(current if current != "title" else "lot")


func _unlock_text() -> String:
	var bits := []
	for m in Game.MECHANICS:
		if m.level == Game.level:
			bits.append("%s is now available in the garage" % m.name)
	for p in Game.PERKS:
		if p.level == Game.level:
			bits.append("you unlocked my %s perk" % p.name)
	if bits.is_empty():
		var cap: int = Game.dealership_info().max_car
		if cap > 0 and Game.max_auction_base() >= cap:
			return "Auctions won't send anything pricier to a %s. Move up to see the good stuff." % Game.dealership_info().name
		return "Pricier cars will start showing up at auction."
	var text: String = ", and ".join(bits)
	return text.substr(0, 1).to_upper() + text.substr(1) + "."


# =====================================================================
# Marco
# =====================================================================

func _screen_marco() -> void:
	set_bg("office", 0.15)
	# Marco (rendered from his 3D model, tools/marco_glb.py) stands in his office in the gap between the two panels
	var stage := Control.new()
	stage.mouse_filter = Control.MOUSE_FILTER_IGNORE
	content.add_child(stage)
	var hero := "res://assets/people/marco_hero.png"
	var man := TextureRect.new()
	man.texture = load(hero) if ResourceLoader.exists(hero) else load("res://assets/people/marco_body.png")
	man.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	man.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT
	man.mouse_filter = Control.MOUSE_FILTER_IGNORE
	stage.add_child(man)
	var place := func():
		var ts: Vector2 = man.texture.get_size()
		var hgt: float = stage.size.y + 30.0
		var w: float = hgt * ts.x / ts.y
		man.size = Vector2(w, hgt)
		man.position = Vector2((stage.size.x - w) / 2.0 + 10.0, 4.0)
	stage.resized.connect(place)
	place.call_deferred()
	var h := UI.hbox(16)
	content.add_child(h)
	# ----- left: the team, Marco highlighted -----
	var lp := _glass_panel()
	lp.custom_minimum_size = Vector2(330, 0)
	lp.size_flags_vertical = Control.SIZE_EXPAND_FILL
	h.add_child(lp)
	var lv := UI.vbox(7)
	lp.add_child(lv)
	lv.add_child(UI.label("MARCO · CEO ADVISOR", 26, UI.TEXT, true))
	lv.add_child(UI.rule(Color(UI.GOLD, 0.35)))
	lv.add_child(_team_row("marco", "Marco", "CEO & Financial Advisor", true, func(): play_dialogue(_marco_tips(), func(): pass)))
	for s in Game.staff:
		lv.add_child(_team_row(Game.staff_pid(s), s.name, "%s · %s" % [_staff_role(s), _stars(s.stars)], false, show_screen.bind("staff")))
	if Game.staff.size() < 5:
		lv.add_child(_team_row("", "Open position", "Hire on StaffHire", false, func():
			pc_tab = "staff"
			show_screen("pc")))
	lv.add_child(UI.spacer())
	lv.add_child(_mini_goals())
	h.add_child(UI.spacer())
	# ----- right: stats and perks -----
	var rcol := UI.vbox(12)
	rcol.custom_minimum_size = Vector2(350, 0)
	h.add_child(rcol)
	var sp := _glass_panel()
	rcol.add_child(sp)
	var sv := UI.vbox(8)
	sp.add_child(sv)
	sv.add_child(UI.label("STATUS & STATS", 20, UI.TEXT, true))
	var s: Dictionary = Game.stats
	var conv: float = 0.0 if s.buyers == 0 else 100.0 * s.sold / s.buyers
	var avg_days: float = 0.0 if s.sold == 0 else float(s.days_held) / s.sold
	var eff: float = clamp(50.0 + s.profit / 500.0, 0.0, 100.0)
	_icon_stat(sv, "efficiency", "Dealership efficiency", "%d%%" % int(eff), eff)
	_icon_stat(sv, "conversion", "Sales conversion rate", "%d%%" % int(conv), conv)
	_icon_stat(sv, "calendar", "Inventory duration", "%.1f days" % avg_days, clamp(100 - avg_days * 15, 0, 100))
	_icon_stat(sv, "smile", "Client satisfaction", "%.1f/5" % Game.reputation, Game.reputation * 20)
	var pp := _glass_panel()
	rcol.add_child(pp)
	var pv := UI.vbox(8)
	pp.add_child(pv)
	pv.add_child(UI.label("ADVISOR PERKS", 20, UI.TEXT, true))
	var perk_icons := {"sourcing": "globe", "vip": "handshake", "insights": "insights"}
	for perk in Game.PERKS:
		var on: bool = Game.level >= perk.level
		var r := UI.hbox(10)
		r.add_child(_icon_box(perk_icons.get(perk.id, "star"), on))
		var t := UI.vbox(0)
		t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		t.add_child(UI.label(perk.name.to_upper() + ("" if on else "  ·  LVL %d" % perk.level), 15, UI.TEXT if on else UI.MUTED, true))
		t.add_child(UI.label(perk.desc, 12, UI.GOLD if on else UI.MUTED, false, true))
		r.add_child(t)
		pv.add_child(r)
	rcol.add_child(UI.spacer())
	var acts := UI.hbox(8)
	rcol.add_child(acts)
	var ask := UI.gold_button("Ask Marco", func(): play_dialogue(_marco_tips(), func(): pass), 0, 46)
	_with_icon(ask, "chat")
	ask.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	acts.add_child(ask)
	var team := UI.button("Team", show_screen.bind("staff"), 0, 46)
	_with_icon(team, "staff")
	team.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	acts.add_child(team)


func _with_icon(b: Button, name: String, px := 24) -> void:
	b.icon = icon_tex(name)
	b.add_theme_constant_override("icon_max_width", px)
	b.add_theme_constant_override("h_separation", 8)


## White line icons in assets/icons, tinted by the node that shows them.
static func icon_tex(name: String) -> Texture2D:
	var p := "res://assets/icons/%s.svg" % name
	return load(p) if ResourceLoader.exists(p) else null


func _icon(name: String, px := 24, tint := UI.GOLD) -> TextureRect:
	var t := TextureRect.new()
	t.texture = icon_tex(name)
	t.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	t.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	t.custom_minimum_size = Vector2(px, px)
	t.modulate = tint
	t.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return t


## Gold-edged square holding an icon, as in the advisor screens.
func _icon_box(name: String, lit := true, px := 44) -> PanelContainer:
	var b := PanelContainer.new()
	var sb := UI.box(Color(0, 0, 0, 0.35), Color(UI.GOLD if lit else UI.MUTED, 0.6), 6, 1, 6)
	b.add_theme_stylebox_override("panel", sb)
	b.custom_minimum_size = Vector2(px, px)
	b.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	b.add_child(_icon(name, px - 16, UI.GOLD if lit else UI.MUTED))
	return b


## Smoked glass panel with a warm rim.
func _glass_panel() -> PanelContainer:
	var p := PanelContainer.new()
	var sb := UI.box(Color(0.05, 0.06, 0.08, 0.72), Color(1, 0.85, 0.6, 0.35), 12, 1, 16)
	sb.shadow_color = Color(0, 0, 0, 0.35)
	sb.shadow_size = 10
	p.add_theme_stylebox_override("panel", sb)
	return p


func _icon_stat(parent: Control, icon: String, name: String, val: String, pct: float) -> void:
	var r := UI.hbox(10)
	r.add_child(_icon_box(icon))
	var v := UI.vbox(4)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var top := UI.hbox(6)
	top.add_child(UI.label(name.to_upper(), 14, UI.TEXT, true))
	top.add_child(UI.spacer())
	top.add_child(UI.label(val, 15, UI.GOLD, true))
	v.add_child(top)
	v.add_child(UI.bar(pct, 100, UI.GOLD, 7))
	r.add_child(v)
	parent.add_child(r)


## One row of the team list: portrait thumbnail, name, role.
func _team_row(pid: String, name: String, role: String, selected: bool, cb: Callable) -> Control:
	var b := Button.new()
	b.custom_minimum_size = Vector2(0, 58)
	b.focus_mode = Control.FOCUS_NONE
	var base := UI.box(Color(0.12, 0.13, 0.16, 0.75), Color(1, 1, 1, 0.12), 6, 1, 4)
	var hot := UI.box(Color(0.2, 0.2, 0.22, 0.85), Color(UI.GOLD, 0.6), 6, 1, 4)
	var sel := UI.box(Color(0.55, 0.42, 0.18, 0.9), UI.GOLD, 6, 2, 4)
	sel.shadow_color = Color(UI.GOLD, 0.45)
	sel.shadow_size = 8
	b.add_theme_stylebox_override("normal", sel if selected else base)
	b.add_theme_stylebox_override("hover", sel if selected else hot)
	b.add_theme_stylebox_override("pressed", sel)
	b.pressed.connect(cb)
	var r := UI.hbox(10)
	r.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	r.offset_left = 6
	r.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(r)
	var th: TextureRect = _face_rect(pid, true) if pid != "" else TextureRect.new()
	th.custom_minimum_size = Vector2(48, 48)
	th.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	th.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	th.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	th.mouse_filter = Control.MOUSE_FILTER_IGNORE
	if pid != "":
		th.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	else:
		th.texture = icon_tex("staff")
		th.modulate = UI.MUTED
		th.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	r.add_child(th)
	var t := UI.vbox(0)
	t.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	t.mouse_filter = Control.MOUSE_FILTER_IGNORE
	t.add_child(UI.label(name.to_upper(), 17, Color.WHITE if selected else UI.TEXT, true))
	t.add_child(UI.label(role, 12, Color(1, 0.93, 0.8) if selected else UI.MUTED))
	r.add_child(t)
	return b


## Portrait for a person: the painted card art for Marco and Maruchan, otherwise the top of the rendered body.
## thumb = head and shoulders only.
func _person_tex(pid: String, thumb := false) -> Texture2D:
	var portrait := "res://assets/people/%s_portrait.png" % pid
	if ResourceLoader.exists(portrait):
		var pt: Texture2D = load(portrait)
		if not thumb:
			return pt
		var pa := AtlasTexture.new()
		pa.atlas = pt
		pa.region = Rect2(pt.get_width() * 0.15, 0, pt.get_width() * 0.7, pt.get_width() * 0.7)
		return pa
	var card := "res://assets/people/%s_card.png" % pid
	if ResourceLoader.exists(card):
		var ct: Texture2D = load(card)
		if not thumb:
			return ct
		var ca := AtlasTexture.new()
		ca.atlas = ct
		ca.region = Rect2(ct.get_width() * 0.2, 0, ct.get_width() * 0.6, ct.get_width() * 0.6)
		return ca
	var body := "res://assets/people/%s_body.png" % pid
	if ResourceLoader.exists(body):
		var bt: Texture2D = load(body)
		var w := float(bt.get_width())
		var a := AtlasTexture.new()
		a.atlas = bt
		a.region = Rect2(w * 0.12, 0, w * 0.76, w * 0.76) if thumb else Rect2(0, 0, w, w * 1.15)
		return a
	var face := "res://assets/people/%s_face_neutral.png" % pid
	return load(face) if ResourceLoader.exists(face) else null


## Round-cornered head-and-shoulders thumbnail from the person's one portrait.
func _thumb(pid: String, px := 40) -> Control:
	var f := PanelContainer.new()
	f.add_theme_stylebox_override("panel", UI.box(Color(0.1, 0.16, 0.22), Color(1, 1, 1, 0.2), 4, 1, 1))
	f.custom_minimum_size = Vector2(px, px)
	f.clip_contents = true
	f.add_child(_face_rect(pid, true))
	return f


## Which person's portrait goes with a speaker's name in dialogue.
func _speaker_pid(speaker: String) -> String:
	match speaker:
		"Marco", "Maruchan", "Amna", "Jeff":
			return speaker.to_lower()
	for s in Game.staff:
		if s.name == speaker:
			return Game.staff_pid(s)
	return PersonArt.pool_pid(speaker.length() * 7, speaker)


func _staff_role(s: Dictionary) -> String:
	match s.get("look", ""):
		"jeff": return "Sales Associate"
		"maruchan": return "Leasing & VIP Relations"
		"amna": return "Finance & Insurance"
	return "Salesperson"


## Goals in a compact list under the team.
func _mini_goals() -> Control:
	var v := UI.vbox(3)
	var hd := UI.hbox(6)
	hd.add_child(_icon("goals", 18))
	hd.add_child(UI.label("GOALS · " + Game.dealership_info().name.to_upper(), 13, UI.GOLD, true))
	v.add_child(hd)
	for g in Game.goals():
		var done: bool = g[1]
		v.add_child(UI.label(("✓ " if done else "○ ") + g[0], 13, UI.GOOD if done else UI.TEXT, false, true))
	var today: bool = Game.stats.goal_sold_today >= 1
	v.add_child(UI.label(("✓ " if today else "○ ") + "Today: sell a car (+$500, +25 XP)", 13, UI.GOOD if today else UI.MUTED, false, true))
	return v


# =====================================================================
# Staff: the team as tall cards
# =====================================================================

const MARCO_CARD := {"name": "Marco", "role": "CEO Advisor", "stats": [["handshake", "Negotiation", 95], ["bank", "Finance", 98], ["insights", "Market insight", 92]]}
const SKILL_ICONS := {"closing": "handshake", "rapport": "smile", "finance": "bank", "upsell": "conversion"}


func _screen_staff() -> void:
	set_bg("showroom", 0.55)
	var v := UI.vbox(12)
	content.add_child(v)
	var head := UI.hbox(10)
	v.add_child(head)
	head.add_child(_icon("staff", 30))
	head.add_child(UI.label("YOUR TEAM", 30, UI.TEXT, true))
	head.add_child(UI.label("%d of 5 salespeople" % Game.staff.size(), 16, UI.MUTED))
	head.add_child(UI.spacer())
	var hire := UI.gold_button("Hire on StaffHire", func():
		pc_tab = "staff"
		show_screen("pc"), 0, 44)
	_with_icon(hire, "staff")
	head.add_child(hire)
	var row := UI.hbox(12)
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	var sc := UI.scroll(row)
	sc.size_flags_vertical = Control.SIZE_EXPAND_FILL
	sc.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	sc.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	v.add_child(sc)
	row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var stats := []
	for st in MARCO_CARD.stats:
		stats.append(st)
	row.add_child(_tall_card("marco", MARCO_CARD.name, MARCO_CARD.role, stats, UI.GOLD, "Runs the books. Not for hire, not for firing.", null))
	for s in Game.staff:
		var ss := []
		for k in Game.SKILLS:
			ss.append([SKILL_ICONS[k], Game.SKILL_NAMES[k], Game.skill(s, k)])
		var accent: Color = UI.GOLD if s.stars >= 4.5 else CARD_CYAN
		var foot := "%s a month · %d sold · closes ~%d%%" % [Game.money_str(s.salary), s.get("sales", 0), int(Game.staff_close_chance(s) * 100)]
		var act: Variant = null
		if not s.fixed:
			act = _small_btn("Let go", func():
				Game.staff.erase(s)
				Game.save_game()
				toast("%s has left the dealership." % s.name)
				show_screen("staff"))
		row.add_child(_tall_card(Game.staff_pid(s), s.name, "%s · %s" % [_staff_role(s), s.trait], ss, accent, foot, act, s.stars))


## A tall team card: big portrait over a glow, name, role, stat rows with icons, footer.
func _tall_card(pid: String, name: String, role: String, stats: Array, accent: Color, foot: String, action: Variant, stars := -1.0) -> Control:
	var card := PanelContainer.new()
	var sb := UI.box(Color(0.04, 0.07, 0.11, 0.9), Color(accent, 0.85), 12, 2, 10)
	sb.shadow_color = Color(accent, 0.45)
	sb.shadow_size = 12
	card.add_theme_stylebox_override("panel", sb)
	card.custom_minimum_size = Vector2(196, 0)
	var v := UI.vbox(5)
	card.add_child(v)
	var frame := PanelContainer.new()
	frame.add_theme_stylebox_override("panel", UI.box(Color(0.08, 0.14, 0.2), Color(accent, 0.5), 8, 1, 2))
	frame.custom_minimum_size = Vector2(176, 210)
	frame.clip_contents = true
	var glow := GlowBack.new()
	glow.accent = accent
	frame.add_child(glow)
	frame.add_child(_face_rect(pid))
	v.add_child(frame)
	v.add_child(UI.label(name.to_upper(), 24, Color.WHITE, true))
	v.add_child(UI.label(role, 12, accent, true, true))
	if stars >= 0:
		v.add_child(UI.label(_stars(stars), 14, UI.GOLD))
	for st in stats:
		var r := UI.hbox(6)
		r.add_child(_icon(st[0], 16, accent))
		var col := UI.vbox(1)
		col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var top := UI.hbox(4)
		top.add_child(UI.label(st[1], 11, CARD_MUTED))
		top.add_child(UI.spacer())
		top.add_child(UI.label("%d%%" % st[2], 11, CARD_TEXT, true))
		col.add_child(top)
		col.add_child(UI.bar(st[2], 100, accent, 5))
		r.add_child(col)
		v.add_child(r)
	v.add_child(UI.spacer())
	v.add_child(UI.label(foot, 11, CARD_MUTED, false, true))
	if action != null:
		v.add_child(action)
	return card


## The whiteboard on the office wall: goals for the current dealership.
func _goals_board() -> Control:
	var wb := UI.panel(Color(0.95, 0.95, 0.93, 0.95), Color(0.55, 0.57, 0.6), 16)
	wb.custom_minimum_size = Vector2(300, 0)
	wb.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
	var v := UI.vbox(6)
	wb.add_child(v)
	v.add_child(UI.label("GOALS", 24, Color(0.12, 0.15, 0.3), true))
	v.add_child(UI.label(Game.dealership_info().name, 13, Color(0.35, 0.37, 0.45)))
	for g in Game.goals():
		var done: bool = g[1]
		v.add_child(UI.label(("☑ " if done else "☐ ") + g[0], 17, Color(0.12, 0.45, 0.2) if done else Color(0.12, 0.15, 0.3)))
	v.add_child(UI.rule(Color(0.55, 0.57, 0.6)))
	var today: bool = Game.stats.goal_sold_today >= 1
	v.add_child(UI.label(("☑ " if today else "☐ ") + "Today: sell a car (+$500, +25 XP)", 15, Color(0.12, 0.45, 0.2) if today else Color(0.35, 0.37, 0.45)))
	return wb


# =====================================================================
# Home: the apartment on the showroom roof
# =====================================================================

func _screen_home() -> void:
	set_bg("apartment%d" % Game.apartment, 0.0)
	if sleeping:
		bg.modulate = Color(0.3, 0.36, 0.6)
	var h := UI.hbox(16)
	content.add_child(h)
	var rows := [["sleep", "Sleep (end the day)", _wake_up if sleeping else _close_for_night],
		["pc", "Computer (Office PC)", show_screen.bind("pc")],
		["lot", "Go to the dealership", show_screen.bind("lot")],
		["marco", "Call Marco", func(): play_dialogue(_marco_tips(), func(): pass)]]
	h.add_child(_menu_panel(Game.apartment_info().name.to_upper(), rows))
	h.add_child(UI.spacer())
	var p := _glass_panel()
	p.custom_minimum_size = Vector2(430, 0)
	p.size_flags_vertical = Control.SIZE_SHRINK_END
	h.add_child(p)
	var v := UI.vbox(8)
	p.add_child(v)
	var cur := Game.apartment_info()
	v.add_child(UI.label("HOME · TEWPORT BEACH", 13, UI.GOLD, true))
	v.add_child(UI.label(cur.name, 26, UI.TEXT, true))
	var stars := ""
	for i in Game.APARTMENTS.size():
		stars += "■ " if i < Game.apartment else "□ "
	v.add_child(UI.label(stars.strip_edges(), 16, UI.GOLD))
	v.add_child(UI.para(cur.desc, 14, UI.MUTED))
	if cur.monthly > 0:
		v.add_child(UI.label("Upkeep %s a month (added to your bills)" % Game.money_str(cur.monthly), 13, UI.BLUE))
	if sleeping:
		v.add_child(UI.rule(UI.GOLD_DIM))
		v.add_child(UI.para("Lights off at the dealership. Tomorrow is %s." % Game.date_str(), 15))
		v.add_child(UI.gold_button("Sleep until 8:00 AM", _wake_up, 0, 52))
	else:
		v.add_child(UI.gold_button("Sleep (close the dealership for today)", _close_for_night, 0, 48))
	if Game.apartment < Game.APARTMENTS.size():
		var nxt := Game.apartment_info(Game.apartment + 1)
		v.add_child(UI.rule(UI.GOLD_DIM))
		v.add_child(UI.label("NEXT UPGRADE", 13, UI.GOLD, true))
		v.add_child(UI.label(nxt.name, 19, UI.TEXT, true))
		v.add_child(UI.para(nxt.desc, 13, UI.MUTED))
		var afford: bool = Game.money >= nxt.price
		var b := UI.gold_button("Move in · %s" % Game.money_str(nxt.price), func():
			if Game.upgrade_apartment():
				toast("Welcome home: %s." % nxt.name)
				show_screen("home")
			else:
				toast("You need %s for that." % Game.money_str(nxt.price)), 0, 46)
		b.disabled = not afford
		v.add_child(b)
	else:
		v.add_child(UI.label("You own the best address in Tewport Beach.", 14, UI.GOOD))


func _stat_row(parent: Control, name: String, val: String, pct: float) -> void:
	var r := UI.hbox(10)
	var l := UI.label(name, 16)
	l.custom_minimum_size = Vector2(200, 0)
	r.add_child(l)
	r.add_child(UI.bar(pct, 100, UI.GOLD, 10))
	var vl := UI.label(val, 16, UI.GOLD)
	vl.custom_minimum_size = Vector2(90, 0)
	vl.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	r.add_child(vl)
	parent.add_child(r)


func _marco_tips() -> Array:
	var t := []
	var who := "CEO & Financial Advisor"
	t.append(["Marco", who, "Market's telling me %s are moving today. Price them about 10%% higher and they'll still sell." % _class_name(Game.hot_class).to_lower()])
	var b := Game.monthly_bills()
	if Game.cars.is_empty() and Game.money < 5000 and Game.loan < Game.loan_limit():
		t.append(["Marco", who, "No cars and no cash. TewportBank on the PC will lend us up to %s. Borrow, buy something cheap at AutoBidz, sell it, pay them back." % Game.money_str(Game.loan_limit() - Game.loan)])
	elif Game.money < b.total:
		t.append(["Marco", who, "Bills on %s come to %s and we don't have it yet. Sell something." % [Game.next_bill_date(), Game.money_str(b.total)]])
	if Game.cars.size() >= Game.lot_capacity():
		t.append(["Marco", who, "Lot's full. A car sitting here is money sitting still. Sell something, even at a thinner margin."])
	if Game.ads_active.is_empty():
		t.append(["Marco", who, "Nobody knows we exist. Even flyers on windshields bring people in. Check AdSpace on your PC."])
	if Game.reputation < 2.5:
		t.append(["Marco", who, "Our reviews are slipping. Smaller margins make happier customers, and happy customers come back."])
	t.append(["Marco", who, ["Always pull the history report. A flood car looks fine until it doesn't.", "The finance office is where the money is. A point or two over the bank rate adds up.", "Detailing is the cheapest profit in this business.", "Squeeze too hard and they walk. A fair deal and a happy customer beats one big margin."].pick_random()])
	return t


# =====================================================================
# Dialogue, toasts, end of day
# =====================================================================

func play_dialogue(lines: Array, done: Callable) -> void:
	dialogue_queue = lines.duplicate()
	dialogue_done = done
	_show_next_line()


func _show_next_line() -> void:
	UI.clear(overlay)
	if dialogue_queue.is_empty():
		overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
		if dialogue_done.is_valid():
			dialogue_done.call()
		return
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	var line: Array = dialogue_queue.pop_front()
	var shade := ColorRect.new()
	shade.color = Color(0, 0, 0, 0.4)
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(shade)
	var wrap := Control.new()
	wrap.anchor_left = 0.2
	wrap.anchor_right = 0.8
	wrap.anchor_top = 1.0
	wrap.anchor_bottom = 1.0
	wrap.offset_top = -262
	wrap.offset_bottom = -92
	wrap.mouse_filter = Control.MOUSE_FILTER_STOP
	wrap.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	wrap.gui_input.connect(func(e):
		if e is InputEventMouseButton and e.pressed and e.button_index == MOUSE_BUTTON_LEFT:
			_show_next_line())
	overlay.add_child(wrap)
	var row := UI.hbox(14)
	row.set_anchors_preset(Control.PRESET_FULL_RECT)
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	wrap.add_child(row)
	var face := _portrait_frame(_speaker_pid(line[0]), 0.5, UI.DIALOG_RIM, 150)
	face.custom_minimum_size.x = 132
	face.size_flags_vertical = Control.SIZE_SHRINK_END
	face.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_child(face)
	var col := UI.vbox(6)
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_child(col)
	var box := PanelContainer.new()
	box.size_flags_vertical = Control.SIZE_EXPAND_FILL
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var sb := StyleBoxFlat.new()
	sb.bg_color = UI.DIALOG_NAVY
	sb.border_color = UI.DIALOG_RIM
	sb.set_border_width_all(1)
	sb.set_corner_radius_all(14)
	sb.shadow_color = Color(0, 0, 0, 0.35)
	sb.shadow_size = 10
	box.add_theme_stylebox_override("panel", sb)
	col.add_child(box)
	var v := UI.vbox(0)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_child(v)
	var head := PanelContainer.new()
	head.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var hs := StyleBoxFlat.new()
	hs.bg_color = UI.DIALOG_HEAD
	hs.corner_radius_top_left = 13
	hs.corner_radius_top_right = 13
	hs.content_margin_left = 18
	hs.content_margin_right = 14
	hs.content_margin_top = 6
	hs.content_margin_bottom = 6
	head.add_theme_stylebox_override("panel", hs)
	v.add_child(head)
	var hh := UI.hbox(8)
	head.add_child(hh)
	hh.add_child(UI.label("%s - %s" % [String(line[0]).to_upper(), _dialogue_role(line[0], line[1]).to_upper()], 17, Color.WHITE, true))
	hh.add_child(UI.spacer())
	hh.add_child(UI.label("★", 18, UI.GOLD, true))
	var bm := MarginContainer.new()
	bm.mouse_filter = Control.MOUSE_FILTER_IGNORE
	for k in ["left", "right"]:
		bm.add_theme_constant_override("margin_" + k, 20)
	bm.add_theme_constant_override("margin_top", 12)
	bm.add_theme_constant_override("margin_bottom", 14)
	v.add_child(bm)
	var text := UI.para(line[2], 18)
	text.add_theme_color_override("font_color", Color.WHITE)
	text.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bm.add_child(text)
	var cont := UI.label("Click to continue", 14, Color(0.85, 0.9, 1.0, 0.85))
	cont.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	cont.mouse_filter = Control.MOUSE_FILTER_IGNORE
	col.add_child(cont)


## The role shown in the dialogue header strip.
func _dialogue_role(speaker: String, given: String) -> String:
	match speaker:
		"Marco": return "CEO Advisor"
		"Jeff": return "Sales Associate"
		"Maruchan": return "Leasing & VIP"
		"Amna": return "Finance"
	for s in Game.staff:
		if s.name == speaker:
			return _staff_role(s)
	if given.to_lower().contains("customer") or given == "":
		return "Customer"
	return given


func toast(text: String) -> void:
	var p := UI.panel(Color(0.05, 0.08, 0.14, 0.95), UI.GOLD, 14)
	p.anchor_left = 0.5
	p.anchor_right = 0.5
	p.offset_left = -340
	p.offset_right = 340
	p.offset_top = 86
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var l := UI.para(text, 17)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	p.add_child(l)
	add_child(p)
	var tw := create_tween()
	tw.tween_interval(2.8)
	tw.tween_property(p, "modulate:a", 0.0, 0.4)
	tw.tween_callback(p.queue_free)


func _close_for_night() -> void:
	if closing or current == "title":
		return
	closing = true
	if not auction.is_empty():
		auction_timer = 0
		_finish_auction()
	var notes := []
	# customers still in the showroom go home
	if not lobby.is_empty():
		notes.append("%d customer%s still waiting when we locked up. Some of them went straight to Yolp." % [lobby.size(), "" if lobby.size() == 1 else "s"])
		for c in lobby:
			if randf() < 0.5:
				Game.add_review(c, 2, "", "", "Showed up before closing and they just locked the doors on me.")
		Game.month_walked += lobby.size()
		Game.stats.walked += lobby.size()
		lobby.clear()
	_close_overlay()
	customer = {}
	sale = {}
	var today := Game.date_str()
	var ledger: Dictionary = Game.ledger_day.duplicate()
	notes += Game.end_day()
	show_screen("lot")
	# the lot after dark
	bg.modulate = Color(0.32, 0.38, 0.6)
	_night_report(today, ledger, notes)


const LEDGER_NAMES := {"sales": "Car sales", "finance": "Finance profit", "addons": "Add-ons", "cars": "Auto acquisitions",
	"repairs": "Repairs & detailing", "shop": "Shop purchases", "ads": "Advertising", "rent": "Rent (lot & showroom)",
	"payroll": "Staff payroll", "legal": "Lawsuits & legal", "interest": "Loan interest", "other": "Other"}


func _money_row(parent: Control, name: String, amount: int, size := 16, bold := false) -> void:
	var h := UI.hbox()
	h.add_child(UI.label(name.to_upper(), size, UI.TEXT, bold))
	h.add_child(UI.spacer())
	h.add_child(UI.label(Game.money_str(amount), size, UI.GOOD if amount >= 0 else UI.BAD, bold))
	parent.add_child(h)


func _night_report(today: String, ledger: Dictionary, notes: Array) -> void:
	var p := _modal(UI.NAVY, 0)
	p.custom_minimum_size = Vector2(620, 0)
	var v := UI.vbox(8)
	p.add_child(v)
	v.add_child(UI.header("Closing report · %s · 9:00 PM" % today))
	var rev := Game.ledger_total(ledger, 1)
	var exp := Game.ledger_total(ledger, -1)
	_money_row(v, "Daily revenue", rev)
	_money_row(v, "Daily expenses", exp)
	v.add_child(UI.rule())
	_money_row(v, "Net profit", rev + exp, 18, true)
	_money_row(v, "Total funds", Game.money, 18, true)
	var exposure := Game.legal_exposure()
	if exposure > 0:
		v.add_child(UI.label("Pending legal risk from shady deals: about %s" % Game.money_str(exposure), 15, UI.BAD))
	for n in notes:
		v.add_child(UI.para(n, 15, UI.BAD if n.begins_with("LAWSUIT") or n.begins_with("BANKRUPT") or n.begins_with("BILLS") else UI.MUTED))
	var next := UI.gold_button("Acknowledge", func():
		if not Game.last_month_report.is_empty():
			_month_report(Game.last_month_report)
		else:
			_night_done(), 0, 48)
	v.add_child(next)


func _month_report(r: Dictionary) -> void:
	var p := _modal(UI.NAVY, 0)
	p.custom_minimum_size = Vector2(700, 0)
	var v := UI.vbox(6)
	p.add_child(v)
	v.add_child(UI.header("End of month financial summary · %s" % r.title))
	var l: Dictionary = r.ledger
	var rev := Game.ledger_total(l, 1)
	_money_row(v, "Monthly revenue", rev, 17, true)
	for k in ["rent", "payroll", "ads", "interest", "cars", "repairs", "shop", "legal", "other"]:
		if l.get(k, 0) != 0:
			_money_row(v, LEDGER_NAMES[k], l[k])
	var alert := UI.panel(Color(0.35, 0.06, 0.06, 0.9), UI.BAD, 10)
	alert.add_child(UI.para("MONTHLY RENT DEDUCTION: rent for the showroom and lot (%s) was debited from your account." % Game.money_str(-l.get("rent", 0)), 14))
	v.add_child(alert)
	var net_amt := rev + Game.ledger_total(l, -1)
	var net := UI.panel(Color(0.08, 0.3, 0.15, 0.9) if net_amt >= 0 else Color(0.3, 0.07, 0.07, 0.9), UI.GOOD if net_amt >= 0 else UI.BAD, 10)
	var nv := UI.vbox(0)
	net.add_child(nv)
	_money_row(nv, "Monthly net profit", net_amt, 19, true)
	v.add_child(net)
	var cols := UI.hbox(12)
	var a := UI.vbox(4)
	a.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	a.add_child(UI.label("CLIENT FEEDBACK", 14, UI.GOLD, true))
	a.add_child(UI.label("Cars sold: %d" % r.sold, 15))
	a.add_child(UI.label("Walked-out customers: %d" % r.walked, 15, UI.BAD if r.walked > 0 else UI.TEXT))
	cols.add_child(a)
	var b := UI.vbox(4)
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	b.add_child(UI.label("DEALERSHIP REPUTATION", 14, UI.GOLD, true))
	b.add_child(UI.label("%s %.1f" % [UI.stars(r.reputation), r.reputation], 18, UI.GOLD))
	b.add_child(UI.label("Total funds %s" % Game.money_str(r.money), 15))
	cols.add_child(b)
	v.add_child(cols)
	v.add_child(UI.gold_button("Acknowledge", _night_done, 0, 48))


func _night_done() -> void:
	_close_overlay()
	if not Game.bankrupt.is_empty():
		_closed_down()
		return
	sleeping = true
	show_screen("home")


## The bills couldn't be paid, even with the bank's help: the dealership closes and the player starts over.
func _closed_down() -> void:
	Game.save_game()
	var p := _modal(Color(0.12, 0.03, 0.03, 0.98), 0)
	p.custom_minimum_size = Vector2(640, 0)
	var v := UI.vbox(10)
	p.add_child(v)
	v.add_child(UI.header("%s has closed down" % Game.dealer_name))
	v.add_child(UI.para("On %s the monthly bills came due and we were %s short. TewportBank wouldn't lend another cent, the landlord changed the locks and the cars went back to auction." % [Game.bankrupt.get("date", Game.date_str()), Game.money_str(int(Game.bankrupt.get("short", 0)))], 16, UI.TEXT))
	v.add_child(UI.para("Days in business: %d    Cars sold: %d    Best net worth: %s" % [Game.day, Game.stats.sold, Game.money_str(Game.peak_worth)], 15, UI.GOLD))
	v.add_child(UI.rule())
	_leaderboard_table(v, Game.run_id)
	v.add_child(UI.gold_button("Start over", func():
		_close_overlay()
		Game.reset_save()
		show_screen("lot")
		_name_dealership(), 0, 52))


func _leaderboard() -> void:
	var p := _modal(UI.NAVY, 0)
	p.custom_minimum_size = Vector2(640, 0)
	var v := UI.vbox(10)
	p.add_child(v)
	v.add_child(UI.header("Leaderboard"))
	v.add_child(UI.para("Your best dealerships on this device, ranked by their highest net worth (cash minus loans, plus cars on the lot).", 14, UI.MUTED))
	_leaderboard_table(v, Game.run_id)
	v.add_child(UI.button("Close", _close_overlay, 0, 44))


func _leaderboard_table(parent: Control, highlight: int) -> void:
	var rows := Game.load_leaderboard()
	if rows.is_empty():
		parent.add_child(UI.para("No dealerships yet. Open one and sell some cars.", 15, UI.MUTED))
		return
	var tiers := ["", "Corner Lot", "Street Showroom", "Harbour Flagship"]
	for i in rows.size():
		var r: Dictionary = rows[i]
		var h := UI.hbox(10)
		var col := UI.GOLD if int(r.get("run", 0)) == highlight else UI.TEXT
		h.add_child(UI.label("#%d" % (i + 1), 16, col, true))
		var name_l := UI.label("%s" % r.get("name", "?"), 16, col, true)
		name_l.custom_minimum_size = Vector2(190, 0)
		h.add_child(name_l)
		h.add_child(UI.label("%s · %d sold · day %d · %s" % [tiers[clamp(int(r.get("tier", 1)), 1, 3)], int(r.get("sold", 0)), int(r.get("days", 1)), r.get("status", "")], 13,
			UI.BAD if r.get("status", "") == "Closed down" else UI.MUTED))
		h.add_child(UI.spacer())
		h.add_child(UI.label(Game.money_str(int(r.get("worth", 0))), 16, UI.GOOD, true))
		parent.add_child(h)


## The Sleep button at home: wake up and get Marco's morning briefing.
func _wake_up() -> void:
	sleeping = false
	var m := ["Marco", "CEO & Financial Advisor"]
	var lines := []
	if Game.money < 0:
		lines.append(m + ["We're in the red. Sell something tomorrow, or take the TewportBank line of credit on the PC. And don't tell my mother."])
	var due: int = Game.monthly_bills().total
	if Game.days_until_bills() <= 7 and Game.money + Game.loan_limit() - Game.loan < due:
		lines.append(m + ["Bills of %s are due in %d days and we can't cover them, even with the bank. If we don't sell cars before then, we close for good." % [Game.money_str(due), Game.days_until_bills()]])
	var tips := _marco_tips()
	lines.append(tips[0])
	if tips.size() > 2:
		lines.append(tips[1])
	play_dialogue(lines, func():
		closing = false
		show_screen("lot"))


## Segmented green-to-red meter with a red walk-out line, like a fuel gauge.
class MeterBar extends Control:
	var value := 0.5
	var red_line := 0.15

	func _draw() -> void:
		var n := 12
		var gap := 2.0
		var w := (size.x - gap * (n - 1)) / n
		for i in n:
			var t := float(i) / (n - 1)
			var col := Color("e0412f").lerp(Color("f1c232"), clamp(t * 2.0, 0.0, 1.0)).lerp(Color("4cc35a"), clamp(t * 2.0 - 1.0, 0.0, 1.0))
			if (i + 0.5) / n > value:
				col = Color(col, 0.18)
			draw_rect(Rect2(i * (w + gap), 0, w, size.y), col)
		var rx := red_line * size.x
		draw_line(Vector2(rx, -3), Vector2(rx, size.y + 3), Color("ff2d2d"), 2.0)
		var mx: float = clamp(value, 0.0, 1.0) * size.x
		draw_colored_polygon(PackedVector2Array([Vector2(mx - 5, size.y + 6), Vector2(mx + 5, size.y + 6), Vector2(mx, size.y)]), Color.WHITE)


## Price (or APR) negotiation track: buyer offer, your counter, and the bad-deal walkout line.
class DealBar extends Control:
	var lo := 0.0
	var hi := 1.0
	var offer := 0.0
	var counter := 0.0
	var threshold := 0.0
	var cost := 0.0
	var percent := false

	func _x(v: float) -> float:
		return 8.0 + clamp((v - lo) / max(0.001, hi - lo), 0.0, 1.0) * (size.x - 16.0)

	func _fmt(v: float) -> String:
		return ("%.1f%%" % v) if percent else Game.money_str(v)

	func _draw() -> void:
		var font := get_theme_default_font()
		var y := 30.0
		var x0 := _x(offer)
		var xt := _x(threshold)
		draw_rect(Rect2(8, y - 4, size.x - 16, 8), Color(1, 1, 1, 0.12))
		# green near their offer, yellow to red as you approach the line, dark past it
		var steps := 24
		for i in steps:
			var a: float = lerp(x0, xt, float(i) / steps)
			var b: float = lerp(x0, xt, float(i + 1) / steps)
			var t := float(i) / steps
			var col := Color("4cc35a").lerp(Color("f1c232"), clamp(t * 2.0, 0.0, 1.0)).lerp(Color("e0412f"), clamp(t * 2.0 - 1.0, 0.0, 1.0))
			draw_rect(Rect2(a, y - 4, b - a, 8), col)
		draw_rect(Rect2(xt, y - 4, size.x - 8 - xt, 8), Color(0.45, 0.05, 0.05))
		if not percent and cost > lo:
			var xc := _x(cost)
			draw_line(Vector2(xc, y - 9), Vector2(xc, y + 9), Color(1, 1, 1, 0.5), 1.0)
		draw_line(Vector2(xt, y - 12), Vector2(xt, y + 12), Color("ff2d2d"), 3.0)
		var xm := _x(counter)
		draw_colored_polygon(PackedVector2Array([Vector2(xm - 7, y - 14), Vector2(xm + 7, y - 14), Vector2(xm, y - 5)]), Color("e8b64c"))
		draw_colored_polygon(PackedVector2Array([Vector2(x0 - 6, y + 14), Vector2(x0 + 6, y + 14), Vector2(x0, y + 5)]), Color("4aa3ff"))
		draw_string(font, Vector2(8, 12), ("BANK RATE " if percent else "BUYER OFFER ") + _fmt(offer), HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color("4aa3ff"))
		draw_string(font, Vector2(0, 12), "YOU " + _fmt(counter), HORIZONTAL_ALIGNMENT_RIGHT, size.x - 8, 12, Color("e8b64c"))
		draw_string(font, Vector2(0, size.y - 2), "BAD DEAL WALKOUT LINE: " + _fmt(threshold), HORIZONTAL_ALIGNMENT_CENTER, size.x, 12, Color("ff6b5b"))


## A person's portrait cropped to whatever box it sits in with the whole face centred (see FaceRect).
func _face_rect(pid: String, tight := false) -> TextureRect:
	var r := FaceRect.new()
	r.tight = tight
	r.src = _person_tex(pid)
	return r


## Shows a 480x600 portrait through an AtlasTexture region with the box's aspect, anchored on the head (top ~55% of the
## portrait), so wide boxes no longer crop to the chest. Boxes wider than the head allow fit the whole head, centred.
## tight = thumbnails: head and a little shoulder only. Other textures (body crops) fall back to cover.
class FaceRect extends TextureRect:
	var src: Texture2D
	var tight := false

	func _init() -> void:
		expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		mouse_filter = Control.MOUSE_FILTER_IGNORE
		set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		resized.connect(_fit)

	func _ready() -> void:
		_fit()

	func _fit() -> void:
		if src == null:
			return
		var tw := float(src.get_width())
		var th := float(src.get_height())
		if src is AtlasTexture or absf(tw / th - 0.8) > 0.02:
			stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
			texture = src
			return
		var k := tw / 480.0
		var aspect := 1.0 if size.y <= 0.0 else clampf(size.x / size.y, 0.45, 1.45)
		var h := minf(600.0, maxf(330.0, 480.0 / aspect))
		if tight:
			h = 360.0 if aspect >= 0.8 else minf(600.0, 360.0 / aspect * 0.8)
		var w := h * aspect
		if w > 480.0:
			w = 480.0
			h = w / aspect
		var y0 := clampf(215.0 - h * 0.5, 0.0, 600.0 - h)
		if tight:
			y0 = clampf(40.0 - (h - 360.0) * 0.3, 0.0, 600.0 - h)
		var a := AtlasTexture.new()
		a.atlas = src
		a.region = Rect2((240.0 - w * 0.5) * k, y0 * k, w * k, h * k)
		texture = a
