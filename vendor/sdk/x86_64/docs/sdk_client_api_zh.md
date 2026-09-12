# robot_sdk_lowlevel — 客户端 API 文档

## 概述

本文档描述 `ZsM1Client`（ZS_M1 机型）和 `ZsM1fClient`（ZS_M1F 机型）两个客户端类的完整接口。两者接口完全一致，仅命名空间和底层数据类型不同。

---

## 命名空间

```cpp
namespace robot_sdk_lowlevel::zs_m1   // ZS_M1 机型
namespace robot_sdk_lowlevel::zs_m1f  // ZS_M1F 机型
```

---

## SDK 版本查询

版本查询接口位于 `robot_sdk_lowlevel/version.h`，用于在日志、诊断信息或兼容性检查中记录当前 SDK 构建版本。

```cpp
#include "robot_sdk_lowlevel/version.h"

const char* GetSdkVersion();
int GetSdkVersionMajor();
int GetSdkVersionMinor();
int GetSdkVersionPatch();
```

示例：

```cpp
std::cout << "SDK version: " << robot_sdk_lowlevel::GetSdkVersion() << "\n";
```

这些接口返回 CMake 工程版本，不等同于握手协议版本。握手协议版本由 SDK 内部用于与机器人固件协商兼容性。

---

## ZsM1Client

```cpp
class ZsM1Client  // 位于 robot_sdk_lowlevel/zs_m1/client.h
```

ZS_M1 机器人的底层 UDP 客户端，拥有完整的通信生命周期管理。

### 构造与析构

#### 构造函数

```cpp
explicit ZsM1Client(UdpClientConfig config)
```

**说明：** 构造客户端并绑定 UDP 传输配置。此时不建立网络连接，仅存储配置。

**参数：**

| 参数名 | 类型 | 说明 |
|:--|:--|:--|
| `config` | `UdpClientConfig` | UDP 连接配置，包含机器人 IP、端口及本地绑定参数 |

**相关类型：** 详见 [数据类型文档](sdk_type_zh.md) 中 `UdpClientConfig` 的说明。

---

#### 析构函数

```cpp
~ZsM1Client()
```

**说明：** 若客户端仍处于已初始化状态，析构时自动调用 `Shutdown()` 释放资源。

---

#### 拷贝与移动

```cpp
ZsM1Client(const ZsM1Client&) = delete;
ZsM1Client& operator=(const ZsM1Client&) = delete;
ZsM1Client(ZsM1Client&&) noexcept;
ZsM1Client& operator=(ZsM1Client&&) noexcept;
```

客户端不可拷贝，支持移动语义。

---

### 生命周期管理

#### Initialize — 初始化

```cpp
std::error_code Initialize()
```

**说明：** 连接机器人、执行握手、启动后台接收线程和心跳线程。必须在调用其他接口前成功完成。

**返回值：**

| 返回值 | 说明 |
|:--|:--|
| 空 `error_code`（`!ec`） | 初始化成功 |
| `SdkErrc::kHandshakeTimeout` | 握手超时，机器人未确认 |
| `SdkErrc::kHandshakeNotEnabled` | 机器人端未启用 Low-Level SDK 控制 |
| `SdkErrc::kHandshakeUnknownDevice` | 设备类型未知，需确认客户端类与机型匹配 |
| `SdkErrc::kHandshakeProtocolMismatch` | 协议版本不匹配 |
| `SdkErrc::kHandshakeServerAlreadyConnected` | 机器人已被其他客户端占用 |
| `SdkErrc::kHandshakeGainControlFailed` | 机器人端获取控制权失败 |
| `SdkErrc::kPayloadSizeMismatch` | 握手响应载荷长度异常 |
| `SdkErrc::kInvalidPacket` | 握手响应数据包格式非法 |
| 系统错误码 | UDP 套接字创建或绑定失败 |

**示例：**

```cpp
auto ec = client.Initialize();
if (ec) {
    std::cerr << "初始化失败: " << ec.message() << " (" << ec.value() << ")\n";
    return 1;
}
```

---

#### Shutdown — 关闭

```cpp
std::error_code Shutdown()
```

**说明：** 停止后台线程并关闭 UDP 传输连接。程序退出前务必调用。

**返回值：**

| 返回值 | 说明 |
|:--|:--|
| 空 `error_code` | 关闭成功 |
| 传输层错误码 | UDP 套接字关闭失败（通常可忽略） |

**示例：**

```cpp
auto ec = client.Shutdown();
if (ec) {
    std::cerr << "Shutdown 警告: " << ec.message() << "\n";
}
```

---

#### IsInitialized — 查询初始化状态

```cpp
bool IsInitialized() const
```

**说明：** 查询客户端是否已完成初始化并正在运行。

**返回值：**

| 返回值 | 说明 |
|:--|:--|
| `true` | 已初始化，正在运行 |
| `false` | 未初始化或已关闭 |

---

### 回调注册

#### RegisterControlLostCallback — 注册控制权丢失回调

```cpp
void RegisterControlLostCallback(CtrlLostCallback cb)
```

**说明：** 注册控制权丢失通知回调。当机器人端检测到控制丢失时，从 SDK 内部接收线程调用此回调。

**参数：**

| 参数名 | 类型 | 说明 |
|:--|:--|:--|
| `cb` | `CtrlLostCallback` | 回调函数 `void()`；传入空 `std::function` 可清除回调 |

**注意：** 回调在 SDK 内部线程调用，应保持短小非阻塞。

**示例：**

```cpp
client.RegisterControlLostCallback([]() {
    std::cerr << "[WARN] 控制权丢失！\n";
});

// 清除回调
client.RegisterControlLostCallback({});
```

---

#### RegisterLowLevelDataRecvCallback — 注册状态数据接收回调

```cpp
void RegisterLowLevelDataRecvCallback(LowlevelDataRecvCallback cb)
```

**说明：** 注册底层状态帧接收回调。每收到一帧机器人状态数据，从 SDK 内部接收线程调用此回调。

**参数：**

| 参数名 | 类型 | 说明 |
|:--|:--|:--|
| `cb` | `LowlevelDataRecvCallback` | 回调函数 `void(std::shared_ptr<LowLevelState>)`；传入空 `std::function` 可清除回调 |

**注意：**
- 回调在 SDK 内部线程调用，应保持短小非阻塞。
- `shared_ptr` 参数引用计数在回调返回后递减；若需在回调外保存数据，请复制结构体而非持有 `shared_ptr`。

**示例：**

```cpp
std::mutex state_mutex;
robot_sdk_lowlevel::zs_m1::LowLevelState latest_state;

client.RegisterLowLevelDataRecvCallback(
    [&](std::shared_ptr<robot_sdk_lowlevel::zs_m1::LowLevelState> state) {
        // 仅做快速数据复制
        std::lock_guard<std::mutex> lock(state_mutex);
        latest_state = *state;
    });
```

---

### 命令发送

#### SendLowLevelCommand — 发送底层控制命令

```cpp
std::error_code SendLowLevelCommand(const LowLevelCommand& cmd)
```

**说明：** 序列化并通过 UDP 发送一帧底层控制命令到机器人。

**参数：**

| 参数名 | 类型 | 说明 |
|:--|:--|:--|
| `cmd` | `const LowLevelCommand&` | 命令帧，包含所有关节目标值和补光灯开关 |

**返回值：**

| 返回值 | 说明 |
|:--|:--|
| 空 `error_code` | 发送成功 |
| `SdkErrc::kNotInitialized` | 客户端未初始化 |
| `SdkErrc::kCommandRateLimited` | 超出内部发送频率限制，应稍后重试 |
| `SdkErrc::kPartialSend` | UDP 发送字节数不完整 |
| 系统错误码 | 套接字发送失败 |

**频率限制说明：** SDK 内部对发送频率有上限保护。若调用过快，返回 `kCommandRateLimited`，此时应等待一个控制周期后重试，而非直接报错退出。

**示例（定频控制循环）：**

```cpp
robot_sdk_lowlevel::zs_m1::LowLevelCommand cmd{};
// 配置关节目标...

auto next_wakeup = std::chrono::steady_clock::now();
while (running) {
    auto ec = client.SendLowLevelCommand(cmd);
    if (ec == robot_sdk_lowlevel::SdkErrc::kCommandRateLimited) {
        // 频率过高，等待本周期结束
    } else if (ec) {
        std::cerr << "发送失败: " << ec.message() << "\n";
        break;
    }
    next_wakeup += std::chrono::milliseconds(2);
    std::this_thread::sleep_until(next_wakeup);
}
```

---

## ZsM1fClient

```cpp
class ZsM1fClient  // 位于 robot_sdk_lowlevel/zs_m1f/client.h
```

ZS_M1F 机器人的底层 UDP 客户端，接口与 `ZsM1Client` 完全相同，仅命名空间和关节数量不同。

**命名空间：** `robot_sdk_lowlevel::zs_m1f`

**主要区别：**

| 项目 | ZsM1Client | ZsM1fClient |
|:--|:--|:--|
| 命名空间 | `zs_m1` | `zs_m1f` |
| 关节数 | 16（含足端轮） | 12（纯腿式） |
| 头文件 | `zs_m1_client.h` | `zs_m1f_client.h` |
| 类型文件 | `zs_m1_type.h` | `zs_m1f_type.h` |

所有方法签名和行为与 `ZsM1Client` 完全一致，此处不再重复列出。

**ZS_M1F 最小示例：**

```cpp
#include "robot_sdk_lowlevel/zs_m1f/client.h"

robot_sdk_lowlevel::UdpClientConfig config;
config.host = "192.168.168.168";
config.port = 8083;

robot_sdk_lowlevel::zs_m1f::ZsM1fClient client(config);
client.RegisterLowLevelDataRecvCallback(
    [](std::shared_ptr<robot_sdk_lowlevel::zs_m1f::LowLevelState> state) {
        std::cout << robot_sdk_lowlevel::zs_m1f::ToString(*state) << "\n";
    });

auto ec = client.Initialize();
// ... 控制循环 ...
client.Shutdown();
```

---

## 最佳实践

### 控制循环频率

推荐使用定时唤醒（`sleep_until`）而非 `sleep_for`，可避免累积误差：

```cpp
auto next_wakeup = std::chrono::steady_clock::now();
const auto period = std::chrono::milliseconds(2);  // 2ms = 500Hz

while (running) {
    client.SendLowLevelCommand(cmd);
    next_wakeup += period;
    std::this_thread::sleep_until(next_wakeup);
}
```

### 实时性要求

对时延敏感的场景，建议在发送线程上设置 SCHED_FIFO 实时调度优先级（需要 `CAP_SYS_NICE` 权限）：

```cpp
#include <pthread.h>
#include <sched.h>

sched_param sp;
sp.sched_priority = sched_get_priority_max(SCHED_FIFO);
pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp);
```

### 失败计数保护

连续发送失败时，建议设置上限后退出：

```cpp
int fail_count = 0;
while (running) {
    auto ec = client.SendLowLevelCommand(cmd);
    if (ec && ec != robot_sdk_lowlevel::SdkErrc::kCommandRateLimited) {
        if (++fail_count > 10) {
            std::cerr << "连续失败过多，退出\n";
            break;
        }
    } else {
        fail_count = 0;
    }
    // ...
}
```

---

## 相关文档

- [使用指南](usage_zh.md) — 快速入门与生命周期说明
- [数据类型](sdk_type_zh.md) — `LowLevelCommand`、`LowLevelState` 及枚举定义
- [错误码参考](sdk_error_zh.md) — `SdkErrc` 枚举与错误处理模式
