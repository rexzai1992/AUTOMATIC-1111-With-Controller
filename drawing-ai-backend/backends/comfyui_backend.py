from __future__ import annotations

import copy
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import requests

from app.config import BASE_DIR
from utils.prompt_presets import resolve_comfy_preset

from .base import (
    BaseGenerationBackend,
    GenerationBackendError,
    build_error_result,
    build_success_result,
    ensure_directory,
    resolve_negative_prompt,
    resolve_prompt,
    resolve_seed,
    safe_filename,
)

logger = logging.getLogger(__name__)

WORKFLOW_PROMPT_FALLBACK = "Change the style of the image to a 3d cartoon style. and enhance the backround"
RECOMMENDED_DEFAULT_PROMPT = (
    "Transform this child’s simple drawing into a beautiful 3D cartoon artwork. Preserve the original drawing shape, "
    "pose, composition, and main subject. Make it cute, colorful, clean, magical, kid-friendly, high quality, with "
    "an enhanced playful background. Do not change the main subject too much."
)
RECOMMENDED_DEFAULT_NEGATIVE_PROMPT = (
    "scary, creepy, horror, ugly, distorted, bad anatomy, extra limbs, extra eyes, text, watermark, logo, blurry, "
    "low quality, messy, dark"
)
NODE_LABELS = {
    "load_image": "Load Image",
    "positive_prompt": "Positive Prompt",
    "negative_prompt": "Negative Prompt",
    "ksampler": "KSampler",
    "save_image": "Save Image",
    "image_scale": "Image Scale",
}


class ComfyUIBackend(BaseGenerationBackend):
    mode = "comfyui"

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        backend_config = dict(config or {})

        self.base_url = str(backend_config.get("base_url") or "http://127.0.0.1:8188").rstrip("/")
        self.workflow_path_configured = str(
            backend_config.get("workflow_path") or "workflows/Ai Genius.json"
        ).strip() or "workflows/Ai Genius.json"
        self.workflow_path = self._resolve_path(self.workflow_path_configured)
        self.workflow_path_metadata = self._to_metadata_path(self.workflow_path)
        self.output_dir = ensure_directory(self._resolve_path(backend_config.get("output_dir") or "outputs/comfyui"))

        self.node_ids = backend_config.get("node_ids") if isinstance(backend_config.get("node_ids"), dict) else {}
        self.defaults = backend_config.get("defaults") if isinstance(backend_config.get("defaults"), dict) else {}

        self.connect_timeout = float(backend_config.get("connect_timeout_seconds") or 10)
        self.request_timeout = float(backend_config.get("request_timeout_seconds") or 60)
        self.generation_timeout = float(backend_config.get("generation_timeout_seconds") or 300)
        self.poll_interval = float(backend_config.get("poll_interval_seconds") or 1.0)

        self.session = requests.Session()

    @staticmethod
    def _resolve_path(value: Any) -> Path:
        path = Path(str(value or "").strip())
        if path.is_absolute():
            return path
        return BASE_DIR / path

    @staticmethod
    def _to_metadata_path(path: Path) -> str:
        try:
            relative = path.resolve().relative_to(BASE_DIR.resolve())
            return relative.as_posix()
        except Exception:
            return str(path)

    @staticmethod
    def _to_int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _to_float(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _is_placeholder(value: Any) -> bool:
        text = str(value or "").strip()
        if not text:
            return True
        return text.upper() == "CHANGE_ME"

    def _required_node_id(self, key: str) -> str:
        node_id = self.node_ids.get(key)
        if self._is_placeholder(node_id):
            label = NODE_LABELS.get(key, key)
            raise GenerationBackendError(
                f"ComfyUI node ID is missing for '{label}' ({key}) in config.json."
            )
        return str(node_id)

    def _optional_node_id(self, key: str) -> Optional[str]:
        node_id = self.node_ids.get(key)
        if self._is_placeholder(node_id):
            return None
        return str(node_id)

    def _node_from_workflow(self, workflow: Dict[str, Any], node_id: str, node_label: str) -> Dict[str, Any]:
        node = workflow.get(str(node_id))
        if not isinstance(node, dict):
            raise GenerationBackendError(
                f"ComfyUI node ID '{node_id}' for '{node_label}' was not found in workflow {self.workflow_path}."
            )
        if not isinstance(node.get("inputs"), dict):
            node["inputs"] = {}
        return node

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base_url}{endpoint}"
        timeout = kwargs.pop("timeout", self.request_timeout)
        if not isinstance(timeout, tuple):
            timeout = (self.connect_timeout, float(timeout))
        try:
            response = self.session.request(method=method, url=url, timeout=timeout, **kwargs)
        except requests.Timeout as exc:
            raise GenerationBackendError(f"ComfyUI request timed out: {method} {endpoint}") from exc
        except requests.RequestException as exc:
            raise GenerationBackendError(
                f"ComfyUI is not reachable at {self.base_url}. Please make sure ComfyUI is running."
            ) from exc

        if response.ok:
            return response

        detail = response.text.strip()
        try:
            detail = str(response.json())
        except ValueError:
            pass
        raise GenerationBackendError(
            f"ComfyUI request failed ({method} {endpoint}) status={response.status_code}: {detail[:500]}"
        )

    def upload_image(self, input_image_path: Path) -> str:
        if not input_image_path.is_file():
            raise GenerationBackendError(f"Input image not found: {input_image_path}")

        upload_name = safe_filename(f"upload_{uuid4().hex}{input_image_path.suffix or '.png'}")
        with input_image_path.open("rb") as image_file:
            response = self._request(
                "POST",
                "/upload/image",
                files={"image": (upload_name, image_file)},
                data={"overwrite": "true"},
                timeout=self.request_timeout,
            )

        try:
            payload = response.json()
        except ValueError:
            payload = {}

        returned_name = str(payload.get("name") or payload.get("filename") or "").strip()
        return returned_name or upload_name

    def load_workflow(self) -> Dict[str, Any]:
        if not self.workflow_path.exists():
            raise GenerationBackendError(f"ComfyUI workflow file is missing: {self.workflow_path}")
        try:
            workflow = json.loads(self.workflow_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise GenerationBackendError(f"ComfyUI workflow JSON is invalid: {self.workflow_path}") from exc

        if not isinstance(workflow, dict):
            raise GenerationBackendError("ComfyUI workflow JSON must be an object (API format).")
        return workflow

    @staticmethod
    def _prompt_value_from_node(node: Dict[str, Any]) -> str:
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        for key in ("prompt", "text"):
            value = inputs.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _set_prompt_value(node: Dict[str, Any], value: str, node_label: str) -> str:
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        if "prompt" in inputs:
            inputs["prompt"] = value
            return "prompt"
        if "text" in inputs:
            inputs["text"] = value
            return "text"
        raise GenerationBackendError(
            f"Prompt input field is missing for '{node_label}'. Expected 'prompt' or 'text'."
        )

    def _resolve_positive_prompt(
        self,
        user_prompt: Optional[str],
        workflow: Dict[str, Any],
        theme: Optional[str],
    ) -> str:
        provided = str(user_prompt or "").strip()
        if provided:
            return resolve_prompt(provided, theme)

        positive_node = self._node_from_workflow(
            workflow,
            self._required_node_id("positive_prompt"),
            NODE_LABELS["positive_prompt"],
        )
        workflow_prompt = self._prompt_value_from_node(positive_node)
        if workflow_prompt:
            return workflow_prompt
        if WORKFLOW_PROMPT_FALLBACK:
            return WORKFLOW_PROMPT_FALLBACK
        return RECOMMENDED_DEFAULT_PROMPT

    def _resolve_negative_prompt(
        self,
        user_negative_prompt: Optional[str],
        workflow: Dict[str, Any],
    ) -> str:
        provided = str(user_negative_prompt or "").strip()
        if provided:
            return provided

        negative_node = self._node_from_workflow(
            workflow,
            self._required_node_id("negative_prompt"),
            NODE_LABELS["negative_prompt"],
        )
        workflow_negative = self._prompt_value_from_node(negative_node)
        if workflow_negative:
            return workflow_negative
        if RECOMMENDED_DEFAULT_NEGATIVE_PROMPT:
            return RECOMMENDED_DEFAULT_NEGATIVE_PROMPT
        return resolve_negative_prompt(None)

    def update_workflow_inputs(
        self,
        workflow: Dict[str, Any],
        uploaded_filename: str,
        prompt: str,
        negative_prompt: str,
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        load_image_id = self._required_node_id("load_image")
        positive_prompt_id = self._required_node_id("positive_prompt")
        negative_prompt_id = self._required_node_id("negative_prompt")
        ksampler_id = self._required_node_id("ksampler")

        workflow_payload = copy.deepcopy(workflow)

        load_image_node = self._node_from_workflow(workflow_payload, load_image_id, NODE_LABELS["load_image"])
        load_image_node.setdefault("inputs", {})["image"] = uploaded_filename

        positive_node = self._node_from_workflow(
            workflow_payload,
            positive_prompt_id,
            NODE_LABELS["positive_prompt"],
        )
        positive_field = self._set_prompt_value(positive_node, prompt, NODE_LABELS["positive_prompt"])

        negative_node = self._node_from_workflow(
            workflow_payload,
            negative_prompt_id,
            NODE_LABELS["negative_prompt"],
        )
        negative_field = self._set_prompt_value(negative_node, negative_prompt, NODE_LABELS["negative_prompt"])

        ksampler_node = self._node_from_workflow(workflow_payload, ksampler_id, NODE_LABELS["ksampler"])
        k_inputs = ksampler_node.setdefault("inputs", {})
        k_inputs["seed"] = int(options["seed"])
        k_inputs["steps"] = int(options["steps"])
        k_inputs["cfg"] = float(options["cfg"])
        k_inputs["denoise"] = float(options["denoise"])

        if options.get("megapixels") is not None:
            image_scale_id = self._required_node_id("image_scale")
            image_scale_node = self._node_from_workflow(
                workflow_payload,
                image_scale_id,
                NODE_LABELS["image_scale"],
            )
            image_scale_node.setdefault("inputs", {})["megapixels"] = float(options["megapixels"])

        logger.info(
            "ComfyUI workflow inputs updated: load_image=%s positive(%s)=%s negative(%s)=%s ksampler=%s",
            load_image_id,
            positive_field,
            positive_prompt_id,
            negative_field,
            negative_prompt_id,
            ksampler_id,
        )

        return workflow_payload

    def queue_prompt(self, workflow: Dict[str, Any], client_id: str) -> str:
        response = self._request(
            "POST",
            "/prompt",
            json={"prompt": workflow, "client_id": client_id},
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise GenerationBackendError("ComfyUI /prompt returned invalid JSON.") from exc

        prompt_id = str(payload.get("prompt_id") or "").strip()
        if not prompt_id:
            raise GenerationBackendError(f"ComfyUI /prompt did not return prompt_id: {payload}")
        return prompt_id

    @staticmethod
    def _extract_history_entry(history_payload: Any, prompt_id: str) -> Optional[Dict[str, Any]]:
        if isinstance(history_payload, dict):
            entry = history_payload.get(prompt_id)
            if isinstance(entry, dict):
                return entry
            if "outputs" in history_payload and isinstance(history_payload.get("outputs"), dict):
                return history_payload
        return None

    @staticmethod
    def _extract_first_image(node_output: Any) -> Optional[Dict[str, str]]:
        if not isinstance(node_output, dict):
            return None
        images = node_output.get("images") if isinstance(node_output.get("images"), list) else []
        for image in images:
            if not isinstance(image, dict):
                continue
            filename = str(image.get("filename") or "").strip()
            if not filename:
                continue
            return {
                "filename": filename,
                "subfolder": str(image.get("subfolder") or ""),
                "type": str(image.get("type") or "output"),
            }
        return None

    @classmethod
    def _extract_output_image_info(
        cls,
        history_entry: Dict[str, Any],
        preferred_node_id: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        outputs = history_entry.get("outputs") if isinstance(history_entry.get("outputs"), dict) else {}

        if preferred_node_id:
            preferred_output = outputs.get(str(preferred_node_id))
            preferred_image = cls._extract_first_image(preferred_output)
            if preferred_image:
                return preferred_image

        for node_output in outputs.values():
            found = cls._extract_first_image(node_output)
            if found:
                return found
        return None

    def wait_for_completion(
        self,
        prompt_id: str,
        timeout_seconds: float,
        *,
        preferred_output_node_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        started = time.time()
        while (time.time() - started) < timeout_seconds:
            response = self._request("GET", f"/history/{prompt_id}")
            try:
                payload = response.json()
            except ValueError:
                payload = {}

            entry = self._extract_history_entry(payload, prompt_id)
            if isinstance(entry, dict):
                status_payload = entry.get("status") if isinstance(entry.get("status"), dict) else {}
                status_info = status_payload.get("status") if isinstance(status_payload.get("status"), dict) else {}
                status_str = str(status_info.get("status_str") or status_payload.get("status_str") or "").strip().lower()
                if status_str in {"error", "failed"}:
                    raise GenerationBackendError(f"ComfyUI execution failed for prompt_id={prompt_id}.")

                image_info = self._extract_output_image_info(
                    entry,
                    preferred_node_id=preferred_output_node_id,
                )
                if image_info:
                    return {"history": entry, "image": image_info}

            time.sleep(self.poll_interval)

        raise GenerationBackendError(
            f"ComfyUI generation timed out after {int(timeout_seconds)} seconds for prompt_id={prompt_id}."
        )

    def download_output_image(self, image_info: Dict[str, str]) -> bytes:
        response = self._request(
            "GET",
            "/view",
            params={
                "filename": image_info.get("filename", ""),
                "subfolder": image_info.get("subfolder", ""),
                "type": image_info.get("type", "output"),
            },
        )
        return response.content

    def _resolve_generation_options(self, options: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(self.defaults)
        for key, value in options.items():
            if value is not None:
                merged[key] = value

        merged_seed = resolve_seed(merged.get("seed", -1))
        merged_steps = self._to_int(merged.get("steps"), 28)
        merged_cfg = self._to_float(
            merged.get("cfg", merged.get("cfgScale")),
            6.0,
        )
        merged_denoise = self._to_float(
            merged.get("denoise", merged.get("denoisingStrength")),
            0.5,
        )
        megapixels_value = merged.get("megapixels")
        megapixels = None
        if megapixels_value not in (None, ""):
            megapixels = self._to_float(megapixels_value, 1.0)

        style_preset = str(
            merged.get("style_preset")
            or merged.get("stylePreset")
            or "random"
        ).strip()
        if not style_preset:
            style_preset = "random"
        style_category = str(
            merged.get("style_category")
            or merged.get("styleCategory")
            or ""
        ).strip().lower()

        return {
            "seed": merged_seed,
            "steps": merged_steps,
            "cfg": merged_cfg,
            "denoise": merged_denoise,
            "theme": str(merged.get("theme") or "").strip().lower(),
            "megapixels": megapixels,
            "style_preset": style_preset,
            "style_category": style_category,
        }

    def generate(
        self,
        input_image_path: str | Path,
        prompt: Optional[str],
        negative_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raw_options = dict(options or {})
        settings = raw_options.get("generation_settings") if isinstance(raw_options.get("generation_settings"), dict) else {}
        merged_options = self._resolve_generation_options({**settings, **raw_options})

        input_path = Path(input_image_path)
        output_path_raw = raw_options.get("output_path")
        output_path = Path(output_path_raw) if output_path_raw else self.output_dir / f"{uuid4().hex}.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        prompt_id = None
        client_id = str(uuid4())
        uploaded_filename = ""
        prompt_text = ""
        negative_text = ""
        selected_preset: Dict[str, str] = {}
        requested_style_preset = str(merged_options.get("style_preset") or "random")

        try:
            try:
                preset_resolution = resolve_comfy_preset(
                    requested_style_preset,
                    category=merged_options.get("style_category"),
                )
            except (FileNotFoundError, ValueError) as exc:
                raise GenerationBackendError(str(exc)) from exc
            except KeyError as exc:
                raise GenerationBackendError(str(exc).strip("'")) from exc
            selected_preset = (
                preset_resolution.get("selected_preset")
                if isinstance(preset_resolution.get("selected_preset"), dict)
                else {}
            )
            if not selected_preset:
                raise GenerationBackendError("Unable to resolve a Comfy style preset.")

            prompt_text = str(selected_preset.get("prompt") or "").strip()
            if not prompt_text:
                raise GenerationBackendError("Selected Comfy style preset has an empty prompt.")
            requested_style_preset = str(
                preset_resolution.get("requested_style_preset") or requested_style_preset or "random"
            )
            logger.info(
                "ComfyUI style preset selected requested=%s filter=%s resolved_id=%s resolved_name=%s category=%s",
                requested_style_preset,
                str(merged_options.get("style_category") or ""),
                str(selected_preset.get("id") or ""),
                str(selected_preset.get("name") or ""),
                str(selected_preset.get("category") or ""),
            )

            requested_negative = str(negative_prompt or "").strip()
            preset_negative = str(preset_resolution.get("negative_prompt") or "").strip()
            negative_text = requested_negative or preset_negative or resolve_negative_prompt(None)

            uploaded_filename = self.upload_image(input_path)
            logger.info(
                "ComfyUI upload complete mode=%s uploaded_filename=%s input=%s",
                self.mode,
                uploaded_filename,
                input_path,
            )
            workflow = self.load_workflow()
            workflow_payload = self.update_workflow_inputs(
                workflow,
                uploaded_filename,
                prompt_text,
                negative_text,
                merged_options,
            )
            prompt_id = self.queue_prompt(workflow_payload, client_id)
            logger.info(
                "ComfyUI queued prompt mode=%s prompt_id=%s uploaded_filename=%s",
                self.mode,
                prompt_id,
                uploaded_filename,
            )
            completion_payload = self.wait_for_completion(
                prompt_id,
                self.generation_timeout,
                preferred_output_node_id=self._optional_node_id("save_image"),
            )
            image_info = completion_payload.get("image")
            if not isinstance(image_info, dict):
                raise GenerationBackendError("ComfyUI completed but no output image was found in history.")

            image_bytes = self.download_output_image(image_info)
            if not image_bytes:
                raise GenerationBackendError("ComfyUI returned an empty output image response.")

            output_path.write_bytes(image_bytes)
            logger.info(
                "ComfyUI generated image mode=%s prompt_id=%s uploaded_filename=%s saved=%s",
                self.mode,
                prompt_id,
                uploaded_filename,
                output_path,
            )

            metadata = {
                "backend": "comfyui",
                "client_id": client_id,
                "workflow_path": self.workflow_path_metadata,
                "node_ids": dict(self.node_ids),
                "uploaded_filename": uploaded_filename,
                "seed": merged_options["seed"],
                "steps": merged_options["steps"],
                "cfg": merged_options["cfg"],
                "denoise": merged_options["denoise"],
                "megapixels": merged_options.get("megapixels"),
                "theme": merged_options.get("theme") or "",
                "style_preset_requested": requested_style_preset,
                "style_preset_id": str(selected_preset.get("id") or ""),
                "style_preset_name": str(selected_preset.get("name") or ""),
                "style_category": str(selected_preset.get("category") or ""),
                "style_category_filter": str(merged_options.get("style_category") or ""),
                "prompt_used": prompt_text,
            }
            return build_success_result(
                mode=self.mode,
                prompt_id=prompt_id,
                input_image=str(input_path),
                output_image=str(output_path),
                prompt=prompt_text,
                negative_prompt=negative_text,
                metadata=metadata,
            )
        except GenerationBackendError as exc:
            return build_error_result(
                mode=self.mode,
                input_image=str(input_path),
                prompt=prompt_text or str(prompt or "").strip(),
                negative_prompt=negative_text or str(negative_prompt or "").strip(),
                error=str(exc),
                metadata={
                    "backend": "comfyui",
                    "prompt_id": prompt_id,
                    "workflow_path": self.workflow_path_metadata,
                    "node_ids": dict(self.node_ids),
                    "uploaded_filename": uploaded_filename,
                    "style_preset_requested": requested_style_preset,
                    "style_preset_id": str(selected_preset.get("id") or ""),
                    "style_preset_name": str(selected_preset.get("name") or ""),
                    "style_category": str(selected_preset.get("category") or ""),
                    "style_category_filter": str(merged_options.get("style_category") or ""),
                    "prompt_used": prompt_text or str(prompt or "").strip(),
                },
            )
        except Exception as exc:  # pragma: no cover - defensive catch
            logger.exception("ComfyUI backend generation failed.")
            return build_error_result(
                mode=self.mode,
                input_image=str(input_path),
                prompt=prompt_text or str(prompt or "").strip(),
                negative_prompt=negative_text or str(negative_prompt or "").strip(),
                error=f"Unexpected ComfyUI backend error: {exc}",
                metadata={
                    "backend": "comfyui",
                    "prompt_id": prompt_id,
                    "workflow_path": self.workflow_path_metadata,
                    "node_ids": dict(self.node_ids),
                    "uploaded_filename": uploaded_filename,
                    "style_preset_requested": requested_style_preset,
                    "style_preset_id": str(selected_preset.get("id") or ""),
                    "style_preset_name": str(selected_preset.get("name") or ""),
                    "style_category": str(selected_preset.get("category") or ""),
                    "style_category_filter": str(merged_options.get("style_category") or ""),
                    "prompt_used": prompt_text or str(prompt or "").strip(),
                },
            )

    def health_check(self) -> Dict[str, Any]:
        try:
            response = self._request("GET", "/system_stats", timeout=self.connect_timeout)
            payload = response.json()
            return {
                "mode": self.mode,
                "reachable": True,
                "system": payload.get("system") if isinstance(payload, dict) else {},
            }
        except Exception as exc:
            return {
                "mode": self.mode,
                "reachable": False,
                "error": str(exc),
            }
