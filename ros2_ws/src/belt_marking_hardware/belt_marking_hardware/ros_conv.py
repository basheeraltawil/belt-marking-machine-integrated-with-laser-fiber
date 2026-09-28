"""IoSnapshot <-> belt_marking_interfaces/IoStatus, and HwCommand dispatch."""

import math

from belt_marking_interfaces.msg import IoStatus
from belt_marking_interfaces.srv import HwCommand

from .hal import IoSnapshot, MAX_STATIONS

_INPUTS = ('estop_ok', 'door_closed', 'safety_relay_ok', 'air_pressure_ok', 'belt_present',
           'knife_extended', 'knife_retracted', 'knife_start', 'driver_fault', 'home_sensor')
_OUT_MAP = {'knife_extend_valve': 'knife_extend', 'knife_retract_valve': 'knife_retract',
            'zair_valve': 'zair', 'dc_motor': 'dc_motor', 'light_red': 'light_red',
            'light_yellow': 'light_yellow', 'light_green': 'light_green', 'buzzer': 'buzzer'}


def snapshot_to_msg(snap: IoSnapshot, stamp, n_stations: int = MAX_STATIONS) -> IoStatus:
    m = IoStatus()
    m.stamp = stamp
    m.link_ok = snap.link_ok
    m.source = snap.source
    m.fw_version = snap.fw_version
    m.fw_uptime_ms = int(snap.fw_uptime_ms) & 0xFFFFFFFF
    for name in _INPUTS:
        setattr(m, name, bool(getattr(snap, name)))
    m.laser_busy = [bool(b) for b in snap.laser_busy[:n_stations]]
    for field, out in _OUT_MAP.items():
        setattr(m, field, bool(snap.outputs.get(out, False)))
    m.laser_trigger = [bool(snap.outputs.get(f'laser_{i}', False)) for i in range(n_stations)]
    m.stepper_enabled = snap.stepper_enabled
    m.position_steps = int(snap.position_steps)
    m.position_mm = float(snap.position_mm)
    m.velocity_mm_s = float(snap.velocity_mm_s)
    m.moving = bool(snap.moving)
    m.motion_id = int(snap.motion_id) & 0xFFFF
    m.encoder_mm = float(snap.encoder_mm)
    m.fault_flags = int(snap.fault_flags) & 0xFFFF
    return m


def msg_to_snapshot(m: IoStatus, now: float) -> IoSnapshot:
    s = IoSnapshot(stamp=now, link_ok=m.link_ok, source=m.source, fw_version=m.fw_version,
                   fw_uptime_ms=m.fw_uptime_ms)
    for name in _INPUTS:
        setattr(s, name, bool(getattr(m, name)))
    busy = list(m.laser_busy) + [False] * MAX_STATIONS
    s.laser_busy = [bool(b) for b in busy[:MAX_STATIONS]]
    for field, out in _OUT_MAP.items():
        s.outputs[out] = bool(getattr(m, field))
    for i, v in enumerate(list(m.laser_trigger)[:MAX_STATIONS]):
        s.outputs[f'laser_{i}'] = bool(v)
    s.stepper_enabled = m.stepper_enabled
    s.position_steps = m.position_steps
    s.position_mm = m.position_mm
    s.velocity_mm_s = m.velocity_mm_s
    s.moving = m.moving
    s.motion_id = m.motion_id
    s.encoder_mm = m.encoder_mm if not math.isnan(m.encoder_mm) else math.nan
    s.fault_flags = m.fault_flags
    return s


def dispatch(req, backend):
    """Execute a HwCommand request on a backend exposing the FakePlant cmd_* API.

    Both the simulation (FakePlant) and the serial bridge (FirmwareClient) implement
    ``cmd_move_rel, cmd_jog, cmd_stop, cmd_set_output, cmd_pulse_output, cmd_enable,
    cmd_zero, cmd_reset_faults`` with identical semantics.
    """
    c = req.command
    if c == HwCommand.Request.STOP:
        return backend.cmd_stop(req.value >= 0.5)
    if c == HwCommand.Request.MOVE_REL:
        return backend.cmd_move_rel(req.value, req.speed, req.accel, req.motion_id)
    if c == HwCommand.Request.JOG:
        return backend.cmd_jog(1 if req.value >= 0 else -1, req.speed, req.duration_ms,
                               req.motion_id)
    if c == HwCommand.Request.SET_OUTPUT:
        return backend.cmd_set_output(req.output, req.state)
    if c == HwCommand.Request.PULSE_OUTPUT:
        return backend.cmd_pulse_output(req.output, req.duration_ms)
    if c == HwCommand.Request.ENABLE_DRIVE:
        return backend.cmd_enable(req.state)
    if c == HwCommand.Request.ZERO_POSITION:
        return backend.cmd_zero()
    if c == HwCommand.Request.RESET_FAULTS:
        return backend.cmd_reset_faults()
    return False, f'unknown command {c}'
