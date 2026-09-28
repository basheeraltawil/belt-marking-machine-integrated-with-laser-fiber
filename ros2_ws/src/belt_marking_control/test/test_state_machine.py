from belt_marking_control.core import CODES, ControlConfig, CutMode, Job, Mode, State
from belt_marking_control.core.sim_harness import Harness
import pytest


def job(**kw):
    base = {'job_id': 'T', 'quantity': 3, 'pitch_mm': 60.0, 'mark_length_mm': 40.0,
            'lead_mm': 10.0, 'cut_mode': CutMode.EVERY, 'laser_time_s': 0.3, 'settle_s': 0.05}
    base.update(kw)
    return Job(**base)


def make():
    h = Harness()
    h.set_laser_time(0.3)
    return h


def test_power_up_stopped_and_reset_to_idle():
    h = make()
    assert h.ctrl.state == State.STOPPED
    ok, _ = h.ctrl.cmd_start(job())
    assert not ok                                   # needs RESET first
    h.reset()
    assert h.ctrl.state == State.IDLE
    assert h.plant.snapshot().stepper_enabled


def test_invalid_job_refused_with_warning():
    h = make()
    h.reset()
    ok, msg = h.ctrl.cmd_start(job(quantity=0))
    assert not ok and 'quantity' in msg
    assert CODES['JOB_INVALID'] in h.codes_raised()
    assert h.ctrl.state == State.IDLE


def test_start_refused_in_manual_mode():
    h = make()
    h.reset()
    assert h.ctrl.cmd_set_mode(Mode.MANUAL)[0]
    ok, msg = h.ctrl.cmd_start(job())
    assert not ok and 'AUTO' in msg


def test_hold_unhold_keeps_position_and_count():
    h = make()
    h.start(job(quantity=6, cut_mode=CutMode.NONE))
    h.run_until(lambda: h.plant.snapshot().moving, 30)
    assert h.ctrl.cmd_hold('op')[0]
    assert h.wait_state(State.HELD, 10)
    assert not h.plant.snapshot().moving
    assert h.ctrl.cmd_unhold('op')[0]
    assert h.wait_state(State.COMPLETE, 120)
    marks = sorted(m.belt_coord_mm for m in h.plant.marks)
    assert marks == pytest.approx([k * 60.0 for k in range(6)], abs=0.02)


def test_stop_ends_job_in_stopped():
    h = make()
    h.start(job(quantity=20))
    h.run(5)
    assert h.ctrl.cmd_stop('op')[0]
    assert h.wait_state(State.STOPPED, 20)
    assert h.ctrl.last_run.final_state == State.STOPPED
    assert h.plant.snapshot().knife_retracted


def test_estop_in_stopped_goes_aborted():
    h = make()
    h.run(0.1)
    h.plant.inject('estop', True)
    h.run(0.1)
    assert h.ctrl.state == State.ABORTED


def test_door_open_blocks_start_and_holds_execute():
    h = make()
    h.reset()
    h.plant.inject('door_open', True)
    h.ctrl.cmd_start(job())
    assert h.wait_state(State.IDLE, 5)
    assert h.ctrl.last_run.final_state == State.IDLE
    h.plant.inject('door_open', False)
    h.start(job(quantity=5))
    h.run(2)
    h.plant.inject('door_open', True)
    assert h.wait_state(State.HELD, 10)
    assert CODES['DOOR_OPEN'] in h.codes_raised()
    assert not h.ctrl.cmd_unhold('op')[0]           # still open
    h.plant.inject('door_open', False)
    h.run(0.1)
    assert h.ctrl.cmd_unhold('op')[0]
    assert h.wait_state(State.COMPLETE, 120)


def test_low_air_holds():
    h = make()
    h.start(job(quantity=5))
    h.run(2)
    h.plant.inject('low_air', True)
    assert h.wait_state(State.HELD, 20)
    assert CODES['LOW_AIR'] in h.codes_raised()


def test_driver_fault_aborts():
    h = make()
    h.start(job(quantity=5))
    h.run(1)
    h.plant.inject('driver_fault', True)
    assert h.wait_state(State.ABORTED, 2)


def test_manual_operations():
    h = make()
    h.reset()
    ok, msg, _ = h.ctrl.manual_jog(10)
    assert not ok and 'MANUAL' in msg               # AUTO mode
    assert h.ctrl.cmd_set_mode(Mode.MANUAL)[0]
    ok, _, task = h.ctrl.manual_jog(12.5)
    assert ok
    h.run_until(lambda: task.done, 10)
    assert task.ok and abs(h.plant.snapshot().position_mm - 12.5) < 0.02
    ok, _, task = h.ctrl.manual_cut()
    h.run_until(lambda: task.done, 5)
    assert task.ok and task.result['extend_time_s'] > 0.2 and h.plant.knife_cycles == 1
    ok, _, task = h.ctrl.manual_laser(0)
    h.run_until(lambda: task.done, 10)
    assert task.ok and len(h.plant.marks) == 1
    ok, msg = h.ctrl.manual_output('zair', True)
    assert not ok and 'MAINTENANCE' in msg
    h.ctrl.cmd_set_mode(Mode.MAINTENANCE)
    assert h.ctrl.manual_output('zair', True)[0]
    assert not h.ctrl.manual_output('knife_extend', True)[0]


def test_jog_in_held_realigns_plan():
    h = make()
    h.start(job(quantity=4, cut_mode=CutMode.NONE))
    h.run_until(lambda: h.ctrl.run.marks_done >= 2, 60)
    h.ctrl.cmd_hold('op')
    h.wait_state(State.HELD, 10)
    ok, _, task = h.ctrl.manual_jog(5.0)
    assert ok
    h.run_until(lambda: task.done, 10)
    h.ctrl.cmd_unhold('op')
    assert h.wait_state(State.COMPLETE, 60)
    coords = sorted(m.belt_coord_mm for m in h.plant.marks)
    # labels after the re-alignment are shifted by the jog distance on the belt
    assert coords[:2] == pytest.approx([0.0, 60.0], abs=0.02)
    assert abs(coords[-1] - (180.0 + 5.0)) < 0.05


def test_light_tower():
    h = make()
    h.reset()
    h.start(job(quantity=5))
    h.run(1.5)
    assert h.plant.outputs['light_green'] and not h.plant.outputs['light_red']
    h.plant.inject('estop', True)
    h.run(0.1)
    assert h.plant.outputs['light_red']


def test_blade_life_warning():
    cfg = ControlConfig()
    cfg.knife.blade_life_cycles = 3
    h = Harness(cfg)
    h.set_laser_time(0.2)
    h.start(job(quantity=4, laser_time_s=0.2))
    h.wait_state(State.COMPLETE, 120)
    assert CODES['KNIFE_BLADE_LIFE'] in h.codes_raised()
    h.ctrl.reset_blade_counter()
    assert h.ctrl.counters.blade_cycles == 0


def test_encoder_slip_detected():
    cfg = ControlConfig()
    cfg.machine.encoder_enabled = True
    h = Harness(cfg)
    h.set_laser_time(0.2)
    h.plant.inject('belt_slip', True, value=0.05)
    h.start(job(quantity=10, laser_time_s=0.2, cut_mode=CutMode.NONE))
    assert h.wait_state(State.HELD, 60)
    assert CODES['BELT_SLIP'] in h.codes_raised()
