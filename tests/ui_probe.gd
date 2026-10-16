extends SceneTree
## Headless UI probe: opens each Office PC site and reports when the browser window outgrows the monitor
## (content under the bezel can't be reached). godot --headless --script res://tests/ui_probe.gd
var m
var frames := 0
var tabs := ["auction", "desk", "showroom", "ads", "staff", "reviews", "bank"]
var ti := 0

func G_():
	return root.get_node("Game")

func _initialize() -> void:
	G_().new_game()
	G_().seen_intro = true
	G_().tutorial = 99
	m = load("res://scenes/main.tscn").instantiate()
	root.size = Vector2i(1280, 720)
	root.add_child(m)

func _process(_d: float) -> bool:
	frames += 1
	if frames == 5:
		m.pc_tab = tabs[ti]
		m.show_screen("pc")
	if frames == 25:
		var st = null
		for c in m.find_children("*", "", true, false):
			if c is PanelContainer and c.clip_contents and c.get_parent() is SceneArt:
				st = c
		if st:
			var r: Rect2 = st.get_parent().monitor_rect
			print("%s: window %s monitor %s %s" % [tabs[ti], st.size, r.size, "OVERFLOW" if st.size.y > r.size.y + 2 else "ok"])
			for sc in st.find_children("*", "ScrollContainer", true, false):
				var ch: Control = sc.get_child(0) if sc.get_child_count() > 0 else null
				if ch:
					var gr: Rect2 = sc.get_global_rect()
					print("   scroll at y %d..%d content %d (min %d) window bottom %d" % [gr.position.y, gr.end.y, ch.size.y, ch.get_combined_minimum_size().y, st.get_global_rect().end.y])
		ti += 1
		frames = 0
		if ti >= tabs.size():
			return true
	return false
