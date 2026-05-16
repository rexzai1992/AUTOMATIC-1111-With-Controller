from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict

import cv2


@dataclass(frozen=True)
class PresetSettings:
    name: str
    control_weight: float
    denoising_strength: float
    control_mode: str
    prompt: str
    negative_prompt: str
    prompt_mode: str


@dataclass(frozen=True)
class DetectionMetrics:
    colorRatio: float
    edgeRatio: float
    whiteBackgroundRatio: float
    roughness: float


@dataclass(frozen=True)
class DetectionResult:
    preset: PresetSettings
    metrics: DetectionMetrics

    def to_dict(self) -> Dict[str, object]:
        return {
            "preset": asdict(self.preset),
            "metrics": asdict(self.metrics),
        }


SKETCH_LINEART = PresetSettings(
    name="sketch_lineart",
    control_weight=0.6,
    denoising_strength=0.7,
    control_mode="My prompt is more important",
    prompt=(
        "Transform the submitted pencil or line drawing into a fully colored lively illustration. "
        "Keep the original composition, subject, and main shapes, but add vibrant colors, soft lighting, "
        "polished storybook details, cheerful mood, expressive characters, rich background, clean painted "
        "shapes, high quality digital artwork, animated movie style."
    ),
    negative_prompt=(
        "black and white, monochrome, pencil sketch, plain lineart, unfinished, empty background, low detail, "
        "dull colors, rough lines, ugly, deformed, distorted, bad anatomy, extra limbs, text, watermark, logo, "
        "photorealistic"
    ),
    prompt_mode="lively_storybook",
)
KID_CRAYON = PresetSettings(
    name="kid_crayon",
    control_weight=0.65,
    denoising_strength=0.65,
    control_mode="My prompt is more important",
    prompt=(
        "Transform the submitted child drawing into a lively colorful children's storybook illustration. "
        "Preserve the main objects, layout, pose, and creative idea from the drawing, but repaint it as a "
        "polished vibrant digital artwork. Add rich colors, warm sunlight, soft shadows, expressive character "
        "faces, detailed background, lush environment, clean shapes, cheerful magical atmosphere, fully colored, "
        "high quality, animated movie style."
    ),
    negative_prompt=(
        "crayon texture, pencil texture, rough sketch, unfinished drawing, monochrome, black and white, flat "
        "colors, empty background, low detail, dull colors, messy lines, ugly, deformed, distorted, bad anatomy, "
        "extra limbs, text, watermark, logo, photorealistic"
    ),
    prompt_mode="lively_storybook",
)
COLORED_DRAWING = PresetSettings(
    name="colored_drawing",
    control_weight=0.7,
    denoising_strength=0.55,
    control_mode="Balanced",
    prompt=(
        "Enhance the submitted colored drawing into a polished vibrant illustration while preserving the original "
        "design, colors, layout, and childlike charm. Improve lighting, shading, cleanliness, depth, color "
        "richness, and details. Keep the artwork cheerful, friendly, fully colored, storybook style, high quality."
    ),
    negative_prompt=(
        "overchanged composition, different subject, monochrome, black and white, dull colors, messy, blurry, "
        "low quality, ugly, deformed, distorted, text, watermark, logo, photorealistic"
    ),
    prompt_mode="enhance_colored",
)
DEFAULT = PresetSettings(
    name="default",
    control_weight=0.65,
    denoising_strength=0.65,
    control_mode="My prompt is more important",
    prompt=(
        "Transform the submitted drawing into a lively colorful enhanced illustration. Preserve the original "
        "composition, subject, main shapes, and creative idea, but repaint it with vibrant colors, warm lighting, "
        "soft shadows, expressive details, clean shapes, cheerful atmosphere, fully colored, high quality "
        "storybook illustration, animated movie style."
    ),
    negative_prompt=(
        "unfinished sketch, monochrome, black and white, flat colors, dull colors, low detail, messy lines, "
        "blurry, ugly, deformed, distorted, bad anatomy, extra limbs, text, watermark, logo, photorealistic"
    ),
    prompt_mode="lively_storybook",
)


def _compute_color_ratio(image_bgr) -> float:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    saturation_channel = hsv[:, :, 1]
    colored_mask = cv2.inRange(saturation_channel, 25, 255)
    return cv2.countNonZero(colored_mask) / float(colored_mask.size)


def _compute_edge_ratio(image_bgr) -> float:
    grayscale = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(grayscale, (5, 5), 0)
    edges = cv2.Canny(blurred, 60, 150)
    return cv2.countNonZero(edges) / float(edges.size)


def _compute_white_background_ratio(image_bgr) -> float:
    white_mask = cv2.inRange(image_bgr, (240, 240, 240), (255, 255, 255))
    return cv2.countNonZero(white_mask) / float(white_mask.size)


def _compute_roughness(image_bgr) -> float:
    grayscale = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    laplacian = cv2.Laplacian(grayscale, cv2.CV_64F)
    _mean, std_dev = cv2.meanStdDev(laplacian)
    # Normalize to a practical 0..1 range for thresholding.
    return min(1.0, float(std_dev[0][0]) / 50.0)


def _select_preset(metrics: DetectionMetrics) -> PresetSettings:
    if metrics.colorRatio < 0.08 and metrics.edgeRatio > 0.12:
        return SKETCH_LINEART
    if metrics.colorRatio > 0.18 and metrics.roughness > 0.4:
        return KID_CRAYON
    if metrics.colorRatio > 0.18:
        return COLORED_DRAWING
    return DEFAULT


def analyze_image(image_path: Path) -> DetectionResult:
    image_bgr = cv2.imread(str(image_path))
    if image_bgr is None:
        raise ValueError(f"Unable to load image for analysis: {image_path}")

    metrics = DetectionMetrics(
        colorRatio=_compute_color_ratio(image_bgr),
        edgeRatio=_compute_edge_ratio(image_bgr),
        whiteBackgroundRatio=_compute_white_background_ratio(image_bgr),
        roughness=_compute_roughness(image_bgr),
    )
    preset = _select_preset(metrics)
    return DetectionResult(preset=preset, metrics=metrics)
