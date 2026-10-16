extends Node
## Exports the empty showroom hall (no cars or people) to glTF for baking lighting in Blender:
## godot --headless? no: needs a renderer for textures. Run windowed under xvfb:
## godot res://tests/_export_hall.tscn -- out.glb
var n := 0
func _process(_d: float) -> void:
	n += 1
	if n == 3:
		var sr := Showroom3D.new()
		add_child(sr)
		sr.size = Vector2(640, 360)
		var root := Node3D.new()
		root.name = "Showroom"
		for c in sr._vp.get_children():
			if c is MeshInstance3D or (c is Node3D and not (c is Camera3D or c is Light3D or c is WorldEnvironment or c is ReflectionProbe)):
				var d: Node = c.duplicate()
				root.add_child(d)
			elif c is Light3D:
				root.add_child(c.duplicate())
		add_child(root)
		var doc := GLTFDocument.new()
		var st := GLTFState.new()
		var err := doc.append_from_scene(root, st)
		var out: String = OS.get_cmdline_user_args()[0]
		err = doc.write_to_filesystem(st, out)
		print("export ", out, " err=", err, " nodes=", root.get_child_count())
		get_tree().quit()
