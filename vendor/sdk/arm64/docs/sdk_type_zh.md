# robot_sdk_lowlevel — 数据类型文档

## 概述

本文档描述 `robot_sdk_lowlevel` SDK 中使用的所有公开数据类型、常量、枚举和结构体定义。

---

## 命名空间

```cpp
namespace robot_sdk_lowlevel          // 公共类型
namespace robot_sdk_lowlevel::zs_m1   // ZS_M1 专用类型
namespace robot_sdk_lowlevel::zs_m1f  // ZS_M1F 专用类型
```

---

## 公共类型

### TransportType

```cpp
enum class TransportType : uint8_t
```

**说明：** SDK 支持的传输协议类型。当前仅支持 UDP。

| 枚举值 | 整数值 | 说明 |
|:--|:--|:--|
| `UDP` | 1 | UDP 数据报传输 |

---

### UdpClientConfig

```cpp
struct UdpClientConfig
```

**说明：** UDP 客户端连接配置，传入客户端构造函数。

**成员变量：**

| 成员名 | 类型 | 默认值 | 说明 |
|:--|:--|:--|:--|
| `host` | `std::string` | `""` | 机器人 IP 地址或可解析主机名 |
| `port` | `uint16_t` | `0` | 机器人 UDP 端口号 |
| `bind_address` | `std::string` | `"0.0.0.0"` | 本地绑定地址，通常保持默认 |
| `bind_port` | `uint16_t` | `0` | 本地绑定端口，`0` 由操作系统自动分配 |

**使用示例：**

```cpp
robot_sdk_lowlevel::UdpClientConfig config;
config.host = "192.168.168.168";
config.port = 8083;
config.bind_address = "0.0.0.0";  // 可省略，默认值
config.bind_port = 0;             // 可省略，默认值
```

---

### CtrlLostCallback

```cpp
using CtrlLostCallback = std::function<void()>
```

**说明：** 控制权丢失通知回调类型。当机器人端报告控制丢失时，从 SDK 内部接收线程调用。

**注意：** 回调必须短小非阻塞。

---

## ZS_M1 专用类型

> 以下类型位于 `namespace robot_sdk_lowlevel::zs_m1`，  
> 头文件：`robot_sdk_lowlevel/zs_m1/types.h`

---

### JointIndex（ZS_M1）

```cpp
enum class JointIndex : uint8_t
```

**说明：** ZS_M1 关节索引枚举，用于访问 `LowLevelCommand::actuators_cmd` 和 `LowLevelState::actuators_data` 数组。ZS_M1 共 16 个关节（含足端轮驱动）。

| 枚举值 | 整数值 | 说明 |
|:--|:--|:--|
| `kFlHipRoll` | 0 | 左前腿髋部横滚 |
| `kFlHipPitch` | 1 | 左前腿髋部俯仰 |
| `kFlKneePitch` | 2 | 左前腿膝部俯仰 |
| `kFlFoot` | 3 | 左前足端（轮驱动） |
| `kFrHipRoll` | 4 | 右前腿髋部横滚 |
| `kFrHipPitch` | 5 | 右前腿髋部俯仰 |
| `kFrKneePitch` | 6 | 右前腿膝部俯仰 |
| `kFrFoot` | 7 | 右前足端（轮驱动） |
| `kBlHipRoll` | 8 | 左后腿髋部横滚 |
| `kBlHipPitch` | 9 | 左后腿髋部俯仰 |
| `kBlKneePitch` | 10 | 左后腿膝部俯仰 |
| `kBlFoot` | 11 | 左后足端（轮驱动） |
| `kBrHipRoll` | 12 | 右后腿髋部横滚 |
| `kBrHipPitch` | 13 | 右后腿髋部俯仰 |
| `kBrKneePitch` | 14 | 右后腿膝部俯仰 |
| `kBrFoot` | 15 | 右后足端（轮驱动） |
| `kCount` | 16 | 关节总数（用于数组大小） |

**常量：** `kActuatorCount = 16`

**按索引访问关节示例：**

```cpp
using namespace robot_sdk_lowlevel::zs_m1;

LowLevelCommand cmd{};
// 通过枚举索引访问（推荐，可读性更强）
cmd.actuators_cmd[static_cast<size_t>(JointIndex::kFlHipRoll)].kd = 5.0;

// 遍历所有关节
for (size_t i = 0; i < kActuatorCount; ++i) {
    cmd.actuators_cmd[i].kd = 5.0;
}
```

---

### ImuIndex（ZS_M1）

```cpp
enum class ImuIndex : uint8_t
```

**说明：** ZS_M1 IMU 索引枚举，用于访问 `LowLevelState::imu_data` 数组。

| 枚举值 | 整数值 | 说明 |
|:--|:--|:--|
| `kBody` | 0 | 机体 IMU |
| `kCount` | 1 | IMU 总数 |

**常量：** `kImuCount = 1`

---

### BatteryIndex（ZS_M1）

```cpp
enum class BatteryIndex : uint8_t
```

**说明：** ZS_M1 电池索引枚举，用于访问 `LowLevelState::battery_data` 数组。

| 枚举值 | 整数值 | 说明 |
|:--|:--|:--|
| `kBattery1` | 0 | 电池 1 |
| `kBattery2` | 1 | 电池 2 |
| `kCount` | 2 | 电池总数 |

**常量：** `kBatteryCount = 2`

---

### FillLightIndex（ZS_M1）

```cpp
enum class FillLightIndex : uint8_t
```

**说明：** ZS_M1 补光灯索引枚举，用于访问 `LowLevelCommand::fill_light_switch` 和 `LowLevelState::fill_light_status` 数组。

| 枚举值 | 整数值 | 说明 |
|:--|:--|:--|
| `kFront` | 0 | 前补光灯 |
| `kBack` | 1 | 后补光灯 |
| `kCount` | 2 | 补光灯总数 |

**常量：** `kFillLightCount = 2`

---

### ActuatorCommand（ZS_M1）

```cpp
struct ActuatorCommand
```

**说明：** 单关节执行器命令数据，包含位置/速度/力矩目标值及 PD 控制增益。

**成员变量：**

| 成员名 | 类型 | 单位 | 说明 |
|:--|:--|:--|:--|
| `pos` | `double` | rad 或 m | 目标位置 |
| `vel` | `double` | rad/s 或 m/s | 目标速度 |
| `tor` | `double` | N·m | 目标力矩（前馈） |
| `kp` | `double` | — | 位置增益（P 项） |
| `kd` | `double` | — | 速度增益（D 项） |

**控制方程：** `τ_out = kp × (pos - pos_actual) + kd × (vel - vel_actual) + tor`

**使用示例：**

```cpp
robot_sdk_lowlevel::zs_m1::ActuatorCommand act;
// 纯阻尼模式（仅 kd，其余为零）
act.pos = 0.0;
act.vel = 0.0;
act.tor = 0.0;
act.kp  = 0.0;
act.kd  = 5.0;
```

---

### ActuatorState（ZS_M1）

```cpp
struct ActuatorState
```

**说明：** 单关节执行器状态数据，从 `LowLevelState::actuators_data` 获取。

**成员变量：**

| 成员名 | 类型 | 单位 | 说明 |
|:--|:--|:--|:--|
| `pos` | `double` | rad 或 m | 当前位置 |
| `vel` | `double` | rad/s 或 m/s | 当前速度 |
| `tor` | `double` | N·m 或 N | 当前力矩 |
| `temp` | `double` | °C | 执行器温度 |
| `voltage` | `double` | V | 执行器电压 |
| `enable` | `bool` | — | 执行器使能标志 |

---

### ImuData（ZS_M1）

```cpp
struct ImuData
```

**说明：** IMU（惯性测量单元）数据，从 `LowLevelState::imu_data` 获取。

**成员变量：**

| 成员名 | 类型 | 单位 | 说明 |
|:--|:--|:--|:--|
| `acc[3]` | `double[3]` | m/s² | 加速度 [X, Y, Z] |
| `gyro[3]` | `double[3]` | rad/s | 角速度 [X, Y, Z] |
| `quat[4]` | `double[4]` | — | 四元数 [x, y, z, w] |

---

### PowerSupplyStatus（ZS_M1）

```cpp
enum class PowerSupplyStatus : uint8_t
```

**说明：** 电池电源状态枚举，对应 `BatteryData::power_supply_status` 字段（以 `uint8_t` 存储）。

| 枚举值 | 整数值 | 说明 |
|:--|:--|:--|
| `UNKNOWN` | 0 | 电源状态未知 |
| `CHARGING` | 1 | 充电中 |
| `DISCHARGING` | 2 | 放电中 |
| `FULL` | 3 | 已满电 |

---

### FillLightStatus（ZS_M1）

```cpp
enum class FillLightStatus : uint8_t
```

**说明：** 补光灯状态枚举，对应 `LowLevelState::fill_light_status` 数组元素（以 `uint8_t` 存储）。

| 枚举值 | 整数值 | 说明 |
|:--|:--|:--|
| `UNKNOWN` | 0 | 状态未知 |
| `ON` | 1 | 补光灯已开启 |
| `OFF` | 2 | 补光灯已关闭 |

---

### BatteryData（ZS_M1）

```cpp
struct BatteryData
```

**说明：** 单块电池状态数据，从 `LowLevelState::battery_data` 获取。

**成员变量：**

| 成员名 | 类型 | 默认值 | 单位 | 说明 |
|:--|:--|:--|:--|:--|
| `power` | `float` | `0.0` | % | 电量百分比（0~100） |
| `present` | `bool` | `false` | — | 电池是否在位 |
| `voltage` | `float` | `0.0` | V | 电压 |
| `temperature` | `float` | `0.0` | °C | 温度 |
| `current` | `float` | `0.0` | A | 电流 |
| `power_supply_status` | `uint8_t` | `0` | — | 电源状态，见 `PowerSupplyStatus` |

**示例：**

```cpp
const auto& bat = state->battery_data[0];  // 电池 1
if (bat.present) {
    std::printf("电量: %.1f%%  电压: %.2fV  状态: %s\n",
                bat.power, bat.voltage,
                robot_sdk_lowlevel::zs_m1::PowerSupplyStatusToString(bat.power_supply_status));
}
```

---

### LowLevelCommand（ZS_M1）

```cpp
struct LowLevelCommand
```

**说明：** 发送给 ZS_M1 机器人的底层控制命令帧。每次调用 `ZsM1Client::SendLowLevelCommand()` 发送一帧。

**成员变量：**

| 成员名 | 类型 | 说明 |
|:--|:--|:--|
| `actuators_cmd` | `std::array<ActuatorCommand, 16>` | 16 个关节的控制目标，按 `JointIndex` 索引 |
| `fill_light_switch` | `std::array<uint8_t, 2>` | 补光灯开关，按 `FillLightIndex` 索引；非零为开，零为关 |

**示例：**

```cpp
robot_sdk_lowlevel::zs_m1::LowLevelCommand cmd{};

// 所有关节设置纯阻尼
for (auto& act : cmd.actuators_cmd) {
    act.kd = 5.0;
}

// 开启前补光灯，关闭后补光灯
cmd.fill_light_switch[static_cast<size_t>(
    robot_sdk_lowlevel::zs_m1::FillLightIndex::kFront)] = 1;
cmd.fill_light_switch[static_cast<size_t>(
    robot_sdk_lowlevel::zs_m1::FillLightIndex::kBack)] = 0;
```

---

### LowLevelState（ZS_M1）

```cpp
struct LowLevelState
```

**说明：** 从 ZS_M1 机器人接收的底层状态帧，通过 `LowlevelDataRecvCallback` 回调传递。

**成员变量：**

| 成员名 | 类型 | 说明 |
|:--|:--|:--|
| `timestamp_ms` | `uint64_t` | 机器人端时间戳（毫秒） |
| `imu_data` | `std::array<ImuData, 1>` | IMU 数据，`[0]` 为机体 IMU |
| `actuators_data` | `std::array<ActuatorState, 16>` | 16 个关节状态，按 `JointIndex` 索引 |
| `battery_data` | `std::array<BatteryData, 2>` | 双电池状态，按 `BatteryIndex` 索引 |
| `fill_light_status` | `std::array<uint8_t, 2>` | 补光灯状态，按 `FillLightIndex` 索引 |
| `illumination` | `float` | 环境光照强度（lux） |

**示例：**

```cpp
client.RegisterLowLevelDataRecvCallback(
    [](std::shared_ptr<robot_sdk_lowlevel::zs_m1::LowLevelState> state) {
        // 时间戳
        std::printf("时间戳: %llu ms\n", state->timestamp_ms);

        // IMU 加速度
        const auto& imu = state->imu_data[0];
        std::printf("加速度: [%.3f, %.3f, %.3f] m/s²\n",
                    imu.acc[0], imu.acc[1], imu.acc[2]);

        // 左前腿髋部位置
        using JI = robot_sdk_lowlevel::zs_m1::JointIndex;
        const auto& fl_hip = state->actuators_data[static_cast<size_t>(JI::kFlHipRoll)];
        std::printf("左前髋横滚位置: %.3f rad\n", fl_hip.pos);

        // 电池
        std::printf("电量: %.1f%%\n", state->battery_data[0].power);

        // 光照
        std::printf("光照: %.1f lux\n", state->illumination);
    });
```

---

### LowlevelDataRecvCallback（ZS_M1）

```cpp
using LowlevelDataRecvCallback = std::function<void(std::shared_ptr<LowLevelState> state)>
```

**说明：** 底层状态帧接收回调类型，从 SDK 内部接收线程调用。

---

### 辅助函数

#### ToString

```cpp
std::string ToString(const LowLevelCommand& cmd)
std::string ToString(const LowLevelState& state)
```

**说明：** 将命令帧或状态帧格式化为可读的单行字符串，用于调试和日志。

```cpp
std::cout << robot_sdk_lowlevel::zs_m1::ToString(*state) << "\n";
```

#### PowerSupplyStatusToString

```cpp
const char* PowerSupplyStatusToString(uint8_t status)
```

将 `BatteryData::power_supply_status` 转换为可读字符串（`"charging"` / `"discharging"` / `"full"` / `"unknown"`）。

#### FillLightStatusToString

```cpp
const char* FillLightStatusToString(uint8_t status)
```

将补光灯状态值转换为可读字符串（`"on"` / `"off"` / `"unknown"`）。

---

## ZS_M1F 专用类型

> 以下类型位于 `namespace robot_sdk_lowlevel::zs_m1f`，  
> 头文件：`robot_sdk_lowlevel/zs_m1f/types.h`

ZS_M1F 是纯足式机器人，**无足端轮驱动关节**，因此关节数为 12（每腿 3 个）。其余枚举和结构体与 ZS_M1 相同（`ImuIndex`、`BatteryIndex`、`FillLightIndex`、`ActuatorCommand`、`ActuatorState`、`ImuData`、`BatteryData`、`PowerSupplyStatus`、`FillLightStatus`、`LowlevelDataRecvCallback`）。

---

### JointIndex（ZS_M1F）

```cpp
enum class JointIndex : uint8_t  // namespace robot_sdk_lowlevel::zs_m1f
```

**说明：** ZS_M1F 关节索引枚举，共 12 个关节（每腿髋横滚、髋俯仰、膝俯仰）。

| 枚举值 | 整数值 | 说明 |
|:--|:--|:--|
| `kFlHipRoll` | 0 | 左前腿髋部横滚 |
| `kFlHipPitch` | 1 | 左前腿髋部俯仰 |
| `kFlKneePitch` | 2 | 左前腿膝部俯仰 |
| `kFrHipRoll` | 3 | 右前腿髋部横滚 |
| `kFrHipPitch` | 4 | 右前腿髋部俯仰 |
| `kFrKneePitch` | 5 | 右前腿膝部俯仰 |
| `kBlHipRoll` | 6 | 左后腿髋部横滚 |
| `kBlHipPitch` | 7 | 左后腿髋部俯仰 |
| `kBlKneePitch` | 8 | 左后腿膝部俯仰 |
| `kBrHipRoll` | 9 | 右后腿髋部横滚 |
| `kBrHipPitch` | 10 | 右后腿髋部俯仰 |
| `kBrKneePitch` | 11 | 右后腿膝部俯仰 |
| `kCount` | 12 | 关节总数 |

**常量：** `kActuatorCount = 12`

---

### LowLevelCommand（ZS_M1F）

```cpp
struct LowLevelCommand  // namespace robot_sdk_lowlevel::zs_m1f
```

| 成员名 | 类型 | 说明 |
|:--|:--|:--|
| `actuators_cmd` | `std::array<ActuatorCommand, 12>` | 12 个关节的控制目标 |
| `fill_light_switch` | `std::array<uint8_t, 2>` | 补光灯开关 |

---

### LowLevelState（ZS_M1F）

```cpp
struct LowLevelState  // namespace robot_sdk_lowlevel::zs_m1f
```

| 成员名 | 类型 | 说明 |
|:--|:--|:--|
| `timestamp_ms` | `uint64_t` | 机器人端时间戳（毫秒） |
| `imu_data` | `std::array<ImuData, 1>` | IMU 数据 |
| `actuators_data` | `std::array<ActuatorState, 12>` | 12 个关节状态 |
| `battery_data` | `std::array<BatteryData, 2>` | 双电池状态 |
| `fill_light_status` | `std::array<uint8_t, 2>` | 补光灯状态 |
| `illumination` | `float` | 环境光照强度（lux） |

---

## 相关文档

- [使用指南](usage_zh.md) — 快速入门与生命周期说明
- [客户端 API](sdk_client_api_zh.md) — `ZsM1Client` / `ZsM1fClient` 接口详细说明
- [错误码参考](sdk_error_zh.md) — `SdkErrc` 枚举与错误处理模式
