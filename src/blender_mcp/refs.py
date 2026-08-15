"""Reference images that guide generation: stored under ``output/refs/``."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .config import Settings

IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"})
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def refs_root(settings: Settings) -> Path:
    root = settings.output_dir / "refs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def sanitize_name(name: str) -> str:
    cleaned = _SAFE.sub("_", name.strip()).strip("._")
    return cleaned or "reference"


def resolve_ref(settings: Settings, path: str) -> Path:
    """Resolve a reference path relative to ``output/refs`` (or absolute)."""
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    return refs_root(settings) / candidate


def list_references(settings: Settings, group: str = "") -> dict:
    root = refs_root(settings)
    search = root / group if group.strip() else root
    if not search.is_dir():
        return {"refs_dir": str(root), "group": group or None, "files": []}

    files = []
    for item in sorted(search.rglob("*")):
        if not item.is_file() or item.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        files.append(
            {
                "path": str(item.relative_to(root)).replace("\\", "/"),
                "bytes": item.stat().st_size,
            }
        )
    return {"refs_dir": str(root), "group": group or None, "files": files}


def add_reference(
    settings: Settings,
    source: str | Path,
    name: str = "",
    group: str = "",
) -> dict:
    """Copy an image into the refs library and return its library-relative path."""
    source_path = Path(source).expanduser()
    if not source_path.is_file():
        raise FileNotFoundError(f"No image at {source_path}")
    if source_path.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError(f"Unsupported image type {source_path.suffix!r}")

    dest_dir = refs_root(settings)
    if group.strip():
        dest_dir = dest_dir / sanitize_name(group)
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = sanitize_name(name) if name.strip() else sanitize_name(source_path.name)
    if not Path(filename).suffix:
        filename += source_path.suffix.lower()
    destination = dest_dir / filename

    counter = 1
    stem, suffix = destination.stem, destination.suffix
    while destination.exists():
        destination = dest_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    shutil.copy2(source_path, destination)
    relative = destination.relative_to(refs_root(settings)).as_posix()
    return {"path": relative, "absolute": str(destination), "bytes": destination.stat().st_size}


def write_reference_bytes(
    settings: Settings,
    data: bytes,
    filename: str,
    group: str = "",
) -> dict:
    """Write uploaded image bytes into the refs library."""
    dest_dir = refs_root(settings)
    if group.strip():
        dest_dir = dest_dir / sanitize_name(group)
    dest_dir.mkdir(parents=True, exist_ok=True)

    safe = sanitize_name(filename)
    if Path(safe).suffix.lower() not in IMAGE_SUFFIXES:
        safe += ".png"
    destination = dest_dir / safe

    counter = 1
    stem, suffix = destination.stem, destination.suffix
    while destination.exists():
        destination = dest_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    destination.write_bytes(data)
    relative = destination.relative_to(refs_root(settings)).as_posix()
    return {"path": relative, "absolute": str(destination), "bytes": len(data)}
