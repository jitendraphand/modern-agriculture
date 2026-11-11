"""Low-level procedural mesh construction.

Plants and props are assembled in plain Python into a :class:`MeshBuilder`
(vertex list + faces + a material key per face) and converted to a Blender
mesh once.  Every primitive works in the plant's local frame (z up, origin at
the soil surface).
"""

import math

import bpy
from mathutils import Matrix, Vector

UP = Vector((0.0, 0.0, 1.0))


class MeshBuilder:
    """Accumulates geometry and per-face material keys."""

    def __init__(self):
        self.verts = []
        self.faces = []
        self.face_mats = []
        self.mats = []
        self._mat_lookup = {}

    # ------------------------------------------------------------------ core
    def mat_index(self, key):
        idx = self._mat_lookup.get(key)
        if idx is None:
            idx = len(self.mats)
            self.mats.append(key)
            self._mat_lookup[key] = idx
        return idx

    def add(self, verts, faces, mat):
        mi = self.mat_index(mat)
        off = len(self.verts)
        self.verts.extend((float(v[0]), float(v[1]), float(v[2])) for v in verts)
        for f in faces:
            self.faces.append(tuple(i + off for i in f))
            self.face_mats.append(mi)

    def merge(self, other, matrix=None):
        off = len(self.verts)
        if matrix is None:
            self.verts.extend(other.verts)
        else:
            for v in other.verts:
                self.verts.append(tuple(matrix @ Vector(v)))
        remap = [self.mat_index(k) for k in other.mats]
        for f, m in zip(other.faces, other.face_mats):
            self.faces.append(tuple(i + off for i in f))
            self.face_mats.append(remap[m])

    def is_empty(self):
        return not self.faces

    def bounds(self):
        if not self.verts:
            return (0, 0, 0), (0, 0, 0)
        xs, ys, zs = zip(*self.verts)
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    def face_count(self):
        return len(self.faces)

    # --------------------------------------------------------------- to bpy
    def build(self, name, materials, smooth=True):
        """Create a ``bpy.types.Mesh``.  ``materials`` maps keys to materials."""
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.verts, [], self.faces)
        for key in self.mats:
            mesh.materials.append(materials[key])
        if self.faces:
            mesh.polygons.foreach_set("material_index", self.face_mats)
            if smooth:
                mesh.polygons.foreach_set("use_smooth", [True] * len(self.faces))
        mesh.update()
        return mesh


# ---------------------------------------------------------------- helpers
def _perp(v):
    """Any unit vector perpendicular to v."""
    a = Vector((1, 0, 0)) if abs(v.x) < 0.9 else Vector((0, 1, 0))
    p = v.cross(a)
    return p.normalized()


def direction(yaw, elev):
    """Unit vector from yaw (around z, 0 = +x) and elevation above horizon."""
    ce = math.cos(elev)
    return Vector((math.cos(yaw) * ce, math.sin(yaw) * ce, math.sin(elev)))


def polyline_arc(base, yaw, elev, length, bend, segs, gravity=True):
    """Points along a curve that starts at ``base`` heading (yaw, elev) and
    rotates its elevation by ``-bend`` radians in total (droop)."""
    pts = [Vector(base)]
    ds = length / segs
    p = Vector(base)
    for i in range(segs):
        t = (i + 0.5) / segs
        e = elev - bend * (t ** 1.3 if gravity else t)
        p = p + direction(yaw, e) * ds
        pts.append(p.copy())
    return pts


# -------------------------------------------------------------- primitives
def tube(mb, pts, radii, mat, sides=5, cap_end=False):
    """Generalised cylinder along a polyline.  ``radii`` is a list or scalar."""
    n = len(pts)
    if n < 2:
        return
    if not isinstance(radii, (list, tuple)):
        radii = [radii] * n
    pts = [Vector(p) for p in pts]
    tangents = []
    for i in range(n):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == n - 1:
            t = pts[-1] - pts[-2]
        else:
            t = pts[i + 1] - pts[i - 1]
        if t.length < 1e-9:
            t = Vector((0, 0, 1))
        tangents.append(t.normalized())
    normal = _perp(tangents[0])
    verts = []
    for i in range(n):
        t = tangents[i]
        # parallel transport of the normal
        normal = (normal - t * normal.dot(t))
        if normal.length < 1e-6:
            normal = _perp(t)
        normal.normalize()
        binorm = t.cross(normal)
        r = radii[i]
        for k in range(sides):
            a = 2 * math.pi * k / sides
            verts.append(pts[i] + (normal * math.cos(a) + binorm * math.sin(a)) * r)
    faces = []
    for i in range(n - 1):
        for k in range(sides):
            a = i * sides + k
            b = i * sides + (k + 1) % sides
            faces.append((a, b, b + sides, a + sides))
    if cap_end:
        c = len(verts)
        verts.append(pts[-1])
        base = (n - 1) * sides
        for k in range(sides):
            faces.append((base + k, base + (k + 1) % sides, c))
    mb.add(verts, faces, mat)


def _profile(kind, t):
    if kind == "strap":          # grasses, corn: wide base, long taper
        return min(1.0, 0.35 + 3.0 * t) * (1.0 - t ** 2.2)
    if kind == "lanceolate":     # narrow, widest ~40%
        return math.sin(math.pi * t ** 0.85) ** 0.9
    if kind == "ovate":          # widest ~30%
        return math.sin(math.pi * t ** 0.65)
    if kind == "obovate":        # widest near tip (lettuce, spinach)
        return math.sin(math.pi * t ** 1.5) ** 0.8
    if kind == "round":          # cabbage, pumpkin
        return math.sin(math.pi * t) ** 0.55
    if kind == "heart":          # sunflower, cotton lobes
        return math.sin(math.pi * t ** 0.55) ** 0.8
    if kind == "needle":         # onion-like / awns
        return 1.0 - t
    return math.sin(math.pi * t)


def leaf(mb, base, yaw, elev, length, width, mat, droop=0.6, segs=6,
         profile="ovate", across=3, fold=0.15, cup=0.0, wave=0.0,
         wave_freq=6.0, roll=0.0, curl=0.0, phase=0.0, min_width=0.0):
    """A leaf blade as a strip of quads along a drooping midrib.

    ``elev`` is the initial elevation of the midrib, ``droop`` the total
    elevation drop along the blade (radians), ``fold`` raises the midrib (V
    shape), ``cup`` lifts the margins (cupped cabbage leaves), ``wave``
    ruffles the margins (lettuce).  Returns the tip position.
    """
    across = max(3, across | 1)  # odd, >= 3
    half = across // 2
    ss = [(j - half) / half for j in range(across)]
    pts = []
    p = Vector(base)
    ds = length / segs
    pts.append(p.copy())
    for i in range(segs):
        t = (i + 0.5) / segs
        e = elev - droop * t ** 1.3
        y = yaw + curl * t
        p = p + direction(y, e) * ds
        pts.append(p.copy())
    verts = []
    for i, c in enumerate(pts):
        t = i / segs
        if i < segs:
            d = (pts[i + 1] - pts[i]).normalized()
        else:
            d = (pts[i] - pts[i - 1]).normalized()
        side = Vector((-math.sin(yaw + curl * t), math.cos(yaw + curl * t), 0.0))
        if abs(roll) > 1e-6:
            side = Matrix.Rotation(roll, 3, d) @ side
        side = (side - d * side.dot(d)).normalized()
        up = d.cross(side).normalized()
        if up.z < 0:
            up = -up
        w = width * max(min_width, _profile(profile, t))
        for s in ss:
            off = side * (s * w * 0.5)
            lift = cup * (s * s) * w * 0.5 - fold * abs(s) * w * 0.25
            if wave:
                lift += wave * w * abs(s) ** 1.5 * math.sin(wave_freq * t * math.pi + phase + 2.0 * s)
            verts.append(c + off + up * lift)
    faces = []
    for i in range(segs):
        for j in range(across - 1):
            a = i * across + j
            faces.append((a, a + 1, a + 1 + across, a + across))
    mb.add(verts, faces, mat)
    return pts[-1]


def ellipsoid(mb, center, radii, mat, u=8, v=6, matrix=None, rib=0.0,
              ribs=0, squash_top=0.0, jitter=None, rng=None, pointy=0.0):
    """UV ellipsoid.  ``rib`` modulates the radius with ``ribs`` lobes
    (pumpkin), ``pointy`` stretches the bottom into a cone (strawberry)."""
    rx, ry, rz = radii
    verts = []
    rot = matrix if matrix is not None else Matrix.Identity(3)
    for i in range(1, v):
        th = math.pi * i / v
        st, ct = math.sin(th), math.cos(th)
        for k in range(u):
            ph = 2 * math.pi * k / u
            r = 1.0
            if ribs:
                r *= 1.0 - rib * (0.5 - 0.5 * math.cos(ribs * ph))
            z = ct
            if squash_top and z > 0:
                z *= 1.0 - squash_top
            if pointy and z < 0:
                z *= 1.0 + pointy
                r *= 1.0 - pointy * 0.35 * (-ct)
            p = Vector((rx * st * math.cos(ph) * r, ry * st * math.sin(ph) * r, rz * z))
            if jitter and rng is not None:
                p *= 1.0 + rng.uniform(-jitter, jitter)
            verts.append(Vector(center) + rot @ p)
    top = len(verts)
    zt = rz * (1.0 - squash_top)
    verts.append(Vector(center) + rot @ Vector((0, 0, zt * (1.0 - rib * 0.6 if ribs else 1.0))))
    bot = len(verts)
    verts.append(Vector(center) + rot @ Vector((0, 0, -rz * (1.0 + pointy))))
    faces = []
    for i in range(v - 2):
        for k in range(u):
            a = i * u + k
            b = i * u + (k + 1) % u
            faces.append((a, b, b + u, a + u))
    for k in range(u):
        faces.append((top, (k + 1) % u, k))
        a = (v - 2) * u
        faces.append((bot, a + k, a + (k + 1) % u))
    mb.add(verts, faces, mat)


def disc(mb, center, normal, radius, mat, segs=12, dome=0.0):
    normal = Vector(normal).normalized()
    a = _perp(normal)
    b = normal.cross(a)
    verts = [Vector(center) + normal * dome]
    for k in range(segs):
        ang = 2 * math.pi * k / segs
        verts.append(Vector(center) + (a * math.cos(ang) + b * math.sin(ang)) * radius)
    faces = [(0, 1 + k, 1 + (k + 1) % segs) for k in range(segs)]
    mb.add(verts, faces, mat)


def box(mb, center, size, mat, yaw=0.0):
    cx, cy, cz = center
    sx, sy, sz = (s * 0.5 for s in size)
    r = Matrix.Rotation(yaw, 3, "Z")
    corners = []
    for z in (-sz, sz):
        for y in (-sy, sy):
            for x in (-sx, sx):
                corners.append(Vector((cx, cy, cz)) + r @ Vector((x, y, z)))
    faces = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    mb.add(corners, faces, mat)


def cone(mb, base, tip, radius, mat, sides=6):
    base = Vector(base)
    tip = Vector(tip)
    d = (tip - base).normalized()
    a = _perp(d)
    b = d.cross(a)
    verts = [base + (a * math.cos(2 * math.pi * k / sides) + b * math.sin(2 * math.pi * k / sides)) * radius
             for k in range(sides)]
    verts.append(tip)
    faces = [(k, (k + 1) % sides, sides) for k in range(sides)]
    mb.add(verts, faces, mat)


def rock(mb, center, size, mat, rng, detail=2):
    """Irregular rock: a jittered, flattened ellipsoid."""
    u, v = 7 + detail * 2, 5 + detail
    ellipsoid(mb, center, (size, size * rng.uniform(0.6, 1.0), size * rng.uniform(0.35, 0.7)),
              mat, u=u, v=v, matrix=Matrix.Rotation(rng.uniform(0, 6.28), 3, "Z"),
              jitter=0.22, rng=rng)


def grid_mesh(name, xs, ys, heights, materials=None):
    """Fast regular-grid mesh from numpy arrays (heights shape: len(ys) x len(xs))."""
    import numpy as np
    nx, ny = len(xs), len(ys)
    gx, gy = np.meshgrid(xs, ys)
    co = np.stack([gx.ravel(), gy.ravel(), heights.ravel()], axis=1).astype(np.float32)
    ix = np.arange(nx * ny).reshape(ny, nx)
    a = ix[:-1, :-1].ravel()
    b = ix[:-1, 1:].ravel()
    c = ix[1:, 1:].ravel()
    d = ix[1:, :-1].ravel()
    quads = np.stack([a, b, c, d], axis=1).astype(np.int32)
    nf = len(quads)
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(nx * ny)
    mesh.vertices.foreach_set("co", co.ravel())
    mesh.loops.add(nf * 4)
    mesh.loops.foreach_set("vertex_index", quads.ravel())
    mesh.polygons.add(nf)
    mesh.polygons.foreach_set("loop_start", np.arange(0, nf * 4, 4, dtype=np.int32))
    mesh.polygons.foreach_set("use_smooth", np.ones(nf, dtype=bool))
    mesh.update(calc_edges=True)
    mesh.validate()
    if materials:
        for m in materials:
            mesh.materials.append(m)
    return mesh
