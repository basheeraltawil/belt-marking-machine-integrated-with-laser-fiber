// Pin map - Arduino Mega 2560. Legacy pins (2019 makine_kodu.ino) are kept where they exist.
// See docs/ELECTRICAL.md for wiring. Items marked TODO are listed in docs/ASSUMPTIONS.md.
#pragma once

#include <stdint.h>

// ---- DM542 stepper driver (legacy pins)
const uint8_t PIN_STEP = 48;  // PUL+
const uint8_t PIN_DIR = 50;   // DIR+
const uint8_t PIN_ENA = 52;   // ENA+  (legacy: LOW = enabled)

// ---- inputs (24 V sensors via optocoupler board -> 5 V)
const uint8_t PIN_BELT_PRESENT = 11;    // Di-Soric fork sensor (legacy ent_s, LOW = belt)
const uint8_t PIN_KNIFE_EXTENDED = 7;   // legacy r_ls   TODO: verify which reed is "extended"
const uint8_t PIN_KNIFE_RETRACTED = 5;  // legacy l_rs
const uint8_t PIN_KNIFE_START = 9;      // legacy ps_s (read but unused in 2019)
const uint8_t PIN_ESTOP_MON = 23;       // NEW: auxiliary NO/NC contact of the E-stop chain
const uint8_t PIN_DOOR = 25;            // NEW: laser enclosure door monitor contact
const uint8_t PIN_AIR = 27;             // NEW: pressure switch
const uint8_t PIN_LASER_BUSY[4] = {29, 31, 33, 35};  // NEW: laser "work/busy" via optocoupler
const uint8_t PIN_DRIVER_ALM = 37;                   // NEW: DM542 ALM output via optocoupler
const uint8_t PIN_SAFETY_RELAY = 39;                 // NEW: safety relay feedback contact
const uint8_t PIN_HOME = 41;                         // optional reference sensor
const uint8_t PIN_ENCODER_A = 2;                     // optional encoder (interrupt pins)
const uint8_t PIN_ENCODER_B = 3;

// input pins in InputBit order (logic::IN_*); 0xFF = not wired
const uint8_t INPUT_PINS[14] = {
    PIN_ESTOP_MON,       PIN_DOOR,        PIN_AIR,           PIN_BELT_PRESENT,  PIN_KNIFE_EXTENDED,
    PIN_KNIFE_RETRACTED, PIN_KNIFE_START, PIN_LASER_BUSY[0], PIN_LASER_BUSY[1], PIN_LASER_BUSY[2],
    PIN_LASER_BUSY[3],   PIN_DRIVER_ALM,  PIN_SAFETY_RELAY,  PIN_HOME};

// ---- outputs
// 8-channel relay module (active LOW, legacy): knife valves, Z-Air, DC motor, lasers
const uint8_t PIN_KNIFE_EXTEND = 42;   // legacy rl_r  TODO: verify extend/retract solenoids
const uint8_t PIN_KNIFE_RETRACT = 40;  // legacy lr_r (energised at rest in 2019)
const uint8_t PIN_ZAIR = 44;           // legacy mlr_r
const uint8_t PIN_DC_MOTOR = 46;       // legacy dcm_r (ejector)
const uint8_t PIN_LASER_TRIG[4] = {38, 36, 34, 32};  // 38 = legacy lasersignal
// 24 V transistor outputs (active HIGH): light tower + buzzer
const uint8_t PIN_LIGHT_RED = 22;
const uint8_t PIN_LIGHT_YELLOW = 24;
const uint8_t PIN_LIGHT_GREEN = 26;
const uint8_t PIN_BUZZER = 28;

// output pins in OutputBit order (logic::OUT_*)
const uint8_t OUTPUT_PINS[12] = {PIN_KNIFE_EXTEND,  PIN_KNIFE_RETRACT, PIN_ZAIR,
                                 PIN_DC_MOTOR,      PIN_LASER_TRIG[0], PIN_LASER_TRIG[1],
                                 PIN_LASER_TRIG[2], PIN_LASER_TRIG[3], PIN_LIGHT_RED,
                                 PIN_LIGHT_YELLOW,  PIN_LIGHT_GREEN,   PIN_BUZZER};
// 1 = output is active LOW (relay module)
const uint16_t OUTPUT_ACTIVE_LOW_MASK = 0x00FF;
