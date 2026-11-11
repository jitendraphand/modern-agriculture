"""Build a furnished, lit house from a house scenario."""

import math
import random
import time

import bpy
import numpy as np
from mathutils import Euler, Vector

from agrifield import environment, semantics
from agrifield import meshkit as mk
from agrifield import props as agri_props
from agrifield.plantkit import PlantModel

from . import furniture as F
from . import layout, styles
from .classes import HOUSE_CLASSES

WALL_HALF = 0.1
FLOOR_BY_ROOM = {"living": "floor_wood", "dining": "floor_wood", "hallway": "floor_wood", "office": "floor_wood",
                 "kitchen": "floor_tile", "bathroom": "floor_tile", "laundry": "floor_tile",
                 "bedroom": "floor_carpet", "kids": "floor_carpet"}

# clutter per support type
SURFACE_ITEMS = {
    "kitchen_counter": ["mug", "cup", "bottle", "bowl", "plate", "fruit_bowl", "can"],
    "dining_table": ["plate", "cup", "bottle", "bowl", "vase", "mug", "fruit_bowl"],
    "coffee_table": ["remote", "book", "mug", "game_controller", "laptop", "phone", "vase", "cup"],
    "desk": ["laptop", "mug", "book", "phone", "keys", "can"],
    "nightstand": ["book", "phone", "glasses_case", "cup"],
    "default": ["book", "vase", "keys", "mug", "bottle"],
}
FLOOR_ITEMS = {
    "tidy": ["shoe", "backpack"],
    "kids": ["toy_block", "ball", "teddy", "toy_car", "toy_block", "ball", "book"],
    "laundry": ["clothes_pile", "laundry_basket", "clothes_pile", "shoe"],
    "moving": ["box", "box", "box", "backpack"],
    "party": ["bottle", "can", "cup", "bottle", "can", "clothes_pile"],
    "messy": ["shoe", "backpack", "clothes_pile", "book", "ball", "box", "laundry_basket", "toy_block"],
}


def _rect_overlap(a, b, m=0.0):
    return not (a[2] <= b[0] + m or b[2] <= a[0] + m or a[3] <= b[1] + m or b[3] <= a[1] + m)


class HouseScene:
    def __init__(self, sc, seed=None, log=print):
        self.sc = sc
        self.seed = sc.get("seed", 0) if seed is None else seed
        self.rng = random.Random(self.seed)
        self.log = log
        self.records = []
        self.next_id = 1
        self.occ = []          # world footprints (x0, y0, x1, y1, label)
        self.supports = []     # dict(rect world corners, z, kind, instance, room)
        self.lights = []
        self.stats = {}

    # ---------------------------------------------------------------- utils
    def coll(self, name):
        c = bpy.data.collections.get(name)
        if c is None:
            c = bpy.data.collections.new(name)
            self.scene.collection.children.link(c)
        return c

    def cid(self, name):
        return semantics.class_id(name)

    def add(self, name, pm, loc, yaw, cls, coll="HM_Furniture", record=None, part_roles=None, scale=1.0):
        mesh = pm.mb.build(name, self.lib.resolve(pm.mb.mats))
        mat_class = {}
        for role, c in (part_roles or {}).items():
            key = self.st.get(role)
            if isinstance(key, str):
                mat_class["HM_" + key] = self.cid(c)
        styles.tag(mesh, self.cid(cls) if cls else None, mat_class)
        obj = bpy.data.objects.new(name, mesh)
        obj.location = loc
        obj.rotation_euler = Euler((0, 0, yaw), "XYZ")
        obj.scale = (scale, scale, scale)
        iid = 0
        if record is not None:
            iid = self.next_id
            self.next_id += 1
            record["instance_id"] = iid
            record.setdefault("label", pm.meta.get("label", name))
            record["position"] = [round(v, 4) for v in loc]
            record["yaw"] = round(yaw, 4)
            self.records.append(record)
        obj.color = semantics.encode_instance(iid) + (1.0,)
        obj.pass_index = iid
        obj["af_instance_id"] = iid
        self.coll(coll).objects.link(obj)
        if record is not None:
            obj.matrix_world = obj.matrix_basis
            lo, hi = pm.mb.bounds()
            cs = [obj.matrix_world @ Vector((x, y, z)) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
            record["bbox3d"] = [[round(min(c[i] for c in cs), 4) for i in range(3)],
                                [round(max(c[i] for c in cs), 4) for i in range(3)]]
        return obj

    # --------------------------------------------------------------- build
    def build(self):
        t0 = time.time()
        bpy.ops.wm.read_factory_settings(use_empty=True)
        semantics.set_classes(HOUSE_CLASSES)
        self.scene = bpy.context.scene
        self.scene.name = self.sc["name"]
        sc = self.sc
        self.st, specs = styles.make(sc.get("style", "modern"), self.rng)
        self.st["glass_p"] = sc.get("glass_p", 0.2)
        self.lib = styles.Library()
        self.lib.register(specs)
        W, D = sc["house"]["width"], sc["house"]["depth"]
        self.W, self.D = W, D
        self.H = sc["house"].get("height", 2.6)
        program = sc["house"].get("rooms") or layout.PROGRAMS[sc["house"]["program"]]
        self.plan = layout.generate(W, D, program, self.rng, min_room=sc["house"].get("min_room", 2.3),
                                    open_plan=sc["house"].get("open_plan", False))
        self._shell()
        self._outside()
        for room in self.plan["rooms"]:
            self._furnish(room)
        self._clutter()
        self._agents()
        self._lights()
        env = dict(sc.get("environment", {}))
        env.setdefault("background", "none")
        self.env = environment.setup(self.scene, env, (W / 2, D / 2))
        self.stats.update(build_seconds=round(time.time() - t0, 1), objects=len(bpy.data.objects),
                          instances=len(self.records), rooms=len(self.plan["rooms"]))
        self.log("  built %s: %d rooms, %d objects, %d annotated instances, %.1fs" % (
            sc["name"], len(self.plan["rooms"]), len(bpy.data.objects), len(self.records), self.stats["build_seconds"]))
        return self

    # ---------------------------------------------------------------- shell
    def _shell(self):
        H = self.H
        rng = self.rng
        style = self.sc.get("style", "modern")
        for room in self.plan["rooms"]:
            R = room["rect"]
            fk = FLOOR_BY_ROOM.get(room["type"], "floor_wood")
            if style == "industrial" and fk == "floor_wood":
                fk = "floor_concrete"
            if self.sc.get("floor_override"):
                fk = self.sc["floor_override"]
            pm = PlantModel()
            mk.box(pm.mb, (R.cx, R.cy, -0.025), (R.w, R.d, 0.05), self.st[fk])
            self.add("floor_%s" % room["name"], pm, (0, 0, 0), 0.0, "floor", coll="HM_Structure",
                     record=dict(category="room", label="room_" + room["type"], room=room["name"],
                                 room_type=room["type"], area_m2=round(R.area, 2)))
            pm = PlantModel()
            mk.box(pm.mb, (R.cx, R.cy, H + 0.025), (R.w, R.d, 0.05), self.st["ceiling"])
            o = self.add("ceiling_%s" % room["name"], pm, (0, 0, 0), 0.0, "ceiling", coll="HM_Structure")
            o["hm_ceiling"] = True
        for wi, wall in enumerate(self.plan["walls"]):
            self._wall(wi, wall)

    def _wall(self, wi, wall):
        H = self.H
        t = 0.2 if wall.exterior else 0.1
        pm = PlantModel()
        mat = self.st["wall"]
        a, b = wall.a - (t / 2 if wall.exterior else 0), wall.b + (t / 2 if wall.exterior else 0)

        def piece(s0, s1, z0, z1):
            if s1 - s0 < 1e-3 or z1 - z0 < 1e-3:
                return
            if wall.axis == "x":
                mk.box(pm.mb, ((s0 + s1) / 2, wall.c, (z0 + z1) / 2), (s1 - s0, t, z1 - z0), mat)
            else:
                mk.box(pm.mb, (wall.c, (s0 + s1) / 2, (z0 + z1) / 2), (t, s1 - s0, z1 - z0), mat)

        cur = a
        for op in wall.openings:
            piece(cur, op["s0"], 0, H)
            piece(op["s0"], op["s1"], 0, op["z0"])
            piece(op["s0"], op["s1"], op["z1"], H)
            cur = op["s1"]
            if op["kind"] in ("door", "front_door"):
                self._door(wall, op, t)
            elif op["kind"] == "window":
                self._window(wall, op, t)
        piece(cur, b, 0, H)
        # bathroom walls get tiles: assign by majority rooms touching (keeps it simple: tile if any room is bathroom)
        self.add("wall_%02d" % wi, pm, (0, 0, 0), 0.0, "wall", coll="HM_Structure")

    def _door(self, wall, op, t):
        rng = self.rng
        st = self.st
        w = op["s1"] - op["s0"]
        h = op["z1"]
        frame = PlantModel()
        for s in (op["s0"] + 0.02, op["s1"] - 0.02):
            if wall.axis == "x":
                mk.box(frame.mb, (s, wall.c, h / 2), (0.04, t + 0.02, h), st["door_frame"])
            else:
                mk.box(frame.mb, (wall.c, s, h / 2), (t + 0.02, 0.04, h), st["door_frame"])
        if wall.axis == "x":
            mk.box(frame.mb, ((op["s0"] + op["s1"]) / 2, wall.c, h - 0.02), (w, t + 0.02, 0.04), st["door_frame"])
        else:
            mk.box(frame.mb, (wall.c, (op["s0"] + op["s1"]) / 2, h - 0.02), (t + 0.02, w, 0.04), st["door_frame"])
        self.add("doorframe_%d" % len(self.records), frame, (0, 0, 0), 0.0, "door", coll="HM_Structure")
        p_open = self.sc.get("doors_open", 0.7)
        if op["kind"] == "front_door":
            p_open = self.sc.get("front_door_open", 0.15)
        opened = rng.random() < p_open
        angle = rng.uniform(70, 100) if opened else (rng.uniform(5, 30) if rng.random() < 0.2 else 0.0)
        lw = w - 0.06
        leaf = PlantModel()
        mk.box(leaf.mb, (lw / 2, 0, (h - 0.03) / 2), (lw, 0.04, h - 0.04), st["door"])
        mk.box(leaf.mb, (lw - 0.08, 0.04, 1.0), (0.12, 0.03, 0.02), st["metal"])
        mk.box(leaf.mb, (lw - 0.08, -0.04, 1.0), (0.12, 0.03, 0.02), st["metal"])
        side = rng.choice((-1, 1))
        if wall.axis == "x":
            hinge = (op["s0"] + 0.03, wall.c, 0.0)
            yaw = side * math.radians(angle)
        else:
            hinge = (wall.c, op["s0"] + 0.03, 0.0)
            yaw = math.pi / 2 + side * math.radians(angle) * -1
        self.add("door_%d" % len(self.records), leaf, hinge, yaw, "door", coll="HM_Structure",
                 record=dict(category="door", label="front_door" if op["kind"] == "front_door" else "door",
                             open_angle_deg=round(angle, 1), state="open" if angle > 45 else ("ajar" if angle > 0 else "closed")))
        if angle > 0:
            # keep the swing area clear of furniture
            s0 = op["s0"]
            if wall.axis == "x":
                self.occ.append((s0, wall.c - lw, s0 + lw, wall.c + lw, "door_swing"))
            else:
                self.occ.append((wall.c - lw, s0, wall.c + lw, s0 + lw, "door_swing"))

    def _window(self, wall, op, t):
        st = self.st
        pm = PlantModel()
        s0, s1, z0, z1 = op["s0"], op["s1"], op["z0"], op["z1"]
        sm, zm, w, h = (s0 + s1) / 2, (z0 + z1) / 2, s1 - s0, z1 - z0
        fw = 0.05

        def bx(s, z, ls, lz, depth, m):
            if wall.axis == "x":
                mk.box(pm.mb, (s, wall.c, z), (ls, depth, lz), m)
            else:
                mk.box(pm.mb, (wall.c, s, z), (depth, ls, lz), m)
        for s in (s0 + fw / 2, s1 - fw / 2):
            bx(s, zm, fw, h, t * 0.6, st["window_frame"])
        for z in (z0 + fw / 2, z1 - fw / 2):
            bx(sm, z, w, fw, t * 0.6, st["window_frame"])
        if w > 1.1:
            bx(sm, zm, fw * 0.7, h, t * 0.5, st["window_frame"])
        bx(sm, zm, w - fw, h - fw, 0.012, st["window_glass"])
        self.add("window_%d" % len(self.records), pm, (0, 0, 0), 0.0, "window", coll="HM_Structure",
                 record=dict(category="window", label="window", sill_height=round(z0, 2), width=round(w, 2)))
        if self.sc.get("curtains", 0.5) > self.rng.random() and z0 < 1.2:
            room = next((r for r in self.plan["rooms"] if r["id"] in op["rooms"]), None)
            if room is not None:
                R = room["rect"]
                inward = 1 if (wall.axis == "x" and abs(wall.c - R.y0) < 1e-6) or (wall.axis == "y" and abs(wall.c - R.x0) < 1e-6) else -1
                for k, s in enumerate((s0 - 0.15, s1 + 0.15)):
                    cpm = F.curtain(self.rng, st, 0.35, z1 + 0.15)
                    off = (t / 2 + 0.06) * inward
                    if wall.axis == "x":
                        loc, yaw = (s, wall.c + off, 0.0), 0.0
                    else:
                        loc, yaw = (wall.c + off, s, 0.0), math.pi / 2
                    self.add("curtain_%d" % len(self.records), cpm, loc, yaw, "textile", coll="HM_Decor",
                             record=dict(category="decor", label="curtain"))

    def _outside(self):
        st = self.st
        W, D = self.W, self.D
        pm = PlantModel()
        R = 120
        pm.mb.add([(-R, -R, -0.06), (R, -R, -0.06), (R, R, -0.06), (-R, R, -0.06)], [(0, 1, 2, 3)], st["grass_out"])
        self.add("ground_out", pm, (0, 0, 0), 0.0, "outdoor", coll="HM_Outside")
        rng = random.Random(self.seed + 5)
        vs = []
        for v in range(4):
            t = PlantModel()
            mk.tube(t.mb, [Vector((0, 0, 0)), Vector((0, 0, 0.45))], 0.03, st["trunk_out"], sides=5)
            for k in range(rng.randint(3, 6)):
                c = Vector((rng.uniform(-.2, .2), rng.uniform(-.2, .2), rng.uniform(0.5, 0.8)))
                r = rng.uniform(0.2, 0.33)
                mk.ellipsoid(t.mb, c, (r, r, r * 0.9), st["tree_out"], u=8, v=6, jitter=0.15, rng=rng)
            me = t.mb.build("tree_out_%d" % v, self.lib.resolve(t.mb.mats))
            styles.tag(me, self.cid("outdoor"))
            vs.append(me)
        for k in range(60):
            a = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(9, 40)
            x, y = W / 2 + r * math.cos(a), D / 2 + r * math.sin(a)
            if -3 < x < W + 3 and -3 < y < D + 3:
                continue
            o = bpy.data.objects.new("tree_out_%02d" % k, rng.choice(vs))
            h = rng.uniform(4, 11)
            o.location = (x, y, -0.06)
            o.scale = (h, h, h)
            o.color = (0, 0, 0, 1)
            self.coll("HM_Outside").objects.link(o)

    # ------------------------------------------------------------ placement
    def _room_inner(self, room):
        R = room["rect"]
        return (R.x0 + WALL_HALF, R.y0 + WALL_HALF, R.x1 - WALL_HALF, R.y1 - WALL_HALF)

    def _free(self, rect, room, label="", check_doors=True):
        ix0, iy0, ix1, iy1 = self._room_inner(room)
        if rect[0] < ix0 - 1e-6 or rect[1] < iy0 - 1e-6 or rect[2] > ix1 + 1e-6 or rect[3] > iy1 + 1e-6:
            return False
        for o in self.occ:
            if _rect_overlap(rect, o, 0.02):
                return False
        if check_doors:
            for z in room["_door_zones"]:
                if _rect_overlap(rect, (z.x0, z.y0, z.x1, z.y1)):
                    return False
        return True

    def _wall_pose(self, room, side, s, w, d):
        x0, y0, x1, y1 = self._room_inner(room)
        if side == "S":
            return (s, y0 + d / 2), 0.0, (s - w / 2, y0, s + w / 2, y0 + d)
        if side == "N":
            return (s, y1 - d / 2), math.pi, (s - w / 2, y1 - d, s + w / 2, y1)
        if side == "W":
            return (x0 + d / 2, s), -math.pi / 2, (x0, s - w / 2, x0 + d, s + w / 2)
        return (x1 - d / 2, s), math.pi / 2, (x1 - d, s - w / 2, x1, s + w / 2)

    def _blocked_by_window(self, room, side, s, w, h):
        for wside, a, b, sill in room["_windows"]:
            if wside == side and h > sill - 0.05 and not (s + w / 2 <= a or s - w / 2 >= b):
                return True
        return False

    def place_wall(self, room, pm, cls, label=None, sides=None, record_extra=None, prefer=None, tries=40,
                   along=None, part_roles=None):
        w, d, h = pm.meta["size"]
        x0, y0, x1, y1 = self._room_inner(room)
        sides = list(sides or ["N", "S", "E", "W"])
        self.rng.shuffle(sides)
        if prefer:
            sides.sort(key=lambda s: s != prefer)
        for side in sides:
            lo, hi = (x0, x1) if side in ("N", "S") else (y0, y1)
            if hi - lo < w:
                continue
            for _ in range(tries // len(sides) + 1):
                s = self.rng.uniform(lo + w / 2, hi - w / 2) if along is None else max(lo + w / 2, min(hi - w / 2, along))
                (cx, cy), yaw, rect = self._wall_pose(room, side, s, w, d)
                if self._blocked_by_window(room, side, s, w, h):
                    continue
                if self._free(rect, room):
                    return self._commit(room, pm, cls, (cx, cy), yaw, rect, label, record_extra, side, part_roles)
        return None

    def place_at(self, room, pm, cls, center, yaw, label=None, record_extra=None, check_doors=True, part_roles=None,
                 occupy=True):
        w, d, h = pm.meta["size"]
        c, s = abs(math.cos(yaw)), abs(math.sin(yaw))
        ex, ey = (w * c + d * s) / 2, (w * s + d * c) / 2
        rect = (center[0] - ex, center[1] - ey, center[0] + ex, center[1] + ey)
        if occupy and not self._free(rect, room, check_doors=check_doors):
            return None
        return self._commit(room, pm, cls, center, yaw, rect, label, record_extra, None, part_roles, occupy)

    def _commit(self, room, pm, cls, center, yaw, rect, label, extra, side, part_roles=None, occupy=True):
        rec = dict(category="furniture", label=label or pm.meta.get("label"), room=room["name"], room_type=room["type"])
        if extra:
            rec.update(extra)
        roles = dict(pm.meta.get("parts", {}))
        roles.update(part_roles or {})
        obj = self.add("%s_%03d" % (rec["label"], self.next_id), pm, (center[0], center[1], 0.0), yaw, cls,
                       record=rec, part_roles=roles)
        if occupy:
            self.occ.append(rect + (rec["label"],))
        mw = obj.matrix_world
        for (sx0, sy0, sx1, sy1, sz) in pm.meta.get("supports", []):
            corners = [mw @ Vector((x, y, sz)) for x, y in ((sx0, sy0), (sx1, sy0), (sx1, sy1), (sx0, sy1))]
            self.supports.append(dict(corners=corners, z=sz, kind=rec["label"], instance=rec["instance_id"],
                                      room=room["name"], local=(sx0, sy0, sx1, sy1), mw=mw.copy(), items=[]))
        for (pos, energy, kind) in pm.meta.get("lights", []):
            self.lights.append((mw @ Vector(pos), energy, kind))
        return dict(obj=obj, center=center, yaw=yaw, side=side, rect=rect, size=pm.meta["size"], record=rec)

    @staticmethod
    def local_to_world(placed, lx, ly):
        yaw = placed["yaw"]
        c, s = math.cos(yaw), math.sin(yaw)
        return placed["center"][0] + lx * c - ly * s, placed["center"][1] + lx * s + ly * c

    def front_of(self, placed, dist):
        """World point at ``dist`` in front of a wall-placed item."""
        yaw = placed["yaw"]
        fx, fy = -math.sin(yaw), math.cos(yaw)
        d = placed["size"][1] / 2 + dist
        return placed["center"][0] + fx * d, placed["center"][1] + fy * d

    # -------------------------------------------------------------- furnish
    def _furnish(self, room):
        room["_door_zones"] = layout.door_zones(self.plan, room)
        room["_windows"] = layout.window_spans(self.plan, room)
        rng, st = self.rng, self.st
        kind = room["type"]
        R = room["rect"]
        getattr(self, "_room_" + kind, self._room_generic)(room, rng, st)
        # wall decoration
        for _ in range(rng.randint(0, 2)):
            self._picture(room)
        if kind not in ("bathroom", "laundry") and rng.random() < self.sc.get("plants", 0.6):
            self.place_wall(room, F.plant(rng, st, big=True), "plant")
        _ = R

    def _picture(self, room):
        x0, y0, x1, y1 = self._room_inner(room)
        rng = self.rng
        side = rng.choice("NSEW")
        w, h = rng.uniform(0.4, 1.0), rng.uniform(0.3, 0.7)
        lo, hi = (x0, x1) if side in "NS" else (y0, y1)
        if hi - lo < w + 0.6:
            return
        s = rng.uniform(lo + w / 2 + 0.2, hi - w / 2 - 0.2)
        if self._blocked_by_window(room, side, s, w + 0.2, 2.5):
            return
        for wall in self.plan["walls"]:  # avoid doors
            for op in wall.openings:
                if op["kind"] != "window" and room["id"] in op.get("rooms", []):
                    if wall.axis == ("x" if side in "NS" else "y") and not (s + w / 2 < op["s0"] - 0.1 or s - w / 2 > op["s1"] + 0.1):
                        if (side in "NS" and abs(wall.c - (room["rect"].y0 if side == "S" else room["rect"].y1)) < 1e-6) or \
                           (side in "EW" and abs(wall.c - (room["rect"].x0 if side == "W" else room["rect"].x1)) < 1e-6):
                            return
        (cx, cy), yaw, _ = self._wall_pose(room, side, s, w, 0.03)
        pm = F.picture(rng, self.st, w, h)
        self.add("picture_%03d" % self.next_id, pm, (cx, cy, rng.uniform(1.4, 1.7)), yaw, "decoration", coll="HM_Decor",
                 record=dict(category="decor", label="picture", room=room["name"], room_type=room["type"]))

    def _rug(self, room, center, w, d, yaw=0.0):
        pm = F.rug(self.rng, self.st, w, d)
        self.place_at(room, pm, "rug", center, yaw, occupy=False)

    def _room_living(self, room, rng, st):
        sofa = self.place_wall(room, F.sofa(rng, st, seats=rng.choice([2, 3, 3])), "seating")
        if sofa:
            cx, cy = self.front_of(sofa, 0.45 + 0.3)
            self._rug(room, (cx, cy), rng.uniform(1.6, 2.4), rng.uniform(1.2, 1.7), sofa["yaw"])
            self.place_at(room, F.coffee_table(rng, st), "table", (cx, cy), sofa["yaw"])
            opp = {"N": "S", "S": "N", "E": "W", "W": "E"}[sofa["side"]]
            along = sofa["center"][0] if opp in ("N", "S") else sofa["center"][1]
            if not self.place_wall(room, F.tv_unit(rng, st), "storage", sides=[opp], along=along, tries=10,
                                   part_roles={"tv": "appliance", "screen": "appliance"}):
                self.place_wall(room, F.tv_unit(rng, st), "storage", part_roles={"tv": "appliance", "screen": "appliance"})
            lamp_pos = self.front_of(sofa, -0.1)
            yaw = sofa["yaw"]
            side_off = sofa["size"][0] / 2 + 0.3
            lp = (lamp_pos[0] + math.cos(yaw) * side_off, lamp_pos[1] + math.sin(yaw) * side_off)
            self.place_at(room, F.floor_lamp(rng, st), "lamp", lp, 0.0)
        else:
            self.place_wall(room, F.tv_unit(rng, st), "storage", part_roles={"tv": "appliance", "screen": "appliance"})
        if rng.random() < 0.7:
            self.place_wall(room, F.armchair(rng, st), "seating")
        for _ in range(rng.randint(1, 2)):
            self.place_wall(room, F.bookshelf(rng, st), "storage")
        if not any(r["type"] == "kitchen" for r in self.plan["rooms"]):
            self._room_kitchen(room, rng, st)
        if room["rect"].area > 22 and not any(r["type"] == "dining" for r in self.plan["rooms"]):
            self._dining_set(room, rng, st, seats=4)
        if self.sc.get("stairs") and not getattr(self, "_stairs_done", False):
            if self.place_wall(room, F.stairs(rng, st), "stairs", record_extra=dict(category="stairs")):
                self._stairs_done = True

    def _room_hallway(self, room, rng, st):
        self.place_wall(room, F.cabinet(rng, st, w=0.8, h=0.9, label="shoe_cabinet", d=0.35), "storage")
        if rng.random() < 0.5:
            self.place_wall(room, F.mirror(rng, st, 0.6, 1.6), "decoration")
        if self.sc.get("stairs") and not getattr(self, "_stairs_done", False):
            if self.place_wall(room, F.stairs(rng, st), "stairs", record_extra=dict(category="stairs")):
                self._stairs_done = True

    def _room_kitchen(self, room, rng, st):
        x0, y0, x1, y1 = self._room_inner(room)
        sides = sorted(["N", "S", "E", "W"], key=lambda s: -((x1 - x0) if s in "NS" else (y1 - y0)))
        placed = None
        for side in sides:
            span = (x1 - x0) if side in "NS" else (y1 - y0)
            for L in (min(3.6, span - 0.9), min(2.4, span - 0.9), 1.6):
                if L < 1.2:
                    continue
                placed = self.place_wall(room, F.kitchen_run(rng, st, L), "counter", sides=[side], tries=20,
                                         part_roles={"hob": "appliance", "sink": "counter"})
                if placed:
                    break
            if placed:
                break
        self.place_wall(room, F.fridge(rng, st), "appliance")
        if room["rect"].area > 10 and not any(r["type"] == "dining" for r in self.plan["rooms"]):
            self._dining_set(room, rng, st, seats=rng.choice([2, 4]), w=1.2, d=0.8)
        elif rng.random() < 0.5:
            self.place_wall(room, F.stool(rng, st), "seating")

    def _dining_set(self, room, rng, st, seats=4, w=1.6, d=0.9):
        R = room["rect"]
        for _ in range(12):
            c = (R.cx + rng.uniform(-0.6, 0.6), R.cy + rng.uniform(-0.6, 0.6))
            yaw = rng.choice([0.0, math.pi / 2])
            t = self.place_at(room, F.table(rng, st, w=w, d=d, glass=rng.random() < st["glass_p"] * 0.7), "table", c, yaw)
            if t:
                break
        else:
            return
        cx, cy = t["center"]
        ax = (math.cos(yaw), math.sin(yaw))     # table long axis
        ny = (-math.sin(yaw), math.cos(yaw))
        per_side = max(1, seats // 2)
        for side in (-1, 1):
            for k in range(per_side):
                off = (k - (per_side - 1) / 2) * (w / per_side)
                px = cx + ax[0] * off + ny[0] * side * (d / 2 + 0.2)
                py = cy + ax[1] * off + ny[1] * side * (d / 2 + 0.2)
                cyaw = yaw + (0 if side < 0 else math.pi) + rng.uniform(-0.25, 0.25)
                p = (px + rng.uniform(-0.05, 0.05), py + rng.uniform(-0.05, 0.05))
                self.place_at(room, F.chair(rng, st), "seating", p, cyaw, check_doors=False)
        if rng.random() < 0.6:
            self.place_wall(room, F.cabinet(rng, st, label="sideboard"), "storage")

    def _room_dining(self, room, rng, st):
        self._rug(room, (room["rect"].cx, room["rect"].cy), 2.4, 1.8)
        self._dining_set(room, rng, st, seats=rng.choice([4, 6]), w=rng.choice([1.6, 1.8]))
        self.place_wall(room, F.cabinet(rng, st, label="sideboard"), "storage")

    def _room_bedroom(self, room, rng, st, double=True):
        b = self.place_wall(room, F.bed(rng, st, double=double), "bed",
                            part_roles={"pillow": "textile", "blanket": "textile"})
        if b:
            yaw = b["yaw"]
            bw, bd = b["size"][0], b["size"][1]
            for side in ((-1, 1) if double else (rng.choice((-1, 1)),)):
                p = self.local_to_world(b, side * (bw / 2 + 0.26), -bd / 2 + 0.22)
                ns = self.place_at(room, F.nightstand(rng, st), "table", p, yaw)
                if ns and rng.random() < 0.8:
                    lamp = F.table_lamp(rng, st)
                    lp = self.local_to_world(ns, 0.08, -0.08)
                    self.add("table_lamp_%03d" % self.next_id, lamp, (lp[0], lp[1], 0.55), yaw, "lamp",
                             record=dict(category="furniture", label="table_lamp", room=room["name"], room_type=room["type"]))
                    self.lights.append((Vector((lp[0], lp[1], 0.55 + 0.33)), 20.0, "point"))
                    sup = self.supports[-1] if self.supports and self.supports[-1]["instance"] == ns["record"]["instance_id"] else None
                    if sup:  # keep clutter off the lamp
                        x0, y0, x1, y1 = sup["local"]
                        sup["local"] = (x0, y0, x1, y1 - 0.17)
            self._rug(room, self.front_of(b, 0.6), rng.uniform(1.2, 1.8), 0.8, yaw)
        self.place_wall(room, F.wardrobe(rng, st), "storage")
        if rng.random() < 0.6:
            self.place_wall(room, F.dresser(rng, st), "storage")

    def _room_kids(self, room, rng, st):
        self._room_bedroom(room, rng, st, double=False)
        d = self.place_wall(room, F.desk(rng, st), "table", part_roles={"screen": "appliance"})
        if d:
            self.place_at(room, F.chair(rng, st), "seating", self.front_of(d, 0.25), d["yaw"] + math.pi, check_doors=False)
        self.place_wall(room, F.bookshelf(rng, st, w=0.8), "storage")
        self._rug(room, (room["rect"].cx, room["rect"].cy), 1.6, 1.2)

    def _room_office(self, room, rng, st):
        d = self.place_wall(room, F.desk(rng, st), "table", part_roles={"screen": "appliance"})
        if d:
            self.place_at(room, F.office_chair(rng, st), "seating", self.front_of(d, 0.3), d["yaw"] + math.pi,
                          check_doors=False)
        for _ in range(rng.randint(1, 3)):
            self.place_wall(room, F.bookshelf(rng, st), "storage")
        self.place_wall(room, F.cabinet(rng, st), "storage")
        if rng.random() < 0.6:
            self.place_wall(room, F.floor_lamp(rng, st), "lamp")

    def _room_bathroom(self, room, rng, st):
        self.place_wall(room, F.toilet(rng, st), "sanitary")
        b = self.place_wall(room, F.basin(rng, st), "sanitary", part_roles={"cabinet": "storage"})
        if b:
            mx, my = b["center"]
            yaw = b["yaw"]
            back = (mx + math.sin(yaw) * (b["size"][1] / 2 - 0.01), my - math.cos(yaw) * (b["size"][1] / 2 - 0.01))
            self.add("mirror_%03d" % self.next_id, F.mirror(rng, st), (back[0], back[1], 1.55), yaw, "decoration",
                     coll="HM_Decor", record=dict(category="decor", label="mirror", room=room["name"], room_type=room["type"]))
        if room["rect"].area > 5.5 and rng.random() < 0.6:
            self.place_wall(room, F.bathtub(rng, st), "sanitary")
        else:
            self.place_wall(room, F.shower(rng, st), "sanitary")

    def _room_laundry(self, room, rng, st):
        for _ in range(rng.randint(1, 2)):
            self.place_wall(room, F.washing_machine(rng, st), "appliance")
        self.place_wall(room, F.cabinet(rng, st, h=2.0, label="utility_cabinet", d=0.5), "storage")
        self.place_wall(room, F.bookshelf(rng, st, w=0.8), "storage")

    def _room_generic(self, room, rng, st):
        self.place_wall(room, F.cabinet(rng, st), "storage")

    # -------------------------------------------------------------- clutter
    def _clutter(self):
        rng = self.rng
        level = self.sc.get("clutter", 0.4)
        theme = self.sc.get("clutter_theme", "tidy")
        n_surface = 0
        for sup in self.supports:
            sx0, sy0, sx1, sy1 = sup["local"]
            area = (sx1 - sx0) * (sy1 - sy0)
            n = np.random.default_rng(rng.randint(0, 1 << 30)).poisson(level * (1.0 + 6.0 * area))
            kinds = SURFACE_ITEMS.get(sup["kind"], SURFACE_ITEMS["default"])
            if theme == "party":
                kinds = kinds + ["bottle", "can", "cup", "bottle"]
            placed = []
            for _ in range(int(n)):
                kind = rng.choice(kinds)
                pm, group = F.small_object(rng, self.st, kind)
                r = max(pm.meta["size"][0], pm.meta["size"][1]) / 2 + 0.01
                for _ in range(15):
                    lx = rng.uniform(sx0 + r, sx1 - r) if sx1 - sx0 > 2 * r else (sx0 + sx1) / 2
                    ly = rng.uniform(sy0 + r, sy1 - r) if sy1 - sy0 > 2 * r else (sy0 + sy1) / 2
                    if all((lx - px) ** 2 + (ly - py) ** 2 > (r + pr) ** 2 for px, py, pr in placed):
                        break
                else:
                    continue
                placed.append((lx, ly, r))
                p = sup["mw"] @ Vector((lx, ly, sup["z"]))
                yaw = rng.uniform(0, 6.28)
                fallen = kind in ("bottle", "can", "cup") and theme == "party" and rng.random() < 0.3
                obj = self.add("%s_%03d" % (kind, self.next_id), pm, (p.x, p.y, p.z + 0.001), yaw, group,
                               coll="HM_Clutter",
                               record=dict(category="object", label=kind, room=sup["room"], support=sup["kind"],
                                           support_instance=sup["instance"], on_floor=False))
                if fallen:
                    obj.rotation_euler = (math.pi / 2, 0, yaw)
                    obj.location.z += 0.035
                    self.records[-1]["fallen"] = True
                sup["items"].append(self.records[-1]["instance_id"])
                n_surface += 1
        # floor clutter
        n_floor = 0
        kinds = FLOOR_ITEMS.get(theme, FLOOR_ITEMS["tidy"])
        for room in self.plan["rooms"]:
            area = room["rect"].area
            n = np.random.default_rng(rng.randint(0, 1 << 30)).poisson(level * area * 0.45)
            if theme == "moving":
                n += int(area * 0.4)
            for _ in range(int(n)):
                kind = rng.choice(kinds)
                pm, group = F.small_object(rng, self.st, kind)
                w, d, h = pm.meta["size"]
                ix0, iy0, ix1, iy1 = self._room_inner(room)
                for _ in range(25):
                    c = (rng.uniform(ix0 + w, ix1 - w), rng.uniform(iy0 + d, iy1 - d))
                    yaw = rng.uniform(0, 6.28)
                    rect = (c[0] - max(w, d) / 2, c[1] - max(w, d) / 2, c[0] + max(w, d) / 2, c[1] + max(w, d) / 2)
                    if self._free(rect, room, check_doors=False):
                        self.add("%s_%03d" % (kind, self.next_id), pm, (c[0], c[1], 0.0), yaw, group, coll="HM_Clutter",
                                 record=dict(category="object", label=kind, room=room["name"], room_type=room["type"],
                                             on_floor=True))
                        self.occ.append(rect + (kind,))
                        n_floor += 1
                        break
        self.stats.update(surface_objects=n_surface, floor_objects=n_floor)

    # --------------------------------------------------------------- agents
    def _agents(self):
        rng = self.rng
        rooms = [r for r in self.plan["rooms"] if r["type"] not in ("bathroom",)]
        for k in range(self.sc.get("people", 0)):
            room = rng.choice(rooms)
            pose = rng.choice(self.sc.get("people_poses", ["standing", "standing", "bending"]))
            pm = agri_props.person(random.Random(self.seed * 31 + k), pose)
            pm.meta["size"] = (0.6, 0.6, pm.meta["height"])
            ix0, iy0, ix1, iy1 = self._room_inner(room)
            for _ in range(30):
                c = (rng.uniform(ix0 + 0.4, ix1 - 0.4), rng.uniform(iy0 + 0.4, iy1 - 0.4))
                if self.place_at(room, pm, "person", c, rng.uniform(0, 6.28), label="person",
                                 record_extra=dict(category="person", pose=pose), check_doors=False):
                    break
        for k in range(self.sc.get("pets", 0)):
            room = rng.choice(rooms)
            kind = rng.choice(self.sc.get("pet_kinds", ["dog", "cat"]))
            pm = F.pet(random.Random(self.seed * 17 + k), self.st, kind)
            ix0, iy0, ix1, iy1 = self._room_inner(room)
            for _ in range(30):
                c = (rng.uniform(ix0 + 0.5, ix1 - 0.5), rng.uniform(iy0 + 0.5, iy1 - 0.5))
                if self.place_at(room, pm, "pet", c, rng.uniform(0, 6.28), label=kind,
                                 record_extra=dict(category="pet", pose=pm.meta["pose"]), check_doors=False):
                    break

    # --------------------------------------------------------------- lights
    def _lights(self):
        on = self.sc.get("lights_on", False)
        H = self.H
        for room in self.plan["rooms"]:
            R = room["rect"]
            pm = F.ceiling_light(self.rng, self.st)
            o = self.add("ceiling_light_%s" % room["name"], pm, (R.cx, R.cy, H), 0.0, "lamp", coll="HM_Lights",
                         record=dict(category="fixture", label="ceiling_light", room=room["name"], room_type=room["type"],
                                     on=bool(on)))
            o["hm_ceiling"] = True
            if on:
                light = bpy.data.lights.new("L_" + room["name"], "AREA")
                light.shape = "DISK"
                light.size = 0.5
                light.energy = 9.0 * R.area * self.sc.get("light_power", 1.0)
                light.color = (1.0, 0.92, 0.82) if self.sc.get("warm_light", True) else (1.0, 1.0, 1.0)
                o = bpy.data.objects.new(light.name, light)
                o.location = (R.cx, R.cy, H - 0.1)
                self.scene.collection.objects.link(o)
        night = self.sc.get("environment", {}).get("lighting") in ("night", "dusk")
        if not on and not night:
            # daylight bounce fill (windows alone under-light deep rooms)
            for room in self.plan["rooms"]:
                R = room["rect"]
                light = bpy.data.lights.new("Fill_" + room["name"], "AREA")
                light.shape = "RECTANGLE"
                light.size, light.size_y = R.w * 0.8, R.d * 0.8
                light.energy = 7.0 * R.area * self.sc.get("daylight_fill", 1.0)
                light.color = (0.95, 0.97, 1.0)
                o = bpy.data.objects.new(light.name, light)
                o.location = (R.cx, R.cy, self.H - 0.3)
                o.visible_camera = False
                o.visible_glossy = False
                self.scene.collection.objects.link(o)
        if not on:
            # emission off when the lights are off
            m = self.lib["light_emit"]
            for n in m.node_tree.nodes:
                if n.type == "EMISSION":
                    n.inputs["Strength"].default_value = 0.0
            return
        for pos, energy, kind in self.lights:
            light = bpy.data.lights.new("Lamp", "POINT")
            light.energy = energy * self.sc.get("light_power", 1.0)
            light.shadow_soft_size = 0.08
            light.color = (1.0, 0.85, 0.65)
            o = bpy.data.objects.new(light.name, light)
            o.location = pos
            self.scene.collection.objects.link(o)

    # ----------------------------------------------------------- occupancy
    def occupancy(self, res=0.05, margin=0.5):
        W, D = self.W, self.D
        nx, ny = int((W + 2 * margin) / res), int((D + 2 * margin) / res)
        grid = np.full((ny, nx), 128, np.uint8)
        xs = -margin + (np.arange(nx) + 0.5) * res
        ys = -margin + (np.arange(ny) + 0.5) * res
        gx, gy = np.meshgrid(xs, ys)
        for room in self.plan["rooms"]:
            R = room["rect"]
            grid[(gx >= R.x0) & (gx <= R.x1) & (gy >= R.y0) & (gy <= R.y1)] = 0
        for wall in self.plan["walls"]:
            t = 0.2 if wall.exterior else 0.1
            segs = []
            cur = wall.a - t / 2
            for op in wall.openings:
                segs.append((cur, op["s0"]))
                if op["kind"] == "window":
                    segs.append((op["s0"], op["s1"]))
                cur = op["s1"]
            segs.append((cur, wall.b + t / 2))
            for s0, s1 in segs:
                if wall.axis == "x":
                    m = (gx >= s0) & (gx <= s1) & (np.abs(gy - wall.c) <= t / 2)
                else:
                    m = (gy >= s0) & (gy <= s1) & (np.abs(gx - wall.c) <= t / 2)
                grid[m] = 255
        for o in self.occ:
            if o[4] in ("door_swing", "rug"):
                continue
            grid[(gx >= o[0]) & (gx <= o[2]) & (gy >= o[1]) & (gy <= o[3])] = 255
        return grid, dict(resolution=res, origin=[-margin, -margin], note="row 0 = smallest y; 0 free, 255 occupied, 128 outside")

    def floorplan(self):
        rooms = [dict(id=r["id"], name=r["name"], type=r["type"], rect=r["rect"].as_list(),
                      area_m2=round(r["rect"].area, 2)) for r in self.plan["rooms"]]
        return dict(width=self.W, depth=self.D, height=self.H, rooms=rooms,
                    walls=[w.to_dict() for w in self.plan["walls"]],
                    front_door=self.plan["front_door"])
