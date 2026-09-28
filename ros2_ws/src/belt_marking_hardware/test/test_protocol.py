import random
import struct

from belt_marking_hardware import protocol as P
import pytest


def test_crc16_ccitt_false_check_value():
    assert P.crc16(b'123456789') == 0x29B1


def test_encode_decode_roundtrip_all_messages():
    samples = {
        P.HEARTBEAT: (123456,), P.MOVE_REL: (-4140, 1000.0, 6900.0, 77),
        P.JOG: (-1, 690.0, 250, 3),
        P.STOP: (1,), P.ENABLE: (0,), P.SET_OUTPUT: (4, 1), P.PULSE_OUTPUT: (3, 1000),
        P.SET_CONFIG: (1, 500.0), P.ACK: (9, 0x10), P.NAK: (9, 0x10, 3),
        P.STATUS: (1000, -5, 12.5, 65535, 3, 0x0FFF, 0x1001, 1, 42), P.EVENT: (1, 4),
    }
    parser = P.Parser()
    stream = b''
    for i, (mid, fields) in enumerate(samples.items()):
        stream += P.encode(mid, i + 1, P.pack(mid, *fields))
    frames = parser.feed(stream)
    assert [f.msg_id for f in frames] == list(samples)
    for f, (mid, fields) in zip(frames, samples.items()):
        got = f.fields()
        assert got == pytest.approx(fields) if mid != P.STATUS else got[3] == 65535


def test_parser_resyncs_on_garbage_split_and_bad_crc():
    good = P.encode(P.ACK, 5, P.pack(P.ACK, 5, P.MOVE_REL))
    bad = bytearray(good)
    bad[-1] ^= 0xFF
    rng = random.Random(1)
    noise = bytes(rng.randrange(256) for _ in range(50)).replace(b'\xAA', b'\x00')
    stream = noise + bytes(bad) + b'\xAA' + good + good
    parser = P.Parser()
    frames = []
    for i in range(0, len(stream), 3):                  # byte-wise arrival
        frames += parser.feed(stream[i:i + 3])
    assert len(frames) == 2 and parser.crc_errors == 1


def test_length_guard():
    parser = P.Parser()
    evil = b'\xAA\x55' + bytes([200, 1, 1]) + b'x' * 10
    assert parser.feed(evil + P.encode(P.ZERO, 7))[-1].msg_id == P.ZERO


def test_status_payload_size_matches_firmware():
    assert struct.calcsize(P._FORMATS[P.STATUS]) == 25
    assert struct.calcsize(P._FORMATS[P.MOVE_REL]) == 14
