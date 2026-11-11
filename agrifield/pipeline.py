"""End-to-end: scenario -> scene -> rendered frames + annotations."""

import json
import math
import os
import random
import time

import bpy

from . import annotate
from . import cameras
from . import environment
from . import render
from .scene import FieldScene


def canopy_height(fs):
    hs = sorted(r["height"] for r in fs.reg.records if r.get("category") == "crop" and "height" in r)
    if not hs:
        return 0.3
    return hs[int(0.9 * (len(hs) - 1))]


def adapt_cameras(specs, fs):
    """Fit rig heights to the crop: nadir stays above the canopy, the side
    camera looks at the middle of the canopy (top of bed included)."""
    canopy = canopy_height(fs)
    bed_h = fs.profile.get("height", 0.0) if fs.profile.get("kind") in ("beds", "ridges") else 0.0
    for spec in specs:
        if spec.get("fixed"):
            continue
        if spec["kind"] == "row_nadir":
            spec["height"] = round(max(spec["height"], canopy + bed_h + 0.5), 3)
        elif spec["kind"] == "row_side":
            spec["height"] = round(min(1.7, max(0.25, bed_h + canopy * 0.55)), 3)
            if canopy < 0.5:
                spec["height"] = round(bed_h + canopy + 0.35, 3)
                spec["pitch"] = min(spec["pitch"], -40.0)
                spec["distance"] = max(spec.get("distance", 0.7), 0.45)
            elif canopy > 2.0:
                spec["distance"] = max(spec.get("distance", 0.7), 1.0)
                spec["pitch"] = 5.0
        elif spec["kind"] == "robot" and spec["name"] == "front" and canopy > 1.2 and not spec.get("keep_height"):
            spec["height"] = max(spec["height"], 1.2)
            spec["pitch"] = max(spec["pitch"], -14.0)
    return canopy


def path_offsets(fs, sc):
    """Lateral offsets (before curvature) of candidate robot driving lines."""
    mode = sc.get("robot", {}).get("path", "auto")
    if mode == "track" and fs.terrain.tracks:
        return [c for c, _ in fs.terrain.tracks]
    if fs.bed_u and mode in ("auto", "furrow"):
        if len(fs.bed_u) >= 2:
            return [0.5 * (fs.bed_u[i] + fs.bed_u[i + 1]) for i in range(len(fs.bed_u) - 1)]
    if fs.bed_u and mode == "bed":
        return list(fs.bed_u)
    if len(fs.row_u) >= 2:
        return [0.5 * (fs.row_u[i] + fs.row_u[i + 1]) for i in range(len(fs.row_u) - 1)]
    return [sc["field"]["width"] / 2]


def resolve_cameras(sc):
    out = []
    for c in sc.get("cameras", ["front"]):
        if isinstance(c, str):
            spec = dict(cameras.DEFAULT_RIG[c])
            spec["name"] = c
        else:
            base = dict(cameras.DEFAULT_RIG[c.get("base", c["name"])])
            base.update(c)
            spec = base
        out.append(spec)
    robot = sc.get("robot", {})
    for spec in out:
        if spec["kind"] == "robot":
            spec["height"] = robot.get("camera_height", spec["height"]) if spec["name"] == "front" else spec["height"]
            spec["pitch"] = robot.get("camera_pitch", spec["pitch"]) if spec["name"] == "front" else spec["pitch"]
    return out


def run(sc, out_root, quality="preview", poses=1, render_frames=True, ground_truth=True,
        save_blend=False, export=None, samples=None, resolution=None, seed=None, threads=0,
        rgb_format="PNG", log=print):
    t0 = time.time()
    name = sc["name"]
    out_dir = os.path.join(out_root, name)
    os.makedirs(out_dir, exist_ok=True)
    fs = FieldScene(sc, seed=seed, log=log).build()
    scene = fs.scene
    render.configure(scene, quality, samples=samples, resolution=resolution, threads=threads)

    specs = resolve_cameras(sc)
    canopy = adapt_cameras(specs, fs)
    rng = random.Random(fs.seed * 7 + 3)
    field = sc["field"]
    row_xs = list(fs.row_u)
    paths = path_offsets(fs, sc)
    path_idx = sc.get("robot", {}).get("path_index")
    pose_list = cameras.rig_poses(field, fs.terrain, paths, rng, poses, path_idx)

    cam_objs = {}
    for spec in specs:
        obj = cameras.make_camera("CAM_" + spec["name"], spec["hfov"])
        scene.collection.objects.link(obj)
        cam_objs[spec["name"]] = obj
    meta = fs.metadata()
    meta["cameras"] = specs
    meta["poses"] = [dict(x=p[0], y=p[1], yaw=p[2]) for p in pose_list]
    meta["canopy_height_p90"] = round(canopy, 3)

    gt = render.GroundTruth(scene) if (render_frames and ground_truth) else None
    writer = annotate.FrameWriter(out_dir, meta) if gt else None
    frames = []
    night = fs.env.get("night")
    for pi, pose in enumerate(pose_list):
        for spec in specs:
            cam = cam_objs[spec["name"]]
            loc, rot = cameras.place(spec["name"], spec, pose, fs.terrain, field, row_xs)
            cam.location = loc
            cam.rotation_euler = rot
            bpy.context.view_layer.update()
            scene.camera = cam
            if not render_frames:
                continue
            light = environment.headlight(scene, cam, sc.get("environment", {}).get("headlight", 900.0)) if night else None
            frame = "%s_p%03d_%s" % (name, pi, spec["name"])
            ext = ".jpg" if rgb_format == "JPEG" else ".png"
            rgb_name = frame + ext
            os.makedirs(os.path.join(out_dir, "rgb"), exist_ok=True)
            tr = time.time()
            render.render_rgb(scene, os.path.join(out_dir, "rgb", rgb_name), rgb_format)
            t_rgb = time.time() - tr
            info = dict(frame=frame, rgb_seconds=round(t_rgb, 1))
            if gt:
                tg = time.time()
                bufs = gt.render(out_dir, frame)
                ann = writer.write(frame, cam, scene, bufs, pose, spec["name"], pi, rgb_name)
                info.update(gt_seconds=round(time.time() - tg, 1), objects=len(ann["objects"]),
                            fruits_visible=sum(1 for f in ann["fruits"] if f["visible"]))
            if light is not None:
                bpy.data.objects.remove(light, do_unlink=True)
            frames.append(info)
            log("    frame %s  rgb %.1fs%s" % (frame, t_rgb, ("  gt %.1fs, %d objects" % (info["gt_seconds"], info["objects"])) if gt else ""))
    if writer:
        writer.finish()

    meta["frames"] = frames
    meta["render"] = dict(quality=quality, samples=scene.cycles.samples,
                          resolution=[scene.render.resolution_x, scene.render.resolution_y])
    with open(os.path.join(out_dir, "scene.json"), "w") as f:
        json.dump(meta, f, separators=(",", ":"))

    if save_blend:
        scene.camera = cam_objs[specs[0]["name"]]
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(os.path.join(out_dir, name + ".blend")), compress=True)
    for fmt in (export or []):
        path = os.path.abspath(os.path.join(out_dir, name + "." + {"usd": "usdc", "gltf": "glb", "obj": "obj", "fbx": "fbx"}[fmt]))
        if fmt == "usd":
            bpy.ops.wm.usd_export(filepath=path, export_materials=True)
        elif fmt == "gltf":
            bpy.ops.export_scene.gltf(filepath=path, export_format="GLB")
        elif fmt == "obj":
            bpy.ops.wm.obj_export(filepath=path)
        elif fmt == "fbx":
            bpy.ops.export_scene.fbx(filepath=path)
        log("    exported %s" % path)
    log("  done %s in %.1fs" % (name, time.time() - t0))
    return meta
