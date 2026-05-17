import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = PROJECT_ROOT / "tests"
RESULTS_DIR = TESTS_DIR / "results"
SAMPLE_IMAGES_DIR = TESTS_DIR / "sample_images"
SAMPLE_MANIFEST_PATH = TESTS_DIR / "sample_manifest.json"


PASS = "PASS"
WARNING = "WARNING"
FAIL = "FAIL"
DANGER = "DANGER"
VALID_LEVELS = {PASS, WARNING, FAIL, DANGER}


def ensure_test_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def env_base_url() -> str:
    value = str(os.getenv("DRAWING_BACKEND_URL", "http://127.0.0.1:8000")).strip()
    return value.rstrip("/")


def env_api_key() -> str:
    return str(os.getenv("DRAWING_API_KEY", os.getenv("API_KEY", ""))).strip()


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "drawing-ai-backend-qa/1.0",
            "Accept": "application/json, text/plain, */*",
        }
    )
    return session


def with_api_key(headers: Optional[Dict[str, str]] = None, api_key: str = "") -> Dict[str, str]:
    output = dict(headers or {})
    if api_key:
        output["X-API-Key"] = api_key
    return output


def endpoint(base_url: str, path: str) -> str:
    cleaned = str(path or "").strip()
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    return f"{base_url.rstrip('/')}{cleaned}"


def is_test_visitor_name(value: Any) -> bool:
    name = str(value or "").strip().upper()
    return name.startswith("TEST_")


def list_sample_images() -> List[Path]:
    ensure_test_dirs()
    candidates: List[Path] = []
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"):
        candidates.extend(SAMPLE_IMAGES_DIR.glob(ext))
    return sorted({path.resolve() for path in candidates}, key=lambda path: path.name)


def load_sample_manifest() -> Dict[str, Any]:
    if not SAMPLE_MANIFEST_PATH.is_file():
        return {"items": []}
    try:
        payload = json.loads(SAMPLE_MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"items": []}
    if not isinstance(payload, dict):
        return {"items": []}
    if not isinstance(payload.get("items"), list):
        payload["items"] = []
    return payload


def save_sample_manifest(payload: Dict[str, Any]) -> None:
    ensure_test_dirs()
    SAMPLE_MANIFEST_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def file_size_bytes(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def directory_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += file_size_bytes(item)
    return total


def percent(value: float, digits: int = 2) -> float:
    return round(float(value) * 100.0, digits)


def safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


@dataclass
class CheckItem:
    level: str
    name: str
    detail: str
    createdAt: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "level": self.level,
            "name": self.name,
            "detail": self.detail,
            "createdAt": self.createdAt,
        }


class TestReporter:
    def __init__(self, script_name: str, base_url: str) -> None:
        self.script_name = script_name
        self.base_url = base_url
        self.started_at = utc_now_iso()
        self.checks: List[CheckItem] = []
        self.metrics: Dict[str, Any] = {}
        self.artifacts: Dict[str, Any] = {}

    def add(self, level: str, name: str, detail: str) -> None:
        resolved = str(level or "").strip().upper()
        if resolved not in VALID_LEVELS:
            raise ValueError(f"Invalid level: {resolved}")
        check = CheckItem(
            level=resolved,
            name=str(name or "").strip() or "Unnamed check",
            detail=str(detail or "").strip(),
            createdAt=utc_now_iso(),
        )
        self.checks.append(check)
        print(f"[{resolved}] {check.name}: {check.detail}")

    def add_pass(self, name: str, detail: str) -> None:
        self.add(PASS, name, detail)

    def add_warning(self, name: str, detail: str) -> None:
        self.add(WARNING, name, detail)

    def add_fail(self, name: str, detail: str) -> None:
        self.add(FAIL, name, detail)

    def add_danger(self, name: str, detail: str) -> None:
        self.add(DANGER, name, detail)

    def count(self, level: str) -> int:
        resolved = str(level or "").strip().upper()
        return sum(1 for item in self.checks if item.level == resolved)

    def counts(self) -> Dict[str, int]:
        return {
            PASS: self.count(PASS),
            WARNING: self.count(WARNING),
            FAIL: self.count(FAIL),
            DANGER: self.count(DANGER),
            "TOTAL": len(self.checks),
        }

    def status(self) -> str:
        counts = self.counts()
        if counts[DANGER] > 0:
            return "danger"
        if counts[FAIL] > 0:
            return "failed"
        if counts[WARNING] > 0:
            return "warning"
        return "ok"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "script": self.script_name,
            "baseUrl": self.base_url,
            "startedAt": self.started_at,
            "finishedAt": utc_now_iso(),
            "status": self.status(),
            "summary": self.counts(),
            "checks": [item.to_dict() for item in self.checks],
            "metrics": self.metrics,
            "artifacts": self.artifacts,
        }

    def render_text(self, payload: Dict[str, Any]) -> str:
        lines: List[str] = []
        lines.append(f"TEST REPORT: {self.script_name}")
        lines.append(f"Generated At: {payload.get('finishedAt')}")
        lines.append(f"Base URL: {self.base_url}")
        lines.append(f"Status: {payload.get('status')}")
        lines.append("")
        summary = payload.get("summary", {})
        lines.append("Summary:")
        lines.append(f"PASS: {summary.get(PASS, 0)}")
        lines.append(f"WARNING: {summary.get(WARNING, 0)}")
        lines.append(f"FAIL: {summary.get(FAIL, 0)}")
        lines.append(f"DANGER: {summary.get(DANGER, 0)}")
        lines.append("")
        lines.append("Checks:")
        for check in payload.get("checks", []):
            lines.append(f"[{check.get('level')}] {check.get('name')}: {check.get('detail')}")
        lines.append("")
        lines.append("Metrics:")
        lines.append(json.dumps(payload.get("metrics", {}), indent=2, ensure_ascii=True))
        lines.append("")
        lines.append("Artifacts:")
        lines.append(json.dumps(payload.get("artifacts", {}), indent=2, ensure_ascii=True))
        return "\n".join(lines).strip() + "\n"

    def save(self, prefix: str) -> Dict[str, Path]:
        ensure_test_dirs()
        stamp = utc_now_stamp()
        payload = self.to_dict()
        json_path = RESULTS_DIR / f"{prefix}_{stamp}.json"
        txt_path = RESULTS_DIR / f"{prefix}_{stamp}.txt"
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        txt_path.write_text(self.render_text(payload), encoding="utf-8")
        print(f"[INFO] Saved report JSON: {json_path}")
        print(f"[INFO] Saved report TXT:  {txt_path}")
        return {"json": json_path, "txt": txt_path}


def request_with_timing(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: int = 30,
    **kwargs: Any,
) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        response = session.request(method=method, url=url, timeout=timeout, **kwargs)
        elapsed = round(time.perf_counter() - started, 3)
        return {"ok": True, "response": response, "error": "", "elapsed": elapsed}
    except requests.RequestException as exc:
        elapsed = round(time.perf_counter() - started, 3)
        return {"ok": False, "response": None, "error": str(exc), "elapsed": elapsed}


def response_json(response: requests.Response) -> Dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    if isinstance(data, dict):
        return data
    return {"value": data}
