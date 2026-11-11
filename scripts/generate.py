"""Generate agricultural field scenes / datasets.

Inside Blender:
    blender -b --python-exit-code 1 -P scripts/generate.py -- --scenario corn_v6_row_following
With the bpy module (pip install bpy):
    python scripts/generate.py --scenario corn_v6_row_following

Examples:
    --list                                  list scenarios
    --list-crops                            list crops and growth stages
    --all --quality draft                   render every scenario (1 pose)
    --scenario tomato_ripening_harvest --poses 20 --quality final
    --scenario orchard_apple_harvest --no-render --save-blend --export usd
    --scenario-file my_field.json           custom scenario(s) (object or list)
    --dump-scenario corn_v6_row_following   print a scenario as JSON to start from
    --seed 123                              re-randomise layout / variants
"""

import argparse
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else a[1:]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scenario", action="append", default=[], help="scenario name (repeatable)")
    p.add_argument("--scenario-file", action="append", default=[], help="JSON file with a scenario or list")
    p.add_argument("--all", action="store_true", help="every catalog scenario")
    p.add_argument("--filter", help="only scenarios whose name contains this text")
    p.add_argument("--list", action="store_true")
    p.add_argument("--list-crops", action="store_true")
    p.add_argument("--dump-scenario")
    p.add_argument("--out", default="output")
    p.add_argument("--quality", default="preview", choices=["draft", "preview", "final", "hd"])
    p.add_argument("--samples", type=int)
    p.add_argument("--resolution", help="WxH, e.g. 1280x720")
    p.add_argument("--poses", type=int, default=1, help="robot poses along the row (frames per camera)")
    p.add_argument("--cameras", help="comma separated camera override, e.g. front,nadir")
    p.add_argument("--seed", type=int)
    p.add_argument("--no-render", action="store_true", help="build only (use with --save-blend / --export)")
    p.add_argument("--no-gt", action="store_true", help="skip ground-truth passes")
    p.add_argument("--save-blend", action="store_true")
    p.add_argument("--export", action="append", default=[], choices=["usd", "gltf", "obj", "fbx"])
    p.add_argument("--jpeg", action="store_true", help="write RGB as JPEG instead of PNG")
    p.add_argument("--threads", type=int, default=0)
    p.add_argument("--keep-going", action="store_true", help="continue with the next scenario on error")
    a = p.parse_args(argv())

    from agrifield import crops, scenarios

    if a.list:
        for s in scenarios.SCENARIOS:
            c = ", ".join("%s/%s" % (e["crop"], e.get("stage") or "+".join(e["stage_mix"])) for e in s["crops"])
            print("%-38s %-30s %s" % (s["name"], c, ", ".join(s["tasks"])))
        print("\n%d scenarios" % len(scenarios.SCENARIOS))
        return 0
    if a.list_crops:
        for c in crops.list_crops():
            print("%-11s %s" % (c["crop"], c["display"]))
            for st, info in c["stages"].items():
                print("    %-13s BBCH %-3s %s" % (st, info["bbch"], info["desc"]))
        return 0
    if a.dump_scenario:
        print(json.dumps(scenarios.get(a.dump_scenario), indent=2))
        return 0

    todo = []
    if a.all:
        todo.extend(scenarios.get(s["name"]) for s in scenarios.SCENARIOS)
    todo.extend(scenarios.get(n) for n in a.scenario)
    for f in a.scenario_file:
        with open(f) as fh:
            data = json.load(fh)
        for d in (data if isinstance(data, list) else [data]):
            todo.append(scenarios._merge(scenarios._BASE, d))
    if a.filter:
        todo = [s for s in todo if a.filter in s["name"]]
    if not todo:
        p.error("nothing to do: give --scenario, --scenario-file or --all (see --list)")
    if a.cameras:
        for s in todo:
            s["cameras"] = a.cameras.split(",")

    from agrifield import pipeline

    res = tuple(int(v) for v in a.resolution.lower().split("x")) if a.resolution else None
    failed = []
    t0 = time.time()
    for i, sc in enumerate(todo):
        print("[%d/%d] %s - %s" % (i + 1, len(todo), sc["name"], sc.get("title", "")), flush=True)
        try:
            pipeline.run(sc, a.out, quality=a.quality, poses=a.poses, render_frames=not a.no_render,
                         ground_truth=not a.no_gt, save_blend=a.save_blend, export=a.export,
                         samples=a.samples, resolution=res, seed=a.seed, threads=a.threads,
                         rgb_format="JPEG" if a.jpeg else "PNG")
        except Exception:
            traceback.print_exc()
            failed.append(sc["name"])
            if not a.keep_going:
                return 1
    print("finished %d scenario(s) in %.1f min%s" % (len(todo), (time.time() - t0) / 60,
                                                  ("; FAILED: " + ", ".join(failed)) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
