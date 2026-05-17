import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


QUEUE_ACTIVE_STATES = {"queued", "processing"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class QueueStore:
    def __init__(self, json_path: Path) -> None:
        self._json_path = json_path
        self._lock = threading.Lock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        self._json_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._json_path.exists():
            self._json_path.write_text("[]", encoding="utf-8")

    def _load_jobs_unlocked(self) -> List[Dict[str, Any]]:
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

    def _save_jobs_unlocked(self, jobs: List[Dict[str, Any]]) -> None:
        ordered = sorted(
            jobs,
            key=lambda item: str(item.get("createdAt") or ""),
            reverse=True,
        )
        self._json_path.write_text(
            json.dumps(ordered, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    @staticmethod
    def _find_index(jobs: List[Dict[str, Any]], job_id: str) -> int:
        for index, job in enumerate(jobs):
            if str(job.get("jobId")) == job_id:
                return index
        return -1

    def list_jobs(self) -> List[Dict[str, Any]]:
        with self._lock:
            jobs = self._load_jobs_unlocked()
        return sorted(jobs, key=lambda item: str(item.get("createdAt") or ""), reverse=True)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            jobs = self._load_jobs_unlocked()
            idx = self._find_index(jobs, job_id)
            if idx < 0:
                return None
            return dict(jobs[idx])

    def upsert_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            jobs = self._load_jobs_unlocked()
            idx = self._find_index(jobs, str(job.get("jobId") or ""))
            if idx < 0:
                jobs.append(job)
            else:
                jobs[idx] = job
            self._save_jobs_unlocked(jobs)
        return job

    def create_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        return self.upsert_job(job)

    def set_status(
        self,
        job_id: str,
        status: str,
        *,
        error: Optional[str] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
        cancelled_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            jobs = self._load_jobs_unlocked()
            idx = self._find_index(jobs, job_id)
            if idx < 0:
                raise KeyError(job_id)
            job = jobs[idx]
            job["status"] = status
            if error is not None:
                job["error"] = error
            if started_at is not None:
                job["startedAt"] = started_at
            if completed_at is not None:
                job["completedAt"] = completed_at
            if cancelled_at is not None:
                job["cancelledAt"] = cancelled_at
            jobs[idx] = job
            self._save_jobs_unlocked(jobs)
            return dict(job)

    def update_job_fields(self, job_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            jobs = self._load_jobs_unlocked()
            idx = self._find_index(jobs, job_id)
            if idx < 0:
                raise KeyError(job_id)
            job = jobs[idx]
            job.update(updates)
            jobs[idx] = job
            self._save_jobs_unlocked(jobs)
            return dict(job)

    def delete_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            jobs = self._load_jobs_unlocked()
            idx = self._find_index(jobs, job_id)
            if idx < 0:
                return None
            removed = jobs.pop(idx)
            self._save_jobs_unlocked(jobs)
            return removed

    def queue_snapshot(self) -> Dict[str, Any]:
        jobs = self.list_jobs()
        queued = [job for job in jobs if str(job.get("status")) == "queued"]
        processing = None
        for job in jobs:
            if str(job.get("status")) == "processing":
                processing = job
                break
        return {
            "jobs": jobs,
            "queued": queued,
            "processing": processing,
            "queueLength": len(queued),
        }

    def recover_unfinished_jobs(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Returns:
            (all_jobs, recovered_to_queue_jobs)
        """
        with self._lock:
            jobs = self._load_jobs_unlocked()
            recovered: List[Dict[str, Any]] = []
            for job in jobs:
                if str(job.get("status")) == "processing":
                    job["status"] = "queued"
                    job["startedAt"] = None
                    job["error"] = "Recovered after backend restart."
                    recovered.append(job)
            self._save_jobs_unlocked(jobs)
            all_jobs = list(jobs)

        queued_recovered = [job for job in all_jobs if str(job.get("status")) == "queued"]
        return all_jobs, queued_recovered

    def pop_next_queued_job(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            jobs = self._load_jobs_unlocked()
            queued = [job for job in jobs if str(job.get("status")) == "queued"]
            if not queued:
                return None
            queued.sort(
                key=lambda item: (
                    str(item.get("queuedAt") or item.get("createdAt") or ""),
                    str(item.get("createdAt") or ""),
                )
            )
            next_job_id = str(queued[0].get("jobId") or "")
            idx = self._find_index(jobs, next_job_id)
            if idx < 0:
                return None
            job = jobs[idx]
            job["status"] = "processing"
            job["startedAt"] = utc_now_iso()
            job["error"] = None
            jobs[idx] = job
            self._save_jobs_unlocked(jobs)
            return dict(job)
