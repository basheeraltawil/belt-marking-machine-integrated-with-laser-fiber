# Arduino Mega 2560 firmware

Real-time I/O controller of the belt marking machine. It replaces the 2019 blocking
sketch (`legacy/machine_codes/`).

* **Non-blocking** cooperative loop (no `delay()`): serial parser, AccelStepper, 1 kHz
  debounced inputs, output pulse timers, heartbeat watchdog, 50 Hz status.
* **Fail-safe**: heartbeat watchdog (500 ms, armed by the first heartbeat) → quick stop,
  lasers/aux off, knife retract, red light. AVR hardware watchdog (250 ms). All outputs are
  driven to a defined state in `setup()` before anything else.
* **Interlocks** identical to the simulation plant model (see docs/SERIAL_PROTOCOL.md §4).
* E-stop / door / air are **monitored only**; the hardwired safety relay does the safety job.
* Pin map in [`include/pins.h`](include/pins.h) (legacy pins kept), settings in
  [`include/config.h`](include/config.h). Portable logic in `lib/` is unit tested on the PC.

```bash
pip install platformio
pio test -e native                                   # 12 unit tests, no board needed
pio run -e megaatmega2560                            # build (RAM ~8 %, flash ~6 %)
pio run -e megaatmega2560 -t upload --upload-port /dev/belt_arduino
python3 ../../tools/serial_console.py /dev/belt_arduino   # I/O check
```

Limits: AccelStepper on a 16 MHz AVR tops out around 4000 steps/s (≈ 58 mm/s at 69
steps/mm). For faster feeds use timer-driven step generation or a Teensy 4.1 (see
docs/ARCHITECTURE.md D1).
