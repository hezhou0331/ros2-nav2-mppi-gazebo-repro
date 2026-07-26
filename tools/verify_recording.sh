#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 VIDEO.mp4 [--min-duration SECONDS]" >&2
}

[[ $# -ge 1 ]] || { usage; exit 2; }
video=$1
shift
min_duration=90

while [[ $# -gt 0 ]]; do
  case "$1" in
    --min-duration)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      min_duration=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

[[ -s "$video" ]] || { echo "Recording is missing or empty: $video" >&2; exit 1; }
command -v ffprobe >/dev/null || {
  echo "ffprobe is not installed; run tools/install_recording_dependencies.sh" >&2
  exit 1
}
command -v ffmpeg >/dev/null || {
  echo "ffmpeg is not installed; run tools/install_recording_dependencies.sh" >&2
  exit 1
}

probe_file="${video}.ffprobe.json"
ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,pix_fmt,width,height,avg_frame_rate \
  -show_entries format=duration,size -of json "$video" >"$probe_file"

/usr/bin/python3 - "$probe_file" "$min_duration" <<'PY'
import json
import sys
from fractions import Fraction

probe_path, minimum = sys.argv[1:]
with open(probe_path, encoding="utf-8") as stream:
    payload = json.load(stream)
streams = payload.get("streams", [])
if len(streams) != 1:
    raise SystemExit("Recording must contain one inspectable video stream")
stream = streams[0]
if stream.get("codec_name") != "h264":
    raise SystemExit(f"Expected H.264 video, got {stream.get('codec_name')!r}")
if stream.get("pix_fmt") != "yuv420p":
    raise SystemExit(f"Expected yuv420p pixels, got {stream.get('pix_fmt')!r}")
if (stream.get("width"), stream.get("height")) != (1920, 1080):
    raise SystemExit(
        f"Expected 1920x1080 video, got {stream.get('width')}x{stream.get('height')}"
    )
try:
    frame_rate = Fraction(stream.get("avg_frame_rate", ""))
except (TypeError, ValueError, ZeroDivisionError):
    raise SystemExit(
        f"Recording has invalid average frame rate {stream.get('avg_frame_rate')!r}"
    )
if frame_rate != Fraction(25, 1):
    raise SystemExit(
        f"Expected 25 fps average frame rate, got {stream.get('avg_frame_rate')!r}"
    )
duration = float(payload.get("format", {}).get("duration", 0.0))
if duration < float(minimum):
    raise SystemExit(f"Recording duration {duration:.1f}s is below {minimum}s")
print(f"Recording verified: {duration:.1f}s, 25 fps H.264 yuv420p 1920x1080")
PY

sample_time=$(/usr/bin/python3 - "$probe_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    duration = float(json.load(stream)["format"]["duration"])
print(round(max(1.0, min(duration - 1.0, duration * 0.5)), 3))
PY
)

left_frame=$(mktemp /tmp/atec_recording_left.XXXXXX.pgm)
right_frame=$(mktemp /tmp/atec_recording_right.XXXXXX.pgm)
cleanup_frames() {
  rm -f "$left_frame" "$right_frame"
}
trap cleanup_frames EXIT

ffmpeg -hide_banner -loglevel error -y -ss "$sample_time" -i "$video" \
  -frames:v 1 -vf "crop=960:1080:0:0,format=gray" "$left_frame"
ffmpeg -hide_banner -loglevel error -y -ss "$sample_time" -i "$video" \
  -frames:v 1 -vf "crop=960:1080:960:0,format=gray" "$right_frame"

visual_file="${video}.visual.json"
/usr/bin/python3 - "$left_frame" "$right_frame" "$sample_time" "$visual_file" <<'PY'
import json
import math
import sys
from pathlib import Path


def next_token(data, offset):
    while offset < len(data):
        if data[offset] == ord("#"):
            offset = data.index(b"\n", offset) + 1
        elif chr(data[offset]).isspace():
            offset += 1
        else:
            break
    start = offset
    while offset < len(data) and not chr(data[offset]).isspace():
        offset += 1
    return data[start:offset].decode("ascii"), offset


def pane_metrics(path):
    data = Path(path).read_bytes()
    offset = 0
    tokens = []
    for _ in range(4):
        token, offset = next_token(data, offset)
        tokens.append(token)
    if tokens[0] != "P5" or tuple(map(int, tokens[1:])) != (960, 1080, 255):
        raise SystemExit(f"Unexpected pane image format in {path}")
    offset += 2 if data[offset:offset + 2] == b"\r\n" else 1
    pixels = data[offset:]
    if len(pixels) != 960 * 1080:
        raise SystemExit(f"Unexpected pane pixel count in {path}: {len(pixels)}")
    count = len(pixels)
    total = sum(pixels)
    mean = total / count
    variance = max(0.0, sum(value * value for value in pixels) / count - mean * mean)
    metrics = {
        "mean_luma": round(mean, 3),
        "luma_stddev": round(math.sqrt(variance), 3),
        "minimum_luma": min(pixels),
        "maximum_luma": max(pixels),
    }
    if metrics["maximum_luma"] - metrics["minimum_luma"] < 25:
        raise SystemExit(f"Pane {path} has insufficient luma range: {metrics}")
    if metrics["luma_stddev"] < 8.0:
        raise SystemExit(f"Pane {path} appears blank or nearly uniform: {metrics}")
    return metrics


left_path, right_path, sample, output_path = sys.argv[1:]
payload = {
    "schema_version": 1,
    "success": True,
    "sample_time_s": float(sample),
    "left_gazebo_pane": pane_metrics(left_path),
    "right_rviz_pane": pane_metrics(right_path),
}
Path(output_path).write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(f"Recording panes verified at {sample}s; report written to {output_path}")
PY
