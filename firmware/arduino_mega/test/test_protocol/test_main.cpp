#include <string.h>
#include <unity.h>

#include "protocol.h"

using namespace proto;

void setUp() {}
void tearDown() {}

static void test_crc_check_value() {
  const uint8_t s[] = "123456789";
  TEST_ASSERT_EQUAL_HEX16(0x29B1, crc16(s, 9));
}

static void test_encode_parse_roundtrip() {
  uint8_t payload[14];
  Writer w(payload);
  w.i32(-4140).f32(1000.0f).f32(6900.0f).u16(77);
  TEST_ASSERT_EQUAL(14, w.size());
  uint8_t buf[80];
  size_t n = encode(MOVE_REL, 9, payload, w.size(), buf);
  TEST_ASSERT_EQUAL(21, n);
  Parser p;
  bool got = false;
  for (size_t i = 0; i < n; ++i) got = p.feed(buf[i]);
  TEST_ASSERT_TRUE(got);
  TEST_ASSERT_EQUAL(MOVE_REL, p.frame().id);
  TEST_ASSERT_EQUAL(9, p.frame().seq);
  Reader r(p.frame().payload, p.frame().len);
  TEST_ASSERT_EQUAL_INT32(-4140, r.i32());
  TEST_ASSERT_EQUAL_FLOAT(1000.0f, r.f32());
  TEST_ASSERT_EQUAL_FLOAT(6900.0f, r.f32());
  TEST_ASSERT_EQUAL_UINT16(77, r.u16());
}

static void test_known_frame_from_python() {
  // protocol.encode(ACK, 5, pack(ACK, 5, 0x10)) in Python
  const uint8_t py[] = {0xAA, 0x55, 0x02, 0x05, 0x80, 0x05, 0x10, 0, 0};
  uint8_t buf[16];
  const uint8_t payload[2] = {0x05, 0x10};
  size_t n = encode(ACK, 5, payload, 2, buf);
  TEST_ASSERT_EQUAL(9, n);
  TEST_ASSERT_EQUAL_UINT8_ARRAY(py, buf, 7);
  uint16_t crc = crc16(buf + 2, 5);
  TEST_ASSERT_EQUAL_HEX8(crc & 0xFF, buf[7]);
  TEST_ASSERT_EQUAL_HEX8(crc >> 8, buf[8]);
}

static void test_bad_crc_rejected_and_resync() {
  uint8_t good[16], bad[16];
  size_t n = encode(ZERO, 3, nullptr, 0, good);
  memcpy(bad, good, n);
  bad[n - 1] ^= 0xFF;
  Parser p;
  int frames = 0;
  const uint8_t garbage[] = {0x00, 0xAA, 0x13, 0x55, 0xAA};
  for (uint8_t b : garbage) frames += p.feed(b);
  for (size_t i = 0; i < n; ++i) frames += p.feed(bad[i]);
  for (size_t i = 0; i < n; ++i) frames += p.feed(good[i]);
  TEST_ASSERT_EQUAL(1, frames);
  TEST_ASSERT_EQUAL(1, p.crcErrors());
}

static void test_oversized_length_ignored() {
  Parser p;
  const uint8_t evil[] = {0xAA, 0x55, 200, 1, 1};
  int frames = 0;
  for (uint8_t b : evil) frames += p.feed(b);
  uint8_t good[16];
  size_t n = encode(GET_INFO, 1, nullptr, 0, good);
  for (size_t i = 0; i < n; ++i) frames += p.feed(good[i]);
  TEST_ASSERT_EQUAL(1, frames);
}

static void test_expected_lengths() {
  TEST_ASSERT_EQUAL(14, expectedLength(MOVE_REL));
  TEST_ASSERT_EQUAL(9, expectedLength(JOG));
  TEST_ASSERT_EQUAL(-1, expectedLength(0x77));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_crc_check_value);
  RUN_TEST(test_encode_parse_roundtrip);
  RUN_TEST(test_known_frame_from_python);
  RUN_TEST(test_bad_crc_rejected_and_resync);
  RUN_TEST(test_oversized_length_ignored);
  RUN_TEST(test_expected_lengths);
  return UNITY_END();
}
