"""Simulated CO2 laser marking controller (device side).

Behaves like a Ruida-type controller in "foot switch start" mode: a *closing* edge on the
pedal input starts the loaded job if the laser is idle and the enclosure interlock is
closed. The busy output is high for the marking time. Faults can be injected to exercise
the alarms of the machine controller.
"""

from dataclasses import dataclass, field
import random
from typing import Callable, List, Optional


@dataclass
class SimLaserFaults:
    no_response: bool = False     # ignores the pedal completely
    late_s: float = 0.0           # extra marking time (e.g. to provoke a timeout)
    weak_mark: bool = False       # marks, but with poor contrast (vision QA reject)
    stuck_busy: bool = False      # busy never drops


@dataclass
class SimCo2Laser:
    station: int
    marking_time_s: float = 3.0
    start_latency_s: float = 0.05
    jitter_s: float = 0.0
    faults: SimLaserFaults = field(default_factory=SimLaserFaults)
    on_mark_done: Optional[Callable[[int, float, bool], None]] = None  # station, t, weak
    rng: random.Random = field(default_factory=lambda: random.Random(0))

    busy: bool = False
    _pedal: bool = False
    _t_start: Optional[float] = None
    _t_end: Optional[float] = None
    jobs_done: int = 0
    history: List[float] = field(default_factory=list)

    def set_marking_time(self, seconds: float) -> None:
        """The design file on the laser defines the marking time. Tests set it here."""
        self.marking_time_s = max(0.0, seconds)

    def update(self, now: float, pedal_closed: bool, interlock_ok: bool) -> None:
        rising = pedal_closed and not self._pedal
        self._pedal = pedal_closed
        if rising and self._t_start is None and not self.faults.no_response and interlock_ok:
            duration = self.marking_time_s + self.faults.late_s
            if self.jitter_s:
                duration += self.rng.uniform(-self.jitter_s, self.jitter_s)
            self._t_start = now + self.start_latency_s
            self._t_end = self._t_start + max(duration, 0.0)
        if self._t_start is not None:
            if not interlock_ok and self.busy:
                # door opened while marking: the laser controller aborts the job
                self._finish(now, completed=False)
                return
            if now >= self._t_start:
                self.busy = True
            if now >= self._t_end and not self.faults.stuck_busy:
                self._finish(now, completed=True)

    def _finish(self, now: float, completed: bool) -> None:
        self.busy = False
        self._t_start = None
        self._t_end = None
        if completed:
            self.jobs_done += 1
            self.history.append(now)
            if self.on_mark_done is not None:
                self.on_mark_done(self.station, now, self.faults.weak_mark)

    def clear_faults(self) -> None:
        self.faults = SimLaserFaults()
        if self._t_start is not None and self._t_end is not None and self.busy:
            return
        self.busy = False
        self._t_start = None
        self._t_end = None
