# belt_marking_description

Parametric xacro model of the machine: conveyor bed, supply reel, entry/drive/pinch/ejector
rollers, NEMA 23, Di-Soric fork sensor, **N CO2 laser stations** (enclosure, X/Y head gantry,
beam), traversing **knife cylinder** with extended/retracted reed sensors, QA camera, E-stop,
light tower and output bin.

| xacro arg | default | meaning |
|---|---|---|
| `belt_width` | 0.05 | belt width [m] (moves the guides) |
| `station_offsets` | `0.0` | laser station positions [m] along x, space separated |
| `knife_offset` | 0.056 | knife distance downstream of station 0 (legacy 56 mm) |
| `camera_offset` | 0.030 | QA camera position |
| `knife_stroke`, `laser_field`, `roller_diameter`, `conveyor_length` | | geometry |
| `gazebo` | false | add JointPositionController systems + camera sensor |

`joint_state_node` turns `hw/io_status` into `joint_states` (rollers from belt position,
knife from valves/sensors, laser head raster + beam while busy). It works identically on
the real machine, so RViz shows the live machine.

```bash
ros2 launch belt_marking_description view.launch.py station_offsets:="0.0 0.35"
```
