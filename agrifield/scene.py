"""Assemble a complete field scene from a scenario description."""

import math
import random
import time

import bpy
import numpy as np
from mathutils import Euler, Vector

from . import crops as crops_mod
from . import environment
from . import materials as matmod
from . import meshkit as mk
from . import props
from . import semantics
from . import terrain as terrain_mod
from . import weeds as weeds_mod


def _seed(*parts):
    h = 1469598103934665603
    for p in parts:
        for ch in str(p):
            h = ((h ^ ord(ch)) * 1099511628211) & 0xFFFFFFFFFFFF
    return h


class Registry:
    """Keeps every annotated object (instance id -> record)."""

    def __init__(self):
        self.records = []
        self.next_id = 1

    def new_id(self):
        iid = self.next_id
        self.next_id += 1
        return iid


class FieldScene:
    def __init__(self, scenario, seed=None, terrain_res=None, log=print):
        self.sc = scenario
        self.seed = scenario.get("seed", 0) if seed is None else seed
        self.log = log
        self.terrain_res = terrain_res or scenario.get("terrain", {}).get("resolution", 0.04)
        self.reg = Registry()
        self.lib = matmod.MaterialLibrary()
        self.rows = []
        self.variant_cache = {}
        self.stats = {}

    # ----------------------------------------------------------- helpers
    def rng(self, *tag):
        return random.Random(_seed(self.seed, *tag))

    def coll(self, name):
        c = bpy.data.collections.get(name)
        if c is None:
            c = bpy.data.collections.new(name)
            self.scene.collection.children.link(c)
        return c

    def mesh_from_model(self, name, pm, smooth=True):
        self.lib.register(self._all_specs)
        mesh = pm.mb.build(name, self.lib.resolve(pm.mb.mats), smooth=smooth)
        matmod.tag_mesh_semantics(mesh)
        return mesh

    def add_object(self, name, mesh, loc, yaw=0.0, scale=1.0, coll="AF_Props", tilt=(0.0, 0.0),
                   instance=None):
        obj = bpy.data.objects.new(name, mesh)
        obj.location = loc
        obj.rotation_euler = Euler((tilt[0], tilt[1], yaw), "XYZ")
        obj.scale = (scale, scale, scale)
        iid = 0
        if instance is not None:
            iid = self.reg.new_id()
            instance["instance_id"] = iid
            self.reg.records.append(instance)
        obj.pass_index = iid
        obj.color = semantics.encode_instance(iid) + (1.0,)
        obj["af_instance_id"] = iid
        self.coll(coll).objects.link(obj)
        return obj

    def _world_bbox(self, obj, local_min, local_max):
        mw = obj.matrix_world
        cs = [mw @ Vector((x, y, z)) for x in (local_min[0], local_max[0])
              for y in (local_min[1], local_max[1]) for z in (local_min[2], local_max[2])]
        lo = [min(c[i] for c in cs) for i in range(3)]
        hi = [max(c[i] for c in cs) for i in range(3)]
        return [round(v, 4) for v in lo], [round(v, 4) for v in hi]

    # ------------------------------------------------------------ layout
    def _layout(self):
        sc = self.sc
        W, Lf = sc["field"]["width"], sc["field"]["length"]
        entries = sc["crops"]
        first = entries[0]
        crop0 = crops_mod.CROPS[first["crop"]]
        lay = dict(crop0.layout)
        lay.update({k: v for k, v in first.items() if k in ("row_spacing", "plant_spacing", "bed", "ridge")})
        tcfg = sc.get("terrain", {})
        profile = dict(kind="flat", row_ridge=tcfg.get("row_ridge", 0.02))
        bed_u = []
        row_u = []
        bed_of_row = []
        if tcfg.get("paddy"):
            profile = dict(kind="paddy")
        bed = tcfg.get("bed", lay.get("bed"))
        ridge = tcfg.get("ridge", lay.get("ridge"))
        if bed and not tcfg.get("paddy"):
            pitch = bed["width"]
            nb = max(1, int((W - 0.3) // pitch))
            start = (W - nb * pitch) / 2 + pitch / 2
            bed_u = [start + j * pitch for j in range(nb)]
            rows_per = bed.get("rows", 1)
            rs = lay["row_spacing"]
            for j, b in enumerate(bed_u):
                for i in range(rows_per):
                    row_u.append(b + (i - (rows_per - 1) / 2) * rs)
                    bed_of_row.append(j)
            profile = dict(kind="beds", width=pitch, top=bed["top"], height=bed["height"])
        else:
            rs = lay["row_spacing"]
            n = max(1, int((W - 0.4) // rs) + 1)
            start = (W - (n - 1) * rs) / 2
            row_u = [start + i * rs for i in range(n)]
            bed_of_row = [None] * n
            if ridge and not tcfg.get("paddy"):
                profile = dict(kind="ridges", width=ridge["width"], height=ridge["height"])
        self.layout = lay
        self.row_u = row_u
        self.bed_u = bed_u
        self.bed_of_row = bed_of_row
        self.profile = profile
        if tcfg.get("mulch", lay.get("mulch")) and "roughness" not in tcfg:
            tcfg = dict(tcfg, roughness=0.002)  # shaped beds under film are smooth
        self.terrain = terrain_mod.Terrain(tcfg, W, Lf, profile, row_u, bed_u, _seed(self.seed, "terrain"))

    # ------------------------------------------------------------ build
    def build(self):
        t0 = time.time()
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene = bpy.context.scene
        self.scene.name = self.sc["name"]
        self._all_specs = {}
        self._all_specs.update(props.materials())
        self._all_specs.update(weeds_mod.materials())
        for e in self.sc["crops"]:
            c = crops_mod.CROPS[e["crop"]]
            for st in self._stages_of(e):
                self._all_specs.update(c.materials(st, e.get("opts", {})))
        self.lib.register(self._all_specs)
        self._layout()
        self._build_terrain()
        self._build_beds_extras()
        self._build_crops()
        self._build_ground_cover()
        self._build_weeds()
        self._build_props()
        self._build_background()
        W, Lf = self.sc["field"]["width"], self.sc["field"]["length"]
        self.env = environment.setup(self.scene, self.sc.get("environment", {}), (W / 2, Lf / 2))
        self.stats["build_seconds"] = round(time.time() - t0, 1)
        self.stats["objects"] = len(bpy.data.objects)
        self.stats["instances"] = len(self.reg.records)
        self.stats["faces_unique"] = sum(len(m.polygons) for m in bpy.data.meshes)
        self.log("  built %s: %d objects, %d annotated instances, %.1fs" % (
            self.sc["name"], self.stats["objects"], self.stats["instances"], self.stats["build_seconds"]))
        return self

    def _stages_of(self, entry):
        mix = entry.get("stage_mix")
        return list(mix.keys()) if mix else [entry["stage"]]

    # ------------------------------------------------------------ terrain
    def _build_terrain(self):
        tcfg = self.sc.get("terrain", {})
        soil = tcfg.get("soil", "loam")
        dark, light = terrain_mod.SOILS[soil]
        wet = tcfg.get("wetness", 0.15)
        self._all_specs["soil"] = dict(kind="soil", dark=dark, light=light, wetness=wet)
        head = tcfg.get("headland", "soil")
        if head == "grass":
            self._all_specs["headland"] = dict(kind="soil", dark="#3a4a22", light="#6a7a3a", wetness=0.1,
                                               semantic="ground_cover", clod_scale=40.0)
        else:
            self._all_specs["headland"] = dict(kind="soil", dark=dark, light=light, wetness=max(0.0, wet - 0.1))
        self.lib.register(self._all_specs)
        (xs, ys, z), (oxs, oys, oz) = self.terrain.build_meshes(res=self.terrain_res)
        me = mk.grid_mesh("AF_Terrain", xs, ys, z, [self.lib["soil"]])
        matmod.tag_mesh_semantics(me)
        o = bpy.data.objects.new("AF_Terrain", me)
        o.color = (0, 0, 0, 1)
        self.coll("AF_Terrain").objects.link(o)
        me2 = mk.grid_mesh("AF_Apron", oxs, oys, oz, [self.lib["headland"]])
        matmod.tag_mesh_semantics(me2)
        o2 = bpy.data.objects.new("AF_Apron", me2)
        o2.color = (0, 0, 0, 1)
        self.coll("AF_Terrain").objects.link(o2)
        self.stats["terrain_vertices"] = len(me.vertices)

    def _strip_mesh(self, name, u_center, half_w, z_off, mat_key, wrinkle=0.0, rng=None, res_u=0.05, res_y=0.1,
                    follow=True):
        W, Lf = self.sc["field"]["width"], self.sc["field"]["length"]
        us = np.linspace(-half_w, half_w, max(3, int(2 * half_w / res_u) + 1))
        ys = np.linspace(-0.2, Lf + 0.2, int((Lf + 0.4) / res_y) + 1)
        gu, gy = np.meshgrid(us, ys)
        gx = u_center + gu + self.terrain.curve(gy)
        gz = self.terrain.height(gx, gy) + z_off
        if wrinkle and rng is not None:
            rs = np.random.default_rng(rng.randint(0, 1 << 30))
            gz = gz + rs.normal(0, wrinkle, gz.shape) * (np.abs(gu) < half_w * 0.85)
        me = bpy.data.meshes.new(name)
        verts = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], 1)
        nu, ny = len(us), len(ys)
        idx = np.arange(nu * ny).reshape(ny, nu)
        quads = np.stack([idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()], 1)
        me.from_pydata(verts.tolist(), [], quads.tolist())
        me.materials.append(self.lib[mat_key])
        me.shade_smooth()
        matmod.tag_mesh_semantics(me)
        return me

    def _build_beds_extras(self):
        """Plastic mulch, drip tape, paddy water, puddles."""
        tcfg = self.sc.get("terrain", {})
        mulch = tcfg.get("mulch", self.layout.get("mulch"))
        rng = self.rng("beds")
        if mulch and self.bed_u:
            key = {"black": "mulch_black", "white": "mulch_white", "silver": "mulch_silver"}[mulch]
            half = self.profile["top"] / 2 + 0.06
            for j, b in enumerate(self.bed_u):
                me = self._strip_mesh("AF_Mulch_%d" % j, b, half, 2.5 * self.terrain.micro + 0.003, key,
                                      wrinkle=0.002, rng=rng)
                o = bpy.data.objects.new(me.name, me)
                o.color = (0, 0, 0, 1)
                self.coll("AF_Beds").objects.link(o)
        if tcfg.get("paddy"):
            W, Lf = self.sc["field"]["width"], self.sc["field"]["length"]
            lvl = tcfg.get("water_level", 0.06)
            self._all_specs["paddy_water"] = dict(kind="water", tint="#6a5a3a")
            self.lib.register(self._all_specs)
            mb = mk.MeshBuilder()
            zc = self.terrain.height1(W / 2, Lf / 2)
            mb.add([(-0.6, -0.6, 0), (W + 0.6, -0.6, 0), (W + 0.6, Lf + 0.6, 0), (-0.6, Lf + 0.6, 0)], [(0, 1, 2, 3)], "paddy_water")
            me = mb.build("AF_PaddyWater", self.lib.resolve(mb.mats), smooth=False)
            matmod.tag_mesh_semantics(me)
            o = bpy.data.objects.new("AF_PaddyWater", me)
            o.location = (0, 0, zc + lvl)
            o.color = (0, 0, 0, 1)
            self.coll("AF_Terrain").objects.link(o)
        np_ = tcfg.get("puddles", 0)
        if np_:
            self._all_specs["puddle"] = dict(kind="water", tint="#4a3a2a", roughness=0.02)
            self.lib.register(self._all_specs)
            W, Lf = self.sc["field"]["width"], self.sc["field"]["length"]
            gaps = [0.5 * (self.row_u[i] + self.row_u[i + 1]) for i in range(len(self.row_u) - 1)] or [W / 2]
            for k in range(np_):
                u = rng.choice(gaps)
                y = rng.uniform(1.0, Lf - 1.0)
                L_ = rng.uniform(0.6, 2.5)
                x = u + float(self.terrain.curve(y))
                zmin = min(self.terrain.height1(x + dx, y + dy) for dx in (-0.1, 0, 0.1) for dy in (-L_ / 3, 0, L_ / 3))
                mb = mk.MeshBuilder()
                n = 16
                pts = [(math.cos(2 * math.pi * i / n) * 0.45 * rng.uniform(0.8, 1.1),
                        math.sin(2 * math.pi * i / n) * L_ / 2 * rng.uniform(0.85, 1.1), 0) for i in range(n)]
                mb.add([(0, 0, 0)] + pts, [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)], "puddle")
                me = mb.build("AF_Puddle_%d" % k, self.lib.resolve(mb.mats), smooth=False)
                matmod.tag_mesh_semantics(me)
                o = bpy.data.objects.new(me.name, me)
                o.location = (x, y, zmin + 0.012)
                o.color = (0, 0, 0, 1)
                self.coll("AF_Terrain").objects.link(o)

    # -------------------------------------------------------------- crops
    def _variants(self, crop, stage, opts, count):
        key = (crop.name, stage, repr(sorted(opts.items())))
        if key in self.variant_cache:
            return self.variant_cache[key]
        out = []
        for v in range(count):
            rng = self.rng("variant", crop.name, stage, v, key[2])
            pm = crop.build(stage, rng, opts)
            me = self.mesh_from_model("%s_%s_v%d" % (crop.name, stage, v), pm)
            lo, hi = pm.mb.bounds()
            out.append(dict(mesh=me, fruits=pm.fruits, meta=pm.meta, lo=lo, hi=hi,
                            faces=pm.mb.face_count()))
        self.variant_cache[key] = out
        return out

    def _row_entry(self, ri):
        entries = self.sc["crops"]
        pattern = self.sc.get("row_pattern")
        if pattern:
            return entries[pattern[ri % len(pattern)]]
        return entries[0]

    def _build_crops(self):
        Lf = self.sc["field"]["length"]
        T = self.terrain
        self.crop_positions = []
        tram = self.sc.get("terrain", {}).get("tramlines", False)
        ruts = T.rut_offsets() if tram else []
        for ri, u in enumerate(self.row_u):
            entry = self._row_entry(ri)
            if ruts and min(abs(u - r) for r in ruts) < 0.13:
                self.rows.append(dict(row_id=ri, crop=entry["crop"], bed_id=None, u=round(u, 4), plants=0,
                                      tramline=True, polyline=[]))
                continue
            crop = crops_mod.CROPS[entry["crop"]]
            lay = dict(crop.layout)
            lay.update({k: v for k, v in entry.items() if k in ("row_spacing", "plant_spacing")})
            unit = lay.get("unit", "plant")
            spacing = lay["plant_spacing"]
            opts = dict(entry.get("opts", {}))
            if unit == "segment":
                opts.setdefault("segment_length", spacing)
                for k in ("stems_per_m",):
                    if k in lay:
                        opts.setdefault(k, lay[k])
            stage_mix = entry.get("stage_mix") or {entry["stage"]: 1.0}
            stage_keys = list(stage_mix.keys())
            stage_w = [stage_mix[k] for k in stage_keys]
            nvar = entry.get("variants", crop.variants)
            vsets = {st: self._variants(crop, st, opts, nvar) for st in stage_keys}
            rng = self.rng("row", ri)
            gap_rate = entry.get("gap_rate", 0.03)
            size_cv = entry.get("size_cv", 0.12)
            stunted = entry.get("stunted_rate", 0.03)
            pts = []
            y = spacing * rng.uniform(0.3, 0.7) + entry.get("row_start", 0.0)
            in_gap = False
            idx = 0
            row_rec = dict(row_id=ri, crop=crop.name, bed_id=self.bed_of_row[ri], u=round(u, 4), plants=0)
            while y < Lf - entry.get("row_end", 0.0) - spacing * 0.2:
                yy = y + (rng.gauss(0, spacing * 0.08) if unit != "segment" else 0.0)
                y += spacing
                if in_gap:
                    in_gap = rng.random() < 0.45
                else:
                    in_gap = rng.random() < gap_rate
                if in_gap:
                    continue
                lat = rng.gauss(0, entry.get("lateral_jitter", 0.012 if unit != "segment" else 0.004))
                x = u + float(T.curve(yy)) + lat
                z = T.height1(x, yy)
                st = rng.choices(stage_keys, stage_w)[0]
                var_i = rng.randrange(len(vsets[st]))
                var = vsets[st][var_i]
                heading = -math.atan(T.curve_slope(yy))
                yaw = heading + (rng.uniform(-0.08, 0.08) if unit == "segment" else rng.uniform(0, 2 * math.pi))
                sc = math.exp(rng.gauss(0, size_cv))
                if rng.random() < stunted:
                    sc *= rng.uniform(0.45, 0.7)
                sc = max(0.35, min(1.6, sc))
                if unit == "segment":
                    sc = max(0.85, min(1.15, sc))
                tilt = (rng.gauss(0, 0.03), rng.gauss(0, 0.03))
                rec = dict(category="crop", label=crop.name, crop=crop.name, stage=st, unit=unit,
                           row_id=ri, index_in_row=idx, variant=var_i,
                           position=[round(x, 4), round(yy, 4), round(z, 4)], yaw=round(yaw, 4), scale=round(sc, 4))
                obj = self.add_object("crop_%s_r%03d_%04d" % (crop.name, ri, idx), var["mesh"], (x, yy, z), yaw, sc,
                                      coll="AF_Crops", tilt=tilt, instance=rec)
                obj.matrix_world = obj.matrix_basis  # make matrix_world valid without depsgraph update
                rec["bbox3d"] = self._world_bbox(obj, var["lo"], var["hi"])
                rec["height"] = round(var["hi"][2] * sc, 4)
                rec["canopy_radius"] = round(max(abs(var["lo"][0]), abs(var["hi"][0]), abs(var["lo"][1]), abs(var["hi"][1])) * sc, 4)
                if var["meta"]:
                    rec["meta"] = var["meta"]
                if crop.record_fruits and var["fruits"]:
                    mw = obj.matrix_world
                    fr = []
                    for f in var["fruits"]:
                        g = dict(f)
                        g["pos"] = [round(c, 4) for c in (mw @ Vector(f["pos"]))]
                        g["radius"] = round(f["radius"] * sc, 4)
                        fr.append(g)
                    rec["fruits"] = fr
                self.crop_positions.append((x, yy, rec["canopy_radius"]))
                idx += 1
            row_rec["plants"] = idx
            ys = np.linspace(0, Lf, max(2, int(Lf / 0.5) + 1))
            row_rec["polyline"] = [[round(u + float(T.curve(yv)), 4), round(float(yv), 4), round(T.height1(u + float(T.curve(yv)), yv), 4)] for yv in ys]
            self.rows.append(row_rec)
        self.stats["crop_instances"] = len(self.crop_positions)

    # -------------------------------------------------------------- weeds
    def _build_weeds(self):
        wc = self.sc.get("weeds")
        if not wc or wc.get("density", 0) <= 0:
            return
        rng = self.rng("weeds")
        W, Lf = self.sc["field"]["width"], self.sc["field"]["length"]
        T = self.terrain
        species = wc.get("species", {"pigweed": 1, "crabgrass": 1})
        stages = wc.get("stages", {wc.get("stage", "small"): 1.0})
        sp_keys, sp_w = list(species.keys()), list(species.values())
        st_keys, st_w = list(stages.keys()), list(stages.values())
        variants = {}
        for s in sp_keys:
            for st in st_keys:
                vs = []
                for v in range(4):
                    pm = weeds_mod.build(s, st, self.rng("weedvar", s, st, v))
                    lo, hi = pm.mb.bounds()
                    vs.append(dict(mesh=self.mesh_from_model("weed_%s_%s_v%d" % (s, st, v), pm), lo=lo, hi=hi))
                variants[(s, st)] = vs
        u0 = min(self.row_u) - 0.3
        u1 = max(self.row_u) + 0.3
        area = (u1 - u0) * Lf
        n = int(wc["density"] * area)
        patch_frac = wc.get("patchiness", 0.4)
        intra = wc.get("intra_row", 0.3)
        centers = [(rng.uniform(u0, u1), rng.uniform(0, Lf)) for _ in range(max(1, n // 25))]
        mulch = self.sc.get("terrain", {}).get("mulch", self.layout.get("mulch"))
        placed = 0
        tries = 0
        while placed < n and tries < n * 6:
            tries += 1
            r = rng.random()
            if r < intra:
                ui = rng.choice(self.row_u)
                yv = rng.uniform(0, Lf)
                u = ui + rng.gauss(0, 0.035)
            elif r < intra + patch_frac:
                cu, cy = rng.choice(centers)
                u, yv = cu + rng.gauss(0, 0.5), cy + rng.gauss(0, 0.7)
            else:
                u, yv = rng.uniform(u0, u1), rng.uniform(0, Lf)
            if not (u0 <= u <= u1 and 0 <= yv <= Lf):
                continue
            if mulch and self.bed_u:
                d = min(abs(u - b) for b in self.bed_u)
                on_bed = d < self.profile["top"] / 2 + 0.06
                near_row = min(abs(u - ru) for ru in self.row_u) < 0.06
                if on_bed and not near_row:
                    continue
            x = u + float(T.curve(yv))
            z = T.height1(x, yv)
            s = rng.choices(sp_keys, sp_w)[0]
            st = rng.choices(st_keys, st_w)[0]
            vi = rng.randrange(4)
            var = variants[(s, st)][vi]
            rec = dict(category="weed", label="weed_" + s, species=s, stage=st, variant=vi,
                       position=[round(x, 4), round(yv, 4), round(z, 4)])
            sc = math.exp(rng.gauss(0, 0.15))
            obj = self.add_object("weed_%s_%04d" % (s, placed), var["mesh"], (x, yv, z), rng.uniform(0, 6.28), sc,
                                  coll="AF_Weeds", instance=rec)
            obj.matrix_world = obj.matrix_basis
            rec["bbox3d"] = self._world_bbox(obj, var["lo"], var["hi"])
            rec["scale"] = round(sc, 3)
            placed += 1
        self.stats["weed_instances"] = placed

    # -------------------------------------------------------- ground cover
    def _build_ground_cover(self):
        gc = self.sc.get("ground_cover")
        if not gc:
            return
        rng = self.rng("cover")
        W, Lf = self.sc["field"]["width"], self.sc["field"]["length"]
        T = self.terrain
        size = gc.get("patch", 0.4)
        vs = []
        for v in range(4):
            pm = weeds_mod.build_cover_patch(self.rng("covervar", v), size=size, density=gc.get("density", 1.0),
                                             dry=gc.get("dry", False), height=gc.get("height", 0.12))
            vs.append(self.mesh_from_model("cover_v%d" % v, pm))
        clear = gc.get("row_clearance", 0.45)
        count = 0
        for u in np.arange(-1.5, W + 1.5, size * 0.9):
            for y in np.arange(-1.5, Lf + 1.5, size * 0.9):
                uu = u + rng.uniform(-0.1, 0.1)
                yy = y + rng.uniform(-0.1, 0.1)
                inside = 0 <= yy <= Lf and min(self.row_u) - 0.5 <= uu <= max(self.row_u) + 0.5
                if inside and min(abs(uu - r) for r in self.row_u) < clear:
                    continue
                if not inside and not gc.get("headland", True):
                    continue
                if inside and gc.get("where", "alleys") == "headland":
                    continue
                if rng.random() > gc.get("coverage", 0.92):
                    continue
                x = uu + float(T.curve(yy))
                z = T.height1(x, yy)
                o = bpy.data.objects.new("cover_%05d" % count, rng.choice(vs))
                o.location = (x, yy, z)
                o.rotation_euler = (0, 0, rng.uniform(0, 6.28))
                o.color = (0, 0, 0, 1)
                self.coll("AF_GroundCover").objects.link(o)
                count += 1
        self.stats["ground_cover_patches"] = count

    # -------------------------------------------------------------- props
    def _path_points(self):
        if len(self.row_u) >= 2:
            return [0.5 * (self.row_u[i] + self.row_u[i + 1]) for i in range(len(self.row_u) - 1)]
        return [self.sc["field"]["width"] / 2]

    def _place_xy(self, rng, where):
        W, Lf = self.sc["field"]["width"], self.sc["field"]["length"]
        if where == "path":
            gaps = self._path_points()
            mid = gaps[len(gaps) // 2]
            u = rng.choice([mid] * 3 + gaps) + rng.gauss(0, 0.05)
            y = rng.uniform(3.0, Lf - 1.0)
        elif where == "headland":
            u = rng.uniform(-2.5, W + 2.5)
            y = rng.choice([rng.uniform(-3.0, -1.0), rng.uniform(Lf + 1.0, Lf + 3.0)])
        else:
            u = rng.uniform(min(self.row_u), max(self.row_u))
            y = rng.uniform(0.5, Lf - 0.5)
        return u + float(self.terrain.curve(y)), y

    def _single(self, name, pm, x, y, yaw, category, label, extra=None, coll="AF_Props", annotate=True):
        me = self.mesh_from_model(name, pm)
        z = self.terrain.height1(x, y)
        rec = None
        if annotate:
            rec = dict(category=category, label=label, position=[round(x, 4), round(y, 4), round(z, 4)], yaw=round(yaw, 4))
            if extra:
                rec.update(extra)
        obj = self.add_object(name, me, (x, y, z), yaw, 1.0, coll=coll, instance=rec)
        if rec is not None:
            obj.matrix_world = obj.matrix_basis
            lo, hi = pm.mb.bounds()
            rec["bbox3d"] = self._world_bbox(obj, lo, hi)
        return obj

    def _build_props(self):
        T = self.terrain
        Lf = self.sc["field"]["length"]
        rng = self.rng("props")
        plist = list(self.sc.get("props", []))
        # crop-implied infrastructure
        crop0 = crops_mod.CROPS[self.sc["crops"][0]["crop"]]
        if "trellis" in crop0.layout and not any(p["type"] == "trellis" for p in plist):
            plist.append(dict(type="trellis"))
        for p in plist:
            t = p["type"]
            if t == "trellis":
                tl = dict(crop0.layout.get("trellis", dict(post_every=6, wires=(0.8, 1.2))))
                tl.update({k: v for k, v in p.items() if k != "type"})
                spacing = crop0.layout["plant_spacing"]
                post_gap = spacing * tl["post_every"]
                post_h = max(tl["wires"]) + 0.15
                post_pm = props.post(post_h, 0.045 if post_h < 2.5 else 0.06)
                post_me = self.mesh_from_model("trellis_post", post_pm)
                for ri, u in enumerate(self.row_u):
                    ys = list(np.arange(0.0, Lf + 1e-6, post_gap))
                    for k, y in enumerate(ys):
                        x = u + float(T.curve(y))
                        z = T.height1(x, y)
                        rec = dict(category="structure", label="trellis_post", row_id=ri,
                                   position=[round(x, 4), round(y, 4), round(z, 4)])
                        self.add_object("post_r%02d_%02d" % (ri, k), post_me, (x, y, z), 0.0, 1.0, coll="AF_Structures", instance=rec)
                        rec["bbox3d"] = [[round(x - 0.06, 3), round(y - 0.06, 3), round(z, 3)], [round(x + 0.06, 3), round(y + 0.06, 3), round(z + post_h, 3)]]
                        if k + 1 < len(ys):
                            y2 = ys[k + 1]
                            x2 = u + float(T.curve(y2))
                            z2 = T.height1(x2, y2)
                            span = math.hypot(x2 - x, y2 - y)
                            wpm = props.wire_span(span, [h + (z2 - z) * 0 for h in tl["wires"]])
                            wme = self.mesh_from_model("wire_r%02d_%02d" % (ri, k), wpm)
                            o = bpy.data.objects.new(wme.name, wme)
                            o.location = (x, y, z)
                            o.rotation_euler = (math.atan2(z2 - z, span) * 1.0, 0, -math.atan2(x2 - x, y2 - y))
                            o.color = (0, 0, 0, 1)
                            self.coll("AF_Structures").objects.link(o)
            elif t == "stakes":
                stake_me = self.mesh_from_model("stake", props.stake(p.get("height", 1.8), p.get("material", "wood")))
                n = 0
                for rec in list(self.reg.records):
                    if rec.get("category") != "crop":
                        continue
                    if rng.random() > p.get("fraction", 1.0):
                        continue
                    x, y, z = rec["position"]
                    a = rng.uniform(0, 6.28)
                    sx, sy = x + 0.06 * math.cos(a), y + 0.06 * math.sin(a)
                    r2 = dict(category="structure", label="stake", parent_instance=rec["instance_id"],
                              position=[round(sx, 4), round(sy, 4), round(T.height1(sx, sy), 4)])
                    self.add_object("stake_%04d" % n, stake_me, (sx, sy, T.height1(sx, sy)), rng.uniform(-.2, .2), 1.0,
                                    coll="AF_Structures", tilt=(rng.gauss(0, 0.03), rng.gauss(0, 0.03)), instance=r2)
                    n += 1
            elif t == "drip_tape":
                targets = self.bed_u if (p.get("per_bed") and self.bed_u) else self.row_u
                for k, u in enumerate(targets):
                    off = p.get("offset", 0.06 if not p.get("per_bed") else 0.0)
                    me = self._strip_mesh("AF_Drip_%d" % k, u + off, 0.008, 0.008 if not self.sc.get("terrain", {}).get("mulch", self.layout.get("mulch")) else 0.012,
                                          "drip_tape", res_u=0.008, res_y=0.25)
                    o = bpy.data.objects.new(me.name, me)
                    o.color = (0, 0, 0, 1)
                    self.coll("AF_Irrigation").objects.link(o)
            elif t == "sprinklers":
                gaps = self._path_points()
                step = p.get("spacing", 12.0)
                for gi in range(0, len(gaps), max(1, int(step / max(0.3, self.layout["row_spacing"])))):
                    for y in np.arange(step / 2, Lf, step):
                        x = gaps[gi] + float(T.curve(y))
                        self._single("sprinkler_%d_%d" % (gi, int(y)), props.sprinkler(p.get("height", 0.9)), x, y, 0.0,
                                     "structure", "sprinkler")
            elif t == "rocks":
                n = p.get("count", 20)
                smin, smax = p.get("size", (0.04, 0.18))
                rme = [self.mesh_from_model("rock_v%d" % v, props.rock_model(self.rng("rock", v), 1.0)) for v in range(5)]
                for k in range(n):
                    x, y = self._place_xy(rng, p.get("where", "field"))
                    s = math.exp(rng.uniform(math.log(smin), math.log(smax)))
                    z = T.height1(x, y) - s * 0.15
                    rec = dict(category="rock", label="rock", size=round(s, 3), position=[round(x, 4), round(y, 4), round(z, 4)])
                    self.add_object("rock_%03d" % k, rng.choice(rme), (x, y, z), rng.uniform(0, 6.28), s, coll="AF_Props", instance=rec)
                    rec["bbox3d"] = [[round(x - s, 3), round(y - s, 3), round(z, 3)], [round(x + s, 3), round(y + s, 3), round(z + s * 0.7, 3)]]
            elif t in ("crates", "buckets", "tools", "hoses"):
                fn = {"crates": props.crate, "buckets": props.bucket, "tools": props.tool, "hoses": props.hose}[t]
                for k in range(p.get("count", 2)):
                    x, y = self._place_xy(rng, p.get("where", "path"))
                    self._single("%s_%02d" % (t[:-1], k), fn(self.rng(t, k)), x, y, rng.uniform(0, 6.28), "obstacle", t[:-1])
            elif t == "people":
                poses = p.get("poses", ["standing"])
                for k in range(p.get("count", 1)):
                    x, y = self._place_xy(rng, p.get("where", "path"))
                    pose = poses[k % len(poses)]
                    pm = props.person(self.rng("person", k), pose)
                    self._single("person_%02d" % k, pm, x, y, rng.uniform(0, 6.28), "person", "person",
                                 extra=dict(pose=pose, height=round(pm.meta["height"], 3)))
            elif t == "residue":
                dens = p.get("density", 1.0)
                vs = [self.mesh_from_model("straw_v%d" % v, props.straw_patch(self.rng("straw", v), 0.6, dens)) for v in range(4)]
                W = self.sc["field"]["width"]
                c = 0
                for u in np.arange(0.0, W, 0.5):
                    for y in np.arange(0.0, Lf, 0.5):
                        if rng.random() > p.get("coverage", 0.85):
                            continue
                        x = u + rng.uniform(-0.15, 0.15) + float(T.curve(y))
                        yy = y + rng.uniform(-0.15, 0.15)
                        o = bpy.data.objects.new("straw_%05d" % c, rng.choice(vs))
                        o.location = (x, yy, T.height1(x, yy))
                        o.rotation_euler = (0, 0, rng.uniform(0, 6.28))
                        o.color = (0, 0, 0, 1)
                        self.coll("AF_Residue").objects.link(o)
                        c += 1
            else:
                raise ValueError("unknown prop type %r" % t)

    def _build_background(self):
        bg = self.sc.get("environment", {}).get("background", "treeline")
        if bg in (None, "none"):
            return
        rng = self.rng("bg")
        W, Lf = self.sc["field"]["width"], self.sc["field"]["length"]
        vs = [self.mesh_from_model("tree_v%d" % v, props.tree_blob(self.rng("tree", v), 1.0)) for v in range(5)]
        n = 140
        for k in range(n):
            a = 2 * math.pi * k / n + rng.uniform(-0.02, 0.02)
            if bg == "partial" and math.sin(a) < 0.2:
                continue
            r = rng.uniform(70, 110)
            x = W / 2 + r * math.cos(a)
            y = Lf / 2 + r * math.sin(a)
            h = rng.uniform(8, 18)
            o = bpy.data.objects.new("bgtree_%03d" % k, rng.choice(vs))
            o.location = (x, y, float(self.terrain.base(x, y)) - 0.5)
            o.scale = (h, h, h)
            o.rotation_euler = (0, 0, rng.uniform(0, 6.28))
            o.color = (0, 0, 0, 1)
            self.coll("AF_Background").objects.link(o)

    # ------------------------------------------------------------ export
    def metadata(self):
        sc = self.sc
        crops_info = []
        for e in sc["crops"]:
            c = crops_mod.CROPS[e["crop"]]
            crops_info.append(dict(crop=c.name, display=c.display,
                                   stages={st: c.stages[st] for st in self._stages_of(e)}))
        return dict(
            scenario=sc,
            seed=self.seed,
            classes=semantics.class_table(),
            crops=crops_info,
            field=dict(width=sc["field"]["width"], length=sc["field"]["length"],
                       profile=self.profile, row_u=[round(u, 4) for u in self.row_u],
                       bed_u=[round(u, 4) for u in self.bed_u], coordinate_frame="z up, rows along +y, metres"),
            rows=self.rows,
            instances=self.reg.records,
            stats=self.stats,
        )
