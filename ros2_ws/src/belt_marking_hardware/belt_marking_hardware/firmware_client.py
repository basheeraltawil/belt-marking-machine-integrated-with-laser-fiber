"""Host side of the serial protocol + a virtual firmware for tests without hardware.

* :class:`FirmwareClient`: talks to the Arduino (or the virtual firmware). It exposes the
  same ``cmd_*`` API as :class:`FakePlant`, so ``ros_conv.dispatch`` serves both.
* :class:`VirtualFirmware`: the plant model behind the real protocol (``tools/`` uses it on
  a pseudo-terminal, and the tests use it through an in-memory pipe).
"""

import math
import queue
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from . import protocol as P
from .fake_plant import FakePlant, PlantConfig
from .hal import IoSnapshot, MAX_STATIONS, OUTPUT_BITS, OUTPUT_NAMES


# ------------------------------------------------------------------ transports
class SerialTransport:
    """pyserial wrapper (imported lazily so tests/CI don't need pyserial)."""

    MAX_EMPTY_READS = 50     # consecutive spurious 'no data' errors before giving up

    def __init__(self, port: str, baud: int = 115200):
        import serial  # noqa: PLC0415 - optional dependency
        self.serial = serial
        self.ser = serial.Serial(port, baud, timeout=0.02, write_timeout=0.2)
        self.ser.reset_input_buffer()
        self._empty = 0

    def write(self, data: bytes) -> None:
        self.ser.write(data)

    def read(self, n: int = 256) -> bytes:
        try:
            data = self.ser.read(max(1, min(n, self.ser.in_waiting or 1)))
        except self.serial.SerialException as exc:
            # pseudo-terminals (and some USB-CDC stacks) report spurious readiness; only a
            # persistent condition means the device is gone
            if 'returned no data' not in str(exc):
                raise
            self._empty += 1
            if self._empty > self.MAX_EMPTY_READS:
                raise
            time.sleep(0.005)
            return b''
        self._empty = 0
        return data

    def close(self) -> None:
        self.ser.close()


class PipeEnd:
    """One end of an in-memory full-duplex byte pipe."""

    def __init__(self, rx: 'queue.Queue', tx: 'queue.Queue'):
        self.rx, self.tx = rx, tx
        self.closed = False

    def write(self, data: bytes) -> None:
        if not self.closed:
            self.tx.put(bytes(data))

    def read(self, n: int = 256) -> bytes:
        try:
            return self.rx.get(timeout=0.02)
        except queue.Empty:
            return b''

    def close(self) -> None:
        self.closed = True


def pipe_pair() -> Tuple[PipeEnd, PipeEnd]:
    """Two connected in-memory transports (tests)."""
    a, b = queue.Queue(), queue.Queue()
    return PipeEnd(a, b), PipeEnd(b, a)


# ---------------------------------------------------------------------- client
class FirmwareClient:
    """Host side of the serial protocol; same cmd_* API as FakePlant."""

    def __init__(self, transport, steps_per_mm: float = 69.0, num_stations: int = 1,
                 ack_timeout_s: float = 0.1, retries: int = 3, status_timeout_s: float = 0.5,
                 encoder_counts_per_mm: float = 0.0):
        self.t = transport
        self.spm = steps_per_mm
        self.n = num_stations
        self.ack_timeout = ack_timeout_s
        self.retries = retries
        self.status_timeout = status_timeout_s
        self.enc_cpm = encoder_counts_per_mm
        self.parser = P.Parser()
        self.status: Optional[P.Status] = None
        self.status_time = 0.0
        self.info = None
        self.events: List[Tuple[str, int]] = []
        self.on_event: Optional[Callable[[str, int], None]] = None
        self._seq = 0
        self._pending: Dict[int, dict] = {}
        self._lock = threading.Lock()
        self._tx_lock = threading.Lock()
        self._running = True
        self.io_error: Optional[str] = None
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    # --------------------------------------------------------------- plumbing
    def close(self) -> None:
        self._running = False
        self._reader.join(timeout=1.0)
        self.t.close()

    def _read_loop(self) -> None:
        while self._running:
            try:
                data = self.t.read(256)
            except Exception as exc:  # noqa: BLE001 - serial unplugged etc.
                self.io_error = str(exc)
                self._running = False
                return
            if data:
                for frame in self.parser.feed(data):
                    self._handle(frame)

    def _handle(self, f: P.Frame) -> None:
        try:
            fields = f.fields()
        except ValueError:
            return
        if f.msg_id == P.STATUS:
            self.status = P.Status(*fields)
            self.status_time = time.monotonic()
        elif f.msg_id in (P.ACK, P.NAK):
            seq = fields[0]
            with self._lock:
                pend = self._pending.get(seq)
            if pend is not None:
                pend['ok'] = f.msg_id == P.ACK
                pend['reason'] = '' if f.msg_id == P.ACK else P.nak_reason(fields[2])
                pend['event'].set()
        elif f.msg_id == P.INFO:
            proto, n, version = fields
            self.info = {'protocol': proto, 'stations': n,
                         'version': version.rstrip(b'\0').decode(errors='replace')}
        elif f.msg_id == P.EVENT:
            name = P.EVENT_CODES.get(fields[0], str(fields[0]))
            self.events.append((name, fields[1]))
            if self.on_event:
                self.on_event(name, fields[1])

    def _write(self, data: bytes) -> None:
        with self._tx_lock:
            self.t.write(data)

    def request(self, msg_id: int, payload: bytes = b'') -> Tuple[bool, str]:
        """Send a command and wait for ACK/NAK (with retries)."""
        with self._lock:
            self._seq = self._seq % 255 + 1          # 1..255, 0 = unsolicited
            seq = self._seq
            pend = {'event': threading.Event(), 'ok': False, 'reason': 'timeout'}
            self._pending[seq] = pend
        frame = P.encode(msg_id, seq, payload)
        try:
            for _ in range(self.retries):
                self._write(frame)
                if pend['event'].wait(self.ack_timeout):
                    return pend['ok'], pend['reason'] or 'ok'
            return False, 'no reply from firmware'
        except Exception as exc:  # noqa: BLE001
            self.io_error = str(exc)
            return False, f'serial error: {exc}'
        finally:
            with self._lock:
                self._pending.pop(seq, None)

    # --------------------------------------------------- FakePlant-compatible API
    def heartbeat(self) -> None:
        try:
            self._write(P.encode(P.HEARTBEAT, 0, P.pack(P.HEARTBEAT,
                                                        int(time.monotonic() * 1000) &
                                                        0xFFFFFFFF)))
        except Exception as exc:  # noqa: BLE001
            self.io_error = str(exc)

    def get_info(self) -> Tuple[bool, str]:
        return self.request(P.GET_INFO)

    def cmd_move_rel(self, distance_mm, speed_mm_s=0.0, accel_mm_s2=0.0, motion_id=0):
        return self.request(P.MOVE_REL, P.pack(
            P.MOVE_REL, int(round(distance_mm * self.spm)), float(speed_mm_s * self.spm),
            float(accel_mm_s2 * self.spm), int(motion_id) & 0xFFFF))

    def cmd_jog(self, direction, speed_mm_s, duration_ms, motion_id=0):
        return self.request(P.JOG, P.pack(P.JOG, 1 if direction >= 0 else -1,
                                          float(speed_mm_s * self.spm),
                                          min(int(duration_ms), 0xFFFF),
                                          int(motion_id) & 0xFFFF))

    def cmd_stop(self, quick=False):
        return self.request(P.STOP, P.pack(P.STOP, 1 if quick else 0))

    def cmd_set_output(self, name, state):
        if name not in OUTPUT_BITS:
            return False, f'unknown output {name!r}'
        return self.request(P.SET_OUTPUT, P.pack(P.SET_OUTPUT, OUTPUT_BITS[name], 1 if state
                                                 else 0))

    def cmd_pulse_output(self, name, duration_ms):
        if name not in OUTPUT_BITS:
            return False, f'unknown output {name!r}'
        return self.request(P.PULSE_OUTPUT, P.pack(P.PULSE_OUTPUT, OUTPUT_BITS[name],
                                                   min(int(duration_ms), 0xFFFF)))

    def cmd_enable(self, on):
        return self.request(P.ENABLE, P.pack(P.ENABLE, 1 if on else 0))

    def cmd_zero(self):
        return self.request(P.ZERO)

    def cmd_reset_faults(self):
        return self.request(P.RESET_FAULTS)

    def set_config(self, key: str, value: float):
        return self.request(P.SET_CONFIG, P.pack(P.SET_CONFIG, P.CONFIG_KEYS[key],
                                                 float(value)))

    # ------------------------------------------------------------------ status
    @property
    def link_ok(self) -> bool:
        return self.status is not None and self.io_error is None and \
            time.monotonic() - self.status_time < self.status_timeout

    def snapshot(self) -> IoSnapshot:
        s = self.status
        snap = IoSnapshot(stamp=time.monotonic(), link_ok=self.link_ok, source='serial',
                          fw_version=(self.info or {}).get('version', ''))
        if s is None:
            return snap
        snap.fw_uptime_ms = s.fw_ms
        ins = IoSnapshot.decode_inputs(s.inputs)
        for name in ('estop_ok', 'door_closed', 'safety_relay_ok', 'belt_present',
                     'knife_extended', 'knife_retracted', 'knife_start', 'driver_fault',
                     'home_sensor'):
            setattr(snap, name, ins[name])
        snap.air_pressure_ok = ins['air_pressure_ok']
        snap.laser_busy = [ins[f'laser_busy_{i}'] for i in range(MAX_STATIONS)]
        snap.outputs, snap.stepper_enabled = IoSnapshot.decode_outputs(s.outputs)
        snap.position_steps = s.pos_steps
        snap.position_mm = s.pos_steps / self.spm
        snap.velocity_mm_s = s.speed_steps_s / self.spm
        snap.moving = bool(s.flags & P.Status.MOVING)
        snap.motion_id = s.motion_id
        snap.encoder_mm = (s.encoder / self.enc_cpm) if self.enc_cpm > 0 else math.nan
        snap.fault_flags = s.faults
        return snap


# ------------------------------------------------------------- virtual firmware
_NAK_CODES = [('interlock', 3), ('fault', 4), ('busy', 5), ('disabled', 6), ('unknown', 7),
              ('safety', 4), ('heartbeat', 4)]


class VirtualFirmware:
    """FakePlant behind the real protocol, mimicking firmware/arduino_mega."""

    def __init__(self, transport, cfg: Optional[PlantConfig] = None, status_hz: float = 50.0,
                 physics_hz: float = 500.0, version: str = 'virtual-1.0.0'):
        self.t = transport
        self.plant = FakePlant(cfg or PlantConfig())
        self.spm = self.plant.cfg.steps_per_mm
        self.parser = P.Parser()
        self.version = version
        self.status_period = 1.0 / status_hz
        self.dt = 1.0 / physics_hz
        self._last = None      # (seq, id) for de-duplication
        self._running = True
        self.rx_frames = 0
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def close(self):
        self._running = False
        self._thread.join(timeout=1.0)

    def _send(self, msg_id, seq, *fields):
        self.t.write(P.encode(msg_id, seq, P.pack(msg_id, *fields)))

    def _loop(self):
        t_prev = time.monotonic()
        t_status = 0.0
        self._send(P.EVENT, 0, 1, 0)                            # boot event
        while self._running:
            data = self.t.read(256)
            for f in self.parser.feed(data):
                self.rx_frames += 1
                self._handle(f)
            now = time.monotonic()
            while now - t_prev >= self.dt:
                self.plant.step(self.dt)
                t_prev += self.dt
            if now - t_status >= self.status_period:
                t_status = now
                self._status()

    def _status(self):
        snap = self.plant.snapshot()
        flags = (P.Status.MOVING if snap.moving else 0) | \
            (P.Status.ENABLED if snap.stepper_enabled else 0) | \
            (P.Status.JOGGING if self.plant.jog_dir else 0)
        enc = int(round(snap.encoder_mm * self.spm)) if not math.isnan(snap.encoder_mm) else 0
        st = P.Status(snap.fw_uptime_ms & 0xFFFFFFFF, snap.position_steps,
                      snap.velocity_mm_s * self.spm, snap.motion_id & 0xFFFF, flags,
                      snap.input_bits(), snap.output_bits(), snap.fault_flags, enc)
        self.t.write(P.encode(P.STATUS, 0, st.to_payload()))

    def _reply(self, f: P.Frame, ok: bool, why: str = ''):
        if ok:
            self._send(P.ACK, 0, f.seq, f.msg_id)
            return
        code = next((c for key, c in _NAK_CODES if key in why), 7)
        self._send(P.NAK, 0, f.seq, f.msg_id, code)

    def _handle(self, f: P.Frame):
        try:
            fields = f.fields()
        except ValueError:
            self._send(P.NAK, 0, f.seq, f.msg_id, 2 if f.msg_id in P._FORMATS else 1)
            return
        if f.msg_id == P.HEARTBEAT:
            self.plant.heartbeat()
            return
        if (f.seq, f.msg_id) == self._last:            # retransmission: ACK again only
            self._send(P.ACK, 0, f.seq, f.msg_id)
            return
        self._last = (f.seq, f.msg_id)
        p = self.plant
        if f.msg_id == P.GET_INFO:
            self._send(P.INFO, 0, P.PROTOCOL_VERSION, len(p.lasers),
                       self.version.encode()[:16].ljust(16, b'\0'))
            ok, why = True, ''
        elif f.msg_id == P.MOVE_REL:
            steps, speed, accel, mid = fields
            ok, why = p.cmd_move_rel(steps / self.spm, speed / self.spm, accel / self.spm, mid)
        elif f.msg_id == P.JOG:
            d, speed, dur, mid = fields
            ok, why = p.cmd_jog(d, speed / self.spm, dur, mid)
        elif f.msg_id == P.STOP:
            ok, why = p.cmd_stop(bool(fields[0]))
        elif f.msg_id == P.ENABLE:
            ok, why = p.cmd_enable(bool(fields[0]))
        elif f.msg_id == P.ZERO:
            ok, why = p.cmd_zero()
        elif f.msg_id in (P.SET_OUTPUT, P.PULSE_OUTPUT):
            idx, val = fields
            if idx >= len(OUTPUT_NAMES):
                ok, why = False, 'unknown output'
            elif f.msg_id == P.SET_OUTPUT:
                ok, why = p.cmd_set_output(OUTPUT_NAMES[idx], bool(val))
            else:
                ok, why = p.cmd_pulse_output(OUTPUT_NAMES[idx], val)
        elif f.msg_id == P.RESET_FAULTS:
            ok, why = p.cmd_reset_faults()
        elif f.msg_id == P.SET_CONFIG:
            key, value = fields
            if key == P.CONFIG_KEYS['heartbeat_timeout_ms']:
                p.cfg.watchdog_s = value / 1000.0
            ok, why = True, ''
        else:
            ok, why = False, 'unknown'
        self._reply(f, ok, why)
