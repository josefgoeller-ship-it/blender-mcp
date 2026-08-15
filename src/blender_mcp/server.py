"""MCP tools for building .blend files, either headlessly or in a live Blender session."""

from __future__ import annotations

import subprocess
from functools import lru_cache
from typing import Literal

from mcp.server.mcpserver import Image, MCPServer

from . import headless, materials, refs, templates
from .bridge import LiveBridge
from .config import Settings, get_settings

Target = Literal["auto", "live", "headless"]

INSTRUCTIONS = """
Create and edit Blender .blend files with a visual critique loop.

Routes (`target`):
  - headless — fresh background Blender (default for generating files)
  - live — drive the open Blender window if the MCP Bridge is running
  - auto — live when reachable, otherwise headless

Quality workflow (follow this unless the user asks otherwise):
  1. list_references / view_reference — look at any guide images first
  2. create_blend from a template (studio or product for lit shots)
  3. Build geometry in small run_script steps; use apply_material for presets
  4. preview_views — multi-angle EEVEE previews; compare to references
  5. Fix with run_script, then preview again
  6. Final render with higher samples (CYCLES only for finals); use
     render_and_view or view_image so you actually see the result

Prefer EEVEE for iteration. Use CYCLES only for the final still.
`run_script` has bpy, mathutils, math, D, C pre-bound. Assign `result` or call
`emit(value)` to report data. Call blender_status if unsure what is available.
""".strip()

server = MCPServer(
    name="blender",
    version="0.2.0",
    instructions=INSTRUCTIONS,
)


def _settings() -> Settings:
    return get_settings()


def _bridge() -> LiveBridge:
    return LiveBridge(_settings())


@lru_cache(maxsize=4)
def _blender_version(executable: str) -> str:
    try:
        completed = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unknown ({exc})"
    first_line = (completed.stdout or "").strip().splitlines()
    return first_line[0] if first_line else "unknown"


def _resolve_target(target: Target, needs_file: bool) -> str:
    """Decide between the live session and a background process."""
    if target == "live":
        return "live"
    if target == "headless" or needs_file:
        return "headless"
    return "live" if _bridge().is_available() else "headless"


def _run(requests: list[dict], target: Target, open_blend: str | None = None) -> dict:
    """Send requests to whichever Blender we settled on, stopping at the first failure."""
    mode = _resolve_target(target, needs_file=open_blend is not None)

    if mode == "live":
        bridge = _bridge()
        if open_blend:
            requests = [{"type": "open", "path": open_blend}, *requests]
        responses: list[dict] = []
        for request in requests:
            response = bridge.request(request)
            responses.append(response)
            if not response.get("ok"):
                break
        return {"target": "live", "responses": responses}

    outcome = headless.run_job(_settings(), requests, open_blend=open_blend)
    return {"target": "headless", "responses": outcome.responses, "blender_output": outcome.stdout}


def _merge(execution: dict) -> dict:
    """Flatten a run into one report the model can read without digging."""
    responses = execution["responses"]
    failed = next((item for item in responses if not item.get("ok")), None)
    report = {
        "ok": failed is None,
        "target": execution["target"],
        "steps": responses,
    }
    if failed is not None:
        report["error"] = failed.get("error", "unknown error")
        if execution.get("blender_output"):
            report["blender_output"] = execution["blender_output"]
    return report


@server.tool()
def blender_status() -> dict:
    """Report the Blender install, output folder, live-bridge state, templates and materials."""
    settings = _settings()
    bridge = _bridge()
    live = bridge.is_available()
    return {
        "executable": str(settings.executable),
        "version": _blender_version(str(settings.executable)),
        "output_dir": str(settings.output_dir),
        "refs_dir": str(refs.refs_root(settings)),
        "live_bridge": {
            "address": bridge.address,
            "connected": live,
            "hint": None
            if live
            else "Open Blender, press N in the 3D viewport, MCP tab, Start MCP Bridge",
        },
        "templates": templates.describe_templates(),
        "materials": materials.describe_presets(),
        "timeout_seconds": settings.timeout,
    }


@server.tool()
def list_references(group: str = "") -> dict:
    """List reference guide images under output/refs (optionally one group folder)."""
    return refs.list_references(_settings(), group=group)


@server.tool(structured_output=False)
def view_reference(path: str) -> Image:
    """Look at a reference/guide image so you can match it while modeling.

    Args:
        path: Path relative to output/refs, or absolute.
    """
    settings = _settings()
    resolved = refs.resolve_ref(settings, path)
    if not resolved.is_file():
        raise FileNotFoundError(f"No reference image at {resolved}")
    return Image(path=resolved)


def _resolve_source_path(settings: Settings, path: str):
    from pathlib import Path

    candidate = Path(path).expanduser()
    if candidate.is_file():
        return candidate
    return settings.resolve_output(path)


@server.tool()
def add_reference(source_path: str, name: str = "", group: str = "") -> dict:
    """Copy an image file into the reference library under output/refs.

    Args:
        source_path: Existing image on disk (absolute or under the output folder).
        name: Optional destination filename.
        group: Optional subfolder name for organising guides.
    """
    settings = _settings()
    source = _resolve_source_path(settings, source_path)
    return refs.add_reference(settings, source, name=name, group=group)


@server.tool()
def create_blend(
    path: str,
    template: str = "studio",
    script: str = "",
    compress: bool = True,
) -> dict:
    """Create a new .blend file from a starter template and save it.

    Args:
        path: Destination, relative to the output folder unless absolute.
            A ".blend" suffix is added when missing.
        template: empty, default, studio, or product.
        script: Optional extra bpy code run after the template.
        compress: Write a compressed .blend.
    """
    settings = _settings()
    destination = settings.resolve_output(path)
    if destination.suffix.lower() != ".blend":
        destination = destination.with_suffix(".blend")

    requests: list[dict] = [{"type": "execute", "code": templates.get_template(template)}]
    if script.strip():
        requests.append({"type": "execute", "code": script})
    requests.append({"type": "save_as", "path": str(destination), "compress": compress})

    report = _merge(_run(requests, target="headless"))
    if report["ok"]:
        report["path"] = str(destination)
    return report


@server.tool()
def run_script(
    code: str,
    blend_file: str = "",
    save_as: str = "",
    target: Target = "auto",
) -> dict:
    """Run Python against Blender's bpy API.

    `bpy`, `mathutils`, `math`, `D` and `C` are pre-bound. Assign to `result` or call
    `emit(value)` to send data back; print() output is captured too.

    Args:
        code: The Python to execute.
        blend_file: Open this .blend first. Supplying it forces a headless run.
        save_as: Save the file here when the script finishes.
        target: "auto", "live" or "headless".
    """
    settings = _settings()
    requests: list[dict] = [{"type": "execute", "code": code}]

    saved_to = None
    if save_as.strip():
        saved_to = settings.resolve_output(save_as)
        if saved_to.suffix.lower() != ".blend":
            saved_to = saved_to.with_suffix(".blend")
        requests.append({"type": "save_as", "path": str(saved_to)})

    open_blend = str(settings.resolve_output(blend_file)) if blend_file.strip() else None
    report = _merge(_run(requests, target=target, open_blend=open_blend))
    if saved_to is not None and report["ok"]:
        report["path"] = str(saved_to)
    return report


@server.tool()
def apply_material(
    object_name: str,
    preset: str,
    color: list[float] | None = None,
    blend_file: str = "",
    save_as: str = "",
    target: Target = "auto",
) -> dict:
    """Apply a procedural material preset (metal, plastic, rubber, glass, wood) to a mesh.

    Args:
        object_name: Mesh object name in the scene.
        preset: One of the presets from blender_status.materials.
        color: Optional RGB or RGBA floats 0-1.
        blend_file: Open this file first (forces headless).
        save_as: Save after applying.
        target: "auto", "live" or "headless".
    """
    code = materials.build_apply_script(object_name, preset, color)
    return run_script(code=code, blend_file=blend_file, save_as=save_as, target=target)


@server.tool()
def inspect_blend(
    blend_file: str = "",
    include_objects: bool = True,
    target: Target = "auto",
) -> dict:
    """Describe a scene: objects, transforms, materials, cameras, lights and render settings.

    Args:
        blend_file: Inspect this file. Leave empty to inspect the live session instead.
        include_objects: Include the per-object breakdown, not just the counts.
        target: Where to look when no file is given.
    """
    settings = _settings()
    open_blend = str(settings.resolve_output(blend_file)) if blend_file.strip() else None
    requests = [{"type": "scene_info", "include_objects": include_objects}]
    return _merge(_run(requests, target=target, open_blend=open_blend))


@server.tool()
def render(
    output: str = "render.png",
    blend_file: str = "",
    engine: str = "EEVEE",
    samples: int = 64,
    width: int = 960,
    height: int = 540,
    frame: int | None = None,
    transparent: bool = False,
    target: Target = "auto",
) -> dict:
    """Render a still image and write it to disk. Prefer render_and_view so you see it.

    Args:
        output: PNG destination, relative to the output folder unless absolute.
        blend_file: Render this file rather than the live session. Forces a headless run.
        engine: "EEVEE", "CYCLES" or "WORKBENCH". EEVEE for iteration; CYCLES for finals.
        samples: Sample count. Keep it low for previews.
        width: Output width in pixels.
        height: Output height in pixels.
        frame: Frame to render. Defaults to the scene's current frame.
        transparent: Render the world background as alpha.
        target: "auto", "live" or "headless".
    """
    settings = _settings()
    destination = settings.resolve_output(output)
    if destination.suffix.lower() != ".png":
        destination = destination.with_suffix(".png")

    request = {
        "type": "render",
        "path": str(destination),
        "engine": engine,
        "samples": samples,
        "resolution": [width, height],
        "transparent": transparent,
    }
    if frame is not None:
        request["frame"] = frame

    open_blend = str(settings.resolve_output(blend_file)) if blend_file.strip() else None
    report = _merge(_run([request], target=target, open_blend=open_blend))
    if report["ok"]:
        report["path"] = report["steps"][-1]["result"]["path"]
    return report


@server.tool(structured_output=False)
def render_and_view(
    output: str = "render.png",
    blend_file: str = "",
    engine: str = "EEVEE",
    samples: int = 32,
    width: int = 960,
    height: int = 540,
    target: Target = "auto",
) -> Image:
    """Render a still and return the image so you must look at it.

    Args:
        output: PNG destination under the output folder.
        blend_file: Optional .blend to open first.
        engine: Prefer EEVEE while iterating.
        samples: Sample count.
        width: Width in pixels.
        height: Height in pixels.
        target: "auto", "live" or "headless".
    """
    report = render(
        output=output,
        blend_file=blend_file,
        engine=engine,
        samples=samples,
        width=width,
        height=height,
        target=target,
    )
    if not report.get("ok"):
        raise RuntimeError(report.get("error", "render failed"))
    return Image(path=report["path"])


@server.tool()
def preview_views(
    blend_file: str,
    output_dir: str = "previews",
    width: int = 480,
    height: int = 270,
    samples: int = 16,
    engine: str = "EEVEE",
    target: Target = "headless",
) -> dict:
    """Render multi-angle EEVEE previews (front, three_quarter, side, top) for critique.

    Args:
        blend_file: .blend to open and preview.
        output_dir: Folder under output/ for the PNGs.
        width: Preview width.
        height: Preview height.
        samples: Low sample count for speed.
        engine: Prefer EEVEE.
        target: Usually headless.
    """
    settings = _settings()
    destination = settings.resolve_output(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    open_blend = str(settings.resolve_output(blend_file))
    request = {
        "type": "preview_views",
        "output_dir": str(destination),
        "width": width,
        "height": height,
        "samples": samples,
        "engine": engine,
    }
    report = _merge(_run([request], target=target, open_blend=open_blend))
    if report["ok"]:
        report["output_dir"] = str(destination)
        report["views"] = report["steps"][-1]["result"]["views"]
    return report


@server.tool(structured_output=False)
def view_preview(path: str) -> Image:
    """Look at one preview PNG from preview_views or a render.

    Args:
        path: Image path relative to output or absolute.
    """
    return view_image(path)


@server.tool()
def viewport_screenshot(output: str = "viewport.png") -> dict:
    """Capture the live Blender window's 3D viewport as it currently looks.

    Requires the MCP Bridge addon to be running in an open Blender session.
    """
    settings = _settings()
    destination = settings.resolve_output(output)
    if destination.suffix.lower() != ".png":
        destination = destination.with_suffix(".png")

    report = _merge(_run([{"type": "screenshot", "path": str(destination)}], target="live"))
    if report["ok"]:
        report["path"] = report["steps"][-1]["result"]["path"]
    return report


@server.tool(structured_output=False)
def view_image(path: str) -> Image:
    """Load a rendered image so it can actually be looked at.

    Args:
        path: Image path, relative to the output folder unless absolute.
    """
    settings = _settings()
    resolved = settings.resolve_output(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"No image at {resolved}")
    return Image(path=resolved)


@server.tool()
def list_outputs(pattern: str = "*") -> dict:
    """List the files produced so far in the output folder."""
    settings = _settings()
    entries = [
        {
            "path": str(item.relative_to(settings.output_dir)),
            "bytes": item.stat().st_size,
        }
        for item in sorted(settings.output_dir.rglob(pattern))
        if item.is_file() and ".jobs" not in item.parts
    ]
    return {"output_dir": str(settings.output_dir), "files": entries}


@server.tool()
def open_in_live_session(blend_file: str) -> dict:
    """Load a .blend into the Blender window the user has open, so they can see it."""
    settings = _settings()
    target_file = settings.resolve_output(blend_file)
    if not target_file.is_file():
        raise FileNotFoundError(f"No .blend at {target_file}")
    return _merge(_run([{"type": "open", "path": str(target_file)}], target="live"))


def main() -> None:
    server.run("stdio")
