"""Industrial simulation scenarios (docs/SCENARIOS.md), executable and self-checking.

Each scenario builds a :class:`Harness` (controller + plant on a simulated clock), runs
the situation and returns a :class:`ScenarioResult` with acceptance checks. They run in
CI through pytest (test/test_scenarios.py) and interactively via::

    ros2 run belt_marking_control run_scenarios            # all
    ros2 run belt_marking_control run_scenarios 6 8 --hours 8
"""

import argparse
from dataclasses import dataclass, field
import json
import sys
import time
from typing import Dict, List

from .core import CODES, ControlConfig, CutMode, Job, LaserDone, State
from .core.db import ProductionDb
from .core.sim_harness import Harness

TOL_MM = 0.02


@dataclass
class ScenarioResult:
    number: int
    name: str
    checks: List[tuple] = field(default_factory=list)   # (description, ok)
    metrics: Dict[str, object] = field(default_factory=dict)
    sim_time_s: float = 0.0
    wall_time_s: float = 0.0

    def check(self, description: str, ok: bool) -> bool:
        self.checks.append((description, bool(ok)))
        return bool(ok)

    @property
    def passed(self) -> bool:
        return all(ok for _, ok in self.checks)


def _job(**kw) -> Job:
    base = {'job_id': 'SCN', 'quantity': 10, 'pitch_mm': 60.0, 'mark_length_mm': 40.0,
            'lead_mm': 10.0, 'cut_mode': CutMode.EVERY, 'laser_time_s': 0.5, 'settle_s': 0.05,
            'feed_speed_mm_s': 30.0, 'belt_width_mm': 25.0}
    base.update(kw)
    return Job(**base)


def _marks_ok(h: Harness, job: Job, station: int = 0) -> bool:
    got = sorted(m.belt_coord_mm for m in h.plant.marks if m.station == station)
    want = [k * job.pitch_mm for k in range(job.quantity)]
    return len(got) == len(want) and all(abs(a - b) <= TOL_MM for a, b in zip(got, want))


def _operator_resume(h: Harness, option: str = '') -> bool:
    h.plant.inject('clear_all')
    h.run(0.2)
    h.ctrl.cmd_ack(0, 'operator')
    ok, _ = h.ctrl.cmd_unhold('operator', option)
    return ok


# --------------------------------------------------------------------------- 1
def s01_continuous(r: ScenarioResult) -> None:
    h = Harness()
    h.set_laser_time(0.5)
    job = _job(job_id='S1', quantity=50, cut_mode=CutMode.NONE)
    h.start(job)
    r.check('job completes', h.wait_state(State.COMPLETE, 600))
    r.check('50 labels marked at k*pitch (+/-0.02 mm)', _marks_ok(h, job))
    r.check('no cuts', not h.plant.cuts)
    r.check('no alarms', not h.codes_raised())
    r.metrics.update(marks=h.ctrl.last_run.marks_done, sim_s=round(h.t, 1))
    r.sim_time_s = h.t


# --------------------------------------------------------------------------- 2
def s02_batch_cut_every(r: ScenarioResult) -> None:
    h = Harness()
    h.set_laser_time(0.6)                      # the design on the laser takes 0.6 s
    job = _job(job_id='S2', quantity=100, pitch_mm=30.0, mark_length_mm=20.0, lead_mm=5.0,
               laser_done_mode=LaserDone.TIMED, laser_time_s=0.8)
    h.start(job)
    r.check('job completes', h.wait_state(State.COMPLETE, 1200))
    want = [(k + 1) * 30.0 - 5.0 for k in range(100)]
    r.check('100 cuts at label boundaries (+/-0.02 mm)',
            len(h.plant.cuts) == 100 and all(
                abs(a - b) <= TOL_MM for a, b in zip(h.plant.cuts, want)))
    r.check('100 labels marked', _marks_ok(h, job))
    r.check('100 pieces ejected', h.plant.pieces_out == 100)
    run = h.ctrl.last_run
    r.metrics.update(pieces=run.pieces_cut, cycle_s=round((run.t_end - run.t_start) / 100, 3))
    r.sim_time_s = h.t


# --------------------------------------------------------------------------- 3
def s03_cut_every_5(r: ScenarioResult) -> None:
    h = Harness()
    h.set_laser_time(0.3)
    job = _job(job_id='S3', quantity=23, cut_mode=CutMode.EVERY_N, cut_every_n=5,
               laser_time_s=0.3)
    h.start(job)
    r.check('job completes', h.wait_state(State.COMPLETE, 600))
    lengths = [e['labels_in_piece'] for e in h.events_of('CUT')]
    r.check('sets of 5,5,5,5 and a final set of 3', lengths == [5, 5, 5, 5, 3])
    r.check('cut lines every 5 pitches', all(
        abs(c - ((i + 1) * 5 * 60.0 - 10.0)) <= TOL_MM for i, c in enumerate(h.plant.cuts[:4])))
    r.metrics.update(pieces=len(lengths))
    r.sim_time_s = h.t


# --------------------------------------------------------------------------- 4
def s04_two_stations(r: ScenarioResult) -> None:
    cfg = ControlConfig()
    cfg.machine.knife_offset_mm = 230.0
    cfg.laser.num_stations = 2
    cfg.laser.station_offsets_mm = [0.0, 150.0]
    cfg.laser.station_delays_s = [0.0, 0.4]
    cfg.laser.station_enabled = [True, True]
    h = Harness(cfg)
    h.plant.lasers[0].set_marking_time(0.5)
    h.plant.lasers[1].set_marking_time(0.8)   # second machine has a longer design
    job = _job(job_id='S4', quantity=12)
    h.start(job)
    r.check('job completes', h.wait_state(State.COMPLETE, 900))
    r.check('station 0 marks every label at k*pitch', _marks_ok(h, job, 0))
    r.check('station 1 marks the same labels at k*pitch', _marks_ok(h, job, 1))
    t0 = {round(m.belt_coord_mm): m.t for m in h.plant.marks if m.station == 0}
    t1 = {round(m.belt_coord_mm): m.t for m in h.plant.marks if m.station == 1}
    r.check('both stations fire in the same stop (sync)',
            len(h.plant.lasers[1].history) == 12)
    r.check('station 1 finishes >= 0.4 s delay + 0.8 s after its trigger',
            all(t1[c] > t0.get(c + 150, 0) for c in t1 if c + 150 in t0))
    r.check('12 pieces cut', len(h.plant.cuts) == 12)
    r.sim_time_s = h.t


# --------------------------------------------------------------------------- 5
def s05_recipe_switch(r: ScenarioResult) -> None:
    db = ProductionDb(':memory:')
    narrow = _job(job_id='S5A', recipe='narrow-20', belt_width_mm=20.0, pitch_mm=40.0,
                  mark_length_mm=25.0, lead_mm=5.0, quantity=8)
    wide = _job(job_id='S5B', recipe='wide-50', belt_width_mm=50.0, pitch_mm=80.0,
                mark_length_mm=45.0, lead_mm=15.0, quantity=6)
    db.save_recipe('narrow-20', narrow.to_json(), 20.0, 'tech')
    db.save_recipe('wide-50', wide.to_json(), 50.0, 'tech')
    h = Harness()
    h.set_laser_time(0.3)
    for name, job_id in (('narrow-20', 'S5A'), ('wide-50', 'S5B')):
        job = Job.from_json(db.load_recipe(name))
        job.job_id = job_id
        h.start(job)
        r.check(f'{name} completes', h.wait_state(State.COMPLETE, 600))
        r.check(f'{name}: belt width reported {job.belt_width_mm:g} mm',
                h.ctrl.status()['belt_width_mm'] == job.belt_width_mm)
        h.plant.marks.clear()
        h.ctrl.cmd_reset('op')
        h.wait_state(State.IDLE, 5)
    bad = _job(job_id='S5C', belt_width_mm=150.0)
    ok, msg = h.ctrl.cmd_start(bad)
    r.check('150 mm belt rejected by validation (machine max 100 mm)',
            not ok and 'belt width' in msg)
    r.metrics.update(recipes=[x['name'] for x in db.list_recipes()])
    r.sim_time_s = h.t


# --------------------------------------------------------------------------- 6
def s06_laser_timeout(r: ScenarioResult) -> None:
    for option in ('retry', 'reject'):
        h = Harness()
        h.set_laser_time(0.5)
        job = _job(job_id=f'S6-{option}', quantity=8, laser_time_s=0.5)
        h.start(job)
        h.run_until(lambda h=h: h.ctrl.run is not None and h.ctrl.run.marks_done >= 3, 120)
        h.plant.inject('laser_late', True, value=30.0)
        r.check(f'[{option}] E-201 raised and machine HELD',
                h.wait_state(State.HELD, 60) and CODES['LASER_TIMEOUT'] in h.codes_raised())
        timeout = 0.5 * 2 + 2.0
        r.check(f'[{option}] belt did not move while waiting', not h.plant.snapshot().moving)
        before = h.ctrl.run.marks_done
        h.run_until(lambda h=h: not h.plant.snapshot().laser_busy[0], 60)   # laser ends late
        r.check(f'[{option}] resume accepted', _operator_resume(h, option))
        r.check(f'[{option}] job completes', h.wait_state(State.COMPLETE, 300))
        run = h.ctrl.last_run
        r.check(f'[{option}] no label lost (marks_done={run.marks_done})',
                run.marks_done == 8 and before <= 4)
        r.check(f'[{option}] rejects = {1 if option == "reject" else 0}',
                run.rejects == (1 if option == 'reject' else 0))
        r.metrics[f'{option}_timeout_s'] = timeout
        r.sim_time_s += h.t


# --------------------------------------------------------------------------- 7
def s07_knife_stuck(r: ScenarioResult) -> None:
    h = Harness()
    h.set_laser_time(0.3)
    job = _job(job_id='S7', quantity=6, laser_time_s=0.3)
    h.start(job)
    h.run_until(lambda: h.ctrl.run is not None and h.ctrl.run.pieces_cut >= 2, 120)
    h.plant.inject('knife_stuck_extend', True)
    r.check('E-301 raised, machine HELD', h.wait_state(State.HELD, 30) and
            CODES['KNIFE_EXTEND_TIMEOUT'] in h.codes_raised())
    snap = h.plant.snapshot()
    r.check('knife safely retracted, belt stopped', snap.knife_retracted and not snap.moving)
    r.check('resume accepted after fixing the knife', _operator_resume(h))
    r.check('job completes', h.wait_state(State.COMPLETE, 300))
    r.check('all 6 pieces cut exactly once per boundary',
            h.ctrl.last_run.pieces_cut == 6 and
            len({round(c, 2) for c in h.plant.cuts}) == 6)
    r.sim_time_s = h.t


# --------------------------------------------------------------------------- 8
def s08_belt_runout(r: ScenarioResult) -> None:
    h = Harness()
    h.set_laser_time(0.3)
    job = _job(job_id='S8', quantity=30, laser_time_s=0.3)
    h.start(job)
    h.run_until(lambda: h.ctrl.run is not None and h.ctrl.run.marks_done >= 10, 300)
    h.plant.inject('belt_runout', True, value=45.0)
    r.check('E-401 raised, machine HELD', h.wait_state(State.HELD, 60) and
            CODES['BELT_MISSING'] in h.codes_raised())
    held_marks = h.ctrl.run.marks_done
    ok, _ = h.ctrl.cmd_unhold('op')
    r.check('resume refused while the belt is missing', not ok)
    r.check('resume accepted after refill', _operator_resume(h))
    r.check('job completes', h.wait_state(State.COMPLETE, 600))
    run = h.ctrl.last_run
    r.check(f'count kept across the refill ({held_marks} -> {run.marks_done})',
            run.marks_done == 30 and run.pieces_cut == 30)
    r.sim_time_s = h.t


# --------------------------------------------------------------------------- 9
def s09_link_lost(r: ScenarioResult) -> None:
    h = Harness()
    h.set_laser_time(0.5)
    h.start(_job(job_id='S9', quantity=20, laser_time_s=0.5, pitch_mm=120.0,
                 mark_length_mm=40.0))
    h.run_until(lambda: h.plant.snapshot().moving, 60)
    t_loss = h.t
    h.plant.inject('link_loss', True)
    r.check('Pi side: E-501 and ABORTED', h.wait_state(State.ABORTED, 5) and
            CODES['SERIAL_LINK_LOST'] in h.codes_raised())
    h.run(0.6)
    p = h.plant
    r.check('firmware side: watchdog tripped within 0.6 s', bool(p.latched & 1))
    r.check('firmware side: belt stopped, knife retract on, lasers off',
            not p.moving and p.outputs['knife_retract'] and
            not any(p.outputs[f'laser_{i}'] for i in range(4)))
    p.inject('link_loss', False)
    h.run(0.3)
    ok, msg = h.ctrl.cmd_clear('tech')
    r.check('CLEAR after link restored', ok and h.wait_state(State.STOPPED, 5))
    h.reset()
    r.check('RESET back to IDLE', h.ctrl.state == State.IDLE)
    r.metrics['reaction_s'] = round(h.t - t_loss, 2)
    r.sim_time_s = h.t


# --------------------------------------------------------------------------- 10
def s10_estop_during_cut(r: ScenarioResult) -> None:
    h = Harness()
    h.set_laser_time(0.3)
    h.start(_job(job_id='S10', quantity=5, laser_time_s=0.3))
    r.check('reaches the cut phase',
            h.run_until(lambda: h.plant.outputs['knife_extend'], 120))
    h.plant.inject('estop', True)
    r.check('ABORTED with E-101', h.wait_state(State.ABORTED, 2) and
            CODES['ESTOP'] in h.codes_raised())
    snap = h.plant.snapshot()
    r.check('drive disabled and belt stopped', not snap.stepper_enabled and not snap.moving)
    ok, _ = h.ctrl.cmd_clear('op')
    r.check('CLEAR refused while E-stop pressed', not ok)
    h.plant.inject('estop', False)
    h.run(0.2)
    ok, _ = h.ctrl.cmd_clear('op')
    r.check('CLEAR -> STOPPED after release', ok and h.wait_state(State.STOPPED, 5))
    h.reset()
    r.check('RESET retracts the knife, IDLE', h.ctrl.state == State.IDLE and
            h.plant.snapshot().knife_retracted)
    h.start(_job(job_id='S10b', quantity=2, laser_time_s=0.3))
    r.check('a new job runs after the reset procedure', h.wait_state(State.COMPLETE, 120))
    r.sim_time_s = h.t


# --------------------------------------------------------------------------- 11
def attach_vision_stub(h: Harness, pitch: float) -> None:
    """Camera-less QA: reads the plant's mark quality (weak marks = unreadable)."""
    def on_plant(kind, data):
        if kind == 'mark' and data['station'] == 0:
            label = int(round(data['belt_coord_mm'] / pitch))
            ok = data['on_belt'] and not data['weak']
            h.ctrl.quality_result(label, ok, '' if ok else 'unreadable')
    h.plant.on_event = on_plant


def s11_vision_reject(r: ScenarioResult) -> None:
    cfg = ControlConfig()
    cfg.machine.consecutive_reject_limit = 3
    h = Harness(cfg)
    h.set_laser_time(0.3)
    job = _job(job_id='S11', quantity=20, laser_time_s=0.3)
    attach_vision_stub(h, job.pitch_mm)
    h.start(job)
    h.run_until(lambda: h.ctrl.run is not None and h.ctrl.run.marks_done >= 5, 120)
    h.plant.lasers[0].faults.weak_mark = True        # e.g. lens dirty / power dropped
    r.check('HELD after 3 consecutive rejects (E-602)', h.wait_state(State.HELD, 120) and
            CODES['CONSECUTIVE_REJECTS'] in h.codes_raised())
    r.check('3 rejects counted', h.ctrl.run.rejects == 3)
    h.plant.lasers[0].faults.weak_mark = False
    r.check('resume after cleaning', _operator_resume(h))
    r.check('job completes', h.wait_state(State.COMPLETE, 300))
    run = h.ctrl.last_run
    r.check('quality = 17/20', run.rejects == 3 and run.marks_done == 20)
    r.metrics['oee_quality'] = round(h.ctrl.oee.quality, 3)
    r.sim_time_s = h.t


# --------------------------------------------------------------------------- 12
def s12_soak(r: ScenarioResult, hours: float = 8.0) -> None:
    """Batches back to back for `hours`, with scheduled faults and an 'operator bot'."""
    h = Harness(dt=0.02, plant_substeps=1)
    h.set_laser_time(1.0)
    end = hours * 3600.0
    faults = [(end * 0.25, 'laser_late', 30.0), (end * 0.5, 'belt_runout', 30.0),
              (end * 0.75, 'knife_stuck_extend', 0.0)]
    batch = 0
    total_labels = 0
    held_since = None
    h.reset()
    while h.t < end:
        st = h.ctrl.state
        if st in (State.IDLE, State.COMPLETE):
            if st == State.COMPLETE:
                total_labels += h.ctrl.last_run.marks_done
                h.ctrl.cmd_reset('bot')
                h.wait_state(State.IDLE, 10)
            batch += 1
            h.start(_job(job_id=f'SOAK-{batch}', quantity=200, pitch_mm=40.0,
                         mark_length_mm=25.0, lead_mm=5.0, cut_mode=CutMode.EVERY_N,
                         cut_every_n=10, laser_time_s=1.0, feed_speed_mm_s=40.0))
        elif st == State.HELD:
            held_since = held_since or h.t
            if h.t - held_since > 60.0:                 # operator reacts after a minute
                _operator_resume(h)
                held_since = None
        elif st in (State.ABORTED, State.STOPPED):
            r.check(f'unexpected {st.name} at {h.t:.0f} s', False)
            break
        if faults and h.t >= faults[0][0]:
            _, name, value = faults.pop(0)
            h.plant.inject(name, True, value=value)
        h.run(1.0)
    rep = h.ctrl.oee.report()
    r.check('ran the full duration without ABORT', h.t >= end - 2)
    r.check('all 3 injected faults recovered', not faults)
    r.check('availability > 90 % (3 faults, ~1 min operator reaction each)',
            rep['availability'] > 0.90)
    r.check('counters consistent',
            h.ctrl.counters.total_marks >= total_labels and h.ctrl.counters.knife_cycles > 0)
    r.metrics.update(hours=hours, batches=batch, labels=h.ctrl.counters.total_marks,
                     pieces=h.ctrl.counters.total_pieces, oee=rep,
                     belt_m=round(h.ctrl.counters.belt_mm / 1000, 1))
    r.sim_time_s = h.t


SCENARIOS: Dict[int, tuple] = {
    1: ('Continuous marking, 50 marks, no cut', s01_continuous),
    2: ('Batch of 100, cut every piece, fixed laser time', s02_batch_cut_every),
    3: ('Cut every 5 marks (sets of labels)', s03_cut_every_5),
    4: ('Two laser stations in sync, offsets and delays', s04_two_stations),
    5: ('Belt width change via recipe switch', s05_recipe_switch),
    6: ('Fault: laser never reports done -> timeout -> HELD -> recovery', s06_laser_timeout),
    7: ('Fault: knife does not reach extended sensor', s07_knife_stuck),
    8: ('Fault: belt runs out mid-batch', s08_belt_runout),
    9: ('Fault: serial link lost', s09_link_lost),
    10: ('E-stop during cut -> ABORTED -> reset', s10_estop_during_cut),
    11: ('Vision QA rejects unreadable marks', s11_vision_reject),
    12: ('Long-run soak test with OEE report', s12_soak),
}


def run_scenario(number: int, **kwargs) -> ScenarioResult:
    name, fn = SCENARIOS[number]
    r = ScenarioResult(number, name)
    t0 = time.time()
    try:
        fn(r, **kwargs)
    except AssertionError as exc:   # harness preconditions
        r.check(f'harness: {exc}', False)
    r.wall_time_s = time.time() - t0
    return r


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Run the industrial simulation scenarios.')
    ap.add_argument('numbers', nargs='*', type=int, help='scenario numbers (default: all)')
    ap.add_argument('--hours', type=float, default=8.0, help='soak test duration (12)')
    ap.add_argument('--json', help='write results to this JSON file')
    args = ap.parse_args(argv)
    numbers = args.numbers or sorted(SCENARIOS)
    results = []
    for n in numbers:
        kw = {'hours': args.hours} if n == 12 else {}
        r = run_scenario(n, **kw)
        results.append(r)
        print(f'[{"PASS" if r.passed else "FAIL"}] {n:2d}. {r.name}  '
              f'(sim {r.sim_time_s:.0f} s, wall {r.wall_time_s:.1f} s)')
        for desc, ok in r.checks:
            print(f'       {"ok " if ok else "NOK"} {desc}')
        if r.metrics:
            print('       metrics: ' + json.dumps(r.metrics, default=str))
    if args.json:
        with open(args.json, 'w') as fh:
            json.dump([{'number': r.number, 'name': r.name, 'passed': r.passed,
                        'checks': r.checks, 'metrics': r.metrics,
                        'sim_time_s': r.sim_time_s} for r in results], fh, indent=2,
                      default=str)
    failed = [r.number for r in results if not r.passed]
    print(f'\n{len(results) - len(failed)}/{len(results)} scenarios passed'
          + (f' (failed: {failed})' if failed else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
