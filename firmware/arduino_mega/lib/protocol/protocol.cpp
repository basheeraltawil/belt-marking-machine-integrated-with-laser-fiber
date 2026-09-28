#include "protocol.h"

#include <string.h>

namespace proto {

int expectedLength(uint8_t id) {
  switch (id) {
    case HEARTBEAT:
      return 4;
    case GET_INFO:
      return 0;
    case MOVE_REL:
      return 14;  // i32 steps, f32 speed, f32 accel, u16 motion id
    case JOG:
      return 9;  // i8 dir, f32 speed, u16 duration ms, u16 motion id
    case STOP:
      return 1;
    case ENABLE:
      return 1;
    case ZERO:
      return 0;
    case SET_OUTPUT:
      return 2;
    case PULSE_OUTPUT:
      return 3;
    case SET_CONFIG:
      return 5;
    case RESET_FAULTS:
      return 0;
    default:
      return -1;
  }
}

uint16_t crc16(const uint8_t* data, size_t len, uint16_t crc) {
  for (size_t i = 0; i < len; ++i) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (uint8_t b = 0; b < 8; ++b) {
      crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021)
                           : static_cast<uint16_t>(crc << 1);
    }
  }
  return crc;
}

size_t encode(uint8_t id, uint8_t seq, const uint8_t* payload, uint8_t len, uint8_t* out) {
  out[0] = SOF0;
  out[1] = SOF1;
  out[2] = len;
  out[3] = seq;
  out[4] = id;
  if (len) memcpy(out + 5, payload, len);
  uint16_t crc = crc16(out + 2, static_cast<size_t>(len) + 3);
  out[5 + len] = static_cast<uint8_t>(crc & 0xFF);
  out[6 + len] = static_cast<uint8_t>(crc >> 8);
  return static_cast<size_t>(len) + 7;
}

bool Parser::feed(uint8_t b) {
  switch (state_) {
    case S_SOF0:
      if (b == SOF0) state_ = S_SOF1;
      return false;
    case S_SOF1:
      state_ = (b == SOF1) ? S_LEN : (b == SOF0 ? S_SOF1 : S_SOF0);
      return false;
    case S_LEN:
      if (b > MAX_PAYLOAD) {
        state_ = S_SOF0;
        return false;
      }
      frame_.len = b;
      state_ = S_SEQ;
      return false;
    case S_SEQ:
      frame_.seq = b;
      state_ = S_ID;
      return false;
    case S_ID:
      frame_.id = b;
      idx_ = 0;
      state_ = frame_.len ? S_PAYLOAD : S_CRC0;
      return false;
    case S_PAYLOAD:
      frame_.payload[idx_++] = b;
      if (idx_ >= frame_.len) state_ = S_CRC0;
      return false;
    case S_CRC0:
      crc_lo_ = b;
      state_ = S_CRC1;
      return false;
    case S_CRC1: {
      state_ = S_SOF0;
      uint8_t head[3] = {frame_.len, frame_.seq, frame_.id};
      uint16_t crc = crc16(head, 3);
      crc = crc16(frame_.payload, frame_.len, crc);
      if (crc == static_cast<uint16_t>(crc_lo_ | (static_cast<uint16_t>(b) << 8))) return true;
      ++crc_errors_;
      return false;
    }
  }
  state_ = S_SOF0;
  return false;
}

Writer& Writer::raw(const void* p, uint8_t n) {
  memcpy(buf_ + n_, p, n);
  n_ = static_cast<uint8_t>(n_ + n);
  return *this;
}

void Reader::raw(void* p, uint8_t n) {
  if (n_ + n > len_) {  // defensive: never read past the payload
    memset(p, 0, n);
    return;
  }
  memcpy(p, buf_ + n_, n);
  n_ = static_cast<uint8_t>(n_ + n);
}

}  // namespace proto
