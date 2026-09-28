"""Mark inspection with OpenCV (+ optional OCR). No ROS dependency.

Checks, in order:
  1. presence   - a mark blob exists in the expected window
  2. contrast   - mark vs belt brightness difference (dirty lens / low power -> weak)
  3. position   - centroid offset along the belt vs the expected position [mm]
  4. text       - optional OCR (Tesseract via pytesseract, or any callable) vs expected text

Image convention: belt runs horizontally in the image (x = belt direction). The
camera looks down; the vision node rotates Gazebo/real frames accordingly.
"""

from dataclasses import dataclass, field
import difflib
from typing import Callable, Optional

import cv2
import numpy as np


@dataclass
class InspectConfig:
    mm_per_px: float = 0.1            # camera scale (calibrate: known label length / px)
    min_area_ratio: float = 0.003     # mark pixels / ROI pixels
    detect_level: float = 25.0        # grey levels above the belt that count as 'marked'
    min_contrast: float = 115.0       # grey levels between mark and belt (calibrate)
    max_offset_mm: float = 2.0
    min_text_ratio: float = 0.7       # difflib ratio for OCR match
    light_marks: bool = True          # CO2 on dark belts: marks lighter than the belt
    roi_across: tuple = (0.0, 1.0)    # image rows (fractions) covering the belt width


@dataclass
class InspectResult:
    ok: bool
    score: float
    reason: str = ''
    contrast: float = 0.0
    area_ratio: float = 0.0
    offset_mm: float = 0.0
    text: str = ''
    details: dict = field(default_factory=dict)


def _tesseract() -> Optional[Callable[[np.ndarray], str]]:
    try:
        import pytesseract  # noqa: PLC0415 - optional
        pytesseract.get_tesseract_version()
    except Exception:  # noqa: BLE001 - not installed
        return None
    return lambda img: pytesseract.image_to_string(img, config='--psm 7').strip()


class MarkInspector:

    def __init__(self, cfg: Optional[InspectConfig] = None,
                 ocr: Optional[Callable[[np.ndarray], str]] = None, use_tesseract: bool = True):
        self.cfg = cfg or InspectConfig()
        self.ocr = ocr or (_tesseract() if use_tesseract else None)

    def inspect(self, image: np.ndarray, expected_text: str = '',
                expected_center_px: Optional[float] = None) -> InspectResult:
        c = self.cfg
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        r0, r1 = (int(gray.shape[0] * f) for f in c.roi_across)
        gray = cv2.GaussianBlur(gray[r0:max(r1, r0 + 1)], (3, 3), 0)
        belt_level = float(np.median(gray))
        # adaptive to the belt: pixels clearly brighter (or darker) than the belt
        diff = (gray.astype(np.int16) - belt_level) if c.light_marks else \
            (belt_level - gray.astype(np.int16))
        mask = (diff > c.detect_level).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        area_ratio = float(np.count_nonzero(mask)) / mask.size
        if area_ratio < c.min_area_ratio:
            return InspectResult(False, 0.0, 'no_mark', 0.0, area_ratio)
        mark_level = float(np.median(gray[mask > 0]))
        contrast = abs(mark_level - belt_level)
        # centre of the marked area's bounding box (the ink centroid of text depends on
        # the characters, e.g. '1' vs '8', and would fake a position error)
        xs = np.nonzero(mask.any(axis=0))[0]
        cx = (xs[0] + xs[-1]) / 2.0
        exp = expected_center_px if expected_center_px is not None else gray.shape[1] / 2
        offset_mm = (cx - exp) * c.mm_per_px
        text = ''
        text_ratio = 1.0
        if expected_text and self.ocr is not None:
            ys, xs = np.nonzero(mask)
            crop = gray[max(0, ys.min() - 5):ys.max() + 5, max(0, xs.min() - 5):xs.max() + 5]
            if c.light_marks:
                crop = 255 - crop                     # OCR prefers dark text on light
            text = self.ocr(crop)
            text_ratio = difflib.SequenceMatcher(None, _norm(text), _norm(expected_text)).ratio()
        score = min(1.0, contrast / (2 * c.min_contrast)) * 0.5 + \
            max(0.0, 1.0 - abs(offset_mm) / (2 * c.max_offset_mm)) * 0.3 + text_ratio * 0.2
        reason = ''
        if contrast < c.min_contrast:
            reason = 'low_contrast'
        elif abs(offset_mm) > c.max_offset_mm:
            reason = 'offset'
        elif expected_text and self.ocr is not None and text_ratio < c.min_text_ratio:
            reason = 'text_mismatch'
        return InspectResult(reason == '', round(score, 3), reason, round(contrast, 1),
                             round(area_ratio, 4), round(offset_mm, 2), text,
                             {'text_ratio': round(text_ratio, 2), 'belt_level': belt_level})


def _norm(s: str) -> str:
    return ''.join(ch for ch in s.upper() if ch.isalnum())


def render_label(text: str = 'BELT-2026', weak: bool = False, missing: bool = False,
                 offset_px: int = 0, size=(480, 640), seed: int = 0) -> np.ndarray:
    """Synthetic camera image of a laser-marked label on a dark belt (tests, sim w/o Gazebo)."""
    rng = np.random.default_rng(seed)
    h, w = size
    img = np.full((h, w, 3), 38, np.uint8)                    # dark belt
    img[int(h * 0.25):int(h * 0.75), :, :] = 30                 # label area
    if not missing:
        level = 90 if weak else 215
        (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 3)
        scale = min(2.2, 0.6 * w / max(tw, 1))          # text fills ~60 % of the label
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 3)
        org = (int((w - tw) / 2) + offset_px, int((h + th) / 2))
        cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (level,) * 3, 3,
                    cv2.LINE_AA)
    noise = rng.normal(0, 4, img.shape)
    return np.clip(img + noise, 0, 255).astype(np.uint8)
