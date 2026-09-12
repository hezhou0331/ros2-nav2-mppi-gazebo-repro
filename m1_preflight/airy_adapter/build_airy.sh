#!/usr/bin/env bash
# 仅构建 AIRY 独立副本，不改固定上游或已有 20 包安装树。
set -eo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../env.sh"
cd "$M1_WORKSPACE"
/usr/bin/python3 m1_preflight/airy_adapter/apply_roamerx_patch.py --source src/slam/src --output src_airy/robot_slam
export CMAKE_BUILD_PARALLEL_LEVEL=2 MAKEFLAGS=-j2
colcon --log-base log_airy build --base-paths src_airy --build-base build_airy --install-base install_airy \
 --executor sequential --packages-select robot_slam --cmake-args \
 -DOpenCV_DIR="$M1_WORKSPACE/deps/usr/lib/cmake/opencv4" -DBUILD_TESTING=OFF \
 -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=/usr/bin/python3 -DPYTHON_EXECUTABLE=/usr/bin/python3
