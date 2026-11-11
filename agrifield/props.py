"""Field infrastructure, obstacles and people."""

import math

from mathutils import Vector

from . import meshkit as mk
from .plantkit import PlantModel


def materials():
    P = lambda a, b=None, sem="obstacle", **kw: dict(kind="plain", color_a=a, color_b=b or a, semantic=sem, **kw)  # noqa: E731
    return {
        "wood": P("#8a6a48", "#6e5236", "structure", roughness=0.85, bump=0.6, bump_scale=30),
        "wood_old": P("#6a5a4a", "#5a4a3a", "structure", roughness=0.9, bump=0.6, bump_scale=30),
        "bamboo": P("#c8b070", "#b8a060", "structure", roughness=0.5),
        "steel": P("#9aa0a4", "#8a9094", "structure", roughness=0.35, metallic=1.0),
        "wire": P("#b0b4b8", sem="structure", roughness=0.3, metallic=1.0),
        "twine": P("#d8d0b0", sem="structure", roughness=0.9),
        "drip_tape": P("#141414", sem="irrigation", roughness=0.4),
        "pvc": P("#e8e8e0", sem="irrigation", roughness=0.4),
        "sprinkler": P("#2a2a2a", "#3a3a3a", "irrigation", roughness=0.4),
        "mulch_black": P("#111111", "#161616", "plastic_mulch", roughness=0.35, coat=0.3, noise_amount=0.04),
        "mulch_white": P("#dcdcd8", sem="plastic_mulch", roughness=0.4, coat=0.2),
        "mulch_silver": P("#a8acb0", sem="plastic_mulch", roughness=0.25, metallic=0.6),
        "rock": P("#7a766e", "#8e8a80", "rock", roughness=0.85, bump=1.0, bump_scale=20, noise_amount=0.2),
        "crate_red": P("#c0281e", sem="obstacle", roughness=0.5),
        "crate_blue": P("#1f4fa8", sem="obstacle", roughness=0.5),
        "crate_green": P("#2a8a3a", sem="obstacle", roughness=0.5),
        "bucket": P("#e8a020", "#e0c020", "obstacle", roughness=0.45),
        "hose": P("#2a6a2a", sem="obstacle", roughness=0.45),
        "tool_metal": P("#6a6e72", sem="obstacle", roughness=0.4, metallic=0.9),
        "skin": P("#c08a6a", "#8a5a3e", "person", roughness=0.5, sss=0.2),
        "cloth_vest": P("#e8f020", "#f07a10", "person", roughness=0.7),
        "cloth_pants": P("#2a3448", "#3a3a3a", "person", roughness=0.85),
        "cloth_shirt": P("#4a6a8a", "#8a4a3a", "person", roughness=0.85),
        "hat": P("#d8c890", "#e8e0d0", "person", roughness=0.8),
        "boots": P("#1a1a1a", "#3a2a1a", "person", roughness=0.6),
        "straw": dict(kind="leaf", color_a="#d8c078", color_b="#c0a862", semantic="residue", roughness=0.7, translucency=0.15),
        "treeline": dict(kind="leaf", color_a="#2f4a25", color_b="#3f5a2a", semantic="background_vegetation", roughness=0.8, translucency=0.1),
        "tree_trunk": P("#3a3028", sem="background_vegetation", roughness=0.9),
    }


def stake(height=1.8, mat="wood"):
    pm = PlantModel()
    mk.box(pm.mb, (0, 0, height / 2 - 0.25), (0.025, 0.025, height), mat)
    return pm


def post(height=2.0, radius=0.05, mat="wood_old"):
    pm = PlantModel()
    mk.tube(pm.mb, [Vector((0, 0, -0.3)), Vector((0, 0, height))], radius, mat, sides=8, cap_end=True)
    return pm


def wire_span(length, heights, mat="wire", sag=0.02, radius=0.0015):
    """Wires along local +y from 0 to ``length`` at the given heights."""
    pm = PlantModel()
    for h in heights:
        pts = []
        for i in range(9):
            t = i / 8
            pts.append(Vector((0, t * length, h - sag * 4 * t * (1 - t))))
        mk.tube(pm.mb, pts, radius, mat, sides=4)
    return pm


def drip_line(length, mat="drip_tape", radius=0.008, rng=None):
    pm = PlantModel()
    pts = []
    n = max(2, int(length / 0.5))
    for i in range(n + 1):
        wob = rng.uniform(-0.015, 0.015) if rng else 0.0
        pts.append(Vector((wob, i * length / n, radius * 0.6)))
    mk.tube(pm.mb, pts, radius, mat, sides=6)
    return pm


def sprinkler(height=0.9):
    pm = PlantModel()
    mk.tube(pm.mb, [Vector((0, 0, -0.1)), Vector((0, 0, height))], 0.012, "pvc", sides=6)
    mk.ellipsoid(pm.mb, (0, 0, height + 0.03), (0.03, 0.03, 0.035), "sprinkler", u=8, v=5)
    mk.tube(pm.mb, [Vector((0, 0, height + 0.04)), Vector((0.08, 0, height + 0.07))], 0.005, "sprinkler", sides=4)
    return pm


def rock_model(rng, size):
    pm = PlantModel()
    mk.rock(pm.mb, (0, 0, size * 0.15), size, "rock", rng)
    return pm


def crate(rng):
    pm = PlantModel()
    mat = rng.choice(["crate_red", "crate_blue", "crate_green"])
    w, d, h = 0.6, 0.4, 0.3
    mb = pm.mb
    mk.box(mb, (0, 0, 0.01), (w, d, 0.02), mat)
    for sx in (-1, 1):
        mk.box(mb, (sx * (w / 2 - 0.01), 0, h / 2), (0.02, d, h), mat)
    for sy in (-1, 1):
        mk.box(mb, (0, sy * (d / 2 - 0.01), h / 2), (w, 0.02, h), mat)
    return pm


def bucket(rng):
    pm = PlantModel()
    pts = [Vector((0, 0, 0.0)), Vector((0, 0, 0.3))]
    mk.tube(pm.mb, pts, [0.12, 0.15], "bucket", sides=14)
    mk.disc(pm.mb, (0, 0, 0.01), (0, 0, 1), 0.12, "bucket", segs=14)
    return pm


def hose(rng, length=4.0):
    pm = PlantModel()
    pts = []
    p = Vector((0, 0, 0.012))
    yaw = rng.uniform(0, 6.28)
    for i in range(40):
        yaw += rng.uniform(-0.5, 0.5)
        p = p + Vector((math.cos(yaw), math.sin(yaw), 0)) * (length / 40)
        pts.append(p.copy())
    mk.tube(pm.mb, pts, 0.012, "hose", sides=6)
    return pm


def tool(rng):
    """A rake / hoe lying on the ground."""
    pm = PlantModel()
    mk.tube(pm.mb, [Vector((-0.7, 0, 0.015)), Vector((0.7, 0, 0.015))], 0.014, "wood", sides=6)
    mk.box(pm.mb, (0.72, 0, 0.03), (0.04, 0.35, 0.05), "tool_metal")
    return pm


def person(rng, pose="standing"):
    """Stylised farm worker (~1.75 m) for safety / people-detection data."""
    pm = PlantModel()
    mb = pm.mb
    h = rng.uniform(1.62, 1.85)
    s = h / 1.75
    bend = pose == "bending"
    crouch = pose == "crouching"
    hip_z = (0.92 if not crouch else 0.45) * s
    # legs
    for side in (-1, 1):
        hip = Vector((0, side * 0.1 * s, hip_z))
        if crouch:
            knee = Vector((0.3 * s, side * 0.13 * s, 0.45 * s))
        else:
            knee = Vector((0.02 * s, side * 0.1 * s, 0.48 * s))
        foot = Vector((0.0, side * 0.11 * s, 0.06 * s))
        mk.tube(mb, [hip, knee, foot], [0.075 * s, 0.06 * s, 0.05 * s], "cloth_pants", sides=8)
        mk.box(mb, foot + Vector((0.05 * s, 0, -0.03 * s)), (0.28 * s, 0.11 * s, 0.1 * s), "boots")
    # torso
    lean = Vector((0.45 * s, 0, -0.05 * s)) if bend else Vector((0.05 * s if crouch else 0, 0, 0))
    chest = Vector((0, 0, hip_z + 0.5 * s)) + lean
    mk.tube(mb, [Vector((0, 0, hip_z - 0.05 * s)), (Vector((0, 0, hip_z)) + chest) / 2, chest],
            [0.16 * s, 0.17 * s, 0.17 * s], "cloth_vest", sides=10)
    shoulder_z = chest
    head = chest + (Vector((0.15 * s, 0, 0.12 * s)) if bend else Vector((0, 0, 0.22 * s)))
    mk.tube(mb, [chest, head - Vector((0, 0, 0.08 * s))], 0.05 * s, "skin", sides=6)
    mk.ellipsoid(mb, head, (0.1 * s, 0.085 * s, 0.115 * s), "skin", u=10, v=7)
    mk.disc(mb, head + Vector((0, 0, 0.07 * s)), (0, 0, 1), 0.2 * s, "hat", segs=14, dome=0.08 * s)
    for side in (-1, 1):
        sh = shoulder_z + Vector((0, side * 0.2 * s, -0.03 * s))
        if bend or crouch:
            hand = sh + Vector((0.3 * s, side * 0.05 * s, -0.5 * s))
            elbow = sh.lerp(hand, 0.5) + Vector((0.05 * s, side * 0.05 * s, 0))
        else:
            elbow = sh + Vector((0.02 * s, side * 0.05 * s, -0.3 * s))
            hand = elbow + Vector((0.12 * s if side > 0 else 0.02 * s, side * 0.02 * s, -0.27 * s))
        mk.tube(mb, [sh, elbow, hand], [0.055 * s, 0.045 * s, 0.04 * s], "cloth_shirt", sides=7)
        mk.ellipsoid(mb, hand, (0.04 * s, 0.03 * s, 0.05 * s), "skin", u=6, v=4)
    pm.meta["height"] = h
    pm.meta["pose"] = pose
    return pm


def straw_patch(rng, size=0.6, density=1.0):
    pm = PlantModel()
    n = int(70 * density)
    for _ in range(n):
        p = Vector((rng.uniform(-size / 2, size / 2), rng.uniform(-size / 2, size / 2), 0.004))
        mk.leaf(pm.mb, p, rng.uniform(0, 6.28), rng.uniform(-0.05, 0.12), rng.uniform(0.06, 0.2), 0.004,
                "straw", droop=0.0, segs=2, profile="strap", across=3, fold=0.6, min_width=0.8)
    return pm


def tree_blob(rng, height):
    """Low-detail background tree for the horizon tree line."""
    pm = PlantModel()
    mk.tube(pm.mb, [Vector((0, 0, 0)), Vector((0, 0, height * 0.45))], height * 0.03, "tree_trunk", sides=5)
    for k in range(rng.randint(3, 6)):
        c = Vector((rng.uniform(-.2, .2) * height, rng.uniform(-.2, .2) * height, height * rng.uniform(0.5, 0.8)))
        r = height * rng.uniform(0.2, 0.33)
        mk.ellipsoid(pm.mb, c, (r, r, r * 0.9), "treeline", u=8, v=6, jitter=0.15, rng=rng)
    return pm

