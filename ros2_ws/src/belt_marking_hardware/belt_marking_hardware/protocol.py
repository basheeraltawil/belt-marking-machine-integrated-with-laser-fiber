"""Pi <-> Arduino Mega framed serial protocol (docs/SERIAL_PROTOCOL.md).

Frame:  0xAA 0x55 | LEN | SEQ | ID | PAYLOAD[LEN] | CRC16 (little endian)
CRC16-CCITT-FALSE (poly 0x1021, init 0xFFFF) over LEN, SEQ, ID, PAYLOAD.
All multi-byte fields are little endian (native on AVR). Keep in sync with
firmware/arduino_mega/lib/protocol/protocol.h.
"""

from dataclasses import dataclass
import struct
from typing import List, Optional

SOF = b'\xAA\x55'
MAX_PAYLOAD = 64
PROTOCOL_VERSION = 1

# host -> firmware
HEARTBEAT = 0x01
GET_INFO = 0x02
MOVE_REL = 0x10
JOG = 0x11
STOP = 0x12
ENABLE = 0x13
ZERO = 0x14
SET_OUTPUT = 0x20
PULSE_OUTPUT = 0x21
SET_CONFIG = 0x30
RESET_FAULTS = 0x31
# firmware -> host
ACK = 0x80
NAK = 0x81
STATUS = 0x90
INFO = 0x91
EVENT = 0x92

NAK_REASONS = {1: 'unknown message', 2: 'bad length', 3: 'interlock', 4: 'fault active',
               5: 'busy', 6: 'drive disabled', 7: 'bad parameter'}
EVENT_CODES = {1: 'boot', 2: 'heartbeat lost', 3: 'estop', 4: 'driver alarm'}
CONFIG_KEYS = {'heartbeat_timeout_ms': 1, 'debounce_ms': 2, 'input_invert_mask': 3,
               'knife_interlock': 4, 'max_speed_steps_s': 5}

_FORMATS = {
    HEARTBEAT: '<I', GET_INFO: '', MOVE_REL: '<iffH', JOG: '<bfHH', STOP: '<B', ENABLE: '<B',
    ZERO: '', SET_OUTPUT: '<BB', PULSE_OUTPUT: '<BH', SET_CONFIG: '<Bf', RESET_FAULTS: '',
    ACK: '<BB', NAK: '<BBB', STATUS: '<IifHBHHHi', INFO: '<BB16s', EVENT: '<BH',
}


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def encode(msg_id: int, seq: int, payload: bytes = b'') -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError('payload too long')
    body = bytes([len(payload), seq & 0xFF, msg_id]) + payload
    return SOF + body + struct.pack('<H', crc16(body))


def pack(msg_id: int, *fields) -> bytes:
    return struct.pack(_FORMATS[msg_id], *fields)


def unpack(msg_id: int, payload: bytes) -> tuple:
    fmt = _FORMATS.get(msg_id)
    if fmt is None:
        raise ValueError(f'unknown message 0x{msg_id:02x}')
    if struct.calcsize(fmt) != len(payload):
        raise ValueError(f'bad length {len(payload)} for 0x{msg_id:02x}')
    return struct.unpack(fmt, payload) if fmt else ()


@dataclass
class Frame:
    msg_id: int
    seq: int
    payload: bytes

    def fields(self) -> tuple:
        return unpack(self.msg_id, self.payload)


class Parser:
    """Incremental, resynchronising frame parser (robust against garbage/partial data)."""

    def __init__(self):
        self.buf = bytearray()
        self.crc_errors = 0
        self.dropped_bytes = 0

    def feed(self, data: bytes) -> List[Frame]:
        self.buf.extend(data)
        frames = []
        while True:
            start = self.buf.find(SOF)
            if start < 0:
                keep = 1 if self.buf.endswith(SOF[:1]) else 0
                self.dropped_bytes += len(self.buf) - keep
                del self.buf[:len(self.buf) - keep]
                return frames
            if start:
                self.dropped_bytes += start
                del self.buf[:start]
            if len(self.buf) < 5:
                return frames
            length = self.buf[2]
            if length > MAX_PAYLOAD:
                del self.buf[:2]
                self.dropped_bytes += 2
                continue
            total = 2 + 3 + length + 2
            if len(self.buf) < total:
                return frames
            body = bytes(self.buf[2:5 + length])
            (crc,) = struct.unpack('<H', self.buf[5 + length:total])
            if crc != crc16(body):
                self.crc_errors += 1
                del self.buf[:2]            # resync on the next SOF
                continue
            frames.append(Frame(msg_id=body[2], seq=body[1], payload=body[3:]))
            del self.buf[:total]


@dataclass
class Status:
    fw_ms: int
    pos_steps: int
    speed_steps_s: float
    motion_id: int
    flags: int
    inputs: int
    outputs: int
    faults: int
    encoder: int

    MOVING = 1
    ENABLED = 2
    JOGGING = 4

    @staticmethod
    def from_payload(payload: bytes) -> 'Status':
        return Status(*unpack(STATUS, payload))

    def to_payload(self) -> bytes:
        return pack(STATUS, self.fw_ms, self.pos_steps, self.speed_steps_s, self.motion_id,
                    self.flags, self.inputs, self.outputs, self.faults, self.encoder)


def describe(frame: Frame) -> str:
    names = {v: k for k, v in globals().items() if isinstance(v, int) and k.isupper()
             and k not in ('SOF', 'MAX_PAYLOAD', 'PROTOCOL_VERSION')}
    name = names.get(frame.msg_id, f'0x{frame.msg_id:02x}')
    try:
        fields = frame.fields()
    except ValueError as exc:
        fields = (str(exc),)
    return f'{name} seq={frame.seq} {fields}'


def nak_reason(code: int) -> str:
    return NAK_REASONS.get(code, f'reason {code}')


def optional_int(value: Optional[int], default: int) -> int:
    return default if value is None else int(value)
