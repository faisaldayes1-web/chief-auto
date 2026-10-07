extends Control
## Chief Auto prototype: one script drives every screen of the core loop.
## Bid on the Office PC -> repair in the Garage -> sell in the Showroom -> sign paperwork -> grow.

const BG := {
	"lot": preload("res://assets/bg_lot.jpg"),
	"office": preload("res://assets/bg_office.jpg"),
	"map": preload("res://assets/bg_map.jpg"),
	"marco_lot": preload("res://assets/bg_marco_lot.jpg"),
}
const LOGO := preload("res://assets/logo.png")

var bg: TextureRect
var dim: ColorRect
var hud: HBoxContainer
var content: MarginContainer
var nav: HBoxContainer
var overlay: Control
var current := ""

# HUD labels
var hud_money: Label
var hud_day: Label
var hud_level: Label
var hud_xp: ProgressBar
var hud_rep: Label

# Auction state
var auction: Dictionary = {}     # listing being bid on live
var auction_timer := 0.0
var rival_timer := 0.0
var auction_view: Dictionary = {}  # labels to refresh while bidding

# Garage / showroom selection
var selected_car_id := -1
var mechanic_index := 0
var garage_log := ""

# Sale state
var sale: Dictionary = {}

# Dialogue queue
var dialogue_queue: Array = []
var dialogue_done: Callable


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
	for side in ["left", "right", "top", "bottom"]:
		content.add_theme_constant_override("margin_" + side, 16)
	root.add_child(content)
	root.add_child(_build_nav())

	overlay = Control.new()
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(overlay)

	Game.changed.connect(_refresh_hud)
	_refresh_hud()
	show_title()


func _process(delta: float) -> void:
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


# =====================================================================
# Shell: HUD, nav, backgrounds
# =====================================================================

func _build_hud() -> Control:
	var p := UI.panel(Color(0.03, 0.05, 0.1, 0.92), UI.GOLD_DIM, 10)
	hud = UI.hbox(18)
	p.add_child(hud)
	var logo := TextureRect.new()
	logo.texture = LOGO
	logo.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	logo.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	logo.custom_minimum_size = Vector2(44, 44)
	hud.add_child(logo)
	hud.add_child(UI.label("OC CHIEF AUTO", 20, UI.GOLD, true))
	hud.add_child(UI.spacer())
	hud_day = UI.label("", 18, UI.MUTED)
	hud.add_child(hud_day)
	hud_money = UI.label("", 22, UI.GOOD, true)
	hud.add_child(hud_money)
	var lv := UI.vbox(2)
	hud_level = UI.label("", 15, UI.TEXT)
	lv.add_child(hud_level)
	hud_xp = UI.bar(0, 100, UI.BLUE, 6)
	hud_xp.custom_minimum_size = Vector2(120, 6)
	lv.add_child(hud_xp)
	hud.add_child(lv)
	hud_rep = UI.label("", 18, UI.GOLD)
	hud.add_child(hud_rep)
	return p


func _refresh_hud() -> void:
	if hud_money == null:
		return
	hud_money.text = "Funds: " + Game.money_str(Game.money)
	hud_day.text = "Day %d" % Game.day
	hud_level.text = "Level %d" % Game.level
	hud_xp.max_value = Game.xp_to_next()
	hud_xp.value = Game.xp
	hud_rep.text = "%s %.1f" % [UI.stars(Game.reputation), Game.reputation]


func _build_nav() -> Control:
	var p := UI.panel(Color(0.03, 0.05, 0.1, 0.92), UI.GOLD_DIM, 8)
	nav = UI.hbox(8)
	nav.alignment = BoxContainer.ALIGNMENT_CENTER
	p.add_child(nav)
	for item in [["Lot", "lot"], ["Office PC", "pc"], ["Garage", "garage"], ["Showroom", "showroom"], ["Marco", "marco"]]:
		var b := UI.button(item[0], show_screen.bind(item[1]), 150, 52)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		nav.add_child(b)
	var end := UI.gold_button("End Day", _end_day, 150, 52)
	end.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	nav.add_child(end)
	return p


func set_bg(key: String, darkness: float) -> void:
	bg.texture = BG[key]
	dim.color = Color(0, 0, 0, darkness)


func show_screen(name: String) -> void:
	current = name
	auction_view = {}
	UI.clear(content)
	hud.get_parent().visible = name != "title"
	nav.get_parent().visible = name != "title"
	match name:
		"title": _screen_title()
		"lot": _screen_lot()
		"pc": _screen_pc()
		"garage": _screen_garage()
		"showroom": _screen_showroom()
		"marco": _screen_marco()


func show_title() -> void:
	show_screen("title")


# =====================================================================
# Title
# =====================================================================

func _screen_title() -> void:
	set_bg("lot", 0.55)
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
		v.add_child(UI.gold_button("Continue (Day %d)" % Game.day, _start_game, 320))
		v.add_child(UI.button("New Game", func():
			Game.reset_save()
			_start_game(), 320))
	else:
		v.add_child(UI.gold_button("Start", _start_game, 320))
	var tag := UI.label("Prototype build · Tewport Beach, Canioria", 14, UI.MUTED)
	tag.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(tag)


func _start_game() -> void:
	show_screen("lot")
	if not Game.seen_intro:
		Game.seen_intro = true
		Game.save_game()
		play_dialogue([
			["Marco", "CEO & Financial Advisor", "Welcome to OC Chief Auto. I'm Marco. I run this place, and I watch every dollar."],
			["Marco", "CEO & Financial Advisor", "Here's the job: win cars at auction on the office PC, get them fixed in the garage, then sell them in the showroom for more than you paid."],
			["Marco", "CEO & Financial Advisor", "You've got $40,000 and room for four cars. Rent is $400 a day. Sell at least one car a day and I'll throw you a bonus."],
			["Jeff", "Sales Associate", "Yo! Jeff here. Top salesman. Well, only salesman. If you get tired of selling, let Jeff handle it. Usually works!"],
			["Marco", "CEO & Financial Advisor", "...Usually. Start with the Office PC. Check the history reports before you bid. Don't buy a flood car."],
		], func(): pass)


# =====================================================================
# Lot (hub)
# =====================================================================

func _screen_lot() -> void:
	set_bg("lot", 0.1)
	var h := UI.hbox(16)
	content.add_child(h)
	var side := UI.panel()
	side.custom_minimum_size = Vector2(430, 0)
	side.size_flags_vertical = Control.SIZE_EXPAND_FILL
	h.add_child(side)
	var v := UI.vbox(10)
	side.add_child(v)
	v.add_child(UI.label("Your Lot  (%d / %d cars)" % [Game.cars.size(), Game.LOT_CAPACITY], 22, UI.GOLD, true))
	v.add_child(UI.para("Market today: %s are hot (+10%% sale price)." % _class_name(Game.hot_class), 15, UI.BLUE))
	var list := UI.vbox(8)
	v.add_child(UI.scroll(list))
	if Game.cars.is_empty():
		list.add_child(UI.para("The lot is empty. Head to the Office PC and win something at auction.", 17, UI.MUTED))
		list.add_child(UI.gold_button("Open Office PC", show_screen.bind("pc")))
	for car in Game.cars:
		list.add_child(_car_card(car))
	h.add_child(UI.spacer())


func _car_card(car: Dictionary) -> Control:
	var p := UI.panel(UI.PANEL_LIGHT, UI.GOLD_DIM, 10)
	var v := UI.vbox(4)
	p.add_child(v)
	v.add_child(UI.label("%d %s" % [car.year, car.model], 19, UI.TEXT, true))
	var cond := Game.condition(car)
	var row := UI.hbox(8)
	row.add_child(UI.label("Condition %d" % cond, 15, UI.cond_color(cond)))
	row.add_child(UI.bar(cond, 100, UI.cond_color(cond), 10))
	v.add_child(row)
	v.add_child(UI.para("Paid %s · Repairs %s · Est. value %s" % [Game.money_str(car.paid), Game.money_str(car.spent), Game.money_str(Game.value(car))], 14, UI.MUTED))
	var btns := UI.hbox(8)
	btns.add_child(UI.button("Repair", func():
		selected_car_id = car.id
		show_screen("garage"), 0, 38))
	btns.add_child(UI.button("Sell", func():
		selected_car_id = car.id
		show_screen("showroom"), 0, 38))
	v.add_child(btns)
	return p


func _class_name(c: String) -> String:
	return {"economy": "Economy cars", "truck": "Trucks", "suv": "SUVs", "sport": "Sports cars", "exotic": "Exotics"}[c]


# =====================================================================
# Office PC: AutoBidz browser
# =====================================================================

func _browser_frame(url: String) -> VBoxContainer:
	set_bg("office", 0.55)
	var win := UI.panel(Color(0.93, 0.94, 0.96, 0.98), Color(0.3, 0.3, 0.35), 0)
	win.size_flags_vertical = Control.SIZE_EXPAND_FILL
	content.add_child(win)
	var v := UI.vbox(0)
	win.add_child(v)
	# tab strip
	var tabs := UI.hbox(4)
	var strip := UI.panel(Color(0.78, 0.8, 0.85), Color.TRANSPARENT, 6)
	strip.add_child(tabs)
	v.add_child(strip)
	tabs.add_child(_tab("AutoBidz · Live Auctions", true))
	tabs.add_child(_tab("TewportBank  (Lvl 4)", false))
	tabs.add_child(_tab("Mail  (Lvl 2)", false))
	# address bar
	var addr_wrap := UI.panel(Color(0.93, 0.94, 0.96), Color.TRANSPARENT, 8)
	var addr := LineEdit.new()
	addr.text = url
	addr.editable = false
	addr_wrap.add_child(addr)
	v.add_child(addr_wrap)
	var body := MarginContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	for side in ["left", "right", "top", "bottom"]:
		body.add_theme_constant_override("margin_" + side, 14)
	v.add_child(body)
	var inner := UI.vbox(10)
	body.add_child(inner)
	return inner


func _tab(text: String, active: bool) -> Control:
	var p := UI.panel(Color(0.93, 0.94, 0.96) if active else Color(0.7, 0.72, 0.77), Color.TRANSPARENT, 8)
	p.add_child(UI.label(text, 14, Color(0.15, 0.15, 0.2) if active else Color(0.4, 0.4, 0.45)))
	return p


func _screen_pc() -> void:
	var inner := _browser_frame("https://www.autobidz.ca/live?region=orange-county")
	var head := UI.hbox(12)
	head.add_child(UI.label("AutoBidz", 30, Color("c0392b"), true))
	head.add_child(UI.label("Orange County Dealer Auction · Day %d" % Game.day, 16, Color(0.35, 0.35, 0.4)))
	head.add_child(UI.spacer())
	head.add_child(UI.label("Lot space: %d / %d" % [Game.cars.size(), Game.LOT_CAPACITY], 16, Color(0.35, 0.35, 0.4)))
	inner.add_child(head)
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 12)
	grid.add_theme_constant_override("v_separation", 12)
	inner.add_child(UI.scroll(grid))
	for l in Game.listings:
		grid.add_child(_listing_card(l))


func _web_box() -> PanelContainer:
	return UI.panel(Color.WHITE, Color(0.8, 0.8, 0.85), 12)


func _listing_card(l: Dictionary) -> Control:
	var car: Dictionary = l.car
	var p := _web_box()
	p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var v := UI.vbox(4)
	p.add_child(v)
	var dark := Color(0.12, 0.12, 0.16)
	var grey := Color(0.4, 0.4, 0.45)
	v.add_child(UI.label("%d %s" % [car.year, car.model], 19, dark, true))
	v.add_child(UI.label("%s mi · Grade %s" % [_num(car.miles), _grade(Game.condition(car))], 15, grey))
	var status := ""
	var col := Color("1e7e34")
	if l.sold:
		status = "SOLD to you" if l.winner == "you" else "Sold to %s" % l.winner
		col = Color("1e7e34") if l.winner == "you" else grey
	else:
		status = "Current bid %s" % Game.money_str(l.current)
		col = Color("c0392b")
	v.add_child(UI.label(status, 16, col))
	if l.buy_now > 0 and not l.sold:
		v.add_child(UI.label("Buy It Now %s" % Game.money_str(l.buy_now), 14, Color("1f6fb2")))
	v.add_child(UI.button("View listing", _open_listing.bind(l), 0, 40))
	return p


func _num(n: int) -> String:
	return Game.money_str(n).substr(1)


func _grade(cond: int) -> String:
	return "%.1f / 5" % (1.0 + cond / 25.0)


func _open_listing(l: Dictionary) -> void:
	UI.clear(content)
	auction_view = {}
	var car: Dictionary = l.car
	var inner := _browser_frame("https://www.autobidz.ca/listing/%d" % car.id)
	var dark := Color(0.12, 0.12, 0.16)
	var grey := Color(0.4, 0.4, 0.45)
	var top := UI.hbox(10)
	top.add_child(UI.button("← All listings", func():
		show_screen("pc"), 0, 36))
	top.add_child(UI.label("%d %s" % [car.year, car.model], 26, dark, true))
	inner.add_child(top)
	var cols := UI.hbox(14)
	cols.size_flags_vertical = Control.SIZE_EXPAND_FILL
	inner.add_child(cols)

	# left: details
	var left := _web_box()
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cols.add_child(left)
	var lv := UI.vbox(6)
	left.add_child(lv)
	lv.add_child(UI.label("%s mi · %s · Seller grade %s" % [_num(car.miles), _class_name(car.cls).trim_suffix("s"), _grade(Game.condition(car))], 16, grey))
	lv.add_child(UI.label("Condition report (from seller)", 17, dark, true))
	for part in Game.PARTS:
		var row := UI.hbox(8)
		var name_l := UI.label(Game.PART_NAMES[part], 15, dark)
		name_l.custom_minimum_size = Vector2(140, 0)
		row.add_child(name_l)
		row.add_child(UI.bar(car.parts[part], 100, UI.cond_color(car.parts[part]), 10))
		row.add_child(UI.label(str(car.parts[part]), 15, dark))
		lv.add_child(row)
	lv.add_child(UI.label("Est. retail value: %s" % Game.money_str(Game.value(car)), 16, dark))
	var hist := UI.vbox(4)
	lv.add_child(hist)
	_fill_history(hist, car)

	# right: bidding
	var right := _web_box()
	right.custom_minimum_size = Vector2(380, 0)
	cols.add_child(right)
	var rv := UI.vbox(8)
	right.add_child(rv)
	if l.sold:
		rv.add_child(UI.label("Auction closed", 22, dark, true))
		rv.add_child(UI.label("Won by %s for %s" % ["you" if l.winner == "you" else l.winner, Game.money_str(l.current)], 17, grey))
		return
	var cur := UI.label("", 28, Color("c0392b"), true)
	var lead := UI.label("", 16, grey)
	var time_l := UI.label("", 16, dark)
	var feed := UI.label("", 14, grey)
	rv.add_child(UI.label("Current bid", 15, grey))
	rv.add_child(cur)
	rv.add_child(lead)
	rv.add_child(time_l)
	var bid_btn := UI.gold_button("", _place_bid.bind(l))
	rv.add_child(bid_btn)
	if l.buy_now > 0:
		var bn := UI.button("Buy It Now: %s" % Game.money_str(l.buy_now), _buy_now.bind(l))
		rv.add_child(bn)
		if not l.haggled:
			rv.add_child(UI.button("Haggle with seller", _haggle.bind(l)))
	rv.add_child(feed)
	auction_view = {"listing": l, "cur": cur, "lead": lead, "time": time_l, "bid": bid_btn, "feed": feed}
	_refresh_auction_view()


func _fill_history(hist: VBoxContainer, car: Dictionary) -> void:
	UI.clear(hist)
	var dark := Color(0.12, 0.12, 0.16)
	if car.history_known:
		var col := Color("1e7e34") if car.history == "Clean" else Color("c0392b")
		hist.add_child(UI.label("History report: %s" % car.history, 16, col, true))
		if car.has("faults_found"):
			var f: Array = car.faults_found
			hist.add_child(UI.para("Inspection: " + ("no hidden problems." if f.is_empty() else "hidden problems in " + ", ".join(f) + "."), 15, dark))
	else:
		hist.add_child(UI.button("Buy history + inspection report (%s)" % Game.money_str(Game.HISTORY_REPORT_COST), func():
			if Game.spend(Game.HISTORY_REPORT_COST):
				car.history_known = true
				car.faults_found = Game.reveal_faults(car)
				Game.save_game()
				_fill_history(hist, car)
			else:
				toast("Not enough money."), 0, 40))


func bid_increment(l: Dictionary) -> int:
	return max(100, int(round(Game.value(l.car) * 0.03 / 100.0)) * 100)


func _place_bid(l: Dictionary) -> void:
	if Game.cars.size() >= Game.LOT_CAPACITY:
		toast("Your lot is full. Sell a car first.")
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
	if l.leader == "":
		auction_view.lead.text = "No bids yet"
	else:
		auction_view.lead.text = "Leading: " + ("YOU" if l.leader == "you" else l.leader)
	if auction == l:
		auction_view.time.text = "Closes in %ds" % ceil(auction_timer)
	else:
		auction_view.time.text = "Place a bid to start the clock"
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
		if Game.spend(l.current):
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
	if Game.cars.size() >= Game.LOT_CAPACITY:
		toast("Your lot is full. Sell a car first.")
		return
	if not Game.spend(l.buy_now):
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


# =====================================================================
# Garage: repairs
# =====================================================================

func _find_car(id: int) -> Dictionary:
	for c in Game.cars:
		if c.id == id:
			return c
	return {}


func _car_picker(parent: Control, on_pick: Callable) -> void:
	var side := UI.panel()
	side.custom_minimum_size = Vector2(300, 0)
	parent.add_child(side)
	var v := UI.vbox(8)
	side.add_child(v)
	v.add_child(UI.label("Your cars", 20, UI.GOLD, true))
	for car in Game.cars:
		var b := UI.button("%s\nCondition %d" % [car.model, Game.condition(car)], func():
			selected_car_id = car.id
			on_pick.call(), 0, 60)
		if car.id == selected_car_id:
			b.add_theme_stylebox_override("normal", UI.box(Color(0.3, 0.24, 0.1, 0.95), UI.GOLD, 8, 2, 14))
		v.add_child(b)


func _screen_garage() -> void:
	set_bg("map", 0.6)
	if Game.cars.is_empty():
		_empty_note("Nothing in the garage yet. Win a car on the Office PC first.")
		return
	if _find_car(selected_car_id).is_empty():
		selected_car_id = Game.cars[0].id
	var car := _find_car(selected_car_id)
	var h := UI.hbox(16)
	content.add_child(h)
	_car_picker(h, show_screen.bind("garage"))

	var main := UI.panel()
	main.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(main)
	var v := UI.vbox(10)
	main.add_child(v)
	v.add_child(UI.label("Service Bay · %d %s" % [car.year, car.model], 24, UI.GOLD, true))
	var cond := Game.condition(car)
	v.add_child(UI.para("Overall condition %d   ·   Est. value %s   ·   Spent on repairs %s" % [cond, Game.money_str(Game.value(car)), Game.money_str(car.spent)], 16, UI.MUTED))

	var mech_row := UI.hbox(10)
	mech_row.add_child(UI.label("Mechanic:", 18))
	var opt := OptionButton.new()
	opt.custom_minimum_size = Vector2(0, 44)
	opt.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for i in Game.MECHANICS.size():
		var m: Dictionary = Game.MECHANICS[i]
		if Game.level >= m.level:
			opt.add_item("%s (%s) · +%d-%d quality · %d%% botch risk" % [m.name, m.where, m.min, m.max, int(m.botch * 100)], i)
		else:
			opt.add_item("%s · unlocks at Level %d" % [m.name, m.level], i)
			opt.set_item_disabled(opt.get_item_index(i), true)
	if Game.level < Game.MECHANICS[mechanic_index].level:
		mechanic_index = 0
	opt.select(opt.get_item_index(mechanic_index))
	opt.item_selected.connect(func(idx):
		mechanic_index = opt.get_item_id(idx)
		show_screen("garage"))
	mech_row.add_child(opt)
	v.add_child(mech_row)

	var mech: Dictionary = Game.MECHANICS[mechanic_index]
	for part in Game.PARTS:
		var row := UI.hbox(10)
		var nl := UI.label(Game.PART_NAMES[part], 17)
		nl.custom_minimum_size = Vector2(150, 0)
		row.add_child(nl)
		var val: int = car.parts[part]
		row.add_child(UI.bar(val, 100, UI.cond_color(val), 14))
		var vl := UI.label(str(val), 17, UI.cond_color(val))
		vl.custom_minimum_size = Vector2(40, 0)
		row.add_child(vl)
		var cost := _repair_cost(car, mech)
		var b := UI.button("Repair %s" % Game.money_str(cost), _repair.bind(car, part, mech), 170, 42)
		b.disabled = val >= 100
		row.add_child(b)
		v.add_child(row)
	var det_cost := _detail_cost(car)
	var det := UI.button("Detailing %s  (buyers love a shiny car)" % Game.money_str(det_cost) if not car.detailed else "Detailed ✓", func():
		if Game.spend(det_cost):
			car.detailed = true
			car.spent += det_cost
			garage_log = "The detailer made it sparkle. Buyers will notice."
			Game.save_game()
			show_screen("garage")
		else:
			toast("Not enough money."), 0, 44)
	det.disabled = car.detailed
	v.add_child(det)
	if garage_log != "":
		v.add_child(UI.para(garage_log, 16, UI.GOOD))


func _repair_cost(car: Dictionary, mech: Dictionary) -> int:
	return max(100, int(round(car.base * mech.cost / 50.0)) * 50)


func _detail_cost(car: Dictionary) -> int:
	return max(150, int(round(car.base * 0.004 / 50.0)) * 50)


func _repair(car: Dictionary, part: String, mech: Dictionary) -> void:
	var cost := _repair_cost(car, mech)
	if not Game.spend(cost):
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
		# The botch stays secret until a buyer finds it.
		var bad: String = Game.PARTS.pick_random()
		car.hidden[bad] = car.hidden.get(bad, 0) + randi_range(10, 20)
	var lines := {
		"Cousin Ray": ["\"Good as new, cuz. Mostly.\"", "\"I used the good duct tape.\"", "\"Don't worry about that noise.\""],
		"Strip-Mall Auto": ["\"Done. Cash or card?\"", "\"All fixed, boss.\""],
		"Harbor Certified": ["\"Serviced to spec.\"", "\"Torqued and tested.\""],
		"Euro Specialist": ["\"Perfetto.\"", "\"She sings now.\""],
	}
	msg += "%s +%d. %s" % [Game.PART_NAMES[part], gain, lines[mech.name].pick_random()]
	garage_log = msg
	Game.save_game()
	show_screen("garage")


func _empty_note(text: String) -> void:
	var c := CenterContainer.new()
	content.add_child(c)
	var p := UI.panel()
	c.add_child(p)
	var v := UI.vbox(12)
	p.add_child(v)
	v.add_child(UI.para(text, 20))
	v.add_child(UI.gold_button("Open Office PC", show_screen.bind("pc")))


# =====================================================================
# Showroom: pricing, sell yourself or let Jeff try
# =====================================================================

func _sale_value(car: Dictionary) -> int:
	var v := float(Game.value(car))
	if car.cls == Game.hot_class:
		v *= 1.1
	if Game.has_perk("vip") and car.cls in ["sport", "exotic"]:
		v *= 1.1
	return int(round(v / 50.0) * 50)


func _screen_showroom() -> void:
	set_bg("lot", 0.45)
	if Game.cars.is_empty():
		_empty_note("No cars to sell. Win one at auction first.")
		return
	if _find_car(selected_car_id).is_empty():
		selected_car_id = Game.cars[0].id
	var car := _find_car(selected_car_id)
	if not car.has("ask"):
		car.ask = int(round(_sale_value(car) * 1.1 / 100.0)) * 100
	if car.get("attempt_day", 0) != Game.day:
		car.attempt_day = Game.day
		car.attempts = 0
	var h := UI.hbox(16)
	content.add_child(h)
	_car_picker(h, show_screen.bind("showroom"))
	var main := UI.panel()
	main.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(main)
	var v := UI.vbox(12)
	main.add_child(v)
	v.add_child(UI.label("Showroom · %d %s" % [car.year, car.model], 24, UI.GOLD, true))
	var cond := Game.condition(car)
	var fair := _sale_value(car)
	v.add_child(UI.para("Condition %d%s   ·   You paid %s + %s repairs" % [cond, "  ·  Detailed" if car.detailed else "", Game.money_str(car.paid), Game.money_str(car.spent)], 16, UI.MUTED))
	var hot := "  (hot market today: +10%)" if car.cls == Game.hot_class else ""
	v.add_child(UI.label("Marco's fair price: %s%s" % [Game.money_str(fair), hot], 18, UI.BLUE))
	if Game.has_perk("insights"):
		v.add_child(UI.para("Market Insights: buyers will stretch to about %s-%s." % [Game.money_str(fair * 0.95), Game.money_str(fair * 1.2)], 15, UI.GOOD))

	var ask_l := UI.label("", 22, UI.TEXT, true)
	var profit_l := UI.label("", 16)
	var slider := HSlider.new()
	slider.min_value = int(fair * 0.7 / 100) * 100
	slider.max_value = int(fair * 1.5 / 100) * 100
	slider.step = 100
	slider.value = car.ask
	slider.custom_minimum_size = Vector2(0, 36)
	var update := func(val):
		car.ask = int(val)
		ask_l.text = "Asking price: " + Game.money_str(car.ask)
		var profit: int = car.ask - car.paid - car.spent
		profit_l.text = "Profit if sold at asking: " + Game.money_str(profit)
		profit_l.add_theme_color_override("font_color", UI.GOOD if profit >= 0 else UI.BAD)
	slider.value_changed.connect(update)
	update.call(car.ask)
	v.add_child(ask_l)
	v.add_child(slider)
	v.add_child(profit_l)
	v.add_child(UI.para("Higher prices make buyers harder to win over. Repairs and detailing make them easier.", 15, UI.MUTED))
	var left: int = 2 - car.attempts
	v.add_child(UI.label("Buyers left for this car today: %d" % left, 16, UI.GOLD))
	var btns := UI.hbox(12)
	var sell := UI.gold_button("Find a buyer (sell it yourself)", _start_sale.bind(car), 0, 56)
	sell.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sell.disabled = left <= 0
	btns.add_child(sell)
	var jeff := UI.button("Let Jeff handle it", _jeff_sale.bind(car), 0, 56)
	jeff.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	jeff.disabled = left <= 0
	btns.add_child(jeff)
	v.add_child(btns)


func _jeff_sale(car: Dictionary) -> void:
	car.attempts += 1
	Game.stats.buyers += 1
	var chance := 0.3 + Game.reputation * 0.03 + (0.1 if car.detailed else 0.0)
	var over: float = float(car.ask) / max(1, _sale_value(car))
	chance -= max(0.0, over - 1.0) * 0.8
	if randf() < chance:
		var price := int(round(car.ask * randf_range(0.85, 1.0) / 100.0)) * 100
		var lines := [["Jeff", "Sales Associate", "BOOM. Sold the %s for %s. Told 'em it was a limited edition. Is it? Who knows!" % [car.model, Game.money_str(price)]]]
		var forgot := randf() < 0.2
		if forgot:
			lines.append(["Marco", "CEO & Financial Advisor", "Jeff forgot the odometer form again. That's a $500 fine from the state. Jeff."])
		play_dialogue(lines, func():
			_complete_sale(car, price, 0, forgot, "Jeff"))
	else:
		var fails := [
			"The buyer asked about gas mileage. I said 'yes.' They left.",
			"I may have called the customer 'bro' eleven times. Too many?",
			"I locked the keys in the car during the test drive. Lost that one.",
			"They wanted a car seat. I recommended the trunk. They left fast.",
		]
		play_dialogue([["Jeff", "Sales Associate", fails.pick_random()]], func():
			Game.save_game()
			show_screen("showroom"))


# =====================================================================
# Sales minigame
# =====================================================================

const CARDS := [
	{"id": "features", "name": "Talk up features", "desc": "+5 to +15 if they care about it"},
	{"id": "test_drive", "name": "Test drive", "desc": "Great on good cars. Can expose hidden faults.", "once": true},
	{"id": "history", "name": "Show history report", "desc": "Builds trust if the history is clean", "once": true},
	{"id": "discount", "name": "Knock off 5%", "desc": "Reliable boost, costs profit"},
	{"id": "extras", "name": "Throw in extras ($300)", "desc": "Floor mats, oil changes, a hat", "once": true},
	{"id": "stretch", "name": "Stretch the truth", "desc": "Big boost. Risk of a bad review."},
	{"id": "close", "name": "Close the deal", "desc": "Works above 70 interest. Risky below."},
]


func _start_sale(car: Dictionary) -> void:
	car.attempts += 1
	Game.stats.buyers += 1
	var type_key: String = Game.BUYER_TYPES.keys().pick_random()
	var bt: Dictionary = Game.BUYER_TYPES[type_key]
	var fair := float(_sale_value(car))
	var start: float = 0.5 * Game.condition(car) + (10 if car.detailed else 0) - 40.0 * (car.ask - fair) / fair
	sale = {
		"car": car, "type": type_key, "bt": bt, "name": Game.BUYER_NAMES.pick_random(),
		"interest": clamp(start, 5.0, 85.0), "patience": bt.patience, "used": [],
		"ask": car.ask, "cap": int(Game.value(car, true) * bt.budget * (1.1 if car.cls == Game.hot_class else 1.0) * (1.1 if Game.has_perk("vip") and car.cls in ["sport", "exotic"] else 1.0)),
		"log": ["%s: \"%s\"" % [Game.BUYER_NAMES.pick_random(), bt.intro]], "extras": 0, "stretched": false,
	}
	sale.log[0] = "%s: \"%s\"" % [sale.name, bt.intro]
	_render_sale()


func _render_sale() -> void:
	UI.clear(overlay)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	var shade := ColorRect.new()
	shade.color = Color(0, 0, 0, 0.55)
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(shade)
	var m := MarginContainer.new()
	m.set_anchors_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right", "top", "bottom"]:
		m.add_theme_constant_override("margin_" + side, 40)
	overlay.add_child(m)
	var p := UI.panel(Color(0.04, 0.07, 0.13, 0.97), UI.GOLD, 20)
	m.add_child(p)
	var h := UI.hbox(20)
	p.add_child(h)

	var car: Dictionary = sale.car
	var left := UI.vbox(10)
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(left)
	left.add_child(UI.label("%s · %s" % [sale.name, sale.bt.title], 26, UI.GOLD, true))
	left.add_child(UI.para("Looking at the %d %s · Asking %s" % [car.year, car.model, Game.money_str(sale.ask)], 17, UI.MUTED))
	var ir := UI.hbox(10)
	ir.add_child(UI.label("Interest", 18))
	var ic: Color = UI.GOOD if sale.interest >= 70 else (UI.GOLD if sale.interest >= 40 else UI.BAD)
	ir.add_child(UI.bar(sale.interest, 100, ic, 20))
	ir.add_child(UI.label(str(int(sale.interest)), 20, ic, true))
	left.add_child(ir)
	var pips := ""
	for i in sale.bt.patience:
		pips += "● " if i < sale.patience else "○ "
	left.add_child(UI.label("Patience  " + pips, 18, UI.GOLD))
	var log_box := UI.vbox(6)
	for line in sale.log:
		log_box.add_child(UI.para(line, 16))
	left.add_child(UI.scroll(log_box))

	var right := UI.vbox(8)
	right.custom_minimum_size = Vector2(430, 0)
	h.add_child(right)
	right.add_child(UI.label("Your move", 20, UI.GOLD, true))
	for c in CARDS:
		var used: bool = c.get("once", false) and c.id in sale.used
		var b := UI.button("%s\n%s" % [c.name, c.desc], _play_card.bind(c.id), 0, 58)
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.add_theme_font_size_override("font_size", 16)
		b.disabled = used
		right.add_child(b)
	right.add_child(UI.button("Walk away", func():
		_end_sale_overlay()
		show_screen("showroom"), 0, 40))


func _say(text: String) -> void:
	sale.log.append(text)


func _play_card(id: String) -> void:
	var car: Dictionary = sale.car
	var likes: Array = sale.bt.likes
	var boost := 1.5 if id in likes else 1.0
	sale.used.append(id)
	sale.patience -= 1
	match id:
		"features":
			var g := randi_range(5, 15) if (id in likes or car.cls in ["sport", "exotic"]) else randi_range(1, 6)
			sale.interest += g * boost
			_say("You: \"Heated seats, premium sound, and it turns heads on Coast Highway.\"  (+%d)" % int(g * boost))
		"test_drive":
			var finds: bool = sale.type == "nerd" or randf() < 0.6
			if Game.hidden_total(car) > 0 and finds:
				var found := Game.reveal_faults(car)
				sale.interest -= 20
				_say("%s: \"Why is the %s doing THAT?\"  The test drive exposed a problem.  (-20)" % [sale.name, found[0].to_lower()])
			else:
				var g2 := Game.condition(car) / 7.0 * boost
				sale.interest += g2
				_say("%s: \"Oh, this drives nice.\"  (+%d)" % [sale.name, int(g2)])
		"history":
			if car.history == "Clean":
				sale.interest += 10 * boost
				_say("%s: \"Clean history. I like that.\"  (+%d)" % [sale.name, int(10 * boost)])
			else:
				car.history_known = true
				sale.interest -= 12
				_say("%s: \"%s? Hmm.\"  (-12)" % [sale.name, car.history])
		"discount":
			sale.ask = int(round(sale.ask * 0.95 / 100.0)) * 100
			var g3 := 14 if sale.type == "bargain" else 8
			sale.interest += g3
			_say("You: \"For you? %s.\"  (+%d)" % [Game.money_str(sale.ask), g3])
		"extras":
			sale.extras += 300
			sale.interest += 6 * boost
			_say("You: \"I'll throw in floor mats and a year of oil changes.\"  (+%d)" % int(6 * boost))
		"stretch":
			sale.interest += 20
			sale.stretched = true
			_say("You: \"Honestly? A celebrity almost bought this one yesterday.\"  (+20)")
		"close":
			sale.patience += 1
			if sale.interest >= 70 or (sale.interest >= 50 and randf() < 0.5):
				_buyer_agrees()
				return
			_say("%s: \"Whoa, slow down. I'm out.\"" % sale.name)
			_buyer_walks()
			return
	sale.interest = clamp(sale.interest, 0, 100)
	if sale.interest >= 100:
		_say("%s: \"Okay, okay. I'm in!\"" % sale.name)
		_buyer_agrees()
		return
	if sale.patience <= 0:
		if sale.interest >= 70:
			_buyer_agrees()
		else:
			_say("%s: \"I need to think about it.\" They leave." % sale.name)
			_buyer_walks()
		return
	_render_sale()


func _buyer_walks() -> void:
	_render_sale()
	var car: Dictionary = sale.car
	await get_tree().create_timer(1.2).timeout
	_end_sale_overlay()
	Game.save_game()
	toast("The buyer walked. Try another buyer or adjust the price.")
	selected_car_id = car.id
	show_screen("showroom")


func _buyer_agrees() -> void:
	var price: int = sale.ask
	if sale.cap < price:
		price = int(round(sale.cap / 100.0)) * 100
		_say("%s: \"I love it, but my max is %s.\"  (Buyers pay for the car's real condition and history.)" % [sale.name, Game.money_str(price)])
		_render_sale()
		_counter_offer(price)
		return
	_say("%s: \"Deal at %s!\"" % [sale.name, Game.money_str(price)])
	_render_sale()
	await get_tree().create_timer(0.8).timeout
	_open_paperwork(price)


func _counter_offer(price: int) -> void:
	var c := CenterContainer.new()
	c.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(c)
	var p := UI.panel(UI.NAVY_SOLID, UI.GOLD, 24)
	c.add_child(p)
	var v := UI.vbox(12)
	p.add_child(v)
	v.add_child(UI.label("Counteroffer: %s" % Game.money_str(price), 26, UI.GOLD, true))
	var car: Dictionary = sale.car
	v.add_child(UI.para("Profit at this price: %s" % Game.money_str(price - car.paid - car.spent - sale.extras), 18))
	var h := UI.hbox(12)
	h.add_child(UI.gold_button("Accept", func(): _open_paperwork(price), 200))
	h.add_child(UI.button("Decline", func():
		_say("You: \"Can't go that low.\"")
		_buyer_walks(), 200))
	v.add_child(h)


func _end_sale_overlay() -> void:
	UI.clear(overlay)
	overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE


# =====================================================================
# Paperwork
# =====================================================================

func _open_paperwork(price: int) -> void:
	var car: Dictionary = sale.car
	var wrong_doc := randi_range(0, 2) if randf() < 0.5 else -1
	var docs := [
		{"title": "Bill of Sale", "field": "Price", "value": Game.money_str(price), "wrong": Game.money_str(price - randi_range(10, 40) * 100)},
		{"title": "Odometer Disclosure", "field": "Mileage", "value": _num(car.miles) + " mi", "wrong": _num(car.miles - randi_range(20, 60) * 1000) + " mi"},
		{"title": "Title Transfer", "field": "Buyer", "value": sale.name + " (verified ID)", "wrong": sale.name + " (ID not checked)"},
	]
	for i in docs.size():
		docs[i].signed = false
		docs[i].error = i == wrong_doc
	sale.paper = {"price": price, "docs": docs, "addons": {"warranty": false, "financing": false, "protect": false}, "time": 30.0, "mistakes": 0}
	_render_paperwork()
	_paper_tick()


func _paper_tick() -> void:
	while sale.has("paper") and sale.paper.time > 0:
		await get_tree().create_timer(1.0).timeout
		if not sale.has("paper"):
			return
		sale.paper.time -= 1
		if sale.paper.has("time_label") and is_instance_valid(sale.paper.time_label):
			sale.paper.time_label.text = "Buyer patience: %ds" % int(sale.paper.time)
	if sale.has("paper"):
		toast("You took too long. The buyer is annoyed.")
		Game.change_rep(-0.1)
		_finish_paperwork()


func _render_paperwork() -> void:
	UI.clear(overlay)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	var shade := ColorRect.new()
	shade.color = Color(0, 0, 0, 0.6)
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(shade)
	var m := MarginContainer.new()
	m.set_anchors_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right", "top", "bottom"]:
		m.add_theme_constant_override("margin_" + side, 50)
	overlay.add_child(m)
	var p := UI.panel(Color(0.96, 0.95, 0.9), Color(0.5, 0.45, 0.3), 22)
	m.add_child(p)
	var v := UI.vbox(10)
	p.add_child(v)
	var ink := Color(0.12, 0.12, 0.16)
	var paper: Dictionary = sale.paper
	var head := UI.hbox(10)
	head.add_child(UI.label("Closing paperwork · %s" % sale.car.model, 24, ink, true))
	head.add_child(UI.spacer())
	paper.time_label = UI.label("Buyer patience: %ds" % int(paper.time), 18, Color("c0392b"))
	head.add_child(paper.time_label)
	v.add_child(head)
	v.add_child(UI.para("Check every document against the deal before signing. A wrong number costs money and reputation.", 15, Color(0.35, 0.35, 0.4)))
	var deal := UI.panel(Color(1, 1, 1), Color(0.75, 0.7, 0.55), 10)
	deal.add_child(UI.label("The deal:  %s  ·  %s mi on the odometer  ·  buyer %s, ID checked" % [Game.money_str(paper.price), _num(sale.car.miles), sale.name], 16, ink, true))
	v.add_child(deal)
	for d in paper.docs:
		var row := UI.hbox(12)
		row.custom_minimum_size = Vector2(0, 50)
		var t := UI.label(d.title, 18, ink, true)
		t.custom_minimum_size = Vector2(220, 0)
		row.add_child(t)
		var shown: String = d.wrong if d.error else d.value
		var f := UI.label("%s: %s" % [d.field, shown], 17, ink)
		f.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(f)
		if d.signed:
			row.add_child(UI.label("Signed ✓", 17, Color("1e7e34"), true))
		else:
			row.add_child(UI.button("Fix error", func():
				if d.error:
					d.error = false
					toast("Good catch.")
				else:
					paper.time -= 3
					toast("Nothing wrong there. (-3s)")
				_render_paperwork(), 130, 42))
			row.add_child(UI.gold_button("Sign", func():
				d.signed = true
				if d.error:
					paper.mistakes += 1
				_render_paperwork(), 110, 42))
		v.add_child(row)
	v.add_child(UI.para("Offer add-ons (each one the buyer accepts adds profit; pushing too many annoys them):", 16, ink))
	var addons := UI.hbox(10)
	for a in [["warranty", "Extended warranty (+$1,200)"], ["financing", "Dealer financing (+$700)"], ["protect", "Paint protection (+$400)"]]:
		var cb := CheckBox.new()
		cb.text = a[1]
		cb.button_pressed = paper.addons[a[0]]
		cb.add_theme_color_override("font_color", ink)
		cb.add_theme_color_override("font_pressed_color", ink)
		cb.add_theme_color_override("font_hover_color", Color(0.3, 0.3, 0.4))
		cb.toggled.connect(func(on): paper.addons[a[0]] = on)
		addons.add_child(cb)
	v.add_child(addons)
	var all_signed: bool = paper.docs.all(func(d): return d.signed)
	var fin := UI.gold_button("Hand over the keys", _finish_paperwork, 0, 54)
	fin.disabled = not all_signed
	v.add_child(fin)


func _finish_paperwork() -> void:
	var paper: Dictionary = sale.paper
	sale.erase("paper")
	var car: Dictionary = sale.car
	var addon_total := 0
	var offered := 0
	var accepted := []
	var vals := {"warranty": 1200, "financing": 700, "protect": 400}
	for k in paper.addons:
		if paper.addons[k]:
			offered += 1
	for k in paper.addons:
		if paper.addons[k] and randf() < 0.25 + sale.interest / 250.0 - offered * 0.05:
			addon_total += vals[k]
			accepted.append(k)
	var fine: int = paper.mistakes * 1000
	_end_sale_overlay()
	_complete_sale(car, paper.price, addon_total - sale.extras, false, "you", fine, accepted.size(), offered)


# =====================================================================
# Completing a sale
# =====================================================================

func _complete_sale(car: Dictionary, price: int, extra: int, jeff_forgot: bool, seller: String, fine := 0, addons_ok := 0, addons_offered := 0) -> void:
	var penalty := fine + (500 if jeff_forgot else 0)
	var total := price + extra - penalty
	Game.earn(total)
	var profit: int = total - car.paid - car.spent
	Game.stats.sold += 1
	Game.stats.goal_sold_today += 1
	Game.stats.profit += profit
	Game.stats.days_held += Game.day - car.day_bought
	var rep_change := 0.05
	var notes := []
	if Game.hidden_total(car) > 0:
		rep_change -= 0.25
		notes.append("Heads up: the car had a hidden problem. Expect a bad review.")
	if sale.get("stretched", false) and randf() < 0.35:
		rep_change -= 0.3
		notes.append("The buyer found out you stretched the truth. One-star review.")
	if fine > 0:
		notes.append("Paperwork mistakes cost %s in fees." % Game.money_str(fine))
		rep_change -= 0.1
	if Game.condition(car, true) >= 80:
		rep_change += 0.1
	Game.change_rep(rep_change)
	Game.remove_car(car)
	var leveled := Game.add_xp(max(10, int(profit / 50)) + 10)
	Game.save_game()
	sale = {}
	var lines := []
	var who := "Jeff" if seller == "Jeff" else "You"
	var summary := "%s sold the %s for %s." % [who, car.model, Game.money_str(price)]
	if extra > 0:
		summary += " Add-ons brought in %s more." % Game.money_str(extra)
	summary += " Profit: %s." % Game.money_str(profit)
	if addons_offered > 0 and seller == "you":
		summary += " (%d of %d add-ons accepted.)" % [addons_ok, addons_offered]
	var reaction := "Not bad. Keep that margin up."
	if profit > 5000:
		reaction = "Now THAT is how we do it at Chief Auto."
	elif profit < 0:
		reaction = "We lost money on that one. Buy smarter or fix smarter."
	lines.append(["Marco", "CEO & Financial Advisor", summary + " " + reaction])
	for n in notes:
		lines.append(["Marco", "CEO & Financial Advisor", n])
	if leveled:
		lines.append(["Marco", "CEO & Financial Advisor", "You hit Level %d. %s" % [Game.level, _unlock_text()]])
	play_dialogue(lines, show_screen.bind("lot"))


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
# Marco: CEO & financial advisor
# =====================================================================

func _screen_marco() -> void:
	set_bg("office", 0.15)
	var h := UI.hbox(16)
	content.add_child(h)
	h.add_child(UI.spacer())
	var p := UI.panel()
	p.custom_minimum_size = Vector2(470, 0)
	h.add_child(p)
	var v := UI.vbox(10)
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
	v.add_child(UI.label("Advisor Perks", 19, UI.GOLD, true))
	for perk in Game.PERKS:
		var on: bool = Game.level >= perk.level
		var col: Color = UI.TEXT if on else UI.MUTED
		v.add_child(UI.label(("✓ " if on else "Lvl %d · " % perk.level) + perk.name, 17, col, true))
		v.add_child(UI.para(perk.desc, 14, UI.MUTED))
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
	if Game.money < 10000:
		t.append(["Marco", who, "Cash is tight. Don't bid on anything you can't fix AND carry for a few days. Rent doesn't care."])
	if Game.cars.size() >= Game.LOT_CAPACITY:
		t.append(["Marco", who, "Lot's full. A car sitting here is money sitting still. Sell something, even at a thinner margin."])
	for car in Game.cars:
		if Game.condition(car) < 55:
			t.append(["Marco", who, "That %s is rough. Fix the worst parts first; buyers judge the whole car by its weakest spot." % car.model])
			break
	if Game.reputation < 2.5:
		t.append(["Marco", who, "Our reviews are slipping. Stop stretching the truth and stop selling cars with hidden problems."])
	t.append(["Marco", who, ["Always pull the history report. A flood car looks fine until it doesn't.", "Cousin Ray is cheap for a reason. Use him on body work, not engines.", "Detailing is the cheapest profit in this business.", "When a buyer is past 70 interest, close. Don't get greedy."].pick_random()])
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
	var box := UI.panel(Color(0.04, 0.07, 0.13, 0.94), UI.BLUE, 20)
	box.anchor_left = 0.2
	box.anchor_right = 0.8
	box.anchor_top = 1.0
	box.anchor_bottom = 1.0
	box.offset_top = -250
	box.offset_bottom = -90
	overlay.add_child(box)
	var v := UI.vbox(8)
	box.add_child(v)
	v.add_child(UI.label("%s · %s" % [line[0].to_upper(), line[1].to_upper()], 19, Color("8fc3ff"), true))
	var text := UI.para(line[2], 19)
	text.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(text)
	var h := UI.hbox()
	h.add_child(UI.spacer())
	h.add_child(UI.button("Continue ▸", _show_next_line, 160, 40))
	v.add_child(h)


func toast(text: String) -> void:
	var p := UI.panel(Color(0.05, 0.08, 0.14, 0.95), UI.GOLD, 14)
	p.anchor_left = 0.5
	p.anchor_right = 0.5
	p.offset_left = -330
	p.offset_right = 330
	p.offset_top = 86
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var l := UI.para(text, 17)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	p.add_child(l)
	add_child(p)
	var tw := create_tween()
	tw.tween_interval(2.4)
	tw.tween_property(p, "modulate:a", 0.0, 0.4)
	tw.tween_callback(p.queue_free)


func _end_day() -> void:
	if not auction.is_empty():
		auction_timer = 0
		_finish_auction()
	var notes := Game.end_day()
	var lines := []
	var text := "End of day. " + " ".join(notes) + " New cars are up on AutoBidz."
	lines.append(["Marco", "CEO & Financial Advisor", text])
	if Game.money < 0:
		lines.append(["Marco", "CEO & Financial Advisor", "We're in the red. Sell something tomorrow or I'm calling the bank. And my mother."])
	lines.append(_marco_tips()[0])
	play_dialogue(lines, show_screen.bind("lot"))
