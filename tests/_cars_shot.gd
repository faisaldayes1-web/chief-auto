extends Node
## Close-up sheet of every garage car model: godot res://tests/_cars_shot.tscn -- out_dir [model_index]
## Each car is shown clean (detailed, no damage) from the front three-quarter, then saved as <out>/car_<i>.png.
var n := 0
var v: Car3DView
var i := 0
var only := -1
func _ready() -> void:
	var a := OS.get_cmdline_user_args()
	if a.size() > 1:
		only = int(a[1])
		i = only
func _process(_d: float) -> void:
	n += 1
	var out: String = OS.get_cmdline_user_args()[0]
	if n == 3:
		_show()
	if n == 60:
		get_viewport().get_texture().get_image().save_png("%s/car_%02d.png" % [out, i])
		i += 1
		if only >= 0 or i >= Game.MODELS.size():
			print("saved cars")
			get_tree().quit()
			return
		v.queue_free()
		n = 2
func _show() -> void:
	seed(3 + i)
	var car: Dictionary = Game.make_car(1000000)
	car.model = Game.MODELS[i][0]
	car.base = Game.MODELS[i][2]
	car.cls = Game.MODELS[i][1]
	car.detailed = true
	for p in car.parts:
		car.parts[p] = 95
	car.hidden = {}
	car.erase("damage")
	Game.ensure_damage(car)
	car.damage = {}
	v = Car3DView.new()
	v._auto_spin = false
	add_child(v)
	v.size = Vector2(1280, 720)
	v.set_car(car)
	v.yaw = 0.75
	v.pitch = 0.16
	v.dist = 6.2
	v._place_camera()
	var hide := OS.get_environment("HIDE_PART")
	if hide != "" and v._meshes.has(hide):
		v._meshes[hide].visible = false
