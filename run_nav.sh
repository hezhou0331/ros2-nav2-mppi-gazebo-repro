#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
gui_mode=${NAV_GUI:-1}

if [[ "$gui_mode" == "0" ]]; then
  use_gui=false
else
  use_gui=true
fi

echo "run_nav.sh is retained for compatibility; starting ATEC A2 + P7 mapping." >&2
exec "$repo_dir/run_mapping.sh" use_gui:="$use_gui" "$@"
