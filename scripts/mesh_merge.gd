class_name MeshMerge
## Bakes the static primitive props under a node (boxes, cylinders, tori: one MeshInstance3D each) into one
## mesh per material. The garage workshop dressing was ~180 separate draw calls; merged it is a handful.

static func merge(root: Node3D) -> int:
	var groups := {}   # material -> [verts, normals, uvs, indices]
	var gone := []
	for mi in _instances(root):
		var m: Material = mi.material_override
		if m == null or m is ShaderMaterial or mi.mesh == null or not (mi.mesh is PrimitiveMesh):
			continue
		var xf := _local_xf(mi, root)
		# PrimitiveMesh arrays are generated in C++; the transforms below are packed-array ops, so this stays a few ms
		var a: Array = _arrays(mi.mesh as PrimitiveMesh)
		if not groups.has(m):
			groups[m] = [PackedVector3Array(), PackedVector3Array(), PackedVector2Array(), PackedInt32Array()]
		var g: Array = groups[m]
		var base: int = (g[0] as PackedVector3Array).size()
		g[0].append_array(xf * (a[Mesh.ARRAY_VERTEX] as PackedVector3Array))
		var nb := Transform3D(xf.basis.inverse().transposed().orthonormalized(), Vector3.ZERO)
		g[1].append_array(nb * (a[Mesh.ARRAY_NORMAL] as PackedVector3Array))
		g[2].append_array(a[Mesh.ARRAY_TEX_UV] as PackedVector2Array)
		var idx: PackedInt32Array = (a[Mesh.ARRAY_INDEX] as PackedInt32Array).duplicate()
		if base > 0:
			for k in idx.size():
				idx[k] += base
		g[3].append_array(idx)
		gone.append(mi)
	for mi in gone:
		mi.get_parent().remove_child(mi)
		mi.queue_free()
	for m in groups:
		var g: Array = groups[m]
		var arr := []
		arr.resize(Mesh.ARRAY_MAX)
		arr[Mesh.ARRAY_VERTEX] = g[0]
		arr[Mesh.ARRAY_NORMAL] = g[1]
		arr[Mesh.ARRAY_TEX_UV] = g[2]
		arr[Mesh.ARRAY_INDEX] = g[3]
		var am := ArrayMesh.new()
		am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
		var out := MeshInstance3D.new()
		out.mesh = am
		out.material_override = m
		root.add_child(out)
	return gone.size()


## Generating a primitive's arrays costs ~0.3 ms even for a box, and the dressing repeats a few shapes many
## times (drawer seams, pulls, bottles), so arrays are shared per shape.
static var _shape_cache := {}


static func _arrays(pm: PrimitiveMesh) -> Array:
	var key := pm.get_class()
	if pm is BoxMesh:
		key += str((pm as BoxMesh).size)
	elif pm is CylinderMesh:
		var c := pm as CylinderMesh
		key += str([c.top_radius, c.bottom_radius, c.height, c.radial_segments, c.rings])
	elif pm is TorusMesh:
		var t := pm as TorusMesh
		key += str([t.inner_radius, t.outer_radius, t.rings, t.ring_segments])
	else:
		return pm.get_mesh_arrays()
	if not _shape_cache.has(key):
		_shape_cache[key] = pm.get_mesh_arrays()
	return _shape_cache[key]


static func _local_xf(n: Node3D, root: Node3D) -> Transform3D:
	var xf := Transform3D.IDENTITY
	var cur: Node = n
	while cur != null and cur != root:
		if cur is Node3D:
			xf = (cur as Node3D).transform * xf
		cur = cur.get_parent()
	return xf


static func _instances(n: Node, out: Array = []) -> Array:
	for c in n.get_children():
		if c is MeshInstance3D:
			out.append(c)
		_instances(c, out)
	return out
