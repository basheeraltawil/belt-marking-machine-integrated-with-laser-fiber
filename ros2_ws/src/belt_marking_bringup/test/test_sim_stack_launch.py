"""ROS-level integration test: the real node graph (sim hardware + control) headless.

Runs a job through the RunJob action, then injects a belt run-out and checks the HOLD
reaction and resume. Complements the fast pure-Python scenario suite in
belt_marking_control/test/test_scenarios.py.
"""

import os
import tempfile
import time
import unittest

from belt_marking_bringup import config_loader as cl
from belt_marking_interfaces.action import RunJob
from belt_marking_interfaces.msg import JobSpec, MachineState
from belt_marking_interfaces.srv import InjectFault, MachineCommand
import launch
import launch_ros.actions
import launch_testing
import launch_testing.actions
import pytest
import rclpy
from rclpy.action import ActionClient
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, '..', 'config', 'machine.yaml')
DB = os.path.join(tempfile.mkdtemp(), 'launch_test.db')


@pytest.mark.launch_test
def generate_test_description():
    cfg = cl.load(CFG)
    cfg['control']['db_path'] = DB
    cfg['sim']['laser_marking_time_s'] = 0.3
    return launch.LaunchDescription([
        launch_ros.actions.Node(package='belt_marking_hardware',
                                executable='sim_hardware_node',
                                parameters=[cl.sim_hardware_params(cfg)]),
        launch_ros.actions.Node(package='belt_marking_control', executable='control_node',
                                parameters=[cl.control_params(cfg, use_sim=True)]),
        launch_testing.actions.ReadyToTest(),
    ])


class TestSimStack(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.node = rclpy.create_node('sim_stack_test')
        cls.state = None
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
        cls.node.create_subscription(MachineState, 'machine/state',
                                     lambda m: setattr(cls, 'state', m), qos)
        cls.cmd = cls.node.create_client(MachineCommand, 'machine/command')
        cls.fault = cls.node.create_client(InjectFault, 'sim/inject_fault')
        cls.action = ActionClient(cls.node, RunJob, 'machine/run_job')

    @classmethod
    def tearDownClass(cls):
        cls.node.destroy_node()
        rclpy.shutdown()

    def spin_until(self, pred, timeout):
        end = time.time() + timeout
        while time.time() < end:
            rclpy.spin_once(self.node, timeout_sec=0.05)
            if pred():
                return True
        return False

    def call(self, client, req):
        self.assertTrue(client.wait_for_service(timeout_sec=10.0))
        fut = client.call_async(req)
        self.assertTrue(self.spin_until(fut.done, 10.0))
        return fut.result()

    def command(self, code, option=''):
        return self.call(self.cmd, MachineCommand.Request(command=code, option=option,
                                                          user='launch_test'))

    def job(self, job_id, quantity):
        spec = JobSpec(job_id=job_id, quantity=quantity, pitch_mm=40.0, mark_length_mm=20.0,
                       lead_mm=5.0, cut_mode=JobSpec.CUT_EVERY, cut_every_n=1,
                       laser_time_s=0.3, settle_s=0.05, feed_speed_mm_s=50.0,
                       belt_width_mm=25.0)
        self.assertTrue(self.action.wait_for_server(timeout_sec=10.0))
        fut = self.action.send_goal_async(RunJob.Goal(spec=spec, user='launch_test'))
        self.assertTrue(self.spin_until(fut.done, 10.0))
        handle = fut.result()
        self.assertTrue(handle.accepted)
        return handle

    def test_1_job_then_belt_runout(self):
        self.assertTrue(self.spin_until(lambda: self.state is not None, 20.0))
        self.assertTrue(self.command(MachineCommand.Request.RESET).accepted)
        self.assertTrue(self.spin_until(lambda: self.state.state_name == 'IDLE', 10.0))

        handle = self.job('LT-1', 3)
        res_fut = handle.get_result_async()
        self.assertTrue(self.spin_until(res_fut.done, 60.0))
        result = res_fut.result().result
        self.assertTrue(result.success, result.message)
        self.assertEqual((result.marks_done, result.pieces_cut), (3, 3))

        # fault: belt runs out mid-batch -> HELD, counts kept, resume after refill
        handle = self.job('LT-2', 6)
        self.assertTrue(self.spin_until(lambda: self.state.marks_done >= 2, 60.0))
        self.call(self.fault, InjectFault.Request(fault='belt_runout', enable=True,
                                                  value=10.0))
        self.assertTrue(self.spin_until(lambda: self.state.state_name == 'HELD', 30.0))
        self.assertIn(401, [a.code for a in self.state.active_alarms])
        held = self.state.marks_done
        self.call(self.fault, InjectFault.Request(fault='belt_runout', enable=False))
        self.spin_until(lambda: False, 0.5)
        self.assertTrue(self.command(MachineCommand.Request.UNHOLD).accepted)
        res_fut = handle.get_result_async()
        self.assertTrue(self.spin_until(res_fut.done, 90.0))
        result = res_fut.result().result
        self.assertTrue(result.success, result.message)
        self.assertGreaterEqual(result.marks_done, held)
        self.assertEqual(result.marks_done, 6)


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):

    def test_exit_codes(self, proc_info):
        launch_testing.asserts.assertExitCodes(proc_info, allowable_exit_codes=[0, -2, -15])
