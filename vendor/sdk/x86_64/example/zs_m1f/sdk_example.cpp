// ZS_M1F 基础连通性示例
//
// 功能：通过 UDP 连接到 ZS_M1F 机器人，以固定频率（默认 500Hz）向所有执行器发送
// 零力矩阻尼指令（kd=5），同时打印机器人上报的状态数据。每隔 5 秒切换一次补光灯。
// 运行结束后打印收到的状态帧总数，可用于验证 SDK 通信链路是否正常。
//
// 与 zs_m1/sdk_example.cpp 逻辑相同，仅客户端和数据类型替换为 ZS_M1F 版本。
//
// 典型用法：
//   ./lowlevel_sdk_zs_m1f_example                      # 使用默认参数
//   ./lowlevel_sdk_zs_m1f_example --host 192.168.1.100 # 指定机器人 IP
//   ./lowlevel_sdk_zs_m1f_example --no-rt              # 禁用实时调度（调试用）

#include <pthread.h>
#include <sched.h>

#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <limits>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

#include "robot_sdk_lowlevel/zs_m1f/client.h"

using robot_sdk_lowlevel::UdpClientConfig;
using robot_sdk_lowlevel::zs_m1f::kActuatorCount;
using robot_sdk_lowlevel::zs_m1f::LowLevelCommand;
using robot_sdk_lowlevel::zs_m1f::LowLevelState;
using robot_sdk_lowlevel::zs_m1f::ZsM1fClient;

struct ExampleConfig {
  std::string host = "192.168.168.168";
  uint16_t port = 8083;
  std::string bind_address = "0.0.0.0";
  uint16_t bind_port = 0;
  int max_cycles = 15000;
  int period_ms = 2;
  bool enable_rt = true;
  int rt_prio = -1;   // <0 means use max FIFO priority
  int recv_cpu = -1;  // <0 means no pin
  int send_cpu = -1;  // <0 means no pin
};

static void PrintUsage(const char* prog) {
  std::printf("Usage: %s [options]\n", prog);
  std::printf("Options:\n");
  std::printf("  --host <ip>           Remote host (default: 192.168.168.168)\n");
  std::printf("  --port <port>         Remote port (default: 8083)\n");
  std::printf("  --bind-address <ip>   Local bind address (default: 0.0.0.0)\n");
  std::printf("  --bind-port <port>    Local bind port (default: 0)\n");
  std::printf("  --max-cycles <n>      Max send cycles (default: 15000)\n");
  std::printf("  --period-ms <n>       Send period in ms (default: 2)\n");
  std::printf("  --recv-cpu <n>        CPU core for recv thread (default: -1 = no pin)\n");
  std::printf("  --send-cpu <n>        CPU core for send thread (default: -1 = no pin)\n");
  std::printf("  --no-rt               Disable RT scheduling\n");
  std::printf("  --rt-prio <n>         RT priority (1..max). Default: max\n");
  std::printf("  -h, --help            Show this help\n");
}

static bool ParseIntRange(const char* value, int min_value, int max_value, int* out) {
  if (value == nullptr || out == nullptr) {
    return false;
  }
  char* end = nullptr;
  long parsed = std::strtol(value, &end, 10);
  if (end == value || *end != '\0') {
    return false;
  }
  if (parsed < min_value || parsed > max_value) {
    return false;
  }
  *out = static_cast<int>(parsed);
  return true;
}

static const char* RequireValue(int argc, char** argv, int* index, const char* opt) {
  if (index == nullptr || *index + 1 >= argc) {
    std::printf("[ERROR] Missing value for %s\n", opt);
    return nullptr;
  }
  ++(*index);
  return argv[*index];
}

// Returns 0 on success, 1 on error, 2 on help.
static int ParseArgs(int argc, char** argv, ExampleConfig* config) {
  if (config == nullptr) {
    return 1;
  }

  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if (arg == "-h" || arg == "--help") {
      PrintUsage(argv[0]);
      return 2;
    }
    if (arg == "--host") {
      const char* value = RequireValue(argc, argv, &i, "--host");
      if (!value) {
        return 1;
      }
      config->host = value;
      continue;
    }
    if (arg == "--port") {
      const char* value = RequireValue(argc, argv, &i, "--port");
      if (!value) {
        return 1;
      }
      int port = 0;
      if (!ParseIntRange(value, 1, 65535, &port)) {
        std::printf("[ERROR] Invalid port: %s\n", value);
        return 1;
      }
      config->port = static_cast<uint16_t>(port);
      continue;
    }
    if (arg == "--bind-address") {
      const char* value = RequireValue(argc, argv, &i, "--bind-address");
      if (!value) {
        return 1;
      }
      config->bind_address = value;
      continue;
    }
    if (arg == "--bind-port") {
      const char* value = RequireValue(argc, argv, &i, "--bind-port");
      if (!value) {
        return 1;
      }
      int port = 0;
      if (!ParseIntRange(value, 0, 65535, &port)) {
        std::printf("[ERROR] Invalid bind port: %s\n", value);
        return 1;
      }
      config->bind_port = static_cast<uint16_t>(port);
      continue;
    }
    if (arg == "--max-cycles") {
      const char* value = RequireValue(argc, argv, &i, "--max-cycles");
      if (!value) {
        return 1;
      }
      int cycles = 0;
      if (!ParseIntRange(value, 1, std::numeric_limits<int>::max(), &cycles)) {
        std::printf("[ERROR] Invalid max-cycles: %s\n", value);
        return 1;
      }
      config->max_cycles = cycles;
      continue;
    }
    if (arg == "--period-ms") {
      const char* value = RequireValue(argc, argv, &i, "--period-ms");
      if (!value) {
        return 1;
      }
      int period_ms = 0;
      if (!ParseIntRange(value, 1, std::numeric_limits<int>::max(), &period_ms)) {
        std::printf("[ERROR] Invalid period-ms: %s\n", value);
        return 1;
      }
      config->period_ms = period_ms;
      continue;
    }
    if (arg == "--recv-cpu") {
      const char* value = RequireValue(argc, argv, &i, "--recv-cpu");
      if (!value) {
        return 1;
      }
      int cpu = 0;
      if (!ParseIntRange(value, -1, std::numeric_limits<int>::max(), &cpu)) {
        std::printf("[ERROR] Invalid recv-cpu: %s\n", value);
        return 1;
      }
      config->recv_cpu = cpu;
      continue;
    }
    if (arg == "--send-cpu") {
      const char* value = RequireValue(argc, argv, &i, "--send-cpu");
      if (!value) {
        return 1;
      }
      int cpu = 0;
      if (!ParseIntRange(value, -1, std::numeric_limits<int>::max(), &cpu)) {
        std::printf("[ERROR] Invalid send-cpu: %s\n", value);
        return 1;
      }
      config->send_cpu = cpu;
      continue;
    }
    if (arg == "--no-rt") {
      config->enable_rt = false;
      continue;
    }
    if (arg == "--rt-prio") {
      const char* value = RequireValue(argc, argv, &i, "--rt-prio");
      if (!value) {
        return 1;
      }
      int prio = 0;
      if (!ParseIntRange(value, 1, 99, &prio)) {
        std::printf("[ERROR] Invalid rt-prio: %s\n", value);
        return 1;
      }
      config->rt_prio = prio;
      continue;
    }

    std::printf("[ERROR] Unknown option: %s\n", arg.c_str());
    PrintUsage(argv[0]);
    return 1;
  }

  return 0;
}

static void SetThreadRtAndAffinity(const char* name, int cpu, int prio) {
  if (name != nullptr) {
    pthread_setname_np(pthread_self(), name);
  }

  if (cpu >= 0) {
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(cpu, &cpuset);
    int rc = pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);
    if (rc != 0) {
      std::cerr << "Failed to set CPU affinity (cpu=" << cpu << "): " << strerror(rc) << "\n";
    }
  }

  if (prio > 0) {
    sched_param sp;
    sp.sched_priority = prio;
    int rc = pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp);
    if (rc != 0) {
      std::cerr << "Failed to set RT scheduling (prio=" << prio << "): " << strerror(rc)
                << " (need CAP_SYS_NICE/root?)\n";
    }
  }
}

int main(int argc, char** argv) {
  std::printf("[INFO] ZS_M1F SDK example starting...\n");
  ExampleConfig config;
  int parse_rc = ParseArgs(argc, argv, &config);
  if (parse_rc != 0) {
    return parse_rc == 2 ? 0 : 1;
  }
  std::printf("[INFO] Config:\n");
  std::printf("       host: %s\n", config.host.c_str());
  std::printf("       port: %u\n", static_cast<unsigned int>(config.port));
  std::printf("       bind: %s:%u\n", config.bind_address.c_str(),
              static_cast<unsigned int>(config.bind_port));
  std::printf("       max cycles: %d\n", config.max_cycles);
  std::printf("       period ms: %d\n", config.period_ms);
  std::printf("       recv cpu: %d\n", config.recv_cpu);
  std::printf("       send cpu: %d\n", config.send_cpu);
  std::printf("       rt scheduling: %s\n", config.enable_rt ? "enabled" : "disabled");

  UdpClientConfig udp_config;
  udp_config.host = config.host;
  udp_config.port = config.port;
  udp_config.bind_address = config.bind_address;
  udp_config.bind_port = config.bind_port;
  std::printf("[INFO] Connecting to %s:%d ...\n", udp_config.host.c_str(), udp_config.port);

  ZsM1fClient client(udp_config);

  auto ec = client.Initialize();
  if (ec) {
    std::printf("[ERROR] Initialize failed: %s (code: %d)\n", ec.message().c_str(), ec.value());
    return 1;
  }
  std::printf("[INFO] ZsM1fClient initialized successfully.\n");

  int cnt = 0;

  std::once_flag recv_affinity_once;
  client.RegisterLowLevelDataRecvCallback(
      [&cnt, &config, &recv_affinity_once](std::shared_ptr<LowLevelState> state) {
        std::call_once(recv_affinity_once,
                       [&config]() { SetThreadRtAndAffinity("udp_recv", config.recv_cpu, 0); });

        std::printf("%s\n", robot_sdk_lowlevel::zs_m1f::ToString(*state).c_str());
        ++cnt;
      });

  client.RegisterControlLostCallback([]() { std::printf("[WARN] Control lost detected!\n"); });

  // 零力矩阻尼指令：kp=0 不跟踪位置，kd=5 提供阻尼以防止关节自由晃动
  LowLevelCommand cmd{};
  for (size_t i = 0; i < kActuatorCount; ++i) {
    cmd.actuators_cmd[i].pos = 0.0;
    cmd.actuators_cmd[i].vel = 0.0;
    cmd.actuators_cmd[i].tor = 0.0;
    cmd.actuators_cmd[i].kp = 0.0;
    cmd.actuators_cmd[i].kd = 5.0;
  }

  auto next_wakeup = std::chrono::steady_clock::now();
  int i = 0;
  if (config.enable_rt || config.send_cpu >= 0) {
    int prio = 0;
    if (config.enable_rt) {
      const int policy = SCHED_FIFO;
      const int max_priority = sched_get_priority_max(policy);
      prio = config.rt_prio;
      if (prio < 0) {
        prio = max_priority;
        std::cout << "[INFO] Using max RT priority: " << prio << "\n";
      }
      if (prio > max_priority) {
        std::printf("[ERROR] rt-prio %d exceeds max %d\n", prio, max_priority);
        return 1;
      }
    }
    SetThreadRtAndAffinity("udp_send", config.send_cpu, prio);
  }

  int freq_hz = 1000 / config.period_ms;
  bool light_switch = false;
  while (i < config.max_cycles) {
    // 每 5 秒切换一次补光灯，验证灯控指令通路
    if (i % (freq_hz * 5) == 0) {
      cmd.fill_light_switch[0] = light_switch;
      cmd.fill_light_switch[1] = light_switch;
      light_switch = !light_switch;
    }
    static int fail_count = 0;
    ec = client.SendLowLevelCommand(cmd);
    if (ec) {
      std::printf("[WARN] SendLowLevelCommand failed: %s (code: %d)\n", ec.message().c_str(),
                  ec.value());
      if (++fail_count > 10) {
        std::printf("[ERROR] Too many send failures, exiting command loop\n");
        break;
      }
    } else {
      fail_count = 0;
    }
    next_wakeup += std::chrono::milliseconds(config.period_ms);
    std::this_thread::sleep_until(next_wakeup);
    ++i;
  }

  std::printf("[INFO] Shutting down client.\n");
  ec = client.Shutdown();
  if (ec) {
    std::printf("[WARN] Client shutdown warning: %s\n", ec.message().c_str());
  }
  std::printf("[INFO] ZS_M1F SDK example finished.\n");
  std::printf("[INFO] Total state callbacks received: %d\n", cnt);
  return 0;
}
