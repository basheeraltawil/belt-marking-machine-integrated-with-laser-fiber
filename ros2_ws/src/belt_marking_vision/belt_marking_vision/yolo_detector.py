"""YOLO mark detector at runtime: ONNX model + OpenCV DNN (no PyTorch on the Pi).

Pipeline
    letterbox to 640x640 -> RGB, /255, NCHW -> network -> output (1, 4 + C, N)
    rows: cx, cy, w, h (input pixels), then C class scores
    keep score > conf, undo letterbox, non-maximum suppression (IoU > iou)

``YoloInspector`` turns detections into the same ``InspectResult`` as the classic
OpenCV inspector, so the vision node can switch with ``detector:=yolo``:
    burn_spot detected            -> reject 'burn_spot'
    best mark is mark_weak, or the measured contrast in its box < min_contrast
                                  -> reject 'low_contrast'
    no mark                       -> reject 'no_mark'
    mark_ok but far from centre   -> reject 'offset'

Hybrid by design: the network finds and classifies, a measurement decides weak vs ok.
The contrast check (mark pixels vs the belt ring around the box) keeps the verdict tied
to a physical quantity that is calibrated on the machine; a network trained on synthetic
images did not transfer this judgement to the Gazebo camera (docs/AI_FEATURES.md).

Train the model with tools/yolo/train_mark_detector.py.
"""

from dataclasses import dataclass
from typing import List, Optional

import cv2
import numpy as np

from .inspector import InspectResult
from .yolo_dataset import CLASSES


@dataclass
class Detection:
    cls: int
    name: str
    score: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2


def letterbox(img: np.ndarray, size: int = 640):
    """Resize keeping the aspect ratio and pad to size x size (grey 114, like Ultralytics)."""
    h, w = img.shape[:2]
    r = min(size / h, size / w)
    nh, nw = int(round(h * r)), int(round(w * r))
    top, left = (size - nh) // 2, (size - nw) // 2
    out = np.full((size, size, 3), 114, np.uint8)
    out[top:top + nh, left:left + nw] = cv2.resize(img, (nw, nh))
    return out, r, left, top


def decode(output: np.ndarray, r: float, pad_x: float, pad_y: float, conf: float = 0.4,
           iou: float = 0.5) -> List[Detection]:
    """YOLOv8/11 head output (1, 4+C, N) -> detections in original image pixels."""
    pred = output[0].T                                   # (N, 4+C)
    scores = pred[:, 4:]
    cls = scores.argmax(1)
    best = scores[np.arange(len(cls)), cls]
    keep = best > conf
    pred, cls, best = pred[keep], cls[keep], best[keep]
    if not len(pred):
        return []
    cx, cy, w, h = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
    x0 = (cx - w / 2 - pad_x) / r
    y0 = (cy - h / 2 - pad_y) / r
    boxes = np.stack([x0, y0, w / r, h / r], 1)
    idx = cv2.dnn.NMSBoxesBatched(boxes.tolist(), best.tolist(), cls.tolist(), conf, iou)
    out = []
    for i in np.array(idx).reshape(-1):
        bx, by, bw, bh = boxes[i]
        out.append(Detection(int(cls[i]), CLASSES[int(cls[i])], float(best[i]),
                             float(bx), float(by), float(bx + bw), float(by + bh)))
    return sorted(out, key=lambda d: -d.score)


class YoloDetector:

    def __init__(self, onnx_path: str, size: int = 640, conf: float = 0.4, iou: float = 0.5):
        self.net = cv2.dnn.readNetFromONNX(onnx_path)
        self.size, self.conf, self.iou = size, conf, iou

    def detect(self, image: np.ndarray) -> List[Detection]:
        bgr = image if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        boxed, r, px, py = letterbox(bgr, self.size)
        blob = cv2.dnn.blobFromImage(boxed, 1 / 255.0, swapRB=True)
        self.net.setInput(blob)
        return decode(self.net.forward(), r, px, py, self.conf, self.iou)


def box_contrast(image: np.ndarray, d: Detection, ring: int = 12) -> float:
    """Brightness of the marked pixels (90th percentile in the box) minus the belt level
    (median of a ring around the box), in grey levels."""
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    x0, y0 = max(0, int(d.x0)), max(0, int(d.y0))
    x1, y1 = min(w, int(d.x1) + 1), min(h, int(d.y1) + 1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inside = gray[y0:y1, x0:x1]
    ox0, oy0 = max(0, x0 - ring), max(0, y0 - ring)
    ox1, oy1 = min(w, x1 + ring), min(h, y1 + ring)
    outer = gray[oy0:oy1, ox0:ox1].astype(np.float32).copy()
    outer[y0 - oy0:y1 - oy0, x0 - ox0:x1 - ox0] = np.nan
    belt = float(np.nanmedian(outer)) if np.isfinite(outer).any() else float(np.median(gray))
    return float(np.percentile(inside, 90)) - belt


class YoloInspector:
    """Same interface as MarkInspector.inspect(), backed by the YOLO detector."""

    def __init__(self, detector: YoloDetector, mm_per_px: float = 0.1,
                 max_offset_mm: float = 2.0, min_contrast: Optional[float] = 115.0):
        self.det = detector
        self.mm_per_px = mm_per_px
        self.max_offset_mm = max_offset_mm
        self.min_contrast = min_contrast      # None = trust the network's mark_weak class
        self.ocr = None

    def inspect(self, image: np.ndarray, expected_text: str = '',
                expected_center_px=None) -> InspectResult:
        dets = self.det.detect(image)
        details = {'detections': [(d.name, round(d.score, 2)) for d in dets]}
        if any(d.name == 'burn_spot' for d in dets):
            return InspectResult(False, 0.0, 'burn_spot', details=details)
        marks = [d for d in dets if d.name in ('mark_ok', 'mark_weak')]
        if not marks:
            return InspectResult(False, 0.0, 'no_mark', details=details)
        best = marks[0]
        exp = expected_center_px if expected_center_px is not None else image.shape[1] / 2
        offset = (best.cx - exp) * self.mm_per_px
        contrast = box_contrast(image, best)
        details['contrast'] = round(contrast, 1)
        too_dim = self.min_contrast is not None and contrast < self.min_contrast
        weak = best.name == 'mark_weak' or too_dim
        if weak:
            return InspectResult(False, round(1 - best.score, 3), 'low_contrast',
                                 contrast=round(contrast, 1), offset_mm=round(offset, 2),
                                 details=details)
        if abs(offset) > self.max_offset_mm:
            return InspectResult(False, best.score, 'offset', offset_mm=round(offset, 2),
                                 details=details)
        return InspectResult(True, round(best.score, 3), '', contrast=round(contrast, 1),
                             offset_mm=round(offset, 2), details=details)
