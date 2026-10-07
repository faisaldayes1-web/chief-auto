extends Control
## Chief Auto prototype: one script drives every screen of the dealership.
## Office PC (auctions + shops) -> Garage -> Showroom walk-ins -> negotiation -> paperwork -> grow.

const BG := {
	"lot": preload("res://assets/bg_lot.jpg"),
	"office": preload("res://assets/bg_office.jpg"),
}
const LOGO := preload("res://assets/logo.png")
const DEAL_DESK := preload("res://assets/bg_dealdesk.jpg")
const PORTRAITS := {"Marco": preload("res://assets/portrait_marco.jpg"), "Maruchan": preload("res://assets/portrait_maruchan.jpg")}
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

# Garage
var selected_car_id := -1
var mechanic_index := 0
var garage_log := ""

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
		if current in ["lot", "marco"]:
			bg.modulate = Game.sky_tint()


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
	hud.add_child(UI.label("OC CHIEF AUTO", 20, UI.GOLD, true))
	hud.add_child(UI.spacer())
	hud_lobby = UI.label("", 16, UI.BLUE)
	hud.add_child(hud_lobby)
	var dv := UI.vbox(0)
	hud_day = UI.label("", 15, UI.MUTED)
	hud_clock = UI.label("", 17, UI.TEXT, true)
	dv.add_child(hud_day)
	dv.add_child(hud_clock)
	hud.add_child(dv)
	var mv := UI.vbox(0)
	hud_money = UI.label("", 22, UI.GOOD, true)
	hud_rent = UI.label("", 13, UI.MUTED)
	mv.add_child(hud_money)
	mv.add_child(hud_rent)
	hud.add_child(mv)
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
	hud_money.text = Game.money_str(Game.money)
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
	for item in [["Lot", "lot"], ["Office PC", "pc"], ["Garage", "garage"], ["Showroom", "showroom"], ["Marco", "marco"]]:
		var b := UI.button(item[0], show_screen.bind(item[1]), 140, 52)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		nav.add_child(b)
	var end := UI.gold_button("Close for the night", _close_for_night, 170, 52)
	end.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	nav.add_child(end)
	return p


func set_bg(key: String, darkness: float) -> void:
	bg.visible = key != ""
	if key != "":
		bg.texture = BG[key]
		bg.modulate = Game.sky_tint()
	dim.color = Color(0, 0, 0, darkness)


func _margins(px: int) -> void:
	for side in ["left", "right", "top", "bottom"]:
		content.add_theme_constant_override("margin_" + side, px)


func show_screen(name: String) -> void:
	current = name
	auction_view = {}
	lobby_stage = null
	UI.clear(content)
	_margins(16)
	hud.get_parent().visible = name != "title"
	nav.get_parent().visible = name != "title"
	for b in nav.get_children():
		if b is Button and b.get_meta("screen", "") == name:
			pass
	match name:
		"title": _screen_title()
		"lot": _screen_lot()
		"pc": _screen_pc()
		"garage": _screen_garage()
		"showroom": _screen_showroom()
		"marco": _screen_marco()
	_refresh_clock()


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
	var tag := UI.label("Prototype build · OC Chief Auto, Tewport Beach", 14, UI.MUTED)
	tag.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(tag)


func _start_game() -> void:
	if Game.debug and Game.cars.is_empty():
		Game.seen_intro = true
		if Game.debug_day > 0:
			Game.day = Game.debug_day
		if Game.debug_level > 0:
			Game.level = Game.debug_level
			Game.money += 50000
		for l in Game.listings.slice(0, 3):
			Game.add_car(l.car, int(Game.value(l.car) * 0.6))
		lobby.append(Game.make_customer())
		lobby.append(Game.make_customer())
	show_screen("lot")
	if not Game.seen_intro:
		Game.seen_intro = true
		Game.save_game()
		var m := ["Marco", "CEO & Financial Advisor"]
		play_dialogue([
			m + ["Welcome to OC Chief Auto. I'm Marco. I run this place, and I watch every dollar."],
			m + ["Win cars at auction on your office PC, fix them in the garage, and sell them to the walk-ins in the showroom."],
			m + ["Rent is $6,000 a month, plus staff salaries and any advertising you buy. Bills hit on the 1st, so watch the countdown up top. October is paid."],
			["Amna", "Senior Sales Consultant", "Hi, I'm Amna. If customers are waiting and you're busy, I'll take care of them. Four stars, ask anyone."],
			["Jeff", "Sales Associate", "And I'm Jeff! One star, but it's a really shiny star."],
			["Maruchan", "Leasing & VIP Relations", "Maruchan. I handle the VIPs. Let me say hi to a customer and they're 15% happier. Guaranteed."],
			m + ["We open at 8 and close at 9. Push a customer past their bad-deal line and they storm out. Cut corners on paperwork and we get sued. Go."],
		], func(): pass)


# =====================================================================
# Lot
# =====================================================================

func _screen_lot() -> void:
	set_bg("lot", 0.0)
	var h := UI.hbox(16)
	content.add_child(h)
	var side := UI.panel()
	side.custom_minimum_size = Vector2(470, 0)
	side.size_flags_vertical = Control.SIZE_EXPAND_FILL
	h.add_child(side)
	var v := UI.vbox(10)
	side.add_child(v)
	v.add_child(UI.label("Your Lot  (%d / %d cars)" % [Game.cars.size(), Game.lot_capacity()], 22, UI.GOLD, true))
	v.add_child(UI.para("Market today: %s are hot (+10%% sale price)." % _class_name(Game.hot_class), 15, UI.BLUE))
	var list := UI.vbox(8)
	v.add_child(UI.scroll(list))
	if Game.cars.is_empty():
		list.add_child(UI.para("The lot is empty. Head to the Office PC and win something at auction.", 17, UI.MUTED))
		list.add_child(UI.gold_button("Open Office PC", show_screen.bind("pc")))
	for car in Game.cars:
		list.add_child(_car_card(car))
	h.add_child(UI.spacer())


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


func _screen_pc() -> void:
	var stage := _stage("desk")
	var win := UI.panel(Color(0.93, 0.94, 0.96, 1.0), Color(0.1, 0.1, 0.1), 0)
	stage.add_child(win)
	var place := func():
		stage._compute()
		win.position = stage.monitor_rect.position
		win.size = stage.monitor_rect.size
	stage.resized.connect(place)
	place.call_deferred()
	var v := UI.vbox(0)
	win.add_child(v)
	var tabs := UI.hbox(3)
	var strip := UI.panel(Color(0.78, 0.8, 0.85), Color.TRANSPARENT, 5)
	strip.add_child(tabs)
	v.add_child(strip)
	for t in PC_TABS:
		var active: bool = t[0] == pc_tab
		var b := UI.button(t[1], func():
			pc_tab = t[0]
			show_screen("pc"), 0, 30)
		b.add_theme_font_size_override("font_size", 14)
		var bg_c := Color(0.93, 0.94, 0.96) if active else Color(0.68, 0.7, 0.75)
		b.add_theme_stylebox_override("normal", UI.box(bg_c, Color.TRANSPARENT, 6, 0, 10))
		b.add_theme_stylebox_override("hover", UI.box(bg_c.lightened(0.2), Color.TRANSPARENT, 6, 0, 10))
		b.add_theme_color_override("font_color", Color(0.15, 0.15, 0.2) if active else Color(0.3, 0.3, 0.35))
		tabs.add_child(b)
	var addr_wrap := UI.panel(Color(0.93, 0.94, 0.96), Color.TRANSPARENT, 6)
	var addr := LineEdit.new()
	addr.text = PC_URLS[pc_tab]
	if pc_tab == "auction":
		addr.text = "https://www." + Game.auction(auction_house).url
	addr.editable = false
	addr.add_theme_font_size_override("font_size", 14)
	addr_wrap.add_child(addr)
	v.add_child(addr_wrap)
	var body := MarginContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	for side in ["left", "right", "top", "bottom"]:
		body.add_theme_constant_override("margin_" + side, 10)
	v.add_child(body)
	var inner := UI.vbox(8)
	body.add_child(inner)
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


func _web_box() -> PanelContainer:
	return UI.panel(Color.WHITE, Color(0.8, 0.8, 0.85), 10)


func _site_head(inner: Control, name: String, col: Color, sub: String) -> void:
	var head := UI.hbox(12)
	head.add_child(UI.label(name, 26, col, true))
	head.add_child(UI.label(sub, 14, GREY))
	head.add_child(UI.spacer())
	head.add_child(UI.label("Balance " + Game.money_str(Game.money), 14, Color("1e7e34")))
	inner.add_child(head)


func _tab_auction(inner: Control) -> void:
	var house := Game.auction(auction_house)
	# auction-house switcher
	var bar := UI.hbox(6)
	for a in Game.AUCTIONS:
		var on: bool = a.id == auction_house
		var member: bool = a.id in Game.memberships
		var b := UI.button(a.name + ("" if member else "  (locked)"), func():
			auction_house = a.id
			show_screen("pc"), 0, 30)
		b.add_theme_font_size_override("font_size", 13)
		var c := Color(a.color)
		b.add_theme_stylebox_override("normal", UI.box(c if on else Color(0.85, 0.86, 0.9), Color.TRANSPARENT, 4, 0, 10))
		b.add_theme_stylebox_override("hover", UI.box(c.lightened(0.15), Color.TRANSPARENT, 4, 0, 10))
		b.add_theme_color_override("font_color", Color.WHITE if on else INK)
		bar.add_child(b)
	inner.add_child(bar)
	_site_head(inner, house.name, Color(house.color), "%s · %s · Lot space %d/%d" % [house.desc, Game.date_str(), Game.cars.size(), Game.lot_capacity()])
	if not auction_house in Game.memberships:
		inner.add_child(_auction_join_card(house))
		return
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 10)
	inner.add_child(UI.scroll(grid))
	for l in Game.listings:
		if l.get("house", "autobidz") == auction_house:
			grid.add_child(_listing_card(l))
	if grid.get_child_count() == 0:
		inner.add_child(UI.label("New lanes open tomorrow morning.", 15, GREY))


func _auction_join_card(a: Dictionary) -> Control:
	var box := _web_box()
	var v := UI.vbox(8)
	box.add_child(v)
	v.add_child(UI.label("Members only", 22, Color(a.color), true))
	var perks := {
		"salvage": "Wrecks and floods from 10 to 20 cents on the dollar. Expect extra faults, so a strong mechanic pays for himself.",
		"dealer": "Dealer-only lanes with clean history reports, fewer faults and fewer rival bidders. Buy-now prices around 75% of value.",
		"exotic": "Porsches, Ferraris and McLarens from Coast Highway collectors. Big money in, bigger money out.",
	}
	v.add_child(UI.label(perks.get(a.id, a.desc), 15, INK))
	var ok_lvl: bool = Game.level >= a.level
	var ok_rep: bool = Game.reputation >= a.rep
	v.add_child(UI.label("%s  Dealer level %d (you are %d)" % ["✓" if ok_lvl else "✗", a.level, Game.level], 15, Color("1e7e34") if ok_lvl else Color("c0392b")))
	if a.rep > 0:
		v.add_child(UI.label("%s  Yolp rating %.1f★ (you have %.1f★)" % ["✓" if ok_rep else "✗", a.rep, Game.reputation], 15, Color("1e7e34") if ok_rep else Color("c0392b")))
	v.add_child(UI.label("Membership fee: %s, one time" % Game.money_str(a.fee), 15, INK, true))
	var join := UI.gold_button("Join " + a.name, func():
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
		show_screen("pc"))
	join.disabled = not Game.auction_unlocked(a)
	v.add_child(join)
	return box


func _listing_card(l: Dictionary) -> Control:
	var car: Dictionary = l.car
	var p := _web_box()
	p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var v := UI.vbox(3)
	p.add_child(v)
	v.add_child(_car_art(car, Vector2(0, 62)))
	v.add_child(UI.label("%d %s" % [car.year, car.model], 17, INK, true))
	v.add_child(UI.label("%s mi · Grade %s" % [_num(car.miles), _grade(Game.condition(car))], 13, GREY))
	var status := ""
	var col := Color("c0392b")
	if l.sold:
		status = "SOLD to you" if l.winner == "you" else "Sold to %s" % l.winner
		col = Color("1e7e34") if l.winner == "you" else GREY
	else:
		status = "Bid %s" % Game.money_str(l.current) + ("  ·  Buy now %s" % Game.money_str(l.buy_now) if l.buy_now > 0 else "")
	v.add_child(UI.label(status, 14, col))
	v.add_child(UI.button("View listing", _open_listing.bind(l), 0, 34))
	return p


func _num(n: int) -> String:
	return Game.money_str(n).substr(1)


func _grade(cond: int) -> String:
	return "%.1f / 5" % (1.0 + cond / 25.0)


func _open_listing(l: Dictionary) -> void:
	_screen_pc_frame_then(func(inner: Control): _listing_detail(inner, l))


func _screen_pc_frame_then(fill: Callable) -> void:
	# Rebuild the PC screen and swap the browser body for a detail page.
	pc_tab = "auction"
	show_screen("pc")
	var stage: SceneArt = content.get_child(0)
	var win: PanelContainer = stage.get_child(0)
	var body: MarginContainer = win.get_child(0).get_child(2)
	var inner: VBoxContainer = body.get_child(0)
	UI.clear(inner)
	fill.call(inner)


func _listing_detail(inner: Control, l: Dictionary) -> void:
	auction_view = {}
	var car: Dictionary = l.car
	var top := UI.hbox(10)
	top.add_child(UI.button("← All listings", func(): show_screen("pc"), 0, 34))
	top.add_child(UI.label("%d %s" % [car.year, car.model], 24, INK, true))
	inner.add_child(top)
	var cols := UI.hbox(12)
	cols.size_flags_vertical = Control.SIZE_EXPAND_FILL
	inner.add_child(cols)
	var left := _web_box()
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cols.add_child(left)
	var lv := UI.vbox(4)
	left.add_child(lv)
	var top_row := UI.hbox(10)
	top_row.add_child(_car_art(car, Vector2(220, 88)))
	var facts := UI.vbox(2)
	facts.add_child(UI.label("%s mi" % _num(car.miles), 15, GREY))
	facts.add_child(UI.label(_class_name(car.cls).trim_suffix("s"), 15, GREY))
	facts.add_child(UI.label("Seller grade %s" % _grade(Game.condition(car)), 15, GREY))
	facts.add_child(UI.label("Est. retail %s" % Game.money_str(Game.value(car)), 15, INK, true))
	top_row.add_child(facts)
	lv.add_child(top_row)
	for part in Game.PARTS:
		var row := UI.hbox(8)
		var name_l := UI.label(Game.PART_NAMES[part], 14, INK)
		name_l.custom_minimum_size = Vector2(130, 0)
		row.add_child(name_l)
		row.add_child(UI.bar(car.parts[part], 100, UI.cond_color(car.parts[part]), 9))
		row.add_child(UI.label(str(car.parts[part]), 14, INK))
		lv.add_child(row)
	var hist := UI.vbox(4)
	lv.add_child(hist)
	_fill_history(hist, car)
	var right := _web_box()
	right.custom_minimum_size = Vector2(300, 0)
	cols.add_child(right)
	var rv := UI.vbox(6)
	right.add_child(rv)
	if l.sold:
		rv.add_child(UI.label("Auction closed", 20, INK, true))
		rv.add_child(UI.para("Won by %s for %s" % ["you" if l.winner == "you" else l.winner, Game.money_str(l.current)], 15, GREY))
		return
	var cur := UI.label("", 26, Color("c0392b"), true)
	var lead := UI.label("", 15, GREY)
	var time_l := UI.label("", 15, INK)
	var feed := UI.label("", 13, GREY)
	rv.add_child(UI.label("Current bid", 14, GREY))
	rv.add_child(cur)
	rv.add_child(lead)
	rv.add_child(time_l)
	var bid_btn := UI.gold_button("", _place_bid.bind(l), 0, 46)
	rv.add_child(bid_btn)
	if l.buy_now > 0:
		rv.add_child(UI.button("Buy It Now: %s" % Game.money_str(l.buy_now), _buy_now.bind(l), 0, 40))
		if not l.haggled:
			rv.add_child(UI.button("Haggle with seller", _haggle.bind(l), 0, 40))
	rv.add_child(feed)
	auction_view = {"listing": l, "cur": cur, "lead": lead, "time": time_l, "bid": bid_btn, "feed": feed}
	_refresh_auction_view()


func _fill_history(hist: VBoxContainer, car: Dictionary) -> void:
	UI.clear(hist)
	if car.history_known:
		var col := Color("1e7e34") if car.history == "Clean" else Color("c0392b")
		hist.add_child(UI.label("History report: %s" % car.history, 15, col, true))
		if car.has("faults_found"):
			var f: Array = car.faults_found
			hist.add_child(UI.para("Inspection: " + ("no hidden problems." if f.is_empty() else "hidden problems in " + ", ".join(f) + "."), 14, INK))
	else:
		hist.add_child(UI.button("Buy history + inspection report ($150)", func():
			if Game.spend(150, "repairs"):
				car.history_known = true
				car.faults_found = Game.reveal_faults(car)
				Game.save_game()
				_fill_history(hist, car)
			else:
				toast("Not enough money."), 0, 36))


func bid_increment(l: Dictionary) -> int:
	return max(100, int(round(Game.value(l.car) * 0.03 / 100.0)) * 100)


func _place_bid(l: Dictionary) -> void:
	if Game.cars.size() >= Game.lot_capacity():
		toast("Your lot is full. Sell a car first, or expand the lot at ShowroomPro.")
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
		if Game.spend(l.current, "cars"):
			Game.add_car(l.car, l.current)
			toast("You won the %s for %s! It's on your lot." % [l.car.model, Game.money_str(l.current)])
		else:
			l.winner = l.rival
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

func _shop_row(inner: Control, title: String, desc: String, right: Control, art: Control = null) -> void:
	var p := _web_box()
	var h := UI.hbox(10)
	p.add_child(h)
	if art:
		h.add_child(art)
	var v := UI.vbox(1)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.add_child(UI.label(title, 16, INK, true))
	v.add_child(UI.para(desc, 13, GREY))
	h.add_child(v)
	h.add_child(right)
	inner.add_child(p)


func _small_btn(text: String, cb: Callable, gold := false) -> Button:
	var b := UI.gold_button(text, cb, 130, 36) if gold else UI.button(text, cb, 130, 36)
	b.add_theme_font_size_override("font_size", 15)
	return b


func _tab_desk(inner: Control) -> void:
	_site_head(inner, "DeskDepot", Color("1f6fb2"), "Make the office yours. Changes show on your desk right away.")
	var list := UI.vbox(6)
	inner.add_child(UI.scroll(list))
	var slots := {"desk": "Desks", "chair": "Chairs", "monitor": "Monitors", "decor": "Decor"}
	for slot in slots:
		list.add_child(UI.label(slots[slot], 17, Color("1f6fb2"), true))
		for it in Game.DESK_ITEMS:
			if it.slot != slot:
				continue
			var owned: bool = it.id in Game.owned
			var btn: Button
			if not owned:
				btn = _small_btn("Buy " + Game.money_str(it.price), _buy_desk_item.bind(it), true)
			elif slot == "decor":
				var on: bool = it.id in Game.decor_on
				btn = _small_btn("Hide" if on else "Show", func():
					if on:
						Game.decor_on.erase(it.id)
					else:
						Game.decor_on.append(it.id)
					Game.save_game()
					show_screen("pc"))
			elif Game.equipped[slot] == it.id:
				btn = _small_btn("In use", func(): pass)
				btn.disabled = true
			else:
				btn = _small_btn("Use", func():
					Game.equipped[slot] = it.id
					Game.save_game()
					show_screen("pc"))
			_shop_row(list, it.name, it.desc, btn)


func _buy_desk_item(it: Dictionary) -> void:
	if not Game.spend(it.price, "shop"):
		toast("Not enough money.")
		return
	Game.owned.append(it.id)
	if it.slot == "decor":
		Game.decor_on.append(it.id)
	else:
		Game.equipped[it.slot] = it.id
	if it.slot == "monitor":
		toast("Installed. More auction listings show up from tomorrow.")
	Game.save_game()
	show_screen("pc")


func _tab_showroom_shop(inner: Control) -> void:
	_site_head(inner, "ShowroomPro", Color("8e44ad"), "Upgrades for your showroom and lot.")
	var list := UI.vbox(6)
	inner.add_child(UI.scroll(list))
	for it in Game.SHOWROOM_UPGRADES:
		var btn: Button
		if Game.has_upgrade(it.id):
			btn = _small_btn("Installed", func(): pass)
			btn.disabled = true
		elif it.has("needs") and not Game.has_upgrade(it.needs):
			btn = _small_btn("Needs first", func(): pass)
			btn.disabled = true
		else:
			btn = _small_btn("Buy " + Game.money_str(it.price), func():
				if Game.spend(it.price, "shop"):
					Game.upgrades.append(it.id)
					Game.save_game()
					toast("%s installed." % it.name)
					show_screen("pc")
				else:
					toast("Not enough money."), true)
		_shop_row(list, it.name, it.desc, btn)


func _tab_ads(inner: Control) -> void:
	_site_head(inner, "AdSpace", Color("d35400"), "Advertising brings more walk-ins. Billed monthly on the 1st.")
	inner.add_child(UI.label("Walk-ins expected today: %d" % Game.walkins_today(), 15, INK))
	var list := UI.vbox(6)
	inner.add_child(UI.scroll(list))
	for a in Game.ADS:
		var on: bool = a.id in Game.ads_active
		var btn: Button
		if on:
			btn = _small_btn("Cancel", func():
				Game.ads_active.erase(a.id)
				Game.save_game()
				show_screen("pc"))
		else:
			var left: int = Game.days_in_month() - Game.date_dict().day + 1
			var now_cost := int(round(a.monthly * left / float(Game.days_in_month()) / 10.0)) * 10
			btn = _small_btn("Start %s" % Game.money_str(now_cost), func():
				if Game.spend(now_cost, "ads"):
					Game.ads_active.append(a.id)
					Game.save_game()
					toast("%s is live. More customers from tomorrow." % a.name)
					show_screen("pc")
				else:
					toast("Not enough money."), true)
		_shop_row(list, "%s · %s/month" % [a.name, Game.money_str(a.monthly)], a.desc + (" Running." if on else " First charge is prorated for the rest of this month."), btn)


func _staff_art(s: Dictionary, sz := Vector2(56, 64)) -> PersonArt:
	var p := PersonArt.new()
	p.custom_minimum_size = sz
	p.pid = Game.staff_pid(s)
	p.mood = 0.6
	return p


func _stars(n: int) -> String:
	return "★".repeat(n) + "☆".repeat(5 - n)


func _tab_staff(inner: Control) -> void:
	_site_head(inner, "StaffHire", Color("16a085"), "Salespeople take walk-ins when you're busy. Better people cost more. Salaries are monthly.")
	var col := UI.vbox(8)
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	inner.add_child(UI.scroll(col))
	col.add_child(UI.label("Applicants this week", 17, Color("16a085"), true))
	var g2 := _card_grid()
	col.add_child(g2)
	for c in Game.candidates:
		g2.add_child(_staff_card(c, true))
	if Game.candidates.is_empty():
		col.add_child(UI.label("No new applicants until Monday.", 14, GREY))
	col.add_child(UI.label("Your team  (%d/5)" % Game.staff.size(), 17, Color("16a085"), true))
	var g1 := _card_grid()
	col.add_child(g1)
	for s in Game.staff:
		g1.add_child(_staff_card(s, false))
	if Game.level < 3 and Game.reputation < 3.8:
		col.add_child(UI.label("Top-tier closers only apply to dealerships at level 3 or with a 3.8★ Yolp rating.", 13, GREY))


func _card_grid() -> GridContainer:
	var g := GridContainer.new()
	g.columns = 4
	g.add_theme_constant_override("h_separation", 8)
	g.add_theme_constant_override("v_separation", 8)
	g.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return g


const SKILL_COLORS := {"closing": Color("c0392b"), "rapport": Color("e67e22"), "finance": Color("1f6fb2"), "upsell": Color("8e44ad")}


func _staff_card(s: Dictionary, applicant: bool) -> Control:
	var box := _web_box()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var v := UI.vbox(3)
	box.add_child(v)
	var top := UI.hbox(6)
	var art := PersonArt.new()
	art.custom_minimum_size = Vector2(64, 76)
	art.pid = Game.staff_pid(s)
	art.mood = 0.6
	top.add_child(art)
	var tv := UI.vbox(0)
	tv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tv.add_child(UI.label(s.name, 17, INK, true))
	tv.add_child(UI.label(_stars(s.stars), 15, Color("d4a017")))
	tv.add_child(UI.label(s.trait, 12, GREY))
	top.add_child(tv)
	v.add_child(top)
	for k in Game.SKILLS:
		var row := UI.hbox(4)
		var nm := UI.label(Game.SKILL_NAMES[k], 11, GREY)
		nm.custom_minimum_size.x = 74
		row.add_child(nm)
		var bar := ProgressBar.new()
		bar.max_value = 100
		bar.value = Game.skill(s, k)
		bar.show_percentage = false
		bar.custom_minimum_size = Vector2(0, 8)
		bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		bar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		bar.add_theme_stylebox_override("background", UI.box(Color(0.88, 0.89, 0.92), Color.TRANSPARENT, 3, 0, 0))
		bar.add_theme_stylebox_override("fill", UI.box(SKILL_COLORS[k], Color.TRANSPARENT, 3, 0, 0))
		row.add_child(bar)
		row.add_child(UI.label(str(Game.skill(s, k)), 11, INK))
		v.add_child(row)
	v.add_child(UI.label("Closes ~%d%% of walk-ins" % int(Game.staff_close_chance(s) * 100), 12, INK))
	v.add_child(UI.label("%s / month" % Game.money_str(s.salary), 15, Color("1e7e34"), true))
	if applicant:
		v.add_child(UI.label("Signing fee %s" % Game.money_str(s.get("hire_fee", 0)), 12, GREY))
		v.add_child(_small_btn("Hire", func():
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
			show_screen("pc"), true))
	elif s.fixed:
		v.add_child(UI.label("%d cars sold" % s.get("sales", 0), 12, GREY))
		var b := _small_btn("Marco says no", func(): pass)
		b.disabled = true
		v.add_child(b)
	else:
		v.add_child(UI.label("%d cars sold" % s.get("sales", 0), 12, GREY))
		v.add_child(_small_btn("Let go", func():
			Game.staff.erase(s)
			Game.save_game()
			toast("%s has left the dealership." % s.name)
			show_screen("pc")))
	return box


# ---------- Yolp ----------

func _tab_reviews(inner: Control) -> void:
	var red := Color("d32323")
	_site_head(inner, "Yolp", red, "OC Chief Auto · Used Car Dealer · Tewport Beach")
	var cols := UI.hbox(12)
	cols.size_flags_vertical = Control.SIZE_EXPAND_FILL
	inner.add_child(cols)
	var side := _web_box()
	side.custom_minimum_size.x = 230
	cols.add_child(side)
	var sv := UI.vbox(4)
	side.add_child(sv)
	var avg := Game.reputation
	sv.add_child(UI.label("%.1f" % avg, 44, INK, true))
	sv.add_child(UI.label(_stars(int(round(avg))), 22, red))
	sv.add_child(UI.label("%d reviews" % Game.reviews.size(), 14, GREY))
	var counts := [0, 0, 0, 0, 0]
	for r in Game.reviews:
		counts[r.stars - 1] += 1
	for st in [5, 4, 3, 2, 1]:
		var row := UI.hbox(4)
		row.add_child(UI.label("%d★" % st, 12, GREY))
		var bar := ProgressBar.new()
		bar.max_value = max(1, Game.reviews.size())
		bar.value = counts[st - 1]
		bar.show_percentage = false
		bar.custom_minimum_size = Vector2(150, 9)
		bar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		bar.add_theme_stylebox_override("background", UI.box(Color(0.9, 0.9, 0.92), Color.TRANSPARENT, 3, 0, 0))
		bar.add_theme_stylebox_override("fill", UI.box(red, Color.TRANSPARENT, 3, 0, 0))
		row.add_child(bar)
		row.add_child(UI.label(str(counts[st - 1]), 12, GREY))
		sv.add_child(row)
	sv.add_child(UI.rule(Color(0.85, 0.85, 0.88)))
	var help := UI.label("Your rating sets how many people walk in, how patient they are, and which auctions will have you. 5★ customers send friends the next day.", 12, GREY)
	help.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	help.custom_minimum_size.x = 220
	sv.add_child(help)
	if Game.referrals > 0:
		sv.add_child(UI.label("%d referral(s) coming in tomorrow" % Game.referrals, 13, Color("1e7e34"), true))
	var list := UI.vbox(8)
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cols.add_child(UI.scroll(list))
	var shown := Game.reviews.duplicate()
	shown.reverse()
	for r in shown.slice(0, 40):
		list.add_child(_review_card(r, red))


func _review_card(r: Dictionary, red: Color) -> Control:
	var box := _web_box()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var h := UI.hbox(10)
	box.add_child(h)
	var face := PersonArt.new()
	face.custom_minimum_size = Vector2(52, 52)
	face.pid = r.get("pid", "p00")
	face.mood = (r.stars - 3) * 0.5
	h.add_child(face)
	var v := UI.vbox(2)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(v)
	var top := UI.hbox(8)
	top.add_child(UI.label(r.name, 15, INK, true))
	top.add_child(UI.label(_stars(r.stars), 15, red))
	top.add_child(UI.spacer())
	top.add_child(UI.label("Day %d" % r.day if r.day > 0 else "Before you took over", 12, GREY))
	v.add_child(top)
	var t := UI.label(r.text, 14, INK)
	t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(t)
	if r.get("fixed", false):
		v.add_child(UI.label("Updated: the owner reached out and made it right.", 12, Color("1e7e34")))
	elif r.stars <= 2 and r.day > 0:
		v.add_child(_small_btn("Make it right ($250 gift card)", func():
			if Game.money < 250:
				toast("Not enough money.")
				return
			Game.spend(250, "other")
			r.stars = min(5, r.stars + 2)
			r.fixed = true
			Game._recompute_rep()
			Game.save_game()
			toast("%s bumped their review to %d★." % [r.name, r.stars])
			show_screen("pc")))
	return box


func _tab_bank(inner: Control) -> void:
	_site_head(inner, "TewportBank", Color("1e7e34"), "Business banking for OC Chief Auto")
	var b := Game.monthly_bills()
	var box := _web_box()
	inner.add_child(box)
	var v := UI.vbox(6)
	box.add_child(v)
	v.add_child(UI.label("Available balance: %s" % Game.money_str(Game.money), 22, INK, true))
	v.add_child(UI.label("Next bills due %s" % Game.next_bill_date(), 16, Color("c0392b")))
	for row in [["Rent (OC Chief Auto lot)", b.rent], ["Staff salaries (%d people)" % Game.staff.size(), b.salaries], ["Advertising", b.ads]]:
		var h := UI.hbox()
		h.add_child(UI.label(row[0], 16, INK))
		h.add_child(UI.spacer())
		h.add_child(UI.label(Game.money_str(row[1]), 16, INK))
		v.add_child(h)
	var tot := UI.hbox()
	tot.add_child(UI.label("Total each month", 17, INK, true))
	tot.add_child(UI.spacer())
	tot.add_child(UI.label(Game.money_str(b.total), 17, INK, true))
	v.add_child(tot)
	v.add_child(UI.label("Cars sold: %d · Total profit: %s · Customers who walked out: %d" % [Game.stats.sold, Game.money_str(Game.stats.profit), Game.stats.get("walked", 0)], 15, GREY))


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
	var art := _car_art(car, Vector2.ZERO)
	stage.add_child(art)
	var panel := UI.panel()
	stage.add_child(panel)
	var place := func():
		var w := stage.size.x
		var h := stage.size.y
		art.position = Vector2(w * 0.08, h * 0.32)
		art.size = Vector2(w * 0.44, h * 0.42)
		panel.position = Vector2(w * 0.56, 12)
		panel.size = Vector2(w * 0.44 - 12, h - 24)
	stage.resized.connect(place)
	place.call_deferred()

	var v := UI.vbox(8)
	panel.add_child(v)
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
	v.add_child(UI.para("Condition %d · Value %s · Repairs so far %s" % [Game.condition(car), Game.money_str(Game.value(car)), Game.money_str(car.spent)], 15, UI.MUTED))
	var opt := OptionButton.new()
	opt.custom_minimum_size = Vector2(0, 40)
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
		show_screen("garage"))
	v.add_child(opt)
	var mech: Dictionary = Game.MECHANICS[mechanic_index]
	for part in Game.PARTS:
		var row := UI.hbox(8)
		var nl := UI.label(Game.PART_NAMES[part], 15)
		nl.custom_minimum_size = Vector2(120, 0)
		row.add_child(nl)
		var val: int = car.parts[part]
		row.add_child(UI.bar(val, 100, UI.cond_color(val), 12))
		var vl := UI.label(str(val), 15, UI.cond_color(val))
		vl.custom_minimum_size = Vector2(32, 0)
		row.add_child(vl)
		var b := UI.button("Fix " + Game.money_str(_repair_cost(car, mech)), _repair.bind(car, part, mech), 116, 36)
		b.add_theme_font_size_override("font_size", 15)
		b.disabled = val >= 100
		row.add_child(b)
		v.add_child(row)
	var det_cost := _detail_cost(car)
	var det := UI.button("Detailing %s" % Game.money_str(det_cost) if not car.detailed else "Detailed ✓", func():
		if Game.spend(det_cost, "repairs"):
			car.detailed = true
			car.spent += det_cost
			garage_log = "The detailer made it sparkle. Customers will notice."
			Game.save_game()
			show_screen("garage")
		else:
			toast("Not enough money."), 0, 38)
	det.disabled = car.detailed
	v.add_child(det)
	if garage_log != "":
		v.add_child(UI.para(garage_log, 15, UI.GOOD))


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
	Game.save_game()
	show_screen("garage")


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
	for car in shown:
		var box := Control.new()
		stage.add_child(box)
		var art := _car_art(car, Vector2.ZERO)
		box.add_child(art)
		var tag := UI.button("%s\n%s" % [car.model, Game.money_str(car.get("sticker", 0))], _price_popup.bind(car), 0, 46)
		tag.add_theme_font_size_override("font_size", 14)
		box.add_child(tag)
		displays.append([box, art, tag])
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
		stage.move_child(btn, 0)  # customers stand behind the display cars
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
		people.append([btn, name_tag, bubble, pat, c])
	var info := UI.panel(Color(0.03, 0.05, 0.1, 0.85), UI.GOLD_DIM, 12)
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
	iv.add_child(UI.label("Tap a price tag to change a sticker price.", 13, UI.MUTED))
	iv.add_child(UI.rule(UI.GOLD_DIM))
	iv.add_child(UI.label("ON THE FLOOR", 13, UI.GOLD, true))
	for st in Game.staff:
		var row := UI.hbox(6)
		var face := PersonArt.new()
		face.custom_minimum_size = Vector2(30, 30)
		face.pid = Game.staff_pid(st)
		face.mood = 0.5
		row.add_child(face)
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
		for i in displays.size():
			var d: Array = displays[i]
			var c: Vector2 = pods[i] if i < pods.size() else Vector2(w * 0.5, h * 0.8)
			var cw: float = min(260.0, w / max(1, pods.size()) - 20)
			d[0].position = Vector2(c.x - cw / 2, c.y - cw * 0.42)
			d[0].size = Vector2(cw, cw * 0.42 + 56)
			d[1].position = Vector2.ZERO
			d[1].size = Vector2(cw, cw * 0.4)
			d[2].position = Vector2(cw * 0.2, cw * 0.42 + 6)
			d[2].size = Vector2(cw * 0.6, 46)
		for i in people.size():
			var pr: Array = people[i]
			var ph: float = h * 0.5
			var pw: float = ph * 0.42
			pr[0].size = Vector2(pw, ph)
			var target := Vector2(w * (0.14 + i * 0.2), h * 0.68 - ph)
			var cust: Dictionary = pr[4]
			if not cust.get("entered", false):
				# new arrivals walk in from the front door on the right
				cust.entered = true
				pr[0].position = Vector2(w * 0.92, target.y)
				pr[0].modulate.a = 0.0
				var tw: Tween = pr[0].create_tween().set_parallel()
				tw.tween_property(pr[0], "position", target, 1.4).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_OUT)
				tw.tween_property(pr[0], "modulate:a", 1.0, 0.5)
			else:
				pr[0].position = target
			pr[1].position = Vector2(-40, -22)
			pr[1].size = Vector2(pw + 80, 20)
			pr[2].position = Vector2(-30, -66)
			pr[2].size = Vector2(pw + 60, 0)
			pr[3].position = Vector2(pw * 0.1, 0)
			pr[3].size = Vector2(pw * 0.8, 7)
		info.position = Vector2(w - 360, 12)
		info.size = Vector2(348, 0)
	stage.resized.connect(place)
	place.call_deferred()


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
			income.finance = int(price * 0.004 * (Game.skill(s, "finance") / 20.0))
		if randf() < Game.skill(s, "upsell") / 180.0:
			income.addons = 1200
		var happy: float = clamp(0.3 + Game.skill(s, "rapport") / 180.0 + randf_range(-0.1, 0.1), 0.0, 1.0)
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
	back.texture = DEAL_DESK
	back.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	back.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	back.set_anchors_preset(Control.PRESET_FULL_RECT)
	back.modulate = Game.sky_tint().darkened(0.15)
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
	var face := PersonArt.new()
	face.pid = Game.customer_pid(c)
	face.mood = c.happiness * 2.0 - 1.0
	face.custom_minimum_size = Vector2(96, 110)
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
			c.log.append("Maruchan: \"Welcome to Chief Auto, my friend. You want a water? You look like a Porsha guy.\"  (+15% happiness)")
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
	var name: String = sale.customer.name if key == "buyer" else "OC Chief Auto"
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
	brand.add_child(UI.label("OC CHIEF AUTO", 15, PAPER_RED, true))
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
	r1.add_child(_pbox("Seller / creditor", "OC Chief Auto, Tewport Beach"))
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
			["   B. Emissions testing charge", "$50"], ["   C. Service contract, paid to Chief Warranty Co.", Game.money_str(warranty) if warranty > 0 else "$ ______"],
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
	var leveled := Game.add_xp(max(10, int(profit / 50)) + 10)
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
		reaction = "Big margin AND a happy customer. That's how we do it at Chief Auto."
	elif profit > 5000:
		reaction = "Big margin, but that customer won't send their friends."
	elif profit < 0:
		reaction = "We lost money on that one. Buy smarter or fix smarter."
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
		return "Pricier cars will start showing up at auction."
	var text: String = ", and ".join(bits)
	return text.substr(0, 1).to_upper() + text.substr(1) + "."


# =====================================================================
# Marco
# =====================================================================

func _screen_marco() -> void:
	set_bg("office", 0.0)
	var h := UI.hbox(16)
	content.add_child(h)
	h.add_child(UI.spacer())
	var p := UI.panel()
	p.custom_minimum_size = Vector2(470, 0)
	h.add_child(p)
	var v := UI.vbox(9)
	p.add_child(v)
	v.add_child(UI.label("MARCO · CEO ADVISOR", 26, UI.TEXT, true))
	v.add_child(UI.label("Status & Stats", 19, UI.GOLD, true))
	var s: Dictionary = Game.stats
	var conv: float = 0.0 if s.buyers == 0 else 100.0 * s.sold / s.buyers
	var avg_days: float = 0.0 if s.sold == 0 else float(s.days_held) / s.sold
	var eff: float = clamp(50.0 + s.profit / 500.0, 0.0, 100.0)
	_stat_row(v, "Dealership efficiency", "%d%%" % int(eff), eff)
	_stat_row(v, "Sales conversion rate", "%d%%" % int(conv), conv)
	_stat_row(v, "Inventory duration", "%.1f days" % avg_days, clamp(100 - avg_days * 15, 0, 100))
	_stat_row(v, "Client satisfaction", "%.1f / 5" % Game.reputation, Game.reputation * 20)
	v.add_child(UI.label("Monthly bills: %s, due %s" % [Game.money_str(Game.monthly_bills().total), Game.next_bill_date()], 15, UI.BLUE))
	v.add_child(UI.label("Advisor Perks", 19, UI.GOLD, true))
	for perk in Game.PERKS:
		var on: bool = Game.level >= perk.level
		v.add_child(UI.label(("✓ " if on else "Lvl %d · " % perk.level) + perk.name, 16, UI.TEXT if on else UI.MUTED, true))
		v.add_child(UI.para(perk.desc, 13, UI.MUTED))
	v.add_child(UI.gold_button("Ask Marco for advice", func(): play_dialogue(_marco_tips(), func(): pass)))


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
	if Game.money < b.total:
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
	var box := UI.panel(Color(0.04, 0.07, 0.13, 0.95), UI.BLUE, 18)
	box.anchor_left = 0.12
	box.anchor_right = 0.88
	box.anchor_top = 1.0
	box.anchor_bottom = 1.0
	box.offset_top = -250
	box.offset_bottom = -90
	overlay.add_child(box)
	var h := UI.hbox(16)
	box.add_child(h)
	if PORTRAITS.has(line[0]):
		var ph := TextureRect.new()
		ph.texture = PORTRAITS[line[0]]
		ph.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		ph.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		ph.custom_minimum_size = Vector2(112, 128)
		h.add_child(ph)
	else:
		var face := PersonArt.new()
		face.pid = line[0].to_lower() if line[0] in ["Amna", "Jeff"] else "marco"
		face.mood = 0.5
		face.custom_minimum_size = Vector2(112, 128)
		h.add_child(face)
	var v := UI.vbox(8)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(v)
	v.add_child(UI.label("%s · %s" % [line[0].to_upper(), line[1].to_upper()], 18, Color("8fc3ff"), true))
	var text := UI.para(line[2], 18)
	text.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(text)
	var hh := UI.hbox()
	hh.add_child(UI.spacer())
	hh.add_child(UI.button("Continue ▸", _show_next_line, 160, 40))
	v.add_child(hh)


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
	"payroll": "Staff payroll", "legal": "Lawsuits & legal", "other": "Other"}


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
		v.add_child(UI.para(n, 15, UI.BAD if n.begins_with("LAWSUIT") else UI.MUTED))
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
	for k in ["rent", "payroll", "ads", "cars", "repairs", "shop", "legal", "other"]:
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
	var m := ["Marco", "CEO & Financial Advisor"]
	var lines := []
	if Game.money < 0:
		lines.append(m + ["We're in the red. Sell something tomorrow or I'm calling the bank. And my mother."])
	lines.append(_marco_tips()[0])
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
