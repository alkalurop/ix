#!/bin/bash
# Traktor remix sets + ~/Music/Traktor/Samples → DJ crates
#
#   docs/examples/traktor-remix-crate.sh
#   docs/examples/traktor-remix-crate.sh --execute
#
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH=crate
exec python3 -u -m ix_crate traktor-remix-crate "$@"
