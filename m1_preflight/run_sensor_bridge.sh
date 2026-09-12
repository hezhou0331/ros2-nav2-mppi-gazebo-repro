#!/usr/bin/env bash
set -eo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
# 只在本机 ROS 域发布；不改变狗内服务或创建运动链路。
export PYTHONPATH="$M1_WORKSPACE/deps/zenoh1101:${PYTHONPATH:-}"
export ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$M1_WORKSPACE/m1_preflight/fastdds_sensors.xml"
mkdir -p "$M1_WORKSPACE/artifacts/real_sensors"
# 用文件锁防止同一工作区重复接收和重复发布。
exec 9>"$M1_WORKSPACE/artifacts/real_sensors/receiver.lock"
if ! flock -n 9; then
  echo "M1 sensor receiver is already running; inspect bridge_status.json." >&2
  exit 3
fi
exec /usr/bin/python3 "$M1_WORKSPACE/m1_preflight/zenoh_sensor_bridge.py" \
  --status "$M1_WORKSPACE/artifacts/real_sensors/bridge_status.json" "$@"
