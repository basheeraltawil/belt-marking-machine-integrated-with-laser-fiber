"""Plant model: the machine *and* the Arduino firmware behaviour, in pure Python.

Used by ``sim_hardware_node`` (real time, optionally mirrored to Gazebo) and directly by
the unit/scenario tests (accelerated time). It deliberately reproduces the firmware's
local interlocks and watchdog (see firmware/arduino_mega/src/machine.cpp), so the
controller is exercised against the same rules it will meet on the real machine.

Belt coordinates: ``belt_mm`` is how far the belt has physically moved. A point of the belt
that was at laser station 0 when ``belt_mm == 0`` has belt coordinate ``s = 0``. A belt
point with coordinate ``s`` is at conveyor position ``x = belt_mm - s``.
"""

from dataclasses import dataclass, field
import math
from typing import Callable, Dict, List, Optional, Tuple

from belt_marking_laser import SimCo2Laser

from .hal import (FAULT_DRIVER_ALM, FAULT_ESTOP, FAULT_HEARTBEAT_LOST, FAULT_INTERLOCK_REJECT,
                  FAULT_KNIFE_SENSOR_CONFLICT, IoSnapshot, MAX_STATIONS, OUTPUT_NAMES)

FAULT_NAMES = (
    'laser_no_response', 'laser_late', 'laser_weak_mark', 'laser_stuck_busy',
    'knife_stuck_extend', 'knife_stuck_retract', 'knife_sensor_conflict',
    'belt_runout', 'belt_slip', 'estop', 'door_open', 'low_air', 'driver_fault',
    'link_loss',
)


@dataclass
class PlantConfig:
    """Physical parameters of the simulated machine."""
    steps_per_mm: float = 69.0            # legacy value  # TODO: verify on hardware
    default_speed_mm_s: float = 14.5
    max_speed_mm_s: float = 60.0
    accel_mm_s2: float = 100.0
    station_offsets_mm: List[float] = field(default_factory=lambda: [0.0])
    knife_offset_mm: float = 56.0         # legacy "metalw"  # TODO: verify on hardware
    fork_sensor_offset_mm: float = 350.0  # upstream of station 0
    knife_stroke_time_s: float = 0.3
    laser_marking_time_s: float = 3.0     # time of the design loaded on the laser(s)
    laser_start_latency_s: float = 0.05
    watchdog_s: float = 0.5
    interlock_knife_for_motion: bool = True
    encoder_enabled: bool = False
    fw_version: str = 'sim-1.0.0'


@dataclass
class PlantMark:
    """A mark as it really landed on the simulated belt (ground truth)."""
    station: int
    belt_coord_mm: float
    t: float
    weak: bool
    on_belt: bool


class FakePlant:
    """Deterministic plant + firmware model. Advance it with :meth:`step`."""

    def __init__(self, cfg: Optional[PlantConfig] = None):
        self.cfg = cfg or PlantConfig()
        self.t = 0.0
        self.events: List[Tuple[str, dict]] = []
        self.on_event: Optional[Callable[[str, dict], None]] = None
        # motion (steps)
        self.pos = 0.0
        self.vel = 0.0
        self.target: Optional[float] = None
        self.cruise = 0.0
        self.accel = 0.0
        self.jog_dir = 0
        self.jog_until = 0.0
        self.motion_id = 0
        self.enabled = False
        self.belt_mm = 0.0                  # physical belt travel (includes slip)
        self._zero_offset_steps = 0.0
        self._zero_belt = 0.0
        # outputs
        self.outputs: Dict[str, bool] = {n: False for n in OUTPUT_NAMES}
        self.pulse_until: Dict[str, float] = {}
        # knife: 0 = retracted, 1 = extended
        self.knife = 0.0
        self._cut_armed = True
        # lasers
        self.lasers = [
            SimCo2Laser(station=i, marking_time_s=self.cfg.laser_marking_time_s,
                        start_latency_s=self.cfg.laser_start_latency_s,
                        on_mark_done=self._on_mark_done)
            for i in range(len(self.cfg.station_offsets_mm))
        ]
        # belt supply: belt coordinate of the tail (inf = endless supply)
        self.tail_coord = math.inf
        self.pending_pieces: List[dict] = []
        # faults
        self.faults: Dict[str, float] = {}
        self.latched = 0
        self.last_heartbeat = 0.0
        self._hb_seen = False
        self.link_up = True
        # records for tests / twin / vision
        self.marks: List[PlantMark] = []
        self.cuts: List[float] = []
        self.pieces_out = 0
        self.knife_cycles = 0

    # ------------------------------------------------------------------ faults
    def inject(self, fault: str, enable: bool = True, value: float = 0.0,
               station: int = 0) -> Tuple[bool, str]:
        """Switch a simulated fault on or off (see FAULT_NAMES)."""
        if fault == 'clear_all':
            for key in list(self.faults):
                name, _, st = key.partition(':')
                self.inject(name, False, station=int(st or 0))
            return True, 'all faults cleared'
        if fault not in FAULT_NAMES:
            return False, f'unknown fault {fault!r}'
        if fault.startswith('laser_'):
            if station >= len(self.lasers):
                return False, f'no laser station {station}'
            f = self.lasers[station].faults
            if fault == 'laser_no_response':
                f.no_response = enable
            elif fault == 'laser_late':
                f.late_s = value if enable else 0.0
            elif fault == 'laser_weak_mark':
                f.weak_mark = enable
            elif fault == 'laser_stuck_busy':
                f.stuck_busy = enable
        if fault == 'belt_runout':
            if enable:
                # the fork sensor sees the belt for `value` more mm
                self.tail_coord = self.belt_mm + self.cfg.fork_sensor_offset_mm + max(value, 0.0)
            else:
                self.tail_coord = math.inf  # refilled / spliced
        if fault == 'link_loss':
            self.link_up = not enable
        key = fault if not fault.startswith('laser_') else f'{fault}:{station}'
        if enable:
            self.faults[key] = value
        else:
            self.faults.pop(key, None)
        return True, f'{fault} {"on" if enable else "off"}'

    def has_fault(self, name: str) -> bool:
        return name in self.faults

    # ------------------------------------------------------------------ inputs
    @property
    def estop_ok(self) -> bool:
        return not self.has_fault('estop')

    @property
    def safety_ok(self) -> bool:
        """Safety relay output: E-stop chain healthy (door handled by the laser interlock)."""
        return self.estop_ok

    @property
    def door_closed(self) -> bool:
        return not self.has_fault('door_open')

    @property
    def air_ok(self) -> bool:
        return not self.has_fault('low_air')

    def belt_at(self, x_mm: float) -> bool:
        """True if belt material is present at conveyor position x."""
        return (self.belt_mm - x_mm) <= self.tail_coord

    @property
    def belt_present(self) -> bool:
        return self.belt_at(-self.cfg.fork_sensor_offset_mm)

    @property
    def knife_extended(self) -> bool:
        return self.knife >= 0.98 or self.has_fault('knife_sensor_conflict')

    @property
    def knife_retracted(self) -> bool:
        return self.knife <= 0.02 or self.has_fault('knife_sensor_conflict')

    @property
    def driver_fault(self) -> bool:
        return self.has_fault('driver_fault')

    @property
    def position_mm(self) -> float:
        return (self.pos - self._zero_offset_steps) / self.cfg.steps_per_mm

    @property
    def moving(self) -> bool:
        return self.target is not None or self.jog_dir != 0 or abs(self.vel) > 1e-9

    def _blocking_faults(self) -> int:
        flags = self.latched
        if not self.estop_ok:
            flags |= FAULT_ESTOP
        if self.driver_fault:
            flags |= FAULT_DRIVER_ALM
        return flags

    # ---------------------------------------------------------------- commands
    def heartbeat(self) -> None:
        if self.link_up:
            self.last_heartbeat = self.t
            self._hb_seen = True

    def cmd_move_rel(self, distance_mm: float, speed_mm_s: float = 0.0,
                     accel_mm_s2: float = 0.0, motion_id: int = 0) -> Tuple[bool, str]:
        ok, why = self._motion_allowed()
        if not ok:
            return False, why
        if self.moving:
            return False, 'busy: already moving'
        speed = speed_mm_s or self.cfg.default_speed_mm_s
        speed = min(abs(speed), self.cfg.max_speed_mm_s)
        self.cruise = speed * self.cfg.steps_per_mm
        self.accel = (accel_mm_s2 or self.cfg.accel_mm_s2) * self.cfg.steps_per_mm
        self.target = float(round(self.pos) + round(distance_mm * self.cfg.steps_per_mm))
        self.motion_id = motion_id
        if self.target == self.pos:
            self.target = None
        return True, 'ok'

    def cmd_jog(self, direction: int, speed_mm_s: float, duration_ms: int,
                motion_id: int = 0) -> Tuple[bool, str]:
        ok, why = self._motion_allowed()
        if not ok:
            return False, why
        direction = 1 if direction >= 0 else -1
        if self.target is not None or (self.jog_dir not in (0, direction)):
            return False, 'busy: already moving'
        self.jog_dir = direction
        self.cruise = min(abs(speed_mm_s) or 5.0, self.cfg.max_speed_mm_s) * self.cfg.steps_per_mm
        self.accel = self.cfg.accel_mm_s2 * self.cfg.steps_per_mm
        self.jog_until = self.t + duration_ms / 1000.0
        self.motion_id = motion_id
        return True, 'ok'

    def cmd_stop(self, quick: bool = False) -> Tuple[bool, str]:
        if quick or abs(self.vel) < 1e-9:
            self._quick_stop()
        else:
            self.jog_dir = 0
            a = self.accel or self.cfg.accel_mm_s2 * self.cfg.steps_per_mm
            d = self.vel * self.vel / (2 * a)
            # stop on a whole step, like the firmware (positions are integer steps)
            self.target = float(math.ceil(self.pos + d) if self.vel > 0
                                else math.floor(self.pos - d))
        return True, 'ok'

    def cmd_set_output(self, name: str, state: bool) -> Tuple[bool, str]:
        if name not in self.outputs:
            return False, f'unknown output {name!r}'
        if state and self._blocking_faults() & (FAULT_HEARTBEAT_LOST | FAULT_ESTOP):
            if name not in ('knife_retract', 'light_red', 'light_yellow', 'buzzer'):
                return False, 'rejected: fault active'
        if state and name.startswith('laser_') and not self.door_closed:
            self.latched |= FAULT_INTERLOCK_REJECT
            return False, 'interlock: laser door open'
        if state and name == 'knife_extend' and self.moving:
            self.latched |= FAULT_INTERLOCK_REJECT
            return False, 'interlock: knife extend while belt moving'
        if name == 'knife_extend' and state:
            self.outputs['knife_retract'] = False
        if name == 'knife_retract' and state:
            self.outputs['knife_extend'] = False
        self.outputs[name] = state
        self.pulse_until.pop(name, None)
        return True, 'ok'

    def cmd_pulse_output(self, name: str, duration_ms: int) -> Tuple[bool, str]:
        ok, why = self.cmd_set_output(name, True)
        if ok:
            self.pulse_until[name] = self.t + duration_ms / 1000.0
        return ok, why

    def cmd_enable(self, on: bool) -> Tuple[bool, str]:
        if on and not self.safety_ok:
            return False, 'rejected: safety chain open'
        self.enabled = on
        if not on:
            self._quick_stop()
        return True, 'ok'

    def cmd_zero(self) -> Tuple[bool, str]:
        if self.moving:
            return False, 'busy: moving'
        self._zero_offset_steps = self.pos
        self._zero_belt = self.belt_mm
        return True, 'ok'

    def cmd_reset_faults(self) -> Tuple[bool, str]:
        if self.t - self.last_heartbeat > self.cfg.watchdog_s:
            return False, 'rejected: no heartbeat'
        self.latched = 0
        return True, 'ok'

    def _motion_allowed(self) -> Tuple[bool, str]:
        flags = self._blocking_faults()
        if flags & (FAULT_HEARTBEAT_LOST | FAULT_ESTOP | FAULT_DRIVER_ALM):
            return False, f'rejected: faults 0x{flags:02x}'
        if not self.enabled:
            return False, 'rejected: drive disabled'
        if self.cfg.interlock_knife_for_motion and not self.knife_retracted:
            self.latched |= FAULT_INTERLOCK_REJECT
            return False, 'interlock: knife not retracted'
        return True, 'ok'

    def _quick_stop(self) -> None:
        self.vel = 0.0
        self.target = None
        self.jog_dir = 0

    # ------------------------------------------------------------------ physics
    def step(self, dt: float) -> None:
        self.t += dt
        self._watchdog()
        self._pulses()
        self._motion(dt)
        self._knife(dt)
        interlock = self.door_closed and self.safety_ok
        for i, laser in enumerate(self.lasers):
            laser.update(self.t, self.outputs.get(f'laser_{i}', False), interlock)
        self._ejector()

    def run(self, seconds: float, dt: float = 0.005) -> None:
        n = max(1, int(round(seconds / dt)))
        for _ in range(n):
            self.step(dt)

    def _watchdog(self) -> None:
        if self._hb_seen and self.t - self.last_heartbeat > self.cfg.watchdog_s and \
                not self.latched & FAULT_HEARTBEAT_LOST:
            self.latched |= FAULT_HEARTBEAT_LOST
            self._safe_state()
        if not self.estop_ok or self.driver_fault:
            self._quick_stop()
        if not self.safety_ok:
            self.enabled = False

    def _safe_state(self) -> None:
        """Firmware fail-safe: stop, retract knife, inhibit lasers, aux off, red light."""
        self._quick_stop()
        for name in self.outputs:
            self.outputs[name] = False
        self.pulse_until.clear()
        self.outputs['knife_retract'] = True
        self.outputs['light_red'] = True

    def _pulses(self) -> None:
        for name, until in list(self.pulse_until.items()):
            if self.t >= until:
                self.outputs[name] = False
                del self.pulse_until[name]

    def _motion(self, dt: float) -> None:
        if not self.enabled:
            self._quick_stop()
            return
        before = self.pos
        a = self.accel or self.cfg.accel_mm_s2 * self.cfg.steps_per_mm
        if self.jog_dir:
            if self.t >= self.jog_until:
                self.cmd_stop(False)
            else:
                v = min(abs(self.vel) + a * dt, self.cruise)
                self.vel = self.jog_dir * v
                self.pos += self.vel * dt
        if self.target is not None and not self.jog_dir:
            rem = self.target - self.pos
            d = 1.0 if rem > 0 else -1.0
            v = self.vel * d
            if v < 0:                      # moving the wrong way: brake first
                v = min(v + a * dt, 0.0)
                self.vel = d * v
                self.pos += self.vel * dt
            else:
                if abs(rem) <= v * v / (2 * a) + 1e-9:
                    v = max(v - a * dt, a * dt)
                else:
                    v = min(v + a * dt, self.cruise)
                step = v * dt
                if step >= abs(rem):
                    self.pos = self.target
                    self.vel = 0.0
                    self.target = None
                else:
                    self.pos += d * step
                    self.vel = d * v
        moved_mm = (self.pos - before) / self.cfg.steps_per_mm
        slip = self.faults.get('belt_slip', 0.0) if self.has_fault('belt_slip') else 0.0
        self.belt_mm += moved_mm * (1.0 - slip)

    def _knife(self, dt: float) -> None:
        powered = self.safety_ok and self.air_ok
        ext = self.outputs['knife_extend'] and powered
        ret = self.outputs['knife_retract'] and powered
        rate = dt / max(self.cfg.knife_stroke_time_s, 1e-3)
        if ext and not ret:
            limit = 0.5 if self.has_fault('knife_stuck_extend') else 1.0
            self.knife = min(limit, self.knife + rate) if self.knife < limit else self.knife
        elif ret and not ext:
            limit = 0.5 if self.has_fault('knife_stuck_retract') else 0.0
            self.knife = max(limit, self.knife - rate) if self.knife > limit else self.knife
        if self.knife >= 0.98 and self._cut_armed:
            self._cut_armed = False
            self.knife_cycles += 1
            x = self.cfg.knife_offset_mm
            if self.belt_at(x):
                s = self.belt_mm - x
                prev = self.cuts[-1] if self.cuts else None
                self.cuts.append(s)
                piece_len = (prev - s) if prev is not None else float('nan')
                self.pending_pieces.append({'coord': s, 'length': piece_len})
                self._emit('cut', {'belt_coord_mm': s, 'length_mm': piece_len})
        if self.knife <= 0.02:
            self._cut_armed = True

    def _ejector(self) -> None:
        if self.outputs['dc_motor'] and self.pending_pieces:
            piece = self.pending_pieces.pop(0)
            self.pieces_out += 1
            self._emit('piece_out', piece)

    def _on_mark_done(self, station: int, t: float, weak: bool) -> None:
        x = self.cfg.station_offsets_mm[station]
        on_belt = self.belt_at(x)
        m = PlantMark(station, self.belt_mm - x, t, weak, on_belt)
        self.marks.append(m)
        self._emit('mark', {'station': station, 'belt_coord_mm': m.belt_coord_mm,
                            'weak': weak, 'on_belt': on_belt})

    def _emit(self, kind: str, data: dict) -> None:
        self.events.append((kind, data))
        if self.on_event is not None:
            self.on_event(kind, data)

    # ----------------------------------------------------------------- status
    def snapshot(self) -> IoSnapshot:
        busy = [la.busy for la in self.lasers] + [False] * (MAX_STATIONS - len(self.lasers))
        flags = self._blocking_faults()
        if self.has_fault('knife_sensor_conflict'):
            flags |= FAULT_KNIFE_SENSOR_CONFLICT
        return IoSnapshot(
            stamp=self.t, link_ok=self.link_up, source='sim', fw_version=self.cfg.fw_version,
            fw_uptime_ms=int(self.t * 1000),
            estop_ok=self.estop_ok, door_closed=self.door_closed,
            safety_relay_ok=self.safety_ok, air_pressure_ok=self.air_ok,
            belt_present=self.belt_present, knife_extended=self.knife_extended,
            knife_retracted=self.knife_retracted,
            knife_start=self.belt_at(self.cfg.knife_offset_mm),
            driver_fault=self.driver_fault, home_sensor=False,
            laser_busy=busy[:MAX_STATIONS], outputs=dict(self.outputs),
            stepper_enabled=self.enabled,
            position_steps=int(round(self.pos - self._zero_offset_steps)),
            position_mm=self.position_mm,
            velocity_mm_s=self.vel / self.cfg.steps_per_mm,
            moving=self.moving, motion_id=self.motion_id,
            encoder_mm=(self.belt_mm - self._zero_belt if self.cfg.encoder_enabled
                        else math.nan),
            fault_flags=flags,
        )
