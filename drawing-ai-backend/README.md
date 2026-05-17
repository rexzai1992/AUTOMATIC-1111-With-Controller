# drawing-ai-backend

Local offline backend for a complete drawing workflow:

- Staff control page (`/staff`)
- Persistent FIFO generation queue (`data/queue.json`)
- Scanner folder auto-import (`scanner_inputs/`)
- Webcam capture endpoint (`/capture`)
- Stable Diffusion img2img + ControlNet generation
- Live public gallery wall (`/gallery`)
- Staff rating + feedback capture
- Tuning reports (`/reports/tuning`, `/reports/tuning.txt`)
- Retry / cancel / regenerate / delete job lifecycle APIs
- Storage cleanup maintenance API

Stable Diffusion WebUI is expected to already run at:

`http://127.0.0.1:7860`

## Quick Start (One Click, Windows)

Double-click:

`run_staff_dashboard.bat`

For Cloudflare public access, use `start-all.bat` or `run-dashboard.bat`.

What it does:

1. Creates `.venv` automatically on first run
2. Installs Python dependencies automatically on first run
3. Checks whether Stable Diffusion WebUI is reachable at `http://127.0.0.1:7860`
4. Starts backend at `http://127.0.0.1:8000`
5. Opens staff page at `http://127.0.0.1:8000/staff`

If the command window closes with an error, read the message in that window first.

## Production Start Scripts (Windows)

Use these scripts in `drawing-ai-backend/`:

- `start-all.bat`
- `run-dashboard.bat`
- `stop-all.bat`
- `restart-all.bat`

`start-all.bat` will:

1. Start Stable Diffusion from `C:\AI ofline\stable-diffusion-webui`
2. Wait for `http://127.0.0.1:7860/sdapi/v1/sd-models`
3. Start backend from `C:\AI ofline\drawing-ai-backend` on `0.0.0.0:8000`
4. Wait for `http://127.0.0.1:8000/health`
5. Start Cloudflare Tunnel (named tunnel when available, fallback to quick tunnel)
6. Open local and public staff pages

`run-dashboard.bat` will:

1. Start backend if not already running
2. Start Cloudflare Tunnel (named tunnel when available, fallback to quick tunnel)
3. Open public `/staff` and `/gallery`

`stop-all.bat` kills ports `7860` and `8000`, and also stops `cloudflared.exe`.

`restart-all.bat` runs stop, waits 3 seconds, then starts all services again.

If `cloudflared` is missing, scripts print:

`cloudflared is not installed. Install Cloudflare Tunnel first.`

and continue without silent failure.

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
  run-dashboard.bat
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
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

4. Open pages:

- Staff page: `http://localhost:8000/staff`
- Gallery wall: `http://localhost:8000/gallery`

## Staff Workflow

1. Enter visitor name on `/staff`
2. Upload drawing, use scanner folder auto-import, or press webcam capture
3. Job enters the FIFO queue (`queued` -> `processing` -> terminal state)
4. Result appears in previews and gallery when completed

## Scanner Workflow

Watcher is enabled by default (`ENABLE_FOLDER_WATCHER = True` in `app/config.py`).

Drop files into:

`scanner_inputs/`

Supported extensions:

- `.png`
- `.jpg`
- `.jpeg`

Backend waits for file copy completion, imports it into `inputs/{jobId}.png`, queues the job, then generates output and adds it to gallery.

## API Endpoints

- `GET /health`
- `GET /admin/api` (API key manager page)
- `GET /admin/api/docs` (admin API documentation page)
- `POST /admin/api/generate`
- `POST /admin/api/reset`
- `POST /admin/api/delete`
- `DELETE /admin/api`
- `POST /api/auth/generate-key`
- `POST /api/jobs` (multipart: `visitorName`, `generationMode`, `styleId`, `image`)
- `GET /api/jobs/{jobId}`
- `GET /api/gallery` (`limit`, `offset`, `mode`, `styleId`, `absolute`)
- `GET /api/gallery/latest` (`mode`, `styleId`, `absolute`)
- `GET /api/before-after` (`limit`, `offset`, `mode`, `styleId`, `absolute`)
- `GET /api/queue/status` (`absolute`)
- `WS /api/ws`
- `POST /generate` (multipart: `visitorName`, `file`)
- `POST /capture` (form: `visitorName`)
- `GET /queue/status`
- `GET /gallery/items` (newest first)
- `POST /gallery/rate/{jobId}` (JSON: `rating`, `feedbackTags`, `feedbackNote`)
- `POST /jobs/{jobId}/retry`
- `POST /jobs/{jobId}/cancel`
- `POST /jobs/{jobId}/regenerate` (JSON: `problemTags`)
- `DELETE /jobs/{jobId}`
- `POST /maintenance/cleanup`
- `GET /reports/tuning`
- `GET /reports/tuning.txt`
- `WS /ws`

## Using the API from another project

Use the `/api/*` endpoints when integrating external apps, dashboards, or kiosks.
Stable Diffusion stays private/local behind this backend.
OpenAPI docs are available at `http://SERVER_IP:8000/docs`.
See docs/API.md for API integration guide.

### Auth (optional)

Set `API_KEY` in `app/config.py`:

```python
API_KEY = ""
```

- If empty: API key is not required.
- If set: send `X-API-Key: your_key` for:
  - `POST /admin/api/generate`
  - `POST /admin/api/reset`
  - `POST /admin/api/delete`
  - `DELETE /admin/api`
  - `POST /api/auth/generate-key`
  - `POST /api/jobs`
  - `POST /jobs/{jobId}/retry`
  - `POST /jobs/{jobId}/regenerate`
  - `DELETE /jobs/{jobId}`

Generate a key from the backend:

```bash
curl -X POST http://SERVER_IP:8000/api/auth/generate-key
```

Admin key management page:

- `http://SERVER_IP:8000/admin/api`

### URL behavior

- By default, responses return relative image URLs such as `/inputs/...` and `/outputs/...`.
- Add `?absolute=true` to supported `/api/*` GET endpoints to get full URLs based on the incoming request host/scheme (LAN/tunnel friendly).

### Create job using curl

```bash
curl -X POST http://SERVER_IP:8000/api/jobs \
  -F "visitorName=Adam" \
  -F "generationMode=drawing_to_artwork" \
  -F "styleId=storybook" \
  -F "image=@drawing.png"
```

### Check status

```bash
curl http://SERVER_IP:8000/api/jobs/JOB_ID
```

### Get gallery

```bash
curl http://SERVER_IP:8000/api/gallery
```

### WebSocket

`ws://SERVER_IP:8000/api/ws`

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

Queue and job lifecycle:

- `queue_updated`
- `job_started`
- `job_completed`
- `job_failed`
- `job_cancelled`

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

## Offline Router Setup (LAN)

1. Connect the RTX server PC, iPad, TV, and scanner device to the same router/LAN.
2. Start services using `start-all.bat` or:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

3. Find the server IP:

```powershell
ipconfig
```

4. Open on iPad/staff device: `http://SERVER_IP:8000/staff`
5. Open on TV/gallery display: `http://SERVER_IP:8000/gallery`
6. Allow Windows Firewall inbound access for port `8000`.

## Cloudflare Tunnel Setup

Use this when you want secure public access to the backend/dashboard while keeping Stable Diffusion private.

1. Install `cloudflared`.
2. Login:

```powershell
cloudflared tunnel login
```

3. Create tunnel:

```powershell
cloudflared tunnel create image-generator-wonderpark
```

4. Route DNS:

```powershell
cloudflared tunnel route dns image-generator-wonderpark Image-generator-wonderpark.izzul.xyz
```

5. Run named tunnel:

```powershell
cloudflared tunnel run image-generator-wonderpark
```

Quick temporary test tunnel (no named tunnel required):

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

Security note:

- Do not expose `http://127.0.0.1:7860` publicly.
- Stable Diffusion API stays local/private.
- Only expose backend `http://127.0.0.1:8000` through Cloudflare Tunnel.
