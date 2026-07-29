#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

unset CONDA_PREFIX CONDA_DEFAULT_ENV PYTHONPATH
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
set +u
source /opt/ros/jazzy/setup.bash
set -u

cd "$repo_dir"
colcon build --symlink-install \
  --cmake-clean-cache \
  --packages-select \
  atec_a2_p7_description \
  atec_a2_sdk2_adapter \
  independent_nav_bringup \
  --cmake-args \
  -DPython3_EXECUTABLE=/usr/bin/python3
