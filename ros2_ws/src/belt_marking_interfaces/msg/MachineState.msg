# Machine state, published on machine/state at 10 Hz (transient local).
# PackML / ISA-88 inspired state model.
uint8 STOPPED=0
uint8 RESETTING=1
uint8 IDLE=2
uint8 STARTING=3
uint8 EXECUTE=4
uint8 HOLDING=5
uint8 HELD=6
uint8 UNHOLDING=7
uint8 COMPLETING=8
uint8 COMPLETE=9
uint8 STOPPING=10
uint8 ABORTING=11
uint8 ABORTED=12
uint8 CLEARING=13

uint8 MODE_AUTO=0
uint8 MODE_MANUAL=1
uint8 MODE_MAINTENANCE=2
uint8 MODE_SIMULATION=3

builtin_interfaces/Time stamp
uint8 state
string state_name
uint8 mode
string mode_name
bool use_sim

# Active job
string job_id
string recipe
string phase                 # e.g. "FEED", "SETTLE", "LASER", "CUT_EXTEND"
uint32 marks_done
uint32 marks_total
uint32 pieces_cut
uint32 rejects
float64 progress             # 0..1
float64 job_elapsed_s

# Motion
float64 belt_position_mm     # absolute commanded belt position
float64 belt_speed_mm_s
float64 belt_width_mm

# Lifetime counters
uint64 total_marks
uint64 total_pieces
uint64 knife_cycles
uint64 laser_triggers
float64 belt_meters
float64 uptime_s

# OEE of the current shift/window (0..1)
float64 oee_availability
float64 oee_performance
float64 oee_quality
float64 oee

# Light tower requested by the state machine
bool light_red
bool light_yellow
bool light_green
bool buzzer

Alarm[] active_alarms
