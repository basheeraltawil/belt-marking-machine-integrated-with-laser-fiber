import math

from belt_marking_hardware.fake_plant import FakePlant, PlantConfig
from belt_marking_hardware.plant_hal import PlantHal


def make(**kw):
    plant = FakePlant(PlantConfig(**kw))
    hal = PlantHal(plant)
    hal.heartbeat(0)
    hal.enable_drive(True)
    return plant, hal


def run(plant, hal, seconds, dt=0.005):
    for _ in range(int(seconds / dt)):
        hal.heartbeat(plant.t)
        plant.step(dt)


def test_move_is_exact_in_steps():
    plant, hal = make()
    mid = hal.move_relative(123.4, 20.0)
    run(plant, hal, 10)
    assert hal.motion_done(mid)
    assert plant.snapshot().position_steps == round(123.4 * 69.0)
    assert not hal.pop_errors()


def test_move_rejected_when_knife_not_retracted():
    plant, hal = make()
    hal.set_output('knife_extend', True)
    run(plant, hal, 1)
    assert plant.snapshot().knife_extended
    hal.move_relative(10)
    assert any('knife' in e for e in hal.pop_errors())


def test_knife_extend_rejected_while_moving():
    plant, hal = make()
    hal.move_relative(100, 10)
    run(plant, hal, 0.5)
    hal.set_output('knife_extend', True)
    assert any('interlock' in e for e in hal.pop_errors())


def test_knife_cycle_and_cut_record():
    plant, hal = make()
    hal.move_relative(10)
    run(plant, hal, 3)
    hal.set_output('knife_extend', True)
    run(plant, hal, 0.5)
    hal.set_output('knife_retract', True)
    run(plant, hal, 0.5)
    snap = plant.snapshot()
    assert snap.knife_retracted and not snap.knife_extended
    assert plant.knife_cycles == 1
    assert math.isclose(plant.cuts[0], 10 - 56.0, abs_tol=0.02)


def test_watchdog_trips_without_heartbeat():
    plant, hal = make()
    hal.move_relative(500, 10)
    plant.run(1.0)                       # no more heartbeats
    snap = plant.snapshot()
    assert snap.fault_flags & 1
    assert not snap.moving
    assert snap.outputs['knife_retract'] and not snap.outputs['laser_0']


def test_estop_stops_and_disables():
    plant, hal = make()
    hal.move_relative(500, 10)
    run(plant, hal, 0.5)
    plant.inject('estop', True)
    run(plant, hal, 0.1)
    snap = plant.snapshot()
    assert not snap.moving and not snap.stepper_enabled and not snap.estop_ok


def test_belt_runout_fork_sensor():
    plant, hal = make()
    plant.inject('belt_runout', True, value=20.0)
    hal.move_relative(15)
    run(plant, hal, 3)
    assert plant.snapshot().belt_present
    hal.move_relative(10)
    run(plant, hal, 3)
    assert not plant.snapshot().belt_present
    plant.inject('belt_runout', False)
    assert plant.snapshot().belt_present


def test_slip_shows_on_encoder():
    plant, hal = make(encoder_enabled=True)
    plant.inject('belt_slip', True, value=0.1)
    hal.move_relative(100, 20)
    run(plant, hal, 10)
    snap = plant.snapshot()
    assert math.isclose(snap.encoder_mm, 90.0, abs_tol=0.1)
    assert math.isclose(snap.position_mm, 100.0, abs_tol=0.02)


def test_laser_pulse_marks_belt():
    plant, hal = make(laser_marking_time_s=0.5)
    hal.pulse_output('laser_0', 200)
    run(plant, hal, 0.1)
    assert plant.snapshot().laser_busy[0]
    run(plant, hal, 1.0)
    assert not plant.snapshot().laser_busy[0]
    assert len(plant.marks) == 1 and plant.marks[0].belt_coord_mm == 0.0


def test_decelerating_stop():
    plant, hal = make()
    mid = hal.move_relative(1000, 40)
    run(plant, hal, 2)
    hal.stop(quick=False)
    run(plant, hal, 2)
    snap = plant.snapshot()
    assert hal.motion_done(mid)
    assert 10 < snap.position_mm < 1000
