"""ROS 2 adapter around the pure-Python MachineController.

Same node for simulation and real machine; the hardware layer behind ``hw/*`` differs.
"""

import threading
import time

from belt_marking_hardware.ros_hal import RosHardwareClient
from belt_marking_interfaces.action import RunJob
from belt_marking_interfaces.msg import Alarm, JobSpec, LaserStation, MachineState
from belt_marking_interfaces.msg import ProcessEvent, QualityResult
from belt_marking_interfaces.srv import (AckAlarm, CutNow, DeleteRecipe, Home, Jog,
                                         ListRecipes, LoadRecipe, MachineCommand, SaveRecipe,
                                         SetMode, SetOutput, TriggerLaser)
from builtin_interfaces.msg import Time
import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .core import ControlConfig, MachineController, Mode, State
from .core.config import apply_flat, flatten
from .core.db import ProductionDb
from .core.job import Job, job_from_msg, job_to_msg

EVENT_TYPES = {'MARK': ProcessEvent.MARK, 'CUT': ProcessEvent.CUT,
               'REJECT': ProcessEvent.REJECT, 'PIECE_OUT': ProcessEvent.PIECE_OUT,
               'JOB_START': ProcessEvent.JOB_START, 'JOB_END': ProcessEvent.JOB_END}


def _stamp(t: float) -> Time:
    sec = int(t)
    return Time(sec=sec, nanosec=int((t - sec) * 1e9))


class ControlNode(Node):

    def __init__(self):
        super().__init__('control_node')
        cfg = ControlConfig()
        for key, default in flatten(cfg).items():
            self.declare_parameter(key, default)
        self.declare_parameter('accel_mm_s2', 100.0)
        self.declare_parameter('steps_per_mm', 69.0)
        self.declare_parameter('state_hz', 10.0)
        values = {k: self.get_parameter(k).value for k in flatten(cfg)}
        apply_flat(cfg, values)
        self.cfg = cfg
        self.lock = threading.RLock()
        self.cb = ReentrantCallbackGroup()
        tick_group = MutuallyExclusiveCallbackGroup()

        self.hal = RosHardwareClient(self)
        self.ctrl = MachineController(self.hal, cfg, now=time.monotonic(),
                                      accel_mm_s2=self.get_parameter('accel_mm_s2').value,
                                      steps_per_mm=self.get_parameter('steps_per_mm').value)
        self.db = ProductionDb(cfg.db_path)
        stored = self.db.load_counters()
        for k, v in stored.items():
            if hasattr(self.ctrl.counters, k):
                setattr(self.ctrl.counters, k, type(getattr(self.ctrl.counters, k))(v))
        self._job_row = None
        self._job_user = ''
        self._t0_wall = time.time() - time.monotonic()

        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.pub_state = self.create_publisher(MachineState, 'machine/state', latched)
        self.pub_alarm = self.create_publisher(Alarm, 'machine/alarms', 50)
        self.pub_event = self.create_publisher(ProcessEvent, 'machine/events', 100)
        self.create_subscription(QualityResult, 'quality/result', self._on_quality, 50,
                                 callback_group=self.cb)
        self.create_subscription(String, 'maintenance/drift', self._on_drift, 10,
                                 callback_group=self.cb)

        self.ctrl.on_event = self._on_event
        self.ctrl.on_alarm = self._on_alarm
        self.ctrl.on_job_end = self._on_job_end
        self.ctrl.on_cycle = lambda kind, s: self.db.log_cycle(kind, s)
        self.ctrl.on_state = lambda old, new: self.get_logger().info(
            f'{old.name} -> {new.name}')

        srv = self.create_service
        srv(MachineCommand, 'machine/command', self._srv_command, callback_group=self.cb)
        srv(SetMode, 'machine/set_mode', self._srv_mode, callback_group=self.cb)
        srv(Jog, 'machine/jog', self._srv_jog, callback_group=self.cb)
        srv(Home, 'machine/home', self._srv_home, callback_group=self.cb)
        srv(CutNow, 'machine/cut_now', self._srv_cut, callback_group=self.cb)
        srv(TriggerLaser, 'machine/trigger_laser', self._srv_laser, callback_group=self.cb)
        srv(SetOutput, 'machine/set_output', self._srv_output, callback_group=self.cb)
        srv(AckAlarm, 'machine/ack_alarm', self._srv_ack, callback_group=self.cb)
        srv(Trigger, 'machine/reset_blade_counter', self._srv_blade, callback_group=self.cb)
        srv(LoadRecipe, 'recipes/load', self._srv_load, callback_group=self.cb)
        srv(SaveRecipe, 'recipes/save', self._srv_save, callback_group=self.cb)
        srv(ListRecipes, 'recipes/list', self._srv_list, callback_group=self.cb)
        srv(DeleteRecipe, 'recipes/delete', self._srv_delete, callback_group=self.cb)
        self._action = ActionServer(
            self, RunJob, 'machine/run_job', execute_callback=self._execute_job,
            goal_callback=self._goal_cb, cancel_callback=lambda _g: CancelResponse.ACCEPT,
            callback_group=self.cb)

        self.create_timer(1.0 / cfg.tick_hz, self._tick, callback_group=tick_group)
        self.create_timer(1.0 / self.get_parameter('state_hz').value, self._publish_state,
                          callback_group=self.cb)
        self.create_timer(30.0, self._save_counters, callback_group=self.cb)
        self.get_logger().info(f'control node up (use_sim={cfg.use_sim}, db={self.db.path})')

    # ------------------------------------------------------------------ loop
    def _tick(self):
        with self.lock:
            self.ctrl.tick(time.monotonic())

    def _wall(self, t_mono: float) -> float:
        return self._t0_wall + t_mono

    def _publish_state(self):
        with self.lock:
            c = self.ctrl
            st = c.status()
            m = MachineState()
            m.stamp = self.get_clock().now().to_msg()
            m.state = int(c.state)
            m.state_name = c.state.name
            m.mode = int(c.mode)
            m.mode_name = c.mode.name
            m.use_sim = self.cfg.use_sim
            m.job_id, m.recipe, m.phase = st['job_id'], st['recipe'], st['phase']
            m.marks_done, m.marks_total = st['marks_done'], st['marks_total']
            m.pieces_cut, m.rejects = st['pieces_cut'], st['rejects']
            m.progress = float(st['progress'])
            m.job_elapsed_s = float(st['job_elapsed_s'])
            m.belt_position_mm = float(st['belt_position_mm'])
            m.belt_speed_mm_s = float(st['belt_speed_mm_s'])
            m.belt_width_mm = float(st['belt_width_mm'])
            k = c.counters
            m.total_marks, m.total_pieces = k.total_marks, k.total_pieces
            m.knife_cycles, m.laser_triggers = k.knife_cycles, k.laser_triggers
            m.belt_meters, m.uptime_s = k.belt_mm / 1000.0, k.uptime_s
            o = c.oee
            m.oee_availability, m.oee_performance = o.availability, o.performance
            m.oee_quality, m.oee = o.quality, o.oee
            m.light_red, m.light_yellow, m.light_green, m.buzzer = st['lights']
            m.active_alarms = [self._alarm_msg(a) for a in c.alarms.active()]
        self.pub_state.publish(m)

    def _alarm_msg(self, a) -> Alarm:
        d = a.definition
        return Alarm(code=d.code, code_text=d.code_text, severity=int(d.severity),
                     reaction=int(d.reaction), text=d.text, remedy=d.remedy,
                     source='control', stamp=_stamp(self._wall(a.raised_at)), active=a.active,
                     acknowledged=a.acknowledged)

    # ------------------------------------------------------------ callbacks
    def _on_alarm(self, a, event):
        self.pub_alarm.publish(self._alarm_msg(a))
        d = a.definition
        self.db.log_alarm(d.code, d.code_text, int(d.severity), event, d.text, a.detail,
                          a.acked_by)
        if event == 'raised':
            log = self.get_logger().error if d.severity >= 2 else self.get_logger().warn
            log(f'{d.code_text} {d.text} {a.detail}')

    def _on_event(self, ev):
        msg = ProcessEvent(type=EVENT_TYPES[ev['type']], job_id=ev['job_id'],
                           label_index=int(ev['label']) if ev['label'] >= 0 else 0,
                           station=int(ev['station']), belt_coord_mm=float(ev['belt_coord_mm']),
                           feed_mm=float(ev['feed_mm']), length_mm=float(ev['length_mm']),
                           labels_in_piece=int(ev['labels_in_piece']), detail=ev['detail'])
        msg.stamp = self.get_clock().now().to_msg()
        self.pub_event.publish(msg)
        if ev['type'] != 'MARK':
            self.db.log_event(ev)
        if ev['type'] == 'JOB_START':
            run = self.ctrl.run
            self._job_row = self.db.job_started(run.job.job_id, run.job.recipe,
                                                run.job.to_json(), self._job_user)

    def _on_job_end(self, run):
        if self._job_row is not None:
            self.db.job_ended(self._job_row, run.final_state.name, run.marks_done,
                              run.pieces_cut, run.rejects, (run.t_end or 0) - run.t_start,
                              run.message)
            self._job_row = None
        self._save_counters()

    def _on_quality(self, msg: QualityResult):
        with self.lock:
            run = self.ctrl.run
            if run is not None and msg.job_id == run.job.job_id:
                self.ctrl.quality_result(msg.label_index, msg.ok, msg.reason)

    def _on_drift(self, msg: String):
        with self.lock:
            self.ctrl.maintenance_warning(msg.data)

    def _save_counters(self):
        self.db.save_counters(self.ctrl.counters.as_dict())

    # --------------------------------------------------------------- services
    def _srv_command(self, req, res):
        cmds = {MachineCommand.Request.RESET: lambda: self.ctrl.cmd_reset(req.user),
                MachineCommand.Request.HOLD: lambda: self.ctrl.cmd_hold(req.user),
                MachineCommand.Request.UNHOLD: lambda: self.ctrl.cmd_unhold(
                    req.user, req.option),
                MachineCommand.Request.STOP: lambda: self.ctrl.cmd_stop(req.user),
                MachineCommand.Request.ABORT: lambda: self.ctrl.cmd_abort(req.user),
                MachineCommand.Request.CLEAR: lambda: self.ctrl.cmd_clear(req.user)}
        fn = cmds.get(req.command)
        with self.lock:
            res.accepted, res.message = fn() if fn else (False, 'unknown command')
        self.db.audit(req.user, 'command', {'command': req.command, 'option': req.option,
                                            'accepted': res.accepted})
        return res

    def _srv_mode(self, req, res):
        with self.lock:
            res.accepted, res.message = self.ctrl.cmd_set_mode(Mode(req.mode), req.user)
        self.db.audit(req.user, 'set_mode', {'mode': req.mode, 'accepted': res.accepted})
        return res

    def _wait_task(self, task, timeout):
        end = time.monotonic() + timeout
        while not task.done and time.monotonic() < end:
            time.sleep(0.02)
        return task

    def _srv_jog(self, req, res):
        with self.lock:
            ok, msg, task = self.ctrl.manual_jog(req.distance_mm, req.speed_mm_s)
        if ok:
            self._wait_task(task, 60.0)
            ok, msg = task.ok, task.message
        res.accepted, res.message = ok, msg
        return res

    def _srv_home(self, req, res):
        with self.lock:
            res.accepted, res.message = self.ctrl.manual_home()
        return res

    def _srv_cut(self, req, res):
        with self.lock:
            ok, msg, task = self.ctrl.manual_cut()
        if ok:
            self._wait_task(task, 10.0)
            ok, msg = task.ok, task.message
            res.extend_time_s = float(task.result.get('extend_time_s', 0.0))
            res.retract_time_s = float(task.result.get('retract_time_s', 0.0))
        res.accepted, res.message = ok, msg
        return res

    def _srv_laser(self, req, res):
        with self.lock:
            ok, msg, task = self.ctrl.manual_laser(req.station, req.wait_done)
        if ok:
            self._wait_task(task, 120.0)
            ok, msg = task.ok, task.message
            res.busy_time_s = float(task.result.get('busy_time_s', 0.0))
        res.accepted, res.message = ok, msg
        return res

    def _srv_output(self, req, res):
        with self.lock:
            res.accepted, res.message = self.ctrl.manual_output(req.output, req.state)
        return res

    def _srv_ack(self, req, res):
        with self.lock:
            res.acknowledged_count = self.ctrl.cmd_ack(req.code, req.user)
        res.accepted = True
        return res

    def _srv_blade(self, req, res):
        with self.lock:
            self.ctrl.reset_blade_counter()
        self.db.audit('', 'reset_blade_counter', '')
        res.success, res.message = True, 'blade counter reset'
        return res

    def _srv_load(self, req, res):
        spec = self.db.load_recipe(req.name)
        res.found = spec is not None
        if spec is not None:
            res.spec = job_to_msg(Job.from_json(spec), JobSpec, LaserStation)
        res.message = 'ok' if res.found else f'recipe {req.name!r} not found'
        return res

    def _srv_save(self, req, res):
        name = req.name.strip()
        if not name:
            res.accepted, res.message = False, 'empty name'
            return res
        job = job_from_msg(req.spec)
        job.recipe = name
        res.accepted = self.db.save_recipe(name, job.to_json(), job.belt_width_mm, req.user,
                                           req.overwrite)
        res.message = 'saved' if res.accepted else 'exists (overwrite not set)'
        return res

    def _srv_list(self, req, res):
        rows = self.db.list_recipes()
        res.names = [r['name'] for r in rows]
        res.belt_widths_mm = [float(r['belt_width_mm'] or 0.0) for r in rows]
        return res

    def _srv_delete(self, req, res):
        res.accepted = self.db.delete_recipe(req.name, req.user)
        res.message = 'deleted' if res.accepted else 'not found'
        return res

    # ----------------------------------------------------------------- action
    def _goal_cb(self, goal):
        with self.lock:
            if self.ctrl.state not in (State.IDLE, State.COMPLETE):
                self.get_logger().warn(f'RunJob rejected in {self.ctrl.state.name}')
                return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _execute_job(self, handle):
        job = job_from_msg(handle.request.spec)
        self._job_user = handle.request.user
        result = RunJob.Result()
        with self.lock:
            if self.ctrl.state == State.COMPLETE:
                self.ctrl.cmd_reset(handle.request.user)
        # wait for IDLE after an automatic reset
        end = time.monotonic() + 10.0
        while self.ctrl.state != State.IDLE and time.monotonic() < end:
            time.sleep(0.02)
        with self.lock:
            ok, msg = self.ctrl.cmd_start(job, handle.request.user)
            run = self.ctrl.run
        self.db.audit(handle.request.user, 'start_job',
                      {'job_id': job.job_id, 'accepted': ok, 'spec': job.to_json()})
        if not ok:
            result.success, result.message = False, msg
            result.final_state = int(self.ctrl.state)
            handle.abort()
            return result
        fb = RunJob.Feedback()
        cancel_sent = False
        while True:
            with self.lock:
                active = self.ctrl.run is run
                st = self.ctrl.status()
                state = self.ctrl.state
            if not active:
                break
            if handle.is_cancel_requested and not cancel_sent:
                with self.lock:
                    self.ctrl.cmd_stop(handle.request.user)
                cancel_sent = True
            fb.current_label = min(run.marks_done, max(0, run.job.quantity - 1))
            fb.marks_done, fb.marks_total = run.marks_done, run.job.quantity
            fb.pieces_cut, fb.progress = run.pieces_cut, float(st['progress'])
            fb.phase, fb.state = st['phase'], int(state)
            handle.publish_feedback(fb)
            time.sleep(0.5)
        final = run.final_state or State.STOPPED
        result.success = final == State.COMPLETE
        result.final_state = int(final)
        result.marks_done, result.pieces_cut, result.rejects = (run.marks_done, run.pieces_cut,
                                                                run.rejects)
        result.duration_s = float((run.t_end or 0.0) - run.t_start)
        result.message = run.message or final.name
        if result.success:
            handle.succeed()
        elif handle.is_cancel_requested:
            handle.canceled()
        else:
            handle.abort()
        return result


def main(args=None):
    rclpy.init(args=args)
    node = ControlNode()
    executor = MultiThreadedExecutor(num_threads=6)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node._save_counters()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
