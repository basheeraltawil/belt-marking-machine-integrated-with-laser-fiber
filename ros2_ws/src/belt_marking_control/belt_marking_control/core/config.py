"""Machine configuration (loaded from ROS parameters / YAML). No magic numbers in code."""

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Dict, List

from belt_marking_laser import DoneMode


@dataclass
class MachineSection:
    """Mechanical limits and monitoring options (machine.*)."""
    knife_offset_mm: float = 56.0           # station 0 -> knife  # TODO: verify on hardware
    fork_sensor_offset_mm: float = 350.0    # fork sensor upstream of station 0
    belt_width_min_mm: float = 10.0
    belt_width_max_mm: float = 100.0
    pitch_min_mm: float = 5.0
    pitch_max_mm: float = 2000.0
    quantity_max: int = 100000
    feed_speed_default_mm_s: float = 14.5   # legacy 1000 steps/s / 69 steps/mm
    feed_speed_max_mm_s: float = 60.0
    jog_speed_mm_s: float = 10.0
    jog_max_mm: float = 500.0
    motion_timeout_margin_s: float = 2.0
    require_belt_present: bool = True
    require_door_closed: bool = True
    monitor_air_pressure: bool = True
    encoder_enabled: bool = False
    slip_tolerance_mm: float = 2.0
    consecutive_reject_limit: int = 3
    settle_default_s: float = 0.1
    drive_release_s: float = 60.0            # release the stepper after this idle time
    startup_grace_s: float = 5.0             # no link alarm until the first status (boot)


@dataclass
class LaserSection:
    """Laser stations and trigger/done settings (laser.*)."""
    num_stations: int = 1
    station_offsets_mm: List[float] = field(default_factory=lambda: [0.0])
    station_delays_s: List[float] = field(default_factory=lambda: [0.0])
    station_enabled: List[bool] = field(default_factory=lambda: [True])
    pulse_ms: int = 200                      # TODO: verify on hardware
    done_mode: str = 'signal'                # signal | timed   # TODO: verify on hardware
    ack_timeout_s: float = 1.0
    timeout_factor: float = 2.0
    timeout_margin_s: float = 2.0
    timeout_recovery: str = 'reject'         # retry | reject
    field_length_mm: float = 50.0            # max mark length along the belt
    marking_time_default_s: float = 3.0

    @property
    def done_mode_enum(self) -> DoneMode:
        return DoneMode(self.done_mode)

    def timeout_for(self, marking_time_s: float) -> float:
        return marking_time_s * self.timeout_factor + self.timeout_margin_s


@dataclass
class KnifeSection:
    """Knife timing and ejector (knife.*)."""
    extend_timeout_s: float = 1.5            # TODO: verify on hardware
    retract_timeout_s: float = 1.5           # TODO: verify on hardware
    dwell_s: float = 0.1
    hold_retract_energized: bool = True      # legacy behaviour: retract solenoid on at rest
    ejector_enabled: bool = True
    eject_ms: int = 1000                     # legacy DC motor pulse
    blade_life_cycles: int = 50000           # maintenance warning


@dataclass
class ZairSection:
    """Z-Air valve behaviour (zair.*)."""
    during_mark: bool = True                 # legacy: Z-Air on while the laser marks


@dataclass
class ControlConfig:
    """All controller settings; filled from machine.yaml."""
    machine: MachineSection = field(default_factory=MachineSection)
    laser: LaserSection = field(default_factory=LaserSection)
    knife: KnifeSection = field(default_factory=KnifeSection)
    zair: ZairSection = field(default_factory=ZairSection)
    tick_hz: float = 100.0
    db_path: str = '~/.belt_marking/belt_marking.db'
    use_sim: bool = False

    def validate(self) -> List[str]:
        """Consistency check of the configuration; returns error strings."""
        errors = []
        n = self.laser.num_stations
        if not 1 <= n <= 4:
            errors.append('laser.num_stations must be 1..4')
        for name in ('station_offsets_mm', 'station_delays_s', 'station_enabled'):
            if len(getattr(self.laser, name)) < n:
                errors.append(f'laser.{name} needs {n} entries')
        if self.laser.done_mode not in ('signal', 'timed'):
            errors.append('laser.done_mode must be "signal" or "timed"')
        if self.laser.timeout_recovery not in ('retry', 'reject'):
            errors.append('laser.timeout_recovery must be "retry" or "reject"')
        return errors


def flatten(cfg: Any, prefix: str = '') -> Dict[str, Any]:
    """Dataclass -> {'machine.knife_offset_mm': 56.0, ...} (ROS parameter names)."""
    out = {}
    for f in fields(cfg):
        value = getattr(cfg, f.name)
        key = f'{prefix}{f.name}'
        if is_dataclass(value):
            out.update(flatten(value, key + '.'))
        else:
            out[key] = value
    return out


def apply_flat(cfg: Any, values: Dict[str, Any]) -> Any:
    """Apply flattened values onto a (nested) dataclass in place, coercing types."""
    for key, value in values.items():
        target = cfg
        parts = key.split('.')
        for p in parts[:-1]:
            target = getattr(target, p)
        current = getattr(target, parts[-1])
        if isinstance(current, bool):
            value = bool(value)
        elif isinstance(current, int):
            value = int(value)
        elif isinstance(current, float):
            value = float(value)
        elif isinstance(current, list):
            value = list(value)
        setattr(target, parts[-1], value)
    return cfg


def from_dict(nested: Dict[str, Any]) -> ControlConfig:
    """Build from a nested dict such as a parsed YAML file."""
    flat = {}

    def walk(d, prefix=''):
        for k, v in d.items():
            if isinstance(v, dict):
                walk(v, f'{prefix}{k}.')
            else:
                flat[f'{prefix}{k}'] = v
    walk(nested)
    known = flatten(ControlConfig())
    return apply_flat(ControlConfig(), {k: v for k, v in flat.items() if k in known})
