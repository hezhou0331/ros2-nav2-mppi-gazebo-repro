#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
echo "validate_fishbot_nav.sh is retained for compatibility; validating ATEC A2 + P7 instead." >&2
exec "$repo_dir/validate_atec_a2_p7_nav.sh" "$@"
