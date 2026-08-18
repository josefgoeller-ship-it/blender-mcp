"""Incremental detail pass on the existing space habitat .blend."""

from __future__ import annotations

from blender_mcp import headless
from blender_mcp.config import get_settings

IMPROVE = r"""
import math as _m

root = D.objects.get("SpaceHabitat")
scene = C.scene
created = []


def aim_at(obj, target=(0.0, 0.0, 0.0)):
    direction = mathutils.Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def parent_root(obj):
    if root:
        obj.parent = root
    created.append(obj.name)


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


def unlink_prefix(*prefixes):
    for obj in list(D.objects):
        if any(obj.name.startswith(p) for p in prefixes):
            D.objects.remove(obj, do_unlink=True)


def seti(bsdf, name, value):
    sock = bsdf.inputs.get(name)
    if sock is not None:
        sock.default_value = value


def mix_color(nt, a, b, fac, blend="MIX"):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    node.blend_type = blend
    if isinstance(fac, (int, float)):
        node.inputs["Factor"].default_value = fac
    else:
        nt.links.new(fac, node.inputs["Factor"])
    color_a = node.inputs.get("A") or node.inputs.get("Color1")
    color_b = node.inputs.get("B") or node.inputs.get("Color2")
    # Blender 4+/5 Mix RGBA sockets are often indices 6/7
    try:
        if hasattr(a, "type"):
            nt.links.new(a, node.inputs[6])
        else:
            node.inputs[6].default_value = a
        if hasattr(b, "type"):
            nt.links.new(b, node.inputs[7])
        else:
            node.inputs[7].default_value = b
    except Exception:
        if hasattr(a, "type"):
            nt.links.new(a, color_a)
        else:
            color_a.default_value = a
        if hasattr(b, "type"):
            nt.links.new(b, color_b)
        else:
            color_b.default_value = b
    return node.outputs[2] if len(node.outputs) > 2 else node.outputs[0]


def rebuild_mat(name):
    m = D.materials.get(name) or D.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (900, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (600, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m, nt, bsdf


# --- materials ---
hull, nt, bsdf = rebuild_mat("HullMetal")
coord = nt.nodes.new("ShaderNodeTexCoord")
coord.location = (-900, 0)
map_n = nt.nodes.new("ShaderNodeMapping")
map_n.location = (-700, 80)
map_n.inputs["Scale"].default_value = (1.4, 1.4, 1.4)
nt.links.new(coord.outputs["Generated"], map_n.inputs["Vector"])
noise = nt.nodes.new("ShaderNodeTexNoise")
noise.location = (-480, 160)
noise.inputs["Scale"].default_value = 7.5
noise.inputs["Detail"].default_value = 10.0
noise.inputs["Roughness"].default_value = 0.55
nt.links.new(map_n.outputs["Vector"], noise.inputs["Vector"])
voronoi = nt.nodes.new("ShaderNodeTexVoronoi")
voronoi.location = (-480, -80)
voronoi.feature = "F1"
voronoi.inputs["Scale"].default_value = 10.0
nt.links.new(map_n.outputs["Vector"], voronoi.inputs["Vector"])
brick = nt.nodes.new("ShaderNodeTexBrick")
brick.location = (-480, 80)
brick.inputs["Scale"].default_value = 5.0
brick.inputs["Mortar Size"].default_value = 0.03
brick.inputs["Color1"].default_value = (0.44, 0.48, 0.54, 1)
brick.inputs["Color2"].default_value = (0.56, 0.60, 0.66, 1)
brick.inputs["Mortar"].default_value = (0.10, 0.11, 0.12, 1)
nt.links.new(map_n.outputs["Vector"], brick.inputs["Vector"])
wear = nt.nodes.new("ShaderNodeTexNoise")
wear.location = (-480, 360)
wear.inputs["Scale"].default_value = 3.2
wear.inputs["Detail"].default_value = 6.0
nt.links.new(map_n.outputs["Vector"], wear.inputs["Vector"])
wear_ramp = nt.nodes.new("ShaderNodeValToRGB")
wear_ramp.location = (-250, 360)
wear_ramp.color_ramp.elements[0].position = 0.55
wear_ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
wear_ramp.color_ramp.elements[1].position = 0.82
wear_ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
nt.links.new(wear.outputs["Fac"], wear_ramp.inputs["Fac"])
rust_mix = mix_color(
    nt, brick.outputs["Color"], (0.32, 0.34, 0.38, 1), voronoi.outputs["Distance"]
)
nt.links.new(rust_mix, bsdf.inputs["Base Color"])
rough_ramp = nt.nodes.new("ShaderNodeValToRGB")
rough_ramp.location = (-80, -280)
rough_ramp.color_ramp.elements[0].position = 0.0
rough_ramp.color_ramp.elements[0].color = (0.22, 0.22, 0.22, 1)
rough_ramp.color_ramp.elements[1].position = 1.0
rough_ramp.color_ramp.elements[1].color = (0.55, 0.55, 0.55, 1)
nt.links.new(noise.outputs["Fac"], rough_ramp.inputs["Fac"])
nt.links.new(rough_ramp.outputs["Color"], bsdf.inputs["Roughness"])
seti(bsdf, "Metallic", 1.0)
seti(bsdf, "Coat Weight", 0.32)
seti(bsdf, "Coat Roughness", 0.18)

dark, nt, bsdf = rebuild_mat("HullDark")
coord = nt.nodes.new("ShaderNodeTexCoord")
map_n = nt.nodes.new("ShaderNodeMapping")
nt.links.new(coord.outputs["Object"], map_n.inputs["Vector"])
brick = nt.nodes.new("ShaderNodeTexBrick")
brick.inputs["Scale"].default_value = 14.0
brick.inputs["Mortar Size"].default_value = 0.02
brick.inputs["Color1"].default_value = (0.16, 0.17, 0.20, 1)
brick.inputs["Color2"].default_value = (0.24, 0.26, 0.30, 1)
brick.inputs["Mortar"].default_value = (0.05, 0.05, 0.06, 1)
nt.links.new(map_n.outputs["Vector"], brick.inputs["Vector"])
noise = nt.nodes.new("ShaderNodeTexNoise")
noise.inputs["Scale"].default_value = 11.0
noise.inputs["Detail"].default_value = 8.0
nt.links.new(map_n.outputs["Vector"], noise.inputs["Vector"])
col = mix_color(nt, brick.outputs["Color"], noise.outputs["Color"], 0.22)
nt.links.new(col, bsdf.inputs["Base Color"])
seti(bsdf, "Metallic", 1.0)
seti(bsdf, "Roughness", 0.48)
seti(bsdf, "Coat Weight", 0.15)

solar, nt, bsdf = rebuild_mat("SolarPanel")
coord = nt.nodes.new("ShaderNodeTexCoord")
map_n = nt.nodes.new("ShaderNodeMapping")
map_n.inputs["Scale"].default_value = (18.0, 18.0, 18.0)
nt.links.new(coord.outputs["UV"], map_n.inputs["Vector"])
# UV may be empty on cubes; also feed Object
map_o = nt.nodes.new("ShaderNodeMapping")
map_o.inputs["Scale"].default_value = (12.0, 4.0, 12.0)
nt.links.new(coord.outputs["Object"], map_o.inputs["Vector"])
brick = nt.nodes.new("ShaderNodeTexBrick")
brick.inputs["Scale"].default_value = 6.0
brick.inputs["Mortar Size"].default_value = 0.04
brick.inputs["Color1"].default_value = (0.01, 0.05, 0.22, 1)
brick.inputs["Color2"].default_value = (0.02, 0.09, 0.32, 1)
brick.inputs["Mortar"].default_value = (0.45, 0.48, 0.52, 1)
nt.links.new(map_o.outputs["Vector"], brick.inputs["Vector"])
nt.links.new(brick.outputs["Color"], bsdf.inputs["Base Color"])
seti(bsdf, "Metallic", 0.72)
seti(bsdf, "Roughness", 0.12)
if "Anisotropic" in bsdf.inputs:
    seti(bsdf, "Anisotropic", 0.35)

rad, nt, bsdf = rebuild_mat("Radiator")
coord = nt.nodes.new("ShaderNodeTexCoord")
wave = nt.nodes.new("ShaderNodeTexWave")
wave.wave_type = "BANDS"
wave.inputs["Scale"].default_value = 28.0
wave.inputs["Distortion"].default_value = 0.4
nt.links.new(coord.outputs["Object"], wave.inputs["Vector"])
col = mix_color(nt, (0.78, 0.82, 0.88, 1), (0.92, 0.94, 0.97, 1), wave.outputs["Fac"])
nt.links.new(col, bsdf.inputs["Base Color"])
seti(bsdf, "Metallic", 0.9)
seti(bsdf, "Roughness", 0.2)

truss, nt, bsdf = rebuild_mat("Truss")
coord = nt.nodes.new("ShaderNodeTexCoord")
noise = nt.nodes.new("ShaderNodeTexNoise")
noise.inputs["Scale"].default_value = 18.0
noise.inputs["Detail"].default_value = 6.0
nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
col = mix_color(nt, (0.70, 0.73, 0.78, 1), (0.82, 0.84, 0.88, 1), noise.outputs["Fac"])
nt.links.new(col, bsdf.inputs["Base Color"])
rough_ramp = nt.nodes.new("ShaderNodeValToRGB")
rough_ramp.color_ramp.elements[0].color = (0.22, 0.22, 0.22, 1)
rough_ramp.color_ramp.elements[1].color = (0.42, 0.42, 0.42, 1)
nt.links.new(noise.outputs["Fac"], rough_ramp.inputs["Fac"])
nt.links.new(rough_ramp.outputs["Color"], bsdf.inputs["Roughness"])
seti(bsdf, "Metallic", 1.0)

glass, nt, bsdf = rebuild_mat("ObsGlass")
seti(bsdf, "Base Color", (1.0, 0.82, 0.52, 1))
seti(bsdf, "Metallic", 0.0)
seti(bsdf, "Roughness", 0.08)
seti(bsdf, "Transmission Weight", 0.12)
seti(bsdf, "IOR", 1.45)
seti(bsdf, "Emission Color", (1.0, 0.62, 0.28, 1))
seti(bsdf, "Emission Strength", 3.5)
seti(bsdf, "Alpha", 1.0)

glow, nt, bsdf = rebuild_mat("InteriorGlow")
for n in list(nt.nodes):
    if n.type != "OUTPUT_MATERIAL":
        nt.nodes.remove(n)
out = nt.nodes.get("Material Output") or nt.nodes.new("ShaderNodeOutputMaterial")
emit = nt.nodes.new("ShaderNodeEmission")
emit.inputs["Color"].default_value = (1.0, 0.62, 0.28, 1)
emit.inputs["Strength"].default_value = 6.5
nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])

accent, nt, bsdf = rebuild_mat("AccentOrange")
seti(bsdf, "Base Color", (1.0, 0.40, 0.07, 1))
seti(bsdf, "Metallic", 0.2)
seti(bsdf, "Roughness", 0.38)
seti(bsdf, "Emission Color", (1.0, 0.32, 0.04, 1))
seti(bsdf, "Emission Strength", 1.4)

gold = D.materials.get("AntennaGold")
if gold and gold.use_nodes:
    gbsdf = next((n for n in gold.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if gbsdf:
        seti(gbsdf, "Roughness", 0.16)
        seti(gbsdf, "Metallic", 1.0)
        seti(gbsdf, "Coat Weight", 0.4)

hull_mat = D.materials["HullMetal"]
dark_mat = D.materials["HullDark"]
glass_mat = D.materials["ObsGlass"]
glow_mat = D.materials["InteriorGlow"]
accent_mat = D.materials["AccentOrange"]
truss_mat = D.materials["Truss"]


def assign(obj, material):
    obj.data.materials.clear()
    obj.data.materials.append(material)


# --- remove old tiny windows so they don't fight the new ones ---
unlink_prefix(
    "Window_",
    "WindowGlow_",
    "CrewWindow_",
    "WinFrame_",
    "WinGlass_",
    "WinGlow_",
    "WinLight_",
    "Hatch_",
    "Pipe_",
    "Stripe_",
    "AntennaExtra_",
    "Hinge_",
    "Rivet_",
)
# Drop Blender-5 glare group from a previous pass (star flares drowned the hull)
old_comp = getattr(scene, "compositing_node_group", None)
if old_comp is not None:
    scene.compositing_node_group = None
    try:
        D.node_groups.remove(old_comp)
    except Exception:
        pass
scene.render.use_compositing = False

RING_R = 5.5
RING_MINOR = 0.85
OUTER = RING_R + RING_MINOR + 0.16


def make_window(tag, loc, rot, size=(0.08, 0.48, 0.30), light_energy=0.0):
    sx, sy, sz = size
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    frame = C.active_object
    frame.name = f"WinFrame_{tag}"
    frame.scale = (sx * 1.15, sy * 1.12, sz * 1.12)
    frame.rotation_euler = rot
    assign(frame, dark_mat)
    smooth_obj(frame)
    parent_root(frame)

    # Keep glow/glass outside the hull so they are not occluded
    out_dir = mathutils.Vector((sx * 0.35, 0.0, 0.0))
    out_dir.rotate(mathutils.Euler(rot))
    glass_loc = mathutils.Vector(loc) + out_dir
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=glass_loc)
    gl = C.active_object
    gl.name = f"WinGlass_{tag}"
    gl.scale = (sx * 0.22, sy * 0.88, sz * 0.84)
    gl.rotation_euler = rot
    assign(gl, glass_mat)
    smooth_obj(gl)
    parent_root(gl)

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    gp = C.active_object
    gp.name = f"WinGlow_{tag}"
    gp.scale = (sx * 0.18, sy * 0.84, sz * 0.80)
    gp.rotation_euler = rot
    assign(gp, glow_mat)
    parent_root(gp)

    if light_energy > 0.0:
        lamp = D.lights.new(f"WinLightData_{tag}", type="POINT")
        lamp.energy = light_energy
        lamp.color = (1.0, 0.72, 0.42)
        lamp.shadow_soft_size = 0.25
        lo = D.objects.new(f"WinLight_{tag}", lamp)
        lo.location = mathutils.Vector(loc) + out_dir * 0.2
        scene.collection.objects.link(lo)
        parent_root(lo)
    return frame


# Ring windows on the outer equator (tilted up so a 3/4 camera sees the pane)
for ang in range(0, 360, 30):
    rad = _m.radians(ang)
    x, y = OUTER * _m.cos(rad), OUTER * _m.sin(rad)
    rot = (0.35, 0.0, rad)
    make_window(f"Ring_{ang}", (x, y, 0.22), rot, size=(0.14, 0.95, 0.55), light_energy=0.0)

# Crown windows on top of the torus — face +Z, readable from above
for ang in range(15, 360, 30):
    rad = _m.radians(ang)
    x, y = RING_R * _m.cos(rad), RING_R * _m.sin(rad)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, RING_MINOR + 0.06))
    fr = C.active_object
    fr.name = f"WinFrame_Crown_{ang}"
    fr.scale = (0.38, 0.55, 0.05)
    fr.rotation_euler = (0.0, 0.0, rad)
    assign(fr, dark_mat)
    parent_root(fr)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, RING_MINOR + 0.10))
    gp = C.active_object
    gp.name = f"WinGlow_Crown_{ang}"
    gp.scale = (0.32, 0.46, 0.03)
    gp.rotation_euler = (0.0, 0.0, rad)
    assign(gp, glow_mat)
    parent_root(gp)

# Larger observation bays
for ang in (45, 135, 225, 315):
    rad = _m.radians(ang)
    x, y = (OUTER + 0.04) * _m.cos(rad), (OUTER + 0.04) * _m.sin(rad)
    make_window(f"Obs_{ang}", (x, y, 0.15), (0.4, 0.0, rad), size=(0.16, 1.25, 0.70), light_energy=2.5)

# Hub portholes
for ang, z in ((20, 0.55), (140, 0.55), (260, 0.55), (80, -0.4), (200, -0.4), (320, -0.4)):
    rad = _m.radians(ang)
    r = 1.42
    loc = (r * _m.cos(rad), r * _m.sin(rad), z)
    make_window(f"Hub_{ang}_{z}", loc, (0.0, 0.0, rad), size=(0.08, 0.34, 0.26), light_energy=0.0)

# Crew module windows (modules sit on ring at 10/100/190/280)
for ang in (10, 100, 190, 280):
    rad = _m.radians(ang)
    r = 6.22
    loc = (r * _m.cos(rad), r * _m.sin(rad), 0.95)
    make_window(f"Crew_{ang}", loc, (0.0, 0.0, rad), size=(0.08, 0.42, 0.26), light_energy=0.0)

# --- greebles ---
for ang in range(0, 360, 45):
    rad = _m.radians(ang)
    x, y = RING_R * _m.cos(rad), RING_R * _m.sin(rad)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.38, minor_radius=0.045, major_segments=24, minor_segments=10, location=(x, y, 0.92)
    )
    h = C.active_object
    h.name = f"Hatch_{ang}"
    h.rotation_euler = (0.0, 0.0, rad)
    assign(h, dark_mat)
    smooth_obj(h)
    parent_root(h)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.42, minor_radius=0.018, major_segments=20, minor_segments=8, location=(x, y, 0.92)
    )
    rv = C.active_object
    rv.name = f"Rivet_{ang}"
    rv.rotation_euler = (0.0, 0.0, rad)
    assign(rv, truss_mat)
    smooth_obj(rv)
    parent_root(rv)

for ang in (0, 180):
    rad = _m.radians(ang)
    mid = 3.2
    x, y = mid * _m.cos(rad), mid * _m.sin(rad)
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.035, depth=3.4, location=(x, y, -0.28))
    p = C.active_object
    p.name = f"Pipe_{ang}"
    p.rotation_euler = (0.0, 1.5708, rad)
    assign(p, dark_mat)
    smooth_obj(p)
    parent_root(p)
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.028, depth=3.4, location=(x, y, -0.42))
    p2 = C.active_object
    p2.name = f"PipeB_{ang}"
    p2.rotation_euler = (0.0, 1.5708, rad)
    assign(p2, truss_mat)
    smooth_obj(p2)
    parent_root(p2)

for i, z in enumerate((0.4, 0.0, -0.4)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(1.36, 0.0, z))
    s = C.active_object
    s.name = f"Stripe_{i}"
    s.scale = (0.04, 0.55, 0.12)
    assign(s, accent_mat)
    parent_root(s)

# Antenna cluster near dish
for i, (dx, dy) in enumerate(((0.18, 0.12), (-0.16, 0.14), (0.05, -0.2))):
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.018, depth=0.55 + i * 0.12, location=(dx, dy, 4.55))
    a = C.active_object
    a.name = f"AntennaExtra_{i}"
    assign(a, truss_mat)
    parent_root(a)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.035, location=(dx, dy, 4.85 + i * 0.06))
    tip = C.active_object
    tip.name = f"AntennaExtra_Tip_{i}"
    assign(tip, accent_mat)
    parent_root(tip)

for side, x_sign in (("Pos", 1.0), ("Neg", -1.0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x_sign * 5.85, 0.0, 0.0))
    hx = C.active_object
    hx.name = f"Hinge_{side}"
    hx.scale = (0.22, 0.28, 0.18)
    assign(hx, dark_mat)
    smooth_obj(hx, 50)
    parent_root(hx)

# --- shading pass on main hull ---
for name in ("HabRing", "HubCore", "CargoModule", "CommDish", "HubCapTop", "HubCapBottom"):
    obj = D.objects.get(name)
    if obj:
        smooth_obj(obj, 35.0)

# --- lighting ---
old_sun = D.objects.get("SunKey")
if old_sun:
    D.objects.remove(old_sun, do_unlink=True)
sun_data = D.lights.new("SunKey", type="SUN")
sun_data.energy = 6.5
sun_data.color = (1.0, 0.96, 0.90)
if hasattr(sun_data, "angle"):
    sun_data.angle = _m.radians(1.6)
sun = D.objects.new("SunKey", sun_data)
sun.location = (18.0, -10.0, 16.0)
aim_at(sun, (0.0, 0.0, 0.2))
scene.collection.objects.link(sun)

fill = D.objects.get("Fill")
if fill and fill.data:
    fill.data.energy = 420.0
    fill.data.color = (0.55, 0.72, 1.0)
    if hasattr(fill.data, "size"):
        fill.data.size = 12.0
rim = D.objects.get("Rim")
if rim and rim.data:
    rim.data.energy = 380.0
    rim.data.color = (0.65, 0.82, 1.0)

world = D.worlds.get("World")
if world and world.use_nodes:
    for n in world.node_tree.nodes:
        if n.type == "BACKGROUND":
            n.inputs[1].default_value = 0.35

cam = D.objects.get("Camera")
if cam:
    cam.location = (13.2, -15.5, 3.4)
    aim_at(cam, (0.0, 0.0, 0.15))
    cam.data.lens = 50.0
    if hasattr(cam.data, "dof"):
        cam.data.dof.use_dof = False

# EEVEE Next has no bloom; skip compositor glare (Blender 5 default is star streaks)
eevee = getattr(scene, "eevee", None)
if eevee is not None and hasattr(eevee, "use_raytracing"):
    eevee.use_raytracing = True
scene.render.use_compositing = False

result = {"created": len(created), "windows": sum(1 for n in created if n.startswith("WinGlow_"))}
"""


def main() -> int:
    settings = get_settings()
    blend = settings.output_dir / "space_habitat" / "space_habitat.blend"
    if not blend.is_file():
        print("Missing blend:", blend)
        return 1
    print("Improving", blend)
    job = headless.run_job(
        settings,
        [
            {"type": "execute", "code": IMPROVE},
            {"type": "save_as", "path": str(blend), "compress": True},
        ],
        open_blend=str(blend),
    )
    print("ok:", job.ok)
    for step in job.responses:
        print(step.get("ok"), step.get("result") or step.get("error"))
    if not job.ok:
        print("STDOUT TAIL:\n", job.stdout[-4000:])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
