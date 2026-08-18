"""Polish pass on the space habitat: smooth shading, materials, camera."""

from __future__ import annotations

from blender_mcp import headless
from blender_mcp.config import get_settings

POLISH = r"""
import math as _m

# Smooth shade everything mesh-like
for obj in list(D.objects):
    if obj.type != "MESH":
        continue
    C.view_layer.objects.active = obj
    obj.select_set(True)
    try:
        bpy.ops.object.shade_smooth()
    except Exception:
        pass
    obj.select_set(False)
    # auto smooth via attribute / modifier for Blender 4.1+
    mesh = obj.data
    if hasattr(mesh, "use_auto_smooth"):
        mesh.use_auto_smooth = True
        mesh.auto_smooth_angle = _m.radians(35)
    else:
        # Blender 5: Smooth by Angle modifier
        if "SmoothByAngle" not in obj.modifiers:
            mod = obj.modifiers.new("SmoothByAngle", "NODES")
            # fallback: edge split-like via bevel already present; set sharp not needed

# Lighten hull materials + add subtle noise roughness where possible
def tweak(name, **kwargs):
    m = D.materials.get(name)
    if not m or not m.use_nodes:
        return
    bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if not bsdf:
        return
    for k, v in kwargs.items():
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = v

tweak("HullMetal", **{"Base Color": (0.62, 0.66, 0.72, 1), "Roughness": 0.32, "Metallic": 1.0, "Coat Weight": 0.4})
tweak("HullDark", **{"Base Color": (0.22, 0.24, 0.28, 1), "Roughness": 0.5, "Metallic": 1.0})
tweak("Truss", **{"Base Color": (0.78, 0.8, 0.84, 1), "Roughness": 0.3})
tweak("Radiator", **{"Base Color": (0.9, 0.92, 0.95, 1), "Roughness": 0.18})
tweak("SolarPanel", **{"Base Color": (0.01, 0.08, 0.28, 1), "Roughness": 0.12, "Metallic": 0.75})
tweak("InteriorGlow", **{"Emission Strength": 14.0, "Emission Color": (1.0, 0.7, 0.35, 1)})
tweak("ObsGlass", **{"Roughness": 0.02, "Transmission Weight": 1.0})
tweak("AccentOrange", **{"Base Color": (1.0, 0.42, 0.08, 1), "Emission Color": (1.0, 0.35, 0.05, 1), "Emission Strength": 0.8})

# Subdivision on main forms
for name in ("HabRing", "HubCore", "CommDish", "CargoModule"):
    obj = D.objects.get(name)
    if not obj:
        continue
    if "Subsurf" not in obj.modifiers:
        mod = obj.modifiers.new("Subsurf", "SUBSURF")
        mod.levels = 1
        mod.render_levels = 2

# Extra ring greebles: cable conduits along spokes
created = []
for ang in (45, 135, 225, 315):
    rad = _m.radians(ang)
    x, y = 3.2 * _m.cos(rad), 3.2 * _m.sin(rad)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.22, minor_radius=0.04, major_segments=24, minor_segments=10, location=(x, y, 0)
    )
    node = C.active_object
    node.name = f"SpokeNode_{ang}"
    mat = D.materials.get("AccentOrange")
    if mat:
        node.data.materials.clear()
        node.data.materials.append(mat)
    created.append(node.name)

# Module boxes on ring (crew modules)
for i, ang in enumerate((10, 100, 190, 280)):
    rad = _m.radians(ang)
    x, y = 5.5 * _m.cos(rad), 5.5 * _m.sin(rad)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, 0.95))
    box = C.active_object
    box.name = f"CrewModule_{ang}"
    box.scale = (0.55, 0.7, 0.35)
    box.rotation_euler = (0, 0, rad)
    mat = D.materials.get("HullDark")
    if mat:
        box.data.materials.clear()
        box.data.materials.append(mat)
    created.append(box.name)
    # small window on module
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=12, radius=0.12, depth=0.08, location=(x * 1.08, y * 1.08, 0.95)
    )
    win = C.active_object
    win.name = f"CrewWindow_{ang}"
    win.rotation_euler = (1.5708, 0, rad)
    gmat = D.materials.get("InteriorGlow")
    if gmat:
        win.data.materials.clear()
        win.data.materials.append(gmat)
    created.append(win.name)

root = D.objects.get("SpaceHabitat")
for name in created:
    obj = D.objects.get(name)
    if obj and root:
        obj.parent = root
        try:
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            C.view_layer.objects.active = obj
            bpy.ops.object.shade_smooth()
        except Exception:
            pass

# Better camera: show solar wings + dish
cam = D.objects.get("Camera")
if cam:
    cam.location = (15.5, -11.5, 8.2)
    direction = mathutils.Vector((0.5, 0.0, 0.4)) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    if cam.data:
        cam.data.lens = 50.0

# Stronger sun for metal catchlights
sun = D.objects.get("SunKey")
if sun and sun.data:
    sun.data.energy = 2400.0
rim = D.objects.get("Rim")
if rim and rim.data:
    rim.data.energy = 900.0

# World a bit brighter so metals aren't crushed black
world = D.worlds.get("World")
if world and world.use_nodes:
    for n in world.node_tree.nodes:
        if n.type == "BACKGROUND":
            n.inputs[1].default_value = 1.2

result = {"polished": True, "extra": created}
"""


def main() -> int:
    settings = get_settings()
    blend = settings.output_dir / "space_habitat" / "space_habitat.blend"
    job = headless.run_job(
        settings,
        [
            {"type": "execute", "code": POLISH},
            {"type": "save_as", "path": str(blend), "compress": True},
        ],
        open_blend=str(blend),
    )
    print("ok:", job.ok)
    for step in job.responses:
        print(step.get("ok"), step.get("result") or step.get("error"))
    if not job.ok:
        print(job.stdout[-3000:])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
