"""Proximity-weighted skinning for the Marco scan (pose helper used by tools/marco_glb.py)."""
import math
import numpy as np


def _rot(a, b):
    """Rotation matrix turning direction a onto direction b."""
    a = a / np.linalg.norm(a); b = b / np.linalg.norm(b)
    v = np.cross(a, b); c = float(np.dot(a, b)); s = np.linalg.norm(v)
    if s < 1e-9:
        return np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]]) / s
    ang = math.atan2(s, c)
    return np.eye(3) + math.sin(ang) * k + (1 - math.cos(ang)) * k @ k


def _axis_rot(axis, deg):
    axis = np.asarray(axis, float); axis /= np.linalg.norm(axis)
    a = math.radians(deg)
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + math.sin(a) * k + (1 - math.cos(a)) * k @ k


def _ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def _seg(p, a, b):
    d = b - a; L = np.linalg.norm(d); u = d / L
    t = (p - a) @ u
    q = a + np.clip(t, 0, L)[:, None] * u
    return t, np.linalg.norm(p - q, axis=1)


# joints of the scan's A-pose (metres, figure 1.78 m, facing -Y); side s=+1 is +X
def joints(s):
    return (np.array([0.20 * s, 0.055, 1.42]), np.array([0.335 * s, 0.035, 1.10]),
            np.array([0.43 * s, -0.075, 0.90]), np.array([0.45 * s, -0.10, 0.77]))


def arm_weights(co, s):
    S, E, W, T = joints(s)
    tu, ru = _seg(co, S, E); tf, rf = _seg(co, E, W); th, rh = _seg(co, W, T)
    r = np.minimum(np.minimum(ru, rf), rh)
    side = co[:, 0] * s
    w_arm = _ss(-0.05, 0.03, tu) * (1 - _ss(0.075, 0.105, r)) * (side > 0.12)
    w_f = _ss(-0.03, 0.03, tf)
    w_h = _ss(-0.015, 0.02, th)
    return w_arm, w_f, w_h


def pose_arm(co, s, up_dir, fore_dir, hand_dir=None, twist=0.0):
    """Returns the arm chain's posed positions for every vertex and the arm weight."""
    S, E, W, T = joints(s)
    w_arm, w_f, w_h = arm_weights(co, s)
    Ru = _rot(E - S, np.asarray(up_dir, float))
    E2 = Ru @ (E - S) + S
    W1 = Ru @ (W - S) + S
    Rf = _rot(W1 - E2, np.asarray(fore_dir, float))
    if twist:
        Rf = _axis_rot(fore_dir, twist) @ Rf
    W2 = Rf @ (W1 - E2) + E2
    T1 = Rf @ (Ru @ (T - S) + S - E2) + E2
    Rh = _rot(T1 - W2, np.asarray(hand_dir, float)) if hand_dir is not None else np.eye(3)
    pu = (co - S) @ Ru.T + S
    pf = (pu - E2) @ Rf.T + E2
    ph = (pf - W2) @ Rh.T + W2
    p = pu * (1 - w_f)[:, None] + (pf * (1 - w_h)[:, None] + ph * w_h[:, None]) * w_f[:, None]
    return p, w_arm


def pose(co, arms, head_pitch=0.0, head_roll=0.0, head_yaw=0.0):
    """arms: {side: (up_dir, fore_dir, hand_dir)}; head angles in degrees (pitch + = chin up)."""
    out = co.copy()
    # head and neck: a neck pivot with weight ramping over the neck
    P = np.array([0.0, 0.01, 1.47])
    R = _axis_rot((0, 0, 1), head_yaw) @ _axis_rot((0, 1, 0), head_roll) @ _axis_rot((1, 0, 0), -head_pitch)
    wh = _ss(1.44, 1.53, co[:, 2]) * (np.abs(co[:, 0]) < 0.17)
    ph = (co - P) @ R.T + P
    out = out * (1 - wh)[:, None] + ph * wh[:, None]
    for s, dirs in arms.items():
        p, w = pose_arm(co, s, *dirs)
        out = out * (1 - w)[:, None] + p * w[:, None]
    return out


def relaxed(s, out_deg=8.0):
    a = math.radians(out_deg)
    return ((math.sin(a) * s, -0.05, -math.cos(a)),      # upper arm hangs nearly straight down
            (0.03 * s, -0.30, -0.95),                     # forearm a little forward
            (0.0 * s, -0.22, -0.97))


def pocket(s):
    """Hand tucked in the front trouser pocket: elbow out and back, forearm angled in to the hip."""
    a = math.radians(18)
    return ((math.sin(a) * s, 0.34, -math.cos(a)),
            (-0.30 * s, -0.50, -0.81),
            (-0.22 * s, 0.25, -0.94))


def expression(co, mood):
    """Small local deforms on the face (before the head pose): angry lowers and knits the brows, happy lifts
    the mouth corners and cheeks."""
    out = co.copy()
    front = _ss(-0.10, -0.13, co[:, 1])       # front of the face only
    x, z = co[:, 0], co[:, 2]
    if mood == "angry":
        band = _ss(1.652, 1.662, z) * (1 - _ss(1.69, 1.715, z))
        inner = 1 - _ss(0.0, 0.055, np.abs(x))
        w = band * front * (1 - _ss(0.06, 0.075, np.abs(x)))
        out[:, 2] -= w * (0.0025 + 0.005 * inner)
        out[:, 0] -= w * np.sign(x) * 0.0025 * inner
        out[:, 1] -= w * 0.0015 * inner        # the knot of the frown pushes forward
    elif mood == "happy":
        for s in (1, -1):
            d = np.sqrt(((x - 0.026 * s) / 0.016) ** 2 + ((z - 1.552) / 0.012) ** 2)
            w = (1 - _ss(0.3, 1.0, d)) * front
            out[:, 2] += w * 0.004
            out[:, 0] += w * s * 0.0012
            c = np.sqrt(((x - 0.04 * s) / 0.022) ** 2 + ((z - 1.585) / 0.018) ** 2)
            out[:, 1] -= (1 - _ss(0.3, 1.0, c)) * front * 0.0015   # cheeks lift
    return out
