"""The xacro model must expand for 1..4 stations and contain all animated joints."""

import os
import subprocess
import xml.etree.ElementTree as ET

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
XACRO = os.path.join(HERE, '..', 'urdf', 'belt_marking_machine.urdf.xacro')


def _expand(**args):
    cmd = ['xacro', XACRO] + [f'{k}:={v}' for k, v in args.items()]
    env = dict(os.environ)
    # make $(find belt_marking_description) resolvable from the source tree
    src = os.path.join(HERE, '..', '..')
    env['ROS_PACKAGE_PATH'] = src + ':' + env.get('ROS_PACKAGE_PATH', '')
    try:
        out = subprocess.run(cmd, check=True, capture_output=True, text=True, env=env).stdout
    except FileNotFoundError:
        pytest.skip('xacro not available')
    except subprocess.CalledProcessError as exc:
        if 'belt_marking_description' in exc.stderr and 'not found' in exc.stderr:
            pytest.skip('package not installed (run after colcon build)')
        raise
    return ET.fromstring(out)


@pytest.mark.parametrize('offsets,n', [('0.0', 1), ('0.0 0.35', 2), ('0.0 0.3 0.6 0.9', 4)])
def test_stations(offsets, n):
    root = _expand(station_offsets=offsets, gazebo='true')
    joints = {j.get('name') for j in root.iter('joint')}
    for i in range(n):
        assert f'laser_{i}_head_x' in joints
        assert f'laser_{i}_beam' in joints
    assert 'knife_joint' in joints
    assert 'drive_roller_joint' in joints


def test_belt_width_changes_guides():
    narrow = _expand(belt_width='0.02')
    wide = _expand(belt_width='0.09')

    def guide_y(root):
        for j in root.iter('joint'):
            if j.get('name') == 'guide_l_joint':
                return float(j.find('origin').get('xyz').split()[1])
    assert guide_y(wide) > guide_y(narrow)
