import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.quality_reviewer import default_auto_review


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
                return [self._normalize_item(item) for item in parsed if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError):
            pass
        return []

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _normalize_auto_review(value: Any) -> Dict[str, Any]:
        base = dict(default_auto_review())
        if not isinstance(value, dict):
            return base

        auto_rating = GalleryStore._safe_int(value.get("autoRating"))
        if auto_rating is not None and 1 <= auto_rating <= 5:
            base["autoRating"] = auto_rating
        else:
            base["autoRating"] = 0

        bad_tags = [str(tag) for tag in value.get("autoBadTags", []) if isinstance(tag, str)]
        good_tags = [str(tag) for tag in value.get("autoGoodTags", []) if isinstance(tag, str)]
        base["autoBadTags"] = list(dict.fromkeys(bad_tags))
        base["autoGoodTags"] = list(dict.fromkeys(good_tags))
        base["autoNotes"] = str(value.get("autoNotes") or "").strip()
        try:
            confidence = float(value.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.0
        base["confidence"] = round(max(0.0, min(1.0, confidence)), 3)
        metrics = value.get("metrics")
        metric_payload = base.get("metrics")
        if not isinstance(metric_payload, dict):
            metric_payload = {}
        if isinstance(metrics, dict):
            metric_payload["similarityScore"] = round(
                max(0.0, min(1.0, GalleryStore._safe_float(metrics.get("similarityScore")))),
                4,
            )
            metric_payload["whiteBackgroundRatio"] = round(
                max(0.0, min(1.0, GalleryStore._safe_float(metrics.get("whiteBackgroundRatio")))),
                4,
            )
            metric_payload["colorRatio"] = round(
                max(0.0, min(1.0, GalleryStore._safe_float(metrics.get("colorRatio")))),
                4,
            )
            metric_payload["edgeRatio"] = round(
                max(0.0, min(1.0, GalleryStore._safe_float(metrics.get("edgeRatio")))),
                4,
            )
            metric_payload["colorGain"] = round(
                max(-1.0, min(1.0, GalleryStore._safe_float(metrics.get("colorGain")))),
                4,
            )
        base["metrics"] = metric_payload
        return base

    @staticmethod
    def _normalize_comparison_scores(value: Any) -> Dict[str, int]:
        if not isinstance(value, dict):
            return {}
        keys = (
            "subjectPreserved",
            "colorImprovement",
            "backgroundFullness",
            "styleQuality",
            "childFriendlyResult",
        )
        output: Dict[str, int] = {}
        for key in keys:
            numeric = GalleryStore._safe_int(value.get(key))
            if numeric is None:
                continue
            if 1 <= numeric <= 5:
                output[key] = int(numeric)
        return output

    @staticmethod
    def _normalize_item(item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(item)

        staff_rating = GalleryStore._safe_int(normalized.get("staffRating"))
        legacy_rating = GalleryStore._safe_int(normalized.get("rating"))
        if staff_rating is None and legacy_rating is not None and 1 <= legacy_rating <= 5:
            staff_rating = legacy_rating
        if staff_rating is not None and not (1 <= staff_rating <= 5):
            staff_rating = None

        normalized["staffRating"] = staff_rating
        normalized["rating"] = staff_rating

        auto_review = GalleryStore._normalize_auto_review(normalized.get("autoReview"))
        fallback_auto = GalleryStore._safe_int(normalized.get("autoRating"))
        if auto_review.get("autoRating", 0) <= 0 and fallback_auto is not None and 1 <= fallback_auto <= 5:
            auto_review["autoRating"] = fallback_auto
        normalized["autoReview"] = auto_review
        normalized["autoRating"] = int(auto_review.get("autoRating") or 0)

        tags = [str(tag) for tag in normalized.get("feedbackTags", []) if isinstance(tag, str)]
        normalized["feedbackTags"] = list(dict.fromkeys(tags))
        normalized["feedbackNote"] = str(normalized.get("feedbackNote") or "").strip()
        normalized["comparisonScores"] = GalleryStore._normalize_comparison_scores(
            normalized.get("comparisonScores")
        )
        return normalized

    def _save_items_unlocked(self, items: List[Dict[str, Any]]) -> None:
        normalized_items = [self._normalize_item(item) for item in items]
        sorted_items = sorted(normalized_items, key=lambda item: item.get("createdAt", ""), reverse=True)
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
        normalized_item = self._normalize_item(item)
        with self._lock:
            items = self._load_items_unlocked()
            items.append(normalized_item)
            self._save_items_unlocked(items)
        return normalized_item

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
        comparison_scores: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            items = self._load_items_unlocked()
            target = self._find_item_by_job_id_unlocked(items, job_id)

            if target is None:
                raise KeyError(job_id)

            target["rating"] = rating
            target["staffRating"] = rating
            target["feedbackTags"] = feedback_tags
            target["feedbackNote"] = feedback_note
            target["comparisonScores"] = self._normalize_comparison_scores(comparison_scores)
            target["ratedAt"] = datetime.now(timezone.utc).isoformat()
            target["updatedAt"] = target["ratedAt"]

            self._save_items_unlocked(items)
            return self._normalize_item(target)

    def rename_item(self, job_id: str, visitor_name: str) -> Dict[str, Any]:
        with self._lock:
            items = self._load_items_unlocked()
            target = self._find_item_by_job_id_unlocked(items, job_id)
            if target is None:
                raise KeyError(job_id)

            target["visitorName"] = visitor_name
            target["updatedAt"] = datetime.now(timezone.utc).isoformat()
            self._save_items_unlocked(items)
            return self._normalize_item(target)

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
            return self._normalize_item(target)

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
            return self._normalize_item(removed_item)
