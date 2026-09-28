"""Forward-only job planner in belt coordinates (see docs/ARCHITECTURE.md §5).

``F`` is the commanded feed in mm since job start. Label ``k`` has its mark origin at
belt coordinate ``s = k * pitch``. Station ``i`` (``x_i`` mm downstream of station 0)
marks it at ``F = k * pitch + x_i``. The cut after label ``k`` lies at
``s = (k + 1) * pitch - lead``. The knife (``x_c``) cuts it at ``F = s + x_c``.
Events closer than ``MERGE_TOL_MM`` are merged into one *stop*.
"""

from dataclasses import dataclass, field
import math
from typing import List, Optional

from .config import ControlConfig
from .job import CutMode, Job

MERGE_TOL_MM = 0.01


@dataclass
class Fire:
    station: int
    label: int
    delay_s: float


@dataclass
class Cut:
    after_label: int          # -1 = initial trim
    belt_coord_mm: float
    labels_in_piece: int
    trim: bool = False


@dataclass
class Stop:
    feed_mm: float
    fires: List[Fire] = field(default_factory=list)
    cut: Optional[Cut] = None


@dataclass
class Plan:
    stops: List[Stop]
    total_labels: int
    total_cuts: int
    stations: List[tuple]
    ideal_time_s: float
    warnings: List[str] = field(default_factory=list)

    @property
    def final_feed_mm(self) -> float:
        return self.stops[-1].feed_mm if self.stops else 0.0

    @property
    def ideal_cycle_s(self) -> float:
        return self.ideal_time_s / max(1, self.total_labels)


def cut_labels(job: Job) -> List[int]:
    """Indices of the labels after which a cut is made."""
    n = job.quantity
    if job.cut_mode == CutMode.NONE:
        return []
    if job.cut_mode == CutMode.EVERY:
        return list(range(n))
    if job.cut_mode == CutMode.EVERY_N:
        step = max(1, job.cut_every_n)
        return sorted(set([k for k in range(n) if (k + 1) % step == 0] + [n - 1]))
    return [n - 1]


def move_time(distance: float, v: float, a: float) -> float:
    """Trapezoidal / triangular move time."""
    distance = abs(distance)
    if distance <= 0:
        return 0.0
    d_acc = v * v / a
    if distance >= d_acc:
        return distance / v + v / a
    return 2.0 * math.sqrt(distance / a)


def plan_job(job: Job, cfg: ControlConfig, accel_mm_s2: float = 100.0) -> Plan:
    stations = job.active_stations(cfg)
    x_c = cfg.machine.knife_offset_mm
    p = job.pitch_mm
    events = []  # (feed, order, payload)
    for k in range(job.quantity):
        for i, x_i, delay in stations:
            events.append((k * p + x_i, 0, Fire(i, k, delay)))
    last = -1
    warnings = []
    if job.initial_trim_cut and job.cut_mode != CutMode.NONE:
        f = x_c - job.lead_mm
        if f >= 0:
            events.append((f, 1, Cut(-1, -job.lead_mm, 0, trim=True)))
        else:
            warnings.append('initial trim skipped: label start already past the knife')
    for k in cut_labels(job):
        s = (k + 1) * p - job.lead_mm
        events.append((s + x_c, 1, Cut(k, s, k - last)))
        last = k
    events.sort(key=lambda e: (e[0], e[1]))

    stops: List[Stop] = []
    for feed, _, payload in events:
        if not stops or feed - stops[-1].feed_mm > MERGE_TOL_MM:
            stops.append(Stop(feed_mm=round(feed, 6)))
        stop = stops[-1]
        if isinstance(payload, Fire):
            stop.fires.append(payload)
        else:
            if stop.cut is not None:  # two cuts at one stop cannot happen with pitch > 0
                warnings.append(f'duplicate cut at {feed:.3f} mm ignored')
                continue
            stop.cut = payload

    # ideal time (used for OEE performance): moves + settle + laser + cut
    t = 0.0
    prev = 0.0
    knife_nominal = 2 * 0.3 + cfg.knife.dwell_s
    for stop in stops:
        t += move_time(stop.feed_mm - prev, job.feed_speed_mm_s, accel_mm_s2)
        prev = stop.feed_mm
        if stop.fires:
            t += job.settle_s + max(f.delay_s for f in stop.fires) + job.laser_time_s
            t += job.post_mark_delay_s
        if stop.cut is not None:
            t += knife_nominal
    total_cuts = sum(1 for s in stops if s.cut is not None and not s.cut.trim)
    return Plan(stops, job.quantity, total_cuts, stations, t, warnings)
