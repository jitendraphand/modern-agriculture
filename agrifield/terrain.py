"""Field terrain: beds, ridges, furrows, slope, undulation, wheel ruts, paddies.

The height field is an analytic function ``height(x, y)`` (numpy friendly)
so that plants, props and cameras can be placed exactly on the surface that
gets meshed.
"""

import math
import random

import numpy as np

SOILS = {
    # name: (dark, light) sRGB
    "loam": ("#3b2a1e", "#6e5440"),
    "dark_loam": ("#2a1e16", "#4e3a2a"),
    "sandy": ("#6e5a42", "#a08868"),
    "clay": ("#6a4a32", "#9a7050"),
    "red": ("#6e2e1a", "#a8543a"),
    "peat": ("#1e1812", "#3a2c22"),
    "paddy_mud": ("#3a3226", "#5a4c3a"),
    "dry_silt": ("#8a7a66", "#b8a890"),
}


def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


class Terrain:
    """Analytic field surface.

    Rows run along +y.  ``row_u`` holds the lateral (x) offset of every crop
    row before row curvature is applied.
    """

    def __init__(self, cfg, field_w, field_l, profile, row_u, bed_u, seed):
        self.cfg = cfg
        self.W = field_w
        self.Lf = field_l
        self.profile = profile            # dict(kind=flat|beds|ridges|paddy, ...)
        self.row_u = np.array(row_u, dtype=float)
        self.bed_u = np.array(bed_u, dtype=float)
        rng = random.Random(seed)
        self.undul = []
        amp = cfg.get("undulation", 0.03)
        for k in range(4):
            ang = rng.uniform(0, math.pi)
            lam = rng.uniform(6.0, 22.0)
            self.undul.append((math.cos(ang), math.sin(ang), 2 * math.pi / lam, rng.uniform(0, 6.28),
                               amp * rng.uniform(0.4, 1.0) / 2.0))
        self.curv_amp = cfg.get("row_curvature", 0.0)
        self.curv_lam = cfg.get("curvature_wavelength", 30.0)
        self.curv_phase = rng.uniform(0, 6.28)
        sd = math.radians(cfg.get("slope_dir_deg", 0.0))
        self.slope = math.tan(math.radians(cfg.get("slope_deg", 0.0)))
        self.slope_dir = (math.cos(sd), math.sin(sd))
        self.micro = cfg.get("roughness", 0.006)
        tr = cfg.get("tracks")
        self.tracks = []
        if tr and len(self.row_u) > 1:
            tr = tr if isinstance(tr, dict) else {}
            every = tr.get("every", 4)
            depth = tr.get("depth", 0.045)
            self.track_gauge = tr.get("gauge", 0.0)
            start = tr.get("start", every // 2)
            for i in range(start, len(self.row_u) - 1, every):
                self.tracks.append((0.5 * (self.row_u[i] + self.row_u[i + 1]), depth))
        self.track_gauge = getattr(self, "track_gauge", 0.0)
        self.rng_seed = seed

    # --------------------------------------------------------------- shape
    def curve(self, y):
        """Lateral row offset at y (contour / curved rows)."""
        if not self.curv_amp:
            return np.zeros_like(np.asarray(y, dtype=float))
        return self.curv_amp * np.sin(2 * math.pi * np.asarray(y) / self.curv_lam + self.curv_phase)

    def curve_slope(self, y):
        if not self.curv_amp:
            return 0.0
        return self.curv_amp * 2 * math.pi / self.curv_lam * math.cos(2 * math.pi * y / self.curv_lam + self.curv_phase)

    def base(self, x, y):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        z = self.slope * (x * self.slope_dir[0] + y * self.slope_dir[1])
        for cx, cy, k, ph, a in self.undul:
            z = z + a * np.sin(k * (x * cx + y * cy) + ph)
        return z

    def _field_window(self, x, y, margin=0.4):
        """1 inside the planted area, fading to 0 at the headlands."""
        if len(self.row_u):
            u0 = self.row_u.min() - 0.8
            u1 = self.row_u.max() + 0.8
        else:
            u0, u1 = 0.0, self.W
        wx = _smoothstep(u0 - margin, u0, x) * (1 - _smoothstep(u1, u1 + margin, x))
        wy = _smoothstep(-margin, 0.0, y) * (1 - _smoothstep(self.Lf, self.Lf + margin, y))
        return wx * wy

    def relief(self, x, y):
        """Row-structure relief (beds / ridges / small planting ridges)."""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        u = x - self.curve(y)
        kind = self.profile.get("kind", "flat")
        z = np.zeros(np.broadcast(u, y).shape)
        if kind == "beds" and len(self.bed_u):
            top = self.profile["top"] * 0.5
            pitch = self.profile["width"]
            sh = max(0.05, (pitch * 0.5 - top) * 0.7)
            d = np.min(np.abs(u[..., None] - self.bed_u), axis=-1)
            z = self.profile["height"] * (1 - _smoothstep(top, top + sh, d))
            # rounded bed shoulders
            z = z - 0.012 * _smoothstep(top * 0.6, top, d) * (d < top)
        elif kind == "ridges" and len(self.row_u):
            w = self.profile["width"] * 0.5
            d = np.min(np.abs(u[..., None] - self.row_u), axis=-1)
            z = self.profile["height"] * np.cos(np.clip(d / w, 0, 1) * math.pi / 2) ** 2
        elif kind == "flat" and len(self.row_u):
            d = np.min(np.abs(u[..., None] - self.row_u), axis=-1)
            z = self.profile.get("row_ridge", 0.025) * np.exp(-(d / 0.1) ** 2)
        g = self.track_gauge
        for c, depth in self.tracks:
            for off in ((-g / 2, g / 2) if g else (0.0,)):
                z = z - depth * np.exp(-((u - c - off) / 0.16) ** 2)
        if kind == "paddy":
            # bunds (levees) around the paddy
            bw = 0.35
            dx = np.minimum(np.abs(x - (-0.6)), np.abs(x - (self.W + 0.6)))
            dy = np.minimum(np.abs(y - (-0.6)), np.abs(y - (self.Lf + 0.6)))
            inside_x = (x > -1.2) & (x < self.W + 1.2)
            inside_y = (y > -1.2) & (y < self.Lf + 1.2)
            bund = np.maximum(np.where(inside_y, np.exp(-(dx / bw) ** 2), 0),
                              np.where(inside_x, np.exp(-(dy / bw) ** 2), 0))
            return z + 0.28 * bund
        return z * self._field_window(x, y)

    def rut_offsets(self):
        g = self.track_gauge
        out = []
        for c, _ in self.tracks:
            out.extend([c - g / 2, c + g / 2] if g else [c])
        return out

    def height(self, x, y):
        return self.base(x, y) + self.relief(x, y)

    def height1(self, x, y):
        return float(self.height(np.array([x]), np.array([y]))[0])

    def normal1(self, x, y, e=0.05):
        hx = (self.height1(x + e, y) - self.height1(x - e, y)) / (2 * e)
        hy = (self.height1(x, y + e) - self.height1(x, y - e)) / (2 * e)
        n = np.array([-hx, -hy, 1.0])
        return n / np.linalg.norm(n)

    # ---------------------------------------------------------------- mesh
    def build_meshes(self, res=0.04, margin=4.0):
        """Return (detail_mesh_args, outer_mesh_args) as (xs, ys, z) tuples."""
        x0, x1 = -margin, self.W + margin
        y0, y1 = -margin, self.Lf + margin
        nx = int((x1 - x0) / res) + 1
        ny = int((y1 - y0) / res) + 1
        xs = np.linspace(x0, x1, nx)
        ys = np.linspace(y0, y1, ny)
        gx, gy = np.meshgrid(xs, ys)
        z = np.empty_like(gx)
        # chunk rows to bound memory of the (n, rows) distance arrays
        step = max(1, int(2_000_000 / max(1, nx * max(1, len(self.row_u), len(self.bed_u)))))
        for i in range(0, ny, step):
            z[i:i + step] = self.height(gx[i:i + step], gy[i:i + step])
        rs = np.random.default_rng(self.rng_seed)
        z += np.clip(rs.normal(0.0, self.micro, z.shape), -2.5 * self.micro, 2.5 * self.micro)
        # outer apron (coarse) reaching the horizon
        R = 250.0
        oxs = np.concatenate([np.linspace(-R, x0 - 1, 24), np.linspace(x0 - 0.5, x1 + 0.5, 30), np.linspace(x1 + 1, R, 24)])
        oys = np.concatenate([np.linspace(-R, y0 - 1, 24), np.linspace(y0 - 0.5, y1 + 0.5, 30), np.linspace(y1 + 1, R, 24)])
        ogx, ogy = np.meshgrid(oxs, oys)
        inside = (ogx > x0 + 0.2) & (ogx < x1 - 0.2) & (ogy > y0 + 0.2) & (ogy < y1 - 0.2)
        oz = self.base(ogx, ogy) - np.where(inside, 0.15, 0.01)
        return (xs, ys, z), (oxs, oys, oz)
