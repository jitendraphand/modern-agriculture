"""Generate indoor house scenes / datasets (homesim).

    python scripts/generate_houses.py --list
    python scripts/generate_houses.py --scenario family_people_and_pets
    python scripts/generate_houses.py --all --quality draft --keep-going
    python scripts/generate_houses.py --scenario villa_multi_room_mapping --poses 30 --quality final
    python scripts/generate_houses.py --scenario studio_tidy_morning --no-render --save-blend --export usd
    blender -b --python-exit-code 1 -P scripts/generate_houses.py -- --scenario laundry_day
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
    p.add_argument("--scenario", action="append", default=[])
    p.add_argument("--scenario-file", action="append", default=[])
    p.add_argument("--all", action="store_true")
    p.add_argument("--list", action="store_true")
    p.add_argument("--dump-scenario")
    p.add_argument("--out", default="output_houses")
    p.add_argument("--quality", default="preview", choices=["draft", "preview", "final", "hd"])
    p.add_argument("--samples", type=int)
    p.add_argument("--resolution")
    p.add_argument("--poses", type=int, default=2, help="robot poses (spread over rooms)")
    p.add_argument("--cameras")
    p.add_argument("--seed", type=int)
    p.add_argument("--no-render", action="store_true")
    p.add_argument("--save-blend", action="store_true")
    p.add_argument("--export", action="append", default=[], choices=["usd", "gltf", "obj"])
    p.add_argument("--threads", type=int, default=0)
    p.add_argument("--keep-going", action="store_true")
    a = p.parse_args(argv())

    import agrifield  # noqa: F401  (imports bpy first)
    from homesim import scenarios

    if a.list:
        for s in scenarios.SCENARIOS:
            print("%-30s %-16s %-13s %s" % (s["name"], s["house"].get("program", "custom"), s["style"], ", ".join(s["tasks"])))
        print("\n%d scenarios" % len(scenarios.SCENARIOS))
        return 0
    if a.dump_scenario:
        print(json.dumps(scenarios.get(a.dump_scenario), indent=2))
        return 0
    todo = [scenarios.get(s["name"]) for s in scenarios.SCENARIOS] if a.all else []
    todo += [scenarios.get(n) for n in a.scenario]
    for f in a.scenario_file:
        data = json.load(open(f))
        todo += [scenarios._merge(scenarios._BASE, d) for d in (data if isinstance(data, list) else [data])]
    if not todo:
        p.error("nothing to do (see --list)")
    if a.cameras:
        for s in todo:
            s["cameras"] = a.cameras.split(",")
    from homesim import pipeline
    res = tuple(int(v) for v in a.resolution.lower().split("x")) if a.resolution else None
    failed = []
    t0 = time.time()
    for i, sc in enumerate(todo):
        print("[%d/%d] %s - %s" % (i + 1, len(todo), sc["name"], sc.get("title", "")), flush=True)
        try:
            pipeline.run(sc, a.out, quality=a.quality, poses=a.poses, samples=a.samples, resolution=res, seed=a.seed,
                         save_blend=a.save_blend, export=a.export, threads=a.threads, render_frames=not a.no_render)
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
