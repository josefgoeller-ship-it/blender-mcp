"""Restyle the cinematic habitat as a USPTO-style black-and-white patent drawing."""

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


def hide_tree(name):
    root = D.objects.get(name)
    if root is None:
        return
    stack = [root]
    seen = set()
    while stack:
        obj = stack.pop()
        if obj.name in seen:
            continue
        seen.add(obj.name)
        obj.hide_render = True
        obj.hide_viewport = True
        stack.extend(list(obj.children))


for n in ("Planet", "PlanetAtmo", "Earthshine", "SunKey", "Fill", "Rim"):
    o = D.objects.get(n)
    if o:
        o.hide_render = True
        o.hide_viewport = True
hide_tree("ScaleShips")

# --- white paper ---
world = D.worlds.get("World") or D.worlds.new("World")
world.use_nodes = True
nt = world.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
wout = nt.nodes.new("ShaderNodeOutputWorld")
wbg = nt.nodes.new("ShaderNodeBackground")
wbg.inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
wbg.inputs[1].default_value = 1.0
nt.links.new(wbg.outputs["Background"], wout.inputs["Surface"])
scene.world = world

# Flat white fill — emission so Freestyle sits on unshaded faces
fill = D.materials.get("PatentFill") or D.materials.new("PatentFill")
fill.use_nodes = True
ntt = fill.node_tree
for n in list(ntt.nodes):
    ntt.nodes.remove(n)
out = ntt.nodes.new("ShaderNodeOutputMaterial")
em = ntt.nodes.new("ShaderNodeEmission")
em.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
em.inputs["Strength"].default_value = 1.0
ntt.links.new(em.outputs["Emission"], out.inputs["Surface"])

for obj in D.objects:
    if obj.type != "MESH":
        continue
    if obj.name in ("Planet", "PlanetAtmo") or obj.hide_render:
        continue
    obj.data.materials.clear()
    obj.data.materials.append(fill)

src_col = D.collections.get("LineArtSource") or D.collections.new("LineArtSource")
if src_col.name not in scene.collection.children:
    scene.collection.children.link(src_col)
for obj in D.objects:
    if obj.type != "MESH" or obj.hide_render:
        continue
    if src_col not in obj.users_collection:
        src_col.objects.link(obj)


def make_ortho(name, loc, target, scale=16.5):
    old = D.objects.get(name)
    if old:
        D.objects.remove(old, do_unlink=True)
    data = D.cameras.new(name)
    data.type = "ORTHO"
    data.ortho_scale = scale
    data.clip_start = 0.05
    data.clip_end = 200.0
    cam = D.objects.new(name, data)
    cam.location = loc
    aim_at(cam, target)
    scene.collection.objects.link(cam)
    return cam


make_ortho("CamFront", (0.0, -16.0, 0.25), (0.0, 0.0, 0.25), 16.5)
make_ortho("CamSide", (16.0, 0.0, 0.25), (0.0, 0.0, 0.25), 16.5)
top = make_ortho("CamTop", (0.0, 0.0, 16.0), (0.0, 0.0, 0.0), 16.5)
top.rotation_euler = (0.0, 0.0, 0.0)

old_iso = D.objects.get("CamIso")
if old_iso:
    D.objects.remove(old_iso, do_unlink=True)
iso_data = D.cameras.new("CamIso")
iso_data.type = "ORTHO"
iso_data.ortho_scale = 18.0
iso_data.clip_start = 0.05
iso_data.clip_end = 200.0
iso = D.objects.new("CamIso", iso_data)
iso.location = (12.0, -12.0, 10.0)
aim_at(iso, (0.0, 0.0, 0.2))
scene.collection.objects.link(iso)
scene.camera = iso

# --- Line Art ---
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
    gp_obj = C.active_object if created else None
    if gp_obj is not None:
        gp_obj.name = "PatentLineArt"
        gp_mat = D.materials.new("LineArtBlack")
        if hasattr(gp_mat, "grease_pencil") and gp_mat.grease_pencil:
            gp_mat.grease_pencil.color = (0.0, 0.0, 0.0, 1.0)
            gp_mat.grease_pencil.show_stroke = True
        try:
            gp_obj.data.materials.append(gp_mat)
        except Exception:
            pass
        mod = None
        for mtype in ("GREASE_PENCIL_LINEART", "LINEART", "GP_LINEART"):
            try:
                mod = gp_obj.modifiers.new("LineArt", mtype)
                break
            except TypeError:
                continue
        if mod is not None:
            if hasattr(mod, "source_type"):
                try:
                    mod.source_type = "COLLECTION"
                except Exception:
                    pass
            if hasattr(mod, "source_collection"):
                try:
                    mod.source_collection = src_col
                except Exception:
                    pass
            for flag in ("use_contour", "use_crease", "use_material", "use_edge_mark"):
                if hasattr(mod, flag):
                    try:
                        setattr(mod, flag, True)
                    except Exception:
                        pass
            if hasattr(mod, "thickness"):
                try:
                    mod.thickness = 1.2
                except Exception:
                    pass
            gp_ok = True
            line_method = "grease_pencil"
except Exception as exc:
    line_method = f"gp_failed:{exc}"

try:
    scene.render.use_freestyle = True
    vl = scene.view_layers[0]
    if hasattr(vl, "use_freestyle"):
        vl.use_freestyle = True
    settings = vl.freestyle_settings
    while settings.linesets:
        settings.linesets.remove(settings.linesets[0])
    ls = settings.linesets.new("PatentLines")
    ls.select_silhouette = True
    ls.select_crease = True
    ls.select_border = True
    ls.select_edge_mark = True
    if hasattr(ls, "select_material_boundary"):
        ls.select_material_boundary = True
    style = ls.linestyle
    style.color = (0.0, 0.0, 0.0)
    style.thickness = 1.15
    line_method = "grease_pencil+freestyle" if gp_ok else "freestyle"
except Exception as exc:
    if not gp_ok:
        line_method = f"freestyle_failed:{exc}"

sh = scene.display.shading
if hasattr(sh, "show_object_outline"):
    sh.show_object_outline = True
if hasattr(sh, "object_outline_color"):
    sh.object_outline_color = (0.0, 0.0, 0.0)
if hasattr(sh, "light"):
    sh.light = "FLAT"
if hasattr(sh, "color_type"):
    sh.color_type = "SINGLE"
if hasattr(sh, "single_color"):
    sh.single_color = (1.0, 1.0, 1.0)

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


def _render_cam(settings, blend: Path, camera: str, output: Path, width: int, height: int):
    code = f"""
scene = C.scene
cam = D.objects.get({camera!r})
if cam is None:
    raise RuntimeError("missing camera")
scene.camera = cam
result = {{"camera": scene.camera.name}}
"""
    return headless.run_job(
        settings,
        [
            {"type": "execute", "code": code},
            {
                "type": "render",
                "path": str(output),
                "engine": "EEVEE",
                "samples": 24,
                "resolution": [width, height],
            },
        ],
        open_blend=str(blend),
    )


def pack_sheet(fig1: Path, front: Path, side: Path, top: Path, dest: Path) -> str:
    from PIL import Image, ImageDraw, ImageFont

    iso = Image.open(fig1).convert("RGB")
    iso = iso.resize((1600, 1200))
    thumbs = [
        Image.open(p).convert("RGB").resize((500, 500)) for p in (front, side, top)
    ]
    pad, header, footer = 28, 56, 28
    w = pad * 2 + 1600
    h = header + iso.height + pad + 500 + footer
    sheet = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    try:
        title_f = ImageFont.truetype("arial.ttf", 28)
        label_f = ImageFont.truetype("arial.ttf", 20)
    except Exception:
        title_f = ImageFont.load_default()
        label_f = title_f
    draw.text((pad, 14), "U.S. PATENT  —  SPACE HABITAT", fill=(0, 0, 0), font=title_f)
    sheet.paste(iso, (pad, header))
    draw.text((pad + 8, header + 8), "FIG. 1", fill=(0, 0, 0), font=label_f)
    labels = ("FIG. 2  FRONT", "FIG. 3  SIDE", "FIG. 4  TOP")
    gap = (1600 - 500 * 3) // 2
    y = header + iso.height + 12
    for i, (im, label) in enumerate(zip(thumbs, labels)):
        x = pad + i * (500 + gap)
        sheet.paste(im, (x, y))
        draw.text((x + 8, y + 8), label, fill=(0, 0, 0), font=label_f)
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest)
    return "pillow"


def main() -> int:
    settings = get_settings()
    src = settings.output_dir / "space_habitat" / "habitat_cinematic.blend"
    blend = settings.output_dir / "space_habitat" / "habitat_patent.blend"
    if not src.is_file():
        print("Missing source:", src)
        return 1

    print("Opening cinematic, writing patent drawing...")
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
    fig1 = out / "habitat_patent_fig1.png"
    front = out / "habitat_patent_front.png"
    side = out / "habitat_patent_side.png"
    top = out / "habitat_patent_top.png"
    sheet = out / "habitat_patent_sheet.png"

    print("Rendering FIG. 1 (iso)...")
    j = _render_cam(settings, blend, "CamIso", fig1, 1600, 1200)
    print("fig1", j.ok, j.responses[-1].get("result") or j.responses[-1].get("error"))
    if not j.ok:
        print(j.stdout[-2000:])
        return 1

    print("Rendering ortho views...")
    for cam, path in (("CamFront", front), ("CamSide", side), ("CamTop", top)):
        j = _render_cam(settings, blend, cam, path, 1200, 1200)
        print(cam, j.ok, j.responses[-1].get("result") or j.responses[-1].get("error"))
        if not j.ok:
            print(j.stdout[-2000:])
            return 1

    how = pack_sheet(fig1, front, side, top, sheet)
    print("sheet:", how, sheet)
    print("Saved blend:", blend)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
