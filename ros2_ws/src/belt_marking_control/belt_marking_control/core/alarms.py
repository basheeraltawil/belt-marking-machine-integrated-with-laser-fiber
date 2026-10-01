"""Alarm catalogue and alarm manager.

Every alarm has a fixed code, severity and *reaction* (what the state machine does).
The catalogue is the single source for the UI, the operator manual
(docs/OPERATOR_MANUAL.md) and the docs assistant.
"""

from dataclasses import dataclass, field
import enum
from typing import Callable, Dict, List, Optional


class Severity(enum.IntEnum):
    """How serious an alarm is."""
    INFO = 0
    WARNING = 1
    ERROR = 2
    FATAL = 3


class Reaction(enum.IntEnum):
    """What the state machine does."""
    NONE = 0
    HOLD = 1
    STOP = 2
    ABORT = 3


@dataclass(frozen=True)
class AlarmDef:
    """Static description of an alarm (catalogue entry)."""
    code: int
    name: str
    severity: Severity
    reaction: Reaction
    text: str
    remedy: str
    latched: bool = True   # False = clears itself when the condition disappears (no ack)

    @property
    def code_text(self) -> str:
        prefix = 'W' if self.severity <= Severity.WARNING else 'E'
        return f'{prefix}-{self.code}'


S, R = Severity, Reaction
CATALOG: Dict[int, AlarmDef] = {a.code: a for a in [
    # 1xx safety chain (monitored only: the hardwired safety relay acts first)
    AlarmDef(101, 'ESTOP', S.FATAL, R.ABORT, 'Emergency stop pressed',
             'Remove the cause, release the E-stop, press CLEAR, then RESET.'),
    AlarmDef(102, 'DOOR_OPEN', S.ERROR, R.HOLD, 'Laser enclosure door open',
             'Close the laser enclosure door. The laser is inhibited in hardware while open.'),
    AlarmDef(103, 'SAFETY_RELAY', S.FATAL, R.ABORT, 'Safety relay not energised',
             'Check the safety relay, E-stop chain wiring and 24 V supply.'),
    # 2xx laser
    AlarmDef(201, 'LASER_TIMEOUT', S.ERROR, R.HOLD, 'Laser did not finish in time',
             'Check the laser controller screen and job file. Resume with RETRY or REJECT.'),
    AlarmDef(202, 'LASER_BUSY_BEFORE_TRIGGER', S.ERROR, R.HOLD,
             'Laser busy before trigger',
             'Wait until the laser controller is idle; check the busy signal wiring.'),
    AlarmDef(203, 'LASER_NO_ACK', S.ERROR, R.HOLD, 'Laser did not start after trigger',
             'Check that the laser is in foot-switch start mode, the job is loaded, the '
             'pedal relay wiring and the busy signal. Resume with RETRY or REJECT.'),
    # 3xx knife
    AlarmDef(301, 'KNIFE_EXTEND_TIMEOUT', S.ERROR, R.HOLD,
             'Knife did not reach the extended sensor',
             'Check air pressure, knife blade, flow controls and the extended sensor.'),
    AlarmDef(302, 'KNIFE_RETRACT_TIMEOUT', S.FATAL, R.ABORT,
             'Knife did not return to the retracted sensor',
             'Lock out air, free the knife, check the retracted sensor, then CLEAR/RESET.'),
    AlarmDef(303, 'KNIFE_SENSOR_CONFLICT', S.FATAL, R.ABORT,
             'Knife extended and retracted sensors both active',
             'Check the reed sensors positions and wiring.'),
    AlarmDef(304, 'KNIFE_NOT_RETRACTED', S.ERROR, R.HOLD,
             'Knife not retracted before belt move',
             'Check the knife position and the retracted sensor.'),
    # 4xx belt / motion
    AlarmDef(401, 'BELT_MISSING', S.ERROR, R.HOLD, 'No belt at the fork sensor',
             'Load / splice a new belt, align it, then RESUME. Counts are kept.'),
    AlarmDef(402, 'BELT_SLIP', S.ERROR, R.HOLD, 'Belt position mismatch (slip)',
             'Check pinch roller pressure, belt tension and the encoder.'),
    AlarmDef(403, 'DRIVER_FAULT', S.FATAL, R.ABORT, 'Stepper driver fault (DM542 ALM)',
             'Check motor wiring, driver supply and overheating; power-cycle the driver.'),
    AlarmDef(404, 'MOTION_TIMEOUT', S.ERROR, R.HOLD, 'Belt move did not complete in time',
             'Check for a jam or a stalled motor.'),
    # 5xx system
    AlarmDef(501, 'SERIAL_LINK_LOST', S.FATAL, R.ABORT,
             'Communication with the I/O controller lost',
             'Check the USB cable and the Arduino power; the machine stopped safely.'),
    AlarmDef(502, 'LOW_AIR', S.ERROR, R.HOLD, 'Air pressure low',
             'Check compressor, filter-regulator and the pressure switch setting.'),
    AlarmDef(503, 'FIRMWARE_FAULT', S.FATAL, R.ABORT,
             'I/O controller fault (watchdog / heartbeat)',
             'Check the log. CLEAR and RESET to continue.'),
    AlarmDef(504, 'HW_COMMAND_REJECTED', S.ERROR, R.HOLD,
             'Hardware rejected a command (interlock)',
             'Check the alarm detail; usually the knife was not retracted or a fault is set.'),
    # 6xx quality
    AlarmDef(601, 'VISION_REJECT', S.WARNING, R.NONE, 'Label rejected by vision QA',
             'Inspect the label. Counted as reject.', latched=False),
    AlarmDef(602, 'CONSECUTIVE_REJECTS', S.ERROR, R.HOLD, 'Too many consecutive rejects',
             'Check laser focus/power, belt position offset and camera.'),
    # 7xx maintenance
    AlarmDef(701, 'KNIFE_BLADE_LIFE', S.WARNING, R.NONE, 'Knife blade service life reached',
             'Replace the blade and reset the blade counter (Maintenance).'),
    AlarmDef(702, 'CYCLE_DRIFT', S.WARNING, R.NONE, 'Cycle time drift detected',
             'A component is slowing down (knife, laser or feed). Plan maintenance.'),
    AlarmDef(703, 'JOB_INVALID', S.WARNING, R.NONE, 'Job parameters invalid',
             'Correct the job fields shown in the message.', latched=False),
]}
CODES = {a.name: a.code for a in CATALOG.values()}


@dataclass
class AlarmInstance:
    """One occurrence of an alarm with its state."""
    definition: AlarmDef
    detail: str
    raised_at: float
    active: bool = True
    acknowledged: bool = False
    acked_by: str = ''
    cleared_at: Optional[float] = None

    @property
    def code(self) -> int:
        return self.definition.code


@dataclass
class AlarmManager:
    """Keeps the active alarm list. Callbacks feed ROS topics and the DB."""

    on_change: Optional[Callable[[AlarmInstance, str], None]] = None  # (alarm, event)
    alarms: Dict[int, AlarmInstance] = field(default_factory=dict)

    def raise_(self, code: int, now: float, detail: str = '') -> Optional[AlarmInstance]:
        """Raise an alarm; returns None if it is already active."""
        existing = self.alarms.get(code)
        if existing is not None and existing.active:
            return None                           # already active: not a new event
        inst = AlarmInstance(CATALOG[code], detail, now)
        self.alarms[code] = inst
        self._notify(inst, 'raised')
        return inst

    def condition(self, code: int, present: bool, now: float, detail: str = '') \
            -> Optional[AlarmInstance]:
        """Level-triggered alarm: raised while ``present``, becomes inactive otherwise."""
        if present:
            return self.raise_(code, now, detail)
        inst = self.alarms.get(code)
        if inst is not None and inst.active:
            self.clear(code, now)
        return None

    def clear(self, code: int, now: float) -> None:
        """Mark an alarm inactive (it stays listed until acknowledged if latched)."""
        inst = self.alarms.get(code)
        if inst is None or not inst.active:
            return
        inst.active = False
        inst.cleared_at = now
        self._notify(inst, 'cleared')
        if inst.acknowledged or not inst.definition.latched:
            del self.alarms[code]

    def ack(self, code: int = 0, user: str = '') -> int:
        """Acknowledge one code (or all with 0); returns how many."""
        count = 0
        for c, inst in list(self.alarms.items()):
            if code not in (0, c) or inst.acknowledged:
                continue
            inst.acknowledged = True
            inst.acked_by = user
            count += 1
            self._notify(inst, 'acknowledged')
            if not inst.active:
                del self.alarms[c]
        return count

    def ack_inactive(self, user: str = '') -> int:
        """Acknowledge every alarm whose condition has gone (used by RESUME / RESET)."""
        count = 0
        for c, inst in list(self.alarms.items()):
            if not inst.active:
                inst.acknowledged = True
                inst.acked_by = user
                self._notify(inst, 'acknowledged')
                del self.alarms[c]
                count += 1
        return count

    def active(self) -> List[AlarmInstance]:
        """Alarms sorted by severity, then time."""
        return sorted(self.alarms.values(), key=lambda a: (-a.definition.severity, a.raised_at))

    def blocking(self, min_reaction: Reaction = Reaction.HOLD) -> List[AlarmInstance]:
        """Alarms that still prevent (re)starting: condition present."""
        return [a for a in self.alarms.values()
                if a.active and a.definition.reaction >= min_reaction]

    def any_active(self, min_severity: Severity) -> bool:
        return any(a.definition.severity >= min_severity for a in self.alarms.values())

    def unacked(self, min_severity: Severity = Severity.ERROR) -> bool:
        return any(not a.acknowledged and a.definition.severity >= min_severity
                   for a in self.alarms.values())

    def _notify(self, inst: AlarmInstance, event: str) -> None:
        if self.on_change is not None:
            self.on_change(inst, event)
