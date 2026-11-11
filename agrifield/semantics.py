"""Semantic class table shared by materials, renders and annotations."""

# id: (name, RGB colour used in semantic.png, description)
CLASSES = {
    0: ("background", (0, 0, 0), "sky / anything not modelled"),
    1: ("soil", (120, 72, 40), "bare soil, beds, furrows, bunds"),
    2: ("crop_foliage", (34, 177, 76), "crop leaves (green or senescent)"),
    3: ("crop_stem", (181, 230, 29), "crop stems, stalks, trunks, petioles, vines"),
    4: ("crop_produce", (237, 28, 36), "harvestable organ: fruit, ear, head, pod, boll, bulb, tuber shoulder"),
    5: ("crop_flower", (255, 242, 0), "flowers, tassels, blossoms"),
    6: ("weed", (255, 0, 255), "any weed plant"),
    7: ("ground_cover", (0, 128, 64), "inter-row grass / cover crop / headland vegetation"),
    8: ("residue", (200, 170, 110), "straw, stubble, crop residue, organic mulch"),
    9: ("plastic_mulch", (63, 72, 204), "plastic film mulch on beds"),
    10: ("irrigation", (0, 162, 232), "drip tape, pipes, sprinkler risers"),
    11: ("structure", (136, 0, 21), "posts, stakes, trellis wires, fences"),
    12: ("rock", (127, 127, 127), "stones and rocks"),
    13: ("obstacle", (255, 127, 39), "crates, buckets, tools, hoses"),
    14: ("person", (255, 174, 201), "people working in the field"),
    15: ("water", (153, 217, 234), "puddles, paddy water"),
    16: ("background_vegetation", (20, 70, 20), "distant hedges / tree line"),
}

NAME_TO_ID = {v[0]: k for k, v in CLASSES.items()}


def class_id(name):
    return NAME_TO_ID[name]


def class_color01(cid):
    r, g, b = CLASSES[cid][1]
    return (r / 255.0, g / 255.0, b / 255.0)


def encode_instance(iid):
    """Instance id -> RGB float triple (24-bit, R = low byte)."""
    return ((iid & 255) / 255.0, ((iid >> 8) & 255) / 255.0, ((iid >> 16) & 255) / 255.0)


def class_table():
    return [
        {"id": k, "name": v[0], "color": list(v[1]), "description": v[2]}
        for k, v in sorted(CLASSES.items())
    ]
