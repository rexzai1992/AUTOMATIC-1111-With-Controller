import argparse
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.qa_common import (
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
    safe_int,
    with_api_key,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="API QA test for drawing-ai-backend")
    parser.add_argument("--base-url", default=env_base_url(), help="Backend base URL.")
    parser.add_argument("--api-key", default=env_api_key(), help="Optional API key.")
    parser.add_argument("--poll-timeout", type=int, default=240, help="Max seconds to wait for job terminal state.")
    parser.add_argument("--poll-interval", type=float, default=2.5, help="Polling interval seconds.")
    parser.add_argument(
        "--sd-down-check",
        action="store_true",
        help="Check expected behavior when Stable Diffusion is offline.",
    )
    return parser.parse_args()


def fetch_json(
    reporter: TestReporter,
    session,
    method: str,
    url: str,
    *,
    timeout: int = 30,
    headers: Optional[Dict[str, str]] = None,
    expected_status: Optional[int] = 200,
    **kwargs: Any,
) -> Optional[Dict[str, Any]]:
    result = request_with_timing(
        session,
        method,
        url,
        timeout=timeout,
        headers=headers,
        **kwargs,
    )
    if not result["ok"]:
        reporter.add_fail("HTTP request", f"{method} {url} failed: {result['error']}")
        return None
    response = result["response"]
    if expected_status is not None and response.status_code != expected_status:
        reporter.add_fail(
            "HTTP status",
            f"{method} {url} returned {response.status_code}, expected {expected_status}.",
        )
        return None
    payload = response_json(response)
    return payload


def verify_relative_or_http_url(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return text.startswith("/") or text.startswith("http://") or text.startswith("https://")


def main() -> int:
    args = parse_args()
    base_url = str(args.base_url).rstrip("/")
    api_key = str(args.api_key or "").strip()
    reporter = TestReporter("api_test", base_url=base_url)
    session = create_session()
    request_headers = with_api_key(api_key=api_key)

    sample_images = list_sample_images()
    if len(sample_images) < 10:
        reporter.add_warning(
            "Sample image availability",
            f"Only {len(sample_images)} image(s) in {SAMPLE_IMAGES_DIR}; less than 10.",
        )
    else:
        reporter.add_pass("Sample image availability", f"Found {len(sample_images)} sample image(s).")

    health_url = endpoint(base_url, "/health")
    health_payload = fetch_json(reporter, session, "GET", health_url, timeout=20)
    if health_payload is not None:
        backend_status = str(health_payload.get("backend") or "")
        if backend_status in {"ok", "degraded"}:
            reporter.add_pass("GET /health", f"/health reachable with backend status={backend_status}.")
        else:
            reporter.add_fail("GET /health", f"Unexpected backend status={backend_status}.")

        sd_reachable = bool((health_payload.get("stableDiffusion") or {}).get("reachable"))
        if args.sd_down_check:
            if backend_status == "degraded" and not sd_reachable:
                reporter.add_pass(
                    "SD down check",
                    "Stable Diffusion offline state detected as degraded, as expected.",
                )
            else:
                reporter.add_warning(
                    "SD down check",
                    "Stable Diffusion appears reachable; offline behavior not exercised.",
                )

    gallery_items_payload = fetch_json(reporter, session, "GET", endpoint(base_url, "/gallery/items"))
    if gallery_items_payload is not None and isinstance(gallery_items_payload.get("items"), list):
        reporter.add_pass(
            "GET /gallery/items",
            f"Returned {len(gallery_items_payload.get('items', []))} item(s).",
        )

    api_gallery_payload = fetch_json(reporter, session, "GET", endpoint(base_url, "/api/gallery"))
    if api_gallery_payload is not None and isinstance(api_gallery_payload.get("items"), list):
        reporter.add_pass(
            "GET /api/gallery",
            f"Returned {len(api_gallery_payload.get('items', []))} API item(s).",
        )

    queue_payload = fetch_json(reporter, session, "GET", endpoint(base_url, "/api/queue/status"))
    if queue_payload is not None:
        if "queueLength" in queue_payload and "jobs" in queue_payload:
            reporter.add_pass(
                "GET /api/queue/status",
                f"queueLength={queue_payload.get('queueLength')}",
            )
        else:
            reporter.add_fail("GET /api/queue/status", "Missing required fields.")

    tuning_result = request_with_timing(session, "GET", endpoint(base_url, "/reports/tuning.txt"), timeout=30)
    if tuning_result["ok"]:
        tuning_response = tuning_result["response"]
        if tuning_response.status_code == 200 and tuning_response.text.strip():
            reporter.add_pass("GET /reports/tuning.txt", "Tuning text report reachable.")
        else:
            reporter.add_fail(
                "GET /reports/tuning.txt",
                f"Unexpected response status={tuning_response.status_code}.",
            )
    else:
        reporter.add_fail("GET /reports/tuning.txt", tuning_result["error"])

    settings_result = request_with_timing(session, "GET", endpoint(base_url, "/settings/presets"), timeout=20)
    if settings_result["ok"]:
        settings_response = settings_result["response"]
        if settings_response.status_code == 200:
            reporter.add_pass("GET /settings/presets", "Preset settings endpoint is available.")
        elif settings_response.status_code == 404:
            reporter.add_warning("GET /settings/presets", "Endpoint not available (404).")
        else:
            reporter.add_fail(
                "GET /settings/presets",
                f"Unexpected status={settings_response.status_code}.",
            )
    else:
        reporter.add_fail("GET /settings/presets", settings_result["error"])

    if not sample_images:
        reporter.add_fail(
            "POST /api/jobs",
            "No sample images available. Run python tests/download_test_images.py first.",
        )
        reporter.save("api_test")
        return 1

    selected_image = sample_images[0]
    visitor_name = f"TEST_API_{uuid.uuid4().hex[:8]}"
    files = {
        "image": (selected_image.name, selected_image.read_bytes(), "image/png"),
    }
    form_data = {
        "visitorName": visitor_name,
        "generationMode": "drawing_to_artwork",
        "styleId": "auto",
    }
    create_result = request_with_timing(
        session,
        "POST",
        endpoint(base_url, "/api/jobs"),
        headers=request_headers,
        files=files,
        data=form_data,
        timeout=60,
    )
    if not create_result["ok"]:
        reporter.add_fail("POST /api/jobs", create_result["error"])
        reporter.save("api_test")
        return 1

    create_response = create_result["response"]
    create_payload = response_json(create_response)
    if create_response.status_code == 401:
        reporter.add_fail(
            "POST /api/jobs",
            "Unauthorized (401). Provide DRAWING_API_KEY if API key protection is enabled.",
        )
        reporter.save("api_test")
        return 1
    if create_response.status_code != 200:
        reporter.add_fail(
            "POST /api/jobs",
            f"Unexpected status={create_response.status_code} payload={create_payload}",
        )
        reporter.save("api_test")
        return 1

    job_id = str(create_payload.get("jobId") or "").strip()
    if not job_id:
        reporter.add_fail("POST /api/jobs", "Missing jobId in response.")
        reporter.save("api_test")
        return 1
    reporter.add_pass(
        "POST /api/jobs",
        f"Queued jobId={job_id} queuePosition={create_payload.get('queuePosition')}.",
    )

    status_payload: Dict[str, Any] = {}
    terminal_status = ""
    poll_start = time.time()
    while time.time() - poll_start < float(args.poll_timeout):
        payload = fetch_json(
            reporter,
            session,
            "GET",
            endpoint(base_url, f"/api/jobs/{job_id}"),
            timeout=20,
            expected_status=200,
        )
        if payload is None:
            break
        status_payload = payload
        current_status = str(payload.get("status") or "").lower()
        if current_status in {"completed", "failed", "cancelled"}:
            terminal_status = current_status
            break
        time.sleep(float(args.poll_interval))

    if not terminal_status:
        reporter.add_danger(
            "Job polling",
            f"Job {job_id} did not reach terminal state within {args.poll_timeout}s.",
        )
    else:
        reporter.add_pass("Job polling", f"Job reached terminal status={terminal_status}.")

    input_url = str(status_payload.get("inputUrl") or "")
    output_url = str(status_payload.get("outputUrl") or "")

    if verify_relative_or_http_url(input_url):
        reporter.add_pass("inputUrl format", f"inputUrl={input_url}")
        if "localhost" in input_url or "127.0.0.1" in input_url:
            reporter.add_fail("inputUrl LAN safety", f"inputUrl hardcoded local host: {input_url}")
        else:
            reporter.add_pass("inputUrl LAN safety", "No localhost hardcoding in inputUrl.")
    else:
        reporter.add_fail("inputUrl format", f"Invalid inputUrl={input_url}")

    if input_url.startswith("/"):
        in_result = request_with_timing(session, "GET", endpoint(base_url, input_url), timeout=20)
        if in_result["ok"] and in_result["response"].status_code == 200:
            reporter.add_pass("inputUrl reachable", f"GET {input_url} -> 200")
        else:
            status_code = in_result["response"].status_code if in_result["ok"] else "error"
            reporter.add_fail("inputUrl reachable", f"GET {input_url} failed ({status_code}).")

    if terminal_status == "completed":
        if verify_relative_or_http_url(output_url):
            if output_url.startswith("/"):
                out_result = request_with_timing(session, "GET", endpoint(base_url, output_url), timeout=20)
                if out_result["ok"] and out_result["response"].status_code == 200:
                    reporter.add_pass("outputUrl reachable", f"GET {output_url} -> 200")
                else:
                    code = out_result["response"].status_code if out_result["ok"] else "error"
                    reporter.add_danger("outputUrl reachable", f"Completed job output not reachable ({code}).")
            else:
                reporter.add_pass("outputUrl format", f"outputUrl={output_url}")
        else:
            reporter.add_danger("outputUrl format", "Missing outputUrl for completed job.")
    elif terminal_status == "failed":
        reporter.add_warning(
            "Job completion",
            f"Job failed with error: {status_payload.get('error')}",
        )

    gallery_verify = fetch_json(reporter, session, "GET", endpoint(base_url, "/api/gallery"), timeout=30)
    if gallery_verify is not None:
        items = gallery_verify.get("items", [])
        found = False
        if isinstance(items, list):
            found = any(str(item.get("jobId") or "") == job_id for item in items if isinstance(item, dict))
        if terminal_status == "completed":
            if found:
                reporter.add_pass("Gallery update", "Completed test job appears in /api/gallery.")
            else:
                reporter.add_fail("Gallery update", "Completed test job not found in /api/gallery.")
        else:
            reporter.add_warning("Gallery update", f"Job terminal status={terminal_status}; gallery presence not strict.")

    absolute_payload = fetch_json(
        reporter,
        session,
        "GET",
        endpoint(base_url, f"/api/jobs/{job_id}"),
        params={"absolute": "true"},
        timeout=20,
    )
    if absolute_payload is not None:
        abs_input = str(absolute_payload.get("inputUrl") or "")
        if abs_input.startswith(base_url):
            reporter.add_pass("absolute=true URL host", "Absolute URLs use request host.")
        else:
            reporter.add_fail(
                "absolute=true URL host",
                f"Absolute URL does not start with base host. inputUrl={abs_input}",
            )

    reporter.metrics.update(
        {
            "jobId": job_id,
            "terminalStatus": terminal_status,
            "pollTimeoutSeconds": safe_int(args.poll_timeout),
            "sampleImageUsed": str(selected_image),
            "apiKeyUsed": bool(api_key),
        }
    )
    reporter.artifacts["jobStatusPayload"] = status_payload
    reporter.save("api_test")
    return 0 if reporter.count(FAIL) == 0 and reporter.count("DANGER") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
