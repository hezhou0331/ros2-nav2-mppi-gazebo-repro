#!/usr/bin/env bash
set -euo pipefail

repro_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
gui_mode=${NAV_GUI:-1}

if [[ "$gui_mode" == "0" ]]; then
  headless=True
  use_rviz=False
else
  headless=False
  use_rviz=True
fi

# VS Code is installed as a Snap. Its terminal exports GTK/GIO paths from
# core20, which are ABI-incompatible with Ubuntu 24.04 ROS GUI processes.
exec env -i \
  HOME="${HOME}" \
  USER="${USER:-hezhou}" \
  LOGNAME="${LOGNAME:-hezhou}" \
  SHELL=/bin/bash \
  LANG="${LANG:-C.UTF-8}" \
  TERM="${TERM:-xterm-256color}" \
  DISPLAY="${DISPLAY:-}" \
  WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}" \
  XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}" \
  DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
  XAUTHORITY="${XAUTHORITY:-}" \
  PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  REPRO_DIR="$repro_dir" \
  NAV_HEADLESS="$headless" \
  NAV_USE_RVIZ="$use_rviz" \
  bash --noprofile --norc -c '
    set -eo pipefail
    source /opt/ros/jazzy/setup.bash
    set -u
    export TURTLEBOT3_MODEL=waffle
    exec ros2 launch nav2_bringup tb3_simulation_launch.py \
      headless:="$NAV_HEADLESS" \
      use_rviz:="$NAV_USE_RVIZ" \
      slam:=False \
      params_file:="$REPRO_DIR/mppi_waffle.yaml"
  '
