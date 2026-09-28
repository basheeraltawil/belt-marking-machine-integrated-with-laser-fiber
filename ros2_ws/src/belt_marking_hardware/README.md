# belt_marking_hardware

The hardware layer. Two interchangeable implementations serve the same ROS contract:

| | `serial_bridge_node` (real) | `sim_hardware_node` (sim) |
|---|---|---|
| backend | Arduino Mega over USB, framed protocol (docs/SERIAL_PROTOCOL.md) | `FakePlant` model |
| `hw/io_status` | `IoStatus` at 50 Hz | same |
| `hw/command` | `HwCommand` service | same |
| `hw/heartbeat` | forwarded to the firmware watchdog | feeds the plant watchdog |
| extras | lifecycle node, auto-reconnect | `sim/inject_fault`, `sim/plant_events` |

Python modules:
* `hal.py`: `HardwareInterface`, `IoSnapshot`, output/input bit maps
* `fake_plant.py`: stepper trapezoid (integer steps), knife cylinder, lasers, belt supply,
  fork sensor, encoder/slip, firmware interlocks + watchdog, fault injection
* `plant_hal.py`: in-process HAL for tests and accelerated simulation
* `ros_hal.py`: `RosHardwareClient`, the HAL over ROS used by `control_node`
* `protocol.py`: frame codec + CRC16 (shared with `tools/serial_console.py`)

```bash
ros2 run belt_marking_hardware sim_hardware_node --ros-args -p laser_marking_time_s:=1.0
ros2 service call /sim/inject_fault belt_marking_interfaces/srv/InjectFault "{fault: belt_runout, enable: true, value: 50.0}"
```
