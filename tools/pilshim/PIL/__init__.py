"""A stand-in for Pillow inside Blender's Python (which has no Pillow and no pypi here).
Image/ImageDraw calls are recorded; the first pixel read replays them in the system python3 with the real Pillow
(see replay.py). Covers what tools/dealership3d.py uses: new, Draw (polygon/line/ellipse/rectangle), resize,
alpha_composite, filter(GaussianBlur) and numpy.asarray."""
