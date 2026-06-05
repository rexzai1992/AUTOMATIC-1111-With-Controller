from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import BASE_DIR

DEFAULT_COMFY_PRESET_PATH = BASE_DIR / "config" / "comfy_prompt_presets.json"
FALLBACK_NEGATIVE_PROMPT = (
    "scary, creepy, horror, ugly, distorted face, bad anatomy, extra fingers, extra limbs, "
    "extra eyes, blurry, low quality, messy, dark, text, watermark, logo"
)


def _resolve_preset_path(path_value: Optional[str | Path]) -> Path:
    if path_value is None:
        return DEFAULT_COMFY_PRESET_PATH
    path = Path(str(path_value).strip())
    if path.is_absolute():
        return path
    return BASE_DIR / path


def _normalize_preset_record(raw_preset: Any, index: int) -> Dict[str, str]:
    if not isinstance(raw_preset, dict):
        raise ValueError(f"Invalid preset record at index {index}: expected object.")

    preset_id = str(raw_preset.get("id") or "").strip()
    name = str(raw_preset.get("name") or "").strip()
    category = str(raw_preset.get("category") or "").strip()
    prompt = str(raw_preset.get("prompt") or "").strip()

    if not preset_id:
        raise ValueError(f"Invalid preset record at index {index}: missing 'id'.")
    if not name:
        raise ValueError(f"Invalid preset record at index {index}: missing 'name'.")
    if not category:
        raise ValueError(f"Invalid preset record at index {index}: missing 'category'.")
    if not prompt:
        raise ValueError(f"Invalid preset record at index {index}: missing 'prompt'.")

    return {
        "id": preset_id,
        "name": name,
        "category": category,
        "prompt": prompt,
    }


def load_comfy_prompt_presets(path_value: Optional[str | Path] = None) -> Dict[str, Any]:
    preset_path = _resolve_preset_path(path_value)
    if not preset_path.is_file():
        raise FileNotFoundError(f"Comfy prompt preset file not found: {preset_path}")

    try:
        payload = json.loads(preset_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in Comfy prompt preset file: {preset_path}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Comfy prompt preset file must be a JSON object.")

    negative_prompt = str(payload.get("negative_prompt") or "").strip() or FALLBACK_NEGATIVE_PROMPT
    presets_raw = payload.get("presets")
    if not isinstance(presets_raw, list) or not presets_raw:
        raise ValueError("Comfy prompt preset file is invalid: 'presets' must be a non-empty array.")

    normalized_presets: List[Dict[str, str]] = []
    seen_ids = set()
    for index, raw in enumerate(presets_raw):
        preset = _normalize_preset_record(raw, index)
        preset_id = preset["id"]
        if preset_id in seen_ids:
            raise ValueError(f"Duplicate preset id detected: {preset_id}")
        seen_ids.add(preset_id)
        normalized_presets.append(preset)

    return {
        "success": True,
        "negative_prompt": negative_prompt,
        "presets": normalized_presets,
        "path": str(preset_path),
    }


def get_random_comfy_preset(
    path_value: Optional[str | Path] = None,
    category: Optional[str] = None,
) -> Dict[str, str]:
    payload = load_comfy_prompt_presets(path_value)
    presets = payload.get("presets") if isinstance(payload.get("presets"), list) else []
    category_filter = str(category or "").strip().lower()
    if category_filter:
        presets = [
            preset
            for preset in presets
            if isinstance(preset, dict)
            and str(preset.get("category") or "").strip().lower() == category_filter
        ]
    if not presets:
        raise ValueError("No Comfy prompt presets available.")
    selected = random.choice(presets)
    return dict(selected)


def get_comfy_preset_by_id(preset_id: str, path_value: Optional[str | Path] = None) -> Dict[str, str]:
    target = str(preset_id or "").strip()
    if not target:
        raise ValueError("style_preset id is required.")

    payload = load_comfy_prompt_presets(path_value)
    presets = payload.get("presets") if isinstance(payload.get("presets"), list) else []
    for preset in presets:
        if not isinstance(preset, dict):
            continue
        if str(preset.get("id") or "") == target:
            return dict(preset)

    raise KeyError(f"Comfy style preset not found: {target}")


def resolve_comfy_preset(
    style_preset: Optional[str],
    path_value: Optional[str | Path] = None,
    *,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    payload = load_comfy_prompt_presets(path_value)
    presets = payload.get("presets") if isinstance(payload.get("presets"), list) else []
    if not presets:
        raise ValueError("No Comfy prompt presets available.")
    category_filter = str(category or "").strip().lower()

    requested = str(style_preset or "").strip()
    if not requested:
        requested = "random"

    if requested.lower() == "random":
        selected_pool = presets
        if category_filter:
            selected_pool = [
                preset
                for preset in presets
                if isinstance(preset, dict)
                and str(preset.get("category") or "").strip().lower() == category_filter
            ]
            if not selected_pool:
                raise ValueError(
                    f"No Comfy prompt presets found for category: {category_filter}"
                )
        selected = random.choice(selected_pool)
        return {
            "requested_style_preset": "random",
            "selected_preset": dict(selected),
            "negative_prompt": str(payload.get("negative_prompt") or FALLBACK_NEGATIVE_PROMPT),
            "is_random": True,
        }

    selected = get_comfy_preset_by_id(requested, path_value)
    return {
        "requested_style_preset": requested,
        "selected_preset": dict(selected),
        "negative_prompt": str(payload.get("negative_prompt") or FALLBACK_NEGATIVE_PROMPT),
        "is_random": False,
    }
