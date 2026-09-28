import os

from belt_marking_bringup import config_loader as cl

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, '..', 'config', 'machine.yaml')
MULTI = os.path.join(HERE, '..', 'config', 'multi_laser.yaml')


def test_control_params_match_control_config():
    from belt_marking_control.core.config import ControlConfig, flatten
    params = cl.control_params(cl.load(CFG), use_sim=True)
    known = set(flatten(ControlConfig()))
    unknown = [k for k in params if k not in known and k not in ('accel_mm_s2', 'steps_per_mm')]
    assert not unknown, f'machine.yaml keys unknown to ControlConfig: {unknown}'
    missing = [k for k in known if k not in params]
    assert not missing, f'ControlConfig keys missing in machine.yaml: {missing}'


def test_multi_laser_overlay():
    cfg = cl.load(CFG, [MULTI])
    assert cl.station_offsets(cfg) == [0.0, 150.0]
    assert cfg['machine']['knife_offset_mm'] == 230.0
    assert cfg['machine']['fork_sensor_offset_mm'] == 350.0      # untouched keys kept
    assert cl.sim_hardware_params(cfg)['station_offsets_mm'] == [0.0, 150.0]
