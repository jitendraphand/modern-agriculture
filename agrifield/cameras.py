"""Robot / drone camera rigs and intrinsics/extrinsics export."""

import math

import bpy
from mathutils import Euler, Matrix, Vector

DEFAULT_RIG = {
    # name: dict(kind, height, pitch(deg, negative = down), hfov(deg), lateral offset)
    "front": dict(kind="robot", height=1.0, pitch=-32.0, hfov=78.0),
    "front_low": dict(kind="robot", height=0.45, pitch=-8.0, hfov=90.0),
    "nadir": dict(kind="row_nadir", height=0.9, pitch=-90.0, hfov=62.0),
    "side": dict(kind="row_side", height=0.9, pitch=-5.0, hfov=70.0, distance=0.7),
    "drone": dict(kind="drone", height=11.0, pitch=-90.0, hfov=70.0),
    "drone_oblique": dict(kind="drone", height=9.0, pitch=-40.0, hfov=75.0, back=8.0),
    "overview": dict(kind="overview", height=4.5, pitch=-24.0, hfov=70.0),
}

SENSOR_WIDTH_MM = 7.6  # roughly a 1/1.8" machine-vision sensor


def make_camera(name, hfov_deg, clip_end=500.0):
    cam = bpy.data.cameras.new(name)
    cam.sensor_fit = "HORIZONTAL"
    cam.sensor_width = SENSOR_WIDTH_MM
    cam.lens = SENSOR_WIDTH_MM / (2 * math.tan(math.radians(hfov_deg) / 2))
    cam.clip_start = 0.02
    cam.clip_end = clip_end
    obj = bpy.data.objects.new(name, cam)
    return obj


def look_rotation(yaw, pitch):
    """Blender camera rotation: heading ``yaw`` (rotation about z, 0 looks
    along +y, positive turns toward -x) and ``pitch`` in degrees."""
    # camera looks along -Z; first point it along +y horizontally, then pitch
    rot = Euler((math.radians(90.0 + pitch), 0.0, yaw), "XYZ")
    return rot


def intrinsics(cam_obj, scene):
    cam = cam_obj.data
    W = scene.render.resolution_x * scene.render.resolution_percentage / 100.0
    H = scene.render.resolution_y * scene.render.resolution_percentage / 100.0
    fx = cam.lens / cam.sensor_width * W
    fy = fx * scene.render.pixel_aspect_x / scene.render.pixel_aspect_y
    cx = W * (0.5 - cam.shift_x)
    cy = H * 0.5 + cam.shift_y * W
    return {
        "width": int(W), "height": int(H),
        "fx": fx, "fy": fy, "cx": cx, "cy": cy,
        "K": [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]],
        "hfov_deg": math.degrees(2 * math.atan(W / (2 * fx))),
        "vfov_deg": math.degrees(2 * math.atan(H / (2 * fy))),
        "focal_mm": cam.lens, "sensor_width_mm": cam.sensor_width,
        "clip": [cam.clip_start, cam.clip_end],
    }


def extrinsics(cam_obj):
    """World->camera in OpenCV convention (x right, y down, z forward)."""
    m = cam_obj.matrix_world
    R_bc = m.to_3x3()
    t = m.to_translation()
    flip = Matrix(((1, 0, 0), (0, -1, 0), (0, 0, -1)))
    R_wc = (R_bc @ flip)              # camera(opencv) -> world
    R_cw = R_wc.transposed()          # world -> camera
    t_cw = -(R_cw @ t)
    return {
        "camera_to_world_blender": [list(r) for r in m],
        "R_world_to_cam_cv": [list(r) for r in R_cw],
        "t_world_to_cam_cv": list(t_cw),
        "position": list(t),
    }


def project(cam_obj, scene, points):
    """Project world points -> pixel (u, v) and camera-z depth (OpenCV)."""
    K = intrinsics(cam_obj, scene)
    ex = extrinsics(cam_obj)
    R = Matrix(ex["R_world_to_cam_cv"])
    t = Vector(ex["t_world_to_cam_cv"])
    out = []
    for p in points:
        pc = R @ Vector(p) + t
        if pc.z <= 1e-4:
            out.append(None)
            continue
        u = K["fx"] * pc.x / pc.z + K["cx"]
        v = K["fy"] * pc.y / pc.z + K["cy"]
        out.append((u, v, pc.z))
    return out


def rig_poses(field, terrain, path_us, rng, poses, path_index=None):
    """Robot poses (x, y, yaw) along one driving line.

    ``path_us`` are lateral offsets of candidate driving lines (inter-rows,
    furrows, tramlines); the middle one is used unless ``path_index`` is set.
    Poses are spread along the row with small heading / lateral noise.
    """
    if path_index is None:
        path_index = len(path_us) // 2
    u = path_us[max(0, min(len(path_us) - 1, path_index))]
    out = []
    L = field["length"]
    for k in range(poses):
        frac = 0.12 + 0.6 * (k / max(1, poses - 1) if poses > 1 else 0.0)
        y = L * frac + rng.uniform(-0.3, 0.3) * (poses > 1)
        x = u + float(terrain.curve(y)) + rng.uniform(-0.04, 0.04)
        heading = -math.atan(terrain.curve_slope(y)) + math.radians(rng.uniform(-2.5, 2.5))
        out.append((x, y, heading))
    return out


def place(cam_name, spec, pose, terrain, field, row_xs):
    """Compute (location, rotation) for one camera of the rig at a robot pose."""
    x, y, heading = pose
    kind = spec["kind"]
    pitch = spec["pitch"]
    yaw = heading
    if kind == "robot":
        loc = Vector((x, y, terrain.height1(x, y) + spec["height"]))
    elif kind == "row_nadir":
        # hover over the nearest crop row
        rx = min(row_xs, key=lambda r: abs(r + float(terrain.curve(y)) - x)) + float(terrain.curve(y)) if row_xs else x
        loc = Vector((rx, y, terrain.height1(rx, y) + spec["height"]))
    elif kind == "row_side":
        rx = min(row_xs, key=lambda r: abs(r + float(terrain.curve(y)) - x)) + float(terrain.curve(y)) if row_xs else x
        side = 1.0 if rx >= x else -1.0
        cx = rx - side * spec.get("distance", 0.7)
        loc = Vector((cx, y, terrain.height1(cx, y) + spec["height"]))
        yaw = heading - side * math.pi / 2
    elif kind == "drone":
        back = spec.get("back", 0.0)
        cx, cy = field["width"] / 2, field["length"] / 2 - back
        if back == 0.0:
            cy = y
        loc = Vector((cx, cy, terrain.height1(cx, cy) + spec["height"]))
        yaw = 0.0
    elif kind == "overview":
        cx, cy = field["width"] * 0.5, -2.5
        loc = Vector((cx, cy, terrain.height1(cx, max(cy, 0.0)) + spec["height"]))
        yaw = 0.0
    else:
        raise ValueError(kind)
    rot = look_rotation(yaw, pitch)
    return loc, rot
