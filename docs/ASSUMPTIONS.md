# Assumptions and open points

Every value that could not be taken from a datasheet, the legacy code or the
owner's description is listed here. The matching config keys are marked
`# TODO: verify on hardware`. Tick an item off during commissioning
([IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)) and record the measured
value.

Status legend: **L** = taken from legacy code (plausible, still verify) ·
**O** = owner statement · **A** = assumption by the upgrade · **D** = design choice.

## Mechanics / motion

| ID | Item | Value used | Source | Config key |
|---|---|---|---|---|
| A-01 | Feed scale | 69.0 steps/mm | L (`69.0 * mm` in `makine_kodu.ino`) | `hardware.steps_per_mm` |
| A-02 | Laser station 0 → knife distance | 56.0 mm | L (`metalw = 56.0`, "METAL WIDTH FORWARD") | `machine.knife_offset_mm` |
| A-03 | Max feed speed | 14.5 mm/s default, 60 mm/s limit | L (1000 steps/s bit-banged); limit is A | `hardware.max_speed_mm_s` |
| A-04 | Acceleration | 100 mm/s² | A (legacy had none) | `hardware.accel_mm_s2` |
| A-05 | DM542 micro-step / current DIP settings | unknown | – | document in ELECTRICAL.md after inspection |
| A-06 | Drive roller diameter (for URDF only) | 40 mm | A (from video proportions) | `roller_diameter` xacro arg |
| A-07 | Conveyor length / width (URDF only) | 600 mm / 120 mm usable | A (from video) | xacro args |
| A-08 | Belt width range | 10–100 mm | A | `machine.belt_width_min_mm`, `..._max_mm` |
| A-09 | There is no home/reference sensor. Position is zeroed at job start | – | L | `hardware.has_home_sensor: false` |
| A-10 | There is no encoder, so belt-slip detection is only active if an encoder is added | – | A | `hardware.encoder_enabled: false` |
| A-11 | Fork sensor position | 350 mm upstream of station 0 | A (video) | `machine.fork_sensor_offset_mm` |
| A-12 | Laser marking field along the belt | 50 mm | A | `laser.field_length_mm` |
| A-13 | AccelStepper on the Mega is limited to about 4000 steps/s (≈ 58 mm/s at 69 steps/mm) | – | D | `DEFAULT_MAX_SPEED_STEPS_S` in `config.h` |

## Pneumatics

| ID | Item | Value used | Source | Config key |
|---|---|---|---|---|
| A-20 | Knife valve is a 5/2 double-solenoid, 2 relays (pin 42 = extend, pin 40 = retract) | – | L (pins), A (which is extend) | `pins.h` |
| A-21 | Knife sensor on pin 7 = extended, pin 5 = retracted | – | A (legacy names "right/left") | `pins.h` |
| A-22 | Knife extend / retract timeout | 1500 ms / 1500 ms | A (legacy waited 500 ms each, without verification) | `knife.extend_timeout_s` / `knife.retract_timeout_s` |
| A-23 | Knife dwell at extended | 100 ms | A | `knife.dwell_s` |
| A-24 | Simulated stroke times | 300 ms / 300 ms | A | `sim.knife_stroke_time_s` |
| A-25 | Z-Air (pin 44) is a hold-down / air assist, energised while marking | – | L (timing) + A (function) | `zair.during_mark` |
| A-26 | Supply pressure | 6 bar | A (typical) | PNEUMATICS.md |
| A-27 | An air-pressure switch exists or will be added | – | A (not in BOM) | `inputs.air_pressure.enabled` |

## Electrical / I/O

| ID | Item | Value used | Source |
|---|---|---|---|
| A-30 | The relay module is active-LOW | – | L (`HIGH` = off in `setup()`) |
| A-31 | Fork sensor: `LOW` = belt present | – | L (`ents_m == LOW` → run) |
| A-32 | Sensors are 24 V PNP and are interfaced to the Mega through optocouplers | – | A (the legacy PCB is undocumented) |
| A-33 | Knife-start sensor = pin 9 (legacy `ps_s`, unused) | – | A |
| A-34 | TDK-Lambda DSP model / rating | unknown (assume 24 V ≥ 2.5 A) | A |
| A-35 | E-stop / door / safety-relay monitor inputs are new wiring | pins in `pins.h` | D |
| A-36 | DM542 alarm output (ALM) is wired to an input | pin 37 | D |

## Laser

| ID | Item | Value used | Source | Config key |
|---|---|---|---|---|
| A-40 | Laser type | CO2, own controller and software | O | – |
| A-41 | Trigger = dry contact across the foot-pedal input | – | O | – |
| A-42 | Trigger pulse length | 200 ms | A (legacy held the relay for the whole marking time) | `laser.pulse_ms` |
| A-43 | The controller has a "work done / busy" output (Ruida-type controllers usually do; the pin and polarity depend on the model) | optional | A | `laser.done_mode: signal\|timed` |
| A-44 | Busy signal polarity | active-HIGH after the optocoupler | A | `laser.busy_active_high` |
| A-45 | Marking time default | 3.0 s | A (the legacy UI asked for it per job) | job field `laser_time_s` |
| A-46 | Laser timeout = marking time × 2 + 2 s | – | D | `laser.timeout_factor`, `laser.timeout_margin_s` |
| A-47 | Time until busy must rise after the trigger | 1.0 s | A | `laser.ack_timeout_s` |
| A-48 | "Multiple laser machines" = N controllers on one conveyor, each with its own pedal relay and done input, each with an offset and a delay | up to 4 | O + D | `laser.stations` |

## Software / platform

Status: **A** = assumption, **D** = design choice.

| ID | Item | Value / decision |
|---|---|---|
| A-60 | LICENSE | The repository had no licence file. **MIT** was added, copyright Basheer Al-Tawil / AIBO Mechatronics. Change it if you prefer something else |
| A-61 | Raspberry Pi 5 | Officially supported from Ubuntu 23.10 / 24.04 onwards. Ubuntu 22.04 (needed for Humble binaries) runs on a Pi 4. For a Pi 5, use Ubuntu 24.04 + ROS 2 Jazzy (source-compatible, untested here) or run Humble in Docker on Raspberry Pi OS. See `raspberry_pi/README.md` |
| A-62 | Serial link | 115200 baud, USB CDC (Mega 16U2) |
| A-63 | Default UI language English, Turkish provided. Translations can be incomplete; missing keys fall back to English |
| A-64 | Default PINs (Operator 1111, Technician 2222, Admin 9999) **must be changed at commissioning** |
| A-65 | The legacy firmware variant B (`makine_kodu/makine_kodu.ino`) is taken as the deployed version |
| A-66 | The coolant/pump parts in the cabinet CAD are not part of the control scope |
| A-67 | The video appears to show a galvo marking head. The owner states the laser is CO2, so the docs use CO2. The `LaserInterface` stays type-agnostic |
| A-68 | Firmware watchdog arms at the first heartbeat. A board powered before the Pi does not latch a fault |
| A-69 | `control_node` waits 5 s after start before raising E-501 (hardware layer still starting) | 
| A-70 | Vision QA: camera 32 mm after station 0 (between laser and knife, inside the enclosure, with a laser-safe filter), `mm_per_px` 0.1, `min_contrast` 115 grey levels (from simulation measurements). **Calibrate on the machine** with good and deliberately weak marks |
| A-71 | Drift detector defaults: baseline 100 cycles, window 30, z > 4 and > 15 % change |
| A-72 | Label mark origin sits under station 0 at job start (the operator aligns the first label, as in 2019) |
