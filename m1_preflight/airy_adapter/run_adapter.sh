#!/usr/bin/env bash
# 输入适配仅用于本机隔离验收；固定校准有效期，不自动伪造新时钟。
set -eo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../env.sh"
export ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$M1_WORKSPACE/m1_preflight/fastdds_sensors.xml"
exec 9>"$M1_WORKSPACE/artifacts/real_sensors/adapter.lock"
flock -n 9 || { echo '适配器已运行'; exit 3; }
exec /usr/bin/python3 "$M1_WORKSPACE/m1_preflight/airy_adapter/adapter_node.py" \
 --profile "$M1_WORKSPACE/artifacts/real_sensors/clock_profile.json" \
 --status "$M1_WORKSPACE/artifacts/real_sensors/adapter_status.json" "$@"
