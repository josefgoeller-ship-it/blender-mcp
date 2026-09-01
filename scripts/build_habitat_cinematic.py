"""Build a new cinematic Stanford-torus habitat from a cleared scene."""

from __future__ import annotations

import shutil
from pathlib import Path

from blender_mcp import headless
from blender_mcp.config import get_settings
from blender_mcp.refs import add_reference

REF_CANDIDATES = [
    Path(r"C:\Users\tulpa\.cursor\projects\e-Myprojects-blender-mcp\assets")
    / "c__Users_tulpa_AppData_Roaming_Cursor_User_workspaceStorage_80f21cda21208b7c2c3223de422ad593_images_spaceship-a33ab5dd-9e82-4233-b6ea-a4147c9f6490.png",
]

BUILD = r"""
import math as _m

# --- clear ---
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
for mesh in list(bpy.data.meshes):
    bpy.data.meshes.remove(mesh)
for light in list(bpy.data.lights):
    bpy.data.lights.remove(light)
for cam in list(bpy.data.cameras):
    bpy.data.cameras.remove(cam)
for mat in list(bpy.data.materials):
    bpy.data.materials.remove(mat)

scene = C.scene

# --- world ---
world = D.worlds.get("World") or D.worlds.new("World")
world.use_nodes = True
wnt = world.node_tree
for n in list(wnt.nodes):
    wnt.nodes.remove(n)
wout = wnt.nodes.new("ShaderNodeOutputWorld")
wbg = wnt.nodes.new("ShaderNodeBackground")
wtex = wnt.nodes.new("ShaderNodeTexNoise")
wtex.inputs["Scale"].default_value = 240.0
wtex.inputs["Detail"].default_value = 12.0
wramp = wnt.nodes.new("ShaderNodeValToRGB")
wramp.color_ramp.elements[0].position = 0.90
wramp.color_ramp.elements[0].color = (0.002, 0.003, 0.01, 1)
wramp.color_ramp.elements[1].position = 0.985
wramp.color_ramp.elements[1].color = (0.85, 0.9, 1.0, 1)
wnt.links.new(wtex.outputs["Fac"], wramp.inputs["Fac"])
wnt.links.new(wramp.outputs["Color"], wbg.inputs["Color"])
wbg.inputs[1].default_value = 0.25
wnt.links.new(wbg.outputs["Background"], wout.inputs["Surface"])
scene.world = world


def aim_at(obj, target=(0.0, 0.0, 0.0)):
    direction = mathutils.Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def parent_keep(obj, parent):
    if parent is None:
        return
    mw = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_parent_inverse = parent.matrix_world.inverted()
    obj.matrix_world = mw


def smooth_obj(obj, angle=40.0):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    C.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=_m.radians(angle))
    except Exception:
        try:
            bpy.ops.object.shade_smooth()
        except Exception:
            pass
    obj.select_set(False)


def seti(bsdf, name, value):
    sock = bsdf.inputs.get(name)
    if sock is not None:
        sock.default_value = value


def new_mat(name):
    m = D.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (900, 0)
    return m, nt, out


def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def link_mix_color(nt, a, b, fac):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    if isinstance(fac, (int, float)):
        node.inputs["Factor"].default_value = fac
    else:
        nt.links.new(fac, node.inputs["Factor"])
    try:
        if hasattr(a, "type"):
            nt.links.new(a, node.inputs[6])
        else:
            node.inputs[6].default_value = a
        if hasattr(b, "type"):
            nt.links.new(b, node.inputs[7])
        else:
            node.inputs[7].default_value = b
        return node.outputs[2]
    except Exception:
        return node.outputs[0]


# --- materials ---
hull, nt, out = new_mat("HullWindows")
coord = nt.nodes.new("ShaderNodeTexCoord")
mapn = nt.nodes.new("ShaderNodeMapping")
mapn.inputs["Scale"].default_value = (1.8, 10.0, 4.0)
nt.links.new(coord.outputs["Object"], mapn.inputs["Vector"])
brick = nt.nodes.new("ShaderNodeTexBrick")
brick.inputs["Scale"].default_value = 16.0
brick.inputs["Mortar Size"].default_value = 0.42
brick.inputs["Color1"].default_value = (1, 1, 1, 1)
brick.inputs["Color2"].default_value = (0.2, 0.2, 0.2, 1)
brick.inputs["Mortar"].default_value = (0, 0, 0, 1)
nt.links.new(mapn.outputs["Vector"], brick.inputs["Vector"])
noise = nt.nodes.new("ShaderNodeTexNoise")
noise.inputs["Scale"].default_value = 22.0
noise.inputs["Detail"].default_value = 4.0
nt.links.new(mapn.outputs["Vector"], noise.inputs["Vector"])
gt = nt.nodes.new("ShaderNodeMath")
gt.operation = "GREATER_THAN"
gt.inputs[1].default_value = 0.72
nt.links.new(noise.outputs["Fac"], gt.inputs[0])
mul = nt.nodes.new("ShaderNodeMath")
mul.operation = "MULTIPLY"
nt.links.new(brick.outputs["Fac"], mul.inputs[0])
nt.links.new(gt.outputs["Value"], mul.inputs[1])
win_ramp = nt.nodes.new("ShaderNodeValToRGB")
win_ramp.color_ramp.elements[0].position = 0.82
win_ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
win_ramp.color_ramp.elements[1].position = 0.94
win_ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
nt.links.new(mul.outputs["Value"], win_ramp.inputs["Fac"])
wear = nt.nodes.new("ShaderNodeTexVoronoi")
wear.feature = "F1"
wear.inputs["Scale"].default_value = 7.0
nt.links.new(coord.outputs["Object"], wear.inputs["Vector"])
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
base = link_mix_color(nt, (0.07, 0.075, 0.085, 1), (0.14, 0.15, 0.17, 1), wear.outputs["Distance"])
nt.links.new(base, bsdf.inputs["Base Color"])
seti(bsdf, "Metallic", 0.92)
seti(bsdf, "Roughness", 0.52)
seti(bsdf, "Coat Weight", 0.08)
emit = nt.nodes.new("ShaderNodeEmission")
emit.inputs["Color"].default_value = (1.0, 0.62, 0.28, 1)
emit.inputs["Strength"].default_value = 14.0
mixs = nt.nodes.new("ShaderNodeMixShader")
nt.links.new(win_ramp.outputs["Color"], mixs.inputs["Fac"])
nt.links.new(bsdf.outputs["BSDF"], mixs.inputs[1])
nt.links.new(emit.outputs["Emission"], mixs.inputs[2])
nt.links.new(mixs.outputs["Shader"], out.inputs["Surface"])

dark, nt, out = new_mat("HullDark")
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
coord = nt.nodes.new("ShaderNodeTexCoord")
vn = nt.nodes.new("ShaderNodeTexVoronoi")
vn.inputs["Scale"].default_value = 12.0
nt.links.new(coord.outputs["Object"], vn.inputs["Vector"])
col = link_mix_color(nt, (0.12, 0.13, 0.15, 1), (0.20, 0.21, 0.24, 1), vn.outputs["Distance"])
nt.links.new(col, bsdf.inputs["Base Color"])
seti(bsdf, "Metallic", 0.95)
seti(bsdf, "Roughness", 0.58)
nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

truss, nt, out = new_mat("TrussMetal")
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
seti(bsdf, "Base Color", (0.45, 0.47, 0.50, 1))
seti(bsdf, "Metallic", 1.0)
seti(bsdf, "Roughness", 0.38)
nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

accent, nt, out = new_mat("SafetyOrange")
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
seti(bsdf, "Base Color", (0.95, 0.38, 0.08, 1))
seti(bsdf, "Metallic", 0.15)
seti(bsdf, "Roughness", 0.42)
seti(bsdf, "Emission Color", (1.0, 0.3, 0.05, 1))
seti(bsdf, "Emission Strength", 0.6)
nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

glow, nt, out = new_mat("BayGlow")
emit = nt.nodes.new("ShaderNodeEmission")
emit.inputs["Color"].default_value = (1.0, 0.64, 0.30, 1)
emit.inputs["Strength"].default_value = 8.0
nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])

glass, nt, out = new_mat("BayGlass")
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
seti(bsdf, "Base Color", (1.0, 0.75, 0.4, 1))
seti(bsdf, "Roughness", 0.08)
seti(bsdf, "Transmission Weight", 0.15)
seti(bsdf, "Emission Color", (1.0, 0.62, 0.28, 1))
seti(bsdf, "Emission Strength", 2.5)
nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

exhaust, nt, out = new_mat("ShipExhaust")
emit = nt.nodes.new("ShaderNodeEmission")
emit.inputs["Color"].default_value = (0.55, 0.75, 1.0, 1)
emit.inputs["Strength"].default_value = 12.0
nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])

# planet
planet_mat, nt, out = new_mat("PlanetBody")
coord = nt.nodes.new("ShaderNodeTexCoord")
noise = nt.nodes.new("ShaderNodeTexNoise")
noise.inputs["Scale"].default_value = 3.2
noise.inputs["Detail"].default_value = 14.0
nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
land = link_mix_color(nt, (0.02, 0.04, 0.12, 1), (0.08, 0.16, 0.06, 1), noise.outputs["Fac"])
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
nt.links.new(land, bsdf.inputs["Base Color"])
seti(bsdf, "Roughness", 0.78)
seti(bsdf, "Metallic", 0.0)
# night lights
n2 = nt.nodes.new("ShaderNodeTexNoise")
n2.inputs["Scale"].default_value = 55.0
n2.inputs["Detail"].default_value = 8.0
nt.links.new(coord.outputs["Object"], n2.inputs["Vector"])
nr = nt.nodes.new("ShaderNodeValToRGB")
nr.color_ramp.elements[0].position = 0.72
nr.color_ramp.elements[0].color = (0, 0, 0, 1)
nr.color_ramp.elements[1].position = 0.88
nr.color_ramp.elements[1].color = (1.0, 0.75, 0.4, 1)
nt.links.new(n2.outputs["Fac"], nr.inputs["Fac"])
em = nt.nodes.new("ShaderNodeEmission")
em.inputs["Strength"].default_value = 4.0
nt.links.new(nr.outputs["Color"], em.inputs["Color"])
add = nt.nodes.new("ShaderNodeAddShader")
nt.links.new(bsdf.outputs["BSDF"], add.inputs[0])
nt.links.new(em.outputs["Emission"], add.inputs[1])
nt.links.new(add.outputs["Shader"], out.inputs["Surface"])

atmo_mat, nt, out = new_mat("PlanetAtmo")
coord = nt.nodes.new("ShaderNodeTexCoord")
lrp = nt.nodes.new("ShaderNodeLayerWeight")
lrp.inputs["Blend"].default_value = 0.28
nt.links.new(coord.outputs["Normal"], lrp.inputs["Normal"])
em = nt.nodes.new("ShaderNodeEmission")
em.inputs["Color"].default_value = (0.25, 0.55, 1.0, 1)
em.inputs["Strength"].default_value = 3.5
nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
# use layer weight as mix vs transparent
tr = nt.nodes.new("ShaderNodeBsdfTransparent")
mixs = nt.nodes.new("ShaderNodeMixShader")
nt.links.new(lrp.outputs["Facing"], mixs.inputs["Fac"])
nt.links.new(em.outputs["Emission"], mixs.inputs[1])
nt.links.new(tr.outputs["BSDF"], mixs.inputs[2])
# reconnect
for l in list(nt.links):
    if l.to_socket == out.inputs["Surface"]:
        nt.links.remove(l)
nt.links.new(mixs.outputs["Shader"], out.inputs["Surface"])
atmo_mat.blend_method = "BLEND" if hasattr(atmo_mat, "blend_method") else "OPAQUE"
if hasattr(atmo_mat, "shadow_method"):
    atmo_mat.shadow_method = "NONE"

# --- hierarchy ---
bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 0))
root = C.active_object
root.name = "HabitatRoot"
bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 0))
ring_root = C.active_object
ring_root.name = "RingRoot"
parent_keep(ring_root, root)
bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 0))
ships_root = C.active_object
ships_root.name = "ScaleShips"

created = 0


def add_cube(name, loc, scale, rot, mat, parent):
    global created
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    o = C.active_object
    o.name = name
    o.scale = scale
    o.rotation_euler = rot
    assign(o, mat)
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    C.view_layer.objects.active = o
    smooth_obj(o, 45)
    parent_keep(o, parent)
    created += 1
    return o


def add_cyl(name, loc, radius, depth, rot, mat, parent, verts=24):
    global created
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=depth, location=loc)
    o = C.active_object
    o.name = name
    o.rotation_euler = rot
    assign(o, mat)
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    C.view_layer.objects.active = o
    smooth_obj(o, 35)
    parent_keep(o, parent)
    created += 1
    return o


# --- spire ---
spire_secs = (
    ("SpireLow", (0, 0, -2.15), 1.55, 2.5),
    ("SpireMid", (0, 0, 0.15), 1.28, 2.1),
    ("SpireUpper", (0, 0, 2.05), 1.02, 1.7),
    ("SpireCap", (0, 0, 3.25), 0.72, 0.75),
)
for name, loc, rad, depth in spire_secs:
    add_cyl(name, loc, rad, depth, (0, 0, 0), hull, root, verts=32)

# ribs + orange bands
for i, z in enumerate((-2.9, -1.4, -0.7, 0.9, 1.7, 2.7, 3.5)):
    r = 1.62 if z < 0 else (1.35 if z < 2.2 else 1.08)
    mat = accent if i % 3 == 1 else dark
    add_cyl(f"SpireRib_{i}", (0, 0, z), r, 0.07, (0, 0, 0), mat, root, verts=28)

add_cyl("CommMast", (0, 0, 4.15), 0.07, 1.5, (0, 0, 0), truss, root, verts=10)
bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.38, location=(0, 0, 4.85))
dish = C.active_object
dish.name = "CommDish"
dish.scale = (1.0, 1.0, 0.18)
assign(dish, truss)
smooth_obj(dish)
parent_keep(dish, root)
created += 1

# spire observation bays (physical)
for ang, z in ((25, 0.3), (115, 0.3), (205, 0.3), (295, 0.3), (70, 1.9), (250, 1.9)):
    rad = _m.radians(ang)
    r = 1.32 if z < 1.0 else 1.06
    loc = (r * _m.cos(rad), r * _m.sin(rad), z)
    rot = (0.0, 0.0, rad)
    add_cube(f"SpireBayFrame_{ang}_{z}", loc, (0.08, 0.42, 0.28), rot, dark, root)
    add_cube(
        f"SpireBayGlow_{ang}_{z}",
        (loc[0] + 0.05 * _m.cos(rad), loc[1] + 0.05 * _m.sin(rad), z),
        (0.03, 0.34, 0.22),
        rot,
        glow,
        root,
    )

# --- modular ring ---
N = 24
R = 5.55
modules = []
for i in range(N):
    ang = i * (360.0 / N)
    rad = _m.radians(ang)
    loc = (R * _m.cos(rad), R * _m.sin(rad), 0.0)
    rot = (0.0, 0.0, rad)
    mod = add_cube(f"RingMod_{i}", loc, (1.35, 1.52, 1.15), rot, hull, ring_root)
    modules.append((mod, ang, rad, loc))
    # top vent
    top = (
        loc[0],
        loc[1],
        0.68,
    )
    add_cube(f"RingVent_{i}", top, (0.45, 0.55, 0.22), rot, dark, mod)
    # side rib
    add_cube(
        f"RingRib_{i}",
        (loc[0], loc[1], 0.0),
        (1.42, 0.12, 1.05),
        rot,
        dark,
        mod,
    )

# outer pods every 3rd module, attached by a neck
for i in range(0, N, 3):
    _mod, ang, rad, loc = modules[i]
    outer_r = R + 0.95
    neck_r = R + 0.72
    neck_loc = (neck_r * _m.cos(rad), neck_r * _m.sin(rad), 0.0)
    pod_loc = (outer_r * _m.cos(rad), outer_r * _m.sin(rad), 0.0)
    add_cyl(
        f"PodNeck_{i}",
        neck_loc,
        0.18,
        0.55,
        (0.0, 1.5708, rad),
        dark,
        _mod,
        verts=12,
    )
    add_cyl(
        f"PodTank_{i}",
        pod_loc,
        0.38,
        0.95,
        (0.0, 1.5708, rad) if i % 6 == 0 else (0.0, 0.0, rad),
        dark,
        _mod,
        verts=16,
    )

# greeble tanks on remaining modules (on the hull, not floating)
for i in range(1, N, 3):
    _mod, ang, rad, loc = modules[i]
    g_r = R + 0.78
    gloc = (g_r * _m.cos(rad), g_r * _m.sin(rad), 0.35)
    add_cyl(f"GreebleTank_{i}", gloc, 0.16, 0.42, (0.0, 1.5708, rad), truss, _mod, verts=10)

# four observation bays on ring outer face
for i in (3, 9, 15, 21):
    _mod, ang, rad, loc = modules[i]
    br = R + 0.70
    bloc = (br * _m.cos(rad), br * _m.sin(rad), 0.08)
    rot = (0.0, 0.0, rad)
    add_cube(f"ObsFrame_{i}", bloc, (0.1, 0.85, 0.48), rot, dark, _mod)
    add_cube(
        f"ObsGlow_{i}",
        ((br + 0.06) * _m.cos(rad), (br + 0.06) * _m.sin(rad), 0.08),
        (0.04, 0.72, 0.38),
        rot,
        glow,
        _mod,
    )
    add_cube(
        f"ObsGlass_{i}",
        ((br + 0.09) * _m.cos(rad), (br + 0.09) * _m.sin(rad), 0.08),
        (0.02, 0.70, 0.36),
        rot,
        glass,
        _mod,
    )

# radiator fins grown from module tops (attached)
for i in (2, 8, 14, 20):
    _mod, ang, rad, loc = modules[i]
    floc = (loc[0], loc[1], 0.95)
    add_cube(f"Radiator_{i}", floc, (0.08, 0.9, 0.55), (0.0, 0.0, rad), truss, _mod)

# --- spokes (thick corridors + lattice) ---
for si, ang in enumerate((0, 90, 180, 270)):
    rad = _m.radians(ang)
    mid = 3.20
    loc = (mid * _m.cos(rad), mid * _m.sin(rad), 0.0)
    rot = (0.0, 1.5708, rad)
    corr = add_cube(f"SpokeCorr_{ang}", loc, (3.55, 0.62, 0.50), (0.0, 0.0, rad), dark, root)
    # window slits on corridor SIDES so they don't read as a runway
    px, py = -_m.sin(rad) * 0.33, _m.cos(rad) * 0.33
    for t in (-0.85, 0.0, 0.85):
        sl = mid + t
        sloc = (sl * _m.cos(rad) + px, sl * _m.sin(rad) + py, 0.05)
        add_cube(f"SpokeWin_{ang}_{t}", sloc, (0.28, 0.05, 0.14), (0.0, 0.0, rad), glow, corr)
    # truss lattice around corridor
    for side, zoff, ysign in ((0, 0.28, 0.28), (1, 0.28, -0.28), (2, -0.28, 0.28), (3, -0.28, -0.28)):
        tloc = (
            mid * _m.cos(rad) + ysign * _m.sin(rad) * 0.0,
            mid * _m.sin(rad) - ysign * _m.cos(rad) * 0.0,
            zoff,
        )
        # offset perpendicular
        px = -_m.sin(rad) * ysign
        py = _m.cos(rad) * ysign
        tloc = (mid * _m.cos(rad) + px, mid * _m.sin(rad) + py, zoff)
        add_cyl(f"SpokeTruss_{ang}_{side}", tloc, 0.04, 2.7, rot, truss, corr, verts=8)

# --- ships ---
def make_ship(tag, loc, yaw, size):
    hull_o = add_cube(f"ShipHull_{tag}", loc, (size * 2.2, size * 0.45, size * 0.32), (0, 0, yaw), dark, ships_root)
    w1 = (
        loc[0] - 0.15 * size * _m.sin(yaw),
        loc[1] + 0.15 * size * _m.cos(yaw),
        loc[2],
    )
    add_cube(f"ShipWingL_{tag}", w1, (size * 0.5, size * 1.1, size * 0.06), (0, 0, yaw), truss, hull_o)
    add_cyl(
        f"ShipEx_{tag}",
        (loc[0] - size * 1.15 * _m.cos(yaw), loc[1] - size * 1.15 * _m.sin(yaw), loc[2]),
        size * 0.08,
        size * 0.12,
        (0, 1.5708, yaw),
        exhaust,
        hull_o,
        verts=8,
    )


make_ship("A", (6.2, -6.6, 1.15), _m.radians(25), 0.22)
make_ship("B", (7.1, -5.4, -0.35), _m.radians(-20), 0.16)
make_ship("C", (5.0, -7.2, 0.55), _m.radians(70), 0.14)

# --- planet ---
bpy.ops.object.select_all(action="DESELECT")
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1.0, location=(16.0, 52.0, -32.0))
planet = C.active_object
planet.name = "Planet"
planet.scale = (22.0, 22.0, 22.0)
assign(planet, planet_mat)
smooth_obj(planet, 30)
bpy.ops.object.select_all(action="DESELECT")
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1.0, location=(16.0, 52.0, -32.0))
atmo = C.active_object
atmo.name = "PlanetAtmo"
atmo.scale = (23.4, 23.4, 23.4)
assign(atmo, atmo_mat)
smooth_obj(atmo, 30)
if hasattr(atmo, "visible_shadow"):
    atmo.visible_shadow = False

# --- lights ---
sun_data = D.lights.new("SunKey", type="SUN")
sun_data.energy = 11.0
sun_data.color = (1.0, 0.97, 0.92)
if hasattr(sun_data, "angle"):
    sun_data.angle = _m.radians(1.5)
sun = D.objects.new("SunKey", sun_data)
sun.location = (22.0, -6.0, 10.0)
aim_at(sun, (0.0, 0.0, 0.2))
scene.collection.objects.link(sun)

fill_data = D.lights.new("Fill", type="AREA")
fill_data.energy = 90.0
fill_data.color = (0.45, 0.62, 1.0)
fill_data.size = 14.0
fill = D.objects.new("Fill", fill_data)
fill.location = (-16.0, -10.0, 6.0)
aim_at(fill, (0, 0, 0))
scene.collection.objects.link(fill)

earth_data = D.lights.new("Earthshine", type="AREA")
earth_data.energy = 70.0
earth_data.color = (0.35, 0.55, 1.0)
earth_data.size = 18.0
earth = D.objects.new("Earthshine", earth_data)
earth.location = (10.0, 20.0, -12.0)
aim_at(earth, (0, 0, 0))
scene.collection.objects.link(earth)

# --- camera ---
cam_data = D.cameras.new("Camera")
cam_data.lens = 52.0
cam = D.objects.new("Camera", cam_data)
cam.location = (-1.8, -16.8, 4.6)
aim_at(cam, (1.6, 1.2, 0.1))
scene.collection.objects.link(cam)
scene.camera = cam
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.film_transparent = False
scene.render.use_compositing = False

eevee = getattr(scene, "eevee", None)
if eevee is not None and hasattr(eevee, "use_raytracing"):
    eevee.use_raytracing = True

result = {"created": created, "modules": N, "root": root.name}
"""


def copy_reference(settings) -> str | None:
    dest_dir = settings.output_dir / "refs" / "space_habitat"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for cand in REF_CANDIDATES:
        if cand.is_file():
            try:
                info = add_reference(settings, cand, name="reference.png", group="space_habitat")
                print("Copied reference:", info["path"])
                return info["path"]
            except Exception as exc:
                dest = dest_dir / "reference.png"
                shutil.copy2(cand, dest)
                print("Copied reference fallback:", dest, exc)
                return str(dest)
    # search assets folder
    assets = Path(r"C:\Users\tulpa\.cursor\projects\e-Myprojects-blender-mcp\assets")
    if assets.is_dir():
        for p in assets.glob("*.png"):
            dest = dest_dir / "reference.png"
            shutil.copy2(p, dest)
            print("Copied reference from assets:", p)
            return str(dest)
    print("No reference image found (continuing without copy)")
    return None


def main() -> int:
    settings = get_settings()
    copy_reference(settings)
    out_dir = settings.output_dir / "space_habitat"
    out_dir.mkdir(parents=True, exist_ok=True)
    blend = out_dir / "habitat_cinematic.blend"
    print("Building cinematic habitat...")
    job = headless.run_job(
        settings,
        [
            {"type": "execute", "code": BUILD},
            {"type": "save_as", "path": str(blend), "compress": True},
        ],
        timeout=180,
    )
    print("ok:", job.ok)
    for step in job.responses:
        print(step.get("ok"), step.get("result") or step.get("error"))
    if not job.ok:
        print("STDOUT TAIL:\n", job.stdout[-4000:])
        return 1
    print("Saved:", blend)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
