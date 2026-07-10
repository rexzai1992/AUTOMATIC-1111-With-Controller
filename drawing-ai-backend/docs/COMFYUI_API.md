# ComfyUI API Guide

This guide covers the ComfyUI-specific endpoints in `drawing-ai-backend`.

## Base URL

Use the backend server IP and port:

`http://SERVER_IP:8000`

Example:

`http://192.168.1.50:8000`

## Authentication

The current ComfyUI staff endpoints are public in the backend route definitions.

General protected endpoints elsewhere in the backend use:

`X-API-Key: your_key`

Full runtime API-key setup is available at:

- `GET /admin/api`
- `POST /admin/api/generate`

`POST /admin/api/generate` creates, applies, and persists the runtime key in `data/api_key_state.json`.

`POST /api/auth/generate-key` only returns a key string. It does not apply or save it.

See `GET /admin/api/docs` for the full API key guide.

## ComfyUI Configuration

Runtime settings are read from `config.json`:

- `generation_engine`: set to `comfyui` to make ComfyUI the default generation backend.
- `comfyui.base_url`: ComfyUI server URL, usually `http://127.0.0.1:8188`.
- `comfyui.workflow_path`: workflow JSON used by the backend.
- `comfyui.output_dir`: output folder for generated images.
- `comfyui.node_ids`: workflow node IDs that the backend patches.
- `comfyui.defaults`: fallback generation values for steps, cfg, denoise, seed, and megapixels.

Prompt presets are loaded from:

`config/comfy_prompt_presets.json`

## Endpoint Reference

### GET `/api/docs/comfyui`

ComfyUI API documentation page.

Aliases:

- `GET /api/docs/comfy-ui`
- `GET /api/docs/comfy%20ui`

### GET `/comfy/staff`

ComfyUI staff dashboard HTML page.

Open in a browser:

`http://SERVER_IP:8000/comfy/staff`

### GET `/api/comfy/staff/status`

Return ComfyUI backend health, queue estimate, runtime defaults, and preset metadata.

Example curl:

```bash
curl http://SERVER_IP:8000/api/comfy/staff/status
```

Example response shape:

```json
{
  "backend": {
    "engine": "comfyui",
    "reachable": true
  },
  "estimate": {
    "estimatedSecondsPerImage": 30,
    "queueLength": 0,
    "queueSource": "comfyui",
    "sampleCount": 5,
    "comfyBaseUrl": "http://127.0.0.1:8188"
  },
  "defaults": {
    "steps": 4,
    "cfg": 1,
    "denoise": 1,
    "seed": -1,
    "megapixels": 1
  },
  "presets": {
    "count": 100,
    "categories": ["cartoon", "craft"]
  }
}
```

### GET `/api/comfy/estimate`

Return the queue and timing estimate used by the staff dashboard.

Example curl:

```bash
curl http://SERVER_IP:8000/api/comfy/estimate
```

Example response shape:

```json
{
  "estimatedSecondsPerImage": 30,
  "queueLength": 0,
  "queueSource": "comfyui",
  "sampleCount": 5,
  "comfyBaseUrl": "http://127.0.0.1:8188"
}
```

### GET `/api/comfy/presets`

List ComfyUI prompt presets.

Query parameters:

- `category` (string, optional): return only presets in this category.

Example curl:

```bash
curl "http://SERVER_IP:8000/api/comfy/presets?category=cartoon"
```

Example response shape:

```json
{
  "success": true,
  "negative_prompt": "scary, creepy, horror, ugly...",
  "presets": [
    {
      "id": "style_001",
      "name": "3D Animated Movie Vibrant Depth",
      "category": "cartoon",
      "prompt": "Change the style of the image..."
    }
  ]
}
```

Alias:

- `GET /comfy/presets`

### POST `/api/comfy/staff/generate`

Queue a ComfyUI generation job from an uploaded image.

Comfy staff results are marked as staff-only gallery items:

- `source`: `staff`
- `generationEngine`: `comfyui`
- `hidden`: `true`
- `showcaseVisible`: `false`

They are visible in the Comfy staff dashboard, but they are not sent to `/showcase`.

Request content type:

- `multipart/form-data`

Form-data parameters:

- `file` (file, required): uploaded image.
- `visitorName` (string, optional): display name stored with the queued job.
- `prompt` (string, optional): positive prompt override.
- `negativePrompt` (string, optional): negative prompt override.
- `stylePreset` (string, optional, default `random`): preset ID such as `style_001`, or `random`.
- `style_preset` (string, optional): snake-case alias for `stylePreset`.
- `styleCategory` (string, optional): category filter used when `stylePreset` is `random`.
- `seed` (integer string, optional): seed override.
- `steps` (integer string, optional): steps override, must be greater than 0.
- `cfg` (number string, optional): CFG override, must be greater than 0.
- `denoise` (number string, optional): denoise override, must be 0 or higher.
- `megapixels` (number string, optional): scale target override, must be greater than 0.

Example curl:

```bash
curl -X POST http://SERVER_IP:8000/api/comfy/staff/generate \
  -F "visitorName=Staff Demo" \
  -F "stylePreset=random" \
  -F "styleCategory=cartoon" \
  -F "steps=4" \
  -F "cfg=1" \
  -F "denoise=1" \
  -F "file=@drawing.png"
```

Example response shape:

```json
{
  "success": true,
  "jobId": "e5c0d7fa7f0f4200a8e6e9d62fe11ace",
  "status": "queued",
  "queuePosition": 1,
  "estimatedWaitSeconds": 30,
  "generationEngine": "comfyui"
}
```

## Related Endpoints

ComfyUI jobs are normal queue and gallery records once they are created.

- `GET /queue/status`: queue status.
- `GET /api/jobs/{jobId}`: job status and output metadata.
- `GET /api/gallery`: gallery items.
- `DELETE /jobs/{jobId}`: delete a job, protected by API key when enabled.
