"""Cycles rendering of RGB and pixel-exact ground-truth passes.

Ground truth is rendered with Cycles too (Workbench/EEVEE need a GPU):
an emission-only override material, 1 sample, a tiny box pixel filter and the
``Raw`` view transform give exact label colours.

* semantic  - per-face ``af_semantic`` attribute colour (class palette)
* instance  - object colour = 24-bit instance id
* depth     - camera-space Z (metres) written to a float EXR
"""

import os

import bpy
import numpy as np

from . import materials as matmod

QUALITY = {
    "draft": dict(samples=16, res=(640, 360)),
    "preview": dict(samples=48, res=(960, 540)),
    "final": dict(samples=128, res=(1280, 720)),
    "hd": dict(samples=256, res=(1920, 1080)),
}


def configure(scene, quality="preview", samples=None, resolution=None, threads=0):
    q = QUALITY[quality]
    r = scene.render
    r.engine = "CYCLES"
    cy = scene.cycles
    cy.device = "CPU"
    cy.samples = samples or q["samples"]
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.03
    cy.use_denoising = True
    try:
        cy.denoiser = "OPENIMAGEDENOISE"
    except TypeError:
        pass
    cy.max_bounces = 6
    cy.diffuse_bounces = 3
    cy.glossy_bounces = 2
    cy.transmission_bounces = 4
    cy.transparent_max_bounces = 8
    cy.volume_bounces = 1
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 1.0
    cy.sample_clamp_indirect = 8.0
    res = resolution or q["res"]
    r.resolution_x, r.resolution_y = int(res[0]), int(res[1])
    r.resolution_percentage = 100
    r.use_persistent_data = True
    r.dither_intensity = 0.0
    if threads:
        r.threads_mode = "FIXED"
        r.threads = threads


def _set_format(scene, fmt, depth="8", mode="RGB", quality=92):
    im = scene.render.image_settings
    im.file_format = fmt
    im.color_mode = mode
    if fmt == "OPEN_EXR":
        im.color_depth = "32"
        im.exr_codec = "ZIP"
    elif fmt == "JPEG":
        im.quality = quality
    else:
        im.color_depth = depth
        im.compression = 15


def render_rgb(scene, path, fmt="PNG"):
    _set_format(scene, fmt)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


class GroundTruth:
    """Renders semantic / instance / depth passes for the active camera."""

    def __init__(self, scene):
        self.scene = scene
        self.mats = matmod.ground_truth_materials()
        w = bpy.data.worlds.new("AF_GT_World")
        nt = w.node_tree
        nt.nodes.clear()
        o = nt.nodes.new("ShaderNodeOutputWorld")
        b = nt.nodes.new("ShaderNodeBackground")
        b.inputs["Color"].default_value = (0, 0, 0, 1)
        b.inputs["Strength"].default_value = 0.0
        nt.links.new(b.outputs[0], o.inputs["Surface"])
        self.world = w

    def _push(self):
        s = self.scene
        cy = s.cycles
        vs = s.view_settings
        self.saved = dict(
            samples=cy.samples, adaptive=cy.use_adaptive_sampling, denoise=cy.use_denoising,
            filter_type=cy.pixel_filter_type, filter_width=cy.filter_width, bounces=cy.max_bounces,
            vt=vs.view_transform, look=vs.look, exposure=vs.exposure, gamma=vs.gamma, world=s.world,
        )
        cy.samples = 1
        cy.use_adaptive_sampling = False
        cy.use_denoising = False
        cy.pixel_filter_type = "BOX"
        cy.filter_width = 0.01
        cy.max_bounces = 0
        vs.view_transform = "Raw"
        vs.look = "None"
        vs.exposure = 0.0
        vs.gamma = 1.0
        s.world = self.world
        self.hidden = []
        for o in s.objects:
            if (o.get("af_render_only") or o.type == "LIGHT") and not o.hide_render:
                o.hide_render = True
                self.hidden.append(o)

    def _pop(self):
        s = self.scene
        cy = s.cycles
        vs = s.view_settings
        d = self.saved
        cy.samples = d["samples"]
        cy.use_adaptive_sampling = d["adaptive"]
        cy.use_denoising = d["denoise"]
        cy.pixel_filter_type = d["filter_type"]
        cy.filter_width = d["filter_width"]
        cy.max_bounces = d["bounces"]
        vs.view_transform = d["vt"]
        vs.look = d["look"]
        vs.exposure = d["exposure"]
        vs.gamma = d["gamma"]
        s.world = d["world"]
        for o in self.hidden:
            o.hide_render = False
        s.view_layers[0].material_override = None

    def render(self, out_dir, stem):
        """Render all passes; returns dict of numpy arrays (top row first)."""
        s = self.scene
        self._push()
        vl = s.view_layers[0]
        res = {}
        try:
            for name, fmt in (("semantic", "PNG"), ("instance", "PNG"), ("depth", "OPEN_EXR")):
                vl.material_override = self.mats[name]
                ext = ".png" if fmt == "PNG" else ".exr"
                path = os.path.join(out_dir, "_tmp_%s_%s%s" % (stem, name, ext))
                _set_format(s, fmt)
                s.render.filepath = path
                bpy.ops.render.render(write_still=True)
                img = bpy.data.images.load(path, check_existing=False)
                w, h = img.size
                px = np.empty(w * h * img.channels, dtype=np.float32)
                img.pixels.foreach_get(px)
                px = px.reshape(h, w, img.channels)[::-1]
                bpy.data.images.remove(img)
                os.remove(path)
                if name == "depth":
                    res[name] = px[..., 0].copy()
                else:
                    res[name] = np.rint(px[..., :3] * 255.0).astype(np.int32)
        finally:
            self._pop()
        return res
