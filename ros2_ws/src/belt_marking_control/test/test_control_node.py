"""control_node logging regression: a WARNING alarm followed by an ERROR alarm used to
crash the node (rclpy forbids changing the severity of one logging call site)."""

import os
import tempfile

import pytest

rclpy = pytest.importorskip('rclpy')


def test_alarm_logging_mixed_severities():
    from belt_marking_control.control_node import ControlNode
    from belt_marking_control.core.alarms import AlarmInstance, CATALOG
    rclpy.init(args=['--ros-args', '-p',
                     f'db_path:={os.path.join(tempfile.mkdtemp(), "t.db")}'])
    try:
        node = ControlNode()
        for code in (703, 201, 601, 501):             # warning, error, warning, fatal
            node._on_alarm(AlarmInstance(CATALOG[code], 'test', 0.0), 'raised')
        node.destroy_node()
    finally:
        rclpy.shutdown()
