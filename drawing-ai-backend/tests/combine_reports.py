import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.qa_common import RESULTS_DIR, ensure_test_dirs, utc_now_stamp


TARGET_PREFIXES = [
    "download_test",
    "api_test",
    "queue_test",
    "websocket_test",
    "stress_test",
    "system_health_report",
]


def latest_file(prefix: str, suffix: str) -> Optional[Path]:
    matches = sorted(
        RESULTS_DIR.glob(f"{prefix}_*.{suffix}"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def merge_counts(items: List[Dict[str, Any]]) -> Dict[str, int]:
    merged = {"PASS": 0, "WARNING": 0, "FAIL": 0, "DANGER": 0}
    for item in items:
        summary = item.get("summary") if isinstance(item, dict) else {}
        if not isinstance(summary, dict):
            continue
        merged["PASS"] += int(summary.get("PASS") or 0)
        merged["WARNING"] += int(summary.get("WARNING") or 0)
        merged["FAIL"] += int(summary.get("FAIL") or 0)
        merged["DANGER"] += int(summary.get("DANGER") or 0)
    return merged


def format_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True)
    return str(value)


def grouped_checks(payload: Dict[str, Any]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {
        "PASS": [],
        "WARNING": [],
        "FAIL": [],
        "DANGER": [],
    }
    checks = payload.get("checks")
    if isinstance(checks, list) and checks:
        for check in checks:
            if not isinstance(check, dict):
                continue
            level = str(check.get("level") or "").strip().upper()
            if level not in grouped:
                continue
            name = str(check.get("name") or "").strip() or "Unnamed check"
            detail = str(check.get("detail") or "").strip()
            message = f"{name}: {detail}" if detail else name
            grouped[level].append(message)
        return grouped

    fallback_map = {
        "PASS": "pass",
        "WARNING": "warning",
        "FAIL": "fail",
        "DANGER": "danger",
    }
    for level, key in fallback_map.items():
        values = payload.get(key)
        if isinstance(values, list):
            grouped[level].extend(str(item).strip() for item in values if str(item).strip())
    return grouped


def build_text(combined: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("DRAWING AI COMBINED TEST REPORT")
    lines.append(f"Generated At: {combined.get('generatedAt')}")
    lines.append("")
    lines.append("Included Reports:")
    for item in combined.get("includedReports", []):
        lines.append(
            f"- {item.get('name')}: {item.get('jsonPath')} | {item.get('txtPath')}"
        )
    lines.append("")
    lines.append("Merged Counts:")
    counts = combined.get("mergedCounts", {})
    lines.append(f"- PASS: {counts.get('PASS', 0)}")
    lines.append(f"- WARNING: {counts.get('WARNING', 0)}")
    lines.append(f"- FAIL: {counts.get('FAIL', 0)}")
    lines.append(f"- DANGER: {counts.get('DANGER', 0)}")
    lines.append("")
    lines.append("Latest Health Summary:")
    health = combined.get("latestHealth", {})
    if health:
        lines.append(f"- Overall Score: {health.get('overallScore')}")
        lines.append(f"- System Status: {health.get('systemStatus')}")
        lines.append(f"- Final System Status: {health.get('finalSystemStatus')}")
    else:
        lines.append("- Not available")
    lines.append("")
    lines.append("Per Report Status:")
    for item in combined.get("reportStatuses", []):
        lines.append(f"- {item.get('name')}: {item.get('status')}")
    lines.append("")
    lines.append("FULL REPORT DETAILS")
    for report in combined.get("reportDetails", []):
        name = report.get("name") or "unknown"
        status = report.get("status") or "unknown"
        json_path = report.get("jsonPath") or ""
        txt_path = report.get("txtPath") or ""
        payload = report.get("payload") if isinstance(report.get("payload"), dict) else {}

        lines.append("")
        lines.append(f"=== {name.upper()} ===")
        lines.append(f"Status: {status}")
        lines.append(f"JSON: {json_path or 'N/A'}")
        lines.append(f"TXT: {txt_path or 'N/A'}")

        summary = payload.get("summary")
        if isinstance(summary, dict):
            lines.append("Summary:")
            lines.append(f"- PASS: {summary.get('PASS', 0)}")
            lines.append(f"- WARNING: {summary.get('WARNING', 0)}")
            lines.append(f"- FAIL: {summary.get('FAIL', 0)}")
            lines.append(f"- DANGER: {summary.get('DANGER', 0)}")

        checks_by_level = grouped_checks(payload)
        for level in ("PASS", "WARNING", "FAIL", "DANGER"):
            entries = checks_by_level.get(level) or []
            lines.append(f"{level}:")
            if entries:
                for entry in entries:
                    lines.append(f"- {entry}")
            else:
                lines.append("- None")

        metrics = payload.get("metrics")
        if isinstance(metrics, dict):
            lines.append("Metrics:")
            if metrics:
                for key, value in metrics.items():
                    lines.append(f"- {key}: {format_value(value)}")
            else:
                lines.append("- None")

        performance = payload.get("performance")
        if isinstance(performance, dict):
            lines.append("Performance:")
            if performance:
                for key, value in performance.items():
                    lines.append(f"- {key}: {format_value(value)}")
            else:
                lines.append("- None")

        recommendations = payload.get("recommendations")
        if isinstance(recommendations, list):
            lines.append("Recommendations:")
            if recommendations:
                for recommendation in recommendations:
                    lines.append(f"- {str(recommendation)}")
            else:
                lines.append("- None")

    lines.append("")
    lines.append("Note:")
    lines.append("- This file combines the latest result for each test type with full check details.")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    ensure_test_dirs()
    included: List[Dict[str, Any]] = []
    report_payloads: List[Dict[str, Any]] = []
    report_details: List[Dict[str, Any]] = []
    report_statuses: List[Dict[str, str]] = []

    for prefix in TARGET_PREFIXES:
        latest_json = latest_file(prefix, "json")
        latest_txt = latest_file(prefix, "txt")
        if not latest_json and not latest_txt:
            continue
        payload = load_json(latest_json) if latest_json else {}
        included.append(
            {
                "name": prefix,
                "jsonPath": str(latest_json) if latest_json else "",
                "txtPath": str(latest_txt) if latest_txt else "",
            }
        )
        status_value = str(payload.get("status") or payload.get("systemStatus") or "unknown")
        report_details.append(
            {
                "name": prefix,
                "status": status_value,
                "jsonPath": str(latest_json) if latest_json else "",
                "txtPath": str(latest_txt) if latest_txt else "",
                "payload": payload,
            }
        )
        if payload:
            report_payloads.append(payload)
            report_statuses.append({"name": prefix, "status": status_value})
        else:
            report_statuses.append({"name": prefix, "status": "unknown"})

    merged_counts = merge_counts(report_payloads)
    latest_health = {}
    health_path = latest_file("system_health_report", "json")
    if health_path and health_path.is_file():
        latest_health = load_json(health_path)

    combined = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "includedReports": included,
        "mergedCounts": merged_counts,
        "reportStatuses": report_statuses,
        "reportDetails": report_details,
        "latestHealth": {
            "overallScore": latest_health.get("overallScore"),
            "systemStatus": latest_health.get("systemStatus"),
            "finalSystemStatus": latest_health.get("finalSystemStatus"),
            "sourcePath": str(health_path) if health_path else "",
        },
        "rawReports": report_payloads,
    }

    stamp = utc_now_stamp()
    json_path = RESULTS_DIR / f"combined_test_report_{stamp}.json"
    txt_path = RESULTS_DIR / f"combined_test_report_{stamp}.txt"

    json_path.write_text(json.dumps(combined, indent=2, ensure_ascii=True), encoding="utf-8")
    txt_path.write_text(build_text(combined), encoding="utf-8")

    print(f"[PASS] Combined report generated.")
    print(f"[INFO] TXT:  {txt_path}")
    print(f"[INFO] JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
