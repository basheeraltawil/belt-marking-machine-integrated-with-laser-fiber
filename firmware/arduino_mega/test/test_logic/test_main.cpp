#include <unity.h>

#include "io_logic.h"

using namespace logic;

void setUp() {}
void tearDown() {}

static void test_debounce_accepts_only_stable_changes() {
  Debouncer d;
  d.configure(5);
  d.force(0);
  TEST_ASSERT_EQUAL_HEX16(0, d.update(0x1, 100));
  TEST_ASSERT_EQUAL_HEX16(0, d.update(0x0, 102));   // bounce
  TEST_ASSERT_EQUAL_HEX16(0, d.update(0x1, 103));
  TEST_ASSERT_EQUAL_HEX16(0, d.update(0x1, 107));
  TEST_ASSERT_EQUAL_HEX16(1, d.update(0x1, 108));   // stable for 5 ms
}

static void test_watchdog_trips_once_and_needs_fresh_heartbeat() {
  HeartbeatWatchdog w;
  w.configure(500);
  TEST_ASSERT_FALSE(w.update(5000));                // not armed before the first heartbeat
  w.beat(0);
  TEST_ASSERT_FALSE(w.update(400));
  TEST_ASSERT_TRUE(w.update(501));
  TEST_ASSERT_FALSE(w.update(600));                 // edge only once
  TEST_ASSERT_TRUE(w.tripped());
  TEST_ASSERT_FALSE(w.reset(700));                  // no fresh heartbeat
  w.beat(710);
  TEST_ASSERT_TRUE(w.reset(720));
  TEST_ASSERT_FALSE(w.tripped());
}

static void test_pulse_timers() {
  PulseTimers p;
  p.start(OUT_LASER_0, 1000, 200);
  p.start(OUT_DC_MOTOR, 1000, 1000);
  TEST_ASSERT_EQUAL_HEX16(0, p.expired(1199));
  TEST_ASSERT_EQUAL_HEX16(1u << OUT_LASER_0, p.expired(1200));
  TEST_ASSERT_EQUAL_HEX16(1u << OUT_DC_MOTOR, p.expired(2000));
  // millis() wrap-around
  p.start(OUT_ZAIR, 0xFFFFFF00u, 0x200);
  TEST_ASSERT_EQUAL_HEX16(0, p.expired(0x00000050u));
  TEST_ASSERT_EQUAL_HEX16(1u << OUT_ZAIR, p.expired(0x00000100u));
}

static MachineView ok_view() {
  MachineView m;
  m.inputs = (1u << IN_KNIFE_RETRACTED) | (1u << IN_DOOR_CLOSED) | (1u << IN_ESTOP_OK);
  m.faults = 0;
  m.enabled = true;
  m.moving = false;
  m.knife_interlock = true;
  return m;
}

static void test_motion_interlocks() {
  MachineView m = ok_view();
  TEST_ASSERT_EQUAL(0, checkMotion(m));
  m.inputs &= ~(1u << IN_KNIFE_RETRACTED);
  TEST_ASSERT_EQUAL(3, checkMotion(m));             // interlock
  m.knife_interlock = false;
  TEST_ASSERT_EQUAL(0, checkMotion(m));
  m = ok_view();
  m.enabled = false;
  TEST_ASSERT_EQUAL(6, checkMotion(m));
  m = ok_view();
  m.faults = F_HEARTBEAT_LOST;
  TEST_ASSERT_EQUAL(4, checkMotion(m));
}

static void test_output_interlocks() {
  MachineView m = ok_view();
  m.moving = true;
  TEST_ASSERT_EQUAL(3, checkOutput(m, OUT_KNIFE_EXTEND, true));
  TEST_ASSERT_EQUAL(0, checkOutput(m, OUT_KNIFE_EXTEND, false));
  m = ok_view();
  m.inputs &= ~(1u << IN_DOOR_CLOSED);
  TEST_ASSERT_EQUAL(3, checkOutput(m, OUT_LASER_0, true));
  m = ok_view();
  m.faults = F_ESTOP;
  TEST_ASSERT_EQUAL(4, checkOutput(m, OUT_ZAIR, true));
  TEST_ASSERT_EQUAL(0, checkOutput(m, OUT_KNIFE_RETRACT, true));
  TEST_ASSERT_EQUAL(7, checkOutput(m, 99, true));
}

static void test_dedup() {
  Dedup d;
  TEST_ASSERT_FALSE(d.isDuplicate(1, 0x10));
  d.remember(1, 0x10);
  TEST_ASSERT_TRUE(d.isDuplicate(1, 0x10));
  TEST_ASSERT_FALSE(d.isDuplicate(2, 0x10));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_debounce_accepts_only_stable_changes);
  RUN_TEST(test_watchdog_trips_once_and_needs_fresh_heartbeat);
  RUN_TEST(test_pulse_timers);
  RUN_TEST(test_motion_interlocks);
  RUN_TEST(test_output_interlocks);
  RUN_TEST(test_dedup);
  return UNITY_END();
}
