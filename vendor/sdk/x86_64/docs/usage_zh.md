# robot_sdk_lowlevel 使用指南

语言版本：

- [English](usage_en.md)
- [中文](usage_zh.md)

---

> **重要提示：** 使用和断开 Low-Level SDK 时，由于控制权切换逻辑，会导致电机参数清0，请务必保持设备处于卧倒状态。运行过程中如果电机控制数据超过 500ms 没有得到更新，底层会自动将电机数据置零保护。

---

## 概览

`robot_sdk_lowlevel` 是面向机器人底层控制的 UDP 通信 SDK，提供直接访问关节执行器、IMU、电池和补光灯的低延迟接口。

**Tips：**

如需启用 Low-Level SDK，需要将 RK3588 升级到 `v0.2.3` 及以上版本，并通过 `v1.1.7` 及以上版本的 MidDogController App 完成启用操作。

**支持的机型：**

| 机型系列 | 支持版本 | 关节数 | 需要实例化的客户端类 |
|:--|:--|:--|:--|
| 中狗轮足机型 | Air 版本、标准版本、Pro 版本、Ultra 版本 | 16 | `zs_m1::ZsM1Client` |
| 中狗点足机型 | Air 版本、标准版本、Pro 版本、Ultra 版本 | 12 | `zs_m1f::ZsM1fClient` |

选择客户端时只需要按机型系列区分：中狗轮足系列使用 `ZsM1Client`，中狗点足系列使用 `ZsM1fClient`。同一系列内不同版本的 Low-Level 控制接口保持一致。

**当前支持的传输方式：** UDP

---

## 公开 API

```
robot_sdk_lowlevel::UdpClientConfig
robot_sdk_lowlevel::CtrlLostCallback
robot_sdk_lowlevel::LogLevel
robot_sdk_lowlevel::SdkErrc
robot_sdk_lowlevel::SetSdkLogLevel()
robot_sdk_lowlevel::sdk_error_category()
robot_sdk_lowlevel::GetSdkVersion()
robot_sdk_lowlevel::GetSdkVersionMajor()
robot_sdk_lowlevel::GetSdkVersionMinor()
robot_sdk_lowlevel::GetSdkVersionPatch()
robot_sdk_lowlevel::zs_m1::ZsM1Client
robot_sdk_lowlevel::zs_m1::LowLevelCommand
robot_sdk_lowlevel::zs_m1::LowLevelState
robot_sdk_lowlevel::zs_m1f::ZsM1fClient
robot_sdk_lowlevel::zs_m1f::LowLevelCommand
robot_sdk_lowlevel::zs_m1f::LowLevelState
```

---

## 公开头文件

```cpp
#include "robot_sdk_lowlevel/common_type.h"      // 公共配置和回调类型
#include "robot_sdk_lowlevel/error.h"            // 错误码
#include "robot_sdk_lowlevel/logging.h"          // SDK 日志等级
#include "robot_sdk_lowlevel/version.h"          // SDK 版本查询
#include "robot_sdk_lowlevel/zs_m1/client.h"     // ZS_M1 客户端
#include "robot_sdk_lowlevel/zs_m1/types.h"      // ZS_M1 数据类型
#include "robot_sdk_lowlevel/zs_m1f/client.h"    // ZS_M1F 客户端
#include "robot_sdk_lowlevel/zs_m1f/types.h"     // ZS_M1F 数据类型
```

---

## 构建集成

安装后使用 CMake 集成：

```cmake
find_package(robot_sdk_lowlevel CONFIG REQUIRED)

add_executable(my_app main.cpp)
target_link_libraries(my_app PRIVATE robot_sdk_lowlevel::robot_sdk_lowlevel)
```

使用 C++17 标准：

```cmake
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
```

---

## SDK 版本查询

如果需要在日志、诊断信息或兼容性检查中记录当前 SDK 版本，可以包含 `robot_sdk_lowlevel/version.h`：

```cpp
#include "robot_sdk_lowlevel/version.h"

std::cout << "SDK version: " << robot_sdk_lowlevel::GetSdkVersion() << "\n";
std::cout << "major: " << robot_sdk_lowlevel::GetSdkVersionMajor() << "\n";
std::cout << "minor: " << robot_sdk_lowlevel::GetSdkVersionMinor() << "\n";
std::cout << "patch: " << robot_sdk_lowlevel::GetSdkVersionPatch() << "\n";
```

这些接口返回 SDK 构建版本，版本号来自 CMake 工程版本。

---

## 典型生命周期

```
构造客户端
    │
    ▼
注册回调（可选）
    │
    ▼
Initialize() ─── 失败 ──→ 检查错误码，退出
    │
    │ 成功
    ▼
控制循环：
  SendLowLevelCommand() ──→ kCommandRateLimited ──→ sleep 后重试
    │
    │（回调接收）
    ▼
  LowlevelDataRecvCallback（状态帧）
  CtrlLostCallback（控制权丢失）
    │
    ▼
Shutdown()
```

1. 创建 `UdpClientConfig` 并填写机器人 IP 和端口。
2. 构造 `ZsM1Client` 或 `ZsM1fClient`。
3. 注册 `CtrlLostCallback` 和 `LowlevelDataRecvCallback`（可选，但建议注册）。
4. 调用 `Initialize()` — 完成 UDP 握手并启动后台线程。
5. 在控制循环中定频调用 `SendLowLevelCommand()`。
6. 在回调中轻量处理 `LowLevelState` 状态帧。
7. 程序退出前调用 `Shutdown()`。

---

## 命令发送线程建议

在高频控制场景中，建议将 `SendLowLevelCommand()` 放在独立的命令发送线程中运行，并尽量减少该线程内的日志、文件 I/O、动态内存分配和复杂计算。发送线程只负责按固定周期生成或读取最新指令并下发，其他耗时工作应放到低优先级线程处理。

在 Linux 上，为了提高高频下发的周期稳定性，可以参考 `sdk_example.cpp` 的实现：

- 使用 `std::this_thread::sleep_until()` 按绝对时间唤醒，减少周期误差累计。
- 使用 `pthread_setschedparam(..., SCHED_FIFO, ...)` 将发送线程设为实时调度，并提高优先级。
- 根据系统负载情况，使用 `pthread_setaffinity_np()` 将发送线程绑定到固定 CPU 核心。
- 实时调度通常需要 `CAP_SYS_NICE` 权限或 root 权限；如果设置失败，程序仍可运行，但高频下发的抖动可能增大。

---

## 最小示例（ZS_M1）

```cpp
#include <chrono>
#include <iostream>
#include <memory>
#include <thread>

#include "robot_sdk_lowlevel/zs_m1/client.h"
#include "robot_sdk_lowlevel/error.h"

int main() {
  // 1. 配置连接参数
  robot_sdk_lowlevel::UdpClientConfig config;
  config.host = "192.168.168.168";
  config.port = 8083;
  config.bind_address = "0.0.0.0";
  config.bind_port = 0;

  // 2. 构造客户端
  robot_sdk_lowlevel::zs_m1::ZsM1Client client(config);

  // 3. 注册回调
  client.RegisterControlLostCallback([]() {
    std::cerr << "[WARN] 控制权丢失\n";
  });
  client.RegisterLowLevelDataRecvCallback(
      [](std::shared_ptr<robot_sdk_lowlevel::zs_m1::LowLevelState> state) {
        std::cout << robot_sdk_lowlevel::zs_m1::ToString(*state) << "\n";
      });

  // 4. 初始化（握手 + 启动内部线程）
  auto ec = client.Initialize();
  if (ec) {
    std::cerr << "Initialize 失败: " << ec.message() << " (" << ec.value() << ")\n";
    return 1;
  }

  // 5. 控制循环（2ms 周期，约 500Hz）
  robot_sdk_lowlevel::zs_m1::LowLevelCommand cmd{};
  for (auto& act : cmd.actuators_cmd) {
    act.kd = 5.0;  // 仅设置阻尼，其余为零
  }

  for (int i = 0; i < 1000; ++i) {
    ec = client.SendLowLevelCommand(cmd);
    if (ec == robot_sdk_lowlevel::SdkErrc::kCommandRateLimited) {
      std::this_thread::sleep_for(std::chrono::milliseconds(2));
      continue;
    }
    if (ec) {
      std::cerr << "SendLowLevelCommand 失败: " << ec.message() << "\n";
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
  }

  // 6. 关闭
  ec = client.Shutdown();
  if (ec) {
    std::cerr << "Shutdown 警告: " << ec.message() << "\n";
  }
  return 0;
}
```

---

## 回调与线程说明

| 回调 | 调用线程 | 注意事项 |
|:--|:--|:--|
| `LowlevelDataRecvCallback` | SDK 内部接收线程 | 保持短小非阻塞 |
| `CtrlLostCallback` | SDK 内部接收线程 | 保持短小非阻塞 |

**重要：** 回调函数应仅做数据复制或简单校验。耗时操作（文件 I/O、网络、复杂计算）必须投递到独立线程处理。

```cpp
// 推荐：在回调中只做数据复制
client.RegisterLowLevelDataRecvCallback(
    [&](std::shared_ptr<robot_sdk_lowlevel::zs_m1::LowLevelState> state) {
      std::lock_guard<std::mutex> lock(state_mutex_);
      latest_state_ = *state;  // 仅复制数据
    });
```

---

## 错误处理

所有主要操作均返回 `std::error_code`。

```cpp
auto ec = client.Initialize();
if (ec) {
    std::cerr << "错误: " << ec.message() << " (值: " << ec.value() << ")\n";
}
```

**判断 SDK 专属错误：**

```cpp
if (ec == robot_sdk_lowlevel::SdkErrc::kCommandRateLimited) {
  // 超出发送频率，稍后重试
}

if (ec.category() == robot_sdk_lowlevel::sdk_error_category()) {
  // SDK 定义错误
}
```

详细错误码说明见 [错误码参考](sdk_error_zh.md)。

---

## SDK 日志

SDK 内部诊断信息默认写到 `stdout`，格式如下：

```text
[YYYY-MM-DD HH:MM:SS.mmm][LowLevel SDK][LEVEL] message
```

默认 SDK 日志等级是 `WARN`。可以为当前进程内的所有 SDK 实例统一调整：

```cpp
#include "robot_sdk_lowlevel/logging.h"

robot_sdk_lowlevel::SetSdkLogLevel(robot_sdk_lowlevel::LogLevel::kInfo);
```

---

## 示例程序

SDK 发布包的 `example/` 目录中提供更完整的控制循环示例。示例工程通过
`find_package(robot_sdk_lowlevel CONFIG REQUIRED)` 使用发布包内的 SDK，不依赖源码仓库。

| 机型系列 | 适用版本 | 源文件 | CMake 入口 |
|:--|:--|:--|:--|
| 中狗轮足机型 | Air、标准、Pro、Ultra | `example/zs_m1/sdk_example.cpp` | `example/zs_m1/CMakeLists.txt` |
| 中狗点足机型 | Air、标准、Pro、Ultra | `example/zs_m1f/sdk_example.cpp` | `example/zs_m1f/CMakeLists.txt` |

### 构建示例

以解压后的 C++ 发布包目录 `robot_sdk_lowlevel-<version>/` 为例：

```bash
cd robot_sdk_lowlevel-<version>

# 构建中狗轮足 ZS_M1 示例
cmake -S example/zs_m1 -B example/zs_m1/build
cmake --build example/zs_m1/build -j

# 构建中狗点足 ZS_M1F 示例
cmake -S example/zs_m1f -B example/zs_m1f/build
cmake --build example/zs_m1f/build -j
```

示例的 `CMakeLists.txt` 会自动从 `example/../..` 推导 SDK 发布包根目录，因此在发布包内直接构建时无需额外设置 `CMAKE_PREFIX_PATH`。

如果将示例复制到发布包目录外部，需要手动指定 SDK 前缀：

```bash
cmake -S <example_dir> -B <build_dir> -DCMAKE_PREFIX_PATH=<sdk_release_dir>
cmake --build <build_dir> -j
```

### 运行基础连通性示例

运行前请确认机器人处于安全姿态，并已通过 App 启用 Low-Level SDK。

```bash
cd robot_sdk_lowlevel-<version>

# 中狗轮足 ZS_M1
sudo ./example/zs_m1/build/lowlevel_sdk_example \
  --host 192.168.168.168 \
  --port 8083

# 中狗点足 ZS_M1F
sudo ./example/zs_m1f/build/lowlevel_sdk_zs_m1f_example \
  --host 192.168.168.168 \
  --port 8083
```

基础示例会完成握手，按固定周期发送零力矩阻尼指令，并打印机器人上报的状态帧。程序结束时会打印收到的状态回调总数，可用于确认通信链路是否正常。

常用参数：

| 参数 | 说明 |
|:--|:--|
| `--host <ip>` | 机器人 IP 地址 |
| `--port <port>` | 机器人 UDP 端口，默认 `8083` |
| `--max-cycles <n>` | 最大发送周期数 |
| `--period-ms <n>` | 发送周期，默认 `2` ms |
| `--no-rt` | 禁用实时调度，便于普通权限下调试 |
| `--send-cpu <n>` | 将发送线程绑定到指定 CPU 核心 |
| `--recv-cpu <n>` | 将接收线程绑定到指定 CPU 核心 |
| `--rt-prio <n>` | 指定实时调度优先级 |

## 相关文档

- [客户端 API](sdk_client_api_zh.md) — `ZsM1Client` / `ZsM1fClient` 接口详细说明
- [数据类型](sdk_type_zh.md) — 命令帧、状态帧、枚举定义
- [错误码参考](sdk_error_zh.md) — `SdkErrc` 枚举与错误处理模式
