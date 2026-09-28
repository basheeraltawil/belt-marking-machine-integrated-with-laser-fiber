# Discrete process event, published on machine/events.
uint8 MARK=0          # a laser station finished marking a label
uint8 CUT=1           # the knife completed a cut
uint8 REJECT=2        # a label was rejected (vision / laser timeout skip)
uint8 PIECE_OUT=3     # a cut piece left the machine
uint8 JOB_START=4
uint8 JOB_END=5

builtin_interfaces/Time stamp
uint8 type
string job_id
uint32 label_index        # label index within the job (MARK / REJECT)
uint32 station            # laser station index (MARK)
float64 belt_coord_mm     # belt coordinate of the mark origin / cut line
float64 feed_mm           # commanded feed at the moment of the event
float64 length_mm         # piece length (CUT / PIECE_OUT)
uint32 labels_in_piece    # (CUT)
string detail
