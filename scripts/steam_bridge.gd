extends Node
## Steam hookup (autoload "SteamBridge"). Works with or without the GodotSteam GDExtension: drop
## addons/godotsteam into the project (Godot Asset Library, "GodotSteam GDExtension" for 4.3) and the
## desktop build starts Steam and unlocks achievements; without it everything here is a quiet no-op.
## Achievements are also remembered locally (user://achievements.json) so they can be re-sent to Steam.
## API names below must match the achievements created in Steamworks (App Admin > Stats & Achievements).

const LOCAL_PATH := "user://achievements.json"
const ACHIEVEMENTS := {
	"FIRST_CAR": ["First Wheels", "Win your first car at auction."],
	"FIRST_SALE": ["Sold!", "Sell your first car."],
	"BIG_MARGIN": ["Margin Call", "Make $10,000 profit on a single sale."],
	"EXOTIC_SALE": ["Supercar Dealer", "Sell an exotic."],
	"FIVE_STARS": ["Five Stars on Yolp", "Get a 5-star review."],
	"FIRST_HIRE": ["Team Player", "Hire your first salesperson."],
	"LEVEL_5": ["Rising Dealer", "Reach level 5."],
	"LEVEL_10": ["Tewport Legend", "Reach level 10."],
	"TIER_2": ["Moving Up", "Upgrade to the second dealership."],
	"TIER_3": ["Flagship", "Open the flagship dealership."],
	"FIFTY_SALES": ["Volume Dealer", "Sell 50 cars."],
	"MILLIONAIRE": ["Seven Figures", "Have $1,000,000 in the bank."],
	"FIRST_MONTH": ["Open for Business", "Make it to November."],
}

var steam: Object = null
var unlocked := {}
var _t := 0.0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_load_local()
	if Settings.is_desktop() and Engine.has_singleton("Steam"):
		steam = Engine.get_singleton("Steam")
		var r = steam.call("steamInitEx", false) if steam.has_method("steamInitEx") else steam.call("steamInit")
		var ok: bool = (typeof(r) == TYPE_DICTIONARY and int(r.get("status", 1)) == 0) or (typeof(r) == TYPE_BOOL and r)
		if not ok:
			push_warning("Steam not running or app ID missing; achievements stay local")
			steam = null
		else:
			for id in unlocked:
				steam.call("setAchievement", id)   # anything earned offline
			steam.call("storeStats")


func is_steam() -> bool:
	return steam != null


func _process(delta: float) -> void:
	if steam:
		steam.call("run_callbacks")
	_t += delta
	if _t < 2.0:
		return
	_t = 0.0
	# state-based achievements: cheap checks a couple of times a second at most
	if Game.cars.size() > 0 or Game.stats.get("sold", 0) > 0:
		unlock("FIRST_CAR")
	if Game.stats.get("sold", 0) >= 1:
		unlock("FIRST_SALE")
	if Game.stats.get("sold", 0) >= 50:
		unlock("FIFTY_SALES")
	if Game.level >= 5:
		unlock("LEVEL_5")
	if Game.level >= 10:
		unlock("LEVEL_10")
	if Game.dealership >= 2:
		unlock("TIER_2")
	if Game.dealership >= 3:
		unlock("TIER_3")
	if Game.money >= 1000000:
		unlock("MILLIONAIRE")
	if Game.day > 31:
		unlock("FIRST_MONTH")
	if Game.staff.size() > 1:
		unlock("FIRST_HIRE")
	for r in Game.reviews:
		if int(r.get("stars", 0)) >= 5 and int(r.get("day", 0)) > 0:   # day 0 = the starting reviews
			unlock("FIVE_STARS")
			break


## Called by the game when a sale closes.
func on_sale(profit: int, cls: String) -> void:
	if profit >= 10000:
		unlock("BIG_MARGIN")
	if cls == "exotic":
		unlock("EXOTIC_SALE")


func unlock(id: String) -> void:
	if unlocked.has(id) or not ACHIEVEMENTS.has(id):
		return
	unlocked[id] = Time.get_unix_time_from_system()
	_save_local()
	if steam:
		steam.call("setAchievement", id)
		steam.call("storeStats")


func _load_local() -> void:
	if not FileAccess.file_exists(LOCAL_PATH):
		return
	var d = JSON.parse_string(FileAccess.get_file_as_string(LOCAL_PATH))
	if typeof(d) == TYPE_DICTIONARY:
		unlocked = d


func _save_local() -> void:
	var f := FileAccess.open(LOCAL_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(unlocked))
