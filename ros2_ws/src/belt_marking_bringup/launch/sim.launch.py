"""Full simulation: plant model + control + (Gazebo twin) + RViz + operator UI.

    ros2 launch belt_marking_bringup sim.launch.py                 # everything
    ros2 launch belt_marking_bringup sim.launch.py gazebo:=false   # no Gazebo (fast, CI)
    ros2 launch belt_marking_bringup sim.launch.py rviz:=false ui:=false headless:=true
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
    return build(LaunchConfiguration('config').perform(context), [overlay] if overlay else [],
                 use_sim=True, gazebo=_truthy(context, 'gazebo'), rviz=_truthy(context, 'rviz'),
                 ui=_truthy(context, 'ui'), vision=_truthy(context, 'vision'),
                 headless=_truthy(context, 'headless'))


def generate_launch_description():
    share = get_package_share_directory('belt_marking_bringup')
    return LaunchDescription([
        DeclareLaunchArgument('config', default_value=os.path.join(share, 'config',
                                                                   'machine.yaml')),
        DeclareLaunchArgument('overlay', default_value=''),
        DeclareLaunchArgument('gazebo', default_value='true'),
        DeclareLaunchArgument('rviz', default_value='true'),
        DeclareLaunchArgument('ui', default_value='true'),
        DeclareLaunchArgument('vision', default_value='true'),
        DeclareLaunchArgument('headless', default_value='false'),
        OpaqueFunction(function=_setup),
    ])
