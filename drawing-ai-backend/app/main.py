import asyncio
import logging
import uuid
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field, conint, validator
from starlette.concurrency import run_in_threadpool

from app.config import (
    ALLOWED_UPLOAD_EXTENSIONS,
    BASE_DIR,
    ENABLE_FOLDER_WATCHER,
    GALLERY_JSON_PATH,
    GENERATION_DEFAULTS,
    INPUT_DIR,
    OUTPUT_DIR,
    SCANNER_INPUT_DIR,
    SD_CONFIG,
    STATIC_DIR,
)
from app.detector import DetectionResult, PresetSettings, analyze_image
from app.gallery_store import GalleryStore
from app.generator import (
    StableDiffusionError,
    StableDiffusionGenerator,
    StableDiffusionUnavailableError,
)
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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/inputs", StaticFiles(directory=str(INPUT_DIR)), name="inputs")
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

ws_manager = WebSocketManager()
sd_generator = StableDiffusionGenerator()
gallery_store = GalleryStore(GALLERY_JSON_PATH)

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

KNOWN_PRESETS = ["kid_crayon", "sketch_lineart", "colored_drawing", "default"]
DEFAULT_GENERATION_ESTIMATE_SECONDS = 60


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


def _normalize_visitor_name(value: Optional[str]) -> str:
    cleaned = (value or "").strip()
    return cleaned if cleaned else "Guest"


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
        "controlNetModel": SD_CONFIG.controlnet_model,
        "controlNetModule": SD_CONFIG.controlnet_module,
        "controlWeight": preset.control_weight,
        "denoisingStrength": preset.denoising_strength,
        "controlMode": preset.control_mode,
        "steps": GENERATION_DEFAULTS.steps,
        "cfgScale": GENERATION_DEFAULTS.cfg_scale,
        "width": GENERATION_DEFAULTS.width,
        "height": GENERATION_DEFAULTS.height,
        "samplerName": GENERATION_DEFAULTS.sampler_name,
    }


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
    detection: DetectionResult,
) -> Dict[str, Any]:
    prompt_mode = detection.preset.prompt_mode
    generation_settings = _build_generation_settings(detection.preset)
    return {
        "jobId": job_id,
        "visitorName": visitor_name,
        "preset": detection.preset.name,
        "promptMode": prompt_mode,
        "promptType": prompt_mode,
        "inputUrl": input_url,
        "outputUrl": output_url,
        "createdAt": created_at,
        "startedAt": started_at,
        "completedAt": completed_at,
        "durationSeconds": duration_seconds,
        "estimatedSeconds": estimated_seconds,
        "detection": _build_detection_payload(detection),
        "generationSettings": generation_settings,
        "prompt": detection.preset.prompt,
        "negativePrompt": detection.preset.negative_prompt,
        "hidden": False,
        "hiddenAt": None,
        "updatedAt": None,
        "rating": None,
        "feedbackTags": [],
        "feedbackNote": "",
        "ratedAt": None,
    }


def _build_generation_complete_event(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "generation_complete",
        "jobId": item["jobId"],
        "visitorName": item["visitorName"],
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

    detection = await run_in_threadpool(analyze_image, input_path)
    output_path = OUTPUT_DIR / f"{job_id}.png"
    prompt_mode = detection.preset.prompt_mode

    logger.info(
        "Job %s started for visitor=%s preset=%s",
        job_id,
        visitor_name,
        detection.preset.name,
    )
    logger.info("Detected preset: %s", detection.preset.name)
    logger.info("Prompt mode: %s", prompt_mode)

    await run_in_threadpool(
        sd_generator.generate_image,
        input_path,
        output_path,
        detection.preset,
    )

    completed_at_dt = datetime.now(timezone.utc)
    completed_at = completed_at_dt.isoformat()
    duration_seconds = round((completed_at_dt - started_at_dt).total_seconds(), 3)
    created_at = completed_at
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
        detection=detection,
    )

    await run_in_threadpool(gallery_store.add_item, item)
    await ws_manager.broadcast(_build_generation_complete_event(item))

    logger.info("Job %s completed for visitor=%s", job_id, visitor_name)
    return {
        **item,
        "estimate": estimate_payload,
        "status": "completed",
    }


async def _run_scanner_job(scanner_file_path: Path, visitor_name: str) -> None:
    job_id = uuid.uuid4().hex
    normalized_name = _normalize_visitor_name(visitor_name)
    input_path, _ = _job_paths(job_id)

    try:
        await run_in_threadpool(_move_or_convert_scanner_image, scanner_file_path, input_path)
        await _run_generation_pipeline(job_id, normalized_name, input_path)
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


@app.on_event("startup")
async def on_startup() -> None:
    app.state.event_loop = asyncio.get_running_loop()
    app.state.scanner_service = ScannerService(
        scanner_input_dir=SCANNER_INPUT_DIR,
        on_file_ready=_schedule_scanner_job,
        enabled=ENABLE_FOLDER_WATCHER,
    )
    app.state.scanner_service.start()
    logger.info("Application startup complete.")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    scanner_service = getattr(app.state, "scanner_service", None)
    if scanner_service:
        scanner_service.stop()
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
    return {"items": items}


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


@app.get("/reports/tuning")
async def tuning_report_json() -> Dict[str, Any]:
    items = await run_in_threadpool(gallery_store.list_items)
    summary = _build_tuning_summary(items)
    summary.pop("_globalBadTags", None)
    summary.pop("_globalGoodTags", None)
    return summary


@app.get("/reports/tuning.txt")
async def tuning_report_text() -> PlainTextResponse:
    items = await run_in_threadpool(gallery_store.list_items)
    summary = _build_tuning_summary(items)
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
        return await _run_generation_pipeline(
            job_id,
            visitor_name,
            input_path,
            estimate_payload=estimate_payload,
        )
    except HTTPException as exc:
        await _broadcast_error(job_id, str(exc.detail))
        raise
    except StableDiffusionUnavailableError as exc:
        logger.error("Job %s: Stable Diffusion unavailable: %s", job_id, exc)
        await _broadcast_error(job_id, str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except StableDiffusionError as exc:
        logger.error("Job %s: Stable Diffusion API error: %s", job_id, exc)
        await _broadcast_error(job_id, str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
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
        return await _run_generation_pipeline(
            job_id,
            visitor_name,
            input_path,
            estimate_payload=estimate_payload,
        )
    except StableDiffusionUnavailableError as exc:
        logger.error("Job %s: Stable Diffusion unavailable: %s", job_id, exc)
        await _broadcast_error(job_id, str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except StableDiffusionError as exc:
        logger.error("Job %s: Stable Diffusion API error: %s", job_id, exc)
        await _broadcast_error(job_id, str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Job %s: webcam capture/generation error", job_id)
        await _broadcast_error(job_id, f"Unexpected error: {exc}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
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
