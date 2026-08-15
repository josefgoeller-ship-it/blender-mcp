"""The operations the MCP server can ask Blender to perform.

Every handler runs on Blender's main thread and returns a plain dict. Headless
jobs call :func:`dispatch` directly; the live addon calls it from a timer.
"""

from __future__ import annotations

import os

import bpy

from . import exec_core

MAX_OBJECTS_REPORTED = 300

# Friendly names, because the render engine identifiers have been renamed more
# than once across Blender releases. Each entry is tried in order.
_ENGINE_ALIASES = {
    "EEVEE": ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"),
    "CYCLES": ("CYCLES",),
    "WORKBENCH": ("BLENDER_WORKBENCH",),
}


def available_engines() -> list[str]:
    """Engines this build can actually select.

    The RNA enum only lists the built-ins, so add-on engines such as Cycles have to
    be picked up from the registered RenderEngine subclasses as well.
    """
    prop = bpy.types.RenderSettings.bl_rna.properties["engine"]
    identifiers = [item.identifier for item in prop.enum_items]
    for subclass in bpy.types.RenderEngine.__subclasses__():
        identifier = getattr(subclass, "bl_idname", None)
        if identifier and identifier not in identifiers:
            identifiers.append(identifier)
    return identifiers


def set_engine(scene: bpy.types.Scene, name: str) -> str:
    """Select a render engine by friendly name, tolerating identifier renames across releases."""
    requested = name.strip().upper()
    for candidate in (requested, *_ENGINE_ALIASES.get(requested, ())):
        try:
            scene.render.engine = candidate
        except TypeError:
            continue
        return scene.render.engine
    raise ValueError(
        f"Could not select render engine {name!r}; this build offers {available_engines()}"
    )


def _ensure_parent_dir(path: str) -> str:
    absolute = os.path.abspath(bpy.path.abspath(path))
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    return absolute


def _object_summary(obj: bpy.types.Object) -> dict:
    summary = {
        "name": obj.name,
        "type": obj.type,
        "location": [round(value, 6) for value in obj.location],
        "rotation_euler": [round(value, 6) for value in obj.rotation_euler],
        "scale": [round(value, 6) for value in obj.scale],
        "dimensions": [round(value, 6) for value in obj.dimensions],
        "visible": not obj.hide_render,
        "collections": [collection.name for collection in obj.users_collection],
    }
    if obj.material_slots:
        summary["materials"] = [slot.material.name for slot in obj.material_slots if slot.material]
    if obj.modifiers:
        summary["modifiers"] = [{"name": mod.name, "type": mod.type} for mod in obj.modifiers]
    if obj.type == "MESH" and obj.data is not None:
        summary["mesh"] = {
            "vertices": len(obj.data.vertices),
            "polygons": len(obj.data.polygons),
        }
    if obj.type == "CAMERA" and obj.data is not None:
        summary["camera"] = {"lens": obj.data.lens, "type": obj.data.type}
    if obj.type == "LIGHT" and obj.data is not None:
        summary["light"] = {"type": obj.data.type, "energy": obj.data.energy}
    return summary


def scene_info(include_objects: bool = True) -> dict:
    scene = bpy.context.scene
    render = scene.render
    info = {
        "blend_file": bpy.data.filepath or None,
        "blender_version": bpy.app.version_string,
        "scene": scene.name,
        "engine": render.engine,
        "available_engines": available_engines(),
        "resolution": [render.resolution_x, render.resolution_y, render.resolution_percentage],
        "frame_range": [scene.frame_start, scene.frame_end, scene.frame_current],
        "fps": render.fps,
        "active_camera": scene.camera.name if scene.camera else None,
        "world": scene.world.name if scene.world else None,
        "counts": {
            "objects": len(bpy.data.objects),
            "meshes": len(bpy.data.meshes),
            "materials": len(bpy.data.materials),
            "collections": len(bpy.data.collections),
            "images": len(bpy.data.images),
        },
        "materials": [material.name for material in bpy.data.materials],
        "collections": [collection.name for collection in bpy.data.collections],
    }
    if include_objects:
        objects = list(scene.objects)
        info["objects"] = [_object_summary(obj) for obj in objects[:MAX_OBJECTS_REPORTED]]
        if len(objects) > MAX_OBJECTS_REPORTED:
            info["objects_truncated"] = len(objects) - MAX_OBJECTS_REPORTED
    return info


def save_as(path: str, compress: bool = True) -> dict:
    target = _ensure_parent_dir(path)
    bpy.ops.wm.save_as_mainfile(filepath=target, compress=compress, copy=False)
    return {"path": target, "bytes": os.path.getsize(target)}


def open_blend(path: str) -> dict:
    target = os.path.abspath(bpy.path.abspath(path))
    if not os.path.isfile(target):
        raise FileNotFoundError(f"No .blend file at {target}")
    bpy.ops.wm.open_mainfile(filepath=target)
    return {"path": target}


def render_still(
    path: str,
    engine: str | None = None,
    samples: int | None = None,
    resolution: list | None = None,
    transparent: bool = False,
    frame: int | None = None,
) -> dict:
    scene = bpy.context.scene
    if scene.camera is None:
        raise RuntimeError("The scene has no active camera, so there is nothing to render")

    if engine:
        set_engine(scene, engine)
    if resolution:
        scene.render.resolution_x = int(resolution[0])
        scene.render.resolution_y = int(resolution[1])
        scene.render.resolution_percentage = 100
    if frame is not None:
        scene.frame_set(int(frame))
    if samples is not None:
        if scene.render.engine == "CYCLES":
            scene.cycles.samples = int(samples)
        elif hasattr(scene, "eevee"):
            scene.eevee.taa_render_samples = int(samples)
    scene.render.film_transparent = bool(transparent)

    target = _ensure_parent_dir(path)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = target
    bpy.ops.render.render(write_still=True)

    # Blender appends the format extension when the path has none.
    if not os.path.isfile(target) and os.path.isfile(target + ".png"):
        target += ".png"
    return {
        "path": target,
        "bytes": os.path.getsize(target),
        "engine": scene.render.engine,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
    }


def viewport_screenshot(path: str) -> dict:
    """OpenGL render of the first 3D viewport. Only meaningful with a UI open."""
    area = next(
        (
            area
            for window in bpy.context.window_manager.windows
            for area in window.screen.areas
            if area.type == "VIEW_3D"
        ),
        None,
    )
    if area is None:
        raise RuntimeError("No 3D viewport is open, so there is nothing to capture")

    scene = bpy.context.scene
    target = _ensure_parent_dir(path)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = target

    window = next(
        window
        for window in bpy.context.window_manager.windows
        if area in tuple(window.screen.areas)
    )
    region = next(region for region in area.regions if region.type == "WINDOW")
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.render.opengl(write_still=True, view_context=True)

    if not os.path.isfile(target) and os.path.isfile(target + ".png"):
        target += ".png"
    return {"path": target, "bytes": os.path.getsize(target)}


_DEFAULT_PREVIEW_ANGLES = (
    {"name": "front", "yaw": 0.0, "pitch": 15.0},
    {"name": "three_quarter", "yaw": 45.0, "pitch": 20.0},
    {"name": "side", "yaw": 90.0, "pitch": 10.0},
    {"name": "top", "yaw": 30.0, "pitch": 75.0},
)


def _scene_center_and_radius() -> tuple[list[float], float]:
    import mathutils

    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        return [0.0, 0.0, 0.5], 2.5

    mins = [1e9, 1e9, 1e9]
    maxs = [-1e9, -1e9, -1e9]
    for obj in meshes:
        for corner in obj.bound_box:
            world = obj.matrix_world @ mathutils.Vector(corner)
            for i in range(3):
                mins[i] = min(mins[i], world[i])
                maxs[i] = max(maxs[i], world[i])
    center = [(mins[i] + maxs[i]) * 0.5 for i in range(3)]
    extent = mathutils.Vector((maxs[0] - mins[0], maxs[1] - mins[1], maxs[2] - mins[2]))
    radius = max(extent.length * 0.5, 0.5)
    return center, float(radius)


def preview_views(
    output_dir: str,
    angles: list | None = None,
    width: int = 480,
    height: int = 270,
    samples: int = 16,
    engine: str = "EEVEE",
    distance_factor: float = 2.8,
) -> dict:
    """Orbit a temporary camera and render several EEVEE preview stills."""
    import math

    import mathutils

    scene = bpy.context.scene
    center, radius = _scene_center_and_radius()
    center_v = mathutils.Vector(center)
    distance = max(radius * distance_factor, 1.5)

    original_camera = scene.camera
    original_engine = scene.render.engine
    original_res = (
        scene.render.resolution_x,
        scene.render.resolution_y,
        scene.render.resolution_percentage,
    )

    cam_data = bpy.data.cameras.new("MCP_PreviewCam")
    cam_data.lens = 50.0
    cam_obj = bpy.data.objects.new("MCP_PreviewCam", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    views = []
    chosen = angles or list(_DEFAULT_PREVIEW_ANGLES)
    try:
        for entry in chosen:
            if isinstance(entry, str):
                named = next((a for a in _DEFAULT_PREVIEW_ANGLES if a["name"] == entry), None)
                if named is None:
                    raise ValueError(f"Unknown angle name {entry!r}")
                entry = named
            name = entry.get("name", "view")
            yaw = math.radians(float(entry.get("yaw", 0.0)))
            pitch = math.radians(float(entry.get("pitch", 15.0)))
            offset = mathutils.Vector(
                (
                    distance * math.cos(pitch) * math.sin(yaw),
                    -distance * math.cos(pitch) * math.cos(yaw),
                    distance * math.sin(pitch),
                )
            )
            cam_obj.location = center_v + offset
            direction = center_v - cam_obj.location
            cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

            path = os.path.join(output_dir, f"{name}.png")
            still = render_still(
                path,
                engine=engine,
                samples=samples,
                resolution=[width, height],
            )
            views.append({"name": name, **still})
    finally:
        scene.camera = original_camera
        scene.render.engine = original_engine
        scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = (
            original_res
        )
        bpy.data.objects.remove(cam_obj, do_unlink=True)
        bpy.data.cameras.remove(cam_data)

    return {"views": views, "center": center, "radius": radius}


def reset_scene(keep_startup: bool = True) -> dict:
    """Back to a clean file: either the factory startup scene or a truly empty one."""
    bpy.ops.wm.read_homefile(use_empty=not keep_startup, use_factory_startup=True)
    return scene_info(include_objects=False)


def dispatch(message: dict) -> dict:
    """Route one request to its handler and wrap the outcome in a uniform envelope."""
    kind = message.get("type")
    try:
        if kind == "ping":
            return _ok(
                {
                    "blender_version": bpy.app.version_string,
                    "background": bpy.app.background,
                    "blend_file": bpy.data.filepath or None,
                }
            )
        if kind == "execute":
            # Passed through untouched: run_code already reports its own success,
            # captured output and traceback in the same envelope shape.
            return exec_core.run_code(message["code"])
        if kind == "scene_info":
            return _ok(scene_info(message.get("include_objects", True)))
        if kind == "save_as":
            return _ok(save_as(message["path"], message.get("compress", True)))
        if kind == "open":
            return _ok(open_blend(message["path"]))
        if kind == "render":
            return _ok(
                render_still(
                    message["path"],
                    engine=message.get("engine"),
                    samples=message.get("samples"),
                    resolution=message.get("resolution"),
                    transparent=message.get("transparent", False),
                    frame=message.get("frame"),
                )
            )
        if kind == "screenshot":
            return _ok(viewport_screenshot(message["path"]))
        if kind == "preview_views":
            return _ok(
                preview_views(
                    message["output_dir"],
                    angles=message.get("angles"),
                    width=message.get("width", 480),
                    height=message.get("height", 270),
                    samples=message.get("samples", 16),
                    engine=message.get("engine", "EEVEE"),
                    distance_factor=message.get("distance_factor", 2.8),
                )
            )
        if kind == "reset":
            return _ok(reset_scene(message.get("keep_startup", True)))
        return {"ok": False, "error": f"Unknown request type {kind!r}"}
    except Exception:
        return {"ok": False, "error": _traceback()}


def _ok(result: object) -> dict:
    return {"ok": True, "result": exec_core.to_jsonable(result)}


def _traceback() -> str:
    import traceback

    return exec_core._clip(traceback.format_exc(), 8_000)
