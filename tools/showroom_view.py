"""Renders the Newport hillside seen through the real-time showroom's glass wall (assets/world/view_hills.jpg).

Builds the same Tewport Beach world as tools/dealership3d.py with every dealership hidden, and looks inland from
standing height on the dealership pad: palms, the villa-covered hillside, a slice of street.
Usage (bpy venv):  python -I tools/showroom_view.py <out_dir>   (PREVIEW=1, SAMPLES as in dealership3d.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402,I001
from mathutils import Vector  # noqa: E402
import dealership3d as d  # noqa: E402

POS = Vector(tuple(float(x) for x in os.environ.get("POS", "-1,4,2.2").split(",")))
TGT = Vector(tuple(float(x) for x in os.environ.get("TGT", "-1,60,7").split(",")))
LENS = float(os.environ.get("LENS", 20))

out = sys.argv[1]
d.build()
cam = d.setup_render()
d.show_sets(set())
d.golden_hour(False)
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = (640, 256) if os.environ.get("PREVIEW") else (2560, 1024)
cam.location = POS
cam.data.lens = LENS
cam.data.clip_end = 5000
cam.rotation_euler = (TGT - POS).to_track_quat("-Z", "Y").to_euler()
sc.view_settings.exposure = -0.4
sc.render.filepath = os.path.join(out, "view_hills.jpg")
bpy.ops.render.render(write_still=True)
