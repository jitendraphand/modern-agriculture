"""Build preview images from rendered scenario folders.

    python scripts/make_gallery.py --src output --dst docs/gallery

For every scenario: <dst>/<name>.jpg = [camera 1 RGB | camera 2 RGB | overview]
                                        [camera 1 semantic | instance | depth   ]
plus <dst>/contact_sheet.jpg with the overview of every scenario.
"""

import argparse
import glob
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bpy  # noqa: E402

from agrifield.pngio import read_png  # noqa: E402


def argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else a[1:]


def load(path):
    im = bpy.data.images.load(path, check_existing=False)
    w, h = im.size
    px = np.empty(w * h * im.channels, np.float32)
    im.pixels.foreach_get(px)
    px = px.reshape(h, w, im.channels)[::-1]
    bpy.data.images.remove(im)
    if px.shape[2] == 1:
        px = np.repeat(px, 3, 2)
    return px[..., :3]


def resize(img, w, h):
    ys = (np.arange(h) * img.shape[0] / h).astype(int)
    xs = (np.arange(w) * img.shape[1] / w).astype(int)
    return img[ys][:, xs]


def colorize_ids(ids):
    ids = ids.astype(np.int64)
    rng = np.random.default_rng(1)
    lut = rng.random((int(ids.max()) + 1, 3)).astype(np.float32) * 0.8 + 0.2
    lut[0] = 0
    return lut[ids]


def colorize_depth(d):
    valid = d > 0
    out = np.zeros(d.shape + (3,), np.float32)
    if valid.any():
        lo, hi = np.percentile(d[valid], 2), np.percentile(d[valid], 98)
        t = np.clip((d - lo) / max(hi - lo, 1e-3), 0, 1)
        out[..., 0] = 1 - t
        out[..., 1] = 0.3 + 0.5 * (1 - abs(t - 0.5) * 2)
        out[..., 2] = t
        out[~valid] = 0
    return out


def save(img, path, quality=85):
    h, w = img.shape[:2]
    im = bpy.data.images.new("out", w, h)
    rgba = np.concatenate([img[::-1], np.ones((h, w, 1), np.float32)], 2)
    im.pixels.foreach_set(rgba.ravel())
    im.filepath_raw = path
    im.file_format = "JPEG"
    bpy.context.scene.render.image_settings.quality = quality
    im.save()
    bpy.data.images.remove(im)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--src", default="output")
    p.add_argument("--dst", default="docs/gallery")
    p.add_argument("--tile", default="480x270")
    a = p.parse_args(argv())
    tw, th = (int(v) for v in a.tile.split("x"))
    os.makedirs(a.dst, exist_ok=True)
    overviews = []
    for sj in sorted(glob.glob(os.path.join(a.src, "*", "scene.json"))):
        d = os.path.dirname(sj)
        meta = json.load(open(sj))
        name = meta["scenario"]["name"]
        cams = [c["name"] for c in meta["cameras"]]
        frames = {c: "%s_p000_%s" % (name, c) for c in cams}
        rgb = {c: glob.glob(os.path.join(d, "rgb", frames[c] + ".*")) for c in cams}
        ovname = "overview" if "overview" in cams else ("topdown" if "topdown" in cams else None)
        main_cams = [c for c in cams if c != ovname][:2]
        if not main_cams or not rgb[main_cams[0]]:
            continue
        top = [resize(load(rgb[c][0]), tw, th) for c in main_cams]
        ov = None
        if ovname and rgb[ovname]:
            ov = resize(load(rgb[ovname][0]), tw, th)
            top.append(ov)
            overviews.append((name, ov))
        while len(top) < 3:
            top.append(np.zeros((th, tw, 3), np.float32))
        f0 = frames[main_cams[0]]
        sem = resize(load(os.path.join(d, "semantic", f0 + ".png")), tw, th)
        ids = read_png(os.path.join(d, "instance", f0 + ".png")).astype(np.int64)
        ins = resize(colorize_ids(ids), tw, th)
        dep = resize(colorize_depth(np.load(os.path.join(d, "depth", f0 + ".npy"))), tw, th)
        grid = np.concatenate([np.concatenate(top[:3], 1), np.concatenate([sem, ins, dep], 1)], 0)
        save(grid, os.path.join(a.dst, name + ".jpg"))
        print("gallery", name)
    if overviews:
        cols = 6
        rows = math.ceil(len(overviews) / cols)
        sw, sh = tw // 2, th // 2
        sheet = np.ones((rows * sh, cols * sw, 3), np.float32)
        for k, (_, ov) in enumerate(overviews):
            r, c = divmod(k, cols)
            sheet[r * sh:(r + 1) * sh, c * sw:(c + 1) * sw] = resize(ov, sw, sh)
        save(sheet, os.path.join(a.dst, "contact_sheet.jpg"), 88)
        print("contact sheet with %d scenarios" % len(overviews))


if __name__ == "__main__":
    main()
