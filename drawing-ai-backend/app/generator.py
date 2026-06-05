import base64
import logging
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from PIL import Image

from app.ai_art_venture import (
    AI_ART_VENTURE_CONTROLNET_FALLBACK_MODEL,
    AI_ART_VENTURE_CONTROLNET_FALLBACK_MODULE,
    AI_ART_VENTURE_CONTROLNET_PREFERRED_MODEL,
    AI_ART_VENTURE_CONTROLNET_PREFERRED_MODULE,
    AI_ART_VENTURE_DENOISE_MAX_NO_IP,
    AI_ART_VENTURE_IP_ADAPTER_WEIGHT,
    AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MAX,
    AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MIN,
    AI_ART_VENTURE_MODE_ID,
    AI_ART_VENTURE_USE_IP_ADAPTER,
)
from app.config import GENERATION_DEFAULTS, SD_CONFIG, StableDiffusionConfig
from app.detector import PresetSettings


logger = logging.getLogger(__name__)

AI_ART_VENTURE_FACEID_MODULE = "ip-adapter_face_id"
AI_ART_VENTURE_FACEID_PLUS_MODULE = "ip-adapter_face_id_plus"
AI_ART_VENTURE_FACEID_WARNING = "IP-Adapter FaceID not detected. Face/person identity may change."


class StableDiffusionError(Exception):
    """Base exception for Stable Diffusion communication failures."""


class StableDiffusionUnavailableError(StableDiffusionError):
    """Raised when Stable Diffusion WebUI is unreachable."""


class StableDiffusionRequestError(StableDiffusionError):
    """Raised for bad responses from Stable Diffusion API."""


class StableDiffusionGenerator:
    def __init__(self, sd_config: Optional[StableDiffusionConfig] = None) -> None:
        self.session = requests.Session()
        self.sd_config = sd_config or SD_CONFIG

    def _url(self, endpoint: str) -> str:
        return f"{self.sd_config.base_url}{endpoint}"

    def fetch_models(self) -> List[dict]:
        try:
            response = self.session.get(
                self._url(self.sd_config.models_endpoint),
                timeout=self.sd_config.connect_timeout_seconds,
            )
            self._raise_for_status(response, f"Loading {self.sd_config.models_endpoint}")
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
                f"Stable Diffusion WebUI is not reachable at {self.sd_config.base_url}."
            ) from exc

    def set_checkpoint(self, checkpoint: Optional[str] = None) -> None:
        payload = {"sd_model_checkpoint": str(checkpoint or self.sd_config.checkpoint)}
        try:
            response = self.session.post(
                self._url(self.sd_config.options_endpoint),
                json=payload,
                timeout=self.sd_config.connect_timeout_seconds,
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

    def fetch_controlnet_models(self) -> List[str]:
        endpoints = ("/controlnet/model_list", "/sdapi/v1/controlnet/model_list")
        last_error: Optional[Exception] = None
        for endpoint in endpoints:
            try:
                response = self.session.get(
                    self._url(endpoint),
                    timeout=self.sd_config.connect_timeout_seconds,
                )
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    model_list = payload.get("model_list")
                    if isinstance(model_list, list):
                        return [str(item) for item in model_list if str(item).strip()]
            except requests.RequestException as exc:
                last_error = exc
                continue
            except ValueError as exc:
                last_error = exc
                continue

        if last_error is not None:
            logger.warning("Unable to fetch ControlNet model list: %s", last_error)
        return []

    def fetch_controlnet_modules(self) -> List[str]:
        endpoints = ("/controlnet/module_list", "/sdapi/v1/controlnet/module_list")
        last_error: Optional[Exception] = None
        for endpoint in endpoints:
            try:
                response = self.session.get(
                    self._url(endpoint),
                    timeout=self.sd_config.connect_timeout_seconds,
                )
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    module_list = payload.get("module_list")
                    if isinstance(module_list, list):
                        return [str(item) for item in module_list if str(item).strip()]
            except requests.RequestException as exc:
                last_error = exc
                continue
            except ValueError as exc:
                last_error = exc
                continue

        if last_error is not None:
            logger.warning("Unable to fetch ControlNet module list: %s", last_error)
        return []

    @staticmethod
    def _match_controlnet_model(available_models: List[str], requested_model: str) -> Optional[str]:
        requested = str(requested_model or "").strip()
        if not requested:
            return None
        requested_lower = requested.lower()
        for model_name in available_models:
            if str(model_name).strip().lower() == requested_lower:
                return str(model_name)
        for model_name in available_models:
            normalized = str(model_name).strip().lower()
            if normalized.startswith(f"{requested_lower} ") or normalized.startswith(f"{requested_lower}["):
                return str(model_name)
        return None

    def _resolve_controlnet_model(self, requested_model: str, fallback_model: Optional[str] = None) -> str:
        requested = str(requested_model or "").strip()
        if not requested:
            return str(self.sd_config.controlnet_model)
        requested_lower = requested.lower()

        available_models = self.fetch_controlnet_models()
        if not available_models:
            return requested

        matched_requested = self._match_controlnet_model(available_models, requested)
        if matched_requested:
            return matched_requested

        if fallback_model:
            matched_fallback = self._match_controlnet_model(available_models, fallback_model)
            if matched_fallback:
                logger.warning(
                    "ControlNet model '%s' missing. Falling back to '%s'.",
                    requested,
                    matched_fallback,
                )
                return matched_fallback

        if "canny" in requested_lower:
            fallback = str(self.sd_config.controlnet_model)
            logger.warning(
                "ControlNet model '%s' missing. Falling back to '%s'.",
                requested,
                fallback,
            )
            return fallback

        return requested

    @staticmethod
    def _match_by_keywords(available: List[str], keywords: List[str]) -> Optional[str]:
        normalized = [str(item).strip() for item in available if str(item).strip()]
        lowered = [item.lower() for item in normalized]
        for keyword in keywords:
            token = str(keyword or "").strip().lower()
            if not token:
                continue
            for index, model_name in enumerate(lowered):
                if token in model_name:
                    return normalized[index]
        return None

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, float(value)))

    def _resolve_ai_art_venture_controlnet(
        self,
        settings: Dict[str, object],
    ) -> tuple[str, str]:
        requested_model = str(
            settings.get("controlNetModel") or AI_ART_VENTURE_CONTROLNET_PREFERRED_MODEL
        )
        requested_module = str(
            settings.get("controlNetModule") or AI_ART_VENTURE_CONTROLNET_PREFERRED_MODULE
        )
        resolved_model = self._resolve_controlnet_model(
            requested_model,
            fallback_model=AI_ART_VENTURE_CONTROLNET_FALLBACK_MODEL,
        )
        resolved_lower = resolved_model.lower()
        module_lower = requested_module.lower()

        if "scribble" in resolved_lower or "scribble" in module_lower:
            logger.warning(
                "AI Art Venture blocked Scribble ControlNet request (%s / %s). "
                "Switching to SoftEdge/Canny.",
                requested_model,
                requested_module,
            )
            resolved_model = self._resolve_controlnet_model(
                AI_ART_VENTURE_CONTROLNET_PREFERRED_MODEL,
                fallback_model=AI_ART_VENTURE_CONTROLNET_FALLBACK_MODEL,
            )
            resolved_lower = resolved_model.lower()

        if "softedge" in resolved_lower:
            resolved_module = AI_ART_VENTURE_CONTROLNET_PREFERRED_MODULE
        elif "canny" in resolved_lower:
            resolved_module = AI_ART_VENTURE_CONTROLNET_FALLBACK_MODULE
        else:
            resolved_model = self._resolve_controlnet_model(
                AI_ART_VENTURE_CONTROLNET_PREFERRED_MODEL,
                fallback_model=AI_ART_VENTURE_CONTROLNET_FALLBACK_MODEL,
            )
            if "softedge" in resolved_model.lower():
                resolved_module = AI_ART_VENTURE_CONTROLNET_PREFERRED_MODULE
            else:
                resolved_module = AI_ART_VENTURE_CONTROLNET_FALLBACK_MODULE

        return resolved_model, resolved_module

    def get_ai_art_venture_ip_adapter_status(self) -> Dict[str, object]:
        modules = [row.lower() for row in self.fetch_controlnet_modules()]
        available_models = self.fetch_controlnet_models()
        module = ""
        module_type = "none"
        model = ""
        warning = ""

        if AI_ART_VENTURE_FACEID_PLUS_MODULE in modules:
            module = AI_ART_VENTURE_FACEID_PLUS_MODULE
            module_type = "faceid_plus"
            model = self._match_by_keywords(
                available_models,
                [
                    "ip-adapter-faceid-plusv2_sd15",
                    "ip-adapter-faceid-plus_sd15",
                    "ip-adapter-faceid-plus",
                    "ip-adapter-faceid",
                ],
            ) or ""
        elif AI_ART_VENTURE_FACEID_MODULE in modules:
            module = AI_ART_VENTURE_FACEID_MODULE
            module_type = "faceid"
            model = self._match_by_keywords(
                available_models,
                [
                    "ip-adapter-faceid_sd15",
                    "ip-adapter-faceid-portrait_sd15",
                    "ip-adapter-faceid",
                ],
            ) or ""

        enabled = bool(module and model)
        if not enabled:
            warning = AI_ART_VENTURE_FACEID_WARNING

        return {
            "enabled": enabled,
            "type": module_type if enabled else "none",
            "module": module if enabled else "",
            "model": model if enabled else "",
            "warning": warning,
        }

    def _resolve_ai_art_venture_ip_adapter(
        self,
        *,
        requested: bool,
        weight: float,
        image_b64: str,
        resize_mode: str,
        control_mode: str,
        guidance_start: float,
        guidance_end: float,
        pixel_perfect: bool,
    ) -> tuple[Optional[Dict[str, object]], Dict[str, object]]:
        status: Dict[str, object] = {
            "ipAdapterEnabled": False,
            "ipAdapterType": "none",
            "ipAdapterWeight": round(weight, 4),
            "identityGuidanceUsed": False,
            "ipAdapterWarning": "",
        }
        if not requested:
            return None, status

        modules = [row.lower() for row in self.fetch_controlnet_modules()]
        available_models = self.fetch_controlnet_models()
        if not modules:
            logger.warning("IP-Adapter requested but ControlNet module list is unavailable.")
            status["ipAdapterWarning"] = AI_ART_VENTURE_FACEID_WARNING
            return None, status
        if not available_models:
            logger.warning("IP-Adapter requested but ControlNet model list is unavailable.")
            status["ipAdapterWarning"] = AI_ART_VENTURE_FACEID_WARNING
            return None, status

        module = ""
        module_type = "none"
        if AI_ART_VENTURE_FACEID_PLUS_MODULE in modules:
            module = AI_ART_VENTURE_FACEID_PLUS_MODULE
            module_type = "faceid_plus"
        elif AI_ART_VENTURE_FACEID_MODULE in modules:
            module = AI_ART_VENTURE_FACEID_MODULE
            module_type = "faceid"
        else:
            logger.warning(
                "IP-Adapter requested but FaceID module not found. "
                "Expected '%s' or '%s'.",
                AI_ART_VENTURE_FACEID_PLUS_MODULE,
                AI_ART_VENTURE_FACEID_MODULE,
            )
            status["ipAdapterWarning"] = AI_ART_VENTURE_FACEID_WARNING
            return None, status

        model_priority: List[str]
        if module_type == "faceid_plus":
            model_priority = [
                "ip-adapter-faceid-plusv2_sd15",
                "ip-adapter-faceid-plus_sd15",
                "ip-adapter-faceid-plus",
                "ip-adapter-faceid",
            ]
        else:
            model_priority = [
                "ip-adapter-faceid_sd15",
                "ip-adapter-faceid-portrait_sd15",
                "ip-adapter-faceid",
            ]

        model = self._match_by_keywords(available_models, model_priority)
        if not model:
            logger.warning("IP-Adapter FaceID model not found in available ControlNet models.")
            status["ipAdapterWarning"] = AI_ART_VENTURE_FACEID_WARNING
            return None, status

        unit = {
            "enabled": True,
            "image": image_b64,
            "module": module,
            "model": model,
            "weight": round(weight, 4),
            "resize_mode": resize_mode,
            "control_mode": control_mode,
            "guidance_start": guidance_start,
            "guidance_end": guidance_end,
            "pixel_perfect": pixel_perfect,
        }
        status.update(
            {
                "ipAdapterEnabled": True,
                "ipAdapterType": module_type,
                "ipAdapterModel": model,
                "ipAdapterModule": module,
                "identityGuidanceUsed": True,
                "ipAdapterWarning": "",
            }
        )
        return unit, status

    @staticmethod
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

    def generate_image(
        self,
        input_image_path: Path,
        output_image_path: Path,
        preset: PresetSettings,
        generation_settings: Dict[str, object] | None = None,
    ) -> Path:
        preset_data: Dict[str, object] = asdict(preset)
        settings = generation_settings or {}
        checkpoint = str(settings.get("checkpoint") or self.sd_config.checkpoint)

        self.fetch_models()
        self.set_checkpoint(checkpoint)

        steps = int(settings.get("steps", preset_data.get("steps", GENERATION_DEFAULTS.steps)))
        cfg_scale = float(settings.get("cfgScale", preset_data.get("cfg_scale", GENERATION_DEFAULTS.cfg_scale)))
        width = int(settings.get("width", GENERATION_DEFAULTS.width))
        height = int(settings.get("height", GENERATION_DEFAULTS.height))
        sampler_name = str(settings.get("samplerName", preset_data.get("sampler_name", GENERATION_DEFAULTS.sampler_name)))
        control_weight = float(settings.get("controlWeight", preset_data["control_weight"]))
        denoising_strength = float(settings.get("denoisingStrength", preset_data["denoising_strength"]))
        control_mode = str(settings.get("controlMode", preset_data["control_mode"]))
        generation_mode = str(settings.get("generationMode") or preset_data.get("prompt_mode") or "").strip().lower()
        is_ai_art_venture = generation_mode == AI_ART_VENTURE_MODE_ID
        requested_controlnet_model = str(
            settings.get("controlNetModel") or self.sd_config.controlnet_model
        )
        requested_controlnet_module = str(
            settings.get("controlNetModule") or self.sd_config.controlnet_module
        )
        if is_ai_art_venture:
            resolved_controlnet_model, controlnet_module = self._resolve_ai_art_venture_controlnet(settings)
        else:
            resolved_controlnet_model = self._resolve_controlnet_model(requested_controlnet_model)
            controlnet_module = requested_controlnet_module
            if (
                "canny" in requested_controlnet_model.lower()
                and resolved_controlnet_model == str(self.sd_config.controlnet_model)
            ):
                controlnet_module = str(self.sd_config.controlnet_module)

        if isinstance(settings, dict):
            settings["controlNetModel"] = resolved_controlnet_model
            settings["controlNetModule"] = controlnet_module
            if is_ai_art_venture:
                settings["softEdgeWeight"] = round(control_weight, 4)

        resize_mode = str(settings.get("resizeMode") or GENERATION_DEFAULTS.resize_mode)
        guidance_start = float(settings.get("guidanceStart", GENERATION_DEFAULTS.guidance_start))
        guidance_end = float(settings.get("guidanceEnd", GENERATION_DEFAULTS.guidance_end))
        pixel_perfect = self._safe_bool(settings.get("pixelPerfect"), GENERATION_DEFAULTS.pixel_perfect)

        base64_image = self._encode_image_base64(input_image_path)
        controlnet_args: List[Dict[str, object]] = [
            {
                "enabled": True,
                "image": base64_image,
                "module": controlnet_module,
                "model": resolved_controlnet_model,
                "weight": control_weight,
                "resize_mode": resize_mode,
                "control_mode": control_mode,
                "guidance_start": guidance_start,
                "guidance_end": guidance_end,
                "pixel_perfect": pixel_perfect,
            }
        ]

        if is_ai_art_venture:
            use_ip_adapter = self._safe_bool(settings.get("useIpAdapter"), AI_ART_VENTURE_USE_IP_ADAPTER)
            try:
                raw_ip_weight = float(settings.get("ipAdapterWeight", AI_ART_VENTURE_IP_ADAPTER_WEIGHT))
            except (TypeError, ValueError):
                raw_ip_weight = float(AI_ART_VENTURE_IP_ADAPTER_WEIGHT)
            ip_weight = self._clamp(
                raw_ip_weight,
                AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MIN,
                AI_ART_VENTURE_IP_ADAPTER_WEIGHT_MAX,
            )
            ip_unit, ip_status = self._resolve_ai_art_venture_ip_adapter(
                requested=use_ip_adapter,
                weight=ip_weight,
                image_b64=base64_image,
                resize_mode=resize_mode,
                control_mode="Balanced",
                guidance_start=0.0,
                guidance_end=1.0,
                pixel_perfect=pixel_perfect,
            )
            if ip_unit is not None:
                controlnet_args.append(ip_unit)
            elif denoising_strength > AI_ART_VENTURE_DENOISE_MAX_NO_IP:
                denoising_strength = AI_ART_VENTURE_DENOISE_MAX_NO_IP
                settings["denoisingStrength"] = denoising_strength
            settings.update(ip_status)

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
                "ControlNet": {
                    "args": controlnet_args
                }
            },
        }

        logger.info("Submitting generation request to Stable Diffusion with preset=%s", preset_data["name"])
        logger.info("Detected preset: %s", preset_data["name"])
        logger.info("Prompt mode: %s", preset_data["prompt_mode"])
        try:
            response = self.session.post(
                self._url(self.sd_config.img2img_endpoint),
                json=payload,
                timeout=self.sd_config.generate_timeout_seconds,
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
        helpful_hint = ""
        request_url = str(getattr(getattr(response, "request", None), "url", "") or "")
        if response.status_code == 404 and "/sdapi/v1/" in request_url:
            helpful_hint = (
                " Endpoint missing. The server on this port is running, but it does not expose "
                "Stable Diffusion sdapi routes. Start WebUI with --api or point backend to the correct server."
            )
        raise StableDiffusionRequestError(
            f"{context} failed with status {response.status_code}: {snippet}{helpful_hint}"
        )
