# Serial protocol: Raspberry Pi ↔ Arduino Mega

Version **1**. Implementations:
[`protocol.py`](../ros2_ws/src/belt_marking_hardware/belt_marking_hardware/protocol.py) (host),
[`protocol.h/.cpp`](../firmware/arduino_mega/lib/protocol/) (firmware). Both have unit tests
against the same check values.

## 1. Physical layer

USB CDC (the Mega's 16U2), **115200 baud 8N1**, no flow control. The udev rule gives the
board a fixed name: `/dev/belt_arduino`.

Bandwidth: status 50 Hz × 32 B = 1.6 kB/s, plus commands. That is about 15 % of the 11.5 kB/s link.

## 2. Frame

```
+------+------+-----+-----+----+-------------+-------------+
| 0xAA | 0x55 | LEN | SEQ | ID | PAYLOAD[LEN] | CRC16 (LE)  |
+------+------+-----+-----+----+-------------+-------------+
```

* `LEN` 0…64, the payload length.
* `SEQ` is the host command sequence number, 1…255 wrapping. 0 is used for unsolicited firmware
  frames (STATUS, EVENT, ACK/NAK carry the acked sequence inside the payload).
* `CRC16-CCITT-FALSE`: polynomial 0x1021, init 0xFFFF, no reflection, no final XOR,
  computed over `LEN, SEQ, ID, PAYLOAD`. Check value: `crc16("123456789") = 0x29B1`.
* All fields are **little endian**. `f32` = IEEE-754 float.
* Parsers resynchronise on the next `AA 55` after garbage, an oversize `LEN` or a CRC error.

## 3. Messages

### Host → firmware

| ID | Name | Payload | Reply |
|---|---|---|---|
| 0x01 | HEARTBEAT | `u32 host_ms` | none |
| 0x02 | GET_INFO | – | ACK + INFO |
| 0x10 | MOVE_REL | `i32 steps, f32 speed_steps_s, f32 accel_steps_s2, u16 motion_id` | ACK/NAK |
| 0x11 | JOG | `i8 dir, f32 speed_steps_s, u16 duration_ms, u16 motion_id` | ACK/NAK |
| 0x12 | STOP | `u8 quick` (0 = decelerate) | ACK |
| 0x13 | ENABLE | `u8 on` | ACK/NAK |
| 0x14 | ZERO | – (position := 0) | ACK/NAK |
| 0x20 | SET_OUTPUT | `u8 output, u8 value` | ACK/NAK |
| 0x21 | PULSE_OUTPUT | `u8 output, u16 ms` (the firmware times the pulse) | ACK/NAK |
| 0x30 | SET_CONFIG | `u8 key, f32 value` | ACK/NAK |
| 0x31 | RESET_FAULTS | – (needs a fresh heartbeat) | ACK/NAK |

`SET_CONFIG` keys: 1 heartbeat timeout [ms], 2 debounce [ms], 3 input invert mask,
4 knife interlock (0/1), 5 max speed [steps/s].

### Firmware → host

| ID | Name | Payload |
|---|---|---|
| 0x80 | ACK | `u8 seq, u8 id` |
| 0x81 | NAK | `u8 seq, u8 id, u8 reason` (1 unknown, 2 bad length, 3 interlock, 4 fault active, 5 busy, 6 drive disabled, 7 bad parameter) |
| 0x90 | STATUS (50 Hz) | `u32 fw_ms, i32 pos_steps, f32 speed_steps_s, u16 motion_id, u8 flags, u16 inputs, u16 outputs, u16 faults, i32 encoder` (25 B) |
| 0x91 | INFO | `u8 protocol_version, u8 stations, char[16] fw_version` |
| 0x92 | EVENT | `u8 code, u16 data` (1 boot (data = MCUSR), 2 heartbeat lost, 3 E-stop, 4 driver alarm) |

`flags`: bit0 moving, bit1 drive enabled, bit2 jogging.

**Input bits** (after debounce and polarity): 0 estop_ok, 1 door_closed, 2 air_ok,
3 belt_present, 4 knife_extended, 5 knife_retracted, 6 knife_start, 7–10 laser_busy_0..3,
11 driver_fault, 12 safety_relay_ok, 13 home.

**Output bits**: 0 knife_extend, 1 knife_retract, 2 zair, 3 dc_motor, 4–7 laser_0..3,
8 light_red, 9 light_yellow, 10 light_green, 11 buzzer, 12 stepper_enable (status only).

**Fault bits** (= `IoStatus.FAULT_*`): 1 heartbeat lost (latched), 2 E-stop, 4 driver
alarm, 8 watchdog reset (latched), 16 interlock reject (latched), 32 knife sensor conflict,
64 RX overflow.

## 4. Reliability rules

* **ACK/NAK + retransmission.** The host waits 100 ms for the ACK and retries the *same
  frame* (same SEQ) up to 3 times. The firmware remembers the last `(SEQ, ID)`. A
  repeat is ACKed again but **not executed twice**, so a lost ACK never causes a double move.
* **Motion completion** is not an ACK. The host compares `STATUS.motion_id` with the id it
  sent and waits for `moving == 0`.
* **Heartbeat / watchdog.** The Pi sends HEARTBEAT every 100 ms, but only while
  `control_node` itself is alive (`hw/heartbeat` fresh < 300 ms). The firmware watchdog
  arms at the first heartbeat. After 500 ms without one it latches *heartbeat lost* and
  goes to the safe state: quick stop, lasers and aux off, knife retract on, red light.
  Motion and outputs are refused until `RESET_FAULTS`, which needs a fresh heartbeat
  (control_node sends it in RESETTING / CLEARING).
* **Link lost on the Pi side.** No STATUS for 500 ms raises E-501 → ABORTED.
* **Hardware watchdog.** The AVR WDT (250 ms) resets a hung loop. After such a reset the
  *WDT reset* fault bit and a boot EVENT are reported (→ E-503).
* **Interlocks** in the firmware (same rules in the simulation plant model): no belt
  motion unless the knife is retracted, no knife extend while moving, no laser pedal pulse
  with the door open, nothing but retract/lights while E-stop or heartbeat-lost is active.

## 5. Tools

```bash
python3 tools/serial_console.py /dev/belt_arduino     # interactive I/O check (sends heartbeats)
python3 tools/serial_console.py --virtual             # same, against the virtual firmware
python3 tools/virtual_firmware.py /tmp/vtty           # plant model on a pty for serial_bridge_node
```
