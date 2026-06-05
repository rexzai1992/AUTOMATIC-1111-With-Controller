from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import requests
from PIL import Image, ImageDraw

BASE_URL = "http://127.0.0.1:8000"
GENERATION_MODE = "drawing_to_artwork"
STYLE_ID = "auto"
POLL_INTERVAL = 3.0
POLL_TIMEOUT = 2400.0


def _mk_dirs() -> Tuple[Path, Path]:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    root = Path("tests") / "results" / f"animal_species_validation_{stamp}"
    inputs_dir = root / "inputs"
    outputs_dir = root / "outputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    return inputs_dir, outputs_dir


def _canvas() -> Image.Image:
    return Image.new("RGB", (768, 768), "white")


def draw_lion(path: Path, variant: int) -> None:
    img = _canvas()
    d = ImageDraw.Draw(img)
    dx = variant * 16
    dy = variant * 10
    d.ellipse((170 + dx, 170 + dy, 610 + dx, 610 + dy), outline="orange", width=28)
    d.ellipse((260 + dx, 250 + dy, 520 + dx, 510 + dy), fill="#f7cf65", outline="brown", width=8)
    d.ellipse((230 + dx, 230 + dy, 300 + dx, 300 + dy), fill="#f7cf65", outline="brown", width=8)
    d.ellipse((480 + dx, 230 + dy, 550 + dx, 300 + dy), fill="#f7cf65", outline="brown", width=8)
    d.ellipse((330 + dx, 335 + dy, 360 + dx, 365 + dy), fill="black")
    d.ellipse((425 + dx, 335 + dy, 455 + dx, 365 + dy), fill="black")
    d.polygon([(390 + dx, 385 + dy), (420 + dx, 415 + dy), (360 + dx, 415 + dy)], fill="#8d5524")
    d.arc((320 + dx, 410 + dy, 470 + dx, 510 + dy), start=200, end=340, fill="black", width=7)
    d.rectangle((300 + dx, 510 + dy, 370 + dx, 650 + dy), fill="#f7cf65", outline="brown", width=6)
    d.rectangle((410 + dx, 510 + dy, 480 + dx, 650 + dy), fill="#f7cf65", outline="brown", width=6)
    d.arc((500 + dx, 520 + dy, 690 + dx, 680 + dy), start=180, end=320, fill="#8d5524", width=10)
    img.save(path)


def draw_zebra(path: Path, variant: int) -> None:
    img = _canvas()
    d = ImageDraw.Draw(img)
    dx = variant * 14
    dy = variant * 12
    d.ellipse((180 + dx, 300 + dy, 560 + dx, 580 + dy), fill="#f5f5f5", outline="black", width=8)
    d.rectangle((500 + dx, 230 + dy, 620 + dx, 420 + dy), fill="#f5f5f5", outline="black", width=8)
    d.ellipse((575 + dx, 210 + dy, 665 + dx, 300 + dy), fill="#f5f5f5", outline="black", width=8)
    d.rectangle((230 + dx, 560 + dy, 280 + dx, 700 + dy), fill="#f5f5f5", outline="black", width=7)
    d.rectangle((320 + dx, 560 + dy, 370 + dx, 700 + dy), fill="#f5f5f5", outline="black", width=7)
    d.rectangle((410 + dx, 560 + dy, 460 + dx, 700 + dy), fill="#f5f5f5", outline="black", width=7)
    d.rectangle((500 + dx, 560 + dy, 550 + dx, 700 + dy), fill="#f5f5f5", outline="black", width=7)
    for x in range(205 + dx, 560 + dx, 34):
        d.line((x, 315 + dy, x + 85, 575 + dy), fill="black", width=10)
    for x in range(515 + dx, 655 + dx, 24):
        d.line((x, 240 + dy, x + 40, 410 + dy), fill="black", width=8)
    d.ellipse((620 + dx, 245 + dy, 640 + dx, 265 + dy), fill="black")
    d.arc((600 + dx, 255 + dy, 660 + dx, 300 + dy), start=180, end=320, fill="black", width=5)
    img.save(path)


def draw_elephant(path: Path, variant: int) -> None:
    img = _canvas()
    d = ImageDraw.Draw(img)
    dx = variant * 12
    dy = variant * 14
    gray = "#c8ccd6"
    d.ellipse((160 + dx, 260 + dy, 600 + dx, 580 + dy), fill=gray, outline="#67707f", width=8)
    d.ellipse((470 + dx, 210 + dy, 670 + dx, 430 + dy), fill=gray, outline="#67707f", width=8)
    d.ellipse((420 + dx, 220 + dy, 530 + dx, 340 + dy), fill="#b8bfcc", outline="#67707f", width=7)
    d.rectangle((510 + dx, 340 + dy, 590 + dx, 560 + dy), fill=gray, outline="#67707f", width=7)
    d.ellipse((530 + dx, 540 + dy, 640 + dx, 690 + dy), fill=gray, outline="#67707f", width=7)
    d.rectangle((220 + dx, 550 + dy, 280 + dx, 710 + dy), fill=gray, outline="#67707f", width=7)
    d.rectangle((320 + dx, 550 + dy, 380 + dx, 710 + dy), fill=gray, outline="#67707f", width=7)
    d.rectangle((420 + dx, 550 + dy, 480 + dx, 710 + dy), fill=gray, outline="#67707f", width=7)
    d.rectangle((520 + dx, 550 + dy, 580 + dx, 710 + dy), fill=gray, outline="#67707f", width=7)
    d.ellipse((605 + dx, 270 + dy, 625 + dx, 290 + dy), fill="black")
    img.save(path)


def draw_tiger(path: Path, variant: int) -> None:
    img = _canvas()
    d = ImageDraw.Draw(img)
    dx = variant * 15
    dy = variant * 10
    orange = "#f79f24"
    d.ellipse((170 + dx, 290 + dy, 560 + dx, 580 + dy), fill=orange, outline="#7a3f00", width=8)
    d.ellipse((470 + dx, 210 + dy, 650 + dx, 390 + dy), fill=orange, outline="#7a3f00", width=8)
    d.rectangle((220 + dx, 555 + dy, 275 + dx, 710 + dy), fill=orange, outline="#7a3f00", width=7)
    d.rectangle((315 + dx, 555 + dy, 370 + dx, 710 + dy), fill=orange, outline="#7a3f00", width=7)
    d.rectangle((410 + dx, 555 + dy, 465 + dx, 710 + dy), fill=orange, outline="#7a3f00", width=7)
    d.rectangle((505 + dx, 555 + dy, 560 + dx, 710 + dy), fill=orange, outline="#7a3f00", width=7)
    d.arc((90 + dx, 350 + dy, 320 + dx, 620 + dy), start=300, end=80, fill="#7a3f00", width=14)
    for x in range(210 + dx, 560 + dx, 40):
        d.polygon([(x, 320 + dy), (x + 25, 430 + dy), (x - 15, 430 + dy)], fill="black")
        d.polygon([(x + 10, 450 + dy), (x + 35, 560 + dy), (x - 5, 560 + dy)], fill="black")
    d.ellipse((560 + dx, 260 + dy, 580 + dx, 280 + dy), fill="black")
    d.arc((540 + dx, 280 + dy, 620 + dx, 340 + dy), start=200, end=340, fill="black", width=6)
    img.save(path)


DRAW_FUNCS = {
    "lion": draw_lion,
    "zebra": draw_zebra,
    "elephant": draw_elephant,
    "tiger": draw_tiger,
}


def submit_job(image_path: Path, animal: str) -> str:
    with image_path.open("rb") as f:
        response = requests.post(
            f"{BASE_URL}/generate",
            data={
                "visitorName": f"species-{animal}",
                "generationMode": GENERATION_MODE,
                "styleId": STYLE_ID,
                "presetAnimal": animal,
            },
            files={"file": (image_path.name, f, "image/png")},
            timeout=180,
        )
    response.raise_for_status()
    payload = response.json()
    job = payload.get("job") if isinstance(payload, dict) else None
    job_id = ""
    if isinstance(job, dict):
        job_id = str(job.get("jobId") or "")
    if not job_id:
        job_id = str(payload.get("jobId") or "")
    if not job_id:
        raise RuntimeError(f"Missing jobId in response: {payload}")
    return job_id


def wait_job(job_id: str) -> Dict[str, object]:
    start = time.time()
    last_status = ""
    while time.time() - start < POLL_TIMEOUT:
        response = requests.get(f"{BASE_URL}/api/jobs/{job_id}", timeout=60)
        response.raise_for_status()
        payload = response.json()
        status = str(payload.get("status") or "").lower()
        if status != last_status:
            print(f"[{job_id}] status={status}")
            last_status = status
        if status in {"completed", "failed", "cancelled"}:
            return payload
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Job {job_id} did not finish within {POLL_TIMEOUT}s")


def main() -> None:
    inputs_dir, outputs_dir = _mk_dirs()
    created_inputs: List[Tuple[str, Path]] = []
    for animal, func in DRAW_FUNCS.items():
        for idx in range(1, 4):
            p = inputs_dir / f"{animal}_{idx}.png"
            func(p, idx)
            created_inputs.append((animal, p))

    queued: List[Dict[str, str]] = []
    for animal, path in created_inputs:
        job_id = submit_job(path, animal)
        queued.append({"animal": animal, "input": str(path), "jobId": job_id})
        print(f"Queued {animal} -> {job_id}")

    results: List[Dict[str, object]] = []
    for row in queued:
        payload = wait_job(row["jobId"])
        output_url = str(payload.get("outputUrl") or "")
        output_file = ""
        if output_url.startswith("/outputs/"):
            candidate = Path("outputs") / output_url.split("/outputs/", 1)[1]
            if candidate.is_file():
                output_file = str((outputs_dir / candidate.name).resolve())
                (outputs_dir / candidate.name).write_bytes(candidate.read_bytes())

        expected_animal = row["animal"]
        prompt_used = str(payload.get("promptUsed") or "")
        species_prompt_used = str(payload.get("speciesPromptUsed") or "")
        preset_animal = str(payload.get("presetAnimal") or "")
        settings = payload.get("generationSettings") if isinstance(payload.get("generationSettings"), dict) else {}

        result = {
            "jobId": row["jobId"],
            "expectedAnimal": expected_animal,
            "status": str(payload.get("status") or ""),
            "presetAnimal": preset_animal,
            "speciesPromptUsedPresent": bool(species_prompt_used),
            "speciesPromptHasExpectedAnimalHint": expected_animal in species_prompt_used.lower(),
            "promptUsedHasExpectedAnimalHint": expected_animal in prompt_used.lower(),
            "checkpoint": payload.get("checkpoint") or settings.get("checkpoint"),
            "controlNetModel": payload.get("controlNetModel") or settings.get("controlNetModel"),
            "controlNetModule": payload.get("controlNetModule") or settings.get("controlNetModule"),
            "controlWeight": payload.get("controlWeight") or settings.get("controlWeight"),
            "denoisingStrength": payload.get("denoisingStrength") or settings.get("denoisingStrength"),
            "controlMode": payload.get("controlMode") or settings.get("controlMode"),
            "outputUrl": output_url,
            "outputFile": output_file,
            "inputFile": row["input"],
        }
        results.append(result)

    summary = {
        "generatedAtUtc": datetime.utcnow().isoformat() + "Z",
        "baseUrl": BASE_URL,
        "total": len(results),
        "completed": sum(1 for r in results if r["status"] == "completed"),
        "failed": [r for r in results if r["status"] != "completed"],
        "results": results,
    }

    report_path = outputs_dir.parent / "validation_report.json"
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Saved: {report_path}")


if __name__ == "__main__":
    main()
