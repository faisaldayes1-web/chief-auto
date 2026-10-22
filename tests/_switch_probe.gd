extends Node
## Per-frame breakdown after each screen switch: frame dt, root-viewport render CPU/GPU, frame setup, and
## script process time. godot --path . res://tests/_switch_probe.tscn
const SCREENS := ["lot", "pc", "garage", "showroom", "lot", "pc", "garage", "showroom"]
var m: Node
var si := -1
var n := 0
var last := 0
var wait := 300

func _ready() -> void:
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	Engine.max_fps = 0
	seed(11)
	Game.new_game()
	Game.seen_intro = true
	Game.tutorial = 99
	Game.level = 6
	Game.money = 180000
	for i in 3:
		var c: Dictionary = Game.make_car(18000 + i * 9000)
		Game.ensure_damage(c)
		Game.cars.append(c)
	m = load("res://scenes/main.tscn").instantiate()
	add_child(m)
	RenderingServer.viewport_set_measure_render_time(get_viewport().get_viewport_rid(), true)
	process_priority = 1000   # run after every other node's _process
	RenderingServer.frame_pre_draw.connect(func(): t_pre = Time.get_ticks_usec())
	RenderingServer.frame_post_draw.connect(func(): t_post = Time.get_ticks_usec())

var t_end := 0
var t_pre := 0
var t_post := 0
var t_start := 0

func _process(_d: float) -> void:
	Engine.max_fps = 0
	var now := Time.get_ticks_usec()
	var dt := (now - last) / 1000.0 if last > 0 else 0.0
	last = now
	n += 1
	var rid := get_viewport().get_viewport_rid()
	if n <= 6 and si >= 0:
		print("  %s f%d flush %.1f draw %.1f | dt %.1f rcpu %.1f rgpu %.1f setup %.1f proc %.1f" % [SCREENS[si], n, (t_pre - t_end) / 1000.0, (t_post - t_pre) / 1000.0, dt,
			RenderingServer.viewport_get_measured_render_time_cpu(rid), RenderingServer.viewport_get_measured_render_time_gpu(rid),
			RenderingServer.get_frame_setup_time_cpu(), Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0])
	if n < wait:
		t_end = Time.get_ticks_usec()
	if n >= wait:
		si += 1
		if si >= SCREENS.size():
			get_tree().quit()
			return
		Game.clock = Game.OPEN_MIN + 120.0
		var a := Time.get_ticks_usec()
		m.show_screen(SCREENS[si])
		print("%s call %.1f" % [SCREENS[si], (Time.get_ticks_usec() - a) / 1000.0])
		n = 0
		wait = 60
	t_end = Time.get_ticks_usec()

func _count(x: Node, cnt: Dictionary) -> void:
	var k := x.get_class()
	if x is Label and (x as Label).autowrap_mode != TextServer.AUTOWRAP_OFF:
		k = "Label(wrap)"
	if x.get_script():
		k += "*"
	cnt[k] = cnt.get(k, 0) + 1
	for c in x.get_children():
		_count(c, cnt)
