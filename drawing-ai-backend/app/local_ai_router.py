import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from local_ai_clients import generate_stable_diffusion_image, queue_comfyui_workflow
from local_ai_config import BASE_DIR, load_local_ai_config
from service_manager import (
    get_all_service_statuses,
    restart_service,
    start_service,
    stop_service,
)
from sf3d_client import generate_3d_from_image


router = APIRouter(tags=["Local AI"])
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


@router.get("/splash", include_in_schema=False)
@router.get("/local-ai", include_in_schema=False)
def local_ai_launcher():
    return FileResponse(BASE_DIR / "static" / "local_ai.html")


@router.get("/local-ai/docs", include_in_schema=False)
def local_ai_docs():
    return FileResponse(BASE_DIR / "static" / "local_ai_docs.html")


@router.get("/api/local-ai/health")
async def local_ai_health() -> dict[str, Any]:
    services = await run_in_threadpool(get_all_service_statuses)
    return {
        "status": "ok",
        "controller": {
            "status": "running",
            "url": "http://127.0.0.1:8000",
        },
        "services": services,
    }


@router.get("/api/local-ai/services")
async def local_ai_services() -> dict[str, Any]:
    return {"services": await run_in_threadpool(get_all_service_statuses)}


def _service_action(
    service_name: str, action: Literal["start", "stop", "restart"]
) -> dict[str, Any]:
    functions = {
        "start": start_service,
        "stop": stop_service,
        "restart": restart_service,
    }
    result = functions[action](service_name)
    if "Unknown service" in str(result.get("error", "")):
        raise HTTPException(status_code=404, detail=result)
    return result


@router.post("/api/local-ai/services/{service_name}/start")
async def local_ai_start_service(service_name: str) -> dict[str, Any]:
    return await run_in_threadpool(_service_action, service_name, "start")


@router.post("/api/local-ai/services/{service_name}/stop")
async def local_ai_stop_service(service_name: str) -> dict[str, Any]:
    return await run_in_threadpool(_service_action, service_name, "stop")


@router.post("/api/local-ai/services/{service_name}/restart")
async def local_ai_restart_service(service_name: str) -> dict[str, Any]:
    return await run_in_threadpool(_service_action, service_name, "restart")


@router.post("/api/local-ai/sf3d/generate")
async def local_ai_sf3d_generate(
    image: UploadFile = File(...),
    remesh: Literal["none", "triangle", "quad"] = Form("triangle"),
    vertex_count: int = Form(3000),
    texture_resolution: int = Form(512),
    foreground_ratio: float = Form(0.85),
) -> dict[str, Any]:
    suffix = Path(image.filename or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="Unsupported image format.")
    config = load_local_ai_config()
    upload_dir = Path(config["output_path"]) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / f"{uuid.uuid4()}{suffix}"
    total = 0
    try:
        with upload_path.open("wb") as target:
            while chunk := await image.read(1024 * 1024):
                total += len(chunk)
                if total > 25 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="Image is too large.")
                target.write(chunk)
        result = await run_in_threadpool(
            generate_3d_from_image,
            upload_path,
            config["output_path"],
            {
                "remesh": remesh,
                "vertex_count": vertex_count,
                "texture_resolution": texture_resolution,
                "foreground_ratio": foreground_ratio,
            },
        )
    finally:
        await image.close()
        upload_path.unlink(missing_ok=True)
    if result.get("success"):
        glb_path = Path(result["glb_path"])
        result["glb_url"] = f"/outputs/local_ai/3d/{glb_path.name}"
        if result.get("preview_path"):
            preview_path = Path(result["preview_path"])
            result["preview_url"] = f"/outputs/local_ai/previews/{preview_path.name}"
    return result


@router.post("/api/local-ai/image/generate")
async def local_ai_image_generate(
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    return await run_in_threadpool(generate_stable_diffusion_image, dict(payload))


@router.post("/api/local-ai/workflow/run")
async def local_ai_workflow_run(
    workflow: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    return await run_in_threadpool(queue_comfyui_workflow, workflow)
