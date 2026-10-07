extends Node
## Global game state for Chief Auto: money, progression, cars, data tables, save/load.

signal changed

const SAVE_PATH := "user://chief_auto_save.json"
const CURRENT_YEAR := 2026
const PARTS := ["engine", "transmission", "body", "interior", "tires"]
const PART_NAMES := {
	"engine": "Engine", "transmission": "Transmission", "body": "Body & Paint",
	"interior": "Interior", "tires": "Tires & Brakes",
}

# Parody models: [name, class, base price new]
const MODELS := [
	["Hondo Civix", "economy", 24000],
	["Toyoda Camri", "economy", 28000],
	["Teslo Model 3", "economy", 42000],
	["Mazdo Miota", "sport", 32000],
	["Subaro Outbuck", "suv", 34000],
	["Forde Rangler", "truck", 36000],
	["Jeap Wrangle", "suv", 42000],
	["Dodgy Charjer", "sport", 45000],
	["Forde Mustank", "sport", 48000],
	["Chevro Tahoma", "suv", 52000],
	["Ramm 1500", "truck", 55000],
	["BMV M4", "sport", 78000],
	["Rang Rovah", "suv", 98000],
	["Porsha 911", "sport", 115000],
	["Mercedez G-Wagon", "suv", 150000],
	["Ferrano 488", "exotic", 250000],
	["Lamborgo Aventa", "exotic", 380000],
]

const MECHANICS := [
	{"name": "Cousin Ray", "where": "backyard garage", "level": 1, "cost": 0.006, "min": 10, "max": 20, "botch": 0.25, "find": 0.2},
	{"name": "Strip-Mall Auto", "where": "strip-mall shop", "level": 3, "cost": 0.012, "min": 20, "max": 30, "botch": 0.10, "find": 0.5},
	{"name": "Harbor Certified", "where": "certified shop", "level": 6, "cost": 0.02, "min": 30, "max": 40, "botch": 0.04, "find": 0.8},
	{"name": "Euro Specialist", "where": "luxury specialist", "level": 10, "cost": 0.03, "min": 40, "max": 50, "botch": 0.01, "find": 1.0},
]

const BUYER_TYPES := {
	"bargain": {"title": "Bargain Hunter", "patience": 5, "budget": 0.97, "likes": ["discount"],
		"intro": "I saw a cheaper one in Costa Mesa. Convince me."},
	"local": {"title": "Tewport Local", "patience": 4, "budget": 1.2, "likes": ["features"],
		"intro": "Does it look good at the yacht club? That's all I need to know."},
	"first": {"title": "First-Time Buyer", "patience": 6, "budget": 1.0, "likes": ["history", "extras"],
		"intro": "Um, hi. My dad said not to get ripped off."},
	"nerd": {"title": "Car Nerd", "patience": 5, "budget": 1.05, "likes": ["test_drive"],
		"intro": "I'll need to hear the cold start. And I brought a code reader."},
	"parent": {"title": "Safety Parent", "patience": 5, "budget": 1.0, "likes": ["history", "test_drive"],
		"intro": "Three kids, one dog. Is it safe?"},
}
const BUYER_NAMES := ["Brad", "Kayla", "Devon", "Priya", "Chad", "Monica", "Luis", "Tiffany", "Grant", "Mei"]

const RIVALS := ["Tustin Tony", "Irvine Imports", "Costa Mesa Motors", "Huntington Hank"]

const PERKS := [
	{"id": "sourcing", "name": "Global Sourcing Boost", "level": 3, "desc": "More sport and exotic cars show up at auction."},
	{"id": "vip", "name": "VIP Negotiator", "level": 5, "desc": "+10% sale price on sport and exotic cars."},
	{"id": "insights", "name": "Market Insights", "level": 8, "desc": "See the price range buyers will accept."},
]

const DAILY_RENT := 400
const LOT_CAPACITY := 4
const HISTORY_REPORT_COST := 150

var money: int = 40000
var xp: int = 0
var level: int = 1
var reputation: float = 3.0
var day: int = 1
var cars: Array = []          # owned cars
var listings: Array = []      # today's auction listings
var hot_class: String = "suv"
var next_id: int = 1
var stats := {"sold": 0, "buyers": 0, "profit": 0, "days_held": 0, "goal_sold_today": 0}
var seen_intro := false
var log_lines: Array = []


func _ready() -> void:
	randomize()
	# Testing hook: ?seed=N in the web build makes runs repeatable.
	if OS.has_feature("web"):
		var loc = JavaScriptBridge.get_interface("location")
		var query: String = str(loc.search) if loc else ""
		var at := query.find("seed=")
		if at >= 0:
			seed(int(query.substr(at + 5)))
	if not load_game():
		new_game()


func new_game() -> void:
	money = 40000
	xp = 0
	level = 1
	reputation = 3.0
	day = 1
	cars = []
	next_id = 1
	stats = {"sold": 0, "buyers": 0, "profit": 0, "days_held": 0, "goal_sold_today": 0}
	seen_intro = false
	hot_class = ["economy", "truck", "suv"].pick_random()
	generate_listings()
	emit_signal("changed")


# ---------- helpers ----------

static func money_str(n: float) -> String:
	var neg := n < 0
	var s := str(int(abs(round(n))))
	var out := ""
	while s.length() > 3:
		out = "," + s.substr(s.length() - 3) + out
		s = s.substr(0, s.length() - 3)
	return ("-$" if neg else "$") + s + out


func has_perk(id: String) -> bool:
	for p in PERKS:
		if p.id == id:
			return level >= p.level
	return false


func unlocked_mechanics() -> Array:
	return MECHANICS.filter(func(m): return level >= m.level)


func xp_to_next() -> int:
	return 150 * level


func add_xp(amount: int) -> bool:
	xp += amount
	var leveled := false
	while xp >= xp_to_next():
		xp -= xp_to_next()
		level += 1
		leveled = true
	emit_signal("changed")
	return leveled


func spend(amount: int) -> bool:
	if amount > money:
		return false
	money -= amount
	emit_signal("changed")
	return true


func earn(amount: int) -> void:
	money += amount
	emit_signal("changed")


func change_rep(delta: float) -> void:
	reputation = clamp(reputation + delta, 0.0, 5.0)
	emit_signal("changed")


# ---------- cars ----------

func make_car(max_base: int) -> Dictionary:
	var pool := MODELS.filter(func(m): return m[2] <= max_base)
	if has_perk("sourcing"):
		pool += MODELS.filter(func(m): return m[1] in ["sport", "exotic"] and m[2] <= max_base * 2)
	var m: Array = pool.pick_random()
	var age := randi_range(2, 14)
	var car := {
		"id": next_id, "model": m[0], "cls": m[1], "base": m[2],
		"year": CURRENT_YEAR - age,
		"miles": int(age * randi_range(7000, 15000) / 100) * 100,
		"parts": {}, "hidden": {}, "detailed": false,
		"history": ["Clean", "Clean", "Clean", "Minor accident", "Major accident", "Flood"].pick_random(),
		"history_known": false, "paid": 0, "spent": 0, "day_bought": 0,
	}
	next_id += 1
	for p in PARTS:
		car.parts[p] = randi_range(25, 90)
	# hidden faults the seller didn't mention
	var faults := randi_range(0, 2)
	if car.history == "Flood":
		faults += 1
	for i in faults:
		var p: String = PARTS.pick_random()
		car.hidden[p] = car.hidden.get(p, 0) + randi_range(15, 35)
	return car


func condition(car: Dictionary, true_value := false) -> int:
	var total := 0.0
	for p in PARTS:
		var v: float = car.parts[p]
		if true_value:
			v = max(0, v - car.hidden.get(p, 0))
		total += v
	return int(round(total / PARTS.size()))


func value(car: Dictionary, true_value := false) -> int:
	var age_factor: float = max(0.35, 1.0 - (CURRENT_YEAR - car.year) * 0.045)
	var miles_factor: float = clamp(1.0 - car.miles / 300000.0, 0.5, 1.0)
	var hist := 1.0
	if car.history_known or true_value:
		hist = {"Clean": 1.0, "Minor accident": 0.92, "Major accident": 0.8, "Flood": 0.65}[car.history]
	var cond := condition(car, true_value)
	var v: float = car.base * age_factor * miles_factor * hist * (0.35 + 0.65 * cond / 100.0)
	return int(round(v / 50.0) * 50)


func hidden_total(car: Dictionary) -> int:
	var t := 0
	for p in car.hidden:
		t += car.hidden[p]
	return t


func reveal_faults(car: Dictionary) -> Array:
	var found := []
	for p in car.hidden.keys():
		car.parts[p] = max(0, car.parts[p] - car.hidden[p])
		found.append(PART_NAMES[p])
	car.hidden = {}
	return found


func max_auction_base() -> int:
	return 60000 + level * 20000


func generate_listings() -> void:
	listings = []
	var used := []
	for i in 6:
		var car := make_car(max_auction_base())
		for attempt in 4:
			if not used.has(car.model):
				break
			car = make_car(max_auction_base())
		used.append(car.model)
		var v := value(car)
		var start: int = int(round(v * randf_range(0.25, 0.4) / 100.0) * 100)
		var listing := {
			"car": car, "current": start, "start": start,
			"leader": "", "rival": RIVALS.pick_random(),
			"rival_max": int(v * randf_range(0.55, 0.85)),
			"buy_now": int(round(v * randf_range(0.85, 0.95) / 100.0) * 100) if randf() < 0.35 else 0,
			"haggled": false, "sold": false, "winner": "",
		}
		listings.append(listing)


func add_car(car: Dictionary, price: int) -> void:
	car.paid = price
	car.day_bought = day
	cars.append(car)
	emit_signal("changed")


func remove_car(car: Dictionary) -> void:
	cars.erase(car)
	emit_signal("changed")


# ---------- day cycle ----------

func end_day() -> Array:
	var notes := []
	money -= DAILY_RENT
	notes.append("Paid %s rent for the lot." % money_str(DAILY_RENT))
	if stats.goal_sold_today >= 1:
		var bonus := 500
		money += bonus
		notes.append("Marco's daily goal met: %s bonus." % money_str(bonus))
		add_xp(25)
	day += 1
	stats.goal_sold_today = 0
	hot_class = ["economy", "truck", "suv", "sport", "exotic"].pick_random()
	generate_listings()
	save_game()
	emit_signal("changed")
	return notes


# ---------- save / load ----------

func save_game() -> void:
	var data := {
		"money": money, "xp": xp, "level": level, "reputation": reputation, "day": day,
		"cars": cars, "listings": listings, "hot_class": hot_class, "next_id": next_id,
		"stats": stats, "seen_intro": seen_intro,
	}
	var f := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(data))


func load_game() -> bool:
	if not FileAccess.file_exists(SAVE_PATH):
		return false
	var f := FileAccess.open(SAVE_PATH, FileAccess.READ)
	if f == null:
		return false
	var data = JSON.parse_string(f.get_as_text())
	if typeof(data) != TYPE_DICTIONARY:
		return false
	money = int(data.money)
	xp = int(data.xp)
	level = int(data.level)
	reputation = float(data.reputation)
	day = int(data.day)
	cars = _fix_ints(data.cars)
	listings = _fix_ints(data.listings)
	hot_class = data.hot_class
	next_id = int(data.next_id)
	stats = _fix_ints(data.stats)
	seen_intro = data.seen_intro
	return true


func reset_save() -> void:
	if FileAccess.file_exists(SAVE_PATH):
		DirAccess.remove_absolute(SAVE_PATH)
	new_game()


# JSON turns every number into a float; turn whole numbers back into ints.
func _fix_ints(v):
	match typeof(v):
		TYPE_FLOAT:
			return int(v) if v == floor(v) else v
		TYPE_ARRAY:
			return v.map(func(x): return _fix_ints(x))
		TYPE_DICTIONARY:
			var out := {}
			for k in v:
				out[k] = _fix_ints(v[k])
			return out
	return v
