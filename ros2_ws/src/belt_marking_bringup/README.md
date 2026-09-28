# belt_marking_bringup

Launch files and the **single machine configuration** (`config/machine.yaml`). The loader
(`config_loader.py`) maps it onto the parameters of every node, so offsets, speeds and
timeouts are never duplicated.

| Launch | What |
|---|---|
| `sim.launch.py` | plant model + control + Gazebo twin + RViz + UI + vision (`gazebo:=false`, `rviz:=false`, `ui:=false`, `vision:=false`, `headless:=true`) |
| `multi_laser_sim.launch.py` | same with `config/multi_laser.yaml` overlay (2 stations, 0/150 mm, delays 0/0.3 s, knife 230 mm) |
| `real.launch.py` | serial bridge to the Arduino + control + UI (`kiosk:=true` on the Pi). Loads `~/.belt_marking/calibration.yaml` and an optional site `overlay:=` |

```bash
ros2 launch belt_marking_bringup sim.launch.py
ros2 launch belt_marking_bringup multi_laser_sim.launch.py
ros2 launch belt_marking_bringup real.launch.py kiosk:=true overlay:=/etc/belt_marking/site.yaml
```

Overlays are partial YAML files merged on top of `machine.yaml`, e.g. a site file:

```yaml
machine: {knife_offset_mm: 55.4}
laser: {done_mode: timed, pulse_ms: 150}
hardware: {steps_per_mm: 70.05}
```

Tests: `test_config.py` (every ControlConfig key present in machine.yaml) and
`test_sim_stack_launch.py` (launch_testing: real node graph, RunJob action, belt run-out
fault → HELD → resume).
