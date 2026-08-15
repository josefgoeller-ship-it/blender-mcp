"""Local FastAPI UI for reference uploads and generation jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from blender_mcp.agent import llm_configured
from blender_mcp.config import get_settings
from blender_mcp.web import jobs as jobstore

PACKAGE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))

app = FastAPI(title="blender-mcp", version="0.2.0")
app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "llm_ready": llm_configured(),
            "recent": jobstore.list_jobs()[:8],
        },
    )


@app.post("/generate")
async def generate(
    prompt: Annotated[str, Form()],
    references: Annotated[list[UploadFile] | None, File()] = None,
) -> RedirectResponse:
    files: list[tuple[str, bytes]] = []
    for upload in references or []:
        if not upload.filename:
            continue
        data = await upload.read()
        if data:
            files.append((upload.filename, data))

    meta = jobstore.create_job(prompt.strip(), files)
    if meta["llm_ready"]:
        jobstore.start_job_async(meta["id"])
    return RedirectResponse(url=f"/jobs/{meta['id']}", status_code=303)


@app.get("/jobs", response_class=HTMLResponse)
async def library(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "library.html",
        {"jobs": jobstore.list_jobs(), "llm_ready": llm_configured()},
    )


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: str) -> HTMLResponse:
    meta = jobstore.load_job(job_id)
    if not meta:
        raise HTTPException(404, "Job not found")
    job_dir = Path(meta["dir"])
    preview_dir = job_dir / "previews"
    final_dir = job_dir / "final"
    refs_dir = job_dir / "refs"
    previews = sorted(preview_dir.glob("*.png")) if preview_dir.is_dir() else []
    finals = sorted(final_dir.glob("*.png")) if final_dir.is_dir() else []
    refs = sorted(refs_dir.glob("*")) if refs_dir.is_dir() else []
    return templates.TemplateResponse(
        request,
        "job.html",
        {
            "job": meta,
            "previews": [p.name for p in previews],
            "finals": [p.name for p in finals],
            "refs": [p.name for p in refs],
            "llm_ready": llm_configured(),
        },
    )


@app.post("/jobs/{job_id}/start")
async def start_job(job_id: str) -> RedirectResponse:
    meta = jobstore.load_job(job_id)
    if not meta:
        raise HTTPException(404, "Job not found")
    if not llm_configured():
        raise HTTPException(400, "Set BLENDER_MCP_LLM_API_KEY in .env to run from the web UI")
    jobstore.start_job_async(job_id)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.get("/jobs/{job_id}/files/{folder}/{filename}")
async def job_file(job_id: str, folder: str, filename: str) -> FileResponse:
    if folder not in {"refs", "previews", "final"}:
        raise HTTPException(404)
    path = jobstore.jobs_root() / job_id / folder / filename
    if not path.is_file():
        # also allow .blend at job root
        if folder == "final":
            alt = jobstore.jobs_root() / job_id / filename
            if alt.is_file():
                return FileResponse(alt)
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/jobs/{job_id}/blend")
async def download_blend(job_id: str) -> FileResponse:
    meta = jobstore.load_job(job_id)
    if not meta:
        raise HTTPException(404)
    if meta.get("blend_path") and Path(meta["blend_path"]).is_file():
        return FileResponse(meta["blend_path"], filename=Path(meta["blend_path"]).name)
    blends = list((jobstore.jobs_root() / job_id).glob("*.blend"))
    if not blends:
        raise HTTPException(404, "No .blend yet")
    return FileResponse(blends[-1], filename=blends[-1].name)


def create_app() -> FastAPI:
    get_settings()
    return app


def main() -> None:
    import uvicorn

    get_settings()
    uvicorn.run(
        "blender_mcp.web.app:app",
        host="127.0.0.1",
        port=int(__import__("os").environ.get("BLENDER_MCP_WEB_PORT", "8765")),
        reload=False,
    )


if __name__ == "__main__":
    main()
