# Simulation image: ROS 2 Humble + Gazebo Fortress (ros_gz) + the belt marking workspace.
#   docker compose -f docker/docker-compose.yml up sim
FROM osrf/ros:humble-desktop

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        ros-humble-ros-gz ros-humble-xacro ros-humble-robot-state-publisher \
        ros-humble-joint-state-publisher-gui ros-humble-launch-testing-ros \
        python3-pyqt5 python3-serial python3-yaml python3-opencv python3-sklearn \
        python3-pytest python3-colcon-common-extensions \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ws
COPY ros2_ws/src /ws/src
RUN . /opt/ros/humble/setup.sh && \
    apt-get update && rosdep update --rosdistro humble && \
    rosdep install --from-paths src --ignore-src -y --rosdistro humble && \
    rm -rf /var/lib/apt/lists/* && \
    colcon build --event-handlers console_direct-

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "belt_marking_bringup", "sim.launch.py"]
