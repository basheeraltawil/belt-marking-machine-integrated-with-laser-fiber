#!/usr/bin/env python3
"""Train, export and evaluate the YOLO mark detector (needs: pip install ultralytics).

    python3 tools/yolo/train_mark_detector.py --out runs/marks          # ~5 min on a GPU
    python3 tools/yolo/train_mark_detector.py --evaluate model.onnx     # evaluation only

Steps
  1. synthetic dataset (belt_marking_vision.yolo_dataset), auto-labelled
  2. fine-tune YOLO11n (Ultralytics), 30 epochs, 640 px
  3. export ONNX (runs with OpenCV DNN on the Raspberry Pi, no PyTorch)
  4. compare with the classic OpenCV inspector on a fresh held-out set
     verdict classes: ok / weak / missing / burn_spot  (position is not scored)
"""

import argparse
import os
import random
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'ros2_ws', 'src', 'belt_marking_vision'))

from belt_marking_vision.inspector import InspectConfig, MarkInspector  # noqa: E402
from belt_marking_vision.yolo_dataset import render_sample, write_dataset  # noqa: E402
from belt_marking_vision.yolo_detector import YoloDetector, YoloInspector  # noqa: E402

REASON_TO_VERDICT = {'': 'ok', 'low_contrast': 'weak', 'no_mark': 'missing',
                     'burn_spot': 'burn_spot', 'offset': 'ok', 'text_mismatch': 'ok'}


def truth(boxes):
    classes = {b[0] for b in boxes}
    if 2 in classes:
        return 'burn_spot'
    if 0 in classes:
        return 'ok'
    if 1 in classes:
        return 'weak'
    return 'missing'


def evaluate(onnx_path, n=500, seed=12345):
    rng = random.Random(seed)
    classic = MarkInspector(InspectConfig(roi_across=(0.35, 0.65), max_offset_mm=1e9),
                            use_tesseract=False)
    yolo = YoloInspector(YoloDetector(onnx_path), max_offset_mm=1e9)
    labels = ['ok', 'weak', 'missing', 'burn_spot']
    conf = {name: {t: {p: 0 for p in labels} for t in labels} for name in ('classic', 'yolo')}
    for _ in range(n):
        img, boxes = render_sample(rng)
        t = truth(boxes)
        for name, ins in (('classic', classic), ('yolo', yolo)):
            conf[name][t][REASON_TO_VERDICT[ins.inspect(img).reason]] += 1
    for name in ('classic', 'yolo'):
        correct = sum(conf[name][t][t] for t in labels)
        print(f'\n{name}: accuracy {correct / n * 100:.1f} % on {n} held-out images')
        head = 'truth/pred'
        print(f'{head:>12} ' + ' '.join(f'{p:>9}' for p in labels))
        for t in labels:
            print(f'{t:>12} ' + ' '.join(f'{conf[name][t][p]:>9}' for p in labels))
    return conf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='runs/marks')
    ap.add_argument('--epochs', type=int, default=30)
    ap.add_argument('--evaluate', help='only evaluate this ONNX model')
    a = ap.parse_args()
    if a.evaluate:
        evaluate(a.evaluate)
        return
    from ultralytics import YOLO  # noqa: PLC0415 - training-only dependency
    data = write_dataset(os.path.join(a.out, 'dataset'), 2000, 400)
    model = YOLO('yolo11n.pt')
    model.train(data=data, epochs=a.epochs, imgsz=640, batch=32, project=a.out, name='train',
                exist_ok=True, plots=False)
    onnx = model.export(format='onnx', imgsz=640, opset=12, simplify=True)
    print('ONNX model:', onnx)
    evaluate(onnx)


if __name__ == '__main__':
    main()
