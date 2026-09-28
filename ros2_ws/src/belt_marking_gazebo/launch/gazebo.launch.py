"""Gazebo Fortress world + machine model + ros_gz bridges + kinematic twin.

Expects ``robot_description`` (xacro with gazebo:=true) to be published by
robot_state_publisher (belt_marking_bringup/sim.launch.py does that).
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction, TimerAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

WORLD_NAME = 'belt_marking'


def _setup(context):
    share = get_package_share_directory('belt_marking_gazebo')
    world = os.path.join(share, 'worlds', 'belt_marking.sdf')
    headless = LaunchConfiguration('headless').perform(context).lower() == 'true'
    n = int(LaunchConfiguration('num_stations').perform(context))
    offsets = [float(v) for v in LaunchConfiguration('station_offsets_mm').perform(context)
               .replace(',', ' ').split()]
    knife = float(LaunchConfiguration('knife_offset_mm').perform(context))
    width = float(LaunchConfiguration('belt_width_mm').perform(context))

    cmd = ['ign', 'gazebo', '-r', world] + (['-s', '--headless-rendering'] if headless else [])
    gz = ExecuteProcess(cmd=cmd, output='screen')

    spawn = Node(package='ros_gz_sim', executable='create', output='screen',
                 arguments=['-world', WORLD_NAME, '-topic', 'robot_description',
                            '-name', 'machine', '-z', '0.0'])

    bridges = [
        '/qa_camera/image_raw@sensor_msgs/msg/Image[ignition.msgs.Image',
        '/overview/image@sensor_msgs/msg/Image[ignition.msgs.Image',
        f'/world/{WORLD_NAME}/create@ros_gz_interfaces/srv/SpawnEntity',
        f'/world/{WORLD_NAME}/remove@ros_gz_interfaces/srv/DeleteEntity',
        f'/world/{WORLD_NAME}/set_pose@ros_gz_interfaces/srv/SetEntityPose',
        '/belt_sim/knife_joint@std_msgs/msg/Float64]ignition.msgs.Double',
    ]
    for i in range(n):
        for j in ('head_x', 'head_y', 'beam'):
            bridges.append(f'/belt_sim/laser_{i}_{j}@std_msgs/msg/Float64]ignition.msgs.Double')
    bridge = Node(package='ros_gz_bridge', executable='parameter_bridge', arguments=bridges,
                  output='screen')

    twin = Node(package='belt_marking_gazebo', executable='gz_twin_node', output='screen',
                parameters=[{'world': WORLD_NAME, 'station_offsets_mm': offsets[:n],
                             'knife_offset_mm': knife, 'belt_width_mm': width}])
    return [gz, TimerAction(period=3.0, actions=[spawn]), bridge, twin]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('headless', default_value='false'),
        DeclareLaunchArgument('num_stations', default_value='1'),
        DeclareLaunchArgument('station_offsets_mm', default_value='0.0'),
        DeclareLaunchArgument('knife_offset_mm', default_value='56.0'),
        DeclareLaunchArgument('belt_width_mm', default_value='25.0'),
        OpaqueFunction(function=_setup),
    ])
