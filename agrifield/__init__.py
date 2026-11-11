"""agrifield - procedural agricultural field scenes in Blender for robot training.

Builds fields of crops at chosen growth stages, with weeds, soil, beds, mulch,
irrigation, trellises, obstacles, lighting and weather, then renders RGB images
with matching ground truth: semantic masks, instance masks, depth and JSON
annotations.

Run inside Blender (``blender -b -P scripts/generate.py -- ...``) or with the
``bpy`` Python module (``pip install bpy``).
"""

__version__ = "1.0.0"

try:  # with the pip ``bpy`` module, ``mathutils`` only becomes importable after bpy
    import bpy  # noqa: F401
except ImportError:  # pragma: no cover - documentation builds without Blender
    pass
