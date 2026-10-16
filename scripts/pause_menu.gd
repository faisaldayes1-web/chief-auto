class_name PauseMenu
extends CanvasLayer
## Esc / Menu button: pauses the game over whatever screen is open, with Resume, Settings,
## Save & Quit to Title and Quit to Desktop. From the title screen it opens straight on Settings.

signal quit_to_title

var _root: Control
var _box: VBoxContainer
var in_game := true


func _init() -> void:
	layer = 50
	process_mode = Node.PROCESS_MODE_ALWAYS
	visible = false
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_STOP
	_root.theme = UI.make_theme()
	add_child(_root)
	var shade := ColorRect.new()
	shade.color = Color(0, 0, 0, 0.6)
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.add_child(shade)
	var cc := CenterContainer.new()
	cc.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.add_child(cc)
	var p := UI.panel(Color(0.04, 0.06, 0.1, 0.96), UI.GOLD, 26)
	p.custom_minimum_size = Vector2(460, 0)
	cc.add_child(p)
	_box = UI.vbox(12)
	p.add_child(_box)


func is_open() -> bool:
	return visible


func open(settings_only := false) -> void:
	visible = true
	if in_game:
		get_tree().paused = true
	if settings_only:
		_show_settings()
	else:
		_show_main()


func close() -> void:
	visible = false
	get_tree().paused = false


func _unhandled_input(e: InputEvent) -> void:
	if e.is_action_pressed("ui_cancel"):
		get_viewport().set_input_as_handled()
		if visible:
			close()
		elif in_game:
			open()


func _show_main() -> void:
	UI.clear(_box)
	_box.add_child(UI.header("PAUSED", 30))
	_box.add_child(UI.gold_button("Resume", close, 400))
	_box.add_child(UI.button("Settings", _show_settings, 400))
	_box.add_child(UI.button("Save & Quit to Title", func():
		Game.save_game()
		close()
		quit_to_title.emit(), 400))
	if Settings.is_desktop():
		_box.add_child(UI.button("Save & Quit to Desktop", func():
			Game.save_game()
			get_tree().quit(), 400))
	var note := UI.label("The game saves every night when you close the dealership.", 14, UI.MUTED, false, true)
	note.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_box.add_child(note)
	_box.add_child(_version_label())


func _show_settings() -> void:
	UI.clear(_box)
	_box.add_child(UI.header("SETTINGS", 30))
	if Settings.is_desktop():
		_box.add_child(_choice("Display", Settings.WINDOW_MODES, Settings.window_mode, func(i):
			Settings.window_mode = i
			Settings.apply()))
		var caps: Array = []
		for c in Settings.FPS_CAPS:
			caps.append("Unlimited" if c == 0 else "%d FPS" % c)
		_box.add_child(_choice("Frame cap", caps, Settings.fps_cap, func(i):
			Settings.fps_cap = i
			Settings.apply()))
		_box.add_child(_toggle("V-Sync", Settings.vsync, func(on):
			Settings.vsync = on
			Settings.apply()))
	_box.add_child(_slider("Master volume", Settings.master, func(v):
		Settings.master = v
		Settings.apply()))
	_box.add_child(_slider("Music", Settings.music, func(v):
		Settings.music = v
		Settings.apply()))
	_box.add_child(_slider("Sound effects", Settings.sfx, func(v):
		Settings.sfx = v
		Settings.apply()
		Sfx.play("click")))
	_box.add_child(_choice("Clock speed", ["Normal", "Fast (1.5x)", "Faster (2x)"], Settings.speed, func(i):
		Settings.speed = i
		Settings.apply()))
	_box.add_child(UI.gold_button("Back" if in_game else "Done", _show_main if in_game else close, 400))
	_box.add_child(_version_label())


func _row(name: String) -> HBoxContainer:
	var r := UI.hbox(12)
	var l := UI.label(name, 17)
	l.custom_minimum_size = Vector2(150, 0)
	r.add_child(l)
	return r


func _choice(name: String, opts: Array, sel: int, cb: Callable) -> Control:
	var r := _row(name)
	var ob := OptionButton.new()
	for o in opts:
		ob.add_item(str(o))
	ob.select(sel)
	ob.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	ob.custom_minimum_size = Vector2(0, 40)
	ob.item_selected.connect(cb)
	r.add_child(ob)
	return r


func _toggle(name: String, on: bool, cb: Callable) -> Control:
	var r := _row(name)
	var cb_box := CheckButton.new()
	cb_box.button_pressed = on
	cb_box.toggled.connect(cb)
	r.add_child(cb_box)
	return r


func _slider(name: String, v: float, cb: Callable) -> Control:
	var r := _row(name)
	var s := HSlider.new()
	s.min_value = 0
	s.max_value = 1
	s.step = 0.05
	s.value = v
	s.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	s.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var pct := UI.label("%d%%" % int(v * 100), 15, UI.MUTED)
	pct.custom_minimum_size = Vector2(48, 0)
	s.value_changed.connect(func(x):
		pct.text = "%d%%" % int(x * 100)
		cb.call(x))
	r.add_child(s)
	r.add_child(pct)
	return r


func _version_label() -> Label:
	var l := UI.label("Chief Auto %s" % Settings.VERSION, 12, UI.MUTED)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	return l
