extends SceneTree
## Pulls the UV2 (lightmap) meshes for the showroom hall out of the Blender bake:
## godot --headless --script res://tests/_extract_bake.gd -- <showroom_hall_uv2.glb>
## Writes res://assets/bake/hall_<i>.res (geometry only) and hall_index.json (glTF node index, origin, size).
const KEEP := [7, 8, 9, 10, 67, 68, 69, 70, 93, 94]

func _init() -> void:
	var src: String = OS.get_cmdline_user_args()[0]
	var doc := GLTFDocument.new()
	var st := GLTFState.new()
	if doc.append_from_file(src, st) != OK:
		print("cannot read ", src)
		quit(1)
		return
	var nodes := st.get_nodes()
	var meshes := st.get_meshes()
	var index := []
	for i in KEEP:
		var gn: GLTFNode = nodes[i]
		var im: ImporterMesh = (meshes[gn.mesh] as GLTFMesh).mesh
		var am := im.get_mesh()
		var out := ArrayMesh.new()
		for s in am.get_surface_count():
			out.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, am.surface_get_arrays(s))
		var path := "res://assets/bake/hall_%d.res" % i
		ResourceSaver.save(out, path, ResourceSaver.FLAG_COMPRESS)
		var ab := out.get_aabb()
		var t: Transform3D = gn.xform
		index.append({"node": i, "res": path, "origin": [t.origin.x, t.origin.y, t.origin.z],
			"size": [ab.size.x, ab.size.y, ab.size.z], "uv2": am.surface_get_format(0) & Mesh.ARRAY_FORMAT_TEX_UV2 != 0})
	var f := FileAccess.open("res://assets/bake/hall_index.json", FileAccess.WRITE)
	f.store_string(JSON.stringify(index, " "))
	print("extracted ", index.size())
	quit()
