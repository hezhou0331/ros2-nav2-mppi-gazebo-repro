#!/usr/bin/env bash
# 完整的只读输入预检：刷新时间审计、有限时适配、逐帧核验，最后检查真实外参。
set -eo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../env.sh"
cd "$M1_WORKSPACE"
export ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$M1_WORKSPACE/m1_preflight/fastdds_sensors.xml"
export PYTHONPATH="$M1_WORKSPACE/deps/zenoh1101:${PYTHONPATH:-}"
mkdir -p artifacts/real_sensors
exec 8>artifacts/real_sensors/preflight.lock
flock -n 8 || { echo '另一个预检正在运行'; exit 3; }
# 先独占适配锁，防止改写其他运行中适配器使用的时间审计。
exec 9>artifacts/real_sensors/adapter.lock
flock -n 9 || { echo '适配器正在运行，请等待其结束'; exit 3; }
# 已锁定或过期的接收状态不能通过重新审计掩盖；先修复来源，再显式重启。
/usr/bin/python3 - <<'PY_CHECK'
import json,time
from pathlib import Path
p=Path('artifacts/real_sensors/bridge_status.json')
try:
 x=json.loads(p.read_text())
 healthy=(x['running'] and x.get('forwarding_enabled',False) and not x.get('source_fault')
          and 0<=time.time()-x['timestamp_unix']<5
          and len(x['streams'])==4
          and all(v.get('seconds_since_receive') is not None and v['seconds_since_receive']<1 for v in x['streams'].values()))
 if not healthy:raise ValueError('接收器不新鲜或已锁定，请检查 source_fault；禁止自动续接旧建图状态')
except (OSError,ValueError,KeyError) as e:
 print('预检未启动：'+str(e));raise SystemExit(2)
PY_CHECK
/usr/bin/python3 m1_preflight/airy_adapter/audit_clocks.py > artifacts/real_sensors/clock_audit_summary.json
/usr/bin/python3 m1_preflight/airy_adapter/prepare_clock_profile.py \
 --audit artifacts/real_sensors/clock_audit.json --output artifacts/real_sensors/clock_profile.json
/usr/bin/python3 m1_preflight/airy_adapter/adapter_node.py \
 --profile artifacts/real_sensors/clock_profile.json --status artifacts/real_sensors/adapter_status.json \
 --seconds 200 > artifacts/real_sensors/adapter_preflight.log 2>&1 &
M1_PREFLIGHT_ADAPTER_PID=$!
trap 'kill "$M1_PREFLIGHT_ADAPTER_PID" 2>/dev/null || true; wait "$M1_PREFLIGHT_ADAPTER_PID" 2>/dev/null || true' EXIT
# 只终止本入口启动的子进程，原始接收器继续运行。
M1_INPUT_RESULT=0
/usr/bin/python3 m1_preflight/airy_adapter/check_live.py --seconds 180 \
 --profile artifacts/real_sensors/clock_profile.json --status artifacts/real_sensors/adapter_status.json \
 --bridge-status artifacts/real_sensors/bridge_status.json --output artifacts/real_sensors/live_preflight.json || M1_INPUT_RESULT=$?
M1_CALIBRATION_RESULT=0
/usr/bin/python3 m1_preflight/airy_adapter/prepare_mapping.py \
 --upstream-config src/slam/src/config/config.yaml --output artifacts/real_sensors/front_mapping.yaml || M1_CALIBRATION_RESULT=$?
if [ "$M1_INPUT_RESULT" -ne 0 ] || [ "$M1_CALIBRATION_RESULT" -ne 0 ]; then
 echo '建图前置未通过，详见 live_preflight.json 和标定检查输出。'
 exit 2
fi
# 软件时间映射仍不能证明传感器硬件同步或实际时延；不提供整机启动快捷方式。
echo '输入与外参检查通过；仍须独立验收同步误差及建图结果。未启动建图。'
