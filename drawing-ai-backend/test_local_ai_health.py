import json

from service_manager import get_all_service_statuses


def main() -> int:
    statuses = get_all_service_statuses()
    payload = {
        "controller": {
            "url": "http://127.0.0.1:8000/health",
            "note": "Controller health is available when the server is running.",
        },
        "services": statuses,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
