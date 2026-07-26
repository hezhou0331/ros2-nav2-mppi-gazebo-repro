#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
artifact_dir=""
xvfb_pid=""
openbox_pid=""
ffmpeg_pid=""
layout_pid=""
demo_pid=""

usage() {
  cat <<EOF
Usage: $0 [--artifact-dir /absolute/path]

Runs the complete A2 + P7 mapping/navigation demo in an isolated Xvfb display
and records the Gazebo and RViz windows side by side.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --artifact-dir)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      artifact_dir=$2
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

if [[ -z "$artifact_dir" ]]; then
  artifact_dir="$repo_dir/artifacts/atec_demo_$(date -u +%Y%m%dT%H%M%SZ)_$$"
elif [[ "$artifact_dir" != /* ]]; then
  echo "--artifact-dir must be an absolute path" >&2
  exit 2
fi
mkdir -p "$artifact_dir/logs"
artifact_dir=$(realpath "$artifact_dir")

recording_report="$artifact_dir/recording_report.json"
video="$artifact_dir/atec_a2_p7_end_to_end.mp4"
probe_file="${video}.ffprobe.json"
visual_file="${video}.visual.json"
thumbnail="$artifact_dir/atec_a2_p7_end_to_end_thumbnail.png"
hash_file="${video}.sha256"
inner_run_report="$artifact_dir/run_report.json"
recording_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
current_phase="preflight"
recording_succeeded=false

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-$(( ($$ % 100) + 10 ))}"
export GZ_PARTITION="${GZ_PARTITION:-atec_recording_$(date -u +%Y%m%dT%H%M%SZ)_$$}"

cleanup() {
  set +e
  [[ -n "$demo_pid" ]] && kill -INT "$demo_pid" 2>/dev/null
  [[ -n "$demo_pid" ]] && wait "$demo_pid" 2>/dev/null
  [[ -n "$ffmpeg_pid" ]] && kill -INT "$ffmpeg_pid" 2>/dev/null
  [[ -n "$ffmpeg_pid" ]] && wait "$ffmpeg_pid" 2>/dev/null
  [[ -n "$layout_pid" ]] && kill -TERM "$layout_pid" 2>/dev/null
  [[ -n "$layout_pid" ]] && wait "$layout_pid" 2>/dev/null
  [[ -n "$openbox_pid" ]] && kill -TERM "$openbox_pid" 2>/dev/null
  [[ -n "$openbox_pid" ]] && wait "$openbox_pid" 2>/dev/null
  [[ -n "$xvfb_pid" ]] && kill -TERM "$xvfb_pid" 2>/dev/null
  [[ -n "$xvfb_pid" ]] && wait "$xvfb_pid" 2>/dev/null
}

write_recording_report() {
  local exit_code=$1
  local finished_at status failed_phase
  finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  status="failed"
  failed_phase="$current_phase"
  if [[ "$recording_succeeded" == true && "$exit_code" -eq 0 ]]; then
    status="passed"
    failed_phase=""
  fi

  /usr/bin/python3 - \
    "$recording_report" "$recording_started_at" "$finished_at" "$status" \
    "$exit_code" "$current_phase" "$failed_phase" "$artifact_dir" \
    "$ROS_DOMAIN_ID" "$GZ_PARTITION" "$video" "$probe_file" \
    "$visual_file" "$thumbnail" "$hash_file" "$inner_run_report" <<'PY'
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
    phase,
    failed_phase,
    artifact_dir,
    ros_domain_id,
    gz_partition,
    video,
    probe,
    visual,
    thumbnail,
    checksum,
    inner_run_report,
) = sys.argv[1:]


def artifact(path_name):
    path = Path(path_name)
    exists = path.is_file()
    return {
        "path": str(path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else None,
    }


output = Path(output_name)
payload = {
    "schema_version": 1,
    "success": status == "passed",
    "status": status,
    "started_at": started_at,
    "finished_at": finished_at,
    "exit_code": int(exit_code),
    "phase": phase,
    "failed_phase": failed_phase or None,
    "artifact_dir": artifact_dir,
    "environment": {
        "ros_domain_id": int(ros_domain_id) if ros_domain_id.isdigit() else ros_domain_id,
        "gz_partition": gz_partition,
    },
    "artifacts": {
        "video": artifact(video),
        "ffprobe": artifact(probe),
        "visual": artifact(visual),
        "thumbnail": artifact(thumbnail),
        "sha256": artifact(checksum),
        "inner_run_report": artifact(inner_run_report),
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
  cleanup
  if [[ "$recording_succeeded" != true && "$exit_code" -eq 0 ]]; then
    exit_code=1
  fi
  if ! write_recording_report "$exit_code"; then
    echo "Unable to write recording report: $recording_report" >&2
    [[ "$exit_code" -ne 0 ]] || exit_code=1
  elif [[ "$recording_succeeded" != true ]]; then
    echo "ATEC recording failed during $current_phase; report: $recording_report" >&2
  fi
  exit "$exit_code"
}
trap 'on_exit "$?"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

for command in Xvfb openbox wmctrl xdotool ffmpeg ffprobe xauth mcookie; do
  command -v "$command" >/dev/null || {
    echo "Missing $command. Run $repo_dir/tools/install_recording_dependencies.sh" >&2
    exit 1
  }
done

xauthority="$artifact_dir/.recording.Xauthority"
: >"$xauthority"
export XAUTHORITY="$xauthority"
export LIBGL_ALWAYS_SOFTWARE=1
export QT_X11_NO_MITSHM=1

current_phase="xvfb_start"
for display_number in {99..109}; do
  [[ -e "/tmp/.X11-unix/X$display_number" ]] && continue
  cookie=$(mcookie)
  xauth -f "$xauthority" add "$(hostname)/unix:$display_number" MIT-MAGIC-COOKIE-1 "$cookie"
  xauth -f "$xauthority" add ":$display_number" MIT-MAGIC-COOKIE-1 "$cookie"
  Xvfb ":$display_number" -screen 0 1920x1080x24 -nolisten tcp \
    -auth "$xauthority" >"$artifact_dir/logs/xvfb.log" 2>&1 &
  candidate_pid=$!
  sleep 1
  if kill -0 "$candidate_pid" 2>/dev/null; then
    xvfb_pid=$candidate_pid
    export DISPLAY=":$display_number"
    break
  fi
  wait "$candidate_pid" 2>/dev/null || true
done

[[ -n "$xvfb_pid" ]] || { echo "Unable to start an isolated Xvfb display" >&2; exit 1; }

current_phase="window_manager_start"
openbox --sm-disable >"$artifact_dir/logs/openbox.log" 2>&1 &
openbox_pid=$!

window_manager_ready=false
for _ in {1..50}; do
  if kill -0 "$openbox_pid" 2>/dev/null && wmctrl -m >/dev/null 2>&1; then
    window_manager_ready=true
    break
  fi
  sleep 0.2
done
[[ "$window_manager_ready" == true ]] || {
  echo "Openbox did not become ready; see logs/openbox.log" >&2
  exit 1
}

layout_log="$artifact_dir/logs/window_layout.tsv"
layout_ready_file="$artifact_dir/logs/window_layout.ready"
: >"$layout_log"
rm -f "$layout_ready_file"

find_window() {
  local pattern=$1
  wmctrl -lx 2>/dev/null | awk -v pattern="$pattern" \
    'tolower($0) ~ pattern { print $1; exit }'
}

layout_windows() {
  while true; do
    local gazebo_id rviz_id
    gazebo_id=$(find_window "gazebo|gz sim|gz-sim" || true)
    rviz_id=$(find_window "rviz" || true)
    if [[ -n "$gazebo_id" && -n "$rviz_id" ]]; then
      if wmctrl -i -r "$gazebo_id" -b remove,maximized_vert,maximized_horz 2>/dev/null \
          && wmctrl -i -r "$rviz_id" -b remove,maximized_vert,maximized_horz 2>/dev/null \
          && wmctrl -i -r "$gazebo_id" -e 0,0,0,960,1080 2>/dev/null \
          && wmctrl -i -r "$rviz_id" -e 0,960,0,960,1080 2>/dev/null; then
        detected_at=$(date +%s)
        printf '%s\t%s\t%s\n' "$detected_at" "$gazebo_id" "$rviz_id" >>"$layout_log"
        printf '%s\t%s\t%s\n' "$detected_at" "$gazebo_id" "$rviz_id" \
          >"${layout_ready_file}.tmp"
        mv "${layout_ready_file}.tmp" "$layout_ready_file"
      fi
    fi
    sleep 1
  done
}
layout_windows &
layout_pid=$!

current_phase="recording_start"
ffmpeg -hide_banner -loglevel warning -y \
  -f x11grab -framerate 25 -video_size 1920x1080 \
  -i "${DISPLAY}.0+0,0" -an \
  -c:v libx264 -preset veryfast -pix_fmt yuv420p -movflags +faststart \
  "$video" >"$artifact_dir/logs/ffmpeg.log" 2>&1 &
ffmpeg_pid=$!

# Fail before starting the several-minute demo if x11grab or the encoder could
# not be initialized. FFmpeg may not finalize the MP4 until it receives SIGINT,
# so liveness is the reliable startup check here.
sleep 2
if ! kill -0 "$ffmpeg_pid" 2>/dev/null; then
  set +e
  wait "$ffmpeg_pid"
  ffmpeg_status=$?
  set -e
  ffmpeg_pid=""
  echo "FFmpeg failed during startup (exit $ffmpeg_status); see logs/ffmpeg.log" >&2
  exit 1
fi

current_phase="demo_start"
"$repo_dir/run_atec_end_to_end_demo.sh" --artifact-dir "$artifact_dir" \
  --use-gui true --use-rviz true \
  > >(tee "$artifact_dir/logs/end_to_end.log") 2>&1 &
demo_pid=$!

current_phase="window_wait"
window_deadline=$((SECONDS + 120))
while [[ ! -s "$layout_ready_file" && "$SECONDS" -lt "$window_deadline" ]]; do
  kill -0 "$demo_pid" 2>/dev/null || break
  kill -0 "$ffmpeg_pid" 2>/dev/null || break
  sleep 1
done

if [[ ! -s "$layout_ready_file" ]]; then
  kill -INT "$demo_pid" 2>/dev/null || true
  set +e
  wait "$demo_pid"
  demo_status=$?
  set -e
  demo_pid=""
  echo "Gazebo and RViz were not both visible within 120 seconds; see $layout_log" >&2
  exit 1
fi

current_phase="demo_wait"
set +e
wait "$demo_pid"
demo_status=$?
set -e
demo_pid=""

current_phase="recording_finalize"
ffmpeg_status=0
ffmpeg_stopped_by_wrapper=false
if kill -0 "$ffmpeg_pid" 2>/dev/null; then
  ffmpeg_stopped_by_wrapper=true
  kill -INT "$ffmpeg_pid" 2>/dev/null || true
fi
set +e
wait "$ffmpeg_pid"
ffmpeg_status=$?
set -e
ffmpeg_pid=""

if [[ "$ffmpeg_status" -ne 0 && "$ffmpeg_stopped_by_wrapper" != true ]]; then
  echo "FFmpeg exited unexpectedly (exit $ffmpeg_status); see logs/ffmpeg.log" >&2
  exit 1
fi

[[ -s "$video" ]] || {
  echo "FFmpeg produced no recording: $video" >&2
  exit 1
}

current_phase="window_completion_check"
layout_detected_at=$(awk -F '\t' 'END {print $1}' "$layout_ready_file")
layout_age=$(( $(date +%s) - layout_detected_at ))
if (( layout_age > 30 )); then
  echo "Gazebo and RViz were not jointly visible near demo completion (last seen ${layout_age}s ago)" >&2
  exit 1
fi

current_phase="demo_result_check"
if [[ "$demo_status" -ne 0 ]]; then
  echo "End-to-end demo failed; recording and logs were retained in $artifact_dir" >&2
  exit "$demo_status"
fi

current_phase="media_validation"
"$repo_dir/tools/verify_recording.sh" "$video" --min-duration 90
thumbnail_time=$(/usr/bin/python3 - "$visual_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    print(json.load(stream)["sample_time_s"])
PY
)
current_phase="thumbnail"
ffmpeg -hide_banner -loglevel error -y -ss "$thumbnail_time" -i "$video" -frames:v 1 \
  "$thumbnail"
current_phase="checksum"
sha256sum "$video" >"$hash_file"

current_phase="artifact_validation"
for required_artifact in \
  "$video" "$probe_file" "$visual_file" "$thumbnail" "$hash_file" "$inner_run_report"; do
  [[ -s "$required_artifact" ]] || {
    echo "Required recording artifact is missing or empty: $required_artifact" >&2
    exit 1
  }
done
sha256sum -c "$hash_file" >/dev/null
/usr/bin/python3 - "$inner_run_report" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    report = json.load(stream)
if report.get("success") is not True or report.get("status") != "passed":
    raise SystemExit(f"Inner end-to-end run did not pass: {sys.argv[1]}")
PY

current_phase="completed"
recording_succeeded=true
echo "Recording completed: $video (report: $recording_report)"
