#pragma once

namespace robot_sdk_lowlevel {

enum class LogLevel {
  kDebug = 0,
  kInfo = 1,
  kWarn = 2,
  kError = 3,
};

void SetSdkLogLevel(LogLevel level);

}  // namespace robot_sdk_lowlevel
