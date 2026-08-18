"""Build a detailed modular space habitat .blend via headless Blender."""

from __future__ import annotations

from blender_mcp import headless
from blender_mcp.config import get_settings

SPACE_WORLD = r"""
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

scene = bpy.context.scene
world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
world.use_nodes = True
nt = world.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
outn = nt.nodes.new("ShaderNodeOutputWorld")
bg = nt.nodes.new("ShaderNodeBackground")
tex = nt.nodes.new("ShaderNodeTexNoise")
tex.inputs["Scale"].default_value = 220.0
tex.inputs["Detail"].default_value = 16.0
tex.inputs["Roughness"].default_value = 0.55
ramp = nt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].position = 0.86
ramp.color_ramp.elements[0].color = (0.003, 0.005, 0.012, 1)
ramp.color_ramp.elements[1].position = 0.97
ramp.color_ramp.elements[1].color = (0.95, 0.97, 1.0, 1)
nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
bg.inputs[1].default_value = 0.9
nt.links.new(bg.outputs["Background"], outn.inputs["Surface"])
scene.world = world


def aim_at(obj, target=(0.0, 0.0, 0.0)):
    direction = mathutils.Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


for name, loc, energy, size, color in (
    ("SunKey", (18.0, -12.0, 10.0), 1800.0, 6.0, (1.0, 0.95, 0.88)),
    ("Fill", (-14.0, -8.0, 4.0), 350.0, 10.0, (0.55, 0.7, 1.0)),
    ("Rim", (2.0, 16.0, 6.0), 700.0, 5.0, (0.7, 0.85, 1.0)),
):
    ld = bpy.data.lights.new(name, type="AREA")
    ld.energy = energy
    ld.size = size
    ld.color = color
    lo = bpy.data.objects.new(name, ld)
    lo.location = loc
    aim_at(lo, (0, 0, 0))
    scene.collection.objects.link(lo)

cam_data = bpy.data.cameras.new("Camera")
cam_data.lens = 55.0
cam = bpy.data.objects.new("Camera", cam_data)
cam.location = (12.8, -14.5, 6.8)
aim_at(cam, (0.0, 0.0, 0.3))
scene.collection.objects.link(cam)
scene.camera = cam
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
result = {"template": "space"}
"""

BUILD = r"""
import math as _m


def mat_principled(
    name,
    *,
    base=(0.5, 0.5, 0.5, 1),
    metallic=0.0,
    roughness=0.4,
    transmission=0.0,
    emission=None,
    emission_strength=0.0,
    coat=0.0,
):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    out = nt.nodes.get("Material Output") or nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    def seti(k, v):
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = v

    seti("Base Color", base)
    seti("Metallic", metallic)
    seti("Roughness", roughness)
    seti("Transmission Weight", transmission)
    seti("Coat Weight", coat)
    if emission is not None:
        seti("Emission Color", emission if len(emission) == 4 else (*emission, 1))
        seti("Emission Strength", emission_strength)
    return m


def assign(obj, material):
    if obj.data.materials:
        obj.data.materials.clear()
    obj.data.materials.append(material)


def bevel(obj, width=0.02, segments=3):
    mod = obj.modifiers.new("Bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"


hull = mat_principled(
    "HullMetal", base=(0.55, 0.58, 0.62, 1), metallic=1.0, roughness=0.28, coat=0.35
)
hull_dark = mat_principled(
    "HullDark", base=(0.12, 0.13, 0.15, 1), metallic=1.0, roughness=0.45
)
accent = mat_principled(
    "AccentOrange", base=(0.85, 0.35, 0.08, 1), metallic=0.15, roughness=0.4
)
panel = mat_principled(
    "SolarPanel", base=(0.02, 0.05, 0.18, 1), metallic=0.6, roughness=0.15
)
glass = mat_principled(
    "ObsGlass", base=(0.75, 0.9, 1.0, 1), metallic=0.0, roughness=0.05, transmission=1.0
)
interior_glow = mat_principled(
    "InteriorGlow",
    base=(1, 0.85, 0.55, 1),
    metallic=0.0,
    roughness=0.6,
    emission=(1.0, 0.75, 0.4),
    emission_strength=6.0,
)
truss_mat = mat_principled(
    "Truss", base=(0.72, 0.74, 0.78, 1), metallic=1.0, roughness=0.35
)
radiator = mat_principled(
    "Radiator", base=(0.85, 0.88, 0.92, 1), metallic=0.85, roughness=0.22
)
rubber = mat_principled(
    "DockSeal", base=(0.05, 0.05, 0.05, 1), metallic=0.0, roughness=0.9
)
gold = mat_principled(
    "AntennaGold", base=(0.85, 0.65, 0.2, 1), metallic=1.0, roughness=0.2
)

created = []

bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=1.35, depth=3.2, location=(0, 0, 0))
hub = C.active_object
hub.name = "HubCore"
assign(hub, hull)
bevel(hub, 0.04, 4)
created.append(hub.name)

bpy.ops.mesh.primitive_torus_add(
    major_radius=1.38, minor_radius=0.08, major_segments=64, minor_segments=16, location=(0, 0, 0)
)
band = C.active_object
band.name = "HubAccentBand"
assign(band, accent)
created.append(band.name)

for z, name in ((1.7, "HubCapTop"), (-1.7, "HubCapBottom")):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=1.15, depth=0.25, location=(0, 0, z))
    cap = C.active_object
    cap.name = name
    assign(cap, hull_dark)
    bevel(cap, 0.03, 3)
    created.append(cap.name)

for loc, rot, name in (
    ((0, 1.55, 0), (1.5708, 0, 0), "DockNorth"),
    ((0, -1.55, 0), (-1.5708, 0, 0), "DockSouth"),
    ((1.55, 0, 0), (0, 1.5708, 0), "DockEast"),
    ((-1.55, 0, 0), (0, -1.5708, 0), "DockWest"),
    ((0, 0, 1.95), (0, 0, 0), "DockZenith"),
):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.38, depth=0.55, location=loc)
    d = C.active_object
    d.name = name
    d.rotation_euler = rot
    assign(d, hull_dark)
    bevel(d, 0.015, 2)
    created.append(d.name)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.4, minor_radius=0.035, major_segments=32, minor_segments=12, location=loc
    )
    s = C.active_object
    s.name = name + "_Seal"
    s.rotation_euler = rot
    assign(s, rubber)
    created.append(s.name)

bpy.ops.mesh.primitive_torus_add(
    major_radius=5.5, minor_radius=0.85, major_segments=96, minor_segments=32, location=(0, 0, 0)
)
ring = C.active_object
ring.name = "HabRing"
assign(ring, hull)
bevel(ring, 0.03, 3)
created.append(ring.name)

for ang in range(0, 360, 45):
    rad = _m.radians(ang)
    x, y = 5.5 * _m.cos(rad), 5.5 * _m.sin(rad)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, 0))
    strip = C.active_object
    strip.name = f"RingPanel_{ang}"
    strip.scale = (0.55, 0.12, 0.55)
    strip.rotation_euler = (0, 0, rad)
    assign(strip, accent if ang % 90 == 0 else hull_dark)
    created.append(strip.name)

for ang in range(20, 360, 40):
    rad = _m.radians(ang)
    x, y = 6.25 * _m.cos(rad), 6.25 * _m.sin(rad)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=16, radius=0.28, depth=0.12, location=(x, y, 0.15)
    )
    w = C.active_object
    w.name = f"Window_{ang}"
    w.rotation_euler = (1.5708, 0, rad)
    assign(w, glass)
    created.append(w.name)
    x2, y2 = 6.05 * _m.cos(rad), 6.05 * _m.sin(rad)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=16, radius=0.22, depth=0.08, location=(x2, y2, 0.15)
    )
    g = C.active_object
    g.name = f"WindowGlow_{ang}"
    g.rotation_euler = (1.5708, 0, rad)
    assign(g, interior_glow)
    created.append(g.name)

for ang in (0, 90, 180, 270):
    rad = _m.radians(ang)
    mid = 3.2
    x, y = mid * _m.cos(rad), mid * _m.sin(rad)
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.12, depth=3.6, location=(x, y, 0))
    sp = C.active_object
    sp.name = f"Spoke_{ang}"
    sp.rotation_euler = (0, 1.5708, rad)
    assign(sp, truss_mat)
    bevel(sp, 0.01, 2)
    created.append(sp.name)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=12, radius=0.05, depth=3.6, location=(x, y, 0.35)
    )
    sp2 = C.active_object
    sp2.name = f"SpokeThin_{ang}"
    sp2.rotation_euler = (0, 1.5708, rad)
    assign(sp2, truss_mat)
    created.append(sp2.name)


def make_solar(side, x_sign):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=12, radius=0.08, depth=4.5, location=(x_sign * 8.2, 0, 0)
    )
    boom = C.active_object
    boom.name = f"SolarBoom_{side}"
    boom.rotation_euler = (0, 1.5708, 0)
    assign(boom, truss_mat)
    created.append(boom.name)
    for i, oy in enumerate((-1.6, 0.0, 1.6)):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x_sign * (6.5 + i * 1.15), oy, 0.0))
        p = C.active_object
        p.name = f"Solar_{side}_{i}_{oy}"
        p.scale = (0.5, 1.35, 0.035)
        assign(p, panel)
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x_sign * (6.5 + i * 1.15), oy, 0.0))
        f = C.active_object
        f.name = f"SolarFrame_{side}_{i}_{oy}"
        f.scale = (0.55, 1.4, 0.02)
        assign(f, hull_dark)
        created.append(p.name)
        created.append(f.name)


make_solar("Pos", 1)
make_solar("Neg", -1)

for ang in (45, 135, 225, 315):
    rad = _m.radians(ang)
    x, y = 5.5 * _m.cos(rad), 5.5 * _m.sin(rad)
    for z_off, suffix in ((1.4, "Up"), (-1.4, "Dn")):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z_off))
        r = C.active_object
        r.name = f"Radiator_{ang}_{suffix}"
        r.scale = (0.08, 0.9, 0.7)
        r.rotation_euler = (0, 0, rad)
        assign(r, radiator)
        created.append(r.name)

bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.06, depth=2.2, location=(0, 0, 3.1))
mast = C.active_object
mast.name = "CommMast"
assign(mast, truss_mat)
created.append(mast.name)

bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.85, location=(0, 0, 4.3))
dish = C.active_object
dish.name = "CommDish"
dish.scale = (1.0, 1.0, 0.22)
assign(dish, gold)
created.append(dish.name)

bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.03, depth=0.7, location=(0, 0, 4.55))
feed = C.active_object
feed.name = "CommFeed"
assign(feed, hull_dark)
created.append(feed.name)

bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.55, depth=2.0, location=(0, -3.2, 0))
cargo = C.active_object
cargo.name = "CargoModule"
cargo.rotation_euler = (1.5708, 0, 0)
assign(cargo, hull)
bevel(cargo, 0.03, 3)
created.append(cargo.name)

bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.42, depth=0.3, location=(0, -4.25, 0))
cargo_cap = C.active_object
cargo_cap.name = "CargoCap"
cargo_cap.rotation_euler = (1.5708, 0, 0)
assign(cargo_cap, accent)
created.append(cargo_cap.name)

nav_red = mat_principled(
    "NavRed", base=(1, 0, 0, 1), emission=(1, 0.05, 0.02), emission_strength=25.0
)
nav_green = mat_principled(
    "NavGreen", base=(0, 1, 0, 1), emission=(0.05, 1, 0.1), emission_strength=25.0
)
nav_white = mat_principled(
    "NavWhite", base=(1, 1, 1, 1), emission=(1, 1, 1), emission_strength=18.0
)
for loc, mat, name in (
    ((6.4, 0, 0.2), nav_red, "NavPort"),
    ((-6.4, 0, 0.2), nav_green, "NavStarboard"),
    ((0, 0, 5.0), nav_white, "NavBeacon"),
):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.08, location=loc)
    n = C.active_object
    n.name = name
    assign(n, mat)
    created.append(n.name)

bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 0))
root = C.active_object
root.name = "SpaceHabitat"
for name in created:
    obj = D.objects.get(name)
    if obj:
        obj.parent = root

result = {"objects": len(created), "sample": created[:10]}
"""


def main() -> int:
    settings = get_settings()
    out = settings.output_dir / "space_habitat"
    out.mkdir(parents=True, exist_ok=True)
    blend = out / "space_habitat.blend"

    print("Building habitat...")
    job = headless.run_job(
        settings,
        [
            {"type": "execute", "code": SPACE_WORLD},
            {"type": "execute", "code": BUILD},
            {"type": "save_as", "path": str(blend), "compress": True},
        ],
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
