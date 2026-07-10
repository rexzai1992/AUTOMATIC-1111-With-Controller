import json
from pathlib import Path

import requests

from local_ai_config import get_service_config


def main() -> int:
    service = get_service_config("sf3d")
    sf3d_dir = Path(service["directory"])
    checks = {
        "sf3d_dir": sf3d_dir.is_dir(),
        "official_repo": (sf3d_dir / ".git").is_dir()
        and (sf3d_dir / "sf3d" / "system.py").is_file(),
        "app_fastapi.py": (sf3d_dir / "app_fastapi.py").is_file(),
        "requirements-api.txt": (sf3d_dir / "requirements-api.txt").is_file(),
        "start_sf3d_api.bat": (sf3d_dir / "start_sf3d_api.bat").is_file(),
        "test_client.py": (sf3d_dir / "test_client.py").is_file(),
    }
    report = {"checks": checks, "health": {"reachable": False}}
    try:
        response = requests.get(str(service["health_url"]), timeout=5)
        report["health"] = {
            "reachable": True,
            "status_code": response.status_code,
            "payload": response.json(),
        }
    except (requests.RequestException, ValueError) as exc:
        report["health"]["error"] = str(exc)
    print(json.dumps(report, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
