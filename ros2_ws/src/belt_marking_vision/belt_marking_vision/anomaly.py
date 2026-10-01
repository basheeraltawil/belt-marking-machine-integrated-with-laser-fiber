"""Cycle-time drift detection (predictive maintenance). No ROS dependency.

Input: per-component cycle times logged by the controller (``cycle_times`` table):
``knife_extend``, ``knife_retract``, ``laser``, ``feed``.

Method (robust and explainable, works from a few hundred samples):
  * baseline = median and MAD of the first ``baseline_n`` samples (after commissioning,
    or after maintenance via ``reset``);
  * the rolling median of the last ``window`` samples is compared to the baseline as a
    robust z-score. A warning needs both z > ``z_threshold`` and a relative change >
    ``min_rel_change`` (to ignore statistically significant but irrelevant shifts).
``MultivariateDetector`` watches several signals together and names the drifting one.
"""

from dataclasses import dataclass
import statistics
from typing import Dict, List, Optional, Sequence


@dataclass
class DriftResult:
    """Outcome of a drift check for one signal."""
    kind: str
    drift: bool
    z: float
    baseline: float
    current: float
    rel_change: float

    def message(self) -> str:
        direction = 'slower' if self.current > self.baseline else 'faster'
        return (f'{self.kind}: {self.current * 1000:.0f} ms vs baseline '
                f'{self.baseline * 1000:.0f} ms ({self.rel_change * 100:+.0f} %, {direction}, '
                f'z={self.z:.1f})')


@dataclass
class DriftDetector:
    """Robust median/MAD drift detector for one cycle-time signal."""
    baseline_n: int = 100
    window: int = 30
    z_threshold: float = 4.0
    min_rel_change: float = 0.15

    def evaluate(self, kind: str, samples: Sequence[float]) -> Optional[DriftResult]:
        """Check the latest samples against the baseline (None = not enough data)."""
        if len(samples) < self.baseline_n + self.window:
            return None
        base = list(samples[:self.baseline_n])
        cur = list(samples[-self.window:])
        med = statistics.median(base)
        mad = statistics.median(abs(x - med) for x in base) * 1.4826 or 1e-6
        cur_med = statistics.median(cur)
        # standard error of a median of `window` samples ~ 1.253 * sigma / sqrt(n)
        z = (cur_med - med) / (1.253 * mad / self.window ** 0.5)
        rel = (cur_med - med) / med if med else 0.0
        drift = abs(z) > self.z_threshold and abs(rel) > self.min_rel_change
        return DriftResult(kind, drift, round(z, 2), med, cur_med, rel)


class MultivariateDetector:
    """Windowed robust z-scores over several signals at once (e.g. knife_extend,
    knife_retract, laser, feed). Flags a window when any signal's window median leaves its
    baseline band, and names the signal.

    An Isolation Forest was evaluated for this and rejected: points outside the training
    range score like the most extreme training points, so large drifts were flagged in
    only ~10 % of the windows (see docs/AI_FEATURES.md).
    """

    def __init__(self, window: int = 10, z_threshold: float = 6.0):
        self.window = window
        self.z_threshold = z_threshold
        self.baseline: Dict[str, tuple] = {}

    def _windows(self, values: Sequence[float]) -> List[float]:
        w = self.window
        return [statistics.median(values[i:i + w]) for i in range(0, len(values) - w + 1, w)]

    def fit(self, series: Dict[str, Sequence[float]]) -> 'MultivariateDetector':
        for name, values in series.items():
            meds = self._windows(values)
            center = statistics.median(meds)
            mad = statistics.median(abs(m - center) for m in meds) * 1.4826 or 1e-9
            self.baseline[name] = (center, mad)
        return self

    def evaluate(self, series: Dict[str, Sequence[float]]) -> List[Dict[str, float]]:
        """Per window: {signal: z}. Only signals beyond the threshold are listed."""
        per_signal = {n: self._windows(v) for n, v in series.items() if n in self.baseline}
        n_win = min(len(v) for v in per_signal.values()) if per_signal else 0
        out = []
        for i in range(n_win):
            flags = {}
            for name, meds in per_signal.items():
                center, mad = self.baseline[name]
                z = (meds[i] - center) / mad
                if abs(z) > self.z_threshold:
                    flags[name] = round(z, 1)
            out.append(flags)
        return out

    def anomalous_fraction(self, series: Dict[str, Sequence[float]]) -> float:
        res = self.evaluate(series)
        return sum(1 for r in res if r) / len(res) if res else 0.0
