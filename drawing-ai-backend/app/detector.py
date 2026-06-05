from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import cv2


@dataclass(frozen=True)
class PresetSettings:
    name: str
    control_weight: float
    denoising_strength: float
    control_mode: str
    cfg_scale: float
    steps: int
    sampler_name: str
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
            "preset": {
                "name": self.preset.name,
                "controlWeight": self.preset.control_weight,
                "denoisingStrength": self.preset.denoising_strength,
                "controlMode": self.preset.control_mode,
                "cfgScale": self.preset.cfg_scale,
                "steps": self.preset.steps,
                "samplerName": self.preset.sampler_name,
                "prompt": self.preset.prompt,
                "negativePrompt": self.preset.negative_prompt,
                "promptMode": self.preset.prompt_mode,
            },
            "metrics": {
                "colorRatio": self.metrics.colorRatio,
                "edgeRatio": self.metrics.edgeRatio,
                "whiteBackgroundRatio": self.metrics.whiteBackgroundRatio,
                "roughness": self.metrics.roughness,
            },
        }


DRAWING_TO_ARTWORK_BASE_PROMPT = (
    "Transform the submitted child drawing into a lively, colorful, polished children's storybook illustration "
    "while preserving the original creative idea, main subject, composition, and childlike charm. Repaint the "
    "drawing with vibrant colors, warm cheerful lighting, soft shadows, richer details, clean shapes, expressive "
    "simple cartoon features, playful environmental details, and a full imaginative background. Make it feel alive, "
    "magical, joyful, and high quality, while still clearly inspired by the original child's drawing."
)
DRAWING_TO_ARTWORK_WHITE_BG_APPEND = (
    "Fill the empty white paper area with a rich playful background, colorful scenery, soft sky, grass, flowers, "
    "magical details, and storybook atmosphere. No empty white background."
)
DRAWING_TO_ARTWORK_NEGATIVE_PROMPT = (
    "same as input, unchanged drawing, too close to sketch, empty white background, plain background, unfinished "
    "sketch, monochrome, dull colors, low detail, boring, flat colors, messy artifacts, scary, horror, "
    "photorealistic, realistic human face, adult anatomy, bad hands, extra fingers, malformed hands, distorted "
    "face, ugly face, blurry, low quality, text, watermark, logo"
)


SKETCH_LINEART = PresetSettings(
    name="sketch_lineart",
    control_weight=0.62,
    denoising_strength=0.7,
    control_mode="My prompt is more important",
    cfg_scale=8.2,
    steps=34,
    sampler_name="DPM++ 2M Karras",
    prompt=DRAWING_TO_ARTWORK_BASE_PROMPT,
    negative_prompt=DRAWING_TO_ARTWORK_NEGATIVE_PROMPT,
    prompt_mode="lively_storybook",
)
KID_CRAYON = PresetSettings(
    name="kid_crayon",
    control_weight=0.68,
    denoising_strength=0.62,
    control_mode="My prompt is more important",
    cfg_scale=8.0,
    steps=32,
    sampler_name="DPM++ 2M Karras",
    prompt=DRAWING_TO_ARTWORK_BASE_PROMPT,
    negative_prompt=DRAWING_TO_ARTWORK_NEGATIVE_PROMPT,
    prompt_mode="lively_storybook",
)
COLORED_DRAWING = PresetSettings(
    name="colored_drawing",
    control_weight=0.7,
    denoising_strength=0.58,
    control_mode="Balanced",
    cfg_scale=7.8,
    steps=32,
    sampler_name="DPM++ 2M Karras",
    prompt=DRAWING_TO_ARTWORK_BASE_PROMPT,
    negative_prompt=DRAWING_TO_ARTWORK_NEGATIVE_PROMPT,
    prompt_mode="enhance_colored",
)
DEFAULT = PresetSettings(
    name="default",
    control_weight=0.60,
    denoising_strength=0.68,
    control_mode="My prompt is more important",
    cfg_scale=8.2,
    steps=32,
    sampler_name="DPM++ 2M Karras",
    prompt=DRAWING_TO_ARTWORK_BASE_PROMPT,
    negative_prompt=DRAWING_TO_ARTWORK_NEGATIVE_PROMPT,
    prompt_mode="lively_storybook",
)
TODDLER_ABSTRACT_PEOPLE = PresetSettings(
    name="toddler_abstract_people",
    control_weight=0.74,
    denoising_strength=0.55,
    control_mode="Balanced",
    cfg_scale=7.8,
    steps=32,
    sampler_name="DPM++ 2M Karras",
    prompt=DRAWING_TO_ARTWORK_BASE_PROMPT,
    negative_prompt=DRAWING_TO_ARTWORK_NEGATIVE_PROMPT,
    prompt_mode="lively_storybook",
)
ROUGH_LOW_COLOR_DRAWING = PresetSettings(
    name="rough_low_color_drawing",
    control_weight=0.58,
    denoising_strength=0.74,
    control_mode="My prompt is more important",
    cfg_scale=8.5,
    steps=34,
    sampler_name="DPM++ 2M Karras",
    prompt=DRAWING_TO_ARTWORK_BASE_PROMPT,
    negative_prompt=DRAWING_TO_ARTWORK_NEGATIVE_PROMPT,
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
    if metrics.whiteBackgroundRatio > 0.75 and metrics.roughness > 0.85 and metrics.edgeRatio < 0.08:
        return TODDLER_ABSTRACT_PEOPLE
    if metrics.whiteBackgroundRatio > 0.80 and metrics.edgeRatio < 0.03:
        return ROUGH_LOW_COLOR_DRAWING
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
    background_boost = metrics.whiteBackgroundRatio > 0.75
    if background_boost:
        preset = PresetSettings(
            name=preset.name,
            control_weight=preset.control_weight,
            denoising_strength=preset.denoising_strength,
            control_mode=preset.control_mode,
            cfg_scale=preset.cfg_scale,
            steps=preset.steps,
            sampler_name=preset.sampler_name,
            prompt=f"{preset.prompt} {DRAWING_TO_ARTWORK_WHITE_BG_APPEND}".strip(),
            negative_prompt=preset.negative_prompt,
            prompt_mode=preset.prompt_mode,
        )
    return DetectionResult(preset=preset, metrics=metrics)
