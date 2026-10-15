"""Runs one of the bpy tools inside a Blender binary instead of the pip bpy module:
  blender -b --python tools/bl_run.py -- tools/car_glb_real.py <args...>
"""
import os
import runpy
import sys

try:
    import PIL  # noqa: F401
except ImportError:  # Blender's Python has no Pillow: record draws and replay them in the system python3
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pilshim"))

argv = sys.argv[sys.argv.index("--") + 1:]
sys.argv = argv
runpy.run_path(argv[0], run_name="__main__")
