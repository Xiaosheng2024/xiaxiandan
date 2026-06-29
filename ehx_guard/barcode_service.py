"""使用 ReportLab 编码规则和 Pillow 生成 Code128 PNG。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.graphics.barcode.code128 import Code128


def generate_code128_png(
    value: str,
    output_path: str | Path,
    *,
    show_text: bool = True,
    module_width: int = 3,
    bar_height: int = 100,
    quiet_zone_modules: int = 10,
) -> Path:
    """生成不依赖条码字体的 Code128 PNG。"""

    text = str(value).strip()
    if not text:
        raise ValueError("Code128 条码内容不能为空")
    barcode = Code128(text)
    barcode.validate()
    barcode.encode()
    pattern = barcode.decompose()
    if not pattern:
        raise ValueError(f"无法编码 Code128：{text}")

    widths = [_pattern_width(character) for character in pattern]
    quiet_pixels = quiet_zone_modules * module_width
    barcode_width = sum(widths) * module_width
    text_height = 28 if show_text else 0
    image = Image.new(
        "RGB",
        (barcode_width + quiet_pixels * 2, bar_height + text_height + 8),
        "white",
    )
    draw = ImageDraw.Draw(image)
    x = quiet_pixels
    for character, width in zip(pattern, widths):
        pixel_width = width * module_width
        if character.isupper():
            draw.rectangle((x, 0, x + pixel_width - 1, bar_height), fill="black")
        x += pixel_width

    if show_text:
        font = _load_text_font(18)
        bounds = draw.textbbox((0, 0), text, font=font)
        text_width = bounds[2] - bounds[0]
        draw.text(
            ((image.width - text_width) / 2, bar_height + 4),
            text,
            fill="black",
            font=font,
        )

    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)
    return destination


def _pattern_width(character: str) -> int:
    base = "A" if character.isupper() else "a"
    width = ord(character) - ord(base) + 1
    if width < 1:
        raise ValueError(f"未知 Code128 图形编码：{character}")
    return width


def _load_text_font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()
