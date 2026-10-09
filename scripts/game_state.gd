extends Node
## Global game state for Chief Auto: money, calendar and clock, progression, cars, staff, shops, save/load.

signal changed

const SAVE_PATH := "user://chief_auto_save.json"
const LEADERBOARD_PATH := "user://chief_auto_leaderboard.json"
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
## [name, class, new price, resale strength]. New prices track the real counterparts (2026 MSRP); resale strength
## is how well the model holds value on the used market (Civics and Wranglers hold, EVs and luxury SUVs drop).
const MODELS := [
	["Hondo Civix", "economy", 26000, 1.10],
	["Toyoda Camri", "economy", 29000, 1.05],
	["Mazdo Miota", "sport", 30000, 1.05],
	["Subaro Outbuck", "suv", 32000, 1.00],
	["Forde Rangler", "truck", 34000, 1.10],
	["Jeap Wrangle", "suv", 36000, 1.15],
	["Dodgy Charjer", "sport", 38000, 0.90],
	["Teslo Model 3", "economy", 42000, 0.80],
	["Forde Mustank", "sport", 48000, 0.95],
	["Ramm 1500", "truck", 48000, 1.00],
	["Chevro Tahoma", "suv", 58000, 1.00],
	["BMV M4", "sport", 80000, 0.85],
	["Rang Rovah", "suv", 90000, 0.75],
	["Porsha 911", "sport", 125000, 1.10],
	["Mercedez G-Wagon", "suv", 150000, 1.05],
	["Ferrano 488", "exotic", 300000, 0.95],
	["Lamborgo Aventa", "exotic", 450000, 0.95],
]

const MECHANICS := [
	{"name": "Cousin Ray", "where": "backyard garage", "level": 1, "cost": 0.008, "min": 10, "max": 20, "botch": 0.25, "find": 0.2},
	{"name": "Strip-Mall Auto", "where": "strip-mall shop", "level": 3, "cost": 0.015, "min": 20, "max": 30, "botch": 0.10, "find": 0.5},
	{"name": "Harbor Certified", "where": "certified shop", "level": 6, "cost": 0.024, "min": 30, "max": 40, "botch": 0.04, "find": 0.8},
	{"name": "Euro Specialist", "where": "luxury specialist", "level": 10, "cost": 0.034, "min": 40, "max": 50, "botch": 0.01, "find": 1.0},
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
	"whale": {"title": "Cash Whale", "budget": 1.35, "likes": ["features", "test_drive"], "tolerance": 1.5,
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
	{"id": "dual", "slot": "monitor", "name": "Dual monitors", "price": 1800, "desc": "+2 auction listings every day."},
	{"id": "ultra", "slot": "monitor", "name": "Curved ultrawide", "price": 4000, "desc": "+3 auction listings every day. Very wide. Very cool."},
	{"id": "plant", "slot": "decor", "name": "Potted palm", "price": 150, "desc": "A little Tewport on your desk."},
	{"id": "mug", "slot": "decor", "name": "\"#1 Closer\" mug", "price": 40, "desc": "Gift from yourself."},
	{"id": "modelcar", "slot": "decor", "name": "Model Ferrano", "price": 900, "desc": "1:18 scale. Shelf display."},
	{"id": "trophy", "slot": "decor", "name": "Salesperson of the Year", "price": 2500, "desc": "You bought it. Still counts."},
	{"id": "bobble_marco", "slot": "decor", "name": "Marco bobblehead", "price": 120, "desc": "Nods at every offer. Just like the real one."},
	{"id": "bobble_jeff", "slot": "decor", "name": "Jeff bobblehead", "price": 90, "desc": "Limited edition. Jeff ordered 400 of them."},
	{"id": "bobble_surfer", "slot": "decor", "name": "Surfer bobblehead", "price": 75, "desc": "Hangs ten on your desk. Never shows up for work."},
	{"id": "bobble_lifeguard", "slot": "decor", "name": "Lifeguard bobblehead", "price": 75, "desc": "Watches your margins. Blows the whistle on lowballers."},
	{"id": "hula", "slot": "decor", "name": "Dashboard hula girl", "price": 60, "desc": "Rescued from a trade-in. Still dancing."},
	{"id": "photo_marco", "slot": "decor", "name": "Framed Marco portrait", "price": 300, "desc": "Walnut frame. His eyes follow you around the office."},
	{"id": "photo_lot", "slot": "decor", "name": "Framed dealership photo", "price": 250, "desc": "The lot on a good day. Proof it happens."},
	{"id": "first_dollar", "slot": "decor", "name": "Framed first dollar", "price": 100, "desc": "Cost you a hundred. Worth a dollar. Worth a dollar. Priceless."},
	{"id": "globe", "slot": "decor", "name": "Desk globe", "price": 350, "desc": "For planning the Chief Auto world takeover."},
	{"id": "lamp", "slot": "decor", "name": "Banker's lamp", "price": 280, "desc": "Green glass. Makes every contract look legally binding."},
	{"id": "polesign", "slot": "decor", "name": "Mini CHIEF AUTO pole sign", "price": 450, "desc": "The pole sign out front, in a size the city can't fine you for."},
	{"id": "cradle", "slot": "decor", "name": "Newton's cradle", "price": 180, "desc": "Click. Click. Click. Customers hate it. You love it."},
	{"id": "magazines", "slot": "decor", "name": "Car magazine stack", "price": 40, "desc": "Every issue since 2019. Never read one."},
	{"id": "neon", "slot": "decor", "name": "Neon CHIEF sign", "price": 3500, "desc": "Pink neon on the wall."},
	{"id": "aquarium", "slot": "decor", "name": "Saltwater aquarium", "price": 6000, "desc": "Three fish. All named Marco."},
]

const SHOWROOM_UPGRADES := [
	{"id": "coffee", "name": "Espresso bar", "price": 3000, "desc": "Offer every walk-in an espresso: +15% happiness and a little more patience."},
	{"id": "lights", "name": "Showroom spotlights", "price": 5000, "desc": "Cars look better: +5 customer interest.", "tier": 2},
	{"id": "lounge", "name": "Leather lounge", "price": 8000, "desc": "Customers wait twice as long and tolerate more haggling.", "tier": 2},
	{"id": "turntable", "name": "Display turntables", "price": 15000, "desc": "Gold podiums: +10 customer interest.", "tier": 3},
	{"id": "expand1", "name": "Expand the lot", "price": 20000, "desc": "+2 car spots on top of what your building holds. Moves with you when you upgrade."},
	{"id": "expand2", "name": "Expand the lot again", "price": 45000, "desc": "+2 more car spots, on top of the first expansion.", "needs": "expand1"},
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
	{"tier": 1, "name": "Corner Lot", "price": 0, "level": 1, "rent": 2500, "cars": 3, "walkins": 0, "budget": 0.9, "max_car": 50000,
		"desc": "A gravel lot, a sales trailer and a carport. Customers browse outside and expect bargains, and auctions won't send you anything too fancy."},
	{"tier": 2, "name": "Street Showroom", "price": 60000, "level": 3, "rent": 4500, "cars": 4, "walkins": 1, "budget": 0.96, "max_car": 110000,
		"desc": "A real building: an indoor showroom, an office for Marco and one service bay. +1 walk-in a day, better budgets, pricier cars at auction, more showroom upgrades."},
	{"tier": 3, "name": "Harbour Flagship", "price": 220000, "level": 6, "rent": 8000, "cars": 6, "walkins": 3, "budget": 1.04, "max_car": 0,
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
const TRAIT_DESC := {"Closer": "+6% close rate", "Smooth talker": "Buyers leave happier", "Upsells warranties": "Sells more warranties",
	"Nervous": "-10% close rate", "Stretches the truth": "Sells, but promises get us sued", "Great with families": "Closes parents and first-timers",
	"Car nerd": "Closes car nerds", "VIP Relations": "Closes whales, locals and influencers", "Finance whiz": "+50% finance profit"}

# ---------- state ----------

var money: int = 15000
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
var desk_slots: Dictionary = {}   # desk slot -> decor id (see DESK_SLOTS)
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
var loan := 0                     # TewportBank line of credit you owe; interest is billed on the 1st
var run_id := 0                   # identifies this dealership's row on the leaderboard
var peak_worth := 0
var bankrupt := {}                # set when the bills can't be paid; the dealership closes and the run is over
var debug_day := 0
var debug_level := 0
var debug_tier := 0
var debug_screen := ""
var debug_desk := false           # &desk=1: a furnished desk with collectibles (screenshots of the desk view)
var debug_broke := false          # &broke: start deep in the red (tests the closing-down screen)
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
		debug_broke = query.find("broke") >= 0
		debug_desk = query.find("desk=1") >= 0
		var dd := query.find("day=")
		if dd >= 0:
			debug_day = int(query.substr(dd + 4).split("&")[0])
		var sc := query.find("screen=")
		if sc >= 0:
			debug_screen = query.substr(sc + 7).split("&")[0]
		var lv := query.find("level=")
		if lv >= 0:
			debug_level = int(query.substr(lv + 6).split("&")[0])
		var tr := query.find("tier=")
		if tr >= 0:
			debug_tier = int(query.substr(tr + 5).split("&")[0])
	if not load_game():
		new_game()


func new_game() -> void:
	auction_clock = 0.0
	run_id = randi()
	peak_worth = 0
	bankrupt = {}
	money = 15000
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
	desk_slots = {}
	upgrades = []
	ads_active = []
	dealership = 1
	apartment = 1
	loan = 0
	pending_referrals = 0
	# a starter dealership: just you and Jeff. Amna and Maruchan are on StaffHire until you hire them.
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
	return 200 * level


func add_xp(amount: int) -> bool:
	xp += amount
	var leveled := false
	while xp >= xp_to_next():
		xp -= xp_to_next()
		level += 1
		leveled = true
	emit_signal("changed")
	return leveled


## XP for a sale grows with the profit, but slower than the money does, so big exotics don't skip whole tiers.
func sale_xp(profit: int) -> int:
	return 20 + int(sqrt(max(0, profit)) * 0.6)


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
	return id in desk_slots.values()


## Places on the desk you can put a collectible: back corners, front corners, the wall shelf.
const DESK_SLOTS := ["lb", "rb", "lf", "rf", "shelf"]
const DESK_SLOT_NAMES := {"lb": "Back left", "rb": "Back right", "lf": "Front left", "rf": "Front right", "shelf": "Wall shelf"}


## Puts an item in a slot (taking it out of any other slot first). Empty id clears the slot.
func place_decor(slot: String, id: String) -> void:
	for s in desk_slots.keys():
		if desk_slots[s] == id:
			desk_slots.erase(s)
	if id == "":
		desk_slots.erase(slot)
	else:
		desk_slots[slot] = id
	decor_on = desk_slots.values()


## &desk=1: owns a mid-range desk setup and a shelf of collectibles.
func debug_furnish() -> void:
	debug_desk = false
	for id in ["oak", "leather", "lcd", "bobble_marco", "photo_marco", "globe", "modelcar", "trophy", "mug", "bobble_surfer", "hula", "lamp", "plant", "cradle"]:
		if not id in owned:
			owned.append(id)
	equipped = {"desk": "oak", "chair": "leather", "monitor": "lcd"}
	desk_slots = {}
	for id in ["bobble_marco", "photo_marco", "modelcar", "globe", "trophy"]:
		auto_place(id)


## A newly bought collectible goes to the first free slot, if there is one.
func auto_place(id: String) -> void:
	for s in DESK_SLOTS:
		if not desk_slots.has(s):
			place_decor(s, id)
			return


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
	var interest := loan_interest()
	return {"rent": rent, "salaries": salaries, "ads": ads, "interest": interest, "total": rent + salaries + ads + interest}


# ---------- TewportBank line of credit: the way back when you're broke with nothing to sell ----------

const LOAN_RATE := 0.02   # per month


func loan_limit() -> int:
	return 15000 * dealership


func loan_interest() -> int:
	return int(ceil(loan * LOAN_RATE / 10.0)) * 10


## Borrowing isn't income, so it stays out of the daily ledger.
func borrow(amount: int) -> bool:
	amount = min(amount, loan_limit() - loan)
	if amount <= 0:
		return false
	loan += amount
	money += amount
	save_game()
	emit_signal("changed")
	return true


func repay(amount: int) -> bool:
	amount = min(amount, loan, money)
	if amount <= 0:
		return false
	loan -= amount
	money -= amount
	save_game()
	emit_signal("changed")
	return true


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
	# Amna and Maruchan keep applying until you hire them
	candidates = (named_applicants() + candidates).slice(0, 4)


func named_applicants() -> Array:
	var out := []
	var hired := staff.map(func(s): return s.name)
	if not "Amna" in hired:
		out.append(make_staff("Amna", "amna", {"closing": 86, "rapport": 74, "finance": 70, "upsell": 64}, "Closer"))
	if not "Maruchan" in hired:
		out.append(make_staff("Maruchan", "maruchan", {"closing": 52, "rapport": 92, "finance": 38, "upsell": 66}, "VIP Relations"))
	return out


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
	# early on the lanes are full of old high-mileage cars; newer, cleaner stock shows up as you level
	var age_lo: int = max(1, 12 - level)
	var age_hi: int = max(age_lo + 3, 24 - level * 2)
	var age := randi_range(age_lo, age_hi)
	if house in ["dealer", "exotic"]:
		age = max(1, age - 4)
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
	var lo: int = {"salvage": 10, "dealer": 50, "exotic": 55}.get(house, min(45, 15 + level * 3))
	var hi: int = {"salvage": 55, "dealer": 92, "exotic": 95}.get(house, min(92, 62 + level * 3))
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


static func model_info(name: String) -> Array:
	for m in MODELS:
		if m[0] == name:
			return m
	return ["", "economy", 25000, 1.0]


## Used-car depreciation like the real market: a big first-year drop, about 10% a year while the car is young,
## slower once it is old, and a floor so a runner is never worth nothing. Resale strength shifts the whole curve.
static func depreciation(age: int, cls: String, hold: float) -> float:
	var f := 0.93
	for a in range(1, age + 1):
		f *= 0.80 if a == 1 else (0.90 if a <= 5 else (0.93 if a <= 12 else 0.96))
	var floor_f: float = {"exotic": 0.30, "sport": 0.14}.get(cls, 0.10)
	return clamp(f * hold, floor_f, 0.95)


func value(car: Dictionary, true_value := false) -> int:
	var age: int = max(0, CURRENT_YEAR - car.year)
	var m := model_info(car.model)
	var dep := depreciation(age, car.cls, m[3])
	# miles against what a car that age would normally have
	var expected: float = max(6000.0, age * 12000.0)
	var miles_factor: float = clamp(1.0 - (car.miles - expected) / 400000.0, 0.75, 1.1)
	var hist := 1.0
	if car.history_known or true_value:
		hist = {"Clean": 1.0, "Minor accident": 0.92, "Major accident": 0.8, "Flood": 0.65}[car.history]
	var cond := condition(car, true_value)
	var cond_factor: float = 0.45 + 0.55 * pow(cond / 100.0, 0.8)
	var v: float = car.base * dep * miles_factor * hist * cond_factor
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


## Priciest new-car price that shows up at auction: grows with your level, capped by what your building can sell.
func max_auction_base() -> int:
	var cap: int = dealership_info().max_car
	var by_level := int(40000 * pow(1.25, level - 1))
	return by_level if cap == 0 else min(cap, by_level)


func listing_count() -> int:
	return 6 + {"crt": 0, "lcd": 1, "dual": 2, "ultra": 3}[equipped.monitor]


# price ranges per house: [start lo, start hi, typical final lo, typical final hi]
const AUCTION_DEAL := {
	"autobidz": [0.25, 0.4, 0.7, 1.0],
	"salvage": [0.1, 0.2, 0.38, 0.6],
	"dealer": [0.28, 0.4, 0.65, 0.88],
	"exotic": [0.3, 0.45, 0.68, 0.92],
}
const AUCTION_SECONDS := 60.0
var auction_clock := 0.0   # seconds of live auction time; only advances while the PC is open


func lane_size(house: String) -> int:
	return listing_count() if house == "autobidz" else 4


func bid_increment(l: Dictionary) -> int:
	return max(100, int(round(value(l.car) * 0.03 / 100.0)) * 100)


## One live auction: ends AUCTION_SECONDS (+/- a little) of auction time from `delay`.
## The rival field's walk-away price is randomized; a quarter of lanes run hot and close 5-30% over value.
func make_listing(house: String, delay := 0.0, avoid: Array = []) -> Dictionary:
	var car := make_car(max_auction_base(), house)
	for attempt in 4:
		if not avoid.has(car.model):
			break
		car = make_car(max_auction_base(), house)
	var v := value(car)
	var d: Array = AUCTION_DEAL.get(house, AUCTION_DEAL.autobidz)
	var start: int = int(round(v * randf_range(d[0], d[1]) / 100.0) * 100)
	var final: int = int(v * randf_range(d[2], d[3]))
	if randf() < 0.25:
		final = int(v * randf_range(1.05, 1.3))
	final = max(final, start)
	return {
		"car": car, "current": start, "start": start, "house": house,
		"leader": "", "rival": RIVALS.pick_random(), "rival_max": final,
		"buy_now": int(round(v * randf_range(1.1, 1.35) / 100.0) * 100),
		"ends_at": auction_clock + delay + randf_range(AUCTION_SECONDS - 10.0, AUCTION_SECONDS + 10.0),
		"next_ai": auction_clock + delay + randf_range(2.0, 6.0),
		"bids": 0, "my_bid": 0, "watch": false, "feed_log": [],
		"haggled": false, "sold": false, "winner": "",
	}


func generate_listings() -> void:
	listings = []
	for house in memberships:
		var used := []
		for i in lane_size(house):
			var l := make_listing(house, i * 8.0, used)
			used.append(l.car.model)
			listings.append(l)


func open_listings(house: String) -> Array:
	return listings.filter(func(l): return l.get("house", "autobidz") == house and not l.sold)


## Buy It Now disappears once the bidding passes it.
func buy_now_open(l: Dictionary) -> bool:
	return not l.sold and int(l.get("buy_now", 0)) > 0 and l.current < int(l.buy_now)


func _auction_note(l: Dictionary, text: String) -> void:
	var f: Array = l.get("feed_log", [])
	f.push_front(text)
	l.feed_log = f.slice(0, 4)


## The player bids one increment over the current price (or the opening bid). Returns "" or why not.
func place_bid(l: Dictionary) -> String:
	if l.sold or auction_clock >= float(l.get("ends_at", 0.0)):
		return "That auction has closed."
	if l.leader == "you":
		return "You're already the high bidder."
	var next: int = int(l.current) + (bid_increment(l) if l.leader != "" else 0)
	if next > money:
		return "You can't cover that bid."
	l.current = next
	l.leader = "you"
	l.my_bid = next
	l.bids = int(l.get("bids", 0)) + 1
	l.watch = true
	# a late bid keeps the lane open a few more seconds so rivals can answer
	l.ends_at = max(float(l.ends_at), auction_clock + 6.0)
	l.next_ai = auction_clock + randf_range(1.0, 3.0)
	_auction_note(l, "You bid %s" % money_str(next))
	return ""


## Buy It Now. Returns "" or why not.
func buy_listing_now(l: Dictionary) -> String:
	if not buy_now_open(l):
		return "Buy It Now is gone: the bidding passed it."
	if cars.size() >= lot_capacity():
		return "Your lot is full. Sell a car first."
	if not spend(int(l.buy_now), "cars"):
		return "Not enough money."
	l.sold = true
	l.winner = "you"
	l.current = int(l.buy_now)
	l.my_bid = int(l.buy_now)
	add_car(l.car, int(l.buy_now))
	return ""


## Advances live auction time: rivals bid at random intervals, lanes close, fresh lanes roll in.
## Returns notes for the player: [{"text", "good"}].
func tick_auctions(dt: float) -> Array:
	auction_clock += dt
	var notes := []
	for l in listings.duplicate():
		if l.sold:
			continue
		if not l.has("ends_at"):
			l.ends_at = auction_clock + randf_range(40.0, 70.0)
			l.next_ai = auction_clock + randf_range(2.0, 5.0)
		var inc := bid_increment(l)
		if auction_clock >= float(l.next_ai) and auction_clock < float(l.ends_at):
			l.next_ai = auction_clock + randf_range(1.5, 5.0)
			var cap := int(l.rival_max)
			if l.leader != "you" and l.leader != "" and randf() < 0.35:
				pass   # rivals sometimes let a bid stand for a while
			elif l.current + inc <= cap:
				var left: float = max(1.0, float(l.ends_at) - auction_clock)
				# bigger jumps early, single increments near the end
				var jump: int = max(inc, int(round((cap - l.current) * randf_range(0.05, 0.3) * min(1.0, left / 30.0) / 100.0)) * 100)
				var was_you: bool = l.leader == "you"
				l.current = int(min(cap, l.current + jump)) if l.leader != "" else int(l.current)
				var names: Array = RIVALS.filter(func(r): return r != l.leader)
				l.leader = names.pick_random()
				l.bids = int(l.get("bids", 0)) + 1
				_auction_note(l, "%s bids %s" % [l.leader, money_str(int(l.current))])
				if float(l.ends_at) - auction_clock < 5.0:
					l.ends_at = auction_clock + 5.0
				if was_you:
					notes.append({"text": "Outbid on the %s: %s now leads at %s." % [l.car.model, l.leader, money_str(int(l.current))], "good": false})
		if auction_clock >= float(l.ends_at):
			notes.append_array(close_auction(l))
	# fresh lanes roll in for the ones that closed
	for house in memberships:
		var open := open_listings(house)
		var used := open.map(func(x): return x.car.model)
		for i in max(0, lane_size(house) - open.size()):
			listings.append(make_listing(house, randf_range(0.0, 6.0), used))
	# closed lots stay visible only if you bid on them (they show in My Bids)
	listings = listings.filter(func(l): return not l.sold or int(l.get("my_bid", 0)) > 0 or l.winner == "you")
	var mine := listings.filter(func(l): return l.sold)
	if mine.size() > 12:
		var drop: Array = mine.slice(0, mine.size() - 12)
		listings = listings.filter(func(l): return not drop.has(l))
	return notes


func close_auction(l: Dictionary) -> Array:
	l.sold = true
	l.winner = l.leader
	if l.winner == "":
		l.winner = "no sale"
		return []
	if l.winner != "you":
		if int(l.get("my_bid", 0)) > 0:
			return [{"text": "%s won the %s for %s." % [l.winner, l.car.model, money_str(int(l.current))], "good": false}]
		return []
	if cars.size() < lot_capacity() and spend(int(l.current), "cars"):
		add_car(l.car, int(l.current))
		return [{"text": "You won the %s for %s! It's on your lot." % [l.car.model, money_str(int(l.current))], "good": true}]
	l.winner = l.rival
	return [{"text": "You couldn't take the %s (no money or no room), so it went to %s." % [l.car.model, l.rival], "good": false}]


## End of the business day: every open lane closes at its current price.
func settle_auctions() -> Array:
	var notes := []
	for l in listings:
		if not l.sold:
			notes.append_array(close_auction(l))
	return notes


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
		log_money("other", 500)
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
		log_money("interest", -b.interest)
		var months := ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
		var prev := date_dict(day - 1)
		last_month_report = {"title": "%s %d" % [months[prev.month - 1], prev.year], "ledger": ledger_month.duplicate(),
			"sold": month_sold, "walked": month_walked, "reputation": reputation, "money": money, "staff": staff.duplicate(true)}
		ledger_month = {}
		month_sold = 0
		month_walked = 0
		notes.append("New month. Paid %s in bills: rent %s, staff %s, advertising %s%s." % [money_str(b.total), money_str(b.rent), money_str(b.salaries), money_str(b.ads),
			", loan interest %s" % money_str(b.interest) if b.interest > 0 else ""])
		if money < 0:
			# TewportBank covers what it can; if even the full credit line can't pay the bills, the dealership closes
			var cover: int = min(-money, loan_limit() - loan)
			if cover > 0:
				loan += cover
				money += cover
				notes.append("We couldn't cover the bills, so TewportBank drew %s from our credit line. We owe %s." % [money_str(cover), money_str(loan)])
			# still short: wholesale the lot to a liquidator at 60% of value, cheapest cars first
			var sorted := cars.duplicate()
			sorted.sort_custom(func(a, b): return value(a) < value(b))
			var dumped := []
			for c in sorted:
				if money >= 0:
					break
				var got := int(value(c) * 0.6)
				money += got
				log_money("sales", got)
				cars.erase(c)
				dumped.append("%s %s" % [c.get("year", ""), c.model])
			if not dumped.is_empty():
				notes.append("BILLS: a liquidator hauled off %s at 60%% of value to pay the bills." % ", ".join(dumped))
			if money < 0:
				bankrupt = {"short": -money, "day": day, "date": date_str()}
				notes.append("BANKRUPT: we're %s short on the bills and the bank won't lend another cent." % money_str(-money))
			last_month_report.money = money
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
	"stats", "seen_intro", "owned", "equipped", "decor_on", "desk_slots", "upgrades", "ads_active", "staff", "candidates", "walkin_schedule",
	"ledger_day", "ledger_month", "month_walked", "month_sold", "liabilities", "reviews", "referrals", "memberships", "apartment", "dealer_name", "tutorial", "dealership",
	"loan", "pending_referrals", "run_id", "peak_worth", "bankrupt", "auction_clock"]


func save_game() -> void:
	update_leaderboard("Closed down" if not bankrupt.is_empty() else "Open")
	var data := {"version": 6}
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
	if typeof(data) != TYPE_DICTIONARY or int(data.get("version", 1)) < 5:   # the economy changed in 5; older saves start over
		return false
	new_game()
	tutorial = TUTORIAL.size()   # saves from before the tutorial existed skip it
	dealership = DEALERSHIPS.size()   # and keep the flagship they already had
	for k in SAVE_KEYS:
		if data.has(k):
			set(k, _fix_ints(data[k]))
	reputation = float(reputation)
	clock = float(clock)
	if int(data.get("version", 1)) < 6:   # 6 put collectibles in desk slots; older saves place what was on the desk
		desk_slots = {}
		for id in decor_on.duplicate():
			auto_place(id)
	return true


# ---------- leaderboard (kept across runs, on this device) ----------

## What the dealership is worth: cash, minus what we owe, plus the cars on the lot.
func net_worth() -> int:
	var w := money - loan
	for c in cars:
		w += value(c)
	return w


func load_leaderboard() -> Array:
	if not FileAccess.file_exists(LEADERBOARD_PATH):
		return []
	var f := FileAccess.open(LEADERBOARD_PATH, FileAccess.READ)
	var data = JSON.parse_string(f.get_as_text()) if f else null
	return _fix_ints(data) if typeof(data) == TYPE_ARRAY else []


## Updates this run's row (best net worth so far, cars sold, how far it got). Top 10 are kept.
func update_leaderboard(status: String) -> void:
	if not seen_intro or run_id == 0:
		return
	peak_worth = max(peak_worth, net_worth())
	var rows := load_leaderboard().filter(func(r): return int(r.get("run", 0)) != run_id)
	rows.append({"run": run_id, "name": dealer_name, "worth": peak_worth, "sold": stats.sold, "days": day,
		"tier": dealership, "level": level, "status": status})
	rows.sort_custom(func(a, b): return a.worth > b.worth)
	var f := FileAccess.open(LEADERBOARD_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(rows.slice(0, 10)))


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
const TWO_DOOR := ["Porsha 911", "Forde Mustank", "Mazdo Miota", "Ferrano 488", "Lamborgo Aventa", "BMV M4"]


func ensure_damage(car: Dictionary) -> void:
	if car.has("damage"):
		return
	var dmg := {}
	var sev: float = 1.0 - car.parts.body / 100.0
	var n := int(round(sev * 9.0 + randf() * 2.0))
	# only panels this body actually has: coupes have no rear doors, pickups have a bed instead of a trunk
	var truck: bool = car.get("cls", "") == "truck"
	var pool := PANELS.filter(func(p):
		if p in ["door_rl", "door_rr"] and car.get("model", "") in TWO_DOOR:
			return false
		if p == "roof" and car.get("model", "") == "Rang Rovah":
			return false   # black roof on that model, not paint
		if p == "bed":
			return truck
		if p == "trunk":
			return not truck
		return true)
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
