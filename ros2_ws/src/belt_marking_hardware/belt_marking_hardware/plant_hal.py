"""In-process HardwareInterface backed by :class:`FakePlant` (tests, accelerated sims)."""

from typing import List

from .fake_plant import FakePlant
from .hal import HardwareInterface, IoSnapshot, MotionIdCounter


class PlantHal(HardwareInterface):
    """HardwareInterface that calls the plant model directly (no ROS)."""

    def __init__(self, plant: FakePlant):
        self.plant = plant
        self._ids = MotionIdCounter()
        self._errors: List[str] = []
        self._last = plant.snapshot()

    def _check(self, result):
        ok, why = result
        if not ok:
            self._errors.append(why)
        return ok

    def snapshot(self) -> IoSnapshot:
        if not self.plant.link_up:
            # like a dead USB link: the Pi only has the last received status
            stale = self._last
            stale.link_ok = False
            return stale
        self._last = self.plant.snapshot()
        return self._last

    def _up(self) -> bool:
        return self.plant.link_up

    def move_relative(self, distance_mm, speed_mm_s=0.0, accel_mm_s2=0.0) -> int:
        mid = self._ids.next_id()
        if self._up():
            self._check(self.plant.cmd_move_rel(distance_mm, speed_mm_s, accel_mm_s2, mid))
        return mid

    def jog(self, direction, speed_mm_s, duration_ms) -> int:
        mid = self._ids.next_id()
        if self._up():
            self._check(self.plant.cmd_jog(direction, speed_mm_s, duration_ms, mid))
        return mid

    def stop(self, quick=False):
        if self._up():
            self._check(self.plant.cmd_stop(quick))

    def set_output(self, name, state):
        if self._up():
            self._check(self.plant.cmd_set_output(name, state))

    def pulse_output(self, name, duration_ms):
        if self._up():
            self._check(self.plant.cmd_pulse_output(name, int(duration_ms)))

    def enable_drive(self, on):
        if self._up():
            self._check(self.plant.cmd_enable(on))

    def zero_position(self):
        if self._up():
            self._check(self.plant.cmd_zero())

    def reset_faults(self):
        if self._up():
            self._check(self.plant.cmd_reset_faults())

    def heartbeat(self, now):
        self.plant.heartbeat()

    def pop_errors(self):
        errors, self._errors = self._errors, []
        return errors
