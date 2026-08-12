"""Draw grounded element boxes on screenshots for debugging."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
import base64
import io

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def annotate_image(image, elements: List[Dict[str, Any]], max_labels: int = 30):
    if not HAS_PIL:
        return None
    if not isinstance(image, Image.Image):
        try:
            image = Image.fromarray(image)
        except Exception:
            return None
    img = image.convert("RGB").copy()
    draw = ImageDraw.Draw(img)
    for i, el in enumerate(elements[:max_labels]):
        bbox = el.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        x1, y1, x2, y2 = map(int, bbox)
        color = (0, 200, 80) if el.get("source") == "fused" else (0, 140, 255)
        if el.get("kind") == "a11y":
            color = (255, 160, 0)
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
        label = (el.get("label") or "")[:28]
        conf = el.get("confidence")
        tag = f"{i}:{label}" + (f" {conf:.2f}" if isinstance(conf, float) else "")
        draw.text((x1 + 2, max(0, y1 - 12)), tag, fill=color)
    return img


def annotate_to_base64(image, elements: List[Dict[str, Any]], quality: int = 70) -> Optional[str]:
    img = annotate_image(image, elements)
    if img is None:
        return None
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("ascii")
