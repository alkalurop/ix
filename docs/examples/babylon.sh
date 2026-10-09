#!/bin/bash
# BABYLON — hygiene + optional STEMIT genre batches + full CRATER (MiK, mashups, decks).
#
# Default STEMIT=0 (no factory). Mixed In Key may stay open (read-only mikdb).
# Rekordbox/Traktor: AppleScript quit at the quit-decks phase (no prompt unless
# BABYLON_CONFIRM_DECK_QUIT=1 or --confirm-deck-quit). Click through save dialogs.
#
# From a Terminal (default): stays attached + stems .venv HUD when Tk is available.
#
#   docs/examples/babylon.sh
#   BABYLON_DETACH=1 docs/examples/babylon.sh   # background job (log only, no HUD)
#   BUDGET=100 docs/examples/babylon.sh
#
# Log: ~/local_tools/crate/reports/babylon-<utc>.log
#
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REPORTS="${HOME}/local_tools/crate/reports"
BUDGET="${BUDGET:-0}"
HYGIENE_SCRIPT="${ROOT}/docs/examples/library-hygiene.sh"
STEMS_PY="${HOME}/github/ixamal/stems/.venv/bin/python3"
if [[ -x "$STEMS_PY" ]]; then
  IX_PYTHON="$STEMS_PY"
else
  IX_PYTHON="$(command -v python3)"
fi

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      sed -n '2,15p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
  esac
done

mkdir -p "$REPORTS"
LOG="${LOG:-${REPORTS}/babylon-$(date -u +%Y%m%dT%H%M%SZ).log}"

print_eta() {
  PYTHONPATH=crate "$IX_PYTHON" -u <<'PY'
import os
from ix_crate.batch_notify import estimate_minutes

budget = int(os.environ.get("BUDGET", "0") or 0)
raw = (os.environ.get("STEMIT_BATCHES") or "").strip()
batches = [int(x) for x in raw.split() if x.strip()] if raw else None
follow = os.environ.get("FOLLOW", "") == "1"
hygiene = os.environ.get("SKIP_HYGIENE", "") != "1"
lo, hi = estimate_minutes(budget=budget, batches=batches, follow=follow, hygiene=hygiene)
print(f"ETA (rough): {lo}–{hi} min wall clock")
PY
}

if [[ "${PREFLIGHT:-}" == 1 ]]; then
  export PYTHONPATH=crate
  cd "$ROOT"
  PREFLIGHT=1 FOREGROUND=1 bash "$HYGIENE_SCRIPT" | tee "${REPORTS}/babylon-preflight-$(date -u +%Y%m%dT%H%M%SZ).log"
  exit 0
fi

if [[ "${FOREGROUND:-}" != 1 && "${BABYLON_DETACH:-}" != 1 && -t 0 ]]; then
  export FOREGROUND=1
fi

if [[ "${FOREGROUND:-}" != 1 ]]; then
  if pgrep -f 'Python.*-m py\.exec\.separate' >/dev/null; then
    echo "STEMIT factory already running (py.exec.separate). Stop it first." >&2
    exit 1
  fi
  export ROOT LOG REPORTS BUDGET SKIP_STEMIT SKIP_HYGIENE SKIP_CRATER FOLLOW STEMIT_BATCHES
  export BABYLON_NO_NOTIFY BABYLON_CONFIRM_DECK_QUIT IX_PYTHON
  export BABYLON_NO_GUI="${BABYLON_NO_GUI:-1}"
  "$IX_PYTHON" -c '
import os, sys
log, script = sys.argv[1], sys.argv[2]
if os.fork():
    os._exit(0)
os.setsid()
if os.fork():
    os._exit(0)
fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
os.dup2(fd, 1)
os.dup2(fd, 2)
os.close(fd)
env = os.environ.copy()
env["FOREGROUND"] = "1"
env["LOG"] = log
os.execvpe("/bin/bash", ["/bin/bash", script], env)
' "$LOG" "$0"
  echo "BABYLON started log=$LOG"
  print_eta
  echo "tail -f $LOG"
  exit 0
fi

cd "$ROOT"
export PYTHONPATH=crate

echo "BABYLON start $(date)  log=$LOG  python=$IX_PYTHON"
print_eta

args=(babylon --execute --log "$LOG" --budget "$BUDGET")
[[ "${SKIP_HYGIENE:-}" == 1 ]] && args+=(--skip-hygiene)
[[ "${SKIP_CRATER:-}" == 1 ]] && args+=(--skip-crater)
[[ "${SKIP_STEMIT:-}" == 1 ]] && args+=(--skip-stemit)
[[ "${FOLLOW:-}" == 1 ]] && args+=(--follow)
[[ -n "${STEMIT_BATCHES:-}" ]] && args+=(--stemit-batches "$STEMIT_BATCHES")
[[ "${BABYLON_NO_NOTIFY:-}" == 1 ]] && args+=(--no-notify)
[[ "${BABYLON_NO_GUI:-}" == 1 ]] && args+=(--no-gui)
[[ "${BABYLON_CONFIRM_DECK_QUIT:-}" == 1 ]] && args+=(--confirm-deck-quit)
nice -n 10 "$IX_PYTHON" -u -m ix_crate "${args[@]}"
exit $?
