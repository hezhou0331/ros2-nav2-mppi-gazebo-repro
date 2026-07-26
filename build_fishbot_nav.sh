#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
echo "build_fishbot_nav.sh is retained for compatibility; building ATEC A2 + P7 instead." >&2
exec "$repo_dir/build_atec_a2_p7_nav.sh" "$@"
