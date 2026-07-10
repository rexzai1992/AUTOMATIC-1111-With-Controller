import base64
import json
import uuid
from pathlib import Path
from typing import Any

import requests

from local_ai_config import load_local_ai_config


def generate_stable_diffusion_image(payload: dict[str, Any]) -> dict[str, Any]:
    config = load_local_ai_config()
    service = config["services"]["stable_diffusion"]
    request_payload = dict(payload)
    timeout_seconds = int(request_payload.pop("timeout_seconds", 300))
    try:
        response = requests.post(
            f"{str(service['url']).rstrip('/')}/sdapi/v1/txt2img",
            json=request_payload,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        images = data.get("images") or []
        if not images:
            raise RuntimeError("Stable Diffusion returned no images.")
        output_dir = Path(config["output_path"]) / "images"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"sd-{uuid.uuid4()}.png"
        encoded = str(images[0]).split(",", 1)[-1]
        output_path.write_bytes(base64.b64decode(encoded))
        return {
            "success": True,
            "service": "stable_diffusion",
            "output_path": str(output_path),
            "info": data.get("info"),
        }
    except Exception as exc:
        return {
            "success": False,
            "service": "stable_diffusion",
            "error": str(exc),
        }


def queue_comfyui_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    config = load_local_ai_config()
    service = config["services"]["comfyui"]
    try:
        response = requests.post(
            f"{str(service['url']).rstrip('/')}/prompt",
            json={"prompt": workflow},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return {
            "success": bool(payload.get("prompt_id")),
            "service": "comfyui",
            **payload,
        }
    except Exception as exc:
        return {"success": False, "service": "comfyui", "error": str(exc)}
