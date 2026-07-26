# ATEC A2 + P7 Model and Safety Boundary

## Scope

This package describes the ATEC competition simulation robot: one Unitree A2
quadruped, a P7 arm on the center of its back, and one head-mounted 3D lidar.
It is a visualization, sensor, and navigation-integration model. It is not a
manufacturer-approved mechanical design or a real-robot control stack.

## Local Model Assets

All runtime meshes and URDF files are stored in this package. Launching the
model does not download assets or depend on the old top-level modeling
workspace.

| Component | Packaged source | Notes |
| --- | --- | --- |
| A2 body and legs | `urdf/vendor/a2.urdf`, `meshes/a2/` | Imported from the Unitree `unitree_ros` A2 model, commit `aa0f5c68b5aba347bad409e71b6430407da758d7`; license is copied to `docs/UNITREE_LICENSE`. |
| P7 arm and UMI gripper | `urdf/vendor/p7_arm_v3_umi_gripper_v3.urdf`, `meshes/p7/`, `meshes/umi_gripper_v3/` | Imported from the team's preserved P7 v3 + UMI source asset; the runtime copy is fully packaged in this repository. |
| Simulation components | `urdf/components/` | Generated from the preserved vendor files by `tools/generate_components.py`; mesh URIs are made package-local, P7 link names receive `p7_` prefixes, and collision shapes are simplified for Gazebo. |
| Competition environment | `worlds/atec_practice_world.sdf` | A practice approximation based on the local ATEC material, not an official measurement drawing. |

The package keeps vendor files separate from generated components. When a
source asset changes, update the vendor copy deliberately, run
`tools/generate_components.py`, and review the resulting component diff.
Detailed source hashes and generation rules are in
[`MODEL_PROVENANCE.md`](MODEL_PROVENANCE.md); third-party license and P7/UMI
redistribution limits are in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Confirmed Configuration

- Platform: Unitree A2, not A2 Pro or another quadruped.
- Arm: P7. The packaged source currently uses the `p7_arm_v3_umi_gripper_v3`
  assembly; confirm the final gripper/end-effector version before hardware
  integration.
- Lidar count: one 3D lidar.
- Lidar location: use the A2's original head location and its imported
  `front_lidar_link` transform. In the pinned source, the transform relative
  to `base_link` is `xyz="0.33767 0 0.08134"`,
  `rpy="1.5708 0 1.5708"`. The simulation-only child
  `front_lidar_sensor_link` changes axes to conventional x-forward, y-left,
  z-up for the Gazebo lidar; it does not change the physical mounting datum.
- Gazebo's GPU sensor reports a sensor-scoped entity name by default. The
  packaged `config/gz_bridge.yaml` uses the supported ros_gz_bridge
  `frame_id` option to inject `front_lidar_sensor_link` into the ROS
  `PointCloud2` header. This changes only the ROS header and is valid because
  the converted Gazebo sensor pose is the same fixed pose as that frame.
- Navigation point-cloud input: `/lidar/points`. The navigation launch
  projects that cloud into `/scan` for SLAM Toolbox and AMCL, then removes
  endpoints inside the A2 + P7 footprint to produce `/collision_scan` for both
  costmaps and Collision Monitor. These are representations of one physical
  lidar.

## Mounting Assumptions

The simulated mounting chain is:

```text
base_link
  -> a2_p7_mount_link
  -> p7_base_link
```

`a2_p7_mount_joint` is fixed at `x=0`, `y=0`, `z=0.145 m` in `base_link`, so
the plate and P7 base are centered on the A2 back. `arm_mount_z` is a launch
argument solely to inspect alternatives in simulation. It must not be used as
a manufacturing dimension.

Before building or operating the physical assembly, obtain and record all of
the following:

1. Unitree-approved rear reserved-hole drawing and allowable payload/load
   envelope for A2.
2. Plate material, thickness, hole pattern, bolt grade, torque and thread-lock
   specification.
3. P7 flange orientation, folded navigation pose, full swept volume, cable
   routing, power budget, and any counterweight.
4. Measured combined mass, center of mass, and stability validation on level
   ground before ramps, steps, grass, mud, or gravel.
5. A measured `base_link -> front_lidar_link` transform from the delivered
   robot. Keep the imported native transform only if that measurement agrees.

## Simulation Boundary

- `gz-sim-velocity-control-system` is a kinematic planar navigation proxy. It
  moves the full model from `/sim/cmd_vel`; it is not an A2 gait controller and
  does not demonstrate foot placement, torque, contact stability, or recovery.
- `/sim/cmd_vel` is bridged to VelocityControl's dedicated `base_link` topic.
  Sending the command to the articulated model entity lets foot-contact and
  joint constraints reduce commanded yaw, so it is unsuitable for this planar
  proxy.
- The four foot-sphere collisions retain normal support but use zero
  tangential friction in simulation. This lets the visually held stance slide
  with the planar proxy instead of pretending that locked legs are walking.
  Do not use this model to estimate A2 traction, stopping distance, or slope
  stability.
- The model holds legs in a conservative stance and holds the P7 in the vendor
  zero pose for navigation. The UMI passive linkage is fixed except for the
  jaw-width joint in this simulation.
- Primitive collisions deliberately replace high-resolution P7 mesh collisions
  to keep Gazebo usable. They are insufficient for arm collision clearance or
  human-safety analysis.
- Terrain and collection objects in `atec_practice_world.sdf` are practice
  proxies. Do not derive real traction, gradeability, grasp clearance, or
  scoring behavior from them.

## Real-Robot Safety Gate

No process in this repository may send movement commands to the physical A2
until the following have been verified with the robot supported and the remote
emergency stop available:

1. The vendor-supported A2 motion API, command units, frame convention,
   watchdog timeout, and loss-of-command behavior.
2. Hardware emergency stop, remote/manual takeover, and a tested stop path
   that overrides autonomous commands.
3. A platform adapter that rejects stale commands and enforces the approved
   speed, acceleration, posture, arm-stow, and competition-zone limits.
4. Lidar time synchronization, measured static transform, data rate, and
   obstacle coverage with the actual P7 plate and cable routing installed.
5. Low-speed, tethered tests with the arm stowed before any autonomous route.

The present `simulation_platform_adapter.py` and Gazebo velocity plugin are
simulation-only. They must never be used as a bridge to a physical A2.
