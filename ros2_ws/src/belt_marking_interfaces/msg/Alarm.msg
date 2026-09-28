# One alarm instance. Published on machine/alarms at every raise / clear / acknowledge
# and embedded in MachineState.active_alarms.
uint8 SEVERITY_INFO=0
uint8 SEVERITY_WARNING=1
uint8 SEVERITY_ERROR=2
uint8 SEVERITY_FATAL=3

# Reaction the state machine applied when the alarm was raised
uint8 REACTION_NONE=0
uint8 REACTION_HOLD=1
uint8 REACTION_STOP=2
uint8 REACTION_ABORT=3

uint16 code                        # e.g. 201 -> shown as "E-201"
string code_text                   # "E-201"
uint8 severity
uint8 reaction
string text                        # short English text (UI translates by code)
string remedy                      # suggested operator action
string source                      # "control", "hardware", "laser", "vision", ...
builtin_interfaces/Time stamp      # time raised
bool active                        # condition still present
bool acknowledged
