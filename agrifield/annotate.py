"""Turn rendered ground-truth buffers into dataset files.

Per frame:
* ``semantic/<frame>.png``        palette colour image (see classes in scene.json)
* ``labels/<frame>.png``          8-bit class-id image
* ``instance/<frame>.png``        16-bit instance-id image (0 = none)
* ``depth/<frame>.png``           16-bit depth in millimetres (0 = sky / no return)
* ``depth/<frame>.npy``           float32 depth in metres
* ``ann/<frame>.json``            camera, visible objects (bbox / area / mask RLE),
                                   fruit key-points with visibility, projected crop rows
"""

import json
import os

import numpy as np

from . import cameras
from . import semantics
from .pngio import write_png


# instance attributes copied into per-frame objects and COCO annotations
EXTRA_KEYS = ("crop", "stage", "species", "row_id", "pose", "room", "room_type", "state", "open_angle_deg",
              "support", "on_floor", "fallen")


def rle_encode(mask):
    """COCO uncompressed RLE (column-major)."""
    flat = np.asarray(mask, dtype=np.uint8).flatten(order="F")
    if flat.size == 0:
        return {"size": list(mask.shape), "counts": []}
    change = np.flatnonzero(np.diff(flat)) + 1
    runs = np.diff(np.concatenate([[0], change, [flat.size]]))
    counts = runs.tolist()
    if flat[0] == 1:
        counts = [0] + counts
    return {"size": [int(mask.shape[0]), int(mask.shape[1])], "counts": counts}


def decode_semantic(sem_rgb):
    lut = {}
    for cid, (_, col, _) in semantics.CLASSES.items():
        lut[(col[0] << 16) | (col[1] << 8) | col[2]] = cid
    key = (sem_rgb[..., 0] << 16) | (sem_rgb[..., 1] << 8) | sem_rgb[..., 2]
    labels = np.zeros(key.shape, dtype=np.uint8)
    unknown = np.ones(key.shape, dtype=bool)
    for k, cid in lut.items():
        m = key == k
        labels[m] = cid
        unknown &= ~m
    return labels, int(unknown.sum())


def decode_instance(ins_rgb):
    return (ins_rgb[..., 0] | (ins_rgb[..., 1] << 8) | (ins_rgb[..., 2] << 16)).astype(np.int64)


class FrameWriter:
    def __init__(self, out_dir, metadata, coco_categories=None):
        self.out = out_dir
        for d in ("rgb", "semantic", "labels", "instance", "depth", "ann"):
            os.makedirs(os.path.join(out_dir, d), exist_ok=True)
        self.meta = metadata
        self.by_id = {r["instance_id"]: r for r in metadata["instances"]}
        self.coco = dict(images=[], annotations=[], categories=[])
        self.cat_ids = {}
        self.ann_id = 1

    def _cat(self, rec):
        key = rec.get("label", rec["category"])
        if key not in self.cat_ids:
            cid = len(self.cat_ids) + 1
            self.cat_ids[key] = cid
            self.coco["categories"].append(dict(id=cid, name=key, supercategory=rec["category"]))
        return self.cat_ids[key]

    def write(self, frame, cam_obj, scene, gt, pose, cam_name, pose_index, rgb_name):
        H, W = gt["instance"].shape[:2]
        labels, unknown = decode_semantic(gt["semantic"])
        inst = decode_instance(gt["instance"])
        depth = gt["depth"].astype(np.float32)
        depth[labels == 0] = 0.0
        write_png(os.path.join(self.out, "semantic", frame + ".png"), gt["semantic"].astype(np.uint8))
        write_png(os.path.join(self.out, "labels", frame + ".png"), labels)
        write_png(os.path.join(self.out, "instance", frame + ".png"), np.clip(inst, 0, 65535).astype(np.uint16))
        write_png(os.path.join(self.out, "depth", frame + ".png"),
                  np.clip(np.rint(depth * 1000.0), 0, 65535).astype(np.uint16))
        np.save(os.path.join(self.out, "depth", frame + ".npy"), depth)

        K = cameras.intrinsics(cam_obj, scene)
        ex = cameras.extrinsics(cam_obj)
        image_id = len(self.coco["images"]) + 1
        self.coco["images"].append(dict(id=image_id, file_name="rgb/" + rgb_name, width=W, height=H,
                                        camera=cam_name, pose_index=pose_index))
        objects = []
        ids, counts = np.unique(inst, return_counts=True)
        for iid, cnt in zip(ids.tolist(), counts.tolist()):
            if iid == 0 or iid not in self.by_id:
                continue
            rec = self.by_id[iid]
            m = inst == iid
            rows = np.flatnonzero(m.any(1))
            cols = np.flatnonzero(m.any(0))
            x0, x1, y0, y1 = int(cols[0]), int(cols[-1]), int(rows[0]), int(rows[-1])
            bbox = [x0, y0, x1 - x0 + 1, y1 - y0 + 1]
            o = dict(instance_id=iid, category=rec["category"], label=rec.get("label"), bbox_xywh=bbox,
                     area_px=int(cnt), truncated=bool(x0 == 0 or y0 == 0 or x1 == W - 1 or y1 == H - 1))
            for k in EXTRA_KEYS:
                if k in rec:
                    o[k] = rec[k]
            pc = cameras.project(cam_obj, scene, [rec["position"]])[0]
            if pc:
                o["base_px"] = [round(pc[0], 1), round(pc[1], 1)]
                o["distance_m"] = round(pc[2], 3)
            objects.append(o)
            self.coco["annotations"].append(dict(
                id=self.ann_id, image_id=image_id, category_id=self._cat(rec), bbox=bbox, area=int(cnt),
                iscrowd=0, segmentation=rle_encode(m), instance_id=iid,
                attributes={k: rec[k] for k in EXTRA_KEYS if k in rec}))
            self.ann_id += 1

        # fruit / harvestable organ key-points with visibility test
        fruits = []
        visible_ids = set(o["instance_id"] for o in objects)
        for iid in visible_ids:
            rec = self.by_id[iid]
            for fi, f in enumerate(rec.get("fruits", [])):
                pr = cameras.project(cam_obj, scene, [f["pos"]])[0]
                if pr is None:
                    continue
                u, v, z = pr
                if not (0 <= u < W and 0 <= v < H):
                    continue
                r_px = K["fx"] * f["radius"] / max(z, 1e-3)
                ui, vi = int(u), int(v)
                hit_inst = int(inst[vi, ui])
                hit_lab = int(labels[vi, ui])
                d = float(depth[vi, ui])
                visible = hit_inst == iid and hit_lab == semantics.class_id("crop_produce") and d <= z + f["radius"] * 1.5
                g = dict(instance_id=iid, fruit_index=fi, kind=f["kind"], center_px=[round(u, 1), round(v, 1)],
                         radius_px=round(r_px, 1), depth_m=round(z, 3), visible=bool(visible))
                for k in ("ripeness", "ripeness_class"):
                    if k in f:
                        g[k] = f[k]
                if visible:
                    g["bbox_xywh"] = [round(u - r_px, 1), round(v - r_px, 1), round(2 * r_px, 1), round(2 * r_px, 1)]
                fruits.append(g)

        # crop rows projected into the image (lane-style row lines)
        rows_px = []
        for row in self.meta["rows"]:
            pts = cameras.project(cam_obj, scene, row["polyline"])
            line = [[round(p[0], 1), round(p[1], 1)] for p in pts
                    if p is not None and -0.5 * W <= p[0] <= 1.5 * W and -0.5 * H <= p[1] <= 1.5 * H and p[2] < 60]
            if len(line) >= 2:
                rows_px.append(dict(row_id=row["row_id"], crop=row["crop"], points=line))

        hist = np.bincount(labels.ravel(), minlength=len(semantics.CLASSES)) / labels.size
        ann = dict(
            frame=frame, scenario=self.meta["scenario"]["name"], camera=cam_name, pose_index=pose_index,
            robot_pose=dict(x=round(pose[0], 4), y=round(pose[1], 4), yaw=round(pose[2], 5)),
            files=dict(rgb="rgb/" + rgb_name, semantic="semantic/%s.png" % frame, labels="labels/%s.png" % frame,
                       instance="instance/%s.png" % frame, depth_mm="depth/%s.png" % frame,
                       depth_m="depth/%s.npy" % frame),
            intrinsics=K, extrinsics=ex,
            semantic_fraction={semantics.CLASSES[i][0]: round(float(hist[i]), 5) for i in range(len(hist)) if hist[i] > 0},
            unknown_semantic_pixels=unknown,
            objects=objects, fruits=fruits, rows_px=rows_px,
        )
        with open(os.path.join(self.out, "ann", frame + ".json"), "w") as f:
            json.dump(ann, f, separators=(",", ":"))
        return ann

    def finish(self):
        self.coco["info"] = dict(description="agrifield synthetic dataset: " + self.meta["scenario"]["name"])
        with open(os.path.join(self.out, "coco_instances.json"), "w") as f:
            json.dump(self.coco, f, separators=(",", ":"))
