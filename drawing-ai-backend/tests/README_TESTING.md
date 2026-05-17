# Drawing AI Backend Testing Guide

This folder contains local QA, stress, WebSocket, queue, and health report tools for `drawing-ai-backend`.

All generated test jobs use visitor names starting with `TEST_`.

## Prerequisites

1. Start Stable Diffusion WebUI locally (default):
   - `http://127.0.0.1:7860`
2. Start backend:
   - `uvicorn app.main:app --host 0.0.0.0 --port 8000`
3. Optional API key:
   - Set environment variable `DRAWING_API_KEY` if protected endpoints require it.

Example:

```powershell
$env:DRAWING_BACKEND_URL="http://127.0.0.1:8000"
$env:DRAWING_API_KEY="your_key_if_needed"
```

## Download Sample Images

Download internet sample images into `tests/sample_images/` and write `tests/sample_manifest.json`:

```powershell
python tests/download_test_images.py
```

The downloader targets category-based child drawing searches and logs:
- `DOWNLOADED`
- `SKIPPED DUPLICATE`
- `FAILED`
- `RETRYING`

## Test Commands

Run API checks:

```powershell
python tests/api_test.py
```

Run queue + lifecycle checks (cancel/retry/regenerate/delete):

```powershell
python tests/queue_test.py
```

Run WebSocket checks:

```powershell
python tests/websocket_test.py
```

Quick stress test (30 jobs burst):

```powershell
python tests/stress_test.py --count 30 --delay 0
```

Real-operation simulation (30 jobs staggered):

```powershell
python tests/stress_test.py --count 30 --delay 30
```

Generate consolidated system health report:

```powershell
python tests/health_report.py
```

Combine latest reports into one full combined report:

```powershell
python tests/combine_reports.py
```

## Output Files

Per-script reports are saved to `tests/results/` as JSON and TXT.

Final health report files:

- `tests/results/system_health_report_TIMESTAMP.txt`
- `tests/results/system_health_report_TIMESTAMP.json`

Combined full report files:

- `tests/results/combined_test_report_TIMESTAMP.txt`
- `tests/results/combined_test_report_TIMESTAMP.json`

## How To Read The Report

The consolidated report includes:

- `PASS`: verified checks
- `WARNING`: non-blocking issues or missing optional coverage
- `FAIL`: failed checks
- `DANGER`: production blockers

Health score bands:

- `100`: Production Ready
- `80-99`: Good, minor fixes
- `60-79`: Warning, needs tuning
- `40-59`: High Risk
- `<40`: Not Safe for public use

## Production Readiness Rules

Production blocker examples include:

- Queue stuck for more than 60 seconds
- Stable Diffusion timeout more than 3 times
- Backend health failures during stress run
- Missing/unreachable `outputUrl` for completed jobs
- More than 20% job failure rate
- Duplicate job IDs
- No WebSocket events received

Pilot-ready condition:

- All 30 jobs complete without critical errors and no DANGER conditions.
