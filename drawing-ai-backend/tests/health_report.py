import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.qa_common import (
    DANGER,
    FAIL,
    PASS,
    RESULTS_DIR,
    WARNING,
    ensure_test_dirs,
    utc_now_stamp,
)


SOURCE_PREFIXES = [
    "download_test",
    "api_test",
    "queue_test",
    "websocket_test",
    "stress_test",
]


def latest_report_for_prefix(prefix: str) -> Optional[Path]:
    candidates = sorted(RESULTS_DIR.glob(f"{prefix}_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def collect_reports() -> List[Dict[str, Any]]:
    reports: List[Dict[str, Any]] = []
    for prefix in SOURCE_PREFIXES:
        report_path = latest_report_for_prefix(prefix)
        if report_path is None:
            continue
        payload = load_json(report_path)
        if isinstance(payload, dict):
            payload["_path"] = str(report_path)
            reports.append(payload)
    return reports


def collect_checks_by_level(reports: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    output = {PASS: [], WARNING: [], FAIL: [], DANGER: []}
    for report in reports:
        script = str(report.get("script") or "unknown")
        checks = report.get("checks", [])
        if not isinstance(checks, list):
            continue
        for check in checks:
            if not isinstance(check, dict):
                continue
            level = str(check.get("level") or "").upper()
            if level not in output:
                continue
            name = str(check.get("name") or "").strip()
            detail = str(check.get("detail") or "").strip()
            output[level].append(f"[{script}] {name}: {detail}")
    return output


def calculate_score(levels: Dict[str, List[str]]) -> int:
    score = 100
    score -= len(levels[WARNING]) * 2
    score -= len(levels[FAIL]) * 8
    score -= len(levels[DANGER]) * 20
    if score < 0:
        score = 0
    if score > 100:
        score = 100
    return int(score)


def score_status(score: int) -> str:
    if score == 100:
        return "PRODUCTION READY"
    if 80 <= score <= 99:
        return "GOOD"
    if 60 <= score <= 79:
        return "WARNING"
    if 40 <= score <= 59:
        return "HIGH RISK"
    return "NOT SAFE FOR PUBLIC USE"


def build_danger_conditions(stress_metrics: Dict[str, Any], levels: Dict[str, List[str]]) -> List[str]:
    dangers: List[str] = []
    queue_stuck = int(stress_metrics.get("queueStuckCount") or 0)
    sd_timeouts = int(stress_metrics.get("stableDiffusionTimeoutCount") or 0)
    failure_rate = float(stress_metrics.get("failed", 0)) / max(1, int(stress_metrics.get("totalSubmitted") or 0))
    duplicates = int(stress_metrics.get("duplicateJobCount") or 0)
    ws_event_seen = bool((stress_metrics.get("webSocketDisconnectCount") is not None))

    if queue_stuck > 0:
        dangers.append("Queue stuck for more than 60 seconds.")
    if sd_timeouts > 3:
        dangers.append("Stable Diffusion timeout exceeded 3 times.")
    if duplicates > 0:
        dangers.append("Duplicate job IDs detected.")
    if failure_rate > 0.2:
        dangers.append("More than 20% of jobs failed.")

    output_missing = any("missing outputurl" in text.lower() for text in levels[DANGER] + levels[FAIL])
    if output_missing:
        dangers.append("One or more completed jobs missing outputUrl.")

    ws_never_received = any("websocket never received events" in text.lower() for text in levels[DANGER])
    if ws_never_received or not ws_event_seen:
        dangers.append("WebSocket never receives events.")

    backend_crash = any("backend crash check" in text.lower() for text in levels[DANGER])
    if backend_crash:
        dangers.append("Backend health check failure detected during stress test.")

    return dangers


def recommend(stress_metrics: Dict[str, Any], danger_conditions: List[str], levels: Dict[str, List[str]]) -> List[str]:
    recommendations: List[str] = []
    avg_gen = float(stress_metrics.get("averageGenerationTime") or 0)
    storage_growth = int(stress_metrics.get("storageGrowthBytes") or 0)
    api_errors = int(stress_metrics.get("apiErrorCount") or 0)
    sd_timeouts = int(stress_metrics.get("stableDiffusionTimeoutCount") or 0)
    failed = int(stress_metrics.get("failed") or 0)
    submitted = max(1, int(stress_metrics.get("totalSubmitted") or 0))
    failure_rate = failed / float(submitted)

    if avg_gen > 90:
        recommendations.append("Lower generation resolution from 768 to 640 to reduce average runtime.")
    if sd_timeouts > 0:
        recommendations.append("Reduce ControlNet load or batch intensity; restart Stable Diffusion every 300 jobs.")
    if failure_rate > 0.2:
        recommendations.append("Fix high failure rate before public use; inspect /health and Stable Diffusion logs.")
    if storage_growth > 500 * 1024 * 1024:
        recommendations.append("Add scheduled storage cleanup and cap retained jobs.")
    if api_errors > 0:
        recommendations.append("Review API timeout and error logs; raise request timeout only where necessary.")
    if any("outputurl" in item.lower() for item in levels[FAIL] + levels[DANGER]):
        recommendations.append("Fix image URL routing and static file access for /inputs and /outputs.")
    if any("queue stuck" in item.lower() for item in levels[DANGER] + levels[FAIL]):
        recommendations.append("Investigate queue worker lifecycle and add automatic stuck-job recovery.")
    if any("websocket" in item.lower() for item in levels[WARNING] + levels[FAIL] + levels[DANGER]):
        recommendations.append("Harden WebSocket reconnect and heartbeat monitoring for long kiosk sessions.")

    if not recommendations:
        recommendations.append("No critical tuning recommendation from current test set.")

    # Remove duplicates while preserving order.
    deduped: List[str] = []
    seen = set()
    for item in recommendations:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def report_text(
    *,
    score: int,
    status: str,
    system_status: str,
    levels: Dict[str, List[str]],
    stress_metrics: Dict[str, Any],
    danger_conditions: List[str],
    recommendations: List[str],
    source_paths: List[str],
) -> str:
    lines: List[str] = []
    lines.append("DRAWING AI SYSTEM HEALTH REPORT")
    lines.append(f"Generated At: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append(f"Overall Score: {score}")
    lines.append(f"System Status: {status}")
    lines.append(f"Final System Status: {system_status}")
    lines.append("")
    lines.append("PASS")
    for item in levels[PASS] or ["(none)"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("WARNING")
    for item in levels[WARNING] or ["(none)"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("FAIL")
    for item in levels[FAIL] or ["(none)"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("DANGER")
    for item in (levels[DANGER] + [f"[rule] {d}" for d in danger_conditions]) or ["(none)"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("PERFORMANCE")
    lines.append(f"- Jobs tested: {stress_metrics.get('jobsTested', 0)}")
    lines.append(f"- Total submitted: {stress_metrics.get('totalSubmitted', 0)}")
    lines.append(f"- Completed: {stress_metrics.get('completed', 0)}")
    lines.append(f"- Failed: {stress_metrics.get('failed', 0)}")
    lines.append(f"- Success rate: {round(float(stress_metrics.get('successRate', 0)) * 100, 2)}%")
    lines.append(f"- Average generation time: {stress_metrics.get('averageGenerationTime', 0)}")
    lines.append(f"- Min generation time: {stress_metrics.get('minGenerationTime', 0)}")
    lines.append(f"- Max generation time: {stress_metrics.get('maxGenerationTime', 0)}")
    lines.append(f"- Peak queue size: {stress_metrics.get('peakQueueSize', 0)}")
    lines.append(f"- Max queue wait: {stress_metrics.get('maxQueueWait', 0)}")
    lines.append(f"- API error count: {stress_metrics.get('apiErrorCount', 0)}")
    lines.append(f"- Timeout count: {stress_metrics.get('timeoutCount', 0)}")
    lines.append(f"- WebSocket disconnect count: {stress_metrics.get('webSocketDisconnectCount', 0)}")
    lines.append(f"- Storage growth: {stress_metrics.get('storageGrowthBytes', 0)} bytes")
    lines.append("")
    lines.append("RECOMMENDATIONS")
    for item in recommendations:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("SOURCE REPORTS")
    for path in source_paths:
        lines.append(f"- {path}")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    ensure_test_dirs()
    reports = collect_reports()
    if not reports:
        print("[FAIL] No test report files found under tests/results.")
        return 1

    levels = collect_checks_by_level(reports)
    score = calculate_score(levels)
    status = score_status(score)

    stress_metrics: Dict[str, Any] = {}
    for report in reports:
        if str(report.get("script") or "") == "stress_test":
            if isinstance(report.get("metrics"), dict):
                stress_metrics = dict(report["metrics"])
            break

    danger_conditions = build_danger_conditions(stress_metrics, levels)
    recommendations = recommend(stress_metrics, danger_conditions, levels)

    completed = int(stress_metrics.get("completed") or 0)
    tested = int(stress_metrics.get("jobsTested") or 0)
    has_critical = bool(danger_conditions or levels[DANGER] or levels[FAIL])
    if tested >= 30 and completed >= tested and not has_critical:
        final_system_status = "SAFE FOR PILOT TEST"
    elif has_critical:
        final_system_status = "NOT READY FOR PUBLIC USE"
    else:
        final_system_status = "NEEDS TUNING BEFORE PUBLIC USE"

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "overallScore": score,
        "systemStatus": status,
        "finalSystemStatus": final_system_status,
        "pass": levels[PASS],
        "warning": levels[WARNING],
        "fail": levels[FAIL],
        "danger": levels[DANGER],
        "dangerConditions": danger_conditions,
        "performance": stress_metrics,
        "recommendations": recommendations,
        "sourceReports": [str(report.get("_path") or "") for report in reports],
    }

    timestamp = utc_now_stamp()
    txt_path = RESULTS_DIR / f"system_health_report_{timestamp}.txt"
    json_path = RESULTS_DIR / f"system_health_report_{timestamp}.json"

    txt_path.write_text(
        report_text(
            score=score,
            status=status,
            system_status=final_system_status,
            levels=levels,
            stress_metrics=stress_metrics,
            danger_conditions=danger_conditions,
            recommendations=recommendations,
            source_paths=payload["sourceReports"],
        ),
        encoding="utf-8",
    )
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    print("[PASS] Health report generated.")
    print(f"[INFO] TXT:  {txt_path}")
    print(f"[INFO] JSON: {json_path}")
    print(f"[INFO] Overall Score: {score}")
    print(f"[INFO] System Status: {status}")
    print(f"[INFO] Final System Status: {final_system_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
