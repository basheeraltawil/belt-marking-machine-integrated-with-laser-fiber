"""Animate the machine model from hardware I/O.

Converts ``hw/io_status`` (identical for sim and real) into ``joint_states`` so RViz and
the Gazebo twin show the real machine state: belt rollers turn with the stepper position,
the knife follows its valves/sensors and the laser heads raster while the laser is busy.
"""

import math

from belt_marking_interfaces.msg import IoStatus
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState


class KnifeKinematics:
    """First-order knife model driven by valve outputs and snapped to the reed sensors."""

    def __init__(self, stroke_m: float, stroke_time_s: float):
        self.stroke = stroke_m
        self.speed = stroke_m / max(stroke_time_s, 1e-3)
        self.pos = 0.0

    def update(self, dt: float, extend_valve: bool, retract_valve: bool,
               extended: bool, retracted: bool) -> float:
        if extended:
            self.pos = self.stroke
        elif retracted:
            self.pos = 0.0
        elif extend_valve and not retract_valve:
            self.pos = min(self.stroke * 0.98, self.pos + self.speed * dt)
        elif retract_valve and not extend_valve:
            self.pos = max(self.stroke * 0.02, self.pos - self.speed * dt)
        return self.pos


def raster(t: float, field: float) -> tuple:
    """Head position of a 'hatch fill' raster over the marking field (visual only)."""
    half = field * 0.4
    x = half * math.sin(2.0 * math.pi * 1.5 * t)
    y = half * (2.0 * ((0.25 * t) % 1.0) - 1.0)
    return x, y


class JointStateNode(Node):

    def __init__(self):
        super().__init__('joint_state_node')
        self.declare_parameter('roller_diameter_m', 0.04)
        self.declare_parameter('pinch_diameter_m', 0.024)
        self.declare_parameter('reel_diameter_m', 0.18)
        self.declare_parameter('knife_stroke_m', 0.12)
        self.declare_parameter('knife_stroke_time_s', 0.3)
        self.declare_parameter('laser_field_m', 0.05)
        self.declare_parameter('num_stations', 1)
        self.declare_parameter('beam_travel_m', 0.13)
        self.declare_parameter('rate_hz', 30.0)
        gp = self.get_parameter
        self.r_drive = gp('roller_diameter_m').value / 2.0
        self.r_pinch = gp('pinch_diameter_m').value / 2.0
        self.r_reel = gp('reel_diameter_m').value / 2.0
        self.field = gp('laser_field_m').value
        self.n = int(gp('num_stations').value)
        self.beam_travel = gp('beam_travel_m').value
        self.knife = KnifeKinematics(gp('knife_stroke_m').value,
                                     gp('knife_stroke_time_s').value)
        self.io = None
        self.ejector_angle = 0.0
        self.busy_since = [None] * self.n
        self.pub = self.create_publisher(JointState, 'joint_states', 10)
        self.create_subscription(IoStatus, 'hw/io_status', self._on_io,
                                 qos_profile_sensor_data)
        self.dt = 1.0 / gp('rate_hz').value
        self.create_timer(self.dt, self._tick)

    def _on_io(self, msg: IoStatus):
        self.io = msg

    def _tick(self):
        io = self.io
        now = self.get_clock().now()
        t = now.nanoseconds * 1e-9
        pos_m = (io.position_mm / 1000.0) if io else 0.0
        names, pos = [], []

        def add(name, value):
            names.append(name)
            pos.append(float(value))

        add('drive_roller_joint', pos_m / self.r_drive)
        add('entry_roller_joint', pos_m / self.r_drive)
        add('pinch_roller_joint', -pos_m / self.r_pinch)
        add('supply_reel_joint', pos_m / self.r_reel)
        if io is not None and io.dc_motor:
            self.ejector_angle += 20.0 * self.dt
        add('ejector_roller_joint', self.ejector_angle)
        knife = 0.0
        if io is not None:
            knife = self.knife.update(self.dt, io.knife_extend_valve, io.knife_retract_valve,
                                      io.knife_extended, io.knife_retracted)
        add('knife_joint', knife)
        for i in range(self.n):
            busy = bool(io is not None and i < len(io.laser_busy) and io.laser_busy[i])
            if busy and self.busy_since[i] is None:
                self.busy_since[i] = t
            if not busy:
                self.busy_since[i] = None
            hx, hy, beam = 0.0, 0.0, 0.0
            if busy:
                hx, hy = raster(t - self.busy_since[i], self.field)
                beam = 1.0
            add(f'laser_{i}_head_x', hx)
            add(f'laser_{i}_head_y', hy)
            add(f'laser_{i}_beam', beam * self.beam_travel)
        msg = JointState()
        msg.header.stamp = now.to_msg()
        msg.name = names
        msg.position = pos
        self.pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = JointStateNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
