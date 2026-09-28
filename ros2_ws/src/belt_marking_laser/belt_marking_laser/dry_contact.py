"""Real laser integration: relay contact across the foot pedal + optional busy input.

Wiring (see docs/ELECTRICAL.md §5): a relay contact that is dry and isolated is wired
in parallel with the pedal contact. We never inject voltage into the laser controller.
The controller's "work done / busy" output, if it has one, reaches a Mega input through
an optocoupler.
"""

from typing import Optional, Protocol

from .interface import DoneMode, LaserConfig, LaserInterface, LaserPoll, LaserResult


class LaserIoPort(Protocol):
    """Minimal I/O needed by the laser. Implemented by the hardware abstraction."""

    def pulse_output(self, name: str, duration_ms: int) -> None: ...

    def laser_busy(self, station: int) -> bool: ...


class DryContactLaser(LaserInterface):
    """Pedal-relay laser with done detection by signal or by time."""

    def __init__(self, io: LaserIoPort, station: int, config: LaserConfig):
        self.io = io
        self.station = station
        self.cfg = config
        self._t_trigger: Optional[float] = None
        self._t_busy: Optional[float] = None
        self._marking_time = 0.0
        self._result: Optional[LaserResult] = None

    @property
    def output_name(self) -> str:
        return f'laser_{self.station}'

    def trigger(self, now: float, marking_time_s: float) -> None:
        self.io.pulse_output(self.output_name, int(self.cfg.pulse_ms))
        self._t_trigger = now
        self._t_busy = None
        self._marking_time = marking_time_s
        self._result = None

    def is_busy(self, now: float) -> bool:
        if self.cfg.done_mode == DoneMode.SIGNAL:
            return self.io.laser_busy(self.station)
        return self.poll_done(now).status == LaserPoll.PENDING

    def reset(self) -> None:
        self._t_trigger = None
        self._t_busy = None
        self._result = None

    def poll_done(self, now: float) -> LaserResult:
        if self._result is not None:
            return self._result
        if self._t_trigger is None:
            return LaserResult(LaserPoll.IDLE)
        elapsed = now - self._t_trigger
        pulse_s = self.cfg.pulse_ms / 1000.0
        if self.cfg.done_mode == DoneMode.TIMED:
            if elapsed >= pulse_s + self._marking_time:
                self._result = LaserResult(LaserPoll.DONE, self._marking_time)
                return self._result
            return LaserResult(LaserPoll.PENDING)

        busy = self.io.laser_busy(self.station)
        if self._t_busy is None:
            if busy:
                self._t_busy = now
            elif elapsed > self.cfg.ack_timeout_s:
                self._result = LaserResult(LaserPoll.NO_ACK)
                return self._result
            return LaserResult(LaserPoll.PENDING)
        if not busy:
            self._result = LaserResult(LaserPoll.DONE, now - self._t_busy)
            return self._result
        if elapsed > self.cfg.timeout_for(self._marking_time):
            self._result = LaserResult(LaserPoll.TIMEOUT, now - self._t_busy)
            return self._result
        return LaserResult(LaserPoll.PENDING)
