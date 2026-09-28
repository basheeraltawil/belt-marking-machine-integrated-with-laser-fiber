# belt_marking_gazebo

Gazebo **Fortress** (Ignition Gazebo 6, the version paired with ROS 2 Humble) world and a
*kinematic digital twin* of the machine.

Gazebo has no deformable belt, and friction conveyors are not repeatable to 0.1 mm. So the
belt position comes from the stepper model in `sim_hardware_node`, and `gz_twin_node`
mirrors the process into Gazebo:

* knife cylinder, laser gantry heads and beams are URDF joints driven by
  `JointPositionController` systems (`/belt_sim/<joint>`), fed from `joint_states`;
* each laser mark (from `sim/plant_events`) is spawned as a decal and moved with the belt
  (`/world/belt_marking/set_pose`). Weak marks, from the `laser_weak_mark` fault, are grey;
* each cut spawns the piece, with its marks, as a dynamic body. When the ejector runs it is
  dropped on the chute and slides into the bin;
* the QA camera (`/qa_camera/image_raw`, 640×480 @ 15 Hz) looks at the belt after the
  laser for the vision QA node.

Normally started by `belt_marking_bringup sim.launch.py gazebo:=true`. Use
`headless:=true` for a server-only run (camera still renders with `--headless-rendering`).
