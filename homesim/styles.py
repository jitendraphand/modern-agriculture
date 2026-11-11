"""Interior styles: material roles -> material specs.

A style maps *roles* used by the furniture builders (``sofa``, ``table``,
``floor_living`` ...) to material keys, and provides the material specs.
Semantic classes of furniture come from the object, not the material, so a
material can be shared by many kinds of objects.
"""

from agrifield import materials as agri_mat
from agrifield import semantics
from agrifield.materials import lin

STYLES = {
    "modern": dict(
        wall="#e9e6e1", accent="#9fb4c7", floor_wood="#a77b52", floor_wood2="#8b6440", tile="#d8d8d4",
        carpet="#8a8f99", sofa="#5d6470", chair="#2b2b2b", table="#d9d4cc", wood="#8a6440", cabinet="#f2f2ef",
        cabinet_front="#e6e6e2", kitchen="#2f3a45", counter="#ececea", bed_frame="#6b7078", blanket="#c6cfd8",
        metal="#9ea3a8", rugs=["#b9b1a5", "#5f6b78", "#c8a98a"], curtain="#d8d4cc"),
    "scandinavian": dict(
        wall="#f4f2ee", accent="#dfe6e0", floor_wood="#d2b48c", floor_wood2="#c4a37a", tile="#ecebe7",
        carpet="#c9c3b8", sofa="#b9b6ae", chair="#e3d2b4", table="#e2cfae", wood="#d0b088", cabinet="#ffffff",
        cabinet_front="#f6f6f4", kitchen="#f5f5f3", counter="#d8c4a2", bed_frame="#dcc6a0", blanket="#e8e2d6",
        metal="#bfc3c6", rugs=["#ece6da", "#9aa79a", "#d4c6b0"], curtain="#f0ece4"),
    "rustic": dict(
        wall="#e3d6c0", accent="#b98a62", floor_wood="#7a4f2c", floor_wood2="#6a4224", tile="#b58a6a",
        carpet="#8a5a3a", sofa="#7a4a32", chair="#6a4a2c", table="#6e4628", wood="#5e3c22", cabinet="#8a6040",
        cabinet_front="#7a5236", kitchen="#6b4a2e", counter="#3e3a36", bed_frame="#5a3a22", blanket="#a8452e",
        metal="#3a3a3a", rugs=["#8a3a2a", "#c8a060", "#4a5a3a"], curtain="#c8b088"),
    "industrial": dict(
        wall="#8e8a86", accent="#a35a3a", floor_wood="#6f6a64", floor_wood2="#5a5550", tile="#4a4a4a",
        carpet="#3a3a3c", sofa="#4a3424", chair="#1e1e1e", table="#5a4632", wood="#4a3828", cabinet="#3a3d40",
        cabinet_front="#2e3134", kitchen="#2a2c2e", counter="#9a9a98", bed_frame="#262626", blanket="#5a6a5a",
        metal="#2a2a2a", rugs=["#5a3a2a", "#2e3a4a", "#8a8070"], curtain="#6a6a64"),
    "dark": dict(
        wall="#4a4844", accent="#2e3a3a", floor_wood="#2e221a", floor_wood2="#241a14", tile="#262626",
        carpet="#1e1e22", sofa="#1c1c1e", chair="#141414", table="#1a1614", wood="#1e1612", cabinet="#202022",
        cabinet_front="#18181a", kitchen="#121214", counter="#2a2a2a", bed_frame="#161616", blanket="#2a2a36",
        metal="#3a3a3a", rugs=["#141414", "#2a1e1a", "#1a2228"], curtain="#202020"),
}


def P(color, sem, **kw):
    d = dict(kind="plain", color_a=color, color_b=kw.pop("color_b", color), semantic=sem, noise_amount=kw.pop("noise", 0.05))
    d.update(kw)
    return d


def make(style_name, rng):
    s = STYLES[style_name]
    specs = {}
    st = {}

    def role(r, key, spec):
        specs[key] = spec
        st[r] = key

    role("wall", "wall", P(s["wall"], "wall", roughness=0.85))
    role("wall_accent", "wall_accent", P(s["accent"], "wall", roughness=0.85))
    role("wall_tile", "wall_tile", P("#e8eaea", "wall", roughness=0.25, bump=0.15, bump_scale=8))
    role("ceiling", "ceiling", P("#f6f6f4", "ceiling", roughness=0.9))
    role("floor_wood", "floor_wood", P(s["floor_wood"], "floor", color_b=s["floor_wood2"], roughness=0.35, noise=0.15,
                                       coat=0.2, bump=0.1, bump_scale=6))
    role("floor_tile", "floor_tile", P(s["tile"], "floor", roughness=0.2, bump=0.1, bump_scale=3))
    role("floor_carpet", "floor_carpet", P(s["carpet"], "floor", roughness=0.95, bump=0.4, bump_scale=200, sheen=0.5))
    role("floor_concrete", "floor_concrete", P("#9a9894", "floor", roughness=0.6, noise=0.2, bump=0.1, bump_scale=2))
    role("door", "door", P("#efeeea" if style_name != "rustic" else "#7a5232", "door", roughness=0.5))
    role("door_frame", "door_frame", P("#f4f4f2" if style_name != "rustic" else "#6a4428", "door", roughness=0.5))
    role("window_frame", "window_frame", P("#f4f4f2" if style_name not in ("industrial", "dark") else "#202020", "window", roughness=0.4))
    specs["window_glass"] = dict(kind="window_glass", semantic="window")
    st["window_glass"] = "window_glass"
    role("skirting", "skirting", P("#f0f0ee", "wall", roughness=0.5))
    role("sofa", "sofa", P(s["sofa"], "seating", roughness=0.9, sheen=0.6, noise=0.08, bump=0.2, bump_scale=300))
    role("pillow", "pillow", P(rng.choice(["#c8553d", "#e0b04a", "#5a7d9a", "#e6e2da", "#7a9a6a"]), "textile", roughness=0.95, sheen=0.7))
    role("chair", "chair", P(s["chair"], "seating", roughness=0.5))
    role("office_fabric", "office_fabric", P("#2a2d33", "seating", roughness=0.9, sheen=0.4))
    role("table", "table", P(s["table"], "table", roughness=0.4, noise=0.1, coat=0.2))
    role("table_leg", "table_leg", P(s["metal"] if rng.random() < 0.5 else s["wood"], "table", roughness=0.4))
    role("glass_top", "glass_top", P("#cfe0e0", "table", roughness=0.02, transmission=0.9, ior=1.5))
    role("wood", "wood", P(s["wood"], "storage", roughness=0.5, noise=0.12))
    role("cabinet", "cabinet", P(s["cabinet"], "storage", roughness=0.45))
    role("cabinet_front", "cabinet_front", P(s["cabinet_front"], "storage", roughness=0.4))
    role("shelf", "shelf", P(s["wood"], "storage", roughness=0.5, noise=0.12))
    role("kitchen_cab", "kitchen_cab", P(s["kitchen"], "counter", roughness=0.4))
    role("kitchen_front", "kitchen_front", P(s["kitchen"], "counter", roughness=0.35, coat=0.3))
    role("counter", "counter", P(s["counter"], "counter", roughness=0.25, noise=0.1, coat=0.3))
    role("sink", "sink", P("#c0c4c8", "counter", roughness=0.25, metallic=1.0))
    role("hob", "hob", P("#101012", "appliance", roughness=0.08, coat=1.0))
    role("appliance", "appliance", P("#d4d6d8" if rng.random() < 0.5 else "#f2f2f2", "appliance", roughness=0.25, metallic=0.6))
    role("appliance_white", "appliance_white", P("#f2f2f2", "appliance", roughness=0.3))
    role("tv", "tv", P("#18181a", "appliance", roughness=0.3))
    role("screen", "screen", P("#05070a", "appliance", roughness=0.05, coat=1.0))
    role("glass_dark", "glass_dark", P("#1a2228", "appliance", roughness=0.05, coat=1.0))
    role("bed_frame", "bed_frame", P(s["bed_frame"], "bed", roughness=0.6))
    role("mattress", "mattress", P("#f2f0ec", "bed", roughness=0.9, sheen=0.5))
    role("blanket", "blanket", P(s["blanket"], "textile", roughness=0.95, sheen=0.7, bump=0.3, bump_scale=40))
    role("ceramic", "ceramic", P("#f6f6f4", "sanitary", roughness=0.1, coat=0.6))
    role("glass_clear", "glass_clear", P("#e8f0f0", "sanitary", roughness=0.02, transmission=0.95, ior=1.5))
    role("metal", "metal", P(s["metal"], "storage", roughness=0.3, metallic=1.0))
    role("plastic_dark", "plastic_dark", P("#202022", "small_object", roughness=0.4))
    role("pot", "pot", P(rng.choice(["#b5643c", "#e8e4dc", "#30363a"]), "plant", roughness=0.6))
    role("pot_soil", "pot_soil", P("#3a2a1e", "plant", roughness=0.95))
    specs["plant_leaf"] = dict(kind="leaf", color_a="#2f6a2a", color_b="#4a8a3a", semantic="plant", roughness=0.4)
    st["plant_leaf"] = "plant_leaf"
    role("shade", "shade", P("#f2e8d6", "lamp", roughness=0.8, sss=0.3))
    role("lamp_base", "lamp_base", P(rng.choice(["#c8b89a", "#30363a", "#a85a3a"]), "lamp", roughness=0.3, coat=0.4))
    specs["light_emit"] = dict(kind="emit", color="#fff4e0", strength=6.0, semantic="lamp")
    st["light_emit"] = "light_emit"
    role("frame", "frame", P(rng.choice(["#1a1a1a", "#d8c4a0", "#f4f4f2"]), "decoration", roughness=0.4))
    specs["mirror"] = dict(kind="plain", color_a="#e8eaec", color_b="#e8eaec", semantic="decoration", roughness=0.0, metallic=1.0, noise_amount=0.0)
    st["mirror"] = "mirror"
    role("curtain", "curtain", P(s["curtain"], "textile", roughness=0.95, sheen=0.6, sss=0.2))
    role("stairs", "stairs", P(s["floor_wood"], "stairs", roughness=0.4, noise=0.15))
    role("liquid", "liquid", P("#3a1f10", "small_object", roughness=0.05, coat=1.0))
    role("glass_green", "glass_green", P("#3a6a3a", "small_object", roughness=0.05, transmission=0.8, ior=1.5))
    role("cardboard", "cardboard", P("#b88a5a", "box", color_b="#a87a4a", roughness=0.85, noise=0.1))
    role("tape", "tape", P("#c8a878", "box", roughness=0.3))
    role("basket", "basket", P(rng.choice(["#e8e8e8", "#7aa0c0", "#c8a878"]), "small_object", roughness=0.6))
    role("fur_light", "fur_light", P("#b8926a", "small_object", roughness=0.95, sheen=1.0))
    role("grass_out", "grass_out", P("#4a6a2a", "outdoor", color_b="#5a7a32", roughness=0.9, noise=0.25, bump=0.4, bump_scale=60))
    role("path_out", "path_out", P("#a8a49c", "outdoor", roughness=0.8, noise=0.2))
    specs["tree_out"] = dict(kind="leaf", color_a="#2f4a25", color_b="#3f5a2a", semantic="outdoor", roughness=0.8, translucency=0.1)
    st["tree_out"] = "tree_out"
    role("trunk_out", "trunk_out", P("#3a3028", "outdoor", roughness=0.9))

    def palette(prefix, colors, sem, **kw):
        keys = []
        for i, c in enumerate(colors):
            k = "%s_%d" % (prefix, i)
            specs[k] = P(c, sem, **kw)
            keys.append(k)
        return keys

    st["rugs"] = palette("rug", s["rugs"], "rug", roughness=0.95, sheen=0.6, bump=0.4, bump_scale=150)
    st["books"] = palette("book", ["#8a2a2a", "#2a4a7a", "#d8c8a0", "#2a6a4a", "#e0a020", "#3a3a3a", "#7a3a6a", "#f0f0e8"],
                          "storage", roughness=0.6)
    st["obj_colors"] = palette("obj", ["#d83a2a", "#2a6ad8", "#f0c020", "#3aa04a", "#f4f4f2", "#222222", "#e07a2a", "#8a4ac8"],
                               "small_object", roughness=0.35)
    st["toy_colors"] = palette("toy", ["#e8302a", "#2a7ae8", "#f8d020", "#30b050", "#f07ab0"], "small_object", roughness=0.3, coat=0.5)
    st["fruit_colors"] = palette("fruit", ["#c8201a", "#f0a020", "#e8d040", "#7ab030"], "small_object", roughness=0.35)
    st["cloth_colors"] = palette("cloth", ["#2a3a6a", "#c83a3a", "#e8e4dc", "#3a3a3a", "#6a8a5a", "#d8a040"], "textile",
                                 roughness=0.95, sheen=0.8)
    st["art"] = palette("art", ["#c86a3a", "#3a6ac8", "#e0c060", "#6a3a7a", "#3a8a7a"], "decoration", roughness=0.6, noise=0.5)
    st["fur"] = palette("fur", ["#8a5a32", "#1e1a18", "#d8c8a8", "#6a6a6a"], "pet", roughness=0.95, sheen=1.0, noise=0.2)
    # people (reuse agrifield.props.person material keys)
    for k, c in (("skin", "#c08a6a"), ("cloth_vest", "#4a6a9a"), ("cloth_pants", "#2a3448"), ("cloth_shirt", "#8a4a3a"),
                 ("hat", "#3a3a3a"), ("boots", "#1a1a1a")):
        specs[k] = P(c, "person", roughness=0.8, color_b={"skin": "#7a4e36", "cloth_vest": "#c8a040"}.get(k, c), noise=0.1)
    return st, specs


# ------------------------------------------------------------------ builders
def _window_glass(name):
    """Glass that lets sun and sky light through (shadow / diffuse rays see
    transparency) while camera rays see reflective glass."""
    mat = agri_mat._new_material(name, "window")
    g = agri_mat._G(mat)
    lp = g.n("ShaderNodeLightPath")
    mx = g.n("ShaderNodeMath")
    mx.operation = "MAXIMUM"
    g.link(lp.outputs["Is Shadow Ray"], mx.inputs[0])
    g.link(lp.outputs["Is Diffuse Ray"], mx.inputs[1])
    glass = g.n("ShaderNodeBsdfPrincipled")
    glass.inputs["Base Color"].default_value = lin("#e6f0f2")
    glass.inputs["Roughness"].default_value = 0.0
    glass.inputs["Transmission Weight"].default_value = 1.0
    glass.inputs["IOR"].default_value = 1.05
    tr = g.n("ShaderNodeBsdfTransparent")
    mix = g.n("ShaderNodeMixShader")
    g.link(mx.outputs[0], mix.inputs["Fac"])
    g.link(glass.outputs[0], mix.inputs[1])
    g.link(tr.outputs[0], mix.inputs[2])
    out = g.n("ShaderNodeOutputMaterial")
    g.link(mix.outputs[0], out.inputs["Surface"])
    return mat


def _emit(name, color, strength, semantic):
    mat = agri_mat._new_material(name, semantic)
    g = agri_mat._G(mat)
    em = g.n("ShaderNodeEmission")
    em.inputs["Color"].default_value = lin(color)
    em.inputs["Strength"].default_value = strength
    out = g.n("ShaderNodeOutputMaterial")
    g.link(em.outputs[0], out.inputs["Surface"])
    return mat


def build_material(name, spec):
    spec = dict(spec)
    kind = spec.get("kind")
    if kind == "window_glass":
        return _window_glass(name)
    if kind == "emit":
        return _emit(name, spec["color"], spec["strength"], spec["semantic"])
    return agri_mat.build(name, spec)


class Library(agri_mat.MaterialLibrary):
    def __getitem__(self, key):
        mat = self.mats.get(key)
        if mat is None:
            mat = build_material("HM_" + key, self.specs[key])
            self.mats[key] = mat
        return mat


def tag(mesh, default_cid, mat_class=None):
    """Per-face semantic attribute: object class, except materials listed in
    ``mat_class`` (material name -> class id)."""
    import numpy as np
    if "af_semantic" in mesh.attributes:
        mesh.attributes.remove(mesh.attributes["af_semantic"])
    attr = mesh.attributes.new("af_semantic", "FLOAT_COLOR", "FACE")
    n = len(mesh.polygons)
    if not n:
        return
    cols = []
    for m in mesh.materials:
        cid = default_cid
        if default_cid is None:
            cid = int(m.get("semantic", 0)) if m else 0
        if mat_class and m is not None and m.name in mat_class:
            cid = mat_class[m.name]
        cols.append(semantics.class_color01(cid) + (1.0,))
    lut = np.array(cols or [(0, 0, 0, 1)], dtype=np.float32)
    idx = np.zeros(n, dtype=np.int32)
    mesh.polygons.foreach_get("material_index", idx)
    attr.data.foreach_set("color", lut[np.clip(idx, 0, len(lut) - 1)].ravel())

