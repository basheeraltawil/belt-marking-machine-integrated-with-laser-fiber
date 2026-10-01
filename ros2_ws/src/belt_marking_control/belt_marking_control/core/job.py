"""Job / recipe model and validation."""

from dataclasses import asdict, dataclass, field
import enum
import json
from typing import List, Optional

from .config import ControlConfig


class CutMode(enum.IntEnum):
    """When the knife cuts."""
    NONE = 0        # continuous marking, no cut
    EVERY = 1       # cut after every label
    EVERY_N = 2     # cut after every N labels
    END = 3         # one cut at the end of the batch


class LaserDone(enum.IntEnum):
    """How the end of marking is detected."""
    CONFIG = 0
    SIGNAL = 1
    TIMED = 2


@dataclass
class Station:
    """One laser machine: enabled, position after station 0, extra delay."""
    enabled: bool = True
    offset_mm: float = 0.0
    delay_s: float = 0.0


@dataclass
class Job:
    """A production order (also stored as a recipe)."""
    job_id: str = ''
    recipe: str = ''
    belt_width_mm: float = 25.0
    quantity: int = 10
    pitch_mm: float = 60.0
    mark_length_mm: float = 40.0
    lead_mm: float = 10.0
    cut_mode: CutMode = CutMode.EVERY
    cut_every_n: int = 1
    initial_trim_cut: bool = False
    laser_done_mode: LaserDone = LaserDone.CONFIG
    laser_time_s: float = 3.0
    settle_s: float = 0.1
    post_mark_delay_s: float = 0.0
    feed_speed_mm_s: float = 14.5
    stations: List[Station] = field(default_factory=list)
    mark_text: str = ''

    # ---- derived
    def active_stations(self, cfg: ControlConfig) -> List[tuple]:
        """[(index, offset_mm, delay_s)] of the enabled stations (job or machine default)."""
        if self.stations:
            src = [(i, s.offset_mm, s.delay_s, s.enabled) for i, s in enumerate(self.stations)]
        else:
            lz = cfg.laser
            src = [(i, lz.station_offsets_mm[i], lz.station_delays_s[i], lz.station_enabled[i])
                   for i in range(lz.num_stations)]
        return [(i, off, dly) for i, off, dly, en in src if en]

    def labels_per_piece(self) -> int:
        if self.cut_mode == CutMode.EVERY:
            return 1
        if self.cut_mode == CutMode.EVERY_N:
            return max(1, self.cut_every_n)
        return self.quantity

    def piece_length_mm(self) -> float:
        """Length of one cut piece."""
        return self.pitch_mm * self.labels_per_piece()

    def use_done_signal(self, cfg: ControlConfig) -> bool:
        if self.laser_done_mode == LaserDone.SIGNAL:
            return True
        if self.laser_done_mode == LaserDone.TIMED:
            return False
        return cfg.laser.done_mode == 'signal'

    # ---- (de)serialisation for recipes / DB
    def to_json(self) -> str:
        d = asdict(self)
        d['cut_mode'] = int(self.cut_mode)
        d['laser_done_mode'] = int(self.laser_done_mode)
        return json.dumps(d, sort_keys=True)

    @staticmethod
    def from_json(text: str) -> 'Job':
        d = json.loads(text)
        d['stations'] = [Station(**s) for s in d.get('stations', [])]
        d['cut_mode'] = CutMode(d.get('cut_mode', 1))
        d['laser_done_mode'] = LaserDone(d.get('laser_done_mode', 0))
        known = Job.__dataclass_fields__
        return Job(**{k: v for k, v in d.items() if k in known})


def validate(job: Job, cfg: ControlConfig) -> List[str]:
    """Return a list of human readable problems (empty = OK). Limits come from config."""
    m = cfg.machine
    e = []

    def rng(name, value, lo, hi, unit=''):
        if not (lo <= value <= hi):
            e.append(f'{name} must be between {lo:g} and {hi:g}{unit} (got {value:g})')

    if not job.job_id.strip():
        e.append('job id is empty')
    rng('quantity', job.quantity, 1, m.quantity_max)
    rng('belt width', job.belt_width_mm, m.belt_width_min_mm, m.belt_width_max_mm, ' mm')
    rng('pitch', job.pitch_mm, m.pitch_min_mm, m.pitch_max_mm, ' mm')
    rng('mark length', job.mark_length_mm, 0.1, min(job.pitch_mm, cfg.laser.field_length_mm),
        ' mm')
    rng('lead', job.lead_mm, 0.0, max(0.0, job.pitch_mm - job.mark_length_mm), ' mm')
    rng('feed speed', job.feed_speed_mm_s, 0.5, m.feed_speed_max_mm_s, ' mm/s')
    rng('laser time', job.laser_time_s, 0.05, 600.0, ' s')
    rng('settle time', job.settle_s, 0.0, 10.0, ' s')
    rng('post-mark delay', job.post_mark_delay_s, 0.0, 60.0, ' s')
    if job.cut_mode == CutMode.EVERY_N:
        rng('cut every N', job.cut_every_n, 1, max(1, job.quantity))
    stations = job.active_stations(cfg)
    if not stations:
        e.append('no laser station enabled')
    if len(job.stations) > cfg.laser.num_stations:
        e.append(f'job uses {len(job.stations)} stations, machine has '
                 f'{cfg.laser.num_stations}')
    offsets = [off for _, off, _ in stations]
    if any(off < 0 for off in offsets):
        e.append('station offsets must be >= 0')
    if len({round(o, 3) for o in offsets}) != len(offsets):
        e.append('two stations have the same offset')
    for _, _, dly in stations:
        rng('station delay', dly, 0.0, 60.0, ' s')
    if job.cut_mode != CutMode.NONE:
        limit = m.knife_offset_mm - job.lead_mm
        for i, off, _ in stations:
            if off > limit + 1e-9:
                e.append(f'station {i} at {off:g} mm is past the cut line '
                         f'(knife {m.knife_offset_mm:g} mm - lead {job.lead_mm:g} mm): '
                         f'labels would be cut before this station marks them')
    return e


def job_from_msg(msg) -> Job:
    """belt_marking_interfaces/JobSpec -> Job (duck-typed so tests need no ROS)."""
    return Job(
        job_id=msg.job_id, recipe=msg.recipe, belt_width_mm=msg.belt_width_mm,
        quantity=int(msg.quantity), pitch_mm=msg.pitch_mm, mark_length_mm=msg.mark_length_mm,
        lead_mm=msg.lead_mm, cut_mode=CutMode(msg.cut_mode), cut_every_n=int(msg.cut_every_n),
        initial_trim_cut=bool(msg.initial_trim_cut),
        laser_done_mode=LaserDone(msg.laser_done_mode), laser_time_s=msg.laser_time_s,
        settle_s=msg.settle_s, post_mark_delay_s=msg.post_mark_delay_s,
        feed_speed_mm_s=msg.feed_speed_mm_s,
        stations=[Station(s.enabled, s.offset_mm, s.delay_s) for s in msg.stations],
        mark_text=msg.mark_text,
    )


def job_to_msg(job: Job, msg_type, station_type, target: Optional[object] = None):
    """Job -> belt_marking_interfaces/JobSpec."""
    msg = target if target is not None else msg_type()
    for name in ('job_id', 'recipe', 'belt_width_mm', 'pitch_mm', 'mark_length_mm', 'lead_mm',
                 'laser_time_s', 'settle_s', 'post_mark_delay_s', 'feed_speed_mm_s',
                 'mark_text'):
        current = getattr(msg, name, None)
        value = getattr(job, name)
        setattr(msg, name, type(current)(value) if current is not None else value)
    msg.quantity = int(job.quantity)
    msg.cut_mode = int(job.cut_mode)
    msg.cut_every_n = int(job.cut_every_n)
    msg.initial_trim_cut = bool(job.initial_trim_cut)
    msg.laser_done_mode = int(job.laser_done_mode)
    msg.stations = [station_type(enabled=s.enabled, offset_mm=float(s.offset_mm),
                                 delay_s=float(s.delay_s)) for s in job.stations]
    return msg
