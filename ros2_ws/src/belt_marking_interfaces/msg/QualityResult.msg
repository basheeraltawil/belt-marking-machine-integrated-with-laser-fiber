# Result of the (optional) vision QA for one label.
builtin_interfaces/Time stamp
string job_id
uint32 label_index
bool ok
float64 score            # 0..1 confidence that the mark is good
string text_read         # OCR result if available
string reason            # "", "no_mark", "low_contrast", "text_mismatch", "offset"
float64 offset_mm        # measured mark offset along the belt
