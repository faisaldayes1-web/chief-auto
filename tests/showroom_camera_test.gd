extends Node
var failures := 0
func check(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error(label)
func _ready() -> void:
	call_deferred("run")
func run() -> void:
	var view := Car3DView.new()
	add_child(view)
	view._auto_spin = false
	var wheel := InputEventMouseButton.new()
	wheel.pressed = true
	wheel.button_index = MOUSE_BUTTON_WHEEL_UP
	for i in 100:
		view._gui_input(wheel)
	check(is_equal_approx(view._target_dist, view._min_dist), "near clamp")
	wheel.button_index = MOUSE_BUTTON_WHEEL_DOWN
	for i in 100:
		view._gui_input(wheel)
	check(is_equal_approx(view._target_dist, view._max_dist), "far clamp")
	var old_pitch := view.pitch
	view._dragging = true
	var motion := InputEventMouseMotion.new()
	motion.relative = Vector2(100, 100)
	view._gui_input(motion)
	check(view.pitch == old_pitch, "vertical axis locked")
	var before := view.yaw
	view._process(1.0 / 60.0)
	check(view.yaw != before and not is_equal_approx(view.yaw, view._target_yaw), "orbit eases")
	for i in 120:
		view._process(1.0 / 60.0)
	check(absf(angle_difference(view.yaw, view._target_yaw)) < 0.001, "orbit settles")
	check(absf(view.dist - view._target_dist) < 0.001, "zoom settles")
	view.queue_free()
	await get_tree().process_frame
	print("camera checks: ", 6 - failures, "/6")
	get_tree().quit(failures)
