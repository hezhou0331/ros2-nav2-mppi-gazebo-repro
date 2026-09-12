# robot_sdk_lowlevel — 错误码参考

## 概述

SDK 所有主要操作均返回 `std::error_code`。本文档描述 SDK 定义的错误枚举、错误类别机制及常见错误处理模式。

---

## 命名空间

```cpp
namespace robot_sdk_lowlevel
```

头文件：`robot_sdk_lowlevel/error.h`

---

## 错误码机制

SDK 使用标准的 `std::error_code` 体系，并扩展了 SDK 专属错误类别：

- **SDK 专属错误**：使用 `robot_sdk_lowlevel::sdk_error_category()`
- **传输层/系统错误**：保留原生 `std::system_category()`

**基本判断模式：**

```cpp
auto ec = client.Initialize();

// 方式一：布尔判断（是否有错误）
if (ec) {
    std::cerr << "错误: " << ec.message() << "\n";
}

// 方式二：与具体错误码比较
if (ec == robot_sdk_lowlevel::SdkErrc::kHandshakeTimeout) {
    // 握手超时处理
}

// 方式三：判断错误类别
if (ec.category() == robot_sdk_lowlevel::sdk_error_category()) {
    // SDK 专属错误
} else {
    // 系统/传输层错误
}
```

---

## SdkErrc 枚举

```cpp
enum class SdkErrc
```

**说明：** SDK 专属错误码枚举。所有枚举值均已注册到 `std::is_error_code_enum`，可直接与 `std::error_code` 比较。

| 枚举值 | 整数值 | 触发接口 | 说明 |
|:--|:--|:--|:--|
| `kNotInitialized` | 1 | `SendLowLevelCommand` | 客户端尚未调用 `Initialize()` |
| `kCommandRateLimited` | 2 | `SendLowLevelCommand` | 超出内部发送频率限制，应稍后重试 |
| `kHandshakeTimeout` | 3 | `Initialize` | 握手超时，机器人未在规定时间内响应 |
| `kHandshakeNotEnabled` | 4 | `Initialize` | 握手功能未启用 |
| `kHandshakeUnknownDevice` | 5 | `Initialize` | 握手时设备类型未知 |
| `kHandshakeProtocolMismatch` | 6 | `Initialize` | SDK 协议版本与机器人不匹配 |
| `kHandshakeServerAlreadyConnected` | 7 | `Initialize` | 机器人已被其他客户端占用 |
| `kHandshakeGainControlFailed` | 8 | `Initialize` | 握手获取控制权失败 |
| `kInvalidPacket` | 9 | 内部接收 | 收到格式非法的数据包 |
| `kPayloadSizeMismatch` | 10 | 内部接收 | 数据包载荷长度不匹配 |
| `kProtocolHandlerMismatch` | 11 | 内部 | 协议处理器不匹配 |
| `kPartialSend` | 12 | `SendLowLevelCommand` | UDP 发送字节数不完整 |

---

## 公开函数

### sdk_error_category

```cpp
const std::error_category& sdk_error_category() noexcept
```

**说明：** 返回 SDK 专属错误类别的引用。用于判断一个 `std::error_code` 是否来自 SDK 层。

**示例：**

```cpp
if (ec.category() == robot_sdk_lowlevel::sdk_error_category()) {
    std::cerr << "SDK 错误: " << ec.message() << "\n";
}
```

---

### make_error_code

```cpp
std::error_code make_error_code(SdkErrc errc) noexcept
```

**说明：** 从 `SdkErrc` 枚举值构造 `std::error_code`。由于已注册 `is_error_code_enum`，通常不需要手动调用，`SdkErrc` 可隐式转换为 `std::error_code`。

---

## 各接口错误码速查

### Initialize()

| 错误码 | 含义 | 处理建议 |
|:--|:--|:--|
| 无错误 | 初始化成功 | 继续 |
| `kHandshakeTimeout` | 机器人未响应握手 | 检查 IP/端口/网络连接；确认机器人已开机 |
| `kHandshakeProtocolMismatch` | 协议版本不匹配 | 升级 SDK 或机器人固件 |
| `kHandshakeServerAlreadyConnected` | 机器人已被占用 | 等待其他客户端断开后重试 |
| `kHandshakeUnknownDevice` | 设备类型未知 | 使用与机型匹配的客户端类 |
| 系统错误码 | UDP 套接字错误 | 检查网络接口配置 |

### SendLowLevelCommand()

| 错误码 | 含义 | 处理建议 |
|:--|:--|:--|
| 无错误 | 发送成功 | 继续 |
| `kNotInitialized` | 未调用 Initialize() | 先完成初始化 |
| `kCommandRateLimited` | 发送频率超限 | 等待一个控制周期后重试（勿报错退出） |
| `kPartialSend` | UDP 发送不完整 | 记录日志，下一周期重试 |
| 系统错误码 | 套接字发送失败 | 检查网络连接，考虑重新初始化 |

### Shutdown()

| 错误码 | 含义 | 处理建议 |
|:--|:--|:--|
| 无错误 | 关闭成功 | — |
| 传输层错误码 | UDP 套接字关闭失败 | 通常可忽略，记录日志即可 |

---

## 错误处理示例

### 示例 1：Initialize 错误处理

```cpp
auto ec = client.Initialize();
if (ec == robot_sdk_lowlevel::SdkErrc::kHandshakeTimeout) {
    std::cerr << "握手超时，请检查机器人是否已开机，IP 是否正确\n";
    return 1;
} else if (ec == robot_sdk_lowlevel::SdkErrc::kHandshakeServerAlreadyConnected) {
    std::cerr << "机器人已被其他客户端占用\n";
    return 1;
} else if (ec) {
    std::cerr << "初始化失败: " << ec.message() << " (" << ec.value() << ")\n";
    return 1;
}
```

### 示例 2：控制循环中的 SendLowLevelCommand 处理

```cpp
int fail_count = 0;
while (running) {
    auto ec = client.SendLowLevelCommand(cmd);

    if (ec == robot_sdk_lowlevel::SdkErrc::kCommandRateLimited) {
        // 频率过高：不计为失败，直接等待下一周期
    } else if (ec) {
        std::cerr << "发送失败: " << ec.message() << "\n";
        if (++fail_count > 10) {
            std::cerr << "连续失败超过 10 次，终止控制循环\n";
            break;
        }
    } else {
        fail_count = 0;
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(2));
}
```

### 示例 3：按错误类别区分处理

```cpp
auto ec = client.Initialize();
if (ec) {
    if (ec.category() == robot_sdk_lowlevel::sdk_error_category()) {
        // SDK 协议层错误，通过枚举精确处理
        std::cerr << "SDK 错误 [" << ec.value() << "]: " << ec.message() << "\n";
    } else {
        // 系统/传输层错误（如 socket 创建失败）
        std::cerr << "系统错误: " << ec.message() << "\n";
    }
}
```

---

## 注意事项

- `SdkErrc` 枚举值**不映射到** `std::errc`。精确比较时请直接与 `SdkErrc` 枚举值比较，而非使用整数值。
- `kCommandRateLimited` **不是真正的错误**，是正常的流量控制反馈，应在控制循环中按重试逻辑处理，不应计入失败计数。
- `Shutdown()` 返回的传输层错误通常无需处理，记录日志即可。

---

## 相关文档

- [使用指南](usage_zh.md) — 快速入门与生命周期说明
- [客户端 API](sdk_client_api_zh.md) — 各接口完整参数与返回值说明
- [数据类型](sdk_type_zh.md) — 命令帧、状态帧及枚举定义
