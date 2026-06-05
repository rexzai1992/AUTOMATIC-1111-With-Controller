from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SCANNER_INPUT_DIR_NAME = "scanner_inputs"
SCANNER_INPUT_DIR = BASE_DIR / SCANNER_INPUT_DIR_NAME
INPUT_DIR = BASE_DIR / "inputs"
OUTPUT_DIR = BASE_DIR / "outputs"
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
PRINTS_DIR = BASE_DIR / "prints"
GALLERY_JSON_PATH = DATA_DIR / "gallery.json"
QUEUE_JSON_PATH = DATA_DIR / "queue.json"
WONDERPARK_SUBMISSIONS_JSON_PATH = DATA_DIR / "wonderpark_submissions.json"
TEMP_DIR = BASE_DIR / "temp"
OBJECT_STORAGE_DIR = BASE_DIR / "storage" / "object"
WONDERPARK_STORAGE_DIR = OBJECT_STORAGE_DIR / "wonderpark"
WONDERPARK_ORIGINALS_DIR = WONDERPARK_STORAGE_DIR / "originals"
WONDERPARK_PROCESSED_DIR = WONDERPARK_STORAGE_DIR / "processed"
WONDERPARK_THUMBNAILS_DIR = WONDERPARK_STORAGE_DIR / "thumbnails"

for directory in (
    SCANNER_INPUT_DIR,
    INPUT_DIR,
    OUTPUT_DIR,
    DATA_DIR,
    STATIC_DIR,
    PRINTS_DIR,
    TEMP_DIR,
    OBJECT_STORAGE_DIR,
    WONDERPARK_STORAGE_DIR,
    WONDERPARK_ORIGINALS_DIR,
    WONDERPARK_PROCESSED_DIR,
    WONDERPARK_THUMBNAILS_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)

if not GALLERY_JSON_PATH.exists():
    GALLERY_JSON_PATH.write_text("[]", encoding="utf-8")
if not QUEUE_JSON_PATH.exists():
    QUEUE_JSON_PATH.write_text("[]", encoding="utf-8")
if not WONDERPARK_SUBMISSIONS_JSON_PATH.exists():
    WONDERPARK_SUBMISSIONS_JSON_PATH.write_text("[]", encoding="utf-8")

ENABLE_FOLDER_WATCHER = True
ALLOWED_UPLOAD_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
SCANNER_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}
API_KEY = ""

# Public Wonderpark upload flow (feature toggle + limits).
WONDERPARK_PUBLIC_UPLOAD_ENABLED = True
WONDERPARK_PUBLIC_ROUTE = "/public/wonderpark"
WONDERPARK_MAX_UPLOAD_BYTES = 12 * 1024 * 1024
WONDERPARK_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
WONDERPARK_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
WONDERPARK_RATE_LIMIT_WINDOW_SECONDS = 300
WONDERPARK_RATE_LIMIT_MAX_PER_IP = 5
WONDERPARK_DUPLICATE_WINDOW_SECONDS = 600
WONDERPARK_MIN_RECOMMENDED_WIDTH = 1200
WONDERPARK_MIN_RECOMMENDED_HEIGHT = 900
WONDERPARK_MAX_PROCESSING_DIMENSION = 2048
WONDERPARK_THUMBNAIL_MAX_DIMENSION = 640
WONDERPARK_DEFAULT_GENERATION_MODE = "person_holding_artwork"
WONDERPARK_DEFAULT_STYLE_ID = "auto"

# CORS settings for local/LAN app integrations.
# Keep permissive defaults for offline kiosk usage; tighten as needed.
CORS_ALLOWED_ORIGINS = ["*"]
CORS_ALLOW_CREDENTIALS = False
CORS_ALLOW_METHODS = ["*"]
CORS_ALLOW_HEADERS = ["*"]


@dataclass(frozen=True)
class StableDiffusionConfig:
    base_url: str = "http://127.0.0.1:7860"
    models_endpoint: str = "/sdapi/v1/sd-models"
    options_endpoint: str = "/sdapi/v1/options"
    img2img_endpoint: str = "/sdapi/v1/img2img"
    checkpoint: str = "DreamShaper_8_pruned.safetensors [879db523c3]"
    controlnet_model: str = "control_v11p_sd15_scribble [4e6af23e]"
    controlnet_module: str = "pidinet_scribble"
    connect_timeout_seconds: int = 10
    generate_timeout_seconds: int = 180


@dataclass(frozen=True)
class GenerationDefaults:
    prompt: str = (
        "Transform the submitted drawing into a colorful enhanced illustration while preserving the "
        "original composition, shapes, creative idea, and hand-drawn charm. Fully colored, vibrant, "
        "cheerful, child-friendly, clean coloring, soft lighting, gentle shading, expressive details, "
        "storybook illustration style, high quality."
    )
    negative_prompt: str = (
        "black and white, monochrome, unfinished sketch, scary, horror, ugly, deformed, distorted, "
        "extra limbs, duplicate objects, bad anatomy, blurry, low quality, messy, text, watermark, logo, "
        "photorealistic"
    )
    steps: int = 30
    cfg_scale: float = 7.0
    width: int = 768
    height: int = 768
    sampler_name: str = "DPM++ 2M Karras"
    resize_mode: str = "Crop and Resize"
    pixel_perfect: bool = True
    guidance_start: float = 0.0
    guidance_end: float = 1.0


SD_CONFIG = StableDiffusionConfig()
GENERATION_DEFAULTS = GenerationDefaults()
