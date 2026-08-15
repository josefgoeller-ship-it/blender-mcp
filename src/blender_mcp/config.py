"""Where Blender lives, where output goes, and how to reach a live session."""

from __future__ import annotations

import os
import re
import shutil
import string
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_VERSION_IN_NAME = re.compile(r"(\d+)\.(\d+)")


def project_root() -> Path:
    """The repository root, found by walking up to the directory holding pyproject.toml."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> None:
    """Populate os.environ from a .env file without pulling in a dependency.

    Values already present in the environment win, so a shell override still works.
    """
    env_file = path or project_root() / ".env"
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def _candidate_install_dirs() -> list[Path]:
    """Standard Blender install locations for the current platform."""
    if sys.platform == "win32":
        roots: list[Path] = []
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:\\")
            if not drive.exists():
                continue
            roots += [
                drive / "Program Files" / "Blender Foundation",
                drive / "Program Files (x86)" / "Blender Foundation",
                drive / "Program Files (x86)" / "Steam" / "steamapps" / "common" / "Blender",
            ]
        return roots
    if sys.platform == "darwin":
        return [Path("/Applications"), Path.home() / "Applications"]
    return [Path("/usr/share"), Path("/opt"), Path.home() / ".local" / "share"]


def _executable_name() -> str:
    return "blender.exe" if sys.platform == "win32" else "blender"


def _version_key(path: Path) -> tuple[int, int]:
    """Sort key so that 'Blender 5.1' beats 'Blender 4.2'."""
    for part in reversed(path.parts):
        match = _VERSION_IN_NAME.search(part)
        if match:
            return int(match.group(1)), int(match.group(2))
    return (0, 0)


def discover_blender() -> Path | None:
    """Locate a Blender executable, preferring the newest version installed."""
    on_path = shutil.which("blender")
    if on_path:
        return Path(on_path)

    found: list[Path] = []
    name = _executable_name()
    for root in _candidate_install_dirs():
        if not root.is_dir():
            continue
        try:
            found.extend(root.glob(f"*/{name}"))
            found.extend(root.glob("*/Contents/MacOS/Blender"))
        except OSError:
            continue
    if not found:
        return None
    return max(found, key=_version_key)


@dataclass(frozen=True)
class Settings:
    executable: Path
    output_dir: Path
    addon_root: Path
    host: str
    port: int
    timeout: float

    def resolve_output(self, path: str) -> Path:
        """Relative paths land in the output directory; absolute paths are honoured as given."""
        candidate = Path(path).expanduser()
        resolved = candidate if candidate.is_absolute() else self.output_dir / candidate
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved


class BlenderNotFound(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    root = project_root()

    configured = os.environ.get("BLENDER_MCP_EXECUTABLE", "").strip()
    executable = Path(configured) if configured else discover_blender()
    if executable is None:
        raise BlenderNotFound(
            "Could not find Blender. Set BLENDER_MCP_EXECUTABLE in .env to the full path "
            "of your blender executable."
        )
    if not Path(executable).is_file():
        raise BlenderNotFound(
            f"BLENDER_MCP_EXECUTABLE points at {executable}, which does not exist"
        )

    output_dir = Path(os.environ.get("BLENDER_MCP_OUTPUT_DIR") or root / "output").expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        executable=Path(executable),
        output_dir=output_dir,
        addon_root=root / "addon",
        host=os.environ.get("BLENDER_MCP_HOST", "127.0.0.1"),
        port=int(os.environ.get("BLENDER_MCP_PORT", "9876")),
        timeout=float(os.environ.get("BLENDER_MCP_TIMEOUT", "300")),
    )
