// Framed serial protocol, firmware side. Keep in sync with
// ros2_ws/src/belt_marking_hardware/belt_marking_hardware/protocol.py and
// docs/SERIAL_PROTOCOL.md.
//
// Frame: 0xAA 0x55 | LEN | SEQ | ID | PAYLOAD[LEN] | CRC16-CCITT-FALSE (LE, over LEN..PAYLOAD)
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace proto {

const uint8_t SOF0 = 0xAA;
const uint8_t SOF1 = 0x55;
const uint8_t MAX_PAYLOAD = 64;
const uint8_t VERSION = 1;

enum MsgId : uint8_t {
  HEARTBEAT = 0x01,
  GET_INFO = 0x02,
  MOVE_REL = 0x10,
  JOG = 0x11,
  STOP = 0x12,
  ENABLE = 0x13,
  ZERO = 0x14,
  SET_OUTPUT = 0x20,
  PULSE_OUTPUT = 0x21,
  SET_CONFIG = 0x30,
  RESET_FAULTS = 0x31,
  ACK = 0x80,
  NAK = 0x81,
  STATUS = 0x90,
  INFO = 0x91,
  EVENT = 0x92,
};

enum NakReason : uint8_t {
  NAK_UNKNOWN = 1,
  NAK_LENGTH = 2,
  NAK_INTERLOCK = 3,
  NAK_FAULT = 4,
  NAK_BUSY = 5,
  NAK_DISABLED = 6,
  NAK_PARAM = 7,
};

enum ConfigKey : uint8_t {
  CFG_HEARTBEAT_TIMEOUT_MS = 1,
  CFG_DEBOUNCE_MS = 2,
  CFG_INPUT_INVERT_MASK = 3,
  CFG_KNIFE_INTERLOCK = 4,
  CFG_MAX_SPEED_STEPS_S = 5,
};

enum EventCode : uint8_t { EV_BOOT = 1, EV_HEARTBEAT_LOST = 2, EV_ESTOP = 3, EV_DRIVER_ALM = 4 };

// expected payload length per message id, -1 = unknown id
int expectedLength(uint8_t id);

uint16_t crc16(const uint8_t* data, size_t len, uint16_t crc = 0xFFFF);

// Writes a complete frame into out (size >= len + 7). Returns the frame length.
size_t encode(uint8_t id, uint8_t seq, const uint8_t* payload, uint8_t len, uint8_t* out);

struct Frame {
  uint8_t id;
  uint8_t seq;
  uint8_t len;
  uint8_t payload[MAX_PAYLOAD];
};

// Byte-wise frame parser (no allocation, resynchronises on errors).
class Parser {
 public:
  Parser() { reset(); }
  // Returns true when a complete, CRC-valid frame is available in frame().
  bool feed(uint8_t b);
  const Frame& frame() const { return frame_; }
  uint16_t crcErrors() const { return crc_errors_; }
  void reset() {
    state_ = S_SOF0;
    idx_ = 0;
  }

 private:
  enum State { S_SOF0, S_SOF1, S_LEN, S_SEQ, S_ID, S_PAYLOAD, S_CRC0, S_CRC1 };
  State state_;
  uint8_t idx_;
  uint8_t crc_lo_;
  Frame frame_;
  uint16_t crc_errors_ = 0;
};

// little endian field helpers (AVR and x86 are both little endian; memcpy keeps it
// alignment-safe and portable)
class Writer {
 public:
  explicit Writer(uint8_t* buf) : buf_(buf), n_(0) {}
  Writer& u8(uint8_t v) {
    buf_[n_++] = v;
    return *this;
  }
  Writer& i8(int8_t v) { return u8(static_cast<uint8_t>(v)); }
  Writer& u16(uint16_t v) { return raw(&v, 2); }
  Writer& u32(uint32_t v) { return raw(&v, 4); }
  Writer& i32(int32_t v) { return raw(&v, 4); }
  Writer& f32(float v) { return raw(&v, 4); }
  Writer& raw(const void* p, uint8_t n);
  uint8_t size() const { return n_; }

 private:
  uint8_t* buf_;
  uint8_t n_;
};

class Reader {
 public:
  Reader(const uint8_t* buf, uint8_t len) : buf_(buf), len_(len), n_(0) {}
  uint8_t u8() { return buf_[n_++]; }
  int8_t i8() { return static_cast<int8_t>(u8()); }
  uint16_t u16() {
    uint16_t v;
    raw(&v, 2);
    return v;
  }
  uint32_t u32() {
    uint32_t v;
    raw(&v, 4);
    return v;
  }
  int32_t i32() {
    int32_t v;
    raw(&v, 4);
    return v;
  }
  float f32() {
    float v;
    raw(&v, 4);
    return v;
  }
  void raw(void* p, uint8_t n);

 private:
  const uint8_t* buf_;
  uint8_t len_;
  uint8_t n_;
};

}  // namespace proto
