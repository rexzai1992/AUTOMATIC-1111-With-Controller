from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.config import BASE_DIR
from app.detector import PresetSettings


logger = logging.getLogger(__name__)

AI_ART_VENTURE_MODE_ID = "ai_art_venture"
AI_ART_VENTURE_MODE_LABEL = "AI Art Venture"
AI_ART_VENTURE_STYLES_PATH = BASE_DIR / "data" / "ai_art_venture_styles.json"
AI_ART_VENTURE_DEFAULT_STYLE_ID = "pixar_3d"
AI_ART_VENTURE_CONTROLNET_PREFERRED_MODEL = "control_v11p_sd15_softedge"
AI_ART_VENTURE_CONTROLNET_PREFERRED_MODULE = "softedge_teed"
AI_ART_VENTURE_CONTROLNET_FALLBACK_MODEL = "control_v11p_sd15_canny"
AI_ART_VENTURE_CONTROLNET_FALLBACK_MODULE = "canny"
AI_ART_VENTURE_USE_IP_ADAPTER = True
AI_ART_VENTURE_IP_ADAPTER_WEIGHT = 0.62
AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MIN = 0.50
AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MAX = 0.75
AI_ART_VENTURE_IDENTITY_TARGET = "recognizable_not_exact"
PLAIN_BACKGROUND_WHITE_RATIO_THRESHOLD = 0.60
AI_ART_VENTURE_DENOISE_MIN = 0.32
AI_ART_VENTURE_DENOISE_MAX = 0.46
AI_ART_VENTURE_DENOISE_MAX_NO_IP = 0.46
AI_ART_VENTURE_CONTROL_WEIGHT_MIN = 0.70
AI_ART_VENTURE_CONTROL_WEIGHT_MAX = 0.90
AI_ART_VENTURE_CFG_MIN = 6.0
AI_ART_VENTURE_CFG_MAX = 8.5
AI_ART_VENTURE_PLAIN_BG_NEGATIVE_SUFFIX = (
    "plain wall, classroom wall, white wall, blank backdrop, empty background, flat studio background"
)
AI_ART_VENTURE_BACKGROUND_REPLACEMENT_PLAIN_DIRECTIVE = (
    "Replace the original plain background with a rich, detailed, style-matching environment. "
    "Do not keep a plain wall, studio wall, blank backdrop, or empty background. "
    "Keep the person and creation recognizable while changing the surrounding environment."
)
AI_ART_VENTURE_BACKGROUND_REPLACEMENT_NON_PLAIN_DIRECTIVE = (
    "Improve the background into a more polished style-matching environment while keeping the person and creation "
    "recognizable."
)
AI_ART_VENTURE_STRONG_BG_NEGATIVE_SUFFIX = (
    "plain white background, blank wall, studio wall, unchanged background, same background as input, no background"
)

AI_ART_VENTURE_BASE_PROMPT = (
    "Transform this photo into the selected artistic style while keeping the person clearly recognizable as the "
    "same person. Preserve recognizable identity, face shape, hairstyle, hair color, glasses or beard if present, "
    "skin tone, expression vibe, clothing color, shirt type, body pose, hand placement, and the artwork or creation "
    "they are holding. The face may become stylized, cartoonized, painterly, anime, toy-like, or 3D, but it must "
    "still feel like the same person. Keep the creation clearly visible and recognizable. Preserve the artwork or "
    "creation shape, content, placement, and visibility. You may redesign the background into a rich immersive "
    "style-matching environment. Change style, rendering, lighting, texture, color mood, and atmosphere while "
    "keeping the subject and creation recognizable. High quality, detailed, clean, expressive, polished, professional."
)

AI_ART_VENTURE_NEGATIVE_PROMPT = (
    "different person, unrecognizable person, gender swap, changed gender, changed face, completely different face "
    "shape, changed hairstyle, changed clothing type, suit, tuxedo, dress, uniform, costume, armor, formal outfit, "
    "missing shirt, missing person, missing artwork, changed artwork, unreadable artwork, destroyed artwork, missing "
    "object, changed object, different pose, hidden face, cropped face, extra fingers, missing fingers, bad hands, "
    "malformed hands, duplicated body, duplicated limbs, distorted face, ugly face, creepy face, blurry, low quality, "
    "watermark, logo, text"
)


def _default_styles_payload() -> Dict[str, Any]:
    return {
        "version": 1,
        "modeId": AI_ART_VENTURE_MODE_ID,
        "modeLabel": AI_ART_VENTURE_MODE_LABEL,
        "defaultStyleId": AI_ART_VENTURE_DEFAULT_STYLE_ID,
        "basePrompt": AI_ART_VENTURE_BASE_PROMPT,
        "negativePrompt": AI_ART_VENTURE_NEGATIVE_PROMPT,
        "baseSettings": {
            "checkpoint": "DreamShaper_8_pruned.safetensors [879db523c3]",
            "controlNetModel": AI_ART_VENTURE_CONTROLNET_PREFERRED_MODEL,
            "controlNetModule": AI_ART_VENTURE_CONTROLNET_PREFERRED_MODULE,
            "controlMode": "Balanced",
            "resizeMode": "Crop and Resize",
            "pixelPerfect": True,
            "guidanceStart": 0.0,
            "guidanceEnd": 1.0,
            "controlWeight": 0.78,
            "softEdgeWeight": 0.78,
            "denoisingStrength": 0.40,
            "cfgScale": 7.4,
            "steps": 32,
            "samplerName": "DPM++ 2M Karras",
            "width": 768,
            "height": 768,
            "useIpAdapter": AI_ART_VENTURE_USE_IP_ADAPTER,
            "ipAdapterModule": "ip-adapter_face_id_plus",
            "ipAdapterModel": "ip-adapter-faceid-plusv2_sd15",
            "ipAdapterWeight": AI_ART_VENTURE_IP_ADAPTER_WEIGHT,
            "identitySafetyMode": True,
            "identityTarget": AI_ART_VENTURE_IDENTITY_TARGET,
            "experimentalMode": False,
        },
        "styles": [
            {
                "id": "storybook",
                "label": "Storybook",
                "styleRiskLevel": "safe",
                "stylePrompt": "children's storybook illustration style, painterly textures, warm narrative lighting",
                "backgroundPrompt": "colorful children's storybook environment with charming narrative scenery and warm light",
                "overrides": {"denoisingStrength": 0.40, "cfgScale": 7.2, "controlWeight": 0.80},
            },
            {
                "id": "watercolor",
                "label": "Watercolor",
                "styleRiskLevel": "safe",
                "stylePrompt": "traditional watercolor painting, soft pigment bloom, paper grain texture, hand-painted washes",
                "backgroundPrompt": "lush watercolor landscape with flowing pigments, layered washes, and painterly depth",
                "overrides": {"denoisingStrength": 0.42, "cfgScale": 7.3, "controlWeight": 0.78},
            },
            {
                "id": "comic_book",
                "label": "Comic Book",
                "styleRiskLevel": "safe",
                "stylePrompt": "bold comic book ink lines, halftone shading, dynamic contrast, graphic novel finish",
                "backgroundPrompt": "dramatic comic world with dynamic perspective, action lighting, and graphic city scenery",
                "overrides": {"denoisingStrength": 0.38, "cfgScale": 7.0, "controlWeight": 0.82},
            },
            {
                "id": "paper_cut",
                "label": "Paper Cut",
                "styleRiskLevel": "safe",
                "stylePrompt": "layered paper-cut collage style, stacked cardstock textures, soft shadow depth",
                "backgroundPrompt": "layered paper art scene with cutout shapes, dimensional shadows, and handcrafted depth",
                "overrides": {"denoisingStrength": 0.39, "cfgScale": 7.0, "controlWeight": 0.82},
            },
            {
                "id": "doodle",
                "label": "Doodle",
                "styleRiskLevel": "safe",
                "stylePrompt": "playful doodle illustration style, marker texture, hand-drawn whimsical line energy",
                "backgroundPrompt": "playful illustrated world with whimsical doodle scenery and hand-drawn decorative elements",
                "overrides": {"denoisingStrength": 0.36, "cfgScale": 6.8, "controlWeight": 0.84},
            },
            {
                "id": "clay_toy",
                "label": "Clay Toy",
                "styleRiskLevel": "safe",
                "stylePrompt": "stop-motion clay toy style, handcrafted clay texture, soft cinematic lighting",
                "backgroundPrompt": "handcrafted clay miniature set with stylized scenery, cozy lighting, and stop-motion atmosphere",
                "overrides": {"denoisingStrength": 0.42, "cfgScale": 7.3, "controlWeight": 0.80},
            },
            {
                "id": "manga",
                "label": "Manga",
                "styleRiskLevel": "safe",
                "stylePrompt": "manga illustration style, crisp screentone shading, clean outlines, dramatic panel-like lighting",
                "backgroundPrompt": "manga-style world with expressive line backgrounds, motion energy, and cinematic framing",
                "overrides": {"denoisingStrength": 0.38, "cfgScale": 7.0, "controlWeight": 0.82},
            },
            {
                "id": "anime_movie",
                "label": "Anime Movie",
                "styleRiskLevel": "balanced",
                "stylePrompt": (
                    "feature anime movie style, clean linework, cinematic lighting, rich color grading, detailed background"
                ),
                "backgroundPrompt": "cinematic anime environment with expressive sky gradients, atmosphere, and depth",
                "overrides": {"denoisingStrength": 0.41, "cfgScale": 7.2, "controlWeight": 0.80},
            },
            {
                "id": "fantasy_epic",
                "label": "Fantasy Epic",
                "styleRiskLevel": "balanced",
                "stylePrompt": "epic fantasy concept art style, cinematic god rays, ornate details, heroic atmosphere",
                "backgroundPrompt": "magical fantasy world with castles, glowing forests, and epic cinematic atmosphere",
                "overrides": {"denoisingStrength": 0.43, "cfgScale": 7.5, "controlWeight": 0.78},
            },
            {
                "id": "steampunk",
                "label": "Steampunk",
                "styleRiskLevel": "balanced",
                "stylePrompt": "steampunk illustration style, brass mechanics, Victorian design elements, warm smoky lighting",
                "backgroundPrompt": "Victorian industrial world with brass machinery, gears, smoke, and cinematic warm depth",
                "overrides": {"denoisingStrength": 0.42, "cfgScale": 7.4, "controlWeight": 0.78},
            },
            {
                "id": "oil_painting",
                "label": "Oil Painting",
                "styleRiskLevel": "balanced",
                "stylePrompt": "classical oil painting, visible brush strokes, rich impasto texture, dramatic studio lighting",
                "backgroundPrompt": "rich painterly environment with textured brushwork, atmospheric depth, and dramatic light",
                "overrides": {"denoisingStrength": 0.43, "cfgScale": 7.5, "controlWeight": 0.78, "steps": 34},
            },
            {
                "id": "renaissance",
                "label": "Renaissance",
                "styleRiskLevel": "balanced",
                "stylePrompt": "Renaissance painting style, museum-quality composition, chiaroscuro lighting, fine canvas texture",
                "backgroundPrompt": "classical old-world architecture and painterly scenery with warm renaissance depth",
                "overrides": {"denoisingStrength": 0.43, "cfgScale": 7.5, "controlWeight": 0.78, "steps": 34},
            },
            {
                "id": "da_vinci",
                "label": "Da Vinci",
                "styleRiskLevel": "balanced",
                "stylePrompt": "Leonardo da Vinci inspired painting style, sfumato shading, old master texture, warm muted palette",
                "backgroundPrompt": "renaissance workshop and old architecture with warm natural light and timeless atmosphere",
                "overrides": {"denoisingStrength": 0.43, "cfgScale": 7.4, "controlWeight": 0.78, "steps": 34},
            },
            {
                "id": "cyberpunk",
                "label": "Cyberpunk",
                "styleRiskLevel": "balanced",
                "stylePrompt": "cyberpunk neon aesthetic, high contrast lighting, holographic reflections, futuristic texture",
                "backgroundPrompt": "neon futuristic city with holograms, rain reflections, and dense atmospheric depth",
                "overrides": {"denoisingStrength": 0.42, "cfgScale": 7.5, "controlWeight": 0.78},
            },
            {
                "id": "plush_toy",
                "label": "Plush Toy",
                "styleRiskLevel": "balanced",
                "stylePrompt": "plush toy fabric style, stitched details, soft fuzzy textures, cozy lighting",
                "backgroundPrompt": "cozy plush-inspired environment with soft textiles, warm lights, and dreamy toy-world depth",
                "overrides": {"denoisingStrength": 0.42, "cfgScale": 7.3, "controlWeight": 0.80},
            },
            {
                "id": "pixar_3d",
                "label": "Pixar 3D",
                "styleRiskLevel": "experimental",
                "stylePrompt": (
                    "3D animated family movie style, cinematic soft lighting, expressive eyes, polished skin, "
                    "high-end 3D render"
                ),
                "backgroundPrompt": "colorful animated world with whimsical architecture, cinematic skies, and playful depth",
                "overrides": {"denoisingStrength": 0.44, "cfgScale": 7.5, "controlWeight": 0.76},
            },
            {
                "id": "disney_3d",
                "label": "Disney 3D",
                "styleRiskLevel": "experimental",
                "stylePrompt": (
                    "Disney-inspired 3D animated film style, magical glow, expressive characters, polished cinematic render"
                ),
                "backgroundPrompt": "storybook-like enchanted kingdom with colorful magical scenery and warm depth",
                "overrides": {"denoisingStrength": 0.44, "cfgScale": 7.5, "controlWeight": 0.76},
            },
            {
                "id": "lego_3d",
                "label": "LEGO 3D",
                "styleRiskLevel": "experimental",
                "stylePrompt": "LEGO brick-built 3D style, plastic material, studio lighting, toy-photography look",
                "backgroundPrompt": "toy brick world with colorful block structures, miniature city details, and playful depth",
                "overrides": {"denoisingStrength": 0.45, "cfgScale": 7.4, "controlWeight": 0.74},
            },
            {
                "id": "minecraft",
                "label": "Minecraft",
                "styleRiskLevel": "experimental",
                "stylePrompt": "Minecraft voxel world style, block-based geometry, pixel textures, game-like lighting",
                "backgroundPrompt": "voxel adventure world with block terrain, stylized sky, and game-like depth",
                "overrides": {"denoisingStrength": 0.46, "cfgScale": 7.4, "controlWeight": 0.74},
            },
            {
                "id": "low_poly",
                "label": "Low Poly",
                "styleRiskLevel": "experimental",
                "stylePrompt": "low poly 3D art style, simplified geometric forms, faceted shading, clean render",
                "backgroundPrompt": "geometric low-poly environment with faceted terrain, stylized sky, and clean depth",
                "overrides": {"denoisingStrength": 0.45, "cfgScale": 7.3, "controlWeight": 0.74},
            },
        ],
    }


def ensure_styles_file() -> Path:
    AI_ART_VENTURE_STYLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if AI_ART_VENTURE_STYLES_PATH.exists():
        return AI_ART_VENTURE_STYLES_PATH

    payload = _default_styles_payload()
    AI_ART_VENTURE_STYLES_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    logger.info("Created default AI Art Venture styles file: %s", AI_ART_VENTURE_STYLES_PATH)
    return AI_ART_VENTURE_STYLES_PATH


def load_styles_payload() -> Dict[str, Any]:
    ensure_styles_file()
    try:
        parsed = json.loads(AI_ART_VENTURE_STYLES_PATH.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            return parsed
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to read %s. Falling back to in-memory defaults.", AI_ART_VENTURE_STYLES_PATH)
    return _default_styles_payload()


def _safe_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _safe_bool(value: Any, fallback: bool) -> bool:
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


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def analyze_background(image_path: Path) -> Dict[str, Any]:
    image_bgr = cv2.imread(str(image_path))
    if image_bgr is None:
        raise ValueError(f"Unable to load image for background analysis: {image_path}")

    height, width = image_bgr.shape[:2]
    total_pixels = float(max(1, height * width))
    white_mask = cv2.inRange(image_bgr, (220, 220, 220), (255, 255, 255))
    white_ratio = cv2.countNonZero(white_mask) / total_pixels

    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    low_sat_mask = cv2.inRange(hsv[:, :, 1], 0, 28)
    high_val_mask = cv2.inRange(hsv[:, :, 2], 140, 255)
    plain_mask = cv2.bitwise_and(low_sat_mask, high_val_mask)
    plain_ratio = cv2.countNonZero(plain_mask) / total_pixels

    grayscale = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(grayscale, (5, 5), 0), 60, 150)
    edge_ratio = cv2.countNonZero(edges) / total_pixels

    border_mask = white_mask.copy()
    border_mask[:] = 0
    band = max(8, int(min(height, width) * 0.18))
    border_mask[:band, :] = 255
    border_mask[height - band :, :] = 255
    border_mask[:, :band] = 255
    border_mask[:, width - band :] = 255
    border_pixels = float(max(1, cv2.countNonZero(border_mask)))

    white_border = cv2.bitwise_and(white_mask, border_mask)
    plain_border = cv2.bitwise_and(plain_mask, border_mask)
    edge_border = cv2.bitwise_and(edges, border_mask)
    white_border_ratio = cv2.countNonZero(white_border) / border_pixels
    plain_border_ratio = cv2.countNonZero(plain_border) / border_pixels
    edge_border_ratio = cv2.countNonZero(edge_border) / border_pixels
    border_indices = border_mask > 0
    border_gray_values = grayscale[border_indices]
    border_sat_values = hsv[:, :, 1][border_indices]
    border_gray_std = float(np.std(border_gray_values)) if border_gray_values.size else 0.0
    border_sat_std = float(np.std(border_sat_values)) if border_sat_values.size else 0.0
    uniform_border = border_gray_std < 22.0 and border_sat_std < 20.0

    studio_like = (
        plain_ratio > 0.68 and edge_ratio < 0.06
    ) or (
        plain_border_ratio > 0.62 and edge_border_ratio < 0.05
    ) or (
        uniform_border
        and edge_border_ratio < 0.08
        and (plain_border_ratio > 0.35 or white_border_ratio > 0.18)
    )
    background_type = "plain" if (
        white_ratio > PLAIN_BACKGROUND_WHITE_RATIO_THRESHOLD
        or white_border_ratio > 0.55
        or studio_like
    ) else "non_plain"

    return {
        "backgroundType": background_type,
        "whiteBackgroundRatio": round(float(white_ratio), 4),
        "plainBackgroundRatio": round(float(plain_ratio), 4),
        "edgeRatio": round(float(edge_ratio), 4),
        "whiteBorderRatio": round(float(white_border_ratio), 4),
        "plainBorderRatio": round(float(plain_border_ratio), 4),
        "edgeBorderRatio": round(float(edge_border_ratio), 4),
        "borderGrayStd": round(float(border_gray_std), 4),
        "borderSatStd": round(float(border_sat_std), 4),
        "uniformBorder": bool(uniform_border),
        "studioLike": bool(studio_like),
    }


def _sanitize_styles(raw_styles: Any) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    if not isinstance(raw_styles, list):
        return output

    for row in raw_styles:
        if not isinstance(row, dict):
            continue
        style_id = str(row.get("id") or "").strip().lower()
        if not style_id:
            continue
        label = str(row.get("label") or style_id.replace("_", " ").title()).strip()
        style_prompt = str(row.get("stylePrompt") or "").strip()
        background_prompt = str(row.get("backgroundPrompt") or "").strip()
        style_risk_level = str(row.get("styleRiskLevel") or "balanced").strip().lower()
        if style_risk_level not in {"safe", "balanced", "experimental"}:
            style_risk_level = "balanced"
        overrides = row.get("overrides")
        if not isinstance(overrides, dict):
            overrides = {}
        output.append(
            {
                "id": style_id,
                "label": label,
                "styleRiskLevel": style_risk_level,
                "stylePrompt": style_prompt,
                "backgroundPrompt": background_prompt,
                "overrides": dict(overrides),
            }
        )
    return output


def get_mode_config() -> Dict[str, Any]:
    payload = load_styles_payload()
    fallback = _default_styles_payload()
    base_settings_raw = payload.get("baseSettings")
    fallback_base = fallback["baseSettings"]
    base_settings = base_settings_raw if isinstance(base_settings_raw, dict) else {}

    controlnet_model = str(base_settings.get("controlNetModel") or fallback_base["controlNetModel"]).strip()
    controlnet_module = str(base_settings.get("controlNetModule") or fallback_base["controlNetModule"]).strip()
    if "scribble" in controlnet_model.lower() or "scribble" in controlnet_module.lower():
        logger.warning(
            "AI Art Venture does not allow Scribble ControlNet. Overriding to %s (%s).",
            AI_ART_VENTURE_CONTROLNET_PREFERRED_MODEL,
            AI_ART_VENTURE_CONTROLNET_PREFERRED_MODULE,
        )
        controlnet_model = AI_ART_VENTURE_CONTROLNET_PREFERRED_MODEL
        controlnet_module = AI_ART_VENTURE_CONTROLNET_PREFERRED_MODULE

    merged_base = {
        "checkpoint": str(base_settings.get("checkpoint") or fallback_base["checkpoint"]),
        "controlNetModel": controlnet_model or AI_ART_VENTURE_CONTROLNET_PREFERRED_MODEL,
        "controlNetModule": controlnet_module or AI_ART_VENTURE_CONTROLNET_PREFERRED_MODULE,
        "controlMode": str(base_settings.get("controlMode") or fallback_base["controlMode"] or "Balanced"),
        "resizeMode": str(base_settings.get("resizeMode") or fallback_base["resizeMode"]),
        "pixelPerfect": bool(base_settings.get("pixelPerfect", fallback_base["pixelPerfect"])),
        "guidanceStart": _safe_float(base_settings.get("guidanceStart"), fallback_base["guidanceStart"]),
        "guidanceEnd": _safe_float(base_settings.get("guidanceEnd"), fallback_base["guidanceEnd"]),
        "controlWeight": _clamp(
            _safe_float(
                base_settings.get("softEdgeWeight", base_settings.get("controlWeight")),
                fallback_base.get("softEdgeWeight", fallback_base["controlWeight"]),
            ),
            AI_ART_VENTURE_CONTROL_WEIGHT_MIN,
            AI_ART_VENTURE_CONTROL_WEIGHT_MAX,
        ),
        "softEdgeWeight": _clamp(
            _safe_float(
                base_settings.get("softEdgeWeight", base_settings.get("controlWeight")),
                fallback_base.get("softEdgeWeight", fallback_base["controlWeight"]),
            ),
            AI_ART_VENTURE_CONTROL_WEIGHT_MIN,
            AI_ART_VENTURE_CONTROL_WEIGHT_MAX,
        ),
        "denoisingStrength": _clamp(
            _safe_float(base_settings.get("denoisingStrength"), fallback_base["denoisingStrength"]),
            AI_ART_VENTURE_DENOISE_MIN,
            AI_ART_VENTURE_DENOISE_MAX,
        ),
        "cfgScale": _clamp(
            _safe_float(base_settings.get("cfgScale"), fallback_base["cfgScale"]),
            AI_ART_VENTURE_CFG_MIN,
            AI_ART_VENTURE_CFG_MAX,
        ),
        "steps": _safe_int(base_settings.get("steps"), fallback_base["steps"]),
        "samplerName": str(base_settings.get("samplerName") or fallback_base["samplerName"]),
        "width": _safe_int(base_settings.get("width"), fallback_base["width"]),
        "height": _safe_int(base_settings.get("height"), fallback_base["height"]),
        "useIpAdapter": _safe_bool(
            base_settings.get("useIpAdapter"),
            _safe_bool(fallback_base.get("useIpAdapter"), AI_ART_VENTURE_USE_IP_ADAPTER),
        ),
        "ipAdapterModule": str(
            base_settings.get("ipAdapterModule")
            or fallback_base.get("ipAdapterModule")
            or "ip-adapter_face_id_plus"
        ),
        "ipAdapterModel": str(
            base_settings.get("ipAdapterModel")
            or fallback_base.get("ipAdapterModel")
            or "ip-adapter-faceid-plusv2_sd15"
        ),
        "ipAdapterWeight": _clamp(
            _safe_float(base_settings.get("ipAdapterWeight"), fallback_base.get("ipAdapterWeight", AI_ART_VENTURE_IP_ADAPTER_WEIGHT)),
            AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MIN,
            AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MAX,
        ),
        "identitySafetyMode": _safe_bool(
            base_settings.get("identitySafetyMode"),
            _safe_bool(fallback_base.get("identitySafetyMode"), True),
        ),
        "identityTarget": str(base_settings.get("identityTarget") or fallback_base.get("identityTarget") or AI_ART_VENTURE_IDENTITY_TARGET),
        "experimentalMode": _safe_bool(
            base_settings.get("experimentalMode"),
            _safe_bool(fallback_base.get("experimentalMode"), False),
        ),
    }

    styles = _sanitize_styles(payload.get("styles"))
    if not styles:
        styles = _sanitize_styles(fallback["styles"])

    default_style_id = str(payload.get("defaultStyleId") or fallback["defaultStyleId"]).strip().lower()
    style_ids = {row["id"] for row in styles}
    if default_style_id not in style_ids and styles:
        default_style_id = styles[0]["id"]

    base_prompt = str(payload.get("basePrompt") or fallback["basePrompt"]).strip()
    negative_prompt = str(payload.get("negativePrompt") or fallback["negativePrompt"]).strip()

    return {
        "modeId": AI_ART_VENTURE_MODE_ID,
        "modeLabel": str(payload.get("modeLabel") or AI_ART_VENTURE_MODE_LABEL),
        "defaultStyleId": default_style_id or AI_ART_VENTURE_DEFAULT_STYLE_ID,
        "basePrompt": base_prompt,
        "negativePrompt": negative_prompt,
        "baseSettings": merged_base,
        "styles": styles,
    }


def resolve_style(style_id: str) -> Dict[str, Any]:
    config = get_mode_config()
    styles = config.get("styles", [])
    if not isinstance(styles, list):
        styles = []
    by_id = {str(item.get("id") or ""): item for item in styles if isinstance(item, dict)}

    candidate = str(style_id or "").strip().lower()
    if candidate in by_id:
        return by_id[candidate]

    default_style_id = str(config.get("defaultStyleId") or AI_ART_VENTURE_DEFAULT_STYLE_ID)
    if default_style_id in by_id:
        return by_id[default_style_id]

    if styles:
        return styles[0]

    return {
        "id": AI_ART_VENTURE_DEFAULT_STYLE_ID,
        "label": "Pixar 3D",
        "styleRiskLevel": "experimental",
        "stylePrompt": "",
        "backgroundPrompt": "",
        "overrides": {},
    }


def build_preset(
    style_id: str,
    *,
    background_analysis: Optional[Dict[str, Any]] = None,
) -> Tuple[PresetSettings, Dict[str, Any], Dict[str, Any]]:
    config = get_mode_config()
    base_settings = config["baseSettings"]
    style = resolve_style(style_id)
    overrides = style.get("overrides", {})
    if not isinstance(overrides, dict):
        overrides = {}

    checkpoint = str(overrides.get("checkpoint") or base_settings["checkpoint"])
    sampler_name = str(overrides.get("samplerName") or base_settings["samplerName"])
    identity_safety_mode = _safe_bool(
        overrides.get("identitySafetyMode"),
        _safe_bool(base_settings.get("identitySafetyMode"), True),
    )
    experimental_mode = _safe_bool(
        overrides.get("experimentalMode"),
        _safe_bool(base_settings.get("experimentalMode"), False),
    )
    control_weight = _clamp(
        _safe_float(
            overrides.get("softEdgeWeight", overrides.get("controlWeight")),
            base_settings.get("softEdgeWeight", base_settings["controlWeight"]),
        ),
        AI_ART_VENTURE_CONTROL_WEIGHT_MIN,
        AI_ART_VENTURE_CONTROL_WEIGHT_MAX,
    )
    use_ip_adapter = _safe_bool(
        overrides.get("useIpAdapter"),
        _safe_bool(base_settings.get("useIpAdapter"), AI_ART_VENTURE_USE_IP_ADAPTER),
    )
    denoise_raw = _safe_float(overrides.get("denoisingStrength"), base_settings["denoisingStrength"])
    denoise_max = AI_ART_VENTURE_DENOISE_MAX if use_ip_adapter else AI_ART_VENTURE_DENOISE_MAX_NO_IP
    denoise = _clamp(denoise_raw, AI_ART_VENTURE_DENOISE_MIN, denoise_max)
    cfg_scale = _clamp(
        _safe_float(overrides.get("cfgScale"), base_settings["cfgScale"]),
        AI_ART_VENTURE_CFG_MIN,
        AI_ART_VENTURE_CFG_MAX,
    )
    steps = _safe_int(overrides.get("steps"), base_settings["steps"])
    style_prompt = str(style.get("stylePrompt") or "").strip()
    background_prompt = str(style.get("backgroundPrompt") or "").strip()

    background_type = str((background_analysis or {}).get("backgroundType") or "non_plain").strip().lower()
    white_background_ratio = _safe_float(
        (background_analysis or {}).get("whiteBackgroundRatio"),
        0.0,
    )
    plain_background_detected = background_type == "plain" or (
        white_background_ratio > PLAIN_BACKGROUND_WHITE_RATIO_THRESHOLD
    )
    background_type = "plain" if plain_background_detected else "non_plain"

    control_mode = str(base_settings.get("controlMode") or "Balanced").strip() or "Balanced"
    if control_mode.lower() not in {"balanced", "my prompt is more important", "controlnet is more important"}:
        control_mode = "Balanced"

    prompt = str(config.get("basePrompt") or AI_ART_VENTURE_BASE_PROMPT).strip()
    if style_prompt:
        prompt = f"{prompt} {style_prompt}".strip()
    if background_prompt:
        prompt = f"{prompt} Background direction: {background_prompt}.".strip()
    if plain_background_detected:
        prompt = (
            f"{prompt} {AI_ART_VENTURE_BACKGROUND_REPLACEMENT_PLAIN_DIRECTIVE}"
        ).strip()
    else:
        prompt = (
            f"{prompt} {AI_ART_VENTURE_BACKGROUND_REPLACEMENT_NON_PLAIN_DIRECTIVE}"
        ).strip()
    negative_prompt = str(config.get("negativePrompt") or AI_ART_VENTURE_NEGATIVE_PROMPT).strip()
    if AI_ART_VENTURE_PLAIN_BG_NEGATIVE_SUFFIX.lower() not in negative_prompt.lower():
        negative_prompt = f"{negative_prompt}, {AI_ART_VENTURE_PLAIN_BG_NEGATIVE_SUFFIX}".strip()
    if plain_background_detected and AI_ART_VENTURE_STRONG_BG_NEGATIVE_SUFFIX.lower() not in negative_prompt.lower():
        negative_prompt = f"{negative_prompt}, {AI_ART_VENTURE_STRONG_BG_NEGATIVE_SUFFIX}".strip()

    preset = PresetSettings(
        name=AI_ART_VENTURE_MODE_ID,
        control_weight=control_weight,
        denoising_strength=denoise,
        control_mode=control_mode,
        cfg_scale=cfg_scale,
        steps=steps,
        sampler_name=sampler_name,
        prompt=prompt,
        negative_prompt=negative_prompt,
        prompt_mode=AI_ART_VENTURE_MODE_ID,
    )

    generation_settings = {
        "checkpoint": checkpoint,
        "presetName": preset.name,
        "controlNetModel": str(base_settings["controlNetModel"]),
        "controlNetModule": str(base_settings["controlNetModule"]),
        "controlWeight": control_weight,
        "softEdgeWeight": control_weight,
        "denoisingStrength": denoise,
        "controlMode": control_mode,
        "steps": steps,
        "cfgScale": cfg_scale,
        "width": _safe_int(base_settings.get("width"), 768),
        "height": _safe_int(base_settings.get("height"), 768),
        "samplerName": sampler_name,
        "resizeMode": str(base_settings["resizeMode"]),
        "pixelPerfect": bool(base_settings["pixelPerfect"]),
        "guidanceStart": _safe_float(base_settings.get("guidanceStart"), 0.0),
        "guidanceEnd": _safe_float(base_settings.get("guidanceEnd"), 1.0),
        "styleLabel": str(style.get("label") or style.get("id") or AI_ART_VENTURE_DEFAULT_STYLE_ID),
        "styleRiskLevel": str(style.get("styleRiskLevel") or "balanced"),
        "stylePrompt": style_prompt,
        "backgroundPrompt": background_prompt,
        "backgroundType": background_type,
        "plainBackgroundDetected": bool(plain_background_detected),
        "whiteBackgroundRatio": round(float(white_background_ratio), 4),
        "softEdgeWeight": control_weight,
        "finalDenoisingStrength": denoise,
        "finalControlWeight": control_weight,
        "finalPrompt": prompt,
        "prompt": prompt,
        "negativePrompt": negative_prompt,
        "promptUsed": prompt,
        "negativePromptUsed": negative_prompt,
        "identitySafetyMode": bool(identity_safety_mode),
        "useIpAdapter": use_ip_adapter,
        "ipAdapterEnabled": False,
        "ipAdapterType": "none",
        "ipAdapterWarning": "",
        "ipAdapterModule": str(base_settings.get("ipAdapterModule") or "ip-adapter_face_id_plus"),
        "ipAdapterModel": str(base_settings.get("ipAdapterModel") or "ip-adapter-faceid-plusv2_sd15"),
        "ipAdapterWeight": _clamp(
            _safe_float(
                overrides.get("ipAdapterWeight", base_settings.get("ipAdapterWeight")),
                AI_ART_VENTURE_IP_ADAPTER_WEIGHT,
            ),
            AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MIN,
            AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MAX,
        ),
        "identityGuidanceUsed": False,
        "identityTarget": str(base_settings.get("identityTarget") or AI_ART_VENTURE_IDENTITY_TARGET),
        "experimentalMode": bool(experimental_mode),
    }

    metadata = {
        "styleId": str(style.get("id") or AI_ART_VENTURE_DEFAULT_STYLE_ID),
        "styleLabel": str(style.get("label") or style.get("id") or "Style"),
        "styleRiskLevel": str(style.get("styleRiskLevel") or "balanced"),
        "backgroundType": background_type,
        "plainBackgroundDetected": bool(plain_background_detected),
        "whiteBackgroundRatio": round(float(white_background_ratio), 4),
        "finalDenoisingStrength": denoise,
        "finalControlWeight": control_weight,
        "finalPrompt": prompt,
        "prompt": prompt,
        "negativePrompt": negative_prompt,
        "promptUsed": prompt,
        "negativePromptUsed": negative_prompt,
        "identitySafetyMode": bool(identity_safety_mode),
        "useIpAdapter": use_ip_adapter,
        "ipAdapterEnabled": False,
        "ipAdapterType": "none",
        "ipAdapterWarning": "",
        "ipAdapterModule": str(base_settings.get("ipAdapterModule") or "ip-adapter_face_id_plus"),
        "ipAdapterModel": str(base_settings.get("ipAdapterModel") or "ip-adapter-faceid-plusv2_sd15"),
        "ipAdapterWeight": _clamp(
            _safe_float(
                overrides.get("ipAdapterWeight", base_settings.get("ipAdapterWeight")),
                AI_ART_VENTURE_IP_ADAPTER_WEIGHT,
            ),
            AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MIN,
            AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MAX,
        ),
        "identityGuidanceUsed": False,
        "identityTarget": str(base_settings.get("identityTarget") or AI_ART_VENTURE_IDENTITY_TARGET),
        "experimentalMode": bool(experimental_mode),
    }
    return preset, generation_settings, metadata


def get_mode_payload_for_ui() -> Dict[str, Any]:
    config = get_mode_config()
    styles = config.get("styles", [])
    ui_styles = []
    for row in styles:
        if not isinstance(row, dict):
            continue
        ui_styles.append(
            {
                "id": str(row.get("id") or ""),
                "label": str(row.get("label") or ""),
                "styleRiskLevel": str(row.get("styleRiskLevel") or "balanced"),
                "stylePrompt": str(row.get("stylePrompt") or ""),
                "backgroundPrompt": str(row.get("backgroundPrompt") or ""),
                "overrides": row.get("overrides", {}) if isinstance(row.get("overrides"), dict) else {},
            }
        )

    return {
        "modeId": AI_ART_VENTURE_MODE_ID,
        "modeLabel": AI_ART_VENTURE_MODE_LABEL,
        "defaultStyleId": str(config.get("defaultStyleId") or AI_ART_VENTURE_DEFAULT_STYLE_ID),
        "basePrompt": str(config.get("basePrompt") or AI_ART_VENTURE_BASE_PROMPT),
        "negativePrompt": str(config.get("negativePrompt") or AI_ART_VENTURE_NEGATIVE_PROMPT),
        "baseSettings": config.get("baseSettings", {}),
        "styles": ui_styles,
    }
