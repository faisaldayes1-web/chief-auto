extends SceneTree
## Headless balance check: a careful bot plays a few months with the real Game rules.
## godot --headless --script res://tests/balance_sim.gd -- [days] [runs]
## The sale formulas mirror main.gd (_max_price, _reserve); keep them in sync.

var G


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var days := int(args[0]) if args.size() > 0 else 120
	var runs := int(args[1]) if args.size() > 1 else 10
	G = root.get_node("Game")
	var t2_days := []
	var t3_days := []
	var broke := 0
	for r in runs:
		seed(1000 + r)
		G.new_game()
		G.tutorial = G.TUTORIAL.size()
		var res := _play(days)
		print("run %d: day %d money %s level %d rep %.1f sold %d profit %s tier %d loan %s t2@%s t3@%s min_money %s" % [r, G.day, G.money_str(G.money), G.level,
			G.reputation, G.stats.sold, G.money_str(G.stats.profit), G.dealership, G.money_str(G.loan), res.t2, res.t3, G.money_str(res.low)])
		if res.t2 > 0: t2_days.append(res.t2)
		if res.t3 > 0: t3_days.append(res.t3)
		if res.low < 0: broke += 1
	print("street showroom reached in %d/%d runs, avg day %s" % [t2_days.size(), runs, _avg(t2_days)])
	print("flagship reached in %d/%d runs, avg day %s" % [t3_days.size(), runs, _avg(t3_days)])
	print("runs that went negative: %d" % broke)
	G.reset_save()
	quit()


func _avg(a: Array) -> String:
	if a.is_empty():
		return "-"
	var t := 0.0
	for x in a:
		t += x
	return "%.0f" % (t / a.size())


func _play(days: int) -> Dictionary:
	var out := {"t2": 0, "t3": 0, "low": G.money}
	for d in days:
		_join_houses()
		_buy_cars()
		for car in G.cars:
			_repair(car)
		_sell_day()
		G.end_day()
		out.low = min(out.low, G.money)
		if OS.get_environment("TRACE") != "" and G.day % 3 == 0:
			print("  day %d money %s lvl %d tier %d sold %d profit %s cars %d rep %.1f" % [G.day, G.money_str(G.money), G.level, G.dealership, G.stats.sold, G.money_str(G.stats.profit), G.cars.size(), G.reputation])
		if G.dealership < G.DEALERSHIPS.size() and G.dealership_blocker() == "" and G.money - G.dealership_info(G.dealership + 1).price > 15000:
			G.upgrade_dealership()
			if G.dealership == 2: out.t2 = G.day
			if G.dealership == 3: out.t3 = G.day
	return out


func _join_houses() -> void:
	for a in G.AUCTIONS:
		if not a.id in G.memberships and G.auction_unlocked(a) and G.money > a.fee + 30000:
			G.spend(a.fee, "other")
			G.memberships.append(a.id)


func _buy_cars() -> void:
	var ls: Array = G.listings.duplicate()
	ls.sort_custom(func(a, b): return G.value(a.car) - a.rival_max > G.value(b.car) - b.rival_max)
	for l in ls:
		if G.cars.size() >= G.lot_capacity():
			return
		var v: int = G.value(l.car)
		var my_max := int(v * (G.dealership_info().budget - float(OS.get_environment("MARGIN") if OS.get_environment("MARGIN") != "" else "0.1")))
		var price := 0
		if l.buy_now > 0 and l.buy_now <= my_max:
			price = l.buy_now
		elif l.rival_max < my_max:
			price = max(l.start, l.rival_max + max(100, int(v * 0.03)))
		if price == 0 or price > G.money - 5000:
			continue
		G.spend(price, "cars")
		G.add_car(l.car, price)
		l.sold = true


func _repair(car: Dictionary) -> void:
	var mech: Dictionary = G.MECHANICS[0]
	for m in G.MECHANICS:
		if G.level >= m.level:
			mech = m
	if not car.history_known and G.money > 1000:
		G.spend(150, "repairs")
		car.history_known = true
		G.reveal_faults(car)
	for i in 12:
		var cost: int = max(100, int(round(car.base * mech.cost / 50.0)) * 50)
		var best := ""
		var best_gain := 0.0
		for p in G.PARTS:
			if car.parts[p] >= 100:
				continue
			var before: int = G.value(car, true)
			var old: int = car.parts[p]
			car.parts[p] = min(100, old + (mech.min + mech.max) / 2)
			var gain: float = (G.value(car, true) - before) * 0.85 - cost
			car.parts[p] = old
			if gain > best_gain:
				best_gain = gain
				best = p
		if best == "" or G.money < cost + 3000:
			break
		G.spend(cost, "repairs")
		car.spent += cost
		car.parts[best] = min(100, car.parts[best] + randi_range(mech.min, mech.max))
		if randf() < mech.botch:
			var bad: String = G.PARTS.pick_random()
			car.hidden[bad] = car.hidden.get(bad, 0) + randi_range(10, 20)
	var det: int = max(150, int(round(car.base * 0.004 / 50.0)) * 50)
	if not car.detailed and G.money > det + 2000:
		G.spend(det, "repairs")
		car.spent += det
		car.detailed = true
	car.sticker = int(round(G.sale_value(car) * 1.05 / 100.0)) * 100


func _max_price(c: Dictionary, car: Dictionary, interest: float) -> int:
	var v: float = float(G.value(car, true)) * c.budget
	if car.cls == G.hot_class:
		v *= 1.1
	if G.has_perk("vip") and car.cls in ["sport", "exotic"]:
		v *= 1.1
	return int(round(v * (0.85 + interest / 400.0) / 100.0)) * 100


func _sell_day() -> void:
	var n: int = G.walkin_schedule.size()
	for i in n:
		var c: Dictionary = G.make_customer()
		G.stats.buyers += 1
		var best := {}
		var best_score := -1e9
		for car in G.cars:
			var mp := _max_price(c, car, 50.0)
			if mp < car.sticker * 0.7:
				continue
			var score: float = (30000 if car.cls == c.wants_cls else 0) - abs(car.sticker - mp)
			if score > best_score:
				best_score = score
				best = car
		if best.is_empty():
			G.stats.walked += 1
			continue
		var human := OS.get_environment("HUMAN") != ""
		if human and randf() < 0.35:
			G.stats.walked += 1
			continue
		var car: Dictionary = best
		var fair := float(G.sale_value(car))
		var interest: float = 0.5 * G.condition(car) + (10 if car.detailed else 0) + (5 if G.has_upgrade("lights") else 0) + (10 if G.has_upgrade("turntable") else 0)
		interest -= 40.0 * (car.sticker - fair) / fair
		interest = clamp(interest + 15, 5, 100)   # a couple of pitches
		var price := int(_max_price(c, car, interest) * (0.9 if human else 0.97) / 100) * 100
		var happy: float = 0.6
		var income := {"sales": price}
		if c.finance:
			var tier: Array = G.CREDIT[c.credit]
			var apr: float = tier[1] + (tier[2] - tier[1]) * 0.6
			income.finance = max(0, int(round(price * (apr - tier[1]) / 100.0 * 60 / 12.0 * 0.5 / 10.0)) * 10)
		if randf() < 0.4:
			income.addons = 1200
		var total := 0
		for k in income:
			G.earn(income[k], k)
			total += income[k]
		var profit: int = total - car.paid - car.spent
		if OS.get_environment("SALES") != "" and G.stats.sold < int(OS.get_environment("SALES")):
			print("    sale d%d t%d %s val %s true %s paid %s spent %s price %s fin %s add %s profit %s budget %.2f" % [G.day, G.dealership, car.model, G.value(car), G.value(car, true), car.paid, car.spent, price, income.get("finance", 0), income.get("addons", 0), profit, c.budget])
		G.stats.sold += 1
		G.month_sold += 1
		G.stats.goal_sold_today += 1
		G.stats.profit += profit
		G.add_review(c, G.stars_from_happiness(happy), car.model)
		G.remove_car(car)
		G.add_xp(G.sale_xp(profit))
