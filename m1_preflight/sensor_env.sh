#!/usr/bin/env bash
# 仅供 source 加载已构建的传感器库环境，不启动驱动。
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh" || return 1
if [[ ! -f "$M1_WORKSPACE/sensors/install/local_setup.bash" ]]; then
  echo 'Build the sensor workspace first.' >&2
  return 1
fi
source "$M1_WORKSPACE/sensors/install/local_setup.bash"
export LD_LIBRARY_PATH="$M1_WORKSPACE/sensors/deps/usr/lib/aarch64-linux-gnu:${LD_LIBRARY_PATH:-}"
