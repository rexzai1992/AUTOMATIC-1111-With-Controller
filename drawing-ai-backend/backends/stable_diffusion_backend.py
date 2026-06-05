from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from app.config import GENERATION_DEFAULTS, SD_CONFIG
from app.detector import PresetSettings
from app.generator import StableDiffusionError, StableDiffusionGenerator

from .base import (
    BaseGenerationBackend,
    build_error_result,
    build_success_result,
    ensure_directory,
    resolve_negative_prompt,
    resolve_prompt,
)

logger = logging.getLogger(__name__)


class StableDiffusionBackend(BaseGenerationBackend):
    mode = "stable_diffusion"

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        backend_config = dict(config or {})
        base_url = str(backend_config.get("base_url") or SD_CONFIG.base_url).strip() or SD_CONFIG.base_url
        output_dir_raw = backend_config.get("output_dir") or "outputs/stable_diffusion"
        self.output_dir = ensure_directory(output_dir_raw)

        sd_runtime_config = replace(SD_CONFIG, base_url=base_url)
        self.generator = StableDiffusionGenerator(sd_config=sd_runtime_config)

    @staticmethod
    def _to_float(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _to_int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _to_text(value: Any, fallback: str) -> str:
        text = str(value or "").strip()
        return text or fallback

    def _build_preset(
        self,
        prompt: Optional[str],
        negative_prompt: Optional[str],
        settings: Dict[str, Any],
    ) -> PresetSettings:
        resolved_prompt = str(prompt or "").strip()
        if not resolved_prompt:
            resolved_prompt = resolve_prompt(None, settings.get("theme"))
        resolved_negative = str(negative_prompt or "").strip() or resolve_negative_prompt(None)
        return PresetSettings(
            name=self._to_text(settings.get("presetName"), "backend_default"),
            control_weight=self._to_float(settings.get("controlWeight"), 0.7),
            denoising_strength=self._to_float(settings.get("denoisingStrength"), 0.6),
            control_mode=self._to_text(settings.get("controlMode"), "Balanced"),
            cfg_scale=self._to_float(settings.get("cfgScale"), float(GENERATION_DEFAULTS.cfg_scale)),
            steps=self._to_int(settings.get("steps"), int(GENERATION_DEFAULTS.steps)),
            sampler_name=self._to_text(settings.get("samplerName"), str(GENERATION_DEFAULTS.sampler_name)),
            prompt=resolved_prompt,
            negative_prompt=resolved_negative,
            prompt_mode=self._to_text(settings.get("promptMode"), "backend_default"),
        )

    def generate(
        self,
        input_image_path: str | Path,
        prompt: Optional[str],
        negative_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raw_options = dict(options or {})
        settings = raw_options.get("generation_settings") if isinstance(raw_options.get("generation_settings"), dict) else {}

        input_path = Path(input_image_path)
        output_path_raw = raw_options.get("output_path")
        output_path = Path(output_path_raw) if output_path_raw else self.output_dir / f"{uuid4().hex}.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        prompt_text = resolve_prompt(prompt, raw_options.get("theme") or settings.get("theme"))
        negative_text = resolve_negative_prompt(negative_prompt)

        preset = raw_options.get("preset")
        if not isinstance(preset, PresetSettings):
            preset = self._build_preset(prompt_text, negative_text, settings)

        try:
            self.generator.generate_image(
                input_path,
                output_path,
                preset,
                settings,
            )
        except StableDiffusionError as exc:
            return build_error_result(
                mode=self.mode,
                input_image=str(input_path),
                prompt=prompt_text,
                negative_prompt=negative_text,
                error=str(exc),
                metadata={"backend": "stable_diffusion"},
            )
        except Exception as exc:  # pragma: no cover - defensive catch
            logger.exception("Stable Diffusion backend generation failed.")
            return build_error_result(
                mode=self.mode,
                input_image=str(input_path),
                prompt=prompt_text,
                negative_prompt=negative_text,
                error=f"Unexpected Stable Diffusion backend error: {exc}",
                metadata={"backend": "stable_diffusion"},
            )

        return build_success_result(
            mode=self.mode,
            prompt_id=None,
            input_image=str(input_path),
            output_image=str(output_path),
            prompt=prompt_text,
            negative_prompt=negative_text,
            metadata={"backend": "stable_diffusion"},
        )

    def health_check(self) -> Dict[str, Any]:
        try:
            models = self.generator.fetch_models()
            return {
                "mode": self.mode,
                "reachable": True,
                "modelCount": len(models),
            }
        except StableDiffusionError as exc:
            return {
                "mode": self.mode,
                "reachable": False,
                "error": str(exc),
            }
