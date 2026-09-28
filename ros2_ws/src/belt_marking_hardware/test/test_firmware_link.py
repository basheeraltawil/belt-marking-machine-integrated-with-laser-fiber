"""FirmwareClient <-> VirtualFirmware over an in-memory pipe (real protocol, real time)."""

import threading
import time

from belt_marking_hardware.fake_plant import PlantConfig
from belt_marking_hardware.firmware_client import FirmwareClient, pipe_pair, VirtualFirmware
from belt_marking_hardware.hal import HardwareInterface, MotionIdCounter
import pytest


@pytest.fixture
def link():
    host, dev = pipe_pair()
    fw = VirtualFirmware(dev, PlantConfig(laser_marking_time_s=0.2, knife_stroke_time_s=0.1))
    cl = FirmwareClient(host, steps_per_mm=69.0)
    cl.hb_enabled = True
    stop = threading.Event()

    def beat():                                   # like serial_bridge_node (10 Hz)
        while not stop.wait(0.1):
            if cl.hb_enabled:
                cl.heartbeat()
    threading.Thread(target=beat, daemon=True).start()
    yield cl, fw
    stop.set()
    cl.close()
    fw.close()


def wait(pred, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_watchdog_not_armed_before_first_heartbeat():
    host, dev = pipe_pair()
    fw = VirtualFirmware(dev)
    cl = FirmwareClient(host)
    try:
        time.sleep(1.0)                                          # board booted, Pi silent
        assert wait(lambda: cl.link_ok)
        assert cl.snapshot().fault_flags & 1 == 0
    finally:
        cl.close()
        fw.close()


def test_info_status_and_move(link):
    cl, fw = link
    assert cl.get_info() == (True, 'ok')
    assert cl.info['protocol'] == 1
    assert wait(lambda: cl.link_ok)
    cl.heartbeat()
    assert cl.cmd_enable(True)[0]
    assert cl.cmd_move_rel(20.0, 40.0, 200.0, 11)[0]
    assert wait(lambda: cl.snapshot().motion_id == 11 and not cl.snapshot().moving)
    assert cl.snapshot().position_steps == 20 * 69


def test_nak_on_interlock_and_disabled(link):
    cl, fw = link
    cl.heartbeat()
    ok, why = cl.cmd_move_rel(5.0)
    assert not ok and why == 'drive disabled'
    cl.cmd_enable(True)
    cl.cmd_set_output('knife_extend', True)
    assert wait(lambda: cl.snapshot().knife_extended)
    ok, why = cl.cmd_move_rel(5.0)
    assert not ok and why == 'interlock'


def test_retransmission_is_not_executed_twice(link):
    cl, fw = link
    from belt_marking_hardware import protocol as P
    cl.heartbeat()
    cl.cmd_enable(True)
    frame = P.encode(P.MOVE_REL, 200, P.pack(P.MOVE_REL, 690, 690.0, 6900.0, 5))
    cl._write(frame)
    cl._write(frame)                                     # duplicate (lost ACK case)
    assert wait(lambda: cl.snapshot().motion_id == 5 and not cl.snapshot().moving)
    assert cl.snapshot().position_steps == 690


def test_watchdog_trips_without_heartbeat(link):
    cl, fw = link
    time.sleep(0.25)                                             # watchdog armed
    cl.cmd_enable(True)
    cl.cmd_move_rel(500.0, 20.0)
    cl.hb_enabled = False                                        # control node "dies"
    assert wait(lambda: cl.snapshot().fault_flags & 1, 2.0)
    snap = cl.snapshot()
    assert not snap.moving and snap.outputs['knife_retract']
    assert not cl.cmd_reset_faults()[0]                          # needs a fresh heartbeat
    cl.hb_enabled = True
    time.sleep(0.25)
    assert cl.cmd_reset_faults()[0]


class ClientHal(HardwareInterface):
    """Minimal synchronous HAL over FirmwareClient (the ROS bridge does the same)."""

    def __init__(self, cl):
        self.cl, self.ids, self.errors = cl, MotionIdCounter(), []

    def _c(self, r):
        if not r[0]:
            self.errors.append(r[1])

    def snapshot(self):
        return self.cl.snapshot()

    def move_relative(self, d, s=0.0, a=0.0):
        mid = self.ids.next_id()
        self._c(self.cl.cmd_move_rel(d, s, a, mid))
        return mid

    def jog(self, direction, s, ms):
        mid = self.ids.next_id()
        self._c(self.cl.cmd_jog(direction, s, ms, mid))
        return mid

    def stop(self, quick=False):
        self._c(self.cl.cmd_stop(quick))

    def set_output(self, n, v):
        self._c(self.cl.cmd_set_output(n, v))

    def pulse_output(self, n, ms):
        self._c(self.cl.cmd_pulse_output(n, ms))

    def enable_drive(self, on):
        self._c(self.cl.cmd_enable(on))

    def zero_position(self):
        self._c(self.cl.cmd_zero())

    def reset_faults(self):
        self._c(self.cl.cmd_reset_faults())

    def heartbeat(self, now):
        self.cl.heartbeat()

    def pop_errors(self):
        e, self.errors = self.errors, []
        return e


def test_full_job_through_the_protocol(link):
    from belt_marking_control.core import ControlConfig, CutMode, Job, MachineController, State
    cl, fw = link
    assert wait(lambda: cl.link_ok)
    cfg = ControlConfig()
    cfg.use_sim = True
    ctrl = MachineController(ClientHal(cl), cfg, now=time.monotonic())
    ctrl.cmd_reset()

    def run_until(pred, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end and not pred():
            ctrl.tick(time.monotonic())
            time.sleep(0.01)
        return pred()
    assert run_until(lambda: ctrl.state == State.IDLE, 5), ctrl.log[-5:]
    ok, msg = ctrl.cmd_start(Job(job_id='SER', quantity=2, pitch_mm=20.0, mark_length_mm=10.0,
                                 lead_mm=2.0, cut_mode=CutMode.EVERY, laser_time_s=0.2,
                                 settle_s=0.02, feed_speed_mm_s=60.0))
    assert ok, msg
    assert run_until(lambda: ctrl.state == State.COMPLETE, 20), ctrl.log[-8:]
    assert [round(m.belt_coord_mm, 2) for m in fw.plant.marks] == [0.0, 20.0]
    assert [round(c, 2) for c in fw.plant.cuts] == [18.0, 38.0]
