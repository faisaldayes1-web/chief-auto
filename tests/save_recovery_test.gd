extends SceneTree
## Agent: Codex-faisal. Run in a disposable project with custom_user_dir_name
## starting Codex-faisal-save-recovery-. Never run against normal player saves.
var failures := 0
var checks := 0
var game
const PRIMARY := "user://chief_auto_save.json"

func _initialize() -> void:
	call_deferred("run_tests")

func check(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		print("FAIL: ", label)

func write_file(path: String, value: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(value)
	file.close()

func archive_case(label: String) -> void:
	for suffix in ["", ".bak", ".tmp"]:
		if FileAccess.file_exists(PRIMARY + suffix):
			check(DirAccess.rename_absolute(PRIMARY + suffix, PRIMARY + suffix + "." + label) == OK, "archive " + label + suffix)

func run_tests() -> void:
	if not OS.get_user_data_dir().contains("Codex-faisal-save-recovery-"):
		push_error("REFUSED: isolated custom user directory required")
		quit(2)
		return
	if FileAccess.file_exists(PRIMARY) or FileAccess.file_exists(PRIMARY + ".bak"):
		push_error("REFUSED: fresh fixture directory required")
		quit(2)
		return
	game = root.get_node("Game")
	game.set_process(false)
	var backup := JSON.stringify({"version": 7, "money": 77777, "day": 12, "seen_intro": true})
	write_file(PRIMARY + ".bak", backup)
	check(game.load_game(), "backup-only restores")
	check(game.money == 77777 and game.day == 12, "backup-only progression")
	check(FileAccess.get_file_as_string(PRIMARY + ".bak") == backup, "backup bytes preserved")
	archive_case("backup-only")
	write_file(PRIMARY, "broken JSON")
	write_file(PRIMARY + ".bak", backup)
	check(game.load_game() and game.money == 77777, "corrupt primary fallback")
	archive_case("corrupt")
	write_file(PRIMARY, JSON.stringify({"version": 7, "money": 12345, "day": 4}))
	write_file(PRIMARY + ".bak", backup)
	check(game.load_game() and game.money == 12345 and game.day == 4, "valid primary wins")
	archive_case("primary")
	game.money = 999
	check(not game.load_game() and game.money == 999, "missing candidates fail without mutation")
	write_file(PRIMARY, "bad")
	write_file(PRIMARY + ".bak", "also bad")
	check(not game.load_game() and game.money == 999, "corrupt candidates fail without mutation")
	check(FileAccess.get_file_as_string(PRIMARY + ".bak") == "also bad", "failed load preserves backup")
	archive_case("invalid")
	write_file(PRIMARY, JSON.stringify({"version": 5, "clock": 9999, "money": 23456}))
	check(game.load_game() and game.money == 23456 and game.clock == game.CLOSE_MIN - 30.0, "v5 migration retained")
	archive_case("migration")
	game.new_game()
	game.money = 45678
	game.day = 9
	game.save_game()
	game.money = 0
	check(game.load_game() and game.money == 45678 and game.day == 9, "ordinary round trip")
	write_file(PRIMARY + ".bak", backup)
	game.reset_save()
	check(game.money == 15000 and game.day == 1, "reset immediately starts new game")
	game.money = 0
	check(game.load_game() and game.money == 15000 and game.day == 1, "reset persists instead of resurrecting backup")
	check(DirAccess.rename_absolute(PRIMARY, PRIMARY + ".fresh-reset") == OK, "archive fresh reset primary")
	check(game.load_game() and game.money == 15000 and game.day == 1, "missing reset primary recovers fresh run")
	write_file(PRIMARY, "invalid fresh primary")
	check(game.load_game() and game.money == 15000 and game.day == 1, "corrupt reset primary recovers fresh run")
	print("Save recovery: ", checks, " checks, ", failures, " failures")
	quit(1 if failures else 0)
