"""Runs one of the bpy tools inside a Blender binary instead of the pip bpy module:
  blender -b --python tools/bl_run.py -- tools/car_glb_real.py <args...>
"""
import runpy
import sys

argv = sys.argv[sys.argv.index("--") + 1:]
sys.argv = argv
runpy.run_path(argv[0], run_name="__main__")
