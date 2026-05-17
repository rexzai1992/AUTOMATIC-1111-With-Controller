import base64
import logging
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from typing import Dict, List

import requests
from PIL import Image

from app.config import GENERATION_DEFAULTS, SD_CONFIG
from app.detector import PresetSettings


logger = logging.getLogger(__name__)


class StableDiffusionError(Exception):
    """Base exception for Stable Diffusion communication failures."""


class StableDiffusionUnavailableError(StableDiffusionError):
    """Raised when Stable Diffusion WebUI is unreachable."""


class StableDiffusionRequestError(StableDiffusionError):
    """Raised for bad responses from Stable Diffusion API."""


class StableDiffusionGenerator:
    def __init__(self) -> None:
        self.session = requests.Session()

    def _url(self, endpoint: str) -> str:
        return f"{SD_CONFIG.base_url}{endpoint}"

    def fetch_models(self) -> List[dict]:
        try:
            response = self.session.get(
                self._url(SD_CONFIG.models_endpoint),
                timeout=SD_CONFIG.connect_timeout_seconds,
            )
            response.raise_for_status()
            models = response.json()
            if not isinstance(models, list):
                raise StableDiffusionRequestError(
                    "Unexpected response format from /sdapi/v1/sd-models."
                )
            return models
        except requests.Timeout as exc:
            raise StableDiffusionUnavailableError(
                "Stable Diffusion API timeout while checking available models."
            ) from exc
        except requests.RequestException as exc:
            raise StableDiffusionUnavailableError(
                "Stable Diffusion WebUI is not reachable at http://127.0.0.1:7860."
            ) from exc

    def set_checkpoint(self) -> None:
        payload = {"sd_model_checkpoint": SD_CONFIG.checkpoint}
        try:
            response = self.session.post(
                self._url(SD_CONFIG.options_endpoint),
                json=payload,
                timeout=SD_CONFIG.connect_timeout_seconds,
            )
            self._raise_for_status(response, "Setting checkpoint")
        except requests.Timeout as exc:
            raise StableDiffusionUnavailableError(
                "Timed out while setting Stable Diffusion checkpoint."
            ) from exc
        except requests.RequestException as exc:
            raise StableDiffusionUnavailableError(
                "Failed to connect to Stable Diffusion while setting checkpoint."
            ) from exc

    def generate_image(
        self,
        input_image_path: Path,
        output_image_path: Path,
        preset: PresetSettings,
        generation_settings: Dict[str, object] | None = None,
    ) -> Path:
        self.fetch_models()
        self.set_checkpoint()

        preset_data: Dict[str, object] = asdict(preset)
        settings = generation_settings or {}
        steps = int(settings.get("steps", preset_data.get("steps", GENERATION_DEFAULTS.steps)))
        cfg_scale = float(settings.get("cfgScale", preset_data.get("cfg_scale", GENERATION_DEFAULTS.cfg_scale)))
        width = int(settings.get("width", GENERATION_DEFAULTS.width))
        height = int(settings.get("height", GENERATION_DEFAULTS.height))
        sampler_name = str(settings.get("samplerName", preset_data.get("sampler_name", GENERATION_DEFAULTS.sampler_name)))
        control_weight = float(settings.get("controlWeight", preset_data["control_weight"]))
        denoising_strength = float(settings.get("denoisingStrength", preset_data["denoising_strength"]))
        control_mode = str(settings.get("controlMode", preset_data["control_mode"]))

        base64_image = self._encode_image_base64(input_image_path)
        payload = {
            "init_images": [base64_image],
            "prompt": preset_data["prompt"],
            "negative_prompt": preset_data["negative_prompt"],
            "steps": steps,
            "cfg_scale": cfg_scale,
            "denoising_strength": denoising_strength,
            "width": width,
            "height": height,
            "sampler_name": sampler_name,
            "alwayson_scripts": {
                "controlnet": {
                    "args": [
                        {
                            "enabled": True,
                            "image": base64_image,
                            "module": SD_CONFIG.controlnet_module,
                            "model": SD_CONFIG.controlnet_model,
                            "weight": control_weight,
                            "resize_mode": GENERATION_DEFAULTS.resize_mode,
                            "control_mode": control_mode,
                            "guidance_start": GENERATION_DEFAULTS.guidance_start,
                            "guidance_end": GENERATION_DEFAULTS.guidance_end,
                            "pixel_perfect": GENERATION_DEFAULTS.pixel_perfect,
                        }
                    ]
                }
            },
        }

        logger.info("Submitting generation request to Stable Diffusion with preset=%s", preset_data["name"])
        logger.info("Detected preset: %s", preset_data["name"])
        logger.info("Prompt mode: %s", preset_data["prompt_mode"])
        try:
            response = self.session.post(
                self._url(SD_CONFIG.img2img_endpoint),
                json=payload,
                timeout=SD_CONFIG.generate_timeout_seconds,
            )
            self._raise_for_status(response, "Image generation")
        except requests.Timeout as exc:
            raise StableDiffusionUnavailableError(
                "Stable Diffusion request timed out during img2img generation."
            ) from exc
        except requests.RequestException as exc:
            raise StableDiffusionUnavailableError(
                "Failed to connect to Stable Diffusion during img2img generation."
            ) from exc

        body = response.json()
        images = body.get("images", [])
        if not images:
            raise StableDiffusionRequestError(
                "Stable Diffusion returned no images in the response payload."
            )

        self._save_base64_png(images[0], output_image_path)
        logger.info("Generated image saved: %s", output_image_path)
        return output_image_path

    @staticmethod
    def _encode_image_base64(image_path: Path) -> str:
        raw_bytes = image_path.read_bytes()
        return base64.b64encode(raw_bytes).decode("utf-8")

    @staticmethod
    def _save_base64_png(base64_content: str, output_path: Path) -> None:
        normalized = base64_content.split(",", 1)[-1]
        image_bytes = base64.b64decode(normalized)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.open(BytesIO(image_bytes))
        image.save(output_path, format="PNG")

    @staticmethod
    def _raise_for_status(response: requests.Response, context: str) -> None:
        if response.ok:
            return

        detail = response.text.strip()
        try:
            detail = str(response.json())
        except ValueError:
            pass

        snippet = detail[:500] if detail else "No response body."
        raise StableDiffusionRequestError(
            f"{context} failed with status {response.status_code}: {snippet}"
        )
