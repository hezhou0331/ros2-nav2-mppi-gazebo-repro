#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y \
  ffmpeg \
  xvfb \
  openbox \
  wmctrl \
  xdotool \
  xauth \
  mesa-utils

echo "Recording dependencies installed."
