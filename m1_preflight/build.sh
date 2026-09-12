#!/usr/bin/env bash
set -eo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
cd "$M1_WORKSPACE"
if [[ ! -f deps/cv_bridge/share/cv_bridge/cmake/cv_bridgeConfig.cmake ]]; then
  echo "Build matching cv_bridge with bash m1_preflight/build_cv_bridge.sh first." >&2
  exit 1
fi
export CMAKE_BUILD_PARALLEL_LEVEL=2 MAKEFLAGS=-j2
colcon --log-base log_preflight build --base-paths src \
  --build-base build_preflight --install-base install_preflight \
  --executor sequential --continue-on-error "$@" --cmake-args \
  -Dcv_bridge_DIR="$M1_WORKSPACE/deps/cv_bridge/share/cv_bridge/cmake" \
  -DOpenCV_DIR="$M1_WORKSPACE/deps/usr/lib/cmake/opencv4" \
  -DCMAKE_MODULE_PATH="$M1_WORKSPACE/m1_preflight/cmake" \
  -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release \
  -DPython3_EXECUTABLE=/usr/bin/python3 -DPYTHON_EXECUTABLE=/usr/bin/python3 \
  2>&1 | tee "$M1_WORKSPACE/artifacts/preflight_build.log"
