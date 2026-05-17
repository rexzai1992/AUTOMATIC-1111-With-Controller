import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import websocket

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.qa_common import (
    DANGER,
    FAIL,
    SAMPLE_IMAGES_DIR,
    TestReporter,
    create_session,
    endpoint,
    env_api_key,
    env_base_url,
    list_sample_images,
    request_with_timing,
    response_json,
    with_api_key,
)


EXPECTED_EVENTS = {
    "queue_updated",
    "job_started",
    "generation_complete",
    "generation_error",
    "job_cancelled",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WebSocket QA test for drawing-ai-backend")
    parser.add_argument("--base-url", default=env_base_url(), help="Backend base URL.")
    parser.add_argument("--api-key", default=env_api_key(), help="Optional API key.")
    parser.add_argument("--listen-timeout", type=int, default=180, help="Event listen timeout in seconds.")
    parser.add_argument("--receive-timeout", type=float, default=2.0, help="WebSocket recv timeout.")
    return parser.parse_args()


def base_to_ws_url(base_url: str, ws_path: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    host = parsed.netloc
    path = ws_path if ws_path.startswith("/") else f"/{ws_path}"
    return f"{scheme}://{host}{path}"


def connect_websocket(base_url: str, receive_timeout: float) -> Tuple[Optional[Any], str]:
    last_error = ""
    for ws_path in ("/api/ws", "/ws"):
        ws_url = base_to_ws_url(base_url, ws_path)
        try:
            conn = websocket.create_connection(ws_url, timeout=10)
            conn.settimeout(receive_timeout)
            return conn, ws_path
        except Exception as exc:
            last_error = f"{ws_url}: {exc}"
    return None, last_error


def submit_test_job(session, base_url: str, api_key: str, image_path: Path, visitor_name: str) -> Dict[str, Any]:
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


def maybe_delete_input_file_for_error(base_url: str, job_payload: Dict[str, Any]) -> bool:
    input_url = str(job_payload.get("inputUrl") or "")
    if not input_url.startswith("/inputs/"):
        return False
    parsed = urlparse(base_url)
    _ = parsed  # keep for symmetry; path resolution stays local project.
    project_root = Path(__file__).resolve().parents[1]
    candidate = project_root.joinpath(*input_url.lstrip("/").split("/"))
    if not candidate.is_file():
        return False
    try:
        candidate.unlink()
        return True
    except OSError:
        return False


def main() -> int:
    args = parse_args()
    base_url = str(args.base_url).rstrip("/")
    api_key = str(args.api_key or "").strip()
    reporter = TestReporter("websocket_test", base_url=base_url)
    session = create_session()

    sample_images = list_sample_images()
    if not sample_images:
        reporter.add_fail(
            "Sample image availability",
            f"No sample images found in {SAMPLE_IMAGES_DIR}.",
        )
        reporter.save("websocket_test")
        return 1

    ws_conn, ws_info = connect_websocket(base_url, float(args.receive_timeout))
    if ws_conn is None:
        reporter.add_danger("WebSocket connect", f"Failed to connect to /api/ws and /ws: {ws_info}")
        reporter.save("websocket_test")
        return 1

    reporter.add_pass("WebSocket connect", f"Connected using path {ws_info}.")
    disconnect_count = 0

    jobs: List[str] = []
    for idx in range(3):
        image_path = sample_images[idx % len(sample_images)]
        visitor = f"TEST_WS_{idx+1:02d}_{uuid.uuid4().hex[:6]}"
        submission = submit_test_job(session, base_url, api_key, image_path, visitor)
        if not submission["ok"]:
            reporter.add_fail(
                "Submit WebSocket trigger job",
                f"Index={idx+1} failed status={submission['status_code']} payload={submission['payload'] or submission['error']}",
            )
            continue
        job_id = str((submission["payload"] or {}).get("jobId") or "").strip()
        if not job_id:
            reporter.add_fail("Submit WebSocket trigger job", f"Index={idx+1} missing jobId.")
            continue
        jobs.append(job_id)
        reporter.add_pass("Submit WebSocket trigger job", f"Submitted jobId={job_id}.")

    cancel_target = jobs[1] if len(jobs) > 1 else ""
    if cancel_target:
        cancel_result = request_with_timing(
            session,
            "POST",
            endpoint(base_url, f"/jobs/{cancel_target}/cancel"),
            timeout=30,
        )
        if cancel_result["ok"] and cancel_result["response"].status_code == 200:
            reporter.add_pass("Trigger job_cancelled event", f"Cancel request sent for {cancel_target}.")
        else:
            code = cancel_result["response"].status_code if cancel_result["ok"] else "error"
            reporter.add_warning("Trigger job_cancelled event", f"Cancel request failed with status={code}.")

    error_target = jobs[2] if len(jobs) > 2 else ""
    if error_target:
        status_result = request_with_timing(
            session,
            "GET",
            endpoint(base_url, f"/api/jobs/{error_target}"),
            timeout=30,
        )
        if status_result["ok"] and status_result["response"].status_code == 200:
            status_payload = response_json(status_result["response"])
            if maybe_delete_input_file_for_error(base_url, status_payload):
                reporter.add_pass(
                    "Trigger generation_error event",
                    f"Deleted queued input file for job {error_target} to trigger controlled failure.",
                )
            else:
                reporter.add_warning(
                    "Trigger generation_error event",
                    f"Could not delete queued input file for {error_target}; error event may not be emitted.",
                )

    observed_events: Dict[str, int] = {name: 0 for name in EXPECTED_EVENTS}
    observed_payloads: List[Dict[str, Any]] = []
    start_time = time.time()

    while time.time() - start_time < float(args.listen_timeout):
        try:
            raw = ws_conn.recv()
        except websocket.WebSocketTimeoutException:
            continue
        except Exception as exc:
            disconnect_count += 1
            reporter.add_warning("WebSocket receive", f"WebSocket disconnected while listening: {exc}")
            break

        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            reporter.add_warning("WebSocket payload", "Received non-JSON event payload.")
            continue

        event_type = str(payload.get("type") or "")
        if event_type in observed_events:
            observed_events[event_type] += 1
            observed_payloads.append(payload)
            reporter.add_pass("WebSocket event", f"Received event type={event_type}.")

        if all(count > 0 for count in observed_events.values()):
            break

    ws_conn.close()

    for event_name, count in observed_events.items():
        if count > 0:
            reporter.add_pass(f"Event check {event_name}", f"Observed {count} event(s).")
        elif event_name == "generation_error":
            reporter.add_warning(
                f"Event check {event_name}",
                "No generation_error received in this run.",
            )
        else:
            reporter.add_fail(
                f"Event check {event_name}",
                "Expected event not observed.",
            )

    if sum(observed_events.values()) == 0:
        reporter.add_danger("WebSocket event stream", "No WebSocket events received at all.")
    else:
        reporter.add_pass(
            "WebSocket event stream",
            f"Total observed expected events={sum(observed_events.values())}.",
        )

    reporter.metrics.update(
        {
            "websocketPath": ws_info,
            "disconnectCount": disconnect_count,
            "observedEvents": observed_events,
            "jobsUsed": jobs,
        }
    )
    reporter.artifacts["eventPayloadSamples"] = observed_payloads[:15]
    reporter.save("websocket_test")

    has_blocker = reporter.count(DANGER) > 0 or reporter.count(FAIL) > 0
    return 1 if has_blocker else 0


if __name__ == "__main__":
    raise SystemExit(main())
