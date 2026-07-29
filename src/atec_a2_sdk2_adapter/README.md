# ATEC A2 SDK2 Adapter

This package is the hardware-side boundary from ROS 2 navigation commands to
Unitree's official A2 high-level motion service. It is deliberately separate
from the Gazebo `VelocityControl` proxy. It does not implement a gait, publish
odometry or TF, stand the robot up, recover it, or switch gait modes.

## Pinned official interface

The runtime dependency is Unitree's official Python SDK2 repository:

- repository: <https://github.com/unitreerobotics/unitree_sdk2_python>
- audited commit: `65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5`
- Python package version: `1.0.1`
- required CycloneDDS Python version: `0.10.2`
- required A2 Sport server API version: `1.0.0.1`
- client: `unitree_sdk2py.a2.sport.sport_client.SportClient`
- state topic: `rt/lf/sportmodestate`
- calls used by this package: `Move(vx, 0.0, vyaw)` and `StopMove()` only

Install that exact revision in the same Python environment that builds and runs
the ROS entry point:

```bash
/path/to/ros-python -m pip install \
  'git+https://github.com/unitreerobotics/unitree_sdk2_python.git@65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5'
```

The SDK pins `cyclonedds==0.10.2`. That release has no CPython 3.12 Linux wheel;
on the current Ubuntu 24.04/Jazzy host a bare pip install fails unless a
compatible native CycloneDDS development prefix is installed and exposed via
`CYCLONEDDS_HOME` or `CMAKE_PREFIX_PATH`. The system Python is also PEP 668
managed. Build a fixed Orin image or an explicitly selected ROS-compatible
environment instead of relying on whichever `python3` appears first in `PATH`.

At startup the adapter reads pip's PEP 610 `direct_url.json` and refuses to load
an SDK whose repository, commit, or package version differs from the values
above. It also checks `cyclonedds==0.10.2` and SHA-256 hashes for the A2 Sport,
RPC, channel, and SportModeState source files used by this boundary. After the
client initializes, it queries the robot and requires the server API version to
equal `1.0.0.1` before the backend becomes available. A copied, modified, or
untracked SDK tree is therefore not accepted as the audited runtime. SDK2 is
still imported only inside the worker startup path, so workspace builds and
SDK-free unit tests do not require it.

These checks detect accidental or unauthorized drift against the audited
source, but the production image and its metadata still need a trusted build
and measured/signature-verified deployment. A process that can modify both the
installed files and their verifier can bypass an in-process integrity check.

The selected interface must exist in Linux sysfs, use the Ethernet hardware
type, be enabled, and not be loopback or a wireless interface. The hardware
launch performs this check before constructing either the velocity gate or the
adapter; the backend repeats it before importing SDK2. Link carrier and A2 DDS
state are separate runtime checks, so passing this preflight does not establish
robot connectivity.

## Safety contract

The node starts and remains fail-closed until all of these inputs are known and
fresh:

| Topic or source | Required condition |
| --- | --- |
| `/platform/automatic_mode` (`std_msgs/Bool`) | `true` heartbeat |
| `/platform/manual_override` (`std_msgs/Bool`) | `false` heartbeat |
| `/platform/estop` (`std_msgs/Bool`) | `false` heartbeat from an authoritative interface |
| A2 `rt/lf/sportmodestate` | fresh, `error_code == 0`, mode 3 or 4 |
| SDK2 request path | initialized and most recent RPC returned zero |

The three ROS safety inputs expire after `0.25 s`; they must be heartbeats, not
one-shot values. `/platform/ready` becomes true only while every condition is
satisfied. `/platform/adapter_status` publishes a `DiagnosticArray` explaining
each fail-closed reason.

RPC failures, malformed commands, manual override, estop, and invalid Sport
states are latched. A later successful `StopMove()` or valid command does not
resume motion. Recovery requires authoritative `automatic_mode=false`, fresh
safe manual-override and estop heartbeats, a valid fresh Sport state, and a
healthy SDK path before `automatic_mode=true`; the adapter also discards the
pre-fault command and requires a new command.

ROS command and safety subscriptions use depth 1 and derive sample age from the
local DDS `received_timestamp`, rather than from callback execution time. A
command older than `0.08 s` or a safety sample older than `0.25 s` while waiting
in the executor is rejected and latched. After the adapter has once become
ready, loss of an authoritative heartbeat or Sport state is also latched and
requires the same rearm sequence. The Sport reader uses a direct callback and
does not add the SDK's optional ten-sample Python FIFO.

`/platform/cmd_vel` accepts only `linear.x` and `angular.z`. It rejects NaN,
infinity, and any unsupported non-zero component, then independently clamps the
accepted axes to `0.10 m/s` and `0.20 rad/s`. A rejected or older-than-`0.08 s`
command causes `StopMove()`. An accepted exact zero command also uses
`StopMove()` rather than `Move(0, 0, 0)`.
If `StopMove()` returns a non-zero code or raises, the worker retries on the
next `0.02 s` control decision instead of waiting for the normal `0.10 s` stop
refresh period. The failure remains latched and still requires the full rearm
sequence after the SDK path is healthy.

The values above are code-level maximums, not merely YAML defaults. Parameters
may reduce the velocity, timeout, unsupported-axis epsilon, or allowed-mode set,
but validation rejects any attempt to raise them or enable a mode outside 3/4.

While the DDS Sport service remains matched, the configured nominal request
path is:

```text
command watchdog + worker period + in-flight Move reply + StopMove reply
0.08 s           + 0.02 s        + 0.02 s              + 0.02 s
= 0.14 s
```

This is not a physical stop guarantee. In the pinned SDK, an unmatched DDS
writer sleeps in fixed `0.10 s` increments even when `rpc_timeout_s` is smaller.
An in-flight `Move` followed by `StopMove()` can therefore make the local caller
path approximately `0.08 + 0.02 + 0.10 + 0.10 = 0.30 s`, before scheduling
overhead. More importantly, a stop request cannot reach the robot while the
service is unreachable, so process-side software has no finite physical stop
bound in that failure mode.

Configuration validation only checks that the nominal matched-service path is
within `nominal_stop_request_budget_s=0.20`. A separately verified robot-side
watchdog and physical estop are mandatory. The complete stop chain must be
measured on the final Orin, Ethernet path, A2 firmware, and load before the
adapter can be marked hardware-verified.

The public Unitree SDK does not expose an authoritative A2 automatic-control or
physical-estop status in this audited interface. The three external topics must
therefore come from a separately verified hardware/PLC bridge. Publishing
constants to them is acceptable only in an isolated mock test, never on the
physical robot. Wireless-controller axes are not accepted as estop evidence.

The pinned A2 `SportClient` constructs its RPC base with lease support disabled,
and plain ROS topics do not authenticate a publisher inside this node. Hardware
deployment therefore requires a physically or VLAN-isolated A2 control network,
a single authorized Sport client, and an enforced ROS security/permissions
policy that admits only the navigation process and verified PLC bridge. This
adapter must not share an unrestricted DDS segment with untrusted publishers.

## Build and run

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select atec_a2_sdk2_adapter
source install/setup.bash
ros2 launch atec_a2_sdk2_adapter a2_sdk2_adapter.launch.py \
  network_interface:=enp2s0
```

To start the complete ROS command boundary without any Gazebo process, mock
supervisor, or simulation TF:

```bash
ros2 launch independent_nav_bringup a2_hardware_control.launch.py \
  network_interface:=enp2s0
```

This launch starts the latching hardware velocity gate and this adapter. It
remaps the gate's enable input to the authoritative
`/platform/automatic_mode`, but deliberately does not publish `/cmd_vel`,
`/nav/healthy`, automatic mode, manual override, or estop. Those inputs must
come from the separately verified navigation, localization, and safety bridge.
It is a deployable control boundary, not a completed real-robot navigation
bringup.

The operator must place the A2 in a safe standing locomotion mode before
enabling automatic control. This node never calls `StandUp`, `RecoveryStand`,
`SwitchGait`, or any low-level joint API.

## Verification sequence

1. Run unit tests and configuration validation without the SDK or robot.
2. On a support stand, launch with all external safety inputs false/unknown and
   verify repeated zero-speed `StopMove()` behavior and `ready=false`.
3. Feed each authoritative heartbeat separately; readiness must remain false
   until all inputs and `SportModeState` are valid.
4. Send zero commands, then single-axis commands within the independent caps.
5. Stop `/platform/cmd_vel` with a healthy matched service and measure the
   nominal command-to-stop path.
6. Assert manual override, estop, malformed command, and RPC failure separately;
   verify that each fault remains latched until an automatic-mode false/true
   cycle and that a new command is required.
7. Disconnect Ethernet and verify the independently configured robot-side
   watchdog meets the approved physical stop deadline; the SDK call cannot
   provide this guarantee.
8. Terminate the process and test host power loss while independently observing
   the robot. During normal shutdown the worker retries a failed `StopMove()`
   every control period within the configured `0.50 s` join deadline, but an
   out-of-band physical stop remains mandatory.

## Tests

```bash
PYTHONPATH="$PWD/src/atec_a2_sdk2_adapter" \
  /usr/bin/python3 -m pytest -q src/atec_a2_sdk2_adapter/test
```

The tests use fake SDK modules and clients. They verify lazy loading, pinned
installation metadata, the exact `Move(vx, 0, wz)` mapping,
startup/watchdog/zero-command/shutdown stops, DDS queue-age preservation,
fail-closed freshness, stale-authority latching/rearm, partial-initialization
cleanup, unsupported-axis rejection, NaN rejection, and immutable hardware
caps. They also verify the CycloneDDS and server API pins, critical SDK file
hashes, wired-interface policy, immediate stop-failure retry, bounded shutdown
retry, and that hardware-launch preflight failures construct no command-path
nodes.
