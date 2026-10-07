extends Node
## Global game state for Chief Auto: money, calendar and clock, progression, cars, staff, shops, save/load.

signal changed

const SAVE_PATH := "user://chief_auto_save.json"
const CURRENT_YEAR := 2026
const START_UNIX := 1790812800  # Oct 1, 2026 (UTC)
const OPEN_MIN := 8 * 60        # dealership opens 8:00
const CLOSE_MIN := 21 * 60      # closes 21:00
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
	"bargain": {"title": "Bargain Hunter", "budget": 0.95, "likes": ["discount"], "tolerance": 0.7,
		"intro": "I saw a cheaper one in Costa Mesa. Convince me."},
	"local": {"title": "Tewport Local", "budget": 1.2, "likes": ["features"], "tolerance": 1.3,
		"intro": "Does it look good at the yacht club? That's all I need to know."},
	"first": {"title": "First-Time Buyer", "budget": 1.0, "likes": ["history", "extras"], "tolerance": 1.0,
		"intro": "Um, hi. My dad said not to get ripped off."},
	"nerd": {"title": "Car Nerd", "budget": 1.05, "likes": ["test_drive"], "tolerance": 0.9,
		"intro": "I'll need to hear the cold start. And I brought a code reader."},
	"parent": {"title": "Safety Parent", "budget": 1.0, "likes": ["history", "test_drive"], "tolerance": 1.0,
		"intro": "Three kids, one dog. Is it safe?"},
	"influencer": {"title": "Influencer", "budget": 1.15, "likes": ["features", "extras"], "tolerance": 0.8,
		"intro": "Is it cool if I film this? I have 80k followers. My review goes out to all of them."},
	"lowballer": {"title": "Lowballer", "budget": 0.85, "likes": ["discount"], "tolerance": 0.55,
		"intro": "I'll give you half. Cash. Today. Final offer. Probably."},
	"whale": {"title": "Cash Whale", "budget": 1.5, "likes": ["features", "test_drive"], "tolerance": 1.5,
		"intro": "I sold my startup last week. Show me something fast."},
}
const REVIEW_NAMES := ["Brad K.", "Kayla M.", "Devon R.", "Priya S.", "Chad W.", "Monica L.", "Luis G.", "Tiffany B.",
	"Grant H.", "Mei C.", "Omar A.", "Jasmine T.", "Tyler P.", "Sofia V.", "Hassan N.", "Brooke D."]
const REVIEW_TEXT := {
	5: ["Bought a {car} and {seller} made it painless. Coffee was great too. 10/10.", "Best dealership in Tewport Beach. Fair price, no games.",
		"{seller} actually listened to me. The {car} is perfect. Telling all my friends.", "Smooth deal, honest numbers, and I drove off smiling."],
	4: ["Good experience overall. Got the {car} for a fair price.", "Friendly staff. Paperwork took a minute but no complaints.",
		"Nice showroom, solid deal on my {car}."],
	3: ["It was fine. The {car} is okay, the negotiating was a lot.", "Decent cars, a little pushy on the numbers.", "Meh. Not bad, not great."],
	2: ["Felt squeezed on price. The {car} better be worth it.", "Waited way too long and the rate they offered was rough.",
		"They tried to upsell me on everything."],
	1: ["Absolute rip-off. Walked out. Avoid.", "The salesman called me 'bro' eleven times. Never again.",
		"Worst negotiation of my life. Went to Costa Mesa instead.", "Do NOT buy here. Check your contract twice."],
}

# Auction houses you can join as the dealership grows.
const AUCTIONS := [
	{"id": "autobidz", "name": "AutoBidz Public", "level": 1, "rep": 0.0, "fee": 0, "color": "c0392b", "url": "autobidz.ca/live",
		"desc": "Open public auction. Anything goes, lots of bidders."},
	{"id": "salvage", "name": "SalvageKing", "level": 2, "rep": 0.0, "fee": 1500, "color": "7f8c8d", "url": "salvageking.ca/yard",
		"desc": "Wrecks, floods and rough cars for pennies. Bring a good mechanic."},
	{"id": "dealer", "name": "Mannheim Dealer Exchange", "level": 4, "rep": 3.2, "fee": 5000, "color": "1f6fb2", "url": "mannheim-dx.ca/lanes",
		"desc": "Dealer-only lanes. Cleaner cars, honest reports, fewer bidders."},
	{"id": "exotic", "name": "Tewport Exotic Collective", "level": 7, "rep": 3.8, "fee": 15000, "color": "b8860b", "url": "tewport-exotics.ca/vault",
		"desc": "Invite-only supercars from Coast Highway collectors."},
]

const SKILLS := ["closing", "rapport", "finance", "upsell"]
const SKILL_NAMES := {"closing": "Closing", "rapport": "Rapport", "finance": "Finance & F&I", "upsell": "Upselling"}
const BUYER_NAMES := ["Brad", "Kayla", "Devon", "Priya", "Chad", "Monica", "Luis", "Tiffany", "Grant", "Mei",
	"Omar", "Jasmine", "Tyler", "Sofia", "Hassan", "Brooke", "Andre", "Leila", "Cody", "Nadia"]

# Credit tiers: [name, bank buy rate %, highest APR they will accept %]
const CREDIT := [
	["Excellent", 4.9, 7.9],
	["Good", 6.9, 10.9],
	["Fair", 9.9, 14.9],
	["Rough", 13.9, 19.9],
]

const RIVALS := ["Tustin Tony", "Irvine Imports", "Costa Mesa Motors", "Huntington Hank"]

const PERKS := [
	{"id": "sourcing", "name": "Global Sourcing Boost", "level": 3, "desc": "More sport and exotic cars show up at auction."},
	{"id": "vip", "name": "VIP Negotiator", "level": 5, "desc": "+10% sale price on sport and exotic cars."},
	{"id": "insights", "name": "Market Insights", "level": 8, "desc": "See the most each customer will pay."},
]

# ---------- shops ----------

const DESK_ITEMS := [
	{"id": "folding", "slot": "desk", "name": "Folding table", "price": 0, "desc": "It came with the lot."},
	{"id": "oak", "slot": "desk", "name": "Oak desk", "price": 1200, "desc": "Solid wood. Smells like money."},
	{"id": "glass", "slot": "desk", "name": "Glass executive desk", "price": 4500, "desc": "Marco has one just like it."},
	{"id": "carbon", "slot": "desk", "name": "Carbon-fiber racing desk", "price": 12000, "desc": "Red racing stripe included."},
	{"id": "plastic", "slot": "chair", "name": "Patio chair", "price": 0, "desc": "Borrowed from the break room."},
	{"id": "office", "slot": "chair", "name": "Mesh office chair", "price": 400, "desc": "Lumbar support. Finally."},
	{"id": "leather", "slot": "chair", "name": "Leather executive chair", "price": 2200, "desc": "Tufted, tall and serious."},
	{"id": "racing", "slot": "chair", "name": "Racing bucket seat", "price": 5000, "desc": "Five-point harness optional."},
	{"id": "crt", "slot": "monitor", "name": "Tewtron CRT", "price": 0, "desc": "Heavy. Warm. Beige."},
	{"id": "lcd", "slot": "monitor", "name": "24-inch LCD", "price": 600, "desc": "+1 auction listing every day."},
	{"id": "dual", "slot": "monitor", "name": "Dual monitors", "price": 1800, "desc": "+2 listings and a watchlist screen."},
	{"id": "ultra", "slot": "monitor", "name": "Curved ultrawide", "price": 4000, "desc": "+3 listings. Very wide. Very cool."},
	{"id": "plant", "slot": "decor", "name": "Potted palm", "price": 150, "desc": "A little Tewport on your desk."},
	{"id": "mug", "slot": "decor", "name": "\"#1 Closer\" mug", "price": 40, "desc": "Gift from yourself."},
	{"id": "modelcar", "slot": "decor", "name": "Model Ferrano", "price": 900, "desc": "1:18 scale. Shelf display."},
	{"id": "trophy", "slot": "decor", "name": "Salesperson of the Year", "price": 2500, "desc": "You bought it. Still counts."},
	{"id": "neon", "slot": "decor", "name": "Neon CHIEF sign", "price": 3500, "desc": "Pink neon on the wall."},
	{"id": "aquarium", "slot": "decor", "name": "Saltwater aquarium", "price": 6000, "desc": "Three fish. All named Marco."},
]

const SHOWROOM_UPGRADES := [
	{"id": "coffee", "name": "Espresso bar", "price": 3000, "desc": "Customers start a little happier."},
	{"id": "lights", "name": "Showroom spotlights", "price": 5000, "desc": "Cars look better: +5 customer interest.", "tier": 2},
	{"id": "lounge", "name": "Leather lounge", "price": 8000, "desc": "Customers wait twice as long and tolerate more haggling.", "tier": 2},
	{"id": "turntable", "name": "Display turntables", "price": 15000, "desc": "Gold podiums: +10 customer interest.", "tier": 3},
	{"id": "expand1", "name": "Expand the lot", "price": 20000, "desc": "+2 car slots (6 total)."},
	{"id": "expand2", "name": "Expand the lot again", "price": 45000, "desc": "+2 more car slots (8 total).", "needs": "expand1"},
]

const ADS := [
	{"id": "flyers", "name": "Flyers on windshields", "monthly": 400, "walkins": 1, "desc": "+1 walk-in a day."},
	{"id": "insta", "name": "Instagram ads", "monthly": 1500, "walkins": 2, "desc": "+2 walk-ins a day."},
	{"id": "radio", "name": "KTEW radio spots", "monthly": 4000, "walkins": 3, "desc": "+3 walk-ins a day, bigger budgets."},
	{"id": "billboard", "name": "Coast Highway billboard", "monthly": 9000, "walkins": 5, "desc": "+5 walk-ins a day, luxury buyers."},
]

## The dealership itself grows in three steps. Each one is a different building on the same Tewport corner
## (tools/dealership3d.py renders every screen for every tier; files end in _t1 / _t2, tier 3 has no suffix).
const DEALERSHIPS := [
	{"tier": 1, "name": "Corner Lot", "price": 0, "level": 1, "rent": 2500, "cars": 3, "walkins": 0, "budget": 0.85,
		"desc": "A gravel lot, a sales trailer and a carport. Customers browse outside and expect bargains."},
	{"tier": 2, "name": "Street Showroom", "price": 60000, "level": 3, "rent": 4500, "cars": 4, "walkins": 1, "budget": 1.0,
		"desc": "A real building: an indoor showroom, an office for Marco and one service bay. +1 walk-in a day, normal budgets, showroom upgrades unlocked."},
	{"tier": 3, "name": "Harbour Flagship", "price": 220000, "level": 6, "rent": 8000, "cars": 6, "walkins": 3, "budget": 1.2,
		"desc": "The glass showroom on the marina: three service bays, a marble floor and a penthouse upstairs. +3 walk-ins a day, richer buyers, Cash Whales."},
]

## First-day coach steps: [title, hint, nav screen to point at]. Each finishes when its check below passes.
const TUTORIAL := [
	["Buy your first car", "Open the Office PC and bid on a car at the AutoBidz auction. Cheap cars with good bones make the easiest profit.", "pc"],
	["Fix it up", "Go to the Garage. Click the dents, rust or a worn part on the car, pick a mechanic and repair it. Better condition sells for more.", "garage"],
	["Sell to a walk-in", "Customers wait in the Showroom. Tap one, show them a car, and haggle. Don't push past their bad-deal line or they walk.", "showroom"],
	["Close up and sleep", "When you're done for the day, hit Close & sleep. Marco reads the numbers, and you rest upstairs in your apartment.", "home"],
]


func tutorial_active() -> bool:
	return tutorial < TUTORIAL.size()


## Advances the first-day coach when the player has done the current step. Returns true when it moved.
func check_tutorial() -> bool:
	if not tutorial_active():
		return false
	var done := false
	match tutorial:
		0: done = not cars.is_empty() or stats.sold > 0
		1: done = cars.any(func(c): return c.get("spent", 0) > 0) or stats.sold > 0
		2: done = stats.sold > 0
		3: done = day > 1
	if done:
		tutorial += 1
		save_game()
	return done


## Marco's whiteboard: goals for the dealership you have now. [text, done?]
func goals() -> Array:
	var hired := staff.size() > 1
	match dealership:
		1:
			return [["Sell 3 cars", stats.sold >= 3], ["Make %s profit" % money_str(10000), stats.profit >= 10000],
				["Hire 1 salesperson", hired], ["Upgrade to the Street Showroom", dealership >= 2]]
		2:
			return [["Sell 15 cars", stats.sold >= 15], ["Make %s profit" % money_str(75000), stats.profit >= 75000],
				["Reach a 4.0★ Yolp rating", reputation >= 4.0], ["Move to the Harbour Flagship", dealership >= 3]]
	return [["Sell 50 cars", stats.sold >= 50], ["Make %s profit" % money_str(500000), stats.profit >= 500000],
		["Reach a 4.5★ Yolp rating", reputation >= 4.5], ["Move into the penthouse", apartment >= 3]]


## Where you sleep: the apartment on the showroom roof. Each tier is a visual upgrade of the same room.
const APARTMENTS := [
	{"tier": 1, "name": "Starter apartment", "price": 0, "monthly": 0, "fresh": 0.0,
		"desc": "A one-bedroom with a kitchenette and a glimpse of the harbour. Rent is covered for now."},
	{"tier": 2, "name": "Harbour condo", "price": 35000, "monthly": 1500, "fresh": 0.05,
		"desc": "Oak floors, a real bed and a TV. You sleep well: customers find you a little more likeable (+5% mood)."},
	{"tier": 3, "name": "Tewport penthouse", "price": 180000, "monthly": 5000, "fresh": 0.1,
		"desc": "Marble, a bar and a hot tub over the marina. +10% customer mood, and your rooftop parties bring a Cash Whale or two (+1 walk-in a day)."},
]

const STAFF_NAMES := ["Marisol", "Derek", "Yusuf", "Brianna", "Kenji", "Tasha", "Rafael", "Caitlin", "Malik", "Hana"]
const STAFF_NAMES2 := ["Sofia", "Andre", "Leila", "Cody", "Nadia", "Victor", "Imani", "Trevor", "Rosa", "Dmitri", "Kiara", "Hector", "Ava", "Jamal"]
const STAFF_TRAITS := ["Closer", "Smooth talker", "Upsells warranties", "Nervous", "Stretches the truth", "Great with families", "Car nerd", "VIP Relations", "Finance whiz"]

# ---------- state ----------

var money: int = 40000
var xp: int = 0
var level: int = 1
var reputation: float = 3.0
var day: int = 1
var clock: float = OPEN_MIN
var cars: Array = []
var listings: Array = []
var hot_class: String = "suv"
var next_id: int = 1
var stats := {"sold": 0, "buyers": 0, "profit": 0, "days_held": 0, "goal_sold_today": 0, "walked": 0, "lawsuits": 0}
var seen_intro := false
var dealer_name := "Chief Auto"   # the player names their dealership on a new game
var tutorial := 0                 # first-day coach: index of the current step, TUTORIAL.size() when finished or skipped
var owned: Array = ["folding", "plastic", "crt"]
var equipped := {"desk": "folding", "chair": "plastic", "monitor": "crt"}
var decor_on: Array = []
var upgrades: Array = []
var ads_active: Array = []
var staff: Array = []
var candidates: Array = []
var walkin_schedule: Array = []   # game minutes when today's walk-ins arrive
var ledger_day := {}              # money in and out today, by category
var ledger_month := {}            # same for this month (shown in the month-end summary)
var month_walked := 0
var month_sold := 0
var liabilities: Array = []       # shady deals that can still turn into lawsuits
var last_month_report := {}       # filled on the 1st, shown by the night report
var reviews: Array = []          # Yolp reviews, newest last
var referrals := 0                # happy customers send friends tomorrow
var pending_referrals := 0        # today's walk-ins who were referred
var memberships: Array = ["autobidz"]
var dealership := 1               # tier of the dealership building (see DEALERSHIPS)
var apartment := 1                # tier of the rooftop apartment (see APARTMENTS)
var debug_day := 0
var debug_level := 0
var debug_screen := ""
var debug := false                # ?debug in the web build: start with cars and a customer (testing)


func _ready() -> void:
	randomize()
	# Testing hook: ?seed=N in the web build makes runs repeatable.
	if OS.has_feature("web"):
		var loc = JavaScriptBridge.get_interface("location")
		var query: String = str(loc.search) if loc else ""
		var at := query.find("seed=")
		if at >= 0:
			seed(int(query.substr(at + 5)))
		debug = query.find("debug") >= 0
		var dd := query.find("day=")
		if dd >= 0:
			debug_day = int(query.substr(dd + 4))
		var sc := query.find("screen=")
		if sc >= 0:
			debug_screen = query.substr(sc + 7).split("&")[0]
		var lv := query.find("level=")
		if lv >= 0:
			debug_level = int(query.substr(lv + 6))
	if not load_game():
		new_game()


func new_game() -> void:
	money = 40000
	xp = 0
	level = 1
	reputation = 3.0
	day = 1
	clock = OPEN_MIN
	cars = []
	next_id = 1
	stats = {"sold": 0, "buyers": 0, "profit": 0, "days_held": 0, "goal_sold_today": 0, "walked": 0, "lawsuits": 0}
	seen_intro = false
	dealer_name = "Chief Auto"
	tutorial = 0
	ledger_day = {}
	ledger_month = {}
	month_walked = 0
	month_sold = 0
	liabilities = []
	last_month_report = {}
	owned = ["folding", "plastic", "crt"]
	equipped = {"desk": "folding", "chair": "plastic", "monitor": "crt"}
	decor_on = []
	upgrades = []
	ads_active = []
	dealership = 1
	apartment = 1
	# a starter dealership: just you and Jeff. Amna and Maruchan are on StaffHire the first week.
	staff = [make_staff("Jeff", "jeff", {"closing": 22, "rapport": 46, "finance": 8, "upsell": 38}, "Stretches the truth")]
	staff[0].fixed = true
	memberships = ["autobidz"]
	referrals = 0
	reviews = []
	for r in [[4, "Kayla M.", "Nice lot, friendly people. Got a fair deal."], [2, "Chad W.", "The blond salesman tried to sell me a minivan as a sports car."],
			[3, "Monica L.", "Under new management? We'll see."], [3, "Omar A.", "Cars are okay. Prices are okay. It's okay."],
			[4, "Mei C.", "Amna was great. Jeff was... there."], [2, "Grant H.", "Waited 40 minutes for anyone to talk to me."]]:
		reviews.append({"stars": r[0], "name": r[1], "text": r[2], "day": 0, "pid": PersonArt.pool_pid(r[1].length() * 7, r[1]), "weight": 1, "fixed": false})
	_recompute_rep()
	hot_class = ["economy", "truck", "suv"].pick_random()
	generate_listings()
	generate_candidates()
	candidates = [make_staff("Amna", "amna", {"closing": 86, "rapport": 74, "finance": 70, "upsell": 64}, "Closer"),
		make_staff("Maruchan", "maruchan", {"closing": 52, "rapport": 92, "finance": 38, "upsell": 66}, "VIP Relations")] + candidates.slice(0, 2)
	schedule_walkins()
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


func spend(amount: int, cat := "other") -> bool:
	if amount > money:
		return false
	money -= amount
	log_money(cat, -amount)
	emit_signal("changed")
	return true


func earn(amount: int, cat := "sales") -> void:
	money += amount
	log_money(cat, amount)
	emit_signal("changed")


## Categories: sales, finance, addons, cars, repairs, shop, ads, rent, payroll, legal, other
func log_money(cat: String, amount: int) -> void:
	ledger_day[cat] = ledger_day.get(cat, 0) + amount
	ledger_month[cat] = ledger_month.get(cat, 0) + amount


func ledger_total(l: Dictionary, sign: int) -> int:
	var t := 0
	for k in l:
		if sign > 0 and l[k] > 0 or sign < 0 and l[k] < 0:
			t += l[k]
	return t


func has_staff(name: String) -> bool:
	for s in staff:
		if s.name == name:
			return true
	return false


func days_until_bills() -> int:
	return days_in_month() - date_dict().day + 1


func day_phase() -> String:
	if clock < 11 * 60: return "Morning"
	if clock < 16.5 * 60: return "Afternoon"
	if clock < 18.5 * 60: return "Golden hour"
	if clock < 20 * 60: return "Dusk"
	return "Night"


func change_rep(delta: float) -> void:
	reputation = clamp(reputation + delta, 0.0, 5.0)
	emit_signal("changed")


# ---------- reviews (Yolp) ----------

func review_avg() -> float:
	var total := 0.0
	var w := 0.0
	for r in reviews.slice(max(0, reviews.size() - 30)):
		total += r.stars * r.weight
		w += r.weight
	return 3.0 if w == 0 else total / w


func _recompute_rep() -> void:
	reputation = clamp(review_avg(), 0.0, 5.0)
	emit_signal("changed")


## Posts a review. stars 1-5; influencers count three times. Five-star reviews send a friend tomorrow.
func add_review(customer: Dictionary, stars: int, car_model := "", seller := "", text := "") -> void:
	stars = clamp(stars, 1, 5)
	if text == "":
		text = REVIEW_TEXT[stars].pick_random().replace("{car}", car_model if car_model != "" else "car").replace("{seller}", seller if seller != "" else "the staff")
	var nm: String = customer.get("name", REVIEW_NAMES.pick_random())
	if not nm.contains("."):
		nm += " " + "ABCDEFGHJKLMNPRSTW"[randi() % 18] + "."
	var infl: bool = customer.get("type", "") == "influencer"
	if infl:
		text = "[Influencer · 80k followers] " + text
	reviews.append({"stars": stars, "name": nm, "text": text, "day": day, "pid": customer_pid(customer), "weight": 3 if infl else 1, "fixed": false})
	if stars == 5:
		referrals += 1
	_recompute_rep()


func stars_from_happiness(h: float) -> int:
	if h >= 0.8: return 5
	if h >= 0.6: return 4
	if h >= 0.4: return 3
	if h >= 0.2: return 2
	return 1


func customer_pid(c: Dictionary) -> String:
	if c.has("pid"):
		return c.pid
	return PersonArt.pool_pid(int(c.get("look_seed", 0)), c.get("name", ""))


func staff_pid(s: Dictionary) -> String:
	match s.get("look", "random"):
		"amna", "jeff", "maruchan":
			return s.look
	return s.get("pid", PersonArt.pool_pid(int(s.get("seed", 1)), s.name))


# ---------- auctions ----------

func auction(id: String) -> Dictionary:
	for a in AUCTIONS:
		if a.id == id:
			return a
	return {}


func auction_unlocked(a: Dictionary) -> bool:
	return level >= a.level and reputation >= a.rep


func has_upgrade(id: String) -> bool:
	return id in upgrades


func has_decor(id: String) -> bool:
	return id in decor_on


func lot_capacity() -> int:
	return dealership_info().cars + (2 if has_upgrade("expand1") else 0) + (2 if has_upgrade("expand2") else 0)


func item(id: String) -> Dictionary:
	for list in [DESK_ITEMS, SHOWROOM_UPGRADES, ADS]:
		for it in list:
			if it.id == id:
				return it
	return {}


# ---------- calendar and clock ----------

func date_dict(d := day) -> Dictionary:
	return Time.get_datetime_dict_from_unix_time(START_UNIX + (d - 1) * 86400)


func date_str(d := day) -> String:
	var dd := date_dict(d)
	var months := ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
	var wk := ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
	return "%s %s %d" % [wk[dd.weekday], months[dd.month - 1], dd.day]


func clock_str() -> String:
	var m := int(clock)
	var hh := m / 60
	var ampm := "AM" if hh < 12 else "PM"
	var h12 := hh % 12
	if h12 == 0:
		h12 = 12
	return "%d:%02d %s" % [h12, m % 60, ampm]


func night_amount() -> float:
	# 0 in daylight, rising after 18:30 to full night at 20:15
	return clamp((clock - 18.5 * 60) / 105.0, 0.0, 1.0)


func sunset_amount() -> float:
	return clamp((clock - 16.5 * 60) / 120.0, 0.0, 1.0) * (1.0 - night_amount())


func sky_tint() -> Color:
	var day_c := Color(1, 1, 1)
	var sunset_c := Color(1.0, 0.82, 0.7)
	var night_c := Color(0.32, 0.38, 0.6)
	var c := day_c.lerp(sunset_c, sunset_amount())
	return c.lerp(night_c, night_amount())


func days_in_month(d := day) -> int:
	var dd := date_dict(d)
	var n := 28
	while date_dict(d - dd.day + 1 + n).month == dd.month:
		n += 1
	return n


func monthly_bills() -> Dictionary:
	var salaries := 0
	for s in staff:
		salaries += s.salary
	var ads := 0
	for a in ADS:
		if a.id in ads_active:
			ads += a.monthly
	var rent: int = dealership_info().rent + apartment_info().monthly
	return {"rent": rent, "salaries": salaries, "ads": ads, "total": rent + salaries + ads}


func dealership_info(tier := -1) -> Dictionary:
	var t: int = dealership if tier < 0 else tier
	return DEALERSHIPS[clamp(t, 1, DEALERSHIPS.size()) - 1]


## File suffix for this tier's renders: "_t1", "_t2", or "" for the flagship.
func world_suffix() -> String:
	return "" if dealership >= DEALERSHIPS.size() else "_t%d" % dealership


## Why the next dealership can't be bought yet, or "" when it can.
func dealership_blocker() -> String:
	if dealership >= DEALERSHIPS.size():
		return "You already own the flagship."
	var nxt := dealership_info(dealership + 1)
	if level < nxt.level:
		return "Reach level %d first." % nxt.level
	if money < nxt.price:
		return "You need %s." % money_str(nxt.price)
	return ""


func upgrade_dealership() -> bool:
	if dealership_blocker() != "":
		return false
	var nxt := dealership_info(dealership + 1)
	money -= nxt.price
	log_money("shop", -nxt.price)
	dealership += 1
	add_xp(100)
	save_game()
	emit_signal("changed")
	return true


func apartment_info(tier := -1) -> Dictionary:
	var t: int = apartment if tier < 0 else tier
	return APARTMENTS[clamp(t, 1, APARTMENTS.size()) - 1]


## Moves into the next apartment tier. Returns false when you can't afford it.
func upgrade_apartment() -> bool:
	if apartment >= APARTMENTS.size():
		return false
	var nxt := apartment_info(apartment + 1)
	if money < nxt.price:
		return false
	money -= nxt.price
	log_money("shop", -nxt.price)
	apartment += 1
	save_game()
	emit_signal("changed")
	return true


func next_bill_date() -> String:
	var dd := date_dict()
	var left: int = days_in_month() - dd.day + 1
	return date_str(day + left)


# ---------- walk-ins ----------

func walkins_today() -> int:
	var n := 2
	for a in ADS:
		if a.id in ads_active:
			n += a.walkins
	if reputation >= 4.0:
		n += 1
	if reputation < 2.0:
		n -= 1
	if apartment >= 3:
		n += 1
	n += dealership_info().walkins
	return max(1, n)


func schedule_walkins() -> void:
	walkin_schedule = []
	for i in walkins_today() + referrals:
		walkin_schedule.append(randi_range(9 * 60, 18 * 60))
	walkin_schedule.sort()
	pending_referrals = referrals
	referrals = 0


func make_customer() -> Dictionary:
	var types := ["bargain", "local", "first", "nerd", "parent", "bargain", "local", "first", "nerd", "parent", "influencer", "lowballer", "lowballer"]
	if reputation >= 3.5 or "billboard" in ads_active or apartment >= 3 or dealership >= 3:
		types += ["whale", "whale"]
	var type_key: String = types.pick_random()
	var rich := 0.0
	if "radio" in ads_active:
		rich += 0.1
	if "billboard" in ads_active:
		rich += 0.25
	var tier := randi_range(0, 3)
	if randf() < rich:
		tier = 0
	var c := {
		"id": next_id, "name": BUYER_NAMES.pick_random(), "type": type_key,
		"look_seed": randi(), "credit": tier,
		"budget": BUYER_TYPES[type_key].budget * randf_range(0.9, 1.15) * (1.0 + rich) * dealership_info().budget,
		"finance": randf() < 0.7, "happiness": 0.55 + randf_range(-0.05, 0.1) + apartment_info().fresh, "patience": 1.0,
		"arrived": clock, "wants_cls": ["economy", "suv", "truck", "sport", "exotic"].pick_random(),
	}
	c.pid = PersonArt.pool_pid(randi(), c.name)
	if type_key == "whale":
		c.finance = false
		c.wants_cls = ["sport", "exotic", "suv"].pick_random()
	if type_key == "influencer":
		c.wants_cls = ["sport", "exotic"].pick_random()
	if pending_referrals > 0:
		pending_referrals -= 1
		c.referral = true
		c.happiness += 0.15
	next_id += 1
	return c


# ---------- staff ----------

## Builds a salesperson. Stars and salary follow their skills: better people cost a lot more.
func make_staff(name: String, look: String, skills: Dictionary, trait_name: String) -> Dictionary:
	var s := {"name": name, "look": look, "skills": skills, "trait": trait_name, "fixed": false, "sales": 0}
	if look == "random":
		s.pid = PersonArt.pool_pid(randi(), name)
	_rate_staff(s)
	return s


func _rate_staff(s: Dictionary) -> void:
	var avg := 0.0
	for k in SKILLS:
		avg += s.skills[k]
	avg /= SKILLS.size()
	s.stars = clamp(int(round(avg / 20.0 + 0.2)), 1, 5)
	s.salary = int(round((1400 + pow(avg / 100.0, 2.2) * 8500) / 100.0)) * 100
	s.hire_fee = int(round(s.salary * (0.4 + avg / 200.0) / 100.0)) * 100


func generate_candidates() -> void:
	candidates = []
	# tiers: rookies are cheap, stars only apply once the dealership has a name
	var tiers := [[18, 45], [38, 68], [58, 84]]
	if level >= 3 or reputation >= 3.8:
		tiers.append([78, 97])
	var used := []
	for s in staff:
		used.append(s.name)
	for i in 4:
		var t: Array = tiers[min(i, tiers.size() - 1)] if i < 3 else tiers.pick_random()
		var skills := {}
		for k in SKILLS:
			skills[k] = clamp(randi_range(t[0], t[1]), 5, 99)
		var spec: String = SKILLS.pick_random()
		skills[spec] = clamp(skills[spec] + randi_range(8, 18), 5, 99)
		var nm: String = (STAFF_NAMES + STAFF_NAMES2).pick_random()
		while nm in used:
			nm = (STAFF_NAMES + STAFF_NAMES2).pick_random()
		used.append(nm)
		var tr_name: String = STAFF_TRAITS.pick_random()
		if spec == "finance" and randf() < 0.5:
			tr_name = "Finance whiz"
		candidates.append(make_staff(nm, "random", skills, tr_name))


func skill(s: Dictionary, k: String) -> int:
	return int(s.get("skills", {}).get(k, s.get("stars", 2) * 18))


func staff_close_chance(s: Dictionary) -> float:
	var c: float = 0.08 + skill(s, "closing") * 0.0072
	if s.trait == "Closer":
		c += 0.06
	if s.trait == "Nervous":
		c -= 0.1
	return clamp(c, 0.05, 0.92)


## Staff get a little better with every car they sell.
func staff_practice(s: Dictionary) -> void:
	s.sales = s.get("sales", 0) + 1
	var k: String = SKILLS.pick_random()
	s.skills[k] = min(99, s.skills[k] + randi_range(1, 2))
	var old_salary: int = s.salary
	_rate_staff(s)
	s.salary = old_salary  # raises are negotiated, not automatic


# ---------- cars ----------

func make_car(max_base: int, house := "autobidz") -> Dictionary:
	var pool := MODELS.filter(func(m): return m[2] <= max_base)
	if has_perk("sourcing"):
		pool += MODELS.filter(func(m): return m[1] in ["sport", "exotic"] and m[2] <= max_base * 2)
	if house == "exotic":
		pool = MODELS.filter(func(m): return m[1] in ["sport", "exotic"] and m[2] >= 45000)
	var m: Array = pool.pick_random()
	var age := randi_range(2, 14)
	var car := {
		"id": next_id, "model": m[0], "cls": m[1], "base": m[2],
		"year": CURRENT_YEAR - age,
		"miles": int(age * randi_range(7000, 15000) / 100) * 100,
		"parts": {}, "hidden": {}, "detailed": false,
		"color": CarArt.PAINTS.pick_random(),
		"history": ["Clean", "Clean", "Clean", "Minor accident", "Major accident", "Flood"].pick_random(),
		"history_known": false, "paid": 0, "spent": 0, "day_bought": 0,
	}
	next_id += 1
	var lo: int = {"salvage": 10, "dealer": 50, "exotic": 55}.get(house, 25)
	var hi: int = {"salvage": 55, "dealer": 92, "exotic": 95}.get(house, 90)
	for p in PARTS:
		car.parts[p] = randi_range(lo, hi)
	var faults := randi_range(0, 2)
	match house:
		"salvage":
			faults += 1
			car.history = ["Minor accident", "Major accident", "Major accident", "Flood", "Flood", "Clean"].pick_random()
		"dealer", "exotic":
			faults = randi_range(0, 1)
			car.history = ["Clean", "Clean", "Clean", "Clean", "Minor accident"].pick_random()
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


func sale_value(car: Dictionary) -> int:
	var v := float(value(car))
	if car.cls == hot_class:
		v *= 1.1
	if has_perk("vip") and car.cls in ["sport", "exotic"]:
		v *= 1.1
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


func listing_count() -> int:
	return 6 + {"crt": 0, "lcd": 1, "dual": 2, "ultra": 3}[equipped.monitor]


func generate_listings() -> void:
	listings = []
	# price ranges per house: [start lo, start hi, rival max lo, rival max hi, buy-now chance, buy-now lo, buy-now hi]
	var deal := {
		"autobidz": [0.25, 0.4, 0.55, 0.85, 0.35, 0.85, 0.95],
		"salvage": [0.1, 0.2, 0.3, 0.5, 0.5, 0.5, 0.62],
		"dealer": [0.28, 0.4, 0.5, 0.7, 0.45, 0.72, 0.82],
		"exotic": [0.3, 0.45, 0.55, 0.75, 0.3, 0.78, 0.88],
	}
	for house in memberships:
		var used := []
		var n: int = listing_count() if house == "autobidz" else 4
		for i in n:
			var car := make_car(max_auction_base(), house)
			for attempt in 4:
				if not used.has(car.model):
					break
				car = make_car(max_auction_base(), house)
			used.append(car.model)
			var v := value(car)
			var d: Array = deal[house]
			var start: int = int(round(v * randf_range(d[0], d[1]) / 100.0) * 100)
			listings.append({
				"car": car, "current": start, "start": start, "house": house,
				"leader": "", "rival": RIVALS.pick_random(),
				"rival_max": int(v * randf_range(d[2], d[3])),
				"buy_now": int(round(v * randf_range(d[5], d[6]) / 100.0) * 100) if randf() < d[4] else 0,
				"haggled": false, "sold": false, "winner": "",
			})


func add_car(car: Dictionary, price: int) -> void:
	car.paid = price
	car.day_bought = day
	car.sticker = int(round(sale_value(car) * 1.1 / 100.0)) * 100
	cars.append(car)
	emit_signal("changed")


func remove_car(car: Dictionary) -> void:
	cars.erase(car)
	emit_signal("changed")


# ---------- day cycle ----------

## Closes the day and opens the next one. Returns notes for Marco's end-of-day report.
func end_day() -> Array:
	var notes := []
	if stats.goal_sold_today >= 1:
		money += 500
		notes.append("Daily goal met: %s bonus." % money_str(500))
		add_xp(25)
	last_month_report = {}
	# shady deals catch up with you
	for l in liabilities.duplicate():
		if day < l.due:
			continue
		liabilities.erase(l)
		if randf() < l.risk:
			var cost: int = l.damages
			money -= cost
			log_money("legal", -cost)
			stats.lawsuits = stats.get("lawsuits", 0) + 1
			add_review({"name": l.customer}, 1, "", "", "Sued them over %s. Read your contract before you sign anything here." % l.reason)
			notes.append("LAWSUIT: %s sued us over %s. Settled for %s." % [l.customer, l.reason, money_str(cost)])
	day += 1
	clock = OPEN_MIN
	stats.goal_sold_today = 0
	hot_class = ["economy", "truck", "suv", "sport", "exotic"].pick_random()
	if date_dict().day == 1:
		var b := monthly_bills()
		money -= b.total
		log_money("rent", -b.rent)
		log_money("payroll", -b.salaries)
		log_money("ads", -b.ads)
		var months := ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
		var prev := date_dict(day - 1)
		last_month_report = {"title": "%s %d" % [months[prev.month - 1], prev.year], "ledger": ledger_month.duplicate(),
			"sold": month_sold, "walked": month_walked, "reputation": reputation, "money": money, "staff": staff.duplicate(true)}
		ledger_month = {}
		month_sold = 0
		month_walked = 0
		notes.append("New month. Paid %s in bills: rent %s, staff %s, advertising %s." % [money_str(b.total), money_str(b.rent), money_str(b.salaries), money_str(b.ads)])
		generate_candidates()
	if date_dict().weekday == 1:
		generate_candidates()
	ledger_day = {}
	generate_listings()
	schedule_walkins()
	save_game()
	emit_signal("changed")
	return notes


## Record a shady deal. risk = chance it becomes a lawsuit; it is decided days later.
func add_liability(customer: String, reason: String, risk: float, damages: int) -> void:
	liabilities.append({"customer": customer, "reason": reason, "risk": clamp(risk, 0.0, 0.95),
		"damages": damages, "due": day + randi_range(2, 6)})


func legal_exposure() -> int:
	var t := 0
	for l in liabilities:
		t += int(l.damages * l.risk)
	return t


# ---------- save / load ----------

const SAVE_KEYS := ["money", "xp", "level", "reputation", "day", "clock", "cars", "listings", "hot_class", "next_id",
	"stats", "seen_intro", "owned", "equipped", "decor_on", "upgrades", "ads_active", "staff", "candidates", "walkin_schedule",
	"ledger_day", "ledger_month", "month_walked", "month_sold", "liabilities", "reviews", "referrals", "memberships", "apartment", "dealer_name", "tutorial", "dealership"]


func save_game() -> void:
	var data := {"version": 4}
	for k in SAVE_KEYS:
		data[k] = get(k)
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
	if typeof(data) != TYPE_DICTIONARY or int(data.get("version", 1)) < 4:
		return false
	new_game()
	tutorial = TUTORIAL.size()   # saves from before the tutorial existed skip it
	dealership = DEALERSHIPS.size()   # and keep the flagship they already had
	for k in SAVE_KEYS:
		if data.has(k):
			set(k, _fix_ints(data[k]))
	reputation = float(reputation)
	clock = float(clock)
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


# ---------- visible body damage (3D service bay) ----------

const PANELS := ["front_bumper", "hood", "fender_fl", "fender_fr", "door_fl", "door_fr", "door_rl", "door_rr",
	"quarter_rl", "quarter_rr", "roof", "trunk", "rear_bumper", "bed"]
const LIGHTS := ["headlight_l", "headlight_r", "taillight_l", "taillight_r"]
const PANEL_NAMES := {"front_bumper": "Front bumper", "hood": "Hood", "fender_fl": "Front fender (left)",
	"fender_fr": "Front fender (right)", "door_fl": "Front door (left)", "door_fr": "Front door (right)",
	"door_rl": "Rear door (left)", "door_rr": "Rear door (right)", "quarter_rl": "Rear quarter (left)",
	"quarter_rr": "Rear quarter (right)", "roof": "Roof", "trunk": "Trunk lid", "rear_bumper": "Rear bumper",
	"bed": "Truck bed", "headlight_l": "Headlight (left)", "headlight_r": "Headlight (right)",
	"taillight_l": "Taillight (left)", "taillight_r": "Taillight (right)"}
const DAMAGE_KINDS := {"dent": "Dent", "rust": "Rust", "scratch": "Scratches"}
const TRIMS := {"chrome": "Chrome", "black": "Gloss black", "body": "Body color"}
const RIMS := {"silver": "Silver", "black": "Satin black", "gunmetal": "Gunmetal", "gold": "Bronze"}


## Gives a car visible damage that matches its body condition and history (once).
func ensure_damage(car: Dictionary) -> void:
	if car.has("damage"):
		return
	var dmg := {}
	var sev: float = 1.0 - car.parts.body / 100.0
	var n := int(round(sev * 9.0 + randf() * 2.0))
	var pool := PANELS.duplicate()
	pool.shuffle()
	for i in min(n, pool.size()):
		var d := {}
		var p: String = pool[i]
		if randf() < 0.55:
			d.scratch = snappedf(randf_range(0.4, 1.0), 0.01)
		if randf() < sev + 0.15:
			d.dent = snappedf(randf_range(0.4, 1.0), 0.01)
		if randf() < sev * 0.8 or car.history == "Flood":
			d.rust = snappedf(randf_range(0.3, 0.9) * (1.3 if car.history == "Flood" else 1.0), 0.01)
		if d.is_empty():
			d.scratch = 0.6
		dmg[p] = d
	if car.history == "Major accident":
		dmg["front_bumper"] = {"dent": 1.0, "scratch": 1.0}
		dmg["hood"] = {"dent": 0.8}
	for l in LIGHTS:
		if randf() < sev * 0.35 or (car.history == "Major accident" and l.begins_with("head") and randf() < 0.5):
			dmg[l] = {"broken": 1.0}
	car.damage = dmg
	if not car.has("trim"):
		car.trim = "chrome" if randf() < 0.5 else "black"
	if not car.has("rims"):
		car.rims = "silver"


func damage_count(car: Dictionary) -> int:
	ensure_damage(car)
	var n := 0
	for p in car.damage:
		n += car.damage[p].size()
	return n


## Cost to fix one kind of damage on one panel with a given shop.
func panel_fix_cost(car: Dictionary, kind: String, mech: Dictionary) -> int:
	var base: int = {"dent": 380, "rust": 520, "scratch": 220, "broken": 450, "repaint": 900}[kind]
	var lux: float = 1.0 + car.base / 120000.0
	var shop: float = 0.6 + mech.cost * 60.0
	return int(round(base * lux * shop / 10.0)) * 10


## Fixes damage on a panel; returns the body-condition points gained.
func fix_panel(car: Dictionary, panel: String, kind: String) -> int:
	var d: Dictionary = car.damage.get(panel, {})
	var gain := 0
	if kind == "repaint":
		for k in ["scratch", "rust"]:
			if d.has(k):
				gain += int(d[k] * 4) + 2
				d.erase(k)
	elif d.has(kind):
		gain = int(d[kind] * 5) + 2
		d.erase(kind)
	if d.is_empty():
		car.damage.erase(panel)
	car.parts.body = min(100, car.parts.body + gain)
	return gain


## When the shop does a general body job, clear the worst panels too so the car looks it.
func clear_some_damage(car: Dictionary, points: int) -> void:
	ensure_damage(car)
	var keys: Array = car.damage.keys()
	keys.shuffle()
	var left := points
	for p in keys:
		if left <= 0:
			break
		var d: Dictionary = car.damage[p]
		for k in d.keys():
			left -= int(d[k] * 5) + 2
			d.erase(k)
			if left <= 0:
				break
		if d.is_empty():
			car.damage.erase(p)
