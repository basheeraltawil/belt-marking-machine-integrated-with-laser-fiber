"""Laser abstraction used by the machine controller.

The laser machine keeps its own controller, software and design files. This module only
models what the belt marking machine can do with it: *trigger* a job (like the foot
pedal) and find out when the job is *done*. Any laser type (CO2, fiber, UV) that offers a
start input and optionally a busy/done output fits behind :class:`LaserInterface`.

All methods take ``now`` (seconds, monotonic) so the same code runs in real time and in
accelerated simulation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import enum
import time


class LaserPoll(enum.Enum):
    IDLE = 'idle'            # nothing triggered
    PENDING = 'pending'      # triggered, waiting for the laser to start / finish
    DONE = 'done'            # job finished
    NO_ACK = 'no_ack'        # signal mode: busy never went high after the trigger
    TIMEOUT = 'timeout'      # still busy (or no done) after the timeout


class DoneMode(str, enum.Enum):
    SIGNAL = 'signal'        # use the controller's busy / done output
    TIMED = 'timed'          # wait a configured marking time


@dataclass
class LaserConfig:
    pulse_ms: int = 200                  # pedal contact closure  # TODO: verify on hardware
    done_mode: DoneMode = DoneMode.SIGNAL
    ack_timeout_s: float = 1.0           # busy must rise within this time (signal mode)
    timeout_factor: float = 2.0          # timeout = marking_time * factor + margin
    timeout_margin_s: float = 2.0

    def timeout_for(self, marking_time_s: float) -> float:
        return marking_time_s * self.timeout_factor + self.timeout_margin_s


@dataclass
class LaserResult:
    status: LaserPoll
    busy_time_s: float = 0.0


class LaserInterface(ABC):
    """One laser marking machine (station)."""

    station: int = 0

    @abstractmethod
    def trigger(self, now: float, marking_time_s: float) -> None:
        """Start one marking job. ``marking_time_s`` is used in timed mode / for timeouts."""

    @abstractmethod
    def is_busy(self, now: float) -> bool:
        """True while the laser is (believed to be) marking."""

    @abstractmethod
    def poll_done(self, now: float) -> LaserResult:
        """Non-blocking state of the last trigger."""

    def reset(self) -> None:  # noqa: B027 - optional hook, default no-op
        """Forget the last trigger (e.g. after recovery)."""

    def wait_done(self, timeout: float, clock=time.monotonic, sleep=time.sleep,
                  period: float = 0.01) -> LaserResult:
        """Blocking helper for scripts and tests. Never used inside the control loop."""
        start = clock()
        while True:
            res = self.poll_done(clock())
            if res.status not in (LaserPoll.PENDING,):
                return res
            if clock() - start > timeout:
                return LaserResult(LaserPoll.TIMEOUT)
            sleep(period)
