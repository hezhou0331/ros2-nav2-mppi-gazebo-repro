#!/usr/bin/env bash
set -eo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/env.sh"
cd "$M1_WORKSPACE"
commit=9800f67cea477c44cfb64e349854bcb6a09dc9ce
source_dir="$M1_WORKSPACE/deps_src/vision_opencv"
if [[ ! -d "$source_dir/.git" ]]; then
  mkdir -p "$M1_WORKSPACE/deps_src"
  git clone --filter=blob:none --no-checkout https://github.com/ros-perception/vision_opencv.git "$source_dir"
  git -C "$source_dir" checkout --detach "$commit"
fi
if [[ $(git -C "$source_dir" rev-parse HEAD) != "$commit" ]] ||
   [[ -n $(git -C "$source_dir" status --porcelain --untracked-files=no) ]]; then
  echo 'cv_bridge source differs from the reviewed commit; preserve it and inspect before building.' >&2
  exit 1
fi
export CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1
colcon --log-base log_cv_bridge build --base-paths "$source_dir/cv_bridge" \
  --build-base build_cv_bridge --install-base deps/cv_bridge --merge-install \
  --executor sequential --allow-overriding cv_bridge --cmake-args \
  -DBUILD_TESTING=OFF -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release \
  -DOpenCV_DIR="$M1_WORKSPACE/deps/usr/lib/cmake/opencv4" \
  -DPython3_EXECUTABLE=/usr/bin/python3 -DPYTHON_EXECUTABLE=/usr/bin/python3 \
  2>&1 | tee "$M1_WORKSPACE/artifacts/cv_bridge_build.log"
