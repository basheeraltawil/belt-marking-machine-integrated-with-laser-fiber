// Firmware configuration. Runtime-adjustable values can also be changed by the Pi with
// SET_CONFIG. Items marked TODO are listed in docs/ASSUMPTIONS.md.
#pragma once

#include <stdint.h>

#define FW_VERSION "1.0.0"

const uint32_t SERIAL_BAUD = 115200;
const uint8_t NUM_STATIONS = 4;             // inputs/outputs reserved for up to 4 lasers

// timing
const uint16_t DEFAULT_HEARTBEAT_TIMEOUT_MS = 500;
const uint16_t DEFAULT_DEBOUNCE_MS = 5;     // TODO: verify on hardware (reed bounce)
const uint16_t STATUS_PERIOD_MS = 20;       // 50 Hz status frames
const uint16_t INPUT_PERIOD_MS = 1;

// motion (AccelStepper on a 16 MHz AVR tops out around 4000 steps/s)
const float DEFAULT_MAX_SPEED_STEPS_S = 4000.0f;
const float DEFAULT_ACCEL_STEPS_S2 = 6900.0f;       // 100 mm/s2 at 69 steps/mm
const float QUICK_STOP_DECEL_STEPS_S2 = 60000.0f;
const bool STEPPER_ENABLE_ACTIVE_LOW = true;        // legacy: digitalWrite(ENA, LOW) = on
const bool DIR_FORWARD_LEVEL_HIGH = true;           // legacy: DIR HIGH = forward
const uint16_t STEP_PULSE_US = 5;                   // DM542 needs >= 2.5 us

// input polarity: bit set = input is active LOW (inverted) in InputBit order.
// legacy: fork sensor LOW = belt present -> bit IN_BELT_PRESENT (3) set.
// TODO: verify every sensor polarity on hardware.
const uint16_t DEFAULT_INPUT_INVERT_MASK = (1u << 3);

// knife interlock: refuse belt motion unless the knife is retracted
const bool DEFAULT_KNIFE_INTERLOCK = true;
