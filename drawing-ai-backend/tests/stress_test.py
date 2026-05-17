import argparse
import itertools
import json
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import psutil
import requests
import websocket

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.qa_common import (
    DANGER,
    FAIL,
    PROJECT_ROOT as QA_PROJECT_ROOT,
    SAMPLE_IMAGES_DIR,
    TestReporter,
    directory_size_bytes,
    endpoint,
    env_api_key,
    env_base_url,
    is_test_visitor_name,
    list_sample_images,
    request_with_timing,
    response_json,
    safe_float,
    safe_int,
    with_api_key,
)


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class WebSocketMonitor:
    def __init__(self, base_url: str, receive_timeout: float = 2.0) -> None:
        self.base_url = base_url
        self.receive_timeout = receive_timeout
        self.event_counts: Dict[str, int] = {}
        self.disconnect_count = 0
        self.connect_path = ""
        self.connect_failures = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._lock = threading.Lock()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "eventCounts": dict(self.event_counts),
                "disconnectCount": int(self.disconnect_count),
                "connectFailures": int(self.connect_failures),
                "path": self.connect_path,
            }

    def _ws_url(self, ws_path: str) -> str:
        parsed = urlparse(self.base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        return f"{scheme}://{parsed.netloc}{ws_path}"

    def _connect(self):
        last_error = None
        for path in ("/api/ws", "/ws"):
            url = self._ws_url(path)
            try:
                conn = websocket.create_connection(url, timeout=10)
                conn.settimeout(self.receive_timeout)
                with self._lock:
                    self.connect_path = path
                return conn
            except Exception as exc:
                last_error = exc
        raise RuntimeError(str(last_error or "Unable to connect websocket"))

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                conn = self._connect()
            except Exception:
                with self._lock:
                    self.connect_failures += 1
                time.sleep(2)
                continue

            try:
                while not self._stop.is_set():
                    try:
                        raw = conn.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    except Exception:
                        with self._lock:
                            self.disconnect_count += 1
                        break
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    event_type = str(payload.get("type") or "")
                    if not event_type:
                        continue
                    with self._lock:
                        self.event_counts[event_type] = self.event_counts.get(event_type, 0) + 1
            finally:
                try:
                    conn.close()
                except Exception:
                    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stress and throttling test for drawing-ai-backend")
    parser.add_argument("--base-url", default=env_base_url(), help="Backend base URL.")
    parser.add_argument("--api-key", default=env_api_key(), help="Optional API key.")
    parser.add_argument("--count", type=int, default=30, help="Number of jobs to submit. Default is 30.")
    parser.add_argument("--delay", type=float, default=0.0, help="Delay seconds between submissions.")
    parser.add_argument("--poll-interval", type=float, default=2.5, help="Polling interval seconds.")
    parser.add_argument(
        "--max-runtime",
        type=int,
        default=900,
        help="Max seconds to monitor processing before timeout.",
    )
    return parser.parse_args()


def load_system_metrics() -> Dict[str, float]:
    mem = psutil.virtual_memory()
    return {
        "cpuPercent": float(psutil.cpu_percent(interval=0.0)),
        "ramPercent": float(mem.percent),
        "ramUsedMB": round(mem.used / (1024 * 1024), 2),
    }


def storage_total_bytes() -> int:
    roots = [QA_PROJECT_ROOT / "inputs", QA_PROJECT_ROOT / "outputs", QA_PROJECT_ROOT / "data"]
    return sum(directory_size_bytes(root) for root in roots)


def submit_job(session, base_url: str, api_key: str, image_path: Path, visitor_name: str) -> Dict[str, Any]:
    files = {"image": (image_path.name, image_path.read_bytes(), "image/png")}
    data = {"visitorName": visitor_name, "generationMode": "drawing_to_artwork", "styleId": "auto"}
    result = request_with_timing(
        session,
        "POST",
        endpoint(base_url, "/api/jobs"),
        headers=with_api_key(api_key=api_key),
        files=files,
        data=data,
        timeout=60,
    )
    if not result["ok"]:
        return {"ok": False, "status_code": None, "payload": {}, "error": result["error"]}
    response = result["response"]
    return {
        "ok": response.status_code == 200,
        "status_code": response.status_code,
        "payload": response_json(response),
        "error": "",
    }


def fetch_queue_status(session, base_url: str) -> Dict[str, Any]:
    result = request_with_timing(session, "GET", endpoint(base_url, "/api/queue/status"), timeout=30)
    if not result["ok"]:
        return {"ok": False, "payload": {}, "error": result["error"]}
    response = result["response"]
    payload = response_json(response)
    return {"ok": response.status_code == 200, "payload": payload, "error": "" if response.status_code == 200 else str(payload)}


def fetch_job(session, base_url: str, job_id: str) -> Dict[str, Any]:
    result = request_with_timing(session, "GET", endpoint(base_url, f"/api/jobs/{job_id}"), timeout=30)
    if not result["ok"]:
        return {"ok": False, "payload": {}, "status": "", "error": result["error"]}
    response = result["response"]
    payload = response_json(response)
    return {
        "ok": response.status_code == 200,
        "payload": payload,
        "status": str(payload.get("status") or "").lower(),
        "error": "" if response.status_code == 200 else str(payload),
    }


def main() -> int:
    args = parse_args()
    base_url = str(args.base_url).rstrip("/")
    api_key = str(args.api_key or "").strip()
    reporter = TestReporter("stress_test", base_url=base_url)
    session = requests.Session()
    session.headers.update({"User-Agent": "drawing-ai-backend-stress-test/1.0"})

    if int(args.count) <= 0:
        reporter.add_fail("Argument validation", "--count must be greater than 0.")
        reporter.save("stress_test")
        return 1

    if int(args.count) > 30:
        reporter.add_warning(
            "Job count safety",
            f"Running with count={int(args.count)}. Default is 30; larger counts are manual.",
        )
    else:
        reporter.add_pass("Job count safety", f"Running within default load count={int(args.count)}.")

    sample_images = list_sample_images()
    if len(sample_images) < 10:
        reporter.add_warning(
            "Sample image availability",
            f"Only {len(sample_images)} image(s) in {SAMPLE_IMAGES_DIR}.",
        )
    else:
        reporter.add_pass("Sample image availability", f"Found {len(sample_images)} sample image(s).")

    if not sample_images:
        reporter.add_fail("Sample image availability", "No sample images available for stress test.")
        reporter.save("stress_test")
        return 1

    storage_before = storage_total_bytes()
    system_samples: List[Dict[str, float]] = [load_system_metrics()]
    ws_monitor = WebSocketMonitor(base_url)
    ws_monitor.start()

    submitted: List[str] = []
    duplicate_ids: set[str] = set()
    queue_positions: List[int] = []
    api_error_count = 0
    submit_failed = 0
    image_cycle = itertools.cycle(sample_images)
    submit_started = time.time()

    for index in range(int(args.count)):
        image_path = next(image_cycle)
        visitor = f"TEST_STRESS_{index+1:03d}_{uuid.uuid4().hex[:8]}"
        submission = submit_job(session, base_url, api_key, image_path, visitor)
        if not submission["ok"]:
            api_error_count += 1
            submit_failed += 1
            reporter.add_fail(
                "Job submit",
                f"Index={index+1} failed status={submission['status_code']} payload={submission['payload'] or submission['error']}",
            )
        else:
            payload = submission["payload"]
            job_id = str(payload.get("jobId") or "").strip()
            if not job_id:
                api_error_count += 1
                submit_failed += 1
                reporter.add_fail("Job submit", f"Index={index+1} response missing jobId.")
            else:
                if job_id in submitted:
                    duplicate_ids.add(job_id)
                submitted.append(job_id)
                queue_positions.append(int(payload.get("queuePosition") or 0))

        if float(args.delay) > 0:
            time.sleep(float(args.delay))

    submit_duration = round(time.time() - submit_started, 3)
    if submit_failed == 0:
        reporter.add_pass("Submit phase", f"Submitted {len(submitted)} jobs in {submit_duration}s.")
    else:
        reporter.add_fail(
            "Submit phase",
            f"Submitted {len(submitted)} jobs with {submit_failed} submission failure(s).",
        )

    if duplicate_ids:
        reporter.add_danger("Duplicate job detection", f"Duplicate IDs detected: {sorted(duplicate_ids)}")
    else:
        reporter.add_pass("Duplicate job detection", "No duplicate job IDs detected.")

    if queue_positions and max(queue_positions) > 1:
        reporter.add_pass("Queue position updates", f"Queue positions observed up to {max(queue_positions)}.")
    else:
        reporter.add_warning("Queue position updates", "Queue positions did not show values above 1.")

    job_states: Dict[str, str] = {job_id: "queued" for job_id in submitted}
    duration_by_job: Dict[str, float] = {}
    timeout_count = 0
    timeout_jobs: set[str] = set()
    output_missing_jobs: set[str] = set()
    peak_queue_size = 0
    max_queue_wait = 0
    max_processing = 0
    queue_stuck_count = 0
    health_fail_count = 0
    last_progress = time.time()
    last_signature = ""
    monitor_start = time.time()

    while time.time() - monitor_start < float(args.max_runtime):
        all_terminal = True
        queue_result = fetch_queue_status(session, base_url)
        queue_payload = queue_result["payload"] if queue_result["ok"] else {}
        if not queue_result["ok"]:
            api_error_count += 1
            reporter.add_fail("Queue status", queue_result["error"])
        else:
            queue_len = int(queue_payload.get("queueLength") or 0)
            peak_queue_size = max(peak_queue_size, queue_len)
            max_queue_wait = max(max_queue_wait, int(queue_payload.get("estimatedWaitSeconds") or 0))
            jobs = queue_payload.get("jobs", [])
            if isinstance(jobs, list):
                for item in jobs:
                    if not isinstance(item, dict):
                        continue
                    job_id = str(item.get("jobId") or "")
                    if job_id not in job_states:
                        continue
                    new_status = str(item.get("status") or "").lower()
                    if new_status and new_status != job_states.get(job_id):
                        job_states[job_id] = new_status
                        last_progress = time.time()

            processing_count = sum(1 for status in job_states.values() if status == "processing")
            max_processing = max(max_processing, processing_count)
            current_job = str(queue_payload.get("currentJob") or "")
            signature = f"{current_job}:{queue_len}:{processing_count}:{sorted(job_states.items())}"
            if signature != last_signature:
                last_signature = signature
                last_progress = time.time()

            if queue_len > 0 and (time.time() - last_progress) > 60:
                queue_stuck_count += 1
                reporter.add_danger(
                    "Queue stuck detection",
                    "Queue unchanged for more than 60 seconds while jobs remain queued.",
                )
                last_progress = time.time()

        for job_id in submitted:
            status = job_states.get(job_id, "")
            if status in TERMINAL_STATUSES:
                continue
            detail = fetch_job(session, base_url, job_id)
            if not detail["ok"]:
                api_error_count += 1
                continue
            payload = detail["payload"]
            new_status = detail["status"]
            old_status = job_states.get(job_id, "")
            if new_status and new_status != old_status:
                job_states[job_id] = new_status
                last_progress = time.time()
            if new_status in TERMINAL_STATUSES:
                duration_seconds = safe_float(payload.get("durationSeconds"), 0.0)
                if duration_seconds > 0:
                    duration_by_job[job_id] = duration_seconds
                if new_status == "failed":
                    error_text = str(payload.get("error") or "").lower()
                    if "timeout" in error_text:
                        timeout_jobs.add(job_id)
                if new_status == "completed":
                    output_url = str(payload.get("outputUrl") or "")
                    if not output_url:
                        output_missing_jobs.add(job_id)
                        reporter.add_danger(
                            "Output URL validation",
                            f"Completed job {job_id} missing outputUrl.",
                        )
                    elif output_url.startswith("/"):
                        output_result = request_with_timing(
                            session,
                            "GET",
                            endpoint(base_url, output_url),
                            timeout=20,
                        )
                        if not output_result["ok"] or output_result["response"].status_code != 200:
                            output_missing_jobs.add(job_id)
                            reporter.add_danger(
                                "Output URL validation",
                                f"Completed job {job_id} output not reachable.",
                            )

            if job_states.get(job_id) not in TERMINAL_STATUSES:
                all_terminal = False

        health_result = request_with_timing(session, "GET", endpoint(base_url, "/health"), timeout=15)
        if not health_result["ok"] or health_result["response"].status_code != 200:
            health_fail_count += 1
            api_error_count += 1
        system_samples.append(load_system_metrics())

        if all(job_states.get(job_id) in TERMINAL_STATUSES for job_id in submitted):
            all_terminal = True

        if all_terminal:
            break
        time.sleep(float(args.poll_interval))

    ws_snapshot = ws_monitor.snapshot()
    ws_monitor.stop()

    unresolved_jobs = [jid for jid, status in job_states.items() if status not in TERMINAL_STATUSES]
    if unresolved_jobs:
        timeout_count += len(unresolved_jobs)
        reporter.add_danger(
            "Monitor timeout",
            f"{len(unresolved_jobs)} job(s) did not reach terminal state within max runtime.",
        )

    # Final reconciliation pass for exact end-state metrics.
    for job_id in submitted:
        detail = fetch_job(session, base_url, job_id)
        if not detail["ok"]:
            continue
        payload = detail["payload"]
        final_status = str(payload.get("status") or "").lower()
        if final_status:
            job_states[job_id] = final_status
        duration_seconds = safe_float(payload.get("durationSeconds"), 0.0)
        if duration_seconds > 0:
            duration_by_job[job_id] = duration_seconds
        if final_status == "failed":
            error_text = str(payload.get("error") or "").lower()
            if "timeout" in error_text:
                timeout_jobs.add(job_id)
        if final_status == "completed":
            output_url = str(payload.get("outputUrl") or "")
            if not output_url:
                output_missing_jobs.add(job_id)

    completed_count = sum(1 for status in job_states.values() if status == "completed")
    failed_count = sum(1 for status in job_states.values() if status == "failed")
    cancelled_count = sum(1 for status in job_states.values() if status == "cancelled")
    total_submitted = len(submitted)
    success_rate = (completed_count / total_submitted) if total_submitted > 0 else 0.0
    failure_rate = (failed_count / total_submitted) if total_submitted > 0 else 0.0
    durations = list(duration_by_job.values())
    avg_duration = round(sum(durations) / len(durations), 3) if durations else 0.0
    min_duration = round(min(durations), 3) if durations else 0.0
    max_duration = round(max(durations), 3) if durations else 0.0
    storage_after = storage_total_bytes()
    storage_growth = storage_after - storage_before
    sd_timeout_count = len(timeout_jobs)
    output_missing_for_completed = len(output_missing_jobs)
    timeout_count += sd_timeout_count

    if max_processing <= 1:
        reporter.add_pass("One-by-one queue processing", f"Max simultaneous processing={max_processing}.")
    else:
        reporter.add_fail("One-by-one queue processing", f"Detected simultaneous processing count={max_processing}.")

    if health_fail_count == 0:
        reporter.add_pass("Backend crash check", "No health check failures detected during stress run.")
    else:
        reporter.add_danger("Backend crash check", f"Health check failures detected: {health_fail_count}.")

    if ws_snapshot.get("eventCounts"):
        reporter.add_pass("WebSocket events observed", f"Event counts={ws_snapshot.get('eventCounts')}.")
    else:
        reporter.add_danger("WebSocket events observed", "WebSocket never received events.")

    if failure_rate > 0.2:
        reporter.add_danger(
            "Failure rate threshold",
            f"Failure rate is {round(failure_rate * 100, 2)}%, above 20%.",
        )
    elif failure_rate > 0:
        reporter.add_warning(
            "Failure rate threshold",
            f"Failure rate is {round(failure_rate * 100, 2)}%.",
        )
    else:
        reporter.add_pass("Failure rate threshold", "No failed jobs in stress run.")

    if queue_stuck_count == 0:
        reporter.add_pass("Queue stuck threshold", "No queue stuck interval >60s.")
    if sd_timeout_count > 3:
        reporter.add_danger("Stable Diffusion timeout threshold", f"Detected {sd_timeout_count} timeout-related failures.")
    elif sd_timeout_count > 0:
        reporter.add_warning("Stable Diffusion timeout threshold", f"Detected {sd_timeout_count} timeout-related failures.")
    else:
        reporter.add_pass("Stable Diffusion timeout threshold", "No timeout-related failures detected.")

    if output_missing_for_completed > 0:
        reporter.add_danger(
            "Completed output integrity",
            f"{output_missing_for_completed} completed job(s) had missing/unreachable outputUrl.",
        )
    else:
        reporter.add_pass("Completed output integrity", "All completed jobs have reachable outputUrl.")

    # Non-destructive storage cleanup endpoint check only.
    cleanup_result = request_with_timing(
        session,
        "POST",
        endpoint(base_url, "/maintenance/cleanup"),
        json={"keepNewest": 99999999},
        timeout=60,
    )
    if cleanup_result["ok"] and cleanup_result["response"].status_code == 200:
        reporter.add_pass(
            "Storage cleanup endpoint",
            "Cleanup endpoint reachable with non-destructive keepNewest check.",
        )
    else:
        code = cleanup_result["response"].status_code if cleanup_result["ok"] else "error"
        reporter.add_warning("Storage cleanup endpoint", f"Cleanup endpoint check failed ({code}).")

    avg_cpu = round(sum(sample["cpuPercent"] for sample in system_samples) / len(system_samples), 2) if system_samples else 0.0
    avg_ram = round(sum(sample["ramPercent"] for sample in system_samples) / len(system_samples), 2) if system_samples else 0.0

    reporter.metrics.update(
        {
            "jobsTested": int(args.count),
            "totalSubmitted": total_submitted,
            "completed": completed_count,
            "failed": failed_count,
            "cancelled": cancelled_count,
            "successRate": round(success_rate, 4),
            "averageGenerationTime": avg_duration,
            "minGenerationTime": min_duration,
            "maxGenerationTime": max_duration,
            "peakQueueSize": peak_queue_size,
            "maxQueueWait": max_queue_wait,
            "apiErrorCount": api_error_count,
            "timeoutCount": timeout_count,
            "queueStuckCount": queue_stuck_count,
            "stableDiffusionTimeoutCount": sd_timeout_count,
            "duplicateJobCount": len(duplicate_ids),
            "webSocketDisconnectCount": safe_int(ws_snapshot.get("disconnectCount"), 0),
            "storageGrowthBytes": int(storage_growth),
            "storageBeforeBytes": int(storage_before),
            "storageAfterBytes": int(storage_after),
            "avgCpuPercent": avg_cpu,
            "avgRamPercent": avg_ram,
            "submitDurationSeconds": submit_duration,
            "delayBetweenSubmissionsSeconds": float(args.delay),
        }
    )
    reporter.artifacts.update(
        {
            "trackedJobIds": submitted,
            "jobStates": job_states,
            "webSocketSnapshot": ws_snapshot,
        }
    )
    reporter.save("stress_test")

    has_blocker = reporter.count(DANGER) > 0 or reporter.count(FAIL) > 0
    return 1 if has_blocker else 0


if __name__ == "__main__":
    raise SystemExit(main())
