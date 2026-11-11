"""House scenario tests (need bpy):  python -m pytest tests -q"""

import importlib.util
import json
import os
import random
import sys
import tempfile

import numpy as np
import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
pytestmark = pytest.mark.skipif(importlib.util.find_spec("bpy") is None, reason="bpy not installed")


def _connected(plan):
    rooms = {r["id"] for r in plan["rooms"]}
    adj = {r: set() for r in rooms}
    for d in plan["doors"]:
        a, b = d["rooms"]
        adj[a].add(b)
        adj[b].add(a)
    start = plan["front_door"]["rooms"][0]
    seen, todo = {start}, [start]
    while todo:
        for n in adj[todo.pop()]:
            if n not in seen:
                seen.add(n)
                todo.append(n)
    return seen == rooms


def test_twenty_scenarios():
    import agrifield  # noqa: F401
    from homesim import scenarios
    assert len(scenarios.SCENARIOS) == 20
    assert len({s["name"] for s in scenarios.SCENARIOS}) == 20
    for s in scenarios.SCENARIOS:
        json.dumps(s)


@pytest.mark.parametrize("program", ["studio", "apartment_2bed", "family_3bed", "villa", "loft", "office_home"])
def test_floorplans_are_connected(program):
    import agrifield  # noqa: F401
    from homesim import layout
    for seed in range(15):
        W, D = {"studio": (7, 5.5), "villa": (17, 13)}.get(program, (12, 9))
        plan = layout.generate(W, D, layout.PROGRAMS[program], random.Random(seed))
        assert plan["front_door"] is not None
        assert _connected(plan), (program, seed)
        total = sum(r["rect"].area for r in plan["rooms"])
        assert abs(total - W * D) < 1e-6


def test_all_houses_build_and_render_exact_gt():
    import agrifield  # noqa: F401
    from homesim import pipeline, scenarios
    with tempfile.TemporaryDirectory() as d:
        for s in scenarios.SCENARIOS:
            pipeline.run(s, d, render_frames=False, log=lambda *a: None)
        sc = scenarios.get("family_people_and_pets")
        sc["cameras"] = ["robot_head", "topdown"]
        meta = pipeline.run(sc, d, quality="draft", poses=1, samples=2, resolution=(160, 90), log=lambda *a: None)
        out = os.path.join(d, sc["name"])
        ann = json.load(open(os.path.join(out, "ann", "%s_p000_robot_head.json" % sc["name"])))
        assert ann["unknown_semantic_pixels"] == 0
        assert ann["objects"]
        ids = {r["instance_id"] for r in meta["instances"]}
        assert {o["instance_id"] for o in ann["objects"]} <= ids
        plan = json.load(open(os.path.join(out, "floorplan.json")))
        assert len(plan["rooms"]) >= 5
        from agrifield.pngio import read_png
        occ = read_png(os.path.join(out, "occupancy.png"))
        assert set(np.unique(occ).tolist()) <= {0, 128, 255}
