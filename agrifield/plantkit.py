"""Reusable plant organs built on top of :mod:`meshkit`."""

import math

from mathutils import Matrix, Vector

from . import meshkit as mk


class PlantModel:
    """Geometry of one plant variant plus point annotations.

    ``fruits`` holds harvestable organs in the plant's local frame:
    ``{"pos": (x, y, z), "radius": r, "kind": str, "ripeness": 0..1}``.
    """

    def __init__(self):
        self.mb = mk.MeshBuilder()
        self.fruits = []
        self.meta = {}

    def add_fruit(self, pos, radius, kind, ripeness=None, **extra):
        f = {"pos": [round(float(c), 4) for c in pos], "radius": round(float(radius), 4), "kind": kind}
        if ripeness is not None:
            f["ripeness"] = round(float(ripeness), 3)
        f.update(extra)
        self.fruits.append(f)


def stem_arc(mb, base, yaw, elev, length, bend, r0, r1, mat, segs=4, sides=5):
    pts = mk.polyline_arc(base, yaw, elev, length, bend, segs)
    radii = [r0 + (r1 - r0) * i / segs for i in range(segs + 1)]
    mk.tube(mb, pts, radii, mat, sides=sides)
    tip = pts[-1]
    d = (pts[-1] - pts[-2]).normalized()
    return tip, d


def dir_to_yaw_elev(d):
    d = Vector(d).normalized()
    return math.atan2(d.y, d.x), math.asin(max(-1.0, min(1.0, d.z)))


def trifoliate(mb, rng, base, yaw, elev, petiole, leaflet_len, leaflet_w, leaf_mat, stem_mat,
               petiole_bend=0.4, leaflet_droop=0.5, spread=0.95, stem_r=0.0015, wave=0.0,
               profile="ovate"):
    tip, d = stem_arc(mb, base, yaw, elev, petiole, petiole_bend, stem_r, stem_r * 0.7, stem_mat, segs=3, sides=4)
    y0, e0 = dir_to_yaw_elev(d)
    e0 = max(-0.3, min(0.5, e0 * 0.4))
    for k, a in enumerate((0.0, spread, -spread)):
        L = leaflet_len * (1.0 if k == 0 else 0.85) * rng.uniform(0.9, 1.1)
        mk.leaf(mb, tip, y0 + a + rng.uniform(-0.12, 0.12), e0 - (0.0 if k == 0 else 0.15),
                L, leaflet_w * L / leaflet_len, leaf_mat, droop=leaflet_droop, segs=4,
                profile=profile, across=3, fold=0.25, wave=wave, phase=rng.uniform(0, 6))
    return tip


def pinnate(mb, rng, base, yaw, elev, rachis, pairs, leaflet_len, leaflet_w, leaf_mat, stem_mat,
            bend=0.8, leaflet_droop=0.5, stem_r=0.002, terminal=True, wave=0.0, profile="ovate",
            minor=0):
    """Compound leaf (tomato, potato, carrot-like when leaflets are thin)."""
    segs = max(3, pairs * 2)
    pts = mk.polyline_arc(base, yaw, elev, rachis, bend, segs)
    radii = [stem_r * (1.0 - 0.6 * i / segs) for i in range(segs + 1)]
    mk.tube(mb, pts, radii, stem_mat, sides=4)
    for p in range(pairs):
        t = (p + 1) / (pairs + 1)
        idx = min(segs - 1, int(t * segs))
        pos = pts[idx].lerp(pts[idx + 1], t * segs - idx)
        d = (pts[idx + 1] - pts[idx]).normalized()
        ry, re = dir_to_yaw_elev(d)
        scale = 1.0 - 0.35 * abs(t - 0.6)
        for side in (1, -1):
            L = leaflet_len * scale * rng.uniform(0.85, 1.1)
            mk.leaf(mb, pos, ry + side * rng.uniform(1.0, 1.35), re * 0.3 + rng.uniform(-0.1, 0.25),
                    L, leaflet_w * L / leaflet_len, leaf_mat, droop=leaflet_droop, segs=3,
                    profile=profile, across=3, fold=0.2, wave=wave, phase=rng.uniform(0, 6))
            for m in range(minor):
                mpos = pos.lerp(pts[min(segs, idx + 1)], 0.5)
                mk.leaf(mb, mpos, ry + side * rng.uniform(0.9, 1.5), re * 0.3,
                        L * 0.4, leaflet_w * 0.4, leaf_mat, droop=0.3, segs=2, profile=profile, across=3)
    if terminal:
        d = (pts[-1] - pts[-2]).normalized()
        ry, re = dir_to_yaw_elev(d)
        mk.leaf(mb, pts[-1], ry, re * 0.5, leaflet_len * 1.1, leaflet_w * 1.1, leaf_mat,
                droop=leaflet_droop, segs=4, profile=profile, across=3, fold=0.2, wave=wave)
    return pts[-1]


def palmate(mb, rng, base, yaw, elev, petiole, size, leaf_mat, stem_mat, lobes=5, spread=1.3,
            stem_r=0.003, petiole_bend=0.6, blade_elev=0.15, droop=0.45, cup=0.0, wave=0.0,
            profile="ovate"):
    """Lobed leaf (grape, cotton, pumpkin, squash) as a fan of overlapping lobes."""
    tip, d = stem_arc(mb, base, yaw, elev, petiole, petiole_bend, stem_r, stem_r * 0.7, stem_mat,
                      segs=3, sides=4)
    y0, _ = dir_to_yaw_elev(d)
    for k in range(lobes):
        a = 0.0 if lobes == 1 else (k / (lobes - 1) - 0.5) * 2 * spread
        L = size * (1.0 - 0.28 * abs(a) / max(spread, 1e-3)) * rng.uniform(0.92, 1.05)
        mk.leaf(mb, tip, y0 + a, blade_elev - 0.2 * abs(a), L, L * 0.75, leaf_mat, droop=droop,
                segs=4, profile=profile, across=5, fold=0.1, cup=cup, wave=wave,
                phase=rng.uniform(0, 6))
    return tip


def flower(mb, center, normal, radius, petal_mat, center_mat, petals=5, segs=2):
    normal = Vector(normal).normalized()
    a = mk._perp(normal)
    b = normal.cross(a)
    for k in range(petals):
        ang = 2 * math.pi * k / petals
        d = a * math.cos(ang) + b * math.sin(ang)
        yaw, elev = dir_to_yaw_elev(d + normal * 0.35)
        mk.leaf(mb, center, yaw, elev, radius, radius * 0.7, petal_mat, droop=0.25, segs=segs,
                profile="obovate", across=3, fold=0.0)
    if center_mat:
        mk.ellipsoid(mb, Vector(center) + normal * radius * 0.08, (radius * 0.28,) * 3, center_mat, u=6, v=4)


def berry_cluster(mb, rng, top, length, width, berry_r, mat, stem_mat=None, density=1.0):
    """Grape-style conical cluster of small spheres hanging below ``top``."""
    top = Vector(top)
    n = int(max(8, 60 * density * (length / 0.14) * (width / 0.06)))
    centers = []
    for _ in range(n):
        t = rng.random() ** 0.8
        r = width * (1.0 - 0.75 * t) * math.sqrt(rng.random())
        a = rng.uniform(0, 2 * math.pi)
        centers.append(top + Vector((r * math.cos(a), r * math.sin(a), -t * length)))
    for c in centers:
        mk.ellipsoid(mb, c, (berry_r, berry_r, berry_r * 1.1), mat, u=6, v=4)
    if stem_mat:
        mk.tube(mb, [top + Vector((0, 0, 0.03)), top - Vector((0, 0, length * 0.6))], [0.002, 0.0015], stem_mat, sides=4)
    return n


def grass_blades(mb, rng, base, n, length, width, mat, spread=0.6, droop=1.0, radius=0.0,
                 elev_range=(0.9, 1.45), segs=4, profile="strap"):
    for _ in range(n):
        a = rng.uniform(0, 2 * math.pi)
        r = radius * math.sqrt(rng.random())
        p = Vector(base) + Vector((r * math.cos(a), r * math.sin(a), 0))
        e = rng.uniform(*elev_range) - spread * rng.random() * 0.5
        L = length * rng.uniform(0.6, 1.1)
        mk.leaf(mb, p, a, e, L, width * rng.uniform(0.8, 1.2), mat, droop=droop * rng.uniform(0.5, 1.3),
                segs=segs, profile=profile, across=3, fold=0.3)


def rot_z(angle):
    return Matrix.Rotation(angle, 3, "Z")
