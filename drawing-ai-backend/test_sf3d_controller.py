import argparse
import json
from pathlib import Path

from local_ai_config import load_local_ai_config
from sf3d_client import generate_3d_from_image


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a GLB through sf3d_client.")
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    config = load_local_ai_config()
    result = generate_3d_from_image(args.image, config["output_path"])
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
