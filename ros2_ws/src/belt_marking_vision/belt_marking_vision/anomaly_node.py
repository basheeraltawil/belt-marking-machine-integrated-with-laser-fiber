"""Reads cycle times from the production DB and publishes drift warnings.

``maintenance/drift`` (std_msgs/String) -> control_node raises W-702 (warning only, no
machine reaction). Read-only access to the DB.
"""

from belt_marking_control.core.db import ProductionDb
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from .anomaly import DriftDetector

KINDS = ('knife_extend', 'knife_retract', 'laser', 'feed')


class AnomalyNode(Node):

    def __init__(self):
        super().__init__('anomaly_node')
        p = self.declare_parameter
        p('db_path', '~/.belt_marking/belt_marking.db')
        p('period_s', 30.0)
        p('baseline_n', 100)
        p('window', 30)
        p('z_threshold', 4.0)
        p('min_rel_change', 0.15)
        g = self.get_parameter
        self.db_path = g('db_path').value
        self.det = DriftDetector(g('baseline_n').value, g('window').value,
                                 g('z_threshold').value, g('min_rel_change').value)
        self.active = set()
        self.pub = self.create_publisher(String, 'maintenance/drift', 10)
        self.create_timer(g('period_s').value, self._check)

    def _check(self):
        try:
            db = ProductionDb(self.db_path, read_only=True)
        except Exception as exc:  # noqa: BLE001 - DB not created yet
            self.get_logger().debug(f'db not ready: {exc}')
            return
        try:
            for kind in KINDS:
                res = self.det.evaluate(kind, db.cycle_times(kind, 2000))
                if res is None:
                    continue
                if res.drift and kind not in self.active:
                    self.active.add(kind)
                    self.pub.publish(String(data=res.message()))
                    self.get_logger().warn('drift: ' + res.message())
                elif not res.drift:
                    self.active.discard(kind)
        finally:
            db.close()


def main(args=None):
    rclpy.init(args=args)
    node = AnomalyNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
