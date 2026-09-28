from belt_marking_laser import (DoneMode, DryContactLaser, LaserConfig, LaserPoll,
                                SimCo2Laser)


class Bench:
    """A pedal relay wired to a simulated laser, stepped in 10 ms increments."""

    def __init__(self, marking_time=1.0, done_mode=DoneMode.SIGNAL):
        self.t = 0.0
        self.pulse_until = -1.0
        self.sim = SimCo2Laser(station=0, marking_time_s=marking_time)
        self.laser = DryContactLaser(self, 0, LaserConfig(pulse_ms=200, done_mode=done_mode))

    # LaserIoPort
    def pulse_output(self, name, duration_ms):
        assert name == 'laser_0'
        self.pulse_until = self.t + duration_ms / 1000.0

    def laser_busy(self, station):
        return self.sim.busy

    def run_until_result(self, limit=30.0):
        while self.t < limit:
            self.sim.update(self.t, self.t < self.pulse_until, True)
            res = self.laser.poll_done(self.t)
            if res.status != LaserPoll.PENDING:
                return res
            self.t += 0.01
        raise AssertionError('no result')


def test_signal_mode_done():
    b = Bench(marking_time=1.0)
    b.laser.trigger(b.t, 1.0)
    res = b.run_until_result()
    assert res.status == LaserPoll.DONE
    assert abs(res.busy_time_s - 1.0) < 0.05
    assert b.sim.jobs_done == 1


def test_signal_mode_no_ack():
    b = Bench()
    b.sim.faults.no_response = True
    b.laser.trigger(b.t, 1.0)
    assert b.run_until_result().status == LaserPoll.NO_ACK


def test_signal_mode_timeout():
    b = Bench(marking_time=1.0)
    b.sim.faults.late_s = 10.0
    b.laser.trigger(b.t, 1.0)
    res = b.run_until_result()
    assert res.status == LaserPoll.TIMEOUT
    assert b.t >= 1.0 * 2 + 2 - 0.02


def test_timed_mode_ignores_busy():
    b = Bench(marking_time=5.0, done_mode=DoneMode.TIMED)
    b.laser.trigger(b.t, 0.5)
    res = b.run_until_result()
    assert res.status == LaserPoll.DONE
    assert 0.69 <= b.t <= 0.72   # 200 ms pulse + 0.5 s


def test_pedal_held_does_not_retrigger():
    sim = SimCo2Laser(station=0, marking_time_s=0.1, start_latency_s=0.0)
    t = 0.0
    while t < 1.0:
        sim.update(t, True, True)
        t += 0.01
    assert sim.jobs_done == 1


def test_interlock_blocks_start():
    sim = SimCo2Laser(station=0, marking_time_s=0.1)
    sim.update(0.0, True, False)
    sim.update(0.5, True, False)
    assert sim.jobs_done == 0 and not sim.busy


def test_wait_done_blocking_helper():
    b = Bench(marking_time=0.3)

    def clock():
        return b.t

    def sleep(dt):
        b.sim.update(b.t, b.t < b.pulse_until, True)
        b.t += dt

    b.laser.trigger(b.t, 0.3)
    assert b.laser.wait_done(5.0, clock=clock, sleep=sleep).status == LaserPoll.DONE
