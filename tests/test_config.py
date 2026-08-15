from pathlib import Path

import pytest

from blender_mcp.config import Settings, _version_key, load_dotenv, project_root


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        executable=tmp_path / "blender.exe",
        output_dir=tmp_path / "out",
        addon_root=tmp_path / "addon",
        host="127.0.0.1",
        port=9876,
        timeout=30.0,
    )


def test_relative_paths_land_in_the_output_dir(tmp_path):
    settings = make_settings(tmp_path)
    assert settings.resolve_output("scene.blend") == tmp_path / "out" / "scene.blend"


def test_nested_relative_paths_get_their_parent_created(tmp_path):
    settings = make_settings(tmp_path)
    resolved = settings.resolve_output("shots/hero/scene.blend")
    assert resolved.parent.is_dir()


def test_absolute_paths_are_left_alone(tmp_path):
    settings = make_settings(tmp_path)
    elsewhere = tmp_path / "elsewhere" / "scene.blend"
    assert settings.resolve_output(str(elsewhere)) == elsewhere


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"), (5, 1)),
        (Path(r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"), (4, 2)),
        (Path("/usr/bin/blender"), (0, 0)),
    ],
)
def test_version_key_reads_the_version_from_the_install_folder(path, expected):
    assert _version_key(path) == expected


def test_newest_install_wins_when_sorting():
    installs = [
        Path(r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"),
        Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"),
        Path(r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe"),
    ]
    assert max(installs, key=_version_key).parent.name == "Blender 5.1"


def test_dotenv_does_not_override_the_real_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("BLENDER_MCP_PORT=1111\nBLENDER_MCP_HOST=10.0.0.1\n", encoding="utf-8")
    monkeypatch.setenv("BLENDER_MCP_PORT", "2222")
    monkeypatch.delenv("BLENDER_MCP_HOST", raising=False)

    load_dotenv(env_file)

    import os

    assert os.environ["BLENDER_MCP_PORT"] == "2222"
    assert os.environ["BLENDER_MCP_HOST"] == "10.0.0.1"


def test_project_root_is_the_directory_holding_pyproject():
    assert (project_root() / "pyproject.toml").is_file()
