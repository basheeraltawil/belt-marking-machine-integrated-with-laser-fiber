"""Real machine: serial bridge to the Arduino Mega + control + UI (kiosk on the Pi).

    ros2 launch belt_marking_bringup real.launch.py                      # on the Pi
    ros2 launch belt_marking_bringup real.launch.py overlay:=/etc/belt_marking/site.yaml
"""

import os

from ament_index_python.packages import get_package_share_directory
from belt_marking_bringup.stack import build
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration


def _truthy(context, name):
    return LaunchConfiguration(name).perform(context).lower() in ('1', 'true', 'yes')


def _setup(context):
    overlay = LaunchConfiguration('overlay').perform(context)
    calib = os.path.expanduser('~/.belt_marking/calibration.yaml')
    overlays = [p for p in (calib if os.path.exists(calib) else '', overlay) if p]
    return build(LaunchConfiguration('config').perform(context), overlays, use_sim=False,
                 gazebo=False, rviz=_truthy(context, 'rviz'), ui=_truthy(context, 'ui'),
                 vision=_truthy(context, 'vision'), kiosk=_truthy(context, 'kiosk'))


def generate_launch_description():
    share = get_package_share_directory('belt_marking_bringup')
    return LaunchDescription([
        DeclareLaunchArgument('config', default_value=os.path.join(share, 'config',
                                                                   'machine.yaml')),
        DeclareLaunchArgument('overlay', default_value='',
                              description='site-specific YAML overlay'),
        DeclareLaunchArgument('rviz', default_value='false'),
        DeclareLaunchArgument('ui', default_value='true'),
        DeclareLaunchArgument('kiosk', default_value='false'),
        DeclareLaunchArgument('vision', default_value='false'),
        OpaqueFunction(function=_setup),
    ])
