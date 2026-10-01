"""YOLO post-processing and dataset tests (no trained model needed).
Set BELT_YOLO_MODEL=/path/best.onnx to also run the model on synthetic labels."""

import os
import random

from belt_marking_vision.yolo_dataset import CLASSES, render_sample, write_dataset
from belt_marking_vision.yolo_detector import decode, Detection, letterbox, YoloInspector
import numpy as np
import pytest


def test_letterbox_geometry():
    img = np.zeros((480, 640, 3), np.uint8)
    out, r, px, py = letterbox(img, 640)
    assert out.shape == (640, 640, 3) and r == 1.0 and (px, py) == (0, 80)


def test_decode_undoes_letterbox_and_suppresses_duplicates():
    # two overlapping 'mark_ok' predictions + one 'burn_spot', in letterboxed pixels
    n = 8400
    out = np.zeros((1, 4 + len(CLASSES), n), np.float32)
    preds = [(320, 320, 100, 40, 0, 0.9), (322, 321, 100, 40, 0, 0.8),
             (100, 300, 20, 20, 2, 0.7)]
    for i, (cx, cy, w, h, cls, score) in enumerate(preds):
        out[0, :4, i] = (cx, cy, w, h)
        out[0, 4 + cls, i] = score
    dets = decode(out, r=1.0, pad_x=0, pad_y=80)
    assert [d.name for d in dets] == ['mark_ok', 'burn_spot']
    assert dets[0].x0 == pytest.approx(270) and dets[0].y0 == pytest.approx(220)


class FakeDetector:

    def __init__(self, dets):
        self.dets = dets

    def detect(self, image):
        return self.dets


@pytest.mark.parametrize('dets,reason', [
    ([Detection(0, 'mark_ok', .9, 270, 220, 370, 260)], ''),
    ([Detection(1, 'mark_weak', .8, 270, 220, 370, 260)], 'low_contrast'),
    ([], 'no_mark'),
    ([Detection(0, 'mark_ok', .9, 270, 220, 370, 260),
      Detection(2, 'burn_spot', .6, 90, 290, 110, 310)], 'burn_spot'),
])
def test_yolo_inspector_verdicts(dets, reason):
    img = np.full((480, 640, 3), 40, np.uint8)
    img[230:250, 280:360] = 220                            # a bright mark inside the box
    r = YoloInspector(FakeDetector(dets)).inspect(img)
    assert r.reason == reason and r.ok == (reason == '')


def test_hybrid_contrast_rejects_a_dim_mark_called_ok():
    img = np.full((480, 640, 3), 40, np.uint8)
    img[230:250, 280:360] = 120                            # only 80 grey levels above belt
    det = [Detection(0, 'mark_ok', .95, 270, 220, 370, 260)]
    assert YoloInspector(FakeDetector(det)).inspect(img).reason == 'low_contrast'
    assert YoloInspector(FakeDetector(det), min_contrast=None).inspect(img).ok


def test_dataset_labels_are_valid(tmp_path):
    write_dataset(str(tmp_path), 20, 5, seed=1)
    for f in os.listdir(tmp_path / 'labels' / 'train'):
        for line in open(tmp_path / 'labels' / 'train' / f):
            c, *box = line.split()
            assert int(c) in range(len(CLASSES))
            assert all(0.0 <= float(v) <= 1.0 for v in box)
    assert (tmp_path / 'data.yaml').exists()


@pytest.mark.skipif(not os.environ.get('BELT_YOLO_MODEL'), reason='no trained model')
def test_trained_model_on_synthetic_labels():
    from belt_marking_vision.yolo_detector import YoloDetector
    ins = YoloInspector(YoloDetector(os.environ['BELT_YOLO_MODEL']), max_offset_mm=1e9,
                        min_contrast=None)
    rng = random.Random(777)
    ok = 0
    for _ in range(50):
        img, boxes = render_sample(rng)
        expected = 'burn_spot' if any(b[0] == 2 for b in boxes) else \
            '' if any(b[0] == 0 for b in boxes) else \
            'low_contrast' if any(b[0] == 1 for b in boxes) else 'no_mark'
        ok += ins.inspect(img).reason == expected
    assert ok >= 45
