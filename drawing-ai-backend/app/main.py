import asyncio
import contextlib
import hashlib
import hmac
import html
import json
import logging
import re
import secrets
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import parse_qs, urlparse

import cv2
import requests
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
from PIL import Image, ImageStat
from pydantic import BaseModel, Field, conint, validator
from starlette.concurrency import run_in_threadpool

from backends import get_generation_backend, load_backend_runtime_config
from app.ai_art_venture import (
    AI_ART_VENTURE_CFG_MAX,
    AI_ART_VENTURE_CFG_MIN,
    AI_ART_VENTURE_CONTROLNET_FALLBACK_MODEL,
    AI_ART_VENTURE_CONTROLNET_FALLBACK_MODULE,
    AI_ART_VENTURE_CONTROLNET_PREFERRED_MODEL,
    AI_ART_VENTURE_CONTROLNET_PREFERRED_MODULE,
    AI_ART_VENTURE_CONTROL_WEIGHT_MAX,
    AI_ART_VENTURE_CONTROL_WEIGHT_MIN,
    AI_ART_VENTURE_DENOISE_MAX,
    AI_ART_VENTURE_DENOISE_MAX_NO_IP,
    AI_ART_VENTURE_DENOISE_MIN,
    AI_ART_VENTURE_IDENTITY_TARGET,
    AI_ART_VENTURE_IP_ADAPTER_WEIGHT,
    AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MAX,
    AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MIN,
    AI_ART_VENTURE_MODE_ID,
    AI_ART_VENTURE_MODE_LABEL,
    AI_ART_VENTURE_USE_IP_ADAPTER,
    analyze_background as analyze_ai_art_venture_background,
    build_preset as build_ai_art_venture_preset,
    ensure_styles_file as ensure_ai_art_venture_styles_file,
    get_mode_payload_for_ui as get_ai_art_venture_mode_payload_for_ui,
)
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
    PRINTS_DIR,
    QUEUE_JSON_PATH,
    SCANNER_INPUT_DIR,
    SD_CONFIG,
    STATIC_DIR,
    TEMP_DIR,
    WONDERPARK_ALLOWED_EXTENSIONS,
    WONDERPARK_ALLOWED_MIME_TYPES,
    WONDERPARK_DEFAULT_STYLE_ID,
    WONDERPARK_DUPLICATE_WINDOW_SECONDS,
    WONDERPARK_MAX_PROCESSING_DIMENSION,
    WONDERPARK_MAX_UPLOAD_BYTES,
    WONDERPARK_MIN_RECOMMENDED_HEIGHT,
    WONDERPARK_MIN_RECOMMENDED_WIDTH,
    WONDERPARK_ORIGINALS_DIR,
    WONDERPARK_PROCESSED_DIR,
    WONDERPARK_PUBLIC_UPLOAD_ENABLED,
    WONDERPARK_RATE_LIMIT_MAX_PER_IP,
    WONDERPARK_RATE_LIMIT_WINDOW_SECONDS,
    WONDERPARK_STORAGE_DIR,
    WONDERPARK_SUBMISSIONS_JSON_PATH,
    WONDERPARK_THUMBNAIL_MAX_DIMENSION,
    WONDERPARK_THUMBNAILS_DIR,
)
from app.detector import DetectionResult, PresetSettings, analyze_image
from app.gallery_store import GalleryStore
from app.generator import (
    StableDiffusionGenerator,
)
from app.local_ai_router import router as local_ai_router
from app.quality_reviewer import default_auto_review, review_generation_quality
from app.queue_store import QueueStore, utc_now_iso
from app.scanner_service import ScannerService
from app.services.photo_print_service import (
    GeneratedOutputMissingError,
    PillowMissingError,
    PHOTO_HEIGHT,
    PHOTO_TEMPLATE,
    PHOTO_WIDTH,
    create_4x6_photo_print,
)
from app.websocket_manager import WebSocketManager
from app.wonderpark_store import WonderparkSubmissionStore
from utils.prompt_presets import load_comfy_prompt_presets


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("drawing-ai-backend")

app = FastAPI(title="drawing-ai-backend", version="3.0.0")
app.include_router(local_ai_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=CORS_ALLOW_METHODS,
    allow_headers=CORS_ALLOW_HEADERS,
)

app.mount("/inputs", StaticFiles(directory=str(INPUT_DIR)), name="inputs")
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")
app.mount("/prints", StaticFiles(directory=str(PRINTS_DIR)), name="prints")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

ws_manager = WebSocketManager()
sd_generator = StableDiffusionGenerator()
gallery_store = GalleryStore(GALLERY_JSON_PATH)
queue_store = QueueStore(QUEUE_JSON_PATH)
wonderpark_store = WonderparkSubmissionStore(WONDERPARK_SUBMISSIONS_JSON_PATH)

try:
    RUNTIME_GENERATION_CONFIG = load_backend_runtime_config()
except Exception as exc:
    raise RuntimeError(f"Failed to load generation runtime config: {exc}") from exc

queue_worker_task: Optional[asyncio.Task] = None
queue_worker_stop = False
queue_current_job_id: Optional[str] = None
queue_status_lock = asyncio.Lock()
api_key_state_lock = threading.Lock()

API_KEY_STATE_PATH = BASE_DIR / "data" / "api_key_state.json"
API_DOCS_MARKDOWN_PATH = BASE_DIR / "docs" / "API.md"
COMFY_API_DOCS_MARKDOWN_PATH = BASE_DIR / "docs" / "COMFYUI_API.md"

BAD_FEEDBACK_TAGS = {
    # New primary tags
    "wrong_subject",
    "person_missing",
    "main_object_missing",
    "wrong_composition",
    "too_empty",
    "same_as_input",
    "style_too_weak",
    "bad_colors",
    "low_quality",
    "over_changed",
    "too_realistic",
    "scary_or_creepy",
    # Existing tags kept for compatibility and richer tuning
    "wrong_generation",
    "person_changed",
    "face_changed",
    "artwork_missing",
    "artwork_changed",
    "object_missing",
    "object_changed",
    "background_wrong",
    "background_not_changed",
    "background_too_plain",
    "gender_changed",
    "clothing_changed",
    "shirt_changed",
    "outfit_changed",
    "person_unrecognizable",
    "face_identity_changed",
    "creation_unrecognizable",
    "too_messy",
    "not_lively_enough",
    "changed_too_much",
    "too_much_change",
    "too_cartoon",
    "bad_face",
    "bad_hands",
    "too_dark",
    "blurry",
    "creepy",
    "text_or_watermark",
    "composition_wrong",
    "style_wrong",
    "wrong_animal",
    "wrong_species",
    "lion_detected_as_tiger",
    "lion_became_cat",
    "tiger_became_lion",
    "zebra_wrong",
    "zebra_became_horse",
    "elephant_wrong",
    "elephant_missing_trunk",
    "tiger_wrong",
    "too_unchanged",
    # Legacy compatibility tag kept to avoid rejecting existing flows.
    "too_close_to_drawing",
}

GOOD_FEEDBACK_TAGS = {
    "good_preserve_shape",
    "good_preserve_person",
    "good_preserve_artwork",
    "good_lively",
    "good_colors",
    "good_style",
    "good_overall",
    "good_preserve_identity",
    "good_preserve_clothing",
    "good_preserve_creation",
    "good_background_change",
    "good_style_change",
    "style_good_identity_good",
}

ALLOWED_FEEDBACK_TAGS = BAD_FEEDBACK_TAGS | GOOD_FEEDBACK_TAGS
WRONG_SUBJECT_TAGS = {"wrong_subject", "wrong_generation"}
OVER_CHANGED_TAGS = {"over_changed", "changed_too_much", "too_much_change"}
WRONG_COMPOSITION_TAGS = {"wrong_composition", "composition_wrong"}
SCARY_TAGS = {"scary_or_creepy", "creepy"}
MISSING_SUBJECT_TAGS = {
    "person_missing",
    "main_object_missing",
    "artwork_missing",
    "object_missing",
}
IDENTITY_CLOTHING_TAGS = {
    "gender_changed",
    "clothing_changed",
    "shirt_changed",
    "outfit_changed",
    "person_unrecognizable",
    "face_identity_changed",
}
BACKGROUND_ISSUE_TAGS = {
    "background_wrong",
    "background_not_changed",
    "background_too_plain",
}
ARTWORK_RELATED_FAILURE_TAGS = {
    "main_object_missing",
    "artwork_missing",
    "artwork_changed",
    "creation_unrecognizable",
    "object_missing",
    "object_changed",
}
COMPARISON_SCORE_KEYS = (
    "subjectPreserved",
    "colorImprovement",
    "backgroundFullness",
    "styleQuality",
    "childFriendlyResult",
)

KNOWN_PRESETS = [
    "toddler_abstract_people",
    "kid_crayon",
    "sketch_lineart",
    "colored_drawing",
    "rough_low_color_drawing",
    "animal_coloring_page",
    "animal_drawing_from_holding_workflow",
    "default",
]
DEFAULT_GENERATION_ESTIMATE_SECONDS = 60
COMFY_STAFF_DURATION_SAMPLE_SIZE = 20
COMFY_STAFF_CONNECT_TIMEOUT_SECONDS = 3.0
COMFY_STAFF_READ_TIMEOUT_SECONDS = 8.0
MAX_RETRY_COUNT = 3

ALLOWED_REGENERATE_PROBLEM_TAGS = {
    # New primary tags
    "wrong_subject",
    "person_missing",
    "main_object_missing",
    "wrong_composition",
    "too_empty",
    "same_as_input",
    "style_too_weak",
    "bad_colors",
    "low_quality",
    "over_changed",
    "too_realistic",
    "scary_or_creepy",
    # Existing tags kept for compatibility
    "wrong_generation",
    "person_changed",
    "face_changed",
    "artwork_missing",
    "artwork_changed",
    "object_missing",
    "object_changed",
    "background_wrong",
    "background_not_changed",
    "background_too_plain",
    "gender_changed",
    "clothing_changed",
    "shirt_changed",
    "outfit_changed",
    "person_unrecognizable",
    "face_identity_changed",
    "creation_unrecognizable",
    "too_messy",
    "not_lively_enough",
    "changed_too_much",
    "too_much_change",
    "too_cartoon",
    "bad_face",
    "bad_hands",
    "too_dark",
    "blurry",
    "creepy",
    "text_or_watermark",
    "composition_wrong",
    "style_wrong",
    "wrong_animal",
    "wrong_species",
    "lion_detected_as_tiger",
    "lion_became_cat",
    "tiger_became_lion",
    "zebra_wrong",
    "zebra_became_horse",
    "elephant_wrong",
    "elephant_missing_trunk",
    "tiger_wrong",
    "too_unchanged",
    # Legacy compatibility tag kept to avoid rejecting existing flows.
    "too_close_to_drawing",
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
REGENERATE_WRONG_GENERATION_PROMPT = (
    "Use the selected generation mode and style routing exactly. Keep the same source image and regenerate "
    "with correct subject intent."
)
REGENERATE_PRESERVE_PERSON_PROMPT = (
    "preserve exact person, face, pose, expression, body proportions, and clothing from the original input"
)
REGENERATE_PRESERVE_ARTWORK_PROMPT = (
    "preserve exact artwork design, paper position, drawing lines, and layout from the original input"
)
REGENERATE_RICH_BACKGROUND_PROMPT = (
    "rich environment, full background, playful scene, no empty white areas, lively storytelling atmosphere"
)
REGENERATE_DRAWING_LIVELY_PROMPT = (
    "Make the result more lively and colorful with rich playful background details while preserving the original child drawing identity and shapes."
)
DRAWING_REGENERATE_DENOISE_MIN = 0.45
DRAWING_REGENERATE_DENOISE_MAX = 0.68
DRAWING_REGENERATE_CONTROL_WEIGHT_MIN = 0.62
DRAWING_REGENERATE_CONTROL_WEIGHT_MAX = 0.88
DRAWING_REGENERATE_CFG_MIN = 7.0
DRAWING_REGENERATE_CFG_MAX = 9.0
ANIMAL_COLORING_PAGE_PRESET_NAME = "animal_coloring_page"
DRAWING_TO_ARTWORK_CHECKPOINT = "DreamShaper_8_pruned.safetensors [879db523c3]"
DRAWING_TO_ARTWORK_CONTROL_WEIGHT = 0.78
DRAWING_TO_ARTWORK_DENOISING_STRENGTH = 0.52
DRAWING_TO_ARTWORK_CONTROL_MODE = "Balanced"
DRAWING_TO_ARTWORK_CFG_SCALE = 8.0
DRAWING_TO_ARTWORK_STEPS = 32
DRAWING_TO_ARTWORK_SAMPLER_NAME = "DPM++ 2M Karras"
DRAWING_TO_ARTWORK_WIDTH = 768
DRAWING_TO_ARTWORK_HEIGHT = 768
DRAWING_TO_ARTWORK_CONTROLNET_MODULE = "pidinet_scribble"
DRAWING_TO_ARTWORK_CONTROLNET_MODEL = "control_v11p_sd15_scribble [4e6af23e]"
ANIMAL_COLORING_PAGE_CHECKPOINT = "DreamShaper_8_pruned.safetensors [879db523c3]"
ANIMAL_COLORING_PAGE_CONTROL_WEIGHT = 0.72
ANIMAL_COLORING_PAGE_DENOISING_STRENGTH = 0.58
ANIMAL_COLORING_PAGE_CONTROL_MODE = "Balanced"
ANIMAL_COLORING_PAGE_CFG_SCALE = 8.2
ANIMAL_COLORING_PAGE_STEPS = 32
ANIMAL_COLORING_PAGE_SAMPLER_NAME = "DPM++ 2M Karras"
ANIMAL_COLORING_PAGE_WIDTH = 768
ANIMAL_COLORING_PAGE_HEIGHT = 768
ANIMAL_COLORING_PAGE_CONTROLNET_MODULE = "pidinet_scribble"
ANIMAL_COLORING_PAGE_CONTROLNET_MODEL = "control_v11p_sd15_scribble [4e6af23e]"
ANIMAL_DRAWING_FROM_HOLDING_WORKFLOW_PRESET_NAME = "animal_drawing_from_holding_workflow"
ANIMAL_DRAWING_FROM_HOLDING_BASED_ON_PRESET = "people_holding_artwork"
ANIMAL_DRAWING_FROM_HOLDING_CHECKPOINT = "DreamShaper_8_pruned.safetensors [879db523c3]"
ANIMAL_DRAWING_FROM_HOLDING_CONTROL_WEIGHT = 0.68
ANIMAL_DRAWING_FROM_HOLDING_DENOISING_STRENGTH = 0.62
ANIMAL_DRAWING_FROM_HOLDING_CONTROL_MODE = "My prompt is more important"
ANIMAL_DRAWING_FROM_HOLDING_CFG_SCALE = 8.0
ANIMAL_DRAWING_FROM_HOLDING_STEPS = 32
ANIMAL_DRAWING_FROM_HOLDING_SAMPLER_NAME = "DPM++ 2M Karras"
ANIMAL_DRAWING_FROM_HOLDING_WIDTH = 768
ANIMAL_DRAWING_FROM_HOLDING_HEIGHT = 768
ANIMAL_DRAWING_FROM_HOLDING_CONTROLNET_MODULE = "pidinet_scribble"
ANIMAL_DRAWING_FROM_HOLDING_CONTROLNET_MODEL = "control_v11p_sd15_scribble [4e6af23e]"
ANIMAL_DRAWING_FROM_HOLDING_PROMPT = (
    "Transform the submitted child-colored animal drawing into a lively, colorful, polished children's storybook "
    "illustration. Preserve the original main subject, overall composition, childlike creative charm, and the "
    "child's main color choices. Keep the result clearly inspired by the original drawing, but repaint it as a "
    "cleaner, richer, more expressive, and more finished illustration. Make the animal drawing cute, cheerful, "
    "playful, and full of life. Add clean cartoon shapes, richer colors, soft shading, highlights, playful details, "
    "warm cheerful lighting, and a polished children's book illustration look. Add a bright child-friendly background "
    "that matches the drawing subject, with playful scenery, soft sky, grass, flowers, trees, bushes, magical "
    "details, and a joyful storybook atmosphere. Do not keep it looking like a plain scanned drawing. Do not leave "
    "the background empty. Do not change the main subject into something unrelated. Do not remove the main subject. "
    "Keep the final image strongly based on the original child drawing while making it much more lively, colorful, "
    "polished, and visually exciting. Style: cute cartoon storybook illustration, children's book art, polished, "
    "vibrant colors, warm lighting, soft shading, playful, magical, cheerful, child-friendly, not photorealistic."
)
ANIMAL_DRAWING_FROM_HOLDING_NEGATIVE_PROMPT = (
    "wrong animal, changed subject, missing main subject, subject removed, unrelated object, plain background, empty "
    "background, white background, gray background, unfinished sketch, same as input, unchanged drawing, dull colors, "
    "monochrome, boring, low detail, messy artifacts, scary, horror, photorealistic, realistic photo, ugly, "
    "deformed, distorted, blurry, low quality, text, watermark, logo"
)
ANIMAL_DRAWING_FROM_HOLDING_LORA_TOKEN_RE = re.compile(
    r"<lora:([^:>]+):([0-9]*\\.?[0-9]+)>",
    re.IGNORECASE,
)
DRAWING_TO_ARTWORK_PRESET_ANIMAL_UNKNOWN = "unknown"
DRAWING_TO_ARTWORK_SPECIES_BASE_PROMPT = (
    "Transform the submitted child-colored animal drawing into a lively, colorful, polished children's storybook "
    "illustration. Enhance the colors, lighting, background, and details while preserving the exact original animal "
    "species, pose, outline, composition, and childlike coloring style. Do not change the animal type. Keep the animal "
    "clearly recognizable as the selected preset animal. Make the result bright, cheerful, playful, finished, and "
    "suitable for children."
)
DRAWING_TO_ARTWORK_SPECIES_NEGATIVE_PROMPT = (
    "wrong animal, changed species, species swap, different animal, cat, kitten, house cat, dog, wolf, fox, horse, "
    "donkey, cow, bear, empty background, plain white background, dull colors, unfinished, same as input, boring, "
    "low detail, blurry, low quality, watermark, text, logo"
)
DRAWING_TO_ARTWORK_SPECIES_OVERRIDES = {
    "lion": (
        "This is a LION coloring page. Keep it clearly a lion. Preserve the lion mane, lion face shape, lion body, "
        "tail, and safari animal look. Do not turn it into a tiger, cat, kitten, dog, or other animal."
    ),
    "zebra": (
        "This is a ZEBRA coloring page. Keep it clearly a zebra. Preserve black-and-white zebra stripes, zebra body "
        "shape, head, legs, and tail. Do not turn it into a horse, donkey, tiger, or other animal."
    ),
    "elephant": (
        "This is an ELEPHANT coloring page. Keep it clearly an elephant. Preserve the trunk, big ears, elephant body "
        "shape, legs, and tail. Do not turn it into another animal."
    ),
    "tiger": (
        "This is a TIGER coloring page. Keep it clearly a tiger. Preserve tiger stripes, tiger face shape, tiger "
        "body, tail, and wild tiger look. Do not turn it into a lion, cat, kitten, dog, or other animal."
    ),
}
DRAWING_TO_ARTWORK_SPECIES_NEGATIVE_OVERRIDES = {
    "lion": "tiger, tiger stripes, cat, kitten, house cat, no mane, missing mane",
    "tiger": "lion, lion mane, cat, kitten, house cat, missing stripes",
    "zebra": "horse, donkey, no stripes, missing stripes, tiger stripes",
    "elephant": "no trunk, missing trunk, small ears, wrong animal",
}
DRAWING_TO_ARTWORK_PRESET_ANIMALS = tuple(DRAWING_TO_ARTWORK_SPECIES_OVERRIDES.keys())
DRAWING_TO_ARTWORK_ALLOWED_PRESET_ANIMALS = (
    *DRAWING_TO_ARTWORK_PRESET_ANIMALS,
    DRAWING_TO_ARTWORK_PRESET_ANIMAL_UNKNOWN,
)
DRAWING_TO_ARTWORK_WHITE_BG_APPEND = (
    "Fill the empty paper/background area with a cheerful full storybook background matching the animal. Do not leave "
    "the background empty."
)
DRAWING_TO_ARTWORK_WHITE_BG_ANIMAL_APPEND = {
    "lion": "Use a sunny safari grassland background.",
    "zebra": "Use a bright savanna grassland background.",
    "elephant": "Use a playful jungle or savanna background.",
    "tiger": "Use a lush jungle background.",
}
DRAWING_TO_ARTWORK_STRONG_SPECIES_APPEND = (
    "Strict animal identity lock: preserve the exact selected animal species and key body traits. Never perform a "
    "species swap."
)
DRAWING_TO_ARTWORK_SPECIES_REGENERATE_TAGS = {
    "wrong_animal",
    "wrong_species",
    "lion_detected_as_tiger",
    "lion_became_cat",
    "tiger_became_lion",
    "zebra_wrong",
    "zebra_became_horse",
    "elephant_wrong",
    "elephant_missing_trunk",
    "tiger_wrong",
}
CUSTOMER_ANIMAL_ROUTE_VALUES = (
    "lion",
    "zebra",
    "elephant",
    "tiger",
    DRAWING_TO_ARTWORK_PRESET_ANIMAL_UNKNOWN,
)

GENERATION_MODE_DRAWING_TO_ARTWORK = "drawing_to_artwork"
GENERATION_MODE_PERSON_HOLDING_ARTWORK = "person_holding_artwork"
GENERATION_MODE_AI_ART_VENTURE = AI_ART_VENTURE_MODE_ID

GENERATION_MODE_ALIASES = {
    GENERATION_MODE_DRAWING_TO_ARTWORK: GENERATION_MODE_DRAWING_TO_ARTWORK,
    "drawing to artwork": GENERATION_MODE_DRAWING_TO_ARTWORK,
    GENERATION_MODE_PERSON_HOLDING_ARTWORK: GENERATION_MODE_PERSON_HOLDING_ARTWORK,
    "person holding artwork": GENERATION_MODE_PERSON_HOLDING_ARTWORK,
    GENERATION_MODE_AI_ART_VENTURE: GENERATION_MODE_AI_ART_VENTURE,
    "ai art venture": GENERATION_MODE_AI_ART_VENTURE,
}

GENERATION_MODE_LABELS = {
    GENERATION_MODE_DRAWING_TO_ARTWORK: "Drawing to Artwork",
    GENERATION_MODE_PERSON_HOLDING_ARTWORK: "Person Holding Artwork",
    GENERATION_MODE_AI_ART_VENTURE: AI_ART_VENTURE_MODE_LABEL,
}

GENERATION_MODE_PROMPT_HINTS = {
    GENERATION_MODE_DRAWING_TO_ARTWORK: (
        "Convert drawing to artwork while preserving composition, character identity, and object placement. "
        "Keep it lively with vibrant colors, warm light, playful atmosphere, and a full detailed background."
    ),
    GENERATION_MODE_PERSON_HOLDING_ARTWORK: (
        "Preserve exact person, face, pose, clothing, and exact artwork design and paper position in hands. "
        "Keep the output polished, colorful, child-friendly, and visually rich."
    ),
    GENERATION_MODE_AI_ART_VENTURE: (
        "Image-to-image transformation only. Keep the exact person identity, face, hairstyle, clothing, body pose, "
        "hand position, artwork/object shape and position, camera framing, and composition unchanged."
    ),
}

STYLE_PROMPT_HINTS = {
    "storybook": "children's storybook illustration style",
    "storybook_plus": "highly polished children's storybook illustration style",
    "watercolor": "soft watercolor illustration style",
    "cartoon": "playful stylized cartoon illustration style",
    "anime": "clean anime-inspired illustration style",
    "pixel": "pixel art illustration style",
    "auto": "children's storybook illustration style with vibrant colors, warm lighting, and rich playful scenery",
}

DEFAULT_GENERATION_MODE = GENERATION_MODE_DRAWING_TO_ARTWORK
DEFAULT_STYLE_ID = "auto"
API_KEY_HEADER = "X-API-Key"
AI_ART_VENTURE_EXTRA_METADATA_KEYS = (
    "mode",
    "aiArtVentureEnabled",
    "randomStyleEnabled",
    "randomThemeEnabled",
    "selectedStyleId",
    "selectedThemeId",
    "customTheme",
    "finalStyleId",
    "finalStyleName",
    "finalThemeId",
    "finalThemeName",
    "styleRiskLevel",
    "softEdgeWeight",
    "samplerName",
    "ipAdapterEnabled",
    "ipAdapterType",
    "ipAdapterWarning",
    "ipAdapterWeight",
    "identityGuidanceUsed",
    "identityTarget",
    "promptUsed",
    "negativePromptUsed",
    "backgroundType",
    "whiteBackgroundRatio",
    "finalDenoisingStrength",
    "finalControlWeight",
    "finalPrompt",
    "identitySafetyMode",
    "experimentalMode",
)
DRAWING_TO_ARTWORK_EXTRA_METADATA_KEYS = (
    "presetAnimal",
    "speciesPromptUsed",
    "basedOnPreset",
    "loraUsed",
    "loraName",
)

AI_ART_VENTURE_GENERATION_METADATA_FIELDS = (
    "styleRiskLevel",
    "softEdgeWeight",
    "samplerName",
    "backgroundType",
    "whiteBackgroundRatio",
    "finalDenoisingStrength",
    "finalControlWeight",
    "finalPrompt",
    "promptUsed",
    "negativePromptUsed",
    "identitySafetyMode",
    "experimentalMode",
    "ipAdapterEnabled",
    "ipAdapterType",
    "ipAdapterWarning",
    "ipAdapterWeight",
    "identityGuidanceUsed",
    "identityTarget",
)
DRAWING_TO_ARTWORK_GENERATION_METADATA_FIELDS = (
    "presetAnimal",
    "speciesPromptUsed",
    "basedOnPreset",
    "loraUsed",
    "loraName",
)


class ComparisonScoresRequest(BaseModel):
    subjectPreserved: Optional[conint(ge=1, le=5)] = None  # type: ignore[valid-type]
    colorImprovement: Optional[conint(ge=1, le=5)] = None  # type: ignore[valid-type]
    backgroundFullness: Optional[conint(ge=1, le=5)] = None  # type: ignore[valid-type]
    styleQuality: Optional[conint(ge=1, le=5)] = None  # type: ignore[valid-type]
    childFriendlyResult: Optional[conint(ge=1, le=5)] = None  # type: ignore[valid-type]

    def to_payload(self) -> Dict[str, int]:
        payload = self.dict(exclude_none=True)
        return {str(key): int(value) for key, value in payload.items()}


class RatingRequest(BaseModel):
    rating: conint(ge=1, le=5)  # type: ignore[valid-type]
    feedbackTags: List[str] = Field(default_factory=list)
    feedbackNote: str = ""
    comparisonScores: Optional[ComparisonScoresRequest] = None

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
    generationMode: Optional[str] = None
    styleId: Optional[str] = None

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

    @validator("generationMode")
    def normalize_generation_mode_value(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _normalize_generation_mode(value)

    @validator("styleId")
    def normalize_style_id_value(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _normalize_style_id(value)


class CleanupRequest(BaseModel):
    olderThanDays: Optional[int] = Field(default=None, ge=1)
    keepNewest: Optional[int] = Field(default=None, ge=1)


def _normalize_visitor_name(value: Optional[str]) -> str:
    cleaned = (value or "").strip()
    return cleaned if cleaned else "Guest"


def _normalize_generation_mode(value: Optional[str]) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return DEFAULT_GENERATION_MODE
    normalized = cleaned.lower().replace("-", "_")
    return GENERATION_MODE_ALIASES.get(normalized, cleaned)


def _normalize_style_id(value: Optional[str]) -> str:
    cleaned = str(value or "").strip()
    return cleaned.lower() if cleaned else DEFAULT_STYLE_ID


def _normalize_preset_animal(value: Optional[str], *, allow_unknown: bool = True) -> str:
    cleaned = str(value or "").strip().lower()
    if cleaned in DRAWING_TO_ARTWORK_PRESET_ANIMALS:
        return cleaned
    if allow_unknown and cleaned == DRAWING_TO_ARTWORK_PRESET_ANIMAL_UNKNOWN:
        return cleaned
    return ""


def _extract_preset_animal_keyword(value: Optional[str]) -> str:
    lowered = str(value or "").strip().lower()
    if not lowered:
        return ""
    for animal in DRAWING_TO_ARTWORK_PRESET_ANIMALS:
        if animal in lowered:
            return animal
    return ""


def _extract_wonderpark_animals_from_url(url_value: Optional[str]) -> tuple[str, str]:
    raw = str(url_value or "").strip()
    if not raw:
        return "", ""
    try:
        parsed = urlparse(raw)
    except Exception:
        return "", ""

    query_animal = _normalize_preset_animal(
        (parse_qs(parsed.query).get("animal") or [""])[0],
        allow_unknown=True,
    )
    path_animal = ""
    path_text = str(parsed.path or "")
    path_parts = [part for part in path_text.split("/") if part]
    if len(path_parts) >= 3 and path_parts[0] == "public" and path_parts[1] == "wonderpark":
        path_animal = _normalize_preset_animal(path_parts[2], allow_unknown=True)
    return query_animal, path_animal


def _resolve_customer_preset_animal(
    *,
    upload_query_animal: Optional[str],
    upload_path_animal: Optional[str],
    referrer_url: Optional[str],
    paper_template_id: Optional[str],
    filename: Optional[str],
    form_preset_animal: Optional[str],
) -> tuple[str, str]:
    direct_query = _normalize_preset_animal(upload_query_animal, allow_unknown=True)
    direct_path = _normalize_preset_animal(upload_path_animal, allow_unknown=True)
    ref_query, ref_path = _extract_wonderpark_animals_from_url(referrer_url)
    template_from_id = _extract_preset_animal_keyword(paper_template_id)
    template_from_form = _normalize_preset_animal(form_preset_animal, allow_unknown=True)
    filename_guess = _extract_preset_animal_keyword(filename)

    candidates: List[tuple[str, str, bool]] = [
        ("query_param_animal", direct_query or ref_query, True),
        ("path_animal", direct_path or ref_path, True),
        ("template_metadata", template_from_id or template_from_form, True),
        ("filename_hint", filename_guess, False),
    ]
    for source_name, candidate, allow_unknown in candidates:
        normalized = _normalize_preset_animal(candidate, allow_unknown=allow_unknown)
        if normalized:
            return normalized, source_name

    return DRAWING_TO_ARTWORK_PRESET_ANIMAL_UNKNOWN, "unknown"


def _has_species_preservation_problem_tags(problem_tags: Any) -> bool:
    if not isinstance(problem_tags, (list, tuple, set)):
        return False
    for tag in problem_tags:
        tag_key = str(tag or "").strip().lower()
        if tag_key in DRAWING_TO_ARTWORK_SPECIES_REGENERATE_TAGS:
            return True
    return False


def _parse_bool_form(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return bool(default)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _parse_optional_int_form(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _parse_optional_float_form(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _safe_form_text(value: Optional[str], max_len: int = 8000) -> str:
    cleaned = str(value or "").strip()
    if max_len > 0 and len(cleaned) > max_len:
        return cleaned[:max_len]
    return cleaned


def _normalize_comfy_style_preset(value: Optional[str]) -> str:
    cleaned = _safe_form_text(value, max_len=120)
    if not cleaned:
        return "random"
    if cleaned.lower() == "random":
        return "random"
    return cleaned


def _build_ai_art_venture_staff_extra_fields(
    *,
    mode_value: Optional[str],
    ai_art_venture_enabled: bool,
    random_style_enabled: bool,
    random_theme_enabled: bool,
    selected_style_id: Optional[str],
    selected_theme_id: Optional[str],
    custom_theme: Optional[str],
    final_style_id: Optional[str],
    final_style_name: Optional[str],
    final_theme_id: Optional[str],
    final_theme_name: Optional[str],
) -> Dict[str, Any]:
    mode_clean = _safe_form_text(mode_value, max_len=64).lower().replace("_", "-")
    resolved_mode = "ai-art-venture" if ai_art_venture_enabled else "normal"
    if mode_clean == "normal":
        resolved_mode = "normal"
    elif mode_clean == "ai-art-venture" and ai_art_venture_enabled:
        resolved_mode = "ai-art-venture"
    return {
        "mode": resolved_mode,
        "aiArtVentureEnabled": bool(ai_art_venture_enabled),
        "randomStyleEnabled": bool(random_style_enabled),
        "randomThemeEnabled": bool(random_theme_enabled),
        "selectedStyleId": _safe_form_text(selected_style_id, max_len=120),
        "selectedThemeId": _safe_form_text(selected_theme_id, max_len=120),
        "customTheme": _safe_form_text(custom_theme, max_len=4000),
        "finalStyleId": _safe_form_text(final_style_id, max_len=120),
        "finalStyleName": _safe_form_text(final_style_name, max_len=200),
        "finalThemeId": _safe_form_text(final_theme_id, max_len=120),
        "finalThemeName": _safe_form_text(final_theme_name, max_len=200),
    }


def _build_ai_art_venture_staff_preset_override(
    style_id: str,
    final_prompt: Optional[str],
    negative_prompt: Optional[str],
) -> tuple[Optional[PresetSettings], Optional[Dict[str, Any]], Dict[str, Any]]:
    prompt_override = _safe_form_text(final_prompt, max_len=12000)
    negative_override = _safe_form_text(negative_prompt, max_len=12000)
    if not prompt_override and not negative_override:
        return None, None, {}

    base_preset, base_settings, _base_meta = build_ai_art_venture_preset(style_id, background_analysis={})
    prompt_used = prompt_override or str(base_preset.prompt or "").strip()
    negative_used = negative_override or str(base_preset.negative_prompt or "").strip()
    override_preset = PresetSettings(
        name=base_preset.name,
        control_weight=base_preset.control_weight,
        denoising_strength=base_preset.denoising_strength,
        control_mode=base_preset.control_mode,
        cfg_scale=base_preset.cfg_scale,
        steps=base_preset.steps,
        sampler_name=base_preset.sampler_name,
        prompt=prompt_used,
        negative_prompt=negative_used,
        prompt_mode=base_preset.prompt_mode,
    )

    override_settings = dict(base_settings or {})
    override_settings["prompt"] = prompt_used
    override_settings["finalPrompt"] = prompt_used
    override_settings["promptUsed"] = prompt_used
    override_settings["negativePrompt"] = negative_used
    override_settings["negativePromptUsed"] = negative_used
    meta = {
        "finalPrompt": prompt_used,
        "promptUsed": prompt_used,
        "negativePromptUsed": negative_used,
    }
    return override_preset, override_settings, meta


def _resolve_mode_and_style_ids(
    generation_mode: Optional[str],
    style_id: Optional[str],
) -> tuple[str, str]:
    normalized_mode = _normalize_generation_mode(generation_mode)
    normalized_style = _normalize_style_id(style_id)
    if normalized_mode == GENERATION_MODE_AI_ART_VENTURE and normalized_style.lower() == "auto":
        config = get_ai_art_venture_mode_payload_for_ui()
        normalized_style = str(config.get("defaultStyleId") or "pixar_3d")
    return normalized_mode, normalized_style


def _resolve_style_label(generation_mode: str, style_id: str) -> str:
    if generation_mode == GENERATION_MODE_AI_ART_VENTURE:
        config = get_ai_art_venture_mode_payload_for_ui()
        styles = config.get("styles", [])
        for style in styles:
            if not isinstance(style, dict):
                continue
            if str(style.get("id") or "").strip().lower() == str(style_id or "").strip().lower():
                return str(style.get("label") or style_id)
        return str(style_id or "Style")
    if not style_id or style_id == "auto":
        return "Auto"
    return str(style_id).replace("_", " ").title()


def _resolve_ai_art_style_metadata(style_id: str) -> Dict[str, str]:
    config = get_ai_art_venture_mode_payload_for_ui()
    styles = config.get("styles", [])
    target = str(style_id or "").strip().lower()
    for style in styles:
        if not isinstance(style, dict):
            continue
        row_id = str(style.get("id") or "").strip().lower()
        if row_id != target:
            continue
        risk = str(style.get("styleRiskLevel") or "balanced").strip().lower()
        if risk not in {"safe", "balanced", "experimental"}:
            risk = "balanced"
        return {
            "styleId": str(style.get("id") or style_id or ""),
            "styleLabel": str(style.get("label") or style_id or "Style"),
            "styleRiskLevel": risk,
        }
    return {
        "styleId": str(style_id or ""),
        "styleLabel": _resolve_style_label(GENERATION_MODE_AI_ART_VENTURE, style_id),
        "styleRiskLevel": "balanced",
    }


def _normalize_source(value: Optional[str]) -> str:
    cleaned = str(value or "").strip().lower()
    if cleaned == "api":
        return "api"
    if cleaned == "public_wonderpark":
        return "public_wonderpark"
    return "staff"


def _append_prompt_sentence(base_prompt: str, sentence: str) -> str:
    prompt = str(base_prompt or "").strip()
    addition = str(sentence or "").strip().rstrip(".")
    if not addition:
        return prompt
    if addition.lower() in prompt.lower():
        return prompt
    if prompt and not prompt.endswith("."):
        prompt = f"{prompt}."
    if prompt:
        return f"{prompt} {addition}."
    return f"{addition}."


def _is_animal_drawing_from_holding_workflow_preset(preset_name: Optional[str]) -> bool:
    return (
        str(preset_name or "").strip().lower()
        == ANIMAL_DRAWING_FROM_HOLDING_WORKFLOW_PRESET_NAME
    )


def _extract_lora_metadata_from_prompt(prompt_text: str) -> Dict[str, Any]:
    prompt = str(prompt_text or "")
    match = ANIMAL_DRAWING_FROM_HOLDING_LORA_TOKEN_RE.search(prompt)
    if not match:
        return {
            "loraUsed": False,
            "loraName": "",
        }
    return {
        "loraUsed": True,
        "loraName": str(match.group(1) or "").strip(),
    }


def _apply_animal_drawing_holding_metadata(
    settings: Dict[str, Any],
    *,
    prompt_text: str,
) -> None:
    if not isinstance(settings, dict):
        return
    lora_meta = _extract_lora_metadata_from_prompt(prompt_text)
    settings["basedOnPreset"] = ANIMAL_DRAWING_FROM_HOLDING_BASED_ON_PRESET
    settings["identityGuidanceUsed"] = False
    settings["loraUsed"] = bool(lora_meta.get("loraUsed"))
    settings["loraName"] = str(lora_meta.get("loraName") or "")


def _build_drawing_species_prompt_bundle(
    *,
    prompt: str,
    negative_prompt: str,
    preset_animal: str,
    white_background_ratio: float,
    strong_species: bool = False,
) -> tuple[str, str, str]:
    species_prompt = DRAWING_TO_ARTWORK_SPECIES_BASE_PROMPT
    normalized_animal = _normalize_preset_animal(preset_animal, allow_unknown=True)
    if normalized_animal and normalized_animal != DRAWING_TO_ARTWORK_PRESET_ANIMAL_UNKNOWN:
        species_prompt = _append_prompt_sentence(
            species_prompt,
            DRAWING_TO_ARTWORK_SPECIES_OVERRIDES.get(normalized_animal, ""),
        )
    elif normalized_animal == DRAWING_TO_ARTWORK_PRESET_ANIMAL_UNKNOWN:
        species_prompt = _append_prompt_sentence(
            species_prompt,
            "Selected animal is unknown. Preserve the exact original animal species from the uploaded drawing.",
        )
    if white_background_ratio > 0.50:
        species_prompt = _append_prompt_sentence(species_prompt, DRAWING_TO_ARTWORK_WHITE_BG_APPEND)
        species_prompt = _append_prompt_sentence(
            species_prompt,
            DRAWING_TO_ARTWORK_WHITE_BG_ANIMAL_APPEND.get(normalized_animal, ""),
        )
    if strong_species:
        species_prompt = _append_prompt_sentence(species_prompt, DRAWING_TO_ARTWORK_STRONG_SPECIES_APPEND)
        species_prompt = _append_prompt_sentence(
            species_prompt,
            DRAWING_TO_ARTWORK_SPECIES_OVERRIDES.get(normalized_animal, ""),
        )

    final_prompt = _append_prompt_sentence(species_prompt, prompt)
    negative_prompt_seed = _append_prompt_sentence(
        DRAWING_TO_ARTWORK_SPECIES_NEGATIVE_PROMPT,
        DRAWING_TO_ARTWORK_SPECIES_NEGATIVE_OVERRIDES.get(normalized_animal, ""),
    )
    final_negative_prompt = _append_prompt_sentence(
        negative_prompt_seed,
        negative_prompt,
    )
    return final_prompt, final_negative_prompt, species_prompt


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _sync_generation_metadata_fields(target: Dict[str, Any], settings: Optional[Dict[str, Any]]) -> None:
    if not isinstance(target, dict) or not isinstance(settings, dict):
        return
    direct_fields = (
        "generationEngine",
        "backendPromptId",
        "backendMetadata",
        "stylePreset",
        "style_preset",
        "stylePresetId",
        "stylePresetName",
        "styleCategory",
        "checkpoint",
        "controlNetModel",
        "controlNetModule",
        "denoisingStrength",
        "controlWeight",
        "softEdgeWeight",
        "controlMode",
        "cfgScale",
        "steps",
    )
    for key in (
        *direct_fields,
        *AI_ART_VENTURE_GENERATION_METADATA_FIELDS,
        *DRAWING_TO_ARTWORK_GENERATION_METADATA_FIELDS,
    ):
        if target.get(key) is None and settings.get(key) is not None:
            target[key] = settings.get(key)

    if _is_empty_value(target.get("finalPrompt")) and settings.get("finalPrompt"):
        target["finalPrompt"] = settings.get("finalPrompt")
    if _is_empty_value(target.get("promptUsed")) and settings.get("promptUsed"):
        target["promptUsed"] = settings.get("promptUsed")
    if _is_empty_value(target.get("negativePromptUsed")) and settings.get("negativePromptUsed"):
        target["negativePromptUsed"] = settings.get("negativePromptUsed")


def _overwrite_generation_metadata_fields(target: Dict[str, Any], settings: Optional[Dict[str, Any]]) -> None:
    if not isinstance(target, dict) or not isinstance(settings, dict):
        return
    direct_fields = (
        "generationEngine",
        "backendPromptId",
        "backendMetadata",
        "stylePreset",
        "style_preset",
        "stylePresetId",
        "stylePresetName",
        "styleCategory",
        "checkpoint",
        "controlNetModel",
        "controlNetModule",
        "denoisingStrength",
        "controlWeight",
        "softEdgeWeight",
        "controlMode",
        "cfgScale",
        "steps",
    )
    for key in (
        *direct_fields,
        *AI_ART_VENTURE_GENERATION_METADATA_FIELDS,
        *DRAWING_TO_ARTWORK_GENERATION_METADATA_FIELDS,
    ):
        if key in settings:
            target[key] = settings.get(key)
    if settings.get("finalPrompt"):
        target["finalPrompt"] = settings.get("finalPrompt")
    if settings.get("promptUsed"):
        target["promptUsed"] = settings.get("promptUsed")
    if settings.get("negativePromptUsed"):
        target["negativePromptUsed"] = settings.get("negativePromptUsed")


def _apply_mode_style_prompt(base_prompt: str, generation_mode: str, style_id: str) -> str:
    prompt = str(base_prompt or "").strip()
    if generation_mode == GENERATION_MODE_AI_ART_VENTURE:
        return prompt

    mode_hint = GENERATION_MODE_PROMPT_HINTS.get(generation_mode, "")
    if mode_hint:
        prompt = _append_prompt_sentence(prompt, mode_hint)
    prompt = _append_prompt_sentence(
        prompt,
        "Avoid dull or empty output; keep strong color contrast, cheerful mood, and full background detail.",
    )

    normalized_style = str(style_id or "").strip().lower()
    style_hint = STYLE_PROMPT_HINTS.get(normalized_style, "")
    if normalized_style and normalized_style != "auto" and not style_hint:
        style_hint = f"Use {normalized_style} illustration style consistently."
    if style_hint:
        prompt = _append_prompt_sentence(prompt, style_hint)
    return prompt


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
    for key in ("inputUrl", "outputUrl", "beforeImageUrl", "afterImageUrl", "photoPrintUrl"):
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


def _reload_runtime_generation_config() -> Dict[str, Any]:
    global RUNTIME_GENERATION_CONFIG
    RUNTIME_GENERATION_CONFIG = load_backend_runtime_config()
    return dict(RUNTIME_GENERATION_CONFIG)


def _normalize_generation_engine(value: Optional[str]) -> str:
    engine = str(value or "").strip().lower()
    if engine in {"stable_diffusion", "comfyui"}:
        return engine
    return "stable_diffusion"


def _resolve_generation_engine_name(preferred: Optional[str] = None) -> str:
    preferred_engine = _normalize_generation_engine(preferred)
    if preferred_engine in {"stable_diffusion", "comfyui"} and str(preferred or "").strip():
        return preferred_engine
    config = _reload_runtime_generation_config()
    return _normalize_generation_engine(config.get("generation_engine"))


def _get_generation_backend_for_engine(preferred: Optional[str] = None):
    config = _reload_runtime_generation_config()
    if preferred is not None:
        config["generation_engine"] = _normalize_generation_engine(preferred)
    backend = get_generation_backend(config)
    return backend, config


def _resolve_output_path_for_engine(job_id: str, generation_engine: str) -> Path:
    engine = _normalize_generation_engine(generation_engine)
    subfolder = "comfyui" if engine == "comfyui" else "stable_diffusion"
    output_path = OUTPUT_DIR / subfolder / f"{job_id}.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def _to_output_url(output_path: Path) -> str:
    try:
        rel_path = output_path.resolve().relative_to(OUTPUT_DIR.resolve())
        return f"/outputs/{rel_path.as_posix()}"
    except Exception:
        return f"/outputs/{output_path.name}"


def _check_generation_backend_health(preferred: Optional[str] = None) -> Dict[str, Any]:
    target_engine = _resolve_generation_engine_name(preferred)
    try:
        backend, config = _get_generation_backend_for_engine(target_engine)
    except Exception as exc:
        return {
            "mode": target_engine,
            "reachable": False,
            "error": str(exc),
        }

    try:
        status = backend.health_check()
    except Exception as exc:  # pragma: no cover - defensive
        status = {
            "mode": target_engine,
            "reachable": False,
            "error": str(exc),
        }

    if not isinstance(status, dict):
        status = {
            "mode": target_engine,
            "reachable": False,
            "error": "Invalid backend health response.",
        }
    status.setdefault("mode", target_engine)
    configured_engine = _normalize_generation_engine(config.get("generation_engine"))
    status["configuredEngine"] = configured_engine
    if target_engine == "comfyui":
        comfy_cfg = config.get("comfyui") if isinstance(config.get("comfyui"), dict) else {}
        workflow_path_raw = str(comfy_cfg.get("workflow_path") or "").strip()
        if workflow_path_raw:
            try:
                workflow_rel = (
                    Path(workflow_path_raw)
                    .resolve()
                    .relative_to(BASE_DIR.resolve())
                    .as_posix()
                )
                status["workflowPath"] = workflow_rel
            except Exception:
                status["workflowPath"] = workflow_path_raw
    return status


def _extract_generation_engine_from_payload(payload: Dict[str, Any]) -> str:
    settings = payload.get("generationSettings") if isinstance(payload.get("generationSettings"), dict) else {}
    return _normalize_generation_engine(
        payload.get("generationEngine")
        or settings.get("generationEngine")
        or "stable_diffusion"
    )


def _get_comfy_defaults() -> Dict[str, Any]:
    config = _reload_runtime_generation_config()
    comfy_cfg = config.get("comfyui") if isinstance(config.get("comfyui"), dict) else {}
    defaults = comfy_cfg.get("defaults") if isinstance(comfy_cfg.get("defaults"), dict) else {}
    return dict(defaults)


def _build_comfy_staff_preset(
    *,
    prompt: Optional[str],
    negative_prompt: Optional[str],
    steps: Optional[int] = None,
    cfg: Optional[float] = None,
    denoise: Optional[float] = None,
) -> PresetSettings:
    defaults = _get_comfy_defaults()
    default_steps = int(defaults.get("steps") or 4)
    default_cfg = float(defaults.get("cfg") or 1.0)
    default_denoise = float(defaults.get("denoise") or 1.0)
    return PresetSettings(
        name="comfy_staff",
        control_weight=0.0,
        denoising_strength=float(denoise if denoise is not None else default_denoise),
        control_mode="Balanced",
        cfg_scale=float(cfg if cfg is not None else default_cfg),
        steps=int(steps if steps is not None else default_steps),
        sampler_name=str(GENERATION_DEFAULTS.sampler_name),
        prompt=str(prompt or "").strip(),
        negative_prompt=str(negative_prompt or "").strip(),
        prompt_mode="comfy_staff",
    )


def _extract_recent_comfy_durations(sample_size: int = COMFY_STAFF_DURATION_SAMPLE_SIZE) -> List[float]:
    try:
        items = gallery_store.list_items(True)
    except Exception:
        return []

    durations: List[float] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if _extract_generation_engine_from_payload(item) != "comfyui":
            continue
        try:
            duration_value = float(item.get("durationSeconds"))
        except (TypeError, ValueError):
            continue
        if duration_value <= 0:
            continue
        durations.append(duration_value)
        if len(durations) >= sample_size:
            break
    return durations


def _fetch_comfyui_queue_snapshot() -> Dict[str, Any]:
    config = _reload_runtime_generation_config()
    comfy_cfg = config.get("comfyui") if isinstance(config.get("comfyui"), dict) else {}
    base_url = str(comfy_cfg.get("base_url") or "http://127.0.0.1:8188").rstrip("/")
    if not base_url:
        base_url = "http://127.0.0.1:8188"

    queue_url = f"{base_url}/queue"
    try:
        response = requests.get(
            queue_url,
            timeout=(COMFY_STAFF_CONNECT_TIMEOUT_SECONDS, COMFY_STAFF_READ_TIMEOUT_SECONDS),
        )
    except requests.RequestException as exc:
        return {
            "reachable": False,
            "error": f"ComfyUI queue request failed: {exc}",
            "baseUrl": base_url,
            "queueRunning": 0,
            "queuePending": 0,
            "queueTotal": 0,
            "raw": {},
        }

    if not response.ok:
        return {
            "reachable": False,
            "error": f"ComfyUI queue request failed ({response.status_code}).",
            "baseUrl": base_url,
            "queueRunning": 0,
            "queuePending": 0,
            "queueTotal": 0,
            "raw": {},
        }

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    running_items = payload.get("queue_running") if isinstance(payload.get("queue_running"), list) else []
    pending_items = payload.get("queue_pending") if isinstance(payload.get("queue_pending"), list) else []
    running_count = len(running_items)
    pending_count = len(pending_items)
    return {
        "reachable": True,
        "error": None,
        "baseUrl": base_url,
        "queueRunning": int(running_count),
        "queuePending": int(pending_count),
        "queueTotal": int(running_count + pending_count),
        "raw": payload if isinstance(payload, dict) else {},
    }


def _local_comfy_queue_snapshot() -> Dict[str, int]:
    snapshot = queue_store.queue_snapshot()
    processing_count = 0
    queued_count = 0
    for job in snapshot.get("jobs", []):
        if not isinstance(job, dict):
            continue
        if _extract_generation_engine_from_payload(job) != "comfyui":
            continue
        status = str(job.get("status") or "").strip().lower()
        if status == "processing":
            processing_count += 1
        elif status == "queued":
            queued_count += 1

    processing = snapshot.get("processing")
    if isinstance(processing, dict) and _extract_generation_engine_from_payload(processing) == "comfyui":
        if processing_count <= 0:
            processing_count = 1

    return {
        "queueRunning": int(max(processing_count, 0)),
        "queuePending": int(max(queued_count, 0)),
        "queueTotal": int(max(processing_count, 0) + max(queued_count, 0)),
    }


def _build_comfyui_estimate_payload() -> Dict[str, Any]:
    fallback_estimate = gallery_store.get_duration_estimate(DEFAULT_GENERATION_ESTIMATE_SECONDS)
    fallback_seconds = int(fallback_estimate.get("estimatedSeconds") or DEFAULT_GENERATION_ESTIMATE_SECONDS)
    if fallback_seconds <= 0:
        fallback_seconds = DEFAULT_GENERATION_ESTIMATE_SECONDS

    duration_samples = _extract_recent_comfy_durations()
    estimated_seconds_per_image = (
        int(round(sum(duration_samples) / len(duration_samples)))
        if duration_samples
        else fallback_seconds
    )
    if estimated_seconds_per_image <= 0:
        estimated_seconds_per_image = fallback_seconds

    queue_snapshot = _fetch_comfyui_queue_snapshot()
    queue_running = int(queue_snapshot.get("queueRunning") or 0)
    queue_pending = int(queue_snapshot.get("queuePending") or 0)
    queue_total = int(queue_snapshot.get("queueTotal") or 0)
    queue_source = "comfyui"

    if not bool(queue_snapshot.get("reachable")):
        local_queue = _local_comfy_queue_snapshot()
        queue_running = int(local_queue.get("queueRunning") or 0)
        queue_pending = int(local_queue.get("queuePending") or 0)
        queue_total = int(local_queue.get("queueTotal") or 0)
        queue_source = "local-fallback"

    return {
        "estimatedSecondsPerImage": int(estimated_seconds_per_image),
        "estimatedWaitSeconds": int(queue_total * estimated_seconds_per_image),
        "sampleCount": int(len(duration_samples)),
        "queueRunning": queue_running,
        "queuePending": queue_pending,
        "queueTotal": queue_total,
        "queueSource": queue_source,
        "queueReachable": bool(queue_snapshot.get("reachable")),
        "queueError": queue_snapshot.get("error"),
        "comfyBaseUrl": queue_snapshot.get("baseUrl"),
    }


def _build_comfy_staff_status_payload() -> Dict[str, Any]:
    backend_status = _check_generation_backend_health("comfyui")
    estimate = _build_comfyui_estimate_payload()
    defaults = _get_comfy_defaults()
    presets_count = 0
    preset_categories: List[str] = []
    presets_error = ""
    try:
        preset_payload = load_comfy_prompt_presets()
        presets = preset_payload.get("presets") if isinstance(preset_payload.get("presets"), list) else []
        presets_count = len(presets)
        preset_categories = sorted(
            {
                str(row.get("category") or "").strip()
                for row in presets
                if isinstance(row, dict) and str(row.get("category") or "").strip()
            }
        )
    except Exception as exc:
        presets_error = str(exc)
    return {
        "ok": bool(backend_status.get("reachable")),
        "backend": backend_status,
        "estimate": estimate,
        "defaults": defaults,
        "presetsCount": int(presets_count),
        "presetCategories": preset_categories,
        "presetsError": presets_error or None,
        "configuredEngine": _resolve_generation_engine_name(),
    }


def _wonderpark_feature_guard() -> None:
    if not WONDERPARK_PUBLIC_UPLOAD_ENABLED:
        raise HTTPException(status_code=404, detail="Wonderpark public upload is disabled.")


async def _ensure_wonderpark_generation_ready() -> None:
    backend_status = await run_in_threadpool(_check_generation_backend_health, "comfyui")
    if not bool(backend_status.get("reachable")):
        detail = str(
            backend_status.get("error")
            or "ComfyUI generation backend is not reachable for Wonderpark."
        )
        raise HTTPException(status_code=503, detail=detail)


def _wonderpark_client_ip(request: Request) -> str:
    forwarded_for = str(request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return str(request.client.host).strip()
    return "unknown"


def _sanitize_wonderpark_customer_name(value: Any) -> str:
    cleaned = " ".join(str(value or "").strip().split())
    if len(cleaned) > 60:
        cleaned = cleaned[:60].strip()
    return cleaned or "Guest"


def _safe_wonderpark_filename(value: Any) -> str:
    raw = Path(str(value or "").strip()).name
    if not raw:
        return "upload.png"
    cleaned = "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "_", ".", " "}).strip()
    return cleaned or "upload.png"


def _guess_ext_from_mime(mime_type: str) -> str:
    normalized = str(mime_type or "").strip().lower()
    if normalized == "image/jpeg":
        return ".jpg"
    if normalized == "image/png":
        return ".png"
    if normalized == "image/webp":
        return ".webp"
    return ".png"


def _safe_mime(upload: UploadFile) -> str:
    return str(upload.content_type or "").strip().lower()


def _safe_rate_limit_info(remaining: int, limit: int, window_seconds: int) -> Dict[str, Any]:
    return {
        "remainingInWindow": max(0, int(remaining)),
        "limitPerWindow": max(1, int(limit)),
        "windowSeconds": max(1, int(window_seconds)),
    }


def _prepare_wonderpark_image_bytes(image_bytes: bytes, *, max_dimension: int) -> bytes:
    if not image_bytes:
        raise ValueError("Image payload is empty.")
    with Image.open(BytesIO(image_bytes)) as img:
        image = img.convert("RGB")
        max_dim = max(256, int(max_dimension))
        if max(image.width, image.height) > max_dim:
            ratio = float(max_dim) / float(max(image.width, image.height))
            new_size = (
                max(1, int(round(image.width * ratio))),
                max(1, int(round(image.height * ratio))),
            )
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()


def _compute_wonderpark_quality_signals(image_bytes: bytes) -> Dict[str, Any]:
    with Image.open(BytesIO(image_bytes)) as img:
        rgb = img.convert("RGB")
        gray = rgb.convert("L")
        width, height = rgb.size
        mean_luma = float(ImageStat.Stat(gray).mean[0]) if gray.size else 0.0
        std_luma = float(ImageStat.Stat(gray).stddev[0]) if gray.size else 0.0
    very_dark = mean_luma < 40.0
    near_blank = std_luma < 7.0 and (mean_luma > 235.0 or mean_luma < 20.0)
    low_resolution = width < WONDERPARK_MIN_RECOMMENDED_WIDTH or height < WONDERPARK_MIN_RECOMMENDED_HEIGHT
    return {
        "imageWidth": int(width),
        "imageHeight": int(height),
        "meanLuma": round(mean_luma, 3),
        "stdLuma": round(std_luma, 3),
        "veryDark": bool(very_dark),
        "nearBlank": bool(near_blank),
        "lowResolution": bool(low_resolution),
    }


def _store_wonderpark_images(
    *,
    submission_id: str,
    original_bytes: bytes,
    original_mime: str,
    processed_bytes: bytes,
) -> Dict[str, Any]:
    ext = _guess_ext_from_mime(original_mime)
    original_path = WONDERPARK_ORIGINALS_DIR / f"{submission_id}{ext}"
    processed_path = WONDERPARK_PROCESSED_DIR / f"{submission_id}.png"
    thumbnail_path = WONDERPARK_THUMBNAILS_DIR / f"{submission_id}.png"

    original_path.write_bytes(original_bytes)
    processed_path.write_bytes(processed_bytes)

    with Image.open(BytesIO(processed_bytes)) as img:
        thumb = img.convert("RGB")
        thumb.thumbnail(
            (
                int(WONDERPARK_THUMBNAIL_MAX_DIMENSION),
                int(WONDERPARK_THUMBNAIL_MAX_DIMENSION),
            ),
            Image.Resampling.LANCZOS,
        )
        thumb.save(thumbnail_path, format="PNG", optimize=True)

    return {
        "originalPath": str(original_path),
        "processedPath": str(processed_path),
        "thumbnailPath": str(thumbnail_path),
        "originalUrl": f"/public/wonderpark/files/original/{original_path.name}",
        "processedUrl": f"/public/wonderpark/files/processed/{processed_path.name}",
        "thumbnailUrl": f"/public/wonderpark/files/thumbnail/{thumbnail_path.name}",
    }


def _remove_wonderpark_file(path_value: Any) -> None:
    candidate_text = str(path_value or "").strip()
    if not candidate_text:
        return
    candidate = Path(candidate_text)
    try:
        resolved = candidate.resolve()
    except OSError:
        return
    allowed_roots = (
        WONDERPARK_STORAGE_DIR.resolve(),
        INPUT_DIR.resolve(),
    )
    if not any(root == resolved or root in resolved.parents for root in allowed_roots):
        return
    if not resolved.is_file():
        return
    try:
        resolved.unlink()
    except OSError:
        logger.warning("Unable to delete Wonderpark file: %s", resolved)


def _wonderpark_to_api_payload(row: Dict[str, Any], request: Request, absolute: bool = False) -> Dict[str, Any]:
    payload = {
        "submission_id": str(row.get("submissionId") or ""),
        "customer_name": str(row.get("customerName") or ""),
        "uploaded_image_url": str(row.get("uploadedImageUrl") or ""),
        "thumbnail_url": str(row.get("thumbnailUrl") or ""),
        "original_image_url": str(row.get("originalImageUrl") or ""),
        "original_filename": str(row.get("originalFilename") or ""),
        "created_at": row.get("createdAt"),
        "updated_at": row.get("updatedAt"),
        "processing_status": str(row.get("processingStatus") or "pending"),
        "result_status": str(row.get("resultStatus") or "pending"),
        "showcase_visible": bool(row.get("showcaseVisible", False)),
        "paper_template_id": row.get("paperTemplateId"),
        "preset_animal": _normalize_preset_animal(row.get("presetAnimal"), allow_unknown=True),
        "preset_animal_source": str(row.get("presetAnimalSource") or ""),
        "queue_job_id": str(row.get("queueJobId") or ""),
        "latest_job_id": str(row.get("latestJobId") or ""),
        "generated_image_url": str(row.get("generatedImageUrl") or ""),
        "latest_output_url": str(row.get("latestOutputUrl") or ""),
        "error": str(row.get("error") or ""),
        "rate_limit_info": row.get("rateLimitInfo") if isinstance(row.get("rateLimitInfo"), dict) else {},
        "image_width": int(row.get("imageWidth") or 0),
        "image_height": int(row.get("imageHeight") or 0),
        "file_size_bytes": int(row.get("fileSizeBytes") or 0),
        "retry_count": int(row.get("retryCount") or 0),
        "generation_attempt": int(row.get("generationAttempt") or 0),
        "approved_at": row.get("approvedAt"),
        "approved_by": str(row.get("approvedBy") or ""),
        "approved_job_id": str(row.get("approvedJobId") or ""),
        "approved_image_url": str(row.get("approvedImageUrl") or ""),
    }
    if absolute:
        url_payload = _with_absolute_image_urls(
            request,
            {
                "inputUrl": payload["uploaded_image_url"],
                "outputUrl": payload["generated_image_url"],
                "beforeImageUrl": payload["thumbnail_url"],
            },
            absolute=True,
        )
        payload["uploaded_image_url"] = str(url_payload.get("inputUrl") or "")
        payload["generated_image_url"] = str(url_payload.get("outputUrl") or "")
        payload["thumbnail_url"] = str(url_payload.get("beforeImageUrl") or "")
        if payload["latest_output_url"]:
            payload["latest_output_url"] = str(_to_public_image_url(request, payload["latest_output_url"], True))
        if payload["approved_image_url"]:
            payload["approved_image_url"] = str(_to_public_image_url(request, payload["approved_image_url"], True))
    return payload


async def _enqueue_wonderpark_submission(submission_id: str) -> Dict[str, Any]:
    submission = await run_in_threadpool(wonderpark_store.get_submission, submission_id)
    if not submission:
        raise KeyError(submission_id)

    customer_name = _sanitize_wonderpark_customer_name(submission.get("customerName"))
    processing_path = Path(str(submission.get("processingInputPath") or ""))
    if not processing_path.is_file():
        raise RuntimeError("Processing image is missing for this submission.")

    queue_job_id = f"{submission_id}-{secrets.token_hex(4)}"
    target_input_path, _ = _job_paths(queue_job_id)
    if processing_path.resolve() != target_input_path.resolve():
        target_input_path.write_bytes(processing_path.read_bytes())

    estimate_payload = await run_in_threadpool(
        gallery_store.get_duration_estimate,
        DEFAULT_GENERATION_ESTIMATE_SECONDS,
    )
    submission_preset_animal = _normalize_preset_animal(
        submission.get("presetAnimal"),
        allow_unknown=True,
    )
    if not submission_preset_animal:
        submission_preset_animal = DRAWING_TO_ARTWORK_PRESET_ANIMAL_UNKNOWN
    if submission_preset_animal == DRAWING_TO_ARTWORK_PRESET_ANIMAL_UNKNOWN:
        logger.warning(
            "Wonderpark submission %s missing known presetAnimal; using unknown.",
            submission_id,
        )
    queued_job = _build_queue_job(
        job_id=queue_job_id,
        visitor_name=customer_name,
        input_path=target_input_path,
        source="public_wonderpark",
        estimate_payload=estimate_payload,
        generation_mode=GENERATION_MODE_DRAWING_TO_ARTWORK,
        style_id=WONDERPARK_DEFAULT_STYLE_ID,
        preset_override=_build_animal_drawing_from_holding_workflow_preset(),
        extra_fields={
            "submissionId": submission_id,
            "presetAnimal": submission_preset_animal,
            "generationEngine": "comfyui",
            "stylePreset": "random",
            "style_preset": "random",
        },
    )
    queued_settings = (
        dict(queued_job.get("generationSettings"))
        if isinstance(queued_job.get("generationSettings"), dict)
        else {}
    )
    queued_settings.setdefault("style_preset", "random")
    queued_settings.setdefault("stylePreset", "random")
    queued_job["generationSettings"] = queued_settings
    queued_job["stylePreset"] = "random"
    queued_job["style_preset"] = "random"
    await _enqueue_job(queued_job)
    return await run_in_threadpool(
        wonderpark_store.update_submission,
        submission_id,
        {
            "processingStatus": "queued",
            "queueJobId": queue_job_id,
            "latestJobId": queue_job_id,
            "error": "",
        },
    )


async def _update_wonderpark_submission_from_job(
    job: Dict[str, Any],
    *,
    status: str,
    generated_image_url: str = "",
    error: str = "",
) -> None:
    if _normalize_source(job.get("source")) != "public_wonderpark":
        return
    submission_id = str(job.get("submissionId") or "").strip()
    if not submission_id:
        return
    updates: Dict[str, Any] = {"processingStatus": status}
    if generated_image_url:
        updates["generatedImageUrl"] = generated_image_url
        updates["latestOutputUrl"] = generated_image_url
    if str(job.get("jobId") or "").strip():
        updates["latestJobId"] = str(job.get("jobId") or "").strip()
    if status == "completed":
        updates["resultStatus"] = "approved"
        updates["showcaseVisible"] = True
        updates["approvedAt"] = datetime.now(timezone.utc).isoformat()
        updates["approvedBy"] = "system_auto"
        updates["approvedJobId"] = str(job.get("jobId") or "").strip()
        updates["approvedImageUrl"] = generated_image_url or str(job.get("outputUrl") or "")
    elif status == "failed":
        updates["resultStatus"] = "failed"
        updates["showcaseVisible"] = False
    else:
        updates["resultStatus"] = "pending"
    if error:
        updates["error"] = error
    try:
        await run_in_threadpool(wonderpark_store.update_submission, submission_id, updates)
    except KeyError:
        logger.warning("Wonderpark submission missing while syncing job status: %s", submission_id)


def _build_generation_settings(preset: PresetSettings) -> Dict[str, Any]:
    generation_engine = _resolve_generation_engine_name()
    return {
        "generationEngine": generation_engine,
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
        "resizeMode": GENERATION_DEFAULTS.resize_mode,
        "pixelPerfect": GENERATION_DEFAULTS.pixel_perfect,
        "guidanceStart": GENERATION_DEFAULTS.guidance_start,
        "guidanceEnd": GENERATION_DEFAULTS.guidance_end,
    }


def _build_comfyui_passthrough_preset() -> PresetSettings:
    return PresetSettings(
        name="comfyui_workflow",
        control_weight=0.0,
        denoising_strength=0.0,
        control_mode="Balanced",
        cfg_scale=float(GENERATION_DEFAULTS.cfg_scale),
        steps=int(GENERATION_DEFAULTS.steps),
        sampler_name=str(GENERATION_DEFAULTS.sampler_name),
        prompt="",
        negative_prompt="",
        prompt_mode="comfyui_workflow",
    )


def _build_animal_coloring_page_preset() -> PresetSettings:
    return PresetSettings(
        name=ANIMAL_COLORING_PAGE_PRESET_NAME,
        control_weight=ANIMAL_COLORING_PAGE_CONTROL_WEIGHT,
        denoising_strength=ANIMAL_COLORING_PAGE_DENOISING_STRENGTH,
        control_mode=ANIMAL_COLORING_PAGE_CONTROL_MODE,
        cfg_scale=ANIMAL_COLORING_PAGE_CFG_SCALE,
        steps=ANIMAL_COLORING_PAGE_STEPS,
        sampler_name=ANIMAL_COLORING_PAGE_SAMPLER_NAME,
        prompt=DRAWING_TO_ARTWORK_SPECIES_BASE_PROMPT,
        negative_prompt=DRAWING_TO_ARTWORK_SPECIES_NEGATIVE_PROMPT,
        prompt_mode=ANIMAL_COLORING_PAGE_PRESET_NAME,
    )


def _build_animal_drawing_from_holding_workflow_preset() -> PresetSettings:
    return PresetSettings(
        name=ANIMAL_DRAWING_FROM_HOLDING_WORKFLOW_PRESET_NAME,
        control_weight=ANIMAL_DRAWING_FROM_HOLDING_CONTROL_WEIGHT,
        denoising_strength=ANIMAL_DRAWING_FROM_HOLDING_DENOISING_STRENGTH,
        control_mode=ANIMAL_DRAWING_FROM_HOLDING_CONTROL_MODE,
        cfg_scale=ANIMAL_DRAWING_FROM_HOLDING_CFG_SCALE,
        steps=ANIMAL_DRAWING_FROM_HOLDING_STEPS,
        sampler_name=ANIMAL_DRAWING_FROM_HOLDING_SAMPLER_NAME,
        prompt=ANIMAL_DRAWING_FROM_HOLDING_PROMPT,
        negative_prompt=ANIMAL_DRAWING_FROM_HOLDING_NEGATIVE_PROMPT,
        prompt_mode=ANIMAL_DRAWING_FROM_HOLDING_WORKFLOW_PRESET_NAME,
    )


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

    def _as_bool(value: Any, fallback: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
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
    settings["checkpoint"] = str(settings.get("checkpoint") or SD_CONFIG.checkpoint)
    settings["controlNetModel"] = str(settings.get("controlNetModel") or SD_CONFIG.controlnet_model)
    settings["controlNetModule"] = str(settings.get("controlNetModule") or SD_CONFIG.controlnet_module)
    settings["resizeMode"] = str(settings.get("resizeMode") or GENERATION_DEFAULTS.resize_mode)
    settings["pixelPerfect"] = _as_bool(
        settings.get("pixelPerfect"),
        bool(GENERATION_DEFAULTS.pixel_perfect),
    )
    settings["guidanceStart"] = _as_float(
        settings.get("guidanceStart"),
        float(GENERATION_DEFAULTS.guidance_start),
    )
    settings["guidanceEnd"] = _as_float(
        settings.get("guidanceEnd"),
        float(GENERATION_DEFAULTS.guidance_end),
    )
    return settings


def _enforce_drawing_to_artwork_generation_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(settings or {})
    preset_name = str(normalized.get("presetName") or normalized.get("preset") or "").strip().lower()
    use_animal_coloring_profile = preset_name == ANIMAL_COLORING_PAGE_PRESET_NAME
    use_animal_holding_profile = _is_animal_drawing_from_holding_workflow_preset(preset_name)
    if use_animal_coloring_profile:
        normalized["checkpoint"] = ANIMAL_COLORING_PAGE_CHECKPOINT
        normalized["controlNetModel"] = ANIMAL_COLORING_PAGE_CONTROLNET_MODEL
        normalized["controlNetModule"] = ANIMAL_COLORING_PAGE_CONTROLNET_MODULE
        normalized["controlWeight"] = ANIMAL_COLORING_PAGE_CONTROL_WEIGHT
        normalized["denoisingStrength"] = ANIMAL_COLORING_PAGE_DENOISING_STRENGTH
        normalized["controlMode"] = ANIMAL_COLORING_PAGE_CONTROL_MODE
        normalized["cfgScale"] = ANIMAL_COLORING_PAGE_CFG_SCALE
        normalized["steps"] = ANIMAL_COLORING_PAGE_STEPS
        normalized["samplerName"] = ANIMAL_COLORING_PAGE_SAMPLER_NAME
        normalized["width"] = ANIMAL_COLORING_PAGE_WIDTH
        normalized["height"] = ANIMAL_COLORING_PAGE_HEIGHT
    elif use_animal_holding_profile:
        normalized["checkpoint"] = ANIMAL_DRAWING_FROM_HOLDING_CHECKPOINT
        normalized["controlNetModel"] = ANIMAL_DRAWING_FROM_HOLDING_CONTROLNET_MODEL
        normalized["controlNetModule"] = ANIMAL_DRAWING_FROM_HOLDING_CONTROLNET_MODULE
        normalized["controlWeight"] = ANIMAL_DRAWING_FROM_HOLDING_CONTROL_WEIGHT
        normalized["denoisingStrength"] = ANIMAL_DRAWING_FROM_HOLDING_DENOISING_STRENGTH
        normalized["controlMode"] = ANIMAL_DRAWING_FROM_HOLDING_CONTROL_MODE
        normalized["cfgScale"] = ANIMAL_DRAWING_FROM_HOLDING_CFG_SCALE
        normalized["steps"] = ANIMAL_DRAWING_FROM_HOLDING_STEPS
        normalized["samplerName"] = ANIMAL_DRAWING_FROM_HOLDING_SAMPLER_NAME
        normalized["width"] = ANIMAL_DRAWING_FROM_HOLDING_WIDTH
        normalized["height"] = ANIMAL_DRAWING_FROM_HOLDING_HEIGHT
    else:
        normalized["checkpoint"] = DRAWING_TO_ARTWORK_CHECKPOINT
        normalized["controlNetModel"] = DRAWING_TO_ARTWORK_CONTROLNET_MODEL
        normalized["controlNetModule"] = DRAWING_TO_ARTWORK_CONTROLNET_MODULE
        normalized["controlWeight"] = DRAWING_TO_ARTWORK_CONTROL_WEIGHT
        normalized["denoisingStrength"] = DRAWING_TO_ARTWORK_DENOISING_STRENGTH
        normalized["controlMode"] = DRAWING_TO_ARTWORK_CONTROL_MODE
        normalized["cfgScale"] = DRAWING_TO_ARTWORK_CFG_SCALE
        normalized["steps"] = DRAWING_TO_ARTWORK_STEPS
        normalized["samplerName"] = DRAWING_TO_ARTWORK_SAMPLER_NAME
        normalized["width"] = DRAWING_TO_ARTWORK_WIDTH
        normalized["height"] = DRAWING_TO_ARTWORK_HEIGHT
    return normalized


def _build_detection_payload(detection: DetectionResult) -> Dict[str, float]:
    return {
        "colorRatio": float(detection.metrics.colorRatio),
        "edgeRatio": float(detection.metrics.edgeRatio),
        "whiteBackgroundRatio": float(detection.metrics.whiteBackgroundRatio),
        "roughness": float(detection.metrics.roughness),
    }


def _enforce_ai_art_venture_generation_limits(
    settings: Dict[str, Any],
    *,
    experimental_mode: bool = False,
) -> Dict[str, Any]:
    normalized = dict(settings)
    try:
        control_weight = float(normalized.get("controlWeight", AI_ART_VENTURE_CONTROL_WEIGHT_MIN))
    except (TypeError, ValueError):
        control_weight = AI_ART_VENTURE_CONTROL_WEIGHT_MIN
    control_weight = max(AI_ART_VENTURE_CONTROL_WEIGHT_MIN, min(AI_ART_VENTURE_CONTROL_WEIGHT_MAX, control_weight))

    use_ip_adapter_raw = normalized.get("useIpAdapter", AI_ART_VENTURE_USE_IP_ADAPTER)
    if isinstance(use_ip_adapter_raw, str):
        use_ip_adapter = use_ip_adapter_raw.strip().lower() in {"1", "true", "yes", "on"}
    else:
        use_ip_adapter = bool(use_ip_adapter_raw)
    denoise_max = AI_ART_VENTURE_DENOISE_MAX if use_ip_adapter else AI_ART_VENTURE_DENOISE_MAX_NO_IP
    try:
        denoising = float(normalized.get("denoisingStrength", AI_ART_VENTURE_DENOISE_MAX))
    except (TypeError, ValueError):
        denoising = AI_ART_VENTURE_DENOISE_MAX
    denoising = max(AI_ART_VENTURE_DENOISE_MIN, min(denoise_max, denoising))

    try:
        cfg_scale = float(normalized.get("cfgScale", AI_ART_VENTURE_CFG_MIN))
    except (TypeError, ValueError):
        cfg_scale = AI_ART_VENTURE_CFG_MIN
    cfg_scale = max(AI_ART_VENTURE_CFG_MIN, min(AI_ART_VENTURE_CFG_MAX, cfg_scale))
    try:
        ip_weight_raw = float(normalized.get("ipAdapterWeight", AI_ART_VENTURE_IP_ADAPTER_WEIGHT))
    except (TypeError, ValueError):
        ip_weight_raw = AI_ART_VENTURE_IP_ADAPTER_WEIGHT
    ip_weight = max(
        AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MIN,
        min(
            AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MAX,
            ip_weight_raw,
        ),
    )

    control_mode = str(normalized.get("controlMode") or "Balanced").strip() or "Balanced"
    if control_mode.lower() not in {"balanced", "my prompt is more important", "controlnet is more important"}:
        control_mode = "Balanced"

    controlnet_model = str(normalized.get("controlNetModel") or AI_ART_VENTURE_CONTROLNET_PREFERRED_MODEL).strip()
    controlnet_module = str(normalized.get("controlNetModule") or AI_ART_VENTURE_CONTROLNET_PREFERRED_MODULE).strip()
    if "scribble" in controlnet_model.lower() or "scribble" in controlnet_module.lower():
        logger.warning(
            "AI Art Venture blocked Scribble ControlNet request (%s / %s). Forcing %s (%s).",
            controlnet_model or "-",
            controlnet_module or "-",
            AI_ART_VENTURE_CONTROLNET_PREFERRED_MODEL,
            AI_ART_VENTURE_CONTROLNET_PREFERRED_MODULE,
        )
        controlnet_model = AI_ART_VENTURE_CONTROLNET_PREFERRED_MODEL
        controlnet_module = AI_ART_VENTURE_CONTROLNET_PREFERRED_MODULE
    if "softedge" in controlnet_model.lower():
        controlnet_module = AI_ART_VENTURE_CONTROLNET_PREFERRED_MODULE
    elif "canny" in controlnet_model.lower():
        controlnet_module = AI_ART_VENTURE_CONTROLNET_FALLBACK_MODULE

    normalized["controlWeight"] = round(control_weight, 4)
    normalized["softEdgeWeight"] = round(control_weight, 4)
    normalized["denoisingStrength"] = round(denoising, 4)
    normalized["cfgScale"] = round(cfg_scale, 4)
    normalized["controlMode"] = control_mode
    normalized["controlNetModel"] = controlnet_model
    normalized["controlNetModule"] = controlnet_module
    normalized["identitySafetyMode"] = bool(normalized.get("identitySafetyMode", True))
    normalized["useIpAdapter"] = bool(normalized.get("useIpAdapter", AI_ART_VENTURE_USE_IP_ADAPTER))
    normalized["ipAdapterWeight"] = round(ip_weight, 4)
    normalized["ipAdapterWarning"] = str(normalized.get("ipAdapterWarning") or "")
    normalized["identityTarget"] = str(normalized.get("identityTarget") or AI_ART_VENTURE_IDENTITY_TARGET)
    normalized["experimentalMode"] = bool(experimental_mode)
    return normalized


def _apply_ai_art_venture_plain_background_forcing(
    preset: PresetSettings,
    settings: Dict[str, Any],
    *,
    background_type: str,
) -> tuple[PresetSettings, Dict[str, Any]]:
    if str(background_type or "").strip().lower() != "plain":
        return preset, settings

    forced_prompt = _append_prompt_sentence(
        str(preset.prompt),
        "Replace the plain or white background with a rich immersive environment matching the selected style. "
        "Do not preserve the empty white background. Keep the person and creation recognizable while redesigning "
        "the surrounding environment.",
    )
    forced_negative = _append_prompt_sentence(
        str(preset.negative_prompt),
        "plain white background, empty background, studio white wall, blank backdrop, no background",
    )
    adjusted_preset = PresetSettings(
        name=preset.name,
        control_weight=preset.control_weight,
        denoising_strength=preset.denoising_strength,
        control_mode=preset.control_mode,
        cfg_scale=preset.cfg_scale,
        steps=preset.steps,
        sampler_name=preset.sampler_name,
        prompt=forced_prompt,
        negative_prompt=forced_negative,
        prompt_mode=preset.prompt_mode,
    )

    adjusted_settings = dict(settings or {})
    adjusted_settings["prompt"] = adjusted_preset.prompt
    adjusted_settings["negativePrompt"] = adjusted_preset.negative_prompt
    adjusted_settings["promptUsed"] = adjusted_preset.prompt
    adjusted_settings["negativePromptUsed"] = adjusted_preset.negative_prompt
    adjusted_settings["finalPrompt"] = adjusted_preset.prompt
    adjusted_settings["backgroundType"] = "plain"
    return adjusted_preset, adjusted_settings


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
        "generationEngine": item_generation_settings.get("generationEngine")
        or _resolve_generation_engine_name(),
        "backendPromptId": item_generation_settings.get("backendPromptId"),
        "backendMetadata": item_generation_settings.get("backendMetadata")
        if isinstance(item_generation_settings.get("backendMetadata"), dict)
        else {},
        "prompt": preset.prompt,
        "negativePrompt": preset.negative_prompt,
        "stylePreset": item_generation_settings.get("stylePreset")
        or item_generation_settings.get("style_preset")
        or "random",
        "style_preset": item_generation_settings.get("style_preset")
        or item_generation_settings.get("stylePreset")
        or "random",
        "stylePresetId": item_generation_settings.get("stylePresetId")
        or item_generation_settings.get("style_preset_id"),
        "stylePresetName": item_generation_settings.get("stylePresetName")
        or item_generation_settings.get("style_preset_name"),
        "styleCategory": item_generation_settings.get("styleCategory")
        or item_generation_settings.get("style_category"),
        "hidden": False,
        "hiddenAt": None,
        "updatedAt": None,
        "rating": None,
        "staffRating": None,
        "autoRating": 0,
        "autoReview": _default_auto_review_payload(),
        "feedbackTags": [],
        "feedbackNote": "",
        "comparisonScores": {},
        "ratedAt": None,
        "generationMode": DEFAULT_GENERATION_MODE,
        "styleId": DEFAULT_STYLE_ID,
        "styleLabel": _resolve_style_label(DEFAULT_GENERATION_MODE, DEFAULT_STYLE_ID),
        "styleRiskLevel": item_generation_settings.get("styleRiskLevel"),
        "checkpoint": item_generation_settings.get("checkpoint"),
        "controlNetModel": item_generation_settings.get("controlNetModel"),
        "controlNetModule": item_generation_settings.get("controlNetModule"),
        "denoisingStrength": item_generation_settings.get("denoisingStrength"),
        "controlWeight": item_generation_settings.get("controlWeight"),
        "controlMode": item_generation_settings.get("controlMode"),
        "cfgScale": item_generation_settings.get("cfgScale"),
        "steps": item_generation_settings.get("steps"),
        "samplerName": item_generation_settings.get("samplerName"),
        "backgroundType": item_generation_settings.get("backgroundType"),
        "whiteBackgroundRatio": item_generation_settings.get("whiteBackgroundRatio"),
        "presetAnimal": item_generation_settings.get("presetAnimal"),
        "speciesPromptUsed": item_generation_settings.get("speciesPromptUsed"),
        "finalDenoisingStrength": item_generation_settings.get("finalDenoisingStrength"),
        "finalControlWeight": item_generation_settings.get("finalControlWeight"),
        "finalPrompt": item_generation_settings.get("finalPrompt"),
        "promptUsed": item_generation_settings.get("promptUsed") or preset.prompt,
        "negativePromptUsed": item_generation_settings.get("negativePromptUsed") or preset.negative_prompt,
        "identitySafetyMode": item_generation_settings.get("identitySafetyMode"),
        "experimentalMode": item_generation_settings.get("experimentalMode"),
        "ipAdapterEnabled": item_generation_settings.get("ipAdapterEnabled"),
        "ipAdapterType": item_generation_settings.get("ipAdapterType"),
        "ipAdapterWeight": item_generation_settings.get("ipAdapterWeight"),
        "identityGuidanceUsed": item_generation_settings.get("identityGuidanceUsed"),
        "identityTarget": item_generation_settings.get("identityTarget"),
        "basedOnPreset": item_generation_settings.get("basedOnPreset"),
        "loraUsed": item_generation_settings.get("loraUsed"),
        "loraName": item_generation_settings.get("loraName"),
    }
    if extra_fields:
        item.update(extra_fields)
    item["source"] = _normalize_source(item.get("source"))
    item["generationMode"], item["styleId"] = _resolve_mode_and_style_ids(
        item.get("generationMode"),
        item.get("styleId"),
    )
    if not item.get("styleLabel"):
        item["styleLabel"] = _resolve_style_label(
            str(item.get("generationMode") or DEFAULT_GENERATION_MODE),
            str(item.get("styleId") or DEFAULT_STYLE_ID),
        )
    if (
        item.get("generationMode") == GENERATION_MODE_AI_ART_VENTURE
        and not item.get("styleRiskLevel")
    ):
        item["styleRiskLevel"] = _resolve_ai_art_style_metadata(str(item.get("styleId") or "")).get(
            "styleRiskLevel",
            "balanced",
        )
    item["checkpoint"] = item_generation_settings.get("checkpoint")
    item["controlNetModel"] = item_generation_settings.get("controlNetModel")
    item["controlNetModule"] = item_generation_settings.get("controlNetModule")
    item["denoisingStrength"] = item_generation_settings.get("denoisingStrength")
    item["controlWeight"] = item_generation_settings.get("controlWeight")
    item["controlMode"] = item_generation_settings.get("controlMode")
    item["cfgScale"] = item_generation_settings.get("cfgScale")
    item["steps"] = item_generation_settings.get("steps")
    item["backgroundType"] = item.get("backgroundType") or item_generation_settings.get("backgroundType")
    item["whiteBackgroundRatio"] = (
        item.get("whiteBackgroundRatio")
        if item.get("whiteBackgroundRatio") is not None
        else item_generation_settings.get("whiteBackgroundRatio")
    )
    item["presetAnimal"] = _normalize_preset_animal(
        item.get("presetAnimal") or item_generation_settings.get("presetAnimal")
    )
    item["speciesPromptUsed"] = (
        item.get("speciesPromptUsed") or item_generation_settings.get("speciesPromptUsed")
    )
    item["finalDenoisingStrength"] = (
        item.get("finalDenoisingStrength")
        if item.get("finalDenoisingStrength") is not None
        else item_generation_settings.get("finalDenoisingStrength")
    )
    item["finalControlWeight"] = (
        item.get("finalControlWeight")
        if item.get("finalControlWeight") is not None
        else item_generation_settings.get("finalControlWeight")
    )
    item["finalPrompt"] = item.get("finalPrompt") or item_generation_settings.get("finalPrompt")
    item["promptUsed"] = item.get("promptUsed") or item_generation_settings.get("promptUsed") or item.get("prompt")
    item["negativePromptUsed"] = (
        item.get("negativePromptUsed")
        or item_generation_settings.get("negativePromptUsed")
        or item.get("negativePrompt")
    )
    item["generationEngine"] = (
        item.get("generationEngine")
        or item_generation_settings.get("generationEngine")
        or _resolve_generation_engine_name()
    )
    item["backendPromptId"] = item.get("backendPromptId") or item_generation_settings.get("backendPromptId")
    if not isinstance(item.get("backendMetadata"), dict):
        item["backendMetadata"] = (
            item_generation_settings.get("backendMetadata")
            if isinstance(item_generation_settings.get("backendMetadata"), dict)
            else {}
        )
    if item.get("identitySafetyMode") is None:
        item["identitySafetyMode"] = item_generation_settings.get("identitySafetyMode")
    if item.get("experimentalMode") is None:
        item["experimentalMode"] = item_generation_settings.get("experimentalMode")
    _sync_generation_metadata_fields(item, item_generation_settings)
    return item


def _build_generation_complete_event(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "generation_complete",
        "jobId": item["jobId"],
        "visitorName": item["visitorName"],
        "source": _normalize_source(item.get("source")),
        "generationMode": item.get("generationMode"),
        "styleId": item.get("styleId"),
        "styleLabel": item.get("styleLabel"),
        "styleRiskLevel": item.get("styleRiskLevel"),
        "mode": item.get("mode"),
        "aiArtVentureEnabled": item.get("aiArtVentureEnabled"),
        "randomStyleEnabled": item.get("randomStyleEnabled"),
        "randomThemeEnabled": item.get("randomThemeEnabled"),
        "selectedStyleId": item.get("selectedStyleId"),
        "selectedThemeId": item.get("selectedThemeId"),
        "customTheme": item.get("customTheme"),
        "finalStyleId": item.get("finalStyleId"),
        "finalStyleName": item.get("finalStyleName"),
        "finalThemeId": item.get("finalThemeId"),
        "finalThemeName": item.get("finalThemeName"),
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
        "generationEngine": item.get("generationEngine"),
        "backendPromptId": item.get("backendPromptId"),
        "backendMetadata": item.get("backendMetadata")
        if isinstance(item.get("backendMetadata"), dict)
        else {},
        "checkpoint": item.get("checkpoint"),
        "controlNetModel": item.get("controlNetModel"),
        "controlNetModule": item.get("controlNetModule"),
        "denoisingStrength": item.get("denoisingStrength"),
        "controlWeight": item.get("controlWeight"),
        "softEdgeWeight": item.get("softEdgeWeight"),
        "controlMode": item.get("controlMode"),
        "cfgScale": item.get("cfgScale"),
        "steps": item.get("steps"),
        "samplerName": item.get("samplerName"),
        "backgroundType": item.get("backgroundType"),
        "whiteBackgroundRatio": item.get("whiteBackgroundRatio"),
        "presetAnimal": item.get("presetAnimal"),
        "speciesPromptUsed": item.get("speciesPromptUsed"),
        "finalDenoisingStrength": item.get("finalDenoisingStrength"),
        "finalControlWeight": item.get("finalControlWeight"),
        "finalPrompt": item.get("finalPrompt"),
        "promptUsed": item.get("promptUsed"),
        "negativePromptUsed": item.get("negativePromptUsed"),
        "stylePreset": (
            item.get("stylePreset")
            or item.get("style_preset")
            or (item.get("generationSettings") or {}).get("stylePreset")
            or (item.get("generationSettings") or {}).get("style_preset")
            or "random"
        ),
        "style_preset": (
            item.get("style_preset")
            or item.get("stylePreset")
            or (item.get("generationSettings") or {}).get("style_preset")
            or (item.get("generationSettings") or {}).get("stylePreset")
            or "random"
        ),
        "stylePresetId": (
            item.get("stylePresetId")
            or (item.get("generationSettings") or {}).get("stylePresetId")
            or (item.get("generationSettings") or {}).get("style_preset_id")
            or (item.get("backendMetadata") or {}).get("style_preset_id")
        ),
        "stylePresetName": (
            item.get("stylePresetName")
            or (item.get("generationSettings") or {}).get("stylePresetName")
            or (item.get("generationSettings") or {}).get("style_preset_name")
            or (item.get("backendMetadata") or {}).get("style_preset_name")
        ),
        "styleCategory": (
            item.get("styleCategory")
            or (item.get("generationSettings") or {}).get("styleCategory")
            or (item.get("generationSettings") or {}).get("style_category")
            or (item.get("backendMetadata") or {}).get("style_category")
        ),
        "identitySafetyMode": item.get("identitySafetyMode"),
        "experimentalMode": item.get("experimentalMode"),
        "ipAdapterEnabled": item.get("ipAdapterEnabled"),
        "ipAdapterType": item.get("ipAdapterType"),
        "ipAdapterWarning": item.get("ipAdapterWarning"),
        "ipAdapterWeight": item.get("ipAdapterWeight"),
        "identityGuidanceUsed": item.get("identityGuidanceUsed"),
        "identityTarget": item.get("identityTarget"),
        "basedOnPreset": item.get("basedOnPreset"),
        "loraUsed": item.get("loraUsed"),
        "loraName": item.get("loraName"),
        "hidden": bool(item.get("hidden", False)),
        "hiddenAt": item.get("hiddenAt"),
        "showcaseVisible": bool(item.get("showcaseVisible", False)),
        "showcaseStatus": item.get("showcaseStatus"),
        "updatedAt": item.get("updatedAt"),
        "rating": _get_staff_rating(item),
        "staffRating": _get_staff_rating(item),
        "autoRating": item.get("autoRating"),
        "autoReview": _normalize_auto_review_payload(item.get("autoReview")),
        "feedbackTags": item.get("feedbackTags", []),
        "feedbackNote": item.get("feedbackNote", ""),
        "comparisonScores": item.get("comparisonScores", {}),
        "ratedAt": item.get("ratedAt"),
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
    output_path_override: Optional[str] = None,
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
    extra_fields = dict(extra_item_fields or {})
    generation_mode, style_id = _resolve_mode_and_style_ids(
        extra_fields.get("generationMode"),
        extra_fields.get("styleId"),
    )
    extra_fields["generationMode"] = generation_mode
    extra_fields["styleId"] = style_id
    if not extra_fields.get("styleLabel"):
        extra_fields["styleLabel"] = _resolve_style_label(generation_mode, style_id)
    requested_generation_engine = _normalize_generation_engine(
        (
            generation_settings_override.get("generationEngine")
            if isinstance(generation_settings_override, dict)
            else None
        )
        or extra_fields.get("generationEngine")
        or _resolve_generation_engine_name()
    )
    extra_fields["generationEngine"] = requested_generation_engine

    detection: Optional[DetectionResult] = None
    if requested_generation_engine == "comfyui":
        if preset_override is None:
            preset = _build_comfyui_passthrough_preset()
        else:
            preset = preset_override
        detection_payload = detection_payload_override or {}
    elif generation_mode == GENERATION_MODE_AI_ART_VENTURE:
        ai_background: Dict[str, Any] = {}
        try:
            ai_background = await run_in_threadpool(analyze_ai_art_venture_background, input_path)
        except Exception as exc:
            logger.warning(
                "AI Art Venture background analysis failed for %s: %s",
                input_path,
                exc,
            )

        preset, ai_mode_settings, ai_mode_meta = build_ai_art_venture_preset(
            style_id,
            background_analysis=ai_background,
        )
        if (
            str(extra_fields.get("source") or "").strip().lower() == "regenerate"
            and preset_override is not None
        ):
            regenerate_prompt = str(preset_override.prompt or "").strip()
            regenerate_negative = str(preset_override.negative_prompt or "").strip()
            if regenerate_prompt:
                preset = PresetSettings(
                    name=preset.name,
                    control_weight=preset.control_weight,
                    denoising_strength=preset.denoising_strength,
                    control_mode=preset.control_mode,
                    cfg_scale=preset.cfg_scale,
                    steps=preset.steps,
                    sampler_name=preset.sampler_name,
                    prompt=regenerate_prompt,
                    negative_prompt=regenerate_negative or preset.negative_prompt,
                    prompt_mode=preset.prompt_mode,
                )
        preset, ai_mode_settings = _apply_ai_art_venture_plain_background_forcing(
            preset,
            ai_mode_settings,
            background_type=str(ai_mode_meta.get("backgroundType") or ""),
        )

        detection_payload = detection_payload_override or {}
        if ai_mode_meta.get("whiteBackgroundRatio") is not None:
            detection_payload["whiteBackgroundRatio"] = ai_mode_meta.get("whiteBackgroundRatio")
        if ai_background.get("edgeRatio") is not None:
            detection_payload["edgeRatio"] = ai_background.get("edgeRatio")
        if ai_background.get("plainBackgroundRatio") is not None:
            detection_payload["plainBackgroundRatio"] = ai_background.get("plainBackgroundRatio")
        if ai_background.get("studioLike") is not None:
            detection_payload["studioLike"] = ai_background.get("studioLike")
        if ai_background.get("borderGrayStd") is not None:
            detection_payload["borderGrayStd"] = ai_background.get("borderGrayStd")
        if ai_background.get("borderSatStd") is not None:
            detection_payload["borderSatStd"] = ai_background.get("borderSatStd")
        if ai_background.get("uniformBorder") is not None:
            detection_payload["uniformBorder"] = ai_background.get("uniformBorder")

        merged_ai_settings = dict(ai_mode_settings)
        if isinstance(generation_settings_override, dict):
            for key, value in generation_settings_override.items():
                if value is not None:
                    merged_ai_settings[key] = value
        experimental_mode = bool(merged_ai_settings.get("experimentalMode", False))
        merged_ai_settings = _enforce_ai_art_venture_generation_limits(
            merged_ai_settings,
            experimental_mode=experimental_mode,
        )
        merged_ai_settings["styleRiskLevel"] = str(
            ai_mode_meta.get("styleRiskLevel")
            or merged_ai_settings.get("styleRiskLevel")
            or "balanced"
        )
        merged_ai_settings["backgroundType"] = ai_mode_meta.get("backgroundType") or "non_plain"
        merged_ai_settings["whiteBackgroundRatio"] = ai_mode_meta.get("whiteBackgroundRatio")
        merged_ai_settings["finalDenoisingStrength"] = merged_ai_settings.get("denoisingStrength")
        merged_ai_settings["finalControlWeight"] = merged_ai_settings.get("controlWeight")
        merged_ai_settings["finalPrompt"] = preset.prompt
        merged_ai_settings["prompt"] = preset.prompt
        merged_ai_settings["negativePrompt"] = preset.negative_prompt
        merged_ai_settings["promptUsed"] = preset.prompt
        merged_ai_settings["negativePromptUsed"] = preset.negative_prompt
        merged_ai_settings["identitySafetyMode"] = True
        merged_ai_settings["experimentalMode"] = experimental_mode
        generation_settings_override = merged_ai_settings

        extra_fields["styleId"] = str(ai_mode_meta.get("styleId") or style_id)
        extra_fields["styleLabel"] = str(ai_mode_meta.get("styleLabel") or extra_fields.get("styleLabel") or "")
        extra_fields["styleRiskLevel"] = str(
            ai_mode_meta.get("styleRiskLevel")
            or merged_ai_settings.get("styleRiskLevel")
            or "balanced"
        )
        extra_fields["backgroundType"] = ai_mode_meta.get("backgroundType")
        extra_fields["whiteBackgroundRatio"] = ai_mode_meta.get("whiteBackgroundRatio")
        extra_fields["finalDenoisingStrength"] = generation_settings_override.get("denoisingStrength")
        extra_fields["finalControlWeight"] = generation_settings_override.get("controlWeight")
        extra_fields["finalPrompt"] = preset.prompt
        extra_fields["promptUsed"] = preset.prompt
        extra_fields["negativePromptUsed"] = preset.negative_prompt
        extra_fields["identitySafetyMode"] = True
        extra_fields["experimentalMode"] = bool(generation_settings_override.get("experimentalMode", False))
        extra_fields["samplerName"] = generation_settings_override.get("samplerName")
        extra_fields["ipAdapterEnabled"] = generation_settings_override.get("ipAdapterEnabled")
        extra_fields["ipAdapterType"] = generation_settings_override.get("ipAdapterType")
        extra_fields["ipAdapterWeight"] = generation_settings_override.get("ipAdapterWeight")
        extra_fields["identityGuidanceUsed"] = generation_settings_override.get("identityGuidanceUsed")
        extra_fields["identityTarget"] = (
            generation_settings_override.get("identityTarget") or AI_ART_VENTURE_IDENTITY_TARGET
        )
        style_id = str(extra_fields.get("styleId") or style_id)
    elif preset_override is None:
        detection = await run_in_threadpool(analyze_image, input_path)
        preset = detection.preset
        detection_payload = _build_detection_payload(detection)
    else:
        preset = preset_override
        detection_payload = detection_payload_override or {}

    use_animal_holding_preset = (
        requested_generation_engine != "comfyui"
        and generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK
        and _is_animal_drawing_from_holding_workflow_preset(preset.name)
    )
    if requested_generation_engine == "comfyui":
        routed_prompt = str(preset.prompt or "")
    else:
        routed_prompt = (
            str(preset.prompt)
            if use_animal_holding_preset
            else _apply_mode_style_prompt(preset.prompt, generation_mode, style_id)
        )
    routed_negative_prompt = str(preset.negative_prompt)
    if requested_generation_engine != "comfyui" and generation_mode == GENERATION_MODE_AI_ART_VENTURE:
        routed_prompt = _append_prompt_sentence(
            routed_prompt,
            "Replace the original background with a detailed immersive style-matching environment; do not keep plain white wall, blank backdrop, or studio background",
        )
    if requested_generation_engine != "comfyui" and generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK:
        preset_animal = _normalize_preset_animal(
            extra_fields.get("presetAnimal")
            or (
                generation_settings_override.get("presetAnimal")
                if isinstance(generation_settings_override, dict)
                else None
            )
        )
        species_preservation_stronger = _has_species_preservation_problem_tags(extra_fields.get("problemTags"))
        white_background_ratio = 0.0
        if isinstance(detection_payload, dict):
            white_background_ratio = _safe_float(detection_payload.get("whiteBackgroundRatio"))
        species_prompt_used = ""
        if not use_animal_holding_preset:
            routed_prompt, routed_negative_prompt, species_prompt_used = _build_drawing_species_prompt_bundle(
                prompt=routed_prompt,
                negative_prompt=routed_negative_prompt,
                preset_animal=preset_animal,
                white_background_ratio=white_background_ratio,
                strong_species=species_preservation_stronger,
            )
        if preset_animal:
            extra_fields["presetAnimal"] = preset_animal
        if species_prompt_used:
            extra_fields["speciesPromptUsed"] = species_prompt_used

    preset = PresetSettings(
        name=preset.name,
        control_weight=preset.control_weight,
        denoising_strength=preset.denoising_strength,
        control_mode=preset.control_mode,
        cfg_scale=preset.cfg_scale,
        steps=preset.steps,
        sampler_name=preset.sampler_name,
        prompt=routed_prompt,
        negative_prompt=routed_negative_prompt,
        prompt_mode=preset.prompt_mode,
    )

    prompt_mode = preset.prompt_mode
    resolved_generation_settings = _merge_generation_settings(preset, generation_settings_override)
    resolved_generation_settings["generationMode"] = generation_mode
    resolved_generation_settings["styleId"] = style_id
    generation_engine = requested_generation_engine
    resolved_generation_settings["generationEngine"] = generation_engine
    output_path = (
        Path(str(output_path_override))
        if str(output_path_override or "").strip()
        else _resolve_output_path_for_engine(job_id, generation_engine)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    extra_fields["generationEngine"] = generation_engine
    if generation_engine != "comfyui" and generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK:
        drawing_override_settings: Dict[str, Any] = {}
        if isinstance(generation_settings_override, dict):
            for key in (
                "controlWeight",
                "denoisingStrength",
                "controlMode",
                "cfgScale",
            ):
                if generation_settings_override.get(key) is not None:
                    drawing_override_settings[key] = generation_settings_override.get(key)
        resolved_generation_settings = _enforce_drawing_to_artwork_generation_settings(
            resolved_generation_settings
        )
        if drawing_override_settings:
            resolved_generation_settings.update(drawing_override_settings)
        resolved_generation_settings["promptUsed"] = preset.prompt
        resolved_generation_settings["negativePromptUsed"] = preset.negative_prompt
        if extra_fields.get("presetAnimal"):
            resolved_generation_settings["presetAnimal"] = _normalize_preset_animal(
                extra_fields.get("presetAnimal")
            )
        if extra_fields.get("speciesPromptUsed"):
            resolved_generation_settings["speciesPromptUsed"] = str(
                extra_fields.get("speciesPromptUsed") or ""
            )
        if use_animal_holding_preset:
            _apply_animal_drawing_holding_metadata(
                resolved_generation_settings,
                prompt_text=str(preset.prompt or ""),
            )
            extra_fields["basedOnPreset"] = resolved_generation_settings.get("basedOnPreset")
            extra_fields["loraUsed"] = resolved_generation_settings.get("loraUsed")
            extra_fields["loraName"] = resolved_generation_settings.get("loraName")
            extra_fields["identityGuidanceUsed"] = resolved_generation_settings.get("identityGuidanceUsed")
    if generation_engine != "comfyui" and generation_mode == GENERATION_MODE_AI_ART_VENTURE:
        resolved_generation_settings.setdefault("styleLabel", extra_fields.get("styleLabel"))
        resolved_generation_settings.setdefault("styleRiskLevel", extra_fields.get("styleRiskLevel"))
        resolved_generation_settings.setdefault("stylePrompt", "")
        resolved_generation_settings.setdefault("identityTarget", AI_ART_VENTURE_IDENTITY_TARGET)
        resolved_generation_settings.setdefault("useIpAdapter", AI_ART_VENTURE_USE_IP_ADAPTER)
        resolved_generation_settings.setdefault("softEdgeWeight", resolved_generation_settings.get("controlWeight"))
        resolved_generation_settings.setdefault("ipAdapterWeight", AI_ART_VENTURE_IP_ADAPTER_WEIGHT)
        resolved_generation_settings.setdefault("ipAdapterEnabled", False)
        resolved_generation_settings.setdefault("ipAdapterType", "none")
        resolved_generation_settings.setdefault("ipAdapterWarning", "")
        resolved_generation_settings.setdefault("identityGuidanceUsed", False)
        resolved_generation_settings = _enforce_ai_art_venture_generation_limits(
            resolved_generation_settings,
            experimental_mode=bool(resolved_generation_settings.get("experimentalMode", False)),
        )
        resolved_generation_settings["backgroundType"] = (
            extra_fields.get("backgroundType")
            or resolved_generation_settings.get("backgroundType")
            or "non_plain"
        )
        if extra_fields.get("whiteBackgroundRatio") is not None:
            resolved_generation_settings["whiteBackgroundRatio"] = extra_fields.get("whiteBackgroundRatio")
        resolved_generation_settings["finalDenoisingStrength"] = resolved_generation_settings.get("denoisingStrength")
        resolved_generation_settings["finalControlWeight"] = resolved_generation_settings.get("controlWeight")
        resolved_generation_settings["finalPrompt"] = preset.prompt
        resolved_generation_settings["prompt"] = preset.prompt
        resolved_generation_settings["negativePrompt"] = preset.negative_prompt
        resolved_generation_settings["promptUsed"] = preset.prompt
        resolved_generation_settings["negativePromptUsed"] = preset.negative_prompt
        resolved_generation_settings["identitySafetyMode"] = True
        resolved_generation_settings["experimentalMode"] = bool(
            resolved_generation_settings.get("experimentalMode", False)
        )
        _sync_generation_metadata_fields(extra_fields, resolved_generation_settings)
        extra_fields["finalDenoisingStrength"] = resolved_generation_settings.get("denoisingStrength")
        extra_fields["finalControlWeight"] = resolved_generation_settings.get("controlWeight")
        extra_fields["finalPrompt"] = preset.prompt
        extra_fields["promptUsed"] = preset.prompt
        extra_fields["negativePromptUsed"] = preset.negative_prompt
        extra_fields["identitySafetyMode"] = True
        extra_fields["experimentalMode"] = bool(
            resolved_generation_settings.get("experimentalMode", False)
        )

    logger.info(
        "Job %s started for visitor=%s preset=%s",
        job_id,
        visitor_name,
        preset.name,
    )
    logger.info("Detected preset: %s", preset.name)
    logger.info("Prompt mode: %s", prompt_mode)
    backend, _backend_runtime_config = await run_in_threadpool(
        _get_generation_backend_for_engine,
        generation_engine,
    )
    backend_result = await run_in_threadpool(
        backend.generate,
        input_path,
        preset.prompt,
        preset.negative_prompt,
        {
            "generation_settings": resolved_generation_settings,
            "preset": preset,
            "output_path": output_path,
        },
    )
    if not bool(backend_result.get("success")):
        raise RuntimeError(str(backend_result.get("error") or "Generation backend failed."))
    output_image_value = str(backend_result.get("output_image") or "").strip()
    if output_image_value:
        output_path = Path(output_image_value)
    if not output_path.is_file():
        raise RuntimeError(f"Generation finished but output image file is missing: {output_path}")
    try:
        if int(output_path.stat().st_size) <= 0:
            raise RuntimeError(f"Generation finished but output image file is empty: {output_path}")
    except OSError as exc:
        raise RuntimeError(f"Unable to verify generated output image file: {output_path}") from exc
    resolved_generation_settings["generationEngine"] = _normalize_generation_engine(
        backend_result.get("mode") or generation_engine
    )
    resolved_generation_settings["backendPromptId"] = backend_result.get("prompt_id")
    resolved_generation_settings["backendMetadata"] = (
        backend_result.get("metadata")
        if isinstance(backend_result.get("metadata"), dict)
        else {}
    )
    backend_metadata = (
        resolved_generation_settings.get("backendMetadata")
        if isinstance(resolved_generation_settings.get("backendMetadata"), dict)
        else {}
    )
    style_preset_id = str(backend_metadata.get("style_preset_id") or "").strip()
    style_preset_name = str(backend_metadata.get("style_preset_name") or "").strip()
    style_category = str(backend_metadata.get("style_category") or "").strip()
    prompt_used_from_backend = str(backend_metadata.get("prompt_used") or "").strip()
    style_preset_requested = str(backend_metadata.get("style_preset_requested") or "").strip()
    if style_preset_id:
        resolved_generation_settings["stylePresetId"] = style_preset_id
        extra_fields["stylePresetId"] = style_preset_id
    if style_preset_name:
        resolved_generation_settings["stylePresetName"] = style_preset_name
        extra_fields["stylePresetName"] = style_preset_name
    if style_category:
        resolved_generation_settings["styleCategory"] = style_category
        extra_fields["styleCategory"] = style_category
    if style_preset_requested:
        resolved_generation_settings["stylePreset"] = style_preset_requested
        resolved_generation_settings["style_preset"] = style_preset_requested
        extra_fields["stylePreset"] = style_preset_requested
        extra_fields["style_preset"] = style_preset_requested
    if prompt_used_from_backend:
        resolved_generation_settings["promptUsed"] = prompt_used_from_backend
        extra_fields["promptUsed"] = prompt_used_from_backend
    backend_prompt_text = str(backend_result.get("prompt") or "").strip()
    backend_negative_text = str(backend_result.get("negative_prompt") or "").strip()
    if backend_prompt_text or backend_negative_text:
        preset = PresetSettings(
            name=preset.name,
            control_weight=preset.control_weight,
            denoising_strength=preset.denoising_strength,
            control_mode=preset.control_mode,
            cfg_scale=preset.cfg_scale,
            steps=preset.steps,
            sampler_name=preset.sampler_name,
            prompt=backend_prompt_text or str(preset.prompt or ""),
            negative_prompt=backend_negative_text or str(preset.negative_prompt or ""),
            prompt_mode=preset.prompt_mode,
        )
        resolved_generation_settings["promptUsed"] = preset.prompt
        resolved_generation_settings["negativePromptUsed"] = preset.negative_prompt
    extra_fields["generationEngine"] = resolved_generation_settings.get("generationEngine")
    extra_fields["backendPromptId"] = resolved_generation_settings.get("backendPromptId")
    extra_fields["backendMetadata"] = resolved_generation_settings.get("backendMetadata")

    if generation_engine != "comfyui" and generation_mode == GENERATION_MODE_AI_ART_VENTURE:
        _sync_generation_metadata_fields(extra_fields, resolved_generation_settings)
        _overwrite_generation_metadata_fields(extra_fields, resolved_generation_settings)

    completed_at_dt = datetime.now(timezone.utc)
    completed_at = completed_at_dt.isoformat()
    duration_seconds = round((completed_at_dt - started_at_dt).total_seconds(), 3)
    created_at = created_at_override or completed_at
    input_url = f"/inputs/{input_path.name}"
    output_url = _to_output_url(output_path)

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
        extra_fields=extra_fields,
    )

    auto_review = await run_in_threadpool(
        review_generation_quality,
        input_path=input_path,
        output_path=output_path,
        generation_mode=generation_mode,
        preset=preset.name,
        style_id=style_id,
        generation_settings=resolved_generation_settings,
    )
    normalized_auto_review = _normalize_auto_review_payload(auto_review)
    item["autoReview"] = normalized_auto_review
    item["autoRating"] = int(normalized_auto_review.get("autoRating") or 0)
    item["staffRating"] = _get_staff_rating(item)
    item["rating"] = item["staffRating"]
    if item["staffRating"] is not None and 1 <= int(item["staffRating"]) <= 5:
        auto_bad_tags = [
            str(tag)
            for tag in normalized_auto_review.get("autoBadTags", [])
            if isinstance(tag, str) and str(tag).strip()
        ]
        auto_good_tags = [
            str(tag)
            for tag in normalized_auto_review.get("autoGoodTags", [])
            if isinstance(tag, str) and str(tag).strip()
        ]
        auto_feedback_tags = list(dict.fromkeys(auto_bad_tags + auto_good_tags))
        auto_notes = str(normalized_auto_review.get("autoNotes") or "").strip()
        item["feedbackTags"] = auto_feedback_tags
        item["feedbackNote"] = (
            f"AUTO REVIEW: {auto_notes}"
            if auto_notes
            else f"AUTO REVIEW: autoRating={item['staffRating']}/5"
        )
        item["ratedAt"] = completed_at
        item["updatedAt"] = completed_at

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
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = utc_now_iso()
    input_url = f"/inputs/{input_path.name}"
    configured_generation_engine = _resolve_generation_engine_name(
        (extra_fields or {}).get("generationEngine")
    )
    output_path = _resolve_output_path_for_engine(job_id, configured_generation_engine)
    output_url = _to_output_url(output_path)
    resolved_generation_mode, resolved_style_id = _resolve_mode_and_style_ids(
        generation_mode,
        style_id,
    )
    resolved_style_label = _resolve_style_label(resolved_generation_mode, resolved_style_id)

    preset_name = ""
    prompt_mode = ""
    prompt_text = ""
    negative_text = ""
    generation_settings: Optional[Dict[str, Any]] = None
    ai_background_analysis: Dict[str, Any] = {}
    if resolved_generation_mode == GENERATION_MODE_AI_ART_VENTURE and preset_override is None:
        try:
            ai_background_analysis = analyze_ai_art_venture_background(input_path)
        except Exception as exc:
            logger.warning(
                "AI Art Venture background analysis failed while queueing %s: %s",
                input_path,
                exc,
            )
            ai_background_analysis = {}
        ai_preset, ai_settings, ai_meta = build_ai_art_venture_preset(
            resolved_style_id,
            background_analysis=ai_background_analysis,
        )
        ai_preset, ai_settings = _apply_ai_art_venture_plain_background_forcing(
            ai_preset,
            ai_settings,
            background_type=str(ai_meta.get("backgroundType") or ""),
        )
        preset_override = ai_preset
        generation_settings = ai_settings
        _sync_generation_metadata_fields(extra_fields or {}, generation_settings)
        resolved_style_id = str(ai_meta.get("styleId") or resolved_style_id)
        resolved_style_label = str(ai_meta.get("styleLabel") or resolved_style_label)
        detection_payload = detection_payload or {}
        if ai_meta.get("whiteBackgroundRatio") is not None:
            detection_payload["whiteBackgroundRatio"] = ai_meta.get("whiteBackgroundRatio")
        if ai_meta.get("backgroundType") is not None:
            detection_payload["backgroundType"] = ai_meta.get("backgroundType")
        if ai_background_analysis.get("plainBackgroundRatio") is not None:
            detection_payload["plainBackgroundRatio"] = ai_background_analysis.get("plainBackgroundRatio")
        if ai_background_analysis.get("studioLike") is not None:
            detection_payload["studioLike"] = ai_background_analysis.get("studioLike")
        if ai_background_analysis.get("borderGrayStd") is not None:
            detection_payload["borderGrayStd"] = ai_background_analysis.get("borderGrayStd")
        if ai_background_analysis.get("borderSatStd") is not None:
            detection_payload["borderSatStd"] = ai_background_analysis.get("borderSatStd")
        if ai_background_analysis.get("uniformBorder") is not None:
            detection_payload["uniformBorder"] = ai_background_analysis.get("uniformBorder")

    normalized_preset_animal_for_route = _normalize_preset_animal(
        (extra_fields or {}).get("presetAnimal"),
        allow_unknown=True,
    )
    if (
        preset_override is None
        and resolved_generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK
        and normalized_preset_animal_for_route
    ):
        preset_override = _build_animal_drawing_from_holding_workflow_preset()

    if preset_override is not None:
        preset_name = preset_override.name
        prompt_mode = preset_override.prompt_mode
        prompt_text = preset_override.prompt
        negative_text = preset_override.negative_prompt
        if generation_settings is None:
            generation_settings = _build_generation_settings(preset_override)

        if resolved_generation_mode == GENERATION_MODE_AI_ART_VENTURE:
            if not ai_background_analysis:
                try:
                    ai_background_analysis = analyze_ai_art_venture_background(input_path)
                except Exception as exc:
                    logger.warning(
                        "AI Art Venture background analysis failed while queueing %s: %s",
                        input_path,
                        exc,
                    )
                    ai_background_analysis = {}
            _ai_preset, ai_settings, ai_meta = build_ai_art_venture_preset(
                resolved_style_id,
                background_analysis=ai_background_analysis,
            )
            _ai_preset, ai_settings = _apply_ai_art_venture_plain_background_forcing(
                _ai_preset,
                ai_settings,
                background_type=str(ai_meta.get("backgroundType") or ""),
            )
            merged_settings = dict(ai_settings)
            merged_settings.update(generation_settings)
            experimental_mode = bool(merged_settings.get("experimentalMode", False))
            merged_settings = _enforce_ai_art_venture_generation_limits(
                merged_settings,
                experimental_mode=experimental_mode,
            )
            merged_settings["backgroundType"] = (
                ai_meta.get("backgroundType") or merged_settings.get("backgroundType") or "non_plain"
            )
            merged_settings["whiteBackgroundRatio"] = ai_meta.get("whiteBackgroundRatio")
            merged_settings["finalDenoisingStrength"] = merged_settings.get("denoisingStrength")
            merged_settings["finalControlWeight"] = merged_settings.get("controlWeight")
            merged_settings["finalPrompt"] = preset_override.prompt
            merged_settings["promptUsed"] = preset_override.prompt
            merged_settings["negativePromptUsed"] = preset_override.negative_prompt
            merged_settings["identitySafetyMode"] = True
            merged_settings["experimentalMode"] = experimental_mode
            generation_settings = _merge_generation_settings(preset_override, merged_settings)
            _sync_generation_metadata_fields(extra_fields or {}, generation_settings)
            resolved_style_id = str(ai_meta.get("styleId") or resolved_style_id)
            resolved_style_label = str(ai_meta.get("styleLabel") or resolved_style_label)
            detection_payload = detection_payload or {}
            if ai_meta.get("whiteBackgroundRatio") is not None:
                detection_payload["whiteBackgroundRatio"] = ai_meta.get("whiteBackgroundRatio")
            if ai_meta.get("backgroundType") is not None:
                detection_payload["backgroundType"] = ai_meta.get("backgroundType")
            if ai_background_analysis.get("plainBackgroundRatio") is not None:
                detection_payload["plainBackgroundRatio"] = ai_background_analysis.get("plainBackgroundRatio")
            if ai_background_analysis.get("studioLike") is not None:
                detection_payload["studioLike"] = ai_background_analysis.get("studioLike")
            if ai_background_analysis.get("borderGrayStd") is not None:
                detection_payload["borderGrayStd"] = ai_background_analysis.get("borderGrayStd")
            if ai_background_analysis.get("borderSatStd") is not None:
                detection_payload["borderSatStd"] = ai_background_analysis.get("borderSatStd")
            if ai_background_analysis.get("uniformBorder") is not None:
                detection_payload["uniformBorder"] = ai_background_analysis.get("uniformBorder")
        else:
            generation_settings = _merge_generation_settings(preset_override, generation_settings)

    if (
        resolved_generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK
        and isinstance(generation_settings, dict)
    ):
        generation_settings = _enforce_drawing_to_artwork_generation_settings(generation_settings)
        generation_settings["promptUsed"] = generation_settings.get("promptUsed") or prompt_text
        generation_settings["negativePromptUsed"] = (
            generation_settings.get("negativePromptUsed") or negative_text
        )
        normalized_preset_animal = _normalize_preset_animal((extra_fields or {}).get("presetAnimal"))
        if normalized_preset_animal:
            generation_settings["presetAnimal"] = normalized_preset_animal
        if (extra_fields or {}).get("speciesPromptUsed"):
            generation_settings["speciesPromptUsed"] = str(
                (extra_fields or {}).get("speciesPromptUsed") or ""
            )
        if _is_animal_drawing_from_holding_workflow_preset(
            generation_settings.get("presetName") or preset_name
        ):
            _apply_animal_drawing_holding_metadata(
                generation_settings,
                prompt_text=str(prompt_text or ""),
            )

    if not isinstance(generation_settings, dict):
        generation_settings = {}
    generation_settings["generationEngine"] = configured_generation_engine
    style_preset_value = _normalize_comfy_style_preset(
        (extra_fields or {}).get("stylePreset")
        or (extra_fields or {}).get("style_preset")
        or generation_settings.get("stylePreset")
        or generation_settings.get("style_preset")
    )
    if configured_generation_engine == "comfyui":
        generation_settings["stylePreset"] = style_preset_value
        generation_settings["style_preset"] = style_preset_value
        # Honor ComfyUI default step count from config.json for queued Comfy jobs.
        comfy_defaults = _get_comfy_defaults()
        try:
            comfy_default_steps = int(comfy_defaults.get("steps") or 0)
        except (TypeError, ValueError):
            comfy_default_steps = 0
        if comfy_default_steps > 0:
            generation_settings["steps"] = comfy_default_steps

    job_payload = {
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
        "generationEngine": configured_generation_engine,
        "generationMode": resolved_generation_mode,
        "styleId": resolved_style_id,
        "styleLabel": resolved_style_label,
        "styleRiskLevel": (generation_settings or {}).get("styleRiskLevel"),
        "inputPath": str(input_path),
        "inputUrl": input_url,
        "outputPath": str(output_path),
        "outputUrl": output_url,
        "preset": preset_name,
        "promptMode": prompt_mode,
        "promptType": prompt_mode,
        "prompt": prompt_text,
        "negativePrompt": negative_text,
        "stylePreset": generation_settings.get("stylePreset")
        or generation_settings.get("style_preset")
        or "random",
        "style_preset": generation_settings.get("style_preset")
        or generation_settings.get("stylePreset")
        or "random",
        "generationSettings": generation_settings,
        "backendPromptId": (generation_settings or {}).get("backendPromptId"),
        "backendMetadata": (generation_settings or {}).get("backendMetadata")
        if isinstance((generation_settings or {}).get("backendMetadata"), dict)
        else {},
        "checkpoint": (generation_settings or {}).get("checkpoint"),
        "controlNetModel": (generation_settings or {}).get("controlNetModel"),
        "controlNetModule": (generation_settings or {}).get("controlNetModule"),
        "denoisingStrength": (generation_settings or {}).get("denoisingStrength"),
        "controlWeight": (generation_settings or {}).get("controlWeight"),
        "controlMode": (generation_settings or {}).get("controlMode"),
        "cfgScale": (generation_settings or {}).get("cfgScale"),
        "steps": (generation_settings or {}).get("steps"),
        "samplerName": (generation_settings or {}).get("samplerName"),
        "backgroundType": (generation_settings or {}).get("backgroundType"),
        "whiteBackgroundRatio": (generation_settings or {}).get("whiteBackgroundRatio"),
        "presetAnimal": _normalize_preset_animal((generation_settings or {}).get("presetAnimal")),
        "speciesPromptUsed": (generation_settings or {}).get("speciesPromptUsed"),
        "finalDenoisingStrength": (generation_settings or {}).get("finalDenoisingStrength"),
        "finalControlWeight": (generation_settings or {}).get("finalControlWeight"),
        "finalPrompt": (generation_settings or {}).get("finalPrompt"),
        "promptUsed": (generation_settings or {}).get("promptUsed") or prompt_text,
        "negativePromptUsed": (generation_settings or {}).get("negativePromptUsed") or negative_text,
        "identitySafetyMode": (generation_settings or {}).get("identitySafetyMode"),
        "experimentalMode": (generation_settings or {}).get("experimentalMode"),
        "ipAdapterEnabled": (generation_settings or {}).get("ipAdapterEnabled"),
        "ipAdapterType": (generation_settings or {}).get("ipAdapterType"),
        "ipAdapterWeight": (generation_settings or {}).get("ipAdapterWeight"),
        "identityGuidanceUsed": (generation_settings or {}).get("identityGuidanceUsed"),
        "identityTarget": (generation_settings or {}).get("identityTarget"),
        "detection": detection_payload or {},
        "originalJobId": original_job_id or job_id,
        "regenerationOf": regeneration_of,
        "version": version,
        "problemTags": list(problem_tags or []),
    }
    if isinstance(extra_fields, dict) and extra_fields:
        job_payload.update(extra_fields)
    if resolved_generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK:
        job_payload["presetAnimal"] = _normalize_preset_animal(
            job_payload.get("presetAnimal") or (generation_settings or {}).get("presetAnimal")
        )
        if job_payload.get("speciesPromptUsed") is None:
            job_payload["speciesPromptUsed"] = (generation_settings or {}).get("speciesPromptUsed")
    if (
        resolved_generation_mode == GENERATION_MODE_AI_ART_VENTURE
        and not job_payload.get("styleRiskLevel")
    ):
        job_payload["styleRiskLevel"] = _resolve_ai_art_style_metadata(resolved_style_id).get(
            "styleRiskLevel",
            "balanced",
        )
    _sync_generation_metadata_fields(job_payload, generation_settings if isinstance(generation_settings, dict) else None)
    return job_payload


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
    active_jobs = [
        job
        for job in snapshot.get("jobs", [])
        if isinstance(job, dict) and str(job.get("status") or "") in {"queued", "processing"}
    ]
    return {
        "queueLength": queue_length,
        "currentJob": (current_job or {}).get("jobId") if current_job else None,
        "estimatedWaitSeconds": int(estimated_wait),
        "jobs": [_job_to_public_payload(job) for job in active_jobs],
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


def _default_auto_review_payload() -> Dict[str, Any]:
    payload = dict(default_auto_review())
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    payload["metrics"] = {
        "similarityScore": round(max(0.0, min(1.0, _safe_float(metrics.get("similarityScore")))), 4),
        "whiteBackgroundRatio": round(max(0.0, min(1.0, _safe_float(metrics.get("whiteBackgroundRatio")))), 4),
        "colorRatio": round(max(0.0, min(1.0, _safe_float(metrics.get("colorRatio")))), 4),
        "edgeRatio": round(max(0.0, min(1.0, _safe_float(metrics.get("edgeRatio")))), 4),
        "colorGain": round(max(-1.0, min(1.0, _safe_float(metrics.get("colorGain")))), 4),
    }
    return payload


def _normalize_comparison_scores(value: Any) -> Dict[str, int]:
    if not isinstance(value, dict):
        return {}
    cleaned: Dict[str, int] = {}
    for key in COMPARISON_SCORE_KEYS:
        numeric = _safe_int(value.get(key))
        if numeric is None:
            continue
        if 1 <= numeric <= 5:
            cleaned[key] = int(numeric)
    return cleaned


def _normalize_auto_review_payload(value: Any) -> Dict[str, Any]:
    base = _default_auto_review_payload()
    if not isinstance(value, dict):
        return base

    auto_rating = _safe_int(value.get("autoRating"))
    if auto_rating is not None and 1 <= auto_rating <= 5:
        base["autoRating"] = auto_rating
    else:
        base["autoRating"] = 0

    bad_tags = [str(tag) for tag in value.get("autoBadTags", []) if isinstance(tag, str)]
    good_tags = [str(tag) for tag in value.get("autoGoodTags", []) if isinstance(tag, str)]
    base["autoBadTags"] = list(dict.fromkeys(bad_tags))
    base["autoGoodTags"] = list(dict.fromkeys(good_tags))
    base["autoNotes"] = str(value.get("autoNotes") or "").strip()
    base["confidence"] = round(max(0.0, min(1.0, _safe_float(value.get("confidence")))), 3)
    metrics = value.get("metrics")
    metric_payload = _default_auto_review_payload().get("metrics", {})
    if isinstance(metrics, dict):
        metric_payload["similarityScore"] = round(
            max(0.0, min(1.0, _safe_float(metrics.get("similarityScore")))),
            4,
        )
        metric_payload["whiteBackgroundRatio"] = round(
            max(0.0, min(1.0, _safe_float(metrics.get("whiteBackgroundRatio")))),
            4,
        )
        metric_payload["colorRatio"] = round(
            max(0.0, min(1.0, _safe_float(metrics.get("colorRatio")))),
            4,
        )
        metric_payload["edgeRatio"] = round(
            max(0.0, min(1.0, _safe_float(metrics.get("edgeRatio")))),
            4,
        )
        metric_payload["colorGain"] = round(
            max(-1.0, min(1.0, _safe_float(metrics.get("colorGain")))),
            4,
        )
    base["metrics"] = metric_payload
    return base


def _get_staff_rating(item: Dict[str, Any]) -> Optional[int]:
    auto_rating = _get_auto_rating(item)
    if auto_rating is not None and 1 <= auto_rating <= 5:
        return auto_rating
    staff_rating = _safe_int(item.get("staffRating"))
    if staff_rating is not None and 1 <= staff_rating <= 5:
        return staff_rating
    legacy_rating = _safe_int(item.get("rating"))
    if legacy_rating is not None and 1 <= legacy_rating <= 5:
        return legacy_rating
    return None


def _get_auto_rating(item: Dict[str, Any]) -> Optional[int]:
    auto_review = _normalize_auto_review_payload(item.get("autoReview"))
    auto_rating = _safe_int(auto_review.get("autoRating"))
    if auto_rating is not None and 1 <= auto_rating <= 5:
        return auto_rating
    fallback = _safe_int(item.get("autoRating"))
    if fallback is not None and 1 <= fallback <= 5:
        return fallback
    return None


def _is_many(tag_count: int, rated_count: int) -> bool:
    if rated_count <= 0:
        return False
    return tag_count >= 2 or (tag_count / rated_count) >= 0.35


def _generate_recommendations(tag_counter: Counter, rated_count: int, context_label: str) -> List[str]:
    recommendations: List[str] = []
    prefix = f"{context_label}: "

    wrong_subject_count = sum(tag_counter.get(tag, 0) for tag in WRONG_SUBJECT_TAGS)
    if wrong_subject_count > 0:
        recommendations.append(
            f"{prefix}Detected wrong_subject/wrong_generation. Check generationMode routing, prompt routing, and "
            "confirm the correct preset/styleId is selected."
        )

    if tag_counter["same_as_input"] > 0 or tag_counter["too_close_to_drawing"] > 0:
        recommendations.append(
            f"{prefix}Detected same_as_input. Increase denoisingStrength by 0.08 and lower controlWeight by 0.05."
        )

    person_identity_score = (
        tag_counter["person_missing"] + tag_counter["person_changed"] + tag_counter["face_changed"]
    )
    if person_identity_score > 0:
        recommendations.append(
            f"{prefix}Detected person identity drift. Increase controlWeight by 0.05-0.1, lower denoisingStrength "
            "by 0.05, use 'person_holding_artwork' mode, and strengthen 'preserve exact person, face, pose, clothing'."
        )
    if tag_counter["face_identity_changed"] > 0 or tag_counter["person_unrecognizable"] > 0:
        recommendations.append(
            f"{prefix}Many identity failures detected. Reduce denoisingStrength by ~0.05, raise controlWeight by "
            "~0.08, and increase IP-Adapter weight by +0.05 (max 0.75) when available."
        )

    main_object_missing_score = (
        tag_counter["main_object_missing"]
        + tag_counter["artwork_missing"]
        + tag_counter["object_missing"]
        + tag_counter["artwork_changed"]
        + tag_counter["object_changed"]
    )
    if main_object_missing_score > 0:
        recommendations.append(
            f"{prefix}Detected main object missing/changed. Increase controlWeight by 0.05-0.1 and lower "
            "denoisingStrength by 0.05 while reinforcing main object preservation."
        )

    if tag_counter["object_missing"] > 0 or tag_counter["object_changed"] > 0:
        recommendations.append(
            f"{prefix}Detected object drift. Increase controlWeight by 0.08 and lower denoisingStrength by 0.05."
        )

    if tag_counter["not_lively_enough"] > 0 or tag_counter["too_empty"] > 0:
        recommendations.append(
            f"{prefix}Detected dull/empty scenes. Increase denoisingStrength by 0.05-0.1, increase cfgScale by "
            "0.5, and add full background / lively environment prompt guidance."
        )

    if (
        tag_counter["background_wrong"] > 0
        or tag_counter["background_not_changed"] > 0
        or tag_counter["background_too_plain"] > 0
    ):
        recommendations.append(
            f"{prefix}Detected weak background transformation. Strengthen background replacement prompt wording and "
            "keep identity settings stable while redesigning only the environment."
        )

    if tag_counter["same_as_input"] > 0 or tag_counter["style_too_weak"] > 0:
        recommendations.append(
            f"{prefix}Detected weak stylization. Increase denoisingStrength slightly (about +0.04) while keeping "
            "identity and creation constraints."
        )

    if tag_counter["artwork_changed"] > 0 or tag_counter["creation_unrecognizable"] > 0:
        recommendations.append(
            f"{prefix}Detected artwork drift. Lower denoisingStrength slightly and raise controlWeight to better "
            "preserve creation shape/content/position."
        )

    if (
        tag_counter["changed_too_much"] > 0
        or tag_counter["over_changed"] > 0
        or tag_counter["too_much_change"] > 0
    ):
        recommendations.append(
            f"{prefix}Detected over-change. Increase controlWeight by 0.05-0.1 and lower denoisingStrength by 0.05-0.1."
        )

    if tag_counter["bad_face"] > 0 or tag_counter["bad_hands"] > 0:
        recommendations.append(
            f"{prefix}Detected face/hand artifacts. Use stronger negative prompt terms and lower denoisingStrength slightly."
        )

    if tag_counter["style_wrong"] > 0:
        recommendations.append(
            f"{prefix}Detected style mismatch. Check selected styleId and style prompt routing."
        )

    wrong_composition_count = sum(tag_counter.get(tag, 0) for tag in WRONG_COMPOSITION_TAGS)
    if wrong_composition_count > 0:
        recommendations.append(
            f"{prefix}Detected wrong composition. Increase controlWeight by 0.05 and reduce denoisingStrength by 0.05 "
            "to preserve composition and object placement."
        )

    if tag_counter["too_messy"] > 0:
        recommendations.append(
            f"{prefix}Detected messy outputs. Increase controlWeight by 0.05 and lower denoisingStrength by 0.05."
        )

    if tag_counter["bad_colors"] > 0 or tag_counter["too_dark"] > 0:
        recommendations.append(
            f"{prefix}Detected color/lighting issues. Increase cfgScale by 0.5 and reinforce bright, warm palette prompting."
        )

    if tag_counter["blurry"] > 0 or tag_counter["low_quality"] > 0:
        recommendations.append(
            f"{prefix}Detected low quality/detail. Increase steps to 35-40 and add stronger quality prompt emphasis."
        )

    return recommendations


def _build_tuning_summary(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_images = len(items)
    staff_rated_items = [item for item in items if _get_staff_rating(item) is not None]
    staff_rated_count = len(staff_rated_items)
    average_staff_rating = (
        round(
            sum(_get_staff_rating(item) or 0 for item in staff_rated_items) / staff_rated_count,
            3,
        )
        if staff_rated_count > 0
        else 0
    )

    auto_rated_items = [item for item in items if _get_auto_rating(item) is not None]
    auto_rated_count = len(auto_rated_items)
    average_auto_rating = (
        round(sum(_get_auto_rating(item) or 0 for item in auto_rated_items) / auto_rated_count, 3)
        if auto_rated_count > 0
        else 0
    )

    by_preset: Dict[str, Dict[str, Any]] = {}
    low_rated_items: List[Dict[str, Any]] = []
    mismatch_examples: List[Dict[str, Any]] = []
    mismatch_total_delta = 0.0
    by_preset_animal: Dict[str, Dict[str, Any]] = {}
    missing_preset_animal_job_ids: List[str] = []

    global_bad_counter: Counter = Counter()
    global_good_counter: Counter = Counter()
    global_auto_bad_counter: Counter = Counter()
    global_auto_good_counter: Counter = Counter()
    bad_by_preset_counter: Dict[str, Counter] = {}
    good_by_preset_counter: Dict[str, Counter] = {}
    bad_by_generation_mode_counter: Dict[str, Counter] = {
        GENERATION_MODE_DRAWING_TO_ARTWORK: Counter(),
        GENERATION_MODE_AI_ART_VENTURE: Counter(),
        GENERATION_MODE_PERSON_HOLDING_ARTWORK: Counter(),
    }
    generation_mode_count_counter: Counter = Counter()
    bad_by_style_id_counter: Dict[str, Counter] = {}
    bad_by_style_risk_counter: Dict[str, Counter] = {}
    bad_by_controlnet_counter: Dict[str, Counter] = {}
    bad_by_ip_adapter_counter: Dict[str, Counter] = {}
    identity_failure_counter: Counter = Counter()
    background_failure_counter: Counter = Counter()
    artwork_failure_counter: Counter = Counter()
    bad_by_preset_animal_counter: Dict[str, Counter] = {}
    similarity_score_sum = 0.0
    similarity_score_count = 0
    white_background_ratio_sum = 0.0
    white_background_ratio_count = 0
    ai_art_venture_style_stats: Dict[str, Dict[str, Any]] = {}
    ai_art_venture_mode_config = get_ai_art_venture_mode_payload_for_ui()
    ai_art_venture_mode_styles = (
        ai_art_venture_mode_config.get("styles")
        if isinstance(ai_art_venture_mode_config.get("styles"), list)
        else []
    )
    for style_row in ai_art_venture_mode_styles:
        if not isinstance(style_row, dict):
            continue
        style_key = str(style_row.get("id") or "").strip().lower()
        if not style_key:
            continue
        risk_level = str(style_row.get("styleRiskLevel") or "balanced").strip().lower()
        if risk_level not in {"safe", "balanced", "experimental"}:
            risk_level = "balanced"
        ai_art_venture_style_stats[style_key] = {
            "styleId": style_key,
            "styleLabel": str(style_row.get("label") or style_key),
            "styleRiskLevel": risk_level,
            "generatedCount": 0,
            "ratedCount": 0,
            "averageRating": 0.0,
            "commonBadTags": [],
            "commonGoodTags": [],
            "averageSoftEdgeWeight": 0.0,
            "averageIpAdapterWeight": 0.0,
            "averageDenoisingStrength": 0.0,
            "ipAdapterEnabledCount": 0,
            "_ratingSum": 0.0,
            "_softEdgeSum": 0.0,
            "_softEdgeCount": 0,
            "_ipWeightSum": 0.0,
            "_ipWeightCount": 0,
            "_denoiseSum": 0.0,
            "_denoiseCount": 0,
            "_badCounter": Counter(),
            "_goodCounter": Counter(),
        }

    def _new_preset_stats() -> Dict[str, Any]:
        return {
            "count": 0,
            "ratedCount": 0,
            "autoRatedCount": 0,
            "averageRating": 0,
            "averageStaffRating": 0,
            "averageAutoRating": 0,
            "averageControlWeight": 0,
            "averageDenoisingStrength": 0,
            "commonBadTags": [],
            "commonGoodTags": [],
            "commonAutoBadTags": [],
            "commonAutoGoodTags": [],
            "badTagCounts": {},
            "goodTagCounts": {},
            "autoBadTagCounts": {},
            "autoGoodTagCounts": {},
            "basedOnPreset": "",
            "basedOnPresetCounts": {},
            "samplePromptUsed": "",
            "sampleNegativePromptUsed": "",
            "_ratingSum": 0.0,
            "_autoRatingSum": 0.0,
            "_controlWeightSum": 0.0,
            "_denoiseSum": 0.0,
            "_badCounter": Counter(),
            "_goodCounter": Counter(),
            "_autoBadCounter": Counter(),
            "_autoGoodCounter": Counter(),
            "_basedOnPresetCounter": Counter(),
            "_promptUsedCounter": Counter(),
            "_negativePromptUsedCounter": Counter(),
        }

    def _new_preset_animal_stats() -> Dict[str, Any]:
        return {
            "count": 0,
            "ratedCount": 0,
            "averageRating": 0,
            "averageControlWeight": 0,
            "averageDenoisingStrength": 0,
            "commonBadTags": [],
            "badTagCounts": {},
            "_ratingSum": 0.0,
            "_controlWeightSum": 0.0,
            "_denoiseSum": 0.0,
            "_badCounter": Counter(),
        }

    for preset_name in KNOWN_PRESETS:
        by_preset[preset_name] = _new_preset_stats()
    for preset_animal in CUSTOMER_ANIMAL_ROUTE_VALUES:
        by_preset_animal[preset_animal] = _new_preset_animal_stats()

    for item in items:
        preset = str(item.get("preset") or "unknown")
        generation_mode, style_id = _resolve_mode_and_style_ids(
            item.get("generationMode"),
            item.get("styleId"),
        )
        generation_mode_count_counter[generation_mode] += 1
        stats = by_preset.setdefault(preset, {**_new_preset_stats()})
        bad_by_preset_counter.setdefault(preset, Counter())
        good_by_preset_counter.setdefault(preset, Counter())
        bad_by_generation_mode_counter.setdefault(generation_mode, Counter())
        bad_by_style_id_counter.setdefault(style_id, Counter())
        style_risk_level = str(item.get("styleRiskLevel") or "").strip().lower()
        if not style_risk_level and generation_mode == GENERATION_MODE_AI_ART_VENTURE:
            style_risk_level = _resolve_ai_art_style_metadata(style_id).get("styleRiskLevel", "balanced")
        if not style_risk_level:
            style_risk_level = "unknown"
        bad_by_style_risk_counter.setdefault(style_risk_level, Counter())
        settings_for_key = item.get("generationSettings") if isinstance(item.get("generationSettings"), dict) else {}
        control_model_key = str(
            item.get("controlNetModel")
            or settings_for_key.get("controlNetModel")
            or "-"
        ).strip()
        control_module_key = str(
            item.get("controlNetModule")
            or settings_for_key.get("controlNetModule")
            or "-"
        ).strip()
        controlnet_key = f"{control_module_key} | {control_model_key}"
        bad_by_controlnet_counter.setdefault(controlnet_key, Counter())
        ip_enabled_value = item.get("ipAdapterEnabled")
        if ip_enabled_value is None:
            ip_enabled_value = settings_for_key.get("ipAdapterEnabled")
        ip_adapter_key = "enabled" if bool(ip_enabled_value) else "disabled"
        bad_by_ip_adapter_counter.setdefault(ip_adapter_key, Counter())
        ai_style_stats = None
        if generation_mode == GENERATION_MODE_AI_ART_VENTURE:
            ai_style_stats = ai_art_venture_style_stats.get(style_id)
            if ai_style_stats is None:
                resolved_style_meta = _resolve_ai_art_style_metadata(style_id)
                ai_style_stats = {
                    "styleId": str(resolved_style_meta.get("styleId") or style_id),
                    "styleLabel": str(resolved_style_meta.get("styleLabel") or style_id or "Style"),
                    "styleRiskLevel": str(resolved_style_meta.get("styleRiskLevel") or "balanced"),
                    "generatedCount": 0,
                    "ratedCount": 0,
                    "averageRating": 0.0,
                    "commonBadTags": [],
                    "commonGoodTags": [],
                    "averageSoftEdgeWeight": 0.0,
                    "averageIpAdapterWeight": 0.0,
                    "averageDenoisingStrength": 0.0,
                    "ipAdapterEnabledCount": 0,
                    "_ratingSum": 0.0,
                    "_softEdgeSum": 0.0,
                    "_softEdgeCount": 0,
                    "_ipWeightSum": 0.0,
                    "_ipWeightCount": 0,
                    "_denoiseSum": 0.0,
                    "_denoiseCount": 0,
                    "_badCounter": Counter(),
                    "_goodCounter": Counter(),
                }
                ai_art_venture_style_stats[style_id] = ai_style_stats

            ai_style_stats["generatedCount"] += 1
            soft_edge_weight_value = _safe_float(
                settings_for_key.get("softEdgeWeight", settings_for_key.get("controlWeight"))
            )
            if soft_edge_weight_value > 0:
                ai_style_stats["_softEdgeSum"] += soft_edge_weight_value
                ai_style_stats["_softEdgeCount"] += 1

            ip_weight_value = _safe_float(settings_for_key.get("ipAdapterWeight"))
            if ip_weight_value > 0:
                ai_style_stats["_ipWeightSum"] += ip_weight_value
                ai_style_stats["_ipWeightCount"] += 1

            denoise_value = _safe_float(settings_for_key.get("denoisingStrength"))
            if denoise_value > 0:
                ai_style_stats["_denoiseSum"] += denoise_value
                ai_style_stats["_denoiseCount"] += 1

            if bool(ip_enabled_value):
                ai_style_stats["ipAdapterEnabledCount"] += 1

        stats["count"] += 1
        generation_settings = item.get("generationSettings") if isinstance(item.get("generationSettings"), dict) else {}
        based_on_preset_value = str(
            item.get("basedOnPreset") or generation_settings.get("basedOnPreset") or ""
        ).strip()
        if based_on_preset_value:
            stats["_basedOnPresetCounter"][based_on_preset_value] += 1
        prompt_used_value = str(
            item.get("promptUsed") or generation_settings.get("promptUsed") or item.get("prompt") or ""
        ).strip()
        if prompt_used_value:
            stats["_promptUsedCounter"][prompt_used_value] += 1
        negative_prompt_used_value = str(
            item.get("negativePromptUsed")
            or generation_settings.get("negativePromptUsed")
            or item.get("negativePrompt")
            or ""
        ).strip()
        if negative_prompt_used_value:
            stats["_negativePromptUsedCounter"][negative_prompt_used_value] += 1
        preset_name_for_item = str(
            item.get("preset") or generation_settings.get("presetName") or ""
        ).strip().lower()
        is_animal_coloring_page_job = (
            _normalize_source(item.get("source")) == "public_wonderpark"
            or preset_name_for_item in {
                ANIMAL_COLORING_PAGE_PRESET_NAME,
                ANIMAL_DRAWING_FROM_HOLDING_WORKFLOW_PRESET_NAME,
            }
        )
        preset_animal = _normalize_preset_animal(
            item.get("presetAnimal") or generation_settings.get("presetAnimal"),
            allow_unknown=True,
        )
        if is_animal_coloring_page_job and not preset_animal:
            missing_job_id = str(item.get("jobId") or "").strip()
            if missing_job_id:
                missing_preset_animal_job_ids.append(missing_job_id)
        if generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK:
            preset_animal_key = preset_animal or DRAWING_TO_ARTWORK_PRESET_ANIMAL_UNKNOWN
            animal_stats = by_preset_animal.setdefault(preset_animal_key, _new_preset_animal_stats())
            bad_by_preset_animal_counter.setdefault(preset_animal_key, Counter())
            animal_stats["count"] += 1
            animal_stats["_controlWeightSum"] += _safe_float(generation_settings.get("controlWeight"))
            animal_stats["_denoiseSum"] += _safe_float(generation_settings.get("denoisingStrength"))
        stats["_controlWeightSum"] += _safe_float(generation_settings.get("controlWeight"))
        stats["_denoiseSum"] += _safe_float(generation_settings.get("denoisingStrength"))

        auto_review = _normalize_auto_review_payload(item.get("autoReview"))
        auto_rating = _safe_int(auto_review.get("autoRating"))
        if auto_rating is not None and 1 <= auto_rating <= 5:
            stats["autoRatedCount"] += 1
            stats["_autoRatingSum"] += auto_rating

        auto_bad_tags = [str(tag) for tag in auto_review.get("autoBadTags", []) if isinstance(tag, str)]
        auto_good_tags = [str(tag) for tag in auto_review.get("autoGoodTags", []) if isinstance(tag, str)]
        auto_metrics = auto_review.get("metrics") if isinstance(auto_review.get("metrics"), dict) else {}
        similarity_score = _safe_float(auto_metrics.get("similarityScore"))
        white_ratio = _safe_float(auto_metrics.get("whiteBackgroundRatio"))
        if 0.0 <= similarity_score <= 1.0:
            similarity_score_sum += similarity_score
            similarity_score_count += 1
        if 0.0 <= white_ratio <= 1.0:
            white_background_ratio_sum += white_ratio
            white_background_ratio_count += 1
        for tag in auto_bad_tags:
            stats["_autoBadCounter"][tag] += 1
            global_auto_bad_counter[tag] += 1
        for tag in auto_good_tags:
            stats["_autoGoodCounter"][tag] += 1
            global_auto_good_counter[tag] += 1

        staff_rating = _get_staff_rating(item)
        if staff_rating is not None:
            stats["ratedCount"] += 1
            stats["_ratingSum"] += staff_rating
            if generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK:
                preset_animal_key = preset_animal or DRAWING_TO_ARTWORK_PRESET_ANIMAL_UNKNOWN
                animal_stats = by_preset_animal.setdefault(preset_animal_key, _new_preset_animal_stats())
                animal_stats["ratedCount"] += 1
                animal_stats["_ratingSum"] += staff_rating
            if ai_style_stats is not None:
                ai_style_stats["ratedCount"] += 1
                ai_style_stats["_ratingSum"] += staff_rating
            tags = [str(tag) for tag in item.get("feedbackTags", []) if isinstance(tag, str)]
            for tag in tags:
                if tag in BAD_FEEDBACK_TAGS:
                    stats["_badCounter"][tag] += 1
                    global_bad_counter[tag] += 1
                    bad_by_preset_counter[preset][tag] += 1
                    bad_by_generation_mode_counter[generation_mode][tag] += 1
                    bad_by_style_id_counter[style_id][tag] += 1
                    bad_by_style_risk_counter[style_risk_level][tag] += 1
                    bad_by_controlnet_counter[controlnet_key][tag] += 1
                    bad_by_ip_adapter_counter[ip_adapter_key][tag] += 1
                    if generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK:
                        preset_animal_key = preset_animal or DRAWING_TO_ARTWORK_PRESET_ANIMAL_UNKNOWN
                        bad_by_preset_animal_counter.setdefault(preset_animal_key, Counter())[tag] += 1
                        by_preset_animal.setdefault(
                            preset_animal_key,
                            _new_preset_animal_stats(),
                        )["_badCounter"][tag] += 1
                    if ai_style_stats is not None:
                        ai_style_stats["_badCounter"][tag] += 1
                    if tag in IDENTITY_CLOTHING_TAGS:
                        identity_failure_counter[tag] += 1
                    if tag in BACKGROUND_ISSUE_TAGS:
                        background_failure_counter[tag] += 1
                    if tag in ARTWORK_RELATED_FAILURE_TAGS:
                        artwork_failure_counter[tag] += 1
                if tag in GOOD_FEEDBACK_TAGS:
                    stats["_goodCounter"][tag] += 1
                    global_good_counter[tag] += 1
                    good_by_preset_counter[preset][tag] += 1
                    if ai_style_stats is not None:
                        ai_style_stats["_goodCounter"][tag] += 1

            if staff_rating <= 2:
                low_rated_items.append(
                    {
                        "jobId": item.get("jobId"),
                        "visitorName": item.get("visitorName"),
                        "preset": item.get("preset"),
                        "rating": staff_rating,
                        "staffRating": staff_rating,
                        "autoRating": auto_rating,
                        "autoReview": auto_review,
                        "generationMode": generation_mode,
                        "styleId": style_id,
                        "presetAnimal": preset_animal or DRAWING_TO_ARTWORK_PRESET_ANIMAL_UNKNOWN,
                        "feedbackTags": item.get("feedbackTags", []),
                        "feedbackNote": item.get("feedbackNote", ""),
                        "comparisonScores": _normalize_comparison_scores(item.get("comparisonScores")),
                        "inputUrl": item.get("inputUrl"),
                        "outputUrl": item.get("outputUrl"),
                        "detection": item.get("detection", {}),
                        "generationSettings": item.get("generationSettings", {}),
                        "prompt": item.get("prompt", ""),
                        "negativePrompt": item.get("negativePrompt", ""),
                        "promptUsed": item.get("promptUsed", ""),
                        "negativePromptUsed": item.get("negativePromptUsed", ""),
                    }
                )
        elif ai_style_stats is not None and auto_rating is not None and 1 <= auto_rating <= 5:
            ai_style_stats["ratedCount"] += 1
            ai_style_stats["_ratingSum"] += float(auto_rating)

        if (
            staff_rating is not None
            and auto_rating is not None
            and 1 <= auto_rating <= 5
            and 1 <= staff_rating <= 5
            and auto_rating != staff_rating
        ):
            delta = abs(staff_rating - auto_rating)
            mismatch_total_delta += float(delta)
            mismatch_examples.append(
                {
                    "jobId": item.get("jobId"),
                    "preset": preset,
                    "generationMode": generation_mode,
                    "styleId": style_id,
                    "staffRating": staff_rating,
                    "autoRating": auto_rating,
                    "ratingDelta": delta,
                }
            )

    recommendations: List[str] = []

    def _counter_to_dict(counter: Counter) -> Dict[str, int]:
        return {tag: int(count) for tag, count in counter.most_common()}

    def _counter_to_ranked_list(counter: Counter, limit: int = 10) -> List[Dict[str, Any]]:
        return [{"tag": tag, "count": int(count)} for tag, count in counter.most_common(limit)]

    def _counter_map_to_ranked(counter_map: Dict[str, Counter], limit: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        output: Dict[str, List[Dict[str, Any]]] = {}
        for key in sorted(counter_map.keys()):
            output[key] = _counter_to_ranked_list(counter_map[key], limit)
        return output

    for preset, stats in by_preset.items():
        count = stats["count"]
        rated_for_preset = stats["ratedCount"]
        auto_rated_for_preset = stats["autoRatedCount"]
        stats["averageControlWeight"] = round(stats["_controlWeightSum"] / count, 4) if count > 0 else 0
        stats["averageDenoisingStrength"] = round(stats["_denoiseSum"] / count, 4) if count > 0 else 0
        stats["averageStaffRating"] = (
            round(stats["_ratingSum"] / rated_for_preset, 3) if rated_for_preset > 0 else 0
        )
        stats["averageRating"] = stats["averageStaffRating"]
        stats["averageAutoRating"] = (
            round(stats["_autoRatingSum"] / auto_rated_for_preset, 3) if auto_rated_for_preset > 0 else 0
        )
        stats["commonBadTags"] = [tag for tag, _ in stats["_badCounter"].most_common(5)]
        stats["commonGoodTags"] = [tag for tag, _ in stats["_goodCounter"].most_common(5)]
        stats["commonAutoBadTags"] = [tag for tag, _ in stats["_autoBadCounter"].most_common(5)]
        stats["commonAutoGoodTags"] = [tag for tag, _ in stats["_autoGoodCounter"].most_common(5)]
        stats["badTagCounts"] = _counter_to_dict(stats["_badCounter"])
        stats["goodTagCounts"] = _counter_to_dict(stats["_goodCounter"])
        stats["autoBadTagCounts"] = _counter_to_dict(stats["_autoBadCounter"])
        stats["autoGoodTagCounts"] = _counter_to_dict(stats["_autoGoodCounter"])
        stats["basedOnPresetCounts"] = _counter_to_dict(stats["_basedOnPresetCounter"])
        stats["basedOnPreset"] = (
            stats["_basedOnPresetCounter"].most_common(1)[0][0]
            if stats["_basedOnPresetCounter"]
            else ""
        )
        stats["samplePromptUsed"] = (
            stats["_promptUsedCounter"].most_common(1)[0][0]
            if stats["_promptUsedCounter"]
            else ""
        )
        stats["sampleNegativePromptUsed"] = (
            stats["_negativePromptUsedCounter"].most_common(1)[0][0]
            if stats["_negativePromptUsedCounter"]
            else ""
        )

        recommendations.extend(
            _generate_recommendations(
                stats["_badCounter"],
                rated_for_preset,
                f"Preset {preset}",
            )
        )

        del stats["_ratingSum"]
        del stats["_autoRatingSum"]
        del stats["_controlWeightSum"]
        del stats["_denoiseSum"]
        del stats["_badCounter"]
        del stats["_goodCounter"]
        del stats["_autoBadCounter"]
        del stats["_autoGoodCounter"]
        del stats["_basedOnPresetCounter"]
        del stats["_promptUsedCounter"]
        del stats["_negativePromptUsedCounter"]

    for preset_animal, stats in by_preset_animal.items():
        count = int(stats.get("count", 0) or 0)
        rated_for_animal = int(stats.get("ratedCount", 0) or 0)
        stats["averageControlWeight"] = (
            round(stats["_controlWeightSum"] / count, 4) if count > 0 else 0
        )
        stats["averageDenoisingStrength"] = (
            round(stats["_denoiseSum"] / count, 4) if count > 0 else 0
        )
        stats["averageRating"] = (
            round(stats["_ratingSum"] / rated_for_animal, 3) if rated_for_animal > 0 else 0
        )
        stats["commonBadTags"] = [tag for tag, _ in stats["_badCounter"].most_common(10)]
        stats["badTagCounts"] = _counter_to_dict(stats["_badCounter"])
        del stats["_ratingSum"]
        del stats["_controlWeightSum"]
        del stats["_denoiseSum"]
        del stats["_badCounter"]

    ai_style_stats_sorted: Dict[str, Dict[str, Any]] = {}
    for style_key in sorted(ai_art_venture_style_stats.keys()):
        style_stats = ai_art_venture_style_stats[style_key]
        generated_count = int(style_stats.get("generatedCount", 0))
        rated_count = int(style_stats.get("ratedCount", 0))
        style_stats["averageRating"] = (
            round(style_stats["_ratingSum"] / rated_count, 3)
            if rated_count > 0
            else 0.0
        )
        style_stats["averageSoftEdgeWeight"] = (
            round(style_stats["_softEdgeSum"] / style_stats["_softEdgeCount"], 4)
            if style_stats["_softEdgeCount"] > 0
            else 0.0
        )
        style_stats["averageIpAdapterWeight"] = (
            round(style_stats["_ipWeightSum"] / style_stats["_ipWeightCount"], 4)
            if style_stats["_ipWeightCount"] > 0
            else 0.0
        )
        style_stats["averageDenoisingStrength"] = (
            round(style_stats["_denoiseSum"] / style_stats["_denoiseCount"], 4)
            if style_stats["_denoiseCount"] > 0
            else 0.0
        )
        style_stats["commonBadTags"] = [tag for tag, _ in style_stats["_badCounter"].most_common(5)]
        style_stats["commonGoodTags"] = [tag for tag, _ in style_stats["_goodCounter"].most_common(5)]
        style_stats["badTagCounts"] = _counter_to_dict(style_stats["_badCounter"])
        style_stats["goodTagCounts"] = _counter_to_dict(style_stats["_goodCounter"])
        style_stats["generatedCount"] = generated_count
        style_stats["ratedCount"] = rated_count
        style_stats["ipAdapterEnabledCount"] = int(style_stats.get("ipAdapterEnabledCount", 0))
        del style_stats["_ratingSum"]
        del style_stats["_softEdgeSum"]
        del style_stats["_softEdgeCount"]
        del style_stats["_ipWeightSum"]
        del style_stats["_ipWeightCount"]
        del style_stats["_denoiseSum"]
        del style_stats["_denoiseCount"]
        del style_stats["_badCounter"]
        del style_stats["_goodCounter"]
        ai_style_stats_sorted[style_key] = style_stats

    recommendations.extend(_generate_recommendations(global_bad_counter, staff_rated_count, "Global"))
    dedup_recommendations = list(dict.fromkeys(recommendations))

    if not recommendations and staff_rated_count > 0:
        dedup_recommendations.append(
            "No strong failure trend detected yet. Continue generating more samples to improve tuning confidence."
        )
    if staff_rated_count == 0:
        dedup_recommendations.append("No auto-rated images yet. Generate more images first to build tuning recommendations.")

    low_rated_items.sort(
        key=lambda item: (
            _safe_int(item.get("rating")) or 5,
            str(item.get("jobId") or ""),
        )
    )
    mismatch_examples.sort(
        key=lambda row: (
            -_safe_float(row.get("ratingDelta")),
            str(row.get("jobId") or ""),
        )
    )

    mismatch_count = len(mismatch_examples)
    average_mismatch_delta = (
        round(mismatch_total_delta / mismatch_count, 3) if mismatch_count > 0 else 0
    )
    average_similarity_score = (
        round(similarity_score_sum / similarity_score_count, 4)
        if similarity_score_count > 0
        else 0
    )
    average_white_background_ratio = (
        round(white_background_ratio_sum / white_background_ratio_count, 4)
        if white_background_ratio_count > 0
        else 0
    )
    wrong_generation_count = int(
        sum(global_bad_counter.get(tag, 0) for tag in WRONG_SUBJECT_TAGS)
    )
    person_main_object_missing_count = int(
        sum(global_bad_counter.get(tag, 0) for tag in MISSING_SUBJECT_TAGS)
    )
    identity_clothing_issue_count = int(
        sum(global_bad_counter.get(tag, 0) for tag in IDENTITY_CLOTHING_TAGS)
    )
    background_issue_count = int(
        sum(global_bad_counter.get(tag, 0) for tag in BACKGROUND_ISSUE_TAGS)
    )
    identity_clothing_issues_by_generation_mode = {
        mode_name: int(sum(counter.get(tag, 0) for tag in IDENTITY_CLOTHING_TAGS))
        for mode_name, counter in bad_by_generation_mode_counter.items()
    }
    identity_clothing_issues_by_style_id = {
        style_name: int(sum(counter.get(tag, 0) for tag in IDENTITY_CLOTHING_TAGS))
        for style_name, counter in bad_by_style_id_counter.items()
    }
    background_issues_by_generation_mode = {
        mode_name: int(sum(counter.get(tag, 0) for tag in BACKGROUND_ISSUE_TAGS))
        for mode_name, counter in bad_by_generation_mode_counter.items()
    }
    background_issues_by_style_id = {
        style_name: int(sum(counter.get(tag, 0) for tag in BACKGROUND_ISSUE_TAGS))
        for style_name, counter in bad_by_style_id_counter.items()
    }
    wrong_species_related_tags = {
        "wrong_animal",
        "wrong_species",
        "lion_detected_as_tiger",
        "lion_became_cat",
        "tiger_became_lion",
        "zebra_wrong",
        "zebra_became_horse",
        "elephant_wrong",
        "elephant_missing_trunk",
        "tiger_wrong",
    }
    wrong_species_count = int(
        sum(global_bad_counter.get(tag, 0) for tag in wrong_species_related_tags)
    )
    too_unchanged_count = int(
        sum(global_bad_counter.get(tag, 0) for tag in {"too_unchanged", "same_as_input"})
    )
    missing_preset_animal_count = len(missing_preset_animal_job_ids)
    missing_preset_animal_warning = (
        "WARNING: presetAnimal missing. Animal identity cannot be tuned accurately."
        if missing_preset_animal_count > 0
        else ""
    )

    return {
        "totalImages": total_images,
        "ratedImages": staff_rated_count,
        "averageRating": average_staff_rating,
        "staffRatedImages": staff_rated_count,
        "autoRatedImages": auto_rated_count,
        "averageStaffRating": average_staff_rating,
        "averageAutoRating": average_auto_rating,
        "autoStaffMismatch": {
            "count": mismatch_count,
            "averageDelta": average_mismatch_delta,
            "examples": mismatch_examples[:10],
        },
        "mostCommonBadTags": _counter_to_ranked_list(global_bad_counter, 20),
        "mostCommonGoodTags": _counter_to_ranked_list(global_good_counter, 20),
        "mostCommonAutoBadTags": _counter_to_ranked_list(global_auto_bad_counter, 20),
        "mostCommonAutoGoodTags": _counter_to_ranked_list(global_auto_good_counter, 20),
        "mostCommonStaffBadTags": _counter_to_ranked_list(global_bad_counter, 20),
        "badTagsByPreset": _counter_map_to_ranked(bad_by_preset_counter, 15),
        "goodTagsByPreset": _counter_map_to_ranked(good_by_preset_counter, 15),
        "badTagsByGenerationMode": _counter_map_to_ranked(bad_by_generation_mode_counter, 15),
        "badTagsByStyleId": _counter_map_to_ranked(bad_by_style_id_counter, 15),
        "badTagsByStyleRiskLevel": _counter_map_to_ranked(bad_by_style_risk_counter, 15),
        "badTagsByControlNet": _counter_map_to_ranked(bad_by_controlnet_counter, 15),
        "badTagsByIpAdapter": _counter_map_to_ranked(bad_by_ip_adapter_counter, 15),
        "mostCommonIdentityFailures": _counter_to_ranked_list(identity_failure_counter, 20),
        "mostCommonBackgroundFailures": _counter_to_ranked_list(background_failure_counter, 20),
        "mostCommonArtworkFailures": _counter_to_ranked_list(artwork_failure_counter, 20),
        "wrongGenerationCount": wrong_generation_count,
        "personMainObjectMissingCount": person_main_object_missing_count,
        "identityClothingIssueCount": identity_clothing_issue_count,
        "backgroundIssueCount": background_issue_count,
        "identityClothingIssuesByGenerationMode": identity_clothing_issues_by_generation_mode,
        "identityClothingIssuesByStyleId": identity_clothing_issues_by_style_id,
        "backgroundIssuesByGenerationMode": background_issues_by_generation_mode,
        "backgroundIssuesByStyleId": background_issues_by_style_id,
        "byPresetAnimal": by_preset_animal,
        "presetAnimalCounts": {
            key: int((row or {}).get("count") or 0)
            for key, row in by_preset_animal.items()
        },
        "badTagsByPresetAnimal": _counter_map_to_ranked(bad_by_preset_animal_counter, 20),
        "wrongSpeciesCount": wrong_species_count,
        "tooUnchangedCount": too_unchanged_count,
        "missingPresetAnimalCount": missing_preset_animal_count,
        "missingPresetAnimalWarning": missing_preset_animal_warning,
        "missingPresetAnimalJobIds": missing_preset_animal_job_ids[:50],
        "imageCountByGenerationMode": {
            GENERATION_MODE_DRAWING_TO_ARTWORK: int(
                generation_mode_count_counter.get(GENERATION_MODE_DRAWING_TO_ARTWORK, 0)
            ),
            GENERATION_MODE_AI_ART_VENTURE: int(
                generation_mode_count_counter.get(GENERATION_MODE_AI_ART_VENTURE, 0)
            ),
            GENERATION_MODE_PERSON_HOLDING_ARTWORK: int(
                generation_mode_count_counter.get(GENERATION_MODE_PERSON_HOLDING_ARTWORK, 0)
            ),
        },
        "averageBeforeAfterSimilarityScore": average_similarity_score,
        "averageWhiteBackgroundRatio": average_white_background_ratio,
        "byPreset": by_preset,
        "aiArtVentureStyleStats": ai_style_stats_sorted,
        "lowRatedItems": low_rated_items,
        "recommendations": dedup_recommendations,
        "_globalBadTags": global_bad_counter,
        "_globalGoodTags": global_good_counter,
    }


def _url_to_local_path(url: Any) -> str:
    if not isinstance(url, str) or not url.startswith("/"):
        return ""
    parts = [part for part in url.strip("/").split("/") if part]
    return str(BASE_DIR.joinpath(*parts))


def _resolve_generated_output_path(job: Dict[str, Any]) -> Path:
    output_path = Path(str(job.get("outputPath") or "")).expanduser()
    if output_path.is_file():
        return output_path

    output_url_path = Path(_url_to_local_path(job.get("outputUrl")))
    if output_url_path.is_file():
        return output_url_path

    raise FileNotFoundError("Generated output image not found")


async def _find_photo_job(job_id: str) -> Dict[str, Any]:
    gallery_item = await run_in_threadpool(gallery_store.get_item, job_id)
    if gallery_item is not None:
        return dict(gallery_item)

    job = await run_in_threadpool(queue_store.get_job, job_id)
    if job is not None:
        return dict(job)

    raise HTTPException(status_code=404, detail="Job not found")


async def _save_photo_metadata(job_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    updated_item: Optional[Dict[str, Any]] = None
    try:
        updated_item = await run_in_threadpool(gallery_store.update_item_fields, job_id, updates)
    except KeyError:
        updated_item = None

    try:
        await run_in_threadpool(queue_store.update_job_fields, job_id, updates)
    except KeyError:
        pass

    if updated_item is not None:
        await ws_manager.broadcast({"type": "gallery_item_updated", "item": updated_item})
    return updated_item


def _existing_photo_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    photo_url = str(job.get("photoPrintUrl") or "")
    if not photo_url:
        return {
            "jobId": str(job.get("jobId") or ""),
            "photoCreated": False,
            "message": "Photo print not created yet",
        }
    return {
        "jobId": str(job.get("jobId") or ""),
        "photoCreated": True,
        "photoPrintUrl": photo_url,
        "photoPrintPath": str(job.get("photoPrintPath") or ""),
        "photoPrintCreatedAt": job.get("photoPrintCreatedAt"),
        "photoPrintTemplate": job.get("photoPrintTemplate") or PHOTO_TEMPLATE,
        "photoPrintWidth": int(_safe_int(job.get("photoPrintWidth")) or PHOTO_WIDTH),
        "photoPrintHeight": int(_safe_int(job.get("photoPrintHeight")) or PHOTO_HEIGHT),
        "visitorNameUsed": str(job.get("visitorNameUsed") or job.get("visitorName") or "Wonderpark Guest"),
        "outputUrlUsedForPhoto": str(job.get("outputUrlUsedForPhoto") or job.get("outputUrl") or ""),
        "logosUsed": bool(job.get("logosUsed", False)),
        "logoFallbackUsed": bool(job.get("logoFallbackUsed", False)),
    }


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
    lines.append(f"Total rated images (auto pipeline): {summary.get('staffRatedImages', summary['ratedImages'])}")
    lines.append(f"Total auto-rated images: {summary.get('autoRatedImages', 0)}")
    lines.append(f"Average final rating: {summary.get('averageStaffRating', summary['averageRating'])}")
    lines.append(f"Average auto rating: {summary.get('averageAutoRating', 0)}")
    mismatch = summary.get("autoStaffMismatch", {})
    lines.append(
        f"Auto/staff mismatch count: {mismatch.get('count', 0)} "
        f"(avg delta: {mismatch.get('averageDelta', 0)})"
    )
    lines.append("")
    lines.append("Average rating by preset:")
    for preset_name, stats in summary["byPreset"].items():
        based_on_preset = str(stats.get("basedOnPreset") or "-")
        lines.append(
            f"- {preset_name}: avgStaff={stats.get('averageStaffRating', stats['averageRating'])} "
            f"avgAuto={stats.get('averageAutoRating', 0)} "
            f"rated={stats['ratedCount']}/{stats['count']} "
            f"autoRated={stats.get('autoRatedCount', 0)}/{stats['count']} "
            f"avgControlWeight={stats['averageControlWeight']} avgDenoising={stats['averageDenoisingStrength']} "
            f"basedOnPreset={based_on_preset}"
        )
        prompt_sample = str(stats.get("samplePromptUsed") or "").strip()
        negative_sample = str(stats.get("sampleNegativePromptUsed") or "").strip()
        if prompt_sample:
            lines.append(f"  promptUsedSample: {prompt_sample}")
        if negative_sample:
            lines.append(f"  negativePromptUsedSample: {negative_sample}")

    lines.append("")
    lines.append("Average rating by presetAnimal:")
    by_preset_animal = summary.get("byPresetAnimal", {})
    if not by_preset_animal:
        lines.append("- None")
    else:
        for preset_animal, stats in by_preset_animal.items():
            lines.append(
                f"- {preset_animal}: avgRating={stats.get('averageRating', 0)} "
                f"rated={stats.get('ratedCount', 0)}/{stats.get('count', 0)} "
                f"avgControlWeight={stats.get('averageControlWeight', 0)} "
                f"avgDenoising={stats.get('averageDenoisingStrength', 0)}"
            )

    lines.append("")
    lines.append("Most common bad feedback tags:")
    most_common_bad = summary.get("mostCommonBadTags", [])
    if not most_common_bad:
        lines.append("- None")
    else:
        for entry in most_common_bad:
            lines.append(f"- {entry.get('tag')}: {entry.get('count')}")

    lines.append("")
    lines.append("Most common good feedback tags:")
    most_common_good = summary.get("mostCommonGoodTags", [])
    if not most_common_good:
        lines.append("- None")
    else:
        for entry in most_common_good:
            lines.append(f"- {entry.get('tag')}: {entry.get('count')}")

    lines.append("")
    lines.append("Most common auto bad tags:")
    most_common_auto_bad = summary.get("mostCommonAutoBadTags", [])
    if not most_common_auto_bad:
        lines.append("- None")
    else:
        for entry in most_common_auto_bad:
            lines.append(f"- {entry.get('tag')}: {entry.get('count')}")

    lines.append("")
    lines.append("Most common staff bad tags:")
    most_common_staff_bad = summary.get("mostCommonStaffBadTags", [])
    if not most_common_staff_bad:
        lines.append("- None")
    else:
        for entry in most_common_staff_bad:
            lines.append(f"- {entry.get('tag')}: {entry.get('count')}")

    lines.append("")
    lines.append("Bad tags by preset:")
    bad_by_preset = summary.get("badTagsByPreset", {})
    if not bad_by_preset:
        lines.append("- None")
    else:
        for preset_name, rows in bad_by_preset.items():
            pairs = [f"{entry.get('tag')}({entry.get('count')})" for entry in rows]
            lines.append(f"- {preset_name}: {pairs}")

    lines.append("")
    lines.append("Good tags by preset:")
    good_by_preset = summary.get("goodTagsByPreset", {})
    if not good_by_preset:
        lines.append("- None")
    else:
        for preset_name, rows in good_by_preset.items():
            pairs = [f"{entry.get('tag')}({entry.get('count')})" for entry in rows]
            lines.append(f"- {preset_name}: {pairs}")

    lines.append("")
    lines.append("Bad tags by presetAnimal:")
    bad_by_preset_animal = summary.get("badTagsByPresetAnimal", {})
    if not bad_by_preset_animal:
        lines.append("- None")
    else:
        for preset_animal, rows in bad_by_preset_animal.items():
            pairs = [f"{entry.get('tag')}({entry.get('count')})" for entry in rows]
            lines.append(f"- {preset_animal}: {pairs}")

    lines.append("")
    lines.append("Bad tags by generationMode:")
    bad_by_mode = summary.get("badTagsByGenerationMode", {})
    if not bad_by_mode:
        lines.append("- None")
    else:
        for mode_name, rows in bad_by_mode.items():
            pairs = [f"{entry.get('tag')}({entry.get('count')})" for entry in rows]
            lines.append(f"- {mode_name}: {pairs}")

    lines.append("")
    lines.append("Bad tags by styleId:")
    bad_by_style = summary.get("badTagsByStyleId", {})
    if not bad_by_style:
        lines.append("- None")
    else:
        for style_name, rows in bad_by_style.items():
            pairs = [f"{entry.get('tag')}({entry.get('count')})" for entry in rows]
            lines.append(f"- {style_name}: {pairs}")

    lines.append("")
    lines.append("Bad tags by styleRiskLevel:")
    bad_by_style_risk = summary.get("badTagsByStyleRiskLevel", {})
    if not bad_by_style_risk:
        lines.append("- None")
    else:
        for risk_level, rows in bad_by_style_risk.items():
            pairs = [f"{entry.get('tag')}({entry.get('count')})" for entry in rows]
            lines.append(f"- {risk_level}: {pairs}")

    lines.append("")
    lines.append("Bad tags by ControlNet module/model:")
    bad_by_controlnet = summary.get("badTagsByControlNet", {})
    if not bad_by_controlnet:
        lines.append("- None")
    else:
        for controlnet_key, rows in bad_by_controlnet.items():
            pairs = [f"{entry.get('tag')}({entry.get('count')})" for entry in rows]
            lines.append(f"- {controlnet_key}: {pairs}")

    lines.append("")
    lines.append("Bad tags by IP-Adapter status:")
    bad_by_ip_adapter = summary.get("badTagsByIpAdapter", {})
    if not bad_by_ip_adapter:
        lines.append("- None")
    else:
        for ip_key, rows in bad_by_ip_adapter.items():
            pairs = [f"{entry.get('tag')}({entry.get('count')})" for entry in rows]
            lines.append(f"- {ip_key}: {pairs}")

    lines.append("")
    lines.append("Most common identity-related failures:")
    identity_failures = summary.get("mostCommonIdentityFailures", [])
    if not identity_failures:
        lines.append("- None")
    else:
        for entry in identity_failures:
            lines.append(f"- {entry.get('tag')}: {entry.get('count')}")

    lines.append("")
    lines.append("Most common background-related failures:")
    background_failures = summary.get("mostCommonBackgroundFailures", [])
    if not background_failures:
        lines.append("- None")
    else:
        for entry in background_failures:
            lines.append(f"- {entry.get('tag')}: {entry.get('count')}")

    lines.append("")
    lines.append("Most common artwork-related failures:")
    artwork_failures = summary.get("mostCommonArtworkFailures", [])
    if not artwork_failures:
        lines.append("- None")
    else:
        for entry in artwork_failures:
            lines.append(f"- {entry.get('tag')}: {entry.get('count')}")

    lines.append("")
    lines.append("Key issue counts:")
    lines.append(f"- wrong generation count: {summary.get('wrongGenerationCount', 0)}")
    lines.append(
        f"- person/main object missing count: {summary.get('personMainObjectMissingCount', 0)}"
    )
    lines.append(
        f"- identity/clothing issue count: {summary.get('identityClothingIssueCount', 0)}"
    )
    lines.append(
        f"- background issue count: {summary.get('backgroundIssueCount', 0)}"
    )
    lines.append(
        f"- wrong species count: {summary.get('wrongSpeciesCount', 0)}"
    )
    lines.append(
        f"- too unchanged count: {summary.get('tooUnchangedCount', 0)}"
    )
    lines.append(
        f"- average before/after similarity score: {summary.get('averageBeforeAfterSimilarityScore', 0)}"
    )
    lines.append(
        f"- average white background ratio: {summary.get('averageWhiteBackgroundRatio', 0)}"
    )
    missing_preset_warning = str(summary.get("missingPresetAnimalWarning") or "").strip()
    if missing_preset_warning:
        lines.append(f"- {missing_preset_warning}")

    lines.append("")
    lines.append("Image count by generationMode:")
    image_count_by_mode = summary.get("imageCountByGenerationMode", {})
    lines.append(
        f"- {GENERATION_MODE_DRAWING_TO_ARTWORK}: {int(image_count_by_mode.get(GENERATION_MODE_DRAWING_TO_ARTWORK, 0))}"
    )
    lines.append(
        f"- {GENERATION_MODE_AI_ART_VENTURE}: {int(image_count_by_mode.get(GENERATION_MODE_AI_ART_VENTURE, 0))}"
    )
    lines.append(
        f"- {GENERATION_MODE_PERSON_HOLDING_ARTWORK}: {int(image_count_by_mode.get(GENERATION_MODE_PERSON_HOLDING_ARTWORK, 0))}"
    )

    lines.append("")
    lines.append("Identity/clothing issues by generationMode:")
    identity_by_mode = summary.get("identityClothingIssuesByGenerationMode", {})
    if not identity_by_mode:
        lines.append("- None")
    else:
        for mode_name, count in identity_by_mode.items():
            lines.append(f"- {mode_name}: {count}")

    lines.append("")
    lines.append("Identity/clothing issues by styleId:")
    identity_by_style = summary.get("identityClothingIssuesByStyleId", {})
    if not identity_by_style:
        lines.append("- None")
    else:
        for style_name, count in identity_by_style.items():
            lines.append(f"- {style_name}: {count}")

    lines.append("")
    lines.append("Background issues by generationMode:")
    background_by_mode = summary.get("backgroundIssuesByGenerationMode", {})
    if not background_by_mode:
        lines.append("- None")
    else:
        for mode_name, count in background_by_mode.items():
            lines.append(f"- {mode_name}: {count}")

    lines.append("")
    lines.append("Background issues by styleId:")
    background_by_style = summary.get("backgroundIssuesByStyleId", {})
    if not background_by_style:
        lines.append("- None")
    else:
        for style_name, count in background_by_style.items():
            lines.append(f"- {style_name}: {count}")

    lines.append("")
    lines.append("Recommendations:")
    for recommendation in summary["recommendations"]:
        lines.append(f"- {recommendation}")

    lines.append("")
    lines.append("Recommendation for next tuning cycle:")
    next_cycle = summary["recommendations"][0] if summary.get("recommendations") else "Continue collecting ratings."
    lines.append(f"- {next_cycle}")

    lines.append("")
    lines.append("Generation settings by preset:")
    for preset_name, stats in summary["byPreset"].items():
        lines.append(
            f"- {preset_name}: avgControlWeight={stats['averageControlWeight']} avgDenoising={stats['averageDenoisingStrength']}"
        )

    lines.append("")
    lines.append("AI Art Venture style performance (all styles):")
    ai_style_stats = summary.get("aiArtVentureStyleStats", {})
    if not ai_style_stats:
        lines.append("- None")
    else:
        for style_id, style_stats in ai_style_stats.items():
            bad_tags = ", ".join(style_stats.get("commonBadTags", [])) or "-"
            good_tags = ", ".join(style_stats.get("commonGoodTags", [])) or "-"
            lines.append(
                f"- {style_id} ({style_stats.get('styleLabel')}) "
                f"[risk={style_stats.get('styleRiskLevel', 'balanced')}]: "
                f"generated={style_stats.get('generatedCount', 0)}, "
                f"avgRating={style_stats.get('averageRating', 0)}, "
                f"commonBadTags={bad_tags}, "
                f"commonGoodTags={good_tags}, "
                f"avgSoftEdgeWeight={style_stats.get('averageSoftEdgeWeight', 0)}, "
                f"avgIpAdapterWeight={style_stats.get('averageIpAdapterWeight', 0)}, "
                f"avgDenoising={style_stats.get('averageDenoisingStrength', 0)}, "
                f"ipAdapterEnabledCount={style_stats.get('ipAdapterEnabledCount', 0)}"
            )

    lines.append("")
    lines.append("Auto/staff mismatch examples:")
    mismatch_examples = (summary.get("autoStaffMismatch") or {}).get("examples", [])
    if not mismatch_examples:
        lines.append("- None")
    else:
        for row in mismatch_examples[:10]:
            lines.append(
                f"- jobId={row.get('jobId')} preset={row.get('preset')} generationMode={row.get('generationMode')} "
                f"styleId={row.get('styleId')} auto={row.get('autoRating')} staff={row.get('staffRating')} "
                f"delta={row.get('ratingDelta')}"
            )

    lines.append("")
    lines.append("Prompts used (from low-rated examples):")
    prompt_set = []
    for item in summary["lowRatedItems"]:
        prompt_text = str(item.get("promptUsed") or item.get("prompt") or "").strip()
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
        lines.append(f"presetAnimal: {item.get('presetAnimal')}")
        lines.append(f"generationMode: {item.get('generationMode')}")
        lines.append(f"styleId: {item.get('styleId')}")
        lines.append(f"staffRating: {item.get('staffRating', item.get('rating'))}")
        lines.append(f"autoRating: {item.get('autoRating')}")
        lines.append(f"autoReview: {item.get('autoReview', {})}")
        lines.append(f"feedbackTags: {item.get('feedbackTags', [])}")
        lines.append(f"feedbackNote: {item.get('feedbackNote', '')}")
        lines.append(f"comparisonScores: {item.get('comparisonScores', {})}")
        lines.append(f"detection: {item.get('detection', {})}")
        lines.append(f"exactGenerationSettings: {item.get('generationSettings', {})}")
        lines.append(f"promptUsed: {item.get('promptUsed') or item.get('prompt', '')}")
        lines.append(f"negativePromptUsed: {item.get('negativePromptUsed') or item.get('negativePrompt', '')}")
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
        "generationEngine",
        "generationMode",
        "styleId",
        "styleLabel",
        "styleRiskLevel",
        "mode",
        "aiArtVentureEnabled",
        "randomStyleEnabled",
        "randomThemeEnabled",
        "selectedStyleId",
        "selectedThemeId",
        "customTheme",
        "finalStyleId",
        "finalStyleName",
        "finalThemeId",
        "finalThemeName",
        "source",
        "inputUrl",
        "outputUrl",
        "preset",
        "promptMode",
        "promptType",
        "generationSettings",
        "backendPromptId",
        "backendMetadata",
        "checkpoint",
        "controlNetModel",
        "controlNetModule",
        "denoisingStrength",
        "controlWeight",
        "controlMode",
        "cfgScale",
        "steps",
        "samplerName",
        "backgroundType",
        "whiteBackgroundRatio",
        "presetAnimal",
        "speciesPromptUsed",
        "finalDenoisingStrength",
        "finalControlWeight",
        "finalPrompt",
        "promptUsed",
        "negativePromptUsed",
        "stylePreset",
        "style_preset",
        "stylePresetId",
        "stylePresetName",
        "styleCategory",
        "identitySafetyMode",
        "experimentalMode",
        "ipAdapterEnabled",
        "ipAdapterType",
        "ipAdapterWarning",
        "ipAdapterWeight",
        "identityGuidanceUsed",
        "identityTarget",
        "basedOnPreset",
        "loraUsed",
        "loraName",
        "originalJobId",
        "regenerationOf",
        "version",
        "problemTags",
        "rating",
        "staffRating",
        "autoRating",
        "autoReview",
        "feedbackTags",
        "feedbackNote",
        "comparisonScores",
        "ratedAt",
    )
    payload = {key: job.get(key) for key in keys}
    payload["generationMode"], payload["styleId"] = _resolve_mode_and_style_ids(
        payload.get("generationMode"),
        payload.get("styleId"),
    )
    if not payload.get("styleLabel"):
        payload["styleLabel"] = _resolve_style_label(
            str(payload.get("generationMode") or DEFAULT_GENERATION_MODE),
            str(payload.get("styleId") or DEFAULT_STYLE_ID),
        )
    if payload.get("generationMode") == GENERATION_MODE_AI_ART_VENTURE and not payload.get("styleRiskLevel"):
        payload["styleRiskLevel"] = _resolve_ai_art_style_metadata(str(payload.get("styleId") or "")).get(
            "styleRiskLevel",
            "balanced",
        )
    settings = payload.get("generationSettings") if isinstance(payload.get("generationSettings"), dict) else {}
    payload["generationEngine"] = _normalize_generation_engine(
        payload.get("generationEngine")
        or settings.get("generationEngine")
        or _resolve_generation_engine_name()
    )
    payload["backendPromptId"] = payload.get("backendPromptId") or settings.get("backendPromptId")
    if not isinstance(payload.get("backendMetadata"), dict):
        payload["backendMetadata"] = (
            settings.get("backendMetadata")
            if isinstance(settings.get("backendMetadata"), dict)
            else {}
        )
    payload["checkpoint"] = payload.get("checkpoint") or settings.get("checkpoint")
    payload["controlNetModel"] = payload.get("controlNetModel") or settings.get("controlNetModel")
    payload["controlNetModule"] = payload.get("controlNetModule") or settings.get("controlNetModule")
    payload["denoisingStrength"] = payload.get("denoisingStrength") or settings.get("denoisingStrength")
    payload["controlWeight"] = payload.get("controlWeight") or settings.get("controlWeight")
    payload["softEdgeWeight"] = (
        payload.get("softEdgeWeight")
        or settings.get("softEdgeWeight")
        or payload.get("controlWeight")
    )
    payload["controlMode"] = payload.get("controlMode") or settings.get("controlMode")
    payload["cfgScale"] = payload.get("cfgScale") or settings.get("cfgScale")
    payload["steps"] = payload.get("steps") or settings.get("steps")
    payload["backgroundType"] = payload.get("backgroundType") or settings.get("backgroundType")
    if payload.get("whiteBackgroundRatio") is None:
        payload["whiteBackgroundRatio"] = settings.get("whiteBackgroundRatio")
    payload["presetAnimal"] = _normalize_preset_animal(
        payload.get("presetAnimal") or settings.get("presetAnimal")
    )
    if payload.get("speciesPromptUsed") is None:
        payload["speciesPromptUsed"] = settings.get("speciesPromptUsed")
    if payload.get("finalDenoisingStrength") is None:
        payload["finalDenoisingStrength"] = settings.get("finalDenoisingStrength")
    if payload.get("finalControlWeight") is None:
        payload["finalControlWeight"] = settings.get("finalControlWeight")
    payload["finalPrompt"] = payload.get("finalPrompt") or settings.get("finalPrompt")
    payload["promptUsed"] = payload.get("promptUsed") or settings.get("promptUsed") or payload.get("prompt")
    payload["negativePromptUsed"] = (
        payload.get("negativePromptUsed")
        or settings.get("negativePromptUsed")
        or payload.get("negativePrompt")
    )
    payload["stylePreset"] = (
        payload.get("stylePreset")
        or payload.get("style_preset")
        or settings.get("stylePreset")
        or settings.get("style_preset")
        or "random"
    )
    payload["style_preset"] = payload["stylePreset"]
    payload["stylePresetId"] = (
        payload.get("stylePresetId")
        or settings.get("stylePresetId")
        or settings.get("style_preset_id")
        or (payload.get("backendMetadata") or {}).get("style_preset_id")
    )
    payload["stylePresetName"] = (
        payload.get("stylePresetName")
        or settings.get("stylePresetName")
        or settings.get("style_preset_name")
        or (payload.get("backendMetadata") or {}).get("style_preset_name")
    )
    payload["styleCategory"] = (
        payload.get("styleCategory")
        or settings.get("styleCategory")
        or settings.get("style_category")
        or (payload.get("backendMetadata") or {}).get("style_category")
    )
    if payload.get("identitySafetyMode") is None:
        payload["identitySafetyMode"] = settings.get("identitySafetyMode")
    if payload.get("experimentalMode") is None:
        payload["experimentalMode"] = settings.get("experimentalMode")
    if payload.get("ipAdapterWarning") is None:
        payload["ipAdapterWarning"] = settings.get("ipAdapterWarning")
    _sync_generation_metadata_fields(payload, settings)
    payload["source"] = _normalize_source(payload.get("source"))
    payload["autoReview"] = _normalize_auto_review_payload(payload.get("autoReview"))
    payload["autoRating"] = int(_safe_int(payload.get("autoRating")) or payload["autoReview"].get("autoRating") or 0)
    payload["staffRating"] = _get_staff_rating(payload) if isinstance(payload, dict) else None
    payload["rating"] = payload["staffRating"]
    payload["comparisonScores"] = payload.get("comparisonScores") if isinstance(payload.get("comparisonScores"), dict) else {}
    return payload


def _gallery_item_to_job_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    generation_mode, style_id = _resolve_mode_and_style_ids(
        item.get("generationMode"),
        item.get("styleId"),
    )
    style_label = str(item.get("styleLabel") or _resolve_style_label(generation_mode, style_id))
    return {
        "jobId": item.get("jobId"),
        "status": "completed",
        "visitorName": item.get("visitorName"),
        "generationEngine": _normalize_generation_engine(
            item.get("generationEngine")
            or (item.get("generationSettings") or {}).get("generationEngine")
            or _resolve_generation_engine_name()
        ),
        "generationMode": generation_mode,
        "styleId": style_id,
        "styleLabel": style_label,
        "styleRiskLevel": item.get("styleRiskLevel"),
        "mode": item.get("mode"),
        "aiArtVentureEnabled": item.get("aiArtVentureEnabled"),
        "randomStyleEnabled": item.get("randomStyleEnabled"),
        "randomThemeEnabled": item.get("randomThemeEnabled"),
        "selectedStyleId": item.get("selectedStyleId"),
        "selectedThemeId": item.get("selectedThemeId"),
        "customTheme": item.get("customTheme"),
        "finalStyleId": item.get("finalStyleId"),
        "finalStyleName": item.get("finalStyleName"),
        "finalThemeId": item.get("finalThemeId"),
        "finalThemeName": item.get("finalThemeName"),
        "source": _normalize_source(item.get("source")),
        "inputUrl": item.get("inputUrl"),
        "outputPath": item.get("outputPath"),
        "outputUrl": item.get("outputUrl"),
        "photoPrintUrl": item.get("photoPrintUrl"),
        "photoPrintPath": item.get("photoPrintPath"),
        "photoPrintCreatedAt": item.get("photoPrintCreatedAt"),
        "photoPrintTemplate": item.get("photoPrintTemplate"),
        "photoPrintWidth": item.get("photoPrintWidth"),
        "photoPrintHeight": item.get("photoPrintHeight"),
        "visitorNameUsed": item.get("visitorNameUsed"),
        "outputUrlUsedForPhoto": item.get("outputUrlUsedForPhoto"),
        "logosUsed": item.get("logosUsed"),
        "logoFallbackUsed": item.get("logoFallbackUsed"),
        "backendPromptId": item.get("backendPromptId"),
        "backendMetadata": item.get("backendMetadata")
        if isinstance(item.get("backendMetadata"), dict)
        else {},
        "createdAt": item.get("createdAt"),
        "startedAt": item.get("startedAt"),
        "completedAt": item.get("completedAt"),
        "durationSeconds": item.get("durationSeconds"),
        "checkpoint": item.get("checkpoint"),
        "controlNetModel": item.get("controlNetModel"),
        "controlNetModule": item.get("controlNetModule"),
        "denoisingStrength": item.get("denoisingStrength"),
        "controlWeight": item.get("controlWeight"),
        "softEdgeWeight": (
            item.get("softEdgeWeight")
            if item.get("softEdgeWeight") is not None
            else (item.get("generationSettings") or {}).get("softEdgeWeight")
        ),
        "controlMode": item.get("controlMode"),
        "cfgScale": item.get("cfgScale"),
        "steps": item.get("steps"),
        "samplerName": item.get("samplerName"),
        "backgroundType": item.get("backgroundType"),
        "whiteBackgroundRatio": item.get("whiteBackgroundRatio"),
        "presetAnimal": _normalize_preset_animal(item.get("presetAnimal")),
        "speciesPromptUsed": item.get("speciesPromptUsed"),
        "finalDenoisingStrength": item.get("finalDenoisingStrength"),
        "finalControlWeight": item.get("finalControlWeight"),
        "finalPrompt": item.get("finalPrompt"),
        "promptUsed": item.get("promptUsed"),
        "negativePromptUsed": item.get("negativePromptUsed"),
        "stylePreset": item.get("stylePreset") or item.get("style_preset") or "random",
        "style_preset": item.get("style_preset") or item.get("stylePreset") or "random",
        "stylePresetId": item.get("stylePresetId"),
        "stylePresetName": item.get("stylePresetName"),
        "styleCategory": item.get("styleCategory"),
        "identitySafetyMode": item.get("identitySafetyMode"),
        "experimentalMode": item.get("experimentalMode"),
        "ipAdapterEnabled": item.get("ipAdapterEnabled"),
        "ipAdapterType": item.get("ipAdapterType"),
        "ipAdapterWarning": item.get("ipAdapterWarning"),
        "ipAdapterWeight": item.get("ipAdapterWeight"),
        "identityGuidanceUsed": item.get("identityGuidanceUsed"),
        "identityTarget": item.get("identityTarget"),
        "basedOnPreset": item.get("basedOnPreset"),
        "loraUsed": item.get("loraUsed"),
        "loraName": item.get("loraName"),
        "rating": _get_staff_rating(item),
        "staffRating": _get_staff_rating(item),
        "autoRating": item.get("autoRating"),
        "autoReview": _normalize_auto_review_payload(item.get("autoReview")),
        "feedbackTags": item.get("feedbackTags", []),
        "feedbackNote": item.get("feedbackNote", ""),
        "comparisonScores": item.get("comparisonScores", {}) if isinstance(item.get("comparisonScores"), dict) else {},
        "ratedAt": item.get("ratedAt"),
        "error": None,
    }


def _build_api_job_payload(job: Dict[str, Any], request: Request, absolute: bool) -> Dict[str, Any]:
    generation_mode, style_id = _resolve_mode_and_style_ids(
        job.get("generationMode"),
        job.get("styleId"),
    )
    style_label = str(job.get("styleLabel") or _resolve_style_label(generation_mode, style_id))
    settings = job.get("generationSettings") if isinstance(job.get("generationSettings"), dict) else {}
    normalized_auto_review = _normalize_auto_review_payload(job.get("autoReview"))
    style_risk_level = str(job.get("styleRiskLevel") or "").strip().lower()
    if generation_mode == GENERATION_MODE_AI_ART_VENTURE and not style_risk_level:
        style_risk_level = _resolve_ai_art_style_metadata(style_id).get("styleRiskLevel", "balanced")
    payload = {
        "jobId": str(job.get("jobId") or ""),
        "status": str(job.get("status") or "queued"),
        "visitorName": _normalize_visitor_name(job.get("visitorName")),
        "generationEngine": _normalize_generation_engine(
            job.get("generationEngine")
            or settings.get("generationEngine")
            or _resolve_generation_engine_name()
        ),
        "generationMode": generation_mode,
        "styleId": style_id,
        "styleLabel": style_label,
        "styleRiskLevel": style_risk_level or None,
        "mode": job.get("mode"),
        "aiArtVentureEnabled": job.get("aiArtVentureEnabled"),
        "randomStyleEnabled": job.get("randomStyleEnabled"),
        "randomThemeEnabled": job.get("randomThemeEnabled"),
        "selectedStyleId": job.get("selectedStyleId"),
        "selectedThemeId": job.get("selectedThemeId"),
        "customTheme": job.get("customTheme"),
        "finalStyleId": job.get("finalStyleId"),
        "finalStyleName": job.get("finalStyleName"),
        "finalThemeId": job.get("finalThemeId"),
        "finalThemeName": job.get("finalThemeName"),
        "source": _normalize_source(job.get("source")),
        "inputUrl": str(job.get("inputUrl") or ""),
        "outputPath": str(job.get("outputPath") or ""),
        "outputUrl": str(job.get("outputUrl") or ""),
        "photoPrintUrl": str(job.get("photoPrintUrl") or ""),
        "photoPrintPath": str(job.get("photoPrintPath") or ""),
        "photoPrintCreatedAt": job.get("photoPrintCreatedAt"),
        "photoPrintTemplate": job.get("photoPrintTemplate"),
        "photoPrintWidth": job.get("photoPrintWidth"),
        "photoPrintHeight": job.get("photoPrintHeight"),
        "visitorNameUsed": job.get("visitorNameUsed"),
        "outputUrlUsedForPhoto": job.get("outputUrlUsedForPhoto"),
        "logosUsed": job.get("logosUsed"),
        "logoFallbackUsed": job.get("logoFallbackUsed"),
        "backendPromptId": job.get("backendPromptId") or settings.get("backendPromptId"),
        "backendMetadata": job.get("backendMetadata")
        if isinstance(job.get("backendMetadata"), dict)
        else (settings.get("backendMetadata") if isinstance(settings.get("backendMetadata"), dict) else {}),
        "createdAt": job.get("createdAt"),
        "startedAt": job.get("startedAt"),
        "completedAt": job.get("completedAt"),
        "durationSeconds": float(_safe_float(job.get("durationSeconds"))),
        "error": job.get("error"),
        "checkpoint": job.get("checkpoint") or settings.get("checkpoint"),
        "controlNetModel": job.get("controlNetModel") or settings.get("controlNetModel"),
        "controlNetModule": job.get("controlNetModule") or settings.get("controlNetModule"),
        "denoisingStrength": job.get("denoisingStrength") or settings.get("denoisingStrength"),
        "controlWeight": job.get("controlWeight") or settings.get("controlWeight"),
        "softEdgeWeight": (
            job.get("softEdgeWeight")
            or settings.get("softEdgeWeight")
            or job.get("controlWeight")
            or settings.get("controlWeight")
        ),
        "controlMode": job.get("controlMode") or settings.get("controlMode"),
        "cfgScale": job.get("cfgScale") or settings.get("cfgScale"),
        "steps": job.get("steps") or settings.get("steps"),
        "samplerName": job.get("samplerName") or settings.get("samplerName"),
        "backgroundType": job.get("backgroundType") or settings.get("backgroundType"),
        "whiteBackgroundRatio": (
            job.get("whiteBackgroundRatio")
            if job.get("whiteBackgroundRatio") is not None
            else settings.get("whiteBackgroundRatio")
        ),
        "presetAnimal": _normalize_preset_animal(
            job.get("presetAnimal") or settings.get("presetAnimal")
        ),
        "speciesPromptUsed": job.get("speciesPromptUsed") or settings.get("speciesPromptUsed"),
        "finalDenoisingStrength": (
            job.get("finalDenoisingStrength")
            if job.get("finalDenoisingStrength") is not None
            else settings.get("finalDenoisingStrength")
        ),
        "finalControlWeight": (
            job.get("finalControlWeight")
            if job.get("finalControlWeight") is not None
            else settings.get("finalControlWeight")
        ),
        "finalPrompt": job.get("finalPrompt") or settings.get("finalPrompt"),
        "promptUsed": job.get("promptUsed") or settings.get("promptUsed") or job.get("prompt"),
        "negativePromptUsed": (
            job.get("negativePromptUsed")
            or settings.get("negativePromptUsed")
            or job.get("negativePrompt")
        ),
        "stylePreset": (
            job.get("stylePreset")
            or job.get("style_preset")
            or settings.get("stylePreset")
            or settings.get("style_preset")
            or "random"
        ),
        "style_preset": (
            job.get("style_preset")
            or job.get("stylePreset")
            or settings.get("style_preset")
            or settings.get("stylePreset")
            or "random"
        ),
        "stylePresetId": (
            job.get("stylePresetId")
            or settings.get("stylePresetId")
            or settings.get("style_preset_id")
            or (job.get("backendMetadata") or {}).get("style_preset_id")
        ),
        "stylePresetName": (
            job.get("stylePresetName")
            or settings.get("stylePresetName")
            or settings.get("style_preset_name")
            or (job.get("backendMetadata") or {}).get("style_preset_name")
        ),
        "styleCategory": (
            job.get("styleCategory")
            or settings.get("styleCategory")
            or settings.get("style_category")
            or (job.get("backendMetadata") or {}).get("style_category")
        ),
        "identitySafetyMode": (
            job.get("identitySafetyMode")
            if job.get("identitySafetyMode") is not None
            else settings.get("identitySafetyMode")
        ),
        "experimentalMode": (
            job.get("experimentalMode")
            if job.get("experimentalMode") is not None
            else settings.get("experimentalMode")
        ),
        "ipAdapterEnabled": (
            job.get("ipAdapterEnabled")
            if job.get("ipAdapterEnabled") is not None
            else settings.get("ipAdapterEnabled")
        ),
        "ipAdapterType": job.get("ipAdapterType") or settings.get("ipAdapterType"),
        "ipAdapterWarning": job.get("ipAdapterWarning") or settings.get("ipAdapterWarning"),
        "ipAdapterWeight": (
            job.get("ipAdapterWeight")
            if job.get("ipAdapterWeight") is not None
            else settings.get("ipAdapterWeight")
        ),
        "identityGuidanceUsed": (
            job.get("identityGuidanceUsed")
            if job.get("identityGuidanceUsed") is not None
            else settings.get("identityGuidanceUsed")
        ),
        "identityTarget": job.get("identityTarget") or settings.get("identityTarget"),
        "basedOnPreset": job.get("basedOnPreset") or settings.get("basedOnPreset"),
        "loraUsed": (
            job.get("loraUsed")
            if job.get("loraUsed") is not None
            else settings.get("loraUsed")
        ),
        "loraName": job.get("loraName") or settings.get("loraName"),
        "rating": _get_staff_rating(job),
        "staffRating": _get_staff_rating(job),
        "autoRating": int(_safe_int(job.get("autoRating")) or normalized_auto_review.get("autoRating") or 0),
        "autoReview": normalized_auto_review,
        "feedbackTags": job.get("feedbackTags", []),
        "feedbackNote": job.get("feedbackNote", ""),
        "comparisonScores": job.get("comparisonScores", {}) if isinstance(job.get("comparisonScores"), dict) else {},
        "ratedAt": job.get("ratedAt"),
    }
    _sync_generation_metadata_fields(payload, settings)
    return _with_absolute_image_urls(request, payload, absolute)


def _build_api_gallery_item(item: Dict[str, Any], request: Request, absolute: bool) -> Dict[str, Any]:
    payload = dict(item)
    payload["generationMode"], payload["styleId"] = _resolve_mode_and_style_ids(
        payload.get("generationMode"),
        payload.get("styleId"),
    )
    if not payload.get("styleLabel"):
        payload["styleLabel"] = _resolve_style_label(payload["generationMode"], payload["styleId"])
    if payload.get("generationMode") == GENERATION_MODE_AI_ART_VENTURE and not payload.get("styleRiskLevel"):
        payload["styleRiskLevel"] = _resolve_ai_art_style_metadata(str(payload.get("styleId") or "")).get(
            "styleRiskLevel",
            "balanced",
        )
    payload["source"] = _normalize_source(payload.get("source"))
    payload["status"] = str(payload.get("status") or "completed")
    payload["inputUrl"] = str(payload.get("inputUrl") or "")
    payload["outputUrl"] = str(payload.get("outputUrl") or "")
    settings = payload.get("generationSettings") if isinstance(payload.get("generationSettings"), dict) else {}
    payload["checkpoint"] = payload.get("checkpoint") or settings.get("checkpoint")
    payload["controlNetModel"] = payload.get("controlNetModel") or settings.get("controlNetModel")
    payload["controlNetModule"] = payload.get("controlNetModule") or settings.get("controlNetModule")
    payload["denoisingStrength"] = payload.get("denoisingStrength") or settings.get("denoisingStrength")
    payload["controlWeight"] = payload.get("controlWeight") or settings.get("controlWeight")
    payload["controlMode"] = payload.get("controlMode") or settings.get("controlMode")
    payload["cfgScale"] = payload.get("cfgScale") or settings.get("cfgScale")
    payload["steps"] = payload.get("steps") or settings.get("steps")
    payload["backgroundType"] = payload.get("backgroundType") or settings.get("backgroundType")
    if payload.get("whiteBackgroundRatio") is None:
        payload["whiteBackgroundRatio"] = settings.get("whiteBackgroundRatio")
    payload["presetAnimal"] = _normalize_preset_animal(
        payload.get("presetAnimal") or settings.get("presetAnimal")
    )
    if payload.get("speciesPromptUsed") is None:
        payload["speciesPromptUsed"] = settings.get("speciesPromptUsed")
    if payload.get("finalDenoisingStrength") is None:
        payload["finalDenoisingStrength"] = settings.get("finalDenoisingStrength")
    if payload.get("finalControlWeight") is None:
        payload["finalControlWeight"] = settings.get("finalControlWeight")
    payload["finalPrompt"] = payload.get("finalPrompt") or settings.get("finalPrompt")
    payload["promptUsed"] = payload.get("promptUsed") or settings.get("promptUsed") or payload.get("prompt")
    payload["negativePromptUsed"] = (
        payload.get("negativePromptUsed")
        or settings.get("negativePromptUsed")
        or payload.get("negativePrompt")
    )
    payload["stylePreset"] = (
        payload.get("stylePreset")
        or payload.get("style_preset")
        or settings.get("stylePreset")
        or settings.get("style_preset")
        or "random"
    )
    payload["style_preset"] = payload["stylePreset"]
    payload["stylePresetId"] = (
        payload.get("stylePresetId")
        or settings.get("stylePresetId")
        or settings.get("style_preset_id")
        or (payload.get("backendMetadata") or {}).get("style_preset_id")
    )
    payload["stylePresetName"] = (
        payload.get("stylePresetName")
        or settings.get("stylePresetName")
        or settings.get("style_preset_name")
        or (payload.get("backendMetadata") or {}).get("style_preset_name")
    )
    payload["styleCategory"] = (
        payload.get("styleCategory")
        or settings.get("styleCategory")
        or settings.get("style_category")
        or (payload.get("backendMetadata") or {}).get("style_category")
    )
    if payload.get("identitySafetyMode") is None:
        payload["identitySafetyMode"] = settings.get("identitySafetyMode")
    if payload.get("experimentalMode") is None:
        payload["experimentalMode"] = settings.get("experimentalMode")
    _sync_generation_metadata_fields(payload, settings)
    payload["staffRating"] = _get_staff_rating(payload)
    payload["rating"] = payload["staffRating"]
    payload["autoReview"] = _normalize_auto_review_payload(payload.get("autoReview"))
    payload["autoRating"] = int(_safe_int(payload.get("autoRating")) or payload["autoReview"].get("autoRating") or 0)
    payload["comparisonScores"] = payload.get("comparisonScores") if isinstance(payload.get("comparisonScores"), dict) else {}
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
        "outputPath": result_item.get("outputPath"),
        "outputUrl": result_item.get("outputUrl"),
        "preset": result_item.get("preset"),
        "promptMode": result_item.get("promptMode"),
        "promptType": result_item.get("promptType"),
        "prompt": result_item.get("prompt"),
        "negativePrompt": result_item.get("negativePrompt"),
        "generationSettings": result_item.get("generationSettings"),
        "detection": result_item.get("detection"),
        "autoRating": result_item.get("autoRating"),
        "autoReview": _normalize_auto_review_payload(result_item.get("autoReview")),
        "rating": result_item.get("rating"),
        "staffRating": result_item.get("staffRating"),
        "feedbackTags": result_item.get("feedbackTags", []),
        "feedbackNote": result_item.get("feedbackNote", ""),
        "ratedAt": result_item.get("ratedAt"),
        "comparisonScores": _normalize_comparison_scores(result_item.get("comparisonScores")),
        "createdAt": result_item.get("createdAt"),
        "generationEngine": result_item.get("generationEngine"),
        "generationMode": result_item.get("generationMode"),
        "styleId": result_item.get("styleId"),
        "styleLabel": result_item.get("styleLabel"),
        "styleRiskLevel": result_item.get("styleRiskLevel"),
        "mode": result_item.get("mode"),
        "aiArtVentureEnabled": result_item.get("aiArtVentureEnabled"),
        "randomStyleEnabled": result_item.get("randomStyleEnabled"),
        "randomThemeEnabled": result_item.get("randomThemeEnabled"),
        "selectedStyleId": result_item.get("selectedStyleId"),
        "selectedThemeId": result_item.get("selectedThemeId"),
        "customTheme": result_item.get("customTheme"),
        "finalStyleId": result_item.get("finalStyleId"),
        "finalStyleName": result_item.get("finalStyleName"),
        "finalThemeId": result_item.get("finalThemeId"),
        "finalThemeName": result_item.get("finalThemeName"),
        "checkpoint": result_item.get("checkpoint"),
        "controlNetModel": result_item.get("controlNetModel"),
        "controlNetModule": result_item.get("controlNetModule"),
        "denoisingStrength": result_item.get("denoisingStrength"),
        "controlWeight": result_item.get("controlWeight"),
        "softEdgeWeight": result_item.get("softEdgeWeight"),
        "controlMode": result_item.get("controlMode"),
        "cfgScale": result_item.get("cfgScale"),
        "steps": result_item.get("steps"),
        "samplerName": result_item.get("samplerName"),
        "backgroundType": result_item.get("backgroundType"),
        "whiteBackgroundRatio": result_item.get("whiteBackgroundRatio"),
        "presetAnimal": result_item.get("presetAnimal"),
        "speciesPromptUsed": result_item.get("speciesPromptUsed"),
        "finalDenoisingStrength": result_item.get("finalDenoisingStrength"),
        "finalControlWeight": result_item.get("finalControlWeight"),
        "finalPrompt": result_item.get("finalPrompt"),
        "promptUsed": result_item.get("promptUsed"),
        "negativePromptUsed": result_item.get("negativePromptUsed"),
        "identitySafetyMode": result_item.get("identitySafetyMode"),
        "experimentalMode": result_item.get("experimentalMode"),
        "ipAdapterEnabled": result_item.get("ipAdapterEnabled"),
        "ipAdapterType": result_item.get("ipAdapterType"),
        "ipAdapterWarning": result_item.get("ipAdapterWarning"),
        "ipAdapterWeight": result_item.get("ipAdapterWeight"),
        "identityGuidanceUsed": result_item.get("identityGuidanceUsed"),
        "identityTarget": result_item.get("identityTarget"),
        "basedOnPreset": result_item.get("basedOnPreset"),
        "loraUsed": result_item.get("loraUsed"),
        "loraName": result_item.get("loraName"),
        "backendPromptId": result_item.get("backendPromptId"),
        "backendMetadata": result_item.get("backendMetadata"),
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
    generation_mode: str,
    style_id: str,
    preset_animal: Optional[str] = None,
) -> PresetSettings:
    control_weight = float(base_preset.control_weight)
    denoising = float(base_preset.denoising_strength)
    cfg_scale = float(base_preset.cfg_scale)
    control_mode = str(base_preset.control_mode or "Balanced")
    if generation_mode == GENERATION_MODE_AI_ART_VENTURE:
        control_mode = "Balanced"
    prompt = _apply_mode_style_prompt(str(base_preset.prompt), generation_mode, style_id)
    negative_prompt = str(base_preset.negative_prompt)

    identity_problem_tags = {
        "person_changed",
        "person_unrecognizable",
        "face_identity_changed",
        "gender_changed",
        "clothing_changed",
        "shirt_changed",
        "outfit_changed",
    }
    creation_problem_tags = {
        "artwork_missing",
        "artwork_changed",
        "creation_unrecognizable",
        "object_missing",
        "object_changed",
    }
    style_strength_problem_tags = {"same_as_input", "style_too_weak"}
    background_problem_tags = {"background_not_changed", "background_wrong"}
    drawing_lively_problem_tags = {
        "not_lively_enough",
        "too_unchanged",
    }

    cleaned_problem_tags: List[str] = []
    problem_tag_keys: set[str] = set()
    for raw_tag in problem_tags:
        tag_text = str(raw_tag or "").strip()
        if tag_text:
            cleaned_problem_tags.append(tag_text)
            problem_tag_keys.add(tag_text.lower())

    drawing_lively_adjustment_applied = (
        generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK
        and bool(problem_tag_keys & drawing_lively_problem_tags)
    )
    drawing_species_issue = (
        generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK
        and bool(problem_tag_keys & DRAWING_TO_ARTWORK_SPECIES_REGENERATE_TAGS)
    )

    normalized_preset_animal = _normalize_preset_animal(preset_animal)
    if drawing_species_issue:
        denoising -= 0.06
        control_weight += 0.08
        control_mode = "Balanced"
        prompt = _append_prompt_sentence(prompt, DRAWING_TO_ARTWORK_STRONG_SPECIES_APPEND)
        if normalized_preset_animal:
            prompt = _append_prompt_sentence(
                prompt,
                DRAWING_TO_ARTWORK_SPECIES_OVERRIDES.get(normalized_preset_animal, ""),
            )
    if drawing_lively_adjustment_applied:
        denoising += 0.05
        control_weight -= 0.04
        prompt = _append_prompt_sentence(prompt, REGENERATE_RICH_BACKGROUND_PROMPT)
        prompt = _append_prompt_sentence(prompt, REGENERATE_DRAWING_LIVELY_PROMPT)

    for tag in cleaned_problem_tags:
        tag_key = tag.lower()
        if drawing_lively_adjustment_applied and tag_key in drawing_lively_problem_tags:
            continue
        if tag in {"wrong_generation", "wrong_subject"}:
            prompt = _append_prompt_sentence(prompt, REGENERATE_WRONG_GENERATION_PROMPT)
            prompt = _apply_mode_style_prompt(prompt, generation_mode, style_id)
        elif tag in style_strength_problem_tags:
            denoising += 0.04
            control_weight -= 0.04
            if generation_mode == GENERATION_MODE_AI_ART_VENTURE:
                prompt = _append_prompt_sentence(
                    prompt,
                    "Increase stylization strength while keeping the person and creation recognizable.",
                )
        elif tag in {"too_close_to_drawing"}:
            denoising += 0.08
            control_weight -= 0.05
        elif tag in {"person_missing", "face_changed"}:
            denoising -= 0.08
            prompt = _append_prompt_sentence(prompt, REGENERATE_PRESERVE_PERSON_PROMPT)
        elif tag in identity_problem_tags:
            denoising -= 0.06
            control_weight += 0.08
            control_mode = "Balanced"
            prompt = _append_prompt_sentence(
                prompt,
                "Preserve the same recognizable person identity, hairstyle, clothing color, shirt type, pose, and facial traits.",
            )
        elif tag in creation_problem_tags:
            denoising -= 0.05
            control_weight += 0.08
            prompt = _append_prompt_sentence(
                prompt,
                "Preserve the exact artwork or creation in shape, content, visibility, and position.",
            )
        elif tag == "main_object_missing":
            denoising -= 0.08
            control_weight += 0.08
            prompt = _append_prompt_sentence(prompt, REGENERATE_PRESERVE_ARTWORK_PROMPT)
        elif tag in {"not_lively_enough", "too_unchanged", "too_empty"}:
            denoising += 0.08
            cfg_scale += 0.5
            prompt = _append_prompt_sentence(prompt, REGENERATE_RICH_BACKGROUND_PROMPT)
        elif tag in background_problem_tags:
            prompt = _append_prompt_sentence(
                prompt,
                "Replace the plain or empty background with a rich style-matching environment while preserving the person and creation.",
            )
        elif tag == "background_too_plain":
            prompt = _append_prompt_sentence(prompt, REGENERATE_RICH_BACKGROUND_PROMPT)
        elif tag == "too_messy":
            denoising -= 0.05
            control_weight += 0.05
        elif tag in {"changed_too_much", "over_changed", "too_much_change"}:
            denoising -= 0.08
            control_weight += 0.08
        elif tag == "bad_face":
            denoising -= 0.05
            negative_prompt = _append_prompt_sentence(negative_prompt, REGENERATE_FACE_NEGATIVE)
        elif tag == "bad_hands":
            denoising -= 0.05
            negative_prompt = _append_prompt_sentence(negative_prompt, REGENERATE_HAND_NEGATIVE)
        elif tag in {"too_dark", "bad_colors", "background_wrong"}:
            cfg_scale += 0.5
            prompt = _append_prompt_sentence(prompt, REGENERATE_BRIGHT_PROMPT)
        elif tag == "style_wrong":
            prompt = _apply_mode_style_prompt(prompt, generation_mode, style_id)
            prompt = _append_prompt_sentence(prompt, "strictly follow selected styleId style prompt")
        elif tag in {"composition_wrong", "wrong_composition"}:
            denoising -= 0.05
            control_weight += 0.05
            prompt = _append_prompt_sentence(prompt, "preserve exact composition and object positions")
        elif tag in {"blurry", "low_quality"}:
            cfg_scale += 0.3
        elif tag == "text_or_watermark":
            negative_prompt = _append_prompt_sentence(negative_prompt, "text, watermark, logo")
        elif tag in {"creepy", "scary_or_creepy"}:
            negative_prompt = _append_prompt_sentence(negative_prompt, "creepy, scary, horror")

    if generation_mode == GENERATION_MODE_AI_ART_VENTURE:
        denoising = max(AI_ART_VENTURE_DENOISE_MIN, min(AI_ART_VENTURE_DENOISE_MAX, denoising))
        control_weight = max(AI_ART_VENTURE_CONTROL_WEIGHT_MIN, min(AI_ART_VENTURE_CONTROL_WEIGHT_MAX, control_weight))
        cfg_scale = max(AI_ART_VENTURE_CFG_MIN, min(AI_ART_VENTURE_CFG_MAX, cfg_scale))
        if not control_mode:
            control_mode = "Balanced"
    elif generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK:
        denoising = max(DRAWING_REGENERATE_DENOISE_MIN, min(DRAWING_REGENERATE_DENOISE_MAX, denoising))
        control_weight = max(
            DRAWING_REGENERATE_CONTROL_WEIGHT_MIN,
            min(DRAWING_REGENERATE_CONTROL_WEIGHT_MAX, control_weight),
        )
        cfg_scale = max(DRAWING_REGENERATE_CFG_MIN, min(DRAWING_REGENERATE_CFG_MAX, cfg_scale))
    else:
        denoising = max(0.2, min(0.9, denoising))
        control_weight = max(0.35, min(1.0, control_weight))
        cfg_scale = max(5.0, min(12.0, cfg_scale))

    return PresetSettings(
        name=base_preset.name,
        control_weight=control_weight,
        denoising_strength=denoising,
        control_mode=control_mode or base_preset.control_mode,
        cfg_scale=cfg_scale,
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
        await _update_wonderpark_submission_from_job(job, status="processing")
        await _broadcast_queue_updated()

        try:
            refreshed = await run_in_threadpool(queue_store.get_job, job_id)
            if refreshed and bool(refreshed.get("cancelRequested")):
                cancelled = await _mark_job_cancelled(job_id, "Cancelled before processing started.")
                await _update_wonderpark_submission_from_job(
                    cancelled,
                    status="failed",
                    error="Cancelled before processing started.",
                )
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

            resolved_mode, resolved_style = _resolve_mode_and_style_ids(
                job.get("generationMode"),
                job.get("styleId"),
            )
            extra_fields = {
                "originalJobId": job.get("originalJobId") or job_id,
                "regenerationOf": job.get("regenerationOf"),
                "version": int(job.get("version") or 1),
                "generationEngine": job.get("generationEngine"),
                "generationMode": resolved_mode,
                "styleId": resolved_style,
                "styleLabel": job.get("styleLabel") or _resolve_style_label(resolved_mode, resolved_style),
                "source": _normalize_source(job.get("source")),
                "problemTags": list(job.get("problemTags") or []),
            }
            for metadata_key in AI_ART_VENTURE_EXTRA_METADATA_KEYS:
                if metadata_key in job:
                    extra_fields[metadata_key] = job.get(metadata_key)
            for metadata_key in DRAWING_TO_ARTWORK_EXTRA_METADATA_KEYS:
                if metadata_key in job:
                    extra_fields[metadata_key] = job.get(metadata_key)

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
                output_path_override=job.get("outputPath"),
            )

            refreshed = await run_in_threadpool(queue_store.get_job, job_id)
            if refreshed and bool(refreshed.get("cancelRequested")):
                await run_in_threadpool(_delete_local_gallery_file, result_item.get("outputUrl"))
                cancelled = await _mark_job_cancelled(job_id, "Cancelled during processing.")
                await _update_wonderpark_submission_from_job(
                    cancelled,
                    status="failed",
                    error="Cancelled during processing.",
                )
                await ws_manager.broadcast({"type": "job_cancelled", "job": _job_to_public_payload(cancelled)})
                await _broadcast_queue_updated()
                if bool(refreshed.get("deleteRequested")):
                    await _delete_job_artifacts(job_id)
                continue

            if _normalize_source(job.get("source")) == "public_wonderpark":
                result_item["hidden"] = False
                result_item["hiddenAt"] = None
                result_item["showcaseVisible"] = True
                result_item["showcaseStatus"] = "approved"
                result_item["status"] = "approved"
                result_item["approvedAt"] = datetime.now(timezone.utc).isoformat()
                result_item["approvedBy"] = "system_auto"

            await run_in_threadpool(gallery_store.add_item, result_item)
            completed = await _update_job_with_completed_result(job, result_item)
            await _update_wonderpark_submission_from_job(
                completed,
                status="completed",
                generated_image_url=str(result_item.get("outputUrl") or ""),
            )
            await ws_manager.broadcast(_build_generation_complete_event(result_item))
            await ws_manager.broadcast({"type": "job_completed", "job": _job_to_public_payload(completed)})
            await _broadcast_queue_updated()

            if bool(completed.get("deleteRequested")):
                await _delete_job_artifacts(job_id)
        except Exception as exc:
            logger.exception("Queue processing failed for job=%s", job_id)
            failed = await _mark_job_failed(job_id, str(exc))
            await _update_wonderpark_submission_from_job(failed, status="failed", error=str(exc))
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
        for job in recovered:
            await _update_wonderpark_submission_from_job(
                job,
                status="queued",
                error="Recovered after backend restart.",
            )
    await _broadcast_queue_updated()


@app.on_event("startup")
async def on_startup() -> None:
    global queue_worker_task
    global queue_worker_stop

    _initialize_api_key_state()
    ensure_ai_art_venture_styles_file()
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
    from service_manager import autostart_services

    local_ai_autostart = await run_in_threadpool(autostart_services)
    logger.info("Local AI autostart results: %s", local_ai_autostart)
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
    backend_status = await run_in_threadpool(_check_generation_backend_health)
    active_engine = _normalize_generation_engine(backend_status.get("mode"))
    backend_reachable = bool(backend_status.get("reachable"))
    status: Dict[str, Any] = {
        "backend": "ok" if backend_reachable else "degraded",
        "generationEngine": active_engine,
        "generationBackend": backend_status,
        "stableDiffusion": {"reachable": False},
        "comfyui": {"reachable": False},
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

    if active_engine == "stable_diffusion":
        status["stableDiffusion"] = {
            "reachable": backend_reachable,
        }
        if backend_status.get("modelCount") is not None:
            status["stableDiffusion"]["modelCount"] = backend_status.get("modelCount")
        if not backend_reachable and backend_status.get("error"):
            status["stableDiffusion"]["error"] = str(backend_status.get("error"))
    else:
        status["comfyui"] = {
            "reachable": backend_reachable,
        }
        if not backend_reachable and backend_status.get("error"):
            status["comfyui"]["error"] = str(backend_status.get("error"))
        if backend_status.get("system") is not None:
            status["comfyui"]["system"] = backend_status.get("system")
        # Keep this legacy key for older frontend/API clients.
        status["stableDiffusion"] = {
            "reachable": backend_reachable,
        }
        if not backend_reachable and backend_status.get("error"):
            status["stableDiffusion"]["error"] = str(backend_status.get("error"))

    return status


@app.get("/public/wonderpark")
async def public_wonderpark_page() -> FileResponse:
    _wonderpark_feature_guard()
    return FileResponse(STATIC_DIR / "public_wonderpark.html")


@app.get("/public/wonderpark/template")
async def public_wonderpark_template_page() -> FileResponse:
    _wonderpark_feature_guard()
    return FileResponse(STATIC_DIR / "wonderpark_template.html")


@app.get("/public/wonderpark/{animal}")
async def public_wonderpark_page_with_animal(animal: str) -> FileResponse:
    _wonderpark_feature_guard()
    normalized = _normalize_preset_animal(animal, allow_unknown=True)
    if not normalized or normalized not in CUSTOMER_ANIMAL_ROUTE_VALUES:
        raise HTTPException(status_code=404, detail="Page not found.")
    return FileResponse(STATIC_DIR / "public_wonderpark.html")


@app.get("/public/wonderpark/files/{kind}/{filename}")
async def public_wonderpark_file(kind: str, filename: str) -> FileResponse:
    _wonderpark_feature_guard()
    safe_filename = Path(str(filename or "")).name
    if safe_filename != str(filename or "") or not safe_filename:
        raise HTTPException(status_code=404, detail="File not found.")
    kind_key = str(kind or "").strip().lower()
    base_map = {
        "original": WONDERPARK_ORIGINALS_DIR,
        "processed": WONDERPARK_PROCESSED_DIR,
        "thumbnail": WONDERPARK_THUMBNAILS_DIR,
    }
    base_dir = base_map.get(kind_key)
    if base_dir is None:
        raise HTTPException(status_code=404, detail="File not found.")
    candidate = (base_dir / safe_filename).resolve()
    base_resolved = base_dir.resolve()
    if not (candidate == base_resolved or base_resolved in candidate.parents):
        raise HTTPException(status_code=404, detail="File not found.")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(candidate)


@app.get("/api/public/wonderpark/config")
async def public_wonderpark_config() -> Dict[str, Any]:
    backend_status = await run_in_threadpool(_check_generation_backend_health, "comfyui")
    active_engine = _normalize_generation_engine(backend_status.get("mode"))
    reachable = bool(backend_status.get("reachable"))
    sd_status: Dict[str, Any] = {"reachable": reachable}
    if active_engine == "stable_diffusion" and backend_status.get("modelCount") is not None:
        sd_status["modelCount"] = backend_status.get("modelCount")
    if not reachable and backend_status.get("error"):
        sd_status["error"] = str(backend_status.get("error"))

    return {
        "enabled": bool(WONDERPARK_PUBLIC_UPLOAD_ENABLED),
        "generationEngine": active_engine,
        "generationBackend": backend_status,
        "defaultStylePreset": "random",
        "route": "/public/wonderpark",
        "supportedAnimals": list(CUSTOMER_ANIMAL_ROUTE_VALUES),
        "animalRouteQuery": "/public/wonderpark?animal={animal}",
        "animalRoutePath": "/public/wonderpark/{animal}",
        "maxUploadBytes": int(WONDERPARK_MAX_UPLOAD_BYTES),
        "allowedExtensions": sorted(list(WONDERPARK_ALLOWED_EXTENSIONS)),
        "allowedMimeTypes": sorted(list(WONDERPARK_ALLOWED_MIME_TYPES)),
        "minRecommendedWidth": int(WONDERPARK_MIN_RECOMMENDED_WIDTH),
        "minRecommendedHeight": int(WONDERPARK_MIN_RECOMMENDED_HEIGHT),
        "rateLimit": {
            "maxUploads": int(WONDERPARK_RATE_LIMIT_MAX_PER_IP),
            "windowSeconds": int(WONDERPARK_RATE_LIMIT_WINDOW_SECONDS),
        },
        "stableDiffusion": sd_status,
    }


@app.post("/api/public/wonderpark/upload")
async def public_wonderpark_upload(
    request: Request,
    customerName: str = Form(""),
    paperTemplateId: Optional[str] = Form(None),
    presetAnimal: Optional[str] = Form(None),
    image: UploadFile = File(...),
    originalImage: Optional[UploadFile] = File(None),
    animal: Optional[str] = Query(None),
    absolute: bool = Query(False),
) -> Dict[str, Any]:
    _wonderpark_feature_guard()
    await _ensure_wonderpark_generation_ready()

    source_ip = _wonderpark_client_ip(request)
    customer_name = _sanitize_wonderpark_customer_name(customerName)
    paper_template_id = _safe_form_text(paperTemplateId, max_len=120) or None
    recent_count = await run_in_threadpool(
        wonderpark_store.count_recent_by_ip,
        source_ip,
        WONDERPARK_RATE_LIMIT_WINDOW_SECONDS,
    )
    if recent_count >= WONDERPARK_RATE_LIMIT_MAX_PER_IP:
        raise HTTPException(
            status_code=429,
            detail="Too many uploads. Please wait a few minutes and try again.",
        )

    image_mime = _safe_mime(image)
    image_ext = Path(str(image.filename or "")).suffix.lower()
    if image_mime not in WONDERPARK_ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use JPG, PNG, or WEBP.")
    if image_ext and image_ext not in WONDERPARK_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file extension. Use JPG, PNG, or WEBP.")

    try:
        processed_upload_bytes = await image.read()
    finally:
        await image.close()
    if not processed_upload_bytes:
        raise HTTPException(status_code=400, detail="Upload image is empty.")
    if len(processed_upload_bytes) > WONDERPARK_MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Upload too large. Max file size is {WONDERPARK_MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    original_bytes = processed_upload_bytes
    original_mime = image_mime
    original_filename = _safe_wonderpark_filename(image.filename)
    if originalImage is not None:
        original_mime_candidate = _safe_mime(originalImage)
        if original_mime_candidate:
            original_mime = original_mime_candidate
        try:
            candidate = await originalImage.read()
        finally:
            await originalImage.close()
        if candidate:
            if len(candidate) > WONDERPARK_MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Original image too large. Max file size is {WONDERPARK_MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                )
            original_bytes = candidate
            original_filename = _safe_wonderpark_filename(originalImage.filename or original_filename)

    if original_mime not in WONDERPARK_ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Original file type is not supported.")

    resolved_preset_animal, resolved_preset_animal_source = _resolve_customer_preset_animal(
        upload_query_animal=animal,
        upload_path_animal=None,
        referrer_url=request.headers.get("referer"),
        paper_template_id=paper_template_id,
        filename=original_filename or image.filename,
        form_preset_animal=presetAnimal,
    )
    if resolved_preset_animal == DRAWING_TO_ARTWORK_PRESET_ANIMAL_UNKNOWN:
        logger.warning(
            "Wonderpark upload resolved presetAnimal=unknown (template=%s filename=%s source=%s).",
            paper_template_id or "-",
            original_filename or "-",
            resolved_preset_animal_source,
        )

    try:
        processed_bytes = _prepare_wonderpark_image_bytes(
            processed_upload_bytes,
            max_dimension=WONDERPARK_MAX_PROCESSING_DIMENSION,
        )
        quality = _compute_wonderpark_quality_signals(processed_bytes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image file: {exc}") from exc

    image_hash = hashlib.sha256(original_bytes).hexdigest()
    duplicate = await run_in_threadpool(
        wonderpark_store.find_recent_duplicate,
        source_ip=source_ip,
        image_hash=image_hash,
        window_seconds=WONDERPARK_DUPLICATE_WINDOW_SECONDS,
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Duplicate artwork detected. Please wait before submitting the same scan again.",
                "submissionId": str(duplicate.get("submissionId") or ""),
            },
        )

    submission_id = f"wp_{uuid.uuid4().hex[:18]}"
    stored = _store_wonderpark_images(
        submission_id=submission_id,
        original_bytes=original_bytes,
        original_mime=original_mime,
        processed_bytes=processed_bytes,
    )
    rate_limit_info = _safe_rate_limit_info(
        remaining=(WONDERPARK_RATE_LIMIT_MAX_PER_IP - (recent_count + 1)),
        limit=WONDERPARK_RATE_LIMIT_MAX_PER_IP,
        window_seconds=WONDERPARK_RATE_LIMIT_WINDOW_SECONDS,
    )
    created_row = await run_in_threadpool(
        wonderpark_store.create_submission,
        {
            "submissionId": submission_id,
            "customerName": customer_name,
            "uploadedImageUrl": stored["processedUrl"],
            "thumbnailUrl": stored["thumbnailUrl"],
            "originalImageUrl": stored["originalUrl"],
            "originalFilename": original_filename,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "processingStatus": "pending",
            "paperTemplateId": paper_template_id,
            "presetAnimal": resolved_preset_animal,
            "presetAnimalSource": resolved_preset_animal_source,
            "queueJobId": "",
            "generatedImageUrl": "",
            "error": "",
            "sourceIp": source_ip,
            "imageHash": image_hash,
            "mimeType": original_mime,
            "fileSizeBytes": len(original_bytes),
            "imageWidth": int(quality.get("imageWidth") or 0),
            "imageHeight": int(quality.get("imageHeight") or 0),
            "rateLimitInfo": rate_limit_info,
            "retryCount": 0,
            "processingInputPath": stored["processedPath"],
            "originalStoragePath": stored["originalPath"],
            "thumbnailStoragePath": stored["thumbnailPath"],
            "sourceInputUrl": stored["processedUrl"],
            "sourceInputPath": stored["processedPath"],
            "sourceUploadId": submission_id,
            "parentSessionId": submission_id,
            "regeneratedFromJobId": "",
            "generationAttempt": 1,
            "regenerateCount": 0,
            "resultStatus": "pending",
            "showcaseVisible": False,
            "approvedAt": None,
            "approvedBy": "",
            "approvedJobId": "",
            "approvedImageUrl": "",
        },
    )

    warnings: List[str] = []
    if bool(quality.get("lowResolution")):
        warnings.append("Image resolution looks low. A clearer scan gives better AI results.")
    if bool(quality.get("veryDark")):
        warnings.append("Image appears very dark. Please use brighter lighting or a scanner.")
    if bool(quality.get("nearBlank")):
        warnings.append("Image looks blank or nearly blank. Please recheck before upload.")

    try:
        queued_row = await _enqueue_wonderpark_submission(submission_id)
    except Exception as exc:
        logger.exception("Wonderpark submission enqueue failed: %s", submission_id)
        queued_row = await run_in_threadpool(
            wonderpark_store.update_submission,
            submission_id,
            {"processingStatus": "failed", "error": str(exc)},
        )

    return {
        "ok": True,
        "message": "Your artwork has been submitted successfully.",
        "submission": _wonderpark_to_api_payload(queued_row or created_row, request, bool(absolute)),
        "warnings": warnings,
    }


@app.get("/api/public/wonderpark/submissions/{submission_id}")
async def public_wonderpark_submission_status(
    request: Request,
    submission_id: str,
    absolute: bool = Query(False),
) -> Dict[str, Any]:
    _wonderpark_feature_guard()
    row = await run_in_threadpool(wonderpark_store.get_submission, submission_id)
    if not row:
        raise HTTPException(status_code=404, detail="Submission not found.")
    return {
        "ok": True,
        "submission": _wonderpark_to_api_payload(row, request, bool(absolute)),
    }


@app.post("/api/public/wonderpark/submissions/{submission_id}/regenerate")
async def public_wonderpark_regenerate_submission(
    request: Request,
    submission_id: str,
    absolute: bool = Query(False),
) -> Dict[str, Any]:
    _wonderpark_feature_guard()
    await _ensure_wonderpark_generation_ready()

    row = await run_in_threadpool(wonderpark_store.get_submission, submission_id)
    if not row:
        raise HTTPException(status_code=404, detail="Submission not found.")

    processing_status = str(row.get("processingStatus") or "").strip().lower()
    if processing_status in {"pending", "queued", "processing"}:
        raise HTTPException(status_code=409, detail="Artwork is still generating. Please wait.")

    result_status = str(row.get("resultStatus") or "").strip().lower()
    if result_status == "approved" or bool(row.get("showcaseVisible", False)):
        raise HTTPException(
            status_code=409,
            detail="Artwork is already approved for showcase. Upload a new artwork for another result.",
        )

    generation_attempt = max(1, int(row.get("generationAttempt") or 1))
    regenerate_count = max(0, int(row.get("regenerateCount") or 0))

    await run_in_threadpool(
        wonderpark_store.update_submission,
        submission_id,
        {
            "processingStatus": "pending",
            "resultStatus": "pending",
            "showcaseVisible": False,
            "error": "",
            "approvedAt": None,
            "approvedBy": "",
            "approvedJobId": "",
            "approvedImageUrl": "",
            "generationAttempt": generation_attempt + 1,
            "regenerateCount": regenerate_count + 1,
        },
    )

    try:
        queued_row = await _enqueue_wonderpark_submission(submission_id)
    except Exception as exc:
        logger.exception("Wonderpark submission regenerate failed: %s", submission_id)
        failed_row = await run_in_threadpool(
            wonderpark_store.update_submission,
            submission_id,
            {
                "processingStatus": "failed",
                "resultStatus": "failed",
                "error": str(exc),
            },
        )
        return {
            "ok": False,
            "message": "Regeneration failed to start.",
            "submission": _wonderpark_to_api_payload(failed_row, request, bool(absolute)),
        }

    return {
        "ok": True,
        "message": "Regenerating your artwork...",
        "submission": _wonderpark_to_api_payload(queued_row, request, bool(absolute)),
    }


@app.post("/api/public/wonderpark/submissions/{submission_id}/approve")
async def public_wonderpark_approve_submission(
    request: Request,
    submission_id: str,
    absolute: bool = Query(False),
) -> Dict[str, Any]:
    _wonderpark_feature_guard()
    row = await run_in_threadpool(wonderpark_store.get_submission, submission_id)
    if not row:
        raise HTTPException(status_code=404, detail="Submission not found.")

    processing_status = str(row.get("processingStatus") or "").strip().lower()
    generated_url = str(row.get("generatedImageUrl") or row.get("latestOutputUrl") or "").strip()
    if processing_status != "completed" or not generated_url:
        raise HTTPException(status_code=409, detail="Artwork is not ready for showcase approval yet.")

    result_status = str(row.get("resultStatus") or "").strip().lower()
    already_visible = bool(row.get("showcaseVisible", False))
    if result_status == "approved" and already_visible:
        return {
            "ok": True,
            "message": "Already approved for showcase.",
            "submission": _wonderpark_to_api_payload(row, request, bool(absolute)),
        }

    latest_job_id = str(row.get("latestJobId") or row.get("queueJobId") or "").strip()
    if not latest_job_id:
        raise HTTPException(status_code=409, detail="Missing generated job reference.")

    item = await run_in_threadpool(gallery_store.get_item, latest_job_id)
    if not item:
        raise HTTPException(status_code=404, detail="Generated artwork not found.")

    updated_gallery_item = await run_in_threadpool(
        gallery_store.update_item_fields,
        latest_job_id,
        {
            "hidden": False,
            "hiddenAt": None,
            "showcaseVisible": True,
            "showcaseStatus": "approved",
            "status": "approved",
            "approvedAt": datetime.now(timezone.utc).isoformat(),
            "approvedBy": "customer",
        },
    )
    await ws_manager.broadcast({"type": "gallery_item_updated", "item": updated_gallery_item})

    approved_at = datetime.now(timezone.utc).isoformat()
    updated_row = await run_in_threadpool(
        wonderpark_store.update_submission,
        submission_id,
        {
            "resultStatus": "approved",
            "showcaseVisible": True,
            "approvedAt": approved_at,
            "approvedBy": "customer",
            "approvedJobId": latest_job_id,
            "approvedImageUrl": str(updated_gallery_item.get("outputUrl") or generated_url),
            "generatedImageUrl": str(updated_gallery_item.get("outputUrl") or generated_url),
            "latestOutputUrl": str(updated_gallery_item.get("outputUrl") or generated_url),
        },
    )
    return {
        "ok": True,
        "message": "Thank you! Your artwork has been added to the showcase.",
        "submission": _wonderpark_to_api_payload(updated_row, request, bool(absolute)),
    }


@app.get("/admin/wonderpark")
async def admin_wonderpark_page(
    request: Request,
    apiKey: Optional[str] = Query(None),
    x_api_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER),
) -> FileResponse:
    _require_admin_api_access(request, x_api_key=x_api_key, query_api_key=apiKey)
    return FileResponse(STATIC_DIR / "wonderpark_admin.html")


@app.get("/api/admin/wonderpark/submissions")
async def admin_wonderpark_submissions(
    request: Request,
    search: str = Query(""),
    status: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    absolute: bool = Query(False),
    apiKey: Optional[str] = Query(None),
    x_api_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER),
) -> Dict[str, Any]:
    _require_admin_api_access(request, x_api_key=x_api_key, query_api_key=apiKey)
    listing = await run_in_threadpool(
        wonderpark_store.list_submissions,
        search=search,
        status=status,
        limit=limit,
        offset=offset,
    )
    rows = listing.get("items", [])
    items = [_wonderpark_to_api_payload(row, request, bool(absolute)) for row in rows if isinstance(row, dict)]
    status_counts = await run_in_threadpool(wonderpark_store.status_counts)
    queue_snapshot = await run_in_threadpool(queue_store.queue_snapshot)
    queue_jobs = queue_snapshot.get("jobs", []) if isinstance(queue_snapshot.get("jobs"), list) else []
    wonderpark_queue = [
        job
        for job in queue_jobs
        if isinstance(job, dict) and _normalize_source(job.get("source")) == "public_wonderpark"
    ]
    return {
        "items": items,
        "total": int(listing.get("total") or 0),
        "statusCounts": status_counts,
        "queueMonitoring": {
            "globalQueueLength": int(queue_snapshot.get("queueLength") or 0),
            "wonderparkQueueLength": int(
                sum(1 for job in wonderpark_queue if str(job.get("status") or "") == "queued")
            ),
            "wonderparkProcessingCount": int(
                sum(1 for job in wonderpark_queue if str(job.get("status") or "") == "processing")
            ),
        },
    }


@app.get("/api/admin/wonderpark/submissions/{submission_id}/download")
async def admin_wonderpark_download_original(
    request: Request,
    submission_id: str,
    apiKey: Optional[str] = Query(None),
    x_api_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER),
) -> FileResponse:
    _require_admin_api_access(request, x_api_key=x_api_key, query_api_key=apiKey)
    row = await run_in_threadpool(wonderpark_store.get_submission, submission_id)
    if not row:
        raise HTTPException(status_code=404, detail="Submission not found.")
    source_path = Path(str(row.get("originalStoragePath") or ""))
    if not source_path.is_file():
        raise HTTPException(status_code=404, detail="Original file not found.")
    download_name = _safe_wonderpark_filename(row.get("originalFilename") or f"{submission_id}.png")
    return FileResponse(source_path, filename=download_name)


@app.post("/api/admin/wonderpark/submissions/{submission_id}/retry")
async def admin_wonderpark_retry_submission(
    request: Request,
    submission_id: str,
    apiKey: Optional[str] = Query(None),
    x_api_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER),
) -> Dict[str, Any]:
    _require_admin_api_access(request, x_api_key=x_api_key, query_api_key=apiKey)
    row = await run_in_threadpool(wonderpark_store.get_submission, submission_id)
    if not row:
        raise HTTPException(status_code=404, detail="Submission not found.")
    current_status = str(row.get("processingStatus") or "pending").strip().lower()
    if current_status in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="Submission is already in queue.")
    retry_count = int(row.get("retryCount") or 0) + 1
    await run_in_threadpool(
        wonderpark_store.update_submission,
        submission_id,
        {"processingStatus": "pending", "retryCount": retry_count, "error": ""},
    )
    try:
        updated = await _enqueue_wonderpark_submission(submission_id)
    except Exception as exc:
        updated = await run_in_threadpool(
            wonderpark_store.update_submission,
            submission_id,
            {"processingStatus": "failed", "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail=f"Failed to retry submission: {exc}") from exc
    return {"ok": True, "submission": _wonderpark_to_api_payload(updated, request, False)}


@app.delete("/api/admin/wonderpark/submissions/{submission_id}")
async def admin_wonderpark_delete_submission(
    request: Request,
    submission_id: str,
    apiKey: Optional[str] = Query(None),
    x_api_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER),
) -> Dict[str, Any]:
    _require_admin_api_access(request, x_api_key=x_api_key, query_api_key=apiKey)
    row = await run_in_threadpool(wonderpark_store.delete_submission, submission_id)
    if not row:
        raise HTTPException(status_code=404, detail="Submission not found.")
    queue_job_id = str(row.get("queueJobId") or "")
    if queue_job_id:
        job = await run_in_threadpool(queue_store.get_job, queue_job_id)
        if isinstance(job, dict):
            await run_in_threadpool(_remove_wonderpark_file, job.get("inputPath"))
            await run_in_threadpool(queue_store.delete_job, queue_job_id)
    await run_in_threadpool(_remove_wonderpark_file, row.get("originalStoragePath"))
    await run_in_threadpool(_remove_wonderpark_file, row.get("processingInputPath"))
    await run_in_threadpool(_remove_wonderpark_file, row.get("thumbnailStoragePath"))
    return {"deleted": True, "submission_id": submission_id}


@app.get("/comfy/staff")
async def comfy_staff_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "comfy_staff.html")


@app.get("/api/comfy/staff/status")
async def comfy_staff_status() -> Dict[str, Any]:
    return await run_in_threadpool(_build_comfy_staff_status_payload)


@app.get("/api/comfy/estimate")
async def comfy_estimate() -> Dict[str, Any]:
    return await run_in_threadpool(_build_comfyui_estimate_payload)


@app.get("/comfy/presets")
@app.get("/api/comfy/presets")
async def comfy_presets(category: Optional[str] = Query(None)) -> Dict[str, Any]:
    try:
        payload = await run_in_threadpool(load_comfy_prompt_presets)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    presets = payload.get("presets") if isinstance(payload.get("presets"), list) else []
    category_filter = str(category or "").strip().lower()
    if category_filter:
        presets = [
            row
            for row in presets
            if isinstance(row, dict) and str(row.get("category") or "").strip().lower() == category_filter
        ]
    return {
        "success": True,
        "negative_prompt": str(payload.get("negative_prompt") or ""),
        "presets": presets,
    }


@app.post("/api/comfy/staff/generate")
async def comfy_staff_generate(
    visitorName: str = Form(""),
    prompt: Optional[str] = Form(None),
    negativePrompt: Optional[str] = Form(None),
    stylePreset: Optional[str] = Form("random"),
    stylePresetSnake: Optional[str] = Form(default=None, alias="style_preset"),
    styleCategory: Optional[str] = Form(None),
    seed: Optional[str] = Form(None),
    steps: Optional[str] = Form(None),
    cfg: Optional[str] = Form(None),
    denoise: Optional[str] = Form(None),
    megapixels: Optional[str] = Form(None),
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image file.")

    extension = _resolve_extension(file)
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file extension.")

    steps_value = _parse_optional_int_form(steps)
    cfg_value = _parse_optional_float_form(cfg)
    denoise_value = _parse_optional_float_form(denoise)
    seed_value = _parse_optional_int_form(seed)
    megapixels_value = _parse_optional_float_form(megapixels)

    if steps_value is not None and steps_value <= 0:
        raise HTTPException(status_code=400, detail="steps must be greater than 0.")
    if cfg_value is not None and cfg_value <= 0:
        raise HTTPException(status_code=400, detail="cfg must be greater than 0.")
    if denoise_value is not None and denoise_value < 0:
        raise HTTPException(status_code=400, detail="denoise must be 0 or higher.")
    if megapixels_value is not None and megapixels_value <= 0:
        raise HTTPException(status_code=400, detail="megapixels must be greater than 0.")

    prompt_text = _safe_form_text(prompt, max_len=12000)
    negative_text = _safe_form_text(negativePrompt, max_len=12000)
    resolved_style_preset = _normalize_comfy_style_preset(stylePresetSnake or stylePreset)
    resolved_style_category = _safe_form_text(styleCategory, max_len=120).lower()

    try:
        preset_payload = await run_in_threadpool(load_comfy_prompt_presets)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    preset_rows = (
        preset_payload.get("presets")
        if isinstance(preset_payload.get("presets"), list)
        else []
    )
    if resolved_style_preset != "random":
        exists = any(
            isinstance(row, dict) and str(row.get("id") or "") == resolved_style_preset
            for row in preset_rows
        )
        if not exists:
            raise HTTPException(
                status_code=400,
                detail=f"Comfy style preset not found: {resolved_style_preset}",
            )
    elif resolved_style_category:
        has_category = any(
            isinstance(row, dict)
            and str(row.get("category") or "").strip().lower() == resolved_style_category
            for row in preset_rows
        )
        if not has_category:
            raise HTTPException(
                status_code=400,
                detail=f"No Comfy style presets found for category: {resolved_style_category}",
            )

    job_id = uuid.uuid4().hex
    input_path, _ = _job_paths(job_id)
    visitor_name = _normalize_visitor_name(visitorName)

    preset_override = _build_comfy_staff_preset(
        prompt=prompt_text,
        negative_prompt=negative_text,
        steps=steps_value,
        cfg=cfg_value,
        denoise=denoise_value,
    )

    comfy_estimate_payload = await run_in_threadpool(_build_comfyui_estimate_payload)
    estimated_seconds = int(
        comfy_estimate_payload.get("estimatedSecondsPerImage") or DEFAULT_GENERATION_ESTIMATE_SECONDS
    )
    if estimated_seconds <= 0:
        estimated_seconds = DEFAULT_GENERATION_ESTIMATE_SECONDS
    estimate_payload = {
        "estimatedSeconds": estimated_seconds,
        "minSeconds": estimated_seconds,
        "maxSeconds": estimated_seconds,
        "sampleCount": int(comfy_estimate_payload.get("sampleCount") or 0),
    }

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        await run_in_threadpool(_save_upload_as_png, content, input_path)
        queued_job = _build_queue_job(
            job_id=job_id,
            visitor_name=visitor_name,
            input_path=input_path,
            source="staff",
            estimate_payload=estimate_payload,
            generation_mode=GENERATION_MODE_DRAWING_TO_ARTWORK,
            style_id=DEFAULT_STYLE_ID,
            preset_override=preset_override,
            extra_fields={
                "generationEngine": "comfyui",
                "generationMode": GENERATION_MODE_DRAWING_TO_ARTWORK,
                "styleId": DEFAULT_STYLE_ID,
                "styleLabel": _resolve_style_label(GENERATION_MODE_DRAWING_TO_ARTWORK, DEFAULT_STYLE_ID),
                "stylePreset": resolved_style_preset,
                "style_preset": resolved_style_preset,
                "stylePresetCategory": resolved_style_category or None,
                "hidden": True,
                "showcaseVisible": False,
                "showcaseStatus": "staff_only",
            },
        )

        generation_settings = (
            dict(queued_job.get("generationSettings"))
            if isinstance(queued_job.get("generationSettings"), dict)
            else {}
        )
        generation_settings["generationEngine"] = "comfyui"
        generation_settings["style_preset"] = resolved_style_preset
        generation_settings["stylePreset"] = resolved_style_preset
        if resolved_style_category:
            generation_settings["styleCategory"] = resolved_style_category
        if seed_value is not None:
            generation_settings["seed"] = seed_value
        if steps_value is not None:
            generation_settings["steps"] = steps_value
        if cfg_value is not None:
            generation_settings["cfg"] = cfg_value
            generation_settings["cfgScale"] = cfg_value
        if denoise_value is not None:
            generation_settings["denoise"] = denoise_value
            generation_settings["denoisingStrength"] = denoise_value
        if megapixels_value is not None:
            generation_settings["megapixels"] = megapixels_value
        if prompt_text:
            generation_settings["promptUsed"] = prompt_text
        if negative_text:
            generation_settings["negativePromptUsed"] = negative_text

        queued_job["generationSettings"] = generation_settings
        queued_job["generationEngine"] = "comfyui"
        queued_job["prompt"] = prompt_text
        queued_job["negativePrompt"] = negative_text
        queued_job["promptUsed"] = prompt_text
        queued_job["negativePromptUsed"] = negative_text
        queued_job["stylePreset"] = resolved_style_preset
        queued_job["style_preset"] = resolved_style_preset
        if resolved_style_category:
            queued_job["stylePresetCategory"] = resolved_style_category
        queued_job["promptMode"] = preset_override.prompt_mode
        queued_job["promptType"] = preset_override.prompt_mode
        queued_job["steps"] = generation_settings.get("steps")
        queued_job["cfgScale"] = generation_settings.get("cfgScale")
        queued_job["denoisingStrength"] = generation_settings.get("denoisingStrength")

        queued = await _enqueue_job(queued_job)
        return await _build_queued_response(queued)
    except HTTPException as exc:
        await _broadcast_error(job_id, str(exc.detail))
        raise
    except Exception as exc:
        logger.exception("Comfy staff generation enqueue failed for job=%s", job_id)
        await _broadcast_error(job_id, f"Unexpected error: {exc}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc
    finally:
        await file.close()


@app.get("/staff")
async def staff_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "staff.html")


@app.get("/gallery")
async def gallery_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "gallery.html")


@app.get("/photo")
async def photo_page_query(jobId: Optional[str] = Query(None)) -> FileResponse:
    return FileResponse(STATIC_DIR / "photo.html")


@app.get("/photo/{jobId}")
async def photo_page(jobId: str) -> FileResponse:
    return FileResponse(STATIC_DIR / "photo.html")


@app.get("/showcase")
async def showcase_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "showcase.html")


@app.get("/publicgallery")
async def public_gallery_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "publicgallery.html")


@app.get("/gallery/items")
async def gallery_items(includeHidden: bool = False) -> Dict[str, Any]:
    items = await run_in_threadpool(gallery_store.list_items, bool(includeHidden))
    normalized_items: List[Dict[str, Any]] = []
    for item in items:
        updated_item = dict(item)
        updated_item["generationMode"], updated_item["styleId"] = _resolve_mode_and_style_ids(
            updated_item.get("generationMode"),
            updated_item.get("styleId"),
        )
        if not updated_item.get("styleLabel"):
            updated_item["styleLabel"] = _resolve_style_label(
                updated_item["generationMode"],
                updated_item["styleId"],
            )
        if (
            updated_item.get("generationMode") == GENERATION_MODE_AI_ART_VENTURE
            and not updated_item.get("styleRiskLevel")
        ):
            updated_item["styleRiskLevel"] = _resolve_ai_art_style_metadata(
                str(updated_item.get("styleId") or "")
            ).get("styleRiskLevel", "balanced")
        settings = (
            updated_item.get("generationSettings")
            if isinstance(updated_item.get("generationSettings"), dict)
            else {}
        )
        updated_item["checkpoint"] = updated_item.get("checkpoint") or settings.get("checkpoint")
        updated_item["controlNetModel"] = updated_item.get("controlNetModel") or settings.get("controlNetModel")
        updated_item["controlNetModule"] = updated_item.get("controlNetModule") or settings.get("controlNetModule")
        updated_item["denoisingStrength"] = updated_item.get("denoisingStrength") or settings.get("denoisingStrength")
        updated_item["controlWeight"] = updated_item.get("controlWeight") or settings.get("controlWeight")
        updated_item["controlMode"] = updated_item.get("controlMode") or settings.get("controlMode")
        updated_item["cfgScale"] = updated_item.get("cfgScale") or settings.get("cfgScale")
        updated_item["steps"] = updated_item.get("steps") or settings.get("steps")
        updated_item["backgroundType"] = updated_item.get("backgroundType") or settings.get("backgroundType")
        if updated_item.get("whiteBackgroundRatio") is None:
            updated_item["whiteBackgroundRatio"] = settings.get("whiteBackgroundRatio")
        updated_item["presetAnimal"] = _normalize_preset_animal(
            updated_item.get("presetAnimal") or settings.get("presetAnimal")
        )
        if updated_item.get("speciesPromptUsed") is None:
            updated_item["speciesPromptUsed"] = settings.get("speciesPromptUsed")
        if updated_item.get("finalDenoisingStrength") is None:
            updated_item["finalDenoisingStrength"] = settings.get("finalDenoisingStrength")
        if updated_item.get("finalControlWeight") is None:
            updated_item["finalControlWeight"] = settings.get("finalControlWeight")
        updated_item["finalPrompt"] = updated_item.get("finalPrompt") or settings.get("finalPrompt")
        updated_item["promptUsed"] = (
            updated_item.get("promptUsed")
            or settings.get("promptUsed")
            or updated_item.get("prompt")
        )
        updated_item["negativePromptUsed"] = (
            updated_item.get("negativePromptUsed")
            or settings.get("negativePromptUsed")
            or updated_item.get("negativePrompt")
        )
        if updated_item.get("identitySafetyMode") is None:
            updated_item["identitySafetyMode"] = settings.get("identitySafetyMode")
        if updated_item.get("experimentalMode") is None:
            updated_item["experimentalMode"] = settings.get("experimentalMode")
        _sync_generation_metadata_fields(updated_item, settings)
        updated_item["source"] = _normalize_source(updated_item.get("source"))
        updated_item["staffRating"] = _get_staff_rating(updated_item)
        updated_item["rating"] = updated_item["staffRating"]
        updated_item["autoReview"] = _normalize_auto_review_payload(updated_item.get("autoReview"))
        updated_item["autoRating"] = int(
            _safe_int(updated_item.get("autoRating"))
            or updated_item["autoReview"].get("autoRating")
            or 0
        )
        updated_item["comparisonScores"] = (
            updated_item.get("comparisonScores")
            if isinstance(updated_item.get("comparisonScores"), dict)
            else {}
        )
        normalized_items.append(updated_item)
    return {"items": normalized_items}


@app.get("/generation/estimate")
async def generation_estimate() -> Dict[str, int]:
    return await run_in_threadpool(
        gallery_store.get_duration_estimate,
        DEFAULT_GENERATION_ESTIMATE_SECONDS,
    )


@app.get("/settings/presets")
async def settings_presets() -> Dict[str, Any]:
    ai_art_venture = get_ai_art_venture_mode_payload_for_ui()
    ip_adapter_status: Dict[str, Any] = {
        "enabled": False,
        "type": "none",
        "module": "",
        "model": "",
        "warning": "IP-Adapter FaceID not detected. Face/person identity may change.",
    }
    try:
        detected_status = await run_in_threadpool(sd_generator.get_ai_art_venture_ip_adapter_status)
        if isinstance(detected_status, dict):
            ip_adapter_status.update(detected_status)
    except Exception as exc:
        logger.warning("Unable to detect IP-Adapter FaceID status for settings UI: %s", exc)

    base_settings = ai_art_venture.get("baseSettings")
    if isinstance(base_settings, dict):
        base_settings["ipAdapterFaceIdEnabled"] = bool(ip_adapter_status.get("enabled"))
        base_settings["ipAdapterFaceIdType"] = str(ip_adapter_status.get("type") or "none")
        base_settings["ipAdapterModule"] = str(
            ip_adapter_status.get("module")
            or base_settings.get("ipAdapterModule")
            or "ip-adapter_face_id_plus"
        )
        base_settings["ipAdapterModel"] = str(
            ip_adapter_status.get("model")
            or base_settings.get("ipAdapterModel")
            or "ip-adapter-faceid-plusv2_sd15"
        )
        base_settings["ipAdapterWarning"] = str(ip_adapter_status.get("warning") or "")
        base_settings["ipAdapterDetected"] = bool(ip_adapter_status.get("enabled"))
    ai_art_venture["ipAdapterStatus"] = ip_adapter_status

    generation_modes = [
        {
            "id": GENERATION_MODE_DRAWING_TO_ARTWORK,
            "label": GENERATION_MODE_LABELS[GENERATION_MODE_DRAWING_TO_ARTWORK],
            "supportsStyles": True,
            "defaultStyleId": "auto",
        },
        {
            "id": GENERATION_MODE_PERSON_HOLDING_ARTWORK,
            "label": GENERATION_MODE_LABELS[GENERATION_MODE_PERSON_HOLDING_ARTWORK],
            "supportsStyles": True,
            "defaultStyleId": "auto",
        },
        {
            "id": GENERATION_MODE_AI_ART_VENTURE,
            "label": GENERATION_MODE_LABELS[GENERATION_MODE_AI_ART_VENTURE],
            "supportsStyles": True,
            "defaultStyleId": str(ai_art_venture.get("defaultStyleId") or "pixar_3d"),
        },
    ]

    standard_style_options = [
        {"id": "auto", "label": "Auto"},
        {"id": "storybook", "label": "Storybook"},
        {"id": "storybook_plus", "label": "Storybook Plus"},
        {"id": "watercolor", "label": "Watercolor"},
        {"id": "cartoon", "label": "Cartoon"},
        {"id": "anime", "label": "Anime"},
        {"id": "pixel", "label": "Pixel"},
    ]

    return {
        "generationModes": generation_modes,
        "defaultGenerationMode": DEFAULT_GENERATION_MODE,
        "defaultStyleId": DEFAULT_STYLE_ID,
        "standardStyles": standard_style_options,
        "aiArtVenture": ai_art_venture,
    }


@app.post("/gallery/rate/{jobId}")
async def rate_gallery_item(jobId: str) -> Dict[str, Any]:
    raise HTTPException(
        status_code=410,
        detail="Manual rating is disabled. Ratings are now generated automatically.",
    )


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


@app.post("/gallery/clear")
async def clear_gallery_items() -> Dict[str, Any]:
    items = await run_in_threadpool(gallery_store.list_items, True)
    deleted_job_ids: List[str] = []

    for item in items:
        job_id = str(item.get("jobId") or "")
        if not job_id:
            continue
        try:
            removed_item = await run_in_threadpool(gallery_store.delete_item, job_id)
        except KeyError:
            continue

        await run_in_threadpool(_delete_local_gallery_file, removed_item.get("inputUrl"))
        await run_in_threadpool(_delete_local_gallery_file, removed_item.get("outputUrl"))
        deleted_job_ids.append(job_id)
        await ws_manager.broadcast({"type": "gallery_item_deleted", "jobId": job_id})

    logger.info("Gallery cleared: deleted=%s requested=%s", len(deleted_job_ids), len(items))
    return {
        "deleted": True,
        "deletedCount": len(deleted_job_ids),
        "requestedCount": len(items),
        "deletedJobIds": deleted_job_ids,
    }


@app.get("/queue/status")
async def queue_status() -> Dict[str, Any]:
    return await _queue_status_payload()


def _load_api_docs_markdown() -> str:
    try:
        return API_DOCS_MARKDOWN_PATH.read_text(encoding="utf-8")
    except OSError:
        return "API documentation file not found: docs/API.md"


def _load_comfy_api_docs_markdown() -> str:
    try:
        return COMFY_API_DOCS_MARKDOWN_PATH.read_text(encoding="utf-8")
    except OSError:
        return "ComfyUI API documentation file not found: docs/COMFYUI_API.md"


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
        <li><a href="/api/docs/comfyui">/api/docs/comfyui</a> (ComfyUI API docs)</li>
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


@app.get("/api/docs/comfy ui", tags=["Docs"], summary="ComfyUI API docs view")
@app.get("/api/docs/comfy-ui", tags=["Docs"], summary="ComfyUI API docs view")
@app.get("/api/docs/comfyui", tags=["Docs"], summary="ComfyUI API docs view")
async def comfy_api_docs_page() -> HTMLResponse:
    markdown_text = _load_comfy_api_docs_markdown()
    escaped = html.escape(markdown_text)
    html_content = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>ComfyUI API Docs</title>
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
      <h1>ComfyUI API Documentation</h1>
      <p class="muted">This page mirrors <span class="mono">docs/COMFYUI_API.md</span> for the ComfyUI staff workflow endpoints.</p>
      <ul>
        <li><a href="/comfy/staff">/comfy/staff</a> (staff dashboard)</li>
        <li><a href="/api/comfy/staff/status">/api/comfy/staff/status</a> (status JSON)</li>
        <li><a href="/api/comfy/presets">/api/comfy/presets</a> (preset JSON)</li>
        <li><a href="/admin/api/docs">/admin/api/docs</a> (full API docs)</li>
        <li><a href="/docs">/docs</a> (OpenAPI Swagger UI)</li>
      </ul>
    </div>
    <div class="card">
      <h2>docs/COMFYUI_API.md</h2>
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
    source: Optional[str] = None,
    engine: Optional[str] = None,
    showcase_only: bool = False,
) -> List[Dict[str, Any]]:
    mode_filter = _normalize_generation_mode(mode) if str(mode or "").strip() else ""
    style_filter = _normalize_style_id(style_id) if str(style_id or "").strip() else ""
    source_filter = _normalize_source(source) if str(source or "").strip() else ""
    engine_filter = _normalize_generation_engine(engine) if str(engine or "").strip() else ""

    def _matches(item: Dict[str, Any]) -> bool:
        item_mode, item_style = _resolve_mode_and_style_ids(
            item.get("generationMode"),
            item.get("styleId"),
        )
        if mode_filter and item_mode != mode_filter:
            return False
        if style_filter and item_style != style_filter:
            return False
        if source_filter and _normalize_source(item.get("source")) != source_filter:
            return False
        if engine_filter:
            settings = item.get("generationSettings") if isinstance(item.get("generationSettings"), dict) else {}
            item_engine = _normalize_generation_engine(
                item.get("generationEngine") or settings.get("generationEngine")
            )
            if item_engine != engine_filter:
                return False
        if showcase_only and not bool(item.get("showcaseVisible", False)):
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
    presetAnimal: Optional[str] = Form(None),
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
    generation_mode, style_id = _resolve_mode_and_style_ids(generationMode, styleId)
    normalized_preset_animal = _normalize_preset_animal(presetAnimal)
    extra_fields: Optional[Dict[str, Any]] = None
    if generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK and normalized_preset_animal:
        extra_fields = {"presetAnimal": normalized_preset_animal}
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
            extra_fields=extra_fields,
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
    "/api/jobs/{jobId}/photo",
    tags=["Public API"],
    summary="Get 4x6 photo print metadata",
)
async def api_get_job_photo(jobId: str) -> Dict[str, Any]:
    job = await _find_photo_job(jobId)
    return _existing_photo_payload(job)


@app.post(
    "/api/jobs/{jobId}/create-photo",
    tags=["Public API"],
    summary="Create or recreate a 4x6 photo print from an existing output image",
)
async def api_create_job_photo(jobId: str) -> Dict[str, Any]:
    job = await _find_photo_job(jobId)
    visitor_name = _normalize_visitor_name(job.get("visitorName")) or "Wonderpark Guest"

    try:
        output_path = _resolve_generated_output_path(job)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail="Generated output image not found") from exc

    try:
        photo_payload = await run_in_threadpool(
            create_4x6_photo_print,
            jobId,
            str(output_path),
            visitor_name,
            str(PRINTS_DIR),
        )
    except PillowMissingError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except GeneratedOutputMissingError as exc:
        raise HTTPException(status_code=400, detail="Generated output image not found") from exc
    except Exception as exc:
        logger.exception("Photo print generation failed jobId=%s", jobId)
        raise HTTPException(status_code=500, detail=f"Photo print generation failed: {exc}") from exc

    created_at = datetime.now(timezone.utc).isoformat()
    updates = {
        "photoPrintUrl": str(photo_payload.get("photoPrintUrl") or ""),
        "photoPrintPath": str(photo_payload.get("photoPrintPath") or ""),
        "photoPrintCreatedAt": created_at,
        "photoPrintTemplate": PHOTO_TEMPLATE,
        "photoPrintWidth": int(photo_payload.get("width") or PHOTO_WIDTH),
        "photoPrintHeight": int(photo_payload.get("height") or PHOTO_HEIGHT),
        "visitorNameUsed": visitor_name,
        "outputUrlUsedForPhoto": str(job.get("outputUrl") or ""),
        "logosUsed": bool(photo_payload.get("logosUsed", False)),
        "logoFallbackUsed": bool(photo_payload.get("logoFallbackUsed", False)),
    }
    await _save_photo_metadata(jobId, updates)
    return {
        "jobId": jobId,
        "photoCreated": True,
        **updates,
    }


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
    source: Optional[str] = Query(None),
    engine: Optional[str] = Query(None),
    showcaseOnly: bool = Query(False),
    absolute: bool = Query(False),
) -> Dict[str, Any]:
    items = await run_in_threadpool(gallery_store.list_items, False)
    filtered = _filter_gallery_items_for_api(
        items,
        mode,
        styleId,
        source=source,
        engine=engine,
        showcase_only=bool(showcaseOnly),
    )
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
    source: Optional[str] = Query(None),
    engine: Optional[str] = Query(None),
    showcaseOnly: bool = Query(False),
    absolute: bool = Query(False),
) -> Dict[str, Any]:
    items = await run_in_threadpool(gallery_store.list_items, False)
    filtered = _filter_gallery_items_for_api(
        items,
        mode,
        styleId,
        source=source,
        engine=engine,
        showcase_only=bool(showcaseOnly),
    )
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
    source: Optional[str] = Query(None),
    engine: Optional[str] = Query(None),
    showcaseOnly: bool = Query(False),
    absolute: bool = Query(False),
) -> Dict[str, Any]:
    items = await run_in_threadpool(gallery_store.list_items, False)
    filtered = _filter_gallery_items_for_api(
        items,
        mode,
        styleId,
        source=source,
        engine=engine,
        showcase_only=bool(showcaseOnly),
    )
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

    target_generation_mode, target_style_id = _resolve_mode_and_style_ids(
        payload.generationMode if payload.generationMode is not None else source_job.get("generationMode"),
        payload.styleId if payload.styleId is not None else source_job.get("styleId"),
    )
    source_settings = source_job.get("generationSettings")
    source_preset_animal = _normalize_preset_animal(source_job.get("presetAnimal"))
    if not source_preset_animal and isinstance(source_settings, dict):
        source_preset_animal = _normalize_preset_animal(source_settings.get("presetAnimal"))

    adjusted_preset = _apply_regenerate_adjustments(
        base_preset=base_preset,
        problem_tags=payload.problemTags,
        generation_mode=target_generation_mode,
        style_id=target_style_id,
        preset_animal=source_preset_animal,
    )
    adjusted_settings = _merge_generation_settings(
        adjusted_preset,
        source_settings if isinstance(source_settings, dict) else None,
    )
    if target_generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK:
        adjusted_settings = _enforce_drawing_to_artwork_generation_settings(adjusted_settings)
        adjusted_settings["controlWeight"] = float(adjusted_preset.control_weight)
        adjusted_settings["denoisingStrength"] = float(adjusted_preset.denoising_strength)
        adjusted_settings["controlMode"] = str(adjusted_preset.control_mode or DRAWING_TO_ARTWORK_CONTROL_MODE)
        adjusted_settings["cfgScale"] = float(adjusted_preset.cfg_scale)
        if source_preset_animal:
            adjusted_settings["presetAnimal"] = source_preset_animal
        adjusted_settings["promptUsed"] = adjusted_preset.prompt
        adjusted_settings["negativePromptUsed"] = adjusted_preset.negative_prompt
    if target_generation_mode == GENERATION_MODE_AI_ART_VENTURE:
        ai_background: Dict[str, Any] = {}
        try:
            ai_background = await run_in_threadpool(analyze_ai_art_venture_background, input_path)
        except Exception as exc:
            logger.warning(
                "AI Art Venture background analysis failed for regenerate job %s: %s",
                jobId,
                exc,
            )
            ai_background = {}
        _ai_preset, ai_defaults, ai_meta = build_ai_art_venture_preset(
            target_style_id,
            background_analysis=ai_background,
        )
        adjusted_preset, ai_defaults = _apply_ai_art_venture_plain_background_forcing(
            adjusted_preset,
            ai_defaults,
            background_type=str(ai_meta.get("backgroundType") or ""),
        )
        merged_settings = dict(ai_defaults)
        merged_settings.update(adjusted_settings)
        problem_tag_set = {str(tag or "").strip() for tag in payload.problemTags}
        identity_problem_tags = {
            "person_changed",
            "person_unrecognizable",
            "face_identity_changed",
            "gender_changed",
            "clothing_changed",
            "shirt_changed",
            "outfit_changed",
        }
        if problem_tag_set & identity_problem_tags:
            merged_settings["controlMode"] = "Balanced"
            use_ip_adapter = bool(merged_settings.get("useIpAdapter", AI_ART_VENTURE_USE_IP_ADAPTER))
            if use_ip_adapter:
                current_weight = _safe_float(merged_settings.get("ipAdapterWeight"))
                if current_weight <= 0:
                    current_weight = AI_ART_VENTURE_IP_ADAPTER_WEIGHT
                merged_settings["ipAdapterWeight"] = max(
                    AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MIN,
                    min(AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MAX, current_weight + 0.05),
                )
        if merged_settings.get("ipAdapterWeight") is not None:
            clamped_ip_weight = _safe_float(merged_settings.get("ipAdapterWeight"))
            if clamped_ip_weight <= 0:
                clamped_ip_weight = AI_ART_VENTURE_IP_ADAPTER_WEIGHT
            merged_settings["ipAdapterWeight"] = max(
                AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MIN,
                min(
                    AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MAX,
                    clamped_ip_weight,
                ),
            )
        experimental_mode = bool(merged_settings.get("experimentalMode", False))
        merged_settings = _enforce_ai_art_venture_generation_limits(
            merged_settings,
            experimental_mode=experimental_mode,
        )
        merged_settings["controlMode"] = str(merged_settings.get("controlMode") or "Balanced")
        merged_settings["backgroundType"] = ai_meta.get("backgroundType") or merged_settings.get("backgroundType") or "non_plain"
        merged_settings["whiteBackgroundRatio"] = ai_meta.get("whiteBackgroundRatio")
        merged_settings["finalDenoisingStrength"] = merged_settings.get("denoisingStrength")
        merged_settings["finalControlWeight"] = merged_settings.get("controlWeight")
        merged_settings["finalPrompt"] = adjusted_preset.prompt
        merged_settings["promptUsed"] = adjusted_preset.prompt
        merged_settings["negativePromptUsed"] = adjusted_preset.negative_prompt
        merged_settings["identitySafetyMode"] = True
        merged_settings["experimentalMode"] = experimental_mode
        adjusted_settings = _merge_generation_settings(adjusted_preset, merged_settings)
        target_style_id = str(ai_meta.get("styleId") or target_style_id)

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
    regenerate_extra_fields: Dict[str, Any] = {}
    if target_generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK and source_preset_animal:
        regenerate_extra_fields["presetAnimal"] = source_preset_animal

    new_job = _build_queue_job(
        job_id=new_job_id,
        visitor_name=_normalize_visitor_name(source_job.get("visitorName")),
        input_path=new_input_path,
        source="regenerate",
        estimate_payload=estimate_payload,
        generation_mode=target_generation_mode,
        style_id=target_style_id,
        original_job_id=original_job_id,
        regeneration_of=jobId,
        version=version,
        problem_tags=payload.problemTags,
        retry_count=0,
        preset_override=adjusted_preset,
        detection_payload=detection_payload,
        extra_fields=regenerate_extra_fields or None,
    )
    updated_generation_engine = _normalize_generation_engine(
        new_job.get("generationEngine")
        or adjusted_settings.get("generationEngine")
        or _resolve_generation_engine_name()
    )
    adjusted_settings["generationEngine"] = updated_generation_engine
    new_job["generationEngine"] = updated_generation_engine
    new_job["generationSettings"] = adjusted_settings
    new_job["styleLabel"] = _resolve_style_label(target_generation_mode, target_style_id)
    new_job["checkpoint"] = adjusted_settings.get("checkpoint")
    new_job["controlNetModel"] = adjusted_settings.get("controlNetModel")
    new_job["controlNetModule"] = adjusted_settings.get("controlNetModule")
    new_job["denoisingStrength"] = adjusted_settings.get("denoisingStrength")
    new_job["controlWeight"] = adjusted_settings.get("controlWeight")
    new_job["controlMode"] = adjusted_settings.get("controlMode")
    new_job["cfgScale"] = adjusted_settings.get("cfgScale")
    new_job["steps"] = adjusted_settings.get("steps")
    new_job["backgroundType"] = adjusted_settings.get("backgroundType")
    new_job["whiteBackgroundRatio"] = adjusted_settings.get("whiteBackgroundRatio")
    new_job["presetAnimal"] = _normalize_preset_animal(adjusted_settings.get("presetAnimal"))
    new_job["speciesPromptUsed"] = adjusted_settings.get("speciesPromptUsed")
    new_job["finalDenoisingStrength"] = adjusted_settings.get("finalDenoisingStrength")
    new_job["finalControlWeight"] = adjusted_settings.get("finalControlWeight")
    new_job["finalPrompt"] = adjusted_settings.get("finalPrompt")
    new_job["promptUsed"] = adjusted_settings.get("promptUsed")
    new_job["negativePromptUsed"] = adjusted_settings.get("negativePromptUsed")
    new_job["identitySafetyMode"] = adjusted_settings.get("identitySafetyMode")
    new_job["experimentalMode"] = adjusted_settings.get("experimentalMode")
    _sync_generation_metadata_fields(new_job, adjusted_settings)
    if target_generation_mode == GENERATION_MODE_AI_ART_VENTURE and not new_job.get("styleRiskLevel"):
        new_job["styleRiskLevel"] = _resolve_ai_art_style_metadata(target_style_id).get("styleRiskLevel", "balanced")

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

    for path in OUTPUT_DIR.rglob("*"):
        if not path.is_file():
            continue
        rel_url = f"/outputs/{path.relative_to(OUTPUT_DIR).as_posix()}"
        if rel_url in referenced_outputs:
            continue
        try:
            path.unlink()
            orphaned_files_removed += 1
        except OSError:
            logger.warning("Unable to delete orphaned output file: %s", path)

    for path in TEMP_DIR.rglob("*"):
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
    staff_count = int(summary.get("staffRatedImages") or summary.get("ratedImages") or 0)
    auto_count = int(summary.get("autoRatedImages") or 0)
    if staff_count == 0 and auto_count == 0:
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
    staff_count = int(summary.get("staffRatedImages") or summary.get("ratedImages") or 0)
    auto_count = int(summary.get("autoRatedImages") or 0)
    if staff_count == 0 and auto_count == 0:
        return PlainTextResponse("No rated images yet.")
    report = _build_tuning_text_report(summary)
    return PlainTextResponse(report)


@app.post("/generate")
async def generate(
    visitorName: str = Form(""),
    generationMode: str = Form(DEFAULT_GENERATION_MODE),
    styleId: str = Form(DEFAULT_STYLE_ID),
    presetAnimal: Optional[str] = Form(None),
    mode: Optional[str] = Form(None),
    aiArtVentureEnabled: Optional[str] = Form(None),
    randomStyleEnabled: Optional[str] = Form(None),
    randomThemeEnabled: Optional[str] = Form(None),
    selectedStyleId: Optional[str] = Form(None),
    selectedThemeId: Optional[str] = Form(None),
    customTheme: Optional[str] = Form(None),
    finalStyleId: Optional[str] = Form(None),
    finalStyleName: Optional[str] = Form(None),
    finalThemeId: Optional[str] = Form(None),
    finalThemeName: Optional[str] = Form(None),
    finalPrompt: Optional[str] = Form(None),
    negativePrompt: Optional[str] = Form(None),
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
    generation_mode, style_id = _resolve_mode_and_style_ids(generationMode, styleId)
    ai_mode_requested = str(mode or "").strip().lower().replace("_", "-") == "ai-art-venture"
    ai_toggle_requested = _parse_bool_form(aiArtVentureEnabled, False)
    ai_art_venture_enabled = generation_mode == GENERATION_MODE_AI_ART_VENTURE
    if not ai_art_venture_enabled and (ai_mode_requested or ai_toggle_requested):
        logger.info(
            "Ignoring AI Art Venture mode/toggle flags because generationMode=%s.",
            generation_mode,
        )
    random_style_enabled = _parse_bool_form(randomStyleEnabled, False)
    random_theme_enabled = _parse_bool_form(randomThemeEnabled, False)
    extra_job_fields = _build_ai_art_venture_staff_extra_fields(
        mode_value=mode,
        ai_art_venture_enabled=ai_art_venture_enabled,
        random_style_enabled=random_style_enabled,
        random_theme_enabled=random_theme_enabled,
        selected_style_id=selectedStyleId,
        selected_theme_id=selectedThemeId,
        custom_theme=customTheme,
        final_style_id=finalStyleId,
        final_style_name=finalStyleName,
        final_theme_id=finalThemeId,
        final_theme_name=finalThemeName,
    )
    normalized_preset_animal = _normalize_preset_animal(presetAnimal)
    if generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK and normalized_preset_animal:
        extra_job_fields["presetAnimal"] = normalized_preset_animal
    preset_override: Optional[PresetSettings] = None
    generation_override_meta: Dict[str, Any] = {}
    if generation_mode == GENERATION_MODE_AI_ART_VENTURE:
        preset_override, _override_settings, generation_override_meta = _build_ai_art_venture_staff_preset_override(
            style_id,
            finalPrompt,
            negativePrompt,
        )
        if generation_override_meta:
            extra_job_fields.update(generation_override_meta)
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
            generation_mode=generation_mode,
            style_id=style_id,
            preset_override=preset_override,
            extra_fields=extra_job_fields,
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
async def capture(
    visitorName: str = Form(""),
    generationMode: str = Form(DEFAULT_GENERATION_MODE),
    styleId: str = Form(DEFAULT_STYLE_ID),
    presetAnimal: Optional[str] = Form(None),
    mode: Optional[str] = Form(None),
    aiArtVentureEnabled: Optional[str] = Form(None),
    randomStyleEnabled: Optional[str] = Form(None),
    randomThemeEnabled: Optional[str] = Form(None),
    selectedStyleId: Optional[str] = Form(None),
    selectedThemeId: Optional[str] = Form(None),
    customTheme: Optional[str] = Form(None),
    finalStyleId: Optional[str] = Form(None),
    finalStyleName: Optional[str] = Form(None),
    finalThemeId: Optional[str] = Form(None),
    finalThemeName: Optional[str] = Form(None),
    finalPrompt: Optional[str] = Form(None),
    negativePrompt: Optional[str] = Form(None),
) -> Dict[str, Any]:
    job_id = uuid.uuid4().hex
    input_path, _ = _job_paths(job_id)
    visitor_name = _normalize_visitor_name(visitorName)
    generation_mode, style_id = _resolve_mode_and_style_ids(generationMode, styleId)
    ai_mode_requested = str(mode or "").strip().lower().replace("_", "-") == "ai-art-venture"
    ai_toggle_requested = _parse_bool_form(aiArtVentureEnabled, False)
    ai_art_venture_enabled = generation_mode == GENERATION_MODE_AI_ART_VENTURE
    if not ai_art_venture_enabled and (ai_mode_requested or ai_toggle_requested):
        logger.info(
            "Ignoring AI Art Venture mode/toggle flags because generationMode=%s.",
            generation_mode,
        )
    random_style_enabled = _parse_bool_form(randomStyleEnabled, False)
    random_theme_enabled = _parse_bool_form(randomThemeEnabled, False)
    extra_job_fields = _build_ai_art_venture_staff_extra_fields(
        mode_value=mode,
        ai_art_venture_enabled=ai_art_venture_enabled,
        random_style_enabled=random_style_enabled,
        random_theme_enabled=random_theme_enabled,
        selected_style_id=selectedStyleId,
        selected_theme_id=selectedThemeId,
        custom_theme=customTheme,
        final_style_id=finalStyleId,
        final_style_name=finalStyleName,
        final_theme_id=finalThemeId,
        final_theme_name=finalThemeName,
    )
    normalized_preset_animal = _normalize_preset_animal(presetAnimal)
    if generation_mode == GENERATION_MODE_DRAWING_TO_ARTWORK and normalized_preset_animal:
        extra_job_fields["presetAnimal"] = normalized_preset_animal
    preset_override: Optional[PresetSettings] = None
    generation_override_meta: Dict[str, Any] = {}
    if generation_mode == GENERATION_MODE_AI_ART_VENTURE:
        preset_override, _override_settings, generation_override_meta = _build_ai_art_venture_staff_preset_override(
            style_id,
            finalPrompt,
            negativePrompt,
        )
        if generation_override_meta:
            extra_job_fields.update(generation_override_meta)
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
            generation_mode=generation_mode,
            style_id=style_id,
            preset_override=preset_override,
            extra_fields=extra_job_fields,
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
