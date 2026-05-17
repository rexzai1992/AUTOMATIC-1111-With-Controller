import io
import json
import hashlib
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw, ImageFilter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.qa_common import (
    RESULTS_DIR,
    SAMPLE_IMAGES_DIR,
    SAMPLE_MANIFEST_PATH,
    TestReporter,
    ensure_test_dirs,
    utc_now_stamp,
)


# Internet source: Google Quick, Draw dataset (public).
QUICKDRAW_BASE = "https://storage.googleapis.com/quickdraw_dataset/full/simplified"
TARGET_PER_CATEGORY = 4
MAX_DOWNLOAD_RETRIES = 3
MAX_DIMENSION = 3000


# These categories are rendered from real Quick, Draw stroke data.
CATEGORY_SPECS: Dict[str, Dict[str, Any]] = {
    "simple_crayon_house": {
        "classes": ["house"],
        "size": (900, 900),
        "stroke_color": (40, 40, 40),
        "bg_color": (255, 255, 255),
        "stroke_width": 4,
    },
    "toddler_abstract_people": {
        "classes": ["person", "face"],
        "size": (900, 900),
        "stroke_color": (30, 30, 30),
        "bg_color": (255, 255, 255),
        "stroke_width": 5,
    },
    "rough_low_color_drawing": {
        "classes": ["scribble", "zigzag", "line"],
        "size": (900, 900),
        "stroke_color": (70, 60, 50),
        "bg_color": (248, 246, 240),
        "stroke_width": 5,
    },
    "colored_kids_drawing": {
        "classes": ["rainbow", "flower", "sun"],
        "size": (900, 900),
        "stroke_color_choices": [(220, 20, 60), (0, 128, 255), (255, 165, 0), (30, 180, 80)],
        "bg_color": (255, 255, 255),
        "stroke_width": 5,
    },
    "pencil_lineart_drawing": {
        "classes": ["cat", "tree", "bird"],
        "size": (900, 900),
        "stroke_color": (20, 20, 20),
        "bg_color": (255, 255, 255),
        "stroke_width": 3,
    },
    "almost_blank_drawing": {
        "classes": ["line", "dot", "square"],
        "size": (900, 900),
        "stroke_color": (30, 30, 30),
        "bg_color": (255, 255, 255),
        "stroke_width": 3,
        "max_points": 24,
    },
    "large_resolution_drawing": {
        "classes": ["house", "person"],
        "size": (3400, 2400),  # Will be resized down to max 3000 by rule.
        "stroke_color": (35, 35, 35),
        "bg_color": (255, 255, 255),
        "stroke_width": 8,
    },
    "weird_aspect_ratio_drawing": {
        "classes": ["house", "tree", "person"],
        "size_choices": [(2200, 700), (700, 2200), (2800, 900)],
        "stroke_color": (40, 40, 40),
        "bg_color": (255, 255, 255),
        "stroke_width": 6,
    },
    "noisy_low_quality_drawing": {
        "classes": ["person", "house", "flower"],
        "size": (900, 900),
        "stroke_color": (40, 40, 40),
        "bg_color": (255, 255, 255),
        "stroke_width": 4,
        "add_noise": True,
    },
}


def safe_name(value: str) -> str:
    text = "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_")
    while "__" in text:
        text = text.replace("__", "_")
    return text or "item"


def download_text_with_retry(session: requests.Session, url: str) -> str:
    for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
        try:
            response = session.get(url, timeout=60)
            response.raise_for_status()
            return response.text
        except Exception:
            if attempt < MAX_DOWNLOAD_RETRIES:
                print(f"RETRYING {url} ({attempt}/{MAX_DOWNLOAD_RETRIES})")
                time.sleep(0.8)
            else:
                print(f"FAILED {url}")
    return ""


def load_quickdraw_group(session: requests.Session, group_name: str, cache: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if group_name in cache:
        return cache[group_name]
    url = f"{QUICKDRAW_BASE}/{quote(group_name)}.ndjson"
    raw_text = download_text_with_retry(session, url)
    if not raw_text:
        cache[group_name] = []
        return cache[group_name]

    parsed_rows: List[Dict[str, Any]] = []
    for line in raw_text.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and isinstance(row.get("drawing"), list):
            parsed_rows.append(row)
    cache[group_name] = parsed_rows
    return parsed_rows


def stroke_point_count(drawing: List[Any]) -> int:
    total = 0
    for stroke in drawing:
        if not isinstance(stroke, list) or len(stroke) < 2:
            continue
        xs, ys = stroke[0], stroke[1]
        if isinstance(xs, list) and isinstance(ys, list):
            total += min(len(xs), len(ys))
    return total


def render_quickdraw_image(
    drawing: List[Any],
    *,
    size: Tuple[int, int],
    stroke_color: Tuple[int, int, int],
    bg_color: Tuple[int, int, int],
    stroke_width: int,
) -> Image.Image:
    image = Image.new("RGB", size, color=bg_color)
    draw = ImageDraw.Draw(image)
    width, height = size
    margin = max(16, int(min(width, height) * 0.08))
    scale_x = (width - 2 * margin) / 255.0
    scale_y = (height - 2 * margin) / 255.0

    for stroke in drawing:
        if not isinstance(stroke, list) or len(stroke) < 2:
            continue
        xs, ys = stroke[0], stroke[1]
        if not isinstance(xs, list) or not isinstance(ys, list):
            continue
        points: List[Tuple[float, float]] = []
        for x, y in zip(xs, ys):
            points.append((margin + float(x) * scale_x, margin + float(y) * scale_y))
        if len(points) >= 2:
            draw.line(points, fill=stroke_color, width=stroke_width, joint="curve")
        elif len(points) == 1:
            px, py = points[0]
            draw.ellipse((px - stroke_width, py - stroke_width, px + stroke_width, py + stroke_width), fill=stroke_color)
    return image


def add_noise_effect(image: Image.Image) -> Image.Image:
    # Simulate low-quality scan/noise from a real drawing source image.
    noisy = image.filter(ImageFilter.GaussianBlur(radius=0.7))
    downscaled = noisy.resize((max(1, image.width // 2), max(1, image.height // 2)), Image.Resampling.BILINEAR)
    upscaled = downscaled.resize(image.size, Image.Resampling.NEAREST)
    return upscaled


def resize_if_needed(image: Image.Image) -> Image.Image:
    max_dim = max(image.width, image.height)
    if max_dim <= MAX_DIMENSION:
        return image
    scale = MAX_DIMENSION / float(max_dim)
    new_size = (
        max(1, int(round(image.width * scale))),
        max(1, int(round(image.height * scale))),
    )
    return image.resize(new_size, Image.Resampling.LANCZOS)


def image_hash_png(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return hashlib.sha256(buffer.getvalue()).hexdigest()


def main() -> int:
    ensure_test_dirs()
    reporter = TestReporter("download_test_images", base_url="N/A")
    session = requests.Session()
    session.headers.update({"User-Agent": "drawing-ai-backend-sample-downloader/1.0"})
    random.seed(42)

    quickdraw_cache: Dict[str, List[Dict[str, Any]]] = {}
    manifest_items: List[Dict[str, Any]] = []
    existing_hashes: set[str] = set()
    requested_total = len(CATEGORY_SPECS) * TARGET_PER_CATEGORY
    downloaded_total = 0
    failed_total = 0

    for category, spec in CATEGORY_SPECS.items():
        category_done = 0
        classes = list(spec.get("classes") or [])
        if not classes:
            reporter.add_fail(f"Category {category}", "No source classes configured.")
            continue

        rows_pool: List[Tuple[str, Dict[str, Any]]] = []
        for class_name in classes:
            rows = load_quickdraw_group(session, class_name, quickdraw_cache)
            # Sample subset to keep runtime fast.
            if rows:
                sample_rows = rows[: min(3000, len(rows))]
                rows_pool.extend((class_name, row) for row in sample_rows)

        if not rows_pool:
            reporter.add_fail(f"Category {category}", "No source data rows downloaded.")
            failed_total += TARGET_PER_CATEGORY
            continue

        random.shuffle(rows_pool)
        row_index = 0
        safety_limit = len(rows_pool)

        while category_done < TARGET_PER_CATEGORY and row_index < safety_limit:
            class_name, row = rows_pool[row_index]
            row_index += 1

            drawing = row.get("drawing")
            if not isinstance(drawing, list):
                continue

            max_points = spec.get("max_points")
            if max_points is not None and stroke_point_count(drawing) > int(max_points):
                continue

            size_choices = spec.get("size_choices")
            if size_choices and isinstance(size_choices, list):
                size = tuple(random.choice(size_choices))
            else:
                size = tuple(spec.get("size", (900, 900)))

            stroke_color_choices = spec.get("stroke_color_choices")
            if stroke_color_choices and isinstance(stroke_color_choices, list):
                stroke_color = tuple(random.choice(stroke_color_choices))
            else:
                stroke_color = tuple(spec.get("stroke_color", (30, 30, 30)))

            bg_color = tuple(spec.get("bg_color", (255, 255, 255)))
            stroke_width = int(spec.get("stroke_width", 4))

            image = render_quickdraw_image(
                drawing,
                size=(int(size[0]), int(size[1])),
                stroke_color=(int(stroke_color[0]), int(stroke_color[1]), int(stroke_color[2])),
                bg_color=(int(bg_color[0]), int(bg_color[1]), int(bg_color[2])),
                stroke_width=stroke_width,
            )
            if spec.get("add_noise"):
                image = add_noise_effect(image)

            image = resize_if_needed(image)
            digest = image_hash_png(image)
            if digest in existing_hashes:
                print(f"SKIPPED DUPLICATE {category}:{class_name}:{row.get('key_id')}")
                continue

            file_name = f"{safe_name(category)}_{category_done+1:02d}_{utc_now_stamp()}.png"
            output_path = SAMPLE_IMAGES_DIR / file_name
            image.save(output_path, format="PNG")
            existing_hashes.add(digest)
            downloaded_total += 1
            category_done += 1

            source_url = f"{QUICKDRAW_BASE}/{quote(class_name)}.ndjson"
            manifest_items.append(
                {
                    "sourceUrl": source_url,
                    "category": category,
                    "filePath": str(output_path.relative_to(PROJECT_ROOT)),
                    "width": int(image.width),
                    "height": int(image.height),
                    "fileSize": int(output_path.stat().st_size),
                    "quickdrawClass": class_name,
                    "quickdrawKeyId": str(row.get("key_id") or ""),
                }
            )
            print(f"DOWNLOADED {source_url} -> {output_path.name}")

        if category_done >= 3:
            reporter.add_pass(f"Category {category}", f"Downloaded {category_done} image(s).")
        elif category_done > 0:
            missing = TARGET_PER_CATEGORY - category_done
            failed_total += missing
            reporter.add_warning(
                f"Category {category}",
                f"Downloaded only {category_done} image(s), below target 3-5.",
            )
        else:
            failed_total += TARGET_PER_CATEGORY
            reporter.add_fail(f"Category {category}", "No image downloaded for this category.")

    manifest_payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "totalItems": len(manifest_items),
        "items": manifest_items,
    }
    SAMPLE_MANIFEST_PATH.write_text(
        json.dumps(manifest_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    if downloaded_total >= 30:
        reporter.add_pass("Total download target", f"Downloaded {downloaded_total} images (>=30 target).")
    else:
        reporter.add_warning("Total download target", f"Downloaded {downloaded_total} images (<30 target).")

    reporter.metrics.update(
        {
            "requestedTotal": requested_total,
            "downloadedTotal": downloaded_total,
            "failedTotal": failed_total,
            "manifestPath": str(SAMPLE_MANIFEST_PATH),
            "sampleImageFolder": str(SAMPLE_IMAGES_DIR),
        }
    )

    print("")
    print(f"Total requested: {requested_total}")
    print(f"Total downloaded: {downloaded_total}")
    print(f"Total failed: {failed_total}")

    report_paths = reporter.save("download_test")
    timestamp = utc_now_stamp()
    custom_report = RESULTS_DIR / f"download_report_{timestamp}.txt"
    custom_report.write_text(
        "\n".join(
            [
                "DOWNLOAD TEST IMAGE REPORT",
                f"Generated At: {datetime.now(timezone.utc).isoformat()}",
                f"Total requested: {requested_total}",
                f"Total downloaded: {downloaded_total}",
                f"Total failed: {failed_total}",
                f"Manifest: {SAMPLE_MANIFEST_PATH}",
                f"Reporter TXT: {report_paths['txt']}",
                f"Reporter JSON: {report_paths['json']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"[INFO] Saved download report: {custom_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
