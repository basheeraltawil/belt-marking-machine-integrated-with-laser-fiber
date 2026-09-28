"""Machine controller: PackML-inspired state machine + job sequencer (pure Python).

The controller is *ticked* (``tick(now)``) at ~100 Hz by the ROS node, or by the tests with a
simulated clock. It never blocks. It talks to the machine only through
:class:`belt_marking_hardware.hal.HardwareInterface`, so simulation and real hardware run
exactly the same logic. See docs/STATE_MACHINE.md.
"""

from dataclasses import dataclass, field
import enum
import math
from typing import Callable, Dict, List, Optional

from belt_marking_hardware.hal import (FAULT_HEARTBEAT_LOST, FAULT_WDT_RESET, HardwareInterface,
                                       IoSnapshot)
from belt_marking_laser import DoneMode, DryContactLaser, LaserConfig, LaserPoll

from .alarms import AlarmInstance, AlarmManager, CATALOG, CODES, Reaction, Severity
from .config import ControlConfig
from .job import Job, validate
from .oee import Counters, OeeTracker
from .planner import Fire, move_time, Plan, plan_job


class State(enum.IntEnum):
    STOPPED = 0
    RESETTING = 1
    IDLE = 2
    STARTING = 3
    EXECUTE = 4
    HOLDING = 5
    HELD = 6
    UNHOLDING = 7
    COMPLETING = 8
    COMPLETE = 9
    STOPPING = 10
    ABORTING = 11
    ABORTED = 12
    CLEARING = 13


class Mode(enum.IntEnum):
    AUTO = 0
    MANUAL = 1
    MAINTENANCE = 2
    SIMULATION = 3


class Phase(str, enum.Enum):
    NONE = 'NONE'
    FEED = 'FEED'
    SETTLE = 'SETTLE'
    LASER = 'LASER'
    POST_DELAY = 'POST_DELAY'
    CUT_EXTEND = 'CUT_EXTEND'
    CUT_DWELL = 'CUT_DWELL'
    CUT_RETRACT = 'CUT_RETRACT'
    NEXT = 'NEXT'


JOB_STATES = {State.STARTING, State.EXECUTE, State.HOLDING, State.HELD, State.UNHOLDING,
              State.COMPLETING}
MANUAL_STATES = {State.STOPPED, State.IDLE, State.COMPLETE}
AUX_OUTPUTS = {'zair', 'dc_motor', 'light_red', 'light_yellow', 'light_green', 'buzzer'}
POS_TOL_MM = 0.02


@dataclass
class FireState:
    fire: Fire
    due: float = 0.0
    triggered: bool = False
    result: Optional[LaserPoll] = None
    rejected: bool = False


@dataclass
class JobRun:
    job: Job
    plan: Plan
    origin_mm: float
    t_start: float
    stop_index: int = 0
    phase: Phase = Phase.NONE
    phase_t0: float = 0.0
    phase_started: bool = False
    motion_id: int = 0
    motion_deadline: float = 0.0
    motion_retries: int = 0
    fires: List[FireState] = field(default_factory=list)
    label_remaining: Dict[int, int] = field(default_factory=dict)
    marks_done: int = 0
    pieces_cut: int = 0
    rejects: int = 0
    consecutive_rejects: int = 0
    rejected_labels: set = field(default_factory=set)
    t_end: Optional[float] = None
    final_state: Optional[State] = None
    message: str = ''

    @property
    def progress(self) -> float:
        n = len(self.plan.stops)
        return self.stop_index / n if n else 1.0


@dataclass
class ManualTask:
    kind: str
    t0: float
    step: str = 'start'
    done: bool = False
    ok: bool = False
    message: str = ''
    result: dict = field(default_factory=dict)
    station: int = 0
    motion_id: int = 0
    deadline: float = 0.0
    laser: Optional[DryContactLaser] = None
    wait_done: bool = True


class MachineController:
    """The machine brain. Construct, then call :meth:`tick` periodically."""

    def __init__(self, hal: HardwareInterface, cfg: ControlConfig, now: float = 0.0,
                 accel_mm_s2: float = 100.0, steps_per_mm: float = 69.0):
        errors = cfg.validate()
        if errors:
            raise ValueError('invalid configuration: ' + '; '.join(errors))
        self.hal = hal
        self.cfg = cfg
        self.accel = accel_mm_s2
        self.step_mm = 1.0 / steps_per_mm
        self.state = State.STOPPED
        self.mode = Mode.SIMULATION if cfg.use_sim else Mode.AUTO
        self.state_since = now
        self.now = now
        self.snap: IoSnapshot = hal.snapshot()
        self.run: Optional[JobRun] = None
        self.last_run: Optional[JobRun] = None
        self.manual: Optional[ManualTask] = None
        self.counters = Counters()
        self.oee = OeeTracker()
        self.alarms = AlarmManager(on_change=self._on_alarm)
        self._lasers: Dict[int, DryContactLaser] = {}
        self._lights = None
        self._last_pos: Optional[float] = None
        self._substep = 0
        self._sub_t0 = now
        self._stopped_since = now
        self._pending_unhold_option = ''
        self._blade_warned = False
        self._slip_baseline = 0.0
        # callbacks (ROS node / DB / tests)
        self.on_event: Optional[Callable[[dict], None]] = None
        self.on_alarm: Optional[Callable[[AlarmInstance, str], None]] = None
        self.on_state: Optional[Callable[[State, State], None]] = None
        self.on_job_end: Optional[Callable[[JobRun], None]] = None
        self.on_cycle: Optional[Callable[[str, float], None]] = None  # (kind, seconds)
        self.log: List[str] = []

    # =================================================================== commands
    def cmd_reset(self, user: str = '') -> tuple:
        if self.state not in (State.STOPPED, State.COMPLETE):
            return False, f'RESET not allowed in {self.state.name}'
        self.alarms.ack_inactive(user)
        self._goto(State.RESETTING)
        return True, 'resetting'

    def cmd_start(self, job: Job, user: str = '') -> tuple:
        if self.mode not in (Mode.AUTO, Mode.SIMULATION):
            return False, f'START needs AUTO mode (mode is {self.mode.name})'
        if self.state != State.IDLE:
            return False, f'START not allowed in {self.state.name} (press RESET first)'
        errors = validate(job, self.cfg)
        if errors:
            self._event_alarm(CODES['JOB_INVALID'], '; '.join(errors))
            return False, 'invalid job: ' + '; '.join(errors)
        plan = plan_job(job, self.cfg, self.accel)
        self.run = JobRun(job=job, plan=plan, origin_mm=self.snap.position_mm, t_start=self.now)
        n_st = len(plan.stations)
        self.run.label_remaining = {k: n_st for k in range(job.quantity)}
        cfg_l = self.cfg.laser
        lcfg = LaserConfig(pulse_ms=cfg_l.pulse_ms,
                           done_mode=DoneMode.SIGNAL if job.use_done_signal(self.cfg)
                           else DoneMode.TIMED,
                           ack_timeout_s=cfg_l.ack_timeout_s, timeout_factor=cfg_l.timeout_factor,
                           timeout_margin_s=cfg_l.timeout_margin_s)
        self._lasers = {i: DryContactLaser(self.hal, i, lcfg) for i, _, _ in plan.stations}
        self._goto(State.STARTING)
        return True, f'starting job {job.job_id} ({len(plan.stops)} stops)'

    def cmd_hold(self, user: str = '') -> tuple:
        if self.state not in (State.EXECUTE, State.STARTING, State.UNHOLDING):
            return False, f'HOLD not allowed in {self.state.name}'
        self._goto(State.HOLDING)
        return True, 'holding'

    def cmd_unhold(self, user: str = '', option: str = '') -> tuple:
        if self.state != State.HELD:
            return False, f'RESUME not allowed in {self.state.name}'
        blocking = self.alarms.blocking()
        if blocking:
            return False, 'active alarms: ' + ', '.join(a.definition.code_text for a in blocking)
        if option and option not in ('retry', 'reject'):
            return False, 'option must be retry or reject'
        self.alarms.ack_inactive(user)
        self._pending_unhold_option = option or self.cfg.laser.timeout_recovery
        self._goto(State.UNHOLDING)
        return True, 'resuming'

    def cmd_stop(self, user: str = '') -> tuple:
        if self.state in (State.STOPPED, State.STOPPING, State.ABORTING, State.ABORTED,
                          State.CLEARING):
            return False, f'STOP not allowed in {self.state.name}'
        self._goto(State.STOPPING)
        return True, 'stopping'

    def cmd_abort(self, user: str = '') -> tuple:
        if self.state in (State.ABORTING, State.ABORTED):
            return False, 'already aborted'
        self._goto(State.ABORTING)
        return True, 'aborting'

    def cmd_clear(self, user: str = '') -> tuple:
        if self.state != State.ABORTED:
            return False, f'CLEAR not allowed in {self.state.name}'
        # firmware faults (heartbeat lost / WDT) are what CLEARING resets, so they don't block
        blocking = [a for a in self.alarms.blocking(Reaction.ABORT)
                    if a.code != CODES['FIRMWARE_FAULT']]
        if blocking:
            return False, 'active alarms: ' + ', '.join(a.definition.code_text for a in blocking)
        self._goto(State.CLEARING)
        return True, 'clearing'

    def cmd_set_mode(self, mode: Mode, user: str = '') -> tuple:
        if self.state not in (State.STOPPED, State.IDLE, State.COMPLETE, State.ABORTED):
            return False, f'mode change not allowed in {self.state.name}'
        if self.cfg.use_sim and mode == Mode.AUTO:
            mode = Mode.SIMULATION
        if not self.cfg.use_sim and mode == Mode.SIMULATION:
            return False, 'SIMULATION mode needs the simulated hardware (use_sim:=true)'
        self.mode = mode
        self._log(f'mode -> {mode.name} ({user})')
        return True, f'mode {mode.name}'

    def cmd_ack(self, code: int = 0, user: str = '') -> int:
        return self.alarms.ack(code, user)

    def quality_result(self, label: int, ok: bool, reason: str = '') -> None:
        run = self.run
        if run is None or label in run.rejected_labels:
            return
        if ok:
            run.consecutive_rejects = 0
            return
        self._reject_label(label, f'vision: {reason}')
        run.consecutive_rejects += 1
        self._event_alarm(CODES['VISION_REJECT'], f'label {label}: {reason}')
        limit = self.cfg.machine.consecutive_reject_limit
        if limit > 0 and run.consecutive_rejects >= limit:
            self._event_alarm(CODES['CONSECUTIVE_REJECTS'],
                              f'{run.consecutive_rejects} consecutive rejects')
            run.consecutive_rejects = 0

    # ---------------------------------------------------------------- manual ops
    def _manual_allowed(self, allow_held: bool = False, maintenance_only: bool = False) -> tuple:
        if self.manual is not None and not self.manual.done:
            return False, f'manual {self.manual.kind} still running'
        if allow_held and self.state == State.HELD:
            return True, ''
        if maintenance_only and self.mode != Mode.MAINTENANCE:
            return False, 'needs MAINTENANCE mode'
        if self.mode not in (Mode.MANUAL, Mode.MAINTENANCE):
            return False, 'needs MANUAL or MAINTENANCE mode'
        if self.state not in MANUAL_STATES:
            return False, f'not allowed in {self.state.name}'
        return True, ''

    def manual_jog(self, distance_mm: float, speed_mm_s: float = 0.0) -> tuple:
        ok, why = self._manual_allowed(allow_held=True)
        if not ok:
            return False, why, None
        if abs(distance_mm) > self.cfg.machine.jog_max_mm:
            return False, f'jog limited to {self.cfg.machine.jog_max_mm:g} mm', None
        if not self.snap.knife_retracted:
            return False, 'knife not retracted', None
        speed = min(speed_mm_s or self.cfg.machine.jog_speed_mm_s,
                    self.cfg.machine.feed_speed_max_mm_s)
        task = ManualTask('jog', self.now)
        self._ensure_drive()
        task.motion_id = self.hal.move_relative(distance_mm, speed, self.accel)
        task.deadline = self.now + move_time(distance_mm, speed, self.accel) * 1.5 + \
            self.cfg.machine.motion_timeout_margin_s
        task.result['distance_mm'] = distance_mm
        if self.state == State.HELD and self.run is not None:
            # re-alignment while held: keep the plan attached to the belt
            self.run.origin_mm += distance_mm
        self.manual = task
        return True, 'jogging', task

    def manual_cut(self) -> tuple:
        ok, why = self._manual_allowed()
        if not ok:
            return False, why, None
        if self.snap.moving:
            return False, 'belt moving', None
        self.manual = ManualTask('cut', self.now)
        return True, 'cutting', self.manual

    def manual_laser(self, station: int, wait_done: bool = True) -> tuple:
        ok, why = self._manual_allowed()
        if not ok:
            return False, why, None
        if station >= self.cfg.laser.num_stations:
            return False, f'no station {station}', None
        if self.cfg.machine.require_door_closed and not self.snap.door_closed:
            return False, 'laser door open', None
        lz = self.cfg.laser
        laser = DryContactLaser(self.hal, station, LaserConfig(
            pulse_ms=lz.pulse_ms, done_mode=lz.done_mode_enum, ack_timeout_s=lz.ack_timeout_s,
            timeout_factor=lz.timeout_factor, timeout_margin_s=lz.timeout_margin_s))
        task = ManualTask('laser', self.now, station=station, laser=laser, wait_done=wait_done)
        laser.trigger(self.now, lz.marking_time_default_s)
        self.counters.laser_triggers += 1
        self.manual = task
        return True, 'triggered', task

    def manual_output(self, name: str, state: bool) -> tuple:
        ok, why = self._manual_allowed(maintenance_only=True)
        if not ok:
            return False, why
        if name not in AUX_OUTPUTS:
            return False, f'{name} cannot be forced (use the dedicated function)'
        self.hal.set_output(name, state)
        return True, f'{name} {"on" if state else "off"}'

    def manual_home(self) -> tuple:
        ok, why = self._manual_allowed()
        if not ok:
            return False, why
        if self.snap.moving:
            return False, 'belt moving'
        self.hal.zero_position()
        self._last_pos = None
        return True, 'position zeroed (no home sensor fitted)'

    # ====================================================================== tick
    def tick(self, now: float) -> None:
        dt = max(0.0, now - self.now)
        self.now = now
        self.hal.heartbeat(now)
        self.snap = self.hal.snapshot()
        self._account(dt)
        self._monitor()
        handler = getattr(self, f'_st_{self.state.name.lower()}')
        handler()
        self._tick_manual()
        self._lights_update()

    # ------------------------------------------------------------------ monitors
    def _monitor(self) -> None:
        s, a, now, m = self.snap, self.alarms, self.now, self.cfg.machine
        a.condition(CODES['SERIAL_LINK_LOST'], not s.link_ok, now)
        if not s.link_ok:
            return   # other inputs are stale
        a.condition(CODES['ESTOP'], not s.estop_ok, now)
        a.condition(CODES['SAFETY_RELAY'], s.estop_ok and not s.safety_relay_ok, now)
        a.condition(CODES['DRIVER_FAULT'], s.driver_fault, now)
        a.condition(CODES['FIRMWARE_FAULT'],
                    bool(s.fault_flags & (FAULT_HEARTBEAT_LOST | FAULT_WDT_RESET)), now,
                    f'fault flags 0x{s.fault_flags:02x}')
        a.condition(CODES['KNIFE_SENSOR_CONFLICT'], s.knife_extended and s.knife_retracted, now)
        a.condition(CODES['LOW_AIR'], m.monitor_air_pressure and not s.air_pressure_ok, now)
        in_job = self.state in JOB_STATES or (self.manual is not None and not self.manual.done
                                              and self.manual.kind == 'laser')
        a.condition(CODES['DOOR_OPEN'], m.require_door_closed and in_job and not s.door_closed,
                    now)
        a.condition(CODES['BELT_MISSING'],
                    m.require_belt_present and self.state in JOB_STATES and not s.belt_present,
                    now)
        if m.encoder_enabled and not math.isnan(s.encoder_mm) and self.run is not None:
            diff = s.encoder_mm - s.position_mm
            if abs(diff - self._slip_baseline) > m.slip_tolerance_mm:
                self._slip_baseline = diff
                self._event_alarm(CODES['BELT_SLIP'],
                                  f'cmd {s.position_mm:.2f} mm, encoder {s.encoder_mm:.2f} mm')
        for err in self.hal.pop_errors():
            if self.state in (State.ABORTING, State.ABORTED, State.CLEARING):
                continue
            self._event_alarm(CODES['HW_COMMAND_REJECTED'], err)

    def _event_alarm(self, code: int, detail: str = '') -> None:
        """Edge alarm: reaction applied now, stays in the list (inactive) until acknowledged."""
        self.alarms.clear(code, self.now)          # a previous instance, if any
        self.alarms.raise_(code, self.now, detail)
        self.alarms.clear(code, self.now)

    def _on_alarm(self, inst: AlarmInstance, event: str) -> None:
        self._log(f'alarm {inst.definition.code_text} {event}: {inst.detail}')
        if self.on_alarm is not None:
            self.on_alarm(inst, event)
        if event != 'raised':
            return
        r = inst.definition.reaction
        if self.manual is not None and not self.manual.done and r >= Reaction.HOLD:
            self._finish_manual(False, inst.definition.text)
            self.hal.stop(quick=True)
        if r == Reaction.ABORT and self.state not in (State.ABORTING, State.ABORTED):
            self._goto(State.ABORTING)
        elif r == Reaction.STOP and self.state in JOB_STATES:
            self._goto(State.STOPPING)
        elif r == Reaction.HOLD and self.state in (State.EXECUTE, State.UNHOLDING):
            # (in STARTING the precondition check refuses the start instead)
            self._goto(State.HOLDING)

    # ------------------------------------------------------------------ states
    def _goto(self, new: State) -> None:
        old = self.state
        if old == new:
            return
        self.state = new
        self.state_since = self.now
        self._substep = 0
        self._sub_t0 = self.now
        self._log(f'state {old.name} -> {new.name}')
        if new == State.STOPPED:
            self._stopped_since = self.now
        if self.on_state is not None:
            self.on_state(old, new)

    def _elapsed(self) -> float:
        return self.now - self.state_since

    def _st_stopped(self):
        if self.snap.stepper_enabled and \
                self.now - self._stopped_since > self.cfg.machine.drive_release_s:
            self.hal.enable_drive(False)

    def _st_resetting(self):
        s = self.snap
        if self._substep == 0:
            blocking = [al for al in self.alarms.blocking() if al.code != CODES['DOOR_OPEN']]
            if blocking or not s.link_ok:
                self._log('reset refused: ' + ', '.join(a.definition.code_text for a in blocking))
                self._goto(State.STOPPED)
                return
            self.hal.reset_faults()
            self.hal.enable_drive(True)
            self.hal.set_output('knife_extend', False)
            self.hal.set_output('knife_retract', True)
            for i in range(self.cfg.laser.num_stations):
                self.hal.set_output(f'laser_{i}', False)
            self.hal.set_output('zair', False)
            self._substep = 1
        elif self._substep == 1:
            if s.knife_retracted and s.stepper_enabled:
                if not self.cfg.knife.hold_retract_energized:
                    self.hal.set_output('knife_retract', False)
                self._goto(State.IDLE)
            elif self._elapsed() > self.cfg.knife.retract_timeout_s + 1.0:
                if not s.knife_retracted:
                    self._event_alarm(CODES['KNIFE_RETRACT_TIMEOUT'], 'during reset')
                else:
                    self._goto(State.STOPPED)

    def _st_idle(self):
        pass

    def _st_starting(self):
        s, m, run = self.snap, self.cfg.machine, self.run
        problems = []
        if m.require_door_closed and not s.door_closed:
            problems.append('laser door open')
        if m.require_belt_present and not s.belt_present:
            problems.append('no belt at the fork sensor')
        if not s.knife_retracted:
            problems.append('knife not retracted')
        if not s.stepper_enabled:
            problems.append('stepper not enabled')
        busy = [i for i, _, _ in run.plan.stations if self.hal.laser_busy(i)] \
            if run.job.use_done_signal(self.cfg) else []
        if busy:
            problems.append(f'laser {busy} busy')
        if problems:
            if self._elapsed() < 0.5:        # give fresh status a moment
                return
            run.message = 'start refused: ' + ', '.join(problems)
            self._event_alarm(CODES['JOB_INVALID'], run.message)
            self._end_job(State.IDLE)
            self._goto(State.IDLE)
            return
        run.origin_mm = s.position_mm
        run.t_start = self.now
        if not math.isnan(s.encoder_mm):
            self._slip_baseline = s.encoder_mm - s.position_mm
        self._emit('JOB_START', detail=run.job.job_id)
        self._start_phase(Phase.FEED)
        self._goto(State.EXECUTE)

    def _st_execute(self):
        run = self.run
        if run.stop_index >= len(run.plan.stops):
            self._goto(State.COMPLETING)
            return
        getattr(self, f'_ph_{run.phase.value.lower()}')()

    def _st_holding(self):
        s = self.snap
        if self._substep == 0:
            if s.moving:
                self.hal.stop(quick=False)
            self.hal.set_output('knife_extend', False)
            self.hal.set_output('knife_retract', True)
            self._substep = 1
            return
        waiting_laser = any(fs.triggered and fs.result is None and self.hal.laser_busy(
            fs.fire.station) for fs in (self.run.fires if self.run else []))
        timeout = self.cfg.laser.timeout_for(self.run.job.laser_time_s) if self.run else 0
        if s.moving or (waiting_laser and self._elapsed() < timeout):
            return
        if not s.knife_retracted:
            if self._elapsed() > self.cfg.knife.retract_timeout_s:
                self._event_alarm(CODES['KNIFE_RETRACT_TIMEOUT'], 'during hold')
            return
        self.hal.set_output('zair', False)
        self._goto(State.HELD)

    def _st_held(self):
        pass

    def _st_unholding(self):
        s, run = self.snap, self.run
        if self._substep == 0:
            self.hal.reset_faults()
            self.hal.enable_drive(True)
            opt = self._pending_unhold_option
            for fs in run.fires:
                if fs.result in (LaserPoll.NO_ACK, LaserPoll.TIMEOUT):
                    if opt == 'retry':
                        fs.triggered, fs.result = False, None
                        self._lasers[fs.fire.station].reset()
                    else:
                        fs.rejected = True
                        self._label_fire_done(fs.fire, rejected=True)
                elif fs.triggered and fs.result is None:
                    res = self._lasers[fs.fire.station].poll_done(self.now)
                    if res.status == LaserPoll.DONE:
                        fs.result = LaserPoll.DONE
                        self._label_fire_done(fs.fire)
            if run.phase in (Phase.CUT_EXTEND, Phase.CUT_DWELL, Phase.CUT_RETRACT):
                run.phase = Phase.CUT_EXTEND
            if run.phase != Phase.LASER:
                run.phase_started = False
            else:
                # keep fire states; re-arm delays for not-yet-triggered fires
                if self.cfg.zair.during_mark:
                    self.hal.set_output('zair', True)
                for fs in run.fires:
                    if not fs.triggered:
                        fs.due = self.now + self.run.job.settle_s + fs.fire.delay_s
            self._substep = 1
            return
        if s.stepper_enabled and s.knife_retracted:
            self._goto(State.EXECUTE)
        elif self._elapsed() > 2.0:
            self._event_alarm(CODES['KNIFE_NOT_RETRACTED'], 'on resume')

    def _st_completing(self):
        if self._substep == 0:
            self.hal.set_output('zair', False)
            self._substep = 1
        if self.snap.moving:
            return
        self._end_job(State.COMPLETE)
        self._goto(State.COMPLETE)

    def _st_complete(self):
        pass

    def _st_stopping(self):
        s = self.snap
        if self._substep == 0:
            if s.moving:
                self.hal.stop(quick=False)
            self.hal.set_output('knife_extend', False)
            self.hal.set_output('knife_retract', True)
            self.hal.set_output('zair', False)
            self._substep = 1
            return
        busy = any(self.hal.laser_busy(i) for i in range(self.cfg.laser.num_stations))
        if (s.moving or busy or not s.knife_retracted) and self._elapsed() < 10.0:
            return
        if self.run is not None:
            self._end_job(State.STOPPED, 'stopped by operator/alarm')
        self._goto(State.STOPPED)

    def _st_aborting(self):
        self.hal.stop(quick=True)
        for i in range(self.cfg.laser.num_stations):
            self.hal.set_output(f'laser_{i}', False)
        for name in ('knife_extend', 'zair', 'dc_motor'):
            self.hal.set_output(name, False)
        self.hal.set_output('knife_retract', True)   # safe retract if air/valves powered
        if self.manual is not None and not self.manual.done:
            self._finish_manual(False, 'aborted')
        if self.run is not None:
            self._end_job(State.ABORTED, 'aborted')
        self._goto(State.ABORTED)

    def _st_aborted(self):
        self.hal.pop_errors()

    def _st_clearing(self):
        if self._substep == 0:
            self.hal.reset_faults()
            self._substep = 1
            return
        if self.snap.fault_flags & (FAULT_HEARTBEAT_LOST | FAULT_WDT_RESET):
            if self._elapsed() > 2.0:
                self._log('clear failed: firmware faults still latched')
                self._goto(State.ABORTED)
            return
        self.alarms.ack_inactive()
        self._goto(State.STOPPED)

    # ------------------------------------------------------------------ phases
    def _start_phase(self, phase: Phase) -> None:
        run = self.run
        run.phase = phase
        run.phase_t0 = self.now
        run.phase_started = False

    def _feed_pos(self) -> float:
        return self.snap.position_mm - self.run.origin_mm

    def _ph_feed(self):
        run = self.run
        stop = run.plan.stops[run.stop_index]
        delta = stop.feed_mm - self._feed_pos()
        if not run.phase_started:
            if abs(delta) < POS_TOL_MM:
                self._after_feed()
                return
            if not self.snap.knife_retracted:
                self._event_alarm(CODES['KNIFE_NOT_RETRACTED'], 'before feed')
                return
            self._ensure_drive()
            run.motion_id = self.hal.move_relative(delta, run.job.feed_speed_mm_s, self.accel)
            run.motion_deadline = self.now + move_time(delta, run.job.feed_speed_mm_s,
                                                       self.accel) * 1.5 \
                + self.cfg.machine.motion_timeout_margin_s
            run.phase_started = True
            run.phase_t0 = self.now
            return
        if self.hal.motion_done(run.motion_id):
            if abs(delta) < POS_TOL_MM:
                self._cycle('feed', self.now - run.phase_t0)
                run.motion_retries = 0
                self._after_feed()
            elif run.motion_retries < 3:
                run.motion_retries += 1
                run.phase_started = False
            else:
                self._event_alarm(CODES['MOTION_TIMEOUT'], f'position error {delta:.3f} mm')
        elif self.now > run.motion_deadline:
            self._event_alarm(CODES['MOTION_TIMEOUT'], f'move to {stop.feed_mm:.2f} mm')

    def _after_feed(self):
        stop = self.run.plan.stops[self.run.stop_index]
        if stop.fires:
            self._start_phase(Phase.SETTLE)
        elif stop.cut is not None:
            self._start_phase(Phase.CUT_EXTEND)
        else:
            self._start_phase(Phase.NEXT)

    def _ph_settle(self):
        run = self.run
        if not run.phase_started:
            run.phase_started = True
            if self.cfg.zair.during_mark:
                self.hal.set_output('zair', True)
            stop = run.plan.stops[run.stop_index]
            run.fires = [FireState(f, due=self.now + run.job.settle_s + f.delay_s)
                         for f in stop.fires]
            for lz in self._lasers.values():
                lz.reset()
        if self.now - run.phase_t0 >= run.job.settle_s:
            self._start_phase(Phase.LASER)
            run.phase_started = True

    def _ph_laser(self):
        run = self.run
        signal = run.job.use_done_signal(self.cfg)
        for fs in run.fires:
            if fs.result is not None or fs.rejected:
                continue
            laser = self._lasers[fs.fire.station]
            if not fs.triggered:
                if self.now < fs.due:
                    continue
                if signal and self.hal.laser_busy(fs.fire.station):
                    self._event_alarm(CODES['LASER_BUSY_BEFORE_TRIGGER'],
                                      f'station {fs.fire.station}')
                    return
                laser.trigger(self.now, run.job.laser_time_s)
                fs.triggered = True
                fs.due = self.now
                self.counters.laser_triggers += 1
                continue
            res = laser.poll_done(self.now)
            if res.status == LaserPoll.DONE:
                fs.result = LaserPoll.DONE
                self._cycle('laser', self.now - fs.due)
                self._label_fire_done(fs.fire)
            elif res.status == LaserPoll.NO_ACK:
                fs.result = LaserPoll.NO_ACK
                self._event_alarm(CODES['LASER_NO_ACK'],
                                  f'station {fs.fire.station}, label {fs.fire.label}')
                return
            elif res.status == LaserPoll.TIMEOUT:
                fs.result = LaserPoll.TIMEOUT
                self._event_alarm(CODES['LASER_TIMEOUT'],
                                  f'station {fs.fire.station}, label {fs.fire.label}')
                return
        if all(fs.result == LaserPoll.DONE or fs.rejected for fs in run.fires):
            self._start_phase(Phase.POST_DELAY)

    def _ph_post_delay(self):
        run = self.run
        if self.now - run.phase_t0 < run.job.post_mark_delay_s:
            return
        if self.cfg.zair.during_mark:
            self.hal.set_output('zair', False)
        stop = run.plan.stops[run.stop_index]
        self._start_phase(Phase.CUT_EXTEND if stop.cut is not None else Phase.NEXT)

    def _ph_cut_extend(self):
        run, k = self.run, self.cfg.knife
        if not run.phase_started:
            if self.snap.moving:
                return
            self.hal.set_output('knife_extend', True)
            run.phase_started = True
            run.phase_t0 = self.now
            return
        if self.snap.knife_extended:
            self._cycle('knife_extend', self.now - run.phase_t0)
            self._start_phase(Phase.CUT_DWELL)
        elif self.now - run.phase_t0 > k.extend_timeout_s:
            self._event_alarm(CODES['KNIFE_EXTEND_TIMEOUT'], f'after {k.extend_timeout_s:g} s')
            self.hal.set_output('knife_retract', True)   # safe retract

    def _ph_cut_dwell(self):
        if self.now - self.run.phase_t0 >= self.cfg.knife.dwell_s:
            self._start_phase(Phase.CUT_RETRACT)

    def _ph_cut_retract(self):
        run, k = self.run, self.cfg.knife
        if not run.phase_started:
            self.hal.set_output('knife_retract', True)
            run.phase_started = True
            run.phase_t0 = self.now
            return
        if self.snap.knife_retracted:
            self._cycle('knife_retract', self.now - run.phase_t0)
            if not k.hold_retract_energized:
                self.hal.set_output('knife_retract', False)
            self._cut_done()
            self._start_phase(Phase.NEXT)
        elif self.now - run.phase_t0 > k.retract_timeout_s:
            self._event_alarm(CODES['KNIFE_RETRACT_TIMEOUT'], f'after {k.retract_timeout_s:g} s')

    def _ph_next(self):
        run = self.run
        run.stop_index += 1
        if run.stop_index >= len(run.plan.stops):
            self._goto(State.COMPLETING)
        else:
            self._start_phase(Phase.FEED)

    # --------------------------------------------------------------- bookkeeping
    def _label_fire_done(self, fire: Fire, rejected: bool = False) -> None:
        run = self.run
        self._emit('MARK' if not rejected else 'REJECT', label=fire.label, station=fire.station,
                   belt_coord=fire.label * run.job.pitch_mm,
                   detail='' if not rejected else 'laser timeout: rejected')
        if rejected:
            self._reject_label(fire.label, 'laser', emit=False)
        rem = run.label_remaining.get(fire.label, 0) - 1
        run.label_remaining[fire.label] = rem
        if rem == 0:
            run.marks_done += 1
            self.counters.total_marks += 1
            self.oee.add_labels(1, run.plan.ideal_cycle_s)

    def _reject_label(self, label: int, why: str, emit: bool = True) -> None:
        run = self.run
        if run is None or label in run.rejected_labels:
            return
        run.rejected_labels.add(label)
        run.rejects += 1
        self.oee.add_rejects(1)
        if emit:
            self._emit('REJECT', label=label, detail=why)

    def _cut_done(self) -> None:
        run = self.run
        cut = run.plan.stops[run.stop_index].cut
        self.counters.knife_cycles += 1
        self.counters.blade_cycles += 1
        self._check_blade()
        if not cut.trim:
            run.pieces_cut += 1
            self.counters.total_pieces += 1
            if self.cfg.knife.ejector_enabled:
                self.hal.pulse_output('dc_motor', self.cfg.knife.eject_ms)
        self._emit('CUT', label=cut.after_label, belt_coord=cut.belt_coord_mm,
                   length=cut.labels_in_piece * run.job.pitch_mm,
                   labels_in_piece=cut.labels_in_piece, detail='trim' if cut.trim else '')

    def _check_blade(self) -> None:
        life = self.cfg.knife.blade_life_cycles
        if life > 0 and self.counters.blade_cycles >= life and not self._blade_warned:
            self._blade_warned = True
            self._event_alarm(CODES['KNIFE_BLADE_LIFE'], f'{self.counters.blade_cycles} cycles')

    def reset_blade_counter(self) -> None:
        self.counters.blade_cycles = 0
        self._blade_warned = False
        self.alarms.clear(CODES['KNIFE_BLADE_LIFE'], self.now)

    def _end_job(self, final: State, message: str = '') -> None:
        run = self.run
        if run is None:
            return
        run.t_end = self.now
        run.final_state = final
        if message and not run.message:
            run.message = message
        if final in (State.COMPLETE, State.STOPPED, State.ABORTED):
            self._emit('JOB_END', detail=final.name)
        self.last_run = run
        self.run = None
        if self.on_job_end is not None:
            self.on_job_end(run)

    def _emit(self, kind: str, label: int = 0, station: int = 0, belt_coord: float = 0.0,
              length: float = 0.0, labels_in_piece: int = 0, detail: str = '') -> None:
        run = self.run
        ev = {'type': kind, 'job_id': run.job.job_id if run else '', 'label': label,
              'station': station, 'belt_coord_mm': belt_coord,
              'feed_mm': self._feed_pos() if run else self.snap.position_mm,
              'length_mm': length, 'labels_in_piece': labels_in_piece, 'detail': detail,
              't': self.now}
        if self.on_event is not None:
            self.on_event(ev)

    def _cycle(self, kind: str, seconds: float) -> None:
        if self.on_cycle is not None:
            self.on_cycle(kind, seconds)

    def _account(self, dt: float) -> None:
        self.counters.uptime_s += dt
        self.oee.add_time(self.state.name, dt, self.run is not None)
        pos = self.snap.position_mm
        if self._last_pos is not None and self.snap.link_ok:
            self.counters.belt_mm += abs(pos - self._last_pos)
        self._last_pos = pos

    def _ensure_drive(self) -> None:
        if not self.snap.stepper_enabled:
            self.hal.enable_drive(True)

    # ------------------------------------------------------------------- manual
    def _tick_manual(self) -> None:
        t = self.manual
        if t is None or t.done:
            return
        s, k = self.snap, self.cfg.knife
        if t.kind == 'jog':
            if self.hal.motion_done(t.motion_id):
                self._finish_manual(True, 'done')
            elif self.now > t.deadline:
                self.hal.stop()
                self._finish_manual(False, 'jog timeout')
        elif t.kind == 'cut':
            if t.step == 'start':
                self.hal.set_output('knife_extend', True)
                t.step, t.deadline = 'extend', self.now
            elif t.step == 'extend':
                if s.knife_extended:
                    t.result['extend_time_s'] = self.now - t.deadline
                    t.step, t.deadline = 'dwell', self.now
                elif self.now - t.deadline > k.extend_timeout_s:
                    self.hal.set_output('knife_retract', True)
                    self._finish_manual(False, 'knife extend timeout')
                    self._event_alarm(CODES['KNIFE_EXTEND_TIMEOUT'], 'manual cut')
            elif t.step == 'dwell':
                if self.now - t.deadline >= k.dwell_s:
                    self.hal.set_output('knife_retract', True)
                    t.step, t.deadline = 'retract', self.now
            elif t.step == 'retract':
                if s.knife_retracted:
                    t.result['retract_time_s'] = self.now - t.deadline
                    self.counters.knife_cycles += 1
                    self.counters.blade_cycles += 1
                    self._check_blade()
                    self._cycle('knife_extend', t.result['extend_time_s'])
                    self._cycle('knife_retract', t.result['retract_time_s'])
                    self._finish_manual(True, 'cut done')
                elif self.now - t.deadline > k.retract_timeout_s:
                    self._finish_manual(False, 'knife retract timeout')
                    self._event_alarm(CODES['KNIFE_RETRACT_TIMEOUT'], 'manual cut')
        elif t.kind == 'laser':
            res = t.laser.poll_done(self.now)
            if not t.wait_done and self.now - t.t0 >= self.cfg.laser.pulse_ms / 1000.0:
                self._finish_manual(True, 'triggered')
            elif res.status == LaserPoll.DONE:
                t.result['busy_time_s'] = res.busy_time_s
                self._finish_manual(True, f'done in {res.busy_time_s:.2f} s')
            elif res.status in (LaserPoll.NO_ACK, LaserPoll.TIMEOUT):
                self._finish_manual(False, f'laser {res.status.value}')

    def _finish_manual(self, ok: bool, message: str) -> None:
        t = self.manual
        t.done, t.ok, t.message = True, ok, message
        self._log(f'manual {t.kind}: {message}')

    # ------------------------------------------------------------------- lights
    def light_request(self) -> tuple:
        red = self.state in (State.ABORTING, State.ABORTED) or \
            any(a.definition.severity >= Severity.ERROR for a in self.alarms.alarms.values())
        yellow = self.state in (State.HOLDING, State.HELD, State.UNHOLDING, State.STOPPING,
                                State.RESETTING, State.STARTING, State.COMPLETING,
                                State.COMPLETE, State.CLEARING) or \
            self.mode in (Mode.MANUAL, Mode.MAINTENANCE) or \
            any(a.definition.severity == Severity.WARNING for a in self.alarms.alarms.values())
        green = self.state == State.EXECUTE
        buzzer = self.alarms.unacked(Severity.ERROR) and any(
            a.active for a in self.alarms.alarms.values()
            if a.definition.severity >= Severity.ERROR)
        return red, yellow, green, buzzer

    def _lights_update(self) -> None:
        req = self.light_request()
        if req == self._lights or not self.snap.link_ok:
            return
        if self.snap.fault_flags & FAULT_HEARTBEAT_LOST:
            return   # firmware owns the outputs in its fail-safe state
        self._lights = req
        for name, on in zip(('light_red', 'light_yellow', 'light_green', 'buzzer'), req):
            self.hal.set_output(name, on)

    def _log(self, text: str) -> None:
        self.log.append(f'{self.now:10.3f} {text}')
        if len(self.log) > 2000:
            del self.log[:1000]

    # ------------------------------------------------------------------ status
    def _progress(self, run: Optional[JobRun]) -> float:
        if run is None:
            return 0.0
        if run is self.run or run.final_state != State.COMPLETE:
            return run.progress
        return 1.0

    def status(self) -> dict:
        run = self.run or self.last_run
        red, yellow, green, buzzer = self.light_request()
        return {
            'state': self.state, 'mode': self.mode,
            'job_id': run.job.job_id if run else '', 'recipe': run.job.recipe if run else '',
            'phase': self.run.phase.value if self.run else '',
            'marks_done': run.marks_done if run else 0,
            'marks_total': run.job.quantity if run else 0,
            'pieces_cut': run.pieces_cut if run else 0,
            'rejects': run.rejects if run else 0,
            'progress': self._progress(run),
            'job_elapsed_s': ((run.t_end or self.now) - run.t_start) if run else 0.0,
            'belt_position_mm': self._feed_pos() if self.run else self.snap.position_mm,
            'belt_speed_mm_s': self.snap.velocity_mm_s,
            'belt_width_mm': run.job.belt_width_mm if run else 0.0,
            'lights': (red, yellow, green, buzzer),
        }


def alarm_definition(code: int):
    return CATALOG.get(code)
