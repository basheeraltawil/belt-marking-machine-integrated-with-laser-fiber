"""Real hardware layer: ROS <-> Arduino Mega over the framed serial protocol.

Lifecycle node (configure = load parameters, activate = connect + serve). With
``autostart:=true`` (default) it configures and activates itself. It reconnects
automatically after the USB cable/board goes away.

Heartbeats are forwarded to the firmware **only while control_node's heartbeat
(``hw/heartbeat``) is fresh**, so the firmware watchdog also trips when the control node
dies, not only when this bridge or the cable does.
"""

import time

from belt_marking_interfaces.msg import IoStatus
from belt_marking_interfaces.srv import HwCommand
import rclpy
from rclpy.lifecycle import LifecycleNode, TransitionCallbackReturn
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import UInt32

from .firmware_client import FirmwareClient, SerialTransport
from .ros_conv import dispatch, snapshot_to_msg


class SerialBridgeNode(LifecycleNode):
    """Real hardware layer: serves hw/* over the serial link."""

    def __init__(self):
        super().__init__('serial_bridge_node')
        p = self.declare_parameter
        p('port', '/dev/belt_arduino')
        p('baud', 115200)
        p('steps_per_mm', 69.0)
        p('default_speed_mm_s', 14.5)
        p('max_speed_mm_s', 60.0)
        p('accel_mm_s2', 100.0)
        p('num_stations', 1)
        p('heartbeat_timeout_ms', 500)
        p('status_timeout_s', 0.5)
        p('control_heartbeat_timeout_s', 0.3)
        p('encoder_enabled', False)
        p('encoder_counts_per_mm', 0.0)
        p('reconnect_period_s', 1.0)
        p('autostart', True)
        self.client = None
        self._timers = []
        self._srv = None
        self._pub = None
        self._last_ctrl_hb = 0.0
        self._connected_once = False
        if self.get_parameter('autostart').value:
            self.trigger_configure()
            self.trigger_activate()

    # ---------------------------------------------------------------- lifecycle
    def on_configure(self, state):
        g = self.get_parameter
        self.port, self.baud = g('port').value, int(g('baud').value)
        self.spm = float(g('steps_per_mm').value)
        self.n = int(g('num_stations').value)
        self._pub = self.create_publisher(IoStatus, 'hw/io_status', qos_profile_sensor_data)
        self.create_subscription(UInt32, 'hw/heartbeat', self._on_ctrl_heartbeat, 10)
        self.add_on_set_parameters_callback(self._on_params)
        self.get_logger().info(f'configured for {self.port} @ {self.baud}')
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, state):
        self._srv = self.create_service(HwCommand, 'hw/command', self._on_command)
        self._timers = [
            self.create_timer(0.02, self._publish),
            self.create_timer(0.1, self._forward_heartbeat),
            self.create_timer(float(self.get_parameter('reconnect_period_s').value),
                              self._ensure_connected),
        ]
        self._ensure_connected()
        return TransitionCallbackReturn.SUCCESS

    def on_deactivate(self, state):
        for t in self._timers:
            self.destroy_timer(t)
        self._timers = []
        if self._srv is not None:
            self.destroy_service(self._srv)
            self._srv = None
        self._disconnect()
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state):
        self._disconnect()
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state):
        self._disconnect()
        return TransitionCallbackReturn.SUCCESS

    # --------------------------------------------------------------- connection
    def _ensure_connected(self):
        if self.client is not None and self.client.io_error is None:
            return
        if self.client is not None:
            self.get_logger().error(f'serial link error: {self.client.io_error}')
            self._disconnect()
        try:
            transport = SerialTransport(self.port, self.baud)
        except Exception as exc:  # noqa: BLE001 - port missing / permission / busy
            self.get_logger().warn(f'cannot open {self.port}: {exc}', throttle_duration_sec=10)
            return
        g = self.get_parameter
        self.client = FirmwareClient(
            transport, steps_per_mm=self.spm, num_stations=self.n,
            status_timeout_s=float(g('status_timeout_s').value),
            encoder_counts_per_mm=float(g('encoder_counts_per_mm').value)
            if g('encoder_enabled').value else 0.0)
        self.client.on_event = lambda name, data: self.get_logger().warn(
            f'firmware event: {name} ({data})')
        time.sleep(0.05)
        self.client.get_info()
        self.client.set_config('heartbeat_timeout_ms',
                               float(g('heartbeat_timeout_ms').value))
        self.client.set_config('max_speed_steps_s',
                               float(g('max_speed_mm_s').value) * self.spm)
        info = self.client.info or {}
        self.get_logger().info(f'connected to firmware {info.get("version", "?")} '
                               f'(protocol {info.get("protocol", "?")}) on {self.port}')
        self._connected_once = True

    def _disconnect(self):
        if self.client is not None:
            try:
                self.client.close()
            except Exception:  # noqa: BLE001
                pass
            self.client = None

    # ----------------------------------------------------------------- traffic
    def _on_ctrl_heartbeat(self, _msg):
        self._last_ctrl_hb = time.monotonic()

    def _forward_heartbeat(self):
        timeout = float(self.get_parameter('control_heartbeat_timeout_s').value)
        if self.client is not None and time.monotonic() - self._last_ctrl_hb < timeout:
            self.client.heartbeat()

    def _publish(self):
        if self.client is None or not self.client.link_ok:
            return        # silence = link lost for control_node (E-501)
        self._pub.publish(snapshot_to_msg(self.client.snapshot(),
                                          self.get_clock().now().to_msg(), self.n))

    def _on_command(self, req, res):
        if self.client is None or not self.client.link_ok:
            res.accepted, res.message = False, 'serial link down'
            return res
        res.accepted, res.message = dispatch(req, self.client)
        return res

    def _on_params(self, params):
        from rcl_interfaces.msg import SetParametersResult
        for prm in params:
            if prm.name == 'steps_per_mm' and float(prm.value) > 0:
                self.spm = float(prm.value)
                if self.client is not None:
                    self.client.spm = self.spm
                self.get_logger().warn(f'steps_per_mm changed to {self.spm}')
        return SetParametersResult(successful=True)


def main(args=None):
    rclpy.init(args=args)
    node = SerialBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node._disconnect()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
