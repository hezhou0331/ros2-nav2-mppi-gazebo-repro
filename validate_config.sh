#!/usr/bin/env bash
set -euo pipefail

repro_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
config="$repro_dir/mppi_waffle.yaml"

if [[ -x /usr/bin/python3 ]]; then
  python_bin=/usr/bin/python3
else
  python_bin=$(command -v python3)
fi

"$python_bin" - "$config" <<'PY'
import sys
from pathlib import Path

import yaml

path = Path(sys.argv[1])
with path.open(encoding="utf-8") as stream:
    data = yaml.safe_load(stream)

controller = data["controller_server"]["ros__parameters"]
mppi = controller["FollowPath"]
local = data["local_costmap"]["local_costmap"]["ros__parameters"]
global_map = data["global_costmap"]["global_costmap"]["ros__parameters"]

expected = {
    "plugin": "nav2_mppi_controller::MPPIController",
    "motion_model": "DiffDrive",
    "batch_size": 512,
    "iteration_count": 5,
    "wz_max": 0.8,
    "wz_std": 0.40,
    "visualize": False,
    "PreferForwardCritic.cost_weight": 5.0,
}

for key, value in expected.items():
    actual = mppi.get(key)
    if actual != value:
        raise SystemExit(f"{key}: expected {value!r}, got {actual!r}")

period = 1.0 / controller["controller_frequency"]
if period > mppi["model_dt"]:
    raise SystemExit("controller period must not exceed MPPI model_dt")

for name, costmap in (("local", local), ("global", global_map)):
    if "voxel_layer" not in costmap["plugins"]:
        raise SystemExit(f"{name} costmap does not enable voxel_layer")
    if costmap["voxel_layer"]["plugin"] != "nav2_costmap_2d::VoxelLayer":
        raise SystemExit(f"{name} costmap has the wrong VoxelLayer plugin")

print("Configuration validation passed.")
PY

if [[ -f /opt/ros/jazzy/setup.bash ]]; then
  set +u
  source /opt/ros/jazzy/setup.bash
  set -u
  ros2 pkg prefix nav2_mppi_controller >/dev/null
  ros2 pkg prefix nav2_bringup >/dev/null
  ros2 pkg prefix ros_gz_sim >/dev/null
  echo "ROS package validation passed."
else
  echo "ROS package validation skipped: /opt/ros/jazzy/setup.bash not found."
fi
