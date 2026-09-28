# Maintenance

Lock out before any work: main switch off and locked, air shut-off closed and locked,
laser key removed. See the risk assessment.

## 1. Schedule

| Interval | Task | Who |
|---|---|---|
| Every shift | Visual check: guards, E-stop, belt tracking, marks readable, no alarms pending. Clean dust/fume residue in the marking area | operator |
| Weekly | Test the E-stop and the laser door interlock (the machine must stop / the laser must not fire). Drain the air filter. Clean the fork sensor optics and the camera window. `belt-backup` | technician |
| Monthly | Check the knife blade (burrs, chips) and cut quality; check reed switch positions; knife timing test (compare with baseline); clean rollers; check the pinch pressure | technician |
| 3 months | Check terminal screws and connectors (vibration); check the fume extraction filter; laser optics per the laser manufacturer; run the steps/mm wizard | technician |
| Yearly | Full SAT subset (SCENARIOS 6–10 physically); safety function proof test per the risk assessment; update the OS (`apt upgrade`) during a planned stop | technician + electrician |
| On W-701 (blade life) | Replace the blade → Calibration → *reset blade counter* | technician |
| On W-702 (cycle drift) | Check the component named in the alarm (knife: air pressure, flow controls, seals; laser: optics/power; feed: rollers, belt tension) | technician |

## 2. Predictive maintenance data

Every knife extend/retract, laser busy time and feed time is stored in the `cycle_times`
table. The anomaly detector (`belt_marking_vision/anomaly_node`, docs/AI_FEATURES.md)
raises W-702 when a component slows down. Export with
`python3 tools/export_logs.py` for offline analysis.

## 3. Spare parts

| Part | Qty on site | Note |
|---|---|---|
| Knife blade | 2 | type per the installed holder (TODO: record part number) |
| Reed switches for the cylinder | 2 | same type as installed |
| Cylinder seal kit | 1 | per the cylinder model |
| Valve coils 24 V | 1 | |
| Fork sensor (Di-Soric) | 1 | same model (TODO: record) |
| DM542 driver | 1 | DIP settings recorded in ELECTRICAL.md §7 |
| Arduino Mega 2560, flashed with the current firmware | 1 | label with the firmware version |
| 8-ch relay module / PhotoMOS relays | 1 | |
| SD card with the current image, or a USB SSD | 1 | make with `dd` after commissioning |
| Fuses for the 24 V circuits | set | |

## 4. Software maintenance

* **Backup / restore**: `belt-backup` (to a USB stick) and `belt-restore <archive>`.
* **Update**: `git pull && sudo ./raspberry_pi/setup_pi.sh` (rebuilds and reinstalls,
  keeps the DB, calibration and site.yaml).
* **Firmware update**: `pio run -t upload`, then the serial console I/O check. The
  firmware version appears in the bridge log (`connected to firmware x.y.z`).
* **Logs**: `journalctl -u belt-marking-ros`, `~/.ros/log` (rotated daily).
