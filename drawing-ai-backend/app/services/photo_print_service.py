import math
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


PHOTO_WIDTH = 1200
PHOTO_HEIGHT = 1800
PHOTO_TEMPLATE = "photo_frame_4x6"


class PillowMissingError(RuntimeError):
    pass


class GeneratedOutputMissingError(FileNotFoundError):
    pass


def _load_pillow() -> Tuple[Any, Any, Any, Any]:
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
    except ImportError as exc:
        raise PillowMissingError(
            "Pillow is required for photo print generation. Install pillow manually."
        ) from exc
    return Image, ImageDraw, ImageFont, ImageOps


def _safe_job_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return safe or "unknown"


def _font(ImageFont: Any, size: int, bold: bool = False) -> Any:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _text_size(draw: Any, text: str, font: Any) -> Tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])


def _draw_centered_text(
    draw: Any,
    box: Tuple[int, int, int, int],
    text: str,
    font: Any,
    fill: Tuple[int, int, int],
) -> None:
    x, y, width, height = box
    text = str(text or "").strip()
    text_width, text_height = _text_size(draw, text, font)
    draw.text(
        (x + (width - text_width) / 2, y + (height - text_height) / 2),
        text,
        font=font,
        fill=fill,
    )


def _star_points(cx: int, cy: int, outer: int, inner: int, points: int = 5) -> list:
    result = []
    for index in range(points * 2):
        radius = outer if index % 2 == 0 else inner
        angle = -math.pi / 2 + (math.pi * index / points)
        result.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
    return result


def _draw_decorations(draw: Any) -> None:
    circles = [
        (45, 220, 34, (255, 202, 212)),
        (1100, 185, 42, (174, 222, 255)),
        (70, 1470, 30, (255, 231, 153)),
        (1090, 1420, 36, (190, 240, 208)),
        (1028, 1680, 26, (255, 202, 212)),
        (150, 1715, 22, (174, 222, 255)),
    ]
    for x, y, radius, color in circles:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)

    confetti = [
        (132, 188, 192, 202, (255, 146, 104)),
        (980, 330, 1030, 344, (133, 196, 255)),
        (70, 900, 118, 914, (132, 213, 163)),
        (1035, 870, 1087, 884, (255, 211, 94)),
        (940, 1330, 990, 1345, (239, 138, 255)),
        (210, 1395, 262, 1410, (93, 196, 225)),
    ]
    for x1, y1, x2, y2, color in confetti:
        draw.rectangle((x1, y1, x2, y2), fill=color)

    stars = [
        (95, 85, 20, 9, (255, 211, 94)),
        (1095, 85, 22, 10, (255, 146, 104)),
        (1025, 1510, 18, 8, (132, 213, 163)),
        (92, 1260, 17, 8, (239, 138, 255)),
    ]
    for cx, cy, outer, inner, color in stars:
        draw.polygon(_star_points(cx, cy, outer, inner), fill=color)


def _fit_image(ImageOps: Any, image: Any, box_size: Tuple[int, int]) -> Any:
    working = image.copy()
    try:
        return ImageOps.contain(working, box_size)
    except AttributeError:
        working.thumbnail(box_size)
        return working


def _paste_rounded(base: Any, image: Any, xy: Tuple[int, int], radius: int) -> None:
    Image, _ImageDraw, _ImageFont, _ImageOps = _load_pillow()
    mask = Image.new("L", image.size, 0)
    mask_draw = _ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, image.width, image.height), radius=radius, fill=255)
    base.paste(image, xy, mask)


def _logo_candidates(filename: str) -> list:
    return [
        Path("public") / "assets" / "print" / filename,
        Path("static") / "assets" / "print" / filename,
    ]


def _draw_logo_or_placeholder(
    canvas: Any,
    draw: Any,
    Image: Any,
    ImageOps: Any,
    ImageFont: Any,
    filename: str,
    placeholder: str,
    box: Tuple[int, int, int, int],
) -> bool:
    x, y, width, height = box
    logo_path: Optional[Path] = None
    for candidate in _logo_candidates(filename):
        if candidate.is_file():
            logo_path = candidate
            break

    draw.rounded_rectangle((x, y, x + width, y + height), radius=24, fill=(255, 255, 255), outline=(83, 146, 255), width=4)
    if logo_path is None:
        font = _font(ImageFont, 34, bold=True)
        _draw_centered_text(draw, (x, y, width, height), placeholder, font, (34, 65, 120))
        return False

    with Image.open(logo_path) as logo:
        fitted = _fit_image(ImageOps, logo.convert("RGBA"), (width - 38, height - 28))
        paste_x = x + (width - fitted.width) // 2
        paste_y = y + (height - fitted.height) // 2
        canvas.paste(fitted, (paste_x, paste_y), fitted)
    return True


def create_4x6_photo_print(
    job_id: str,
    output_path: str,
    visitor_name: str,
    output_dir: str = "prints",
) -> Dict[str, Any]:
    Image, ImageDraw, ImageFont, ImageOps = _load_pillow()

    source_path = Path(str(output_path or "")).expanduser()
    if not source_path.is_file():
        raise GeneratedOutputMissingError("Generated output image not found")

    safe_job_id = _safe_job_id(job_id)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    print_path = output_root / f"photo_{safe_job_id}.png"

    canvas = Image.new("RGB", (PHOTO_WIDTH, PHOTO_HEIGHT), (255, 249, 238))
    draw = ImageDraw.Draw(canvas)

    for y in range(PHOTO_HEIGHT):
        ratio = y / PHOTO_HEIGHT
        color = (
            int(255 - ratio * 10),
            int(249 - ratio * 20),
            int(238 + ratio * 14),
        )
        draw.line((0, y, PHOTO_WIDTH, y), fill=color)

    _draw_decorations(draw)
    draw.rounded_rectangle((38, 38, 1162, 1762), radius=52, outline=(255, 126, 118), width=10)
    draw.rounded_rectangle((58, 58, 1142, 1742), radius=42, outline=(91, 184, 238), width=6)

    title_font = _font(ImageFont, 58, bold=True)
    subtitle_font = _font(ImageFont, 32)
    name_label_font = _font(ImageFont, 28)
    name_font = _font(ImageFont, 54, bold=True)
    footer_font = _font(ImageFont, 28)

    _draw_centered_text(draw, (100, 65, 1000, 70), "AI Genius Photo", title_font, (34, 65, 120))
    _draw_centered_text(draw, (100, 145, 1000, 46), "Created at Wonderpark", subtitle_font, (73, 105, 155))

    card_box = (100, 250, 1100, 1300)
    draw.rounded_rectangle(card_box, radius=38, fill=(255, 255, 255), outline=(255, 189, 73), width=12)
    draw.rounded_rectangle((118, 268, 1082, 1282), radius=30, outline=(132, 213, 163), width=6)

    with Image.open(source_path) as source:
        fitted = _fit_image(ImageOps, source.convert("RGB"), (940, 990))
        paste_x = 100 + (1000 - fitted.width) // 2
        paste_y = 250 + (1050 - fitted.height) // 2
        _paste_rounded(canvas, fitted, (paste_x, paste_y), radius=26)

    display_name = str(visitor_name or "").strip() or "Wonderpark Guest"
    _draw_centered_text(draw, (100, 1316, 1000, 34), "Created by", name_label_font, (96, 116, 150))
    _draw_centered_text(draw, (100, 1350, 1000, 76), display_name, name_font, (30, 59, 112))

    wonderpark_used = _draw_logo_or_placeholder(
        canvas,
        draw,
        Image,
        ImageOps,
        ImageFont,
        "wonderpark-logo.png",
        "WONDERPARK",
        (150, 1510, 340, 110),
    )
    ai_genius_used = _draw_logo_or_placeholder(
        canvas,
        draw,
        Image,
        ImageOps,
        ImageFont,
        "ai-genius-logo.png",
        "AI GENIUS",
        (710, 1510, 340, 110),
    )

    _draw_centered_text(
        draw,
        (100, 1652, 1000, 54),
        "Thank you for creating with AI Genius at Wonderpark!",
        footer_font,
        (73, 105, 155),
    )

    canvas.save(print_path, format="PNG")
    stored_path = f"{output_root.name}/{print_path.name}" if output_root.is_absolute() else print_path.as_posix()
    return {
        "photoPrintPath": stored_path,
        "photoPrintUrl": f"/prints/{print_path.name}",
        "width": PHOTO_WIDTH,
        "height": PHOTO_HEIGHT,
        "logosUsed": bool(wonderpark_used or ai_genius_used),
        "logoFallbackUsed": not bool(wonderpark_used and ai_genius_used),
    }
