"""Procedural material presets applied inside Blender via bpy."""

from __future__ import annotations

# Each preset is bpy source that expects ``obj_name`` and optional ``color`` in the namespace.
# It binds ``result`` to a short summary.

_APPLY_HEADER = """
obj = bpy.data.objects.get(obj_name)
if obj is None:
    raise ValueError(f"No object named {obj_name!r}")
if obj.type != "MESH":
    raise ValueError(f"Object {obj_name!r} is {obj.type}, not MESH")

mat_name = f"{preset_name}_{obj_name}"
material = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
material.use_nodes = True
nodes = material.node_tree.nodes
links = material.node_tree.links
for node in list(nodes):
    if node.type != "OUTPUT_MATERIAL":
        nodes.remove(node)
output = nodes.get("Material Output") or nodes.new("ShaderNodeOutputMaterial")
bsdf = nodes.new("ShaderNodeBsdfPrincipled")
links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

def set_input(name, value):
    socket = bsdf.inputs.get(name)
    if socket is not None:
        socket.default_value = value

base = list(color) + [1.0] if len(color) == 3 else list(color)
"""

PRESETS: dict[str, dict[str, str]] = {
    "metal": {
        "description": "Polished metal. Optional color as RGB 0-1.",
        "code": _APPLY_HEADER
        + """
set_input("Base Color", base)
set_input("Metallic", 1.0)
set_input("Roughness", 0.25)
obj.data.materials.clear()
obj.data.materials.append(material)
result = {"object": obj.name, "material": material.name, "preset": "metal"}
""",
    },
    "plastic": {
        "description": "Hard plastic / painted surface.",
        "code": _APPLY_HEADER
        + """
set_input("Base Color", base)
set_input("Metallic", 0.0)
set_input("Roughness", 0.35)
set_input("Specular IOR Level", 0.5)
obj.data.materials.clear()
obj.data.materials.append(material)
result = {"object": obj.name, "material": material.name, "preset": "plastic"}
""",
    },
    "rubber": {
        "description": "Matte rubber / soft soft-touch surface.",
        "code": _APPLY_HEADER
        + """
set_input("Base Color", base)
set_input("Metallic", 0.0)
set_input("Roughness", 0.85)
obj.data.materials.clear()
obj.data.materials.append(material)
result = {"object": obj.name, "material": material.name, "preset": "rubber"}
""",
    },
    "glass": {
        "description": "Clear glass. Color tints the transmission.",
        "code": _APPLY_HEADER
        + """
set_input("Base Color", (1.0, 1.0, 1.0, 1.0))
set_input("Metallic", 0.0)
set_input("Roughness", 0.05)
set_input("Transmission Weight", 1.0)
set_input("IOR", 1.45)
if "Transmission Color" in bsdf.inputs:
    set_input("Transmission Color", base)
obj.data.materials.clear()
obj.data.materials.append(material)
result = {"object": obj.name, "material": material.name, "preset": "glass"}
""",
    },
    "wood": {
        "description": "Simple procedural wood (noise-based).",
        "code": _APPLY_HEADER
        + """
tex_coord = nodes.new("ShaderNodeTexCoord")
mapping = nodes.new("ShaderNodeMapping")
noise = nodes.new("ShaderNodeTexNoise")
noise.inputs["Scale"].default_value = 12.0
noise.inputs["Detail"].default_value = 8.0
ramp = nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].color = (0.22, 0.12, 0.05, 1.0)
ramp.color_ramp.elements[1].color = base
links.new(tex_coord.outputs["Object"], mapping.inputs["Vector"])
links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
set_input("Metallic", 0.0)
set_input("Roughness", 0.55)
obj.data.materials.clear()
obj.data.materials.append(material)
result = {"object": obj.name, "material": material.name, "preset": "wood"}
""",
    },
}

DEFAULT_COLORS = {
    "metal": (0.72, 0.45, 0.20),
    "plastic": (0.15, 0.45, 0.85),
    "rubber": (0.08, 0.08, 0.08),
    "glass": (0.85, 0.95, 1.0),
    "wood": (0.55, 0.32, 0.14),
}


def describe_presets() -> dict[str, str]:
    return {name: entry["description"] for name, entry in PRESETS.items()}


def build_apply_script(object_name: str, preset: str, color: list[float] | None = None) -> str:
    if preset not in PRESETS:
        raise ValueError(
            f"Unknown material preset {preset!r}. Available: {', '.join(sorted(PRESETS))}"
        )
    rgb = color if color is not None else list(DEFAULT_COLORS[preset])
    if len(rgb) not in (3, 4):
        raise ValueError("color must be RGB or RGBA floats in 0-1")
    prelude = f"obj_name = {object_name!r}\npreset_name = {preset!r}\ncolor = {tuple(rgb)!r}\n"
    return prelude + PRESETS[preset]["code"]
