"""Hardware abstraction shared by the real serial bridge and the simulation.

The machine controller only sees :class:`HardwareInterface`. Three implementations exist:

* :class:`belt_marking_hardware.plant_hal.PlantHal`: direct, in-process plant model (unit
  and scenario tests, accelerated time).
* :class:`belt_marking_hardware.ros_hal.RosHardwareClient`: talks over ``hw/command`` +
  ``hw/io_status`` to *either* ``serial_bridge_node`` (real) or ``sim_hardware_node``.

Commands are fire-and-forget. Asynchronous rejections are collected and returned by
:meth:`HardwareInterface.pop_errors`.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import math
from typing import List, Tuple

MAX_STATIONS = 4

OUTPUT_NAMES = (
    'knife_extend', 'knife_retract', 'zair', 'dc_motor',
    'laser_0', 'laser_1', 'laser_2', 'laser_3',
    'light_red', 'light_yellow', 'light_green', 'buzzer',
)
# bit index of each output in the serial protocol / plant bitmask
OUTPUT_BITS = {name: i for i, name in enumerate(OUTPUT_NAMES)}
OUTPUT_BITS['stepper_enable'] = 12

INPUT_NAMES = (
    'estop_ok', 'door_closed', 'air_pressure_ok', 'belt_present',
    'knife_extended', 'knife_retracted', 'knife_start',
    'laser_busy_0', 'laser_busy_1', 'laser_busy_2', 'laser_busy_3',
    'driver_fault', 'safety_relay_ok', 'home_sensor',
)
INPUT_BITS = {name: i for i, name in enumerate(INPUT_NAMES)}

# fault flag bits (same as IoStatus.FAULT_* and the firmware)
FAULT_HEARTBEAT_LOST = 1
FAULT_ESTOP = 2
FAULT_DRIVER_ALM = 4
FAULT_WDT_RESET = 8
FAULT_INTERLOCK_REJECT = 16
FAULT_KNIFE_SENSOR_CONFLICT = 32
FAULT_RX_OVERFLOW = 64


@dataclass
class IoSnapshot:
    """Polarity-corrected hardware state (mirror of ``IoStatus``)."""

    stamp: float = 0.0
    link_ok: bool = False
    source: str = ''
    fw_version: str = ''
    fw_uptime_ms: int = 0
    # inputs
    estop_ok: bool = True
    door_closed: bool = True
    safety_relay_ok: bool = True
    air_pressure_ok: bool = True
    belt_present: bool = True
    knife_extended: bool = False
    knife_retracted: bool = True
    knife_start: bool = False
    driver_fault: bool = False
    home_sensor: bool = False
    laser_busy: List[bool] = field(default_factory=lambda: [False] * MAX_STATIONS)
    # outputs
    outputs: dict = field(default_factory=lambda: {n: False for n in OUTPUT_NAMES})
    stepper_enabled: bool = False
    # motion
    position_steps: int = 0
    position_mm: float = 0.0
    velocity_mm_s: float = 0.0
    moving: bool = False
    motion_id: int = 0
    encoder_mm: float = math.nan
    fault_flags: int = 0

    def input_bits(self) -> int:
        bits = 0
        values = {
            'estop_ok': self.estop_ok, 'door_closed': self.door_closed,
            'air_pressure_ok': self.air_pressure_ok, 'belt_present': self.belt_present,
            'knife_extended': self.knife_extended, 'knife_retracted': self.knife_retracted,
            'knife_start': self.knife_start, 'driver_fault': self.driver_fault,
            'safety_relay_ok': self.safety_relay_ok, 'home_sensor': self.home_sensor,
        }
        for i in range(MAX_STATIONS):
            values[f'laser_busy_{i}'] = self.laser_busy[i]
        for name, v in values.items():
            if v:
                bits |= 1 << INPUT_BITS[name]
        return bits

    def output_bits(self) -> int:
        bits = 0
        for name, v in self.outputs.items():
            if v:
                bits |= 1 << OUTPUT_BITS[name]
        if self.stepper_enabled:
            bits |= 1 << OUTPUT_BITS['stepper_enable']
        return bits

    @staticmethod
    def decode_inputs(bits: int) -> dict:
        return {name: bool(bits >> i & 1) for name, i in INPUT_BITS.items()}

    @staticmethod
    def decode_outputs(bits: int) -> Tuple[dict, bool]:
        outs = {name: bool(bits >> OUTPUT_BITS[name] & 1) for name in OUTPUT_NAMES}
        return outs, bool(bits >> OUTPUT_BITS['stepper_enable'] & 1)


class HardwareInterface(ABC):
    """What the machine controller may ask of the hardware layer."""

    @abstractmethod
    def snapshot(self) -> IoSnapshot:
        """Latest I/O state."""

    @abstractmethod
    def move_relative(self, distance_mm: float, speed_mm_s: float = 0.0,
                      accel_mm_s2: float = 0.0) -> int:
        """Start a relative belt move. Returns the motion id that will appear in the status."""

    @abstractmethod
    def jog(self, direction: int, speed_mm_s: float, duration_ms: int) -> int:
        """Continuous move, stopped by :meth:`stop` or after ``duration_ms``."""

    @abstractmethod
    def stop(self, quick: bool = False) -> None:
        """Stop the belt (decelerate, or as fast as possible)."""

    @abstractmethod
    def set_output(self, name: str, state: bool) -> None:
        """Switch an output."""

    @abstractmethod
    def pulse_output(self, name: str, duration_ms: int) -> None:
        """Switch an output on for a time measured by the firmware (not the Pi)."""

    @abstractmethod
    def enable_drive(self, on: bool) -> None:
        """Enable / release the stepper driver."""

    @abstractmethod
    def zero_position(self) -> None:
        """Set the position counter to 0."""

    @abstractmethod
    def reset_faults(self) -> None:
        """Clear latched firmware faults (heartbeat lost, interlock reject)."""

    @abstractmethod
    def heartbeat(self, now: float) -> None:
        """Called every controller tick. Implementations rate-limit as needed."""

    def pop_errors(self) -> List[str]:
        """Asynchronous command rejections since the last call."""
        return []

    # -- helpers used by the laser abstraction (LaserIoPort)
    def laser_busy(self, station: int) -> bool:
        snap = self.snapshot()
        return bool(station < len(snap.laser_busy) and snap.laser_busy[station])

    def motion_done(self, motion_id: int) -> bool:
        snap = self.snapshot()
        return snap.motion_id == motion_id and not snap.moving


class MotionIdCounter:
    """16-bit motion ids, never 0 (0 = no motion yet)."""

    def __init__(self):
        self._id = 0

    def next_id(self) -> int:
        self._id = self._id % 0xFFFF + 1
        return self._id
