#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <string>
#include <variant>

namespace robot_sdk_lowlevel {
/**
 * @brief Transport implementations understood by the SDK.
 *
 * The current public SDK only exposes UDP transport configuration.
 */
enum class TransportType : uint8_t {
  UDP = 1,  ///< UDP datagram transport.
};

/**
 * @brief UDP client configuration used to connect to a robot.
 *
 * The SDK opens a UDP socket to `host:port` and optionally binds a local
 * address/port before connecting.
 */
struct UdpClientConfig {
  std::string host;   ///< Robot IP address or resolvable hostname.
  uint16_t port = 0;  ///< Robot UDP port.

  std::string bind_address = "0.0.0.0";  ///< Optional local source address.
  uint16_t bind_port = 0;                ///< Optional local source port. `0` lets OS choose.
};

/**
 * @brief Generic transport configuration wrapper.
 *
 * This alias exists so the SDK can grow additional transport backends later
 * without changing the higher-level API shape. At the moment it only contains
 * `UdpClientConfig`.
 */
using TransportConfig = std::variant<UdpClientConfig>;

/**
 * @brief Callback invoked when the robot reports that control has been lost.
 *
 * @note The callback is executed on the SDK internal receive thread. Keep the
 * handler short and non-blocking.
 */
using CtrlLostCallback = std::function<void()>;

}  // namespace robot_sdk_lowlevel
