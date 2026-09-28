"""rclpy in a background thread, exposed to Qt through signals (thread-safe).

The UI never talks to hardware: only to control_node's topics/services/action (and, in
simulation, to ``sim/inject_fault``). A ``FakeBridge`` with the same API lets the UI run
and be tested without ROS.
"""

import threading

from PyQt5.QtCore import pyqtSignal, QObject


class BridgeBase(QObject):
    state = pyqtSignal(object)        # MachineState
    io = pyqtSignal(object)           # IoStatus
    alarm = pyqtSignal(object)        # Alarm
    event = pyqtSignal(object)        # ProcessEvent
    result = pyqtSignal(object, object)   # (callback, response)  -> delivered in GUI thread
    job_feedback = pyqtSignal(object)
    job_done = pyqtSignal(object)
    connected = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.result.connect(lambda cb, res: cb(res) if cb else None)


class RosBridge(BridgeBase):
    """Owns a rclpy node spinning in a daemon thread."""

    def __init__(self, node_name: str = 'operator_ui', args=None):
        super().__init__()
        import rclpy
        from rclpy.action import ActionClient
        from rclpy.executors import MultiThreadedExecutor
        from rclpy.qos import (DurabilityPolicy, qos_profile_sensor_data, QoSProfile,
                               ReliabilityPolicy)
        from belt_marking_interfaces import msg as M, srv as S
        from belt_marking_interfaces.action import RunJob
        from std_srvs.srv import Trigger
        from rcl_interfaces.srv import SetParameters

        if not rclpy.ok():
            rclpy.init(args=args)
        self.rclpy = rclpy
        self.M, self.S, self.RunJob = M, S, RunJob
        self.node = rclpy.create_node(node_name)
        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        n = self.node
        n.create_subscription(M.MachineState, 'machine/state', self.state.emit, latched)
        n.create_subscription(M.IoStatus, 'hw/io_status', self.io.emit, qos_profile_sensor_data)
        n.create_subscription(M.Alarm, 'machine/alarms', self.alarm.emit, 50)
        n.create_subscription(M.ProcessEvent, 'machine/events', self.event.emit, 100)
        self.clients = {
            'command': n.create_client(S.MachineCommand, 'machine/command'),
            'set_mode': n.create_client(S.SetMode, 'machine/set_mode'),
            'jog': n.create_client(S.Jog, 'machine/jog'),
            'home': n.create_client(S.Home, 'machine/home'),
            'cut_now': n.create_client(S.CutNow, 'machine/cut_now'),
            'trigger_laser': n.create_client(S.TriggerLaser, 'machine/trigger_laser'),
            'set_output': n.create_client(S.SetOutput, 'machine/set_output'),
            'ack': n.create_client(S.AckAlarm, 'machine/ack_alarm'),
            'reset_blade': n.create_client(Trigger, 'machine/reset_blade_counter'),
            'load': n.create_client(S.LoadRecipe, 'recipes/load'),
            'save': n.create_client(S.SaveRecipe, 'recipes/save'),
            'list': n.create_client(S.ListRecipes, 'recipes/list'),
            'delete': n.create_client(S.DeleteRecipe, 'recipes/delete'),
            'inject_fault': n.create_client(S.InjectFault, 'sim/inject_fault'),
            'hw_params': n.create_client(SetParameters, 'serial_bridge_node/set_parameters'),
            'sim_params': n.create_client(SetParameters, 'sim_hardware_node/set_parameters'),
        }
        self.action = ActionClient(n, RunJob, 'machine/run_job')
        self._goal = None
        self.executor = MultiThreadedExecutor(num_threads=2)
        self.executor.add_node(n)
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def _spin(self):
        try:
            self.executor.spin()
        except Exception:   # noqa: BLE001 - shutdown races
            pass

    def shutdown(self):
        self.executor.shutdown()
        self.node.destroy_node()
        self.rclpy.try_shutdown()

    # ----------------------------------------------------------------- services
    def request(self, name: str):
        cli = self.clients[name]
        return cli.srv_type.Request()

    def call(self, name: str, req, callback=None, timeout_msg='service not available'):
        cli = self.clients[name]
        if not cli.service_is_ready():
            if callback:
                self.result.emit(callback, None)
            return False
        fut = cli.call_async(req)
        fut.add_done_callback(lambda f: self.result.emit(callback, f.result()))
        return True

    # ------------------------------------------------------------------- action
    def run_job(self, spec, user: str):
        if not self.action.server_is_ready():
            self.job_done.emit(None)
            return False
        goal = self.RunJob.Goal(spec=spec, user=user)
        fut = self.action.send_goal_async(goal, feedback_callback=lambda fb:
                                          self.job_feedback.emit(fb.feedback))
        fut.add_done_callback(self._on_goal)
        return True

    def _on_goal(self, fut):
        handle = fut.result()
        if handle is None or not handle.accepted:
            self.job_done.emit(None)
            return
        self._goal = handle
        handle.get_result_async().add_done_callback(
            lambda f: self.job_done.emit(f.result().result))

    def cancel_job(self):
        if self._goal is not None:
            self._goal.cancel_goal_async()

    def job_spec(self):
        return self.M.JobSpec()

    def station_msg(self, **kw):
        return self.M.LaserStation(**kw)

    def param_request(self, name: str, value: float):
        from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue
        from rcl_interfaces.srv import SetParameters
        req = SetParameters.Request()
        req.parameters = [Parameter(name=name, value=ParameterValue(
            type=ParameterType.PARAMETER_DOUBLE, double_value=float(value)))]
        return req


class FakeBridge(BridgeBase):
    """No-ROS stand-in used by tests and `operator_ui --demo`. Records calls."""

    def __init__(self):
        super().__init__()
        self.calls = []

    class _Obj:

        def __init__(self, **kw):
            self.__dict__.update(kw)

    def request(self, name):
        return FakeBridge._Obj()

    def call(self, name, req, callback=None, **_):
        self.calls.append((name, req))
        if callback:
            res = FakeBridge._Obj(accepted=True, message='ok (demo)', names=['demo'],
                                  belt_widths_mm=[25.0], found=False, acknowledged_count=0,
                                  extend_time_s=0.3, retract_time_s=0.3, busy_time_s=2.0,
                                  success=True, results=[])
            self.result.emit(callback, res)
        return True

    def run_job(self, spec, user):
        self.calls.append(('run_job', spec))
        return True

    def cancel_job(self):
        self.calls.append(('cancel', None))

    def job_spec(self):
        return FakeBridge._Obj(stations=[])

    def station_msg(self, **kw):
        return FakeBridge._Obj(**kw)

    def param_request(self, name, value):
        return FakeBridge._Obj(name=name, value=value)

    def shutdown(self):
        pass
