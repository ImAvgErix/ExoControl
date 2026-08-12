"""
Exo Control - Perception Layer (Eyes)
Hybrid screen observation: screenshot + OCR + simple vision elements + diff.
Designed to be extended with OmniParser, UI-TARS, platform a11y, continuous capture.
"""

from __future__ import annotations
import base64
import hashlib
import io
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import mss
    import mss.tools
    HAS_MSS = True
except ImportError:
    HAS_MSS = False


def _mss_session():
    return getattr(mss, "MSS", mss.mss)()

try:
    from PIL import Image, ImageDraw, ImageChops
    import numpy as np
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Lazy OCR flags — never import easyocr/torch at module load (CLI cold start).
HAS_EASYOCR: Optional[bool] = None
HAS_TESSERACT: Optional[bool] = None


def _probe_tesseract() -> bool:
    global HAS_TESSERACT
    if HAS_TESSERACT is not None:
        return HAS_TESSERACT
    try:
        import pytesseract  # noqa: F401
        HAS_TESSERACT = True
    except ImportError:
        HAS_TESSERACT = False
    return bool(HAS_TESSERACT)


def _probe_easyocr() -> bool:
    global HAS_EASYOCR
    if HAS_EASYOCR is not None:
        return HAS_EASYOCR
    try:
        import easyocr  # noqa: F401
        HAS_EASYOCR = True
    except ImportError:
        HAS_EASYOCR = False
    return bool(HAS_EASYOCR)


@dataclass
class BBox:
    x1: int
    y1: int
    x2: int
    y2: int

    def as_list(self) -> List[int]:
        return [self.x1, self.y1, self.x2, self.y2]

    @property
    def center(self) -> Tuple[int, int]:
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)


class PerceptionEngine:
    """Core eyes for Exo Control."""

    def __init__(self, use_ocr: bool = True, ocr_engine: str = "auto"):
        self.use_ocr = use_ocr
        self.ocr_engine = ocr_engine
        self._last_frame: Optional[Image.Image] = None
        self._last_hash: Optional[str] = None
        self._ocr_reader = None
        self._ocr_init_attempted = False
        self._obs_cache = None
        self._obs_cache_time = 0.0
        self._obs_cache_ttl = 0.35  # seconds — continuous perception reuse
        # Do NOT construct easyocr.Reader here — it pulls torch and can take
        # seconds + spam deprecation warnings on every CLI/MCP cold start.

    def ocr_available(self) -> bool:
        """Whether an OCR backend can be used without claiming it is loaded."""
        if not self.use_ocr:
            return False
        eng = (self.ocr_engine or "auto").lower()
        if eng in ("auto", "easyocr") and _probe_easyocr():
            return True
        if eng in ("auto", "tesseract") and _probe_tesseract():
            return True
        return False

    def _ensure_ocr_reader(self) -> None:
        """Lazy-load easyocr only on first OCR request."""
        if self._ocr_init_attempted or not self.use_ocr:
            return
        self._ocr_init_attempted = True
        eng = (self.ocr_engine or "auto").lower()
        if eng not in ("auto", "easyocr"):
            return
        if not _probe_easyocr():
            return
        try:
            import easyocr
            self._ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        except Exception:
            self._ocr_reader = None

    def list_monitors(self) -> List[Dict[str, Any]]:
        if not HAS_MSS:
            return [{"id": 0, "width": 1920, "height": 1080, "left": 0, "top": 0}]
        with _mss_session() as sct:
            mons = []
            for i, mon in enumerate(sct.monitors):
                if i == 0:  # skip the "all" virtual
                    continue
                mons.append({
                    "id": i,
                    "left": mon["left"],
                    "top": mon["top"],
                    "width": mon["width"],
                    "height": mon["height"],
                })
            return mons

    def capture(
        self,
        monitor: int = 1,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> Optional[Image.Image]:
        if not HAS_MSS or not HAS_PIL:
            return None
        with _mss_session() as sct:
            if region:
                mon = {"left": region[0], "top": region[1], "width": region[2] - region[0], "height": region[3] - region[1]}
            else:
                mon = sct.monitors[monitor] if monitor < len(sct.monitors) else sct.monitors[1]
            shot = sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            return img

    def _image_to_base64(self, img: Image.Image, max_side: int = 1280, quality: int = 70) -> str:
        w, h = img.size
        scale = min(1.0, max_side / max(w, h))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def _simple_grounded_elements(self, img: Image.Image, max_elements: int = 40) -> List[Dict]:
        """Local UI grounding via OpenCV structure + OCR fusion (see grounding.py)."""
        try:
            from .grounding import LocalGrounder
            ocr = self._run_ocr(img) if self.use_ocr else []
            grounder = LocalGrounder(max_elements=max_elements)
            els = grounder.ground(img, ocr_items=ocr)
            return [e.as_dict() for e in els]
        except Exception:
            return []


    def _preprocess_for_ocr(self, img: Image.Image) -> Image.Image:
        """Upscale + contrast to improve OCR on UI text."""
        try:
            import numpy as np
            arr = np.array(img.convert("L"))
            # mild upscale for small UI text
            h, w = arr.shape[:2]
            if max(h, w) < 1400:
                arr = np.array(img.convert("L").resize((w * 2, h * 2), Image.Resampling.LANCZOS))
            # simple contrast stretch
            p2, p98 = np.percentile(arr, (2, 98))
            if p98 > p2:
                arr = np.clip((arr - p2) * (255.0 / (p98 - p2)), 0, 255).astype("uint8")
            return Image.fromarray(arr)
        except Exception:
            return img

    def _run_ocr(self, img: Image.Image) -> List[Dict]:
        results = []
        try:
            img = self._preprocess_for_ocr(img)
        except Exception:
            pass
        self._ensure_ocr_reader()
        if self._ocr_reader is not None:
            try:
                ocr_out = self._ocr_reader.readtext(np.array(img))
                for (bbox, text, conf) in ocr_out:
                    if conf < 0.3:
                        continue
                    xs = [p[0] for p in bbox]
                    ys = [p[1] for p in bbox]
                    results.append({
                        "text": text,
                        "bbox": [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))],
                        "confidence": float(conf),
                    })
            except Exception:
                pass
        elif _probe_tesseract():
            try:
                import pytesseract
                data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                n = len(data["text"])
                for i in range(n):
                    conf = float(data["conf"][i])
                    if conf < 40 or not data["text"][i].strip():
                        continue
                    x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                    results.append({
                        "text": data["text"][i],
                        "bbox": [x, y, x + w, y + h],
                        "confidence": conf / 100.0,
                    })
            except Exception:
                pass
        return results

    def _compute_diff(self, img: Image.Image) -> Dict[str, Any]:
        if self._last_frame is None or not HAS_PIL:
            self._last_frame = img.copy()
            return {"similarity": 1.0, "changed": False, "changed_regions": []}
        try:
            # Simple resize for speed
            a = self._last_frame.resize((320, 180)).convert("L")
            b = img.resize((320, 180)).convert("L")
            diff = ImageChops.difference(a, b)
            arr = np.array(diff)
            mean_diff = float(arr.mean())
            similarity = max(0.0, 1.0 - mean_diff / 50.0)
            changed = mean_diff > 5.0
            self._last_frame = img.copy()
            return {
                "similarity": round(similarity, 3),
                "changed": changed,
                "mean_pixel_diff": round(mean_diff, 2),
                "changed_regions": [],  # could add connected components later
            }
        except Exception:
            self._last_frame = img.copy()
            return {"similarity": 0.0, "changed": True, "changed_regions": []}

    def observe(
        self,
        scope: str = "desktop",
        monitor: int = 1,
        region: Optional[Tuple[int, int, int, int]] = None,
        modes: Optional[List[str]] = None,
        include_image: bool = False,
        max_image_side: int = 1280,
        previous_obs: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Main observation entry point.
        modes: subset of ["vision", "ocr", "diff", "a11y"]
        a11y is stubbed here; real backends plug in platform libraries.
        """
        if modes is None:
            modes = ["vision", "ocr", "diff"]

        obs_id = str(uuid.uuid4())[:8]
        ts = time.time()

        img = self.capture(monitor=monitor, region=region)
        if img is None:
            return {
                "obs_id": obs_id,
                "error": "Capture failed. Install mss and pillow: pip install mss pillow",
                "timestamp": ts,
            }

        w, h = img.size
        result: Dict[str, Any] = {
            "obs_id": obs_id,
            "timestamp": ts,
            "scope": scope,
            "resolution": {"width": w, "height": h},
            "monitors": self.list_monitors(),
            "a11y": {
                "available": False,
                "note": "Use read/observe via ExoExecEngine for UIA. PerceptionEngine.observe is pixels/OCR only.",
                "tree": [],
                "focused": None,
            },
            "vision": {
                "elements": [],
                "ocr": [],
                "summary": None,
            },
            "diff": None,
            "screenshot": None,
        }

        if "vision" in modes:
            result["vision"]["elements"] = self._simple_grounded_elements(img)

        if "ocr" in modes and self.use_ocr:
            result["vision"]["ocr"] = self._run_ocr(img)

        if "diff" in modes:
            result["diff"] = self._compute_diff(img)

        if include_image:
            b64 = self._image_to_base64(img, max_side=max_image_side)
            result["screenshot"] = {
                "base64": b64,
                "width": w,
                "height": h,
                "format": "jpeg",
                "note": "Downscaled for token efficiency. Full res available via path if saved.",
            }

        # Optional save for debugging
        # img.save(f"/tmp/aether_obs_{obs_id}.jpg")

        return result


    def set_cache_ttl(self, ttl: float) -> None:
        self._obs_cache_ttl = max(0.0, float(ttl))

    def observe_region(self, x1: int, y1: int, x2: int, y2: int, modes=None,
                       include_image: bool = False, max_image_side: int = 1024) -> dict:
        """Faster observe of a screen rectangle (for verify around a click)."""
        from PIL import Image
        full = self.capture(monitor=1)
        if full is None:
            return self.observe(modes=modes or ["diff"], include_image=False)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(full.width, x2), min(full.height, y2)
        if x2 <= x1 or y2 <= y1:
            return self.observe(modes=modes or ["diff"], include_image=False)
        crop = full.crop((x1, y1, x2, y2))
        # Temporarily run OCR/elements on crop by using observe path on full is heavy;
        # for region we mainly need diff capability — store as image for caller
        import time, uuid
        result = {
            "obs_id": str(uuid.uuid4())[:8],
            "timestamp": time.time(),
            "scope": "region",
            "region": [x1, y1, x2, y2],
            "vision": {"elements": [], "ocr": []},
            "diff": {"available": False},
        }
        if include_image:
            result["vision"]["screenshot_base64"] = self._image_to_base64(crop, max_side=max_image_side)
        if modes and "ocr" in modes and self.use_ocr:
            result["vision"]["ocr"] = self._run_ocr(crop)
        if modes and "vision" in modes:
            result["vision"]["elements"] = self._simple_grounded_elements(crop)
        return result

    def observe_cached(self, **kwargs) -> dict:
        """Reuse last observation if fresher than TTL (continuous perception speedup)."""
        import time
        now = time.time()
        # Only cache non-image or short-ttl requests for speed of verify loops
        want_image = kwargs.get("include_image", True)
        if (not want_image and self._obs_cache is not None
                and (now - self._obs_cache_time) <= self._obs_cache_ttl):
            return self._obs_cache
        obs = self.observe(**kwargs)
        if not want_image:
            self._obs_cache = obs
            self._obs_cache_time = now
        return obs

    def find_text(self, text: str, obs: Optional[Dict] = None) -> List[Dict]:
        """Simple text search over OCR results."""
        if obs is None:
            obs = self.observe(modes=["ocr"], include_image=False)
        matches = []
        for item in obs.get("vision", {}).get("ocr", []):
            if text.lower() in item.get("text", "").lower():
                matches.append(item)
        return matches


# Convenience
def quick_observe(**kwargs) -> Dict[str, Any]:
    eng = PerceptionEngine()
    return eng.observe(**kwargs)
