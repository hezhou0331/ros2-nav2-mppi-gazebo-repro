#pragma once

#include <memory>
#include <system_error>

#include "robot_sdk_lowlevel/common_type.h"
#include "robot_sdk_lowlevel/error.h"
#include "robot_sdk_lowlevel/zs_m1f/types.h"

namespace robot_sdk_lowlevel {
namespace zs_m1f {

/**
 * @brief Low-level UDP client for the ZS_M1 robot.
 *
 * `ZsM1fClient` owns the full communication lifecycle for one robot
 * connection:
 * 1. Construct with a UDP transport configuration.
 * 2. Optionally register callbacks.
 * 3. Call `Initialize()` to connect, handshake, and start worker threads.
 * 4. Send `LowLevelCommand` messages and consume `LowLevelState` callbacks.
 * 5. Call `Shutdown()` before exit.
 *
 * The SDK internally runs a receive thread and a heartbeat thread after
 * successful initialization.
 */
class ZsM1fClient {
 public:
  /**
   * @brief Construct a client for one ZS_M1 robot endpoint.
   * @param config UDP transport configuration for the target robot.
   */
  explicit ZsM1fClient(UdpClientConfig config);
  /**
   * @brief Destructor.
   *
   * If the client is still initialized, the destructor shuts it down first.
   */
  ~ZsM1fClient();

  ZsM1fClient(const ZsM1fClient&) = delete;
  ZsM1fClient& operator=(const ZsM1fClient&) = delete;
  ZsM1fClient(ZsM1fClient&&) noexcept;
  ZsM1fClient& operator=(ZsM1fClient&&) noexcept;

  /**
   * @brief Connect, perform handshake, and start internal worker threads.
   * @return Empty `std::error_code` on success; otherwise the failure reason.
   */
  std::error_code Initialize();
  /**
   * @brief Stop worker threads and close the transport connection.
   * @return Empty `std::error_code` on success; otherwise the shutdown error.
   */
  std::error_code Shutdown();
  /**
   * @brief Whether the client has completed initialization successfully.
   * @return `true` when the client is running.
   */
  bool IsInitialized() const;

  /**
   * @brief Register a callback for robot-side control loss notifications.
   * @param cb Callback invoked from the SDK receive thread.
   *
   * Pass an empty `std::function` to clear the callback.
   */
  void RegisterControlLostCallback(CtrlLostCallback cb);
  /**
   * @brief Register a callback for structured ZS_M1 low-level state messages.
   * @param cb Callback invoked from the SDK receive thread.
   *
   * Pass an empty `std::function` to clear the callback.
   */
  void RegisterLowLevelDataRecvCallback(LowlevelDataRecvCallback cb);

  /**
   * @brief Send one low-level control command frame to the robot.
   * @param cmd Command payload to serialize and send.
   * @return Empty `std::error_code` on success.
   *
   * @note The client enforces a default command-rate limit internally. If the
   * call is faster than the supported send rate, it returns
   * `SdkErrc::kCommandRateLimited`.
   */
  std::error_code SendLowLevelCommand(const LowLevelCommand& cmd);

 private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace zs_m1f
}  // namespace robot_sdk_lowlevel
