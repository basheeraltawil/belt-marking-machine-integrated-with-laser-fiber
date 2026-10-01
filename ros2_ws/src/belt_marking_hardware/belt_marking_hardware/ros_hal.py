"""HardwareInterface over ROS: ``hw/command`` (service) + ``hw/io_status`` (topic).

Used by ``control_node``. It does not know whether ``serial_bridge_node`` (real) or
``sim_hardware_node`` (simulation) answers, which is the point.
"""

import copy
import threading
import time
from typing import List

from belt_marking_interfaces.msg import IoStatus
from belt_marking_interfaces.srv import HwCommand
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import UInt32

from .hal import HardwareInterface, IoSnapshot, MotionIdCounter
from .ros_conv import msg_to_snapshot


class RosHardwareClient(HardwareInterface):
    """HardwareInterface over ROS (hw/command, hw/io_status)."""

    def __init__(self, node, stale_s: float = 0.5, heartbeat_hz: float = 10.0):
        self.node = node
        self.stale_s = stale_s
        self._hb_period = 1.0 / heartbeat_hz
        self._hb_last = 0.0
        self._hb_count = 0
        self._lock = threading.Lock()
        self._snap = IoSnapshot(link_ok=False)
        self._rx_time = None
        self._errors: List[str] = []
        self._ids = MotionIdCounter()
        group = ReentrantCallbackGroup()
        node.create_subscription(IoStatus, 'hw/io_status', self._on_status,
                                 qos_profile_sensor_data, callback_group=group)
        self._cli = node.create_client(HwCommand, 'hw/command', callback_group=group)
        self._hb = node.create_publisher(UInt32, 'hw/heartbeat', 10)

    # ------------------------------------------------------------------ status
    def _on_status(self, msg: IoStatus) -> None:
        snap = msg_to_snapshot(msg, time.monotonic())
        with self._lock:
            self._snap = snap
            self._rx_time = time.monotonic()

    def snapshot(self) -> IoSnapshot:
        with self._lock:
            snap = copy.copy(self._snap)
            fresh = self._rx_time is not None and \
                time.monotonic() - self._rx_time < self.stale_s
        if not fresh:
            snap.link_ok = False
        return snap

    # ---------------------------------------------------------------- commands
    def _send(self, **fields) -> None:
        if not self._cli.service_is_ready():
            self._errors.append('hw/command service not available')
            return
        req = HwCommand.Request()
        for k, v in fields.items():
            setattr(req, k, v)
        fut = self._cli.call_async(req)
        fut.add_done_callback(self._on_response)

    def _on_response(self, fut) -> None:
        try:
            res = fut.result()
        except Exception as exc:  # noqa: BLE001 - report any transport error
            self._errors.append(f'hw/command failed: {exc}')
            return
        if not res.accepted and 'link down' not in res.message:
            self._errors.append(res.message)      # link loss is reported as E-501 instead

    def move_relative(self, distance_mm, speed_mm_s=0.0, accel_mm_s2=0.0) -> int:
        mid = self._ids.next_id()
        self._send(command=HwCommand.Request.MOVE_REL, motion_id=mid, value=float(distance_mm),
                   speed=float(speed_mm_s), accel=float(accel_mm_s2))
        return mid

    def jog(self, direction, speed_mm_s, duration_ms) -> int:
        mid = self._ids.next_id()
        self._send(command=HwCommand.Request.JOG, motion_id=mid, value=float(direction),
                   speed=float(speed_mm_s), duration_ms=int(duration_ms))
        return mid

    def stop(self, quick=False):
        self._send(command=HwCommand.Request.STOP, value=1.0 if quick else 0.0)

    def set_output(self, name, state):
        self._send(command=HwCommand.Request.SET_OUTPUT, output=name, state=bool(state))

    def pulse_output(self, name, duration_ms):
        self._send(command=HwCommand.Request.PULSE_OUTPUT, output=name,
                   duration_ms=int(duration_ms))

    def enable_drive(self, on):
        self._send(command=HwCommand.Request.ENABLE_DRIVE, state=bool(on))

    def zero_position(self):
        self._send(command=HwCommand.Request.ZERO_POSITION)

    def reset_faults(self):
        self._send(command=HwCommand.Request.RESET_FAULTS)

    def heartbeat(self, now):
        if now - self._hb_last >= self._hb_period:
            self._hb_last = now
            self._hb_count = (self._hb_count + 1) & 0xFFFFFFFF
            self._hb.publish(UInt32(data=self._hb_count))

    def pop_errors(self):
        errors, self._errors = self._errors, []
        return errors
