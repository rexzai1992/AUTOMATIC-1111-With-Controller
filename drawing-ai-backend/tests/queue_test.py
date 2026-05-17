import argparse
import itertools
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.qa_common import (
    DANGER,
    FAIL,
    PASS,
    SAMPLE_IMAGES_DIR,
    TestReporter,
    create_session,
    endpoint,
    env_api_key,
    env_base_url,
    is_test_visitor_name,
    list_sample_images,
    request_with_timing,
    response_json,
    with_api_key,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Queue QA test for drawing-ai-backend")
    parser.add_argument("--base-url", default=env_base_url(), help="Backend base URL.")
    parser.add_argument("--api-key", default=env_api_key(), help="Optional API key.")
    parser.add_argument("--count", type=int, default=10, help="Number of jobs to enqueue quickly.")
    parser.add_argument("--poll-timeout", type=int, default=420, help="Polling timeout in seconds.")
    parser.add_argument("--poll-interval", type=float, default=2.5, help="Polling interval in seconds.")
    return parser.parse_args()


def submit_job(
    session,
    base_url: str,
    api_key: str,
    image_path,
    visitor_name: str,
) -> Dict[str, Any]:
    files = {"image": (image_path.name, image_path.read_bytes(), "image/png")}
    data = {
        "visitorName": visitor_name,
        "generationMode": "drawing_to_artwork",
        "styleId": "auto",
    }
    result = request_with_timing(
        session,
        "POST",
        endpoint(base_url, "/api/jobs"),
        headers=with_api_key(api_key=api_key),
        data=data,
        files=files,
        timeout=60,
    )
    if not result["ok"]:
        return {"ok": False, "error": result["error"], "status_code": None, "payload": {}}
    response = result["response"]
    return {
        "ok": response.status_code == 200,
        "error": "",
        "status_code": response.status_code,
        "payload": response_json(response),
    }


def fetch_job_status(session, base_url: str, job_id: str) -> Dict[str, Any]:
    result = request_with_timing(
        session,
        "GET",
        endpoint(base_url, f"/api/jobs/{job_id}"),
        timeout=30,
    )
    if not result["ok"]:
        return {"ok": False, "status": "", "payload": {}, "error": result["error"]}
    response = result["response"]
    payload = response_json(response)
    return {
        "ok": response.status_code == 200,
        "status": str(payload.get("status") or "").lower(),
        "payload": payload,
        "error": "" if response.status_code == 200 else str(payload),
    }


def fetch_queue_status(session, base_url: str) -> Dict[str, Any]:
    result = request_with_timing(
        session,
        "GET",
        endpoint(base_url, "/api/queue/status"),
        timeout=30,
    )
    if not result["ok"]:
        return {"ok": False, "payload": {}, "error": result["error"]}
    response = result["response"]
    payload = response_json(response)
    return {
        "ok": response.status_code == 200,
        "payload": payload,
        "error": "" if response.status_code == 200 else str(payload),
    }


def main() -> int:
    args = parse_args()
    base_url = str(args.base_url).rstrip("/")
    api_key = str(args.api_key or "").strip()
    reporter = TestReporter("queue_test", base_url=base_url)
    session = create_session()

    sample_images = list_sample_images()
    if not sample_images:
        reporter.add_fail(
            "Sample image availability",
            f"No images found in {SAMPLE_IMAGES_DIR}. Run python tests/download_test_images.py first.",
        )
        reporter.save("queue_test")
        return 1

    if len(sample_images) < 10:
        reporter.add_warning(
            "Sample image availability",
            f"Only {len(sample_images)} sample images available.",
        )
    else:
        reporter.add_pass("Sample image availability", f"Found {len(sample_images)} sample images.")

    created_jobs: List[Dict[str, Any]] = []
    duplicate_ids: set[str] = set()
    unique_ids: set[str] = set()
    queue_positions: List[int] = []
    submit_failures = 0
    image_cycle = itertools.cycle(sample_images)

    for index in range(int(args.count)):
        image_path = next(image_cycle)
        visitor = f"TEST_QUEUE_{index+1:02d}_{uuid.uuid4().hex[:6]}"
        submission = submit_job(session, base_url, api_key, image_path, visitor)
        if not submission["ok"]:
            status_code = submission.get("status_code")
            payload = submission.get("payload")
            submit_failures += 1
            reporter.add_fail(
                "Queue submit",
                f"Submit index={index+1} failed status={status_code} payload={payload or submission.get('error')}",
            )
            continue

        payload = submission["payload"]
        job_id = str(payload.get("jobId") or "").strip()
        queue_pos = int(payload.get("queuePosition") or 0)
        if not job_id:
            submit_failures += 1
            reporter.add_fail("Queue submit", f"Missing jobId for index={index+1}.")
            continue
        if job_id in unique_ids:
            duplicate_ids.add(job_id)
        unique_ids.add(job_id)
        queue_positions.append(queue_pos)
        created_jobs.append(
            {
                "jobId": job_id,
                "visitorName": visitor,
                "initialQueuePosition": queue_pos,
                "status": "queued",
            }
        )

    if submit_failures == 0:
        reporter.add_pass("Queue submit", f"Submitted {len(created_jobs)} test jobs.")
    else:
        reporter.add_fail(
            "Queue submit",
            f"{submit_failures} submission(s) failed out of {int(args.count)}.",
        )

    if duplicate_ids:
        reporter.add_danger("Duplicate job IDs", f"Detected duplicate IDs: {sorted(duplicate_ids)}")
    else:
        reporter.add_pass("Duplicate job IDs", "No duplicate job IDs detected.")

    if queue_positions:
        if max(queue_positions) > 1:
            reporter.add_pass(
                "Queue position assignment",
                f"Queue positions returned: min={min(queue_positions)} max={max(queue_positions)}.",
            )
        else:
            reporter.add_warning(
                "Queue position assignment",
                "Queue position did not exceed 1; test load may have been too low or processing too fast.",
            )

    cancel_target_id = ""
    queue_payload = fetch_queue_status(session, base_url)
    if queue_payload["ok"]:
        jobs = queue_payload["payload"].get("jobs", [])
        if isinstance(jobs, list):
            for item in jobs:
                if not isinstance(item, dict):
                    continue
                jid = str(item.get("jobId") or "")
                status = str(item.get("status") or "").lower()
                if jid in unique_ids and status == "queued":
                    cancel_target_id = jid
                    break

    if cancel_target_id:
        cancel_result = request_with_timing(
            session,
            "POST",
            endpoint(base_url, f"/jobs/{cancel_target_id}/cancel"),
            timeout=30,
        )
        if cancel_result["ok"] and cancel_result["response"].status_code == 200:
            payload = response_json(cancel_result["response"])
            cancelled_status = str(((payload.get("job") or {}).get("status") or "")).lower()
            if cancelled_status in {"cancelled", "queued", "processing"}:
                reporter.add_pass("Cancel queued job", f"Cancel request accepted for {cancel_target_id}.")
            else:
                reporter.add_warning(
                    "Cancel queued job",
                    f"Cancel endpoint returned unexpected status={cancelled_status}.",
                )
        else:
            code = cancel_result["response"].status_code if cancel_result["ok"] else "error"
            reporter.add_fail("Cancel queued job", f"Cancel request failed status={code}.")
    else:
        reporter.add_warning("Cancel queued job", "No queued test job found to cancel.")

    tracked_ids = [item["jobId"] for item in created_jobs]
    job_states: Dict[str, str] = {job_id: "queued" for job_id in tracked_ids}
    peak_queue_size = 0
    max_processing = 0
    queue_stuck_count = 0
    last_progress = time.time()
    last_signature = ""
    monitoring_start = time.time()

    while time.time() - monitoring_start < float(args.poll_timeout):
        all_terminal = True
        for job_id in tracked_ids:
            status_payload = fetch_job_status(session, base_url, job_id)
            if not status_payload["ok"]:
                reporter.add_fail("Job status polling", f"Failed to fetch status for {job_id}: {status_payload['error']}")
                continue
            new_status = status_payload["status"]
            if new_status != job_states.get(job_id):
                job_states[job_id] = new_status
                last_progress = time.time()
            if new_status not in {"completed", "failed", "cancelled"}:
                all_terminal = False

        queue_status = fetch_queue_status(session, base_url)
        if queue_status["ok"]:
            payload = queue_status["payload"]
            queue_len = int(payload.get("queueLength") or 0)
            peak_queue_size = max(peak_queue_size, queue_len)
            current_job = str(payload.get("currentJob") or "")
            processing_count = sum(1 for status in job_states.values() if status == "processing")
            max_processing = max(max_processing, processing_count)
            signature = f"{current_job}:{queue_len}:{processing_count}:{sorted(job_states.items())}"
            if signature != last_signature:
                last_signature = signature
                last_progress = time.time()

            if queue_len > 0 and (time.time() - last_progress) > 60:
                queue_stuck_count += 1
                reporter.add_danger(
                    "Queue stuck detection",
                    "Queue appears stuck for more than 60 seconds.",
                )
                last_progress = time.time()
        else:
            reporter.add_fail("Queue status polling", queue_status["error"])

        if all_terminal:
            break
        time.sleep(float(args.poll_interval))

    unresolved = [job_id for job_id, status in job_states.items() if status not in {"completed", "failed", "cancelled"}]
    if unresolved:
        reporter.add_danger(
            "Queue terminal state",
            f"Jobs not terminal within timeout: {unresolved}",
        )
    else:
        reporter.add_pass("Queue terminal state", "All submitted jobs reached terminal state.")

    if max_processing <= 1:
        reporter.add_pass("One-by-one processing", f"Max simultaneous processing jobs={max_processing}.")
    else:
        reporter.add_fail("One-by-one processing", f"Detected {max_processing} simultaneous processing jobs.")

    if queue_stuck_count == 0:
        reporter.add_pass("Queue stuck detection", "No stuck queue interval >60s detected.")

    completed_jobs = [jid for jid, status in job_states.items() if status == "completed"]
    failed_jobs = [jid for jid, status in job_states.items() if status == "failed"]

    retry_target = failed_jobs[0] if failed_jobs else ""
    if retry_target:
        retry_result = request_with_timing(
            session,
            "POST",
            endpoint(base_url, f"/jobs/{retry_target}/retry"),
            headers=with_api_key(api_key=api_key),
            timeout=30,
        )
        if retry_result["ok"]:
            response = retry_result["response"]
            if response.status_code == 200:
                reporter.add_pass("Retry failed job", f"Retry accepted for job {retry_target}.")
            elif response.status_code == 401:
                reporter.add_warning(
                    "Retry failed job",
                    "Retry endpoint requires API key. Set DRAWING_API_KEY to run this check.",
                )
            else:
                reporter.add_fail(
                    "Retry failed job",
                    f"Retry returned status={response.status_code} payload={response_json(response)}",
                )
        else:
            reporter.add_fail("Retry failed job", retry_result["error"])
    else:
        reporter.add_warning("Retry failed job", "No failed test job found to retry.")

    regenerate_target = completed_jobs[0] if completed_jobs else ""
    regenerated_job_id = ""
    if regenerate_target:
        regen_payload = {"problemTags": ["not_lively_enough", "bad_colors"]}
        regen_result = request_with_timing(
            session,
            "POST",
            endpoint(base_url, f"/jobs/{regenerate_target}/regenerate"),
            headers=with_api_key({"Content-Type": "application/json"}, api_key=api_key),
            json=regen_payload,
            timeout=45,
        )
        if regen_result["ok"]:
            response = regen_result["response"]
            payload = response_json(response)
            if response.status_code == 200:
                job_info = payload.get("job") or {}
                regenerated_job_id = str(job_info.get("jobId") or "")
                regeneration_of = str(job_info.get("regenerationOf") or "")
                if regenerated_job_id and regeneration_of == regenerate_target:
                    reporter.add_pass(
                        "Regenerate with fix",
                        f"Regenerated job {regenerated_job_id} linked to source {regenerate_target}.",
                    )
                else:
                    reporter.add_fail(
                        "Regenerate with fix",
                        f"Unexpected regenerate payload: {payload}",
                    )
            elif response.status_code == 401:
                reporter.add_warning(
                    "Regenerate with fix",
                    "Regenerate endpoint requires API key. Set DRAWING_API_KEY to run this check.",
                )
            else:
                reporter.add_fail(
                    "Regenerate with fix",
                    f"Regenerate returned status={response.status_code} payload={payload}",
                )
        else:
            reporter.add_fail("Regenerate with fix", regen_result["error"])
    else:
        reporter.add_warning("Regenerate with fix", "No completed test job available for regeneration.")

    delete_target = completed_jobs[1] if len(completed_jobs) > 1 else (completed_jobs[0] if completed_jobs else "")
    if delete_target:
        delete_result = request_with_timing(
            session,
            "DELETE",
            endpoint(base_url, f"/jobs/{delete_target}"),
            headers=with_api_key(api_key=api_key),
            timeout=45,
        )
        if delete_result["ok"]:
            response = delete_result["response"]
            payload = response_json(response)
            if response.status_code == 200 and payload.get("deleted") is True:
                reporter.add_pass("Delete completed test job", f"Deleted job {delete_target}.")
            elif response.status_code == 401:
                reporter.add_warning(
                    "Delete completed test job",
                    "Delete endpoint requires API key. Set DRAWING_API_KEY to run this check.",
                )
            else:
                reporter.add_fail(
                    "Delete completed test job",
                    f"Delete returned status={response.status_code} payload={payload}",
                )
        else:
            reporter.add_fail("Delete completed test job", delete_result["error"])
    else:
        reporter.add_warning("Delete completed test job", "No completed job available for deletion test.")

    gallery_result = request_with_timing(session, "GET", endpoint(base_url, "/api/gallery"), timeout=30)
    if gallery_result["ok"] and gallery_result["response"].status_code == 200:
        payload = response_json(gallery_result["response"])
        items = payload.get("items", [])
        if isinstance(items, list):
            non_test_items_touched = any(
                isinstance(item, dict)
                and str(item.get("jobId") or "") in tracked_ids
                and not is_test_visitor_name(item.get("visitorName"))
                for item in items
            )
            if non_test_items_touched:
                reporter.add_fail(
                    "Test safety guard",
                    "Detected touched item without TEST_ visitor prefix.",
                )
            else:
                reporter.add_pass("Test safety guard", "Only TEST_ jobs were targeted by lifecycle operations.")
    else:
        reporter.add_warning("Gallery verification", "Unable to verify gallery safety check.")

    reporter.metrics.update(
        {
            "submittedJobs": len(created_jobs),
            "submitFailures": submit_failures,
            "duplicateJobCount": len(duplicate_ids),
            "peakQueueSize": peak_queue_size,
            "maxSimultaneousProcessing": max_processing,
            "queueStuckCount": queue_stuck_count,
            "completedCount": len(completed_jobs),
            "failedCount": len(failed_jobs),
            "cancelTargetId": cancel_target_id,
            "retryTargetId": retry_target,
            "regeneratedJobId": regenerated_job_id,
            "pollTimeoutSeconds": int(args.poll_timeout),
        }
    )
    reporter.artifacts["trackedJobIds"] = tracked_ids
    reporter.artifacts["jobStates"] = job_states
    reporter.save("queue_test")

    has_blocker = reporter.count(DANGER) > 0 or reporter.count(FAIL) > 0
    return 1 if has_blocker else 0


if __name__ == "__main__":
    raise SystemExit(main())
