"""Entry point executed *inside* Blender by ``blender --background --python``.

Reads a job description from disk, replays its requests through the same handlers
the live addon uses, and writes the responses back out as JSON. Nothing here may
import from the ``blender_mcp`` package: it runs under Blender's own interpreter.
"""

from __future__ import annotations

import json
import sys
import traceback


def _job_path(argv: list[str]) -> str:
    if "--" not in argv:
        raise SystemExit("run_job.py expects the job file after a '--' separator")
    return argv[argv.index("--") + 1]


def main() -> None:
    job_file = _job_path(sys.argv)
    with open(job_file, encoding="utf-8") as handle:
        job = json.load(handle)

    result_file = job["result_path"]
    payload: dict = {"responses": []}
    try:
        sys.path.insert(0, job["addon_root"])
        from blender_mcp_addon import handlers

        if job.get("open"):
            payload["responses"].append(handlers.dispatch({"type": "open", "path": job["open"]}))
            if not payload["responses"][-1]["ok"]:
                _write(result_file, payload)
                return

        for request in job["requests"]:
            response = handlers.dispatch(request)
            payload["responses"].append(response)
            if not response.get("ok"):
                break
    except Exception:
        payload["fatal"] = traceback.format_exc()
    finally:
        _write(result_file, payload)


def _write(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


if __name__ == "__main__":
    main()
