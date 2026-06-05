import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


WONDERPARK_ALLOWED_STATUSES = {"pending", "queued", "processing", "completed", "failed"}
WONDERPARK_ALLOWED_PRESET_ANIMALS = {"lion", "zebra", "elephant", "tiger", "unknown"}
WONDERPARK_ALLOWED_RESULT_STATUSES = {"generated_hidden", "approved", "failed", "pending"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


class WonderparkSubmissionStore:
    def __init__(self, json_path: Path) -> None:
        self._json_path = json_path
        self._lock = threading.Lock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        self._json_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._json_path.exists():
            self._json_path.write_text("[]", encoding="utf-8")

    def _load_unlocked(self) -> List[Dict[str, Any]]:
        try:
            raw = self._json_path.read_text(encoding="utf-8").strip()
            if not raw:
                return []
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [self._normalize_row(row) for row in parsed if isinstance(row, dict)]
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def _save_unlocked(self, rows: List[Dict[str, Any]]) -> None:
        normalized = [self._normalize_row(row) for row in rows]
        normalized.sort(key=lambda row: str(row.get("createdAt") or ""), reverse=True)
        self._json_path.write_text(
            json.dumps(normalized, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    @staticmethod
    def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(row)
        payload["submissionId"] = str(payload.get("submissionId") or "").strip()
        payload["customerName"] = str(payload.get("customerName") or "").strip()
        payload["uploadedImageUrl"] = str(payload.get("uploadedImageUrl") or "").strip()
        payload["thumbnailUrl"] = str(payload.get("thumbnailUrl") or "").strip()
        payload["originalImageUrl"] = str(payload.get("originalImageUrl") or "").strip()
        payload["originalFilename"] = str(payload.get("originalFilename") or "").strip()
        payload["createdAt"] = str(payload.get("createdAt") or utc_now_iso())
        payload["updatedAt"] = str(payload.get("updatedAt") or payload["createdAt"])
        payload["processingStatus"] = str(payload.get("processingStatus") or "pending").strip().lower()
        if payload["processingStatus"] not in WONDERPARK_ALLOWED_STATUSES:
            payload["processingStatus"] = "pending"
        payload["paperTemplateId"] = str(payload.get("paperTemplateId") or "").strip() or None
        preset_animal = str(payload.get("presetAnimal") or "").strip().lower()
        if preset_animal not in WONDERPARK_ALLOWED_PRESET_ANIMALS:
            preset_animal = "unknown"
        payload["presetAnimal"] = preset_animal
        payload["presetAnimalSource"] = str(payload.get("presetAnimalSource") or "").strip()
        payload["queueJobId"] = str(payload.get("queueJobId") or "").strip()
        payload["latestJobId"] = str(payload.get("latestJobId") or "").strip()
        payload["generatedImageUrl"] = str(payload.get("generatedImageUrl") or "").strip()
        payload["latestOutputUrl"] = str(payload.get("latestOutputUrl") or "").strip()
        payload["error"] = str(payload.get("error") or "").strip()
        payload["sourceIp"] = str(payload.get("sourceIp") or "").strip()
        payload["imageHash"] = str(payload.get("imageHash") or "").strip()
        payload["mimeType"] = str(payload.get("mimeType") or "").strip().lower()
        payload["fileSizeBytes"] = int(payload.get("fileSizeBytes") or 0)
        payload["imageWidth"] = int(payload.get("imageWidth") or 0)
        payload["imageHeight"] = int(payload.get("imageHeight") or 0)
        payload["rateLimitInfo"] = payload.get("rateLimitInfo") if isinstance(payload.get("rateLimitInfo"), dict) else {}
        payload["retryCount"] = int(payload.get("retryCount") or 0)
        payload["processingInputPath"] = str(payload.get("processingInputPath") or "").strip()
        payload["originalStoragePath"] = str(payload.get("originalStoragePath") or "").strip()
        payload["thumbnailStoragePath"] = str(payload.get("thumbnailStoragePath") or "").strip()
        payload["sourceInputUrl"] = str(payload.get("sourceInputUrl") or payload.get("uploadedImageUrl") or "").strip()
        payload["sourceInputPath"] = str(payload.get("sourceInputPath") or payload.get("processingInputPath") or "").strip()
        payload["sourceUploadId"] = str(payload.get("sourceUploadId") or payload.get("submissionId") or "").strip()
        payload["parentSessionId"] = str(payload.get("parentSessionId") or payload.get("sourceUploadId") or payload.get("submissionId") or "").strip()
        payload["regeneratedFromJobId"] = str(payload.get("regeneratedFromJobId") or "").strip()
        payload["generationAttempt"] = max(0, int(payload.get("generationAttempt") or 0))
        payload["regenerateCount"] = max(0, int(payload.get("regenerateCount") or 0))
        result_status = str(payload.get("resultStatus") or "pending").strip().lower()
        if result_status not in WONDERPARK_ALLOWED_RESULT_STATUSES:
            result_status = "pending"
        payload["resultStatus"] = result_status
        payload["showcaseVisible"] = bool(payload.get("showcaseVisible", False))
        payload["approvedAt"] = (
            str(payload.get("approvedAt") or "").strip()
            if payload.get("approvedAt")
            else None
        )
        payload["approvedBy"] = str(payload.get("approvedBy") or "").strip()
        payload["approvedJobId"] = str(payload.get("approvedJobId") or "").strip()
        payload["approvedImageUrl"] = str(payload.get("approvedImageUrl") or "").strip()
        return payload

    @staticmethod
    def _find_index(rows: List[Dict[str, Any]], submission_id: str) -> int:
        for idx, row in enumerate(rows):
            if str(row.get("submissionId") or "") == submission_id:
                return idx
        return -1

    def list_submissions(
        self,
        *,
        search: str = "",
        status: str = "",
        limit: int = 200,
        offset: int = 0,
    ) -> Dict[str, Any]:
        search_key = str(search or "").strip().lower()
        status_key = str(status or "").strip().lower()
        with self._lock:
            rows = self._load_unlocked()
        filtered: List[Dict[str, Any]] = []
        for row in rows:
            if status_key and str(row.get("processingStatus") or "").lower() != status_key:
                continue
            if search_key:
                haystack = " ".join(
                    [
                        str(row.get("submissionId") or ""),
                        str(row.get("customerName") or ""),
                        str(row.get("originalFilename") or ""),
                    ]
                ).lower()
                if search_key not in haystack:
                    continue
            filtered.append(dict(row))
        total = len(filtered)
        safe_offset = max(0, int(offset))
        safe_limit = max(1, min(500, int(limit)))
        paged = filtered[safe_offset : safe_offset + safe_limit]
        return {"items": paged, "total": total}

    def get_submission(self, submission_id: str) -> Optional[Dict[str, Any]]:
        key = str(submission_id or "").strip()
        if not key:
            return None
        with self._lock:
            rows = self._load_unlocked()
            idx = self._find_index(rows, key)
            if idx < 0:
                return None
            return dict(rows[idx])

    def create_submission(self, row: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_row(row)
        with self._lock:
            rows = self._load_unlocked()
            idx = self._find_index(rows, str(normalized.get("submissionId") or ""))
            if idx >= 0:
                rows[idx] = normalized
            else:
                rows.append(normalized)
            self._save_unlocked(rows)
        return dict(normalized)

    def update_submission(self, submission_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        key = str(submission_id or "").strip()
        if not key:
            raise KeyError(submission_id)
        with self._lock:
            rows = self._load_unlocked()
            idx = self._find_index(rows, key)
            if idx < 0:
                raise KeyError(submission_id)
            target = dict(rows[idx])
            target.update(updates)
            target["updatedAt"] = utc_now_iso()
            rows[idx] = self._normalize_row(target)
            self._save_unlocked(rows)
            return dict(rows[idx])

    def delete_submission(self, submission_id: str) -> Optional[Dict[str, Any]]:
        key = str(submission_id or "").strip()
        if not key:
            return None
        with self._lock:
            rows = self._load_unlocked()
            idx = self._find_index(rows, key)
            if idx < 0:
                return None
            removed = rows.pop(idx)
            self._save_unlocked(rows)
            return dict(removed)

    def find_by_queue_job_id(self, queue_job_id: str) -> Optional[Dict[str, Any]]:
        key = str(queue_job_id or "").strip()
        if not key:
            return None
        with self._lock:
            rows = self._load_unlocked()
            for row in rows:
                if str(row.get("queueJobId") or "") == key:
                    return dict(row)
        return None

    def count_recent_by_ip(self, source_ip: str, window_seconds: int) -> int:
        ip_key = str(source_ip or "").strip()
        if not ip_key:
            return 0
        cutoff = datetime.now(timezone.utc).timestamp() - max(1, int(window_seconds))
        with self._lock:
            rows = self._load_unlocked()
        count = 0
        for row in rows:
            if str(row.get("sourceIp") or "").strip() != ip_key:
                continue
            created = _parse_iso(row.get("createdAt"))
            if created is None:
                continue
            if created.timestamp() >= cutoff:
                count += 1
        return count

    def find_recent_duplicate(
        self,
        *,
        source_ip: str,
        image_hash: str,
        window_seconds: int,
    ) -> Optional[Dict[str, Any]]:
        ip_key = str(source_ip or "").strip()
        hash_key = str(image_hash or "").strip().lower()
        if not ip_key or not hash_key:
            return None
        cutoff = datetime.now(timezone.utc).timestamp() - max(1, int(window_seconds))
        with self._lock:
            rows = self._load_unlocked()
        for row in rows:
            if str(row.get("sourceIp") or "").strip() != ip_key:
                continue
            if str(row.get("imageHash") or "").strip().lower() != hash_key:
                continue
            created = _parse_iso(row.get("createdAt"))
            if created is None:
                continue
            if created.timestamp() >= cutoff:
                return dict(row)
        return None

    def status_counts(self) -> Dict[str, int]:
        counts = {status: 0 for status in WONDERPARK_ALLOWED_STATUSES}
        with self._lock:
            rows = self._load_unlocked()
        for row in rows:
            status = str(row.get("processingStatus") or "pending").strip().lower()
            if status not in counts:
                status = "pending"
            counts[status] += 1
        return counts
