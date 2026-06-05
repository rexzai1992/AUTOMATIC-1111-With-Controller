from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import BASE_DIR

from .comfyui_backend import ComfyUIBackend
from .stable_diffusion_backend import StableDiffusionBackend

DEFAULT_RUNTIME_CONFIG: Dict[str, Any] = {
    "generation_engine": "comfyui",
    "stable_diffusion": {
        "base_url": "http://127.0.0.1:7860",
        "output_dir": "outputs/stable_diffusion",
    },
    "comfyui": {
        "base_url": "http://127.0.0.1:8188",
        "workflow_path": "workflows/Ai Genius.json",
        "output_dir": "outputs/comfyui",
        "node_ids": {
            "load_image": "78",
            "positive_prompt": "115:111",
            "negative_prompt": "115:110",
            "ksampler": "115:3",
            "save_image": "60",
            "image_scale": "115:93",
        },
        "defaults": {
            "steps": 4,
            "cfg": 1,
            "denoise": 1,
            "seed": -1,
            "megapixels": 1,
        },
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    output = dict(base)
    for key, value in override.items():
        if isinstance(output.get(key), dict) and isinstance(value, dict):
            output[key] = _deep_merge(output[key], value)
        else:
            output[key] = value
    return output


def _to_abs_path(path_value: Any) -> str:
    path = Path(str(path_value or "").strip())
    if path.is_absolute():
        return str(path)
    return str((BASE_DIR / path).resolve())


def load_backend_runtime_config(config_path: Optional[str | Path] = None) -> Dict[str, Any]:
    source_path = Path(config_path) if config_path else BASE_DIR / "config.json"
    merged = copy.deepcopy(DEFAULT_RUNTIME_CONFIG)

    if source_path.exists():
        try:
            payload = json.loads(source_path.read_text(encoding="utf-8-sig"))
            if isinstance(payload, dict):
                merged = _deep_merge(merged, payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in config file: {source_path}") from exc

    engine = str(merged.get("generation_engine") or "stable_diffusion").strip().lower()
    merged["generation_engine"] = engine

    stable_cfg = merged.get("stable_diffusion") if isinstance(merged.get("stable_diffusion"), dict) else {}
    comfy_cfg = merged.get("comfyui") if isinstance(merged.get("comfyui"), dict) else {}

    stable_cfg["output_dir"] = _to_abs_path(stable_cfg.get("output_dir") or "outputs/stable_diffusion")
    comfy_cfg["output_dir"] = _to_abs_path(comfy_cfg.get("output_dir") or "outputs/comfyui")
    comfy_cfg["workflow_path"] = _to_abs_path(
        comfy_cfg.get("workflow_path") or "workflows/Ai Genius.json"
    )

    Path(stable_cfg["output_dir"]).mkdir(parents=True, exist_ok=True)
    Path(comfy_cfg["output_dir"]).mkdir(parents=True, exist_ok=True)

    (BASE_DIR / "uploads").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "workflows").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "temp" / "stable_diffusion").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "temp" / "comfyui").mkdir(parents=True, exist_ok=True)

    merged["stable_diffusion"] = stable_cfg
    merged["comfyui"] = comfy_cfg
    return merged


def get_generation_backend(config: Dict[str, Any]):
    engine = str(config.get("generation_engine") or "").strip().lower()
    if engine == "stable_diffusion":
        return StableDiffusionBackend(config.get("stable_diffusion") if isinstance(config.get("stable_diffusion"), dict) else {})
    if engine == "comfyui":
        return ComfyUIBackend(config.get("comfyui") if isinstance(config.get("comfyui"), dict) else {})
    raise ValueError("Unsupported generation_engine")


def get_generation_backend_for_engine(engine: str, config: Dict[str, Any]):
    runtime = dict(config)
    runtime["generation_engine"] = str(engine or runtime.get("generation_engine") or "").strip().lower()
    return get_generation_backend(runtime)
