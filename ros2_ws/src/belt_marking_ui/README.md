# belt_marking_ui

Touchscreen operator UI, **PyQt5 + rclpy** (apt `python3-pyqt5`, no browser). Designed for
the official 7" Raspberry Pi display (800×480): ≥ 48 px touch targets, on-screen numeric
keypad, and glove-friendly press-and-hold jog. English and Turkish (`language` parameter,
or switch in Settings).

| Screen | Content | Role |
|---|---|---|
| Production | START / HOLD / RESUME (retry/reject after laser timeout) / STOP / RESET / CLEAR, progress, counters, light tower | operator |
| Job setup | job id, belt width, marks, pitch, mark length, lead, cut mode (continuous / every / every N / end), laser time or done signal, delays, speed, stations (enable / offset / delay), validation + confirmation | operator |
| Recipes | load / save / duplicate / delete per belt type | technician (edit) |
| Manual | mode switch, jog ± (hold), feed X mm, cut now, trigger laser, Z-Air, zero | technician |
| Calibration | steps/mm wizard (→ `~/.belt_marking/calibration.yaml`), knife timing, laser test, blade counter, live sensor check | technician |
| Alarms | active (with remedy text) + history, acknowledge | operator |
| Logs / OEE | OEE tiles, lifetime counters, job table, CSV export to USB | operator |
| Settings | language, users + PINs, audit trail, **simulation fault injection** | admin / technician |

The UI only talks to `control_node` (action `machine/run_job`, services `machine/*`,
`recipes/*`) and reads history from the SQLite DB, so it runs on the same host. Job
validation uses the controller's own `validate()` with the limits from `machine.yaml`.

```bash
ros2 run belt_marking_ui operator_ui                              # with ROS
ros2 run belt_marking_ui operator_ui --ros-args -p kiosk:=true    # full screen, no cursor
ros2 run belt_marking_ui operator_ui --demo                       # no ROS (layout work)
```

Default PINs: operator 1111, technician 2222, admin 9999. **Change them at
commissioning.** Users are logged out automatically after 10 min without input.
