# API Integration Guide

This guide explains how another app or project can connect to `drawing-ai-backend` through its public API.

## 1. Base URL

Use the backend server IP and port:

`http://SERVER_IP:8000`

Example:

`http://192.168.1.50:8000`

## 2. Authentication

Authentication is optional.

- If `API_KEY` in `app/config.py` is empty, no API key is required.
- If `API_KEY` is set, include this header on protected endpoints:

`X-API-Key: your_key`

Protected endpoints:

- `POST /admin/api/generate`
- `POST /admin/api/reset`
- `POST /admin/api/delete`
- `DELETE /admin/api`
- `POST /api/auth/generate-key`
- `POST /api/jobs`
- `POST /jobs/{jobId}/retry`
- `POST /jobs/{jobId}/regenerate`
- `DELETE /jobs/{jobId}`

Generate a key from backend:

```bash
curl -X POST http://SERVER_IP:8000/api/auth/generate-key
```

Notes:

- If `API_KEY` is already set, call with `X-API-Key`.
- Runtime key management UI is available at:
  - `GET /admin/api`
  - `GET /admin/api/docs`

## 3. Endpoint Reference

### GET `/admin/api`

Admin page for API key management actions:

- Generate new key
- Reset key to `app/config.py` value
- Delete key (disable API-key auth)

### GET `/admin/api/docs`

Admin docs page that mirrors `docs/API.md` and shows parameter examples.

### POST `/admin/api/generate`

Generate and apply a new runtime API key immediately.

Example response:

```json
{
  "ok": true,
  "action": "generate",
  "apiKey": "....",
  "maskedApiKey": "abcd...wxyz",
  "updatedAt": "2026-05-17T14:40:00+00:00",
  "message": "New API key generated and applied immediately."
}
```

### POST `/admin/api/reset`

Reset runtime key back to `API_KEY` from `app/config.py`.

Example response:

```json
{
  "ok": true,
  "action": "reset",
  "apiKeyEnabled": false,
  "maskedApiKey": "(empty)",
  "updatedAt": "2026-05-17T14:40:00+00:00",
  "message": "API key reset to app/config.py value."
}
```

### POST `/admin/api/delete`

Delete runtime key and disable key auth.

Example response:

```json
{
  "ok": true,
  "action": "delete",
  "apiKeyEnabled": false,
  "maskedApiKey": "(empty)",
  "updatedAt": "2026-05-17T14:40:00+00:00",
  "message": "API key deleted. Protected endpoints are now open until a new key is set."
}
```

### DELETE `/admin/api`

Alternative delete endpoint for script/CLI usage.

### POST `/api/auth/generate-key`

Generate a new API key string (helper endpoint; does not apply automatically).

Use this key in header:

- `X-API-Key: your_key`

Then set in server config:

- `API_KEY = "your_key"` in `app/config.py`
- restart backend

Example response:

```json
{
  "apiKey": "E-8D1...generated-token...",
  "headerName": "X-API-Key",
  "generatedAt": "2026-05-17T14:35:00+00:00",
  "howToUse": "Apply from /admin/api or set API_KEY in app/config.py and restart backend."
}
```

### POST `/api/jobs`

Create a new generation job and place it in the queue.

Request content type:

- `multipart/form-data`

Form-data parameters:

- `visitorName` (string, optional)
- `generationMode` (string, optional, default: `drawing_to_artwork`)
- `styleId` (string, optional, default: `auto`)
- `image` (file, required)

Example curl:

```bash
curl -X POST http://SERVER_IP:8000/api/jobs \
  -F "visitorName=Adam" \
  -F "generationMode=drawing_to_artwork" \
  -F "styleId=storybook" \
  -F "image=@drawing.png"
```

Example response:

```json
{
  "jobId": "e5c0d7fa7f0f4200a8e6e9d62fe11ace",
  "status": "queued",
  "queuePosition": 1,
  "estimatedWaitSeconds": 30
}
```

### GET `/api/jobs/{jobId}`

Get status and metadata for a specific job.

Example response:

```json
{
  "jobId": "e5c0d7fa7f0f4200a8e6e9d62fe11ace",
  "status": "queued",
  "visitorName": "Adam",
  "generationMode": "drawing_to_artwork",
  "styleId": "storybook",
  "inputUrl": "/inputs/e5c0d7fa7f0f4200a8e6e9d62fe11ace.png",
  "outputUrl": "/outputs/e5c0d7fa7f0f4200a8e6e9d62fe11ace.png",
  "createdAt": "2026-05-17T14:31:55.220503+00:00",
  "startedAt": null,
  "completedAt": null,
  "durationSeconds": 0,
  "error": null
}
```

### GET `/api/gallery`

List gallery items (newest first).

Query parameters:

- `limit` (int, default `50`)
- `offset` (int, default `0`)
- `mode` (string, optional; mapped from `generationMode`)
- `styleId` (string, optional)
- `absolute` (bool, default `false`)

Example curl:

```bash
curl "http://SERVER_IP:8000/api/gallery?limit=20&offset=0&mode=drawing_to_artwork&styleId=storybook"
```

Example response:

```json
{
  "items": [
    {
      "jobId": "abc123",
      "visitorName": "Adam",
      "preset": "default",
      "promptMode": "lively_storybook",
      "promptType": "lively_storybook",
      "inputUrl": "/inputs/abc123.png",
      "outputUrl": "/outputs/abc123.png",
      "createdAt": "2026-05-17T10:00:00+00:00",
      "startedAt": "2026-05-17T10:00:02+00:00",
      "completedAt": "2026-05-17T10:00:11+00:00",
      "durationSeconds": 9.1,
      "estimatedSeconds": 8,
      "generationMode": "drawing_to_artwork",
      "styleId": "storybook",
      "status": "completed"
    }
  ],
  "limit": 20,
  "offset": 0,
  "total": 1
}
```

### GET `/api/gallery/latest`

Get the latest completed gallery item.

Supports:

- `mode`
- `styleId`
- `absolute`

Example response:

```json
{
  "jobId": "abc123",
  "visitorName": "Adam",
  "inputUrl": "/inputs/abc123.png",
  "outputUrl": "/outputs/abc123.png",
  "createdAt": "2026-05-17T10:00:00+00:00",
  "generationMode": "drawing_to_artwork",
  "styleId": "storybook",
  "status": "completed"
}
```

### GET `/api/before-after`

Get gallery data in before/after display format.

Supports:

- `limit`
- `offset`
- `mode`
- `styleId`
- `absolute`

Example response:

```json
{
  "items": [
    {
      "jobId": "abc123",
      "visitorName": "Adam",
      "beforeImageUrl": "/inputs/abc123.png",
      "afterImageUrl": "/outputs/abc123.png",
      "createdAt": "2026-05-17T10:00:00+00:00"
    }
  ],
  "limit": 20,
  "offset": 0,
  "total": 1
}
```

### GET `/api/queue/status`

Get current queue status and job list.

Supports:

- `absolute`

Example response:

```json
{
  "queueLength": 2,
  "currentJob": "job_processing_id",
  "estimatedWaitSeconds": 24,
  "jobs": [
    {
      "jobId": "job_queued_1",
      "status": "queued",
      "visitorName": "Adam",
      "generationMode": "drawing_to_artwork",
      "styleId": "storybook",
      "inputUrl": "/inputs/job_queued_1.png",
      "outputUrl": "/outputs/job_queued_1.png",
      "createdAt": "2026-05-17T10:01:00+00:00",
      "startedAt": null,
      "completedAt": null,
      "durationSeconds": 0,
      "error": null
    }
  ]
}
```

### WebSocket `/api/ws`

Connection URL:

- `ws://SERVER_IP:8000/api/ws`
- use `wss://` if backend is behind HTTPS

Event types:

- `queue_updated`
- `job_started`
- `generation_complete`
- `generation_error`
- `job_cancelled`

Example `queue_updated`:

```json
{
  "type": "queue_updated",
  "queueLength": 2,
  "currentJob": "job_processing_id",
  "estimatedWaitSeconds": 24,
  "jobs": []
}
```

Example `job_started`:

```json
{
  "type": "job_started",
  "job": {
    "jobId": "abc123",
    "status": "processing",
    "visitorName": "Adam",
    "generationMode": "drawing_to_artwork",
    "styleId": "storybook",
    "inputUrl": "/inputs/abc123.png",
    "outputUrl": "/outputs/abc123.png"
  }
}
```

Example `generation_complete`:

```json
{
  "type": "generation_complete",
  "jobId": "abc123",
  "visitorName": "Adam",
  "generationMode": "drawing_to_artwork",
  "styleId": "storybook",
  "preset": "default",
  "promptMode": "lively_storybook",
  "promptType": "lively_storybook",
  "inputUrl": "/inputs/abc123.png",
  "outputUrl": "/outputs/abc123.png",
  "createdAt": "2026-05-17T10:00:00+00:00",
  "startedAt": "2026-05-17T10:00:02+00:00",
  "completedAt": "2026-05-17T10:00:11+00:00",
  "durationSeconds": 9.1,
  "estimatedSeconds": 8,
  "detection": {},
  "generationSettings": {},
  "hidden": false,
  "hiddenAt": null,
  "updatedAt": null,
  "rating": null
}
```

Example `generation_error`:

```json
{
  "type": "generation_error",
  "jobId": "abc123",
  "error": "Stable Diffusion WebUI is not reachable at http://127.0.0.1:7860."
}
```

Example `job_cancelled`:

```json
{
  "type": "job_cancelled",
  "job": {
    "jobId": "abc123",
    "status": "cancelled",
    "error": "Cancelled while queued."
  }
}
```

## 4. Image URLs

`inputUrl` is the original uploaded image (before image).

`outputUrl` is the generated result image (after image).

Relative URL example:

- `/inputs/abc123.png`
- `/outputs/abc123.png`

Absolute URL support:

- Add `?absolute=true` on supported GET endpoints (`/api/jobs/{jobId}`, `/api/gallery`, `/api/gallery/latest`, `/api/before-after`, `/api/queue/status`).
- Example:
  - `/api/gallery?absolute=true`
  - response URL becomes `http://SERVER_IP:8000/inputs/abc123.png`

## 5. Example Integration Code

### JavaScript fetch example

```javascript
const BASE_URL = "http://SERVER_IP:8000";
const API_KEY = ""; // optional

function authHeaders() {
  return API_KEY ? { "X-API-Key": API_KEY } : {};
}

async function createJob(file) {
  const form = new FormData();
  form.append("visitorName", "Adam");
  form.append("generationMode", "drawing_to_artwork");
  form.append("styleId", "storybook");
  form.append("image", file);

  const res = await fetch(`${BASE_URL}/api/jobs`, {
    method: "POST",
    headers: { ...authHeaders() },
    body: form
  });
  if (!res.ok) throw new Error(`Create job failed: ${res.status}`);
  return res.json();
}

async function getJob(jobId) {
  const res = await fetch(`${BASE_URL}/api/jobs/${jobId}?absolute=true`);
  if (!res.ok) throw new Error(`Get job failed: ${res.status}`);
  return res.json();
}

async function waitForCompletion(jobId, onUpdate) {
  while (true) {
    const job = await getJob(jobId);
    onUpdate(job);
    if (job.status === "completed" || job.status === "failed" || job.status === "cancelled") {
      return job;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}

async function uploadAndRender(file, beforeImgEl, afterImgEl, statusEl) {
  const created = await createJob(file);
  statusEl.textContent = `Queued. Position: ${created.queuePosition}`;

  const finalJob = await waitForCompletion(created.jobId, (job) => {
    statusEl.textContent = `Job ${job.status}`;
    if (job.inputUrl) beforeImgEl.src = job.inputUrl;
    if (job.outputUrl && job.status === "completed") afterImgEl.src = job.outputUrl;
  });

  if (finalJob.status !== "completed") {
    statusEl.textContent = `Job ended: ${finalJob.status}. ${finalJob.error || ""}`;
  }
}
```

### WebSocket JavaScript example

```javascript
const BASE_URL = "http://SERVER_IP:8000";
const wsProtocol = BASE_URL.startsWith("https") ? "wss" : "ws";
const wsHost = BASE_URL.replace(/^https?:\/\//, "");
const ws = new WebSocket(`${wsProtocol}://${wsHost}/api/ws`);

ws.onopen = () => {
  console.log("WebSocket connected");
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log("WS event:", message.type, message);

  if (message.type === "generation_complete") {
    const beforeUrl = message.inputUrl;
    const afterUrl = message.outputUrl;
    // Example UI update:
    // document.querySelector("#before").src = beforeUrl;
    // document.querySelector("#after").src = afterUrl;
  }
};

ws.onclose = () => {
  console.log("WebSocket disconnected");
};
```

## 6. LAN / Offline Router Usage

- Run backend on the RTX server PC.
- Other devices (iPad, another PC, TV app) must call:
  - `http://SERVER_IP:8000`
- Do not use `localhost` on remote devices. `localhost` points to that device itself, not the server.
- Stable Diffusion should remain private/local on the server at:
  - `http://127.0.0.1:7860`
- Other apps should never call Stable Diffusion directly, only this backend API.

## 7. Troubleshooting

### 503 / Stable Diffusion not reachable

- Check Stable Diffusion WebUI is running on the same server.
- Verify it is reachable at `http://127.0.0.1:7860`.
- Check backend logs and `/health`.

### Image URL returns 404

- Ensure the job has completed.
- Verify `/inputs` and `/outputs` mounts are accessible from the device.
- If using URLs in another app, consider `?absolute=true` to avoid wrong host resolution.

### WebSocket disconnected

- Reconnect automatically from client code.
- Check network stability and firewall rules.
- If using HTTPS reverse proxy/tunnel, use `wss://` not `ws://`.

### Wrong `SERVER_IP`

- On the server, run `ipconfig` and use the active LAN adapter IPv4 address.
- Ensure client device is on the same router/LAN.

### Windows Firewall blocks port 8000

- Allow inbound TCP for port `8000` on the backend server.
- Re-test from another device with `http://SERVER_IP:8000/health`.
