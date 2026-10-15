def _pts(xy):
    return [[float(v) for v in p] if isinstance(p, (tuple, list)) else float(p) for p in xy]


class Draw:
    def __init__(self, im):
        self.im = im

    def _rec(self, name, xy, kw):
        self.im._ops().append(["draw", name, _pts(xy), {k: (list(v) if isinstance(v, tuple) else v) for k, v in kw.items()}])

    def polygon(self, xy, **kw):
        self._rec("polygon", xy, kw)

    def line(self, xy, **kw):
        self._rec("line", xy, kw)

    def ellipse(self, xy, **kw):
        self._rec("ellipse", xy, kw)

    def rectangle(self, xy, **kw):
        self._rec("rectangle", xy, kw)
