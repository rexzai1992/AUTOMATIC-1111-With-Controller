# drawing-ai-backend

Local offline backend for a complete drawing workflow:

- Staff control page (`/staff`)
- Scanner folder auto-import (`scanner_inputs/`)
- Webcam capture endpoint (`/capture`)
- Stable Diffusion img2img + ControlNet generation
- Live public gallery wall (`/gallery`)
- Staff rating + feedback capture
- Tuning reports (`/reports/tuning`, `/reports/tuning.txt`)

Stable Diffusion WebUI is expected to already run at:

`http://127.0.0.1:7860`

## Quick Start (One Click, Windows)

Double-click:

`run_staff_dashboard.bat`

What it does:

1. Creates `.venv` automatically on first run
2. Installs Python dependencies automatically on first run
3. Checks whether Stable Diffusion WebUI is reachable at `http://127.0.0.1:7860`
4. Starts backend at `http://127.0.0.1:8000`
5. Opens staff page at `http://127.0.0.1:8000/staff`

If the command window closes with an error, read the message in that window first.

## Folder Structure

```text
drawing-ai-backend/
  app/
    __init__.py
    main.py
    config.py
    detector.py
    generator.py
    scanner_service.py
    websocket_manager.py
    gallery_store.py
  scanner_inputs/
  inputs/
  outputs/
  data/
    gallery.json
  static/
    staff.html
    gallery.html
    style.css
    staff.js
    gallery.js
  requirements.txt
  README.md
  run_staff_dashboard.bat
```

## Setup

1. Create and activate virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Run backend:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

4. Open pages:

- Staff page: `http://localhost:8000/staff`
- Gallery wall: `http://localhost:8000/gallery`

## Staff Workflow

1. Enter visitor name on `/staff`
2. Upload drawing, use scanner folder auto-import, or press webcam capture
3. Generation starts
4. Result appears in previews and gallery

## Scanner Workflow

Watcher is enabled by default (`ENABLE_FOLDER_WATCHER = True` in `app/config.py`).

Drop files into:

`scanner_inputs/`

Supported extensions:

- `.png`
- `.jpg`
- `.jpeg`

Backend waits for file copy completion, imports it into `inputs/{jobId}.png`, generates output, and adds it to gallery.

## API Endpoints

- `GET /health`
- `POST /generate` (multipart: `visitorName`, `file`)
- `POST /capture` (form: `visitorName`)
- `GET /gallery/items` (newest first)
- `POST /gallery/rate/{jobId}` (JSON: `rating`, `feedbackTags`, `feedbackNote`)
- `GET /reports/tuning`
- `GET /reports/tuning.txt`
- `WS /ws`

Static mounts:

- `/inputs`
- `/outputs`
- `/static`

## WebSocket Events

Completion:

```json
{
  "type": "generation_complete",
  "jobId": "...",
  "visitorName": "...",
  "preset": "...",
  "promptMode": "...",
  "inputUrl": "...",
  "outputUrl": "...",
  "createdAt": "...",
  "detection": {},
  "generationSettings": {}
}
```

Error:

```json
{
  "type": "generation_error",
  "jobId": "...",
  "error": "..."
}
```

## curl Tests

Health:

```powershell
curl.exe "http://127.0.0.1:8000/health"
```

Upload and generate:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/generate" -F "visitorName=Alice" -F "file=@C:\path\to\drawing.png"
```

Webcam capture and generate:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/capture" -F "visitorName=Alice"
```

Gallery items:

```powershell
curl.exe "http://127.0.0.1:8000/gallery/items"
```

Save rating:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/gallery/rate/<jobId>" -H "Content-Type: application/json" -d "{\"rating\":5,\"feedbackTags\":[\"good_overall\"],\"feedbackNote\":\"Great result\"}"
```

Open tuning report JSON:

```powershell
curl.exe "http://127.0.0.1:8000/reports/tuning"
```

Open tuning report text:

`http://localhost:8000/reports/tuning.txt`

## Rating Workflow

1. Generate an image from `/staff` or auto-import via scanner.
2. In `/staff`, use the 1-5 star controls, feedback tags, and optional note, then click `Save Rating`.
3. In `/gallery`, click `Rate` on a card to open the compact rating panel and submit feedback.
4. Use `/reports/tuning.txt` when you want a shareable manual tuning report.

## Notes

- Stable Diffusion checkpoint is set before generation:
  - `DreamShaper_8_pruned.safetensors [879db523c3]`
- ControlNet settings:
  - module: `pidinet_scribble`
  - model: `control_v11p_sd15_scribble [4e6af23e]`
- Logs are printed to console for health checks, jobs, scanner events, and errors.
