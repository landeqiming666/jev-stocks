#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$(uname -sm)" != "Darwin arm64" ]]; then
  echo "BUILD FAILED: requires macOS arm64" >&2
  exit 3
fi
exec python3 "$repo_root/vendors/jevdb/build.py" "$@"
