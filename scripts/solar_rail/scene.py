"""Twisted roller-coaster rail with a solar-panel bogie.

The centerline is straight. The cross-section rolls one full turn from start to
end, and the bogie is fixed to that local frame. The photovoltaic face points
along local +Z, so it faces the zenith at both ends and the ground in the middle.
"""

from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

LENGTH = 30.0
HEIGHT = 5.6
GAUGE = 1.15
RAIL_R = 0.064
WHEEL_R = 0.20
FLANGE_R = 0.228
PANEL_Z = 1.16
TWIST = math.tau
FRAMES = 192
FPS = 24

# Solids only. Rail-head clips sit below this box.
WAGON_AABB = ((-1.85, 1.85), (-0.98, 0.98), (0.08, 1.36))


def smoothstep(u: float) -> float:
    return u * u * (3.0 - 2.0 * u)


def clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.lights,
        bpy.data.cameras,
    ):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)


def collection(name: str) -> bpy.types.Collection:
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def set_input(node, names: tuple[str, ...], value) -> None:
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            socket.default_value = value
            return


def principled(name, color, metallic=0.0, roughness=0.5, specular=0.5, coat=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    set_input(bsdf, ("Base Color",), (*color, 1.0))
    set_input(bsdf, ("Metallic",), metallic)
    set_input(bsdf, ("Roughness",), roughness)
    set_input(bsdf, ("Specular IOR Level", "Specular"), specular)
    set_input(bsdf, ("Coat Weight",), coat)
    return mat


def cell_material():
    """Matte navy cells with a fat silver grid. Low coat so the sky does not silver the face."""
    mat = principled("PVCells", (0.01, 0.03, 0.07), metallic=0.04, roughness=0.55, specular=0.18, coat=0.0)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    brick = mat.node_tree.nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.5
    brick.offset_frequency = 2
    set_input(brick, ("Color1",), (0.008, 0.025, 0.07, 1.0))
    set_input(brick, ("Color2",), (0.02, 0.055, 0.13, 1.0))
    set_input(brick, ("Mortar",), (0.90, 0.93, 0.96, 1.0))
    set_input(brick, ("Scale",), 3.2)
    set_input(brick, ("Mortar Size",), 0.045)
    set_input(brick, ("Mortar Smooth",), 0.05)
    set_input(brick, ("Brick Width",), 0.5)
    set_input(brick, ("Row Height",), 0.28)
    mat.node_tree.links.new(brick.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def emission(name, color, strength):
    mat = principled(name, (0.0, 0.0, 0.0), roughness=1.0)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    set_input(bsdf, ("Emission Color",), (*color, 1.0))
    set_input(bsdf, ("Emission Strength",), strength)
    return mat


def new_object(name, data, coll, parent=None, location=(0.0, 0.0, 0.0)):
    obj = bpy.data.objects.new(name, data)
    coll.objects.link(obj)
    obj.rotation_mode = "XYZ"
    if parent is not None:
        obj.parent = parent
        obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.location = location
    return obj


def box_mesh(name, size):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Diagonal((*size, 1.0)))
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def link_box(name, size, mat, coll, parent=None, location=(0.0, 0.0, 0.0), mesh=None):
    data = mesh if mesh is not None else box_mesh(name, size)
    obj = new_object(name, data, coll, parent=parent, location=location)
    if mat is not None and len(obj.data.materials) == 0:
        obj.data.materials.append(mat)
    elif mat is not None and obj.material_slots and obj.material_slots[0].material is None:
        obj.material_slots[0].material = mat
    return obj


LEAD = 2.4


def roll_at_x(x: float) -> float:
    """Flat under the wagon at both ends, 180° at mid, 360° at the end.

    Smoothstep keeps the rail tangent horizontal across the wheelbase when the
    bogie is parked at either end, and still locks the roll to position.
    """
    if x <= 0.0:
        return 0.0
    if x >= LENGTH:
        return TWIST
    u = x / LENGTH
    eased = u * u * (3.0 - 2.0 * u)
    return TWIST * eased


def frame_x(x: float) -> Matrix:
    return Matrix.Translation((x, 0.0, HEIGHT)) @ Matrix.Rotation(roll_at_x(x), 4, "X")


def frame(t: float) -> Matrix:
    return frame_x(LENGTH * t)


def rail_point(t: float, side: float) -> Vector:
    return frame(t) @ Vector((0.0, side * GAUGE * 0.5, 0.0))


def rail_at_x(x: float, side: float) -> Vector:
    return frame_x(x) @ Vector((0.0, side * GAUGE * 0.5, 0.0))


def look_at(obj, target):
    obj.rotation_mode = "XYZ"
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_cone(bm, p0, p1, radius, segments=10):
    start = Vector(p0)
    end = Vector(p1)
    direction = end - start
    length = direction.length
    if length < 1e-5:
        return
    matrix = Matrix.Translation((start + end) * 0.5) @ direction.to_track_quat("Z", "Y").to_matrix().to_4x4()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        segments=segments,
        radius1=radius,
        radius2=radius,
        depth=length,
        matrix=matrix,
    )


def tube_curve(name, points, radius, mat, coll):
    curve = bpy.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = radius
    curve.bevel_resolution = 6
    curve.use_fill_caps = True
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, co in zip(spline.points, points):
        point.co = (co[0], co[1], co[2], 1.0)
    obj = new_object(name, curve, coll)
    obj.data.materials.append(mat)
    return obj


def build_world(scene):
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    for node in list(nodes):
        nodes.remove(node)
    out = nodes.new("ShaderNodeOutputWorld")
    bg = nodes.new("ShaderNodeBackground")
    coord = nodes.new("ShaderNodeTexCoord")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.62, 0.70, 0.78, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.13, 0.28, 0.52, 1.0)
    links.new(coord.outputs["Window"], sep.inputs["Vector"])
    links.new(sep.outputs["Y"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.72
    links.new(bg.outputs["Background"], out.inputs["Surface"])
    scene.world = world


def build_environment(coll, concrete, earth):
    link_box("Ground", (420.0, 420.0, 12.0), earth, coll, location=(LENGTH * 0.5, 0.0, -6.0))
    link_box(
        "TrackBed",
        (LENGTH + 8.0, 5.4, 0.05),
        concrete,
        coll,
        location=(LENGTH * 0.5, 0.0, 0.025),
    )


def build_rails(coll, steel, tie_mat):
    samples = 240
    span = LENGTH + 2.0 * LEAD
    left = []
    right = []
    for i in range(samples + 1):
        x = -LEAD + span * i / samples
        right.append(rail_at_x(x, 1.0))
        left.append(rail_at_x(x, -1.0))
    tube_curve("RailRight", right, RAIL_R, steel, coll)
    tube_curve("RailLeft", left, RAIL_R, steel, coll)

    # Keep ties between the tubes, and out of the wheel stations at the three poses.
    wheel_x = []
    for origin in (0.0, LENGTH * 0.5, LENGTH):
        wheel_x.extend((origin - 0.46, origin + 0.46))
    mesh = bpy.data.meshes.new("Crossties")
    bm = bmesh.new()
    tie_scale = Matrix.Diagonal((0.08, GAUGE * 0.62, 0.035, 1.0))
    x = -LEAD
    while x <= LENGTH + LEAD + 1e-6:
        if all(abs(x - station) > 0.34 for station in wheel_x):
            matrix = frame_x(x) @ Matrix.Translation((0.0, 0.0, -0.01)) @ tie_scale
            bmesh.ops.create_cube(bm, size=1.0, matrix=matrix)
        x += 0.55
    bm.to_mesh(mesh)
    bm.free()
    obj = new_object("Crossties", mesh, coll)
    obj.data.materials.append(tie_mat)


def support_collision(p0, p1, radius, tag, hits):
    start = Vector(p0)
    end = Vector(p1)
    steps = 14
    for i in range(steps + 1):
        point = start.lerp(end, i / steps)
        if point.x < -1.6 or point.x > LENGTH + 1.6:
            continue
        for offset in (-1.2, -0.6, 0.0, 0.6, 1.2):
            center_x = point.x + offset
            if center_x < 0.0 or center_x > LENGTH:
                continue
            local = frame(center_x / LENGTH).inverted() @ point
            pad = radius + 0.06
            if (
                WAGON_AABB[0][0] - pad <= local.x <= WAGON_AABB[0][1] + pad
                and WAGON_AABB[1][0] - pad <= local.y <= WAGON_AABB[1][1] + pad
                and WAGON_AABB[2][0] - pad <= local.z <= WAGON_AABB[2][1] + pad
            ):
                hits.append(
                    {
                        "tag": tag,
                        "world": [round(v, 3) for v in point],
                        "local": [round(v, 3) for v in local],
                    }
                )
                return


def build_supports(coll, steel, concrete):
    segments = []
    feet = []
    hits = []

    def seg(p0, p1, radius, tag):
        segments.append((Vector(p0), Vector(p1), radius))
        support_collision(p0, p1, radius, tag, hits)

    def footing(x, y):
        feet.append((x, y))

    def under_post(t, tag):
        """Prop from below. Used only while the panel is still above the rails."""
        x = LENGTH * t
        top_z = HEIGHT - 1.25
        seg((x, 0.0, 0.18), (x, 0.0, top_z), 0.075, tag)
        for side in (-1.0, 1.0):
            seg((x, 0.0, top_z), rail_point(t, side), 0.042, tag + "-fork")
        footing(x, 0.0)

    def hanger(t, tag):
        """Single diagonal from the +Y side, then a short drop clear of the hanging panel."""
        x = LENGTH * t
        y = 4.8
        crown = HEIGHT + 2.65
        hub_z = HEIGHT + 1.45
        seg((x, y, 0.18), (x, 0.0, crown), 0.06, tag)
        seg((x, 0.0, crown), (x, 0.0, hub_z), 0.042, tag + "-drop")
        hub = (x, 0.0, hub_z)
        for side in (-1.0, 1.0):
            seg(hub, rail_point(t, side), 0.036, tag + "-fork")
        footing(x, y)

    for t in (0.07, 0.14, 0.86, 0.93):
        under_post(t, f"post-{t:.2f}")
    for t in (0.34, 0.50, 0.66):
        hanger(t, f"hanger-{t:.2f}")

    mesh = bpy.data.meshes.new("Supports")
    bm = bmesh.new()
    for p0, p1, radius in segments:
        add_cone(bm, p0, p1, radius)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = new_object("Supports", mesh, coll)
    obj.data.materials.append(steel)

    foot_mesh = bpy.data.meshes.new("Footings")
    bm = bmesh.new()
    for x, y in feet:
        matrix = Matrix.Translation((x, y, 0.12)) @ Matrix.Diagonal((1.25, 1.25, 0.24, 1.0))
        bmesh.ops.create_cube(bm, size=1.0, matrix=matrix)
    bm.to_mesh(foot_mesh)
    bm.free()
    foot = new_object("Footings", foot_mesh, coll)
    foot.data.materials.append(concrete)
    return hits


def build_bogie(coll, mats):
    bogie = bpy.data.objects.new("Bogie", None)
    bogie.empty_display_type = "ARROWS"
    bogie.empty_display_size = 0.45
    bogie.rotation_mode = "XYZ"
    bogie.location = (0.0, 0.0, HEIGHT)
    coll.objects.link(bogie)

    def part(name, size, mat, location, mesh=None):
        return link_box(name, size, mat, coll, parent=bogie, location=location, mesh=mesh)

    part("Deck", (2.20, 0.96, 0.11), mats["orange"], (0.0, 0.0, 0.42))
    part("Sill", (2.32, 1.02, 0.045), mats["orange_dark"], (0.0, 0.0, 0.34))
    part("CouplerFront", (0.28, 0.12, 0.08), mats["steel_dark"], (1.20, 0.0, 0.40))
    part("CouplerRear", (0.28, 0.12, 0.08), mats["steel_dark"], (-1.20, 0.0, 0.40))
    part("Nose", (0.16, 0.16, 0.16), mats["red"], (1.32, 0.0, 0.52))

    cols, rows = 4, 2
    mod_x, mod_y, gap = 0.84, 0.78, 0.028
    total_x = cols * mod_x + (cols - 1) * gap
    total_y = rows * mod_y + (rows - 1) * gap
    # Cream back on local -Z, navy cells proud of it on local +Z, so a side view
    # shows a dark cap on the photovoltaic side.
    part("ArrayBack", (total_x - 0.04, total_y - 0.04, 0.09), mats["back"], (0.0, 0.0, PANEL_Z - 0.055))
    part(
        "Bezel",
        (total_x + 0.08, total_y + 0.08, 0.03),
        mats["frame"],
        (0.0, 0.0, PANEL_Z - 0.008),
    )

    cell = box_mesh("PVModule", (mod_x - 0.045, mod_y - 0.045, 0.085))
    cell.materials.append(mats["cells"])
    for ix in range(cols):
        for iy in range(rows):
            x = (ix - (cols - 1) / 2) * (mod_x + gap)
            y = (iy - (rows - 1) / 2) * (mod_y + gap)
            link_box(
                f"Cells_{ix}{iy}",
                (mod_x - 0.045, mod_y - 0.045, 0.085),
                mats["cells"],
                coll,
                parent=bogie,
                location=(x, y, PANEL_Z + 0.032),
                mesh=cell,
            )

    brace_mesh = bpy.data.meshes.new("Braces")
    bm = bmesh.new()
    corners = (
        (total_x * 0.42, total_y * 0.42),
        (total_x * 0.42, -total_y * 0.42),
        (-total_x * 0.42, total_y * 0.42),
        (-total_x * 0.42, -total_y * 0.42),
    )
    for x, y in corners:
        add_cone(bm, (x * 0.72, y * 0.55, 0.52), (x, y, PANEL_Z - 0.05), 0.028, segments=8)
    bm.to_mesh(brace_mesh)
    bm.free()
    braces = new_object("Braces", brace_mesh, coll, parent=bogie)
    braces.data.materials.append(mats["aluminum"])

    axle_mesh = bpy.data.meshes.new("Axles")
    bm = bmesh.new()
    rot = Matrix.Rotation(math.pi / 2.0, 4, "X")
    for x in (-0.46, 0.46):
        matrix = Matrix.Translation((x, 0.0, RAIL_R + WHEEL_R)) @ rot
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            segments=12,
            radius1=0.035,
            radius2=0.035,
            depth=GAUGE * 0.72,
            matrix=matrix,
        )
    bm.to_mesh(axle_mesh)
    bm.free()
    axles = new_object("Axles", axle_mesh, coll, parent=bogie)
    axles.data.materials.append(mats["steel_dark"])

    def make_wheel(flange_sign):
        mesh = bpy.data.meshes.new("WheelMesh")
        bm = bmesh.new()
        spin = Matrix.Rotation(math.pi / 2.0, 4, "X")
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            segments=28,
            radius1=WHEEL_R,
            radius2=WHEEL_R,
            depth=0.10,
            matrix=spin,
        )
        for face in bm.faces:
            face.material_index = 0
            face.smooth = True
            face.tag = True
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            segments=28,
            radius1=FLANGE_R,
            radius2=FLANGE_R,
            depth=0.028,
            matrix=Matrix.Translation((0.0, flange_sign * 0.052, 0.0)) @ spin,
        )
        for face in bm.faces:
            if not face.tag:
                face.material_index = 1
                face.smooth = True
        bm.to_mesh(mesh)
        bm.free()
        mesh.materials.append(mats["rubber"])
        mesh.materials.append(mats["flange"])
        return mesh

    wheel_pos = make_wheel(-1.0)
    wheel_neg = make_wheel(1.0)
    wheels = []
    # Tread sits on the rail crown: local +Z is the side the panel occupies.
    z = RAIL_R + WHEEL_R
    for x in (-0.46, 0.46):
        for y, mesh in ((GAUGE * 0.5, wheel_pos), (-GAUGE * 0.5, wheel_neg)):
            wheel = new_object(f"Wheel_{x:+.2f}_{y:+.2f}", mesh, coll, parent=bogie, location=(x, y, z))
            wheels.append(wheel)
    return bogie, wheels


def build_lights(coll):
    sun = bpy.data.lights.new("SunKey", type="SUN")
    sun.energy = 4.2
    sun.color = (1.0, 0.97, 0.92)
    sun.angle = math.radians(3.5)
    sun_obj = new_object("SunKey", sun, coll)
    sun_obj.rotation_euler = (math.radians(38), math.radians(-22), math.radians(8))

    sky = bpy.data.lights.new("SkyFill", type="SUN")
    sky.energy = 0.45
    sky.color = (0.72, 0.80, 0.95)
    sky.angle = math.radians(50.0)
    sky_obj = new_object("SkyFill", sky, coll)
    sky_obj.rotation_euler = (math.radians(78), 0.0, math.radians(30))

    # Warm lift so a downward cell face stays navy instead of dropping to black.
    bounce = bpy.data.lights.new("GroundBounce", type="AREA")
    bounce.energy = 220.0
    bounce.size = 16.0
    bounce.color = (0.90, 0.82, 0.70)
    bounce_obj = new_object("GroundBounce", bounce, coll, location=(LENGTH * 0.5, 0.0, 0.9))
    bounce_obj.rotation_euler = (math.pi, 0.0, 0.0)


def build_cameras(coll):
    def camera(name, lens, ortho=None):
        data = bpy.data.cameras.new(name)
        data.clip_start = 0.05
        data.clip_end = 500.0
        data.sensor_fit = "HORIZONTAL"
        data.sensor_width = 36.0
        if ortho is None:
            data.type = "PERSP"
            data.lens = lens
        else:
            data.type = "ORTHO"
            data.ortho_scale = ortho
        return new_object(name, data, coll)

    side = camera("CameraSide", 50, ortho=15.0)
    track = camera("CameraTrack", 50, ortho=7.0)
    hero = camera("CameraHero", 28)
    axle = camera("CameraAxle", 32)
    return side, track, hero, axle


def animate(scene, bogie, wheels, cameras):
    side, track, hero, axle = cameras

    for frame_num in range(1, FRAMES + 1):
        u = (frame_num - 1) / (FRAMES - 1)
        distance_t = smoothstep(u)
        x = distance_t * LENGTH
        roll = roll_at_x(x)
        bogie.location = (x, 0.0, HEIGHT)
        bogie.rotation_euler = (roll, 0.0, 0.0)
        bogie.keyframe_insert("location", frame=frame_num)
        bogie.keyframe_insert("rotation_euler", frame=frame_num)

        spin = -x / WHEEL_R
        for wheel in wheels:
            wheel.rotation_euler = (0.0, spin, 0.0)
            wheel.keyframe_insert("rotation_euler", frame=frame_num)

        pose = frame(distance_t)
        normal = pose.to_3x3() @ Vector((0.0, 0.0, 1.0))
        panel = pose @ Vector((0.0, 0.0, PANEL_Z))
        center = Vector((x, 0.0, HEIGHT))
        # World up stays up. Shift only along world Z, toward whichever way the cells face.
        face = normal.z

        track.location = (x, -14.0, HEIGHT)
        look_at(track, center)
        track.keyframe_insert("location", frame=frame_num)
        track.keyframe_insert("rotation_euler", frame=frame_num)

        side.location = (x, -20.0, HEIGHT - 1.05)
        look_at(side, (x, 0.0, HEIGHT - 1.05))
        side.keyframe_insert("location", frame=frame_num)
        side.keyframe_insert("rotation_euler", frame=frame_num)

        hero.location = (x - 3.4, -6.6, panel.z + face * 3.5)
        look_at(hero, panel.lerp(center, 0.40))
        hero.keyframe_insert("location", frame=frame_num)
        hero.keyframe_insert("rotation_euler", frame=frame_num)

        axle.location = (x - 2.4, -4.6, panel.z + face * 1.05)
        look_at(axle, panel.lerp(center, 0.45))
        axle.keyframe_insert("location", frame=frame_num)
        axle.keyframe_insert("rotation_euler", frame=frame_num)

    scene.frame_start = 1
    scene.frame_end = FRAMES
    scene.frame_current = 1
    scene.frame_set(1)


def configure_scene(scene):
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.fps = FPS
    scene.render.fps_base = 1.0
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    eevee = getattr(scene, "eevee", None)
    if eevee is not None and hasattr(eevee, "taa_render_samples"):
        eevee.taa_render_samples = 16
    try:
        scene.view_settings.view_transform = "AgX"
    except (TypeError, ValueError):
        pass
    try:
        scene.view_settings.look = "AgX - Medium Contrast"
    except (TypeError, ValueError):
        pass


def main():
    clear_scene()
    scene = bpy.context.scene
    configure_scene(scene)
    build_world(scene)

    env = collection("Environment")
    rail = collection("Rail")
    wagon = collection("Wagon")
    lights = collection("Lights")
    cameras = collection("Cameras")

    steel = principled("Steel", (0.16, 0.17, 0.19), metallic=0.82, roughness=0.38)
    tie_mat = principled("Ties", (0.80, 0.78, 0.72), roughness=0.92, specular=0.12)
    concrete = principled("Concrete", (0.55, 0.54, 0.51), roughness=0.9, specular=0.18)
    earth = principled("Earth", (0.34, 0.38, 0.32), roughness=0.96, specular=0.08)
    mats = {
        "orange": principled("WagonOrange", (0.90, 0.36, 0.06), roughness=0.48, specular=0.3),
        "orange_dark": principled("WagonShadow", (0.42, 0.15, 0.04), roughness=0.6),
        "red": principled("NoseRed", (0.82, 0.08, 0.04), roughness=0.4),
        "aluminum": principled("Aluminum", (0.70, 0.72, 0.75), metallic=0.8, roughness=0.32),
        "back": principled("PanelBack", (0.95, 0.93, 0.86), roughness=0.72, specular=0.15),
        "frame": principled("ModuleFrame", (0.10, 0.11, 0.13), metallic=0.55, roughness=0.42),
        "cells": cell_material(),
        "steel_dark": principled("SteelDark", (0.10, 0.10, 0.11), metallic=0.75, roughness=0.38),
        "flange": principled("Flange", (0.68, 0.70, 0.72), metallic=0.9, roughness=0.3),
        "rubber": principled("Rubber", (0.02, 0.02, 0.022), roughness=0.78, specular=0.2),
    }

    build_environment(env, concrete, earth)
    build_rails(rail, steel, tie_mat)
    collisions = build_supports(rail, steel, concrete)
    bogie, wheels = build_bogie(wagon, mats)
    build_lights(lights)
    cams = build_cameras(cameras)
    scene.camera = cams[0]
    animate(scene, bogie, wheels, cams)

    normals = {}
    for label, t in (("start", 0.0), ("mid", 0.5), ("end", 1.0)):
        normal = frame(t).to_3x3() @ Vector((0.0, 0.0, 1.0))
        normals[label] = [round(v, 4) for v in normal]

    result = {
        "length_m": LENGTH,
        "height_m": HEIGHT,
        "frames": FRAMES,
        "fps": FPS,
        "panel_z": PANEL_Z,
        "normals": normals,
        "collisions": collisions[:12],
        "collision_count": len(collisions),
        "cameras": [cam.name for cam in cams],
    }
    return result


result = main()
