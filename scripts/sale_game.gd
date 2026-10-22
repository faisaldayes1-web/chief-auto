class_name SaleGame
extends Control
## The walk-in sale minigame: read the customer, play three rounds of pitch cards, then a timing beat on the price
## needle. A deal hands off to main.gd's existing finance desk and paperwork. Odds come from the car's TRUE
## condition (repair quality and hidden faults) and the buyer type; staff can still take over mid-pitch.
## Card rules are static so the smoke test can check them without a scene.

const TURNS := 3
const HAND := 3
const SWINGS := 3

## id: [title, short desc, icon]
const CARDS := {
	"features": ["Talk up features", "Sells on the car itself. Better repairs, bigger lift.", "seat"],
	"test_drive": ["Test drive", "Big lift on a solid car. Hidden faults show up.", "car_side"],
	"history": ["History report", "Honesty. Bad history costs interest.", "info"],
	"financing": ["Monthly payment", "Talk payments, not price. Calms them.", "bank"],
	"trade": ["Take their trade", "Generous trade-in. Costs you $400.", "conversion"],
	"urgency": ["Another buyer's coming", "Pressure. Some love it, some hate it.", "phone"],
	"discount": ["Knock off 3%", "Costs margin. Bargain types melt.", "tag"],
	"extras": ["Throw in extras", "Mats and oil changes. Costs $300.", "upgrades"],
	"espresso": ["Lounge espresso", "Restores patience and mood.", "smile"],
	"maruchan": ["Maruchan says hi", "VIP charm. Patience and mood.", "star"],
}

## How each buyer type reacts to a card (1 = neutral, >1 loves it, <0 backfires).
const REACT := {
	"bargain": {"discount": 1.7, "trade": 1.3, "urgency": -1.0, "features": 0.7},
	"local": {"features": 1.5, "urgency": 1.2, "discount": 0.6, "test_drive": 1.2},
	"first": {"history": 1.5, "extras": 1.4, "financing": 1.6, "urgency": -0.6},
	"nerd": {"test_drive": 1.7, "features": 1.2, "urgency": -1.0, "extras": 0.6},
	"parent": {"history": 1.6, "test_drive": 1.3, "urgency": -1.0, "financing": 1.2},
	"influencer": {"features": 1.6, "extras": 1.4, "urgency": 1.3, "history": 0.6},
	"lowballer": {"discount": 1.8, "urgency": -1.2, "features": 0.5, "trade": 1.2},
	"whale": {"features": 1.4, "test_drive": 1.5, "urgency": 1.4, "discount": 0.2},
}

## One-line hint about what each type responds to (the "read").
const TELLS := {
	"bargain": "Keeps checking prices on their phone.",
	"local": "Wants to know how it looks parked at the yacht club.",
	"first": "Nervous. Asked twice about monthly costs.",
	"nerd": "Already crouched by the wheel, looking at the brakes.",
	"parent": "Opened the back door to check the car seat anchors.",
	"influencer": "Filming the interior lights. Loves a story.",
	"lowballer": "Arms crossed. Hasn't said a number yet.",
	"whale": "Glanced at the speedometer, not the sticker.",
}

var m: Node            # main.gd
var c: Dictionary      # the customer (main.customer)
var car: Dictionary
var phase := "pitch"   # pitch, haggle
var turn := 1
var hand: Array = []
var last_line := ""
var last_fx := ""
var swings := 0
var needle := 0.0      # 0..1 along the haggle bar
var needle_dir := 1.0
var running := false
var locked_msg := ""
var bar: HaggleBar
var price_lab: Label
var center: VBoxContainer


# ---------------- rules (static) ----------------

static func react(type: String, id: String) -> float:
	var r: float = REACT.get(type, {}).get(id, 1.0)
	if r > 0.0 and id in Game.BUYER_TYPES.get(type, {}).get("likes", []):
		r = max(r, 1.5)
	return r


static func available(cust: Dictionary, has_maruchan: bool, has_coffee: bool) -> Array:
	var out: Array = []
	for id in CARDS:
		if id in cust.get("used", []):
			continue
		if id == "financing" and not cust.get("finance", false):
			continue
		if id == "maruchan" and not has_maruchan:
			continue
		if id == "espresso" and not has_coffee:
			continue
		out.append(id)
	return out


## Plays one card. Mutates the customer and returns {line, fx, liked}.
static func play(id: String, cust: Dictionary, the_car: Dictionary) -> Dictionary:
	var r := react(cust.type, id)
	var q: float = Game.condition(the_car, true)          # repair quality, hidden faults included
	var di := 0.0
	var dp := -0.06
	var dh := 0.0
	var line := ""
	cust.used = cust.get("used", []) + [id]
	match id:
		"features":
			di = clamp((q - 40.0) / 4.5, 1.0, 14.0) * r
			line = "\"Heated seats, great sound, and it turns heads on Coast Highway.\""
		"test_drive":
			dp = -0.1
			cust.test_drive_until = Game.clock + 25.0
			var finds: bool = cust.type == "nerd" or randf() < 0.6
			if Game.hidden_total(the_car) > 0 and finds:
				var found: Array = Game.reveal_faults(the_car)
				di = -20.0
				dh = -0.1
				line = "\"Why is the %s doing THAT?\" The drive exposed a fault." % str(found[0]).to_lower()
			else:
				di = q / 6.5 * r
				dh = 0.12
				line = "\"Oh, this drives nice.\""
		"history":
			the_car.history_known = true
			if the_car.history == "Clean":
				di = 10.0 * r
				line = "\"Clean history. I like that.\""
			else:
				di = -12.0
				dh = 0.05
				line = "\"%s? Hmm. Thanks for being upfront.\"" % the_car.history
		"financing":
			di = 8.0 * r
			dp = 0.06
			line = "\"Oh, it's only that much a month? Okay...\""
		"trade":
			cust.extras = int(cust.get("extras", 0)) + 400
			di = 10.0 * r
			dh = 0.05
			line = "\"You'll take my old Civic? For that? Nice.\""
		"urgency":
			if r > 0:
				di = 12.0 * r
				dp = -0.12
				line = "\"Wait, someone else wants it? Let's not waste time.\""
			else:
				di = -6.0
				dh = -0.15 * -r
				dp = -0.2
				line = "\"Don't pull that on me. I've heard it before.\""
		"discount":
			cust.extras = int(cust.get("extras", 0)) + int(round(the_car.get("sticker", Game.sale_value(the_car)) * 0.03 / 50.0)) * 50
			di = 14.0 * r
			dh = 0.05
			line = "\"Now we're talking.\"" if r >= 1.0 else "\"I don't need a discount. I need a reason.\""
		"extras":
			cust.extras = int(cust.get("extras", 0)) + 300
			di = 6.0 * r
			dh = 0.08
			line = "\"Floor mats and oil changes? Sure, I'll take it.\""
		"espresso":
			dh = 0.15
			dp = 0.15
			line = "\"Oh, that's actually good espresso.\""
		"maruchan":
			dh = 0.15
			dp = 0.12
			line = "Maruchan: \"Welcome, my friend. You look like a Porsha guy.\""
	cust.interest = clamp(float(cust.get("interest", 40.0)) + di, 0.0, 100.0)
	cust.patience = clamp(float(cust.get("patience", 1.0)) + dp, 0.0, 1.0)
	cust.happiness = clamp(float(cust.get("happiness", 0.5)) + dh, 0.0, 1.0)
	var bits: Array = []
	if abs(di) >= 0.5: bits.append("%+d interest" % int(round(di)))
	if abs(dh) >= 0.01: bits.append("%+d%% mood" % int(round(dh * 100)))
	if abs(dp) >= 0.01: bits.append("%+d%% patience" % int(round(dp * 100)))
	var liked := r >= 1.3
	if liked:
		cust.liked = cust.get("liked", []) + [id]
	return {"line": line, "fx": ", ".join(bits), "liked": liked, "backfire": r < 0}


## Result of locking the needle at price p: "deal", "counter" or "storm".
static func lock(cust: Dictionary, p: int, swing: int) -> String:
	if p > int(cust.threshold):
		return "storm"
	if p <= int(cust.max_price):
		var room: float = max(100.0, float(cust.max_price - cust.offer))
		var squeeze: float = clamp((p - cust.offer) / room, 0.0, 1.0)
		if swing >= SWINGS or randf() < 0.55 + (1.0 - squeeze) * 0.45:
			return "deal"
	return "counter"


# ---------------- scene ----------------

func setup(main: Node, cust: Dictionary, the_car: Dictionary, start_phase := "pitch") -> void:
	m = main
	c = cust
	car = the_car
	if not c.has("used"):
		c.used = []
	if not c.has("interest"):
		c.interest = 40.0
	c.sale_game = true
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	last_line = c.log[-1] if not c.get("log", []).is_empty() else ""
	if start_phase == "haggle":
		_start_haggle()
	else:
		_deal()
	_build()


func _deal() -> void:
	var pool := available(c, Game.has_staff("Maruchan"), Game.has_upgrade("coffee"))
	pool.shuffle()
	hand = pool.slice(0, HAND)


func _start_haggle() -> void:
	phase = "haggle"
	c.stage = "negotiate"
	c.max_price = m._max_price(c, car, c.interest)
	var tol: float = m._tol()
	c.threshold = int(round(c.max_price * (1.06 + 0.06 * tol) / 100.0)) * 100
	var sticker: int = car.get("sticker", Game.sale_value(car))
	if not c.has("offer") or int(c.get("rounds", 0)) == 0:
		c.offer = int(round(min(sticker, c.max_price) * randf_range(0.8, 0.9) / 100.0)) * 100
	c.rounds = 0
	swings = 0
	running = true
	needle = 0.0
	last_line = "%s: \"I'll be honest. I can do %s.\"" % [c.name, Game.money_str(c.offer)]
	last_fx = "Stop the needle as high as you dare. Green they take, amber they counter, red they storm out."
	c.log.append(last_line)


func _process(delta: float) -> void:
	if phase != "haggle" or not running or bar == null:
		return
	# lower patience, faster needle
	var speed: float = 0.45 + (1.0 - float(c.patience)) * 0.55 + swings * 0.12
	needle += needle_dir * speed * delta
	if needle >= 1.0:
		needle = 1.0
		needle_dir = -1.0
	elif needle <= 0.0:
		needle = 0.0
		needle_dir = 1.0
	bar.needle = needle
	bar.queue_redraw()
	if price_lab:
		var p := _needle_price()
		price_lab.text = "%s   ·   margin %s" % [Game.money_str(p), Game.money_str(p - _cost())]


func _unhandled_input(e: InputEvent) -> void:
	if phase == "haggle" and running and e is InputEventKey and e.pressed and not e.echo and e.keycode == KEY_SPACE:
		get_viewport().set_input_as_handled()
		_lock()


func _cost() -> int:
	return int(car.paid) + int(car.spent) + int(c.get("extras", 0))


func _needle_price() -> int:
	return int(round(lerp(float(bar.lo), float(bar.hi), needle) / 100.0)) * 100


func _build() -> void:
	UI.clear(self)
	bar = null
	price_lab = null
	var W: float = m.size.x
	var H: float = m.size.y
	var back := TextureRect.new()
	back.texture = m.world_tex("dealdesk")
	back.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	back.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	back.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	# Faisal's pick D (painted illustration): the sales floor stays visible and sunlit behind the panels,
	# painted by the shared world shader, instead of a near-black wash.
	back.material = WorldLook.new_material()
	WorldLook.update(back.material, back.texture, "dealdesk" + Game.world_suffix())
	add_child(back)
	var shade := TextureRect.new()
	var grad := Gradient.new()
	grad.set_color(0, Color(0.015, 0.025, 0.05, 0.12))
	grad.set_color(1, Color(0.015, 0.025, 0.05, 0.5))
	var gt := GradientTexture2D.new()
	gt.gradient = grad
	gt.fill_from = Vector2(0, 0)
	gt.fill_to = Vector2(0, 1)
	shade.texture = gt
	shade.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	shade.stretch_mode = TextureRect.STRETCH_SCALE
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(shade)
	# ----- left: the customer, read -----
	var left := _panel(14)
	add_child(left)
	m._place(left, 18, 18, 300, H - 36)
	var lv := UI.vbox(6)
	left.add_child(lv)
	var face: Control = m._portrait_frame(Game.customer_pid(c), c.happiness * 2.0 - 1.0, m.CARD_CYAN, 210)
	lv.add_child(face)
	lv.add_child(UI.label(c.name.to_upper(), 22, UI.GOLD, true))
	lv.add_child(UI.label(Game.BUYER_TYPES[c.type].title + (" · financing" if c.finance else " · cash"), 14, UI.MUTED))
	var tell := UI.label("“%s”" % TELLS.get(c.type, "Hard to read."), 13, UI.CYAN, false, true)
	lv.add_child(tell)
	lv.add_child(UI.rule(UI.GOLD_DIM))
	_meter_row(lv, "MOOD", c.happiness)
	_meter_row(lv, "PATIENCE", c.patience)
	_meter_row(lv, "INTEREST", c.interest / 100.0)
	lv.add_child(UI.rule(UI.GOLD_DIM))
	lv.add_child(UI.label("BUDGET READ", 12, UI.MUTED, true))
	var est: int = m._max_price(c, car, c.interest)
	var spread: float = 0.0 if Game.has_perk("insights") else [0.22, 0.14, 0.08, 0.05][clamp(turn - 1, 0, 3)]
	if phase == "haggle":
		spread = max(0.0, spread - 0.03)
	var lo := int(round(est * (1.0 - spread) / 500.0)) * 500
	var hi := int(round(est * (1.0 + spread) / 500.0)) * 500
	lv.add_child(UI.label(Game.money_str(est) if spread == 0.0 else "%s – %s" % [Game.money_str(lo), Game.money_str(hi)], 18, UI.TEXT, true))
	lv.add_child(UI.label("Narrows as you talk." if spread > 0.0 else "Market Insights: exact.", 12, UI.MUTED))
	var liked: Array = c.get("liked", [])
	if not liked.is_empty():
		lv.add_child(UI.label("RESPONDS TO: " + ", ".join(liked.map(func(x): return CARDS[x][0].to_lower())), 12, UI.GOOD, false, true))
	# ----- right: the car -----
	var right := _panel(14)
	add_child(right)
	m._place(right, W - 318, 18, 300)
	var rv := UI.vbox(4)
	right.add_child(rv)
	rv.add_child(UI.label(("%d %s" % [car.year, car.model]).to_upper(), 22, UI.TEXT, true))
	rv.add_child(UI.rule(UI.GOLD))
	rv.add_child(m._car_art(car, Vector2(0, 140)))
	for row in [["Sticker", Game.money_str(car.get("sticker", 0))], ["You're in for", Game.money_str(_cost())],
			["Condition", "%d / 100" % Game.condition(car)], ["History", car.history if car.history_known else "Not checked"]]:
		var hr := UI.hbox()
		hr.add_child(UI.label(row[0].to_upper(), 12, UI.MUTED))
		hr.add_child(UI.spacer())
		hr.add_child(UI.label(row[1], 14))
		rv.add_child(hr)
	# staff hand-off, with the warm-up you've done counting toward their odds
	if phase == "pitch" and not Game.staff.is_empty():
		rv.add_child(UI.rule(UI.GOLD_DIM))
		rv.add_child(UI.label("HAND OFF", 12, UI.MUTED, true))
		for s in Game.staff:
			var free: bool = s.get("busy_until", 0.0) <= Game.clock or s.get("busy_day", 0) != Game.day
			var b := UI.button("%s · %d%% close" % [s.name, int(m._handoff_chance(c, s) * 100)], _handoff.bind(s), 0, 34)
			b.add_theme_font_size_override("font_size", 13)
			b.disabled = not free
			rv.add_child(b)
	# ----- centre -----
	var mid := _panel(16)
	add_child(mid)
	var cw: float = W - 300 - 300 - 18 * 4
	m._place(mid, 18 + 300 + 18, 0, cw)
	center = UI.vbox(10)
	mid.add_child(center)
	var head := UI.hbox(8)
	head.add_child(UI.label("THE SALE" if phase == "pitch" else "THE NUMBERS", 30, UI.GOLD, true))
	head.add_child(UI.spacer())
	head.add_child(UI.label(("PITCH %d / %d" % [turn, TURNS]) if phase == "pitch" else ("SWING %d / %d" % [swings + 1, SWINGS]), 14, UI.MUTED, true))
	var x := UI.button("✕", _step_away, 34, 30)
	x.tooltip_text = "Step away (they keep waiting)"
	head.add_child(x)
	center.add_child(head)
	center.add_child(UI.rule(UI.GOLD))
	var bubble := UI.panel(UI.DIALOG_NAVY, UI.DIALOG_RIM, 12)
	var bv := UI.vbox(2)
	bubble.add_child(bv)
	bv.add_child(UI.label(last_line, 16, UI.TEXT, false, true))
	if last_fx != "":
		bv.add_child(UI.label(last_fx, 13, UI.GOLD, false, true))
	center.add_child(bubble)
	if phase == "pitch":
		_build_pitch()
	else:
		_build_haggle()
	var dock := func():
		mid.size.y = 0
		mid.position.y = H - 18 - mid.get_combined_minimum_size().y
	dock.call_deferred()


## Pick D panels: deep navy with a warm gold rim, solid enough to read over the sunlit painted backdrop.
func _panel(pad: int) -> PanelContainer:
	var p := PanelContainer.new()
	var sb := UI.box(Color(0.03, 0.055, 0.1, 0.93), Color(0.91, 0.71, 0.3, 0.75), 12, 2, pad)
	sb.shadow_color = Color(0, 0, 0, 0.5)
	sb.shadow_size = 14
	p.add_theme_stylebox_override("panel", sb)
	return p


func _meter_row(parent: Control, name: String, v: float) -> void:
	var row := UI.hbox(6)
	var l := UI.label(name, 12, UI.MUTED)
	l.custom_minimum_size.x = 70
	row.add_child(l)
	var b := UI.bar(v * 100.0, 100.0, UI.GOOD if v >= 0.6 else (UI.GOLD if v >= 0.3 else UI.BAD), 10)
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(b)
	parent.add_child(row)


func _build_pitch() -> void:
	center.add_child(UI.label("Play a card. Watch the tell: each buyer type loves some pitches and hates others.", 13, UI.MUTED, false, true))
	var row := UI.hbox(10)
	center.add_child(row)
	for id in hand:
		var info: Array = CARDS[id]
		var card := Button.new()
		card.custom_minimum_size = Vector2(0, 168)
		card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		card.add_theme_stylebox_override("normal", UI.box(Color(0.06, 0.08, 0.13, 0.92), UI.GOLD_DIM, 10, 2, 10))
		card.add_theme_stylebox_override("hover", UI.box(Color(0.12, 0.13, 0.18, 0.95), UI.GOLD, 10, 2, 10))
		card.add_theme_stylebox_override("pressed", UI.box(Color(0.25, 0.2, 0.08, 0.95), UI.GOLD, 10, 2, 10))
		card.pressed.connect(_play.bind(id))
		var cv := UI.vbox(4)
		cv.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		cv.offset_left = 10
		cv.offset_right = -10
		cv.offset_top = 10
		cv.offset_bottom = -10
		cv.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var ic := TextureRect.new()
		ic.texture = m.icon_tex(info[2])
		ic.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		ic.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		ic.custom_minimum_size = Vector2(0, 58)
		ic.modulate = UI.GOLD.lightened(0.1)
		ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
		cv.add_child(ic)
		var t := UI.label(info[0].to_upper(), 16, UI.TEXT, true, true)
		t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		t.mouse_filter = Control.MOUSE_FILTER_IGNORE
		cv.add_child(t)
		var d := UI.label(info[1], 12, UI.MUTED, false, true)
		d.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		d.mouse_filter = Control.MOUSE_FILTER_IGNORE
		cv.add_child(d)
		card.add_child(cv)
		row.add_child(card)
	var btns := UI.hbox(8)
	var go := UI.gold_button("Talk numbers  →", func():
		_start_haggle()
		_build(), 0, 52)
	go.add_theme_font_size_override("font_size", 24)
	go.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	btns.add_child(go)
	center.add_child(btns)


func _play(id: String) -> void:
	var r := play(id, c, car)
	last_line = ("" if id == "maruchan" else c.name + ": ") + r.line
	last_fx = ("★ They loved that.  " if r.liked else ("✕ That backfired.  " if r.backfire else "")) + r.fx
	c.log.append(last_line)
	if m._check_walkout():
		return
	turn += 1
	if turn > TURNS or available(c, Game.has_staff("Maruchan"), Game.has_upgrade("coffee")).is_empty():
		_start_haggle()
	else:
		_deal()
	_build()


func _build_haggle() -> void:
	bar = HaggleBar.new()
	bar.custom_minimum_size = Vector2(0, 104)
	bar.lo = c.offer
	bar.hi = int(c.threshold * 1.08 / 100.0) * 100
	bar.offer = c.offer
	bar.max_price = c.max_price
	bar.threshold = c.threshold
	bar.cost = _cost()
	bar.needle = needle
	center.add_child(bar)
	price_lab = UI.label("", 20, UI.TEXT, true)
	price_lab.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	center.add_child(price_lab)
	var btns := UI.hbox(8)
	var lk := UI.gold_button("LOCK IT IN  (space)", _lock, 0, 48)
	lk.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	btns.add_child(lk)
	var take := UI.button("TAKE %s" % Game.money_str(c.offer), func(): _deal_at(int(c.offer)), 0, 48)
	take.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	btns.add_child(take)
	var walk := UI.button("WALK AWAY", func(): m._customer_leaves("%s: \"Fine, I'll take my business elsewhere.\"" % c.name), 0, 48)
	btns.add_child(walk)
	center.add_child(btns)


func _lock() -> void:
	if not running or bar == null:
		return
	var p := _needle_price()
	swings += 1
	c.rounds = swings
	c.log.append("You: \"I can do %s.\"" % Game.money_str(p))
	if p <= int(c.offer):
		_deal_at(int(c.offer))
		return
	match lock(c, p, swings):
		"storm":
			running = false
			m._storm_out("%s slams the desk. \"%s?! That's a rip-off. Enjoy your one-star review.\"" % [c.name, Game.money_str(p)])
		"deal":
			_deal_at(p)
		_:
			var tol: float = m._tol()
			c.patience = clamp(c.patience - 0.14 / tol, 0.0, 1.0)
			if p > int(c.max_price):
				c.happiness = clamp(c.happiness - (0.08 + float(p - c.max_price) / c.max_price * 1.2) / tol, 0.0, 1.0)
				c.offer = int(round((c.offer + (c.max_price - c.offer) * 0.6) / 100.0)) * 100
				last_line = "%s: \"Too rich for me. %s.\"" % [c.name, Game.money_str(c.offer)]
			else:
				c.happiness = clamp(c.happiness - 0.05 / tol, 0.0, 1.0)
				c.offer = int(round((c.offer + (p - c.offer) * 0.5) / 100.0)) * 100
				last_line = "%s: \"Meet me in the middle? %s.\"" % [c.name, Game.money_str(c.offer)]
			c.log.append(last_line)
			if swings >= SWINGS:
				last_line += "  Final offer."
				running = false
			last_fx = "-%d%% patience. The needle speeds up." % int(round(14 / tol))
			if m._check_walkout():
				return
			if swings >= SWINGS:
				_deal_at(int(c.offer))
				return
			needle = 0.0
			needle_dir = 1.0
			_build()


func _deal_at(p: int) -> void:
	running = false
	var room: float = max(100.0, float(c.max_price - c.offer))
	var squeeze: float = clamp((p - float(c.offer)) / room, 0.0, 1.0) if p > int(c.offer) else 0.0
	c.erase("sale_game")
	m._price_agreed(p, squeeze)


func _handoff(s: Dictionary) -> void:
	var cust := c
	c.erase("sale_game")
	m._close_overlay()
	m.customer = {}
	m._staff_handles(cust, s)


func _step_away() -> void:
	c.erase("sale_game")
	m._step_away()


## The haggle track: their offer (blue), the green zone they accept, amber they counter, red line they storm out.
class HaggleBar extends Control:
	var lo := 0.0
	var hi := 1.0
	var offer := 0.0
	var max_price := 0.0
	var threshold := 0.0
	var cost := 0.0
	var needle := 0.0

	func _x(v: float) -> float:
		return 10.0 + clamp((v - lo) / max(1.0, hi - lo), 0.0, 1.0) * (size.x - 20.0)

	func _draw() -> void:
		var font := get_theme_default_font()
		var y := 40.0
		var h := 20.0
		var x0 := _x(offer)
		var xm := _x(max_price)
		var xt := _x(threshold)
		var xe := size.x - 10.0
		draw_rect(Rect2(x0, y - h / 2, xm - x0, h), Color("3fa34d"))
		draw_rect(Rect2(xm, y - h / 2, xt - xm, h), Color("d9a72c"))
		draw_rect(Rect2(xt, y - h / 2, xe - xt, h), Color("a3281e"))
		# the green edge is soft: you only know their budget roughly
		for i in 6:
			draw_rect(Rect2(xm - 18 + i * 6, y - h / 2, 6, h), Color(Color("3fa34d").lerp(Color("d9a72c"), i / 5.0), 0.85))
		draw_rect(Rect2(x0, y - h / 2, xe - x0, h), Color(1, 1, 1, 0.35), false, 1.0)
		if cost > lo and cost < hi:
			var xc := _x(cost)
			draw_line(Vector2(xc, y - h), Vector2(xc, y + h), Color(1, 1, 1, 0.8), 2.0)
			draw_string(font, Vector2(xc - 40, y + h + 14), "BREAK-EVEN", HORIZONTAL_ALIGNMENT_CENTER, 80, 11, Color(1, 1, 1, 0.8))
		var xn: float = 10.0 + needle * (size.x - 20.0)
		draw_rect(Rect2(xn - 2, y - h, 4, h * 2), Color.WHITE)
		draw_colored_polygon(PackedVector2Array([Vector2(xn - 8, y - h - 10), Vector2(xn + 8, y - h - 10), Vector2(xn, y - h)]), Color("e8b64c"))
		draw_string(font, Vector2(10, 12), "THEIR OFFER " + Game.money_str(offer), HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color("8fd0ff"))
		draw_string(font, Vector2(0, 12), "WALKOUT LINE " + Game.money_str(threshold), HORIZONTAL_ALIGNMENT_RIGHT, size.x - 10, 12, Color("ff6b5b"))
		draw_string(font, Vector2(0, size.y - 2), "GREEN they take it  ·  AMBER they counter  ·  RED they storm out", HORIZONTAL_ALIGNMENT_CENTER, size.x, 12, Color(1, 1, 1, 0.7))
