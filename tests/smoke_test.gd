extends SceneTree
## Headless rules smoke test: month ends, save/load round trip, the broke-with-no-cars escape, goals and tutorial.
## godot --headless --script res://tests/smoke_test.gd

var G
var fails := 0


func check(ok: bool, what: String) -> void:
	if not ok:
		fails += 1
		print("FAIL: " + what)


func _initialize() -> void:
	G = root.get_node("Game")
	# every game script must parse (a typo in main.gd otherwise only shows up as a grey screen in the browser)
	for path in ["res://scripts/main.gd", "res://scripts/ui.gd", "res://scripts/car3d_view.gd", "res://scripts/scene_art.gd", "res://scripts/person_art.gd", "res://scripts/car_art.gd", "res://scripts/world_look.gd"]:
		var scr: GDScript = load(path)
		check(scr != null and scr.can_instantiate(), "%s parses" % path)
	G.new_game()
	# month end: bills hit on Nov 1 and the report is filled
	var start: int = G.money
	var bills: int = G.monthly_bills().total
	for i in 30:
		G.end_day()
	check(G.date_dict().day == 31, "day 31 is Oct 31")
	G.end_day()
	check(G.date_dict().day == 1 and G.date_dict().month == 11, "rolled into November")
	check(not G.last_month_report.is_empty(), "month report filled")
	check(G.money == start - bills, "bills charged once (%d vs %d)" % [G.money, start - bills])
	# broke with nothing to sell: the bank gets you moving again
	G.money = -2000
	G.cars = []
	check(G.borrow(G.loan_limit()), "can borrow when broke")
	var cheapest := 1 << 30
	for l in G.listings:
		cheapest = min(cheapest, l.buy_now if l.buy_now > 0 else l.rival_max + 500)
	check(cheapest <= G.money, "a listing is winnable after borrowing (cheapest %d, money %d)" % [cheapest, G.money])
	check(G.monthly_bills().interest > 0, "loan interest billed")
	# live auctions: bid, rivals answer, the high bidder at the bell wins; Buy It Now goes once bidding passes it
	G.money = 500000
	G.cars = []
	var la: Dictionary = G.listings[0]
	check(la.has("ends_at") and float(la.ends_at) > G.auction_clock + 30.0, "listing has a live end time")
	check(G.buy_now_open(la) and la.buy_now >= G.value(la.car) * 0.88 and la.buy_now <= G.value(la.car) * 1.1 + 100, "Buy It Now is priced around retail")
	check(G.place_bid(la) == "" and la.leader == "you", "player bid leads")
	la.rival_max = la.current
	var won := false
	for i in 200:
		for n in G.tick_auctions(1.0):
			won = won or n.good
		if la.sold:
			break
	check(la.sold and la.winner == "you" and won and G.cars.has(la.car), "winning bidder gets the car")
	var lb: Dictionary = G.open_listings("autobidz")[0]
	G.place_bid(lb)
	lb.rival_max = lb.current + 50 * G.bid_increment(lb)
	lb.next_ai = 0.0
	G.tick_auctions(0.1)
	check(lb.leader != "you", "rivals outbid the player")
	G.cars = []
	var lc: Dictionary = {}
	for l in G.open_listings("autobidz"):
		if l != lb and G.buy_now_open(l):
			lc = l
			break
	check(G.buy_listing_now(lc) == "" and lc.winner == "you", "Buy It Now buys instantly")
	G.tick_auctions(0.1)
	check(G.open_listings("autobidz").size() == G.lane_size("autobidz"), "fresh lots roll in")
	var over := 0
	for i in 400:
		var t: Dictionary = G.make_listing("autobidz")
		if t.rival_max > G.value(t.car) * 1.04:
			over += 1
	check(over > 50 and over < 160, "about a quarter of auctions run over value (%d/400)" % over)
	G.money = -2000
	# save / load keeps every field
	G.pending_referrals = 2
	G.upgrades = ["expand1"]
	G.save_game()
	var loan: int = G.loan
	G.new_game()
	check(G.load_game(), "save loads")
	check(G.loan == loan, "loan saved")
	check(G.pending_referrals == 2, "pending referrals saved")
	check(G.lot_capacity() == G.dealership_info().cars + 2, "expansion adds 2 spots")
	for k in G.SAVE_KEYS:
		check(k in G, "save key %s is a real field" % k)
	# goals and tutorial can complete
	G.new_game()
	G.stats.sold = 3
	G.stats.profit = 10000
	G.staff.append(G.candidates[0])
	var ok := true
	for g in G.goals().slice(0, 3):
		ok = ok and g[1]
	check(ok, "corner lot goals can be ticked")
	G.tutorial = 0
	G.add_car(G.listings[0].car, 1000)
	G.check_tutorial()
	G.cars[0].spent = 100
	G.check_tutorial()
	G.check_tutorial()
	G.end_day()
	G.check_tutorial()
	check(not G.tutorial_active(), "tutorial finishes")
	# bills the bank can cover draw on the credit line; bills it can't close the dealership
	# (start from an empty leaderboard: it keeps only the top 10, so earlier runs could push this one out)
	DirAccess.remove_absolute(ProjectSettings.globalize_path(G.LEADERBOARD_PATH))
	G.new_game()
	G.seen_intro = true
	G.money = 1000
	while G.date_dict().day != 1 or G.day == 1:
		G.end_day()
	check(G.bankrupt.is_empty() and G.loan > 0 and G.money >= 0, "bank covers a small shortfall (loan %d)" % G.loan)
	G.money = -200000
	for i in 31:
		if not G.bankrupt.is_empty():
			break
		G.end_day()
	check(not G.bankrupt.is_empty(), "can't pay the bills: dealership closes")
	check(G.load_leaderboard().any(func(r): return int(r.run) == G.run_id and r.status == "Closed down"), "closed run is on the leaderboard")
	G.reset_save()
	check(G.bankrupt.is_empty(), "starting over clears the bankruptcy")
	# repairs on an old runner are priced off its fixed-up value, so they can pay for themselves
	var junk: Dictionary = G.make_car(30000)
	junk.year = 2009
	check(G.repair_cost(junk, G.MECHANICS[0]) < int(junk.base * G.MECHANICS[0].cost), "junker repairs cost less than the new-price formula")
	# late-game fit-outs: the overflow lot adds spots; the closing report has a next-tier hint
	G.dealership = 3
	G.upgrades = ["expand1", "expand2", "expand3"]
	check(G.lot_capacity() == G.dealership_info().cars + 7, "overflow lot adds 3 spots")
	G.dealership = 1
	G.upgrades = []
	G.level = 1
	check(G.next_tier_hint().begins_with("Street Showroom"), "next tier hint names the Street Showroom")
	print("smoke test: %s" % ("OK" if fails == 0 else "%d failures" % fails))
	quit(1 if fails > 0 else 0)
