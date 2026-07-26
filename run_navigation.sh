#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /absolute/path/to/map.yaml [use_gui:=true]" >&2
  exit 2
fi
unset CONDA_PREFIX CONDA_DEFAULT_ENV PYTHONPATH
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export GZ_PARTITION="${GZ_PARTITION:-atec_a2_p7_independent_nav}"
set +u
source /opt/ros/jazzy/setup.bash
source "$repo_dir/install/setup.bash"
set -u
exec ros2 launch independent_nav_bringup navigation.launch.py map:="$1" "${@:2}"
