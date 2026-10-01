"""Synthetic, auto-labelled dataset for the YOLO mark detector (Ultralytics format).

Classes
    0 mark_ok     readable mark with good contrast
    1 mark_weak   mark with low contrast (dirty lens, low power, defocus)
    2 burn_spot   over-burn / scorch spot on the belt (a real CO2 marking defect)
Images with no box are "missing mark" negatives.

Variation: text marks and solid marks (like the Gazebo decals), belt brightness,
illumination gradient, position, scale, small rotation, blur and noise. The labels come
from the drawing masks, so no manual annotation is needed. For the real machine, add
a few hundred labelled camera images (domain gap) - see docs/AI_FEATURES.md.

    python3 -m belt_marking_vision.yolo_dataset /tmp/marks --train 1500 --val 300
"""

import argparse
import os
import random
import string
from typing import List, Tuple

import cv2
import numpy as np

CLASSES = ['mark_ok', 'mark_weak', 'burn_spot']
H, W = 480, 640


def _box(mask: np.ndarray) -> Tuple[float, float, float, float]:
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    return ((x0 + x1) / 2 / W, (y0 + y1) / 2 / H, (x1 - x0 + 1) / W, (y1 - y0 + 1) / H)


def _rand_text(rng: random.Random) -> str:
    n = rng.randint(3, 12)
    return ''.join(rng.choice(string.ascii_uppercase + string.digits + '-') for _ in range(n))


def render_sample(rng: random.Random) -> Tuple[np.ndarray, List[tuple]]:
    """One image + list of (class, cx, cy, w, h) normalised boxes."""
    belt = rng.randint(20, 95)
    img = np.full((H, W), belt, np.float32)
    band = rng.uniform(0.25, 0.45)                     # belt band across the image
    y_top, y_bot = int(H * (0.5 - band / 2)), int(H * (0.5 + band / 2))
    img[:y_top] = rng.randint(120, 230)                # surroundings (bed, guides)
    img[y_bot:] = rng.randint(120, 230)
    boxes = []
    kind = rng.choices(['ok', 'weak', 'none'], [0.55, 0.3, 0.15])[0]
    if kind != 'none':
        mask = np.zeros((H, W), np.uint8)
        cx = int(W / 2 + rng.uniform(-0.25, 0.25) * W)
        cy = int((y_top + y_bot) / 2 + rng.uniform(-0.1, 0.1) * (y_bot - y_top))
        if rng.random() < 0.65:                        # laser-marked text
            text = _rand_text(rng)
            scale = rng.uniform(0.6, 1.8)
            thick = rng.randint(1, 4)
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
            org = (int(np.clip(cx - tw / 2, 5, W - tw - 5)), int(cy + th / 2))
            cv2.putText(mask, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, 255, thick,
                        cv2.LINE_AA)
        else:                                          # filled mark / logo field
            w, h = rng.randint(60, 260), rng.randint(25, max(26, y_bot - y_top - 20))
            cv2.rectangle(mask, (cx - w // 2, cy - h // 2), (cx + w // 2, cy + h // 2), 255,
                          -1)
        mask = mask[:, :]
        if rng.random() < 0.3:                         # small rotation
            m = cv2.getRotationMatrix2D((cx, cy), rng.uniform(-6, 6), 1.0)
            mask = cv2.warpAffine(mask, m, (W, H))
        # same definition as the classic inspector: weak below ~100 grey levels
        contrast = rng.uniform(115, 200) if kind == 'ok' else rng.uniform(20, 95)
        level = min(255, belt + contrast)
        alpha = mask.astype(np.float32) / 255
        img = img * (1 - alpha) + level * alpha
        if mask.any():
            boxes.append((0 if kind == 'ok' else 1,) + _box(mask > 64))
    if rng.random() < 0.25:                            # scorch / burn spot
        spot = np.zeros((H, W), np.uint8)
        sx = rng.randint(60, W - 60)
        sy = rng.randint(y_top + 10, max(y_top + 11, y_bot - 10))
        cv2.ellipse(spot, (sx, sy), (rng.randint(8, 30), rng.randint(6, 22)),
                    rng.uniform(0, 180), 0, 360, 255, -1)
        spot = cv2.GaussianBlur(spot, (0, 0), rng.uniform(2, 5))
        a = spot.astype(np.float32) / 255
        img = img * (1 - a) + rng.uniform(150, 210) * a * 0.8 + img * a * 0.2
        boxes.append((2,) + _box(spot > 80))
    # optics and lighting
    gx = np.linspace(rng.uniform(-25, 0), rng.uniform(0, 25), W)[None, :]
    img = img + gx
    if rng.random() < 0.5:
        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.5, 1.8))
    noise_rng = np.random.default_rng(rng.randint(0, 1 << 30))
    img = img + noise_rng.normal(0, rng.uniform(2, 8), img.shape)
    img = np.clip(img, 0, 255).astype(np.uint8)
    tint = np.array([rng.uniform(0.9, 1.1) for _ in range(3)], np.float32)
    color = np.clip(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) * tint, 0, 255).astype(np.uint8)
    return color, boxes


def write_dataset(root: str, n_train: int, n_val: int, seed: int = 0) -> str:
    rng = random.Random(seed)
    for split, n in (('train', n_train), ('val', n_val)):
        os.makedirs(os.path.join(root, 'images', split), exist_ok=True)
        os.makedirs(os.path.join(root, 'labels', split), exist_ok=True)
        for i in range(n):
            img, boxes = render_sample(rng)
            name = f'{split}_{i:05d}'
            cv2.imwrite(os.path.join(root, 'images', split, name + '.jpg'), img)
            with open(os.path.join(root, 'labels', split, name + '.txt'), 'w') as fh:
                for b in boxes:
                    fh.write(f'{b[0]} {b[1]:.6f} {b[2]:.6f} {b[3]:.6f} {b[4]:.6f}\n')
    yaml_path = os.path.join(root, 'data.yaml')
    with open(yaml_path, 'w') as fh:
        fh.write(f'path: {os.path.abspath(root)}\ntrain: images/train\nval: images/val\n'
                 f'names: {dict(enumerate(CLASSES))}\n')
    return yaml_path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('root')
    ap.add_argument('--train', type=int, default=1500)
    ap.add_argument('--val', type=int, default=300)
    ap.add_argument('--seed', type=int, default=0)
    a = ap.parse_args(argv)
    print('dataset:', write_dataset(a.root, a.train, a.val, a.seed))


if __name__ == '__main__':
    main()
