"""Floor-plan generation: BSP rooms, doors, windows, wall segments.

Everything is axis aligned and in metres; the house occupies
``[0, W] x [0, D]`` with the floor at z = 0.
"""


class Rect:
    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    @property
    def w(self):
        return self.x1 - self.x0

    @property
    def d(self):
        return self.y1 - self.y0

    @property
    def area(self):
        return self.w * self.d

    @property
    def cx(self):
        return 0.5 * (self.x0 + self.x1)

    @property
    def cy(self):
        return 0.5 * (self.y0 + self.y1)

    def as_list(self):
        return [round(self.x0, 3), round(self.y0, 3), round(self.x1, 3), round(self.y1, 3)]


class Wall:
    """Axis-aligned wall segment with openings.

    ``axis`` 'x' means the wall runs along x at y = ``c`` (from a to b).
    Openings: dicts with s0, s1 (along the wall), z0, z1, kind, ...
    """

    def __init__(self, axis, c, a, b, exterior, rooms=()):
        self.axis, self.c, self.a, self.b = axis, c, a, b
        self.exterior = exterior
        self.rooms = list(rooms)
        self.openings = []

    def to_dict(self):
        return dict(axis=self.axis, c=round(self.c, 3), a=round(self.a, 3), b=round(self.b, 3),
                    exterior=self.exterior, openings=self.openings)


PROGRAMS = {
    "studio": ["living", "bathroom"],
    "apartment_1bed": ["living", "kitchen", "bedroom", "bathroom"],
    "apartment_2bed": ["living", "kitchen", "bedroom", "bedroom", "bathroom", "hallway"],
    "family_3bed": ["living", "kitchen", "dining", "bedroom", "bedroom", "kids", "bathroom", "hallway"],
    "bungalow": ["living", "kitchen", "bedroom", "bedroom", "bathroom", "laundry"],
    "loft": ["living", "kitchen", "bedroom", "bathroom"],
    "villa": ["living", "kitchen", "dining", "office", "bedroom", "bedroom", "kids", "bathroom", "bathroom",
              "laundry", "hallway"],
    "office_home": ["living", "kitchen", "office", "office", "bathroom", "bedroom"],
    "care_home": ["living", "kitchen", "bedroom", "bathroom", "hallway"],
}

# rough relative size preference used to match rooms to BSP cells
SIZE_PREF = {"living": 10, "kitchen": 6, "dining": 6, "bedroom": 5, "kids": 4.5, "office": 4,
             "laundry": 2, "bathroom": 2.5, "hallway": 1}


def generate(W, D, program, rng, min_room=2.3, open_plan=False):
    """Return dict(rooms, walls, doors, windows, front_door)."""
    n = len(program)
    leaves = [Rect(0, 0, W, D)]
    splits = []  # (axis, c, a, b, left_ids, right_ids) recorded after leaf ids are fixed
    tree = []    # list of (axis, coordinate, rect, child rect A, child rect B)
    guard = 0
    while len(leaves) < n and guard < 200:
        guard += 1
        leaves.sort(key=lambda r: -r.area)
        cand = None
        for r in leaves:
            axis = "x" if r.w >= r.d else "y"   # split the long side
            length = r.w if axis == "x" else r.d
            if length >= 2 * min_room:
                cand = (r, axis)
                break
            other = "y" if axis == "x" else "x"
            length = r.w if other == "x" else r.d
            if length >= 2 * min_room:
                cand = (r, other)
                break
        if cand is None:
            break
        r, axis = cand
        lo = r.x0 if axis == "x" else r.y0
        hi = r.x1 if axis == "x" else r.y1
        t = rng.uniform(0.35, 0.65)
        c = lo + (hi - lo) * t
        c = max(lo + min_room, min(hi - min_room, c))
        c = round(c * 10) / 10.0
        if axis == "x":
            A, B = Rect(r.x0, r.y0, c, r.y1), Rect(c, r.y0, r.x1, r.y1)
            wall = Wall("y", c, r.y0, r.y1, False)
        else:
            A, B = Rect(r.x0, r.y0, r.x1, c), Rect(r.x0, c, r.x1, r.y1)
            wall = Wall("x", c, r.x0, r.x1, False)
        leaves.remove(r)
        leaves.extend([A, B])
        tree.append((wall, A, B))

    # assign room types: big cells -> big programs
    cells = sorted(leaves, key=lambda r: -r.area)
    prog = sorted(program[:len(cells)], key=lambda p: -SIZE_PREF.get(p, 3))
    # hallways prefer the thinnest cell
    rooms = []
    for cell, kind in zip(cells, prog):
        rooms.append(dict(rect=cell, type=kind))
    hall = [r for r in rooms if r["type"] == "hallway"]
    if hall:
        thin = min(rooms, key=lambda r: min(r["rect"].w, r["rect"].d) / max(r["rect"].w, r["rect"].d))
        hall[0]["type"], thin["type"] = thin["type"], hall[0]["type"]
    for i, r in enumerate(rooms):
        r["id"] = i
        r["name"] = "%s_%d" % (r["type"], i)

    def room_at(px, py):
        for r in rooms:
            R = r["rect"]
            if R.x0 - 1e-6 <= px <= R.x1 + 1e-6 and R.y0 - 1e-6 <= py <= R.y1 + 1e-6:
                return r
        return None

    walls = [
        Wall("x", 0.0, 0.0, W, True), Wall("x", D, 0.0, W, True),
        Wall("y", 0.0, 0.0, D, True), Wall("y", W, 0.0, D, True),
    ]
    doors = []
    for wall, A, B in tree:
        walls.append(wall)
        # rooms on both sides along this wall -> shared intervals
        shared = []
        for ra in rooms:
            for rb in rooms:
                if ra is rb:
                    continue
                Ra, Rb = ra["rect"], rb["rect"]
                if wall.axis == "y":
                    if abs(Ra.x1 - wall.c) < 1e-6 and abs(Rb.x0 - wall.c) < 1e-6:
                        s0, s1 = max(Ra.y0, Rb.y0, wall.a), min(Ra.y1, Rb.y1, wall.b)
                        if s1 - s0 > 1.1:
                            shared.append((s1 - s0, s0, s1, ra, rb))
                else:
                    if abs(Ra.y1 - wall.c) < 1e-6 and abs(Rb.y0 - wall.c) < 1e-6:
                        s0, s1 = max(Ra.x0, Rb.x0, wall.a), min(Ra.x1, Rb.x1, wall.b)
                        if s1 - s0 > 1.1:
                            shared.append((s1 - s0, s0, s1, ra, rb))
        if not shared:
            continue
        # prefer connecting to living / hallway (circulation)
        def score(s):
            ln, s0, s1, ra, rb = s
            pri = sum(2 for r in (ra, rb) if r["type"] in ("hallway", "living"))
            return pri + ln * 0.1 + rng.random() * 0.5
        shared.sort(key=score, reverse=True)
        ln, s0, s1, ra, rb = shared[0]
        types = {ra["type"], rb["type"]}
        wide = open_plan and types <= {"living", "kitchen", "dining"}
        width = min(ln - 0.4, rng.uniform(1.8, 2.8)) if wide else 0.9
        pos = rng.uniform(s0 + 0.15 + width / 2, s1 - 0.15 - width / 2)
        op = dict(kind="opening" if wide else "door", s0=round(pos - width / 2, 3), s1=round(pos + width / 2, 3),
                  z0=0.0, z1=2.05 if not wide else 2.3, rooms=[ra["id"], rb["id"]])
        wall.openings.append(op)
        doors.append(dict(op, axis=wall.axis, c=wall.c))

    # windows and the front door on exterior walls
    windows = []
    front = None
    entry_rooms = [r for r in rooms if r["type"] in ("hallway", "living")]
    for wall in walls[:4]:
        segs = []
        for r in rooms:
            R = r["rect"]
            if wall.axis == "x":
                if abs(R.y0 - wall.c) < 1e-6 or abs(R.y1 - wall.c) < 1e-6:
                    segs.append((R.x0, R.x1, r))
            else:
                if abs(R.x0 - wall.c) < 1e-6 or abs(R.x1 - wall.c) < 1e-6:
                    segs.append((R.y0, R.y1, r))
        for s0, s1, r in segs:
            ln = s1 - s0
            if front is None and r in entry_rooms and ln > 2.0 and rng.random() < 0.7:
                pos = rng.uniform(s0 + 0.6, s1 - 0.6)
                op = dict(kind="front_door", s0=round(pos - 0.5, 3), s1=round(pos + 0.5, 3), z0=0.0, z1=2.1,
                          rooms=[r["id"]])
                wall.openings.append(op)
                front = dict(op, axis=wall.axis, c=wall.c)
                continue
            if r["type"] in ("hallway",) and ln < 2.5:
                continue
            if r["type"] in ("bathroom", "laundry"):
                if ln > 1.2:
                    pos = rng.uniform(s0 + 0.5, s1 - 0.5)
                    op = dict(kind="window", s0=round(pos - 0.3, 3), s1=round(pos + 0.3, 3), z0=1.5, z1=2.1, rooms=[r["id"]])
                    wall.openings.append(op)
                    windows.append(dict(op, axis=wall.axis, c=wall.c))
                continue
            nwin = 1 if ln < 4.0 else 2
            for k in range(nwin):
                seg0 = s0 + (ln / nwin) * k
                seg1 = seg0 + ln / nwin
                ww = min(seg1 - seg0 - 0.6, rng.uniform(1.0, 1.8))
                if ww < 0.6:
                    continue
                pos = rng.uniform(seg0 + 0.3 + ww / 2, seg1 - 0.3 - ww / 2)
                sill = 0.9 if r["type"] != "living" or rng.random() < 0.6 else 0.25
                op = dict(kind="window", s0=round(pos - ww / 2, 3), s1=round(pos + ww / 2, 3), z0=sill, z1=2.15,
                          rooms=[r["id"]])
                wall.openings.append(op)
                windows.append(dict(op, axis=wall.axis, c=wall.c))
    if front is None:  # guarantee an entrance
        r = entry_rooms[0] if entry_rooms else rooms[0]
        R = r["rect"]
        wall = walls[0] if abs(R.y0) < 1e-6 else (walls[1] if abs(R.y1 - D) < 1e-6 else
                                                   (walls[2] if abs(R.x0) < 1e-6 else walls[3]))
        a, b = (R.x0, R.x1) if wall.axis == "x" else (R.y0, R.y1)
        pos = 0.5 * (a + b)
        wall.openings = [o for o in wall.openings if o["s1"] < pos - 0.6 or o["s0"] > pos + 0.6]
        op = dict(kind="front_door", s0=round(pos - 0.5, 3), s1=round(pos + 0.5, 3), z0=0.0, z1=2.1, rooms=[r["id"]])
        wall.openings.append(op)
        front = dict(op, axis=wall.axis, c=wall.c)
    for w in walls:
        w.openings.sort(key=lambda o: o["s0"])
    return dict(rooms=rooms, walls=walls, doors=doors, windows=windows, front_door=front, room_at=room_at)


def door_zones(plan, room, clearance=0.95):
    """Rectangles in front of doors / openings of ``room`` that must stay free."""
    R = room["rect"]
    zones = []
    for wall in plan["walls"]:
        for op in wall.openings:
            if room["id"] not in op.get("rooms", []) or op["kind"] == "window":
                continue
            s0, s1 = op["s0"] - 0.1, op["s1"] + 0.1
            if wall.axis == "x":
                if abs(wall.c - R.y0) < 1e-6:
                    zones.append(Rect(s0, R.y0, s1, R.y0 + clearance))
                elif abs(wall.c - R.y1) < 1e-6:
                    zones.append(Rect(s0, R.y1 - clearance, s1, R.y1))
            else:
                if abs(wall.c - R.x0) < 1e-6:
                    zones.append(Rect(R.x0, s0, R.x0 + clearance, s1))
                elif abs(wall.c - R.x1) < 1e-6:
                    zones.append(Rect(R.x1 - clearance, s0, R.x1, s1))
    return zones


def window_spans(plan, room):
    """(side, s0, s1, sill) of windows of the room. side in N,S,E,W."""
    R = room["rect"]
    out = []
    for wall in plan["walls"]:
        for op in wall.openings:
            if op["kind"] != "window" or room["id"] not in op.get("rooms", []):
                continue
            if wall.axis == "x":
                side = "S" if abs(wall.c - R.y0) < 1e-6 else "N"
            else:
                side = "W" if abs(wall.c - R.x0) < 1e-6 else "E"
            out.append((side, op["s0"], op["s1"], op["z0"]))
    return out

