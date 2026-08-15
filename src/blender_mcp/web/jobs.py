"""Job persistence under ``output/jobs/<id>/``."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from blender_mcp.agent import llm_configured, run_agent_job
from blender_mcp.config import get_settings


def jobs_root() -> Path:
    root = get_settings().output_dir / "jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_job(prompt: str, reference_files: list[tuple[str, bytes]]) -> dict:
    job_id = uuid.uuid4().hex[:12]
    job_dir = jobs_root() / job_id
    (job_dir / "refs").mkdir(parents=True)
    (job_dir / "previews").mkdir()
    (job_dir / "final").mkdir()

    saved_refs = []
    for filename, data in reference_files:
        dest = job_dir / "refs" / Path(filename).name
        dest.write_bytes(data)
        saved_refs.append(dest.name)

    meta = {
        "id": job_id,
        "prompt": prompt,
        "status": "queued",
        "created_at": _now(),
        "updated_at": _now(),
        "refs": saved_refs,
        "log": [],
        "blend_path": None,
        "final_render": None,
        "error": None,
        "llm_ready": llm_configured(),
    }
    _write_meta(job_dir, meta)
    return meta


def _write_meta(job_dir: Path, meta: dict) -> None:
    (job_dir / "prompt.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def load_job(job_id: str) -> dict | None:
    job_dir = jobs_root() / job_id
    meta_path = job_dir / "prompt.json"
    if not meta_path.is_file():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["dir"] = str(job_dir)
    return meta


def list_jobs() -> list[dict]:
    jobs = []
    for path in sorted(jobs_root().iterdir(), reverse=True):
        if not path.is_dir():
            continue
        meta = load_job(path.name)
        if meta:
            jobs.append(meta)
    return jobs


def append_log(job_id: str, line: str) -> None:
    meta = load_job(job_id)
    if not meta:
        return
    meta.setdefault("log", []).append(line)
    meta["updated_at"] = _now()
    _write_meta(jobs_root() / job_id, {k: v for k, v in meta.items() if k != "dir"})


def start_job_async(job_id: str) -> None:
    thread = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
    thread.start()


def _run_job(job_id: str) -> None:
    meta = load_job(job_id)
    if not meta:
        return
    job_dir = jobs_root() / job_id
    meta["status"] = "running"
    meta["updated_at"] = _now()
    _write_meta(job_dir, {k: v for k, v in meta.items() if k != "dir"})

    def on_log(line: str) -> None:
        append_log(job_id, line)

    refs = [job_dir / "refs" / name for name in meta.get("refs") or []]
    result = run_agent_job(
        prompt=meta["prompt"],
        job_dir=job_dir,
        reference_paths=refs,
        on_log=on_log,
    )

    meta = load_job(job_id) or meta
    if result.ok:
        meta["status"] = "done"
        if result.error:
            meta["warning"] = result.error
    else:
        meta["status"] = "error"
        meta["error"] = result.error
    meta["blend_path"] = result.blend_path
    meta["final_render"] = result.final_render
    if not result.ok:
        meta["error"] = result.error
    meta["log"] = result.log
    meta["updated_at"] = _now()
    _write_meta(job_dir, {k: v for k, v in meta.items() if k != "dir"})
