#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
unset CONDA_PREFIX CONDA_DEFAULT_ENV PYTHONPATH
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export GZ_PARTITION="${GZ_PARTITION:-atec_a2_p7_independent_nav}"
set +u
source /opt/ros/jazzy/setup.bash
source "$repo_dir/install/setup.bash"
set -u
exec ros2 launch independent_nav_bringup mapping.launch.py "$@"
