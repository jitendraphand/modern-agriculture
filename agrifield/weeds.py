"""Procedural weed species (and ground-cover grass) for weeding datasets."""

import math

from mathutils import Vector

from . import meshkit as mk
from . import plantkit as pk
from .plantkit import PlantModel

# size multipliers per weed growth stage
WEED_STAGES = {"cotyledon": 0.25, "small": 0.55, "medium": 1.0, "large": 1.6}

SPECIES = {
    "pigweed": "Amaranthus retroflexus - upright broadleaf, reddish stem",
    "lambsquarters": "Chenopodium album - upright broadleaf, mealy grey-green",
    "crabgrass": "Digitaria sanguinalis - spreading grass clump",
    "dandelion": "Taraxacum officinale - flat rosette, lobed leaves, yellow flower",
    "thistle": "Cirsium arvense - spiny rosette / upright",
    "clover": "Trifolium repens - low creeping trifoliate",
    "nutsedge": "Cyperus esculentus - upright grass-like, glossy",
}


def materials():
    return {
        "weed_pigweed": dict(kind="leaf", color_a="#4c7f2e", color_b="#5a8c35", semantic="weed", roughness=0.45),
        "weed_pigweed_stem": dict(kind="plain", color_a="#9a3a3a", color_b="#7a4a30", semantic="weed"),
        "weed_lambs": dict(kind="leaf", color_a="#7f9a6a", color_b="#8aa878", semantic="weed", roughness=0.7, sheen=0.6),
        "weed_grass": dict(kind="leaf", color_a="#6a9a3a", color_b="#7aaa45", semantic="weed", roughness=0.5),
        "weed_dandelion": dict(kind="leaf", color_a="#4f8a30", color_b="#5a9a3a", semantic="weed", roughness=0.45),
        "weed_flower": dict(kind="plain", color_a="#f8d010", semantic="weed"),
        "weed_thistle": dict(kind="leaf", color_a="#5a7f4a", color_b="#6a8f55", semantic="weed", roughness=0.55),
        "weed_clover": dict(kind="leaf", color_a="#3f7a35", color_b="#4a8a40", semantic="weed", roughness=0.45),
        "weed_sedge": dict(kind="leaf", color_a="#8aaa3a", color_b="#9ab845", semantic="weed", roughness=0.3),
        # ground cover in orchard / vineyard alleys and headlands
        "cover_grass": dict(kind="leaf", color_a="#5a8a35", color_b="#7a9a45", semantic="ground_cover", roughness=0.55),
        "cover_grass_dry": dict(kind="leaf", color_a="#a8a060", color_b="#8a9a50", semantic="ground_cover", roughness=0.7),
    }


def build(species, stage, rng):
    s = WEED_STAGES[stage] * rng.uniform(0.75, 1.25)
    pm = PlantModel()
    mb = pm.mb
    if species in ("pigweed", "lambsquarters"):
        lm = "weed_pigweed" if species == "pigweed" else "weed_lambs"
        sm = "weed_pigweed_stem" if species == "pigweed" else "weed_lambs"
        H = 0.25 * s
        n = max(2, int(4 + 6 * s))
        if s < 0.35:
            for a in (0, math.pi):
                mk.leaf(mb, Vector((0, 0, 0.01)), a + rng.uniform(-.2, .2), 0.4, 0.02, 0.008, lm, droop=0.3, segs=3, profile="lanceolate")
        else:
            pts = [Vector((0, 0, H * i / 4)) for i in range(5)]
            mk.tube(mb, pts, [0.003 * s + 0.001] * 5, sm, sides=4)
            yaw = rng.uniform(0, 6.28)
            for i in range(n):
                t = (i + 0.5) / n
                yaw += 2.4
                p = Vector((0, 0, H * t))
                pet = 0.02 * s
                tip, d = pk.stem_arc(mb, p, yaw, 0.6, pet, 0.3, 0.0012, 0.001, sm, segs=2, sides=3)
                sz = 0.06 * s * (1.1 - 0.5 * t)
                mk.leaf(mb, tip, yaw, 0.3, sz, sz * (0.6 if species == "pigweed" else 0.75), lm, droop=0.5, segs=4,
                        profile="ovate", across=3, fold=0.25, wave=0.06)
            if s > 1.2:
                mk.ellipsoid(mb, Vector((0, 0, H + 0.03)), (0.012, 0.012, 0.05 * s), lm, u=6, v=4)
    elif species in ("crabgrass", "nutsedge"):
        m = "weed_grass" if species == "crabgrass" else "weed_sedge"
        n = int(5 + 12 * s)
        upright = species == "nutsedge"
        pk.grass_blades(mb, rng, (0, 0, 0), n, 0.18 * s + 0.03, 0.005 + 0.002 * s, m,
                        droop=0.6 if upright else 1.5, radius=0.015 * s,
                        elev_range=(1.2, 1.5) if upright else (0.4, 1.0), segs=4)
    elif species in ("dandelion", "thistle"):
        m = "weed_dandelion" if species == "dandelion" else "weed_thistle"
        n = int(5 + 7 * s)
        yaw = rng.uniform(0, 6.28)
        for i in range(n):
            yaw += 2.4
            L_ = (0.06 + 0.09 * s) * rng.uniform(0.8, 1.15)
            mk.leaf(mb, Vector((0, 0, 0.005)), yaw, 0.25 if species == "dandelion" else 0.5, L_,
                    L_ * (0.28 if species == "dandelion" else 0.3), m, droop=0.35, segs=6, profile="lanceolate",
                    across=5, wave=0.5 if species == "thistle" else 0.35, wave_freq=10, fold=0.1)
        if species == "dandelion" and s > 0.9 and rng.random() < 0.6:
            tip, _ = pk.stem_arc(mb, Vector((0, 0, 0)), rng.uniform(0, 6.28), 1.35, 0.12 * s, 0.3, 0.0015, 0.0012, m, segs=3, sides=3)
            mk.ellipsoid(mb, tip, (0.016, 0.016, 0.01), "weed_flower", u=8, v=4)
        if species == "thistle" and s > 1.0:
            pts = [Vector((0, 0, 0)), Vector((0, 0, 0.3 * s))]
            mk.tube(mb, pts, 0.003, m, sides=4)
            for i in range(6):
                mk.leaf(mb, Vector((0, 0, 0.05 * s * (i + 1))), i * 2.4, 0.5, 0.07 * s, 0.02, m, droop=0.4,
                        segs=4, profile="lanceolate", across=5, wave=0.5, wave_freq=10)
    elif species == "clover":
        n = int(3 + 8 * s)
        for i in range(n):
            a = rng.uniform(0, 6.28)
            r = rng.uniform(0, 0.06 * s)
            base = Vector((math.cos(a) * r, math.sin(a) * r, 0.003))
            pk.trifoliate(mb, rng, base, rng.uniform(0, 6.28), 1.2, 0.03 + 0.03 * s, 0.012 + 0.006 * s,
                          0.012 + 0.006 * s, "weed_clover", "weed_clover", petiole_bend=1.2,
                          leaflet_droop=0.2, stem_r=0.0008, profile="round")
    else:
        raise ValueError("unknown weed species %r" % species)
    return pm


def build_cover_patch(rng, size=0.4, density=1.0, dry=False, height=0.12):
    """Square patch of ground-cover grass, used to carpet alleys / headlands."""
    pm = PlantModel()
    m = "cover_grass_dry" if dry else "cover_grass"
    n = int(55 * density)
    for _ in range(n):
        base = Vector((rng.uniform(-size / 2, size / 2), rng.uniform(-size / 2, size / 2), 0))
        mk.leaf(pm.mb, base, rng.uniform(0, 6.28), rng.uniform(0.9, 1.45), height * rng.uniform(0.5, 1.2),
                0.006, m, droop=rng.uniform(0.6, 1.6), segs=3, profile="strap", across=3, fold=0.3)
    return pm
