#!/usr/bin/env bash
# 在 Orin 的新 bash 终端中 source 本文件；不改变 ROS 发现配置或系统设置。
if [[ ! -f /opt/ros/humble/setup.bash ]]; then
  echo 'This workspace requires ROS 2 Humble on Orin.' >&2
  return 1
fi
if [[ -n ${ROS_DISTRO:-} && $ROS_DISTRO != humble ]]; then
  echo 'Open a fresh bash without another ROS distribution sourced.' >&2
  return 1
fi
M1_WORKSPACE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
source /opt/ros/humble/setup.bash
if [[ -f "$M1_WORKSPACE/deps/cv_bridge/local_setup.bash" ]]; then
  source "$M1_WORKSPACE/deps/cv_bridge/local_setup.bash"
fi
if [[ -f "$M1_WORKSPACE/install_preflight/local_setup.bash" ]]; then
  source "$M1_WORKSPACE/install_preflight/local_setup.bash"
fi
export CMAKE_PREFIX_PATH="$M1_WORKSPACE/deps/opt/ros/humble:$M1_WORKSPACE/deps/usr:${CMAKE_PREFIX_PATH:-}"
export LD_LIBRARY_PATH="$M1_WORKSPACE/deps/opt/ros/humble/lib:$M1_WORKSPACE/deps/usr/lib:$M1_WORKSPACE/deps/usr/lib/aarch64-linux-gnu:${LD_LIBRARY_PATH:-}"
export PATH="/usr/bin:/bin:$PATH"
export ROS_LOG_DIR="$M1_WORKSPACE/artifacts/ros_logs"
mkdir -p "$ROS_LOG_DIR"
