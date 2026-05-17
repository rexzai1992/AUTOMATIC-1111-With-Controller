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


SKETCH_LINEART = PresetSettings(
    name="sketch_lineart",
    control_weight=0.6,
    denoising_strength=0.7,
    control_mode="My prompt is more important",
    cfg_scale=7.0,
    steps=30,
    sampler_name="DPM++ 2M Karras",
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
    control_weight=0.78,
    denoising_strength=0.48,
    control_mode="Balanced",
    cfg_scale=7.2,
    steps=30,
    sampler_name="DPM++ 2M Karras",
    prompt=(
        "Transform the submitted child drawing into a lively colorful children's storybook illustration. Keep the "
        "main objects, layout, pose, and creative idea, then repaint with bold playful colors, warm sunlight, soft "
        "shadows, expressive cartoon faces, cleaner hands, detailed scenery, and rich environment depth. Keep the "
        "result clearly stylized and non-photorealistic, fully colored, cheerful, magical, polished, and high "
        "quality animated movie style."
    ),
    negative_prompt=(
        "photorealistic, realistic skin, realistic face, realistic hands, 3d render, adult proportions, scary, "
        "horror, crayon texture, pencil texture, rough sketch, unfinished drawing, monochrome, black and white, "
        "flat colors, empty background, low detail, dull colors, messy lines, bad face, bad eyes, bad hands, extra "
        "fingers, missing fingers, fused fingers, bad anatomy, deformed, distorted, extra limbs, text, watermark, "
        "logo"
    ),
    prompt_mode="lively_storybook",
)
COLORED_DRAWING = PresetSettings(
    name="colored_drawing",
    control_weight=0.7,
    denoising_strength=0.55,
    control_mode="Balanced",
    cfg_scale=7.0,
    steps=30,
    sampler_name="DPM++ 2M Karras",
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
    control_weight=0.55,
    denoising_strength=0.74,
    control_mode="My prompt is more important",
    cfg_scale=8.2,
    steps=30,
    sampler_name="DPM++ 2M Karras",
    prompt=(
        "Transform the submitted drawing into a lively colorful enhanced storybook illustration. Preserve the "
        "original composition, subject, main shapes, and creative idea, then push stronger stylization, richer "
        "colors, warm cinematic lighting, soft shading, expressive details, and playful character energy. Deliver a "
        "fully colored cheerful scene with clean shapes, charming depth, and high quality animated movie style."
    ),
    negative_prompt=(
        "unfinished sketch, monochrome, black and white, flat colors, dull colors, low detail, messy lines, "
        "blurry, ugly, deformed, distorted, bad anatomy, extra limbs, text, watermark, logo, photorealistic"
    ),
    prompt_mode="lively_storybook",
)
TODDLER_ABSTRACT_PEOPLE = PresetSettings(
    name="toddler_abstract_people",
    control_weight=0.82,
    denoising_strength=0.42,
    control_mode="Balanced",
    cfg_scale=7.5,
    steps=28,
    sampler_name="DPM++ 2M Karras",
    prompt=(
        "Transform the submitted toddler drawing into a beautiful children's picture-book illustration while "
        "preserving the original childlike identity, proportions, object positions, face placement, pose, and "
        "playful imperfections from the drawing. Do not redesign the composition. Keep the character simple, "
        "innocent, and charming like a real young child's imagination. Preserve the large face shape, simple facial "
        "placement, simple limbs, floating decorative objects, and unusual childlike proportions exactly as "
        "interpreted from the original drawing. Convert rough lines into clean soft illustrated outlines while "
        "keeping the original playful structure. Add cheerful colorful storybook styling, soft pastel colors, warm "
        "sunlight, gentle soft shadows, magical playful atmosphere, child-safe environment, cute simple flowers, "
        "sparkles, whimsical decorative elements, rich but not overcrowded background, soft grass or playful dreamy "
        "environment. Use simple cartoon facial features, friendly eyes, soft smile, natural child-safe expression, "
        "soft rounded features, simple cute hands, simple cute fingers, soft body proportions, charming children's "
        "illustration style. Highly detailed children's storybook illustration, polished digital art, soft lighting, "
        "warm colors, magical innocence, picture book quality, family friendly, visually rich, emotionally warm."
    ),
    negative_prompt=(
        "photorealistic, realistic human face, adult face, mature face, creepy face, horror, scary, monster, "
        "zombie, sharp jawline, realistic skin, cinematic portrait, hyper realistic eyes, muscular anatomy, sexy, "
        "violent, dark scene, extra fingers, extra hands, malformed hands, mutated limbs, broken anatomy, deformed "
        "face, ugly face, distorted face, duplicated body, duplicated limbs, missing limbs, empty white background, "
        "unfinished sketch, rough pencil texture, grayscale, monochrome, blurry, low quality, watermark, logo, text"
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
    if metrics.whiteBackgroundRatio > 0.75 and metrics.roughness > 0.85 and metrics.edgeRatio < 0.08:
        return TODDLER_ABSTRACT_PEOPLE
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
            prompt=f"{preset.prompt} rich environment, full background, playful scene, no empty white areas",
            negative_prompt=preset.negative_prompt,
            prompt_mode=preset.prompt_mode,
        )
    return DetectionResult(preset=preset, metrics=metrics)
