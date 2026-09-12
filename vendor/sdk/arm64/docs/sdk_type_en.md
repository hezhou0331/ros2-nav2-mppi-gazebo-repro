# robot_sdk_lowlevel — Data Type Reference

## Overview

This document describes the public data types, constants, enums, and structures
used by `robot_sdk_lowlevel`.

---

## Namespaces

```cpp
namespace robot_sdk_lowlevel          // Common types
namespace robot_sdk_lowlevel::zs_m1   // ZS_M1-specific types
namespace robot_sdk_lowlevel::zs_m1f  // ZS_M1F-specific types
```

---

## Common Types

### TransportType

```cpp
enum class TransportType : uint8_t
```

**Description:** Transport protocol type supported by the SDK. Currently only
UDP is supported.

| Enum value | Integer value | Description |
|:--|:--|:--|
| `UDP` | 1 | UDP datagram transport |

---

### UdpClientConfig

```cpp
struct UdpClientConfig
```

**Description:** UDP client connection configuration passed to the client
constructor.

**Members:**

| Member | Type | Default | Description |
|:--|:--|:--|:--|
| `host` | `std::string` | `""` | Robot IP address or resolvable host name |
| `port` | `uint16_t` | `0` | Robot UDP port |
| `bind_address` | `std::string` | `"0.0.0.0"` | Local bind address; usually keep the default |
| `bind_port` | `uint16_t` | `0` | Local bind port; `0` lets the OS choose automatically |

**Example:**

```cpp
robot_sdk_lowlevel::UdpClientConfig config;
config.host = "192.168.168.168";
config.port = 8083;
config.bind_address = "0.0.0.0";  // Optional default.
config.bind_port = 0;             // Optional default.
```

---

### CtrlLostCallback

```cpp
using CtrlLostCallback = std::function<void()>
```

**Description:** Control-lost notification callback type. The SDK invokes it
from the internal receive thread when the robot reports lost control.

**Note:** Keep the callback short and non-blocking.

---

## ZS_M1-Specific Types

> These types are in `namespace robot_sdk_lowlevel::zs_m1`.  
> Header: `robot_sdk_lowlevel/zs_m1/types.h`

---

### JointIndex (ZS_M1)

```cpp
enum class JointIndex : uint8_t
```

**Description:** Joint index enum for accessing
`LowLevelCommand::actuators_cmd` and `LowLevelState::actuators_data`. ZS_M1 has
16 joints, including foot wheel drives.

| Enum value | Integer value | Description |
|:--|:--|:--|
| `kFlHipRoll` | 0 | Front-left hip roll |
| `kFlHipPitch` | 1 | Front-left hip pitch |
| `kFlKneePitch` | 2 | Front-left knee pitch |
| `kFlFoot` | 3 | Front-left foot wheel drive |
| `kFrHipRoll` | 4 | Front-right hip roll |
| `kFrHipPitch` | 5 | Front-right hip pitch |
| `kFrKneePitch` | 6 | Front-right knee pitch |
| `kFrFoot` | 7 | Front-right foot wheel drive |
| `kBlHipRoll` | 8 | Back-left hip roll |
| `kBlHipPitch` | 9 | Back-left hip pitch |
| `kBlKneePitch` | 10 | Back-left knee pitch |
| `kBlFoot` | 11 | Back-left foot wheel drive |
| `kBrHipRoll` | 12 | Back-right hip roll |
| `kBrHipPitch` | 13 | Back-right hip pitch |
| `kBrKneePitch` | 14 | Back-right knee pitch |
| `kBrFoot` | 15 | Back-right foot wheel drive |
| `kCount` | 16 | Total joint count for array sizes |

**Constant:** `kActuatorCount = 16`

**Example:**

```cpp
using namespace robot_sdk_lowlevel::zs_m1;

LowLevelCommand cmd{};
cmd.actuators_cmd[static_cast<size_t>(JointIndex::kFlHipRoll)].kd = 5.0;

for (size_t i = 0; i < kActuatorCount; ++i) {
    cmd.actuators_cmd[i].kd = 5.0;
}
```

---

### ImuIndex (ZS_M1)

```cpp
enum class ImuIndex : uint8_t
```

**Description:** IMU index enum for accessing `LowLevelState::imu_data`.

| Enum value | Integer value | Description |
|:--|:--|:--|
| `kBody` | 0 | Body IMU |
| `kCount` | 1 | Total IMU count |

**Constant:** `kImuCount = 1`

---

### BatteryIndex (ZS_M1)

```cpp
enum class BatteryIndex : uint8_t
```

**Description:** Battery index enum for accessing `LowLevelState::battery_data`.

| Enum value | Integer value | Description |
|:--|:--|:--|
| `kBattery1` | 0 | Battery 1 |
| `kBattery2` | 1 | Battery 2 |
| `kCount` | 2 | Total battery count |

**Constant:** `kBatteryCount = 2`

---

### FillLightIndex (ZS_M1)

```cpp
enum class FillLightIndex : uint8_t
```

**Description:** Fill-light index enum for accessing
`LowLevelCommand::fill_light_switch` and `LowLevelState::fill_light_status`.

| Enum value | Integer value | Description |
|:--|:--|:--|
| `kFront` | 0 | Front fill light |
| `kBack` | 1 | Back fill light |
| `kCount` | 2 | Total fill-light count |

**Constant:** `kFillLightCount = 2`

---

### ActuatorCommand (ZS_M1)

```cpp
struct ActuatorCommand
```

**Description:** Per-actuator command data, including position, velocity,
torque targets, and PD gains.

| Member | Type | Unit | Description |
|:--|:--|:--|:--|
| `pos` | `double` | rad or m | Target position |
| `vel` | `double` | rad/s or m/s | Target velocity |
| `tor` | `double` | N·m | Target feed-forward torque |
| `kp` | `double` | - | Position gain |
| `kd` | `double` | - | Velocity gain |

**Control equation:** `tau_out = kp * (pos - pos_actual) + kd * (vel - vel_actual) + tor`

**Example:**

```cpp
robot_sdk_lowlevel::zs_m1::ActuatorCommand act;
act.pos = 0.0;
act.vel = 0.0;
act.tor = 0.0;
act.kp = 0.0;
act.kd = 5.0;
```

---

### ActuatorState (ZS_M1)

```cpp
struct ActuatorState
```

**Description:** Per-actuator state data obtained from
`LowLevelState::actuators_data`.

| Member | Type | Unit | Description |
|:--|:--|:--|:--|
| `pos` | `double` | rad or m | Current position |
| `vel` | `double` | rad/s or m/s | Current velocity |
| `tor` | `double` | N·m or N | Current torque |
| `temp` | `double` | C | Actuator temperature |
| `voltage` | `double` | V | Actuator voltage |
| `enable` | `bool` | - | Actuator enabled flag |

---

### ImuData (ZS_M1)

```cpp
struct ImuData
```

**Description:** IMU data obtained from `LowLevelState::imu_data`.

| Member | Type | Unit | Description |
|:--|:--|:--|:--|
| `acc[3]` | `double[3]` | m/s^2 | Acceleration [X, Y, Z] |
| `gyro[3]` | `double[3]` | rad/s | Angular velocity [X, Y, Z] |
| `quat[4]` | `double[4]` | - | Quaternion [x, y, z, w] |

---

### PowerSupplyStatus (ZS_M1)

```cpp
enum class PowerSupplyStatus : uint8_t
```

**Description:** Battery power supply status enum corresponding to
`BatteryData::power_supply_status`, stored as `uint8_t`.

| Enum value | Integer value | Description |
|:--|:--|:--|
| `UNKNOWN` | 0 | Unknown power status |
| `CHARGING` | 1 | Charging |
| `DISCHARGING` | 2 | Discharging |
| `FULL` | 3 | Fully charged |

---

### FillLightStatus (ZS_M1)

```cpp
enum class FillLightStatus : uint8_t
```

**Description:** Fill-light status enum corresponding to entries in
`LowLevelState::fill_light_status`, stored as `uint8_t`.

| Enum value | Integer value | Description |
|:--|:--|:--|
| `UNKNOWN` | 0 | Unknown status |
| `ON` | 1 | Fill light on |
| `OFF` | 2 | Fill light off |

---

### BatteryData (ZS_M1)

```cpp
struct BatteryData
```

**Description:** Per-battery state data obtained from
`LowLevelState::battery_data`.

| Member | Type | Default | Unit | Description |
|:--|:--|:--|:--|:--|
| `power` | `float` | `0.0` | % | Battery percentage, 0 to 100 |
| `present` | `bool` | `false` | - | Whether the battery is present |
| `voltage` | `float` | `0.0` | V | Voltage |
| `temperature` | `float` | `0.0` | C | Temperature |
| `current` | `float` | `0.0` | A | Current |
| `power_supply_status` | `uint8_t` | `0` | - | Power status; see `PowerSupplyStatus` |

**Example:**

```cpp
const auto& bat = state->battery_data[0];  // Battery 1.
if (bat.present) {
    std::printf("Power: %.1f%%  Voltage: %.2fV  Status: %s\n",
                bat.power, bat.voltage,
                robot_sdk_lowlevel::zs_m1::PowerSupplyStatusToString(bat.power_supply_status));
}
```

---

### LowLevelCommand (ZS_M1)

```cpp
struct LowLevelCommand
```

**Description:** Low-level command frame sent to a ZS_M1 robot. Each call to
`ZsM1Client::SendLowLevelCommand()` sends one frame.

| Member | Type | Description |
|:--|:--|:--|
| `actuators_cmd` | `std::array<ActuatorCommand, 16>` | Control targets for 16 joints, indexed by `JointIndex` |
| `fill_light_switch` | `std::array<uint8_t, 2>` | Fill-light switches indexed by `FillLightIndex`; nonzero means on, zero means off |

**Example:**

```cpp
robot_sdk_lowlevel::zs_m1::LowLevelCommand cmd{};

for (auto& act : cmd.actuators_cmd) {
    act.kd = 5.0;
}

cmd.fill_light_switch[static_cast<size_t>(
    robot_sdk_lowlevel::zs_m1::FillLightIndex::kFront)] = 1;
cmd.fill_light_switch[static_cast<size_t>(
    robot_sdk_lowlevel::zs_m1::FillLightIndex::kBack)] = 0;
```

---

### LowLevelState (ZS_M1)

```cpp
struct LowLevelState
```

**Description:** Low-level state frame received from a ZS_M1 robot and delivered
through `LowlevelDataRecvCallback`.

| Member | Type | Description |
|:--|:--|:--|
| `timestamp_ms` | `uint64_t` | Robot timestamp in milliseconds |
| `imu_data` | `std::array<ImuData, 1>` | IMU data; `[0]` is the body IMU |
| `actuators_data` | `std::array<ActuatorState, 16>` | State for 16 joints, indexed by `JointIndex` |
| `battery_data` | `std::array<BatteryData, 2>` | Dual-battery state, indexed by `BatteryIndex` |
| `fill_light_status` | `std::array<uint8_t, 2>` | Fill-light status, indexed by `FillLightIndex` |
| `illumination` | `float` | Ambient illumination in lux |

**Example:**

```cpp
client.RegisterLowLevelDataRecvCallback(
    [](std::shared_ptr<robot_sdk_lowlevel::zs_m1::LowLevelState> state) {
        std::printf("Timestamp: %llu ms\n", state->timestamp_ms);

        const auto& imu = state->imu_data[0];
        std::printf("Acceleration: [%.3f, %.3f, %.3f] m/s^2\n",
                    imu.acc[0], imu.acc[1], imu.acc[2]);

        using JI = robot_sdk_lowlevel::zs_m1::JointIndex;
        const auto& fl_hip = state->actuators_data[static_cast<size_t>(JI::kFlHipRoll)];
        std::printf("Front-left hip roll position: %.3f rad\n", fl_hip.pos);

        std::printf("Power: %.1f%%\n", state->battery_data[0].power);
        std::printf("Illumination: %.1f lux\n", state->illumination);
    });
```

---

### LowlevelDataRecvCallback (ZS_M1)

```cpp
using LowlevelDataRecvCallback = std::function<void(std::shared_ptr<LowLevelState> state)>
```

**Description:** Low-level state frame receive callback type. The SDK invokes it
from the internal receive thread.

---

### Helper Functions

#### ToString

```cpp
std::string ToString(const LowLevelCommand& cmd)
std::string ToString(const LowLevelState& state)
```

Formats a command or state frame into a readable single-line string for
debugging and logging.

```cpp
std::cout << robot_sdk_lowlevel::zs_m1::ToString(*state) << "\n";
```

#### PowerSupplyStatusToString

```cpp
const char* PowerSupplyStatusToString(uint8_t status)
```

Converts `BatteryData::power_supply_status` to readable text:
`"charging"`, `"discharging"`, `"full"`, or `"unknown"`.

#### FillLightStatusToString

```cpp
const char* FillLightStatusToString(uint8_t status)
```

Converts a fill-light status value to readable text: `"on"`, `"off"`, or
`"unknown"`.

---

## ZS_M1F-Specific Types

> These types are in `namespace robot_sdk_lowlevel::zs_m1f`.  
> Header: `robot_sdk_lowlevel/zs_m1f/types.h`

ZS_M1F is a leg-only robot and has no foot wheel drive joints. It therefore has
12 joints, three per leg. The other enums and structures are the same as ZS_M1:
`ImuIndex`, `BatteryIndex`, `FillLightIndex`, `ActuatorCommand`,
`ActuatorState`, `ImuData`, `BatteryData`, `PowerSupplyStatus`,
`FillLightStatus`, and `LowlevelDataRecvCallback`.

---

### JointIndex (ZS_M1F)

```cpp
enum class JointIndex : uint8_t  // namespace robot_sdk_lowlevel::zs_m1f
```

**Description:** ZS_M1F joint index enum. It has 12 joints: hip roll, hip pitch,
and knee pitch for each leg.

| Enum value | Integer value | Description |
|:--|:--|:--|
| `kFlHipRoll` | 0 | Front-left hip roll |
| `kFlHipPitch` | 1 | Front-left hip pitch |
| `kFlKneePitch` | 2 | Front-left knee pitch |
| `kFrHipRoll` | 3 | Front-right hip roll |
| `kFrHipPitch` | 4 | Front-right hip pitch |
| `kFrKneePitch` | 5 | Front-right knee pitch |
| `kBlHipRoll` | 6 | Back-left hip roll |
| `kBlHipPitch` | 7 | Back-left hip pitch |
| `kBlKneePitch` | 8 | Back-left knee pitch |
| `kBrHipRoll` | 9 | Back-right hip roll |
| `kBrHipPitch` | 10 | Back-right hip pitch |
| `kBrKneePitch` | 11 | Back-right knee pitch |
| `kCount` | 12 | Total joint count |

**Constant:** `kActuatorCount = 12`

---

### LowLevelCommand (ZS_M1F)

```cpp
struct LowLevelCommand  // namespace robot_sdk_lowlevel::zs_m1f
```

| Member | Type | Description |
|:--|:--|:--|
| `actuators_cmd` | `std::array<ActuatorCommand, 12>` | Control targets for 12 joints |
| `fill_light_switch` | `std::array<uint8_t, 2>` | Fill-light switches |

---

### LowLevelState (ZS_M1F)

```cpp
struct LowLevelState  // namespace robot_sdk_lowlevel::zs_m1f
```

| Member | Type | Description |
|:--|:--|:--|
| `timestamp_ms` | `uint64_t` | Robot timestamp in milliseconds |
| `imu_data` | `std::array<ImuData, 1>` | IMU data |
| `actuators_data` | `std::array<ActuatorState, 12>` | State for 12 joints |
| `battery_data` | `std::array<BatteryData, 2>` | Dual-battery state |
| `fill_light_status` | `std::array<uint8_t, 2>` | Fill-light status |
| `illumination` | `float` | Ambient illumination in lux |

---

## Related Documents

- [Usage Guide](usage_en.md) - Quick start and lifecycle guidance
- [Client API](sdk_client_api_en.md) - Detailed `ZsM1Client` / `ZsM1fClient` API reference
- [Error Code Reference](sdk_error_en.md) - `SdkErrc` enum and error handling patterns
