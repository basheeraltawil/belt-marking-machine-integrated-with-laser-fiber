// Portable machine logic of the firmware (no Arduino dependencies -> unit tested on PC).
// Bit numbering matches belt_marking_hardware/hal.py (INPUT_BITS / OUTPUT_BITS).
#pragma once

#include <stdint.h>

namespace logic {

// ---- input bits (logical, after polarity correction)
enum InputBit : uint8_t {
  IN_ESTOP_OK = 0,
  IN_DOOR_CLOSED,
  IN_AIR_OK,
  IN_BELT_PRESENT,
  IN_KNIFE_EXTENDED,
  IN_KNIFE_RETRACTED,
  IN_KNIFE_START,
  IN_LASER_BUSY_0,
  IN_LASER_BUSY_1,
  IN_LASER_BUSY_2,
  IN_LASER_BUSY_3,
  IN_DRIVER_FAULT,
  IN_SAFETY_RELAY_OK,
  IN_HOME,
  IN_COUNT
};

// ---- output bits
enum OutputBit : uint8_t {
  OUT_KNIFE_EXTEND = 0,
  OUT_KNIFE_RETRACT,
  OUT_ZAIR,
  OUT_DC_MOTOR,
  OUT_LASER_0,
  OUT_LASER_1,
  OUT_LASER_2,
  OUT_LASER_3,
  OUT_LIGHT_RED,
  OUT_LIGHT_YELLOW,
  OUT_LIGHT_GREEN,
  OUT_BUZZER,
  OUT_COUNT,
  OUT_STEPPER_ENABLE = 12
};

// ---- fault flags (IoStatus.FAULT_*)
enum FaultBit : uint16_t {
  F_HEARTBEAT_LOST = 1,
  F_ESTOP = 2,
  F_DRIVER_ALM = 4,
  F_WDT_RESET = 8,
  F_INTERLOCK_REJECT = 16,
  F_KNIFE_SENSOR_CONFLICT = 32,
  F_RX_OVERFLOW = 64
};

inline bool hasBit(uint16_t mask, uint8_t b) { return (mask >> b) & 1u; }

// Time-based debouncer for up to 16 inputs: a change is accepted after it was stable
// for `debounce_ms`.
class Debouncer {
 public:
  void configure(uint16_t debounce_ms) { debounce_ms_ = debounce_ms; }
  // raw: logical raw sample (already polarity corrected). Returns the debounced mask.
  uint16_t update(uint16_t raw, uint32_t now_ms);
  uint16_t state() const { return stable_; }
  void force(uint16_t v) { stable_ = candidate_ = v; }

 private:
  uint16_t stable_ = 0;
  uint16_t candidate_ = 0;
  uint32_t since_[16] = {0};
  uint16_t debounce_ms_ = 5;
};

// Heartbeat watchdog: trips once when no heartbeat for timeout_ms; latched until reset.
class HeartbeatWatchdog {
 public:
  void configure(uint16_t timeout_ms) { timeout_ms_ = timeout_ms; }
  void beat(uint32_t now_ms) {
    last_ = now_ms;
    seen_ = true;
  }
  // Returns true exactly once, on the tripping edge. Armed by the first heartbeat.
  bool update(uint32_t now_ms);
  bool tripped() const { return tripped_; }
  bool fresh(uint32_t now_ms) const { return seen_ && now_ms - last_ <= timeout_ms_; }
  bool reset(uint32_t now_ms);  // only succeeds with a fresh heartbeat
  uint16_t timeout() const { return timeout_ms_; }

 private:
  uint32_t last_ = 0;
  uint16_t timeout_ms_ = 500;
  bool tripped_ = false;
  bool seen_ = false;
};

// Output pulse timers (e.g. laser pedal 200 ms, ejector 1000 ms).
class PulseTimers {
 public:
  void start(uint8_t out, uint32_t now_ms, uint16_t duration_ms);
  void cancel(uint8_t out) { active_ &= static_cast<uint16_t>(~(1u << out)); }
  void cancelAll() { active_ = 0; }
  // Returns the mask of outputs whose pulse just ended.
  uint16_t expired(uint32_t now_ms);

 private:
  uint32_t until_[OUT_COUNT] = {0};
  uint16_t active_ = 0;
};

struct MachineView {
  uint16_t inputs;  // debounced logical inputs
  uint16_t faults;  // current fault flags
  bool enabled;     // stepper driver enabled
  bool moving;
  bool knife_interlock;  // require knife retracted for belt motion
};

// Interlock rules (identical to FakePlant in the Python simulation). 0 = allowed,
// otherwise a proto::NakReason value.
uint8_t checkMotion(const MachineView& m);
uint8_t checkOutput(const MachineView& m, uint8_t out, bool value);

// Duplicate detection for retransmitted commands.
class Dedup {
 public:
  bool isDuplicate(uint8_t seq, uint8_t id) const { return valid_ && seq == seq_ && id == id_; }
  void remember(uint8_t seq, uint8_t id) {
    seq_ = seq;
    id_ = id;
    valid_ = true;
  }

 private:
  uint8_t seq_ = 0, id_ = 0;
  bool valid_ = false;
};

}  // namespace logic
