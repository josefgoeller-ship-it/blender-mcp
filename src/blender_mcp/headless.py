"""Runs a batch of requests in a throwaway background Blender process.

Each call starts Blender with ``--factory-startup`` so results never depend on
whatever the user happens to have configured, runs the requests in order, and
stops at the first failure.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import Settings

RUNNER = Path(__file__).parent / "runtime" / "run_job.py"
STDOUT_TAIL = 4_000


class HeadlessError(RuntimeError):
    pass


@dataclass
class JobResult:
    responses: list[dict]
    stdout: str

    @property
    def ok(self) -> bool:
        return bool(self.responses) and all(response.get("ok") for response in self.responses)

    @property
    def last(self) -> dict:
        if not self.responses:
            raise HeadlessError("Blender produced no responses")
        return self.responses[-1]


def run_job(
    settings: Settings,
    requests: list[dict],
    open_blend: str | Path | None = None,
    timeout: float | None = None,
) -> JobResult:
    scratch = settings.output_dir / ".jobs"
    scratch.mkdir(parents=True, exist_ok=True)

    job_id = uuid.uuid4().hex[:12]
    job_file = scratch / f"{job_id}.job.json"
    result_file = scratch / f"{job_id}.result.json"

    job = {
        "addon_root": str(settings.addon_root),
        "result_path": str(result_file),
        "open": str(open_blend) if open_blend else None,
        "requests": requests,
    }
    job_file.write_text(json.dumps(job), encoding="utf-8")

    command = [
        str(settings.executable),
        "--background",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(RUNNER),
        "--",
        str(job_file),
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout or settings.timeout,
            cwd=tempfile.gettempdir(),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HeadlessError(
            f"Blender did not finish within {timeout or settings.timeout:.0f}s. "
            "Raise BLENDER_MCP_TIMEOUT for heavy renders."
        ) from exc

    stdout = (completed.stdout or "") + (completed.stderr or "")
    if not result_file.is_file():
        raise HeadlessError(
            f"Blender exited with code {completed.returncode} without writing a result.\n"
            f"--- Blender output (tail) ---\n{stdout[-STDOUT_TAIL:]}"
        )

    payload = json.loads(result_file.read_text(encoding="utf-8"))
    for temporary in (job_file, result_file):
        temporary.unlink(missing_ok=True)

    if "fatal" in payload:
        raise HeadlessError(f"The job crashed inside Blender:\n{payload['fatal']}")

    return JobResult(responses=payload["responses"], stdout=stdout[-STDOUT_TAIL:])
