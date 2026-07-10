import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
LOCAL_AI_OUTPUT_DIR = BASE_DIR / "outputs" / "local_ai"
LOG_DIR = BASE_DIR / "logs"
PID_STATE_PATH = LOG_DIR / "local_ai_pids.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "output_dir": "outputs/local_ai",
    "services": {
        "comfyui": {
            "enabled": True,
            "autostart": True,
            "directory": (
                r"C:\Users\User\Downloads\ComfyUI_windows_portable_nvidia"
                r"\ComfyUI_windows_portable"
            ),
            "url": "http://127.0.0.1:8188",
            "health_url": "http://127.0.0.1:8188",
            "start_command": "run_nvidia_gpu.bat",
            "log_file": "logs/comfyui.log",
        },
        "stable_diffusion": {
            "enabled": True,
            "autostart": False,
            "directory": str((BASE_DIR.parent / "stable-diffusion-webui").resolve()),
            "url": "http://127.0.0.1:7860",
            "health_url": "http://127.0.0.1:7860/sdapi/v1/sd-models",
            "start_command": "webui-user.bat --api",
            "log_file": "logs/stable_diffusion.log",
        },
        "sf3d": {
            "enabled": True,
            "autostart": False,
            "autostart_on_generate": True,
            "directory": r"C:\AI\stable-fast-3d",
            "url": "http://127.0.0.1:8003",
            "health_url": "http://127.0.0.1:8003/health",
            "start_command": "start_sf3d_api.bat",
            "log_file": "logs/sf3d.log",
            "startup_timeout_seconds": 30,
            "timeout_seconds": 600,
            "defaults": {
                "remesh": "triangle",
                "vertex_count": 3000,
                "texture_resolution": 512,
                "foreground_ratio": 0.85,
            },
        },
    },
}


def _merge(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_local_ai_config() -> dict[str, Any]:
    raw: dict[str, Any] = {}
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        raw = payload.get("local_ai") if isinstance(payload.get("local_ai"), dict) else {}
    except (OSError, json.JSONDecodeError):
        raw = {}
    config = _merge(DEFAULT_CONFIG, raw)
    output_value = os.getenv("LOCAL_AI_OUTPUT_DIR", str(config["output_dir"]))
    output_path = Path(output_value)
    if not output_path.is_absolute():
        output_path = BASE_DIR / output_path
    config["output_path"] = output_path.resolve()
    return config


def get_service_config(service_name: str) -> dict[str, Any]:
    services = load_local_ai_config()["services"]
    if service_name not in services:
        raise KeyError(f"Unknown local AI service: {service_name}")
    return services[service_name]


for directory in (
    LOCAL_AI_OUTPUT_DIR / "3d",
    LOCAL_AI_OUTPUT_DIR / "previews",
    LOCAL_AI_OUTPUT_DIR / "images",
    LOCAL_AI_OUTPUT_DIR / "uploads",
    LOG_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)
