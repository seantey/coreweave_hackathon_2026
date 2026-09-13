import asyncio, json, os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .models import Edit, ImageRegion, Camera
from .storage import (
    DATA,
    read_scene,
    list_scenes,
    propose,
    decide,
    scene_path,
    media_path,
    identifier,
    event,
    save_camera,
)
from .capture import capture

app = FastAPI(title="Clean Room Imputation", version="0.1.0")
JOBS = {}


@app.exception_handler(ValueError)
async def invalid_request(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "services": {
            "wandb_configured": bool(os.environ.get("WANDB_API_KEY")),
            "fal_configured": bool(os.environ.get("FAL_KEY")),
        },
    }


@app.get("/api/scenes")
def scenes():
    return [
        {
            "id": s.id,
            "title": s.title,
            "description": s.description,
            "source_kind": s.source_kind,
        }
        for s in list_scenes()
    ]


@app.get("/api/scenes/{scene_id}")
def scene(scene_id: str):
    try:
        return read_scene(scene_id)
    except FileNotFoundError:
        raise HTTPException(404, "Scene not found")


@app.get("/api/scenes/{scene_id}/events")
def events(scene_id: str):
    p = scene_path(scene_id).parent / "events.jsonl"
    return (
        [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []
    )


@app.get("/media/{path:path}")
def media(path: str):
    p = media_path(path)
    # Only serve browser assets, never provider response records or credential files.
    if p.suffix.lower() not in {
        ".png",
        ".jpg",
        ".jpeg",
        ".mp4",
        ".ply",
        ".spz",
        ".rad",
        ".glb",
        ".splat",
    }:
        raise HTTPException(403, "This file type is not exposed")
    if not p.is_file():
        raise HTTPException(404, "Asset not found")
    return FileResponse(p)


@app.post("/api/scenes/{scene_id}/edits")
def edit(scene_id: str, edit: Edit):
    revision = propose(scene_id, edit)
    event(scene_id, "manual_candidate", {"revision": revision.model_dump(mode="json")})
    return revision


class Decision(BaseModel):
    accept: bool
    reason: str = Field(min_length=5)


@app.post("/api/scenes/{scene_id}/revisions/{revision_id}/decision")
def decision(scene_id: str, revision_id: str, value: Decision):
    revision = decide(
        scene_id, revision_id, value.accept, {"source": "human", "reason": value.reason}
    )
    event(scene_id, "human_decision", {"revision": revision_id, **value.model_dump()})
    return revision


class CaptureRequest(BaseModel):
    camera: str
    revision: str | None = None
    region: ImageRegion | None = None


@app.post("/api/scenes/{scene_id}/capture")
def screenshot(scene_id: str, request: CaptureRequest):
    scene = read_scene(scene_id)
    if request.camera not in scene.cameras:
        raise HTTPException(422, "Unknown camera")
    result = capture(
        scene_id,
        request.revision or scene.current_revision,
        request.camera,
        request.region,
    )
    event(scene_id, "capture", result)
    return result


class LoopRequest(BaseModel):
    max_passes: int = Field(default=2, ge=1, le=5)


@app.post("/api/scenes/{scene_id}/loop")
async def loop(scene_id: str, request: LoopRequest):
    read_scene(scene_id)
    if any(
        j["scene_id"] == scene_id and j["status"] == "running" for j in JOBS.values()
    ):
        raise HTTPException(409, "A loop is already running for this scene")
    job = identifier("loop")
    JOBS[job] = {"id": job, "scene_id": scene_id, "status": "running"}

    async def work():
        try:

            def run():
                from .agent import run_traced_loop

                return run_traced_loop(scene_id, request.max_passes, job)

            result = await asyncio.to_thread(run)
            JOBS[job].update(status="completed", result=result)
        except Exception as exc:
            message = str(exc)
            for name in ("WANDB_API_KEY", "FAL_KEY"):
                if os.environ.get(name):
                    message = message.replace(os.environ[name], "[redacted]")
            JOBS[job].update(status="failed", error=message[:1000])
            event(scene_id, "loop_failed", {"job_id": job, "error": message[:1000]})

    asyncio.create_task(work())
    return JOBS[job]


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found in this server session")
    return JOBS[job_id]


class CameraRequest(BaseModel):
    camera: Camera
    reason: str = Field(min_length=5)


@app.post("/api/scenes/{scene_id}/cameras")
def register_camera(scene_id: str, request: CameraRequest):
    name = save_camera(scene_id, request.camera, request.reason)
    return {"name": name, "camera": request.camera.model_dump()}
