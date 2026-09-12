# robot_sdk_lowlevel — Client API Reference

## Overview

This document describes the complete API of `ZsM1Client` for ZS_M1 devices and
`ZsM1fClient` for ZS_M1F devices. The two clients expose the same interface;
only the namespace and model-specific data types differ.

---

## Namespaces

```cpp
namespace robot_sdk_lowlevel::zs_m1   // ZS_M1 devices
namespace robot_sdk_lowlevel::zs_m1f  // ZS_M1F devices
```

---

## SDK Version Query

The SDK version query APIs are declared in `robot_sdk_lowlevel/version.h`. Use
them in logs, diagnostics, and compatibility checks to record the SDK build
version.

```cpp
#include "robot_sdk_lowlevel/version.h"

const char* GetSdkVersion();
int GetSdkVersionMajor();
int GetSdkVersionMinor();
int GetSdkVersionPatch();
```

Example:

```cpp
std::cout << "SDK version: " << robot_sdk_lowlevel::GetSdkVersion() << "\n";
```

These APIs return the CMake project version. They are not the handshake protocol
version. The handshake protocol version is used internally by the SDK when
negotiating compatibility with robot firmware.

---

## ZsM1Client

```cpp
class ZsM1Client  // in robot_sdk_lowlevel/zs_m1/client.h
```

Low-level UDP client for ZS_M1 robots. It manages the full communication
lifecycle.

### Construction and Destruction

#### Constructor

```cpp
explicit ZsM1Client(UdpClientConfig config)
```

**Description:** Constructs a client and stores the UDP transport
configuration. This does not establish a network connection.

**Parameters:**

| Parameter | Type | Description |
|:--|:--|:--|
| `config` | `UdpClientConfig` | UDP connection configuration, including robot IP, port, and local bind parameters |

**Related type:** See `UdpClientConfig` in the [Data Type Reference](sdk_type_en.md).

---

#### Destructor

```cpp
~ZsM1Client()
```

**Description:** If the client is still initialized, the destructor calls
`Shutdown()` automatically to release resources.

---

#### Copy and Move

```cpp
ZsM1Client(const ZsM1Client&) = delete;
ZsM1Client& operator=(const ZsM1Client&) = delete;
ZsM1Client(ZsM1Client&&) noexcept;
ZsM1Client& operator=(ZsM1Client&&) noexcept;
```

The client is non-copyable and movable.

---

### Lifecycle Management

#### Initialize

```cpp
std::error_code Initialize()
```

**Description:** Connects to the robot, performs the handshake, and starts the
background receive and heartbeat threads. This must succeed before using other
client operations.

**Return values:**

| Return value | Description |
|:--|:--|
| Empty `error_code` (`!ec`) | Initialization succeeded |
| `SdkErrc::kHandshakeTimeout` | Handshake timed out; the robot did not acknowledge |
| `SdkErrc::kHandshakeNotEnabled` | Low-Level SDK control is not enabled on the robot |
| `SdkErrc::kHandshakeUnknownDevice` | Unknown device type; check whether the client class matches the robot model |
| `SdkErrc::kHandshakeProtocolMismatch` | Protocol version mismatch |
| `SdkErrc::kHandshakeServerAlreadyConnected` | The robot is already occupied by another client |
| `SdkErrc::kHandshakeGainControlFailed` | The robot failed to grant control |
| `SdkErrc::kPayloadSizeMismatch` | Unexpected handshake response payload length |
| `SdkErrc::kInvalidPacket` | Invalid handshake response packet format |
| System error code | UDP socket creation or binding failed |

**Example:**

```cpp
auto ec = client.Initialize();
if (ec) {
    std::cerr << "Initialize failed: " << ec.message() << " (" << ec.value() << ")\n";
    return 1;
}
```

---

#### Shutdown

```cpp
std::error_code Shutdown()
```

**Description:** Stops background threads and closes the UDP transport. Call it
before program exit.

**Return values:**

| Return value | Description |
|:--|:--|
| Empty `error_code` | Shutdown succeeded |
| Transport error code | UDP socket close failed; usually safe to log and ignore |

**Example:**

```cpp
auto ec = client.Shutdown();
if (ec) {
    std::cerr << "Shutdown warning: " << ec.message() << "\n";
}
```

---

#### IsInitialized

```cpp
bool IsInitialized() const
```

**Description:** Returns whether the client has completed initialization and is
running.

| Return value | Description |
|:--|:--|
| `true` | Initialized and running |
| `false` | Not initialized or already shut down |

---

### Callback Registration

#### RegisterControlLostCallback

```cpp
void RegisterControlLostCallback(CtrlLostCallback cb)
```

**Description:** Registers a control-lost notification callback. When the robot
reports lost control, the SDK invokes this callback from its internal receive
thread.

**Parameters:**

| Parameter | Type | Description |
|:--|:--|:--|
| `cb` | `CtrlLostCallback` | Callback `void()`; pass an empty `std::function` to clear it |

**Note:** The callback runs on an SDK internal thread. Keep it short and
non-blocking.

**Example:**

```cpp
client.RegisterControlLostCallback([]() {
    std::cerr << "[WARN] control lost\n";
});

// Clear callback.
client.RegisterControlLostCallback({});
```

---

#### RegisterLowLevelDataRecvCallback

```cpp
void RegisterLowLevelDataRecvCallback(LowlevelDataRecvCallback cb)
```

**Description:** Registers a low-level state frame receive callback. Each time a
state frame is received, the SDK invokes this callback from its internal receive
thread.

**Parameters:**

| Parameter | Type | Description |
|:--|:--|:--|
| `cb` | `LowlevelDataRecvCallback` | Callback `void(std::shared_ptr<LowLevelState>)`; pass an empty `std::function` to clear it |

**Notes:**

- The callback runs on an SDK internal thread. Keep it short and non-blocking.
- The `shared_ptr` reference count is decremented after the callback returns.
  If data must outlive the callback, copy the structure instead of holding the
  `shared_ptr`.

**Example:**

```cpp
std::mutex state_mutex;
robot_sdk_lowlevel::zs_m1::LowLevelState latest_state;

client.RegisterLowLevelDataRecvCallback(
    [&](std::shared_ptr<robot_sdk_lowlevel::zs_m1::LowLevelState> state) {
        // Only copy data quickly.
        std::lock_guard<std::mutex> lock(state_mutex);
        latest_state = *state;
    });
```

---

### Command Sending

#### SendLowLevelCommand

```cpp
std::error_code SendLowLevelCommand(const LowLevelCommand& cmd)
```

**Description:** Serializes and sends one low-level control command frame to the
robot over UDP.

**Parameters:**

| Parameter | Type | Description |
|:--|:--|:--|
| `cmd` | `const LowLevelCommand&` | Command frame containing all joint targets and fill-light switches |

**Return values:**

| Return value | Description |
|:--|:--|
| Empty `error_code` | Send succeeded |
| `SdkErrc::kNotInitialized` | Client is not initialized |
| `SdkErrc::kCommandRateLimited` | Internal send-rate limit exceeded; retry later |
| `SdkErrc::kPartialSend` | UDP send completed with an incomplete byte count |
| System error code | Socket send failed |

**Rate limit note:** The SDK applies an internal upper bound to the send rate.
If `kCommandRateLimited` is returned, wait for the next control period and retry
instead of treating it as a fatal error.

**Example fixed-rate control loop:**

```cpp
robot_sdk_lowlevel::zs_m1::LowLevelCommand cmd{};
// Configure joint targets...

auto next_wakeup = std::chrono::steady_clock::now();
while (running) {
    auto ec = client.SendLowLevelCommand(cmd);
    if (ec == robot_sdk_lowlevel::SdkErrc::kCommandRateLimited) {
        // Send rate is too high; wait until this period ends.
    } else if (ec) {
        std::cerr << "Send failed: " << ec.message() << "\n";
        break;
    }
    next_wakeup += std::chrono::milliseconds(2);
    std::this_thread::sleep_until(next_wakeup);
}
```

---

## ZsM1fClient

```cpp
class ZsM1fClient  // in robot_sdk_lowlevel/zs_m1f/client.h
```

Low-level UDP client for ZS_M1F robots. Its interface is identical to
`ZsM1Client`; only the namespace and joint count differ.

**Namespace:** `robot_sdk_lowlevel::zs_m1f`

**Main differences:**

| Item | ZsM1Client | ZsM1fClient |
|:--|:--|:--|
| Namespace | `zs_m1` | `zs_m1f` |
| Joint count | 16, including foot wheels | 12, leg-only |
| Client header | `robot_sdk_lowlevel/zs_m1/client.h` | `robot_sdk_lowlevel/zs_m1f/client.h` |
| Type header | `robot_sdk_lowlevel/zs_m1/types.h` | `robot_sdk_lowlevel/zs_m1f/types.h` |

All method signatures and behavior are the same as `ZsM1Client` and are not
repeated here.

**Minimal ZS_M1F example:**

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
// ... control loop ...
client.Shutdown();
```

---

## Best Practices

### Control Loop Frequency

Use timed absolute wakeups (`sleep_until`) instead of `sleep_for` to avoid
accumulated drift:

```cpp
auto next_wakeup = std::chrono::steady_clock::now();
const auto period = std::chrono::milliseconds(2);  // 2 ms = 500 Hz

while (running) {
    client.SendLowLevelCommand(cmd);
    next_wakeup += period;
    std::this_thread::sleep_until(next_wakeup);
}
```

### Realtime Requirements

For latency-sensitive applications, set `SCHED_FIFO` realtime scheduling
priority on the send thread when possible. This requires `CAP_SYS_NICE`
permission.

```cpp
#include <pthread.h>
#include <sched.h>

sched_param sp;
sp.sched_priority = sched_get_priority_max(SCHED_FIFO);
pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp);
```

### Failure Count Protection

When sends fail repeatedly, use an upper bound and exit the control loop:

```cpp
int fail_count = 0;
while (running) {
    auto ec = client.SendLowLevelCommand(cmd);
    if (ec && ec != robot_sdk_lowlevel::SdkErrc::kCommandRateLimited) {
        if (++fail_count > 10) {
            std::cerr << "Too many consecutive failures, exiting\n";
            break;
        }
    } else {
        fail_count = 0;
    }
    // ...
}
```

---

## Related Documents

- [Usage Guide](usage_en.md) - Quick start and lifecycle guidance
- [Data Type Reference](sdk_type_en.md) - `LowLevelCommand`, `LowLevelState`, and enum definitions
- [Error Code Reference](sdk_error_en.md) - `SdkErrc` enum and error handling patterns
