# belt_marking_control

Machine control, the same code for simulation and the real machine.

* `core/` (no ROS): `controller.py` (PackML state machine + job sequencer), `planner.py`
  (forward-only belt-coordinate planner), `job.py` (job model + validation), `alarms.py`
  (catalogue + manager), `db.py` (SQLite), `oee.py`, `config.py`, `sim_harness.py`
* `scenarios.py`: the 12 industrial scenarios, self-checking (`ros2 run belt_marking_control run_scenarios`)
* `control_node`: ROS adapter (action `machine/run_job`, services `machine/*`,
  `recipes/*`, topics `machine/state|alarms|events`)
* `rviz_markers_node`: belt, marks, cuts and state banner for RViz

See docs/STATE_MACHINE.md and docs/ARCHITECTURE.md §5.

```bash
ros2 run belt_marking_control run_scenarios            # all 12 scenarios, ~1 min
python3 -m pytest test/                                # unit + scenario tests
```
