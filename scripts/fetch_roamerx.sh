#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
upstream="$root/third_party/genisom_roamerx_open"
readarray -t lock < <(python3 - "$root/upstream.lock.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); print(x['url']); print(x['commit'])
PY
)
if [[ -d "$upstream/.git" ]]; then
  if [[ -n $(git -C "$upstream" status --porcelain) ]]; then
    echo 'Upstream checkout has local changes; preserve them before fetching.' >&2
    exit 1
  fi
else
  mkdir -p "$(dirname "$upstream")"
  git clone --filter=blob:none --no-checkout "${lock[0]}" "$upstream"
fi
git -C "$upstream" fetch --depth 1 origin "${lock[1]}"
git -C "$upstream" sparse-checkout init --cone
git -C "$upstream" sparse-checkout set src script
git -C "$upstream" checkout --detach "${lock[1]}"
echo "RoamerX checked out at $(git -C "$upstream" rev-parse HEAD)"
