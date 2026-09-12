# robot_sdk_lowlevel — Error Code Reference

## Overview

All major SDK operations return `std::error_code`. This document describes the
SDK-defined error enum, error category mechanism, and common error handling
patterns.

---

## Namespace

```cpp
namespace robot_sdk_lowlevel
```

Header: `robot_sdk_lowlevel/error.h`

---

## Error Code Mechanism

The SDK uses the standard `std::error_code` mechanism and extends it with an
SDK-specific error category:

- **SDK-defined errors:** use `robot_sdk_lowlevel::sdk_error_category()`
- **Transport/system errors:** keep their native `std::system_category()`

**Basic checking patterns:**

```cpp
auto ec = client.Initialize();

// 1. Boolean check.
if (ec) {
    std::cerr << "Error: " << ec.message() << "\n";
}

// 2. Compare with a specific SDK error.
if (ec == robot_sdk_lowlevel::SdkErrc::kHandshakeTimeout) {
    // Handle handshake timeout.
}

// 3. Check the error category.
if (ec.category() == robot_sdk_lowlevel::sdk_error_category()) {
    // SDK-defined error.
} else {
    // System/transport error.
}
```

---

## SdkErrc Enum

```cpp
enum class SdkErrc
```

**Description:** SDK-defined error code enum. All enum values are registered
with `std::is_error_code_enum`, so they can be compared directly with
`std::error_code`.

| Enum value | Integer value | Triggering API | Description |
|:--|:--|:--|:--|
| `kNotInitialized` | 1 | `SendLowLevelCommand` | Client has not called `Initialize()` |
| `kCommandRateLimited` | 2 | `SendLowLevelCommand` | Internal send-rate limit exceeded; retry later |
| `kHandshakeTimeout` | 3 | `Initialize` | Handshake timed out; the robot did not respond in time |
| `kHandshakeNotEnabled` | 4 | `Initialize` | Handshake / Low-Level SDK control is not enabled |
| `kHandshakeUnknownDevice` | 5 | `Initialize` | Unknown device type during handshake |
| `kHandshakeProtocolMismatch` | 6 | `Initialize` | SDK protocol version does not match the robot |
| `kHandshakeServerAlreadyConnected` | 7 | `Initialize` | The robot is already occupied by another client |
| `kHandshakeGainControlFailed` | 8 | `Initialize` | Failed to gain control during handshake |
| `kInvalidPacket` | 9 | Internal receive path | Received an invalid packet |
| `kPayloadSizeMismatch` | 10 | Internal receive path | Packet payload size does not match the expected size |
| `kProtocolHandlerMismatch` | 11 | Internal path | Protocol handler mismatch |
| `kPartialSend` | 12 | `SendLowLevelCommand` | UDP send completed with an incomplete byte count |

---

## Public Functions

### sdk_error_category

```cpp
const std::error_category& sdk_error_category() noexcept
```

**Description:** Returns the SDK-specific error category. Use it to determine
whether a `std::error_code` came from the SDK layer.

**Example:**

```cpp
if (ec.category() == robot_sdk_lowlevel::sdk_error_category()) {
    std::cerr << "SDK error: " << ec.message() << "\n";
}
```

---

### make_error_code

```cpp
std::error_code make_error_code(SdkErrc errc) noexcept
```

**Description:** Constructs a `std::error_code` from `SdkErrc`. Because
`SdkErrc` is registered as an `is_error_code_enum`, you usually do not need to
call this manually.

---

## Error Codes by API

### Initialize()

| Error code | Meaning | Suggested handling |
|:--|:--|:--|
| No error | Initialization succeeded | Continue |
| `kHandshakeTimeout` | The robot did not respond to the handshake | Check IP, port, network connection, and robot power |
| `kHandshakeNotEnabled` | Low-Level SDK control is not enabled | Enable Low-Level SDK control on the robot side |
| `kHandshakeUnknownDevice` | Unknown device type | Use the client class matching the robot model |
| `kHandshakeProtocolMismatch` | Protocol version mismatch | Upgrade the SDK or robot firmware |
| `kHandshakeServerAlreadyConnected` | The robot is already occupied | Wait for the other client to disconnect and retry |
| `kHandshakeGainControlFailed` | Failed to gain control | Check robot state and retry after the robot is ready |
| `kPayloadSizeMismatch` | Unexpected handshake payload length | Check SDK/firmware compatibility |
| `kInvalidPacket` | Invalid handshake packet format | Check SDK/firmware compatibility and network integrity |
| System error code | UDP socket error | Check network interface configuration |

### SendLowLevelCommand()

| Error code | Meaning | Suggested handling |
|:--|:--|:--|
| No error | Send succeeded | Continue |
| `kNotInitialized` | `Initialize()` has not been called | Initialize first |
| `kCommandRateLimited` | Send rate exceeded | Wait for one control period and retry; do not treat as fatal |
| `kPartialSend` | UDP send was incomplete | Log and retry in the next cycle |
| System error code | Socket send failed | Check network connection and consider reinitialization |

### Shutdown()

| Error code | Meaning | Suggested handling |
|:--|:--|:--|
| No error | Shutdown succeeded | - |
| Transport error code | UDP socket close failed | Usually safe to log and ignore |

---

## Error Handling Examples

### Example 1: Initialize Error Handling

```cpp
auto ec = client.Initialize();
if (ec == robot_sdk_lowlevel::SdkErrc::kHandshakeTimeout) {
    std::cerr << "Handshake timed out. Check robot power and IP address.\n";
    return 1;
} else if (ec == robot_sdk_lowlevel::SdkErrc::kHandshakeServerAlreadyConnected) {
    std::cerr << "Robot is already occupied by another client.\n";
    return 1;
} else if (ec) {
    std::cerr << "Initialize failed: " << ec.message() << " (" << ec.value() << ")\n";
    return 1;
}
```

### Example 2: SendLowLevelCommand Handling in a Control Loop

```cpp
int fail_count = 0;
while (running) {
    auto ec = client.SendLowLevelCommand(cmd);

    if (ec == robot_sdk_lowlevel::SdkErrc::kCommandRateLimited) {
        // Send rate is too high. Do not count it as a failure.
    } else if (ec) {
        std::cerr << "Send failed: " << ec.message() << "\n";
        if (++fail_count > 10) {
            std::cerr << "More than 10 consecutive failures; stopping control loop.\n";
            break;
        }
    } else {
        fail_count = 0;
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(2));
}
```

### Example 3: Handling by Error Category

```cpp
auto ec = client.Initialize();
if (ec) {
    if (ec.category() == robot_sdk_lowlevel::sdk_error_category()) {
        std::cerr << "SDK error [" << ec.value() << "]: " << ec.message() << "\n";
    } else {
        std::cerr << "System error: " << ec.message() << "\n";
    }
}
```

---

## Notes

- `SdkErrc` enum values do not map to `std::errc`. For exact comparisons,
  compare directly with `SdkErrc` enum values instead of integer values.
- `kCommandRateLimited` is normal flow-control feedback, not a fatal error. In
  a control loop, handle it by retrying later and do not count it as a send
  failure.
- Transport errors returned from `Shutdown()` usually do not require recovery;
  logging them is enough.

---

## Related Documents

- [Usage Guide](usage_en.md) - Quick start and lifecycle guidance
- [Client API](sdk_client_api_en.md) - Complete parameters and return values for client APIs
- [Data Type Reference](sdk_type_en.md) - Command frames, state frames, and enum definitions
