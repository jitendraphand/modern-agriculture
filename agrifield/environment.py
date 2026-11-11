"""Sun, sky, weather and exposure presets."""

import math

import bpy

from .materials import lin

# elevation / azimuth in degrees (azimuth: 0 = +y north, 90 = +x east)
LIGHTING = {
    "dawn": dict(elev=4, az=75, sun=1.2, color="#ffb27a", sky=0.35, turb=0.6, exposure=0.6, angle=1.0),
    "morning": dict(elev=22, az=105, sun=3.2, color="#fff0dc", sky=0.7, turb=0.4, exposure=0.0, angle=0.6),
    "noon": dict(elev=62, az=175, sun=4.5, color="#fffaf2", sky=0.8, turb=0.3, exposure=-0.4, angle=0.5),
    "afternoon": dict(elev=35, az=235, sun=3.8, color="#fff4e4", sky=0.75, turb=0.4, exposure=-0.2, angle=0.55),
    "golden_hour": dict(elev=7, az=280, sun=2.4, color="#ffc68a", sky=0.45, turb=0.6, exposure=0.3, angle=0.8),
    "overcast": dict(elev=40, az=200, sun=0.25, color="#f0f2f5", sky=1.6, turb=1.0, exposure=0.5, angle=25.0, grey=0.85),
    "dusk": dict(elev=-1.5, az=285, sun=0.0, color="#ff9a6a", sky=0.6, turb=0.5, exposure=2.4, angle=1.0),
    "night": dict(elev=-20, az=0, sun=0.0, color="#ffffff", sky=0.0, turb=0.3, exposure=0.6, angle=1.0, night=True),
}


def _sun_dir(elev, az):
    e, a = math.radians(elev), math.radians(az)
    # direction the light travels (from sun to ground)
    return (-math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), -math.sin(e))


def setup(scene, cfg, field_center):
    preset = dict(LIGHTING[cfg.get("lighting", "morning")])
    preset.update(cfg.get("lighting_overrides", {}))
    world = bpy.data.worlds.new("AF_World")
    scene.world = world
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    night = preset.get("night", False)
    if night:
        bg.inputs["Color"].default_value = lin("#0a0f1e")
        bg.inputs["Strength"].default_value = 0.02
    else:
        sky = nt.nodes.new("ShaderNodeTexSky")
        try:
            sky.sky_type = "MULTIPLE_SCATTERING"
        except TypeError:
            sky.sky_type = "HOSEK_WILKIE"
        if hasattr(sky, "sun_disc"):
            sky.sun_disc = False
        sky.sun_elevation = math.radians(max(preset["elev"], -4.0))
        sky.sun_rotation = math.radians(90 - preset["az"] + 180)
        sky.air_density = 1.0
        sky.aerosol_density = 1.0 + 3.0 * preset["turb"]
        grey = preset.get("grey", 0.0)
        if grey:
            mix = nt.nodes.new("ShaderNodeMixRGB")
            mix.inputs[0].default_value = grey
            mix.inputs[2].default_value = lin("#c8ccd2")
            nt.links.new(sky.outputs[0], mix.inputs[1])
            nt.links.new(mix.outputs[0], bg.inputs["Color"])
        else:
            nt.links.new(sky.outputs[0], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = preset["sky"] * 0.3 if not grey else preset["sky"]
    world["af_preset"] = cfg.get("lighting", "morning")

    sun_obj = None
    if preset["sun"] > 0:
        sun = bpy.data.lights.new("AF_Sun", "SUN")
        sun.energy = preset["sun"]
        sun.color = lin(preset["color"])[:3]
        sun.angle = math.radians(preset.get("angle", 0.5))
        sun_obj = bpy.data.objects.new("AF_Sun", sun)
        scene.collection.objects.link(sun_obj)
        d = _sun_dir(preset["elev"], preset["az"])
        from mathutils import Vector
        sun_obj.rotation_euler = Vector(d).to_track_quat("-Z", "Y").to_euler()
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = preset["exposure"] + cfg.get("exposure", 0.0)

    fog = cfg.get("fog", 0.0)
    fog_obj = None
    if fog > 0:
        me = bpy.data.meshes.new("AF_FogVolume")
        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(me)
        bm.free()
        fog_obj = bpy.data.objects.new("AF_FogVolume", me)
        fog_obj.scale = (160, 160, 30)
        fog_obj.location = (field_center[0], field_center[1], 14.0)
        mat = bpy.data.materials.new("AF_Fog")
        mat["semantic"] = 0
        mnt = mat.node_tree
        mnt.nodes.clear()
        o = mnt.nodes.new("ShaderNodeOutputMaterial")
        v = mnt.nodes.new("ShaderNodeVolumePrincipled")
        v.inputs["Density"].default_value = 0.02 * fog
        v.inputs["Color"].default_value = lin("#e8ecf0")
        mnt.links.new(v.outputs[0], o.inputs["Volume"])
        me.materials.append(mat)
        scene.collection.objects.link(fog_obj)
        fog_obj["af_render_only"] = True
    return dict(preset=preset, sun=sun_obj, fog=fog_obj, night=night)


def headlight(scene, cam_obj, energy=600.0):
    """Robot-mounted flood light (used for night scenarios)."""
    light = bpy.data.lights.new("AF_Headlight_" + cam_obj.name, "SPOT")
    light.energy = energy
    light.spot_size = math.radians(95)
    light.spot_blend = 0.6
    light.color = (1.0, 0.97, 0.92)
    light.shadow_soft_size = 0.15
    obj = bpy.data.objects.new(light.name, light)
    scene.collection.objects.link(obj)
    obj.matrix_world = cam_obj.matrix_world.copy()
    return obj
