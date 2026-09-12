#pragma once

#include <system_error>
#include <type_traits>

namespace robot_sdk_lowlevel {

enum class SdkErrc {
  kNotInitialized = 1,
  kCommandRateLimited,
  kHandshakeTimeout,
  kHandshakeNotEnabled,
  kHandshakeUnknownDevice,
  kHandshakeProtocolMismatch,
  kHandshakeServerAlreadyConnected,
  kHandshakeGainControlFailed,
  kInvalidPacket,
  kPayloadSizeMismatch,
  kProtocolHandlerMismatch,
  kPartialSend,
};

const std::error_category& sdk_error_category() noexcept;
std::error_code make_error_code(SdkErrc errc) noexcept;

}  // namespace robot_sdk_lowlevel

namespace std {
template <>
struct is_error_code_enum<robot_sdk_lowlevel::SdkErrc> : std::true_type {};
}  // namespace std
