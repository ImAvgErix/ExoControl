"""
Local UI Grounding — clearer vision without heavy models.

Fuses:
  1. OpenCV structural detection (buttons, inputs, clickable-looking regions)
  2. OCR text regions
  3. Optional external detector hook (OmniParser / UI-TARS) if installed

Goal: when Cua a11y is sparse or missing, still produce high-quality
click targets so smart_click stays accurate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


@dataclass
class GroundedElement:
    label: str
    bbox: List[int]  # x1,y1,x2,y2
    confidence: float
    kind: str  # button | input | text | icon | region
    source: str  # opencv | ocr | fused | omniparser
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def center(self) -> Tuple[int, int]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "bbox": self.bbox,
            "confidence": round(self.confidence, 3),
            "kind": self.kind,
            "source": self.source,
            "x": self.center[0],
            "y": self.center[1],
        }


def _pil_to_bgr(img) -> Optional[np.ndarray]:
    if not HAS_CV2 or not HAS_PIL:
        return None
    if isinstance(img, np.ndarray):
        if img.ndim == 2:
            return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        if img.shape[2] == 4:
            return cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        if img.shape[2] == 3:
            # assume RGB from PIL
            return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        return img
    arr = np.array(img)
    if arr.ndim == 2:
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    if arr.shape[2] == 4:
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def detect_structural(img_bgr: np.ndarray, max_elements: int = 40) -> List[GroundedElement]:
    """
    Find button-like and input-like regions via edges + contours + aspect heuristics.
    Fast, offline, no model weights.
    """
    if not HAS_CV2:
        return []
    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 40, 120)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.dilate(edges, kernel, iterations=1)
    # Also threshold path for filled controls
    try:
        thr = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY_INV, 11, 2)
        edges = cv2.bitwise_or(edges, thr)
    except Exception:
        pass
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    elements: List[GroundedElement] = []
    area_img = float(h * w)

    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw < 18 or bh < 12:
            continue
        if bw > w * 0.92 or bh > h * 0.6:
            continue
        area = bw * bh
        if area < 200 or area > area_img * 0.25:
            continue
        aspect = bw / max(bh, 1)
        # Heuristic classification
        kind = "region"
        conf = 0.35
        if 1.5 <= aspect <= 8 and 18 <= bh <= 64:
            kind = "button"
            conf = 0.5
        elif 2.5 <= aspect <= 20 and 16 <= bh <= 48:
            kind = "input"
            conf = 0.48
        elif 0.7 <= aspect <= 1.4 and 20 <= bw <= 80:
            kind = "icon"
            conf = 0.4
        # Rectangularity check
        rect_area = bw * bh
        cnt_area = cv2.contourArea(cnt)
        if rect_area > 0 and cnt_area / rect_area > 0.55:
            conf += 0.08
        # Reject near-full-width thin lines
        if bh < 10 and bw > w * 0.5:
            continue
        elements.append(GroundedElement(
            label=f"{kind}",
            bbox=[int(x), int(y), int(x + bw), int(y + bh)],
            confidence=min(0.75, conf),
            kind=kind,
            source="opencv",
            meta={"aspect": round(aspect, 2), "area": int(area)},
        ))

    # Prefer larger mid-size interactive looking boxes, limit count
    elements.sort(key=lambda e: (e.confidence, (e.bbox[2]-e.bbox[0])*(e.bbox[3]-e.bbox[1])), reverse=True)
    return elements[:max_elements]


def fuse_ocr_with_structure(
    ocr_items: List[Dict[str, Any]],
    structural: List[GroundedElement],
    iou_thresh: float = 0.15,
) -> List[GroundedElement]:
    """
    Attach OCR text labels to nearby structural boxes; keep pure OCR as text targets.
    """
    def iou(a: List[int], b: List[int]) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        inter = iw * ih
        if inter <= 0:
            return 0.0
        area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
        area_b = max(1, (bx2 - bx1) * (by2 - by1))
        return inter / float(area_a + area_b - inter)

    used_ocr = set()
    fused: List[GroundedElement] = []

    for s in structural:
        best_i, best_iou, best_text, best_conf = -1, 0.0, "", 0.0
        for i, item in enumerate(ocr_items):
            bbox = item.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            score = iou(s.bbox, bbox)
            # also accept OCR center inside structural box
            cx = (bbox[0] + bbox[2]) // 2
            cy = (bbox[1] + bbox[3]) // 2
            inside = s.bbox[0] <= cx <= s.bbox[2] and s.bbox[1] <= cy <= s.bbox[3]
            if inside:
                score = max(score, 0.25)
            if score > best_iou:
                best_iou = score
                best_i = i
                best_text = (item.get("text") or "").strip()
                best_conf = float(item.get("confidence", 0.5))
        if best_i >= 0 and best_iou >= iou_thresh and best_text:
            used_ocr.add(best_i)
            fused.append(GroundedElement(
                label=best_text,
                bbox=s.bbox,
                confidence=min(0.95, max(s.confidence, best_conf) + 0.12),
                kind=s.kind if s.kind != "region" else "button",
                source="fused",
                meta={"ocr": best_text, "struct_kind": s.kind},
            ))
        else:
            fused.append(s)

    # Remaining OCR as text targets
    for i, item in enumerate(ocr_items):
        if i in used_ocr:
            continue
        text = (item.get("text") or "").strip()
        bbox = item.get("bbox")
        if not text or not bbox or len(bbox) != 4:
            continue
        conf = float(item.get("confidence", 0.5))
        fused.append(GroundedElement(
            label=text,
            bbox=[int(b) for b in bbox],
            confidence=conf,
            kind="text",
            source="ocr",
            meta=item,
        ))

    fused.sort(key=lambda e: e.confidence, reverse=True)
    return fused


def try_omniparser(img_bgr: np.ndarray) -> List[GroundedElement]:
    """Optional hook: if OmniParser (or similar) is installed, use it."""
    try:
        # Placeholder for optional dependency — users can plug in real OmniParser
        import importlib
        mod = importlib.util.find_spec("omniparser")
        if mod is None:
            return []
        # Real integration would go here
        return []
    except Exception:
        return []


class LocalGrounder:
    """
    Main entry: given a screenshot (PIL or ndarray) + optional OCR items,
    return ranked GroundedElements.
    """

    def __init__(self, max_elements: int = 50):
        self.max_elements = max_elements
        self._cache_key = None
        self._cache_result: List[GroundedElement] = []

    def ground(
        self,
        image: Any,
        ocr_items: Optional[List[Dict[str, Any]]] = None,
        use_cache: bool = True,
    ) -> List[GroundedElement]:
        ocr_items = ocr_items or []
        bgr = _pil_to_bgr(image)
        if bgr is None:
            # OCR-only fallback
            out = []
            for item in ocr_items:
                text = (item.get("text") or "").strip()
                bbox = item.get("bbox")
                if text and bbox and len(bbox) == 4:
                    out.append(GroundedElement(
                        label=text, bbox=[int(b) for b in bbox],
                        confidence=float(item.get("confidence", 0.5)),
                        kind="text", source="ocr", meta=item,
                    ))
            return out[: self.max_elements]

        # Optional heavy detector
        omni = try_omniparser(bgr)
        if omni:
            return omni[: self.max_elements]

        structural = detect_structural(bgr, max_elements=self.max_elements)
        fused = fuse_ocr_with_structure(ocr_items, structural)
        return fused[: self.max_elements]

    def ground_from_obs(self, obs: Dict[str, Any]) -> List[GroundedElement]:
        """Convenience: extract image + OCR from Aether observation dict."""
        ocr = obs.get("vision", {}).get("ocr", []) or []
        # image may be base64 or absent — structural needs pixels
        # PerceptionEngine stores raw sometimes under vision.image_raw; else skip structural
        image = obs.get("vision", {}).get("image_raw")
        if image is None:
            # OCR-only
            return self.ground(None, ocr_items=ocr)
        return self.ground(image, ocr_items=ocr)
