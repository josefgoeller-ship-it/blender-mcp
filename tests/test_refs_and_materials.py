from pathlib import Path

from blender_mcp import materials, refs, templates
from blender_mcp.config import Settings


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        executable=tmp_path / "blender.exe",
        output_dir=tmp_path / "out",
        addon_root=tmp_path / "addon",
        host="127.0.0.1",
        port=9876,
        timeout=30.0,
    )


def test_refs_root_is_created(tmp_path):
    settings = make_settings(tmp_path)
    root = refs.refs_root(settings)
    assert root.is_dir()
    assert root == tmp_path / "out" / "refs"


def test_add_and_list_reference(tmp_path):
    settings = make_settings(tmp_path)
    source = tmp_path / "guide.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)

    added = refs.add_reference(settings, source, name="hero.png", group="job1")
    assert added["path"] == "job1/hero.png"

    listed = refs.list_references(settings, group="job1")
    assert any(item["path"] == "job1/hero.png" for item in listed["files"])

    resolved = refs.resolve_ref(settings, "job1/hero.png")
    assert resolved.is_file()


def test_write_reference_bytes(tmp_path):
    settings = make_settings(tmp_path)
    written = refs.write_reference_bytes(settings, b"abc", "shot.jpg", group="uploads")
    assert written["path"] == "uploads/shot.jpg"
    assert refs.resolve_ref(settings, written["path"]).read_bytes() == b"abc"


def test_product_template_is_registered():
    assert "product" in templates.TEMPLATES
    compile(templates.get_template("product"), "<product>", "exec")


def test_material_presets_compile():
    for name in materials.PRESETS:
        code = materials.build_apply_script("Cube", name)
        compile(code, f"<{name}>", "exec")


def test_unknown_material_lists_presets():
    import pytest

    with pytest.raises(ValueError, match="metal"):
        materials.build_apply_script("Cube", "nope")
