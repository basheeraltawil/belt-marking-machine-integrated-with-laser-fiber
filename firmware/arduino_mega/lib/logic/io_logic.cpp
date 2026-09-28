#include "io_logic.h"

namespace logic {

// NakReason values (duplicated here to keep this library independent of protocol.h)
static const uint8_t NAK_INTERLOCK = 3, NAK_FAULT = 4, NAK_DISABLED = 6, NAK_PARAM = 7;

uint16_t Debouncer::update(uint16_t raw, uint32_t now_ms) {
  for (uint8_t i = 0; i < 16; ++i) {
    const uint16_t m = static_cast<uint16_t>(1u << i);
    if ((raw & m) != (candidate_ & m)) {       // new candidate level
      candidate_ = static_cast<uint16_t>((candidate_ & ~m) | (raw & m));
      since_[i] = now_ms;
    }
    if ((candidate_ & m) != (stable_ & m) && now_ms - since_[i] >= debounce_ms_) {
      stable_ = static_cast<uint16_t>((stable_ & ~m) | (candidate_ & m));
    }
  }
  return stable_;
}

bool HeartbeatWatchdog::update(uint32_t now_ms) {
  // armed by the first heartbeat: before that the machine is idle and safe anyway
  if (tripped_ || !seen_) return false;
  if (now_ms - last_ > timeout_ms_) {
    tripped_ = true;
    return true;
  }
  return false;
}

bool HeartbeatWatchdog::reset(uint32_t now_ms) {
  if (!fresh(now_ms)) return false;
  tripped_ = false;
  return true;
}

void PulseTimers::start(uint8_t out, uint32_t now_ms, uint16_t duration_ms) {
  if (out >= OUT_COUNT) return;
  until_[out] = now_ms + duration_ms;
  active_ |= static_cast<uint16_t>(1u << out);
}

uint16_t PulseTimers::expired(uint32_t now_ms) {
  uint16_t done = 0;
  for (uint8_t i = 0; i < OUT_COUNT; ++i) {
    const uint16_t m = static_cast<uint16_t>(1u << i);
    if ((active_ & m) && static_cast<int32_t>(now_ms - until_[i]) >= 0) {
      active_ = static_cast<uint16_t>(active_ & ~m);
      done |= m;
    }
  }
  return done;
}

uint8_t checkMotion(const MachineView& m) {
  if (m.faults & (F_HEARTBEAT_LOST | F_ESTOP | F_DRIVER_ALM)) return NAK_FAULT;
  if (!m.enabled) return NAK_DISABLED;
  if (m.knife_interlock && !hasBit(m.inputs, IN_KNIFE_RETRACTED)) return NAK_INTERLOCK;
  return 0;
}

uint8_t checkOutput(const MachineView& m, uint8_t out, bool value) {
  if (out >= OUT_COUNT) return NAK_PARAM;
  if (!value) return 0;                                    // switching off is always allowed
  if (m.faults & (F_HEARTBEAT_LOST | F_ESTOP)) {
    const bool allowed = out == OUT_KNIFE_RETRACT || out == OUT_LIGHT_RED ||
                         out == OUT_LIGHT_YELLOW || out == OUT_BUZZER;
    if (!allowed) return NAK_FAULT;
  }
  if (out == OUT_KNIFE_EXTEND && m.moving) return NAK_INTERLOCK;
  if (out >= OUT_LASER_0 && out <= OUT_LASER_3 && !hasBit(m.inputs, IN_DOOR_CLOSED)) {
    return NAK_INTERLOCK;                                  // the enclosure interlock is
  }                                                        // hardwired too; this is extra
  return 0;
}

}  // namespace logic
