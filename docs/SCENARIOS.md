# Industrial simulation scenarios

Every scenario is **executable and self-checking**. The same definitions serve as the
simulation acceptance test and, later, as the site acceptance test (SAT) on the real
machine (§3).

| How | Command | Time |
|---|---|---|
| all scenarios, headless, accelerated | `ros2 run belt_marking_control run_scenarios` | ~1 min (8 h soak ≈ 25 s) |
| selected, JSON report | `ros2 run belt_marking_control run_scenarios 6 8 --json report.json` | |
| in CI (pytest, 2 h soak) | `colcon test --packages-select belt_marking_control` | |
| ROS graph level (action, services, fault injection) | `colcon test --packages-select belt_marking_bringup` | ~30 s |
| interactively (Gazebo + UI) | `ros2 launch belt_marking_bringup sim.launch.py`, then use Settings → fault injection | real time |

The scenario runner ([`scenarios.py`](../ros2_ws/src/belt_marking_control/belt_marking_control/scenarios.py))
drives the unchanged `MachineController` against the plant model (stepper, knife, lasers,
belt supply, firmware interlocks and watchdog) on a simulated clock. Positions are checked
against the plant's ground truth: where each mark actually landed on the belt and where
each cut was made.

## 1. Scenarios and acceptance criteria

Common setup unless stated: pitch 60 mm, mark 40 mm, lead 10 mm, knife 56 mm after
station 0, feed 30 mm/s, laser design time 0.5 s (done-signal mode).

| # | Scenario | Setup | Expected behaviour | Acceptance criteria |
|---|---|---|---|---|
| 1 | Continuous marking, no cut | 50 labels, cut mode *continuous* | 50 feed/mark stops, no knife motion | COMPLETE; 50 marks at k·60 mm ± 0.02 mm; 0 cuts; no alarm |
| 2 | Batch, cut every piece, fixed laser time | 100 labels, pitch 30, lead 5, **timed** mode 0.8 s (laser needs 0.6 s) | feed → mark (timed) → feed to knife → cut → eject, 100× | COMPLETE; 100 cuts at (k+1)·30−5 mm ± 0.02; 100 marks; 100 pieces ejected |
| 3 | Cut every 5 marks | 23 labels, *every N* = 5 | sets of labels, last set shorter | pieces of 5,5,5,5,3 labels; cut lines every 300 mm |
| 4 | Two laser stations in sync | stations at 0 / 150 mm, delays 0 / 0.4 s, laser times 0.5 / 0.8 s, knife 230 mm | each stop triggers both lasers (station 1 marks the label 150 mm behind) | both stations mark every label at k·60 ± 0.02; 12 triggers each; 12 cuts |
| 5 | Belt width change via recipe | recipes *narrow-20* (20 mm, pitch 40) and *wide-50* (50 mm, pitch 80) in the DB | job A, reset, job B | both COMPLETE; reported width follows the recipe; a 150 mm job is **refused** by validation (machine max 100 mm) |
| 6 | Fault: laser never reports done | after label 3, laser takes 30 s longer | E-201 after `0.5·2 + 2 = 3 s`, HOLD, belt stays still; operator resumes with RETRY or REJECT | HELD with E-201; no belt motion while waiting; job completes with 8 labels; rejects = 0 (retry) or 1 (reject) |
| 7 | Fault: knife does not reach extended sensor | knife sticks halfway after 2 pieces | E-301, automatic safe retract, HOLD | knife retracted, belt stopped; after fix + RESUME all 6 pieces cut exactly once |
| 8 | Fault: belt runs out mid-batch | fork sensor loses the belt after label 10 | E-401, HOLD; RESUME refused while no belt | counts preserved across the refill (10 → 30); 30 marks, 30 pieces |
| 9 | Fault: serial link lost | cable unplugged while moving | Pi: E-501 → ABORTED. Firmware: watchdog within 0.5 s → quick stop, knife retract on, lasers off | both sides safe; CLEAR after the link returns → STOPPED; RESET → IDLE |
| 10 | E-stop during cut | E-stop while the knife extends | ABORTED (E-101), drive disabled; CLEAR refused while pressed | after release: CLEAR → STOPPED → RESET retracts the knife → IDLE; a new job runs |
| 11 | Vision QA: unreadable marks | weak marks (e.g. dirty lens) after label 5; reject limit 3 | each bad label counted as reject (W-601); 3 in a row → E-602 HOLD | 3 rejects counted; after cleaning, resume; quality = 17/20 |
| 12 | Long-run soak with OEE | 8 simulated hours of 200-label batches (every 10 cut), with 3 injected faults (laser late, belt run-out, knife stuck) and an "operator bot" who resumes after 1 min | continuous production | no ABORT; all faults recovered; availability > 90 %; OEE report |

### Reference results (8 h soak)

```
53 batches, 10 498 labels, 1 049 pieces, 422 m of belt
availability 99.4 %  performance 94.2 %  quality 99.99 %  OEE 93.6 %
(simulated in 24 s wall time)
```

Performance < 100 % because the ideal cycle ignores settle/acceleration details. Quality
contains one label rejected during the laser-timeout recovery.

## 2. Fault injection (simulation)

`sim/inject_fault` (`belt_marking_interfaces/srv/InjectFault`), also available as buttons
in the UI (Settings → simulation):

| fault | value | effect |
|---|---|---|
| `laser_no_response` | – | laser ignores the pedal (→ E-203) |
| `laser_late` | extra seconds | job takes longer (→ E-201 if beyond the timeout) |
| `laser_weak_mark` | – | marks with poor contrast (vision rejects) |
| `laser_stuck_busy` | – | busy never drops |
| `knife_stuck_extend` / `knife_stuck_retract` | – | cylinder stops half way (→ E-301 / E-302) |
| `knife_sensor_conflict` | – | both reed sensors on (→ E-303) |
| `belt_runout` | mm still visible to the fork sensor | belt tail (→ E-401) |
| `belt_slip` | slip ratio, e.g. 0.05 | encoder differs from steps (→ E-402 if encoder enabled) |
| `estop`, `door_open`, `low_air`, `driver_fault` | – | safety/monitor inputs |
| `link_loss` | – | USB unplugged: no status, commands lost, firmware watchdog trips |
| `clear_all` | – | remove all faults (refill, repair) |

```bash
ros2 service call /sim/inject_fault belt_marking_interfaces/srv/InjectFault \
  "{fault: laser_late, enable: true, value: 20.0}"
```

## 3. Reuse as site acceptance test

On the real machine the same scenarios are run manually with the checklist in
[IMPLEMENTATION_GUIDE.md §10](IMPLEMENTATION_GUIDE.md#10-site-acceptance-test-sat). Faults
are provoked physically: unplug the laser busy wire (6), close the knife flow control
(7), cut the belt (8), unplug the USB cable (9), press the E-stop (10), defocus the laser
(11). Acceptance criteria are the same, with the mark position tolerance replaced by
the measured tolerance from calibration (typ. ± 0.3 mm).
