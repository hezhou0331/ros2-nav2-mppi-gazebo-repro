# Platform Adapter Contract

The navigation stack never controls a robot or simulator directly. Nav2 sends
commands through `velocity_gate.py`, and a platform adapter is the sole
consumer of `/platform/cmd_vel`. The adapter publishes `/platform/ready` and
must not publish `odom -> base_link`; the localization source is the sole owner
of that TF.

Two mutually exclusive adapters currently implement this boundary:

| Adapter | Target | Verification status |
| --- | --- | --- |
| `simulation_platform_adapter.py` | Gazebo `VelocityControl` planar proxy | Navigation regression only |
| `atec_a2_sdk2_adapter` | Unitree A2 official SDK2 Sport service | SDK-free tests passed; physical A2 not verified |

The Gazebo adapter is not a gait controller and must never be connected to a
physical platform. The SDK2 adapter is not used by the Gazebo regression and
does not make the planar proxy a legged-motion simulation.

`a2_hardware_control.launch.py` starts only the latching hardware velocity gate
and the SDK2 adapter. It does not start Gazebo, publish a simulation TF, or
generate fake safety states. It expects separately verified `/cmd_vel`,
`/nav/healthy`, `/platform/automatic_mode`, `/platform/manual_override`, and
`/platform/estop` sources. This is the runtime connection for the control
boundary, not a complete hardware navigation bringup.

## A2 SDK2 boundary

The hardware adapter is pinned to the official
`unitreerobotics/unitree_sdk2_python` commit
`65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5`. Its deliberately narrow API is:

- client: `unitree_sdk2py.a2.sport.sport_client.SportClient`
- state: `rt/lf/sportmodestate`
- motion calls: `Move(vx, 0.0, vyaw)` and `StopMove()` only
- accepted Sport modes: `DEFAULT_MODE` (3) and `RUNNING_MODE` (4)

The adapter does not stand the robot up, recover it, choose a gait, issue
low-level joint commands, publish odometry, or publish TF. Every nonzero SDK2
RPC return code is treated as a failure, including positive timeout/error codes.
The installed distribution must also carry PEP 610 metadata proving that it came
from the pinned repository and commit. Package version `1.0.1`,
`cyclonedds==0.10.2`, hashes of the command-path SDK files, and the robot's A2
Sport server API version `1.0.0.1` are also checked before motion is available;
otherwise startup remains fail-closed.

## ROS safety inputs

The hardware adapter starts fail-closed and requires fresh values for all of
the following conditions before `/platform/ready` can become true:

| Topic or source | Required state |
| --- | --- |
| `/platform/automatic_mode` | `true` heartbeat |
| `/platform/manual_override` | `false` heartbeat |
| `/platform/estop` | `false` heartbeat from an authoritative safety interface |
| A2 SportModeState | `error_code == 0`, allowed mode, and fresh sample |
| SDK2 request path | initialized and most recent RPC returned zero |

The public SDK revision above does not expose an authoritative A2 automatic
mode, physical-estop, or wireless-controller takeover state. A separately
verified hardware or PLC bridge must publish those three ROS heartbeats.
Constant publishers and controller axes are not acceptable safety evidence on
the physical robot.

The official A2 Sport client disables the SDK lease mechanism, and this node
does not identify ROS publishers by itself. The hardware control network must
therefore be isolated, only one authorized Sport client may be present, and ROS
DDS permissions must restrict these command and safety topics to the verified
navigation and PLC processes.

RPC failures, malformed commands, manual override, estop, and invalid Sport
states latch the hardware adapter closed. Recovery requires an authoritative
`automatic_mode=false -> true` cycle while manual override, estop, Sport state,
and the SDK path are fresh and safe; the old velocity command is discarded, so
motion also requires a new command.

Command and Bool inputs use depth-one subscriptions and local DDS receive
timestamps. Samples that already exceeded their watchdog while waiting in the
executor are rejected instead of being re-stamped at callback time. After the
adapter has once been ready, a stale authoritative heartbeat or Sport state also
latches the adapter and clears the previous command. The SDK Sport subscriber
uses a direct callback without the optional ten-sample Python FIFO.

`/platform/cmd_vel` accepts only `linear.x` and `angular.z`. The hardware
adapter rejects NaN, infinity, or any unsupported nonzero degree of freedom and
independently clamps commands to `0.10 m/s` and `0.20 rad/s`. Its default
nominal request path while the DDS service remains matched is:

```text
0.08 s command watchdog + 0.02 s worker period + 2 * 0.02 s RPC timeout
= 0.14 s
```

Those velocity caps, watchdog ceilings, unsupported-axis epsilon, and allowed
Sport modes are hard code limits. Configuration may only make them stricter.
An exact zero velocity is translated to `StopMove()` rather than a successful
`Move(0, 0, 0)` call.
Non-zero `StopMove()` returns and exceptions remain latched and are retried on
the next `0.02 s` control decision; only a successful stop enters the normal
`0.10 s` refresh cadence.

This is not a physical stop guarantee. The pinned SDK sleeps in fixed `0.10 s`
increments when its DDS writer is unmatched, so the corresponding local return
path is approximately `0.30 s` before scheduling overhead, and the stop request
cannot reach an unavailable service. A separately verified robot-side watchdog
and physical out-of-band stop are mandatory. Normal shutdown attempts
`StopMove()` and retries failures every control period within the configured
join deadline; process `SIGKILL`, host power loss, or a wedged network cannot
be made safe by this process alone.

Detailed setup and support-stand tests are in
`src/atec_a2_sdk2_adapter/README.md`. Until those tests pass on the target A2,
`platform.adapter_verified` remains `false` and the package must not be used for
unattended operation.

## Sensor and TF boundary

The ATEC reference configuration assumes one head-mounted 3D lidar mounted at
the official `front_lidar_link`. The simulation publishes its point cloud in
the child `front_lidar_sensor_link`, whose axes are suitable for a horizontal
scan. It publishes `/lidar/points`; the launch file projects that single stream
to `/scan` for SLAM and localization, then removes endpoints inside the A2 + P7
footprint to produce `/collision_scan` for both costmaps and Collision Monitor.
Those are representations of one sensor. Real driver extrinsics and self-filter
geometry remain subject to final hardware measurement.
