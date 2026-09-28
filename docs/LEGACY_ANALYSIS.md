# Legacy analysis (2019–2020 system)

All legacy material is preserved in [`legacy/`](../legacy/README.md). This
document records what it actually does, the evidence for each conclusion, and
what the new system changes. Where the evidence is thin, the conclusion is
marked **(inferred)** and listed in [`ASSUMPTIONS.md`](ASSUMPTIONS.md).

## 1. Inventory

| Item | Content | Notes |
|---|---|---|
| `legacy/README_original.md`, `legacy/docs/project_clarifications.pdf` | Timeline, BOM, cost list (525 TL), feature list | Same text in both |
| `legacy/machine_codes/makine_kodu.ino` (A) and `makine_kodu/makine_kodu.ino` (B) | 572-line Arduino Mega sketch | Differ in 2 lines (see §2.7) |
| `legacy/interface_design_coodes/KONTROL_KODU.pde` | 140-line Processing 3 + ControlP5 UI for a Windows PC | Serial to Arduino on `COM9` |
| `legacy/machine_working.mp4` | 52 s video, 400×224 | Shows the PC UI, a galvo marking head marking dark rectangular labels on a feed belt/tape, the feeder with rollers and the knife unit |
| `legacy/control_panel_design/` | 79 SolidWorks files + STL + STEP + 1 PDF drawing | Control **cabinet**, not the conveyor (see §4) |

There is **no** schematic, PCB file, or datasheet in the repository. The
cost list mentions "PCB card work (200 TL)", so a carrier PCB existed but is
not documented.

## 2. Original Arduino firmware

### 2.1 Pin map (from source)

| Pin | Name in code | Direction | Meaning (comment in code → interpretation) |
|---|---|---|---|
| 48 | `stepPin` | OUT | DM542 PUL |
| 50 | `dirPin` | OUT | DM542 DIR (`HIGH` = forward, `LOW` = backward) |
| 52 | `enblPin` | OUT | DM542 ENA (`LOW` written before every move; never set back) |
| 11 | `ent_s` | IN | "entrance sensor" → **Di-Soric fork light sensor**, belt/label present. `LOW` = belt present, `HIGH` = stops the loop |
| 7 | `r_ls` | IN | "right to left sensor" → knife cylinder end-position sensor 1 |
| 5 | `l_rs` | IN | "left to right sensor" → knife cylinder end-position sensor 2 |
| 9 | `ps_s` | IN | "dc motor starting sensor" → read but **never used**. Likely the "knife starting sensor" in the BOM **(inferred)** |
| 42 | `rl_r` | OUT | relay: knife valve solenoid A ("right to left") |
| 40 | `lr_r` | OUT | relay: knife valve solenoid B ("left to right") |
| 44 | `mlr_r` | OUT | relay: "middle pneumatic" → **Z-Air** valve. Switched exactly like the laser relay (on while marking) |
| 46 | `dcm_r` | OUT | relay: DC motor, "DC MOTOR REMOVAL MECHANISM" → piece ejector/removal after a cut |
| 38 | `lasersignal` | OUT | relay in parallel with the laser foot pedal |

Relays are **active-LOW** (the 8-channel module convention). `setup()` writes
`HIGH` to `dcm_r`, `mlr_r` and `lasersignal` (all off). The knife valve relays are
not initialised, so they come up energised (`LOW`) until the first cycle.

### 2.2 Serial protocol (Processing → Arduino)

9600 baud, ASCII, no framing, no checksum, no reply. The UI sends:

```
a<label_mm> b<laser_s> c<count> d<gap_mm> i<mode> j      (no spaces)
e.g.  a60b3c10d2ikesj
```

| Field | UI label (Turkish) | Meaning |
|---|---|---|
| `a..b` | "etikit boyutu (mm)" | label (piece) length in mm |
| `b..c` | "gecikme (saniye)" | laser delay in s. The laser relay is held closed this long, which is the marking time |
| `c..d` | "kaç adet" | number of labels |
| `d..e` | "boşluk değeri" | gap between labels in mm. Parsed up to an `e` that is never sent, so `substring` runs to the end of the string. It works only because `toFloat()` stops at `i` |
| `i..j` | mode | `kes` = cut each label, `kesm` = mark without cutting (one final cut), `br` = one piece ("bir adet") |

The Arduino reads with `Serial.readString()`, which blocks for the 1 s
default timeout. There is no acknowledgement, no status and no stop command.
The only way to stop a running job is to interrupt the fork sensor or reset
the board.

### 2.3 Motion

- Steps are bit-banged with `delayMicroseconds(500)` high + 500 low → about
  **1000 steps/s**, with no acceleration ramp.
- The scale is hard-coded at **69 pulses/mm** (`69.0 * mm`). With 1000 steps/s
  that gives about **14.5 mm/s** feed.
- `metalw = 56.0` mm ("METAL WIDTH FORWARD") is the distance the belt moves
  between the marking position and the knife **(inferred: laser-to-knife
  offset)**.
- Some cycles end with a **reverse** move (`dirPin LOW`, `rm2 - gap` pulses) to
  bring the next label back under the laser after cutting.

### 2.4 Cycle per mode (simplified)

`kes` (cut every label, only if label length > 56 mm, otherwise silently does nothing):
1. First label: Z-Air + laser relay ON for `laser_s`, then feed `label` mm, then Z-Air + laser ON again.
2. Each next label: feed 56 mm → knife cycle → DC motor 1 s pulse (with 1 s waits) → feed `label − 56` mm → laser ON for `laser_s`.
3. End: feed 56 mm → knife cycle → DC motor → **reverse** `56 − gap` mm.

`kesm` (mark continuously): per label, laser ON for `laser_s`, then feed
`label + gap` mm. At the end: laser once more, feed `label + gap + 56` mm, knife cycle,
DC motor, reverse `56 − gap` mm.

`br` (one piece): laser, feed `label + gap + 56`, knife, DC motor, reverse.

Knife cycle: reads both end sensors. For (1,0), (0,1) and (0,0) the relays
are sequenced B-off/A-on → wait 500 ms → A-off/B-on → wait 500 ms, so the
knife goes out and back. It is **time-based**: the sensors only select a
branch and are never checked for arrival. The (1,1) case, a sensor fault, does
nothing.

### 2.5 Laser synchronisation / "communication with other laser machines"

The only laser-related output is the relay on pin 38, held closed for the whole
"gecikme" time. The pedal of the laser controller is wired in parallel with it
(owner's description). `mlr_r` (pin 44) switches identically. The README calls
this "communication with other laser machines synchronously with equal
delays". In code terms that means **one or more laser controllers triggered from the
same relay event, with one common delay**. There is no done/busy feedback and no
per-machine delay.

### 2.6 Original UI (Processing)

800×800 window with a banner (`laser.png`), four text fields (label size,
delay, count, gap) with pictograms, and three buttons: **KESICEK** (cut),
**kesmicek** (don't cut), **biradet** (one piece). The port is hard-coded to
`COM9`. There is no status display, no input validation and no stop button (a commented-out
`STOP` button exists). The rotating circle and moving rectangle are decoration only.

### 2.7 Differences between firmware variants A and B

| Line | A (`machine_codes/makine_kodu.ino`) | B (`machine_codes/makine_kodu/makine_kodu.ino`) |
|---|---|---|
| 383 | `if (m = n - 1)` | `if (m = n)` |
| 551 | `for (i = 0; i < gapf2 + rm2; i++)` (reverse `56 + gap`) | `for (i = 0; i < rm2 - gapf2; i++)` (reverse `56 − gap`) |

Both use `=` (assignment), not `==`, so the condition is always true
(non-zero). B is the one in the Arduino-IDE folder layout and is treated as
the last-deployed version **(inferred)**.

## 3. Hardware: what each element does

| BOM element | Role in the machine | Evidence |
|---|---|---|
| NEMA 23 + DM542 | Drives the feed roller that indexes the belt/labels under the laser and to the knife | pins 48/50/52, motion code |
| DC motor (relay) | Piece removal/ejector after a cut ("DC MOTOR REMOVAL MECHANISM") | comment in code, 1 s pulse after each cut |
| Di-Soric fork light sensor | Belt/label present at the entrance. The job stops when it goes `HIGH` | `ent_s`, pin 11 |
| Pneumatic double-acting actuator + valve | Knife cylinder, driven by 2 relays (bistable/5-2 double-solenoid valve) | pins 40/42 |
| 2× pneumatic linear sensors | Knife cylinder end positions (reed switches) | pins 5/7 |
| Knife starting sensor | Probably pin 9 `ps_s`, read but unused **(inferred)** | pin 9 |
| Z-Air pneumatic + driver | Energised during marking, released during feed. Belt hold-down/clamp or air assist **(inferred)** | pin 44 timing |
| TDK-Lambda DSP | 24 V DIN-rail PSU (the exact model is not recorded) | BOM |
| 8-channel relay module | 5 channels used (38, 40, 42, 44, 46), active-LOW | code |

## 4. Mechanical parts (control cabinet)

The CAD folder is the **electrical control cabinet**, not the conveyor. Bounding
boxes were measured from the STEP/STL files:

| Part | Process | Size (mm) | Role |
|---|---|---|---|
| `basen`, `base` | laser cut | 300 × 100 × 10 | cabinet bottom plate |
| `baseup`, `baseupn` | laser cut | 300 × 103 × 10–34 | cabinet top plate (with handle) |
| `left_sidee`, `sides`, `right_side` | laser cut | 300–304 × 100 × 10–25 | side walls |
| `wall2` | laser cut, drawing `wall2.PDF` | 300 × 292 × 10 | back/mounting wall (drawing shows 400 × 444 outline at 1:5 for an earlier revision) |
| `holder` / `holderr` (×12) | laser cut / 3D | 100 × 24 × 10 / 23 × 15 × 23 | brackets that join the plates |
| `kapi` (door), `frontdoor` | laser cut | 298 × 300 × 20 / 308 × 304 × 5 | front door |
| `hinge*`, `revolute*`, `upper_revolute` | 3D printed | 53 × 22 × 37.5 / 29.5 × 27 × 23 | door hinges |
| `KART_HOLDER` | 3D printed | 127 × 127 × 10 | "PCB card protector", the carrier for the Arduino/PCB |
| `relay_support` | 3D printed | 150 × 60 × 24 | 8-channel relay module mount |
| `cover`, `usb`, `switch_body` | 3D printed | 40 × 44 × 7 / 25 × 35 × 21 / 40 × 30 × 50 | cable housing, panel USB socket, panel switch |
| `dm542`, `driver`, `7 INCH_DIN_RAIL`, B18 screws | model only | – | purchased components placed in the assembly |
| `pump`, `bottles*`, `circulation_pipe*`, `sensor_reservoir*`, `rubber pipe` | model only | – | a coolant/circulation reservoir sub-assembly. It is consistent with CO2 tube water cooling, but it isn't referenced anywhere else **(inferred)** |

Top-level assemblies: `last_assembly.SLDASM`, `assemblyy.SLDASM`,
`Assem1.SLDASM`, `switch.SLDASM`. The conveyor frame, rollers and knife
station have no CAD. The new URDF models them parametrically from the video and
the code constants.

## 5. Weaknesses fixed by the upgrade

| # | Weakness | Consequence | Fix in the new system |
|---|---|---|---|
| 1 | Everything blocks: `delay()`, `delayMicroseconds()`, `readString()` | No stop, no status, no reaction to sensors during motion | Non-blocking firmware: cooperative scheduler + AccelStepper |
| 2 | No E-stop, interlock or air-pressure handling | Unsafe. The laser can be triggered with the door open | Hardwired safety chain. Firmware and Pi only monitor it ([ELECTRICAL.md](ELECTRICAL.md)) |
| 3 | Knife is time-based and sensors are not verified | A jammed knife goes undetected. The belt feeds into an extended blade | Extend/retract are confirmed by sensors with timeouts, plus an alarm and safe retract |
| 4 | No laser feedback | Belt moves while the laser may still be marking | Done/busy input with a timed fallback and a timeout alarm |
| 5 | `if (m = n)` assignment bugs, `label > 56` mm silently required | Wrong final moves. Short labels do nothing in cut mode | Job planner with unit tests. Validation errors are shown to the operator |
| 6 | Hard-coded values (69 pulses/mm, 56 mm, 500 µs, COM9, delays) | Recalibration requires reflashing | YAML config + calibration wizard |
| 7 | Unframed ASCII protocol, no ACK, 9600 baud | Lost or partial commands go undetected | Framed binary protocol, CRC16, sequence numbers, ACK/NAK, heartbeat, 115200 baud |
| 8 | Laser relay held for the whole marking time | Relies on the laser accepting a long "pedal press" | Configurable pulse (e.g. 200 ms) + done signal |
| 9 | Reverse moves to re-align labels | Backlash and belt slack cause position error | Forward-only plan based on belt coordinates (§ ARCHITECTURE "job planner") |
| 10 | No counters, logs or recipes | No traceability | SQLite production log, alarm history, recipes, OEE |
| 11 | Stepper enable never released | Motor always energised, runs hot | Enable is managed (released in STOPPED after a timeout, configurable) |
| 12 | Relays for the knife valve not initialised | Undefined knife state at power-up | Firmware drives all outputs to a defined safe state before anything else |
