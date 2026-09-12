# robot_sdk_lowlevel Usage Guide

Language versions:

- [English](usage_en.md)
- [中文](usage_zh.md)

---

> **Important:** When connecting or disconnecting the Low-Level SDK, the motor parameters will be reset to zero due to the control handover logic. Always keep the device in the lying-down position before doing so. During operation, if motor control data is not updated for more than 500 ms, the low-level system automatically zeros the motor data as a protective measure.

---

## Overview

`robot_sdk_lowlevel` is a UDP communication SDK for low-level robot control. It provides low-latency access to joint actuators, IMU data, battery data, and fill lights.

**Tips:**

To enable the Low-Level SDK, upgrade RK3588 to `v0.2.3` or later and enable it through MidDogController App `v1.1.7` or later.

**Supported device families:**

| Device family | Supported variants | Joints | Client class to instantiate |
|:--|:--|:--|:--|
| MidDog wheel-leg family | Air, Standard, Pro, Ultra | 16 | `zs_m1::ZsM1Client` |
| MidDog point-foot family | Air, Standard, Pro, Ultra | 12 | `zs_m1f::ZsM1fClient` |

Select the client by device family: use `ZsM1Client` for the MidDog wheel-leg family and `ZsM1fClient` for the MidDog point-foot family. Variants in the same family share the same Low-Level control interface.

**Currently supported transport:** UDP

---

## Public API

```text
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

## Public Headers

Include the public headers from the installed include tree:

```cpp
#include "robot_sdk_lowlevel/common_type.h"      // Common config and callback types
#include "robot_sdk_lowlevel/error.h"            // Error codes
#include "robot_sdk_lowlevel/logging.h"          // SDK log levels
#include "robot_sdk_lowlevel/version.h"          // SDK version query
#include "robot_sdk_lowlevel/zs_m1/client.h"     // ZS_M1 client
#include "robot_sdk_lowlevel/zs_m1/types.h"      // ZS_M1 data types
#include "robot_sdk_lowlevel/zs_m1f/client.h"    // ZS_M1F client
#include "robot_sdk_lowlevel/zs_m1f/types.h"     // ZS_M1F data types
```

---

## Build Integration

When using CMake after installation:

```cmake
find_package(robot_sdk_lowlevel CONFIG REQUIRED)

add_executable(my_app main.cpp)
target_link_libraries(my_app PRIVATE robot_sdk_lowlevel::robot_sdk_lowlevel)
```

Use the C++17 standard:

```cmake
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
```

---

## SDK Version Query

Include `robot_sdk_lowlevel/version.h` when you need to record the SDK version
in logs, diagnostics, or compatibility checks:

```cpp
#include "robot_sdk_lowlevel/version.h"

std::cout << "SDK version: " << robot_sdk_lowlevel::GetSdkVersion() << "\n";
std::cout << "major: " << robot_sdk_lowlevel::GetSdkVersionMajor() << "\n";
std::cout << "minor: " << robot_sdk_lowlevel::GetSdkVersionMinor() << "\n";
std::cout << "patch: " << robot_sdk_lowlevel::GetSdkVersionPatch() << "\n";
```

These functions return the SDK build version. The version value comes from the
CMake project version.

---

## Typical Lifecycle

```text
Construct client
    |
    v
Register callbacks (optional)
    |
    v
Initialize() ---- failure ----> inspect error code and exit
    |
    | success
    v
Control loop:
  SendLowLevelCommand() ---> kCommandRateLimited ---> sleep and retry
    |
    | callbacks receive
    v
  LowlevelDataRecvCallback (state frames)
  CtrlLostCallback (control lost)
    |
    v
Shutdown()
```

1. Create `UdpClientConfig`.
2. Construct `zs_m1::ZsM1Client` or `zs_m1f::ZsM1fClient`.
3. Register `CtrlLostCallback` and `LowlevelDataRecvCallback` (optional, but recommended).
4. Call `Initialize()` to complete the UDP handshake and start background threads.
5. Call `SendLowLevelCommand()` at a fixed rate in your control loop.
6. Keep callback handling lightweight when consuming `LowLevelState` frames.
7. Call `Shutdown()` before exit.

---

## Command Send Thread Recommendations

For high-frequency control, run
`SendLowLevelCommand()` from a dedicated command send thread. Keep logging, file
I/O, dynamic allocation, and complex computation out of this thread. The send
thread should only produce or read the latest command at a fixed period and send
it; move other work to lower-priority threads.

On Linux, to improve command period stability under high-frequency sending,
refer to `sdk_example.cpp`:

- Use `std::this_thread::sleep_until()` with absolute wakeup times to avoid
  accumulating period drift.
- Use `pthread_setschedparam(..., SCHED_FIFO, ...)` to run the send thread with
  realtime scheduling and a higher priority.
- Use `pthread_setaffinity_np()` to pin the send thread to a fixed CPU core when
  appropriate for the system load.
- Realtime scheduling usually requires `CAP_SYS_NICE` or root privileges. If
  setting it fails, the program can still run, but high-frequency command jitter
  may increase.

---

## Minimal Example (ZS_M1)

```cpp
#include <chrono>
#include <iostream>
#include <memory>
#include <thread>

#include "robot_sdk_lowlevel/zs_m1/client.h"
#include "robot_sdk_lowlevel/error.h"

int main() {
  // 1. Configure connection parameters.
  robot_sdk_lowlevel::UdpClientConfig config;
  config.host = "192.168.168.168";
  config.port = 8083;
  config.bind_address = "0.0.0.0";
  config.bind_port = 0;

  // 2. Construct the client.
  robot_sdk_lowlevel::zs_m1::ZsM1Client client(config);

  // 3. Register callbacks.
  client.RegisterControlLostCallback([]() {
    std::cerr << "[WARN] control lost\n";
  });
  client.RegisterLowLevelDataRecvCallback(
      [](std::shared_ptr<robot_sdk_lowlevel::zs_m1::LowLevelState> state) {
        std::cout << robot_sdk_lowlevel::zs_m1::ToString(*state) << "\n";
      });

  // 4. Initialize (handshake + internal threads).
  auto ec = client.Initialize();
  if (ec) {
    std::cerr << "Initialize failed: " << ec.message() << " (" << ec.value() << ")\n";
    return 1;
  }

  // 5. Control loop (2 ms period, about 500 Hz).
  robot_sdk_lowlevel::zs_m1::LowLevelCommand cmd{};
  for (auto& act : cmd.actuators_cmd) {
    act.kd = 5.0;  // Damping only. Other fields remain zero.
  }

  for (int i = 0; i < 1000; ++i) {
    ec = client.SendLowLevelCommand(cmd);
    if (ec == robot_sdk_lowlevel::SdkErrc::kCommandRateLimited) {
      std::this_thread::sleep_for(std::chrono::milliseconds(2));
      continue;
    }
    if (ec) {
      std::cerr << "SendLowLevelCommand failed: " << ec.message() << "\n";
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
  }

  // 6. Shutdown.
  ec = client.Shutdown();
  if (ec) {
    std::cerr << "Shutdown warning: " << ec.message() << "\n";
  }
  return 0;
}
```

---

## Callback and Threading Notes

| Callback | Calling thread | Notes |
|:--|:--|:--|
| `LowlevelDataRecvCallback` | SDK internal receive thread | Keep it short and non-blocking |
| `CtrlLostCallback` | SDK internal receive thread | Keep it short and non-blocking |

**Important:** Callback functions should only copy data or run simple validation. Expensive work such as file I/O, networking, or complex computation must be handed off to a separate thread.

```cpp
// Recommended: only copy data in the callback.
client.RegisterLowLevelDataRecvCallback(
    [&](std::shared_ptr<robot_sdk_lowlevel::zs_m1::LowLevelState> state) {
      std::lock_guard<std::mutex> lock(state_mutex_);
      latest_state_ = *state;  // Copy data only.
    });
```

---

## Error Handling

All major SDK operations return `std::error_code`.

```cpp
auto ec = client.Initialize();
if (ec) {
  std::cerr << "Error: " << ec.message() << " (value: " << ec.value() << ")\n";
}
```

**Checking SDK-defined errors:**

```cpp
if (ec == robot_sdk_lowlevel::SdkErrc::kCommandRateLimited) {
  // Command rate exceeded. Retry later.
}

if (ec.category() == robot_sdk_lowlevel::sdk_error_category()) {
  // SDK-defined error.
}
```

See [Error Code Reference](sdk_error_en.md) for detailed error code descriptions.

---

## SDK Logging

The SDK writes internal diagnostics to `stdout` using this format:

```text
[YYYY-MM-DD HH:MM:SS.mmm][LowLevel SDK][LEVEL] message
```

The default SDK log level is `WARN`. Change it globally for all SDK instances in
the process:

```cpp
#include "robot_sdk_lowlevel/logging.h"

robot_sdk_lowlevel::SetSdkLogLevel(robot_sdk_lowlevel::LogLevel::kInfo);
```

---

## Example Programs

The C++ release package includes more complete control-loop examples under
`example/`. The example projects use
`find_package(robot_sdk_lowlevel CONFIG REQUIRED)` and link against the SDK
inside the release package; they do not depend on the source repository.

| Device family | Supported variants | Source file | CMake entry |
|:--|:--|:--|:--|
| MidDog wheel-leg family | Air, Standard, Pro, Ultra | `example/zs_m1/sdk_example.cpp` | `example/zs_m1/CMakeLists.txt` |
| MidDog point-foot family | Air, Standard, Pro, Ultra | `example/zs_m1f/sdk_example.cpp` | `example/zs_m1f/CMakeLists.txt` |

### Build Examples

Assume the C++ release package has been extracted to
`robot_sdk_lowlevel-<version>/`:

```bash
cd robot_sdk_lowlevel-<version>

# Build MidDog wheel-leg ZS_M1 examples.
cmake -S example/zs_m1 -B example/zs_m1/build
cmake --build example/zs_m1/build -j

# Build MidDog point-foot ZS_M1F examples.
cmake -S example/zs_m1f -B example/zs_m1f/build
cmake --build example/zs_m1f/build -j
```

The example `CMakeLists.txt` files automatically derive the SDK release root
from `example/../..`, so no extra `CMAKE_PREFIX_PATH` is required when building
inside the release package.

If you copy an example outside the release package, specify the SDK prefix
manually:

```bash
cmake -S <example_dir> -B <build_dir> -DCMAKE_PREFIX_PATH=<sdk_release_dir>
cmake --build <build_dir> -j
```

### Run Connectivity Examples

Before running an example, keep the robot in a safe posture and make sure the
Low-Level SDK has been enabled through the app.

```bash
cd robot_sdk_lowlevel-<version>

# MidDog wheel-leg ZS_M1.
sudo ./example/zs_m1/build/lowlevel_sdk_example \
  --host 192.168.168.168 \
  --port 8083

# MidDog point-foot ZS_M1F.
sudo ./example/zs_m1f/build/lowlevel_sdk_zs_m1f_example \
  --host 192.168.168.168 \
  --port 8083
```

The connectivity examples perform the handshake, send zero-torque damping
commands at a fixed period, and print received robot state frames. When the
program exits, it prints the total number of received state callbacks, which can
be used to confirm that the communication link is working.

Common options:

| Option | Description |
|:--|:--|
| `--host <ip>` | Robot IP address |
| `--port <port>` | Robot UDP port, default `8083` |
| `--max-cycles <n>` | Maximum number of send cycles |
| `--period-ms <n>` | Send period, default `2` ms |
| `--no-rt` | Disable realtime scheduling for debugging without elevated permissions |
| `--send-cpu <n>` | Pin the send thread to a CPU core |
| `--recv-cpu <n>` | Pin the receive thread to a CPU core |
| `--rt-prio <n>` | Set realtime scheduling priority |

## Related Documents

- [Client API](sdk_client_api_en.md) - Detailed `ZsM1Client` / `ZsM1fClient` API reference
- [Data Types](sdk_type_en.md) - Command frames, state frames, and enum definitions
- [Error Code Reference](sdk_error_en.md) - `SdkErrc` enum and error handling patterns
