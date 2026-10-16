import json, os, subprocess, tempfile
import numpy as np

LANCZOS = "LANCZOS"
_REPLAY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "replay.py")


class Image:
    def __init__(self, tree, size):
        self.tree = tree          # {"new": [mode, size, colour], "ops": [...]} or {"from": tree, "op": ...}
        self.size = tuple(size)
        self._px = None

    def _ops(self):
        return self.tree.setdefault("ops", [])

    def resize(self, size, resample=None):
        return Image({"from": _snap(self), "op": ["resize", list(size)], "ops": []}, size)

    def filter(self, f):
        return Image({"from": _snap(self), "op": ["blur", f.radius], "ops": []}, self.size)

    def alpha_composite(self, other):
        self._ops().append(["composite", _snap(other)])

    def __array__(self, dtype=None, copy=None):
        if self._px is None:
            with tempfile.TemporaryDirectory() as td:
                src, out = os.path.join(td, "t.json"), os.path.join(td, "o.npy")
                json.dump(_snap(self), open(src, "w"))
                subprocess.run(["python3", "-I", _REPLAY, src, out], check=True)
                self._px = np.load(out)
        return self._px.astype(dtype) if dtype is not None else self._px


def _snap(im):
    return json.loads(json.dumps(im.tree))


def new(mode, size, color=0):
    return Image({"new": [mode, list(size), list(color) if isinstance(color, (tuple, list)) else color], "ops": []}, size)
