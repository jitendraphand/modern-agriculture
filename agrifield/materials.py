"""Procedural Cycles materials, each tagged with a semantic class.

Every material carries ``mat["semantic"]`` (class id).  After meshes are
built, :func:`tag_mesh_semantics` writes a per-face ``af_semantic`` colour
attribute from the material slots, which the ground-truth render passes read.
"""

import bpy
import numpy as np

from . import semantics


def _srgb_to_linear(c):
    c = max(0.0, min(1.0, c))
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lin(rgb):
    """Hex string or 0-255/0-1 sRGB triple -> linear RGBA tuple."""
    if isinstance(rgb, str):
        h = rgb.lstrip("#")
        rgb = tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    elif max(rgb) > 1.0:
        rgb = tuple(v / 255.0 for v in rgb)
    return tuple(_srgb_to_linear(v) for v in rgb) + (1.0,)


class _G:
    """Tiny helper for building node graphs."""

    def __init__(self, mat):
        self.nt = mat.node_tree
        self.nt.nodes.clear()
        self.x = 0

    def n(self, kind, **inputs):
        node = self.nt.nodes.new(kind)
        node.location = (self.x, 0)
        self.x += 200
        for k, v in inputs.items():
            sock = node.inputs[k] if not isinstance(k, int) else node.inputs[k]
            sock.default_value = v
        return node

    def link(self, out, inp):
        self.nt.links.new(out, inp)


def _new_material(name, semantic):
    mat = bpy.data.materials.new(name)
    mat["semantic"] = semantics.class_id(semantic)
    col = semantics.class_color01(mat["semantic"])
    mat.diffuse_color = col + (1.0,)
    return mat


def _variation(g, color_a, color_b, noise_scale=25.0, noise_amount=0.15, coord="Object"):
    """Per-object random mix between two colours plus fine noise."""
    oi = g.n("ShaderNodeObjectInfo")
    mix = g.n("ShaderNodeMixRGB")
    mix.inputs["Color1"].default_value = lin(color_a)
    mix.inputs["Color2"].default_value = lin(color_b)
    g.link(oi.outputs["Random"], mix.inputs["Fac"] if "Fac" in mix.inputs else mix.inputs[0])
    tc = g.n("ShaderNodeTexCoord")
    noise = g.n("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = noise_scale
    noise.inputs["Detail"].default_value = 3.0
    g.link(tc.outputs[coord], noise.inputs["Vector"])
    hs = g.n("ShaderNodeHueSaturation")
    rng = g.n("ShaderNodeMapRange")
    rng.inputs["To Min"].default_value = 1.0 - noise_amount
    rng.inputs["To Max"].default_value = 1.0 + noise_amount
    g.link(noise.outputs["Factor"], rng.inputs["Value"])
    g.link(rng.outputs["Result"], hs.inputs["Value"])
    g.link(mix.outputs[0], hs.inputs["Color"])
    return hs.outputs["Color"]


def make_leaf(name, color_a, color_b=None, semantic="crop_foliage", roughness=0.5,
              translucency=0.3, specular=0.45, sheen=0.0, noise_amount=0.12):
    mat = _new_material(name, semantic)
    g = _G(mat)
    col = _variation(g, color_a, color_b or color_a, noise_amount=noise_amount)
    bsdf = g.n("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Specular IOR Level"].default_value = specular
    if sheen:
        bsdf.inputs["Sheen Weight"].default_value = sheen
    g.link(col, bsdf.inputs["Base Color"])
    tr = g.n("ShaderNodeBsdfTranslucent")
    g.link(col, tr.inputs["Color"])
    mix = g.n("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = translucency
    g.link(bsdf.outputs[0], mix.inputs[1])
    g.link(tr.outputs[0], mix.inputs[2])
    out = g.n("ShaderNodeOutputMaterial")
    g.link(mix.outputs[0], out.inputs["Surface"])
    return mat


def make_plain(name, color_a, color_b=None, semantic="obstacle", roughness=0.6,
               metallic=0.0, specular=0.5, noise_amount=0.1, coat=0.0,
               transmission=0.0, ior=1.45, bump=0.0, bump_scale=60.0, sss=0.0, sheen=0.0):
    mat = _new_material(name, semantic)
    g = _G(mat)
    col = _variation(g, color_a, color_b or color_a, noise_amount=noise_amount)
    bsdf = g.n("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Specular IOR Level"].default_value = specular
    bsdf.inputs["Coat Weight"].default_value = coat
    bsdf.inputs["Transmission Weight"].default_value = transmission
    bsdf.inputs["IOR"].default_value = ior
    if sheen:
        bsdf.inputs["Sheen Weight"].default_value = sheen
    if sss:
        bsdf.inputs["Subsurface Weight"].default_value = sss
        bsdf.inputs["Subsurface Scale"].default_value = 0.01
    g.link(col, bsdf.inputs["Base Color"])
    if bump:
        tc = g.n("ShaderNodeTexCoord")
        nz = g.n("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = bump_scale
        nz.inputs["Detail"].default_value = 4.0
        g.link(tc.outputs["Object"], nz.inputs["Vector"])
        bp = g.n("ShaderNodeBump")
        bp.inputs["Strength"].default_value = bump
        bp.inputs["Distance"].default_value = 0.01
        g.link(nz.outputs["Factor"], bp.inputs["Height"])
        g.link(bp.outputs["Normal"], bsdf.inputs["Normal"])
    out = g.n("ShaderNodeOutputMaterial")
    g.link(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def make_soil(name, dark, light, wetness=0.0, clod_scale=18.0, semantic="soil"):
    """Soil with large-scale moisture/colour patches, clods and fine grain."""
    mat = _new_material(name, semantic)
    g = _G(mat)
    tc = g.n("ShaderNodeTexCoord")
    big = g.n("ShaderNodeTexNoise", Scale=0.35, Detail=4.0, Roughness=0.6)
    g.link(tc.outputs["Object"], big.inputs["Vector"])
    fine = g.n("ShaderNodeTexNoise", Scale=9.0, Detail=8.0, Roughness=0.7)
    g.link(tc.outputs["Object"], fine.inputs["Vector"])
    vor = g.n("ShaderNodeTexVoronoi", Scale=clod_scale)
    g.link(tc.outputs["Object"], vor.inputs["Vector"])
    m1 = g.n("ShaderNodeMath")
    m1.operation = "MULTIPLY_ADD"
    m1.inputs[1].default_value = 0.6
    g.link(big.outputs["Factor"], m1.inputs[0])
    g.link(fine.outputs["Factor"], m1.inputs[2])
    ramp = g.n("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = lin(dark)
    ramp.color_ramp.elements[1].position = 0.95
    ramp.color_ramp.elements[1].color = lin(light)
    g.link(m1.outputs[0], ramp.inputs["Factor"])
    hs = g.n("ShaderNodeHueSaturation")
    hs.inputs["Value"].default_value = 1.0 - 0.45 * wetness
    hs.inputs["Saturation"].default_value = 1.0 + 0.15 * wetness
    g.link(ramp.outputs["Color"], hs.inputs["Color"])
    bsdf = g.n("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.95 - 0.55 * wetness
    bsdf.inputs["Specular IOR Level"].default_value = 0.3 + 0.4 * wetness
    g.link(hs.outputs["Color"], bsdf.inputs["Base Color"])
    hmix = g.n("ShaderNodeMath")
    hmix.operation = "MULTIPLY_ADD"
    hmix.inputs[1].default_value = 0.5
    g.link(vor.outputs["Distance"], hmix.inputs[0])
    g.link(fine.outputs["Factor"], hmix.inputs[2])
    bump = g.n("ShaderNodeBump", Strength=0.6, Distance=0.02)
    g.link(hmix.outputs[0], bump.inputs["Height"])
    g.link(bump.outputs["Normal"], bsdf.inputs["Normal"])
    out = g.n("ShaderNodeOutputMaterial")
    g.link(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def make_water(name, tint="#6b5a3a", roughness=0.04):
    mat = _new_material(name, "water")
    g = _G(mat)
    bsdf = g.n("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = lin(tint)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Transmission Weight"].default_value = 0.7
    bsdf.inputs["IOR"].default_value = 1.333
    tc = g.n("ShaderNodeTexCoord")
    nz = g.n("ShaderNodeTexNoise", Scale=3.0, Detail=6.0)
    g.link(tc.outputs["Object"], nz.inputs["Vector"])
    bp = g.n("ShaderNodeBump", Strength=0.08, Distance=0.01)
    g.link(nz.outputs["Factor"], bp.inputs["Height"])
    g.link(bp.outputs["Normal"], bsdf.inputs["Normal"])
    out = g.n("ShaderNodeOutputMaterial")
    g.link(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def build(name, spec):
    """Create a material from a spec dict (see crops / props modules)."""
    spec = dict(spec)
    kind = spec.pop("kind", "plain")
    if kind == "leaf":
        return make_leaf(name, **spec)
    if kind == "soil":
        return make_soil(name, **spec)
    if kind == "water":
        return make_water(name, **spec)
    return make_plain(name, **spec)


class MaterialLibrary:
    """Lazily creates materials by key from registered specs."""

    def __init__(self):
        self.specs = {}
        self.mats = {}

    def register(self, specs):
        for k, v in specs.items():
            if k not in self.specs:
                self.specs[k] = v

    def __getitem__(self, key):
        mat = self.mats.get(key)
        if mat is None:
            if key not in self.specs:
                raise KeyError("material spec not registered: %s" % key)
            mat = build("AF_" + key, self.specs[key])
            self.mats[key] = mat
        return mat

    def resolve(self, keys):
        return {k: self[k] for k in keys}


# ------------------------------------------------------------ ground truth
def tag_mesh_semantics(mesh):
    """Write a per-face ``af_semantic`` colour attribute from material slots."""
    if "af_semantic" in mesh.attributes:
        return
    n = len(mesh.polygons)
    attr = mesh.attributes.new("af_semantic", "FLOAT_COLOR", "FACE")
    if n == 0:
        return
    slot_cols = []
    for m in mesh.materials:
        cid = int(m.get("semantic", 0)) if m is not None else 0
        slot_cols.append(semantics.class_color01(cid) + (1.0,))
    if not slot_cols:
        slot_cols = [(0.0, 0.0, 0.0, 1.0)]
    lut = np.array(slot_cols, dtype=np.float32)
    idx = np.zeros(n, dtype=np.int32)
    mesh.polygons.foreach_get("material_index", idx)
    idx = np.clip(idx, 0, len(lut) - 1)
    attr.data.foreach_set("color", lut[idx].ravel())


def ground_truth_materials():
    """Emission-only override materials for semantic / instance / depth passes."""
    out = {}

    sem = bpy.data.materials.new("AF_GT_semantic")
    g = _G(sem)
    at = g.n("ShaderNodeAttribute")
    at.attribute_type = "GEOMETRY"
    at.attribute_name = "af_semantic"
    em = g.n("ShaderNodeEmission", Strength=1.0)
    g.link(at.outputs["Color"], em.inputs["Color"])
    o = g.n("ShaderNodeOutputMaterial")
    g.link(em.outputs[0], o.inputs["Surface"])
    out["semantic"] = sem

    ins = bpy.data.materials.new("AF_GT_instance")
    g = _G(ins)
    oi = g.n("ShaderNodeObjectInfo")
    em = g.n("ShaderNodeEmission", Strength=1.0)
    g.link(oi.outputs["Color"], em.inputs["Color"])
    o = g.n("ShaderNodeOutputMaterial")
    g.link(em.outputs[0], o.inputs["Surface"])
    out["instance"] = ins

    dep = bpy.data.materials.new("AF_GT_depth")
    g = _G(dep)
    cd = g.n("ShaderNodeCameraData")
    em = g.n("ShaderNodeEmission", Strength=1.0)
    g.link(cd.outputs["View Z Depth"], em.inputs["Color"])
    o = g.n("ShaderNodeOutputMaterial")
    g.link(em.outputs[0], o.inputs["Surface"])
    out["depth"] = dep
    return out
