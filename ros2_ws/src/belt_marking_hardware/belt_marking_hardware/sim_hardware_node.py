"""Simulated hardware layer: the plant model behind the same ROS contract as the real
serial bridge (``hw/command`` + ``hw/io_status`` + ``hw/heartbeat``).

Extra (simulation only):
  * ``sim/inject_fault`` (InjectFault): exercise alarms and recovery
  * ``sim/plant_events`` (ProcessEvent): ground truth of marks/cuts (used by the Gazebo twin
    and the synthetic vision camera)
  * parameter ``laser_marking_time_s``: duration of the design "loaded on the laser"
"""

import time

from belt_marking_interfaces.msg import IoStatus, ProcessEvent
from belt_marking_interfaces.srv import HwCommand, InjectFault
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import UInt32

from .fake_plant import FakePlant, PlantConfig
from .ros_conv import dispatch, snapshot_to_msg

_EVENT_TYPES = {'mark': ProcessEvent.MARK, 'cut': ProcessEvent.CUT,
                'piece_out': ProcessEvent.PIECE_OUT}


class SimHardwareNode(Node):

    def __init__(self):
        super().__init__('sim_hardware_node')
        p = self.declare_parameter
        p('steps_per_mm', 69.0)
        p('default_speed_mm_s', 14.5)
        p('max_speed_mm_s', 60.0)
        p('accel_mm_s2', 100.0)
        p('station_offsets_mm', [0.0])
        p('knife_offset_mm', 56.0)
        p('fork_sensor_offset_mm', 350.0)
        p('knife_stroke_time_s', 0.3)
        p('laser_marking_time_s', 2.0)
        p('watchdog_s', 0.5)
        p('encoder_enabled', False)
        p('physics_hz', 200.0)
        p('status_hz', 50.0)
        g = self.get_parameter
        offsets = [float(v) for v in g('station_offsets_mm').value]
        self.cfg = PlantConfig(
            steps_per_mm=g('steps_per_mm').value,
            default_speed_mm_s=g('default_speed_mm_s').value,
            max_speed_mm_s=g('max_speed_mm_s').value, accel_mm_s2=g('accel_mm_s2').value,
            station_offsets_mm=offsets, knife_offset_mm=g('knife_offset_mm').value,
            fork_sensor_offset_mm=g('fork_sensor_offset_mm').value,
            knife_stroke_time_s=g('knife_stroke_time_s').value,
            laser_marking_time_s=g('laser_marking_time_s').value,
            watchdog_s=g('watchdog_s').value, encoder_enabled=g('encoder_enabled').value)
        self.plant = FakePlant(self.cfg)
        self.plant.heartbeat()
        self.plant.on_event = self._on_plant_event
        self.n = len(offsets)

        self.pub_io = self.create_publisher(IoStatus, 'hw/io_status', qos_profile_sensor_data)
        self.pub_ev = self.create_publisher(ProcessEvent, 'sim/plant_events', 50)
        self.create_service(HwCommand, 'hw/command', self._on_command)
        self.create_service(InjectFault, 'sim/inject_fault', self._on_fault)
        self.create_subscription(UInt32, 'hw/heartbeat', self._on_heartbeat, 10)
        self.add_on_set_parameters_callback(self._on_params)

        self._t_last = time.monotonic()
        self.create_timer(1.0 / g('physics_hz').value, self._physics)
        self.create_timer(1.0 / g('status_hz').value, self._publish)
        self.get_logger().info(f'simulated hardware: {self.n} laser station(s) at {offsets} mm, '
                               f'knife at {self.cfg.knife_offset_mm} mm')

    def _on_params(self, params):
        from rcl_interfaces.msg import SetParametersResult
        for prm in params:
            if prm.name == 'laser_marking_time_s':
                for laser in self.plant.lasers:
                    laser.set_marking_time(float(prm.value))
        return SetParametersResult(successful=True)

    def _physics(self):
        now = time.monotonic()
        dt = min(now - self._t_last, 0.05)
        self._t_last = now
        self.plant.step(dt)

    def _publish(self):
        if not self.plant.link_up:
            return                               # simulated cable unplugged
        msg = snapshot_to_msg(self.plant.snapshot(), self.get_clock().now().to_msg(), self.n)
        self.pub_io.publish(msg)

    def _on_heartbeat(self, _msg):
        self.plant.heartbeat()

    def _on_command(self, req, res):
        if not self.plant.link_up:
            res.accepted, res.message = False, 'link down'
            return res
        res.accepted, res.message = dispatch(req, self.plant)
        return res

    def _on_fault(self, req, res):
        res.accepted, res.message = self.plant.inject(req.fault, req.enable, req.value,
                                                      req.station)
        self.get_logger().warn(f'fault injection: {res.message}')
        return res

    def _on_plant_event(self, kind, data):
        ev = ProcessEvent()
        ev.stamp = self.get_clock().now().to_msg()
        ev.type = _EVENT_TYPES.get(kind, ProcessEvent.MARK)
        ev.station = int(data.get('station', 0))
        ev.belt_coord_mm = float(data.get('belt_coord_mm', data.get('coord', 0.0)))
        length = data.get('length_mm', data.get('length', 0.0))
        ev.length_mm = float(length) if length == length else 0.0   # NaN -> 0
        ev.feed_mm = float(self.plant.position_mm)
        flags = []
        if data.get('weak'):
            flags.append('weak')
        if data.get('on_belt') is False:
            flags.append('no_belt')
        ev.detail = ','.join(flags)
        self.pub_ev.publish(ev)


def main(args=None):
    rclpy.init(args=args)
    node = SimHardwareNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
