#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
trial=""
artifact_dir=""
use_gui=false
use_rviz=false
acknowledge_planar_proxy=false
launch_pid=""
publisher_pid=""

usage() {
  cat <<EOF
Usage: $0 --trial ramp_up|ramp_down|stairs_up --acknowledge-planar-proxy [options]

Options:
  --artifact-dir ABSOLUTE_PATH
  --use-gui true|false
  --use-rviz true|false

This is a rigid-body simulation probe, not an A2 gait validation. The explicit
acknowledgement flag is required so its result cannot be mistaken for a real
quadruped terrain capability.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --trial)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      trial=$2
      shift 2
      ;;
    --artifact-dir)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      artifact_dir=$2
      shift 2
      ;;
    --use-gui)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      use_gui=$2
      shift 2
      ;;
    --use-rviz)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      use_rviz=$2
      shift 2
      ;;
    --acknowledge-planar-proxy)
      acknowledge_planar_proxy=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ "$acknowledge_planar_proxy" == true ]] || {
  echo "Refusing terrain motion without --acknowledge-planar-proxy." >&2
  exit 2
}
[[ "$use_gui" == true || "$use_gui" == false ]] || {
  echo "--use-gui must be true or false" >&2
  exit 2
}
[[ "$use_rviz" == true || "$use_rviz" == false ]] || {
  echo "--use-rviz must be true or false" >&2
  exit 2
}

case "$trial" in
  ramp_up)
    spawn_x=3.45; spawn_y=3.0; spawn_z=0.56; spawn_yaw=3.14159
    velocity=0.10; duration=34; expected_direction=negative_x
    ;;
  ramp_down)
    spawn_x=0.85; spawn_y=3.0; spawn_z=0.95; spawn_yaw=0.0
    velocity=0.08; duration=30; expected_direction=positive_x
    ;;
  stairs_up)
    spawn_x=-3.65; spawn_y=2.9; spawn_z=0.56; spawn_yaw=0.0
    velocity=0.08; duration=38; expected_direction=positive_x
    ;;
  *)
    echo "--trial must be ramp_up, ramp_down, or stairs_up" >&2
    exit 2
    ;;
esac

if [[ -z "$artifact_dir" ]]; then
  artifact_dir="$repo_dir/artifacts/terrain_${trial}_$(date -u +%Y%m%dT%H%M%SZ)_$$"
elif [[ "$artifact_dir" != /* ]]; then
  echo "--artifact-dir must be an absolute path" >&2
  exit 2
fi
mkdir -p "$artifact_dir/logs/ros"
artifact_dir=$(realpath "$artifact_dir")

cleanup() {
  set +e
  [[ -n "$publisher_pid" ]] && kill -INT "$publisher_pid" 2>/dev/null
  [[ -n "$publisher_pid" ]] && wait "$publisher_pid" 2>/dev/null
  if [[ -n "$launch_pid" ]] && kill -0 "$launch_pid" 2>/dev/null; then
    kill -INT -- "-$launch_pid" 2>/dev/null
    for _ in {1..50}; do
      kill -0 "$launch_pid" 2>/dev/null || break
      sleep 0.2
    done
    kill -TERM -- "-$launch_pid" 2>/dev/null || true
    wait "$launch_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

unset CONDA_PREFIX CONDA_DEFAULT_ENV PYTHONPATH
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-$(( ($$ % 100) + 120 ))}"
export GZ_PARTITION="${GZ_PARTITION:-atec_terrain_${trial}_$(date -u +%Y%m%dT%H%M%SZ)_$$}"
export ROS_LOG_DIR="$artifact_dir/logs/ros"
set +u
source /opt/ros/jazzy/setup.bash
source "$repo_dir/install/setup.bash"
set -u

setsid ros2 launch independent_nav_bringup mapping.launch.py \
  use_gui:="$use_gui" use_rviz:="$use_rviz" \
  spawn_x:="$spawn_x" spawn_y:="$spawn_y" spawn_z:="$spawn_z" \
  spawn_yaw:="$spawn_yaw" >"$artifact_dir/logs/terrain_launch.log" 2>&1 &
launch_pid=$!

pose_line() {
  gz model -m atec_a2_p7 -p --force-version 8 2>/dev/null | awk '
    /Pose \[/ {
      getline; gsub(/\[|\]/, ""); xyz=$0
      getline; gsub(/\[|\]/, ""); print xyz, $0
    }'
}

sample_pose() {
  local pose=""
  for _ in {1..10}; do
    pose=$(pose_line)
    if [[ -n "$pose" ]]; then
      printf '%s\n' "$pose"
      return 0
    fi
    sleep 0.2
  done
  return 1
}

for _ in {1..45}; do
  [[ -n "$(sample_pose || true)" ]] && break
  kill -0 "$launch_pid" 2>/dev/null || {
    echo "Terrain launch exited before the robot spawned" >&2
    exit 1
  }
  sleep 1
done
[[ -n "$(sample_pose || true)" ]] || {
  echo "Robot pose was unavailable after 45 seconds" >&2
  exit 1
}

# The safety supervisor deliberately publishes false for five seconds before
# enabling motion. Let scan, odom and all gate states become fresh first.
sleep 8
printf 'sample\tx\ty\tz\troll\tpitch\tyaw\n' >"$artifact_dir/terrain_poses.tsv"
read -r x y z roll pitch yaw <<<"$(sample_pose)"
printf '0\t%s\t%s\t%s\t%s\t%s\t%s\n' "$x" "$y" "$z" "$roll" "$pitch" "$yaw" \
  >>"$artifact_dir/terrain_poses.tsv"

ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: $velocity}}" >"$artifact_dir/logs/command.log" 2>&1 &
publisher_pid=$!

for ((sample=1; sample<=duration; sample++)); do
  sleep 1
  read -r x y z roll pitch yaw <<<"$(sample_pose)"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$sample" "$x" "$y" "$z" "$roll" "$pitch" "$yaw" \
    >>"$artifact_dir/terrain_poses.tsv"
done

kill -INT "$publisher_pid" 2>/dev/null || true
wait "$publisher_pid" 2>/dev/null || true
publisher_pid=""
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist '{}' \
  >"$artifact_dir/logs/zero_command.log" 2>&1

/usr/bin/python3 - \
  "$trial" "$expected_direction" "$velocity" "$duration" \
  "$artifact_dir/terrain_poses.tsv" "$artifact_dir/terrain_probe.json" <<'PY'
import csv
import json
import math
import os
import sys
from pathlib import Path

trial, direction, velocity, duration, samples_path, output_path = sys.argv[1:]
with open(samples_path, encoding="utf-8") as stream:
    samples = [
        {key: float(value) for key, value in row.items()}
        for row in csv.DictReader(stream, delimiter="\t")
    ]
first = samples[0]
last = samples[-1]
signed_progress = (
    first["x"] - last["x"] if direction == "negative_x"
    else last["x"] - first["x"]
)
z_change = last["z"] - first["z"]
max_abs_pitch = max(abs(item["pitch"]) for item in samples)
max_z = max(item["z"] for item in samples)

if trial == "ramp_up":
    proxy_pass = signed_progress >= 2.4 and z_change >= 0.20 and max_abs_pitch <= 0.45
elif trial == "ramp_down":
    proxy_pass = signed_progress >= 2.4 and z_change <= -0.20 and max_abs_pitch <= 0.45
else:
    proxy_pass = signed_progress >= 2.2 and max_z - first["z"] >= 0.10 and max_abs_pitch <= 0.60

payload = {
    "schema_version": 1,
    "trial": trial,
    "status": "proxy_pass" if proxy_pass else "proxy_failed",
    "proxy_trial_pass": proxy_pass,
    "simulation_proxy": "gz-sim-velocity-control-system",
    "is_quadruped_gait_validation": False,
    "safe_for_real_robot": False,
    "real_a2_capability": "unverified",
    "command_path": "/cmd_vel -> velocity_gate -> /platform/cmd_vel -> /sim/cmd_vel",
    "parameters": {
        "command_linear_x_mps": float(velocity),
        "duration_s": float(duration),
        "expected_direction": direction,
    },
    "sample_count": len(samples),
    "first_pose": first,
    "last_pose": last,
    "signed_progress_m": round(signed_progress, 4),
    "horizontal_distance_m": round(
        math.hypot(last["x"] - first["x"], last["y"] - first["y"]), 4
    ),
    "z_change_m": round(z_change, 4),
    "min_z_m": round(min(item["z"] for item in samples), 4),
    "max_z_m": round(max_z, 4),
    "max_abs_roll_rad": round(max(abs(item["roll"]) for item in samples), 4),
    "max_abs_pitch_rad": round(max_abs_pitch, 4),
    "reason": (
        "Rigid planar proxy met this diagnostic threshold; this is not gait proof."
        if proxy_pass else
        "Rigid planar proxy did not meet the terrain diagnostic threshold."
    ),
}
output = Path(output_path)
temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
os.replace(temporary, output)
print(json.dumps(payload, indent=2))
PY

echo "Terrain proxy probe completed: $artifact_dir"
