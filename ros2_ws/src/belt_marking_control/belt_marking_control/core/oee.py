"""Counters and OEE (availability x performance x quality)."""

from dataclasses import asdict, dataclass

RUN_STATES = {'EXECUTE'}
DOWN_STATES = {'HOLDING', 'HELD', 'UNHOLDING', 'STOPPING', 'ABORTING', 'ABORTED', 'CLEARING'}


@dataclass
class Counters:
    """Lifetime counters (persisted in the DB)."""

    total_marks: int = 0
    total_pieces: int = 0
    knife_cycles: int = 0
    blade_cycles: int = 0
    laser_triggers: int = 0
    belt_mm: float = 0.0
    uptime_s: float = 0.0

    def as_dict(self):
        return asdict(self)


@dataclass
class OeeTracker:
    """OEE over a window (e.g. a shift). Only counts time while a job is loaded.

    * availability = run time / (run time + unplanned down time)
    * performance  = (labels produced x ideal cycle time) / run time
    * quality      = good labels / labels produced
    """

    run_s: float = 0.0
    down_s: float = 0.0
    labels: int = 0
    rejects: int = 0
    ideal_s: float = 0.0

    def add_time(self, state_name: str, dt: float, job_active: bool) -> None:
        if not job_active:
            return
        if state_name in RUN_STATES:
            self.run_s += dt
        elif state_name in DOWN_STATES:
            self.down_s += dt

    def add_labels(self, count: int, ideal_cycle_s: float) -> None:
        self.labels += count
        self.ideal_s += count * ideal_cycle_s

    def add_rejects(self, count: int) -> None:
        self.rejects += count

    @property
    def availability(self) -> float:
        total = self.run_s + self.down_s
        return self.run_s / total if total > 0 else 1.0

    @property
    def performance(self) -> float:
        return min(1.0, self.ideal_s / self.run_s) if self.run_s > 0 else 1.0

    @property
    def quality(self) -> float:
        return (self.labels - self.rejects) / self.labels if self.labels > 0 else 1.0

    @property
    def oee(self) -> float:
        return self.availability * self.performance * self.quality

    def report(self) -> dict:
        return {
            'run_s': round(self.run_s, 1), 'down_s': round(self.down_s, 1),
            'labels': self.labels, 'rejects': self.rejects,
            'availability': round(self.availability, 4),
            'performance': round(self.performance, 4),
            'quality': round(self.quality, 4), 'oee': round(self.oee, 4),
        }
