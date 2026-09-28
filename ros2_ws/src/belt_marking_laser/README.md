# belt_marking_laser

Pure-Python laser abstraction (no ROS dependency).

* `LaserInterface`: `trigger(now, marking_time)`, `is_busy(now)`, `poll_done(now)`,
  `wait_done(timeout)`. The machine controller uses only this.
* `DryContactLaser`: the real integration. It pulses the pedal relay (a dry contact in
  parallel with the foot pedal) and detects completion either from the controller's
  busy/done output (`signal`) or from a configured marking time (`timed`). Result: `DONE`,
  `NO_ACK` (busy never rose), `TIMEOUT`.
* `SimCo2Laser`: device model of a CO2 laser controller in foot-switch mode (start on the
  closing edge, busy for the design time, blocked by the enclosure interlock) with
  injectable faults `no_response`, `late_s`, `weak_mark`, `stuck_busy`.

A fiber/UV laser, or a controller with an Ethernet/RS-232 API, is added by implementing
`LaserInterface`.
