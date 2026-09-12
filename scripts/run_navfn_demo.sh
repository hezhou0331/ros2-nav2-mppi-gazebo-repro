#!/usr/bin/env bash
set -eo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ! -f "$root/third_party/genisom_roamerx_open/src/navigation/src/navigo_navfn_planner/src/navfn.cpp" ]]; then
  echo 'Run ./scripts/fetch_roamerx.sh first.' >&2
  exit 1
fi
if [[ -z ${ROS_DISTRO:-} ]]; then
  if [[ -f /opt/ros/humble/setup.bash ]]; then
    source /opt/ros/humble/setup.bash
  elif [[ -f /opt/ros/jazzy/setup.bash ]]; then
    source /opt/ros/jazzy/setup.bash
  else
    echo 'ROS 2 Humble or Jazzy development environment is required.' >&2
    exit 1
  fi
fi
set -u
cmake -S "$root/experiments/navfn" -B "$root/build/navfn" \
  -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=/usr/bin/python3
cmake --build "$root/build/navfn" -j2
"$root/build/navfn/roamerx_offline_demo" "$root/artifacts/navfn"
/usr/bin/python3 "$root/experiments/navfn/plot.py" "$root/artifacts/navfn" "$root/artifacts/navfn/result.png"
