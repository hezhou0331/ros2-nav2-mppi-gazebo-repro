#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <functional>
#include <iomanip>
#include <memory>
#include <new>
#include <sstream>
#include <string>
#include <utility>
#include <variant>

#include "robot_sdk_lowlevel/common_type.h"

namespace robot_sdk_lowlevel {

namespace zs_m1 {

/**
 * @brief Joint ordering used by ZS_M1 low-level command/state arrays.
 */
enum class JointIndex : uint8_t {
  kFlHipRoll = 0,
  kFlHipPitch,
  kFlKneePitch,
  kFlFoot,
  kFrHipRoll,
  kFrHipPitch,
  kFrKneePitch,
  kFrFoot,
  kBlHipRoll,
  kBlHipPitch,
  kBlKneePitch,
  kBlFoot,
  kBrHipRoll,
  kBrHipPitch,
  kBrKneePitch,
  kBrFoot,
  kCount
};
/// Number of actuators encoded in ZS_M1 low-level messages.
static constexpr size_t kActuatorCount = static_cast<size_t>(JointIndex::kCount);

/**
 * @brief IMU ordering used by ZS_M1 low-level state arrays.
 */
enum class ImuIndex : uint8_t { kBody = 0, kCount };
/// Number of IMU payload entries in one ZS_M1 state frame.
static constexpr size_t kImuCount = static_cast<size_t>(ImuIndex::kCount);

/**
 * @brief Battery ordering used by ZS_M1 low-level state arrays.
 */
enum class BatteryIndex : uint8_t { kBattery1 = 0, kBattery2, kCount };
/// Number of battery payload entries in one ZS_M1 state frame.
static constexpr size_t kBatteryCount = static_cast<size_t>(BatteryIndex::kCount);

/**
 * @brief Fill-light ordering used by ZS_M1 low-level command/state arrays.
 */
enum class FillLightIndex : uint8_t { kFront = 0, kBack, kCount };
/// Number of fill-light entries in ZS_M1 command/state frames.
static constexpr size_t kFillLightCount = static_cast<size_t>(FillLightIndex::kCount);

/**
 * @brief Actuator state data.
 */
struct ActuatorState {
  double pos;      ///< Position: rad or m.
  double vel;      ///< Velocity: rad/s or m/s.
  double tor;      ///< Torque: N·m or N.
  double temp;     ///< Temperature: C.
  double voltage;  ///< Voltage: V.
  bool enable;     ///< Enabled flag.
};

/**
 * @brief Actuator command data.
 */
struct ActuatorCommand {
  double pos;  ///< Target position: rad or m.
  double vel;  ///< Target velocity: rad/s or m/s.
  double tor;  ///< Target torque: N·m.
  double kp;   ///< Position gain.
  double kd;   ///< Velocity gain.
};

/**
 * @brief IMU data.
 */
struct ImuData {
  double acc[3];   ///< Acceleration X/Y/Z: m/s^2.
  double gyro[3];  ///< Angular velocity X/Y/Z: rad/s.
  double quat[4];  ///< Quaternion (x, y, z, w).
};

/**
 * @brief Power supply status enumeration.
 */
enum class PowerSupplyStatus : uint8_t {
  UNKNOWN = 0,      ///< Power supply status unknown.
  CHARGING = 1,     ///< Charging.
  DISCHARGING = 2,  ///< Discharging.
  FULL = 3,         ///< Fully charged.
};

/**
 * @brief Fill light status enumeration.
 */
enum class FillLightStatus : uint8_t {
  UNKNOWN = 0,  ///< Fill light status unknown.
  ON = 1,       ///< Fill light on.
  OFF = 2,      ///< Fill light off.
};

/** @brief Battery state data. */
struct BatteryData {
  float power = 0.0F;        ///< Power percentage: %.
  bool present = false;      ///< Battery present flag.
  float voltage = 0.0F;      ///< Voltage: V.
  float temperature = 0.0F;  ///< Temperature: C.
  float current = 0.0F;      ///< Current: A.
  uint8_t power_supply_status =
      static_cast<uint8_t>(PowerSupplyStatus::UNKNOWN);  ///< Power supply status.
};

/**
 * @brief Convert a battery power-supply status value into readable text.
 * @param status Raw `BatteryData::power_supply_status` value.
 * @return Human-readable status string.
 */
inline const char* PowerSupplyStatusToString(uint8_t status) {
  switch (static_cast<PowerSupplyStatus>(status)) {
    case PowerSupplyStatus::CHARGING:
      return "charging";
    case PowerSupplyStatus::DISCHARGING:
      return "discharging";
    case PowerSupplyStatus::FULL:
      return "full";
    case PowerSupplyStatus::UNKNOWN:
    default:
      return "unknown";
  }
}

/**
 * @brief Convert a fill-light status value into readable text.
 * @param status Raw fill-light status value.
 * @return Human-readable status string.
 */
inline const char* FillLightStatusToString(uint8_t status) {
  switch (static_cast<FillLightStatus>(status)) {
    case FillLightStatus::ON:
      return "on";
    case FillLightStatus::OFF:
      return "off";
    case FillLightStatus::UNKNOWN:
    default:
      return "unknown";
  }
}

inline void AppendImu(std::ostringstream& oss, const ImuData& imu, size_t index) {
  oss << "{idx=" << index << ", acc=[" << imu.acc[0] << ", " << imu.acc[1] << ", " << imu.acc[2]
      << "], gyro=[" << imu.gyro[0] << ", " << imu.gyro[1] << ", " << imu.gyro[2] << "], quat=["
      << imu.quat[0] << ", " << imu.quat[1] << ", " << imu.quat[2] << ", " << imu.quat[3] << "]}";
}

inline void AppendActuatorCommand(std::ostringstream& oss, const ActuatorCommand& cmd,
                                  size_t index) {
  oss << "{idx=" << index << ", pos=" << cmd.pos << ", vel=" << cmd.vel << ", tor=" << cmd.tor
      << ", kp=" << cmd.kp << ", kd=" << cmd.kd << "}";
}

inline void AppendActuatorState(std::ostringstream& oss, const ActuatorState& state, size_t index) {
  oss << "{idx=" << index << ", pos=" << state.pos << ", vel=" << state.vel << ", tor=" << state.tor
      << ", temp=" << state.temp << ", voltage=" << state.voltage
      << ", enable=" << (state.enable ? "true" : "false") << "}";
}

inline void AppendBattery(std::ostringstream& oss, const BatteryData& battery, size_t index) {
  oss << "{idx=" << index << ", power=" << battery.power
      << ", present=" << (battery.present ? "true" : "false") << ", voltage=" << battery.voltage
      << ", temperature=" << battery.temperature << ", current=" << battery.current
      << ", status=" << PowerSupplyStatusToString(battery.power_supply_status) << "}";
}

inline void AppendFillLight(std::ostringstream& oss, uint8_t status, size_t index) {
  oss << "{idx=" << index << ", value=" << static_cast<unsigned int>(status)
      << ", status=" << FillLightStatusToString(status) << "}";
}

/**
 * @brief Command frame sent from the SDK to a ZS_M1 robot.
 *
 * Each call to `ZsM1Client::SendLowLevelCommand()` serializes one instance of
 * this structure.
 */
struct LowLevelCommand {
  std::array<ActuatorCommand, kActuatorCount> actuators_cmd;
  std::array<uint8_t, kFillLightCount> fill_light_switch;
};

/**
 * @brief State frame received from a ZS_M1 robot.
 *
 * This structure is delivered through `LowlevelDataRecvCallback`.
 */
struct LowLevelState {
  uint64_t timestamp_ms;
  std::array<ImuData, kImuCount> imu_data;
  std::array<ActuatorState, kActuatorCount> actuators_data;
  std::array<BatteryData, kBatteryCount> battery_data;
  std::array<uint8_t, kFillLightCount> fill_light_status;
  float illumination = 0.0F;
};

/**
 * @brief Format a `LowLevelCommand` into a readable single-line string.
 * @param cmd Command payload to format.
 * @return Readable text for debugging and logging.
 */
inline std::string ToString(const LowLevelCommand& cmd) {
  std::ostringstream oss;
  oss << std::fixed << std::setprecision(3);
  oss << "LowLevelCommand{actuators_cmd=[";
  for (size_t i = 0; i < cmd.actuators_cmd.size(); ++i) {
    if (i != 0) {
      oss << ", ";
    }
    AppendActuatorCommand(oss, cmd.actuators_cmd[i], i);
  }

  oss << "], fill_light_switch=[";
  for (size_t i = 0; i < cmd.fill_light_switch.size(); ++i) {
    if (i != 0) {
      oss << ", ";
    }
    oss << "{idx=" << i << ", value=" << static_cast<unsigned int>(cmd.fill_light_switch[i]) << "}";
  }
  oss << "]}";
  return oss.str();
}

/**
 * @brief Format a `LowLevelState` into a readable single-line string.
 * @param state State payload to format.
 * @return Readable text for debugging and logging.
 */
inline std::string ToString(const LowLevelState& state) {
  std::ostringstream oss;
  oss << std::fixed << std::setprecision(3);
  oss << "LowLevelState{timestamp_ms=" << state.timestamp_ms;

  oss << ", imu_data=[";
  for (size_t i = 0; i < state.imu_data.size(); ++i) {
    if (i != 0) {
      oss << ", ";
    }
    AppendImu(oss, state.imu_data[i], i);
  }

  oss << "], actuators_data=[";
  for (size_t i = 0; i < state.actuators_data.size(); ++i) {
    if (i != 0) {
      oss << ", ";
    }
    AppendActuatorState(oss, state.actuators_data[i], i);
  }

  oss << "], battery_data=[";
  for (size_t i = 0; i < state.battery_data.size(); ++i) {
    if (i != 0) {
      oss << ", ";
    }
    AppendBattery(oss, state.battery_data[i], i);
  }

  oss << "], fill_light_status=[";
  for (size_t i = 0; i < state.fill_light_status.size(); ++i) {
    if (i != 0) {
      oss << ", ";
    }
    AppendFillLight(oss, state.fill_light_status[i], i);
  }

  oss << "], illumination=" << state.illumination << "}";
  return oss.str();
}

/**
 * @brief Callback for structured ZS_M1 low-level state updates.
 * @param state Shared state payload for one received frame.
 *
 * @note The callback is invoked from the SDK internal receive thread.
 */
using LowlevelDataRecvCallback = std::function<void(std::shared_ptr<LowLevelState> state)>;

}  // namespace zs_m1
}  // namespace robot_sdk_lowlevel
