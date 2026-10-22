extends Node
## Performance benchmark: godot --path . res://tests/perf_bench.tscn -- out.json
## Uncapped (no vsync, no fps cap). Measures startup, each screen switch (the show_screen call itself and
## the worst frame in the next 60), steady frame time over 240 frames per screen, draw calls, memory and nodes.
## Run with APPDATA pointed at a scratch folder so the real save is untouched.
const SCREENS := ["lot", "pc", "garage", "showroom", "marco", "staff", "home", "lot", "pc", "garage", "showroom", "marco", "staff", "home"]
const SETTLE := 60
const SAMPLE := 240

var m: Node
var t0 := 0
var phase := "boot"
var si := 0
var n := 0
var last := 0
var frames: PackedFloat64Array = []
var res := {"screens": []}
var cur := {}

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	Engine.max_fps = 0
	get_tree().create_timer(300.0, true, false, true).timeout.connect(func(): print("bench timeout"); get_tree().quit(2))
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
	print("tex before main %.0f MB" % (Performance.get_monitor(Performance.RENDER_TEXTURE_MEM_USED) / 1048576.0))
	t0 = Time.get_ticks_usec()
	m = load("res://scenes/main.tscn").instantiate()
	add_child(m)
	res.main_instantiate_ms = (Time.get_ticks_usec() - t0) / 1000.0
	res.boot_since_engine_start_ms = Time.get_ticks_msec()

func _process(_d: float) -> void:
	Settings.set("fps_cap", 4)
	Engine.max_fps = 0
	var now := Time.get_ticks_usec()
	var dt := (now - last) / 1000.0 if last > 0 else 0.0
	last = now
	n += 1
	match phase:
		"boot":
			if n == 1:
				return
			frames.append(dt)
			if n in [2, 5, 10, 20, 40, 60, 90, 119]:
				print("boot frame %d dt %.1f tex %.0f MB vram %.0f MB" % [n, dt, Performance.get_monitor(Performance.RENDER_TEXTURE_MEM_USED) / 1048576.0, Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED) / 1048576.0])
			if n >= 120 and Time.get_ticks_msec() - t0 / 1000 >= 1500:   # a player sees the title for a few seconds at least
				res.first_120_frames_worst_ms = _max(frames)
				res.first_120_frames_total_ms = _sum(frames)
				frames = []
				_switch()
		"settle":
			frames.append(dt)
			if frames.size() >= SETTLE:
				cur.settle_worst_ms = _max(frames)
				cur.settle_total_ms = _sum(frames)
				frames = []
				phase = "sample"
		"sample":
			frames.append(dt)
			if frames.size() >= SAMPLE:
				var s := frames.duplicate()
				s.sort()
				cur.avg_ms = _sum(frames) / frames.size()
				cur.p95_ms = s[int(s.size() * 0.95)]
				cur.max_ms = s[s.size() - 1]
				cur.draw_calls = Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)
				cur.objects_in_frame = Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME)
				cur.primitives = Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)
				cur.process_ms = Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0
				cur.static_mem_mb = Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576.0
				cur.vram_mb = Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED) / 1048576.0
				cur.texture_mem_mb = Performance.get_monitor(Performance.RENDER_TEXTURE_MEM_USED) / 1048576.0
				var vps := _viewports(get_tree().root)
				var gpu := RenderingServer.viewport_get_measured_render_time_gpu(get_viewport().get_viewport_rid())
				var cpu := RenderingServer.viewport_get_measured_render_time_cpu(get_viewport().get_viewport_rid())
				var live := []
				for v in vps:
					var sv := v as SubViewport
					if sv.render_target_update_mode != SubViewport.UPDATE_DISABLED:
						gpu += RenderingServer.viewport_get_measured_render_time_gpu(sv.get_viewport_rid())
						cpu += RenderingServer.viewport_get_measured_render_time_cpu(sv.get_viewport_rid())
						live.append("%s:%dx%d:%d" % [sv.name, sv.size.x, sv.size.y, sv.render_target_update_mode])
				cur.render_gpu_ms = gpu
				cur.render_cpu_ms = cpu
				cur.live_subviewports = live
				cur.nodes = Performance.get_monitor(Performance.OBJECT_NODE_COUNT)
				cur.objects = Performance.get_monitor(Performance.OBJECT_COUNT)
				cur.orphans = Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT)
				res.screens.append(cur)
				print(JSON.stringify(cur))
				frames = []
				si += 1
				if si >= SCREENS.size():
					res.total_bench_ms = Time.get_ticks_msec()
					var f := FileAccess.open(OS.get_cmdline_user_args()[0], FileAccess.WRITE)
					f.store_string(JSON.stringify(res, "  "))
					f.close()
					print("bench done")
					get_tree().quit()
					return
				_switch()

func _switch() -> void:
	Game.clock = Game.OPEN_MIN + 120.0
	var name: String = SCREENS[si]
	var a := Time.get_ticks_usec()
	m.show_screen(name)
	RenderingServer.viewport_set_measure_render_time(get_viewport().get_viewport_rid(), true)
	_viewports(get_tree().root)
	cur = {"screen": name, "switch_call_ms": (Time.get_ticks_usec() - a) / 1000.0}
	phase = "settle"

func _viewports(n: Node, out: Array = []) -> Array:
	if n is SubViewport:
		RenderingServer.viewport_set_measure_render_time((n as SubViewport).get_viewport_rid(), true)
		out.append(n)
	for c in n.get_children():
		_viewports(c, out)
	return out

func _sum(a: PackedFloat64Array) -> float:
	var t := 0.0
	for x in a: t += x
	return t

func _max(a: PackedFloat64Array) -> float:
	var t := 0.0
	for x in a: t = max(t, x)
	return t
