"""Procedural crop models with growth stages.

Each crop is a :class:`Crop` subclass registered in :data:`CROPS`.  A crop
declares its growth stages (with BBCH-style codes), default field layout,
material specs, and a ``build(stage, rng, opts)`` method that returns a
:class:`~agrifield.plantkit.PlantModel` in local coordinates (origin on the
soil surface, z up).  The scene builder creates several random variants per
crop/stage and instances them across the field.
"""

import math

from mathutils import Matrix, Vector

from . import meshkit as mk
from . import plantkit as pk
from .plantkit import PlantModel

CROPS = {}


def register(cls):
    CROPS[cls.name] = cls()
    return cls


class Crop:
    name = ""
    display = ""
    stages = {}
    # unit: plant | segment (dense row segment, e.g. cereals) | hill (rice clump)
    layout = dict(row_spacing=0.75, plant_spacing=0.2, unit="plant")
    variants = 6
    record_fruits = True

    def stage_info(self, stage):
        if stage not in self.stages:
            raise ValueError("crop %s has no stage %r (choose from %s)" % (self.name, stage, list(self.stages)))
        return self.stages[stage]

    def materials(self, stage, opts):
        return {}

    def build(self, stage, rng, opts):
        raise NotImplementedError


def L(color_a, color_b=None, **kw):
    d = dict(kind="leaf", color_a=color_a, color_b=color_b or color_a)
    d.update(kw)
    return d


def P(color_a, color_b=None, semantic="crop_stem", **kw):
    d = dict(kind="plain", color_a=color_a, color_b=color_b or color_a, semantic=semantic)
    d.update(kw)
    return d


# ===================================================================== corn
@register
class Corn(Crop):
    name = "corn"
    display = "Maize / corn"
    stages = {
        "V2": dict(bbch="12", desc="two collared leaves, ~10 cm", n=3, stalk=0.02, leaf=0.16, w=0.022),
        "V6": dict(bbch="16", desc="six leaves, knee high, ~55 cm", n=7, stalk=0.18, leaf=0.55, w=0.055),
        "V12": dict(bbch="32", desc="twelve leaves, rapid growth, ~1.5 m", n=13, stalk=1.05, leaf=0.85, w=0.085),
        "VT": dict(bbch="65", desc="tasseling / silking, ~2.3 m", n=16, stalk=1.95, leaf=0.9, w=0.09),
        "R6": dict(bbch="89", desc="physiological maturity, dry stalks and ears", n=15, stalk=1.9, leaf=0.8, w=0.08),
    }
    layout = dict(row_spacing=0.76, plant_spacing=0.18, unit="plant")

    def materials(self, stage, opts):
        return {
            "corn_leaf": L("#4f7d2a", "#3d6b22", roughness=0.45),
            "corn_leaf_dry": L("#b8a070", "#9c8358", roughness=0.7, translucency=0.15),
            "corn_stalk": P("#6f9440", "#5e8236", roughness=0.5),
            "corn_stalk_dry": P("#c4ab7c", "#b39a6a", roughness=0.7),
            "corn_tassel": P("#cdb978", "#b8a060", semantic="crop_flower", roughness=0.7),
            "corn_ear": P("#86a44c", "#7a9840", semantic="crop_produce", roughness=0.55),
            "corn_ear_dry": P("#d6c08e", "#c7ad78", semantic="crop_produce", roughness=0.75),
            "corn_silk": P("#8c5a2e", semantic="crop_flower", roughness=0.8),
        }

    def build(self, stage, rng, opts):
        s = self.stage_info(stage)
        pm = PlantModel()
        mb = pm.mb
        dry = stage == "R6"
        leaf_m = "corn_leaf_dry" if dry else "corn_leaf"
        stalk_m = "corn_stalk_dry" if dry else "corn_stalk"
        n = s["n"] + rng.randint(-1, 1)
        stalk_h = s["stalk"] * rng.uniform(0.85, 1.12)
        r0 = 0.004 + 0.012 * min(1.0, stalk_h / 1.5)
        lean = Vector((rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03), 0)) * stalk_h
        pts = [Vector((0, 0, 0)) + lean * (i / 5) ** 2 + Vector((0, 0, stalk_h * i / 5 + 0.01)) for i in range(6)]
        mk.tube(mb, pts, [r0 * (1.0 - 0.45 * i / 5) for i in range(6)], stalk_m, sides=6)
        yaw0 = rng.uniform(0, 2 * math.pi)
        for i in range(n):
            t = i / max(1, n - 1)
            z = stalk_h * (0.08 + 0.92 * t ** 1.15) if stalk_h > 0.1 else stalk_h + 0.01 * i
            base = Vector((0, 0, z)) + lean * t ** 2
            if s["n"] <= 3:
                length = s["leaf"] * (0.55 + 0.45 * t)
            else:
                length = s["leaf"] * (0.45 + 0.55 * math.sin(math.pi * (0.2 + 0.65 * t)))
            if stage in ("V6", "V12") and t > 0.75:
                length *= 1.0 - 1.4 * (t - 0.75)  # whorl leaves still emerging
            length *= rng.uniform(0.85, 1.1)
            width = s["w"] * (0.6 + 0.4 * math.sin(math.pi * (0.2 + 0.7 * t))) * rng.uniform(0.85, 1.1)
            yaw = yaw0 + (i % 2) * math.pi + rng.uniform(-0.35, 0.35)
            elev = 0.8 + 0.5 * t + rng.uniform(-0.15, 0.15)
            droop = (1.45 - 0.7 * t) * rng.uniform(0.8, 1.2)
            if dry:
                droop += 0.6
                if rng.random() < 0.25 and t < 0.5:
                    length *= 0.5
            if stage in ("V6", "V12") and t > 0.85:
                elev, droop = 1.45, 0.3
            mk.leaf(mb, base, yaw, elev, length, width, leaf_m, droop=droop, segs=7 if length > 0.3 else 4,
                    profile="strap", across=3, fold=0.45, wave=0.04, wave_freq=14, phase=rng.uniform(0, 6))
        top = pts[-1]
        if stage in ("VT", "R6"):
            tas_m = "corn_stalk_dry" if dry else "corn_tassel"
            spike = [top, top + Vector((0, 0, 0.18)), top + Vector((rng.uniform(-.02, .02), rng.uniform(-.02, .02), 0.36))]
            mk.tube(mb, spike, [0.004, 0.003, 0.001], tas_m, sides=4)
            for k in range(rng.randint(6, 10)):
                b = top + Vector((0, 0, 0.05 + 0.1 * rng.random()))
                pk.stem_arc(mb, b, rng.uniform(0, 6.28), rng.uniform(0.6, 1.1), rng.uniform(0.12, 0.22),
                            1.2, 0.0018, 0.0008, tas_m, segs=4, sides=3)
            ears = 1 if rng.random() < 0.85 else 2
            for e in range(ears):
                z = stalk_h * rng.uniform(0.42, 0.52) - e * 0.15
                yaw = yaw0 + rng.uniform(0, 2 * math.pi)
                tilt = -2.3 if dry else 0.45
                d = mk.direction(yaw, math.pi / 2 - (0.5 if not dry else 0)) if not dry else mk.direction(yaw, -0.9)
                c = Vector((0, 0, z)) + lean * 0.25 + Vector((math.cos(yaw), math.sin(yaw), 0)) * 0.03 + d * 0.09
                rot = Vector((0, 0, 1)).rotation_difference(d).to_matrix()
                mk.ellipsoid(mb, c, (0.026, 0.026, 0.1), "corn_ear_dry" if dry else "corn_ear", u=8, v=6, matrix=rot)
                if not dry:
                    tip = c + d * 0.1
                    pk.stem_arc(mb, tip, yaw, 0.2, 0.06, 1.0, 0.006, 0.002, "corn_silk", segs=3, sides=4)
                pm.add_fruit(c, 0.1, "ear", ripeness=1.0 if dry else 0.5, axis=[round(v, 3) for v in d])
                _ = tilt
        pm.meta["leaves"] = n
        return pm


# ==================================================================== wheat
@register
class Wheat(Crop):
    name = "wheat"
    display = "Winter wheat"
    stages = {
        "tillering": dict(bbch="23", desc="tillering, leaves only, ~15 cm", h=0.0),
        "jointing": dict(bbch="32", desc="stem elongation, ~40 cm", h=0.35),
        "heading": dict(bbch="55", desc="ear emergence, green heads, ~80 cm", h=0.72),
        "ripe": dict(bbch="89", desc="fully ripe, golden, ~85 cm", h=0.78),
        "stubble": dict(bbch="99", desc="post-harvest stubble, ~15 cm", h=0.14),
    }
    layout = dict(row_spacing=0.19, plant_spacing=0.5, unit="segment", stems_per_m=60)
    record_fruits = False

    def materials(self, stage, opts):
        return {
            "wheat_leaf": L("#5f8f35", "#4b7a29", roughness=0.5),
            "wheat_leaf_dry": L("#d4b86a", "#c0a052", roughness=0.75, translucency=0.2),
            "wheat_stem": P("#6f9a40", "#628c38"),
            "wheat_stem_dry": P("#dcc276", "#cdb066", roughness=0.6),
            "wheat_head": P("#7fa64a", "#8aae55", semantic="crop_produce"),
            "wheat_head_ripe": P("#e3c574", "#d4b25c", semantic="crop_produce", roughness=0.65),
        }

    def build(self, stage, rng, opts):
        pm = PlantModel()
        mb = pm.mb
        seg = self.layout["plant_spacing"] if "segment_length" not in opts else opts["segment_length"]
        n = int(opts.get("stems_per_m", self.layout["stems_per_m"]) * seg * rng.uniform(0.8, 1.15))
        ripe = stage in ("ripe", "stubble")
        leaf_m = "wheat_leaf_dry" if ripe else "wheat_leaf"
        stem_m = "wheat_stem_dry" if ripe else "wheat_stem"
        head_m = "wheat_head_ripe" if ripe else "wheat_head"
        H = self.stage_info(stage)["h"]
        heads = 0
        for _ in range(n if stage != "tillering" else max(4, n // 3)):
            base = Vector((rng.gauss(0, 0.012), rng.uniform(-seg / 2, seg / 2), 0))
            if stage == "tillering":
                pk.grass_blades(mb, rng, base, rng.randint(3, 5), 0.17, 0.008, leaf_m, droop=1.2,
                                radius=0.01, elev_range=(0.9, 1.35), segs=4)
                continue
            h = H * rng.uniform(0.85, 1.1)
            yaw = rng.uniform(0, 2 * math.pi)
            elev = math.pi / 2 - abs(rng.gauss(0, 0.08 if stage != "stubble" else 0.15))
            bend = 0.12 if stage == "ripe" else 0.05
            if stage == "stubble":
                pts = mk.polyline_arc(base, yaw, elev, h, 0.0, 2)
                mk.tube(mb, pts, 0.0018, stem_m, sides=4)
                continue
            pts = mk.polyline_arc(base, yaw, elev, h, bend, 4)
            mk.tube(mb, pts, [0.0022, 0.002, 0.0018, 0.0016, 0.0014], stem_m, sides=4)
            nleaves = 3 if stage == "jointing" else 2
            for k in range(nleaves):
                t = 0.25 + 0.55 * k / nleaves + rng.uniform(-0.05, 0.05)
                idx = min(3, int(t * 4))
                p = pts[idx].lerp(pts[idx + 1], t * 4 - idx)
                Lk = rng.uniform(0.13, 0.2) * (0.8 if ripe else 1.0)
                mk.leaf(mb, p, rng.uniform(0, 6.28), rng.uniform(0.5, 1.0), Lk, 0.011, leaf_m,
                        droop=rng.uniform(0.9, 1.6) + (0.8 if ripe else 0), segs=4, profile="strap",
                        across=3, fold=0.3, curl=rng.uniform(-0.5, 0.5) if ripe else 0)
            if stage in ("heading", "ripe"):
                d = (pts[-1] - pts[-2]).normalized()
                c = pts[-1] + d * 0.035
                rot = Vector((0, 0, 1)).rotation_difference(d).to_matrix()
                mk.ellipsoid(mb, c, (0.0065, 0.0045, 0.04), head_m, u=6, v=5, matrix=rot)
                for a in range(4):
                    ang = a * math.pi / 2 + rng.uniform(-0.3, 0.3)
                    ap = c + rot @ Vector((0.004 * math.cos(ang), 0.004 * math.sin(ang), rng.uniform(-0.01, 0.03)))
                    ay, ae = pk.dir_to_yaw_elev(rot @ Vector((0.35 * math.cos(ang), 0.35 * math.sin(ang), 1)))
                    mk.leaf(mb, ap, ay, ae, rng.uniform(0.04, 0.07), 0.0012, head_m, droop=0.1, segs=2,
                            profile="needle", across=3, fold=0)
                heads += 1
        pm.meta["head_count"] = heads
        pm.meta["stems"] = n
        return pm


# ===================================================================== rice
@register
class Rice(Crop):
    name = "rice"
    display = "Paddy rice"
    stages = {
        "transplanted": dict(bbch="13", desc="recently transplanted seedlings, ~20 cm", h=0.2, tillers=4),
        "tillering": dict(bbch="25", desc="active tillering, ~50 cm", h=0.5, tillers=14),
        "heading": dict(bbch="59", desc="panicle emergence, ~90 cm", h=0.8, tillers=16),
        "ripe": dict(bbch="89", desc="ripe golden panicles", h=0.85, tillers=16),
    }
    layout = dict(row_spacing=0.25, plant_spacing=0.2, unit="hill")
    record_fruits = False

    def materials(self, stage, opts):
        return {
            "rice_leaf": L("#5c9c3a", "#4a8a30", roughness=0.4),
            "rice_leaf_dry": L("#c8b060", "#b49a4a", roughness=0.65),
            "rice_panicle": P("#9aaa50", "#a6b45c", semantic="crop_produce"),
            "rice_panicle_ripe": P("#d8b85a", "#c9a64a", semantic="crop_produce", roughness=0.7),
        }

    def build(self, stage, rng, opts):
        s = self.stage_info(stage)
        pm = PlantModel()
        mb = pm.mb
        ripe = stage == "ripe"
        leaf_m = "rice_leaf_dry" if ripe else "rice_leaf"
        n = s["tillers"] + rng.randint(-2, 3)
        panicles = 0
        for _ in range(n):
            yaw = rng.uniform(0, 2 * math.pi)
            elev = math.pi / 2 - rng.uniform(0.05, 0.35)
            h = s["h"] * rng.uniform(0.8, 1.1)
            base = Vector((rng.gauss(0, 0.01), rng.gauss(0, 0.01), 0))
            for k in range(3):
                mk.leaf(mb, base + Vector((0, 0, 0.02 * k)), yaw + rng.uniform(-0.6, 0.6), elev - 0.1 * k,
                        h * rng.uniform(0.7, 1.0), 0.009, leaf_m, droop=rng.uniform(0.4, 1.2) + (0.5 if ripe else 0),
                        segs=5, profile="strap", across=3, fold=0.35)
            if stage in ("heading", "ripe"):
                pts = mk.polyline_arc(base, yaw, elev, h * 0.95, 0.15, 4)
                mk.tube(mb, pts, 0.0018, leaf_m, sides=4)
                droop = 1.6 if ripe else 0.9
                pan = mk.polyline_arc(pts[-1], yaw, math.pi / 2 - 0.2, 0.2, droop + 1.0, 6)
                pmat = "rice_panicle_ripe" if ripe else "rice_panicle"
                mk.tube(mb, pan, [0.004, 0.005, 0.005, 0.0045, 0.004, 0.003, 0.0015], pmat, sides=5)
                for b in range(3):
                    i = 2 + b
                    pk.stem_arc(mb, pan[i], yaw + rng.uniform(-1, 1), -0.6, 0.06, 0.3, 0.003, 0.0015, pmat, segs=2, sides=4)
                panicles += 1
        pm.meta["tillers"] = n
        pm.meta["panicles"] = panicles
        return pm


# ================================================================== soybean
@register
class Soybean(Crop):
    name = "soybean"
    display = "Soybean"
    stages = {
        "V2": dict(bbch="12", desc="second trifoliate, ~10 cm", nodes=3, h=0.1),
        "V5": dict(bbch="15", desc="fifth trifoliate, ~35 cm", nodes=6, h=0.32),
        "R2": dict(bbch="65", desc="full bloom, ~60 cm", nodes=10, h=0.6),
        "R6": dict(bbch="79", desc="full seed, green pods, ~80 cm", nodes=12, h=0.75),
        "R8": dict(bbch="89", desc="full maturity, defoliated, brown pods", nodes=12, h=0.75),
    }
    layout = dict(row_spacing=0.76, plant_spacing=0.07, unit="plant")

    def materials(self, stage, opts):
        return {
            "soy_leaf": L("#3f7a2a", "#4f8a33", roughness=0.5, sheen=0.3),
            "soy_leaf_yellow": L("#c8b438", "#a88e30", roughness=0.6),
            "soy_stem": P("#5f8a35"),
            "soy_stem_dry": P("#7a5a38", "#6a4c30", roughness=0.8),
            "soy_flower": P("#a678c4", "#c098d8", semantic="crop_flower"),
            "soy_pod": P("#7da84a", "#86ae50", semantic="crop_produce", sheen=0.0),
            "soy_pod_dry": P("#8a6a3e", "#735532", semantic="crop_produce", roughness=0.8),
        }

    def build(self, stage, rng, opts):
        s = self.stage_info(stage)
        pm = PlantModel()
        mb = pm.mb
        mature = stage == "R8"
        stem_m = "soy_stem_dry" if mature else "soy_stem"
        nodes = s["nodes"] + rng.randint(-1, 1)
        H = s["h"] * rng.uniform(0.85, 1.12)
        lean = Vector((rng.uniform(-0.04, 0.04), rng.uniform(-0.04, 0.04), 0))
        pts = [Vector((0, 0, 0)) + lean * (i / 6) ** 2 * H * 3 + Vector((0, 0, H * i / 6)) for i in range(7)]
        mk.tube(mb, pts, [0.004 * (1 - 0.6 * i / 6) + 0.001 for i in range(7)], stem_m, sides=5)
        ang = rng.uniform(0, 6.28)
        leaflet = 0.045 + 0.065 * min(1.0, H / 0.5)
        for i in range(nodes):
            t = (i + 1) / (nodes + 1)
            idx = min(5, int(t * 6))
            p = pts[idx].lerp(pts[idx + 1], t * 6 - idx)
            ang += 2.4
            keep_leaf = (not mature) or rng.random() < 0.12
            if keep_leaf:
                lm = "soy_leaf_yellow" if (mature or (stage == "R6" and t < 0.2 and rng.random() < 0.6)) else "soy_leaf"
                pet = (0.05 + 0.14 * min(1.0, H / 0.6)) * rng.uniform(0.8, 1.2)
                if i == 0 and stage == "V2":
                    for side in (0, math.pi):
                        mk.leaf(mb, p, ang + side, 0.4, leaflet * 0.9, leaflet * 0.6, lm, droop=0.5, segs=4, profile="ovate")
                else:
                    pk.trifoliate(mb, rng, p, ang, 0.5 + 0.6 * t, pet, leaflet * rng.uniform(0.85, 1.15),
                                  leaflet * 0.62, lm, stem_m, petiole_bend=0.6, leaflet_droop=0.4,
                                  stem_r=0.0015, wave=0.05)
            if stage == "R2" and 0.2 < t < 0.85:
                for f in range(rng.randint(1, 3)):
                    fp = p + Vector((rng.uniform(-.012, .012), rng.uniform(-.012, .012), rng.uniform(0, 0.01)))
                    mk.ellipsoid(mb, fp, (0.004, 0.004, 0.006), "soy_flower", u=5, v=3)
            if stage in ("R6", "R8") and 0.1 < t < 0.9:
                pod_m = "soy_pod_dry" if mature else "soy_pod"
                for f in range(rng.randint(2, 4)):
                    a = rng.uniform(0, 6.28)
                    d = Vector((math.cos(a), math.sin(a), rng.uniform(-1.2, -0.2))).normalized()
                    c = p + d * 0.025
                    rot = Vector((0, 0, 1)).rotation_difference(d).to_matrix()
                    mk.ellipsoid(mb, c, (0.006, 0.0035, 0.022), pod_m, u=6, v=4, matrix=rot)
                    pm.add_fruit(c, 0.022, "pod", ripeness=1.0 if mature else 0.6)
        nbranch = {"V2": 0, "V5": 1, "R2": 4, "R6": 5, "R8": 5}[stage] + rng.randint(0, 1)
        for b in range(nbranch):
            t = rng.uniform(0.1, 0.45)
            base = Vector((0, 0, H * t))
            by = rng.uniform(0, 6.28)
            blen = H * rng.uniform(0.4, 0.6)
            bpts = mk.polyline_arc(base, by, 0.8, blen, 0.5, 3)
            mk.tube(mb, bpts, [0.0028, 0.0022, 0.0016, 0.0012], stem_m, sides=4)
            for j in range(1, 4):
                q = bpts[j]
                if not mature or rng.random() < 0.12:
                    pk.trifoliate(mb, rng, q, by + rng.uniform(-1.5, 1.5), 0.6, 0.07 * rng.uniform(0.8, 1.3),
                                  leaflet * 0.9, leaflet * 0.58, "soy_leaf_yellow" if mature else "soy_leaf",
                                  stem_m, stem_r=0.0013, wave=0.05)
                if stage in ("R6", "R8"):
                    for f in range(rng.randint(1, 3)):
                        a = rng.uniform(0, 6.28)
                        d = Vector((math.cos(a), math.sin(a), rng.uniform(-1.2, -0.2))).normalized()
                        c = q + d * 0.022
                        rot = Vector((0, 0, 1)).rotation_difference(d).to_matrix()
                        mk.ellipsoid(mb, c, (0.006, 0.0035, 0.022), "soy_pod_dry" if mature else "soy_pod", u=6, v=4, matrix=rot)
                        pm.add_fruit(c, 0.022, "pod", ripeness=1.0 if mature else 0.6)
        return pm


# ================================================================== lettuce
@register
class Lettuce(Crop):
    name = "lettuce"
    display = "Lettuce"
    stages = {
        "seedling": dict(bbch="13", desc="3-4 true leaves, 5 cm", n=4, size=0.05),
        "rosette": dict(bbch="18", desc="open rosette, ~18 cm across", n=12, size=0.11),
        "heading": dict(bbch="45", desc="harvest-ready head, ~30 cm across", n=24, size=0.17),
    }
    layout = dict(row_spacing=0.3, plant_spacing=0.3, unit="plant",
                  bed=dict(width=1.0, height=0.12, top=0.75, rows=2))

    def materials(self, stage, opts):
        v = opts.get("variety", "green")
        if v == "red":
            outer = L("#7a2f3a", "#5e2a35", roughness=0.4, translucency=0.25)
        elif v == "romaine":
            outer = L("#3f8530", "#4f9538", roughness=0.4)
        else:
            outer = L("#7fbf3f", "#93cc4c", roughness=0.4)
        return {
            "lettuce_leaf": outer,
            "lettuce_inner": L("#c8e090", "#b8d878", roughness=0.4),
            "lettuce_stem": P("#d8e8a8"),
        }

    def build(self, stage, rng, opts):
        s = self.stage_info(stage)
        pm = PlantModel()
        mb = pm.mb
        variety = opts.get("variety", "green")
        n = s["n"] + rng.randint(-2, 2)
        size = s["size"] * rng.uniform(0.85, 1.15)
        ga = 2.39996
        yaw0 = rng.uniform(0, 6.28)
        romaine = variety == "romaine"
        for i in range(n):
            t = i / max(1, n - 1)          # 0 = outer/oldest
            yaw = yaw0 + i * ga
            Lk = size * (1.0 - 0.55 * t ** 1.5) * rng.uniform(0.88, 1.1)
            if romaine:
                Lk *= 1.5
                elev = 0.9 + 0.6 * t
            else:
                elev = 0.2 + 0.9 * t ** 1.5
            droop = 0.9 - 0.6 * t if not romaine else 0.5 - 0.4 * t
            mat = "lettuce_inner" if (t > 0.75 and stage == "heading") else "lettuce_leaf"
            wave = 0.25 if variety in ("green", "red") else 0.08
            mk.leaf(mb, Vector((0, 0, 0.005 + 0.01 * t)), yaw, elev, Lk, Lk * (0.55 if romaine else 0.85), mat,
                    droop=droop, segs=7, profile="obovate", across=7, cup=0.1 + 0.3 * t, wave=wave * 0.75,
                    wave_freq=7, fold=0.1, phase=rng.uniform(0, 6))
        if stage == "heading":
            r = size * (0.35 if not romaine else 0.25)
            c = Vector((0, 0, r * (1.0 if not romaine else 2.0)))
            mk.ellipsoid(mb, c, (r, r, r * (0.85 if not romaine else 2.2)), "lettuce_inner", u=10, v=7,
                         jitter=0.05, rng=rng)
            pm.add_fruit(c, size, "head", ripeness=1.0)
        return pm


# ================================================================== cabbage
@register
class Cabbage(Crop):
    name = "cabbage"
    display = "Cabbage"
    stages = {
        "seedling": dict(bbch="14", desc="4-5 true leaves", n=5, size=0.07, head=0.0),
        "cupping": dict(bbch="19", desc="leaves cupping, head initiating", n=10, size=0.17, head=0.03),
        "heading": dict(bbch="45", desc="head half size", n=12, size=0.24, head=0.07),
        "mature": dict(bbch="49", desc="firm head, harvest ready", n=13, size=0.27, head=0.105),
    }
    layout = dict(row_spacing=0.6, plant_spacing=0.45, unit="plant")

    def materials(self, stage, opts):
        return {
            "cabbage_leaf": L("#6f9a7a", "#7fa888", roughness=0.35, translucency=0.2),
            "cabbage_leaf_old": L("#a8b070", "#98a868", roughness=0.45),
            "cabbage_head": P("#c4dc9c", "#b8d48c", semantic="crop_produce", roughness=0.35),
            "cabbage_stem": P("#a8c08c"),
        }

    def build(self, stage, rng, opts):
        s = self.stage_info(stage)
        pm = PlantModel()
        mb = pm.mb
        n = s["n"] + rng.randint(-1, 2)
        size = s["size"] * rng.uniform(0.88, 1.12)
        hr = s["head"] * rng.uniform(0.9, 1.1)
        yaw0 = rng.uniform(0, 6.28)
        for i in range(n):
            t = i / max(1, n - 1)
            yaw = yaw0 + i * 2.39996
            Lk = size * (1.0 - 0.3 * t) * rng.uniform(0.9, 1.1)
            base = Vector((0, 0, 0.02 + 0.03 * t * (hr > 0)))
            pet = Lk * 0.25
            tip, d = pk.stem_arc(mb, base, yaw, 0.7 + 0.4 * t, pet, 0.3, 0.006, 0.004, "cabbage_stem", segs=2)
            mat = "cabbage_leaf_old" if (stage == "mature" and t < 0.2) else "cabbage_leaf"
            mk.leaf(mb, tip, yaw, 0.55 + 0.7 * t, Lk, Lk * 0.95, mat, droop=0.9 + 0.3 * rng.random(), segs=7,
                    profile="round", across=7, cup=0.7, wave=0.08, wave_freq=6, fold=0.05,
                    phase=rng.uniform(0, 6))
        if hr > 0:
            c = Vector((0, 0, 0.02 + hr * 0.95))
            mk.ellipsoid(mb, c, (hr, hr, hr * 0.92), "cabbage_head", u=12, v=8, jitter=0.03, rng=rng)
            for k in range(4):
                yaw = yaw0 + k * 1.57 + rng.uniform(-0.3, 0.3)
                p = Vector((0, 0, 0.02 + hr * 0.2)) + Vector((math.cos(yaw), math.sin(yaw), 0)) * hr * 0.7
                mk.leaf(mb, p, yaw, 1.3, hr * 1.7, hr * 1.4, "cabbage_leaf", droop=2.6, segs=6,
                        profile="round", across=7, cup=0.6)
            if stage in ("heading", "mature"):
                pm.add_fruit(c, hr, "head", ripeness=1.0 if stage == "mature" else 0.5)
        return pm


# =================================================================== tomato
@register
class Tomato(Crop):
    name = "tomato"
    display = "Staked tomato"
    stages = {
        "transplant": dict(bbch="14", desc="recently transplanted, ~20 cm", h=0.2, trusses=0),
        "vegetative": dict(bbch="19", desc="vegetative growth, ~60 cm", h=0.6, trusses=0),
        "flowering": dict(bbch="61", desc="first trusses flowering, ~1 m", h=1.0, trusses=3),
        "fruiting": dict(bbch="75", desc="green fruit set, ~1.4 m", h=1.35, trusses=5),
        "ripening": dict(bbch="85", desc="mixed ripeness, harvest ongoing, ~1.6 m", h=1.55, trusses=6),
    }
    layout = dict(row_spacing=1.5, plant_spacing=0.5, unit="plant",
                  bed=dict(width=1.5, height=0.15, top=0.8, rows=1))

    def materials(self, stage, opts):
        return {
            "tom_leaf": L("#3d6b25", "#4a7a2c", roughness=0.55, sheen=0.4),
            "tom_stem": P("#5a7a30", "#6a8a3a", roughness=0.6, sheen=0.3),
            "tom_flower": P("#f0d020", "#e8c818", semantic="crop_flower"),
            "tom_green": P("#6c9a35", "#78a640", semantic="crop_produce", roughness=0.25, coat=0.3),
            "tom_turning": P("#e8a038", "#d8862a", semantic="crop_produce", roughness=0.25, coat=0.3),
            "tom_red": P("#c8261c", "#b81c18", semantic="crop_produce", roughness=0.22, coat=0.4),
        }

    def build(self, stage, rng, opts):
        s = self.stage_info(stage)
        pm = PlantModel()
        mb = pm.mb
        H = s["h"] * rng.uniform(0.88, 1.1)
        nseg = max(3, int(H / 0.08))
        pts = []
        for i in range(nseg + 1):
            z = H * i / nseg
            pts.append(Vector((0.01 * math.sin(i * 1.7) + rng.uniform(-0.006, 0.006),
                               0.01 * math.cos(i * 1.3) + rng.uniform(-0.006, 0.006), z)))
        mk.tube(mb, pts, [0.009 * (1 - 0.6 * i / nseg) + 0.002 for i in range(nseg + 1)], "tom_stem", sides=5)
        yaw = rng.uniform(0, 6.28)
        rach = 0.15 + 0.25 * min(1.0, H / 0.8)
        leaflet = 0.04 + 0.045 * min(1.0, H / 0.8)
        nleaf = max(3, int(H / 0.065))
        for i in range(nleaf):
            t = (i + 0.5) / nleaf
            p = pts[min(nseg, int(t * nseg))]
            yaw += 2.4 + rng.uniform(-0.3, 0.3)
            pk.pinnate(mb, rng, p, yaw, 0.6 - 0.2 * (1 - t), rach * (1.1 - 0.4 * t) * rng.uniform(0.85, 1.15),
                       3, leaflet, leaflet * 0.62, "tom_leaf", "tom_stem", bend=1.0 + 0.4 * (1 - t),
                       leaflet_droop=0.6, stem_r=0.0022, wave=0.08, minor=1 if H > 0.4 else 0)
        trusses = s["trusses"]
        for k in range(trusses):
            t = 0.25 + 0.65 * k / max(1, trusses)
            p = pts[min(nseg, int(t * nseg))]
            ty = rng.uniform(0, 6.28)
            tip, d = pk.stem_arc(mb, p, ty, 0.3, 0.07, 1.2, 0.0025, 0.0018, "tom_stem", segs=3, sides=4)
            if stage == "flowering" or (stage == "fruiting" and k == trusses - 1):
                for f in range(rng.randint(4, 7)):
                    fp = tip + Vector((rng.uniform(-.04, .04), rng.uniform(-.04, .04), rng.uniform(-.03, .01)))
                    pk.flower(mb, fp, (rng.uniform(-.5, .5), rng.uniform(-.5, .5), -0.6), 0.011, "tom_flower", None, segs=1)
                continue
            if stage in ("fruiting", "ripening"):
                nf = rng.randint(3, 6)
                placed = []
                for f in range(nf):
                    r = rng.uniform(0.022, 0.032)
                    a = ty + (f - nf / 2) * 0.9
                    dist = 0.03 + 0.02 * f
                    fp = tip + Vector((math.cos(a) * dist, math.sin(a) * dist, -0.03 - 0.02 * f - r))
                    for _ in range(6):  # push apart overlapping fruit
                        clash = [q for q, qr in placed if (q - fp).length < (r + qr) * 1.02]
                        if not clash:
                            break
                        fp = fp + Vector((math.cos(a), math.sin(a), -0.6)).normalized() * r * 0.8
                    placed.append((fp, r))
                    if stage == "ripening":
                        ripeness = max(0.0, min(1.0, 1.15 - t * 1.2 + rng.uniform(-0.25, 0.25)))
                    else:
                        ripeness = rng.uniform(0.0, 0.15)
                    mat = "tom_red" if ripeness > 0.7 else ("tom_turning" if ripeness > 0.4 else "tom_green")
                    mk.ellipsoid(mb, fp, (r, r, r * 0.85), mat, u=10, v=6)
                    mk.tube(mb, [fp + Vector((0, 0, r * 0.8)), tip], 0.0012, "tom_stem", sides=3)
                    pm.add_fruit(fp, r, "tomato", ripeness=ripeness,
                                 ripeness_class="red" if ripeness > 0.7 else ("turning" if ripeness > 0.4 else "green"))
        pm.meta["height"] = H
        return pm


# =================================================================== potato
@register
class Potato(Crop):
    name = "potato"
    display = "Potato (hilled)"
    stages = {
        "emergence": dict(bbch="09", desc="shoots emerging from ridge", stems=3, h=0.1),
        "vegetative": dict(bbch="31", desc="canopy closing, ~45 cm", stems=5, h=0.4),
        "flowering": dict(bbch="65", desc="full flowering, ~60 cm", stems=6, h=0.55),
        "senescence": dict(bbch="91", desc="haulm yellowing / dying back", stems=5, h=0.4),
    }
    layout = dict(row_spacing=0.9, plant_spacing=0.3, unit="plant",
                  ridge=dict(height=0.2, width=0.55))

    def materials(self, stage, opts):
        return {
            "pot_leaf": L("#3f6e2a", "#4b7d2f", roughness=0.55, sheen=0.2),
            "pot_leaf_sen": L("#b8a040", "#8a7a35", roughness=0.65),
            "pot_stem": P("#5a7a35"),
            "pot_stem_sen": P("#7a6a3a", roughness=0.8),
            "pot_flower": P("#f2f0ea" if opts.get("flower", "white") == "white" else "#a58ac8", semantic="crop_flower"),
            "pot_flower_c": P("#f0c020", semantic="crop_flower"),
        }

    def build(self, stage, rng, opts):
        s = self.stage_info(stage)
        pm = PlantModel()
        mb = pm.mb
        sen = stage == "senescence"
        leaf_m, stem_m = ("pot_leaf_sen", "pot_stem_sen") if sen else ("pot_leaf", "pot_stem")
        for k in range(s["stems"] + rng.randint(-1, 1)):
            yaw = rng.uniform(0, 6.28)
            elev = rng.uniform(1.0, 1.4) if not sen else rng.uniform(0.35, 0.8)
            h = s["h"] * rng.uniform(0.75, 1.15)
            base = Vector((rng.gauss(0, 0.03), rng.gauss(0, 0.03), 0))
            pts = mk.polyline_arc(base, yaw, elev, h, 0.3 if not sen else 0.6, 5)
            mk.tube(mb, pts, [0.006 * (1 - 0.5 * i / 5) for i in range(6)], stem_m, sides=5)
            nl = max(2, int(h / 0.08))
            for i in range(nl):
                t = (i + 1) / (nl + 1)
                idx = min(4, int(t * 5))
                p = pts[idx].lerp(pts[idx + 1], t * 5 - idx)
                ly = yaw + rng.uniform(-2.2, 2.2)
                size = (0.03 + 0.05 * min(1.0, h / 0.4)) * (1.1 - 0.3 * t)
                pk.pinnate(mb, rng, p, ly, 0.5 if not sen else 0.0, size * 3.2, 3, size, size * 0.7,
                           leaf_m, stem_m, bend=0.6 if not sen else 1.2, leaflet_droop=0.35, stem_r=0.002,
                           wave=0.06, minor=0)
            if stage == "flowering":
                top = pts[-1]
                for f in range(rng.randint(3, 7)):
                    fp = top + Vector((rng.uniform(-.04, .04), rng.uniform(-.04, .04), rng.uniform(0.0, 0.05)))
                    pk.flower(mb, fp, (rng.uniform(-.3, .3), rng.uniform(-.3, .3), 1), 0.014, "pot_flower", "pot_flower_c", segs=1)
        return pm


# ================================================================ sunflower
@register
class Sunflower(Crop):
    name = "sunflower"
    display = "Sunflower"
    stages = {
        "vegetative": dict(bbch="18", desc="8 leaves, ~50 cm", n=8, h=0.45),
        "bud": dict(bbch="55", desc="star bud visible, ~1.2 m", n=16, h=1.15),
        "bloom": dict(bbch="65", desc="full flowering, ~1.8 m", n=20, h=1.7),
        "mature": dict(bbch="89", desc="drooping dry heads, ~1.8 m", n=18, h=1.7),
    }
    layout = dict(row_spacing=0.76, plant_spacing=0.3, unit="plant")

    def materials(self, stage, opts):
        return {
            "sun_leaf": L("#4a7a2a", "#3f6e25", roughness=0.6, sheen=0.4),
            "sun_leaf_dry": L("#7a6440", "#5e4c30", roughness=0.8, translucency=0.1),
            "sun_stem": P("#6a8f3a", roughness=0.6, sheen=0.4),
            "sun_stem_dry": P("#8a7350", roughness=0.8),
            "sun_disc": P("#3a2412", "#4a2e18", semantic="crop_produce", roughness=0.8, bump=0.5, bump_scale=300),
            "sun_back": P("#86a447", "#6f8f3a", semantic="crop_produce"),
            "sun_back_dry": P("#9a8050", semantic="crop_produce", roughness=0.8),
            "sun_petal": L("#f5c518", "#f0b010", semantic="crop_flower", roughness=0.5),
        }

    def build(self, stage, rng, opts):
        s = self.stage_info(stage)
        pm = PlantModel()
        mb = pm.mb
        dry = stage == "mature"
        H = s["h"] * rng.uniform(0.88, 1.1)
        stem_m = "sun_stem_dry" if dry else "sun_stem"
        pts = [Vector((rng.uniform(-.01, .01) * i, rng.uniform(-.01, .01) * i, H * i / 6)) for i in range(7)]
        mk.tube(mb, pts, [0.016 * (1 - 0.5 * i / 6) + 0.003 for i in range(7)], stem_m, sides=6)
        n = s["n"]
        yaw = rng.uniform(0, 6.28)
        for i in range(n):
            t = (i + 0.5) / n
            p = pts[min(6, int(t * 6))].lerp(pts[min(6, int(t * 6) + 1 if t * 6 < 6 else 6)], (t * 6) % 1)
            yaw += 2.4
            size = (0.08 + 0.2 * min(1.0, H / 1.0)) * (1.15 - 0.6 * t) * rng.uniform(0.85, 1.1)
            lm = "sun_leaf_dry" if (dry and rng.random() < 0.8) or (stage == "bloom" and t < 0.15) else "sun_leaf"
            pet = size * 0.6
            tip, d = pk.stem_arc(mb, p, yaw, 0.7, pet, 0.4 + (0.8 if dry else 0), 0.004, 0.003, stem_m, segs=3)
            mk.leaf(mb, tip, yaw, 0.1 - (0.8 if dry else 0), size, size * 0.8, lm, droop=0.6 + (0.8 if dry else 0),
                    segs=5, profile="heart", across=5, fold=0.15, cup=-0.1, wave=0.05,
                    curl=rng.uniform(-0.6, 0.6) if dry else 0.0)
        top = pts[-1]
        if stage == "bud":
            mk.ellipsoid(mb, top + Vector((0, 0, 0.03)), (0.045, 0.045, 0.035), "sun_back", u=10, v=6)
            for k in range(12):
                a = k * 0.52
                mk.leaf(mb, top + Vector((0, 0, 0.04)), a, 1.0, 0.04, 0.012, "sun_leaf", droop=-0.3, segs=2, profile="lanceolate")
            pm.add_fruit(top + Vector((0, 0, 0.03)), 0.045, "head", ripeness=0.1)
        elif stage in ("bloom", "mature"):
            r = rng.uniform(0.1, 0.14)
            if dry:
                face = Vector((rng.uniform(-.3, .3), rng.uniform(-.3, .3), -1)).normalized()
                c = top + Vector((0.08, 0, -0.06))
            else:
                face = Vector((1.0, rng.uniform(-.3, .3), rng.uniform(0.0, 0.5))).normalized()  # east (+x)
                c = top + face * 0.05 + Vector((0, 0, 0.05))
            mk.tube(mb, [top, top + Vector((0, 0, 0.06)), c], 0.01, stem_m, sides=5)
            mk.disc(mb, c + face * 0.012, face, r, "sun_disc", segs=20, dome=0.012)
            mk.disc(mb, c - face * 0.01, -face, r * 1.02, "sun_back_dry" if dry else "sun_back", segs=20, dome=0.03)
            if not dry:
                a = mk._perp(face)
                b = face.cross(a)
                for k in range(26):
                    ang = 2 * math.pi * k / 26
                    d = a * math.cos(ang) + b * math.sin(ang)
                    py, pe = pk.dir_to_yaw_elev(d + face * 0.15)
                    mk.leaf(mb, c + d * r * 0.95, py, pe, r * 0.65, r * 0.22, "sun_petal", droop=0.2, segs=3,
                            profile="lanceolate", across=3, fold=0.0, roll=0.0)
            pm.add_fruit(c, r, "head", ripeness=1.0 if dry else 0.4, facing=[round(v, 3) for v in face])
        return pm


# =============================================================== strawberry
@register
class Strawberry(Crop):
    name = "strawberry"
    display = "Strawberry (plasticulture)"
    stages = {
        "flowering": dict(bbch="65", desc="full flowering, few green fruit"),
        "fruiting": dict(bbch="87", desc="main harvest, mixed ripeness"),
    }
    layout = dict(row_spacing=0.35, plant_spacing=0.3, unit="plant",
                  bed=dict(width=1.3, height=0.2, top=0.7, rows=2), mulch="black")

    def materials(self, stage, opts):
        return {
            "sb_leaf": L("#2f6a2a", "#3c7a30", roughness=0.4),
            "sb_stem": P("#6a8a3a", "#7a5a3a"),
            "sb_flower": P("#f5f5ee", semantic="crop_flower"),
            "sb_flower_c": P("#e8c020", semantic="crop_flower"),
            "sb_red": P("#c0141e", "#a8101a", semantic="crop_produce", roughness=0.25, coat=0.5, bump=0.3, bump_scale=250),
            "sb_white": P("#e2ecc0", "#d0e0a8", semantic="crop_produce", roughness=0.3),
            "sb_green": P("#8ab050", semantic="crop_produce", roughness=0.3),
        }

    def build(self, stage, rng, opts):
        pm = PlantModel()
        mb = pm.mb
        n = rng.randint(13, 19)
        yaw = rng.uniform(0, 6.28)
        for i in range(n):
            yaw += 2.4 + rng.uniform(-0.3, 0.3)
            pk.trifoliate(mb, rng, Vector((0, 0, 0.01)), yaw, rng.uniform(1.0, 1.4), rng.uniform(0.07, 0.13),
                          rng.uniform(0.05, 0.07), 0.045, "sb_leaf", "sb_stem", petiole_bend=1.0,
                          leaflet_droop=0.35, spread=1.0, stem_r=0.0018, wave=0.12, profile="ovate")
        for k in range(rng.randint(3, 6)):
            a = rng.uniform(0, 6.28)
            tip, d = pk.stem_arc(mb, Vector((0, 0, 0.01)), a, 0.9, rng.uniform(0.1, 0.16),
                                 1.6 if stage == "fruiting" else 1.0, 0.0015, 0.0012, "sb_stem", segs=4, sides=3)
            if stage == "flowering" and rng.random() < 0.75:
                pk.flower(mb, tip, (math.cos(a), math.sin(a), 0.5), 0.012, "sb_flower", "sb_flower_c", segs=1)
            else:
                ripeness = rng.uniform(0.6, 1.0) if stage == "fruiting" else rng.uniform(0.0, 0.3)
                if stage == "fruiting" and rng.random() < 0.35:
                    ripeness = rng.uniform(0.0, 0.6)
                mat = "sb_red" if ripeness > 0.7 else ("sb_white" if ripeness > 0.35 else "sb_green")
                r = rng.uniform(0.008, 0.012) * (0.75 + 0.45 * ripeness)
                c = tip - Vector((0, 0, r * 1.2))
                mk.ellipsoid(mb, c, (r, r, r * 1.05), mat, u=8, v=6, pointy=0.5)
                pm.add_fruit(c, r * 1.3, "strawberry", ripeness=ripeness,
                             ripeness_class="ripe" if ripeness > 0.7 else ("white" if ripeness > 0.35 else "green"))
        return pm


# ================================================================ grapevine
@register
class Grapevine(Crop):
    name = "grapevine"
    display = "Wine grape (VSP trellis)"
    stages = {
        "budbreak": dict(bbch="09", desc="short new shoots on cordons", shoot=0.15, clusters=0),
        "leafy": dict(bbch="71", desc="full canopy, small green clusters", shoot=0.75, clusters=1),
        "veraison": dict(bbch="83", desc="berries colouring, mixed", shoot=0.8, clusters=2),
        "harvest": dict(bbch="89", desc="ripe dark clusters, some yellow leaves", shoot=0.8, clusters=3),
    }
    layout = dict(row_spacing=2.5, plant_spacing=1.5, unit="plant", trellis=dict(post_every=4, wires=(0.9, 1.25, 1.6)))
    variants = 4

    def materials(self, stage, opts):
        return {
            "vine_leaf": L("#4f7f2a", "#5f8f35", roughness=0.5),
            "vine_leaf_yellow": L("#c8b040", "#b89a30", roughness=0.6),
            "vine_wood": P("#5a4632", "#4a3a2a", semantic="crop_stem", roughness=0.9, bump=0.5),
            "vine_shoot": P("#7a8a3a", "#6a7a35"),
            "grape_green": P("#9ab84a", "#a8c050", semantic="crop_produce", roughness=0.3, sss=0.2),
            "grape_dark": P("#3a1f3f", "#2a1430", semantic="crop_produce", roughness=0.35, sheen=0.4),
        }

    def build(self, stage, rng, opts):
        s = self.stage_info(stage)
        pm = PlantModel()
        mb = pm.mb
        h_cordon = 0.9
        half = self.layout["plant_spacing"] * 0.5
        trunk = [Vector((rng.uniform(-.02, .02), rng.uniform(-.02, .02), z)) for z in (0, 0.3, 0.6, h_cordon - 0.05)]
        mk.tube(mb, trunk, [0.035, 0.03, 0.028, 0.025], "vine_wood", sides=7)
        for side in (1, -1):
            cord = [trunk[-1], Vector((0, side * 0.12, h_cordon)), Vector((0, side * half * 0.5, h_cordon + 0.01)),
                    Vector((0, side * half * 0.95, h_cordon))]
            mk.tube(mb, cord, [0.022, 0.018, 0.015, 0.01], "vine_wood", sides=6)
            nshoot = 7
            for k in range(nshoot):
                y = side * (0.1 + (half * 0.85) * k / (nshoot - 1))
                base = Vector((rng.uniform(-.01, .01), y, h_cordon + 0.01))
                L_ = s["shoot"] * rng.uniform(0.8, 1.15)
                yaw = rng.uniform(0, 6.28)
                pts = mk.polyline_arc(base, yaw, math.pi / 2 - rng.uniform(0.0, 0.25), L_, 0.15, 5)
                mk.tube(mb, pts, [0.006, 0.005, 0.004, 0.0035, 0.003, 0.002], "vine_shoot", sides=4)
                nl = max(2, int(L_ / 0.075))
                for i in range(nl):
                    t = (i + 0.7) / (nl + 0.7)
                    idx = min(4, int(t * 5))
                    p = pts[idx].lerp(pts[idx + 1], t * 5 - idx)
                    ly = (0 if rng.random() < 0.5 else math.pi) + rng.uniform(-0.8, 0.8)
                    size = (0.11 if stage != "budbreak" else 0.045) * rng.uniform(0.85, 1.2) * (1.1 - 0.4 * t)
                    lm = "vine_leaf_yellow" if (stage == "harvest" and rng.random() < 0.25) else "vine_leaf"
                    pk.palmate(mb, rng, p, ly, 0.3, size * 0.8, size, lm, "vine_shoot", lobes=5, spread=1.1,
                               stem_r=0.0015, petiole_bend=0.4, blade_elev=0.5, droop=0.6, wave=0.05, profile="heart")
                if s["clusters"] and rng.random() < 0.75:
                    for c in range(min(2, s["clusters"])):
                        top = base + Vector((rng.choice((-1, 1)) * 0.04, rng.uniform(-.03, .03), -0.02 - 0.05 * c))
                        if stage == "leafy":
                            mat, ripeness = "grape_green", 0.1
                        elif stage == "veraison":
                            ripeness = rng.uniform(0.2, 0.8)
                            mat = "grape_dark" if ripeness > 0.5 else "grape_green"
                        else:
                            mat, ripeness = "grape_dark", rng.uniform(0.85, 1.0)
                        cl = rng.uniform(0.1, 0.16)
                        br = 0.006 if stage == "leafy" else 0.0085
                        pk.berry_cluster(mb, rng, top, cl, 0.045, br, mat, "vine_shoot",
                                         density=0.7 if stage == "leafy" else 1.0)
                        pm.add_fruit(top - Vector((0, 0, cl * 0.4)), cl * 0.55, "grape_cluster", ripeness=ripeness)
        return pm


# ==================================================================== apple
@register
class Apple(Crop):
    name = "apple"
    display = "Apple (tall spindle orchard)"
    stages = {
        "blossom": dict(bbch="65", desc="full bloom, young leaves"),
        "fruitlet": dict(bbch="72", desc="fruitlets ~2 cm, full leaf"),
        "harvest": dict(bbch="87", desc="ripe red fruit, harvest ready"),
    }
    layout = dict(row_spacing=3.5, plant_spacing=1.0, unit="plant", trellis=dict(post_every=8, wires=(1.0, 2.0, 2.8)))
    variants = 4

    def materials(self, stage, opts):
        return {
            "apple_leaf": L("#3f6f2a", "#4f7f30", roughness=0.4, sheen=0.2),
            "apple_bark": P("#4a3a2c", "#5a4836", semantic="crop_stem", roughness=0.9, bump=0.8, bump_scale=40),
            "apple_blossom": P("#f6e2e6", "#f0c8d0", semantic="crop_flower", roughness=0.5, sss=0.2),
            "apple_fruit_red": P("#b3202a", "#c8402a", semantic="crop_produce", roughness=0.3, coat=0.4),
            "apple_fruit_green": P("#9ab840", "#a8c048", semantic="crop_produce", roughness=0.3, coat=0.3),
        }

    def build(self, stage, rng, opts):
        pm = PlantModel()
        mb = pm.mb
        H = rng.uniform(2.7, 3.1)
        trunk = [Vector((rng.uniform(-.03, .03) * (i / 6), rng.uniform(-.03, .03) * (i / 6), H * i / 6)) for i in range(7)]
        mk.tube(mb, trunk, [0.05 * (1 - 0.75 * i / 6) + 0.006 for i in range(7)], "apple_bark", sides=7)
        nb = rng.randint(16, 22)
        yaw = rng.uniform(0, 6.28)
        leaf_density = 0.45 if stage == "blossom" else 1.0
        for b in range(nb):
            t = 0.22 + 0.75 * b / nb
            z = H * t
            yaw += 2.4 + rng.uniform(-0.3, 0.3)
            # tall spindle: branches trained along the row (y) more than across
            by = yaw if rng.random() < 0.4 else (math.pi / 2 if math.sin(yaw) > 0 else -math.pi / 2) + rng.uniform(-0.5, 0.5)
            length = (1.1 - 0.75 * t) * rng.uniform(0.8, 1.2)
            pts = mk.polyline_arc(Vector((0, 0, z)), by, rng.uniform(0.1, 0.5), length, 0.6, 4)
            mk.tube(mb, pts, [0.016 * (1 - 0.6 * t), 0.012, 0.008, 0.005, 0.003], "apple_bark", sides=5)
            spurs = max(3, int(length / 0.045))
            for sidx in range(spurs):
                u = (sidx + 0.5) / spurs
                idx = min(3, int(u * 4))
                p = pts[idx].lerp(pts[idx + 1], u * 4 - idx)
                nlv = int(rng.randint(6, 9) * leaf_density)
                for lv in range(nlv):
                    Ll = rng.uniform(0.06, 0.09) * (0.7 if stage == "blossom" else 1)
                    mk.leaf(mb, p, rng.uniform(0, 6.28), rng.uniform(-0.2, 0.9), Ll,
                            Ll * 0.55, "apple_leaf", droop=0.5, segs=3, profile="ovate", across=3, fold=0.3)
                if rng.random() < 0.35 * leaf_density:
                    sy = by + rng.uniform(-1.2, 1.2)
                    spts = mk.polyline_arc(p, sy, rng.uniform(0.3, 1.0), rng.uniform(0.12, 0.3), 0.3, 3)
                    mk.tube(mb, spts, [0.003, 0.0025, 0.002, 0.0015], "apple_bark", sides=4)
                    for q in spts[1:]:
                        for lv in range(3):
                            Ll = rng.uniform(0.06, 0.09)
                            mk.leaf(mb, q, rng.uniform(0, 6.28), rng.uniform(0.0, 0.8), Ll, Ll * 0.55, "apple_leaf",
                                    droop=0.5, segs=3, profile="ovate", across=3, fold=0.3)
                if stage == "blossom" and rng.random() < 0.7:
                    for f in range(rng.randint(2, 5)):
                        fp = p + Vector((rng.uniform(-.03, .03), rng.uniform(-.03, .03), rng.uniform(0, .03)))
                        pk.flower(mb, fp, (rng.uniform(-.5, .5), rng.uniform(-.5, .5), 1), 0.016, "apple_blossom", None, segs=1)
                elif stage in ("fruitlet", "harvest") and rng.random() < (0.22 if stage == "harvest" else 0.3):
                    r = rng.uniform(0.035, 0.045) if stage == "harvest" else rng.uniform(0.01, 0.016)
                    c = p + Vector((rng.uniform(-.03, .03), rng.uniform(-.03, .03), -r - 0.01))
                    if stage == "harvest":
                        ripeness = rng.uniform(0.75, 1.0)
                        mat = "apple_fruit_red" if rng.random() < 0.85 else "apple_fruit_green"
                    else:
                        ripeness, mat = 0.1, "apple_fruit_green"
                    mk.ellipsoid(mb, c, (r, r, r * 0.9), mat, u=10, v=7, squash_top=0.1)
                    mk.tube(mb, [c + Vector((0, 0, r * 0.85)), c + Vector((0, 0, r * 0.85 + 0.015))], 0.0012, "apple_bark", sides=3)
                    pm.add_fruit(c, r, "apple", ripeness=ripeness)
        return pm


# =================================================================== cotton
@register
class Cotton(Crop):
    name = "cotton"
    display = "Cotton"
    stages = {
        "squaring": dict(bbch="51", desc="square (bud) formation, ~70 cm"),
        "open_boll": dict(bbch="89", desc="defoliated, open bolls, harvest ready"),
    }
    layout = dict(row_spacing=0.96, plant_spacing=0.12, unit="plant")

    def materials(self, stage, opts):
        return {
            "cot_leaf": L("#3f7a35", "#4a8a3a", roughness=0.45),
            "cot_leaf_dry": L("#5a4030", "#7a5a38", roughness=0.85, translucency=0.05),
            "cot_stem": P("#7a5040", "#6a8a3a"),
            "cot_stem_dry": P("#5a3e2c", "#4a3424", roughness=0.85),
            "cot_square": P("#7aa04a", semantic="crop_flower"),
            "cot_lint": P("#f6f4ee", "#ecebe4", semantic="crop_produce", roughness=0.95, sheen=1.0, sss=0.3),
            "cot_burr": P("#4a3220", semantic="crop_stem", roughness=0.85),
        }

    def build(self, stage, rng, opts):
        pm = PlantModel()
        mb = pm.mb
        dry = stage == "open_boll"
        H = rng.uniform(0.65, 0.95)
        stem_m = "cot_stem_dry" if dry else "cot_stem"
        pts = [Vector((rng.uniform(-.01, .01) * i, rng.uniform(-.01, .01) * i, H * i / 5)) for i in range(6)]
        mk.tube(mb, pts, [0.008 * (1 - 0.6 * i / 5) + 0.001 for i in range(6)], stem_m, sides=5)
        yaw = rng.uniform(0, 6.28)
        nb = rng.randint(7, 11)
        for b in range(nb):
            t = 0.2 + 0.75 * b / nb
            yaw += 2.4
            p = Vector((0, 0, H * t))
            length = (0.35 - 0.25 * t) * rng.uniform(0.8, 1.2)
            tip, d = pk.stem_arc(mb, p, yaw, 0.5, length, 0.4, 0.004, 0.002, stem_m, segs=3)
            nodes = [p.lerp(tip, f) for f in (0.35, 0.7, 1.0)]
            if not dry:
                pk.palmate(mb, rng, p, yaw + 2.0, 0.8, 0.08, rng.uniform(0.09, 0.13), "cot_leaf", stem_m, lobes=3,
                           spread=0.8, stem_r=0.0015, blade_elev=0.25, droop=0.4, profile="heart")
            for q in nodes:
                if not dry or rng.random() < 0.08:
                    pk.palmate(mb, rng, q, yaw + rng.uniform(-1, 1), 0.6, 0.07, rng.uniform(0.09, 0.13),
                               "cot_leaf_dry" if dry else "cot_leaf", stem_m, lobes=3, spread=0.8,
                               stem_r=0.0015, blade_elev=0.2, droop=0.4, profile="heart")
                if dry and rng.random() < 0.8:
                    c = q + Vector((0, 0, 0.02))
                    for k in range(4):
                        a = k * 1.57 + rng.uniform(-0.2, 0.2)
                        lc = c + Vector((math.cos(a) * 0.014, math.sin(a) * 0.014, 0.008))
                        mk.ellipsoid(mb, lc, (0.016, 0.016, 0.02), "cot_lint", u=7, v=5, jitter=0.12, rng=rng)
                    for k in range(4):
                        a = k * 1.57 + 0.78
                        mk.leaf(mb, c - Vector((0, 0, 0.005)), a, -0.2, 0.03, 0.02, "cot_burr", droop=-0.6, segs=2, profile="ovate")
                    pm.add_fruit(c + Vector((0, 0, 0.01)), 0.035, "boll", ripeness=1.0)
                elif not dry and rng.random() < 0.5:
                    mk.ellipsoid(mb, q + Vector((0, 0, 0.01)), (0.008, 0.008, 0.012), "cot_square", u=5, v=4)
            if not dry:
                pk.palmate(mb, rng, tip, yaw, 0.7, 0.06, rng.uniform(0.09, 0.12), "cot_leaf", stem_m, lobes=3,
                           spread=0.8, stem_r=0.0015, blade_elev=0.25, droop=0.4, profile="heart")
        return pm


# ==================================================================== onion
@register
class Onion(Crop):
    name = "onion"
    display = "Onion"
    stages = {
        "vegetative": dict(bbch="16", desc="6 upright tubular leaves, ~40 cm"),
        "bulbing": dict(bbch="47", desc="bulbs swelling above soil, tops falling over"),
    }
    layout = dict(row_spacing=0.3, plant_spacing=0.1, unit="plant",
                  bed=dict(width=1.5, height=0.1, top=1.2, rows=4))

    def materials(self, stage, opts):
        return {
            "onion_leaf": P("#5a8a50", "#4f7f48", semantic="crop_foliage", roughness=0.35, coat=0.2),
            "onion_leaf_tip": P("#b8a860", semantic="crop_foliage", roughness=0.6),
            "onion_bulb": P("#c9a060", "#b88a48", semantic="crop_produce", roughness=0.45, sheen=0.3),
        }

    def build(self, stage, rng, opts):
        pm = PlantModel()
        mb = pm.mb
        bulbing = stage == "bulbing"
        br = rng.uniform(0.03, 0.045) if bulbing else 0.012
        if bulbing:
            mk.ellipsoid(mb, Vector((0, 0, br * 0.4)), (br, br, br * 0.85), "onion_bulb", u=10, v=7)
            pm.add_fruit((0, 0, br * 0.4), br, "bulb", ripeness=0.8)
        neck = Vector((0, 0, br * 1.1 if bulbing else 0.02))
        n = rng.randint(5, 8)
        for k in range(n):
            yaw = rng.uniform(0, 6.28)
            fall = bulbing and rng.random() < 0.6
            elev = rng.uniform(1.25, 1.5) if not fall else rng.uniform(0.2, 0.6)
            L_ = rng.uniform(0.3, 0.45)
            pts = mk.polyline_arc(neck, yaw, elev, L_, rng.uniform(0.3, 0.9) + (1.0 if fall else 0), 6)
            radii = [0.005 * (1 - i / 7) + 0.0008 for i in range(7)]
            mk.tube(mb, pts[:5], radii[:5], "onion_leaf", sides=5)
            mk.tube(mb, pts[4:], radii[4:], "onion_leaf_tip" if bulbing else "onion_leaf", sides=5, cap_end=True)
        return pm


# =================================================================== carrot
@register
class Carrot(Crop):
    name = "carrot"
    display = "Carrot"
    stages = {
        "seedling": dict(bbch="12", desc="first true leaves, ~6 cm", petioles=3, h=0.06),
        "vegetative": dict(bbch="45", desc="full feathery canopy, ~30 cm, shoulders visible", petioles=14, h=0.3),
    }
    layout = dict(row_spacing=0.25, plant_spacing=0.06, unit="plant",
                  bed=dict(width=1.5, height=0.12, top=1.1, rows=4))

    def materials(self, stage, opts):
        return {
            "carrot_leaf": L("#3f7a2a", "#4a8a30", roughness=0.5),
            "carrot_stem": P("#6a9a40"),
            "carrot_root": P("#e07020", "#d06018", semantic="crop_produce", roughness=0.5),
        }

    def build(self, stage, rng, opts):
        s = self.stage_info(stage)
        pm = PlantModel()
        mb = pm.mb
        for k in range(s["petioles"] + rng.randint(-1, 2)):
            yaw = rng.uniform(0, 6.28)
            L_ = s["h"] * rng.uniform(0.75, 1.15)
            pk.pinnate(mb, rng, Vector((0, 0, 0.005)), yaw, rng.uniform(1.0, 1.4), L_, 3 if stage == "vegetative" else 2,
                       0.03 + 0.035 * (L_ / 0.3), 0.008 + 0.006 * (L_ / 0.3), "carrot_leaf", "carrot_stem",
                       bend=0.9, leaflet_droop=0.3, stem_r=0.0012, profile="lanceolate", minor=2 if stage == "vegetative" else 0)
        if stage == "vegetative":
            r = rng.uniform(0.012, 0.018)
            mk.ellipsoid(mb, Vector((0, 0, 0.0)), (r, r, r * 1.2), "carrot_root", u=8, v=5)
            pm.add_fruit((0, 0, 0), r, "root_shoulder", ripeness=0.7)
        return pm


# ================================================================== pumpkin
@register
class Pumpkin(Crop):
    name = "pumpkin"
    display = "Pumpkin"
    stages = {
        "vining": dict(bbch="35", desc="vines running, large leaves"),
        "fruiting": dict(bbch="87", desc="orange fruit on vines, harvest ready"),
    }
    layout = dict(row_spacing=2.0, plant_spacing=1.4, unit="plant")
    variants = 4

    def materials(self, stage, opts):
        return {
            "pk_leaf": L("#3f6f2a", "#4a7a30", roughness=0.55, sheen=0.4),
            "pk_leaf_old": L("#8a9a40", "#9aa848", roughness=0.6),
            "pk_vine": P("#6a8a3a", roughness=0.6, sheen=0.4),
            "pk_fruit": P("#e07a1a", "#d06a10", semantic="crop_produce", roughness=0.4, coat=0.2),
            "pk_fruit_green": P("#4a6a2a", semantic="crop_produce", roughness=0.4),
            "pk_flower": P("#f0a818", semantic="crop_flower"),
        }

    def build(self, stage, rng, opts):
        pm = PlantModel()
        mb = pm.mb
        for v in range(rng.randint(2, 3)):
            yaw = rng.uniform(0, 6.28)
            length = rng.uniform(1.2, 2.0)
            pts = [Vector((0, 0, 0.02))]
            p = pts[0].copy()
            for i in range(14):
                yaw += rng.uniform(-0.35, 0.35)
                p = p + Vector((math.cos(yaw), math.sin(yaw), 0)) * (length / 14)
                p.z = 0.02
                pts.append(p.copy())
            mk.tube(mb, pts, 0.008, "pk_vine", sides=5)
            for i in range(1, 14, 2):
                q = pts[i]
                ly = yaw + rng.uniform(-2, 2)
                lm = "pk_leaf_old" if (stage == "fruiting" and rng.random() < 0.3) else "pk_leaf"
                pk.palmate(mb, rng, q, ly, 1.25, rng.uniform(0.25, 0.4), rng.uniform(0.2, 0.27), lm, "pk_vine",
                           lobes=5, spread=1.3, stem_r=0.005, petiole_bend=1.1, blade_elev=0.25, droop=0.5,
                           cup=-0.1, wave=0.06, profile="round")
                if stage == "vining" and rng.random() < 0.3:
                    pk.flower(mb, q + Vector((0, 0, 0.05)), (0, 0, 1), 0.05, "pk_flower", None, segs=2)
            if stage == "fruiting" and rng.random() < 0.8:
                q = pts[rng.randint(5, 12)]
                r = rng.uniform(0.13, 0.2)
                green = rng.random() < 0.1
                c = Vector((q.x + 0.05, q.y + 0.05, r * 0.82))
                mk.ellipsoid(mb, c, (r, r, r * 0.82), "pk_fruit_green" if green else "pk_fruit", u=24, v=10, rib=0.12, ribs=12)
                mk.tube(mb, [c + Vector((0, 0, r * 0.7)), c + Vector((0.02, 0, r * 0.95))], 0.012, "pk_vine", sides=5)
                pm.add_fruit(c, r, "pumpkin", ripeness=0.3 if green else 1.0)
        return pm


def list_crops():
    out = []
    for name, c in CROPS.items():
        out.append({
            "crop": name,
            "display": c.display,
            "stages": {k: {"bbch": v.get("bbch"), "desc": v.get("desc")} for k, v in c.stages.items()},
            "layout": {k: v for k, v in c.layout.items()},
        })
    return out
