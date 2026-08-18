"""Restyle the cinematic habitat as a cyan-on-navy blueprint. New file only."""

from __future__ import annotations

from pathlib import Path

from blender_mcp import headless
from blender_mcp.config import get_settings

SETUP = r"""
import math as _m

scene = C.scene

def aim_at(obj, target=(0.0, 0.0, 0.0)):
    direction = mathutils.Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def seti(bsdf, name, value):
    sock = bsdf.inputs.get(name)
    if sock is not None:
        sock.default_value = value


# --- hide planet / earthshine ---
for n in ("Planet", "PlanetAtmo", "Earthshine"):
    o = D.objects.get(n)
    if o:
        o.hide_render = True
        o.hide_viewport = True

# --- navy world ---
world = D.worlds.get("World") or D.worlds.new("World")
world.use_nodes = True
nt = world.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
wout = nt.nodes.new("ShaderNodeOutputWorld")
wbg = nt.nodes.new("ShaderNodeBackground")
wbg.inputs[0].default_value = (0.02, 0.06, 0.14, 1)
wbg.inputs[1].default_value = 1.0
nt.links.new(wbg.outputs["Background"], wout.inputs["Surface"])
scene.world = world

# --- blueprint materials ---
def make_fill():
    m = D.materials.get("BlueprintFill") or D.materials.new("BlueprintFill")
    m.use_nodes = True
    ntt = m.node_tree
    for n in list(ntt.nodes):
        ntt.nodes.remove(n)
    out = ntt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = ntt.nodes.new("ShaderNodeBsdfPrincipled")
    seti(bsdf, "Base Color", (0.03, 0.10, 0.22, 1))
    seti(bsdf, "Metallic", 0.0)
    seti(bsdf, "Roughness", 1.0)
    seti(bsdf, "Emission Color", (0.15, 0.45, 0.75, 1))
    seti(bsdf, "Emission Strength", 0.18)
    ntt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def make_glow():
    m = D.materials.get("BlueprintGlow") or D.materials.new("BlueprintGlow")
    m.use_nodes = True
    ntt = m.node_tree
    for n in list(ntt.nodes):
        ntt.nodes.remove(n)
    out = ntt.nodes.new("ShaderNodeOutputMaterial")
    em = ntt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.45, 0.85, 1.0, 1)
    em.inputs["Strength"].default_value = 6.0
    ntt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


def make_grid_mat():
    m = D.materials.get("BlueprintGrid") or D.materials.new("BlueprintGrid")
    m.use_nodes = True
    ntt = m.node_tree
    for n in list(ntt.nodes):
        ntt.nodes.remove(n)
    out = ntt.nodes.new("ShaderNodeOutputMaterial")
    coord = ntt.nodes.new("ShaderNodeTexCoord")
    brick = ntt.nodes.new("ShaderNodeTexBrick")
    brick.inputs["Scale"].default_value = 8.0
    brick.inputs["Mortar Size"].default_value = 0.012
    brick.inputs["Color1"].default_value = (0.02, 0.07, 0.16, 1)
    brick.inputs["Color2"].default_value = (0.025, 0.08, 0.18, 1)
    brick.inputs["Mortar"].default_value = (0.25, 0.55, 0.85, 1)
    ntt.links.new(coord.outputs["Object"], brick.inputs["Vector"])
    em = ntt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    ntt.links.new(brick.outputs["Color"], em.inputs["Color"])
    ntt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


fill = make_fill()
glow = make_glow()
grid_mat = make_grid_mat()

GLOW_NAMES = ("BayGlow", "ShipExhaust", "InteriorGlow")
GLOW_PREFIXES = ("WinGlow", "SpokeWin", "ObsGlow", "SpireBayGlow")

for obj in D.objects:
    if obj.type != "MESH" or obj.name.startswith("Grid"):
        continue
    if obj.name in ("Planet", "PlanetAtmo"):
        continue
    use_glow = False
    if obj.data.materials:
        mat0 = obj.data.materials[0]
        if mat0 and (mat0.name in GLOW_NAMES or any(mat0.name.startswith(p) for p in GLOW_PREFIXES)):
            use_glow = True
    if any(obj.name.startswith(p) for p in GLOW_PREFIXES) or obj.name.startswith("ShipEx"):
        use_glow = True
    obj.data.materials.clear()
    obj.data.materials.append(glow if use_glow else fill)

# --- collection for line art ---
src_col = D.collections.get("LineArtSource") or D.collections.new("LineArtSource")
if src_col.name not in scene.collection.children:
    scene.collection.children.link(src_col)
root = D.objects.get("HabitatRoot")
ships = D.objects.get("ScaleShips")
for obj in list(D.objects):
    if obj.type != "MESH":
        continue
    if obj.name in ("Planet", "PlanetAtmo") or obj.name.startswith("Grid"):
        continue
    if src_col not in obj.users_collection:
        src_col.objects.link(obj)

# --- grid planes (hidden on 3D hero; shown per ortho) ---
def add_grid(name, loc, rot, size=42.0):
    existing = D.objects.get(name)
    if existing:
        D.objects.remove(existing, do_unlink=True)
    bpy.ops.mesh.primitive_plane_add(size=size, location=loc)
    g = C.active_object
    g.name = name
    g.rotation_euler = rot
    g.data.materials.clear()
    g.data.materials.append(grid_mat)
    g.hide_render = True
    return g


add_grid("GridFloor", (0.0, 0.0, -5.5), (0.0, 0.0, 0.0))
add_grid("GridFront", (0.0, 10.0, 0.2), (_m.radians(90), 0.0, 0.0))
add_grid("GridSide", (-10.0, 0.0, 0.2), (_m.radians(90), 0.0, _m.radians(90)))

# --- ortho cameras ---
def make_ortho(name, loc, target, scale=16.5):
    old = D.objects.get(name)
    if old:
        D.objects.remove(old, do_unlink=True)
    data = D.cameras.new(name)
    data.type = "ORTHO"
    data.ortho_scale = scale
    data.clip_start = 0.1
    data.clip_end = 200.0
    cam = D.objects.new(name, data)
    cam.location = loc
    aim_at(cam, target)
    scene.collection.objects.link(cam)
    return cam


make_ortho("CamFront", (0.0, -16.0, 0.25), (0.0, 0.0, 0.25))
make_ortho("CamSide", (16.0, 0.0, 0.25), (0.0, 0.0, 0.25))
top = make_ortho("CamTop", (0.0, 0.0, 16.0), (0.0, 0.0, 0.0))
top.rotation_euler = (0.0, 0.0, 0.0)

hero = D.objects.get("Camera")
if hero and hero.data:
    hero.data.clip_end = 200.0
    scene.camera = hero

# --- Line Art: GP, then Freestyle, then Workbench flags ---
line_method = "none"
gp_ok = False
try:
    bpy.ops.object.select_all(action="DESELECT")
    created = False
    for gp_type in ("LINEART_SCENE", "LINEART_COLLECTION", "EMPTY", "STROKE"):
        try:
            bpy.ops.object.grease_pencil_add(type=gp_type)
            created = True
            break
        except Exception:
            continue
    if not created:
        try:
            bpy.ops.object.gpencil_add(type="LRT_SCENE")
            created = True
        except Exception:
            pass
    gp_obj = C.active_object if created else None
    if gp_obj is not None:
        gp_obj.name = "BlueprintLineArt"
        gp_data = gp_obj.data
        gp_mat = D.materials.new("LineArtCyan")
        gp_mat.grease_pencil = True if hasattr(gp_mat, "grease_pencil") else False
        # GP material color
        if hasattr(gp_mat, "grease_pencil") and gp_mat.grease_pencil:
            gp_mat.grease_pencil.color = (0.55, 0.85, 1.0, 1.0)
            gp_mat.grease_pencil.show_stroke = True
        try:
            gp_data.materials.append(gp_mat)
        except Exception:
            pass
        mod = None
        for mtype in ("GREASE_PENCIL_LINEART", "LINEART", "GP_LINEART"):
            try:
                mod = gp_obj.modifiers.new("LineArt", mtype)
                break
            except TypeError:
                continue
        if mod is None:
            for existing in gp_obj.modifiers:
                if "LINE" in existing.type or "line" in existing.name.lower():
                    mod = existing
                    break
        if mod is not None:
            if hasattr(mod, "source_type"):
                try:
                    mod.source_type = "COLLECTION"
                except Exception:
                    try:
                        mod.source_type = "SCENE"
                    except Exception:
                        pass
            if hasattr(mod, "source_collection"):
                try:
                    mod.source_collection = src_col
                except Exception:
                    pass
            for flag in ("use_contour", "use_crease", "use_material", "use_edge_mark", "use_intersection"):
                if hasattr(mod, flag):
                    try:
                        setattr(mod, flag, True)
                    except Exception:
                        pass
            if hasattr(mod, "thickness"):
                try:
                    mod.thickness = 1.6
                except Exception:
                    pass
            if hasattr(mod, "target_material"):
                try:
                    mod.target_material = gp_mat
                except Exception:
                    pass
            gp_ok = True
            line_method = "grease_pencil"
except Exception as exc:
    line_method = f"gp_failed:{exc}"

# Freestyle always as extra edges (works in EEVEE/Cycles)
try:
    scene.render.use_freestyle = True
    vl = scene.view_layers[0]
    fs = vl.use_freestyle if hasattr(vl, "use_freestyle") else True
    if hasattr(vl, "use_freestyle"):
        vl.use_freestyle = True
    settings = vl.freestyle_settings
    while settings.linesets:
        settings.linesets.remove(settings.linesets[0])
    ls = settings.linesets.new("BlueprintLines")
    ls.select_silhouette = True
    ls.select_crease = True
    ls.select_border = True
    ls.select_edge_mark = True
    if hasattr(ls, "select_material_boundary"):
        ls.select_material_boundary = True
    style = ls.linestyle
    style.color = (0.55, 0.85, 1.0)
    style.thickness = 1.35
    if not gp_ok:
        line_method = "freestyle"
    else:
        line_method = "grease_pencil+freestyle"
except Exception as exc:
    if not gp_ok:
        line_method = f"freestyle_failed:{exc}"

# Workbench outline as last-resort flags (used if we render WORKBENCH)
sh = scene.display.shading
if hasattr(sh, "show_object_outline"):
    sh.show_object_outline = True
if hasattr(sh, "object_outline_color"):
    sh.object_outline_color = (0.55, 0.85, 1.0)
if hasattr(sh, "light"):
    sh.light = "FLAT"
if hasattr(sh, "color_type"):
    sh.color_type = "SINGLE"
if hasattr(sh, "single_color"):
    sh.single_color = (0.04, 0.12, 0.28)

scene.render.film_transparent = False
scene.render.use_compositing = False
if hasattr(scene, "eevee") and hasattr(scene.eevee, "use_bloom"):
    scene.eevee.use_bloom = False

result = {
    "line_method": line_method,
    "gp_ok": gp_ok,
    "cameras": [c.name for c in D.objects if c.type == "CAMERA"],
}
"""


def _render_cam(settings, blend: Path, camera: str, output: Path, width: int, height: int, grids: list[str]):
    show = ", ".join(repr(n) for n in grids) or ""
    code = f"""
scene = C.scene
cam = D.objects.get({camera!r})
if cam is None:
    raise RuntimeError("missing camera " + {camera!r})
scene.camera = cam
for gname in ("GridFloor", "GridFront", "GridSide"):
    g = D.objects.get(gname)
    if g:
        g.hide_render = gname not in ({show},) if {bool(grids)!r} else True
        if not {bool(grids)!r}:
            g.hide_render = True
for gname in [{show}]:
    g = D.objects.get(gname)
    if g:
        g.hide_render = False
result = {{"camera": scene.camera.name}}
"""
    # simpler grid visibility
    code = f"""
scene = C.scene
cam = D.objects.get({camera!r})
if cam is None:
    raise RuntimeError("missing camera")
scene.camera = cam
wanted = {grids!r}
for gname in ("GridFloor", "GridFront", "GridSide"):
    g = D.objects.get(gname)
    if g:
        g.hide_render = gname not in wanted
result = {{"camera": scene.camera.name, "grids": wanted}}
"""
    job = headless.run_job(
        settings,
        [
            {"type": "execute", "code": code},
            {
                "type": "render",
                "path": str(output),
                "engine": "EEVEE",
                "samples": 32,
                "resolution": [width, height],
            },
        ],
        open_blend=str(blend),
    )
    return job


def pack_sheet(front: Path, side: Path, top: Path, dest: Path) -> str:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return _pack_sheet_blender(front, side, top, dest)

    imgs = [Image.open(p).convert("RGB") for p in (front, side, top)]
    size = 800
    imgs = [im.resize((size, size)) for im in imgs]
    pad, header = 24, 48
    w = pad * 4 + size * 3
    h = pad * 2 + header + size
    sheet = Image.new("RGB", (w, h), (8, 20, 40))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    labels = ("FRONT", "SIDE", "TOP")
    for i, (im, label) in enumerate(zip(imgs, labels)):
        x = pad + i * (size + pad)
        y = pad + header
        sheet.paste(im, (x, y))
        draw.text((x + 8, pad + 12), label, fill=(140, 210, 255), font=font)
    draw.text((pad, 8), "SPACE HABITAT  —  BLUEPRINT", fill=(180, 230, 255), font=font)
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest)
    return "pillow"


def _pack_sheet_blender(front: Path, side: Path, top: Path, dest: Path) -> str:
    # fallback: just copy front if pillow missing
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(front.read_bytes())
    return "fallback_front"


def main() -> int:
    settings = get_settings()
    src = settings.output_dir / "space_habitat" / "habitat_cinematic.blend"
    blend = settings.output_dir / "space_habitat" / "habitat_blueprint.blend"
    if not src.is_file():
        print("Missing source:", src)
        return 1

    print("Opening cinematic, writing blueprint...")
    job = headless.run_job(
        settings,
        [
            {"type": "execute", "code": SETUP},
            {"type": "save_as", "path": str(blend), "compress": True},
        ],
        open_blend=str(src),
        timeout=180,
    )
    print("ok:", job.ok)
    for step in job.responses:
        print(step.get("ok"), step.get("result") or step.get("error"))
    if not job.ok:
        print(job.stdout[-4000:])
        return 1

    out = settings.output_dir / "space_habitat"
    hero = out / "habitat_blueprint_hero.png"
    front = out / "habitat_blueprint_front.png"
    side = out / "habitat_blueprint_side.png"
    top = out / "habitat_blueprint_top.png"
    sheet = out / "habitat_blueprint_sheet.png"

    print("Rendering hero...")
    j = _render_cam(settings, blend, "Camera", hero, 1600, 900, [])
    print("hero", j.ok, j.responses[-1].get("result") or j.responses[-1].get("error"))
    if not j.ok:
        print(j.stdout[-2000:])
        return 1

    print("Rendering ortho views...")
    for cam, path, grids in (
        ("CamFront", front, ["GridFront"]),
        ("CamSide", side, ["GridSide"]),
        ("CamTop", top, ["GridFloor"]),
    ):
        j = _render_cam(settings, blend, cam, path, 1200, 1200, grids)
        print(cam, j.ok, j.responses[-1].get("result") or j.responses[-1].get("error"))
        if not j.ok:
            print(j.stdout[-2000:])
            return 1

    how = pack_sheet(front, side, top, sheet)
    print("sheet:", how, sheet)
    print("Saved blend:", blend)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
