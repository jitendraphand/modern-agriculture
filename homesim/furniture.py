"""Procedural furniture, fixtures, clutter, people and pets.

Every builder returns a :class:`~agrifield.plantkit.PlantModel` whose ``meta``
holds ``size`` (w, d, h), ``supports`` (surfaces clutter can be placed on, as
``(x0, y0, x1, y1, z)`` in local coordinates) and optional ``lights``.
Local frame: origin at the centre of the footprint on the floor, the front of
the item faces +y, the back (wall side) is at y = -d/2.
"""

import math

from mathutils import Matrix, Vector

from agrifield import meshkit as mk
from agrifield import props as agri_props
from agrifield.plantkit import PlantModel


def _pm(w, d, h, label):
    pm = PlantModel()
    pm.meta.update(size=(w, d, h), supports=[], label=label, lights=[])
    return pm


def _legs(mb, w, d, h, mat, r=0.02, inset=0.05, round_=True):
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (w / 2 - inset), sy * (d / 2 - inset)
            if round_:
                mk.tube(mb, [Vector((x, y, 0)), Vector((x, y, h))], r, mat, sides=6)
            else:
                mk.box(mb, (x, y, h / 2), (2 * r, 2 * r, h), mat)


# ------------------------------------------------------------------ seating
def sofa(rng, st, seats=3):
    w = 0.75 * seats + 0.3
    d, h = 0.92, 0.85
    pm = _pm(w, d, h, "sofa")
    mb = pm.mb
    m = st["sofa"]
    mk.box(mb, (0, 0, 0.25), (w, d, 0.3), m)
    mk.box(mb, (0, -d / 2 + 0.11, 0.55), (w - 0.1, 0.22, 0.6), m)
    for sx in (-1, 1):
        mk.box(mb, (sx * (w / 2 - 0.1), 0.02, 0.45), (0.2, d - 0.04, 0.4), m)
    cw = (w - 0.4) / seats
    for k in range(seats):
        x = -w / 2 + 0.2 + cw * (k + 0.5)
        mk.box(mb, (x, 0.08, 0.46), (cw - 0.02, d - 0.3, 0.12), m)
    _legs(mb, w - 0.1, d - 0.1, 0.1, st["metal"], r=0.015)
    for k in range(rng.randint(1, 3)):
        x = rng.uniform(-w / 2 + 0.35, w / 2 - 0.35)
        mk.box(mb, (x, -d / 2 + 0.3, 0.68), (0.42, 0.14, 0.4), st["pillow"], yaw=rng.uniform(-0.2, 0.2))
    return pm


def armchair(rng, st):
    pm = _pm(0.85, 0.85, 0.85, "armchair")
    mb = pm.mb
    m = st["sofa"]
    mk.box(mb, (0, 0, 0.25), (0.85, 0.85, 0.3), m)
    mk.box(mb, (0, -0.32, 0.58), (0.8, 0.2, 0.6), m)
    for sx in (-1, 1):
        mk.box(mb, (sx * 0.34, 0.02, 0.48), (0.16, 0.8, 0.38), m)
    mk.box(mb, (0, 0.08, 0.45), (0.52, 0.6, 0.12), m)
    _legs(mb, 0.8, 0.8, 0.1, st["wood"], r=0.02)
    return pm


def chair(rng, st):
    pm = _pm(0.45, 0.5, 0.9, "chair")
    mb = pm.mb
    m = st["chair"]
    _legs(mb, 0.42, 0.44, 0.45, m, r=0.015, inset=0.03)
    mk.box(mb, (0, 0, 0.46), (0.45, 0.46, 0.035), m)
    for sx in (-1, 1):
        mk.box(mb, (sx * 0.19, -0.2, 0.68), (0.03, 0.03, 0.45), m)
    mk.box(mb, (0, -0.2, 0.8), (0.42, 0.025, 0.16), m)
    return pm


def office_chair(rng, st):
    pm = _pm(0.6, 0.6, 1.1, "office_chair")
    mb = pm.mb
    for k in range(5):
        a = 2 * math.pi * k / 5
        mk.tube(mb, [Vector((0, 0, 0.08)), Vector((0.28 * math.cos(a), 0.28 * math.sin(a), 0.05))], 0.015, st["metal"], sides=5)
        mk.ellipsoid(mb, (0.28 * math.cos(a), 0.28 * math.sin(a), 0.03), (0.025, 0.025, 0.025), st["plastic_dark"], u=6, v=4)
    mk.tube(mb, [Vector((0, 0, 0.08)), Vector((0, 0, 0.45))], 0.025, st["metal"], sides=8)
    mk.box(mb, (0, 0, 0.48), (0.5, 0.48, 0.07), st["office_fabric"])
    mk.box(mb, (0, -0.24, 0.8), (0.46, 0.06, 0.55), st["office_fabric"])
    return pm


def stool(rng, st):
    pm = _pm(0.38, 0.38, 0.65, "stool")
    _legs(pm.mb, 0.34, 0.34, 0.63, st["metal"], r=0.012, inset=0.02)
    mk.tube(pm.mb, [Vector((0, 0, 0.62)), Vector((0, 0, 0.66))], 0.18, st["wood"], sides=14, cap_end=True)
    return pm


# ------------------------------------------------------------------- tables
def table(rng, st, w=1.6, d=0.9, h=0.75, label="dining_table", glass=False):
    pm = _pm(w, d, h, label)
    mb = pm.mb
    top = st["glass_top"] if glass else st["table"]
    mk.box(mb, (0, 0, h - 0.02), (w, d, 0.04), top)
    _legs(mb, w, d, h - 0.04, st["table_leg"], r=0.025, inset=0.07, round_=rng.random() < 0.5)
    pm.meta["supports"].append((-w / 2 + 0.05, -d / 2 + 0.05, w / 2 - 0.05, d / 2 - 0.05, h))
    return pm


def coffee_table(rng, st):
    pm = table(rng, st, w=rng.uniform(0.9, 1.2), d=0.6, h=0.42, label="coffee_table", glass=rng.random() < st.get("glass_p", 0.2))
    mk.box(pm.mb, (0, 0, 0.12), (pm.meta["size"][0] - 0.15, 0.5, 0.02), st["table"])
    return pm


def desk(rng, st):
    w = rng.uniform(1.1, 1.5)
    pm = table(rng, st, w=w, d=0.65, h=0.75, label="desk")
    mb = pm.mb
    mk.box(mb, (w / 2 - 0.22, 0, 0.36), (0.4, 0.6, 0.7), st["cabinet"])
    # monitor
    mk.box(mb, (0, -0.2, 0.77), (0.22, 0.16, 0.02), st["plastic_dark"])
    mk.tube(mb, [Vector((0, -0.22, 0.77)), Vector((0, -0.22, 0.95))], 0.015, st["plastic_dark"], sides=5)
    mk.box(mb, (0, -0.2, 1.1), (0.62, 0.03, 0.36), st["screen"])
    mk.box(mb, (0, 0.05, 0.765), (0.45, 0.15, 0.02), st["plastic_dark"])
    pm.meta["supports"] = [(-w / 2 + 0.05, 0.0, w / 2 - 0.45, 0.28, 0.75)]
    return pm


def nightstand(rng, st):
    pm = _pm(0.45, 0.4, 0.55, "nightstand")
    mb = pm.mb
    mk.box(mb, (0, 0, 0.275), (0.45, 0.4, 0.55), st["cabinet"])
    mk.box(mb, (0, 0.201, 0.38), (0.4, 0.005, 0.18), st["cabinet_front"])
    mk.box(mb, (0, 0.201, 0.17), (0.4, 0.005, 0.18), st["cabinet_front"])
    pm.meta["supports"].append((-0.2, -0.15, 0.2, 0.17, 0.55))
    return pm


# ------------------------------------------------------------------ storage
def bookshelf(rng, st, w=None):
    w = w or rng.choice([0.8, 0.9, 1.2])
    d, h = 0.32, rng.uniform(1.6, 2.0)
    pm = _pm(w, d, h, "bookshelf")
    mb = pm.mb
    m = st["shelf"]
    for sx in (-1, 1):
        mk.box(mb, (sx * (w / 2 - 0.01), 0, h / 2), (0.02, d, h), m)
    mk.box(mb, (0, -d / 2 + 0.005, h / 2), (w, 0.01, h), m)
    n = int(h / 0.36)
    for k in range(n + 1):
        z = 0.03 + k * (h - 0.05) / n
        mk.box(mb, (0, 0, z), (w - 0.02, d, 0.02), m)
        if k < n:
            x = -w / 2 + 0.03
            while x < w / 2 - 0.06 and rng.random() < 0.97:
                bw = rng.uniform(0.02, 0.05)
                bh = rng.uniform(0.18, 0.3)
                if rng.random() < 0.08:
                    x += rng.uniform(0.05, 0.2)
                    continue
                mk.box(mb, (x + bw / 2, 0.0, z + 0.01 + bh / 2), (bw, rng.uniform(0.15, 0.24), bh),
                       rng.choice(st["books"]))
                x += bw + 0.002
    pm.meta["supports"].append((-w / 2 + 0.03, -d / 2 + 0.03, w / 2 - 0.03, d / 2 - 0.03, h))
    return pm


def cabinet(rng, st, w=None, h=None, label="cabinet", d=0.45):
    w = w or rng.choice([0.8, 1.0, 1.2])
    h = h or rng.uniform(0.75, 0.95)
    pm = _pm(w, d, h, label)
    mb = pm.mb
    mk.box(mb, (0, 0, h / 2 + 0.04), (w, d, h - 0.08), st["cabinet"])
    mk.box(mb, (0, 0, 0.02), (w - 0.04, d - 0.04, 0.04), st["plastic_dark"])
    ndoor = max(1, int(round(w / 0.45)))
    for k in range(ndoor):
        x = -w / 2 + w / ndoor * (k + 0.5)
        mk.box(mb, (x, d / 2 + 0.005, h / 2 + 0.04), (w / ndoor - 0.01, 0.01, h - 0.1), st["cabinet_front"])
        mk.box(mb, (x + (0.1 if k % 2 else -0.1) * (w / ndoor / 0.45), d / 2 + 0.02, h * 0.7), (0.01, 0.02, 0.12), st["metal"])
    pm.meta["supports"].append((-w / 2 + 0.03, -d / 2 + 0.03, w / 2 - 0.03, d / 2 - 0.03, h))
    return pm


def wardrobe(rng, st):
    w = rng.choice([1.0, 1.2, 1.6])
    pm = cabinet(rng, st, w=w, h=2.05, label="wardrobe", d=0.6)
    pm.meta["supports"] = []
    return pm


def dresser(rng, st):
    pm = cabinet(rng, st, w=rng.choice([0.9, 1.1]), h=0.85, label="dresser", d=0.45)
    return pm


def tv_unit(rng, st):
    w = rng.uniform(1.4, 1.9)
    pm = cabinet(rng, st, w=w, h=0.48, label="tv_unit", d=0.42)
    mb = pm.mb
    tw = min(w - 0.2, rng.choice([1.0, 1.2, 1.4]))
    th = tw * 0.58
    mk.box(mb, (0, -0.05, 0.5), (0.3, 0.2, 0.02), st["plastic_dark"])
    mk.box(mb, (0, -0.08, 0.5 + 0.06 + th / 2), (tw, 0.04, th), st["tv"])
    mk.box(mb, (0, -0.057, 0.5 + 0.06 + th / 2), (tw - 0.03, 0.002, th - 0.03), st["screen"])
    pm.meta["supports"] = [(-w / 2 + 0.03, 0.05, -tw / 2 + 0.25, 0.19, 0.48), (tw / 2 - 0.25, 0.05, w / 2 - 0.03, 0.19, 0.48)]
    pm.meta["parts"] = {"tv": "appliance"}
    return pm


# ------------------------------------------------------------------- beds
def bed(rng, st, double=True):
    w = rng.choice([1.4, 1.6, 1.8]) if double else 0.9
    d, h = 2.05, 0.5
    pm = _pm(w + 0.08, d + 0.05, 1.0, "bed" if double else "single_bed")
    mb = pm.mb
    mk.box(mb, (0, 0, 0.17), (w + 0.08, d, 0.2), st["bed_frame"])
    mk.box(mb, (0, -d / 2 + 0.02, 0.5), (w + 0.08, 0.06, 1.0), st["bed_frame"])
    _legs(mb, w, d - 0.1, 0.07, st["bed_frame"], r=0.03, round_=False)
    mk.box(mb, (0, 0.02, 0.36), (w, d - 0.08, 0.2), st["mattress"])
    npil = 2 if double else 1
    for k in range(npil):
        x = (k - (npil - 1) / 2) * (w / 2)
        mk.ellipsoid(mb, (x, -d / 2 + 0.3, 0.5), (w / (2 * npil) * 0.85, 0.2, 0.07), st["pillow"], u=10, v=5)
    # blanket covering the lower 2/3
    cover = d * rng.uniform(0.55, 0.72)
    mk.box(mb, (0, d / 2 - cover / 2 - 0.02, 0.47), (w + 0.12, cover, 0.04), st["blanket"])
    for sx in (-1, 1):
        mk.box(mb, (sx * (w / 2 + 0.05), d / 2 - cover / 2 - 0.02, 0.33), (0.02, cover, 0.3), st["blanket"])
    pm.meta["supports"].append((-w / 2 + 0.1, 0.0, w / 2 - 0.1, d / 2 - 0.2, 0.49))
    pm.meta["parts"] = {"pillow": "textile", "blanket": "textile"}
    return pm


# ------------------------------------------------------------------ kitchen
def kitchen_run(rng, st, length):
    """Base cabinets + countertop + sink + hob + upper cabinets along a wall."""
    d, h = 0.62, 0.9
    pm = _pm(length, d, 2.2, "kitchen_counter")
    mb = pm.mb
    mk.box(mb, (0, 0, h / 2 + 0.05), (length, d - 0.04, h - 0.1), st["kitchen_cab"])
    mk.box(mb, (0, 0, 0.05), (length - 0.04, d - 0.1, 0.1), st["plastic_dark"])
    n = max(1, int(length / 0.6))
    for k in range(n):
        x = -length / 2 + length / n * (k + 0.5)
        mk.box(mb, (x, d / 2 - 0.015, h / 2 + 0.05), (length / n - 0.01, 0.01, h - 0.12), st["kitchen_front"])
        mk.box(mb, (x, d / 2, h - 0.12), (length / n * 0.5, 0.02, 0.012), st["metal"])
    mk.box(mb, (0, 0.01, h + 0.02), (length, d, 0.04), st["counter"])
    sx = rng.uniform(-length / 2 + 0.5, -0.1) if length > 1.4 else 0.0
    mk.box(mb, (sx, 0.02, h + 0.0), (0.55, 0.42, 0.06), st["sink"])
    mk.tube(mb, [Vector((sx, -0.22, h + 0.04)), Vector((sx, -0.22, h + 0.3)), Vector((sx, -0.08, h + 0.32))],
            0.012, st["metal"], sides=6)
    hx = rng.uniform(0.2, length / 2 - 0.4) if length > 1.6 else None
    if hx is not None:
        mk.box(mb, (hx, 0.02, h + 0.045), (0.6, 0.52, 0.01), st["hob"])
        for ox in (-0.15, 0.15):
            for oy in (-0.12, 0.12):
                mk.disc(mb, (hx + ox, 0.02 + oy, h + 0.051), (0, 0, 1), 0.08, st["plastic_dark"], segs=14)
    # upper cabinets
    if length > 1.2:
        mk.box(mb, (0, -d / 2 + 0.18, 1.85), (length, 0.35, 0.7), st["kitchen_front"])
        for k in range(n):
            x = -length / 2 + length / n * (k + 0.5)
            mk.box(mb, (x, -d / 2 + 0.36, 1.85), (length / n - 0.01, 0.005, 0.66), st["kitchen_cab"])
    sup = []
    x0 = -length / 2 + 0.05
    for cut0, cut1 in sorted([(sx - 0.3, sx + 0.3)] + ([(hx - 0.32, hx + 0.32)] if hx is not None else [])):
        if cut0 - x0 > 0.25:
            sup.append((x0, -0.15, cut0, d / 2 - 0.05, h + 0.04))
        x0 = cut1
    if length / 2 - 0.05 - x0 > 0.25:
        sup.append((x0, -0.15, length / 2 - 0.05, d / 2 - 0.05, h + 0.04))
    pm.meta["supports"] = sup
    pm.meta["parts"] = {"sink": "counter", "hob": "appliance"}
    return pm


def fridge(rng, st):
    pm = _pm(0.7, 0.68, 1.85, "fridge")
    mb = pm.mb
    mk.box(mb, (0, 0, 0.925), (0.7, 0.68, 1.85), st["appliance"])
    mk.box(mb, (0, 0.345, 1.25), (0.68, 0.01, 1.15), st["appliance"])
    mk.box(mb, (0, 0.345, 0.33), (0.68, 0.01, 0.6), st["appliance"])
    for z in (1.2, 0.5):
        mk.box(mb, (0.28, 0.37, z), (0.02, 0.03, 0.3), st["metal"])
    return pm


def washing_machine(rng, st):
    pm = _pm(0.6, 0.6, 0.85, "washing_machine")
    mb = pm.mb
    mk.box(mb, (0, 0, 0.425), (0.6, 0.6, 0.85), st["appliance_white"])
    mk.tube(mb, [Vector((0, 0.3, 0.42)), Vector((0, 0.32, 0.42))], 0.2, st["metal"], sides=20, cap_end=True)
    mk.disc(mb, (0, 0.325, 0.42), (0, 1, 0), 0.16, st["glass_dark"], segs=20)
    pm.meta["supports"].append((-0.27, -0.27, 0.27, 0.27, 0.85))
    return pm


# ----------------------------------------------------------------- bathroom
def toilet(rng, st):
    pm = _pm(0.4, 0.7, 0.8, "toilet")
    mb = pm.mb
    c = st["ceramic"]
    mk.tube(mb, [Vector((0, 0.05, 0)), Vector((0, 0.08, 0.38))], [0.13, 0.17], c, sides=12)
    mk.ellipsoid(mb, (0, 0.1, 0.4), (0.19, 0.24, 0.04), c, u=14, v=5)
    mk.box(mb, (0, -0.27, 0.6), (0.38, 0.16, 0.38), c)
    return pm


def bathtub(rng, st):
    pm = _pm(1.7, 0.75, 0.56, "bathtub")
    mb = pm.mb
    c = st["ceramic"]
    mk.box(mb, (0, 0, 0.28), (1.7, 0.75, 0.56), c)
    mk.box(mb, (0, 0, 0.555), (1.5, 0.58, 0.02), st["glass_dark"])
    return pm


def basin(rng, st):
    pm = _pm(0.65, 0.48, 0.88, "washbasin")
    mb = pm.mb
    mk.box(mb, (0, 0, 0.42), (0.6, 0.45, 0.8), st["cabinet"])
    mk.box(mb, (0, 0.02, 0.86), (0.65, 0.48, 0.06), st["ceramic"])
    mk.tube(mb, [Vector((0, -0.18, 0.88)), Vector((0, -0.18, 1.05)), Vector((0, -0.08, 1.06))], 0.012, st["metal"], sides=6)
    pm.meta["supports"].append((0.16, -0.2, 0.3, 0.2, 0.89))
    pm.meta["parts"] = {"sink": "sanitary"}
    return pm


def shower(rng, st):
    pm = _pm(0.9, 0.9, 2.0, "shower")
    mb = pm.mb
    mk.box(mb, (0, 0, 0.04), (0.9, 0.9, 0.08), st["ceramic"])
    mk.box(mb, (0.44, 0.0, 1.05), (0.01, 0.9, 1.9), st["glass_clear"])
    mk.box(mb, (0.0, 0.44, 1.05), (0.9, 0.01, 1.9), st["glass_clear"])
    mk.tube(mb, [Vector((-0.4, -0.4, 1.0)), Vector((-0.4, -0.4, 2.0)), Vector((-0.25, -0.25, 2.0))], 0.012, st["metal"], sides=6)
    return pm


# ------------------------------------------------------------------- decor
def rug(rng, st, w, d):
    pm = _pm(w, d, 0.012, "rug")
    mk.box(pm.mb, (0, 0, 0.006), (w, d, 0.012), rng.choice(st["rugs"]))
    return pm


def plant(rng, st, big=True):
    h = rng.uniform(0.7, 1.5) if big else rng.uniform(0.25, 0.4)
    r = 0.18 if big else 0.07
    pm = _pm(2 * r + 0.3, 2 * r + 0.3, h, "potted_plant")
    mb = pm.mb
    mk.tube(mb, [Vector((0, 0, 0)), Vector((0, 0, r * 1.6))], [r * 0.8, r], st["pot"], sides=12)
    mk.disc(mb, (0, 0, r * 1.5), (0, 0, 1), r * 0.95, st["pot_soil"], segs=12)
    n = rng.randint(8, 16) if big else rng.randint(5, 9)
    for k in range(n):
        yaw = rng.uniform(0, 6.28)
        L = (h - r * 1.5) * rng.uniform(0.6, 1.0)
        mk.leaf(mb, (0, 0, r * 1.5), yaw, rng.uniform(0.9, 1.4), L, L * rng.uniform(0.15, 0.3), st["plant_leaf"],
                droop=rng.uniform(0.6, 1.4), segs=5, profile="lanceolate", across=3, fold=0.3)
    return pm


def floor_lamp(rng, st):
    pm = _pm(0.4, 0.4, 1.6, "floor_lamp")
    mb = pm.mb
    mk.disc(mb, (0, 0, 0.01), (0, 0, 1), 0.16, st["metal"], segs=14)
    mk.tube(mb, [Vector((0, 0, 0)), Vector((0, 0, 1.45))], 0.012, st["metal"], sides=6)
    mk.tube(mb, [Vector((0, 0, 1.38)), Vector((0, 0, 1.62))], [0.2, 0.13], st["shade"], sides=16)
    pm.meta["lights"].append(((0, 0, 1.5), 60.0, "point"))
    return pm


def table_lamp(rng, st):
    pm = _pm(0.25, 0.25, 0.45, "table_lamp")
    mb = pm.mb
    mk.tube(mb, [Vector((0, 0, 0)), Vector((0, 0, 0.25))], [0.07, 0.04], st["lamp_base"], sides=10)
    mk.tube(mb, [Vector((0, 0, 0.25)), Vector((0, 0, 0.45))], [0.13, 0.09], st["shade"], sides=14)
    pm.meta["lights"].append(((0, 0, 0.33), 20.0, "point"))
    return pm


def ceiling_light(rng, st):
    pm = _pm(0.4, 0.4, 0.08, "ceiling_light")
    mk.ellipsoid(pm.mb, (0, 0, -0.04), (0.2, 0.2, 0.05), st["light_emit"], u=14, v=5)
    return pm


def picture(rng, st, w, h):
    pm = _pm(w, 0.03, h, "picture")
    mk.box(pm.mb, (0, 0, 0), (w, 0.03, h), st["frame"])
    mk.box(pm.mb, (0, 0.016, 0), (w - 0.06, 0.002, h - 0.06), rng.choice(st["art"]))
    return pm


def mirror(rng, st, w=0.6, h=0.8):
    pm = _pm(w, 0.02, h, "mirror")
    mk.box(pm.mb, (0, 0, 0), (w, 0.02, h), st["frame"])
    mk.box(pm.mb, (0, 0.011, 0), (w - 0.04, 0.002, h - 0.04), st["mirror"])
    return pm


def curtain(rng, st, w, h):
    pm = _pm(w, 0.08, h, "curtain")
    pts = []
    n = int(w / 0.06) + 1
    verts = []
    for i in range(n):
        x = -w / 2 + w * i / (n - 1)
        y = 0.03 * math.sin(i * 1.3)
        verts += [(x, y, 0), (x, y, h)]
    faces = [(2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1) for i in range(n - 1)]
    pm.mb.add(verts, faces, st["curtain"])
    _ = pts
    return pm


def stairs(rng, st, w=1.0, steps=12, rise=0.18, run=0.26):
    pm = _pm(w, steps * run, steps * rise, "stairs")
    L = steps * run
    for k in range(steps):
        z = (k + 1) * rise
        mk.box(pm.mb, (0, -L / 2 + run * (k + 0.5), z / 2), (w, run, z), st["stairs"])
    mk.box(pm.mb, (w / 2 + 0.03, 0, steps * rise / 2 + 0.45), (0.04, L, 0.04), st["metal"])
    return pm


# ------------------------------------------------------------------- clutter
SMALL = ["mug", "cup", "bottle", "can", "bowl", "plate", "book", "laptop", "phone", "remote", "toy_block",
         "ball", "teddy", "shoe", "backpack", "laundry_basket", "clothes_pile", "box", "toy_car", "fruit_bowl",
         "vase", "keys", "glasses_case", "game_controller"]


def small_object(rng, st, kind):
    """Graspable clutter.  Returns (pm, semantic_group)."""
    pm = PlantModel()
    mb = pm.mb
    col = rng.choice(st["obj_colors"])
    group = "small_object"
    if kind in ("mug", "cup"):
        r, h = (0.042, 0.095) if kind == "mug" else (0.035, 0.08)
        mk.tube(mb, [Vector((0, 0, 0)), Vector((0, 0, h))], [r * 0.9, r], col, sides=14)
        mk.disc(mb, (0, 0, 0.003), (0, 0, 1), r * 0.9, col, segs=14)
        mk.disc(mb, (0, 0, h - 0.01), (0, 0, 1), r * 0.95, st["liquid"], segs=14)
        if kind == "mug":
            mk.tube(mb, [Vector((r, 0, h * 0.75)), Vector((r + 0.03, 0, h * 0.6)), Vector((r, 0, h * 0.3))], 0.007, col, sides=5)
    elif kind == "bottle":
        h = rng.uniform(0.2, 0.32)
        m = rng.choice([st["glass_green"], st["glass_clear"], col])
        mk.tube(mb, [Vector((0, 0, 0)), Vector((0, 0, h * 0.65)), Vector((0, 0, h * 0.8)), Vector((0, 0, h))],
                [0.035, 0.035, 0.014, 0.013], m, sides=14, cap_end=True)
        mk.disc(mb, (0, 0, 0.002), (0, 0, -1), 0.035, m, segs=14)
    elif kind == "can":
        mk.tube(mb, [Vector((0, 0, 0)), Vector((0, 0, 0.12))], 0.033, col, sides=14, cap_end=True)
    elif kind == "bowl":
        pts = [Vector((0, 0, 0.0)), Vector((0, 0, 0.05)), Vector((0, 0, 0.07))]
        mk.tube(mb, pts, [0.05, 0.08, 0.09], col, sides=16)
        mk.disc(mb, (0, 0, 0.002), (0, 0, 1), 0.05, col, segs=16)
    elif kind == "plate":
        mk.tube(mb, [Vector((0, 0, 0)), Vector((0, 0, 0.02))], [0.09, 0.13], st["ceramic"], sides=20)
        mk.disc(mb, (0, 0, 0.005), (0, 0, 1), 0.09, st["ceramic"], segs=20)
    elif kind == "book":
        mk.box(mb, (0, 0, 0.015 * rng.randint(1, 3)), (0.16, 0.23, 0.03 * rng.randint(1, 2)), rng.choice(st["books"]))
    elif kind == "laptop":
        a = rng.uniform(1.6, 2.0)
        mk.box(mb, (0, 0, 0.01), (0.34, 0.24, 0.02), st["metal"])
        lid = Matrix.Rotation(-(math.pi - a), 3, "X")
        verts = [Vector((x, 0, z)) for z in (0, 0.23) for x in (-0.17, 0.17)]
        verts = [lid @ v + Vector((0, -0.12, 0.02)) for v in verts]
        mb.add(verts, [(0, 1, 3, 2)], st["screen"])
    elif kind == "phone":
        mk.box(mb, (0, 0, 0.005), (0.075, 0.155, 0.009), st["plastic_dark"])
    elif kind == "remote":
        mk.box(mb, (0, 0, 0.012), (0.05, 0.19, 0.022), st["plastic_dark"])
    elif kind == "game_controller":
        mk.ellipsoid(mb, (-0.04, 0, 0.025), (0.05, 0.04, 0.025), st["plastic_dark"], u=10, v=5)
        mk.ellipsoid(mb, (0.04, 0, 0.025), (0.05, 0.04, 0.025), st["plastic_dark"], u=10, v=5)
    elif kind == "toy_block":
        s = rng.uniform(0.04, 0.07)
        for k in range(rng.randint(1, 3)):
            mk.box(mb, (rng.uniform(-.03, .03), rng.uniform(-.03, .03), s / 2 + k * s), (s, s, s), rng.choice(st["toy_colors"]),
                   yaw=rng.uniform(0, 1.5))
    elif kind == "ball":
        r = rng.uniform(0.06, 0.11)
        mk.ellipsoid(mb, (0, 0, r), (r, r, r), rng.choice(st["toy_colors"]), u=14, v=8)
    elif kind == "teddy":
        m = st["fur_light"]
        mk.ellipsoid(mb, (0, 0, 0.1), (0.08, 0.07, 0.1), m, u=10, v=6)
        mk.ellipsoid(mb, (0, 0, 0.24), (0.065, 0.06, 0.06), m, u=10, v=6)
        for sx in (-1, 1):
            mk.ellipsoid(mb, (sx * 0.045, 0, 0.3), (0.022, 0.012, 0.022), m, u=6, v=4)
            mk.ellipsoid(mb, (sx * 0.07, 0.03, 0.04), (0.03, 0.04, 0.03), m, u=6, v=4)
            mk.ellipsoid(mb, (sx * 0.09, 0.0, 0.13), (0.025, 0.025, 0.05), m, u=6, v=4)
    elif kind == "shoe":
        for sx in (-1, 1):
            o = Vector((sx * 0.06 + rng.uniform(-.02, .02), rng.uniform(-.03, .03), 0))
            mk.ellipsoid(mb, o + Vector((0, 0, 0.04)), (0.045, 0.13, 0.045), col, u=10, v=5, squash_top=0.3)
            mk.box(mb, o + Vector((0, 0, 0.008)), (0.09, 0.26, 0.016), st["plastic_dark"])
    elif kind == "backpack":
        mk.box(mb, (0, 0, 0.2), (0.3, 0.15, 0.4), col)
        mk.ellipsoid(mb, (0, 0.08, 0.15), (0.12, 0.05, 0.1), col, u=10, v=5)
        group = "textile"
    elif kind == "laundry_basket":
        mk.tube(mb, [Vector((0, 0, 0)), Vector((0, 0, 0.4))], [0.22, 0.26], st["basket"], sides=16)
        mk.disc(mb, (0, 0, 0.005), (0, 0, 1), 0.22, st["basket"], segs=16)
        for k in range(4):
            mk.ellipsoid(mb, (rng.uniform(-.1, .1), rng.uniform(-.1, .1), 0.33 + 0.03 * k), (0.12, 0.1, 0.05),
                         rng.choice(st["cloth_colors"]), u=8, v=4, jitter=0.2, rng=rng)
    elif kind == "clothes_pile":
        for k in range(rng.randint(2, 5)):
            mk.ellipsoid(mb, (rng.uniform(-.12, .12), rng.uniform(-.12, .12), 0.025 + 0.03 * k),
                         (rng.uniform(0.12, 0.22), rng.uniform(0.1, 0.18), 0.03), rng.choice(st["cloth_colors"]),
                         u=10, v=4, jitter=0.25, rng=rng)
        group = "textile"
    elif kind == "box":
        s = (rng.uniform(0.25, 0.6), rng.uniform(0.25, 0.5), rng.uniform(0.2, 0.45))
        for k in range(rng.randint(1, 2)):
            ss = tuple(v * (0.8 ** k) for v in s)
            mk.box(mb, (rng.uniform(-.03, .03), rng.uniform(-.03, .03), s[2] * sum(0.8 ** j for j in range(k)) + ss[2] / 2),
                   ss, st["cardboard"], yaw=rng.uniform(-0.3, 0.3))
        mk.box(mb, (0, 0, s[2] + 0.001), (s[0] * 0.98, 0.05, 0.002), st["tape"])
        group = "box"
    elif kind == "toy_car":
        mk.box(mb, (0, 0, 0.03), (0.07, 0.15, 0.03), col)
        mk.box(mb, (0, -0.01, 0.055), (0.06, 0.07, 0.025), col)
        for sx in (-1, 1):
            for sy in (-1, 1):
                mk.tube(mb, [Vector((sx * 0.04, sy * 0.05, 0.015)), Vector((sx * 0.03, sy * 0.05, 0.015))], 0.015, st["plastic_dark"], sides=8)
    elif kind == "fruit_bowl":
        mk.tube(mb, [Vector((0, 0, 0)), Vector((0, 0, 0.05)), Vector((0, 0, 0.08))], [0.07, 0.11, 0.13], st["ceramic"], sides=16)
        for k in range(rng.randint(3, 6)):
            a = rng.uniform(0, 6.28)
            mk.ellipsoid(mb, (0.06 * math.cos(a), 0.06 * math.sin(a), 0.08 + 0.02 * (k % 2)), (0.035, 0.035, 0.033),
                         rng.choice(st["fruit_colors"]), u=10, v=6)
    elif kind == "vase":
        h = rng.uniform(0.18, 0.35)
        mk.tube(mb, [Vector((0, 0, 0)), Vector((0, 0, h * 0.4)), Vector((0, 0, h))], [0.05, 0.08, 0.04], col, sides=14)
        mk.disc(mb, (0, 0, 0.002), (0, 0, -1), 0.05, col, segs=14)
        group = "decoration"
    elif kind == "keys":
        mk.tube(mb, [Vector((0, 0, 0.004)), Vector((0.02, 0.005, 0.004))], 0.012, st["metal"], sides=8)
        mk.box(mb, (0.045, 0.0, 0.003), (0.05, 0.012, 0.003), st["metal"])
    elif kind == "glasses_case":
        mk.ellipsoid(mb, (0, 0, 0.02), (0.08, 0.03, 0.02), col, u=10, v=5)
    else:
        raise ValueError(kind)
    lo, hi = mb.bounds()
    pm.meta.update(size=(hi[0] - lo[0], hi[1] - lo[1], hi[2]), label=kind)
    return pm, group


# ------------------------------------------------------------ people & pets
def person(rng, pose):
    return agri_props.person(rng, pose)


def pet(rng, st, kind="dog"):
    pm = PlantModel()
    mb = pm.mb
    m = rng.choice(st["fur"])
    s = rng.uniform(0.8, 1.2) * (1.0 if kind == "dog" else 0.45)
    lying = rng.random() < 0.35
    body_z = 0.42 * s if not lying else 0.15 * s
    mk.ellipsoid(mb, (0, 0, body_z), (0.14 * s, 0.33 * s, 0.14 * s), m, u=12, v=7)
    head = Vector((0, 0.36 * s, body_z + (0.16 * s if not lying else 0.08 * s)))
    mk.ellipsoid(mb, head, (0.1 * s, 0.12 * s, 0.1 * s), m, u=10, v=6)
    mk.ellipsoid(mb, head + Vector((0, 0.11 * s, -0.03 * s)), (0.05 * s, 0.07 * s, 0.045 * s), m, u=8, v=5)
    for sx in (-1, 1):
        mk.ellipsoid(mb, head + Vector((sx * 0.07 * s, -0.02 * s, 0.09 * s)), (0.03 * s, 0.02 * s, 0.06 * s), m, u=6, v=4)
        for sy in (-1, 1):
            top = Vector((sx * 0.08 * s, sy * 0.22 * s, body_z - 0.05 * s))
            foot = Vector((sx * 0.09 * s, sy * 0.22 * s + (0.15 * s if lying else 0), 0.02))
            mk.tube(mb, [top, foot], [0.04 * s, 0.03 * s], m, sides=6)
    mk.tube(mb, [Vector((0, -0.32 * s, body_z + 0.05 * s)), Vector((0, -0.48 * s, body_z + 0.2 * s))], [0.03 * s, 0.012 * s], m, sides=5)
    pm.meta.update(label=kind, size=(0.3 * s, 0.9 * s, body_z + 0.3 * s), pose="lying" if lying else "standing")
    return pm
