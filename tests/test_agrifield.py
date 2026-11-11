"""Tests.  Run with the bpy module installed:  python -m pytest tests -q

The scene/render tests are skipped when ``bpy`` is not importable.
"""

import importlib.util
import json
import os
import sys
import tempfile

import numpy as np
import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

HAS_BPY = importlib.util.find_spec("bpy") is not None
needs_bpy = pytest.mark.skipif(not HAS_BPY, reason="bpy not installed")


def _read_png(path):
    from agrifield.pngio import read_png
    return read_png(path)


def test_png_roundtrip():
    from agrifield.pngio import write_png
    with tempfile.TemporaryDirectory() as d:
        a8 = (np.arange(60).reshape(6, 10) % 256).astype(np.uint8)
        a16 = (np.arange(60).reshape(6, 10) * 1000).astype(np.uint16)
        rgb = np.random.default_rng(0).integers(0, 255, (5, 7, 3)).astype(np.uint8)
        for arr, name in ((a8, "a.png"), (a16, "b.png"), (rgb, "c.png")):
            p = os.path.join(d, name)
            write_png(p, arr)
            assert np.array_equal(_read_png(p).astype(arr.dtype), arr)


def test_rle_roundtrip():
    from agrifield.annotate import rle_encode
    m = np.zeros((7, 5), dtype=np.uint8)
    m[2:5, 1:3] = 1
    m[0, 0] = 1
    r = rle_encode(m)
    flat = []
    v = 0
    for c in r["counts"]:
        flat.extend([v] * c)
        v ^= 1
    assert np.array_equal(np.array(flat).reshape(5, 7).T, m)


def test_semantic_tables_unique():
    from agrifield import semantics
    cols = [v[1] for v in semantics.CLASSES.values()]
    assert len(set(cols)) == len(cols)
    assert semantics.encode_instance(0x030201) == (1 / 255, 2 / 255, 3 / 255)


@needs_bpy
def test_catalog_has_30_plus_valid_scenarios():
    from agrifield import cameras, crops, scenarios
    assert len(scenarios.SCENARIOS) >= 30
    names = [s["name"] for s in scenarios.SCENARIOS]
    assert len(set(names)) == len(names)
    for s in scenarios.SCENARIOS:
        for e in s["crops"]:
            c = crops.CROPS[e["crop"]]
            for st in (e.get("stage_mix") or {e["stage"]: 1}):
                assert st in c.stages, (s["name"], st)
        for cam in s["cameras"]:
            name = cam if isinstance(cam, str) else cam.get("base", cam["name"])
            assert name in cameras.DEFAULT_RIG
        json.dumps(s)


@needs_bpy
@pytest.mark.parametrize("crop", ["corn", "wheat", "rice", "soybean", "lettuce", "cabbage", "tomato", "potato",
                                  "sunflower", "strawberry", "grapevine", "apple", "cotton", "onion", "carrot",
                                  "pumpkin"])
def test_every_crop_stage_builds(crop):
    import random
    from agrifield import crops
    c = crops.CROPS[crop]
    for st in c.stages:
        pm = c.build(st, random.Random(1), {"segment_length": 0.5})
        assert pm.mb.face_count() > 10
        lo, hi = pm.mb.bounds()
        assert hi[2] > 0.0
        assert set(pm.mb.mats) <= set(c.materials(st, {})), (crop, st)


@needs_bpy
def test_render_ground_truth_is_exact():
    from agrifield import pipeline
    sc = dict(name="t_small", seed=3, field=dict(width=3.0, length=4.0),
              crops=[dict(crop="lettuce", stage="rosette")],
              terrain=dict(soil="loam", mulch="black"),
              weeds=dict(density=3, species={"pigweed": 1}, stage="small"),
              props=[dict(type="rocks", count=3)],
              environment=dict(lighting="noon", background="none"),
              cameras=["nadir"])
    with tempfile.TemporaryDirectory() as d:
        meta = pipeline.run(sc, d, quality="draft", samples=4, resolution=(160, 90), log=lambda *a: None)
        out = os.path.join(d, "t_small")
        ann = json.load(open(os.path.join(out, "ann", "t_small_p000_nadir.json")))
        assert ann["unknown_semantic_pixels"] == 0
        ids = {r["instance_id"] for r in meta["instances"]}
        inst = _read_png(os.path.join(out, "instance", "t_small_p000_nadir.png"))
        assert set(np.unique(inst).tolist()) - {0} <= ids
        assert ann["objects"], "nadir camera should see plants"
        depth = np.load(os.path.join(out, "depth", "t_small_p000_nadir.npy"))
        assert 0.3 < float(np.median(depth[depth > 0])) < 3.0
        coco = json.load(open(os.path.join(out, "coco_instances.json")))
        assert len(coco["annotations"]) == len(ann["objects"])
