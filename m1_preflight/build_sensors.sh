#!/usr/bin/env bash
# 编译固定版本的 AIRY 驱动，不运行节点，也不修改雷达配置。
set -eo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
cd "$M1_WORKSPACE/sensors"
export CPATH="$PWD/deps/usr/include:$M1_WORKSPACE/deps/usr/include:${CPATH:-}"
export LIBRARY_PATH="$PWD/deps/usr/lib/aarch64-linux-gnu:$M1_WORKSPACE/deps/usr/lib/aarch64-linux-gnu:${LIBRARY_PATH:-}"
/usr/bin/python3 "$M1_WORKSPACE/m1_preflight/prepare_sensor_dependencies.py"
export CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1
colcon --log-base log build --base-paths src/rslidar_msg src/rslidar_sdk \
  --build-base build --install-base install --executor sequential \
  --cmake-args -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release \
  -DPOINT_TYPE=XYZIRT -DENABLE_IMU_DATA_PARSE=ON \
  -DPython3_EXECUTABLE=/usr/bin/python3 -DPYTHON_EXECUTABLE=/usr/bin/python3 \
  2>&1 | tee "$M1_WORKSPACE/artifacts/airy_build.log"
