"""Controller + plant model on a simulated clock (no ROS). Used by tests and scenarios."""

from typing import Callable, List, Optional

from belt_marking_hardware.fake_plant import FakePlant, PlantConfig
from belt_marking_hardware.plant_hal import PlantHal

from .config import ControlConfig
from .controller import MachineController, Mode, State
from .job import Job


class Harness:

    def __init__(self, cfg: Optional[ControlConfig] = None,
                 plant_cfg: Optional[PlantConfig] = None, dt: float = 0.01,
                 plant_substeps: int = 2):
        self.cfg = cfg or ControlConfig()
        self.cfg.use_sim = True
        if plant_cfg is None:
            lz = self.cfg.laser
            plant_cfg = PlantConfig(
                station_offsets_mm=list(lz.station_offsets_mm[:lz.num_stations]),
                knife_offset_mm=self.cfg.machine.knife_offset_mm,
                fork_sensor_offset_mm=self.cfg.machine.fork_sensor_offset_mm,
                encoder_enabled=self.cfg.machine.encoder_enabled)
        self.plant = FakePlant(plant_cfg)
        self.hal = PlantHal(self.plant)
        self.dt = dt
        self.substeps = plant_substeps
        self.ctrl = MachineController(self.hal, self.cfg, now=0.0,
                                      accel_mm_s2=plant_cfg.accel_mm_s2,
                                      steps_per_mm=plant_cfg.steps_per_mm)
        self.events: List[dict] = []
        self.alarm_log: List[tuple] = []
        self.ctrl.on_event = self.events.append
        self.ctrl.on_alarm = lambda a, e: self.alarm_log.append(
            (a.definition.code, e, self.plant.t))
        self.hal.heartbeat(0.0)

    @property
    def t(self) -> float:
        return self.plant.t

    def step(self) -> None:
        sub = self.dt / self.substeps
        for _ in range(self.substeps):
            self.plant.step(sub)
        self.ctrl.tick(self.plant.t)

    def run(self, seconds: float) -> None:
        for _ in range(int(round(seconds / self.dt))):
            self.step()

    def run_until(self, pred: Callable[[], bool], timeout: float) -> bool:
        end = self.t + timeout
        while self.t < end:
            self.step()
            if pred():
                return True
        return False

    def wait_state(self, state: State, timeout: float = 30.0) -> bool:
        return self.run_until(lambda: self.ctrl.state == state, timeout)

    # convenience -------------------------------------------------------------
    def reset(self) -> None:
        self.run(0.05)
        ok, msg = self.ctrl.cmd_reset('test')
        assert ok, msg
        assert self.wait_state(State.IDLE, 10), self.ctrl.log[-5:]

    def start(self, job: Job) -> None:
        if self.ctrl.state != State.IDLE:
            self.reset()
        if self.ctrl.mode not in (Mode.AUTO, Mode.SIMULATION):
            self.ctrl.cmd_set_mode(Mode.SIMULATION)
        ok, msg = self.ctrl.cmd_start(job, 'test')
        assert ok, msg

    def set_laser_time(self, seconds: float) -> None:
        for laser in self.plant.lasers:
            laser.set_marking_time(seconds)

    def codes_raised(self) -> List[int]:
        return [c for c, e, _ in self.alarm_log if e == 'raised']

    def events_of(self, kind: str) -> List[dict]:
        return [e for e in self.events if e['type'] == kind]
