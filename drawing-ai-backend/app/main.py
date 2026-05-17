import asyncio
import contextlib
import hmac
import html
import json
import logging
import secrets
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import cv2
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field, conint, validator
from starlette.concurrency import run_in_threadpool

from app.config import (
    ALLOWED_UPLOAD_EXTENSIONS,
    API_KEY,
    BASE_DIR,
    CORS_ALLOW_CREDENTIALS,
    CORS_ALLOW_HEADERS,
    CORS_ALLOW_METHODS,
    CORS_ALLOWED_ORIGINS,
    ENABLE_FOLDER_WATCHER,
    GALLERY_JSON_PATH,
    GENERATION_DEFAULTS,
    INPUT_DIR,
    OUTPUT_DIR,
    QUEUE_JSON_PATH,
    SCANNER_INPUT_DIR,
    SD_CONFIG,
    STATIC_DIR,
    TEMP_DIR,
)
from app.detector import DetectionResult, PresetSettings, analyze_image
from app.gallery_store import GalleryStore
from app.generator import (
    StableDiffusionError,
    StableDiffusionGenerator,
    StableDiffusionUnavailableError,
)
from app.queue_store import QueueStore, utc_now_iso
from app.scanner_service import ScannerService
from app.websocket_manager import WebSocketManager


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("drawing-ai-backend")

app = FastAPI(title="drawing-ai-backend", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=CORS_ALLOW_METHODS,
    allow_headers=CORS_ALLOW_HEADERS,
)

app.mount("/inputs", StaticFiles(directory=str(INPUT_DIR)), name="inputs")
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

ws_manager = WebSocketManager()
sd_generator = StableDiffusionGenerator()
gallery_store = GalleryStore(GALLERY_JSON_PATH)
queue_store = QueueStore(QUEUE_JSON_PATH)

queue_worker_task: Optional[asyncio.Task] = None
queue_worker_stop = False
queue_current_job_id: Optional[str] = None
queue_status_lock = asyncio.Lock()
api_key_state_lock = threading.Lock()

API_KEY_STATE_PATH = BASE_DIR / "data" / "api_key_state.json"
API_DOCS_MARKDOWN_PATH = BASE_DIR / "docs" / "API.md"

ALLOWED_FEEDBACK_TAGS = {
    "too_close_to_drawing",
    "changed_too_much",
    "not_lively_enough",
    "too_realistic",
    "too_cartoon",
    "bad_face",
    "bad_hands",
    "bad_colors",
    "too_dark",
    "too_empty",
    "good_preserve_shape",
    "good_lively",
    "good_colors",
    "good_overall",
}

BAD_FEEDBACK_TAGS = {
    "too_close_to_drawing",
    "changed_too_much",
    "not_lively_enough",
    "too_realistic",
    "too_cartoon",
    "bad_face",
    "bad_hands",
    "bad_colors",
    "too_dark",
    "too_empty",
}

GOOD_FEEDBACK_TAGS = {
    "good_preserve_shape",
    "good_lively",
    "good_colors",
    "good_overall",
}

KNOWN_PRESETS = [
    "toddler_abstract_people",
    "kid_crayon",
    "sketch_lineart",
    "colored_drawing",
    "rough_low_color_drawing",
    "default",
]
DEFAULT_GENERATION_ESTIMATE_SECONDS = 60
MAX_RETRY_COUNT = 3

ALLOWED_REGENERATE_PROBLEM_TAGS = {
    "not_lively_enough",
    "changed_too_much",
    "bad_face",
    "bad_hands",
    "bad_colors",
    "too_dark",
    "artwork_changed",
    "person_changed",
}

REGENERATE_BRIGHT_PROMPT = (
    "bright lighting, warm sunlight, vivid palette, colorful cheerful scene"
)
REGENERATE_FACE_NEGATIVE = (
    "bad face, deformed face, asymmetrical face, distorted face, malformed eyes"
)
REGENERATE_HAND_NEGATIVE = (
    "bad hands, malformed hands, extra fingers, fused fingers, extra limbs"
)

DEFAULT_GENERATION_MODE = "drawing_to_artwork"
DEFAULT_STYLE_ID = "auto"
API_KEY_HEADER = "X-API-Key"


class RatingRequest(BaseModel):
    rating: conint(ge=1, le=5)  # type: ignore[valid-type]
    feedbackTags: List[str] = Field(default_factory=list)
    feedbackNote: str = ""

    @validator("feedbackTags")
    def validate_feedback_tags(cls, value: List[str]) -> List[str]:
        unique = []
        seen = set()
        for tag in value:
            normalized = tag.strip()
            if not normalized:
                continue
            if normalized not in ALLOWED_FEEDBACK_TAGS:
                raise ValueError(f"Invalid feedback tag: {normalized}")
            if normalized not in seen:
                seen.add(normalized)
                unique.append(normalized)
        return unique

    @validator("feedbackNote")
    def normalize_feedback_note(cls, value: str) -> str:
        return (value or "").strip()


class GalleryRenameRequest(BaseModel):
    visitorName: str = ""

    @validator("visitorName")
    def normalize_visitor_name(cls, value: str) -> str:
        return _normalize_visitor_name(value)


class GalleryVisibilityRequest(BaseModel):
    hidden: bool = False


class RegenerateRequest(BaseModel):
    problemTags: List[str] = Field(default_factory=list)

    @validator("problemTags")
    def validate_problem_tags(cls, value: List[str]) -> List[str]:
        cleaned: List[str] = []
        seen: Set[str] = set()
        for tag in value:
            normalized = str(tag or "").strip()
            if not normalized:
                continue
            if normalized not in ALLOWED_REGENERATE_PROBLEM_TAGS:
                raise ValueError(f"Invalid regenerate problem tag: {normalized}")
            if normalized not in seen:
                seen.add(normalized)
                cleaned.append(normalized)
        return cleaned


class CleanupRequest(BaseModel):
    olderThanDays: Optional[int] = Field(default=None, ge=1)
    keepNewest: Optional[int] = Field(default=None, ge=1)


def _normalize_visitor_name(value: Optional[str]) -> str:
    cleaned = (value or "").strip()
    return cleaned if cleaned else "Guest"


def _normalize_generation_mode(value: Optional[str]) -> str:
    cleaned = str(value or "").strip()
    return cleaned if cleaned else DEFAULT_GENERATION_MODE


def _normalize_style_id(value: Optional[str]) -> str:
    cleaned = str(value or "").strip()
    return cleaned if cleaned else DEFAULT_STYLE_ID


def _normalize_source(value: Optional[str]) -> str:
    cleaned = str(value or "").strip().lower()
    if cleaned == "api":
        return "api"
    return "staff"


def _to_public_image_url(request: Request, url_value: Any, absolute: bool) -> str:
    raw = str(url_value or "").strip()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if not absolute or not raw.startswith("/"):
        return raw
    return f"{str(request.base_url).rstrip('/')}{raw}"


def _with_absolute_image_urls(request: Request, payload: Dict[str, Any], absolute: bool) -> Dict[str, Any]:
    if not absolute:
        return dict(payload)
    output = dict(payload)
    for key in ("inputUrl", "outputUrl", "beforeImageUrl", "afterImageUrl"):
        if key in output:
            output[key] = _to_public_image_url(request, output.get(key), absolute=True)
    return output


def _find_queue_position(jobs: List[Dict[str, Any]], job_id: str) -> int:
    queued_jobs = [job for job in jobs if str(job.get("status") or "") == "queued"]
    queued_jobs.sort(
        key=lambda item: (
            str(item.get("queuedAt") or item.get("createdAt") or ""),
            str(item.get("createdAt") or ""),
        )
    )
    for index, job in enumerate(queued_jobs, start=1):
        if str(job.get("jobId") or "") == job_id:
            return index
    return 0


def _read_api_key_state_unlocked() -> Dict[str, Any]:
    try:
        raw = API_KEY_STATE_PATH.read_text(encoding="utf-8").strip()
        if raw:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _write_api_key_state_unlocked(api_key_value: str) -> None:
    API_KEY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "apiKey": str(api_key_value or "").strip(),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    API_KEY_STATE_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def _initialize_api_key_state() -> None:
    config_key = str(API_KEY or "").strip()
    with api_key_state_lock:
        state = _read_api_key_state_unlocked()
        stored_key = str(state.get("apiKey") or "").strip()
        if not API_KEY_STATE_PATH.exists():
            stored_key = config_key
            _write_api_key_state_unlocked(stored_key)
        elif not state:
            stored_key = config_key
            _write_api_key_state_unlocked(stored_key)
    app.state.api_key = stored_key


def _get_active_api_key() -> str:
    return str(getattr(app.state, "api_key", str(API_KEY or "").strip()) or "").strip()


def _set_active_api_key(api_key_value: str, *, persist: bool = True) -> str:
    cleaned = str(api_key_value or "").strip()
    app.state.api_key = cleaned
    if persist:
        with api_key_state_lock:
            _write_api_key_state_unlocked(cleaned)
    return cleaned


def _mask_api_key(api_key_value: str) -> str:
    cleaned = str(api_key_value or "").strip()
    if not cleaned:
        return "(empty)"
    if len(cleaned) <= 8:
        return "*" * len(cleaned)
    return f"{cleaned[:4]}...{cleaned[-4:]}"


def _require_admin_api_access(
    request: Request,
    *,
    x_api_key: Optional[str] = None,
    query_api_key: Optional[str] = None,
    form_api_key: Optional[str] = None,
) -> None:
    active_key = _get_active_api_key()
    if not active_key:
        return
    provided = str(x_api_key or query_api_key or form_api_key or "").strip()
    if not provided or not hmac.compare_digest(provided, active_key):
        raise HTTPException(
            status_code=401,
            detail=f"Missing or invalid {API_KEY_HEADER}. Use header {API_KEY_HEADER} or query/form apiKey.",
        )


def _require_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER),
) -> None:
    configured_key = _get_active_api_key()
    if not configured_key:
        return
    provided_key = str(x_api_key or request.headers.get(API_KEY_HEADER, "")).strip()
    if not provided_key or not hmac.compare_digest(provided_key, configured_key):
        raise HTTPException(status_code=401, detail=f"Missing or invalid {API_KEY_HEADER} header.")


def _resolve_extension(upload: UploadFile) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix in ALLOWED_UPLOAD_EXTENSIONS:
        return suffix
    return ".png"


def _save_upload_as_png(upload_bytes: bytes, destination: Path) -> None:
    with Image.open(BytesIO(upload_bytes)) as image:
        image.convert("RGB").save(destination, format="PNG")


def _capture_webcam_to_png(destination: Path) -> None:
    backend = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY
    capture = cv2.VideoCapture(0, backend)
    if not capture.isOpened():
        capture.release()
        raise RuntimeError("Unable to access webcam index 0.")

    frame = None
    for _ in range(5):
        success, candidate = capture.read()
        if success:
            frame = candidate

    capture.release()

    if frame is None:
        raise RuntimeError("Webcam capture failed to read a frame.")

    if not cv2.imwrite(str(destination), frame):
        raise RuntimeError(f"Failed to save webcam capture to {destination}.")


def _move_or_convert_scanner_image(source_path: Path, destination: Path) -> None:
    source_ext = source_path.suffix.lower()
    if source_ext == ".png":
        try:
            source_path.replace(destination)
            return
        except OSError:
            logger.warning("Fallback to copy for scanner file: %s", source_path)

    with Image.open(source_path) as image:
        image.convert("RGB").save(destination, format="PNG")

    try:
        source_path.unlink()
    except OSError:
        logger.warning("Unable to remove scanner source file after import: %s", source_path)


def _job_paths(job_id: str) -> tuple[Path, Path]:
    return INPUT_DIR / f"{job_id}.png", OUTPUT_DIR / f"{job_id}.png"


def _build_generation_settings(preset: PresetSettings) -> Dict[str, Any]:
    return {
        "checkpoint": SD_CONFIG.checkpoint,
        "presetName": preset.name,
        "controlNetModel": SD_CONFIG.controlnet_model,
        "controlNetModule": SD_CONFIG.controlnet_module,
        "controlWeight": preset.control_weight,
        "denoisingStrength": preset.denoising_strength,
        "controlMode": preset.control_mode,
        "steps": preset.steps,
        "cfgScale": preset.cfg_scale,
        "width": GENERATION_DEFAULTS.width,
        "height": GENERATION_DEFAULTS.height,
        "samplerName": preset.sampler_name,
    }


def _merge_generation_settings(
    preset: PresetSettings,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    settings = _build_generation_settings(preset)
    if overrides:
        for key, value in overrides.items():
            if value is not None:
                settings[key] = value

    def _as_float(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    def _as_int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    settings["controlWeight"] = _as_float(settings.get("controlWeight"), float(preset.control_weight))
    settings["denoisingStrength"] = _as_float(
        settings.get("denoisingStrength"), float(preset.denoising_strength)
    )
    settings["cfgScale"] = _as_float(settings.get("cfgScale"), float(preset.cfg_scale))
    settings["steps"] = _as_int(settings.get("steps"), int(preset.steps))
    settings["width"] = _as_int(settings.get("width"), int(GENERATION_DEFAULTS.width))
    settings["height"] = _as_int(settings.get("height"), int(GENERATION_DEFAULTS.height))
    settings["samplerName"] = str(settings.get("samplerName") or preset.sampler_name)
    settings["controlMode"] = str(settings.get("controlMode") or preset.control_mode)
    return settings


def _build_detection_payload(detection: DetectionResult) -> Dict[str, float]:
    return {
        "colorRatio": float(detection.metrics.colorRatio),
        "edgeRatio": float(detection.metrics.edgeRatio),
        "whiteBackgroundRatio": float(detection.metrics.whiteBackgroundRatio),
        "roughness": float(detection.metrics.roughness),
    }


def _build_gallery_item(
    *,
    job_id: str,
    visitor_name: str,
    created_at: str,
    started_at: str,
    completed_at: str,
    duration_seconds: float,
    estimated_seconds: int,
    input_url: str,
    output_url: str,
    preset: PresetSettings,
    detection_payload: Optional[Dict[str, float]] = None,
    generation_settings: Optional[Dict[str, Any]] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    prompt_mode = preset.prompt_mode
    item_generation_settings = generation_settings or _build_generation_settings(preset)
    item = {
        "jobId": job_id,
        "visitorName": visitor_name,
        "source": "staff",
        "preset": preset.name,
        "promptMode": prompt_mode,
        "promptType": prompt_mode,
        "inputUrl": input_url,
        "outputUrl": output_url,
        "createdAt": created_at,
        "startedAt": started_at,
        "completedAt": completed_at,
        "durationSeconds": duration_seconds,
        "estimatedSeconds": estimated_seconds,
        "detection": detection_payload or {},
        "generationSettings": item_generation_settings,
        "prompt": preset.prompt,
        "negativePrompt": preset.negative_prompt,
        "hidden": False,
        "hiddenAt": None,
        "updatedAt": None,
        "rating": None,
        "feedbackTags": [],
        "feedbackNote": "",
        "ratedAt": None,
        "generationMode": DEFAULT_GENERATION_MODE,
        "styleId": DEFAULT_STYLE_ID,
    }
    if extra_fields:
        item.update(extra_fields)
    item["source"] = _normalize_source(item.get("source"))
    return item


def _build_generation_complete_event(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "generation_complete",
        "jobId": item["jobId"],
        "visitorName": item["visitorName"],
        "source": _normalize_source(item.get("source")),
        "generationMode": item.get("generationMode"),
        "styleId": item.get("styleId"),
        "preset": item["preset"],
        "promptMode": item["promptMode"],
        "promptType": item["promptMode"],
        "inputUrl": item["inputUrl"],
        "outputUrl": item["outputUrl"],
        "createdAt": item["createdAt"],
        "startedAt": item.get("startedAt"),
        "completedAt": item.get("completedAt"),
        "durationSeconds": item.get("durationSeconds"),
        "estimatedSeconds": item.get("estimatedSeconds"),
        "detection": item["detection"],
        "generationSettings": item["generationSettings"],
        "hidden": bool(item.get("hidden", False)),
        "hiddenAt": item.get("hiddenAt"),
        "updatedAt": item.get("updatedAt"),
        "rating": item.get("rating"),
    }


async def _broadcast_error(job_id: str, error_message: str) -> None:
    await ws_manager.broadcast(
        {
            "type": "generation_error",
            "jobId": job_id,
            "error": error_message,
        }
    )


async def _run_generation_pipeline(
    job_id: str,
    visitor_name: str,
    input_path: Path,
    estimate_payload: Optional[Dict[str, Any]] = None,
    *,
    preset_override: Optional[PresetSettings] = None,
    detection_payload_override: Optional[Dict[str, float]] = None,
    persist_result: bool = True,
    created_at_override: Optional[str] = None,
    extra_item_fields: Optional[Dict[str, Any]] = None,
    generation_settings_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    started_at_dt = datetime.now(timezone.utc)
    started_at = started_at_dt.isoformat()

    if estimate_payload is None:
        estimate_payload = await run_in_threadpool(
            gallery_store.get_duration_estimate,
            DEFAULT_GENERATION_ESTIMATE_SECONDS,
        )

    estimated_seconds = int(
        estimate_payload.get("estimatedSeconds", DEFAULT_GENERATION_ESTIMATE_SECONDS)
    )

    detection: Optional[DetectionResult] = None
    if preset_override is None:
        detection = await run_in_threadpool(analyze_image, input_path)
        preset = detection.preset
        detection_payload = _build_detection_payload(detection)
    else:
        preset = preset_override
        detection_payload = detection_payload_override or {}

    output_path = OUTPUT_DIR / f"{job_id}.png"
    prompt_mode = preset.prompt_mode
    resolved_generation_settings = _merge_generation_settings(preset, generation_settings_override)

    logger.info(
        "Job %s started for visitor=%s preset=%s",
        job_id,
        visitor_name,
        preset.name,
    )
    logger.info("Detected preset: %s", preset.name)
    logger.info("Prompt mode: %s", prompt_mode)

    await run_in_threadpool(
        sd_generator.generate_image,
        input_path,
        output_path,
        preset,
        resolved_generation_settings,
    )

    completed_at_dt = datetime.now(timezone.utc)
    completed_at = completed_at_dt.isoformat()
    duration_seconds = round((completed_at_dt - started_at_dt).total_seconds(), 3)
    created_at = created_at_override or completed_at
    input_url = f"/inputs/{input_path.name}"
    output_url = f"/outputs/{output_path.name}"

    item = _build_gallery_item(
        job_id=job_id,
        visitor_name=visitor_name,
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=duration_seconds,
        estimated_seconds=estimated_seconds,
        input_url=input_url,
        output_url=output_url,
        preset=preset,
        detection_payload=detection_payload,
        generation_settings=resolved_generation_settings,
        extra_fields=extra_item_fields,
    )

    if persist_result:
        await run_in_threadpool(gallery_store.add_item, item)
        await ws_manager.broadcast(_build_generation_complete_event(item))

    logger.info("Job %s completed for visitor=%s", job_id, visitor_name)
    return {
        **item,
        "estimate": estimate_payload,
        "status": "completed",
        "outputPath": str(output_path),
        "inputPath": str(input_path),
    }


def _build_queue_job(
    *,
    job_id: str,
    visitor_name: str,
    input_path: Path,
    source: str,
    estimate_payload: Dict[str, Any],
    generation_mode: Optional[str] = None,
    style_id: Optional[str] = None,
    original_job_id: Optional[str] = None,
    regeneration_of: Optional[str] = None,
    version: int = 1,
    problem_tags: Optional[List[str]] = None,
    retry_count: int = 0,
    preset_override: Optional[PresetSettings] = None,
    detection_payload: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    now = utc_now_iso()
    input_url = f"/inputs/{input_path.name}"
    output_path = OUTPUT_DIR / f"{job_id}.png"
    output_url = f"/outputs/{output_path.name}"
    resolved_generation_mode = _normalize_generation_mode(generation_mode)
    resolved_style_id = _normalize_style_id(style_id)

    preset_name = ""
    prompt_mode = ""
    prompt_text = ""
    negative_text = ""
    generation_settings: Optional[Dict[str, Any]] = None
    if preset_override is not None:
        preset_name = preset_override.name
        prompt_mode = preset_override.prompt_mode
        prompt_text = preset_override.prompt
        negative_text = preset_override.negative_prompt
        generation_settings = _build_generation_settings(preset_override)

    return {
        "jobId": job_id,
        "visitorName": visitor_name,
        "status": "queued",
        "createdAt": now,
        "queuedAt": now,
        "startedAt": None,
        "completedAt": None,
        "failedAt": None,
        "cancelledAt": None,
        "durationSeconds": None,
        "estimatedSeconds": int(
            estimate_payload.get("estimatedSeconds", DEFAULT_GENERATION_ESTIMATE_SECONDS)
        ),
        "retryCount": retry_count,
        "maxRetries": MAX_RETRY_COUNT,
        "permanentlyFailed": False,
        "cancelRequested": False,
        "deleteRequested": False,
        "error": None,
        "source": _normalize_source(source),
        "generationMode": resolved_generation_mode,
        "styleId": resolved_style_id,
        "inputPath": str(input_path),
        "inputUrl": input_url,
        "outputPath": str(output_path),
        "outputUrl": output_url,
        "preset": preset_name,
        "promptMode": prompt_mode,
        "promptType": prompt_mode,
        "prompt": prompt_text,
        "negativePrompt": negative_text,
        "generationSettings": generation_settings,
        "detection": detection_payload or {},
        "originalJobId": original_job_id or job_id,
        "regenerationOf": regeneration_of,
        "version": version,
        "problemTags": list(problem_tags or []),
    }


def _preset_from_job(job: Dict[str, Any]) -> Optional[PresetSettings]:
    generation_settings = job.get("generationSettings") or {}
    prompt = str(job.get("prompt") or "").strip()
    negative_prompt = str(job.get("negativePrompt") or "").strip()
    preset_name = str(job.get("preset") or "").strip() or "default"
    prompt_mode = str(job.get("promptMode") or job.get("promptType") or "").strip() or "custom"

    if not prompt or not negative_prompt:
        return None

    try:
        control_weight = float(generation_settings.get("controlWeight"))
        denoising_strength = float(generation_settings.get("denoisingStrength"))
    except (TypeError, ValueError):
        return None

    control_mode = str(generation_settings.get("controlMode") or "Balanced")
    cfg_scale = _safe_float(generation_settings.get("cfgScale"))
    if cfg_scale <= 0:
        cfg_scale = float(GENERATION_DEFAULTS.cfg_scale)
    steps = int(_safe_float(generation_settings.get("steps")) or GENERATION_DEFAULTS.steps)
    if steps <= 0:
        steps = int(GENERATION_DEFAULTS.steps)
    sampler_name = str(generation_settings.get("samplerName") or GENERATION_DEFAULTS.sampler_name)
    return PresetSettings(
        name=preset_name,
        control_weight=control_weight,
        denoising_strength=denoising_strength,
        control_mode=control_mode,
        cfg_scale=cfg_scale,
        steps=steps,
        sampler_name=sampler_name,
        prompt=prompt,
        negative_prompt=negative_prompt,
        prompt_mode=prompt_mode,
    )


async def _queue_status_payload() -> Dict[str, Any]:
    snapshot = await run_in_threadpool(queue_store.queue_snapshot)
    estimate = await run_in_threadpool(
        gallery_store.get_duration_estimate,
        DEFAULT_GENERATION_ESTIMATE_SECONDS,
    )
    estimated_seconds = int(
        estimate.get("estimatedSeconds", DEFAULT_GENERATION_ESTIMATE_SECONDS)
    )
    queue_length = int(snapshot.get("queueLength") or 0)
    current_job = snapshot.get("processing")
    estimated_wait = queue_length * estimated_seconds
    if current_job:
        estimated_wait += estimated_seconds
    return {
        "queueLength": queue_length,
        "currentJob": (current_job or {}).get("jobId") if current_job else None,
        "estimatedWaitSeconds": int(estimated_wait),
        "jobs": [_job_to_public_payload(job) for job in snapshot.get("jobs", [])],
    }


async def _broadcast_queue_updated() -> None:
    status_payload = await _queue_status_payload()
    await ws_manager.broadcast({"type": "queue_updated", **status_payload})


async def _enqueue_job(job: Dict[str, Any]) -> Dict[str, Any]:
    await run_in_threadpool(queue_store.create_job, job)
    await _broadcast_queue_updated()
    return job


async def _run_scanner_job(scanner_file_path: Path, visitor_name: str) -> None:
    job_id = uuid.uuid4().hex
    normalized_name = _normalize_visitor_name(visitor_name)
    input_path, _ = _job_paths(job_id)

    try:
        await run_in_threadpool(_move_or_convert_scanner_image, scanner_file_path, input_path)
        estimate_payload = await run_in_threadpool(
            gallery_store.get_duration_estimate,
            DEFAULT_GENERATION_ESTIMATE_SECONDS,
        )
        job = _build_queue_job(
            job_id=job_id,
            visitor_name=normalized_name,
            input_path=input_path,
            source="scanner",
            estimate_payload=estimate_payload,
        )
        await _enqueue_job(job)
    except Exception as exc:
        logger.exception("Scanner job failed for file=%s", scanner_file_path)
        await _broadcast_error(job_id, str(exc))


def _schedule_scanner_job(scanner_file_path: Path, visitor_name: str) -> None:
    app_loop = getattr(app.state, "event_loop", None)
    if app_loop is None:
        logger.error("Event loop not available; scanner job skipped for %s", scanner_file_path)
        return

    future = asyncio.run_coroutine_threadsafe(
        _run_scanner_job(scanner_file_path, visitor_name),
        app_loop,
    )

    def _log_future_error(task_future) -> None:
        try:
            exception = task_future.exception()
        except Exception as exc:
            logger.error("Scanner job future inspection failed: %s", exc)
            return
        if exception:
            logger.error("Scanner job coroutine error: %s", exception)

    future.add_done_callback(_log_future_error)


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_many(tag_count: int, rated_count: int) -> bool:
    if rated_count <= 0:
        return False
    return tag_count >= 2 or (tag_count / rated_count) >= 0.35


def _generate_recommendations(tag_counter: Counter, rated_count: int, preset_name: str) -> List[str]:
    recommendations: List[str] = []

    too_close_score = tag_counter["too_close_to_drawing"] + tag_counter["not_lively_enough"]
    if _is_many(too_close_score, rated_count):
        recommendations.append(
            f"{preset_name} has many close/not lively outputs. Try increasing denoisingStrength by 0.05-0.1, "
            f"decreasing controlWeight by 0.05-0.1, and using 'My prompt is more important'."
        )

    changed_too_much_score = tag_counter["changed_too_much"]
    if _is_many(changed_too_much_score, rated_count):
        recommendations.append(
            f"{preset_name} changes composition too much. Try decreasing denoisingStrength by 0.05-0.1, "
            f"increasing controlWeight by 0.05-0.1, and using 'Balanced'."
        )

    if _is_many(tag_counter["too_realistic"], rated_count):
        recommendations.append(
            f"{preset_name} trends too realistic. Strengthen storybook/cartoon prompt language and keep "
            f"'photorealistic' in the negative prompt."
        )

    face_hand_score = tag_counter["bad_face"] + tag_counter["bad_hands"]
    if _is_many(face_hand_score, rated_count):
        recommendations.append(
            f"{preset_name} has frequent face/hand issues. Add stronger face/hand negative terms and slightly "
            f"lower denoisingStrength; enable face restoration only if needed."
        )

    color_dark_score = tag_counter["bad_colors"] + tag_counter["too_dark"]
    if _is_many(color_dark_score, rated_count):
        recommendations.append(
            f"{preset_name} has color/brightness issues. Reinforce vibrant warm palette in prompt and consider "
            f"a slight CFG scale increase."
        )

    return recommendations


def _build_tuning_summary(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_images = len(items)
    rated_items = [item for item in items if _safe_int(item.get("rating")) is not None]
    rated_count = len(rated_items)
    average_rating = (
        round(sum(_safe_int(item.get("rating")) or 0 for item in rated_items) / rated_count, 3)
        if rated_count > 0
        else 0
    )

    by_preset: Dict[str, Dict[str, Any]] = {}
    low_rated_items: List[Dict[str, Any]] = []
    global_bad_counter: Counter = Counter()
    global_good_counter: Counter = Counter()

    def _new_preset_stats() -> Dict[str, Any]:
        return {
            "count": 0,
            "ratedCount": 0,
            "averageRating": 0,
            "averageControlWeight": 0,
            "averageDenoisingStrength": 0,
            "commonBadTags": [],
            "commonGoodTags": [],
            "_ratingSum": 0.0,
            "_controlWeightSum": 0.0,
            "_denoiseSum": 0.0,
            "_badCounter": Counter(),
            "_goodCounter": Counter(),
        }

    for preset_name in KNOWN_PRESETS:
        by_preset[preset_name] = _new_preset_stats()

    for item in items:
        preset = str(item.get("preset") or "unknown")
        stats = by_preset.setdefault(
            preset,
            {
                **_new_preset_stats(),
            },
        )

        stats["count"] += 1
        generation_settings = item.get("generationSettings") or {}
        stats["_controlWeightSum"] += _safe_float(generation_settings.get("controlWeight"))
        stats["_denoiseSum"] += _safe_float(generation_settings.get("denoisingStrength"))

        rating = _safe_int(item.get("rating"))
        if rating is not None:
            stats["ratedCount"] += 1
            stats["_ratingSum"] += rating
            tags = [str(tag) for tag in item.get("feedbackTags", []) if isinstance(tag, str)]
            for tag in tags:
                if tag in BAD_FEEDBACK_TAGS:
                    stats["_badCounter"][tag] += 1
                    global_bad_counter[tag] += 1
                if tag in GOOD_FEEDBACK_TAGS:
                    stats["_goodCounter"][tag] += 1
                    global_good_counter[tag] += 1

            if rating <= 2:
                low_rated_items.append(
                    {
                        "jobId": item.get("jobId"),
                        "visitorName": item.get("visitorName"),
                        "preset": item.get("preset"),
                        "rating": rating,
                        "feedbackTags": item.get("feedbackTags", []),
                        "feedbackNote": item.get("feedbackNote", ""),
                        "inputUrl": item.get("inputUrl"),
                        "outputUrl": item.get("outputUrl"),
                        "detection": item.get("detection", {}),
                        "generationSettings": item.get("generationSettings", {}),
                        "prompt": item.get("prompt", ""),
                        "negativePrompt": item.get("negativePrompt", ""),
                    }
                )

    recommendations: List[str] = []
    for preset, stats in by_preset.items():
        count = stats["count"]
        rated_for_preset = stats["ratedCount"]
        stats["averageControlWeight"] = round(stats["_controlWeightSum"] / count, 4) if count > 0 else 0
        stats["averageDenoisingStrength"] = round(stats["_denoiseSum"] / count, 4) if count > 0 else 0
        stats["averageRating"] = (
            round(stats["_ratingSum"] / rated_for_preset, 3) if rated_for_preset > 0 else 0
        )
        stats["commonBadTags"] = [tag for tag, _ in stats["_badCounter"].most_common(5)]
        stats["commonGoodTags"] = [tag for tag, _ in stats["_goodCounter"].most_common(5)]

        recommendations.extend(_generate_recommendations(stats["_badCounter"], rated_for_preset, preset))

        del stats["_ratingSum"]
        del stats["_controlWeightSum"]
        del stats["_denoiseSum"]
        del stats["_badCounter"]
        del stats["_goodCounter"]

    if not recommendations and rated_count > 0:
        recommendations.append(
            "No strong failure trend detected yet. Continue rating more samples to improve tuning confidence."
        )
    if rated_count == 0:
        recommendations.append("No rated images yet. Add ratings first to generate tuning recommendations.")

    low_rated_items.sort(
        key=lambda item: (
            _safe_int(item.get("rating")) or 5,
            str(item.get("jobId") or ""),
        )
    )

    return {
        "totalImages": total_images,
        "ratedImages": rated_count,
        "averageRating": average_rating,
        "byPreset": by_preset,
        "lowRatedItems": low_rated_items,
        "recommendations": recommendations,
        "_globalBadTags": global_bad_counter,
        "_globalGoodTags": global_good_counter,
    }


def _url_to_local_path(url: Any) -> str:
    if not isinstance(url, str) or not url.startswith("/"):
        return ""
    parts = [part for part in url.strip("/").split("/") if part]
    return str(BASE_DIR.joinpath(*parts))


def _delete_local_gallery_file(url: Any) -> None:
    if not isinstance(url, str) or not url.startswith("/"):
        return

    parts = [part for part in url.strip("/").split("/") if part]
    if not parts:
        return

    try:
        candidate = BASE_DIR.joinpath(*parts).resolve()
    except OSError:
        return

    allowed_roots = (INPUT_DIR.resolve(), OUTPUT_DIR.resolve())
    if not any(root == candidate or root in candidate.parents for root in allowed_roots):
        return

    if not candidate.is_file():
        return

    try:
        candidate.unlink()
    except OSError:
        logger.warning("Unable to delete gallery file: %s", candidate)


def _build_tuning_text_report(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("DRAWING AI TUNING REPORT")
    lines.append(f"Generated At: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append(f"Total generated images: {summary['totalImages']}")
    lines.append(f"Total rated images: {summary['ratedImages']}")
    lines.append(f"Average rating: {summary['averageRating']}")
    lines.append("")
    lines.append("Average rating by preset:")
    for preset_name, stats in summary["byPreset"].items():
        lines.append(
            f"- {preset_name}: avgRating={stats['averageRating']} rated={stats['ratedCount']}/{stats['count']} "
            f"avgControlWeight={stats['averageControlWeight']} avgDenoising={stats['averageDenoisingStrength']}"
        )

    global_bad_counter: Counter = summary.get("_globalBadTags", Counter())
    global_good_counter: Counter = summary.get("_globalGoodTags", Counter())
    lines.append("")
    lines.append(f"Most common bad feedback tags: {[tag for tag, _ in global_bad_counter.most_common(10)]}")
    lines.append(f"Most common good feedback tags: {[tag for tag, _ in global_good_counter.most_common(10)]}")

    lines.append("")
    lines.append("Recommendations:")
    for recommendation in summary["recommendations"]:
        lines.append(f"- {recommendation}")

    lines.append("")
    lines.append("Generation settings by preset:")
    for preset_name, stats in summary["byPreset"].items():
        lines.append(
            f"- {preset_name}: avgControlWeight={stats['averageControlWeight']} avgDenoising={stats['averageDenoisingStrength']}"
        )

    lines.append("")
    lines.append("Prompts used (from low-rated examples):")
    prompt_set = []
    for item in summary["lowRatedItems"]:
        prompt_text = str(item.get("prompt") or "").strip()
        if prompt_text and prompt_text not in prompt_set:
            prompt_set.append(prompt_text)
        if len(prompt_set) >= 10:
            break
    if not prompt_set:
        lines.append("- No low-rated prompts available yet.")
    else:
        for prompt_text in prompt_set:
            lines.append(f"- {prompt_text}")

    lines.append("")
    lines.append("10 lowest-rated examples:")
    low_rated_items = summary["lowRatedItems"][:10]
    if not low_rated_items:
        lines.append("- No low-rated items yet.")
    for item in low_rated_items:
        lines.append("")
        lines.append(f"jobId: {item.get('jobId')}")
        lines.append(f"preset: {item.get('preset')}")
        lines.append(f"rating: {item.get('rating')}")
        lines.append(f"feedbackTags: {item.get('feedbackTags', [])}")
        lines.append(f"feedbackNote: {item.get('feedbackNote', '')}")
        lines.append(f"detection: {item.get('detection', {})}")
        lines.append(f"generationSettings: {item.get('generationSettings', {})}")
        lines.append(f"prompt: {item.get('prompt', '')}")
        lines.append(f"negativePrompt: {item.get('negativePrompt', '')}")
        lines.append(f"inputUrl: {item.get('inputUrl', '')}")
        lines.append(f"outputUrl: {item.get('outputUrl', '')}")
        lines.append(f"inputPath: {_url_to_local_path(item.get('inputUrl'))}")
        lines.append(f"outputPath: {_url_to_local_path(item.get('outputUrl'))}")

    return "\n".join(lines).strip() + "\n"


def _job_to_public_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "jobId",
        "visitorName",
        "status",
        "createdAt",
        "queuedAt",
        "startedAt",
        "completedAt",
        "failedAt",
        "cancelledAt",
        "durationSeconds",
        "estimatedSeconds",
        "retryCount",
        "maxRetries",
        "permanentlyFailed",
        "cancelRequested",
        "error",
        "generationMode",
        "styleId",
        "source",
        "inputUrl",
        "outputUrl",
        "preset",
        "promptMode",
        "promptType",
        "generationSettings",
        "originalJobId",
        "regenerationOf",
        "version",
        "problemTags",
    )
    payload = {key: job.get(key) for key in keys}
    payload["source"] = _normalize_source(payload.get("source"))
    return payload


def _gallery_item_to_job_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "jobId": item.get("jobId"),
        "status": "completed",
        "visitorName": item.get("visitorName"),
        "generationMode": item.get("generationMode"),
        "styleId": item.get("styleId"),
        "source": _normalize_source(item.get("source")),
        "inputUrl": item.get("inputUrl"),
        "outputUrl": item.get("outputUrl"),
        "createdAt": item.get("createdAt"),
        "startedAt": item.get("startedAt"),
        "completedAt": item.get("completedAt"),
        "durationSeconds": item.get("durationSeconds"),
        "error": None,
    }


def _build_api_job_payload(job: Dict[str, Any], request: Request, absolute: bool) -> Dict[str, Any]:
    payload = {
        "jobId": str(job.get("jobId") or ""),
        "status": str(job.get("status") or "queued"),
        "visitorName": _normalize_visitor_name(job.get("visitorName")),
        "generationMode": _normalize_generation_mode(job.get("generationMode")),
        "styleId": _normalize_style_id(job.get("styleId")),
        "source": _normalize_source(job.get("source")),
        "inputUrl": str(job.get("inputUrl") or ""),
        "outputUrl": str(job.get("outputUrl") or ""),
        "createdAt": job.get("createdAt"),
        "startedAt": job.get("startedAt"),
        "completedAt": job.get("completedAt"),
        "durationSeconds": float(_safe_float(job.get("durationSeconds"))),
        "error": job.get("error"),
    }
    return _with_absolute_image_urls(request, payload, absolute)


def _build_api_gallery_item(item: Dict[str, Any], request: Request, absolute: bool) -> Dict[str, Any]:
    payload = dict(item)
    payload["generationMode"] = _normalize_generation_mode(payload.get("generationMode"))
    payload["styleId"] = _normalize_style_id(payload.get("styleId"))
    payload["source"] = _normalize_source(payload.get("source"))
    payload["status"] = str(payload.get("status") or "completed")
    payload["inputUrl"] = str(payload.get("inputUrl") or "")
    payload["outputUrl"] = str(payload.get("outputUrl") or "")
    return _with_absolute_image_urls(request, payload, absolute)


async def _update_job_with_completed_result(job: Dict[str, Any], result_item: Dict[str, Any]) -> Dict[str, Any]:
    updates = {
        "status": "completed",
        "error": None,
        "startedAt": result_item.get("startedAt"),
        "completedAt": result_item.get("completedAt"),
        "durationSeconds": result_item.get("durationSeconds"),
        "estimatedSeconds": result_item.get("estimatedSeconds"),
        "inputUrl": result_item.get("inputUrl"),
        "outputUrl": result_item.get("outputUrl"),
        "preset": result_item.get("preset"),
        "promptMode": result_item.get("promptMode"),
        "promptType": result_item.get("promptType"),
        "prompt": result_item.get("prompt"),
        "negativePrompt": result_item.get("negativePrompt"),
        "generationSettings": result_item.get("generationSettings"),
        "detection": result_item.get("detection"),
        "createdAt": result_item.get("createdAt"),
        "generationMode": result_item.get("generationMode"),
        "styleId": result_item.get("styleId"),
        "source": _normalize_source(result_item.get("source")),
    }
    return await run_in_threadpool(
        queue_store.update_job_fields,
        str(job.get("jobId") or ""),
        updates,
    )


async def _mark_job_failed(job_id: str, error_message: str) -> Dict[str, Any]:
    job = await run_in_threadpool(queue_store.get_job, job_id)
    retry_count = int((job or {}).get("retryCount") or 0)
    permanently_failed = retry_count >= MAX_RETRY_COUNT
    updates = {
        "status": "failed",
        "failedAt": utc_now_iso(),
        "error": error_message,
        "permanentlyFailed": permanently_failed,
    }
    return await run_in_threadpool(queue_store.update_job_fields, job_id, updates)


async def _mark_job_cancelled(job_id: str, reason: str) -> Dict[str, Any]:
    updates = {
        "status": "cancelled",
        "cancelledAt": utc_now_iso(),
        "error": reason,
    }
    return await run_in_threadpool(queue_store.update_job_fields, job_id, updates)


async def _delete_job_artifacts(job_id: str) -> Dict[str, Any]:
    job = await run_in_threadpool(queue_store.get_job, job_id)

    removed_gallery_item = None
    try:
        removed_gallery_item = await run_in_threadpool(gallery_store.delete_item, job_id)
    except KeyError:
        removed_gallery_item = None

    if job:
        await run_in_threadpool(_delete_local_gallery_file, job.get("inputUrl"))
        await run_in_threadpool(_delete_local_gallery_file, job.get("outputUrl"))
        input_path = Path(str(job.get("inputPath") or ""))
        output_path = Path(str(job.get("outputPath") or ""))
        if input_path.is_file():
            try:
                input_path.unlink()
            except OSError:
                logger.warning("Unable to delete input file: %s", input_path)
        if output_path.is_file():
            try:
                output_path.unlink()
            except OSError:
                logger.warning("Unable to delete output file: %s", output_path)

    if removed_gallery_item:
        await run_in_threadpool(_delete_local_gallery_file, removed_gallery_item.get("inputUrl"))
        await run_in_threadpool(_delete_local_gallery_file, removed_gallery_item.get("outputUrl"))

    removed_job = await run_in_threadpool(queue_store.delete_job, job_id)
    await ws_manager.broadcast({"type": "gallery_item_deleted", "jobId": job_id})
    return {"deleted": bool(removed_job or removed_gallery_item), "jobId": job_id}


def _apply_regenerate_adjustments(
    *,
    base_preset: PresetSettings,
    problem_tags: List[str],
) -> PresetSettings:
    control_weight = float(base_preset.control_weight)
    denoising = float(base_preset.denoising_strength)
    prompt = str(base_preset.prompt)
    negative_prompt = str(base_preset.negative_prompt)

    for tag in problem_tags:
        if tag == "not_lively_enough":
            denoising += 0.08
            control_weight -= 0.08
        elif tag == "changed_too_much":
            denoising -= 0.08
            control_weight += 0.08
        elif tag == "bad_face":
            denoising -= 0.05
            negative_prompt = f"{negative_prompt}, {REGENERATE_FACE_NEGATIVE}"
        elif tag == "bad_hands":
            denoising -= 0.05
            negative_prompt = f"{negative_prompt}, {REGENERATE_HAND_NEGATIVE}"
        elif tag == "too_dark":
            prompt = f"{prompt}. {REGENERATE_BRIGHT_PROMPT}."
        elif tag == "artwork_changed":
            denoising -= 0.08
            control_weight += 0.1
        elif tag == "person_changed":
            denoising -= 0.1

    denoising = max(0.25, min(0.75, denoising))
    control_weight = max(0.45, min(1.0, control_weight))

    return PresetSettings(
        name=base_preset.name,
        control_weight=control_weight,
        denoising_strength=denoising,
        control_mode=base_preset.control_mode,
        cfg_scale=base_preset.cfg_scale,
        steps=base_preset.steps,
        sampler_name=base_preset.sampler_name,
        prompt=prompt,
        negative_prompt=negative_prompt,
        prompt_mode=base_preset.prompt_mode,
    )


async def _queue_worker_loop() -> None:
    global queue_worker_stop
    global queue_current_job_id

    while not queue_worker_stop:
        job = await run_in_threadpool(queue_store.pop_next_queued_job)
        if job is None:
            await asyncio.sleep(0.3)
            continue

        job_id = str(job.get("jobId") or "")
        async with queue_status_lock:
            queue_current_job_id = job_id

        await ws_manager.broadcast({"type": "job_started", "job": _job_to_public_payload(job)})
        await _broadcast_queue_updated()

        try:
            refreshed = await run_in_threadpool(queue_store.get_job, job_id)
            if refreshed and bool(refreshed.get("cancelRequested")):
                cancelled = await _mark_job_cancelled(job_id, "Cancelled before processing started.")
                await ws_manager.broadcast({"type": "job_cancelled", "job": _job_to_public_payload(cancelled)})
                await _broadcast_queue_updated()
                continue

            input_path = Path(str(job.get("inputPath") or ""))
            if not input_path.is_file():
                raise RuntimeError("Input image is missing for this job.")

            preset_override = _preset_from_job(job)
            detection_override = job.get("detection") if isinstance(job.get("detection"), dict) else None

            estimate_payload = {
                "estimatedSeconds": int(
                    job.get("estimatedSeconds") or DEFAULT_GENERATION_ESTIMATE_SECONDS
                ),
                "minSeconds": int(job.get("estimatedSeconds") or DEFAULT_GENERATION_ESTIMATE_SECONDS),
                "maxSeconds": int(job.get("estimatedSeconds") or DEFAULT_GENERATION_ESTIMATE_SECONDS),
                "sampleCount": 0,
            }

            extra_fields = {
                "originalJobId": job.get("originalJobId") or job_id,
                "regenerationOf": job.get("regenerationOf"),
                "version": int(job.get("version") or 1),
                "generationMode": _normalize_generation_mode(job.get("generationMode")),
                "styleId": _normalize_style_id(job.get("styleId")),
                "source": _normalize_source(job.get("source")),
            }

            result_item = await _run_generation_pipeline(
                job_id,
                str(job.get("visitorName") or "Guest"),
                input_path,
                estimate_payload=estimate_payload,
                preset_override=preset_override,
                detection_payload_override=detection_override,
                persist_result=False,
                created_at_override=str(job.get("createdAt") or utc_now_iso()),
                extra_item_fields=extra_fields,
                generation_settings_override=job.get("generationSettings")
                if isinstance(job.get("generationSettings"), dict)
                else None,
            )

            refreshed = await run_in_threadpool(queue_store.get_job, job_id)
            if refreshed and bool(refreshed.get("cancelRequested")):
                await run_in_threadpool(_delete_local_gallery_file, result_item.get("outputUrl"))
                cancelled = await _mark_job_cancelled(job_id, "Cancelled during processing.")
                await ws_manager.broadcast({"type": "job_cancelled", "job": _job_to_public_payload(cancelled)})
                await _broadcast_queue_updated()
                if bool(refreshed.get("deleteRequested")):
                    await _delete_job_artifacts(job_id)
                continue

            await run_in_threadpool(gallery_store.add_item, result_item)
            completed = await _update_job_with_completed_result(job, result_item)
            await ws_manager.broadcast(_build_generation_complete_event(result_item))
            await ws_manager.broadcast({"type": "job_completed", "job": _job_to_public_payload(completed)})
            await _broadcast_queue_updated()

            if bool(completed.get("deleteRequested")):
                await _delete_job_artifacts(job_id)
        except Exception as exc:
            logger.exception("Queue processing failed for job=%s", job_id)
            failed = await _mark_job_failed(job_id, str(exc))
            await _broadcast_error(job_id, str(exc))
            await ws_manager.broadcast({"type": "job_failed", "job": _job_to_public_payload(failed)})
            await _broadcast_queue_updated()
        finally:
            async with queue_status_lock:
                queue_current_job_id = None


async def _recover_queue_on_startup() -> None:
    _all, recovered = await run_in_threadpool(queue_store.recover_unfinished_jobs)
    if recovered:
        logger.info("Recovered %s unfinished queue job(s).", len(recovered))
    await _broadcast_queue_updated()


@app.on_event("startup")
async def on_startup() -> None:
    global queue_worker_task
    global queue_worker_stop

    _initialize_api_key_state()
    app.state.event_loop = asyncio.get_running_loop()
    app.state.scanner_service = ScannerService(
        scanner_input_dir=SCANNER_INPUT_DIR,
        on_file_ready=_schedule_scanner_job,
        enabled=ENABLE_FOLDER_WATCHER,
    )
    app.state.scanner_service.start()
    queue_worker_stop = False
    await _recover_queue_on_startup()
    queue_worker_task = asyncio.create_task(_queue_worker_loop(), name="queue-worker")
    logger.info("Application startup complete.")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global queue_worker_stop
    global queue_worker_task

    scanner_service = getattr(app.state, "scanner_service", None)
    if scanner_service:
        scanner_service.stop()
    queue_worker_stop = True
    if queue_worker_task:
        try:
            await asyncio.wait_for(queue_worker_task, timeout=3)
        except asyncio.TimeoutError:
            queue_worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await queue_worker_task
        queue_worker_task = None
    logger.info("Application shutdown complete.")


@app.get("/health")
async def health() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "backend": "ok",
        "stableDiffusion": {"reachable": False},
        "folderWatcher": {
            "enabled": ENABLE_FOLDER_WATCHER,
            "running": False,
            "path": str(SCANNER_INPUT_DIR),
        },
        "checkedAtUtc": datetime.now(timezone.utc).isoformat(),
    }

    scanner_service = getattr(app.state, "scanner_service", None)
    if scanner_service:
        status["folderWatcher"]["running"] = scanner_service.running

    try:
        models = await run_in_threadpool(sd_generator.fetch_models)
        status["stableDiffusion"] = {
            "reachable": True,
            "modelCount": len(models),
        }
    except StableDiffusionError as exc:
        logger.warning("Health check: Stable Diffusion unreachable: %s", exc)
        status["backend"] = "degraded"
        status["stableDiffusion"] = {
            "reachable": False,
            "error": str(exc),
        }

    return status


@app.get("/staff")
async def staff_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "staff.html")


@app.get("/gallery")
async def gallery_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "gallery.html")


@app.get("/gallery/items")
async def gallery_items(includeHidden: bool = False) -> Dict[str, Any]:
    items = await run_in_threadpool(gallery_store.list_items, bool(includeHidden))
    normalized_items: List[Dict[str, Any]] = []
    for item in items:
        updated_item = dict(item)
        updated_item["source"] = _normalize_source(updated_item.get("source"))
        normalized_items.append(updated_item)
    return {"items": normalized_items}


@app.get("/generation/estimate")
async def generation_estimate() -> Dict[str, int]:
    return await run_in_threadpool(
        gallery_store.get_duration_estimate,
        DEFAULT_GENERATION_ESTIMATE_SECONDS,
    )


@app.post("/gallery/rate/{jobId}")
async def rate_gallery_item(jobId: str, payload: RatingRequest) -> Dict[str, Any]:
    try:
        updated_item = await run_in_threadpool(
            gallery_store.rate_item,
            jobId,
            int(payload.rating),
            payload.feedbackTags,
            payload.feedbackNote,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Gallery item not found: {jobId}") from exc

    logger.info("Rating saved for jobId=%s rating=%s tags=%s", jobId, payload.rating, payload.feedbackTags)
    await ws_manager.broadcast({"type": "gallery_item_updated", "item": updated_item})
    return updated_item


@app.patch("/gallery/item/{jobId}/name")
async def rename_gallery_item(jobId: str, payload: GalleryRenameRequest) -> Dict[str, Any]:
    try:
        updated_item = await run_in_threadpool(
            gallery_store.rename_item,
            jobId,
            payload.visitorName,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Gallery item not found: {jobId}") from exc

    logger.info("Gallery item renamed jobId=%s visitorName=%s", jobId, payload.visitorName)
    await ws_manager.broadcast({"type": "gallery_item_updated", "item": updated_item})
    return updated_item


@app.patch("/gallery/item/{jobId}/visibility")
async def set_gallery_item_visibility(jobId: str, payload: GalleryVisibilityRequest) -> Dict[str, Any]:
    try:
        updated_item = await run_in_threadpool(
            gallery_store.set_hidden,
            jobId,
            bool(payload.hidden),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Gallery item not found: {jobId}") from exc

    logger.info("Gallery item visibility changed jobId=%s hidden=%s", jobId, bool(payload.hidden))
    await ws_manager.broadcast({"type": "gallery_item_updated", "item": updated_item})
    return updated_item


@app.delete("/gallery/item/{jobId}")
async def delete_gallery_item(jobId: str) -> Dict[str, Any]:
    try:
        removed_item = await run_in_threadpool(gallery_store.delete_item, jobId)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Gallery item not found: {jobId}") from exc

    await run_in_threadpool(_delete_local_gallery_file, removed_item.get("inputUrl"))
    await run_in_threadpool(_delete_local_gallery_file, removed_item.get("outputUrl"))

    logger.info("Gallery item deleted jobId=%s", jobId)
    await ws_manager.broadcast({"type": "gallery_item_deleted", "jobId": jobId})
    return {"deleted": True, "jobId": jobId}


@app.get("/queue/status")
async def queue_status() -> Dict[str, Any]:
    return await _queue_status_payload()


def _load_api_docs_markdown() -> str:
    try:
        return API_DOCS_MARKDOWN_PATH.read_text(encoding="utf-8")
    except OSError:
        return "API documentation file not found: docs/API.md"


@app.get("/admin/api", tags=["Admin"], summary="Admin API key manager")
async def admin_api_page(request: Request) -> HTMLResponse:
    active_key = _get_active_api_key()
    key_enabled = bool(active_key)
    masked = _mask_api_key(active_key)
    configured_masked = _mask_api_key(str(API_KEY or "").strip())
    base_url = str(request.base_url).rstrip("/")

    html_content = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Admin API Key</title>
  <style>
    body {{ font-family: Arial, sans-serif; background: #f6f7fb; color: #1f2937; margin: 0; }}
    .wrap {{ max-width: 900px; margin: 24px auto; padding: 0 16px; }}
    .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; margin-bottom: 16px; }}
    h1, h2 {{ margin: 0 0 12px 0; }}
    .muted {{ color: #6b7280; font-size: 14px; }}
    .row {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    input[type=text] {{ flex: 1; min-width: 260px; padding: 10px; border: 1px solid #d1d5db; border-radius: 8px; }}
    button {{ padding: 10px 14px; border: 0; border-radius: 8px; cursor: pointer; }}
    .primary {{ background: #2563eb; color: #fff; }}
    .warn {{ background: #ea580c; color: #fff; }}
    .danger {{ background: #dc2626; color: #fff; }}
    .mono {{ font-family: Consolas, monospace; background: #f3f4f6; padding: 2px 6px; border-radius: 6px; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #111827; color: #e5e7eb; padding: 12px; border-radius: 8px; }}
    a {{ color: #2563eb; text-decoration: none; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Admin API Key Manager</h1>
      <p class="muted">Manage runtime API key at <span class="mono">/admin/api</span>. Docs page: <a href="/admin/api/docs">/admin/api/docs</a></p>
      <p>Status: <strong>{"Enabled" if key_enabled else "Disabled"}</strong></p>
      <p>Active key (masked): <span class="mono">{html.escape(masked)}</span></p>
      <p>Config default (masked): <span class="mono">{html.escape(configured_masked)}</span></p>
      <p class="muted">Protected API endpoints require header <span class="mono">{API_KEY_HEADER}</span> when key is enabled.</p>
    </div>

    <div class="card">
      <h2>Actions</h2>
      <p class="muted">If key is currently enabled, enter the current key to authorize changes.</p>
      <div class="row">
        <input id="apiKeyInput" type="text" placeholder="Current API key (if enabled)" />
      </div>
      <div class="row">
        <button class="primary" onclick="doAction('generate')">Generate New Key</button>
        <button class="warn" onclick="doAction('reset')">Reset To app/config.py API_KEY</button>
        <button class="danger" onclick="doAction('delete')">Delete Key (Disable Auth)</button>
      </div>
      <div class="row">
        <button onclick="openDocs()">Open API Docs Page</button>
        <button onclick="openOpenApi()">Open Swagger /docs</button>
      </div>
      <pre id="resultBox">No action yet.</pre>
    </div>

    <div class="card">
      <h2>Connection Base URL</h2>
      <p class="mono">{html.escape(base_url)}</p>
    </div>
  </div>
  <script>
    async function doAction(action) {{
      const apiKey = document.getElementById('apiKeyInput').value.trim();
      const headers = {{ "Content-Type": "application/json" }};
      if (apiKey) headers["{API_KEY_HEADER}"] = apiKey;
      let method = "POST";
      let url = "/admin/api/" + action;
      if (action === "delete") method = "DELETE";
      const response = await fetch(url, {{ method, headers }});
      const data = await response.json().catch(() => ({{ ok: false, message: "Non-JSON response" }}));
      document.getElementById('resultBox').textContent = JSON.stringify({{
        httpStatus: response.status,
        ...data
      }}, null, 2);
    }}
    function openDocs() {{ window.location.href = "/admin/api/docs"; }}
    function openOpenApi() {{ window.location.href = "/docs"; }}
  </script>
</body>
</html>"""
    return HTMLResponse(html_content)


@app.get("/admin/api/docs", tags=["Admin"], summary="Admin API docs view")
async def admin_api_docs_page() -> HTMLResponse:
    markdown_text = _load_api_docs_markdown()
    escaped = html.escape(markdown_text)
    html_content = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Admin API Docs</title>
  <style>
    body {{ font-family: Arial, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; }}
    .wrap {{ max-width: 1100px; margin: 24px auto; padding: 0 16px; }}
    .card {{ background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 16px; margin-bottom: 16px; }}
    h1, h2 {{ margin: 0 0 12px 0; }}
    .muted {{ color: #94a3b8; }}
    .mono {{ font-family: Consolas, monospace; background: #1f2937; padding: 2px 6px; border-radius: 6px; }}
    a {{ color: #93c5fd; text-decoration: none; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #020617; color: #e2e8f0; padding: 14px; border-radius: 10px; border: 1px solid #1f2937; }}
    ul {{ margin: 0; padding-left: 18px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Admin API Documentation</h1>
      <p class="muted">This page mirrors <span class="mono">docs/API.md</span> and includes example parameters for all public API endpoints.</p>
      <ul>
        <li><a href="/admin/api">/admin/api</a> (key manager)</li>
        <li><a href="/docs">/docs</a> (OpenAPI Swagger UI)</li>
      </ul>
    </div>
    <div class="card">
      <h2>docs/API.md</h2>
      <pre>{escaped}</pre>
    </div>
  </div>
</body>
</html>"""
    return HTMLResponse(html_content)


@app.post("/admin/api/generate", tags=["Admin"], summary="Generate and apply a new runtime API key")
async def admin_generate_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER),
    apiKey: Optional[str] = Form(default=None),
) -> Dict[str, Any]:
    _require_admin_api_access(request, x_api_key=x_api_key, form_api_key=apiKey)
    generated_key = secrets.token_urlsafe(32)
    _set_active_api_key(generated_key, persist=True)
    return {
        "ok": True,
        "action": "generate",
        "apiKey": generated_key,
        "maskedApiKey": _mask_api_key(generated_key),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "message": "New API key generated and applied immediately.",
    }


@app.post("/admin/api/reset", tags=["Admin"], summary="Reset runtime API key to app/config.py API_KEY")
async def admin_reset_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER),
    apiKey: Optional[str] = Form(default=None),
) -> Dict[str, Any]:
    _require_admin_api_access(request, x_api_key=x_api_key, form_api_key=apiKey)
    reset_value = _set_active_api_key(str(API_KEY or "").strip(), persist=True)
    return {
        "ok": True,
        "action": "reset",
        "apiKeyEnabled": bool(reset_value),
        "maskedApiKey": _mask_api_key(reset_value),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "message": "API key reset to app/config.py value.",
    }


@app.post("/admin/api/delete", tags=["Admin"], summary="Delete runtime API key (disable API key auth)")
async def admin_delete_api_key_post(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER),
    apiKey: Optional[str] = Form(default=None),
) -> Dict[str, Any]:
    _require_admin_api_access(request, x_api_key=x_api_key, form_api_key=apiKey)
    _set_active_api_key("", persist=True)
    return {
        "ok": True,
        "action": "delete",
        "apiKeyEnabled": False,
        "maskedApiKey": _mask_api_key(""),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "message": "API key deleted. Protected endpoints are now open until a new key is set.",
    }


@app.delete("/admin/api", tags=["Admin"], summary="Delete runtime API key (disable API key auth)")
async def admin_delete_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER),
    apiKey: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    _require_admin_api_access(request, x_api_key=x_api_key, query_api_key=apiKey)
    _set_active_api_key("", persist=True)
    return {
        "ok": True,
        "action": "delete",
        "apiKeyEnabled": False,
        "maskedApiKey": _mask_api_key(""),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "message": "API key deleted. Protected endpoints are now open until a new key is set.",
    }


def _filter_gallery_items_for_api(
    items: List[Dict[str, Any]],
    mode: Optional[str],
    style_id: Optional[str],
) -> List[Dict[str, Any]]:
    mode_filter = str(mode or "").strip()
    style_filter = str(style_id or "").strip()

    def _matches(item: Dict[str, Any]) -> bool:
        item_mode = _normalize_generation_mode(item.get("generationMode"))
        item_style = _normalize_style_id(item.get("styleId"))
        if mode_filter and item_mode != mode_filter:
            return False
        if style_filter and item_style != style_filter:
            return False
        return True

    return [item for item in items if _matches(item)]


@app.post(
    "/api/auth/generate-key",
    tags=["Public API"],
    summary="Generate a new API key",
)
async def api_generate_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER),
) -> Dict[str, str]:
    configured_key = _get_active_api_key()
    if configured_key:
        _require_api_key(request, x_api_key)

    generated_key = secrets.token_urlsafe(32)
    return {
        "apiKey": generated_key,
        "headerName": API_KEY_HEADER,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "howToUse": "Apply from /admin/api or set API_KEY in app/config.py and restart backend.",
    }


@app.post(
    "/api/jobs",
    tags=["Public API"],
    summary="Create a new generation job",
    dependencies=[Depends(_require_api_key)],
)
async def api_create_job(
    visitorName: str = Form(""),
    generationMode: str = Form(DEFAULT_GENERATION_MODE),
    styleId: str = Form(DEFAULT_STYLE_ID),
    image: UploadFile = File(...),
) -> Dict[str, Any]:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image file.")

    extension = _resolve_extension(image)
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file extension.")

    job_id = uuid.uuid4().hex
    input_path, _ = _job_paths(job_id)
    visitor_name = _normalize_visitor_name(visitorName)
    generation_mode = _normalize_generation_mode(generationMode)
    style_id = _normalize_style_id(styleId)
    estimate_payload = await run_in_threadpool(
        gallery_store.get_duration_estimate,
        DEFAULT_GENERATION_ESTIMATE_SECONDS,
    )

    try:
        content = await image.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        await run_in_threadpool(_save_upload_as_png, content, input_path)
        queued_job = _build_queue_job(
            job_id=job_id,
            visitor_name=visitor_name,
            input_path=input_path,
            source="api",
            estimate_payload=estimate_payload,
            generation_mode=generation_mode,
            style_id=style_id,
        )
        await _enqueue_job(queued_job)

        status_payload = await _queue_status_payload()
        queue_position = _find_queue_position(status_payload.get("jobs", []), job_id)
        return {
            "jobId": job_id,
            "status": "queued",
            "queuePosition": int(queue_position),
            "estimatedWaitSeconds": int(status_payload.get("estimatedWaitSeconds") or 0),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("API job %s failed before enqueue", job_id)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc
    finally:
        await image.close()


@app.get(
    "/api/jobs/{jobId}",
    tags=["Public API"],
    summary="Get job status and metadata",
)
async def api_get_job(
    request: Request,
    jobId: str,
    absolute: bool = Query(False),
) -> Dict[str, Any]:
    job = await run_in_threadpool(queue_store.get_job, jobId)
    if job is None:
        gallery_item = await run_in_threadpool(gallery_store.get_item, jobId)
        if gallery_item is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {jobId}")
        job = _gallery_item_to_job_payload(gallery_item)
    return _build_api_job_payload(job, request, bool(absolute))


@app.get(
    "/api/gallery",
    tags=["Public API"],
    summary="List gallery items (newest first)",
)
async def api_gallery(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    mode: Optional[str] = Query(None),
    styleId: Optional[str] = Query(None),
    absolute: bool = Query(False),
) -> Dict[str, Any]:
    items = await run_in_threadpool(gallery_store.list_items, False)
    filtered = _filter_gallery_items_for_api(items, mode, styleId)
    total = len(filtered)
    paged = filtered[offset : offset + limit]
    payload_items = [_build_api_gallery_item(item, request, bool(absolute)) for item in paged]
    return {
        "items": payload_items,
        "limit": limit,
        "offset": offset,
        "total": total,
    }


@app.get(
    "/api/gallery/latest",
    tags=["Public API"],
    summary="Get latest completed gallery item",
)
async def api_gallery_latest(
    request: Request,
    mode: Optional[str] = Query(None),
    styleId: Optional[str] = Query(None),
    absolute: bool = Query(False),
) -> Dict[str, Any]:
    items = await run_in_threadpool(gallery_store.list_items, False)
    filtered = _filter_gallery_items_for_api(items, mode, styleId)
    if not filtered:
        raise HTTPException(status_code=404, detail="No gallery items found.")
    return _build_api_gallery_item(filtered[0], request, bool(absolute))


@app.get(
    "/api/before-after",
    tags=["Public API"],
    summary="Get before/after formatted items",
)
async def api_before_after(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    mode: Optional[str] = Query(None),
    styleId: Optional[str] = Query(None),
    absolute: bool = Query(False),
) -> Dict[str, Any]:
    items = await run_in_threadpool(gallery_store.list_items, False)
    filtered = _filter_gallery_items_for_api(items, mode, styleId)
    paged = filtered[offset : offset + limit]
    response_items: List[Dict[str, Any]] = []
    for item in paged:
        row = {
            "jobId": str(item.get("jobId") or ""),
            "visitorName": _normalize_visitor_name(item.get("visitorName")),
            "beforeImageUrl": str(item.get("inputUrl") or ""),
            "afterImageUrl": str(item.get("outputUrl") or ""),
            "createdAt": item.get("createdAt"),
        }
        response_items.append(_with_absolute_image_urls(request, row, bool(absolute)))
    return {
        "items": response_items,
        "limit": limit,
        "offset": offset,
        "total": len(filtered),
    }


@app.get(
    "/api/queue/status",
    tags=["Public API"],
    summary="Get queue status",
)
async def api_queue_status(
    request: Request,
    absolute: bool = Query(False),
) -> Dict[str, Any]:
    payload = await _queue_status_payload()
    jobs = payload.get("jobs", [])
    api_jobs = [
        _build_api_job_payload(job, request, bool(absolute))
        for job in jobs
        if isinstance(job, dict)
    ]
    return {
        "queueLength": int(payload.get("queueLength") or 0),
        "currentJob": payload.get("currentJob"),
        "estimatedWaitSeconds": int(payload.get("estimatedWaitSeconds") or 0),
        "jobs": api_jobs,
    }


async def _build_queued_response(job: Dict[str, Any]) -> Dict[str, Any]:
    status_payload = await _queue_status_payload()
    return {
        "status": "queued",
        "job": _job_to_public_payload(job),
        **status_payload,
    }


@app.post("/jobs/{jobId}/cancel")
async def cancel_job(jobId: str) -> Dict[str, Any]:
    job = await run_in_threadpool(queue_store.get_job, jobId)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {jobId}")

    status = str(job.get("status") or "")
    if status == "queued":
        cancelled = await _mark_job_cancelled(jobId, "Cancelled while queued.")
        await ws_manager.broadcast({"type": "job_cancelled", "job": _job_to_public_payload(cancelled)})
        await _broadcast_queue_updated()
        return {"job": _job_to_public_payload(cancelled)}

    if status == "processing":
        updated = await run_in_threadpool(
            queue_store.update_job_fields,
            jobId,
            {"cancelRequested": True},
        )
        await _broadcast_queue_updated()
        return {
            "job": _job_to_public_payload(updated),
            "message": "Cancellation requested. Output will be discarded after current generation request finishes.",
        }

    return {"job": _job_to_public_payload(job), "message": f"Job already in terminal state: {status}"}


@app.post("/jobs/{jobId}/retry", dependencies=[Depends(_require_api_key)])
async def retry_job(jobId: str) -> Dict[str, Any]:
    job = await run_in_threadpool(queue_store.get_job, jobId)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {jobId}")

    status = str(job.get("status") or "")
    if status not in {"failed", "cancelled"}:
        raise HTTPException(status_code=400, detail="Only failed or cancelled jobs can be retried.")

    retry_count = int(job.get("retryCount") or 0)
    if retry_count >= MAX_RETRY_COUNT:
        updated = await run_in_threadpool(
            queue_store.update_job_fields,
            jobId,
            {"permanentlyFailed": True, "status": "failed"},
        )
        await ws_manager.broadcast({"type": "job_failed", "job": _job_to_public_payload(updated)})
        await _broadcast_queue_updated()
        raise HTTPException(status_code=400, detail="Max retry count exceeded (3). Permanently failed.")

    input_path = Path(str(job.get("inputPath") or ""))
    if not input_path.is_file():
        raise HTTPException(status_code=404, detail="Original input image is missing.")

    updates = {
        "status": "queued",
        "queuedAt": utc_now_iso(),
        "startedAt": None,
        "completedAt": None,
        "failedAt": None,
        "cancelledAt": None,
        "durationSeconds": None,
        "error": None,
        "permanentlyFailed": False,
        "cancelRequested": False,
        "deleteRequested": False,
        "retryCount": retry_count + 1,
    }
    updated = await run_in_threadpool(queue_store.update_job_fields, jobId, updates)
    await _broadcast_queue_updated()
    return await _build_queued_response(updated)


@app.post("/jobs/{jobId}/regenerate", dependencies=[Depends(_require_api_key)])
async def regenerate_job(jobId: str, payload: RegenerateRequest) -> Dict[str, Any]:
    source_job = await run_in_threadpool(queue_store.get_job, jobId)
    if source_job is None:
        source_job = await run_in_threadpool(gallery_store.get_item, jobId)
    if source_job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {jobId}")

    input_url = str(source_job.get("inputUrl") or "")
    input_path = Path(_url_to_local_path(input_url))
    if not input_path.is_file():
        raise HTTPException(status_code=404, detail="Original input image is missing.")

    base_preset = _preset_from_job(source_job)
    if base_preset is None:
        raise HTTPException(status_code=400, detail="Original generation settings are missing.")

    adjusted_preset = _apply_regenerate_adjustments(
        base_preset=base_preset,
        problem_tags=payload.problemTags,
    )
    adjusted_settings = _build_generation_settings(adjusted_preset)

    cfg_scale = float(source_job.get("generationSettings", {}).get("cfgScale", GENERATION_DEFAULTS.cfg_scale))
    for tag in payload.problemTags:
        if tag in {"bad_colors", "too_dark"}:
            cfg_scale += 0.8
    cfg_scale = max(5.0, min(9.0, cfg_scale))
    adjusted_settings["cfgScale"] = cfg_scale

    new_job_id = uuid.uuid4().hex
    new_input_path, _ = _job_paths(new_job_id)
    await run_in_threadpool(new_input_path.write_bytes, input_path.read_bytes())

    estimate_payload = await run_in_threadpool(
        gallery_store.get_duration_estimate,
        DEFAULT_GENERATION_ESTIMATE_SECONDS,
    )
    version = int(source_job.get("version") or 1) + 1
    original_job_id = str(source_job.get("originalJobId") or source_job.get("jobId") or jobId)

    detection_payload = source_job.get("detection")
    if not isinstance(detection_payload, dict):
        detection_payload = {}

    new_job = _build_queue_job(
        job_id=new_job_id,
        visitor_name=_normalize_visitor_name(source_job.get("visitorName")),
        input_path=new_input_path,
        source="regenerate",
        estimate_payload=estimate_payload,
        generation_mode=_normalize_generation_mode(source_job.get("generationMode")),
        style_id=_normalize_style_id(source_job.get("styleId")),
        original_job_id=original_job_id,
        regeneration_of=jobId,
        version=version,
        problem_tags=payload.problemTags,
        retry_count=0,
        preset_override=adjusted_preset,
        detection_payload=detection_payload,
    )
    new_job["generationSettings"] = adjusted_settings

    enqueued = await _enqueue_job(new_job)
    return await _build_queued_response(enqueued)


@app.delete("/jobs/{jobId}", dependencies=[Depends(_require_api_key)])
async def delete_job(jobId: str) -> Dict[str, Any]:
    job = await run_in_threadpool(queue_store.get_job, jobId)
    if job is None:
        # Still allow deleting completed gallery-only metadata if present.
        gallery_item = await run_in_threadpool(gallery_store.get_item, jobId)
        if gallery_item is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {jobId}")
        removed = await _delete_job_artifacts(jobId)
        await _broadcast_queue_updated()
        return removed

    if str(job.get("status") or "") == "processing":
        pending = await run_in_threadpool(
            queue_store.update_job_fields,
            jobId,
            {"cancelRequested": True, "deleteRequested": True},
        )
        await _broadcast_queue_updated()
        return {
            "deleted": False,
            "pending": True,
            "message": "Delete requested; job is processing and will be removed after request finishes.",
            "job": _job_to_public_payload(pending),
        }

    removed = await _delete_job_artifacts(jobId)
    await _broadcast_queue_updated()
    return removed


@app.post("/maintenance/cleanup")
async def maintenance_cleanup(payload: CleanupRequest = CleanupRequest()) -> Dict[str, Any]:
    keep_newest = int(payload.keepNewest or 5000)
    older_than_days = payload.olderThanDays

    all_items = await run_in_threadpool(gallery_store.list_items, True)
    removed_job_ids: List[str] = []
    removed_outputs = 0
    removed_inputs = 0
    removed_metadata = 0
    orphaned_metadata_removed = 0
    orphaned_files_removed = 0
    temp_files_removed = 0

    if older_than_days is not None:
        now = datetime.now(timezone.utc)
        target_ids: List[str] = []
        for item in all_items:
            created_raw = str(item.get("createdAt") or "")
            try:
                created_dt = datetime.fromisoformat(created_raw)
            except ValueError:
                continue
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            if (now - created_dt).days > int(older_than_days):
                target_ids.append(str(item.get("jobId") or ""))
    else:
        sorted_items = sorted(all_items, key=lambda item: str(item.get("createdAt") or ""), reverse=True)
        target_ids = [str(item.get("jobId") or "") for item in sorted_items[keep_newest:]]

    for job_id in target_ids:
        job_id = str(job_id or "")
        if not job_id:
            continue
        item = await run_in_threadpool(gallery_store.get_item, job_id)
        if item:
            if Path(_url_to_local_path(item.get("inputUrl"))).is_file():
                removed_inputs += 1
            if Path(_url_to_local_path(item.get("outputUrl"))).is_file():
                removed_outputs += 1
        removed = await _delete_job_artifacts(job_id)
        if removed.get("deleted"):
            removed_job_ids.append(job_id)
            removed_metadata += 1

    # Remove broken metadata entries (missing files).
    current_items = await run_in_threadpool(gallery_store.list_items, True)
    for item in current_items:
        input_exists = Path(_url_to_local_path(item.get("inputUrl"))).is_file()
        output_exists = Path(_url_to_local_path(item.get("outputUrl"))).is_file()
        if input_exists and output_exists:
            continue
        try:
            await run_in_threadpool(gallery_store.delete_item, str(item.get("jobId") or ""))
            orphaned_metadata_removed += 1
        except KeyError:
            pass

    # Remove orphaned files not referenced by gallery or queue jobs.
    refreshed_items = await run_in_threadpool(gallery_store.list_items, True)
    queue_jobs = await run_in_threadpool(queue_store.list_jobs)
    referenced_inputs = {str(item.get("inputUrl") or "") for item in refreshed_items}
    referenced_outputs = {str(item.get("outputUrl") or "") for item in refreshed_items}
    referenced_inputs.update(str(job.get("inputUrl") or "") for job in queue_jobs)
    referenced_outputs.update(str(job.get("outputUrl") or "") for job in queue_jobs)

    for path in INPUT_DIR.glob("*"):
        if not path.is_file():
            continue
        rel_url = f"/inputs/{path.name}"
        if rel_url in referenced_inputs:
            continue
        try:
            path.unlink()
            orphaned_files_removed += 1
        except OSError:
            logger.warning("Unable to delete orphaned input file: %s", path)

    for path in OUTPUT_DIR.glob("*"):
        if not path.is_file():
            continue
        rel_url = f"/outputs/{path.name}"
        if rel_url in referenced_outputs:
            continue
        try:
            path.unlink()
            orphaned_files_removed += 1
        except OSError:
            logger.warning("Unable to delete orphaned output file: %s", path)

    for path in TEMP_DIR.glob("*"):
        if not path.is_file():
            continue
        try:
            path.unlink()
            temp_files_removed += 1
        except OSError:
            logger.warning("Unable to delete temp file: %s", path)

    await _broadcast_queue_updated()
    return {
        "deletedJobs": len(removed_job_ids),
        "deletedOutputs": removed_outputs,
        "deletedInputs": removed_inputs,
        "deletedMetadata": removed_metadata,
        "orphanedMetadataRemoved": orphaned_metadata_removed,
        "orphanedFilesRemoved": orphaned_files_removed,
        "tempFilesRemoved": temp_files_removed,
        "mode": "olderThanDays" if older_than_days is not None else "keepNewest",
        "olderThanDays": older_than_days,
        "keepNewest": keep_newest,
    }


@app.get("/reports/tuning")
async def tuning_report_json() -> Dict[str, Any]:
    items = await run_in_threadpool(gallery_store.list_items)
    summary = _build_tuning_summary(items)
    if int(summary.get("ratedImages") or 0) == 0:
        summary.pop("_globalBadTags", None)
        summary.pop("_globalGoodTags", None)
        summary["message"] = "No rated images yet."
        return summary
    summary.pop("_globalBadTags", None)
    summary.pop("_globalGoodTags", None)
    return summary


@app.get("/reports/tuning.txt")
async def tuning_report_text() -> PlainTextResponse:
    items = await run_in_threadpool(gallery_store.list_items)
    summary = _build_tuning_summary(items)
    if int(summary.get("ratedImages") or 0) == 0:
        return PlainTextResponse("No rated images yet.")
    report = _build_tuning_text_report(summary)
    return PlainTextResponse(report)


@app.post("/generate")
async def generate(
    visitorName: str = Form(""),
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image file.")

    extension = _resolve_extension(file)
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file extension.")

    job_id = uuid.uuid4().hex
    input_path, _ = _job_paths(job_id)
    visitor_name = _normalize_visitor_name(visitorName)
    estimate_payload = await run_in_threadpool(
        gallery_store.get_duration_estimate,
        DEFAULT_GENERATION_ESTIMATE_SECONDS,
    )

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        await run_in_threadpool(_save_upload_as_png, content, input_path)
        queued_job = _build_queue_job(
            job_id=job_id,
            visitor_name=visitor_name,
            input_path=input_path,
            source="upload",
            estimate_payload=estimate_payload,
        )
        queued = await _enqueue_job(queued_job)
        return await _build_queued_response(queued)
    except HTTPException as exc:
        await _broadcast_error(job_id, str(exc.detail))
        raise
    except Exception as exc:
        logger.exception("Job %s: unexpected error", job_id)
        await _broadcast_error(job_id, f"Unexpected error: {exc}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc
    finally:
        await file.close()


@app.post("/capture")
async def capture(visitorName: str = Form("")) -> Dict[str, Any]:
    job_id = uuid.uuid4().hex
    input_path, _ = _job_paths(job_id)
    visitor_name = _normalize_visitor_name(visitorName)
    estimate_payload = await run_in_threadpool(
        gallery_store.get_duration_estimate,
        DEFAULT_GENERATION_ESTIMATE_SECONDS,
    )

    try:
        await run_in_threadpool(_capture_webcam_to_png, input_path)
        queued_job = _build_queue_job(
            job_id=job_id,
            visitor_name=visitor_name,
            input_path=input_path,
            source="capture",
            estimate_payload=estimate_payload,
        )
        queued = await _enqueue_job(queued_job)
        return await _build_queued_response(queued)
    except Exception as exc:
        logger.exception("Job %s: webcam capture/generation error", job_id)
        await _broadcast_error(job_id, f"Unexpected error: {exc}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc


async def _serve_websocket_connection(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    logger.info("WebSocket client connected. active=%s", ws_manager.connection_count)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        logger.info("WebSocket client disconnected. active=%s", ws_manager.connection_count)
    except Exception:
        ws_manager.disconnect(websocket)
        logger.exception("WebSocket connection ended with error.")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await _serve_websocket_connection(websocket)


@app.websocket("/api/ws")
async def api_websocket_endpoint(websocket: WebSocket) -> None:
    await _serve_websocket_connection(websocket)
