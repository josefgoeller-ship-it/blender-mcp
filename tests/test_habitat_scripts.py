"""Regression tests for habitat build-script bugs (no Blender required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _script(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8")


def test_pillow_is_a_declared_dependency():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "pillow" in pyproject.lower()


def test_pack_sheet_writes_a_composite_png(tmp_path):
    sys.path.insert(0, str(SCRIPTS))
    from build_habitat_patent import pack_sheet
    from PIL import Image

    fig1 = tmp_path / "fig1.png"
    front = tmp_path / "front.png"
    side = tmp_path / "side.png"
    top = tmp_path / "top.png"
    dest = tmp_path / "out" / "sheet.png"
    Image.new("RGB", (80, 60), (10, 10, 10)).save(fig1)
    for path in (front, side, top):
        Image.new("RGB", (40, 40), (200, 200, 200)).save(path)

    how = pack_sheet(fig1, front, side, top, dest)

    assert how == "pillow"
    assert dest.is_file()
    sheet = Image.open(dest)
    assert sheet.size[0] >= 1600
    assert sheet.size[1] >= 1200


def test_patent_main_imports_pillow_before_rendering():
    src = _script("build_habitat_patent.py")
    main = src.split("def main()")[1].split("def ")[0]
    assert "PIL" in main or "pillow" in main.lower()
    render_at = main.find("Rendering FIG")
    import_at = min(
        i for i in (main.find("PIL"), main.find("pillow"), main.find("Pillow")) if i >= 0
    )
    assert import_at < render_at


def test_polish_scales_sun_energy_by_lamp_type():
    polish = _script("polish_space_habitat.py")
    block = polish.split("sun = D.objects.get")[1].split("rim =")[0]
    assert "SUN" in block
    assert "2400" in block
    assert "type" in block


def test_polish_tweak_updates_emission_shaders():
    polish = _script("polish_space_habitat.py")
    tweak = polish.split("def tweak(")[1].split("tweak(")[0]
    assert "EMISSION" in tweak


def test_window_glow_uses_the_outward_glass_offset():
    improve = _script("improve_space_habitat.py")
    before_name = improve.split('gp.name = f"WinGlow_{tag}"')[0]
    spawn = before_name.rsplit("primitive_cube_add", 1)[-1]
    assert "glass_loc" in spawn
    assert "location=loc)" not in spawn


def test_ship_left_wing_uses_the_computed_offset():
    cinematic = _script("build_habitat_cinematic.py")
    make_ship = cinematic.split("def make_ship")[1].split("make_ship(")[0]
    assert "ShipWingL_" in make_ship
    assert "add_cube(f\"ShipWingL_{tag}\", w1," in make_ship
