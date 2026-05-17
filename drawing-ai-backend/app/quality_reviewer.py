from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


BAD_TAGS = {
    # New primary tags
    "wrong_subject",
    "person_missing",
    "main_object_missing",
    "wrong_composition",
    "too_empty",
    "same_as_input",
    "bad_colors",
    "low_quality",
    "over_changed",
    "too_realistic",
    "scary_or_creepy",
    # Compatibility tags
    "wrong_generation",
    "composition_wrong",
    "changed_too_much",
    "creepy",
    "artwork_missing",
    "object_missing",
}

GOOD_TAGS = {
    "good_preserve_shape",
    "good_preserve_person",
    "good_preserve_artwork",
    "good_lively",
    "good_colors",
    "good_style",
    "good_overall",
}

_FACE_CASCADE: Optional[cv2.CascadeClassifier] = None
_FACE_CASCADE_READY = False


def _default_metrics() -> Dict[str, float]:
    return {
        "similarityScore": 0.0,
        "whiteBackgroundRatio": 0.0,
        "colorRatio": 0.0,
        "edgeRatio": 0.0,
        "colorGain": 0.0,
    }


def _default_review(
    note: str = "Auto review unavailable.",
    rating: int = 2,
    confidence: float = 0.3,
) -> Dict[str, Any]:
    return {
        "autoRating": int(max(1, min(5, rating))),
        "autoBadTags": [],
        "autoGoodTags": [],
        "autoNotes": note,
        "confidence": round(float(max(0.0, min(1.0, confidence))), 3),
        "metrics": _default_metrics(),
    }


def default_auto_review() -> Dict[str, Any]:
    return {
        "autoRating": 0,
        "autoBadTags": [],
        "autoGoodTags": [],
        "autoNotes": "Awaiting output image for auto review.",
        "confidence": 0.0,
        "metrics": _default_metrics(),
    }


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _load_image(path: Path) -> Optional[np.ndarray]:
    try:
        image = cv2.imread(str(path))
    except Exception:
        return None
    if image is None or image.size == 0:
        return None
    return image


def _resize_for_compare(
    a_bgr: np.ndarray,
    b_bgr: np.ndarray,
    max_dim: int = 768,
) -> Tuple[np.ndarray, np.ndarray]:
    h = min(a_bgr.shape[0], b_bgr.shape[0])
    w = min(a_bgr.shape[1], b_bgr.shape[1])
    if h <= 0 or w <= 0:
        return a_bgr, b_bgr

    scale = min(1.0, float(max_dim) / float(max(h, w)))
    target_w = max(32, int(w * scale))
    target_h = max(32, int(h * scale))

    a_resized = cv2.resize(a_bgr, (target_w, target_h), interpolation=cv2.INTER_AREA)
    b_resized = cv2.resize(b_bgr, (target_w, target_h), interpolation=cv2.INTER_AREA)
    return a_resized, b_resized


def _colorfulness_score(image_bgr: np.ndarray) -> float:
    image = image_bgr.astype(np.float32)
    b_channel, g_channel, r_channel = cv2.split(image)
    rg = np.abs(r_channel - g_channel)
    yb = np.abs(0.5 * (r_channel + g_channel) - b_channel)
    std_rg, std_yb = float(np.std(rg)), float(np.std(yb))
    mean_rg, mean_yb = float(np.mean(rg)), float(np.mean(yb))
    score = np.sqrt(std_rg * std_rg + std_yb * std_yb) + 0.3 * np.sqrt(
        mean_rg * mean_rg + mean_yb * mean_yb
    )
    return _clamp01(score / 100.0)


def _brightness_score(image_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    return _clamp01(float(np.mean(gray)) / 255.0)


def _white_ratio(image_bgr: np.ndarray) -> float:
    white_mask = cv2.inRange(image_bgr, (240, 240, 240), (255, 255, 255))
    return _clamp01(float(cv2.countNonZero(white_mask)) / float(white_mask.size))


def _edge_map(gray: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    return cv2.Canny(blurred, 60, 150)


def _edge_density(edge_map: np.ndarray) -> float:
    return _clamp01(float(cv2.countNonZero(edge_map)) / float(edge_map.size))


def _edge_iou(edge_a: np.ndarray, edge_b: np.ndarray) -> float:
    a_bin = edge_a > 0
    b_bin = edge_b > 0
    union = np.logical_or(a_bin, b_bin)
    union_count = int(np.count_nonzero(union))
    if union_count == 0:
        return 1.0
    intersection_count = int(np.count_nonzero(np.logical_and(a_bin, b_bin)))
    return _clamp01(intersection_count / float(union_count))


def _mse_normalized(a_bgr: np.ndarray, b_bgr: np.ndarray) -> float:
    diff = a_bgr.astype(np.float32) - b_bgr.astype(np.float32)
    mse = float(np.mean(diff * diff))
    return _clamp01(mse / (255.0 * 255.0))


def _hist_corr(a_bgr: np.ndarray, b_bgr: np.ndarray) -> float:
    a_hsv = cv2.cvtColor(a_bgr, cv2.COLOR_BGR2HSV)
    b_hsv = cv2.cvtColor(b_bgr, cv2.COLOR_BGR2HSV)
    hist_a = cv2.calcHist([a_hsv], [0, 1], None, [36, 32], [0, 180, 0, 256])
    hist_b = cv2.calcHist([b_hsv], [0, 1], None, [36, 32], [0, 180, 0, 256])
    cv2.normalize(hist_a, hist_a, alpha=1.0, norm_type=cv2.NORM_L1)
    cv2.normalize(hist_b, hist_b, alpha=1.0, norm_type=cv2.NORM_L1)
    corr = float(cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL))
    return _clamp01((corr + 1.0) / 2.0)


def _sharpness_score(image_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    variance = float(laplacian.var())
    return _clamp01(variance / 2500.0)


def _face_cascade() -> Optional[cv2.CascadeClassifier]:
    global _FACE_CASCADE
    global _FACE_CASCADE_READY
    if _FACE_CASCADE_READY:
        return _FACE_CASCADE
    _FACE_CASCADE_READY = True
    try:
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(str(cascade_path))
        if cascade.empty():
            _FACE_CASCADE = None
        else:
            _FACE_CASCADE = cascade
    except Exception:
        _FACE_CASCADE = None
    return _FACE_CASCADE


def _count_faces(image_bgr: np.ndarray) -> int:
    cascade = _face_cascade()
    if cascade is None:
        return 0
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(28, 28))
    return int(len(faces))


def _paper_score(image_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 45, 130)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image_area = float(max(1, image_bgr.shape[0] * image_bgr.shape[1]))
    best_score = 0.0
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area <= 0:
            continue
        area_ratio = area / image_area
        if area_ratio < 0.03 or area_ratio > 0.75:
            continue

        perimeter = float(cv2.arcLength(contour, True))
        if perimeter <= 0:
            continue
        approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
        vertex_count = len(approx)
        if vertex_count < 4 or vertex_count > 8:
            continue

        x, y, w, h = cv2.boundingRect(contour)
        rect_area = float(max(1, w * h))
        rectangularity = area / rect_area
        shape_score = _clamp01(rectangularity)
        score = _clamp01(area_ratio * 1.8) * shape_score
        best_score = max(best_score, score)
    return _clamp01(best_score)


def _add_tag(target: List[str], tag: str) -> None:
    if tag in BAD_TAGS and tag not in target:
        target.append(tag)


def _add_good(target: List[str], tag: str) -> None:
    if tag in GOOD_TAGS and tag not in target:
        target.append(tag)


def _vision_mode_enabled() -> bool:
    mode = str(os.getenv("QUALITY_REVIEW_MODE", "heuristic")).strip().lower()
    return mode in {"vision", "hybrid"}


def _run_optional_vision_review() -> Optional[str]:
    # Placeholder for future vision-model integration.
    return None


def review_generation_quality(
    *,
    input_path: Path,
    output_path: Path,
    generation_mode: str,
    preset: str,
    style_id: str,
    generation_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    input_image = _load_image(input_path)
    output_image = _load_image(output_path)

    if input_image is None:
        out = _default_review(
            note="Input image could not be read. Heuristic review skipped.",
            rating=2,
            confidence=0.25,
        )
        return out

    if output_image is None:
        return {
            "autoRating": 1,
            "autoBadTags": ["low_quality", "wrong_subject"],
            "autoGoodTags": [],
            "autoNotes": "Output image missing or invalid. Heuristic review flagged critical failure.",
            "confidence": 0.98,
            "metrics": _default_metrics(),
        }

    in_cmp, out_cmp = _resize_for_compare(input_image, output_image)
    in_gray = cv2.cvtColor(in_cmp, cv2.COLOR_BGR2GRAY)
    out_gray = cv2.cvtColor(out_cmp, cv2.COLOR_BGR2GRAY)
    in_edges = _edge_map(in_gray)
    out_edges = _edge_map(out_gray)

    color_in = _colorfulness_score(in_cmp)
    color_out = _colorfulness_score(out_cmp)
    color_gain = color_out - color_in
    brightness_out = _brightness_score(out_cmp)
    white_in = _white_ratio(in_cmp)
    white_out = _white_ratio(out_cmp)
    edge_iou = _edge_iou(in_edges, out_edges)
    edge_density_out = _edge_density(out_edges)
    mse_norm = _mse_normalized(in_cmp, out_cmp)
    hist_corr = _hist_corr(in_cmp, out_cmp)
    sharpness_out = _sharpness_score(out_cmp)
    faces_in = _count_faces(in_cmp)
    faces_out = _count_faces(out_cmp)
    paper_in = _paper_score(in_cmp)
    paper_out = _paper_score(out_cmp)

    similarity_score = _clamp01(0.45 * edge_iou + 0.35 * hist_corr + 0.2 * (1.0 - mse_norm))
    same_as_input = similarity_score > 0.9 and mse_norm < 0.012
    over_changed = similarity_score < 0.18 and mse_norm > 0.18
    too_empty = white_out > 0.82 or edge_density_out < 0.007
    bad_colors = color_out < 0.09 or (color_gain < 0.01 and white_out > 0.72)
    low_quality = sharpness_out < 0.033 or edge_density_out < 0.0055
    too_realistic = bool(
        faces_out > 0 and sharpness_out > 0.62 and hist_corr < 0.32 and color_out < 0.18 and white_out < 0.35
    )
    scary_or_creepy = bool(brightness_out < 0.12 or (brightness_out < 0.18 and color_out < 0.08))

    mode = str(generation_mode or "").strip().lower() or "drawing_to_artwork"
    bad_tags: List[str] = []
    good_tags: List[str] = []
    notes: List[str] = []
    score = 3.0

    if same_as_input:
        _add_tag(bad_tags, "same_as_input")
        score -= 1.35

    if over_changed:
        _add_tag(bad_tags, "over_changed")
        score -= 1.05

    if too_empty:
        _add_tag(bad_tags, "too_empty")
        score -= 1.0

    if bad_colors:
        _add_tag(bad_tags, "bad_colors")
        score -= 0.65

    if low_quality:
        _add_tag(bad_tags, "low_quality")
        score -= 0.8

    if too_realistic:
        _add_tag(bad_tags, "too_realistic")
        score -= 0.45

    if scary_or_creepy:
        _add_tag(bad_tags, "scary_or_creepy")
        score -= 0.5

    if mode == "person_holding_artwork":
        person_missing = faces_in > 0 and faces_out == 0
        main_object_missing = paper_in > 0.12 and paper_out < max(0.04, paper_in * 0.35)
        person_changed = faces_in > 0 and faces_out > 0 and edge_iou < 0.18
        wrong_composition = similarity_score < 0.14 and edge_iou < 0.12

        if person_missing:
            _add_tag(bad_tags, "person_missing")
            score -= 1.2
        elif person_changed:
            _add_tag(bad_tags, "wrong_subject")
            score -= 0.9

        if main_object_missing:
            _add_tag(bad_tags, "main_object_missing")
            score -= 1.0

        if wrong_composition:
            _add_tag(bad_tags, "wrong_composition")
            score -= 0.65

        if person_missing or main_object_missing:
            _add_tag(bad_tags, "wrong_subject")
            score -= 0.6

        if not person_missing and not person_changed and (faces_in > 0 or faces_out > 0):
            _add_good(good_tags, "good_preserve_person")
            score += 0.45
        if not main_object_missing and paper_out > 0.03:
            _add_good(good_tags, "good_preserve_artwork")
            score += 0.35
        if edge_iou >= 0.2 and edge_iou <= 0.85:
            _add_good(good_tags, "good_preserve_shape")
            score += 0.35
    else:
        if same_as_input and color_gain <= 0.015:
            _add_tag(bad_tags, "wrong_subject")
            score -= 0.65
        if similarity_score < 0.1 and edge_iou < 0.1:
            _add_tag(bad_tags, "main_object_missing")
            score -= 0.7
        if over_changed:
            _add_tag(bad_tags, "wrong_composition")
            score -= 0.4
        if edge_iou >= 0.18 and edge_iou <= 0.82:
            _add_good(good_tags, "good_preserve_shape")
            score += 0.45
        if color_gain > 0.02 and white_out < white_in:
            _add_good(good_tags, "good_colors")
            _add_good(good_tags, "good_lively")
            score += 0.65
        if not too_empty and not low_quality and color_out > 0.12:
            _add_good(good_tags, "good_style")
            score += 0.25

    if not bad_tags and score >= 3.85:
        _add_good(good_tags, "good_overall")

    score = max(1.0, min(5.0, score))
    auto_rating = int(round(score))

    notes.append("Heuristic review: white/empty, similarity, color, edge-detail checks enabled.")
    if _vision_mode_enabled():
        vision_note = _run_optional_vision_review()
        if vision_note:
            notes.append(f"Vision review: {vision_note}")
        else:
            notes.append("Vision review mode requested but no model configured; heuristic fallback used.")
    notes.append(
        f"mode={mode} preset={preset or '-'} styleId={style_id or '-'} "
        f"sim={similarity_score:.3f} colorGain={color_gain:.3f} edge={edge_density_out:.3f} "
        f"mse={mse_norm:.3f} white={white_out:.3f}"
    )
    if generation_settings:
        denoise = generation_settings.get("denoisingStrength")
        weight = generation_settings.get("controlWeight")
        cfg = generation_settings.get("cfgScale")
        notes.append(f"settings: denoise={denoise} controlWeight={weight} cfgScale={cfg}")

    confidence = 0.5
    if faces_in > 0 or faces_out > 0:
        confidence += 0.1
    if paper_in > 0.08 or paper_out > 0.08:
        confidence += 0.08
    if same_as_input or over_changed or too_empty or low_quality:
        confidence += 0.08
    if _vision_mode_enabled():
        confidence -= 0.05
    confidence = min(0.86, max(0.35, confidence))

    return {
        "autoRating": auto_rating,
        "autoBadTags": bad_tags,
        "autoGoodTags": good_tags,
        "autoNotes": " | ".join(notes),
        "confidence": round(float(confidence), 3),
        "metrics": {
            "similarityScore": round(similarity_score, 4),
            "whiteBackgroundRatio": round(white_out, 4),
            "colorRatio": round(color_out, 4),
            "edgeRatio": round(edge_density_out, 4),
            "colorGain": round(color_gain, 4),
        },
    }
