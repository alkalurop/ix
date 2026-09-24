#!/bin/bash
# CRATER — daily celestial crate pass (5:00).
# Load with docs/examples/ai.ixamal.crater.plist
# Quit Traktor before NML. Quit Rekordbox before xml.
# Never runs the stem factory.
set -euo pipefail
cd "${HOME}/github/ixamal/ix"
export PYTHONPATH=crate
nice -n 10 python3 -m ix_crate crater --execute
