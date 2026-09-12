#!/usr/bin/env bash
set -euo pipefail
exec ssh -o ConnectTimeout=10 -o BatchMode=yes nvidia@100.68.24.27 "$@"
