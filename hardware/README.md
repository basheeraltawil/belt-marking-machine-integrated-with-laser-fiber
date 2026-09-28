# Hardware reference

| Topic | Where |
|---|---|
| Pin map (source of truth) | [`firmware/arduino_mega/include/pins.h`](../firmware/arduino_mega/include/pins.h), table in [docs/ELECTRICAL.md §4](../docs/ELECTRICAL.md#4-pin-map-arduino-mega-2560) |
| Power, safety chain, pedal relay wiring, DM542 | [docs/ELECTRICAL.md](../docs/ELECTRICAL.md) |
| Pneumatic circuit | [docs/PNEUMATICS.md](../docs/PNEUMATICS.md) |
| Layout, BOM, cabinet | [docs/MECHANICAL.md](../docs/MECHANICAL.md) |
| Original cabinet CAD (SolidWorks, STEP, STL) | [`legacy/control_panel_design/`](../legacy/control_panel_design/) |
| 3D-printed parts (STL) | `legacy/control_panel_design/*.STL`: hinges, KART_HOLDER (PCB carrier), relay_support, cover, usb, switch_body |
| Laser-cut parts (STEP) | `legacy/control_panel_design/stepp_file/` and `step_dosyasi/` |

## Carrier PCB notes

The 2019 carrier PCB ("PCB card work", 200 TL) is not documented. For the upgrade, a new
carrier (or DIN-rail modules) should provide:

* 16 optocoupled 24 V inputs → Mega pins in `INPUT_PINS` order (PC817 or ISO1212-class digital inputs);
* 8 relay outputs, active LOW. Relays 5–8 are dry contacts with gold-plated or PhotoMOS contacts (laser pedals);
* 4 × 24 V low-side outputs (ULN2803 or MOSFET) for the light tower and buzzer;
* DM542 header (PUL/DIR/ENA/ALM), encoder header (pins 2/3);
* screw terminals labelled with the ELECTRICAL.md names, 24 V fused per group.

Put the as-built terminal plan and photos of the finished cabinet in this folder at commissioning.
