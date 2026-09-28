# Parameters of one production job (also the payload of a recipe).
uint8 CUT_NONE=0        # continuous marking, no cut
uint8 CUT_EVERY=1       # cut after every mark
uint8 CUT_EVERY_N=2     # cut after every N marks (sets of labels)
uint8 CUT_END=3         # one cut at the end of the batch

uint8 LASER_DONE_CONFIG=0   # use machine default (laser.done_mode)
uint8 LASER_DONE_SIGNAL=1   # wait for busy->idle signal from the laser controller
uint8 LASER_DONE_TIMED=2    # wait laser_time_s

string job_id
string recipe
float64 belt_width_mm
uint32 quantity              # number of marks (labels) to produce
float64 pitch_mm             # distance between consecutive marks = label length + gap
float64 mark_length_mm       # length of the marked area along the belt (validation / visuals)
float64 lead_mm              # label leading edge -> mark origin (cut position reference)
uint8 cut_mode
uint32 cut_every_n
bool initial_trim_cut        # cut the belt start before the first label
uint8 laser_done_mode
float64 laser_time_s         # marking time (timed mode) / expected time (signal mode)
float64 settle_s             # wait after a feed before triggering
float64 post_mark_delay_s    # wait after marking before the next feed
float64 feed_speed_mm_s
LaserStation[] stations      # empty -> machine default stations
string mark_text             # expected text for vision QA (optional)
