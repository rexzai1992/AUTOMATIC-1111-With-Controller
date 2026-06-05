from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import BASE_DIR
from backends import get_generation_backend, load_backend_runtime_config


def main() -> int:
    config_path = BASE_DIR / "config.json"
    runtime_config = load_backend_runtime_config(config_path)
    runtime_config["generation_engine"] = "comfyui"

    backend = get_generation_backend(runtime_config)

    test_image_path = BASE_DIR / "uploads" / "test.png"
    if not test_image_path.is_file():
        print(
            json.dumps(
                {
                    "success": False,
                    "error": f"Test image not found: {test_image_path}",
                },
                indent=2,
                ensure_ascii=True,
            )
        )
        return 1

    result = backend.generate(
        input_image_path=test_image_path,
        prompt=None,
        negative_prompt=None,
        options={"theme": "fantasy", "style_preset": "random"},
    )
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if bool(result.get("success")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
