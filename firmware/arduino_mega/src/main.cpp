// Belt marking machine - Arduino Mega 2560 real-time I/O firmware.
//
// Non-blocking: no delay(). A cooperative loop services the serial parser, AccelStepper,
// debounced inputs, output pulse timers, the heartbeat watchdog and 50 Hz status frames.
// The AVR hardware watchdog (250 ms) resets the board if the loop ever hangs.
//
// Safety: E-stop, door interlock and air pressure act on a HARDWIRED safety relay.
// This firmware only monitors them and goes to a safe state; it is not a safety function.

#include <AccelStepper.h>
#include <Arduino.h>
#include <avr/wdt.h>

#include "config.h"
#include "io_logic.h"
#include "pins.h"
#include "protocol.h"

using namespace logic;

static AccelStepper stepper(AccelStepper::DRIVER, PIN_STEP, PIN_DIR);
static proto::Parser parser;
static Debouncer debouncer;
static HeartbeatWatchdog watchdog;
static PulseTimers pulses;
static Dedup dedup;

static uint16_t outputs = 0;          // logical output state (OutputBit)
static uint16_t faults = 0;           // FaultBit
static uint16_t invert_mask = DEFAULT_INPUT_INVERT_MASK;
static bool knife_interlock = DEFAULT_KNIFE_INTERLOCK;
static bool enabled = false;
static bool jogging = false;
static uint32_t jog_until = 0;
static uint16_t motion_id = 0;
static float max_speed = DEFAULT_MAX_SPEED_STEPS_S;
static volatile int32_t encoder_count = 0;
static uint32_t t_status = 0, t_inputs = 0;
static uint8_t boot_cause = 0;

// ------------------------------------------------------------------------ outputs
static void writeOutput(uint8_t out, bool on) {
  if (out >= OUT_COUNT) return;
  const bool active_low = (OUTPUT_ACTIVE_LOW_MASK >> out) & 1u;
  digitalWrite(OUTPUT_PINS[out], (on != active_low) ? HIGH : LOW);
  if (on) outputs |= (1u << out);
  else outputs &= ~(1u << out);
}

static void setEnable(bool on) {
  enabled = on;
  digitalWrite(PIN_ENA, (on == STEPPER_ENABLE_ACTIVE_LOW) ? LOW : HIGH);
}

static void quickStop() {
  jogging = false;
  stepper.setCurrentPosition(stepper.currentPosition());   // speed -> 0, target = here
}

static void safeState() {
  // fail-safe: stop, inhibit lasers, aux off, retract knife, red light
  quickStop();
  pulses.cancelAll();
  for (uint8_t i = 0; i < OUT_COUNT; ++i) writeOutput(i, false);
  writeOutput(OUT_KNIFE_RETRACT, true);
  writeOutput(OUT_LIGHT_RED, true);
}

// ------------------------------------------------------------------------ comms
static void sendFrame(uint8_t id, uint8_t seq, const uint8_t* payload, uint8_t len) {
  uint8_t buf[proto::MAX_PAYLOAD + 7];
  size_t n = proto::encode(id, seq, payload, len, buf);
  if (Serial.availableForWrite() < static_cast<int>(n)) return;   // never block the loop
  Serial.write(buf, n);
}

static void sendAck(uint8_t seq, uint8_t id) {
  uint8_t p[2] = {seq, id};
  sendFrame(proto::ACK, 0, p, 2);
}

static void sendNak(uint8_t seq, uint8_t id, uint8_t reason) {
  uint8_t p[3] = {seq, id, reason};
  sendFrame(proto::NAK, 0, p, 3);
}

static void sendEvent(uint8_t code, uint16_t data) {
  uint8_t p[3];
  proto::Writer(p).u8(code).u16(data);
  sendFrame(proto::EVENT, 0, p, 3);
}

static bool isMoving() { return jogging || stepper.distanceToGo() != 0 || stepper.speed() != 0; }

static void sendStatus() {
  uint8_t p[25];
  uint8_t flags = (isMoving() ? 1 : 0) | (enabled ? 2 : 0) | (jogging ? 4 : 0);
  uint16_t outs = outputs | (enabled ? (1u << OUT_STEPPER_ENABLE) : 0);
  noInterrupts();
  int32_t enc = encoder_count;
  interrupts();
  proto::Writer w(p);
  w.u32(millis()).i32(stepper.currentPosition()).f32(stepper.speed()).u16(motion_id)
      .u8(flags).u16(debouncer.state()).u16(outs).u16(faults).i32(enc);
  sendFrame(proto::STATUS, 0, p, w.size());
}

static void sendInfo() {
  uint8_t p[18] = {0};
  p[0] = proto::VERSION;
  p[1] = NUM_STATIONS;
  const char* v = FW_VERSION;
  for (uint8_t i = 0; i < 16 && v[i]; ++i) p[2 + i] = static_cast<uint8_t>(v[i]);
  sendFrame(proto::INFO, 0, p, 18);
}

static MachineView view() {
  return MachineView{debouncer.state(), faults, enabled, isMoving(), knife_interlock};
}

// ------------------------------------------------------------------ command handling
static void handleFrame(const proto::Frame& f) {
  const int expected = proto::expectedLength(f.id);
  if (expected < 0) { sendNak(f.seq, f.id, proto::NAK_UNKNOWN); return; }
  if (expected != f.len) { sendNak(f.seq, f.id, proto::NAK_LENGTH); return; }
  const uint32_t now = millis();
  if (f.id == proto::HEARTBEAT) { watchdog.beat(now); return; }     // no ACK
  if (dedup.isDuplicate(f.seq, f.id)) { sendAck(f.seq, f.id); return; }
  dedup.remember(f.seq, f.id);

  proto::Reader r(f.payload, f.len);
  uint8_t nak = 0;
  switch (f.id) {
    case proto::GET_INFO:
      sendInfo();
      break;
    case proto::MOVE_REL: {
      int32_t steps = r.i32();
      float speed = r.f32(), accel = r.f32();
      uint16_t mid = r.u16();
      nak = checkMotion(view());
      if (!nak && isMoving()) nak = proto::NAK_BUSY;
      if (nak) { if (nak == proto::NAK_INTERLOCK) faults |= F_INTERLOCK_REJECT; break; }
      stepper.setMaxSpeed(speed > 0 ? min(speed, max_speed) : max_speed);
      stepper.setAcceleration(accel > 0 ? accel : DEFAULT_ACCEL_STEPS_S2);
      stepper.move(steps);
      motion_id = mid;
      break;
    }
    case proto::JOG: {
      int8_t dir = r.i8();
      float speed = r.f32();
      uint16_t dur = r.u16(), mid = r.u16();
      nak = checkMotion(view());
      if (!nak && isMoving() && !jogging) nak = proto::NAK_BUSY;
      if (nak) break;
      stepper.setMaxSpeed(speed > 0 ? min(speed, max_speed) : max_speed);
      stepper.setAcceleration(DEFAULT_ACCEL_STEPS_S2);
      stepper.moveTo(stepper.currentPosition() + (dir >= 0 ? 1000000L : -1000000L));
      jogging = true;
      jog_until = now + dur;
      motion_id = mid;
      break;
    }
    case proto::STOP:
      if (r.u8()) quickStop();
      else { jogging = false; stepper.stop(); }
      break;
    case proto::ENABLE: {
      bool on = r.u8();
      if (on && !hasBit(debouncer.state(), IN_SAFETY_RELAY_OK)) { nak = proto::NAK_FAULT; break; }
      setEnable(on);
      if (!on) quickStop();
      break;
    }
    case proto::ZERO:
      if (isMoving()) { nak = proto::NAK_BUSY; break; }
      stepper.setCurrentPosition(0);
      noInterrupts();
      encoder_count = 0;
      interrupts();
      break;
    case proto::SET_OUTPUT:
    case proto::PULSE_OUTPUT: {
      uint8_t out = r.u8();
      uint16_t val = (f.id == proto::SET_OUTPUT) ? r.u8() : r.u16();
      bool on = val != 0;
      nak = checkOutput(view(), out, on);
      if (nak) { if (nak == proto::NAK_INTERLOCK) faults |= F_INTERLOCK_REJECT; break; }
      if (out == OUT_KNIFE_EXTEND && on) writeOutput(OUT_KNIFE_RETRACT, false);
      if (out == OUT_KNIFE_RETRACT && on) writeOutput(OUT_KNIFE_EXTEND, false);
      writeOutput(out, on);
      if (f.id == proto::PULSE_OUTPUT) pulses.start(out, now, val);
      else pulses.cancel(out);
      break;
    }
    case proto::SET_CONFIG: {
      uint8_t key = r.u8();
      float v = r.f32();
      if (key == proto::CFG_HEARTBEAT_TIMEOUT_MS) watchdog.configure(static_cast<uint16_t>(v));
      else if (key == proto::CFG_DEBOUNCE_MS) debouncer.configure(static_cast<uint16_t>(v));
      else if (key == proto::CFG_INPUT_INVERT_MASK) invert_mask = static_cast<uint16_t>(v);
      else if (key == proto::CFG_KNIFE_INTERLOCK) knife_interlock = v != 0.0f;
      else if (key == proto::CFG_MAX_SPEED_STEPS_S)
        max_speed = min(v, DEFAULT_MAX_SPEED_STEPS_S);
      else nak = proto::NAK_PARAM;
      break;
    }
    case proto::RESET_FAULTS:
      if (!watchdog.reset(now)) { nak = proto::NAK_FAULT; break; }
      faults &= ~(F_HEARTBEAT_LOST | F_INTERLOCK_REJECT | F_WDT_RESET | F_RX_OVERFLOW);
      writeOutput(OUT_LIGHT_RED, false);
      break;
    default:
      nak = proto::NAK_UNKNOWN;
  }
  if (nak) sendNak(f.seq, f.id, nak);
  else sendAck(f.seq, f.id);
}

// ------------------------------------------------------------------------ inputs
static void encoderIsr() {
  encoder_count += (digitalRead(PIN_ENCODER_B) == HIGH) ? 1 : -1;
}

static uint16_t sampleInputs() {
  uint16_t raw = 0;
  for (uint8_t i = 0; i < IN_COUNT; ++i) {
    if (INPUT_PINS[i] == 0xFF) continue;
    if (digitalRead(INPUT_PINS[i]) == HIGH) raw |= (1u << i);
  }
  return raw ^ invert_mask;
}

static void superviseInputs(uint32_t now) {
  const uint16_t in = debouncer.update(sampleInputs(), now);
  const bool estop = !hasBit(in, IN_ESTOP_OK);
  if (estop && !(faults & F_ESTOP)) { safeState(); sendEvent(proto::EV_ESTOP, 0); }
  faults = estop ? (faults | F_ESTOP) : (faults & ~F_ESTOP);
  const bool alm = hasBit(in, IN_DRIVER_FAULT);
  if (alm && !(faults & F_DRIVER_ALM)) { quickStop(); sendEvent(proto::EV_DRIVER_ALM, 0); }
  faults = alm ? (faults | F_DRIVER_ALM) : (faults & ~F_DRIVER_ALM);
  const bool conflict = hasBit(in, IN_KNIFE_EXTENDED) && hasBit(in, IN_KNIFE_RETRACTED);
  faults = conflict ? (faults | F_KNIFE_SENSOR_CONFLICT) : (faults & ~F_KNIFE_SENSOR_CONFLICT);
  if (!hasBit(in, IN_SAFETY_RELAY_OK) && enabled) setEnable(false);   // drive lost its power
  if (!hasBit(in, IN_DOOR_CLOSED)) {                                   // never pedal with door open
    for (uint8_t o = OUT_LASER_0; o <= OUT_LASER_3; ++o) {
      if (hasBit(outputs, o)) { writeOutput(o, false); pulses.cancel(o); }
    }
  }
}

// ------------------------------------------------------------------------ setup/loop
void setup() {
  boot_cause = MCUSR;
  MCUSR = 0;
  wdt_disable();
  // outputs to a defined safe state BEFORE anything else (legacy left valves undefined)
  for (uint8_t i = 0; i < OUT_COUNT; ++i) {
    pinMode(OUTPUT_PINS[i], OUTPUT);
    writeOutput(i, false);
  }
  writeOutput(OUT_KNIFE_RETRACT, true);
  pinMode(PIN_ENA, OUTPUT);
  setEnable(false);
  for (uint8_t i = 0; i < IN_COUNT; ++i) {
    if (INPUT_PINS[i] != 0xFF) pinMode(INPUT_PINS[i], INPUT);
  }
  pinMode(PIN_ENCODER_A, INPUT_PULLUP);
  pinMode(PIN_ENCODER_B, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_ENCODER_A), encoderIsr, RISING);

  stepper.setMinPulseWidth(STEP_PULSE_US);
  stepper.setPinsInverted(!DIR_FORWARD_LEVEL_HIGH, false, false);
  stepper.setMaxSpeed(max_speed);
  stepper.setAcceleration(DEFAULT_ACCEL_STEPS_S2);

  debouncer.configure(DEFAULT_DEBOUNCE_MS);
  debouncer.force(sampleInputs());
  watchdog.configure(DEFAULT_HEARTBEAT_TIMEOUT_MS);
  if (boot_cause & _BV(WDRF)) faults |= F_WDT_RESET;

  Serial.begin(SERIAL_BAUD);
  wdt_enable(WDTO_250MS);
  sendEvent(proto::EV_BOOT, boot_cause);
}

void loop() {
  wdt_reset();
  const uint32_t now = millis();

  // 1. serial: parse everything available (bounded so stepping is not starved)
  for (uint8_t n = 0; n < 64 && Serial.available(); ++n) {
    if (parser.feed(static_cast<uint8_t>(Serial.read()))) handleFrame(parser.frame());
  }

  // 2. motion
  if (jogging && static_cast<int32_t>(now - jog_until) >= 0) {
    jogging = false;
    stepper.stop();                                         // decelerate
  }
  stepper.run();

  // 3. inputs (1 kHz)
  if (now - t_inputs >= INPUT_PERIOD_MS) {
    t_inputs = now;
    superviseInputs(now);
  }

  // 4. output pulses
  const uint16_t ended = pulses.expired(now);
  if (ended) {
    for (uint8_t i = 0; i < OUT_COUNT; ++i) {
      if ((ended >> i) & 1u) writeOutput(i, false);
    }
  }

  // 5. heartbeat watchdog -> fail-safe
  if (watchdog.update(now)) {
    faults |= F_HEARTBEAT_LOST;
    safeState();
    sendEvent(proto::EV_HEARTBEAT_LOST, 0);
  }

  // 6. status
  if (now - t_status >= STATUS_PERIOD_MS) {
    t_status = now;
    sendStatus();
  }
}
