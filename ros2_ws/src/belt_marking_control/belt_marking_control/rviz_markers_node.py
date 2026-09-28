"""RViz view of the process: belt, laser marks, cut lines, stations and machine state.

Works identically on the real machine (it only uses machine/state + machine/events).
"""

from belt_marking_interfaces.msg import MachineState, ProcessEvent
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from visualization_msgs.msg import Marker, MarkerArray

BELT_Z = 0.30          # must match the URDF belt surface height


def _color(m, r, g, b, a=1.0):
    m.color.r, m.color.g, m.color.b, m.color.a = float(r), float(g), float(b), float(a)


class RvizMarkersNode(Node):

    def __init__(self):
        super().__init__('rviz_markers_node')
        p = self.declare_parameter
        p('station_offsets_mm', [0.0])
        p('knife_offset_mm', 56.0)
        p('mark_length_mm', 20.0)
        p('x_min_m', -0.45)
        p('x_max_m', 0.45)
        p('default_belt_width_mm', 25.0)
        g = self.get_parameter
        self.stations = [float(v) for v in g('station_offsets_mm').value]
        self.knife = g('knife_offset_mm').value
        self.mark_len = g('mark_length_mm').value / 1000.0
        self.x_min, self.x_max = g('x_min_m').value, g('x_max_m').value
        self.width = g('default_belt_width_mm').value / 1000.0
        self.marks = []    # (belt_coord_mm, station, rejected)
        self.cuts = []     # belt_coord_mm
        self.rejects = set()
        self.state = None
        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(MachineState, 'machine/state', self._on_state, latched)
        self.create_subscription(ProcessEvent, 'machine/events', self._on_event, 100)
        self.pub = self.create_publisher(MarkerArray, 'machine/markers', 10)
        self.create_timer(0.1, self._publish)

    def _on_state(self, msg):
        self.state = msg
        if msg.belt_width_mm > 0:
            self.width = msg.belt_width_mm / 1000.0

    def _on_event(self, ev):
        if ev.type == ProcessEvent.JOB_START:
            self.marks.clear()
            self.cuts.clear()
            self.rejects.clear()
        elif ev.type == ProcessEvent.MARK:
            self.marks.append((ev.belt_coord_mm, ev.station))
        elif ev.type == ProcessEvent.CUT:
            self.cuts.append(ev.belt_coord_mm)
        elif ev.type == ProcessEvent.REJECT:
            self.rejects.add(ev.label_index)

    def _box(self, mid, ns, x, y, z, sx, sy, sz, rgba):
        m = Marker()
        m.header.frame_id = 'world'
        m.header.stamp = self.get_clock().now().to_msg()
        m.ns, m.id, m.type, m.action = ns, mid, Marker.CUBE, Marker.ADD
        m.pose.position.x, m.pose.position.y, m.pose.position.z = float(x), float(y), float(z)
        m.pose.orientation.w = 1.0
        m.scale.x, m.scale.y, m.scale.z = float(sx), float(sy), float(sz)
        _color(m, *rgba)
        return m

    def _text(self, mid, ns, x, y, z, text, size=0.025, rgba=(1, 1, 1, 1)):
        m = self._box(mid, ns, x, y, z, 0, 0, size, rgba)
        m.type = Marker.TEXT_VIEW_FACING
        m.text = text
        return m

    def _publish(self):
        arr = MarkerArray()
        clear = Marker()
        clear.action = Marker.DELETEALL
        arr.markers.append(clear)
        st = self.state
        feed = st.belt_position_mm if st is not None and st.job_id else 0.0
        z = BELT_Z + 0.0012
        # belt
        arr.markers.append(self._box(0, 'belt', (self.x_min + self.x_max) / 2, 0, BELT_Z - 0.001,
                                     self.x_max - self.x_min, self.width, 0.002,
                                     (0.12, 0.12, 0.12, 1)))
        # marks travel with the belt: x = feed - s
        for i, (s, station) in enumerate(self.marks):
            x = (feed - s) / 1000.0
            if not self.x_min <= x <= self.x_max + 0.3:
                continue
            color = (0.95, 0.85, 0.2, 1) if station == 0 else (0.3, 0.8, 1.0, 1)
            arr.markers.append(self._box(i + 1, 'marks', x + self.mark_len / 2, 0, z,
                                         self.mark_len, self.width * 0.7, 0.0008, color))
        for i, s in enumerate(self.cuts):
            x = (feed - s) / 1000.0
            if self.x_min <= x <= self.x_max + 0.3:
                arr.markers.append(self._box(i + 1, 'cuts', x, 0, z + 0.001, 0.0015,
                                             self.width * 1.3, 0.003, (1, 0.1, 0.1, 1)))
        # stations and knife
        for i, off in enumerate(self.stations):
            arr.markers.append(self._text(100 + i, 'labels', off / 1000.0, -0.12, BELT_Z + 0.05,
                                          f'LASER {i}', 0.018, (1, 0.9, 0.3, 1)))
        arr.markers.append(self._text(200, 'labels', self.knife / 1000.0, 0.14, BELT_Z + 0.12,
                                      'KNIFE', 0.018, (0.5, 0.7, 1, 1)))
        # state banner
        if st is not None:
            alarms = ' '.join(a.code_text for a in st.active_alarms[:3])
            text = (f'{st.state_name} [{st.mode_name}]  {st.job_id}  '
                    f'{st.marks_done}/{st.marks_total} marks  {st.pieces_cut} cut  '
                    f'{st.rejects} rej  {alarms}')
            color = (1, 0.3, 0.3, 1) if st.light_red else \
                (1, 0.9, 0.2, 1) if st.light_yellow else (0.3, 1, 0.3, 1)
            arr.markers.append(self._text(300, 'state', 0.0, 0.0, BELT_Z + 0.42, text, 0.03,
                                          color))
        self.pub.publish(arr)


def main(args=None):
    rclpy.init(args=args)
    node = RvizMarkersNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
