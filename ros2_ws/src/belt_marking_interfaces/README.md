# belt_marking_interfaces

ROS 2 messages, services and the `RunJob` action shared by all packages. The interface
version follows the package version: breaking field changes bump the major version.

| Kind | Name | Purpose |
|---|---|---|
| msg | `MachineState` | PackML state, mode, job progress, counters, OEE, light tower, active alarms |
| msg | `Alarm` | code (`E-201`), severity, reaction, text, remedy, ack flag |
| msg | `IoStatus` | every input/output of the hardware layer + motion + fault flags |
| msg | `JobSpec`, `LaserStation` | job / recipe parameters |
| msg | `ProcessEvent` | mark / cut / reject / piece-out events |
| msg | `QualityResult` | vision QA verdict per label |
| action | `RunJob` | run a job with progress feedback |
| srv | `MachineCommand`, `SetMode` | reset / hold / unhold / stop / abort / clear, mode change |
| srv | `Jog`, `Home`, `CutNow`, `TriggerLaser`, `SetOutput` | manual operations |
| srv | `AckAlarm` | acknowledge one or all alarms |
| srv | `LoadRecipe`, `SaveRecipe`, `ListRecipes`, `DeleteRecipe` | recipe management |
| srv | `HwCommand` | control → hardware layer (sim and real implement the same contract) |
| srv | `InjectFault` | simulation fault injection |
