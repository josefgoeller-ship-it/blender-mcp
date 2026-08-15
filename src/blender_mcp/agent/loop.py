"""Bounded multimodal agent that drives blender_mcp tools with an LLM API key."""

from __future__ import annotations

import base64
import json
import os
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from blender_mcp import materials, refs, server
from blender_mcp.config import get_settings

LogFn = Callable[[str], None]


SYSTEM = """You are a Blender scene builder. You use tools to create .blend files that match
the user's prompt and any reference images.

Workflow:
1. If references were provided, you already see them — match silhouette, materials, colours.
2. create_blend with template studio or product.
3. Build geometry with run_script in small steps; use apply_material for presets.
4. preview_views then ask to view previews via view_image paths returned.
5. Fix with run_script; iterate.
6. Final render (CYCLES ok for final only) then stop with a short summary.

Prefer EEVEE while iterating. Keep scripts focused. When done, reply with DONE: and the
paths to the .blend and final PNG.
"""


@dataclass
class AgentResult:
    ok: bool
    job_dir: Path
    blend_path: str | None = None
    final_render: str | None = None
    log: list[str] = field(default_factory=list)
    error: str | None = None


def _log(lines: list[str], message: str, callback: LogFn | None) -> None:
    lines.append(message)
    if callback:
        callback(message)


def _image_b64(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    suffix = path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "image/png")
    return mime, base64.b64encode(data).decode("ascii")


TOOL_SPECS = [
    {
        "name": "create_blend",
        "description": "Create a new .blend from a template",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "template": {"type": "string", "enum": ["empty", "default", "studio", "product"]},
                "script": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_script",
        "description": "Run bpy Python against a blend file",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "blend_file": {"type": "string"},
                "save_as": {"type": "string"},
            },
            "required": ["code", "blend_file"],
        },
    },
    {
        "name": "apply_material",
        "description": "Apply a material preset to a mesh object",
        "parameters": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string"},
                "preset": {"type": "string", "enum": list(materials.PRESETS)},
                "color": {"type": "array", "items": {"type": "number"}},
                "blend_file": {"type": "string"},
                "save_as": {"type": "string"},
            },
            "required": ["object_name", "preset", "blend_file"],
        },
    },
    {
        "name": "preview_views",
        "description": "Multi-angle EEVEE previews for critique",
        "parameters": {
            "type": "object",
            "properties": {
                "blend_file": {"type": "string"},
                "output_dir": {"type": "string"},
            },
            "required": ["blend_file"],
        },
    },
    {
        "name": "render",
        "description": "Render a still PNG",
        "parameters": {
            "type": "object",
            "properties": {
                "output": {"type": "string"},
                "blend_file": {"type": "string"},
                "engine": {"type": "string"},
                "samples": {"type": "integer"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
            },
            "required": ["blend_file", "output"],
        },
    },
    {
        "name": "inspect_blend",
        "description": "Describe the scene contents",
        "parameters": {
            "type": "object",
            "properties": {"blend_file": {"type": "string"}},
            "required": ["blend_file"],
        },
    },
]


def _dispatch_tool(name: str, arguments: dict[str, Any], job_dir: Path) -> dict[str, Any]:
    if name == "create_blend":
        path = arguments.get("path") or str(job_dir / "scene.blend")
        if not Path(path).is_absolute():
            path = str(job_dir / Path(path).name)
        return server.create_blend(
            path=path,
            template=arguments.get("template", "studio"),
            script=arguments.get("script", ""),
        )
    if name == "run_script":
        return server.run_script(
            code=arguments["code"],
            blend_file=arguments.get("blend_file", ""),
            save_as=arguments.get("save_as", ""),
            target="headless",
        )
    if name == "apply_material":
        return server.apply_material(
            object_name=arguments["object_name"],
            preset=arguments["preset"],
            color=arguments.get("color"),
            blend_file=arguments.get("blend_file", ""),
            save_as=arguments.get("save_as", ""),
            target="headless",
        )
    if name == "preview_views":
        out = arguments.get("output_dir") or str(job_dir / "previews")
        if not Path(out).is_absolute():
            out = str(job_dir / "previews")
        return server.preview_views(
            blend_file=arguments["blend_file"],
            output_dir=out,
            width=480,
            height=270,
            samples=12,
            target="headless",
        )
    if name == "render":
        out = arguments.get("output") or str(job_dir / "final" / "render.png")
        if not Path(out).is_absolute():
            out = str(job_dir / "final" / Path(out).name)
        return server.render(
            output=out,
            blend_file=arguments["blend_file"],
            engine=arguments.get("engine", "EEVEE"),
            samples=int(arguments.get("samples", 64)),
            width=int(arguments.get("width", 1280)),
            height=int(arguments.get("height", 720)),
            target="headless",
        )
    if name == "inspect_blend":
        return server.inspect_blend(
            blend_file=arguments["blend_file"],
            target="headless",
        )
    return {"ok": False, "error": f"Unknown tool {name}"}


def _openai_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": spec["name"],
                "description": spec["description"],
                "parameters": spec["parameters"],
            },
        }
        for spec in TOOL_SPECS
    ]


def _anthropic_tools() -> list[dict]:
    return [
        {
            "name": spec["name"],
            "description": spec["description"],
            "input_schema": spec["parameters"],
        }
        for spec in TOOL_SPECS
    ]


def llm_configured() -> bool:
    get_settings()  # load dotenv
    return bool(os.environ.get("BLENDER_MCP_LLM_API_KEY", "").strip())


def run_agent_job(
    prompt: str,
    job_dir: Path,
    reference_paths: list[Path] | None = None,
    max_iterations: int = 8,
    on_log: LogFn | None = None,
) -> AgentResult:
    """Run a bounded tool loop. Requires BLENDER_MCP_LLM_API_KEY in the environment."""
    get_settings()
    provider = os.environ.get("BLENDER_MCP_LLM_PROVIDER", "openai").strip().lower()
    api_key = os.environ.get("BLENDER_MCP_LLM_API_KEY", "").strip()
    model = os.environ.get("BLENDER_MCP_LLM_MODEL", "").strip()
    log: list[str] = []

    if not api_key:
        return AgentResult(
            ok=False,
            job_dir=job_dir,
            log=log,
            error=(
                "No BLENDER_MCP_LLM_API_KEY set. Upload refs and run the job from Cursor, "
                "or add an API key to .env."
            ),
        )

    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "previews").mkdir(exist_ok=True)
    (job_dir / "final").mkdir(exist_ok=True)
    (job_dir / "refs").mkdir(exist_ok=True)

    settings = get_settings()
    ref_relatives: list[str] = []
    for path in reference_paths or []:
        if path.is_file():
            added = refs.add_reference(settings, path, group=job_dir.name)
            # Also keep a copy beside the job for the gallery.
            dest = job_dir / "refs" / path.name
            if not dest.exists():
                dest.write_bytes(path.read_bytes())
            ref_relatives.append(added["path"])

    _log(log, f"Starting job in {job_dir} with provider={provider}", on_log)

    try:
        if provider in ("openai", "openrouter", "compatible"):
            ref_paths = [
                job_dir / "refs" / path.name for path in (reference_paths or []) if path.is_file()
            ] or list((job_dir / "refs").glob("*"))
            return _run_openai_compatible(
                prompt=prompt,
                job_dir=job_dir,
                ref_paths=ref_paths,
                api_key=api_key,
                model=model or "gpt-4.1",
                base_url=os.environ.get(
                    "BLENDER_MCP_LLM_BASE_URL",
                    "https://api.openai.com/v1"
                    if provider == "openai"
                    else os.environ.get("BLENDER_MCP_LLM_BASE_URL", "https://api.openai.com/v1"),
                ),
                max_iterations=max_iterations,
                log=log,
                on_log=on_log,
            )
        if provider == "anthropic":
            return _run_anthropic(
                prompt=prompt,
                job_dir=job_dir,
                ref_paths=list((job_dir / "refs").glob("*")),
                api_key=api_key,
                model=model or "claude-sonnet-4-6",
                max_iterations=max_iterations,
                log=log,
                on_log=on_log,
            )
        return AgentResult(
            ok=False,
            job_dir=job_dir,
            log=log,
            error=f"Unknown BLENDER_MCP_LLM_PROVIDER {provider!r} (use openai or anthropic)",
        )
    except Exception as exc:
        _log(log, traceback.format_exc(), on_log)
        return AgentResult(ok=False, job_dir=job_dir, log=log, error=str(exc))


def _extract_paths(job_dir: Path, tool_results: list[dict]) -> tuple[str | None, str | None]:
    blend = None
    render = None
    for result in tool_results:
        if isinstance(result, dict):
            if result.get("path", "").endswith(".blend"):
                blend = result["path"]
            if result.get("path", "").endswith(".png") and "final" in result.get("path", ""):
                render = result["path"]
    finals = list((job_dir / "final").glob("*.png"))
    blends = list(job_dir.glob("*.blend"))
    if finals:
        render = str(finals[-1])
    if blends:
        blend = str(blends[-1])
    return blend, render


def _run_openai_compatible(
    *,
    prompt: str,
    job_dir: Path,
    ref_paths: list[Path],
    api_key: str,
    model: str,
    base_url: str,
    max_iterations: int,
    log: list[str],
    on_log: LogFn | None,
) -> AgentResult:
    user_content: list[dict] = [{"type": "text", "text": prompt}]
    for path in ref_paths:
        if path.suffix.lower() not in refs.IMAGE_SUFFIXES:
            continue
        mime, b64 = _image_b64(path)
        user_content.append(
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
        )

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_content},
    ]
    tool_results_acc: list[dict] = []
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    with httpx.Client(timeout=180.0) as client:
        for step in range(max_iterations):
            _log(log, f"LLM step {step + 1}/{max_iterations}", on_log)
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "tools": _openai_tools(),
                    "tool_choice": "auto",
                },
            )
            response.raise_for_status()
            payload = response.json()
            message = payload["choices"][0]["message"]
            messages.append(message)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                text = message.get("content") or ""
                _log(log, f"Assistant: {text[:500]}", on_log)
                blend, final = _extract_paths(job_dir, tool_results_acc)
                return AgentResult(
                    ok=True,
                    job_dir=job_dir,
                    blend_path=blend,
                    final_render=final,
                    log=log,
                )

            for call in tool_calls:
                name = call["function"]["name"]
                raw_args = call["function"].get("arguments") or "{}"
                arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                _log(log, f"Tool {name}({json.dumps(arguments)[:200]})", on_log)
                result = _dispatch_tool(name, arguments, job_dir)
                tool_results_acc.append(result)
                # Attach preview images back into the conversation for vision critique.
                follow_text = json.dumps(result, default=str)[:12_000]
                if name == "preview_views" and result.get("ok"):
                    follow_text += "\nPreview images saved at:\n" + "\n".join(
                        view["path"] for view in (result.get("views") or [])
                    )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": follow_text,
                    }
                )
                # Feed preview images as a follow-up user message for vision critique.
                vision_bits: list[dict] = []
                if name == "preview_views" and result.get("ok"):
                    for view in result.get("views") or []:
                        path = Path(view["path"])
                        if path.is_file():
                            mime, b64 = _image_b64(path)
                            vision_bits.append(
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                                }
                            )
                if name == "render" and result.get("ok") and result.get("path"):
                    path = Path(result["path"])
                    if path.is_file():
                        mime, b64 = _image_b64(path)
                        vision_bits.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"},
                            }
                        )
                if vision_bits:
                    messages.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Visual feedback from the last tool. Critique and fix.",
                                },
                                *vision_bits,
                            ],
                        }
                    )

    blend, final = _extract_paths(job_dir, tool_results_acc)
    return AgentResult(
        ok=True,
        job_dir=job_dir,
        blend_path=blend,
        final_render=final,
        log=log,
        error="Reached iteration limit",
    )


def _run_anthropic(
    *,
    prompt: str,
    job_dir: Path,
    ref_paths: list[Path],
    api_key: str,
    model: str,
    max_iterations: int,
    log: list[str],
    on_log: LogFn | None,
) -> AgentResult:
    user_content: list[dict] = []
    for path in ref_paths:
        if path.suffix.lower() not in refs.IMAGE_SUFFIXES:
            continue
        mime, b64 = _image_b64(path)
        user_content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": b64},
            }
        )
    user_content.append({"type": "text", "text": prompt})

    messages: list[dict] = [{"role": "user", "content": user_content}]
    tool_results_acc: list[dict] = []
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    with httpx.Client(timeout=180.0) as client:
        for step in range(max_iterations):
            _log(log, f"LLM step {step + 1}/{max_iterations}", on_log)
            response = client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json={
                    "model": model,
                    "max_tokens": 4096,
                    "system": SYSTEM,
                    "tools": _anthropic_tools(),
                    "messages": messages,
                },
            )
            response.raise_for_status()
            payload = response.json()
            content = payload.get("content") or []
            messages.append({"role": "assistant", "content": content})

            tool_uses = [block for block in content if block.get("type") == "tool_use"]
            if not tool_uses:
                text = "".join(
                    block.get("text", "") for block in content if block.get("type") == "text"
                )
                _log(log, f"Assistant: {text[:500]}", on_log)
                blend, final = _extract_paths(job_dir, tool_results_acc)
                return AgentResult(
                    ok=True,
                    job_dir=job_dir,
                    blend_path=blend,
                    final_render=final,
                    log=log,
                )

            tool_results_content: list[dict] = []
            for block in tool_uses:
                name = block["name"]
                arguments = block.get("input") or {}
                _log(log, f"Tool {name}({json.dumps(arguments)[:200]})", on_log)
                result = _dispatch_tool(name, arguments, job_dir)
                tool_results_acc.append(result)
                tool_results_content.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": json.dumps(result, default=str)[:12_000],
                    }
                )
                if name == "preview_views" and result.get("ok"):
                    for view in result.get("views") or []:
                        path = Path(view["path"])
                        if path.is_file():
                            mime, b64 = _image_b64(path)
                            tool_results_content.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block["id"],
                                    "content": [
                                        {
                                            "type": "image",
                                            "source": {
                                                "type": "base64",
                                                "media_type": mime,
                                                "data": b64,
                                            },
                                        }
                                    ],
                                }
                            )
            messages.append({"role": "user", "content": tool_results_content})

    blend, final = _extract_paths(job_dir, tool_results_acc)
    return AgentResult(
        ok=True,
        job_dir=job_dir,
        blend_path=blend,
        final_render=final,
        log=log,
        error="Reached iteration limit",
    )
