#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
artifact_dir=""
use_gui=false
use_rviz=false
stage_pid=""

usage() {
  cat <<EOF
Usage: $0 [--artifact-dir /absolute/path] [--use-gui true|false] [--use-rviz true|false]

Runs mapping, saves and validates the map, restarts the simulation, then sends
two Nav2 goals. The default artifact directory is
artifacts/atec_demo_<UTC timestamp>_<PID>.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --artifact-dir)
      [[ $# -ge 2 ]] || { echo "--artifact-dir requires a value" >&2; exit 2; }
      artifact_dir=$2
      shift 2
      ;;
    --use-gui)
      [[ $# -ge 2 ]] || { echo "--use-gui requires true or false" >&2; exit 2; }
      use_gui=$2
      shift 2
      ;;
    --use-rviz)
      [[ $# -ge 2 ]] || { echo "--use-rviz requires true or false" >&2; exit 2; }
      use_rviz=$2
      shift 2
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

for value in "$use_gui" "$use_rviz"; do
  [[ "$value" == true || "$value" == false ]] || {
    echo "--use-gui and --use-rviz accept only true or false" >&2
    exit 2
  }
done

if [[ -z "$artifact_dir" ]]; then
  artifact_dir="$repo_dir/artifacts/atec_demo_$(date -u +%Y%m%dT%H%M%SZ)_$$"
elif [[ "$artifact_dir" != /* ]]; then
  echo "--artifact-dir must be an absolute path" >&2
  exit 2
fi

mkdir -p "$artifact_dir/logs" "$artifact_dir/maps"
artifact_dir=$(realpath "$artifact_dir")
map_base="$repo_dir/maps/atec_practice_world"
artifact_map="$artifact_dir/maps/atec_practice_world.yaml"
mapping_report="$artifact_dir/mapping_patrol.json"
navigation_report="$artifact_dir/navigation_mission.json"
run_report="$artifact_dir/run_report.json"
run_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
current_stage="preflight"
run_succeeded=false

export GZ_PARTITION="${GZ_PARTITION:-atec_demo_$(date -u +%Y%m%dT%H%M%SZ)_$$}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-$(( ($$ % 200) + 20 ))}"
export ROS_LOG_DIR="$artifact_dir/logs/ros"
mkdir -p "$ROS_LOG_DIR"

stop_stage() {
  if [[ -z "$stage_pid" ]] || ! kill -0 "$stage_pid" 2>/dev/null; then
    stage_pid=""
    return
  fi
  # Let ROS launch propagate one orderly SIGINT to its children. Signaling the
  # whole process group here makes launch deliver a second signal to them.
  kill -INT "$stage_pid" 2>/dev/null || true
  for _ in {1..50}; do
    kill -0 "$stage_pid" 2>/dev/null || break
    sleep 0.2
  done
  if kill -0 "$stage_pid" 2>/dev/null; then
    kill -TERM -- "-$stage_pid" 2>/dev/null || true
  fi
  wait "$stage_pid" 2>/dev/null || true
  stage_pid=""
}

write_run_report() {
  local exit_code=$1
  local finished_at status failed_stage
  finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  status="failed"
  failed_stage="$current_stage"
  if [[ "$run_succeeded" == true && "$exit_code" -eq 0 ]]; then
    status="passed"
    failed_stage=""
  fi

  /usr/bin/python3 - \
    "$run_report" "$run_started_at" "$finished_at" "$status" \
    "$exit_code" "$current_stage" "$failed_stage" "$artifact_dir" \
    "$GZ_PARTITION" "$ROS_DOMAIN_ID" "$artifact_map" \
    "$mapping_report" "$navigation_report" <<'PY'
import json
import os
import sys
from pathlib import Path

(
    output_name,
    started_at,
    finished_at,
    status,
    exit_code,
    stage,
    failed_stage,
    artifact_dir,
    gz_partition,
    ros_domain_id,
    map_yaml,
    mapping_report,
    navigation_report,
) = sys.argv[1:]

output = Path(output_name)
payload = {
    "schema_version": 1,
    "success": status == "passed",
    "status": status,
    "started_at": started_at,
    "finished_at": finished_at,
    "exit_code": int(exit_code),
    "stage": stage,
    "failed_stage": failed_stage or None,
    "artifact_dir": artifact_dir,
    "environment": {
        "gz_partition": gz_partition,
        "ros_domain_id": int(ros_domain_id) if ros_domain_id.isdigit() else ros_domain_id,
    },
    "artifacts": {
        "map_yaml": map_yaml,
        "mapping_report": mapping_report,
        "navigation_report": navigation_report,
        "demo_report": str(Path(artifact_dir) / "demo_report.json"),
    },
}
temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
os.replace(temporary, output)
PY
}

on_exit() {
  local exit_code=$1
  trap - EXIT INT TERM
  set +e
  stop_stage
  if [[ "$run_succeeded" != true && "$exit_code" -eq 0 ]]; then
    exit_code=1
  fi
  if ! write_run_report "$exit_code"; then
    echo "Unable to write orchestration report: $run_report" >&2
    [[ "$exit_code" -ne 0 ]] || exit_code=1
  elif [[ "$run_succeeded" != true ]]; then
    echo "ATEC end-to-end demo failed during $current_stage; report: $run_report" >&2
  fi
  exit "$exit_code"
}
trap 'on_exit "$?"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

start_stage() {
  local name=$1
  shift
  # Background jobs inherit SIGINT as ignored from a non-interactive shell.
  # Reset it before exec so the launch process can perform an orderly shutdown.
  setsid env --default-signal=INT --default-signal=QUIT \
    "$@" >"$artifact_dir/logs/${name}_launch.log" 2>&1 &
  stage_pid=$!
  echo "Started $name stage (PID $stage_pid)."
}

if [[ ! -f "$repo_dir/install/setup.bash" ]]; then
  echo "Workspace is not built. Run $repo_dir/build_atec_a2_p7_nav.sh first." >&2
  exit 1
fi

current_stage="environment_setup"
unset CONDA_PREFIX CONDA_DEFAULT_ENV PYTHONPATH
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
set +u
source /opt/ros/jazzy/setup.bash
source "$repo_dir/install/setup.bash"
set -u

echo "Artifacts: $artifact_dir"
echo "Isolation: ROS_DOMAIN_ID=$ROS_DOMAIN_ID GZ_PARTITION=$GZ_PARTITION"
current_stage="mapping_launch"
start_stage mapping "$repo_dir/run_mapping.sh" \
  "use_gui:=$use_gui" "use_rviz:=$use_rviz"

current_stage="mapping_patrol"
ros2 run independent_nav_bringup mapping_patrol.py \
  --output "$mapping_report" --timeout 300 \
  --state-timeout 2.0 --odom-timeout 2.0 --scan-timeout 2.0 \
  2>&1 | tee "$artifact_dir/logs/mapping_patrol.log"

# Let SLAM publish its final optimized grid before saving it.
sleep 3
current_stage="map_save"
ros2 run independent_nav_bringup save_map.py \
  --output "$map_base" --timeout 30 \
  2>&1 | tee "$artifact_dir/logs/map_save.log"

current_stage="map_footprint_cleanup"
/usr/bin/python3 "$repo_dir/tools/clear_mapping_patrol_footprint.py" \
  --map "${map_base}.yaml" \
  --output "$artifact_dir/map_footprint_cleanup.json"

current_stage="map_validation"
/usr/bin/python3 "$repo_dir/tools/validate_demo_artifacts.py" \
  --map "${map_base}.yaml" \
  --mapping-report "$mapping_report" \
  --output "$artifact_dir/map_validation.json"

current_stage="map_snapshot"
cp "${map_base}.pgm" "${map_base}.yaml" "$artifact_dir/maps/"
current_stage="mapping_shutdown"
stop_stage
sleep 2

current_stage="navigation_launch"
start_stage navigation "$repo_dir/run_navigation.sh" "$artifact_map" \
  "use_gui:=$use_gui" "use_rviz:=$use_rviz"

current_stage="navigation_mission"
ros2 run independent_nav_bringup navigation_mission.py \
  --output "$navigation_report" --timeout 540 \
  --goal-timeout 240 --state-timeout 2.0 \
  2>&1 | tee "$artifact_dir/logs/navigation_mission.log"

current_stage="demo_validation"
/usr/bin/python3 "$repo_dir/tools/validate_demo_artifacts.py" \
  --map "$artifact_map" \
  --mapping-report "$mapping_report" \
  --navigation-report "$navigation_report" \
  --output "$artifact_dir/demo_report.json"

current_stage="navigation_shutdown"
stop_stage
current_stage="completed"
run_succeeded=true
echo "ATEC end-to-end demo passed. Reports: $artifact_dir/demo_report.json and $run_report"
