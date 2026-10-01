"""OEE of a simulated shift and the sensitivity of the drift detector.

OEE (core/oee.py)
    availability A = run_time / (run_time + down_time)
    performance  P = labels * ideal_cycle / run_time
    quality      Q = good_labels / labels
    OEE = A * P * Q

Drift detector (belt_marking_vision/anomaly.py), robust statistics
    baseline median m0 and MAD of the first N samples, sigma ~ 1.4826 * MAD
    z = (median(last W) - m0) / (1.253 * sigma / sqrt(W))
    warning if |z| > 4 and |relative change| > 15 %

Run:  python3 analysis/oee_and_drift.py      (~15 s)
"""

import random

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

from _paths import savefig  # noqa: E402
from belt_marking_control.scenarios import run_scenario  # noqa: E402
from belt_marking_vision.anomaly import DriftDetector  # noqa: E402


def cycles_to_detect(drift_pct: float, noise_pct: float = 3.0, seed: int = 0) -> int:
    """Number of cycles after a sudden slowdown until the detector warns (-1 = never)."""
    rng = random.Random(seed)
    base_t = 0.30
    det = DriftDetector(baseline_n=100, window=30)
    samples = [base_t * (1 + rng.gauss(0, noise_pct / 100))
               for _ in range(300)]                               # long normal run
    for n in range(1, 400):
        samples.append(base_t * (1 + drift_pct / 100) * (1 + rng.gauss(0, noise_pct / 100)))
        res = det.evaluate('knife', samples)
        if res is not None and res.drift:
            return n
    return -1


def main():
    r = run_scenario(12, hours=2.0)
    oee = r.metrics['oee']
    print('2 h simulated shift with 3 faults (scenario 12):')
    for k in ('availability', 'performance', 'quality', 'oee'):
        print(f'  {k:12s} {oee[k] * 100:6.2f} %')
    print(f'  run {oee["run_s"]:.0f} s, down {oee["down_s"]:.0f} s, labels {oee["labels"]}')

    drifts = [5, 10, 15, 20, 30, 50]
    delays = [cycles_to_detect(d) for d in drifts]
    print('\ndrift of the knife time -> cycles until W-702 (3 % noise):')
    for d, n in zip(drifts, delays):
        print(f'  +{d:2d} %  ->  {"not flagged (below 15 % rule)" if n < 0 else f"{n} cycles"}')
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar([f'+{d}%' for d in drifts], [max(n, 0) for n in delays])
    ax.set_ylabel('cycles until warning')
    ax.set_title('Drift detector: delay vs slowdown')
    print('figure:', savefig(fig, 'drift_detection_delay.png'))


if __name__ == '__main__':
    main()
