"""Starter scenes used by ``create_blend``.

Each template is bpy source executed in the namespace described in
``addon/blender_mcp_addon/exec_core.py``, so ``bpy``, ``mathutils`` and ``math``
are already bound.
"""

from __future__ import annotations

_CLEAR_EVERYTHING = """
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
for collection in list(bpy.data.collections):
    bpy.data.collections.remove(collection)
for block in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
    for item in list(block):
        if item.users == 0:
            block.remove(item)
"""

_AIM_HELPER = """
def aim_at(obj, target=(0.0, 0.0, 0.0)):
    direction = mathutils.Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
"""

_STUDIO = (
    _CLEAR_EVERYTHING
    + _AIM_HELPER
    + """
scene = bpy.context.scene

world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.05, 0.06, 1.0)
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
scene.world = world

bpy.ops.mesh.primitive_plane_add(size=40.0, location=(0.0, 0.0, 0.0))
floor = bpy.context.active_object
floor.name = "Floor"
floor_material = bpy.data.materials.new("FloorGrey")
floor_material.use_nodes = True
floor_material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (
    0.22, 0.22, 0.24, 1.0
)
floor_material.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.7
floor.data.materials.append(floor_material)

for name, location, energy, size in (
    ("Key", (4.0, -4.0, 5.0), 900.0, 4.0),
    ("Fill", (-5.0, -2.5, 3.0), 250.0, 5.0),
    ("Rim", (0.0, 5.0, 4.5), 500.0, 3.0),
):
    light_data = bpy.data.lights.new(name, type='AREA')
    light_data.energy = energy
    light_data.size = size
    light = bpy.data.objects.new(name, light_data)
    light.location = location
    aim_at(light)
    scene.collection.objects.link(light)

camera_data = bpy.data.cameras.new("Camera")
camera_data.lens = 50.0
camera = bpy.data.objects.new("Camera", camera_data)
camera.location = (7.36, -6.93, 4.96)
aim_at(camera, (0.0, 0.0, 0.6))
scene.collection.objects.link(camera)
scene.camera = camera

scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.film_transparent = False

result = {"template": "studio", "objects": [obj.name for obj in scene.objects]}
"""
)

_EMPTY = (
    _CLEAR_EVERYTHING
    + """
result = {"template": "empty", "objects": []}
"""
)

_DEFAULT = """
result = {"template": "default", "objects": [obj.name for obj in bpy.context.scene.objects]}
"""

_PRODUCT = (
    _CLEAR_EVERYTHING
    + _AIM_HELPER
    + """
scene = bpy.context.scene

world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.92, 0.93, 0.95, 1.0)
bg.inputs[1].default_value = 0.6
scene.world = world

# Seamless curved backdrop (large plane + subdivision for soft horizon)
bpy.ops.mesh.primitive_plane_add(size=20.0, location=(0.0, 4.0, 0.0))
backdrop = bpy.context.active_object
backdrop.name = "Backdrop"
backdrop.rotation_euler = (math.radians(85.0), 0.0, 0.0)
mat_back = bpy.data.materials.new("BackdropWhite")
mat_back.use_nodes = True
mat_back.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (
    0.95, 0.95, 0.96, 1.0
)
mat_back.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
backdrop.data.materials.append(mat_back)

bpy.ops.mesh.primitive_plane_add(size=20.0, location=(0.0, 0.0, 0.0))
floor = bpy.context.active_object
floor.name = "Floor"
floor.data.materials.append(mat_back)

for name, location, energy, size in (
    ("Key", (3.5, -3.5, 4.5), 700.0, 3.5),
    ("Fill", (-4.0, -2.0, 2.8), 220.0, 4.5),
    ("Rim", (0.0, 4.0, 3.5), 350.0, 2.5),
):
    light_data = bpy.data.lights.new(name, type='AREA')
    light_data.energy = energy
    light_data.size = size
    light = bpy.data.objects.new(name, light_data)
    light.location = location
    aim_at(light, (0.0, 0.0, 0.5))
    scene.collection.objects.link(light)

camera_data = bpy.data.cameras.new("Camera")
camera_data.lens = 85.0
camera = bpy.data.objects.new("Camera", camera_data)
camera.location = (4.5, -5.5, 2.8)
aim_at(camera, (0.0, 0.0, 0.5))
scene.collection.objects.link(camera)
scene.camera = camera

scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.film_transparent = False

result = {"template": "product", "objects": [obj.name for obj in scene.objects]}
"""
)

TEMPLATES: dict[str, dict[str, str]] = {
    "empty": {
        "description": "Nothing at all - no objects, no camera, no lights.",
        "code": _EMPTY,
    },
    "default": {
        "description": "Blender's own startup scene: cube, camera and one light.",
        "code": _DEFAULT,
    },
    "studio": {
        "description": (
            "Render-ready set: grey floor, three-point area lighting, a 50mm camera "
            "aimed at the origin and 1920x1080 output."
        ),
        "code": _STUDIO,
    },
    "product": {
        "description": (
            "Product-shot set: white seamless floor/backdrop, soft three-point lights, "
            "85mm camera framed on the origin."
        ),
        "code": _PRODUCT,
    },
}


def get_template(name: str) -> str:
    try:
        return TEMPLATES[name]["code"]
    except KeyError:
        raise ValueError(
            f"Unknown template {name!r}. Available: {', '.join(sorted(TEMPLATES))}"
        ) from None


def describe_templates() -> dict[str, str]:
    return {name: entry["description"] for name, entry in TEMPLATES.items()}
