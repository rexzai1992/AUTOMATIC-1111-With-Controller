import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class GalleryStore:
    def __init__(self, json_path: Path) -> None:
        self._json_path = json_path
        self._lock = threading.Lock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        self._json_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._json_path.exists():
            self._json_path.write_text("[]", encoding="utf-8")

    def _load_items_unlocked(self) -> List[Dict[str, Any]]:
        try:
            raw = self._json_path.read_text(encoding="utf-8").strip()
            if not raw:
                return []
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def _save_items_unlocked(self, items: List[Dict[str, Any]]) -> None:
        sorted_items = sorted(items, key=lambda item: item.get("createdAt", ""), reverse=True)
        self._json_path.write_text(
            json.dumps(sorted_items, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    def list_items(self, include_hidden: bool = True) -> List[Dict[str, Any]]:
        with self._lock:
            items = self._load_items_unlocked()
        if not include_hidden:
            items = [item for item in items if not bool(item.get("hidden", False))]
        return sorted(items, key=lambda item: item.get("createdAt", ""), reverse=True)

    def add_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            items = self._load_items_unlocked()
            items.append(item)
            self._save_items_unlocked(items)
        return item

    @staticmethod
    def _extract_duration_seconds(item: Dict[str, Any]) -> Optional[float]:
        raw_value = item.get("durationSeconds")
        try:
            duration = float(raw_value)
        except (TypeError, ValueError):
            return None
        if duration <= 0:
            return None
        return duration

    def get_duration_estimate(self, default_seconds: int = 60) -> Dict[str, int]:
        safe_default = max(1, int(default_seconds))
        with self._lock:
            items = self._load_items_unlocked()

        durations: List[float] = []
        for item in items:
            duration = self._extract_duration_seconds(item)
            if duration is not None:
                durations.append(duration)

        sample_count = len(durations)
        average_seconds = sum(durations) / sample_count if sample_count > 0 else float(safe_default)

        estimated_seconds = max(1, round(average_seconds))
        min_seconds = max(1, round(average_seconds * 0.8))
        max_seconds = max(min_seconds, round(average_seconds * 1.3))

        return {
            "estimatedSeconds": estimated_seconds,
            "minSeconds": min_seconds,
            "maxSeconds": max_seconds,
            "sampleCount": sample_count,
        }

    def get_item(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            items = self._load_items_unlocked()
            for item in items:
                if item.get("jobId") == job_id:
                    return item
        return None

    @staticmethod
    def _find_item_by_job_id_unlocked(
        items: List[Dict[str, Any]],
        job_id: str,
    ) -> Optional[Dict[str, Any]]:
        for item in items:
            if item.get("jobId") == job_id:
                return item
        return None

    def rate_item(
        self,
        job_id: str,
        rating: int,
        feedback_tags: List[str],
        feedback_note: str,
    ) -> Dict[str, Any]:
        with self._lock:
            items = self._load_items_unlocked()
            target = self._find_item_by_job_id_unlocked(items, job_id)

            if target is None:
                raise KeyError(job_id)

            target["rating"] = rating
            target["feedbackTags"] = feedback_tags
            target["feedbackNote"] = feedback_note
            target["ratedAt"] = datetime.now(timezone.utc).isoformat()

            self._save_items_unlocked(items)
            return target

    def rename_item(self, job_id: str, visitor_name: str) -> Dict[str, Any]:
        with self._lock:
            items = self._load_items_unlocked()
            target = self._find_item_by_job_id_unlocked(items, job_id)
            if target is None:
                raise KeyError(job_id)

            target["visitorName"] = visitor_name
            target["updatedAt"] = datetime.now(timezone.utc).isoformat()
            self._save_items_unlocked(items)
            return target

    def set_hidden(self, job_id: str, hidden: bool) -> Dict[str, Any]:
        with self._lock:
            items = self._load_items_unlocked()
            target = self._find_item_by_job_id_unlocked(items, job_id)
            if target is None:
                raise KeyError(job_id)

            hidden_value = bool(hidden)
            target["hidden"] = hidden_value
            target["hiddenAt"] = datetime.now(timezone.utc).isoformat() if hidden_value else None
            target["updatedAt"] = datetime.now(timezone.utc).isoformat()
            self._save_items_unlocked(items)
            return target

    def delete_item(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            items = self._load_items_unlocked()
            removed_item = None
            remaining_items: List[Dict[str, Any]] = []

            for item in items:
                if removed_item is None and item.get("jobId") == job_id:
                    removed_item = item
                    continue
                remaining_items.append(item)

            if removed_item is None:
                raise KeyError(job_id)

            self._save_items_unlocked(remaining_items)
            return removed_item
