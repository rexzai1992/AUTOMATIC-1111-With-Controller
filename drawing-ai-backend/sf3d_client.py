import shutil
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from PIL import Image, UnidentifiedImageError

from local_ai_config import get_service_config
from service_manager import start_service, wait_for_health


def health_check() -> dict[str, Any]:
    service = get_service_config("sf3d")
    try:
        response = requests.get(str(service["health_url"]), timeout=5)
        payload = response.json()
        return {
            "healthy": response.ok and bool(payload.get("model_loaded")),
            "status_code": response.status_code,
            "payload": payload,
        }
    except (requests.RequestException, ValueError) as exc:
        return {"healthy": False, "error": str(exc)}


def _failure(stage: str, error: str, details: Any = None) -> dict[str, Any]:
    return {
        "success": False,
        "service": "sf3d",
        "stage": stage,
        "error": error,
        "details": details,
    }


def _download(url: str, output_path: Path, timeout: int = 120) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".part")
    try:
        with requests.get(url, stream=True, timeout=timeout) as response:
            response.raise_for_status()
            with temporary.open("wb") as target:
                shutil.copyfileobj(response.raw, target)
        if not temporary.exists() or temporary.stat().st_size <= 0:
            raise RuntimeError("Downloaded file is empty.")
        temporary.replace(output_path)
        return output_path
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def download_glb(job_id: str, output_path: str | Path) -> str:
    service = get_service_config("sf3d")
    url = f"{str(service['url']).rstrip('/')}/download/{job_id}"
    return str(_download(url, Path(output_path)))


def download_preview(job_id: str, output_path: str | Path) -> str:
    service = get_service_config("sf3d")
    url = f"{str(service['url']).rstrip('/')}/preview/{job_id}"
    return str(_download(url, Path(output_path)))


def generate_3d_from_image(
    image_path: str | Path,
    output_dir: str | Path,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    image_path = Path(image_path)
    if not image_path.is_file():
        return _failure("validate_image", "Image does not exist.", str(image_path))
    try:
        with Image.open(image_path) as probe:
            probe.verify()
    except (UnidentifiedImageError, OSError) as exc:
        return _failure("validate_image", "Invalid image.", str(exc))

    service = get_service_config("sf3d")
    health = health_check()
    if not health["healthy"]:
        if not service.get("autostart_on_generate", True):
            return _failure("health_check", "SF3D API is not running.", health)
        started = start_service("sf3d")
        if not started.get("success"):
            return _failure("autostart", "Failed to start SF3D API.", started)
        ready = wait_for_health(
            str(service["health_url"]),
            min(int(service.get("timeout_seconds", 600)), 180),
        )
        if not ready["healthy"]:
            return _failure("autostart", "SF3D API did not become healthy.", ready)

    settings = dict(service.get("defaults") or {})
    if options:
        settings.update({k: v for k, v in options.items() if v is not None})
    timeout = int(service.get("timeout_seconds", 600))
    try:
        with image_path.open("rb") as handle:
            response = requests.post(
                f"{str(service['url']).rstrip('/')}/generate",
                files={"image": (image_path.name, handle)},
                data=settings,
                timeout=timeout,
            )
        response.raise_for_status()
        payload = response.json()
    except requests.Timeout as exc:
        return _failure("upload", "SF3D generation timed out.", str(exc))
    except (requests.RequestException, ValueError) as exc:
        details = getattr(exc, "response", None)
        return _failure(
            "upload",
            "SF3D upload/generation failed.",
            details.text[:1000] if details is not None else str(exc),
        )

    job_id = str(payload.get("job_id") or "")
    glb_url = str(payload.get("glb_url") or "")
    if not job_id:
        return _failure("parse_response", "SF3D response is missing job_id.", payload)
    if not glb_url:
        return _failure("parse_response", "SF3D response is missing glb_url.", payload)

    output_root = Path(output_dir)
    glb_path = output_root / "3d" / f"sf3d-{job_id}.glb"
    preview_path = output_root / "previews" / f"sf3d-{job_id}.png"
    base_url = f"{str(service['url']).rstrip('/')}/"
    try:
        _download(urljoin(base_url, glb_url.lstrip("/")), glb_path)
    except Exception as exc:
        return _failure("download_glb", "Failed to download GLB.", str(exc))
    if not glb_path.exists() or glb_path.stat().st_size <= 0:
        return _failure("validate_glb", "GLB is missing or empty.", str(glb_path))

    preview_result: str | None = None
    preview_url = str(payload.get("preview_url") or "")
    if preview_url:
        try:
            _download(urljoin(base_url, preview_url.lstrip("/")), preview_path)
            preview_result = str(preview_path)
        except Exception:
            preview_result = None

    return {
        "success": True,
        "service": "sf3d",
        "job_id": job_id,
        "glb_path": str(glb_path),
        "preview_path": preview_result,
        "processing_time_seconds": payload.get("processing_time_seconds"),
        "settings": payload.get("settings", settings),
        "api_response": payload,
    }
