from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_POSITIVE_PROMPT = (
    "Enhance this child\u2019s simple drawing into a beautiful colorful storybook illustration. "
    "Preserve the original drawing shape, pose, composition, and main subject. "
    "Cute, magical, clean, kid-friendly, vibrant, high quality, soft lighting, playful fantasy background."
)

DEFAULT_NEGATIVE_PROMPT = (
    "scary, creepy, horror, ugly, distorted, bad anatomy, extra limbs, extra eyes, "
    "text, watermark, logo, blurry, low quality, messy, dark"
)

THEME_PROMPTS = {
    "fantasy": "magical fantasy background, glowing colors",
    "underwater": "underwater world, coral reef, bubbles, colorful fish",
    "jungle": "lush jungle background, tropical plants, soft sunlight",
    "space": "cute outer space background, stars, planets, colorful nebula",
    "ocean": "bright ocean adventure background, waves, islands, sunshine",
}


class GenerationBackendError(RuntimeError):
    """Raised for backend adapter errors that should be surfaced to users."""


class BaseGenerationBackend:
    mode = "unknown"

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = dict(config or {})

    def generate(
        self,
        input_image_path: str | Path,
        prompt: Optional[str],
        negative_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def health_check(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "reachable": False,
            "error": "Health check is not implemented for this backend.",
        }


def ensure_directory(path_value: str | Path) -> Path:
    path = Path(path_value)
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(name: str, *, fallback: str = "image.png") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", str(name or "").strip())
    cleaned = cleaned.strip("._")
    return cleaned or fallback


def resolve_seed(raw_value: Any) -> int:
    try:
        seed = int(raw_value)
    except (TypeError, ValueError):
        seed = -1
    if seed == -1:
        return random.randint(1, 2_147_483_647)
    return seed


def resolve_prompt(prompt: Optional[str], theme: Optional[str]) -> str:
    final_prompt = str(prompt or "").strip() or DEFAULT_POSITIVE_PROMPT
    theme_key = str(theme or "").strip().lower()
    theme_suffix = THEME_PROMPTS.get(theme_key)
    if theme_suffix:
        final_prompt = f"{final_prompt} {theme_suffix}".strip()
    return final_prompt


def resolve_negative_prompt(negative_prompt: Optional[str]) -> str:
    return str(negative_prompt or "").strip() or DEFAULT_NEGATIVE_PROMPT


def build_success_result(
    *,
    mode: str,
    prompt_id: Optional[str],
    input_image: str,
    output_image: str,
    prompt: str,
    negative_prompt: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "success": True,
        "mode": mode,
        "prompt_id": prompt_id,
        "input_image": input_image,
        "output_image": output_image,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "error": None,
        "metadata": metadata or {},
    }


def build_error_result(
    *,
    mode: str,
    input_image: str,
    prompt: str,
    negative_prompt: str,
    error: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "success": False,
        "mode": mode,
        "prompt_id": None,
        "input_image": input_image,
        "output_image": None,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "error": str(error or "Unknown generation error."),
        "metadata": metadata or {},
    }
