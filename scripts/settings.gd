extends Node
## Player settings (autoload "Settings"): display mode, vsync, frame cap, volumes and game speed.
## Saved to user://settings.cfg and applied at startup and whenever a value changes.

signal changed

const PATH := "user://settings.cfg"
const VERSION := "0.9.0 beta"
const WINDOW_MODES := ["Windowed", "Fullscreen", "Borderless"]
const FPS_CAPS := [30, 60, 120, 144, 0]   # 0 = unlimited
const SPEEDS := [1.0, 1.5, 2.0]

var window_mode := 0
var vsync := true
var fps_cap := 1        # index into FPS_CAPS
var master := 0.8
var music := 0.6
var sfx := 0.8
var speed := 0          # index into SPEEDS: how fast the in-game clock runs


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for bus in ["Music", "SFX"]:
		if AudioServer.get_bus_index(bus) < 0:
			AudioServer.add_bus()
			var i := AudioServer.bus_count - 1
			AudioServer.set_bus_name(i, bus)
			AudioServer.set_bus_send(i, "Master")
	load_settings()
	apply()


func load_settings() -> void:
	var cf := ConfigFile.new()
	if cf.load(PATH) != OK:
		return
	window_mode = clampi(int(cf.get_value("display", "window_mode", window_mode)), 0, WINDOW_MODES.size() - 1)
	vsync = bool(cf.get_value("display", "vsync", vsync))
	fps_cap = clampi(int(cf.get_value("display", "fps_cap", fps_cap)), 0, FPS_CAPS.size() - 1)
	master = clampf(float(cf.get_value("audio", "master", master)), 0.0, 1.0)
	music = clampf(float(cf.get_value("audio", "music", music)), 0.0, 1.0)
	sfx = clampf(float(cf.get_value("audio", "sfx", sfx)), 0.0, 1.0)
	speed = clampi(int(cf.get_value("game", "speed", speed)), 0, SPEEDS.size() - 1)


func save_settings() -> void:
	var cf := ConfigFile.new()
	cf.set_value("display", "window_mode", window_mode)
	cf.set_value("display", "vsync", vsync)
	cf.set_value("display", "fps_cap", fps_cap)
	cf.set_value("audio", "master", master)
	cf.set_value("audio", "music", music)
	cf.set_value("audio", "sfx", sfx)
	cf.set_value("game", "speed", speed)
	cf.save(PATH)


## Applies every setting and saves. The browser owns the window on the web, so display settings
## only apply to desktop builds.
func apply() -> void:
	if not OS.has_feature("web") and DisplayServer.get_name() != "headless":
		var w := get_window()
		match window_mode:
			1:
				w.mode = Window.MODE_EXCLUSIVE_FULLSCREEN
			2:
				w.mode = Window.MODE_FULLSCREEN
			_:
				if w.mode != Window.MODE_WINDOWED and w.mode != Window.MODE_MAXIMIZED:
					w.mode = Window.MODE_WINDOWED
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED if vsync else DisplayServer.VSYNC_DISABLED)
		Engine.max_fps = FPS_CAPS[fps_cap]
	_set_vol("Master", master)
	_set_vol("Music", music)
	_set_vol("SFX", sfx)
	save_settings()
	changed.emit()


func clock_speed() -> float:
	return SPEEDS[speed]


func is_desktop() -> bool:
	return not OS.has_feature("web") and not OS.has_feature("mobile")


func _set_vol(bus: String, v: float) -> void:
	var i := AudioServer.get_bus_index(bus)
	if i < 0:
		return
	AudioServer.set_bus_mute(i, v <= 0.001)
	AudioServer.set_bus_volume_db(i, linear_to_db(maxf(v, 0.001)))
