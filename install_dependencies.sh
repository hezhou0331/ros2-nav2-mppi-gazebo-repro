#!/usr/bin/env bash
set -euo pipefail

if ! apt-cache show ros-jazzy-desktop >/dev/null 2>&1; then
  echo "The ROS 2 Jazzy apt repository is not configured." >&2
  echo "Add it first: https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html" >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y \
  python3-yaml \
  ros-jazzy-desktop \
  ros-jazzy-navigation2 \
  ros-jazzy-nav2-bringup \
  ros-jazzy-nav2-regulated-pure-pursuit-controller \
  ros-jazzy-slam-toolbox \
  ros-jazzy-pointcloud-to-laserscan \
  ros-jazzy-ros-gz-sim \
  ros-jazzy-ros-gz-bridge \
  ros-jazzy-joint-state-publisher \
  ros-jazzy-robot-state-publisher \
  ros-jazzy-xacro

echo "Dependencies installed. Run ./build_atec_a2_p7_nav.sh, then ./validate_atec_a2_p7_nav.sh."
