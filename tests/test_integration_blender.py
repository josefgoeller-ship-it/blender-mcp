"""End-to-end tests that drive a real background Blender.

Run with `uv run pytest -m blender`. Each test starts Blender, so they are slow.
"""

from pathlib import Path

import pytest

from blender_mcp import headless, server

pytestmark = pytest.mark.blender


def test_blender_answers_a_ping(settings):
    outcome = headless.run_job(settings, [{"type": "ping"}])
    assert outcome.ok
    assert outcome.last["result"]["background"] is True
    assert outcome.last["result"]["blender_version"]


def test_scripts_can_return_values_three_ways(settings):
    code = "print('printed')\nemit({'from': 'emit'})\nresult = 6 * 7"
    outcome = headless.run_job(settings, [{"type": "execute", "code": code}])
    response = outcome.last
    assert response["result"] == 42
    assert response["emitted"] == [{"from": "emit"}]
    assert "printed" in response["stdout"]


def test_a_broken_script_reports_the_error_without_crashing(settings):
    outcome = headless.run_job(settings, [{"type": "execute", "code": "1 / 0"}])
    response = outcome.last
    assert response["ok"] is False
    assert "ZeroDivisionError" in response["error"]
    # The traceback should point at the user's script, not at our exec plumbing.
    assert "<blender-mcp>" in response["error"]


def test_studio_template_produces_a_render_ready_file(settings):
    report = server.create_blend(path="tests/studio.blend", template="studio")
    assert report["ok"], report.get("error")

    blend = Path(report["path"])
    assert blend.is_file()
    assert blend.stat().st_size > 0

    info = server.inspect_blend(blend_file=str(blend), target="headless")
    scene = info["steps"][-1]["result"]
    assert scene["active_camera"] == "Camera"
    names = {obj["name"] for obj in scene["objects"]}
    assert {"Floor", "Key", "Fill", "Rim", "Camera"} <= names


def test_a_script_can_add_geometry_to_a_template(settings):
    report = server.create_blend(
        path="tests/with_sphere.blend",
        template="studio",
        script=(
            "bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 1))\n"
            "bpy.context.active_object.name = 'Hero'\n"
            "result = bpy.context.active_object.name"
        ),
    )
    assert report["ok"], report.get("error")

    info = server.inspect_blend(blend_file=report["path"], target="headless")
    names = {obj["name"] for obj in info["steps"][-1]["result"]["objects"]}
    assert "Hero" in names


@pytest.mark.parametrize("engine", ["EEVEE", "WORKBENCH"])
def test_rendering_writes_a_png(settings, engine):
    blend = server.create_blend(path="tests/render_source.blend", template="studio")
    assert blend["ok"], blend.get("error")

    report = server.render(
        output=f"tests/render_{engine.lower()}.png",
        blend_file=blend["path"],
        engine=engine,
        samples=8,
        width=160,
        height=90,
        target="headless",
    )
    assert report["ok"], report.get("error")

    image = Path(report["path"])
    assert image.is_file()
    assert image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_rendering_without_a_camera_explains_itself(settings):
    blend = server.create_blend(path="tests/no_camera.blend", template="empty")
    assert blend["ok"], blend.get("error")

    report = server.render(
        output="tests/no_camera.png",
        blend_file=blend["path"],
        target="headless",
        width=160,
        height=90,
    )
    assert report["ok"] is False
    assert "camera" in report["error"].lower()


def test_status_finds_blender_and_lists_templates(settings):
    status = server.blender_status()
    assert "Blender" in status["version"]
    assert "studio" in status["templates"]
    assert "product" in status["templates"]
    assert "metal" in status["materials"]
    assert status["live_bridge"]["address"].startswith("127.0.0.1:")


def test_preview_views_writes_multiple_pngs(settings):
    blend = server.create_blend(
        path="tests/preview_source.blend",
        template="studio",
        script=(
            "bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 1))\n"
            "bpy.context.active_object.name = 'Hero'\n"
        ),
    )
    assert blend["ok"], blend.get("error")

    report = server.preview_views(
        blend_file=blend["path"],
        output_dir="tests/previews",
        width=160,
        height=90,
        samples=4,
        target="headless",
    )
    assert report["ok"], report.get("error")
    assert len(report["views"]) >= 3
    for view in report["views"]:
        image = Path(view["path"])
        assert image.is_file()
        assert image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_apply_material_preset(settings):
    blend = server.create_blend(
        path="tests/material_source.blend",
        template="studio",
        script=(
            "bpy.ops.mesh.primitive_cube_add(location=(0, 0, 1))\n"
            "bpy.context.active_object.name = 'Block'\n"
        ),
    )
    assert blend["ok"], blend.get("error")

    report = server.apply_material(
        object_name="Block",
        preset="metal",
        color=[0.8, 0.5, 0.2],
        blend_file=blend["path"],
        save_as="tests/material_applied.blend",
        target="headless",
    )
    assert report["ok"], report.get("error")
    execute = next(
        step
        for step in report["steps"]
        if isinstance(step.get("result"), dict) and step["result"].get("preset") == "metal"
    )
    assert execute["result"]["preset"] == "metal"
