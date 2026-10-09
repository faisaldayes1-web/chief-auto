"""Projects PCH's lanes into each lot render for the passing cars (scripts/main.gd _lot_traffic).

Writes assets/world/road_<view>.json: per lane, points along it as [u, v, ppm] (image fractions, and pixels per metre
as a fraction of the image width), only where the road is in front of the camera and inside the picture.
Usage: /root/bpyenv/bin/python tools/lot_road.py assets/world
"""
import json
import math
import os
import sys

sys.argv, OUT = sys.argv[:1], sys.argv[1]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402
from mathutils import Vector  # noqa: E402

import dealership3d as d3  # noqa: E402

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = 1600, 900
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
pts = d3.pch_points(2.0)
for view in ("lot", "lot_t1", "lot_t2"):
    pos, tgt, lens, _ = d3.VIEWS[view]
    cam.location = pos
    cam.data.lens = lens
    cam.rotation_euler = (Vector(tgt) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    lanes = []
    for off in (5.6, 1.9, -1.9, -5.6):     # northbound (east side) then southbound lanes, metres from the centre
        lane = []
        for i in range(1, len(pts) - 1):
            p, q = pts[i], pts[i + 1]
            t = (q - p).normalized()
            n = Vector((t.y, -t.x, 0))
            w = p + n * off
            a = world_to_camera_view(sc, cam, w)
            b = world_to_camera_view(sc, cam, w + Vector((1, 0, 0)))
            if a.z <= 1 or not (-0.1 < a.x < 1.1 and 0 < a.y < 1):
                continue
            ppm = math.hypot(b.x - a.x, (b.y - a.y) * 900 / 1600)
            lane.append([round(a.x, 4), round(1 - a.y, 4), round(ppm, 5)])
        lanes.append(lane)
    json.dump({"lanes": lanes}, open(os.path.join(OUT, "road_%s.json" % view), "w"))
    print(view, [len(l) for l in lanes])
