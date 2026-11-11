"""House scenario -> rendered frames + ground truth (reuses agrifield's renderer)."""

import json
import math
import os
import random
import time

import bpy
import numpy as np
from mathutils import Vector

from agrifield import annotate, cameras, environment, render, semantics
from agrifield.pngio import write_png

from .house import HouseScene

RIG = {
    # kind, height, pitch, hfov
    "robot_head": dict(kind="robot", height=1.25, pitch=-15.0, hfov=85.0),
    "robot_vacuum": dict(kind="robot", height=0.09, pitch=4.0, hfov=110.0),
    "tabletop": dict(kind="tabletop", height=0.5, pitch=-38.0, hfov=70.0, distance=0.75),
    "room_corner": dict(kind="corner", height=2.3, pitch=-24.0, hfov=95.0),
    "topdown": dict(kind="topdown", height=0.0, pitch=-90.0, hfov=50.0),
}


def free_space(hs, clearance=0.3):
    grid, info = hs.occupancy()
    occ = grid != 0
    res = info["resolution"]
    k = int(math.ceil(clearance / res))
    dil = occ.copy()
    for dy in range(-k, k + 1):
        for dx in range(-k, k + 1):
            if dx * dx + dy * dy > k * k:
                continue
            dil |= np.roll(np.roll(occ, dy, 0), dx, 1)
    return ~dil, info, grid


def robot_poses(hs, n, rng):
    free, info, _ = free_space(hs)
    res, (ox, oy) = info["resolution"], info["origin"]
    rooms = sorted(hs.plan["rooms"], key=lambda r: -r["rect"].area)
    poses = []
    for k in range(n):
        room = rooms[k % len(rooms)]
        R = room["rect"]
        ys, xs = np.nonzero(free)
        wx = ox + (xs + 0.5) * res
        wy = oy + (ys + 0.5) * res
        m = (wx > R.x0 + 0.2) & (wx < R.x1 - 0.2) & (wy > R.y0 + 0.2) & (wy < R.y1 - 0.2)
        if not m.any():
            continue
        idx = rng.choice(list(np.flatnonzero(m)))
        x, y = float(wx[idx]), float(wy[idx])
        # look at the farthest part of the room so the view is not a wall
        tx, ty = (R.x1 if x < R.cx else R.x0), (R.y1 if y < R.cy else R.y0)
        tx, ty = 0.5 * (tx + R.cx), 0.5 * (ty + R.cy)
        yaw = math.atan2(-(tx - x), ty - y) + math.radians(rng.uniform(-25, 25))
        poses.append(dict(x=x, y=y, yaw=yaw, room=room["name"]))
    return poses


def place(spec, pose, hs, rng):
    kind = spec["kind"]
    if kind == "robot":
        loc = Vector((pose["x"], pose["y"], spec["height"]))
        return loc, cameras.look_rotation(pose["yaw"], spec["pitch"])
    if kind == "corner":
        room = next(r for r in hs.plan["rooms"] if r["name"] == pose["room"])
        R = room["rect"]
        cx = R.x0 + 0.3 if rng.random() < 0.5 else R.x1 - 0.3
        cy = R.y0 + 0.3 if rng.random() < 0.5 else R.y1 - 0.3
        yaw = math.atan2(-(R.cx - cx), R.cy - cy)
        return Vector((cx, cy, spec["height"])), cameras.look_rotation(yaw, spec["pitch"])
    if kind == "topdown":
        half = max(hs.W, hs.D) / 2 + 0.6
        z = half / math.tan(math.radians(spec["hfov"]) / 2) + hs.H
        return Vector((hs.W / 2, hs.D / 2, z)), cameras.look_rotation(0.0, -90.0)
    if kind == "tabletop":
        cands = sorted(hs.supports, key=lambda s: -len(s["items"]))[:4]
        if not cands:
            return None
        sup = rng.choice(cands)
        x0, y0, x1, y1 = sup["local"]
        mw = sup["mw"]
        c = mw @ Vector(((x0 + x1) / 2, (y0 + y1) / 2, sup["z"]))
        front = mw @ Vector(((x0 + x1) / 2, y1 + spec.get("distance", 0.75), sup["z"]))
        d = (c - front)
        yaw = math.atan2(-d.x, d.y)
        loc = Vector((front.x, front.y, sup["z"] + spec["height"]))
        return loc, cameras.look_rotation(yaw, spec["pitch"])
    raise ValueError(kind)


def run(sc, out_root, quality="preview", poses=2, samples=None, resolution=None, seed=None, save_blend=False,
        export=None, threads=0, log=print, render_frames=True):
    t0 = time.time()
    name = sc["name"]
    out = os.path.join(out_root, name)
    os.makedirs(out, exist_ok=True)
    hs = HouseScene(sc, seed=seed, log=log).build()
    scene = hs.scene
    render.configure(scene, quality, samples=samples, resolution=resolution, threads=threads)
    scene.cycles.diffuse_bounces = 4
    scene.cycles.max_bounces = 8
    rng = random.Random(hs.seed * 13 + 1)

    grid, info = hs.occupancy()
    write_png(os.path.join(out, "occupancy.png"), grid[::-1].copy())
    plan = hs.floorplan()
    plan["occupancy"] = info
    with open(os.path.join(out, "floorplan.json"), "w") as f:
        json.dump(plan, f, indent=1)

    specs = []
    for c in sc.get("cameras", ["robot_head", "robot_vacuum", "tabletop", "topdown"]):
        spec = dict(RIG[c if isinstance(c, str) else c.get("base", c["name"])])
        if isinstance(c, dict):
            spec.update(c)
        spec.setdefault("name", c if isinstance(c, str) else c["name"])
        specs.append(spec)
    plist = robot_poses(hs, poses, rng)
    meta = dict(scenario=sc, seed=hs.seed, classes=[dict(id=k, name=v[0], color=list(v[1]), description=v[2])
                                                     for k, v in sorted(semantics.CLASSES.items())],
                rows=[], instances=hs.records, floorplan=plan, cameras=specs, poses=plist, stats=hs.stats)
    cam_objs = {}
    for spec in specs:
        o = cameras.make_camera("CAM_" + spec["name"], spec["hfov"], clip_end=300)
        o.data.clip_start = 0.01
        scene.collection.objects.link(o)
        cam_objs[spec["name"]] = o
    gt = render.GroundTruth(scene) if render_frames else None
    writer = annotate.FrameWriter(out, meta) if render_frames else None
    ceilings = [o for o in scene.objects if o.get("hm_ceiling")]
    night = hs.env.get("night")
    frames = []
    for pi, pose in enumerate(plist):
        for spec in specs:
            if spec["kind"] == "topdown" and pi > 0:
                continue
            pl = place(spec, pose, hs, rng)
            if pl is None:
                continue
            cam = cam_objs[spec["name"]]
            cam.location, cam.rotation_euler = pl
            bpy.context.view_layer.update()
            scene.camera = cam
            if not render_frames:
                continue
            for o in ceilings:
                o.hide_render = spec["kind"] == "topdown"
            light = None
            if night and spec["kind"] == "robot" and sc.get("robot_light", True):
                light = environment.headlight(scene, cam, 120.0)
            frame = "%s_p%03d_%s" % (name, pi, spec["name"])
            rgb_name = frame + ".png"
            os.makedirs(os.path.join(out, "rgb"), exist_ok=True)
            tr = time.time()
            render.render_rgb(scene, os.path.join(out, "rgb", rgb_name), "PNG")
            t_rgb = time.time() - tr
            bufs = gt.render(out, frame)
            ann = writer.write(frame, cam, scene, bufs, (pose["x"], pose["y"], pose["yaw"]), spec["name"], pi, rgb_name)
            ann_path = os.path.join(out, "ann", frame + ".json")
            ann["room"] = pose["room"]
            with open(ann_path, "w") as f:
                json.dump(ann, f, separators=(",", ":"))
            if light is not None:
                bpy.data.objects.remove(light, do_unlink=True)
            frames.append(dict(frame=frame, rgb_seconds=round(t_rgb, 1), objects=len(ann["objects"])))
            log("    frame %s  rgb %.1fs  %d objects" % (frame, t_rgb, len(ann["objects"])))
        for o in ceilings:
            o.hide_render = False
    if writer:
        writer.finish()
    meta["frames"] = frames
    meta["render"] = dict(quality=quality, samples=scene.cycles.samples,
                          resolution=[scene.render.resolution_x, scene.render.resolution_y])
    with open(os.path.join(out, "scene.json"), "w") as f:
        json.dump(meta, f, separators=(",", ":"))
    if save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(os.path.join(out, name + ".blend")), compress=True)
    for fmt in (export or []):
        path = os.path.abspath(os.path.join(out, name + "." + {"usd": "usdc", "gltf": "glb", "obj": "obj"}[fmt]))
        if fmt == "usd":
            bpy.ops.wm.usd_export(filepath=path, export_materials=True)
        elif fmt == "gltf":
            bpy.ops.export_scene.gltf(filepath=path, export_format="GLB")
        else:
            bpy.ops.wm.obj_export(filepath=path)
    log("  done %s in %.1fs" % (name, time.time() - t0))
    return meta
