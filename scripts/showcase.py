"""Render a gallery of every crop model at every growth stage.

    blender -b -P scripts/showcase.py -- --out docs/crops [--crop tomato] [--samples 32]
    python scripts/showcase.py --out docs/crops          # with the bpy module

One image per crop: its stages side by side (young -> mature, left -> right).
"""

import argparse
import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from agrifield import cameras, crops, environment, materials, render, weeds  # noqa: E402
from agrifield import meshkit as mk  # noqa: E402
from agrifield.terrain import SOILS  # noqa: E402


def argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else a[1:]


def build_crop_row(crop, lib, samples, out, res):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    stages = list(crop.stages)
    specs = {}
    for st in stages:
        specs.update(crop.materials(st, {}))
    specs["soil"] = dict(kind="soil", dark=SOILS["loam"][0], light=SOILS["loam"][1], wetness=0.1)
    lib = materials.MaterialLibrary()
    lib.register(specs)
    heights = []
    models = []
    for st in stages:
        pm = crop.build(st, random.Random(7), {"segment_length": 0.5})
        lo, hi = pm.mb.bounds()
        models.append((st, pm, lo, hi))
        heights.append(hi[2])
    widths = [max(hi[0] - lo[0], hi[1] - lo[1], 0.15) for _, _, lo, hi in models]
    gap = max(0.12, 0.25 * max(widths))
    x = 0.0
    centers = []
    for (st, pm, lo, hi), w in zip(models, widths):
        x += w / 2
        me = pm.mb.build("%s_%s" % (crop.name, st), lib.resolve(pm.mb.mats))
        o = bpy.data.objects.new(me.name, me)
        o.location = (x, 0, 0)
        scene.collection.objects.link(o)
        centers.append(x)
        x += w / 2 + gap
    total = x - gap
    H = max(heights + [0.2])
    ground = mk.MeshBuilder()
    s = max(total, H) * 3 + 4
    ground.add([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [(0, 1, 2, 3)], "soil")
    gme = ground.build("ground", lib.resolve(ground.mats), smooth=False)
    scene.collection.objects.link(bpy.data.objects.new("ground", gme))
    environment.setup(scene, dict(lighting="morning", exposure=0.2), (total / 2, 0))
    render.configure(scene, "draft", samples=samples, resolution=res)
    aspect = res[0] / res[1]
    hfov = 40.0
    span = max(total * 1.12, H * 1.25 * aspect)
    dist = span / 2 / math.tan(math.radians(hfov / 2))
    cam = cameras.make_camera("cam", hfov)
    scene.collection.objects.link(cam)
    pitch = -14.0
    target = Vector((total / 2, 0, H * 0.45))
    d = Vector((0, math.cos(math.radians(pitch)), math.sin(math.radians(pitch))))
    cam.location = target - d * dist
    cam.rotation_euler = cameras.look_rotation(0.0, pitch)
    scene.camera = cam
    path = os.path.join(out, "%s.jpg" % crop.name)
    render.render_rgb(scene, path, "JPEG")
    return path, stages


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="docs/crops")
    p.add_argument("--crop", action="append")
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--res", default="1200x480")
    a = p.parse_args(argv())
    os.makedirs(a.out, exist_ok=True)
    res = tuple(int(v) for v in a.res.split("x"))
    names = a.crop or list(crops.CROPS)
    for n in names:
        path, stages = build_crop_row(crops.CROPS[n], None, a.samples, a.out, res)
        print("wrote", path, "stages:", ", ".join(stages))
    _ = weeds


if __name__ == "__main__":
    main()
