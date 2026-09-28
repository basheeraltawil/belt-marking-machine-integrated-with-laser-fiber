# Raw hardware status, published by the hardware layer (real or sim) on hw/io_status.
builtin_interfaces/Time stamp
bool link_ok                 # serial link / sim plant alive
string source                # "serial" or "sim"
string fw_version
uint32 fw_uptime_ms

# --- inputs (already polarity-corrected and debounced: true = condition present)
bool estop_ok                # safety chain E-stop channel healthy (monitor only)
bool door_closed             # laser enclosure door interlock closed (monitor only)
bool safety_relay_ok         # safety relay output energised (monitor only)
bool air_pressure_ok
bool belt_present            # Di-Soric fork light sensor
bool knife_extended
bool knife_retracted
bool knife_start             # knife start sensor
bool driver_fault            # DM542 ALM
bool home_sensor
bool[] laser_busy            # one per laser station

# --- outputs (actual state)
bool knife_extend_valve
bool knife_retract_valve
bool zair_valve
bool dc_motor
bool[] laser_trigger
bool stepper_enabled
bool light_red
bool light_yellow
bool light_green
bool buzzer

# --- motion
int64 position_steps
float64 position_mm
float64 velocity_mm_s
bool moving
uint16 motion_id             # id of the last accepted motion command
float64 encoder_mm           # NaN when no encoder is fitted

# --- faults reported by the firmware / plant (bitmask, see SERIAL_PROTOCOL.md)
uint16 fault_flags
uint16 FAULT_HEARTBEAT_LOST=1
uint16 FAULT_ESTOP=2
uint16 FAULT_DRIVER_ALM=4
uint16 FAULT_WDT_RESET=8
uint16 FAULT_INTERLOCK_REJECT=16
uint16 FAULT_KNIFE_SENSOR_CONFLICT=32
uint16 FAULT_RX_OVERFLOW=64
