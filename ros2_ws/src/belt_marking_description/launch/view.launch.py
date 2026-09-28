"""Show the machine model in RViz with sliders for all joints (no control stack)."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg = FindPackageShare('belt_marking_description')
    description = ParameterValue(Command([
        'xacro ', PathJoinSubstitution([pkg, 'urdf', 'belt_marking_machine.urdf.xacro']),
        ' station_offsets:="', LaunchConfiguration('station_offsets'), '"',
        ' belt_width:=', LaunchConfiguration('belt_width'),
    ]), value_type=str)
    return LaunchDescription([
        DeclareLaunchArgument('station_offsets', default_value='0.0',
                              description='laser station offsets in metres, space separated'),
        DeclareLaunchArgument('belt_width', default_value='0.05'),
        DeclareLaunchArgument('gui', default_value='true'),
        Node(package='robot_state_publisher', executable='robot_state_publisher',
             parameters=[{'robot_description': description}]),
        Node(package='joint_state_publisher_gui', executable='joint_state_publisher_gui',
             condition=IfCondition(LaunchConfiguration('gui'))),
        Node(package='rviz2', executable='rviz2',
             arguments=['-d', PathJoinSubstitution([pkg, 'rviz', 'machine.rviz'])]),
    ])
