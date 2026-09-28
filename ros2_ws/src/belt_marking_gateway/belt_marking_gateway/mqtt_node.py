"""MQTT publisher: machine state, alarms and process events for dashboards / MES.

Topics (base = ``<prefix>/<machine_id>``):
  <base>/state   JSON, retained, on every change (at most ``max_rate_hz``) and every 10 s
  <base>/alarm   JSON per alarm event
  <base>/event   JSON per process event (MARK/CUT/REJECT/JOB_START/JOB_END)
  <base>/online  "1" / "0" (last will)

Publish-only: the MQTT side cannot command the machine. Credentials come from the
environment (``BELT_MQTT_USER`` / ``BELT_MQTT_PASSWORD``), never from files in the repo.
Requires ``paho-mqtt`` (``apt install python3-paho-mqtt``).
"""

import os
import time

from belt_marking_interfaces.msg import Alarm, MachineState, ProcessEvent
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

from .payloads import alarm_to_dict, event_to_dict, state_to_dict, to_json


class MqttGateway(Node):

    def __init__(self, client_factory=None):
        super().__init__('mqtt_gateway')
        p = self.declare_parameter
        p('host', 'localhost')
        p('port', 1883)
        p('tls', False)
        p('prefix', 'factory/belt_marking')
        p('machine_id', 'belt-marker-1')
        p('max_rate_hz', 2.0)
        g = self.get_parameter
        self.base = f'{g("prefix").value}/{g("machine_id").value}'
        self.machine_id = g('machine_id').value
        self.min_period = 1.0 / g('max_rate_hz').value
        self._last_pub = 0.0
        self._last_payload = None
        self.client = (client_factory or self._paho)(g('host').value, g('port').value,
                                                     g('tls').value)
        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(MachineState, 'machine/state', self._on_state, latched)
        self.create_subscription(Alarm, 'machine/alarms', self._on_alarm, 50)
        self.create_subscription(ProcessEvent, 'machine/events', self._on_event, 100)
        self.create_timer(10.0, lambda: self._publish_state(force=True))
        self.state = None

    def _paho(self, host, port, tls):
        import paho.mqtt.client as mqtt  # noqa: PLC0415 - optional dependency
        c = mqtt.Client(client_id=f'belt-marking-{self.machine_id}')
        user = os.environ.get('BELT_MQTT_USER')
        if user:
            c.username_pw_set(user, os.environ.get('BELT_MQTT_PASSWORD', ''))
        if tls:
            c.tls_set()
        c.will_set(f'{self.base}/online', '0', qos=1, retain=True)
        c.connect_async(host, int(port), keepalive=30)
        c.loop_start()
        c.publish(f'{self.base}/online', '1', qos=1, retain=True)
        self.get_logger().info(f'MQTT -> {host}:{port} base topic {self.base}')
        return c

    def _on_state(self, msg):
        self.state = msg
        self._publish_state()

    def _publish_state(self, force=False):
        if self.state is None:
            return
        d = state_to_dict(self.state, self.machine_id)
        key = {k: v for k, v in d.items() if k not in ('time', 'uptime_s', 'job_elapsed_s')}
        now = time.monotonic()
        if not force and (key == self._last_payload or now - self._last_pub < self.min_period):
            return
        self._last_payload, self._last_pub = key, now
        self.client.publish(f'{self.base}/state', to_json(d), qos=0, retain=True)

    def _on_alarm(self, msg):
        self.client.publish(f'{self.base}/alarm', to_json(alarm_to_dict(msg)), qos=1)

    def _on_event(self, msg):
        if msg.type != ProcessEvent.MARK:           # marks are frequent; counts are in state
            self.client.publish(f'{self.base}/event', to_json(event_to_dict(msg)), qos=1)


def main(args=None):
    rclpy.init(args=args)
    try:
        node = MqttGateway()
    except ImportError:
        print('paho-mqtt not installed: sudo apt install python3-paho-mqtt')
        rclpy.try_shutdown()
        return
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
