extends SceneTree
## Probe: if you pay Marco's max bid and fix to the flip target, what does an average walk-in pay?
func _initialize() -> void:
	var G = root.get_node("Game")
	G.new_game()
	var winnable := 0; var bin_over := 0; var profits := []
	for i in 400:
		var l: Dictionary = G.make_listing("autobidz")
		var car: Dictionary = l.car
		var f: Dictionary = G.flip_estimate(car)
		if l.rival_max < f.max_bid: winnable += 1
		if l.buy_now > f.max_bid: bin_over += 1
		if f.max_bid <= 0: continue
		var mech: Dictionary = G.MECHANICS[0]
		var spent := 0
		for p in G.PARTS:
			while car.parts[p] < G.FLIP_TARGET:
				spent += G.repair_cost(car, mech)
				car.parts[p] = min(100, car.parts[p] + randi_range(mech.min, mech.max))
				if randf() < mech.botch:
					var bad: String = G.PARTS.pick_random()
					car.hidden[bad] = car.hidden.get(bad, 0) + randi_range(10, 20)
		var budget: float = 1.0 * G.dealership_info().budget
		var sell := int(G.value(car, true) * budget * (0.85 + 80 / 400.0))
		profits.append(sell - f.max_bid - spent)
	profits.sort()
	var tot := 0
	for p in profits: tot += p
	print("winnable_under_max %d/400 bin_over_max %d/400 profit avg %d median %d p10 %d" % [winnable, bin_over, tot / profits.size(), profits[profits.size() / 2], profits[profits.size() / 10]])
	quit()
